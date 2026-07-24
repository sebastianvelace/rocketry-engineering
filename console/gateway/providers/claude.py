"""Claude Code Agent SDK adapter with native sessions and approvals."""
from __future__ import annotations

import asyncio
import dataclasses
import shutil
import uuid
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    TERMINAL_TASK_STATUSES,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from gateway.providers.base import (
    ApprovalSink,
    EventSink,
    ProviderApproval,
    ProviderError,
    ProviderEvent,
)

CLAUDE_ALLOWED_TOOLS = [
    "mcp__rocketry__*",
    "Bash(eza *)",
    "Bash(rg --files *)",
    "Bash(gh auth status *)",
    "Bash(pnpm test *)",
    "Bash(pnpm build *)",
    "Bash(pnpm exec playwright test *)",
    "Bash(cargo check *)",
]


def normalize_claude(payload: dict[str, Any]) -> list[ProviderEvent]:
    """Normalize raw CLI stream-json payloads kept for fixtures and imports."""
    event_type = str(payload.get("type") or "")
    events: list[ProviderEvent] = []
    if event_type == "stream_event":
        event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
        delta = event.get("delta") if isinstance(event.get("delta"), dict) else {}
        if delta.get("type") == "text_delta":
            events.append(
                ProviderEvent(
                    "assistant_delta",
                    str(delta.get("text") or ""),
                    "assistant",
                    raw=payload,
                )
            )
    elif event_type == "assistant":
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                events.append(
                    ProviderEvent(
                        "tool_started",
                        str(block.get("name") or "tool"),
                        data={"tool": block},
                        raw=payload,
                    )
                )
    elif event_type == "user":
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                events.append(
                    ProviderEvent(
                        "tool_completed",
                        "Tool completed",
                        data={"tool_result": block},
                        raw=payload,
                    )
                )
    elif event_type == "result":
        result = str(payload.get("result") or "")
        if result:
            events.append(
                ProviderEvent(
                    "assistant_message",
                    result,
                    "assistant",
                    data={"session_id": payload.get("session_id")},
                    raw=payload,
                )
            )
        events.append(
            ProviderEvent(
                "usage",
                "Turn usage",
                data={
                    "usage": payload.get("usage"),
                    "cost_usd": payload.get("total_cost_usd"),
                },
                raw=payload,
            )
        )
        events.append(
            ProviderEvent(
                "session",
                "Turn completed",
                data={"stop_reason": payload.get("stop_reason")},
                raw=payload,
            )
        )
    elif event_type == "system":
        events.append(
            ProviderEvent(
                "session",
                str(payload.get("subtype") or "Claude initialized"),
                data={"session_id": payload.get("session_id")},
                raw=payload,
            )
        )
    return events


def _raw_message(message: Any) -> dict[str, Any]:
    return dataclasses.asdict(message) if dataclasses.is_dataclass(message) else {}


