"""Git worktree isolation for sessions that edit files concurrently.

Each isolated session gets its own working tree under
``.rocketry/worktrees/<session_id>`` on a dedicated ``workstation/<session_id>``
branch, so two sessions editing the repository at the same time never step on
each other's uncommitted changes. Removal is only ever scoped to paths this
module created — it never touches the user's real working tree.
"""
from __future__ import annotations

import asyncio
from pathlib import Path


class WorktreeError(RuntimeError):
    pass


class WorktreeManager:
    def __init__(self, repo_root: Path, *, base_dir: Path | None = None):
        self.repo_root = repo_root
        self.base_dir = base_dir or repo_root / ".rocketry" / "worktrees"
        self._lock = asyncio.Lock()

    def branch(self, session_id: str) -> str:
        return f"workstation/{session_id}"

    def path(self, session_id: str) -> Path:
        return self.base_dir / session_id

    async def create(self, session_id: str) -> Path:
        target = self.path(session_id)
        async with self._lock:
            self.base_dir.mkdir(parents=True, exist_ok=True)
            await self._run(
                ["git", "worktree", "add", "-b", self.branch(session_id), str(target), "HEAD"]
            )
        return target

    async def remove(self, session_id: str) -> None:
        target = self.path(session_id)
        if not target.is_relative_to(self.base_dir):
            raise WorktreeError("Refusing to remove a path outside the worktree directory.")
        if not target.exists():
            return
        async with self._lock:
            await self._run(["git", "worktree", "remove", "--force", str(target)], check=False)
            await self._run(["git", "branch", "-D", self.branch(session_id)], check=False)

    async def _run(self, args: list[str], *, check: bool = True) -> None:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=self.repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if check and process.returncode != 0:
            raise WorktreeError((stderr or stdout).decode().strip())
