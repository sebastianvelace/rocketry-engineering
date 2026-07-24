import asyncio
import subprocess
import tempfile
import unittest
from pathlib import Path

from gateway.manager import SessionManager
from gateway.providers.base import ProviderApproval, ProviderEvent
from gateway.store import GatewayStore
from gateway.worktrees import WorktreeHasPendingChangesError, WorktreeManager


def init_git_repo(root: Path) -> None:
    """Mirrors the real repo's .gitignore (.rocketry/, gateway.db) so a
    merge's "is the repo root clean?" check sees the same thing production
    does — without it, this fixture's own gateway.db and worktrees would
    falsely look like the operator's uncommitted changes."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / ".gitignore").write_text(".rocketry/\ngateway.db\n")
    (root / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=root, check=True)


class FakeAdapter:
    def __init__(
        self,
        *,
        provider,
        workspace,
        event_sink,
        provider_session_id=None,
    ):
        self.provider = provider
        self.workspace = workspace
        self.event_sink = event_sink
        self.provider_session_id = provider_session_id or f"{provider}-session"
        self.prompts = []
        self.interrupted = False
        self.closed = False
        self.approvals = []
        self.guidance = []
        self.turn_id = None

    async def start(self):
        return self.provider_session_id

    async def send_turn(self, prompt):
        self.prompts.append(prompt)
        self.turn_id = "turn-1"
        return "turn-1"

    async def steer(self, prompt):
        self.guidance.append(prompt)

    async def interrupt(self):
        self.interrupted = True

    async def resolve_approval(self, request_id, *, approved, for_session, answers=None):
        self.approvals.append((request_id, approved, for_session, answers))

    async def close(self):
        self.closed = True


class SessionManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        init_git_repo(self.root)
        self.store = GatewayStore(self.root / "gateway.db")
        self.adapters = []

        def factory(**kwargs):
            adapter = FakeAdapter(**kwargs)
            self.adapters.append(adapter)
            return adapter

        self.manager = SessionManager(
            self.store,
            allowed_workspaces=[self.root],
            adapter_factory=factory,
            queue_size=2,
        )
        self.isolated_manager = SessionManager(
            self.store,
            allowed_workspaces=[self.root],
            adapter_factory=factory,
            queue_size=2,
            worktrees=WorktreeManager(self.root),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_message_starts_provider_and_persists_visible_events(self):
        async def exercise():
            session = await self.manager.create_session(
                provider="codex",
                workspace=str(self.root),
                title="Test",
            )
            queue = self.manager.subscribe(session.id)
            submitted = await self.manager.send_message(session.id, "Run tests")
            return session, queue, submitted

        session, queue, submitted = asyncio.run(exercise())
        loaded = self.store.get_session(session.id)
        events = self.store.list_events(session.id)

        self.assertEqual(loaded.provider_session_id, "codex-session")
        self.assertEqual(loaded.status, "running")
        self.assertEqual(self.adapters[0].prompts, ["Run tests"])
        self.assertEqual(submitted.text, "Turn submitted")
        self.assertIn("Run tests", [event.text for event in events])
        self.assertEqual(queue.qsize(), 2)

    def test_reconnect_falls_back_to_a_fresh_provider_session_when_resume_fails(self):
        """A stored provider_session_id can stop being resumable for reasons
        outside this gateway's knowledge (the provider prunes or clears its
        own local session state, observed for real against a live Claude
        Code CLI: "No conversation found with session ID: ..."). Without a
        fallback, every reconnect attempt repeats the same failure forever
        and the conversation is permanently stuck."""

        class FlakyResumeAdapter(FakeAdapter):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.resume_attempted = kwargs.get("provider_session_id") is not None

            async def start(self):
                if self.resume_attempted:
                    raise RuntimeError("No conversation found with session ID: stale-session")
                self.provider_session_id = "fresh-session"
                return self.provider_session_id

        created_adapters = []

        def factory(**kwargs):
            adapter = FlakyResumeAdapter(**kwargs)
            created_adapters.append(adapter)
            return adapter

        manager = SessionManager(
            self.store,
            allowed_workspaces=[self.root],
            adapter_factory=factory,
            queue_size=4,
        )

        async def exercise():
            session = await manager.create_session(provider="claude", workspace=str(self.root))
            self.store.update_session(session.id, provider_session_id="stale-session")
            queue = manager.subscribe(session.id)
            await manager.send_message(session.id, "Continue where we left off")
            return session.id, queue

        session_id, queue = asyncio.run(exercise())

        self.assertEqual(len(created_adapters), 2)
        self.assertTrue(created_adapters[0].resume_attempted)
        self.assertTrue(created_adapters[0].closed)
        self.assertFalse(created_adapters[1].resume_attempted)
        self.assertEqual(created_adapters[1].prompts, ["Continue where we left off"])

        loaded = self.store.get_session(session_id)
        self.assertEqual(loaded.provider_session_id, "fresh-session")
        self.assertEqual(loaded.status, "running")
        events = self.store.list_events(session_id)
        notice = next(event for event in events if event.text == "Provider session could not be resumed; starting a new one")
        self.assertEqual(notice.type, "notice")

    def test_provider_completion_returns_session_to_ready(self):
        async def exercise():
            session = await self.manager.create_session(
                provider="claude",
                workspace=str(self.root),
            )
            await self.manager.send_message(session.id, "Inspect")
            await self.adapters[0].event_sink(
                ProviderEvent("assistant_message", "Done", role="assistant")
            )
            await self.adapters[0].event_sink(
                ProviderEvent("session", "Turn completed")
            )
            return session.id

        session_id = asyncio.run(exercise())
        self.assertEqual(self.store.get_session(session_id).status, "ready")
        self.assertEqual(
            [event.text for event in self.store.list_events(session_id)][-2:],
            ["Done", "Turn completed"],
        )

    def test_native_approval_round_trip_reaches_adapter(self):
        async def exercise():
            session = await self.manager.create_session(
                provider="codex",
                workspace=str(self.root),
            )
            await self.manager.send_message(session.id, "Fetch")
            await self.manager._handle_provider_approval(
                session.id,
                ProviderApproval(
                    request_id=81,
                    action="item/commandExecution/requestApproval",
                    details={"command": "git fetch"},
                ),
            )
            pending = self.store.list_pending_approvals(session.id)
            resolved = await self.manager.resolve_approval(
                pending[0].id,
                approved=True,
                for_session=True,
            )
            return session.id, resolved

        session_id, resolved = asyncio.run(exercise())
        self.assertEqual(resolved.status, "approved")
        self.assertEqual(self.adapters[0].approvals, [(81, True, True, None)])
        self.assertEqual(self.store.get_session(session_id).status, "running")

    def test_interrupt_updates_provider_and_durable_status(self):
        async def exercise():
            session = await self.manager.create_session(
                provider="claude",
                workspace=str(self.root),
            )
            await asyncio.wait_for(
                self.manager.send_message(session.id, "Long task"),
                timeout=2,
            )
            await asyncio.wait_for(self.manager.interrupt(session.id), timeout=2)
            return session.id

        session_id = asyncio.run(exercise())
        self.assertTrue(self.adapters[0].interrupted)
        self.assertEqual(self.store.get_session(session_id).status, "interrupted")

    def test_codex_active_turn_accepts_guidance_without_starting_another_turn(self):
        async def exercise():
            session = await self.manager.create_session(
                provider="codex",
                workspace=str(self.root),
            )
            await self.manager.send_message(session.id, "Run the simulation")
            guided = await self.manager.steer(
                session.id,
                "Use the lighter airframe and keep the same motor.",
            )
            return session.id, guided

        session_id, guided = asyncio.run(exercise())
        self.assertEqual(self.adapters[0].prompts, ["Run the simulation"])
        self.assertEqual(
            self.adapters[0].guidance,
            ["Use the lighter airframe and keep the same motor."],
        )
        self.assertEqual(guided.text, "Active turn guided")
        self.assertEqual(self.store.get_session(session_id).status, "running")
        user_events = [
            event for event in self.store.list_events(session_id)
            if event.type == "user_message"
        ]
        self.assertTrue(user_events[-1].data["steer"])

    def test_delete_session_closes_live_adapter_and_removes_data(self):
        async def exercise():
            session = await self.manager.create_session(
                provider="claude",
                workspace=str(self.root),
            )
            await self.manager.connect(session.id)
            await self.manager._handle_provider_approval(
                session.id,
                ProviderApproval(
                    request_id="approval-1",
                    action="Bash",
                    details={"command": "pytest"},
                ),
            )
            queue = self.manager.subscribe(session.id)
            approval_id = self.store.list_pending_approvals(session.id)[0].id
            await self.manager.delete_session(session.id)
            return session.id, approval_id, queue

        session_id, approval_id, queue = asyncio.run(exercise())

        self.assertTrue(self.adapters[0].closed)
        self.assertNotIn(session_id, self.manager.adapters)
        self.assertNotIn(session_id, self.manager._subscribers)
        self.assertNotIn(approval_id, self.manager._provider_approvals)
        with self.assertRaises(KeyError):
            self.store.get_session(session_id)

    def test_isolated_session_gets_its_own_worktree_and_it_is_removed_on_delete(self):
        async def exercise():
            session = await self.isolated_manager.create_session(
                provider="claude",
                workspace=str(self.root),
                isolated=True,
            )
            worktree_path = Path(session.workspace)
            worktree_exists_after_create = worktree_path.is_dir()
            await self.isolated_manager.delete_session(session.id)
            return session, worktree_path, worktree_exists_after_create

        session, worktree_path, worktree_exists_after_create = asyncio.run(exercise())
        self.assertTrue(worktree_exists_after_create)
        self.assertNotEqual(worktree_path, self.root)
        self.assertTrue(session.metadata["isolated_workspace"])
        self.assertFalse(worktree_path.exists())

    def test_delete_refuses_when_the_worktree_has_uncommitted_work(self):
        async def exercise():
            session = await self.isolated_manager.create_session(
                provider="claude",
                workspace=str(self.root),
                isolated=True,
            )
            (Path(session.workspace) / "agent_edit.txt").write_text("work in progress\n")
            await self.isolated_manager.delete_session(session.id)
            return session

        with self.assertRaises(WorktreeHasPendingChangesError) as raised:
            asyncio.run(exercise())
        self.assertEqual(raised.exception.status.uncommitted_files, 1)
        # Nothing was actually deleted: the session and its worktree survive.
        sessions = [item.id for item in self.store.list_sessions()]
        self.assertEqual(len(sessions), 1)
        session_id = sessions[0]
        self.assertTrue(Path(self.store.get_session(session_id).workspace).exists())

    def test_delete_with_force_discards_pending_worktree_changes(self):
        async def exercise():
            session = await self.isolated_manager.create_session(
                provider="claude",
                workspace=str(self.root),
                isolated=True,
            )
            (Path(session.workspace) / "agent_edit.txt").write_text("discard me\n")
            await self.isolated_manager.delete_session(session.id, force=True)
            return session

        session = asyncio.run(exercise())
        with self.assertRaises(KeyError):
            self.store.get_session(session.id)
        self.assertFalse(Path(session.workspace).exists())

    def test_review_and_merge_worktree_then_delete_cleanly(self):
        async def exercise():
            session = await self.isolated_manager.create_session(
                provider="claude",
                workspace=str(self.root),
                isolated=True,
            )
            (Path(session.workspace) / "agent_edit.txt").write_text("feature work\n")

            review = await self.isolated_manager.get_worktree_review(session.id)
            self.assertTrue(review["has_pending"])
            self.assertIn("agent_edit.txt", review["diff"])

            await self.isolated_manager.merge_worktree(session.id)
            notices = [
                event.text
                for event in self.store.list_events(session.id)
                if event.type == "notice"
            ]
            # Now clean and merged: a non-force delete succeeds.
            await self.isolated_manager.delete_session(session.id)
            return session, notices

        session, notices = asyncio.run(exercise())
        with self.assertRaises(KeyError):
            self.store.get_session(session.id)
        self.assertTrue((self.root / "agent_edit.txt").exists())
        self.assertTrue(any("Merged isolated session" in text for text in notices))

    def test_isolated_session_requires_a_configured_worktree_manager(self):
        async def exercise():
            await self.manager.create_session(
                provider="claude",
                workspace=str(self.root),
                isolated=True,
            )

        with self.assertRaisesRegex(ValueError, "not configured"):
            asyncio.run(exercise())

    def test_workspace_must_be_inside_allowed_root(self):
        async def exercise():
            await self.manager.create_session(
                provider="codex",
                workspace="/",
            )

        with self.assertRaisesRegex(ValueError, "outside"):
            asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
