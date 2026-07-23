"""Async JSON-lines subprocess with bounded stderr forwarding."""
from __future__ import annotations

import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Any, Awaitable, Callable

JsonSink = Callable[[dict[str, Any]], Awaitable[None]]
LogSink = Callable[[str], Awaitable[None]]


class JsonLineProcess:
    def __init__(
        self,
        command: list[str],
        *,
        cwd: Path,
        on_message: JsonSink,
        on_stderr: LogSink,
        environment: dict[str, str] | None = None,
    ):
        self.command = command
        self.cwd = cwd
        self.on_message = on_message
        self.on_stderr = on_stderr
        self.environment = environment
        self.process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.process is not None and self.process.returncode is None:
            return
        environment = os.environ.copy()
        if self.environment:
            environment.update(self.environment)
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            env=environment,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        while line := await self.process.stdout.readline():
            try:
                payload = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                await self.on_stderr(line.decode(errors="replace").strip()[:2000])
                continue
            if isinstance(payload, dict):
                await self.on_message(payload)

    async def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while line := await self.process.stderr.readline():
            await self.on_stderr(line.decode(errors="replace").strip()[:2000])

    async def send(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.returncode is not None:
            raise RuntimeError("Provider process is not running.")
        assert self.process.stdin is not None
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        async with self._write_lock:
            self.process.stdin.write(encoded)
            await self.process.stdin.drain()

    async def interrupt(self) -> None:
        if self.process is not None and self.process.returncode is None:
            os.killpg(self.process.pid, signal.SIGINT)

    async def close(self, *, timeout: float = 5.0) -> None:
        if self.process is None:
            return
        if self.process.stdin is not None and not self.process.stdin.is_closing():
            self.process.stdin.close()
        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()
        tasks = [task for task in (self._stdout_task, self._stderr_task) if task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
