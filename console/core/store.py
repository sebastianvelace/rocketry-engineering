"""
SQLite-backed history of captured/simulated runs.

This is what makes the console a single place instead of a pile of panels:
every capture (bench) or simulation result (motor, flight) that gets saved
here can be listed, reopened, and compared later, across restarts of the app.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "runs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    meta_json TEXT NOT NULL,
    columns_json TEXT NOT NULL,
    rows_json TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);
"""


@dataclass
class RunRecord:
    id: int
    created_at: str
    kind: str
    meta: dict
    columns: list
    rows: list
    note: str


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def save_run(kind: str, meta: dict, columns: list, rows: list, note: str = "") -> int:
    """Persist one run. Returns the new row's id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (created_at, kind, meta_json, columns_json, rows_json, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                kind,
                json.dumps(meta),
                json.dumps(columns),
                json.dumps(rows),
                note,
            ),
        )
        return cur.lastrowid


def list_runs(kind: str | None = None) -> list[RunRecord]:
    """List runs, most recent first. Rows/columns are NOT loaded (use get_run)."""
    with _connect() as conn:
        if kind:
            cur = conn.execute(
                "SELECT id, created_at, kind, meta_json, note FROM runs "
                "WHERE kind = ? ORDER BY id DESC", (kind,))
        else:
            cur = conn.execute(
                "SELECT id, created_at, kind, meta_json, note FROM runs ORDER BY id DESC")
        return [
            RunRecord(id=r[0], created_at=r[1], kind=r[2], meta=json.loads(r[3]),
                      columns=[], rows=[], note=r[4])
            for r in cur.fetchall()
        ]


def get_run(run_id: int) -> RunRecord | None:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT id, created_at, kind, meta_json, columns_json, rows_json, note "
            "FROM runs WHERE id = ?", (run_id,))
        r = cur.fetchone()
        if r is None:
            return None
        return RunRecord(
            id=r[0], created_at=r[1], kind=r[2],
            meta=json.loads(r[3]), columns=json.loads(r[4]), rows=json.loads(r[5]),
            note=r[6],
        )


def delete_run(run_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))


def count_runs() -> int:
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
