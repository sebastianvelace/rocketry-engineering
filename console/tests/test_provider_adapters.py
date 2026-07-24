import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    PermissionResultAllow,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    ToolPermissionContext,
    ToolUseBlock,
)

from gateway.providers.base import ProviderApproval
from gateway.providers.claude import (
    ClaudeAdapter,
    normalize_claude,
    normalize_sdk_message,
)
from gateway.providers.codex import CodexAdapter, normalize_codex
from gateway.providers.json_process import JsonLineProcess


class ProviderNormalizationTests(unittest.TestCase):
    def test_codex_thread_uses_current_workspace_write_preset(self):
        async def exercise():
            requests = []

            async def emit(event):
                pass

            async def approve(request):
                pass

            adapter = CodexAdapter(
                workspace=Path("/tmp"),
                event_sink=emit,
                approval_sink=approve,
            )

            async def start_process():
                pass

            async def send(payload):
                pass

            async def request(method, params, **kwargs):
                requests.append((method, params))
                if method == "thread/start":
                    return {"thread": {"id": "thread-1"}}
                return {}

            adapter.process.start = start_process
            adapter.process.send = send
            adapter._request = request
            await adapter.start()
            return requests

        requests = asyncio.run(exercise())
        thread_start = next(params for method, params in requests if method == "thread/start")
        self.assertEqual(thread_start["sandbox"], "workspace-write")

    def test_codex_catalog_drives_model_and_native_compaction(self):
        async def exercise():
            requests = []
            events = []

            async def emit(event):
                events.append(event)

            async def approve(request):
                pass

            adapter = CodexAdapter(
                workspace=Path("/tmp"),
                event_sink=emit,
                approval_sink=approve,
            )

            async def start_process():
                pass

            async def send(payload):
                pass

            async def request(method, params, **kwargs):
                requests.append((method, params))
                if method == "thread/start":
                    return {"thread": {"id": "thread-1"}}
                if method == "model/list":
                    return {
                        "data": [{
                            "id": "model-1",
                            "model": "gpt-test",
                            "displayName": "GPT Test",
                            "description": "Test model",
                            "isDefault": True,
                            "supportedReasoningEfforts": [],
                            "serviceTiers": [],
                        }]
                    }
                if method == "turn/start":
                    return {"turn": {"id": "turn-1"}}
                return {}

            adapter.process.start = start_process
            adapter.process.send = send
            adapter._request = request
            await adapter.start()
            await adapter.set_model("gpt-test")
            await adapter.send_turn("hello")
            await adapter.compact()
            return requests, events

        requests, events = asyncio.run(exercise())
        turn = next(params for method, params in requests if method == "turn/start")
        self.assertEqual(turn["model"], "gpt-test")
        self.assertTrue(any(method == "thread/compact/start" for method, _ in requests))
        capabilities = next(event for event in events if event.text == "Provider capabilities")
        self.assertEqual(capabilities.data["models"][0]["value"], "gpt-test")
        self.assertIn("compact", [item["name"] for item in capabilities.data["commands"]])

    def test_codex_normalizes_stream_tools_and_completion(self):
        delta = normalize_codex(
            {
                "method": "item/agentMessage/delta",
                "params": {"delta": "hello"},
            }
        )
        command = normalize_codex(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "id": "item-1",
                        "command": "bash tools/ci_check.sh",
                    }
                },
            }
        )
        completed = normalize_codex(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "id": "item-2",
                        "text": "done",
                    }
                },
            }
        )

        self.assertEqual((delta[0].type, delta[0].text), ("assistant_delta", "hello"))
        self.assertEqual((command[0].type, command[0].text), ("tool_started", "bash tools/ci_check.sh"))
        self.assertEqual((completed[0].type, completed[0].text), ("assistant_message", "done"))

    def test_claude_normalizes_partial_text_tool_and_result(self):
        partial = normalize_claude(
            {
                "type": "stream_event",
                "event": {"delta": {"type": "text_delta", "text": "hello"}},
            }
        )
        tool = normalize_claude(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {}}
                    ]
                },
            }
        )
        result = normalize_claude(
            {
                "type": "result",
                "result": "done",
                "session_id": "session-1",
                "usage": {"input_tokens": 2},
            }
        )

        self.assertEqual((partial[0].type, partial[0].text), ("assistant_delta", "hello"))
        self.assertEqual((tool[0].type, tool[0].text), ("tool_started", "Bash"))
        self.assertEqual(
            [event.type for event in result],
            ["assistant_message", "usage", "session"],
        )

    def test_codex_routes_native_approval_request(self):
        async def exercise():
            approvals = []

            async def emit(event):
                pass

            async def approve(request):
                approvals.append(request)

            adapter = CodexAdapter(
                workspace=Path("/tmp"),
                event_sink=emit,
                approval_sink=approve,
            )
            await adapter._on_message(
                {
                    "id": 41,
                    "method": "item/commandExecution/requestApproval",
                    "params": {"command": "git fetch", "reason": "network"},
                }
            )
            return approvals

        approvals = asyncio.run(exercise())
        self.assertEqual(
            approvals,
            [
                ProviderApproval(
                    request_id=41,
                    action="item/commandExecution/requestApproval",
                    details={"command": "git fetch", "reason": "network"},
                )
            ],
        )

    def test_codex_permission_approval_returns_requested_profile(self):
        async def exercise():
            sent = []

            async def emit(event):
                pass

            async def approve(request):
                pass

            adapter = CodexAdapter(
                workspace=Path("/tmp"),
                event_sink=emit,
                approval_sink=approve,
            )

            async def send(payload):
                sent.append(payload)

            adapter.process.send = send
            await adapter._on_message(
                {
                    "id": "permission-1",
                    "method": "item/permissions/requestApproval",
                    "params": {
                        "permissions": {"network": {"enabled": True}},
                        "reason": "Download dependencies",
                    },
                }
            )
            await adapter.resolve_approval(
                "permission-1",
                approved=True,
                for_session=True,
            )
            return sent

        sent = asyncio.run(exercise())
        self.assertEqual(
            sent,
            [
                {
                    "id": "permission-1",
                    "result": {
                        "permissions": {"network": {"enabled": True}},
                        "scope": "session",
                    },
                }
            ],
        )

    def test_claude_sdk_messages_use_same_event_contract(self):
        partial = normalize_sdk_message(
            StreamEvent(
                uuid="message-1",
                session_id="session-1",
                event={"delta": {"type": "text_delta", "text": "hello"}},
            )
        )
        tool = normalize_sdk_message(
            AssistantMessage(
                content=[
                    ToolUseBlock(
                        id="tool-1",
                        name="Bash",
                        input={"command": "pytest"},
                    )
                ],
                model="claude",
            )
        )
        result = normalize_sdk_message(
            ResultMessage(
                subtype="success",
                duration_ms=10,
                duration_api_ms=8,
                is_error=False,
                num_turns=1,
                session_id="session-1",
                result="done",
            )
        )

        self.assertEqual((partial[0].type, partial[0].text), ("assistant_delta", "hello"))
        self.assertEqual((tool[0].type, tool[0].text), ("tool_started", "Bash"))
        self.assertEqual(
            [event.type for event in result],
            ["assistant_message", "usage", "session"],
        )

    def test_claude_permission_waits_for_gateway_resolution(self):
        async def exercise():
            approvals = []
            adapter = None

            async def emit(event):
                pass

            async def approve(request):
                approvals.append(request)
                await adapter.resolve_approval(
                    request.request_id,
                    approved=True,
                    for_session=False,
                )

            adapter = ClaudeAdapter(
                workspace=Path("/tmp"),
                event_sink=emit,
                approval_sink=approve,
            )
            result = await adapter._request_permission(
                "Bash",
                {"command": "git fetch"},
                ToolPermissionContext(
                    tool_use_id="tool-1",
                    title="Network access",
                ),
            )
            return approvals, result

        approvals, result = asyncio.run(exercise())
        self.assertEqual(approvals[0].action, "Bash")
        self.assertEqual(approvals[0].details["input"], {"command": "git fetch"})
        self.assertIsInstance(result, PermissionResultAllow)
        self.assertEqual(result.updated_input, {"command": "git fetch"})

    def test_claude_discards_internal_status_and_compacts_init(self):
        self.assertEqual(
            normalize_sdk_message(
                SystemMessage(
                    subtype="status",
                    data={"status": "requesting", "large_internal_value": "x" * 1000},
                )
            ),
            [],
        )
        initialized = normalize_sdk_message(
            SystemMessage(
                subtype="init",
                data={
                    "session_id": "session-1",
                    "model": "claude",
                    "tools": ["Bash"] * 100,
                },
            )
        )
        self.assertEqual(
            initialized[0].data,
            {"session_id": "session-1", "model": "claude"},
        )
        self.assertEqual(initialized[0].raw, {})


class JsonLineProcessTests(unittest.TestCase):
    def test_process_round_trip_and_stderr_capture(self):
        async def exercise():
            messages = []
            logs = []
            received = asyncio.Event()

            async def on_message(payload):
                messages.append(payload)
                received.set()

            async def on_stderr(line):
                logs.append(line)

            code = (
                "import json,sys;"
                "line=sys.stdin.readline();"
                "print(json.dumps({'echo':json.loads(line)['value']}),flush=True);"
                "print('diagnostic',file=sys.stderr,flush=True)"
            )
            process = JsonLineProcess(
                [sys.executable, "-u", "-c", code],
                cwd=Path(tempfile.gettempdir()),
                on_message=on_message,
                on_stderr=on_stderr,
            )
            await process.start()
            await process.send({"value": 7})
            await asyncio.wait_for(received.wait(), 2)
            assert process.process is not None
            await process.process.wait()
            await process.close()
            return messages, logs

        messages, logs = asyncio.run(exercise())
        self.assertEqual(messages, [{"echo": 7}])
        self.assertIn("diagnostic", logs)


if __name__ == "__main__":
    unittest.main()
