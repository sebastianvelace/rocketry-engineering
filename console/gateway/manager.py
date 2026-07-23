"""Session lifecycle, provider supervision and durable event fan-out."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from gateway.models import EventRecord, Provider, SessionRecord
from gateway.providers import ClaudeAdapter, CodexAdapter
from gateway.providers.base import ProviderApproval, ProviderEvent
from gateway.store import GatewayStore

AdapterFactory = Callable[..., Any]


class SessionManager:
    def __init__(
        self,
        store: GatewayStore,
        *,
        allowed_workspaces: list[Path],
        adapter_factory: AdapterFactory | None = None,
        queue_size: int = 512,
    ):
        self.store = store
        self.allowed_workspaces = [path.resolve() for path in allowed_workspaces]
        self.adapter_factory = adapter_factory
        self.queue_size = queue_size
        self.adapters: dict[str, Any] = {}
        self._session_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._subscribers: defaultdict[str, set[asyncio.Queue]] = defaultdict(set)
        self._provider_approvals: dict[str, int | str] = {}

    async def recover(self) -> int:
        return self.store.mark_unfinished_interrupted()

    def _validate_workspace(self, workspace: str) -> Path:
        candidate = Path(workspace).expanduser().resolve()
        if not candidate.is_dir():
            raise ValueError(f"Workspace does not exist: {candidate}")
        if not any(candidate == root or root in candidate.parents for root in self.allowed_workspaces):
            raise ValueError("Workspace is outside the configured allowed roots.")
        return candidate

    async def create_session(
        self,
        *,
        provider: Provider,
        workspace: str,
        title: str = "New session",
    ) -> SessionRecord:
        resolved = self._validate_workspace(workspace)
        session = self.store.create_session(
            provider=provider,
            workspace=str(resolved),
            title=title,
        )
        event = self.store.append_event(
            session.id,
            type="session",
            text="Session created",
            data={"provider": provider},
        )
        await self._publish(event)
        return session

    def _build_adapter(self, session: SessionRecord):
        kwargs = {
            "workspace": Path(session.workspace),
            "event_sink": lambda event: self._handle_provider_event(session.id, event),
            "provider_session_id": session.provider_session_id,
        }
        if self.adapter_factory is not None:
            return self.adapter_factory(provider=session.provider, **kwargs)
        if session.provider == "codex":
            return CodexAdapter(
                **kwargs,
                approval_sink=lambda approval: self._handle_provider_approval(
                    session.id,
                    approval,
                ),
            )
        return ClaudeAdapter(
            **kwargs,
            approval_sink=lambda approval: self._handle_provider_approval(
                session.id,
                approval,
            ),
        )

    async def _ensure_adapter(self, session_id: str):
        adapter = self.adapters.get(session_id)
        if adapter is not None:
            process = getattr(adapter, "process", None)
            child = getattr(process, "process", None)
            if child is None or child.returncode is None:
                return adapter
            self.adapters.pop(session_id, None)
        session = self.store.get_session(session_id)
        adapter = self._build_adapter(session)
        provider_session_id = await adapter.start()
        self.adapters[session_id] = adapter
        updated = self.store.update_session(
            session_id,
            status="ready",
            provider_session_id=provider_session_id,
        )
        event = self.store.append_event(
            session_id,
            type="session",
            text="Provider connected",
            data={
                "provider": updated.provider,
                "provider_session_id": provider_session_id,
            },
        )
        await self._publish(event)
        return adapter

    async def send_message(self, session_id: str, text: str) -> EventRecord:
        prompt = text.strip()
        if not prompt:
            raise ValueError("Message cannot be empty.")
        if len(prompt.encode("utf-8")) > 200_000:
            raise ValueError("Message is too large.")
        async with self._session_locks[session_id]:
            session = self.store.get_session(session_id)
            if session.status in {"running", "waiting_approval", "interrupting"}:
                raise RuntimeError("The session already has an active turn.")
            adapter = await self._ensure_adapter(session_id)
            event = self.store.append_event(
                session_id,
                type="user_message",
                role="user",
                text=prompt,
            )
            await self._publish(event)
            self.store.update_session(session_id, status="running")
            try:
                turn_id = await adapter.send_turn(prompt)
            except Exception:
                self.store.update_session(session_id, status="failed")
                raise
            submitted = self.store.append_event(
                session_id,
                type="session",
                text="Turn submitted",
                data={"turn_id": turn_id},
            )
            await self._publish(submitted)
            return submitted

    async def connect(self, session_id: str) -> None:
        """Warm a provider without consuming a model turn."""
        async with self._session_locks[session_id]:
            session = self.store.get_session(session_id)
            if session.status in {"running", "waiting_approval", "interrupting"}:
                return
            await self._ensure_adapter(session_id)

    async def _handle_provider_event(
        self,
        session_id: str,
        provider_event: ProviderEvent,
    ) -> None:
        event = self.store.append_event(
            session_id,
            type=provider_event.type,
            text=provider_event.text,
            role=provider_event.role,
            data=provider_event.data,
            raw=provider_event.raw,
        )
        await self._publish(event)
        if provider_event.type == "session":
            turn = provider_event.data.get("turn")
            status = turn.get("status") if isinstance(turn, dict) else None
            if status in {"completed", "interrupted", "failed"}:
                mapped = "ready" if status == "completed" else status
                self.store.update_session(session_id, status=mapped)
            elif provider_event.text == "Turn completed":
                self.store.update_session(session_id, status="ready")
        elif provider_event.type == "error":
            self.store.update_session(session_id, status="failed")

    async def _handle_provider_approval(
        self,
        session_id: str,
        provider_approval: ProviderApproval,
    ) -> None:
        approval = self.store.create_approval(
            session_id,
            action=provider_approval.action,
            details=provider_approval.details,
        )
        self._provider_approvals[approval.id] = provider_approval.request_id
        self.store.update_session(
            session_id,
            status="waiting_approval",
        )
        event = self.store.append_event(
            session_id,
            type="approval_requested",
            text=provider_approval.action,
            data={"approval": self.store.serialize(approval)},
        )
        await self._publish(event)

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        for_session: bool = False,
    ):
        current = self.store.get_approval(approval_id)
        resolution = self.store.resolve_approval(
            approval_id,
            approved=approved,
        )
        if current.status == "pending":
            adapter = self.adapters.get(current.session_id)
            provider_request_id = self._provider_approvals.pop(approval_id, None)
            if (
                adapter is not None
                and provider_request_id is not None
                and hasattr(adapter, "resolve_approval")
            ):
                await adapter.resolve_approval(
                    provider_request_id,
                    approved=approved,
                    for_session=for_session,
                )
            self.store.update_session(
                current.session_id,
                status="running",
            )
            event = self.store.append_event(
                current.session_id,
                type="approval_resolved",
                text=resolution.status,
                data={"approval": self.store.serialize(resolution)},
            )
            await self._publish(event)
        return resolution

    async def interrupt(self, session_id: str) -> None:
        adapter = self.adapters.get(session_id)
        if adapter is None:
            self.store.update_session(session_id, status="interrupted")
            return
        self.store.update_session(session_id, status="interrupting")
        await adapter.interrupt()
        self.store.update_session(session_id, status="interrupted")
        event = self.store.append_event(
            session_id,
            type="session",
            text="Turn interrupted",
        )
        await self._publish(event)

    def subscribe(self, session_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers[session_id].add(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(session_id)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(session_id, None)

    async def _publish(self, event: EventRecord) -> None:
        payload = self.store.serialize(event)
        for queue in list(self._subscribers.get(event.session_id, ())):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def close(self) -> None:
        adapters = list(self.adapters.values())
        self.adapters.clear()
        await asyncio.gather(
            *(adapter.close() for adapter in adapters),
            return_exceptions=True,
        )
