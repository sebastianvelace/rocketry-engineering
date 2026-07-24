import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

from gateway.worktrees import WorktreeError, WorktreeHasPendingChangesError, WorktreeManager


def init_repo(root: Path) -> None:
    """Mirrors the real repo's .gitignore (which excludes .rocketry/) so
    these tests see the same "is the root clean?" behavior production
    does — without it, the worktrees directory itself would show up as an
    untracked change at the repo root and every merge would be refused."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / ".gitignore").write_text(".rocketry/\n")
    (root / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)


class WorktreeManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        init_repo(self.root)
        self.manager = WorktreeManager(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_create_allocates_an_isolated_worktree_on_its_own_branch_off_the_current_head(self):
        async def exercise():
            path, base_branch = await self.manager.create("session-1")
            (path / "scratch.txt").write_text("isolated edit\n")
            return path, base_branch

        path, base_branch = asyncio.run(exercise())
        self.assertTrue(path.is_dir())
        self.assertEqual(path, self.root / ".rocketry" / "worktrees" / "session-1")
        self.assertFalse((self.root / "scratch.txt").exists())
        self.assertIn(base_branch, ("main", "master"))

        branches = subprocess.run(
            ["git", "branch", "--list", "workstation/session-1"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertIn("workstation/session-1", branches)

    def test_remove_cleans_up_a_clean_worktree_and_its_branch(self):
        async def exercise():
            await self.manager.create("session-2")
            await self.manager.remove("session-2")

        asyncio.run(exercise())
        self.assertFalse((self.root / ".rocketry" / "worktrees" / "session-2").exists())
        branches = subprocess.run(
            ["git", "branch", "--list", "workstation/session-2"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertNotIn("workstation/session-2", branches)

    def test_remove_refuses_to_destroy_uncommitted_work_without_force(self):
        async def exercise():
            path, _ = await self.manager.create("session-3")
            (path / "scratch.txt").write_text("not committed anywhere\n")
            await self.manager.remove("session-3")

        with self.assertRaises(WorktreeError):
            asyncio.run(exercise())
        self.assertTrue((self.root / ".rocketry" / "worktrees" / "session-3").exists())
        self.assertTrue((self.root / ".rocketry" / "worktrees" / "session-3" / "scratch.txt").exists())

    def test_remove_with_force_discards_uncommitted_work(self):
        async def exercise():
            path, _ = await self.manager.create("session-4")
            (path / "scratch.txt").write_text("discard me\n")
            await self.manager.remove("session-4", force=True)

        asyncio.run(exercise())
        self.assertFalse((self.root / ".rocketry" / "worktrees" / "session-4").exists())
        branches = subprocess.run(
            ["git", "branch", "--list", "workstation/session-4"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertNotIn("workstation/session-4", branches)

    def test_remove_is_a_no_op_for_an_unknown_session(self):
        asyncio.run(self.manager.remove("never-created"))

    def test_remove_refuses_a_path_outside_the_worktree_directory(self):
        escaped = WorktreeManager(self.root, base_dir=self.root / ".rocketry" / "worktrees")
        escaped.path = lambda session_id: self.root  # type: ignore[method-assign]
        with self.assertRaises(WorktreeError):
            asyncio.run(escaped.remove("session-5"))

    def test_status_reports_uncommitted_files_and_commits_ahead(self):
        async def exercise():
            path, base_branch = await self.manager.create("session-6")
            clean = await self.manager.status("session-6", base_branch)

            (path / "scratch.txt").write_text("dirty\n")
            dirty = await self.manager.status("session-6", base_branch)

            subprocess.run(["git", "add", "-A"], cwd=path, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "committed change"], cwd=path, check=True)
            committed = await self.manager.status("session-6", base_branch)
            return clean, dirty, committed

        clean, dirty, committed = asyncio.run(exercise())
        self.assertFalse(clean.has_pending)
        self.assertEqual(dirty.uncommitted_files, 1)
        self.assertTrue(dirty.has_pending)
        self.assertEqual(committed.uncommitted_files, 0)
        self.assertEqual(committed.commits_ahead, 1)
        self.assertTrue(committed.has_pending)

    def test_diff_includes_committed_and_uncommitted_sections(self):
        async def exercise():
            path, base_branch = await self.manager.create("session-7")
            (path / "committed.txt").write_text("committed content\n")
            subprocess.run(["git", "add", "-A"], cwd=path, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "add committed file"], cwd=path, check=True)
            (path / "pending.txt").write_text("pending content\n")
            return await self.manager.diff("session-7", base_branch)

        diff = asyncio.run(exercise())
        self.assertIn("committed.txt", diff)
        self.assertIn("Committed on", diff)
        self.assertIn("pending.txt", diff)
        self.assertIn("Uncommitted changes", diff)

    def test_merge_commits_pending_work_and_merges_into_base(self):
        async def exercise():
            path, base_branch = await self.manager.create("session-8")
            (path / "feature.txt").write_text("feature content\n")
            await self.manager.merge("session-8", base_branch)
            return base_branch

        base_branch = asyncio.run(exercise())
        self.assertEqual(
            subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=self.root, capture_output=True, text=True, check=True).stdout.strip(),
            base_branch,
        )
        self.assertTrue((self.root / "feature.txt").exists())
        log = subprocess.run(["git", "log", "--oneline", "-3"], cwd=self.root, capture_output=True, text=True, check=True).stdout
        self.assertIn("Merge isolated session", log)

        # A clean, non-force remove now succeeds: the branch is fully merged.
        status = asyncio.run(self.manager.status("session-8", base_branch))
        self.assertFalse(status.has_pending)
        asyncio.run(self.manager.remove("session-8"))
        self.assertFalse((self.root / ".rocketry" / "worktrees" / "session-8").exists())

    def test_merge_refuses_when_repo_root_has_its_own_uncommitted_changes(self):
        async def exercise():
            path, base_branch = await self.manager.create("session-9")
            (path / "feature.txt").write_text("feature content\n")
            (self.root / "unrelated.txt").write_text("operator's own dirty work\n")
            await self.manager.merge("session-9", base_branch)

        with self.assertRaisesRegex(WorktreeError, "own uncommitted"):
            asyncio.run(exercise())
        self.assertFalse((self.root / "feature.txt").exists())

    def test_merge_refuses_when_checked_out_branch_does_not_match_base(self):
        async def exercise():
            path, base_branch = await self.manager.create("session-10")
            (path / "feature.txt").write_text("feature content\n")
            subprocess.run(["git", "checkout", "-b", "unrelated-branch"], cwd=self.root, check=True)
            await self.manager.merge("session-10", base_branch)

        with self.assertRaisesRegex(WorktreeError, "unrelated-branch"):
            asyncio.run(exercise())


class WorktreePendingChangesErrorTests(unittest.TestCase):
    def test_error_carries_the_status_it_was_raised_for(self):
        from gateway.worktrees import WorktreeStatus

        status = WorktreeStatus(branch="workstation/x", base_branch="main", uncommitted_files=2, commits_ahead=1)
        error = WorktreeHasPendingChangesError(status)
        self.assertIs(error.status, status)
        self.assertIn("workstation/x", str(error))


if __name__ == "__main__":
    unittest.main()
