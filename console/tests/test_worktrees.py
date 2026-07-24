import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

from gateway.worktrees import WorktreeError, WorktreeManager


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)


class WorktreeManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        init_repo(self.root)
        self.manager = WorktreeManager(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_create_allocates_an_isolated_worktree_on_its_own_branch(self):
        async def exercise():
            path = await self.manager.create("session-1")
            (path / "scratch.txt").write_text("isolated edit\n")
            return path

        path = asyncio.run(exercise())
        self.assertTrue(path.is_dir())
        self.assertEqual(path, self.root / ".rocketry" / "worktrees" / "session-1")
        self.assertFalse((self.root / "scratch.txt").exists())

        branches = subprocess.run(
            ["git", "branch", "--list", "workstation/session-1"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        self.assertIn("workstation/session-1", branches)

    def test_remove_cleans_up_the_worktree_and_its_branch(self):
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

    def test_remove_is_a_no_op_for_an_unknown_session(self):
        asyncio.run(self.manager.remove("never-created"))

    def test_remove_refuses_a_path_outside_the_worktree_directory(self):
        escaped = WorktreeManager(self.root, base_dir=self.root / ".rocketry" / "worktrees")
        escaped.path = lambda session_id: self.root  # type: ignore[method-assign]
        with self.assertRaises(WorktreeError):
            asyncio.run(escaped.remove("session-3"))


if __name__ == "__main__":
    unittest.main()
