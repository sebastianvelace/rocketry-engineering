"""Session lifecycle, provider supervision and durable event fan-out."""
from __future__ import annotations

import asyncio
import dataclasses
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from gateway.models import EventRecord, Provider, SessionRecord
from gateway.providers import ClaudeAdapter, CodexAdapter
from gateway.providers.base import ProviderApproval, ProviderEvent
from gateway.store import GatewayStore
from gateway.worktrees import WorktreeHasPendingChangesError, WorktreeManager

AdapterFactory = Callable[..., Any]


class SessionManager:
    def __init__(
        self,
        store: GatewayStore,
        *,
        allowed_workspaces: list[Path],
        adapter_factory: AdapterFactory | None = None,
        queue_size: int = 512,
        worktrees: WorktreeManager | None = None,
    ):
        self.store = store
        self.allowed_workspaces = [path.resolve() for path in allowed_workspaces]
        self.adapter_factory = adapter_factory
        self.queue_size = queue_size
        self.worktrees = worktrees
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
        isolated: bool = False,
    ) -> SessionRecord:
        session_id: str | None = None
        metadata: dict[str, Any] = {}
        if isolated:
            if self.worktrees is None:
                raise ValueError("Isolated workspaces are not configured for this gateway.")
            session_id = str(uuid.uuid4())
            resolved, base_branch = await self.worktrees.create(session_id)
            metadata["isolated_workspace"] = True
            metadata["worktree_branch"] = self.worktrees.branch(session_id)
            metadata["worktree_base_branch"] = base_branch
        else:
            resolved = self._validate_workspace(workspace)
        session = self.store.create_session(
            provider=provider,
            workspace=str(resolved),
            title=title,
            session_id=session_id,
            metadata=metadata,
        )
        event = self.store.append_event(
            session.id,
            type="session",
            text="Session created",
            data={"provider": provider, "isolated_workspace": isolated},
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

    async def _fail_connection(self, session_id: str, adapter: Any, exc: Exception) -> None:
        self.store.update_session(session_id, status="failed")
        event = self.store.append_event(
            session_id,
            type="error",
            text="Provider connection failed",
            data={"error": str(exc)},
        )
        await self._publish(event)
        try:
            await adapter.close()
        except Exception:
            pass

    async def _start_with_resume_fallback(self, session_id: str, session: SessionRecord):
        """Start the adapter, falling back to a fresh provider session if a
        resume fails.

        A stored provider_session_id can stop being resumable for reasons
        outside this gateway's knowledge (the provider prunes or clears its
        own local session state). Without this fallback, that permanently
        bricks the conversation: every reconnect attempt repeats the same
        failure. The durable event history here is unaffected either way,
        so falling back to a new provider session keeps the conversation
        usable instead of leaving it stuck.
        """
        adapter = self._build_adapter(session)
        if not session.provider_session_id:
            try:
                provider_session_id = await adapter.start()
            except Exception as exc:
                await self._fail_connection(session_id, adapter, exc)
                raise
            return adapter, provider_session_id

        try:
            provider_session_id = await adapter.start()
            return adapter, provider_session_id
        except Exception as exc:
            try:
                await adapter.close()
            except Exception:
                pass
            event = self.store.append_event(
                session_id,
                type="notice",
                text="Provider session could not be resumed; starting a new one",
                data={"error": str(exc)},
            )
            await self._publish(event)

        fresh_session = dataclasses.replace(session, provider_session_id=None)
        adapter = self._build_adapter(fresh_session)
        try:
            provider_session_id = await adapter.start()
        except Exception as exc:
            await self._fail_connection(session_id, adapter, exc)
            raise
        return adapter, provider_session_id

    async def _ensure_adapter(self, session_id: str):
        adapter = self.adapters.get(session_id)
        if adapter is not None:
            process = getattr(adapter, "process", None)
            child = getattr(process, "process", None)
            if child is None or child.returncode is None:
                return adapter
            self.adapters.pop(session_id, None)
        session = self.store.get_session(session_id)
        adapter, provider_session_id = await self._start_with_resume_fallback(session_id, session)
        try:
            preferred_model = session.metadata.get("model")
            if preferred_model and hasattr(adapter, "set_model"):
                await adapter.set_model(str(preferred_model))
        except Exception as exc:
            await self._fail_connection(session_id, adapter, exc)
            raise
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
            session = self.store.get_session(session_id)
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

    def _require_worktree_metadata(self, session: SessionRecord) -> str:
        if not session.metadata.get("isolated_workspace") or self.worktrees is None:
            raise ValueError(f"Session {session.id} does not have an isolated workspace.")
        base_branch = session.metadata.get("worktree_base_branch")
        if not base_branch:
            raise ValueError(f"Session {session.id} has no recorded worktree base branch.")
        return str(base_branch)

    async def get_worktree_review(self, session_id: str) -> dict[str, Any]:
        session = self.store.get_session(session_id)
        base_branch = self._require_worktree_metadata(session)
        assert self.worktrees is not None
        status = await self.worktrees.status(session_id, base_branch)
        diff = await self.worktrees.diff(session_id, base_branch)
        return {
            "branch": status.branch,
            "base_branch": status.base_branch,
            "uncommitted_files": status.uncommitted_files,
            "commits_ahead": status.commits_ahead,
            "has_pending": status.has_pending,
            "diff": diff,
        }

    async def merge_worktree(self, session_id: str) -> dict[str, Any]:
        async with self._session_locks[session_id]:
            session = self.store.get_session(session_id)
            base_branch = self._require_worktree_metadata(session)
            assert self.worktrees is not None
            result = await self.worktrees.merge(session_id, base_branch)
            event = self.store.append_event(
                session_id,
                type="notice",
                text=f"Merged isolated session into {base_branch}",
                data={"base_branch": base_branch, "merge_result": result},
            )
            await self._publish(event)
            return {"base_branch": base_branch, "merge_result": result}

    async def delete_session(self, session_id: str, *, force: bool = False) -> None:
        """Stop a live provider and remove all durable conversation data.

        For an isolated session, this checks the worktree's status *before*
        touching the adapter or the durable store — if there's uncommitted
        or unmerged work and the caller didn't force it, nothing is deleted
        at all. That mirrors git's own "worktree remove"/"branch -d" safety
        checks: an unsafe delete request changes nothing rather than
        partially destroying state.
        """
        async with self._session_locks[session_id]:
            session = self.store.get_session(session_id)
            is_isolated = bool(session.metadata.get("isolated_workspace")) and self.worktrees is not None
            if is_isolated and not force:
                assert self.worktrees is not None
                base_branch = session.metadata.get("worktree_base_branch")
                if base_branch:
                    status = await self.worktrees.status(session_id, str(base_branch))
                    if status.has_pending:
                        raise WorktreeHasPendingChangesError(status)

            adapter = self.adapters.pop(session_id, None)
            if adapter is not None:
                try:
                    await adapter.close()
                except Exception:
                    # Deletion is authoritative even if an already-failing
                    # provider process cannot complete its shutdown handshake.
                    pass

            pending = self.store.list_pending_approvals(session_id)
            for approval in pending:
                self._provider_approvals.pop(approval.id, None)

            self.store.delete_session(session_id)
            self._subscribers.pop(session_id, None)

            if is_isolated:
                assert self.worktrees is not None
                await self.worktrees.remove(session_id, force=force)

    async def set_model(self, session_id: str, model: str) -> SessionRecord:
        async with self._session_locks[session_id]:
            session = self.store.get_session(session_id)
            if session.status in {"running", "waiting_approval", "interrupting"}:
                raise RuntimeError("The model cannot change during an active turn.")
            adapter = await self._ensure_adapter(session_id)
            if not hasattr(adapter, "set_model"):
                raise ValueError(f"Model switching is unavailable for {session.provider}.")
            await adapter.set_model(model)
            updated = self.store.update_session(
                session_id,
                metadata={**session.metadata, "model": model},
            )
            event = self.store.append_event(
                session_id,
                type="session",
                text="Model changed",
                data={"model": model},
            )
            await self._publish(event)
            return updated

    async def execute_command(
        self,
        session_id: str,
        command: str,
        arguments: str = "",
    ) -> dict[str, Any]:
        name = command.strip().lstrip("/").lower()
        args = arguments.strip()
        if not name:
            raise ValueError("command is required.")

        async with self._session_locks[session_id]:
            session = self.store.get_session(session_id)
            if session.status in {"running", "waiting_approval", "interrupting"}:
                raise RuntimeError("The session already has an active turn.")

            if name == "usage":
                return {"action": "usage", "session": session}

            if name == "clear":
                created = await self.create_session(
                    provider=session.provider,
                    workspace=session.workspace,
                    title=args or f"{session.title} · new",
                )
                return {"action": "created", "session": created}

            adapter = await self._ensure_adapter(session_id)
            session = self.store.get_session(session_id)

            if name == "status":
                model = session.metadata.get("model") or "provider default"
                text = (
                    f"**{session.provider.upper()}**\n\n"
                    f"- Workspace: `{session.workspace}`\n"
                    f"- Model: `{model}`\n"
                    f"- Status: `{session.status}`\n"
                    f"- Provider session: `{session.provider_session_id or 'connecting'}`"
                )
                event = self.store.append_event(
                    session_id,
                    type="assistant_message",
                    role="assistant",
                    text=text,
                    data={"command": "status"},
                )
                await self._publish(event)
                return {"action": "event", "session": session, "event": event}

            if name == "rename":
                if not args:
                    raise ValueError("/rename requires a name.")
                if session.provider == "codex":
                    await adapter.rename(args)
                else:
                    await self._start_provider_command(session, adapter, name, args)
                updated = self.store.update_session(session_id, title=args)
                event = self.store.append_event(
                    session_id,
                    type="session",
                    text="Session renamed",
                    data={"title": args},
                )
                await self._publish(event)
                return {"action": "renamed", "session": updated, "event": event}

            if name == "fork":
                if session.provider != "codex":
                    raise ValueError("/fork is not available through the Claude Agent SDK.")
                provider_session_id = await adapter.fork()
                created = self.store.create_session(
                    provider="codex",
                    workspace=session.workspace,
                    title=args or f"{session.title} · fork",
                    metadata=session.metadata,
                )
                created = self.store.update_session(
                    created.id,
                    status="ready",
                    provider_session_id=provider_session_id,
                )
                event = self.store.append_event(
                    created.id,
                    type="session",
                    text="Session forked",
                    data={"source_session_id": session_id},
                )
                await self._publish(event)
                return {"action": "created", "session": created, "event": event}

            if session.provider == "codex":
                if name == "compact":
                    self.store.update_session(session_id, status="running")
                    try:
                        await adapter.compact()
                    except Exception:
                        self.store.update_session(session_id, status="ready")
                        raise
                    return {"action": "running", "session": self.store.get_session(session_id)}
                if name == "review":
                    self.store.update_session(session_id, status="running")
                    try:
                        turn_id = await adapter.review(args)
                    except Exception:
                        self.store.update_session(session_id, status="ready")
                        raise
                    event = self.store.append_event(
                        session_id,
                        type="session",
                        text="Review submitted",
                        data={"turn_id": turn_id},
                    )
                    await self._publish(event)
                    return {"action": "running", "session": self.store.get_session(session_id), "event": event}
                raise ValueError(f"/{name} is not supported by the Codex app-server integration.")

            available = {
                str(item.get("name") or "").lower()
                for item in getattr(adapter, "available_commands", [])
                if isinstance(item, dict)
            }
            if name not in available:
                raise ValueError(f"/{name} is not dispatchable through the Claude Agent SDK.")
            event = await self._start_provider_command(session, adapter, name, args)
            return {
                "action": "running",
                "session": self.store.get_session(session_id),
                "event": event,
            }

    async def _start_provider_command(
        self,
        session: SessionRecord,
        adapter: Any,
        command: str,
        arguments: str,
    ) -> EventRecord:
        prompt = f"/{command}{f' {arguments}' if arguments else ''}"
        user_event = self.store.append_event(
            session.id,
            type="user_message",
            role="user",
            text=prompt,
            data={"command": command},
        )
        await self._publish(user_event)
        self.store.update_session(session.id, status="running")
        try:
            turn_id = await adapter.send_turn(prompt)
        except Exception:
            self.store.update_session(session.id, status="failed")
            raise
        event = self.store.append_event(
            session.id,
            type="session",
            text="Command submitted",
            data={"command": command, "turn_id": turn_id},
        )
        await self._publish(event)
        return event

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
            elif provider_event.text == "Context compacted":
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
        answers: dict[str, str] | None = None,
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
                    answers=answers,
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
