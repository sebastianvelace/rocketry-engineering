"""Git worktree isolation for sessions that edit files concurrently.

Each isolated session gets its own working tree under
``.rocketry/worktrees/<session_id>`` on a dedicated ``workstation/<session_id>``
branch, so two sessions editing the repository at the same time never step on
each other's uncommitted changes. Removal is only ever scoped to paths this
module created — it never touches the user's real working tree.

Removal and branch deletion rely on git's own built-in safety checks
(``git worktree remove`` without ``--force`` refuses on uncommitted or
untracked changes; ``git branch -d`` without ``-D`` refuses on unmerged
commits) rather than bypassing them — a worktree with real work in it is
never silently destroyed.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path


class WorktreeError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorktreeStatus:
    branch: str
    base_branch: str
    uncommitted_files: int
    commits_ahead: int

    @property
    def has_pending(self) -> bool:
        return self.uncommitted_files > 0 or self.commits_ahead > 0


class WorktreeHasPendingChangesError(WorktreeError):
    def __init__(self, status: WorktreeStatus):
        super().__init__(
            f"Worktree for branch {status.branch} has {status.uncommitted_files} "
            f"uncommitted file(s) and {status.commits_ahead} commit(s) not yet "
            f"merged into {status.base_branch}."
        )
        self.status = status


class WorktreeManager:
    def __init__(self, repo_root: Path, *, base_dir: Path | None = None):
        self.repo_root = repo_root
        self.base_dir = base_dir or repo_root / ".rocketry" / "worktrees"
        self._lock = asyncio.Lock()

    def branch(self, session_id: str) -> str:
        return f"workstation/{session_id}"

    def path(self, session_id: str) -> Path:
        return self.base_dir / session_id

    async def create(self, session_id: str) -> tuple[Path, str]:
        target = self.path(session_id)
        async with self._lock:
            base_branch = (
                await self._run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True
                )
            ).strip()
            self.base_dir.mkdir(parents=True, exist_ok=True)
            await self._run(
                ["git", "worktree", "add", "-b", self.branch(session_id), str(target), "HEAD"]
            )
        return target, base_branch or "HEAD"

    async def status(self, session_id: str, base_branch: str) -> WorktreeStatus:
        target = self.path(session_id)
        branch = self.branch(session_id)
        porcelain = await self._run(
            ["git", "-C", str(target), "status", "--porcelain"], capture=True
        )
        uncommitted_files = len([line for line in porcelain.splitlines() if line.strip()])
        ahead_raw = await self._run(
            ["git", "rev-list", "--count", f"{base_branch}..{branch}"],
            capture=True,
            check=False,
        )
        try:
            commits_ahead = int(ahead_raw.strip() or "0")
        except ValueError:
            commits_ahead = 0
        return WorktreeStatus(
            branch=branch,
            base_branch=base_branch,
            uncommitted_files=uncommitted_files,
            commits_ahead=commits_ahead,
        )

    async def diff(self, session_id: str, base_branch: str) -> str:
        target = self.path(session_id)
        branch = self.branch(session_id)
        sections = []
        committed = await self._run(
            ["git", "diff", f"{base_branch}...{branch}"], capture=True, check=False
        )
        if committed.strip():
            sections.append(f"# Committed on {branch} since it diverged from {base_branch}\n{committed}")

        # git diff HEAD only shows tracked-file changes — a brand new
        # untracked file is invisible to it, so list those separately
        # rather than silently omitting them from the review.
        uncommitted = await self._run(
            ["git", "-C", str(target), "diff", "HEAD"], capture=True, check=False
        )
        porcelain = await self._run(
            ["git", "-C", str(target), "status", "--porcelain"], capture=True
        )
        untracked = [
            line[3:] for line in porcelain.splitlines() if line.startswith("??")
        ]
        uncommitted_parts = []
        if uncommitted.strip():
            uncommitted_parts.append(uncommitted)
        if untracked:
            uncommitted_parts.append("New untracked file(s): " + ", ".join(untracked))
        if uncommitted_parts:
            sections.append("# Uncommitted changes in the worktree\n" + "\n".join(uncommitted_parts))
        return "\n\n".join(sections)

    async def merge(self, session_id: str, base_branch: str) -> str:
        """Commit any pending work on the isolated branch, then merge it
        into base_branch. Refuses outright if the repo root isn't clean and
        on base_branch already — this never touches the operator's real
        working tree state beyond the merge commit itself."""
        target = self.path(session_id)
        branch = self.branch(session_id)
        async with self._lock:
            porcelain = await self._run(
                ["git", "-C", str(target), "status", "--porcelain"], capture=True
            )
            if porcelain.strip():
                await self._run(["git", "-C", str(target), "add", "-A"])
                await self._run(
                    [
                        "git",
                        "-C",
                        str(target),
                        "commit",
                        "-m",
                        f"Isolated session changes on {branch}",
                    ]
                )

            root_status = await self._run(["git", "status", "--porcelain"], capture=True)
            if root_status.strip():
                raise WorktreeError(
                    f"Refusing to merge: {self.repo_root} has its own uncommitted "
                    "changes. Commit or stash them first."
                )
            current_branch = (
                await self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
            ).strip()
            if current_branch != base_branch:
                raise WorktreeError(
                    f"Refusing to merge: checked out branch is {current_branch!r}, "
                    f"expected {base_branch!r}. Check out {base_branch} first."
                )

            before = (await self._run(["git", "rev-parse", "HEAD"], capture=True)).strip()
            await self._run(
                ["git", "merge", "--no-ff", branch, "-m", f"Merge isolated session ({branch})"]
            )
            after = (await self._run(["git", "rev-parse", "HEAD"], capture=True)).strip()
        return after if after != before else "already up to date"

    async def remove(self, session_id: str, *, force: bool = False) -> None:
        target = self.path(session_id)
        if not target.is_relative_to(self.base_dir):
            raise WorktreeError("Refusing to remove a path outside the worktree directory.")
        if not target.exists():
            return
        async with self._lock:
            remove_args = ["git", "worktree", "remove", str(target)]
            if force:
                remove_args.insert(3, "--force")
            await self._run(remove_args)
            branch_args = ["git", "branch", "-D" if force else "-d", self.branch(session_id)]
            await self._run(branch_args, check=False)

    async def _run(
        self, args: list[str], *, check: bool = True, capture: bool = False
    ) -> str:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=self.repo_root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if check and process.returncode != 0:
            raise WorktreeError((stderr or stdout).decode().strip())
        return stdout.decode() if capture else ""