def normalize_sdk_message(message: Any) -> list[ProviderEvent]:
    """Map typed Agent SDK messages to the gateway's provider-neutral stream."""
    if isinstance(message, StreamEvent):
        raw = _raw_message(message)
        delta = message.event.get("delta")
        if isinstance(delta, dict) and delta.get("type") == "text_delta":
            return [
                ProviderEvent(
                    "assistant_delta",
                    str(delta.get("text") or ""),
                    "assistant",
                    raw=raw,
                )
            ]
        return []
    if isinstance(message, AssistantMessage):
        raw = _raw_message(message)
        events: list[ProviderEvent] = []
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                events.append(
                    ProviderEvent(
                        "tool_started",
                        block.name,
                        data={
                            "tool": {
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            }
                        },
                        raw=raw,
                    )
                )
            elif isinstance(block, ThinkingBlock):
                events.append(
                    ProviderEvent("thinking", block.thinking, "assistant", raw=raw)
                )
            elif isinstance(block, TextBlock):
                # Complete text is useful when partial streaming is disabled.
                # With partial streaming enabled it is intentionally omitted to
                # avoid rendering the same answer twice.
                continue
        return events
    if isinstance(message, UserMessage) and isinstance(message.content, list):
        raw = _raw_message(message)
        return [
            ProviderEvent(
                "tool_completed",
                "Tool completed",
                data={
                    "tool_result": {
                        "tool_use_id": block.tool_use_id,
                        "content": block.content,
                        "is_error": block.is_error,
                    }
                },
                raw=raw,
            )
            for block in message.content
            if isinstance(block, ToolResultBlock)
        ]
    if isinstance(message, ResultMessage):
        raw = _raw_message(message)
        events = []
        if message.result:
            events.append(
                ProviderEvent(
                    "assistant_message",
                    message.result,
                    "assistant",
                    data={"session_id": message.session_id},
                    raw=raw,
                )
            )
        events.extend(
            [
                ProviderEvent(
                    "usage",
                    "Turn usage",
                    data={
                        "usage": message.usage,
                        "cost_usd": message.total_cost_usd,
                        "turns": message.num_turns,
                    },
                    raw=raw,
                ),
                ProviderEvent(
                    "session",
                    "Turn completed",
                    data={
                        "session_id": message.session_id,
                        "stop_reason": message.stop_reason,
                        "subtype": message.subtype,
                        "is_error": message.is_error,
                    },
                    raw=raw,
                ),
            ]
        )
        return events
    if isinstance(message, TaskStartedMessage):
        return [
            ProviderEvent(
                "subagent_started",
                message.description,
                data={
                    "task_id": message.task_id,
                    "tool_use_id": message.tool_use_id,
                    "task_type": message.task_type,
                },
            )
        ]
    if isinstance(message, TaskProgressMessage):
        return [
            ProviderEvent(
                "subagent_progress",
                message.description,
                data={
                    "task_id": message.task_id,
                    "tool_use_id": message.tool_use_id,
                    "last_tool_name": message.last_tool_name,
                    "usage": message.usage,
                },
            )
        ]
    if isinstance(message, TaskNotificationMessage):
        return [
            ProviderEvent(
                "subagent_completed",
                message.summary,
                data={
                    "task_id": message.task_id,
                    "tool_use_id": message.tool_use_id,
                    "status": message.status,
                    "usage": message.usage,
                },
            )
        ]
    if isinstance(message, TaskUpdatedMessage):
        terminal = message.status in TERMINAL_TASK_STATUSES if message.status else False
        return [
            ProviderEvent(
                "subagent_completed" if terminal else "subagent_progress",
                f"Task {message.status or 'updated'}",
                data={"task_id": message.task_id, "status": message.status, "patch": message.patch},
            )
        ]
    if isinstance(message, SystemMessage):
        if message.subtype != "init":
            return []
        compact = {
            key: message.data.get(key)
            for key in (
                "session_id",
                "model",
                "permissionMode",
                "claude_code_version",
            )
            if message.data.get(key) is not None
        }
        return [
            ProviderEvent(
                "session",
                "Claude initialized",
                data=compact,
            )
        ]
    return []


