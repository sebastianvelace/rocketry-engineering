"""Linux process-wide operation locks for independent MCP server processes."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from services import ServiceError


class OperationLocks:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(__file__).resolve().parent.parent / ".rocketry" / "locks"

    @contextmanager
    def acquire(self, name: str) -> Iterator[None]:
        if not name or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for character in name):
            raise ValueError(f"Invalid lock name: {name!r}")
        self.root.mkdir(parents=True, exist_ok=True)
        handle: TextIO = (self.root / f"{name}.lock").open("a+", encoding="utf-8")
        try:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ServiceError(
                    "operation_busy",
                    f"Another session is already using the {name} operation.",
                    cause=exc,
                )
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
