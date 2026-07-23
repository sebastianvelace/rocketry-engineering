"""SQLite event store for durable, resumable local agent sessions."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gateway.models import ApprovalRecord, EventRecord, EventType, Provider, SessionRecord, SessionStatus

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / ".rocketry" / "gateway.db"
MAX_EVENT_TEXT = 1_000_000
MAX_EVENT_JSON = 2_000_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider IN ('codex', 'claude')),
    provider_session_id TEXT,
    workspace TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    type TEXT NOT NULL,
    role TEXT,
    text TEXT NOT NULL,
    data_json TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_events_session_sequence
ON agent_events(session_id, sequence);

CREATE TABLE IF NOT EXISTS agent_approvals (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    status TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_approvals_session_status
ON agent_approvals(session_id, status);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class GatewayStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.RLock()
        with self._connection() as connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_EVENT_JSON:
            raise ValueError("Event JSON payload is too large.")
        return encoded

    @staticmethod
    def _session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            provider=row["provider"],
            provider_session_id=row["provider_session_id"],
            workspace=row["workspace"],
            title=row["title"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def _event(row: sqlite3.Row) -> EventRecord:
        return EventRecord(
            sequence=row["sequence"],
            id=row["id"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            type=row["type"],
            role=row["role"],
            text=row["text"],
            data=json.loads(row["data_json"]),
            raw=json.loads(row["raw_json"]),
        )

    @staticmethod
    def _approval(row: sqlite3.Row) -> ApprovalRecord:
        return ApprovalRecord(
            id=row["id"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            status=row["status"],
            action=row["action"],
            details=json.loads(row["details_json"]),
        )

    def create_session(
        self,
        *,
        provider: Provider,
        workspace: str,
        title: str = "New session",
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> SessionRecord:
        if provider not in {"codex", "claude"}:
            raise ValueError(f"Unsupported provider: {provider}")
        if not workspace.strip():
            raise ValueError("workspace is required")
        session_id = session_id or str(uuid.uuid4())
        now = utc_now()
        with self._write_lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_sessions
                (id, provider, provider_session_id, workspace, title, status,
                 created_at, updated_at, metadata_json)
                VALUES (?, ?, NULL, ?, ?, 'created', ?, ?, ?)
                """,
                (
                    session_id,
                    provider,
                    workspace,
                    title.strip() or "New session",
                    now,
                    now,
                    self._json(metadata or {}),
                ),
            )
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> SessionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Session {session_id} does not exist.")
        return self._session(row)

    def list_sessions(self, *, limit: int = 100) -> list[SessionRecord]:
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._session(row) for row in rows]

    def update_session(
        self,
        session_id: str,
        *,
        status: SessionStatus | None = None,
        provider_session_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionRecord:
        existing = self.get_session(session_id)
        values = {
            "status": status or existing.status,
            "provider_session_id": (
                provider_session_id
                if provider_session_id is not None
                else existing.provider_session_id
            ),
            "title": title.strip() if title is not None and title.strip() else existing.title,
            "metadata_json": self._json(metadata if metadata is not None else existing.metadata),
            "updated_at": utc_now(),
        }
        with self._write_lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE agent_sessions
                SET status = ?, provider_session_id = ?, title = ?,
                    metadata_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    values["status"],
                    values["provider_session_id"],
                    values["title"],
                    values["metadata_json"],
                    values["updated_at"],
                    session_id,
                ),
            )
        return self.get_session(session_id)

    def append_event(
        self,
        session_id: str,
        *,
        type: EventType,
        text: str = "",
        role: str | None = None,
        data: dict[str, Any] | None = None,
        raw: dict[str, Any] | None = None,
        event_id: str | None = None,
    ) -> EventRecord:
        encoded_text = str(text)
        if len(encoded_text.encode("utf-8")) > MAX_EVENT_TEXT:
            raise ValueError("Event text is too large.")
        event_id = event_id or str(uuid.uuid4())
        created_at = utc_now()
        with self._write_lock, self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO agent_events
                (id, session_id, created_at, type, role, text, data_json, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    created_at,
                    type,
                    role,
                    encoded_text,
                    self._json(data or {}),
                    self._json(raw or {}),
                ),
            )
            row = connection.execute(
                "SELECT * FROM agent_events WHERE id = ?",
                (event_id,),
            ).fetchone()
            connection.execute(
                "UPDATE agent_sessions SET updated_at = ? WHERE id = ?",
                (created_at, session_id),
            )
        if row is None:
            raise KeyError(f"Session {session_id} does not exist.")
        return self._event(row)

    def list_events(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 500,
    ) -> list[EventRecord]:
        if after_sequence < 0 or limit < 1 or limit > 2000:
            raise ValueError("Invalid event page.")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agent_events
                WHERE session_id = ? AND sequence > ?
                ORDER BY sequence ASC LIMIT ?
                """,
                (session_id, after_sequence, limit),
            ).fetchall()
        return [self._event(row) for row in rows]

    def create_approval(
        self,
        session_id: str,
        *,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> ApprovalRecord:
        approval_id = str(uuid.uuid4())
        created_at = utc_now()
        with self._write_lock, self._connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_approvals
                (id, session_id, created_at, resolved_at, status, action, details_json)
                VALUES (?, ?, ?, NULL, 'pending', ?, ?)
                """,
                (
                    approval_id,
                    session_id,
                    created_at,
                    action,
                    self._json(details or {}),
                ),
            )
        return self.get_approval(approval_id)

    def get_approval(self, approval_id: str) -> ApprovalRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM agent_approvals WHERE id = ?",
                (approval_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Approval {approval_id} does not exist.")
        return self._approval(row)

    def list_pending_approvals(self, session_id: str) -> list[ApprovalRecord]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agent_approvals
                WHERE session_id = ? AND status = 'pending'
                ORDER BY created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._approval(row) for row in rows]

    def resolve_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
    ) -> ApprovalRecord:
        current = self.get_approval(approval_id)
        if current.status != "pending":
            return current
        with self._write_lock, self._connection() as connection:
            connection.execute(
                """
                UPDATE agent_approvals
                SET status = ?, resolved_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                ("approved" if approved else "denied", utc_now(), approval_id),
            )
        return self.get_approval(approval_id)

    def mark_unfinished_interrupted(self) -> int:
        active = ("running", "waiting_approval", "interrupting")
        now = utc_now()
        with self._write_lock, self._connection() as connection:
            cursor = connection.execute(
                f"""
                UPDATE agent_sessions
                SET status = 'interrupted', updated_at = ?
                WHERE status IN ({",".join("?" for _ in active)})
                """,
                (now, *active),
            )
            connection.execute(
                """
                UPDATE agent_approvals
                SET status = 'cancelled', resolved_at = ?
                WHERE status = 'pending'
                """,
                (now,),
            )
            return cursor.rowcount

    @staticmethod
    def serialize(record: SessionRecord | EventRecord | ApprovalRecord) -> dict[str, Any]:
        return asdict(record)