class ClaudeAdapter:
    def __init__(
        self,
        *,
        workspace: Path,
        event_sink: EventSink,
        approval_sink: ApprovalSink,
        provider_session_id: str | None = None,
    ):
        self.workspace = workspace
        self.event_sink = event_sink
        self.approval_sink = approval_sink
        self.provider_session_id = provider_session_id or str(uuid.uuid4())
        self._resuming = provider_session_id is not None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._receiver: asyncio.Task | None = None
        self.available_models: list[dict[str, Any]] = []
        self.available_commands: list[dict[str, Any]] = []
        self._pending_permissions: dict[
            str,
            tuple[asyncio.Future, dict[str, Any], list[Any]],
        ] = {}
        console_root = Path(__file__).resolve().parents[2]
        rocketry_python = console_root / ".venv" / "bin" / "python"
        rocketry_server = console_root / "rocketry_mcp.py"
        self.sandbox_enabled = bool(shutil.which("bwrap") and shutil.which("socat"))
        options = ClaudeAgentOptions(
            cwd=workspace,
            resume=provider_session_id,
            session_id=None if provider_session_id else self.provider_session_id,
            permission_mode="acceptEdits",
            can_use_tool=self._request_permission,
            allowed_tools=CLAUDE_ALLOWED_TOOLS,
            sandbox=(
                {
                    "enabled": True,
                    "autoAllowBashIfSandboxed": True,
                    "allowUnsandboxedCommands": True,
                }
                if self.sandbox_enabled
                else None
            ),
            include_partial_messages=True,
            include_hook_events=False,
            setting_sources=["project", "local"],
            mcp_servers={
                "rocketry": {
                    "type": "stdio",
                    "command": str(rocketry_python),
                    "args": [str(rocketry_server)],
                }
            },
            strict_mcp_config=True,
            stderr=self._stderr,
        )
        self.client = ClaudeSDKClient(options=options)

    def _stderr(self, line: str) -> None:
        if line and self._loop is not None:
            self._loop.create_task(
                self.event_sink(
                    ProviderEvent(
                        "command_output",
                        line,
                        data={"stream": "stderr"},
                    )
                )
            )

    async def _request_permission(self, tool_name, input_data, context):
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        suggestions = list(context.suggestions or [])
        self._pending_permissions[request_id] = (future, input_data, suggestions)
        details = {
            "tool_name": tool_name,
            "input": input_data,
            "tool_use_id": context.tool_use_id,
            "title": context.title,
            "display_name": context.display_name,
            "description": context.description,
            "decision_reason": context.decision_reason,
            "blocked_path": context.blocked_path,
        }
        try:
            await self.approval_sink(
                ProviderApproval(
                    request_id=request_id,
                    action=tool_name,
                    details=details,
                )
            )
            return await future
        finally:
            self._pending_permissions.pop(request_id, None)

    async def start(self) -> str:
        self._loop = asyncio.get_running_loop()
        try:
            await self.client.connect()
            info = await self.client.get_server_info() or {}
            self.available_models = list(info.get("models") or [])
            self.available_commands = list(info.get("commands") or [])
            await self.event_sink(
                ProviderEvent(
                    "session",
                    "Provider capabilities",
                    data={
                        "commands": self.available_commands,
                        "models": self.available_models,
                        "output_style": info.get("output_style"),
                        "sandbox_enabled": self.sandbox_enabled,
                    },
                )
            )
        except Exception as exc:
            raise ProviderError(f"Claude Code failed to start: {exc}") from exc
        return self.provider_session_id

    async def set_model(self, model: str) -> None:
        allowed = {
            str(item.get("value"))
            for item in self.available_models
            if isinstance(item, dict) and item.get("value")
        }
        if model not in allowed:
            raise ProviderError(f"Claude model is not available: {model}")
        await self.client.set_model(None if model == "default" else model)

    async def _receive_turn(self) -> None:
        try:
            async for message in self.client.receive_response():
                if isinstance(message, ResultMessage):
                    self.provider_session_id = message.session_id
                elif isinstance(message, SystemMessage):
                    observed = message.data.get("session_id")
                    if isinstance(observed, str):
                        self.provider_session_id = observed
                for event in normalize_sdk_message(message):
                    await self.event_sink(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.event_sink(
                ProviderEvent(
                    "error",
                    f"Claude stream failed: {exc}",
                    data={"exception": type(exc).__name__},
                )
            )

    async def send_turn(self, prompt: str) -> str:
        if self._receiver is not None and not self._receiver.done():
            raise ProviderError("Claude already has an active turn.")
        try:
            await self.client.query(prompt)
        except Exception as exc:
            raise ProviderError(f"Claude rejected the turn: {exc}") from exc
        self._receiver = asyncio.create_task(self._receive_turn())
        return self.provider_session_id

    async def resolve_approval(
        self,
        request_id: int | str,
        *,
        approved: bool,
        for_session: bool,
    ) -> None:
        pending = self._pending_permissions.get(str(request_id))
        if pending is None:
            raise ProviderError("Claude permission request is no longer active.")
        future, input_data, suggestions = pending
        if future.done():
            return
        if approved:
            session_permissions = (
                [
                    dataclasses.replace(suggestion, destination="session")
                    for suggestion in suggestions
                ]
                if for_session
                else None
            )
            future.set_result(
                PermissionResultAllow(
                    updated_input=input_data,
                    updated_permissions=session_permissions,
                )
            )
        else:
            future.set_result(
                PermissionResultDeny(message="The user denied this action.")
            )

    async def interrupt(self) -> None:
        await self.client.interrupt()
        if self._receiver is not None and not self._receiver.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._receiver),
                    timeout=15,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderError(
                    "Claude did not finish draining the interrupted turn."
                ) from exc

    async def close(self) -> None:
        for future, _, _ in self._pending_permissions.values():
            if not future.done():
                future.set_result(
                    PermissionResultDeny(
                        message="The workstation session was closed.",
                        interrupt=True,
                    )
                )
        self._pending_permissions.clear()
        if self._receiver is not None and not self._receiver.done():
            self._receiver.cancel()
            await asyncio.gather(self._receiver, return_exceptions=True)
        await self.client.disconnect()
