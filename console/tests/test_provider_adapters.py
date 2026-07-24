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
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    ThinkingBlock,
    ToolPermissionContext,
    ToolUseBlock,
)
from claude_agent_sdk.types import PermissionRuleValue, PermissionUpdate

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
            await adapter.steer("prefer the smaller patch")
            await adapter.compact()
            return requests, events

        requests, events = asyncio.run(exercise())
        turn = next(params for method, params in requests if method == "turn/start")
        self.assertEqual(turn["model"], "gpt-test")
        steer = next(params for method, params in requests if method == "turn/steer")
        self.assertEqual(steer["expectedTurnId"], "turn-1")
        self.assertEqual(steer["input"][0]["text"], "prefer the smaller patch")
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

    def test_codex_plan_update_is_not_mislabeled_as_usage(self):
        plan = normalize_codex(
            {
                "method": "turn/plan/updated",
                "params": {"plan": [{"step": "Read config", "status": "completed"}]},
            }
        )
        usage = normalize_codex(
            {
                "method": "thread/tokenUsage/updated",
                "params": {"totalTokens": 42},
            }
        )

        self.assertEqual(plan[0].type, "plan_updated")
        self.assertEqual(plan[0].data["plan"], [{"step": "Read config", "status": "completed"}])
        self.assertEqual(usage[0].type, "usage")

    def test_codex_exposes_tool_progress_and_runtime_warnings(self):
        progress = normalize_codex(
            {
                "method": "item/mcpToolCall/progress",
                "params": {"itemId": "tool-1", "message": "Simulating candidate 3 of 8"},
            }
        )
        warning = normalize_codex(
            {
                "method": "configWarning",
                "params": {"summary": "Ignored unknown setting", "path": "/tmp/config.toml"},
            }
        )
        rerouted = normalize_codex(
            {
                "method": "model/rerouted",
                "params": {"fromModel": "gpt-a", "toModel": "gpt-b", "reason": "capacity"},
            }
        )

        self.assertEqual(progress[0].type, "tool_progress")
        self.assertEqual(progress[0].data["item_id"], "tool-1")
        self.assertEqual(warning[0].type, "notice")
        self.assertEqual(warning[0].text, "Ignored unknown setting")
        self.assertIn("gpt-a", rerouted[0].text)
        self.assertIn("gpt-b", rerouted[0].text)

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

    def test_codex_request_user_input_uses_structured_questions_and_answers(self):
        async def exercise():
            approvals = []
            sent = []

            async def emit(event):
                pass

            async def approve(request):
                approvals.append(request)

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
                    "id": "question-1",
                    "method": "item/tool/requestUserInput",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "itemId": "item-1",
                        "autoResolutionMs": None,
                        "questions": [
                            {
                                "id": "motor",
                                "header": "Motor",
                                "question": "Which motor?",
                                "isOther": True,
                                "isSecret": False,
                                "options": [
                                    {"label": "F-class", "description": "Lower impulse"},
                                    {"label": "G-class", "description": "Higher impulse"},
                                ],
                            }
                        ],
                    },
                }
            )
            await adapter.resolve_approval(
                "question-1",
                approved=True,
                answers={"motor": "G-class"},
            )
            return approvals, sent

        approvals, sent = asyncio.run(exercise())
        self.assertEqual(approvals[0].action, "request_user_input")
        self.assertEqual(approvals[0].details["kind"], "ask_user_question")
        self.assertEqual(approvals[0].details["questions"][0]["id"], "motor")
        self.assertTrue(approvals[0].details["questions"][0]["isOther"])
        self.assertEqual(
            sent,
            [{"id": "question-1", "result": {"answers": {"motor": {"answers": ["G-class"]}}}}],
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

    def test_claude_tags_ask_user_question_and_returns_selected_answers(self):
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
                    answers={"Which motor?": "F-class"},
                )

            adapter = ClaudeAdapter(
                workspace=Path("/tmp"),
                event_sink=emit,
                approval_sink=approve,
            )
            result = await adapter._request_permission(
                "AskUserQuestion",
                {
                    "questions": [
                        {
                            "question": "Which motor?",
                            "header": "Motor",
                            "options": [{"label": "F-class", "description": ""}],
                            "multiSelect": False,
                        }
                    ]
                },
                ToolPermissionContext(tool_use_id="tool-1"),
            )
            return approvals, result

        approvals, result = asyncio.run(exercise())
        self.assertEqual(approvals[0].details["kind"], "ask_user_question")
        self.assertEqual(len(approvals[0].details["questions"]), 1)
        self.assertIsInstance(result, PermissionResultAllow)
        self.assertEqual(result.updated_input["answers"], {"Which motor?": "F-class"})

    def test_claude_uses_sandboxed_low_prompt_mode_and_session_scoped_approval(self):
        async def exercise():
            adapter = None

            async def emit(event):
                pass

            async def approve(request):
                await adapter.resolve_approval(
                    request.request_id,
                    approved=True,
                    for_session=True,
                )

            adapter = ClaudeAdapter(
                workspace=Path("/tmp"),
                event_sink=emit,
                approval_sink=approve,
            )
            result = await adapter._request_permission(
                "Bash",
                {"command": "pnpm test"},
                ToolPermissionContext(
                    tool_use_id="tool-1",
                    suggestions=[
                        PermissionUpdate(
                            type="addRules",
                            rules=[PermissionRuleValue("Bash", "pnpm test")],
                            behavior="allow",
                            destination="localSettings",
                        )
                    ],
                ),
            )
            return adapter.client.options, result

        options, result = asyncio.run(exercise())
        self.assertEqual(options.permission_mode, "acceptEdits")
        self.assertIn("mcp__rocketry__*", options.allowed_tools)
        self.assertIn("Bash(eza *)", options.allowed_tools)
        if options.sandbox is not None:
            self.assertTrue(options.sandbox["enabled"])
            self.assertTrue(options.sandbox["autoAllowBashIfSandboxed"])
        self.assertEqual(result.updated_permissions[0].destination, "session")

    def test_claude_normalizes_thinking_block(self):
        thinking = normalize_sdk_message(
            AssistantMessage(
                content=[ThinkingBlock(thinking="considering options", signature="sig")],
                model="claude",
            )
        )
        self.assertEqual(
            (thinking[0].type, thinking[0].text, thinking[0].role),
            ("thinking", "considering options", "assistant"),
        )

    def test_claude_normalizes_subagent_task_lifecycle(self):
        started = normalize_sdk_message(
            TaskStartedMessage(
                subtype="task_started",
                data={},
                task_id="task-1",
                description="Investigate flaky test",
                uuid="uuid-1",
                session_id="session-1",
                tool_use_id="tool-1",
                task_type="general-purpose",
            )
        )
        progress = normalize_sdk_message(
            TaskProgressMessage(
                subtype="task_progress",
                data={},
                task_id="task-1",
                description="Investigate flaky test",
                usage={"total_tokens": 100, "tool_uses": 2, "duration_ms": 500},
                uuid="uuid-2",
                session_id="session-1",
                tool_use_id="tool-1",
                last_tool_name="Bash",
            )
        )
        notified = normalize_sdk_message(
            TaskNotificationMessage(
                subtype="task_notification",
                data={},
                task_id="task-1",
                status="completed",
                output_file="",
                summary="Found root cause",
                uuid="uuid-3",
                session_id="session-1",
                tool_use_id="tool-1",
            )
        )
        updated_running = normalize_sdk_message(
            TaskUpdatedMessage(
                subtype="task_updated",
                data={},
                task_id="task-1",
                patch={"status": "running"},
                status="running",
            )
        )
        updated_killed = normalize_sdk_message(
            TaskUpdatedMessage(
                subtype="task_updated",
                data={},
                task_id="task-1",
                patch={"status": "killed"},
                status="killed",
            )
        )

        self.assertEqual(
            (started[0].type, started[0].text, started[0].data["task_id"]),
            ("subagent_started", "Investigate flaky test", "task-1"),
        )
        self.assertEqual((progress[0].type, progress[0].text), ("subagent_progress", "Investigate flaky test"))
        self.assertEqual((notified[0].type, notified[0].text), ("subagent_completed", "Found root cause"))
        self.assertEqual(updated_running[0].type, "subagent_progress")
        self.assertEqual(updated_killed[0].type, "subagent_completed")

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
