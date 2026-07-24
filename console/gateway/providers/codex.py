"""Codex app-server adapter with native streaming and approvals."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from gateway.providers.base import ApprovalSink, EventSink, ProviderApproval, ProviderError, ProviderEvent
from gateway.providers.json_process import JsonLineProcess

CODEX_COMMANDS = [
    {"name": "model", "description": "Select the model for this session.", "argumentHint": "<model>"},
    {"name": "compact", "description": "Compact the current thread context.", "argumentHint": ""},
    {"name": "review", "description": "Review uncommitted changes or follow custom instructions.", "argumentHint": "[instructions]"},
    {"name": "status", "description": "Show the current provider and workspace state.", "argumentHint": ""},
    {"name": "usage", "description": "Open real account and local usage.", "argumentHint": ""},
    {"name": "rename", "description": "Rename this conversation.", "argumentHint": "<name>"},
    {"name": "fork", "description": "Fork this conversation into a new session.", "argumentHint": "[name]"},
    {"name": "clear", "description": "Start a new empty conversation.", "argumentHint": "[name]"},
]


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
    elif method == "thread/compacted":
        events.append(ProviderEvent("session", "Context compacted", data=params, raw=payload))
    elif method == "thread/tokenUsage/updated":
        events.append(ProviderEvent("usage", method, data=params, raw=payload))
    elif method == "turn/plan/updated":
        events.append(ProviderEvent("plan_updated", method, data=params, raw=payload))
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
        self.selected_model: str | None = None
        self.available_models: list[dict[str, Any]] = []
        self._initialized = False
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

    async def _initialize(self) -> None:
        if self._initialized:
            return
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
        self._initialized = True

    async def start(self) -> str:
        await self._initialize()
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
        catalog = await self._request("model/list", {"limit": 100, "includeHidden": False})
        self.available_models = list(catalog.get("data") or [])
        await self.event_sink(
            ProviderEvent(
                "session",
                "Provider capabilities",
                data={
                    "commands": CODEX_COMMANDS,
                    "models": [
                        {
                            "value": item.get("model") or item.get("id"),
                            "resolvedModel": item.get("model") or item.get("id"),
                            "displayName": item.get("displayName") or item.get("model"),
                            "description": item.get("description") or "",
                            "supportsEffort": bool(item.get("supportedReasoningEfforts")),
                            "supportedEffortLevels": [
                                effort.get("reasoningEffort")
                                for effort in item.get("supportedReasoningEfforts") or []
                                if isinstance(effort, dict) and effort.get("reasoningEffort")
                            ],
                            "supportsFastMode": any(
                                tier.get("id") == "fast"
                                for tier in item.get("serviceTiers") or []
                                if isinstance(tier, dict)
                            ),
                            "isDefault": bool(item.get("isDefault")),
                        }
                        for item in self.available_models
                        if isinstance(item, dict)
                    ],
                },
            )
        )
        return self.provider_session_id

    async def set_model(self, model: str) -> None:
        allowed = {
            str(item.get("model") or item.get("id"))
            for item in self.available_models
            if isinstance(item, dict) and (item.get("model") or item.get("id"))
        }
        if model not in allowed:
            raise ProviderError(f"Codex model is not available: {model}")
        self.selected_model = model

    async def send_turn(self, prompt: str) -> str:
        if not self.provider_session_id:
            raise ProviderError("Codex thread has not started.")
        params: dict[str, Any] = {
            "threadId": self.provider_session_id,
            "input": [{"type": "text", "text": prompt}],
        }
        if self.selected_model:
            params["model"] = self.selected_model
        result = await self._request("turn/start", params)
        self.turn_id = str((result.get("turn") or {})["id"])
        return self.turn_id

    async def steer(self, prompt: str) -> None:
        """Add operator guidance to the currently active Codex turn."""
        if not self.provider_session_id or not self.turn_id:
            raise ProviderError("Codex has no active turn to steer.")
        await self._request(
            "turn/steer",
            {
                "threadId": self.provider_session_id,
                "input": [{"type": "text", "text": prompt}],
                "expectedTurnId": self.turn_id,
            },
        )

    async def compact(self) -> None:
        if not self.provider_session_id:
            raise ProviderError("Codex thread has not started.")
        await self._request("thread/compact/start", {"threadId": self.provider_session_id})

    async def review(self, instructions: str = "") -> str:
        if not self.provider_session_id:
            raise ProviderError("Codex thread has not started.")
        target: dict[str, Any] = (
            {"type": "custom", "instructions": instructions}
            if instructions
            else {"type": "uncommittedChanges"}
        )
        result = await self._request(
            "review/start",
            {"threadId": self.provider_session_id, "target": target, "delivery": "inline"},
        )
        self.turn_id = str((result.get("turn") or {})["id"])
        return self.turn_id

    async def rename(self, name: str) -> None:
        if not self.provider_session_id:
            raise ProviderError("Codex thread has not started.")
        await self._request(
            "thread/name/set",
            {"threadId": self.provider_session_id, "name": name},
        )

    async def fork(self) -> str:
        if not self.provider_session_id:
            raise ProviderError("Codex thread has not started.")
        result = await self._request(
            "thread/fork",
            {
                "threadId": self.provider_session_id,
                "cwd": str(self.workspace),
                "approvalPolicy": "on-request",
                "sandbox": "workspace-write",
                "model": self.selected_model,
            },
        )
        thread = result.get("thread") or {}
        return str(thread["id"])

    async def account_usage(self) -> dict[str, Any]:
        await self._initialize()
        rate_limits, token_usage = await asyncio.gather(
            self._request("account/rateLimits/read", {}),
            self._request("account/usage/read", {}),
        )
        return {"rate_limits": rate_limits, "token_usage": token_usage}

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
        answers: dict[str, str] | None = None,
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
