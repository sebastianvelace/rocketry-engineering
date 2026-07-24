"""Codex app-server adapter with native streaming and approvals."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from gateway.providers.base import ApprovalSink, EventSink, ProviderApproval, ProviderError, ProviderEvent
from gateway.providers.json_process import JsonLineProcess


def normalize_codex(payload: dict[str, Any]) -> list[ProviderEvent]:
    method = str(payload.get("method") or "")
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    item = params.get("item") if isinstance(params.get("item"), dict) else {}
    events: list[ProviderEvent] = []

    if method == "item/agentMessage/delta":
        events.append(ProviderEvent("assistant_delta", str(params.get("delta") or ""), "assistant", raw=payload))
    elif method in {"item/reasoning/summaryTextDelta", "item/reasoning/textDelta"}:
        events.append(ProviderEvent("reasoning", str(params.get("delta") or ""), "assistant", raw=payload))
    elif method == "item/commandExecution/outputDelta":
        events.append(ProviderEvent("command_output", str(params.get("delta") or ""), data={"item_id": params.get("itemId")}, raw=payload))
    elif method == "item/started":
        item_type = str(item.get("type") or "item")
        if item_type in {"commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall"}:
            text = item.get("command") or item.get("tool") or item_type
            events.append(ProviderEvent("tool_started", str(text), data={"item": item}, raw=payload))
    elif method == "item/completed":
        item_type = str(item.get("type") or "item")
        if item_type == "agentMessage":
            events.append(ProviderEvent("assistant_message", str(item.get("text") or ""), "assistant", data={"item": item}, raw=payload))
        elif item_type in {"commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall"}:
            events.append(ProviderEvent("tool_completed", str(item.get("status") or item_type), data={"item": item}, raw=payload))
    elif method == "turn/started":
        events.append(ProviderEvent("session", "Turn started", data={"turn": params.get("turn")}, raw=payload))
    elif method == "turn/completed":
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        events.append(ProviderEvent("session", f"Turn {turn.get('status', 'completed')}", data={"turn": turn}, raw=payload))
    elif method in {"thread/tokenUsage/updated", "turn/plan/updated"}:
        events.append(ProviderEvent("usage", method, data=params, raw=payload))
    elif method == "error":
        error = params.get("error") if isinstance(params.get("error"), dict) else params
        events.append(ProviderEvent("error", str(error.get("message") if isinstance(error, dict) else error), data=params, raw=payload))
    return events


class CodexAdapter:
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
        self.provider_session_id = provider_session_id
        self.turn_id: str | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._approval_requests: dict[int | str, tuple[str, dict[str, Any]]] = {}
        self.process = JsonLineProcess(
            ["codex", "app-server", "--stdio"],
            cwd=workspace,
            on_message=self._on_message,
            on_stderr=self._on_stderr,
        )

    async def _on_stderr(self, line: str) -> None:
        if line:
            await self.event_sink(ProviderEvent("command_output", line, data={"stream": "stderr"}))

    async def _on_message(self, payload: dict[str, Any]) -> None:
        response_id = payload.get("id")
        if isinstance(response_id, int) and "method" not in payload:
            future = self._pending.pop(response_id, None)
            if future is not None and not future.done():
                if "error" in payload:
                    future.set_exception(ProviderError(str(payload["error"])))
                else:
                    future.set_result(payload.get("result"))
            return
        method = str(payload.get("method") or "")
        if response_id is not None and method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            details = payload.get("params") or {}
            self._approval_requests[response_id] = (method, details)
            await self.approval_sink(
                ProviderApproval(
                    request_id=response_id,
                    action=method,
                    details=details,
                )
            )
            return
        for event in normalize_codex(payload):
            await self.event_sink(event)

    async def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        await self.process.send({"method": method, "id": request_id, "params": params})
        try:
            result = await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(request_id, None)
        return result or {}

    async def start(self) -> str:
        await self.process.start()
        await self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "rocketry_workstation",
                    "title": "Rocketry Workstation",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": False},
            },
        )
        await self.process.send({"method": "initialized", "params": {}})
        if self.provider_session_id:
            result = await self._request(
                "thread/resume",
                {
                    "threadId": self.provider_session_id,
                    "approvalPolicy": "on-request",
                    "sandbox": "workspace-write",
                    "cwd": str(self.workspace),
                },
            )
        else:
            result = await self._request(
                "thread/start",
                {
                    "cwd": str(self.workspace),
                    "approvalPolicy": "on-request",
                    "sandbox": "workspace-write",
                    "serviceName": "rocketry_workstation",
                },
            )
        thread = result.get("thread") or {}
        self.provider_session_id = str(thread["id"])
        return self.provider_session_id

    async def send_turn(self, prompt: str) -> str:
        if not self.provider_session_id:
            raise ProviderError("Codex thread has not started.")
        result = await self._request(
            "turn/start",
            {
                "threadId": self.provider_session_id,
                "input": [{"type": "text", "text": prompt}],
            },
        )
        self.turn_id = str((result.get("turn") or {})["id"])
        return self.turn_id

    async def interrupt(self) -> None:
        if self.provider_session_id and self.turn_id:
            await self._request(
                "turn/interrupt",
                {"threadId": self.provider_session_id, "turnId": self.turn_id},
                timeout=15,
            )

    async def resolve_approval(
        self,
        request_id: int | str,
        *,
        approved: bool,
        for_session: bool = False,
    ) -> None:
        request = self._approval_requests.pop(request_id, None)
        if request is None:
            raise ProviderError("Codex approval request is no longer active.")
        method, params = request
        if method == "item/permissions/requestApproval":
            result = {
                "permissions": params.get("permissions") if approved else {},
                "scope": "session" if approved and for_session else "turn",
            }
        else:
            decision = (
                "acceptForSession"
                if approved and for_session
                else "accept"
                if approved
                else "decline"
            )
            result = {"decision": decision}
        await self.process.send({"id": request_id, "result": result})

    async def close(self) -> None:
        await self.process.close()
