import tempfile
import unittest
from pathlib import Path

from gateway.store import GatewayStore


class GatewayStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = GatewayStore(Path(self.temporary.name) / "gateway.db")

    def tearDown(self):
        self.temporary.cleanup()

    def test_session_and_events_survive_new_store_instance(self):
        session = self.store.create_session(
            provider="codex",
            workspace="/workspace",
            title="Motor analysis",
        )
        first = self.store.append_event(
            session.id,
            type="user_message",
            role="user",
            text="Run the compact sweep",
            data={"language": "en"},
        )
        self.store.update_session(
            session.id,
            status="running",
            provider_session_id="thread-123",
        )

        reopened = GatewayStore(self.store.path)
        loaded = reopened.get_session(session.id)
        events = reopened.list_events(session.id)

        self.assertEqual(loaded.provider, "codex")
        self.assertEqual(loaded.provider_session_id, "thread-123")
        self.assertEqual(loaded.status, "running")
        self.assertEqual(events, [first])

    def test_duplicate_provider_event_is_idempotent(self):
        session = self.store.create_session(provider="claude", workspace="/workspace")
        first = self.store.append_event(
            session.id,
            type="assistant_delta",
            text="hello",
            event_id="provider-event-1",
        )
        duplicate = self.store.append_event(
            session.id,
            type="assistant_delta",
            text="should not replace",
            event_id="provider-event-1",
        )

        self.assertEqual(first, duplicate)
        self.assertEqual(len(self.store.list_events(session.id)), 1)
        self.assertEqual(duplicate.text, "hello")

    def test_event_pagination_is_ordered_and_bounded(self):
        session = self.store.create_session(provider="codex", workspace="/workspace")
        events = [
            self.store.append_event(
                session.id,
                type="command_output",
                text=f"line {index}",
            )
            for index in range(5)
        ]

        page = self.store.list_events(
            session.id,
            after_sequence=events[1].sequence,
            limit=2,
        )

        self.assertEqual([event.text for event in page], ["line 2", "line 3"])

    def test_approval_resolution_is_idempotent(self):
        session = self.store.create_session(provider="claude", workspace="/workspace")
        approval = self.store.create_approval(
            session.id,
            action="network",
            details={"command": "git fetch"},
        )

        approved = self.store.resolve_approval(approval.id, approved=True)
        second = self.store.resolve_approval(approval.id, approved=False)

        self.assertEqual(approved.status, "approved")
        self.assertEqual(second.status, "approved")
        self.assertIsNotNone(second.resolved_at)
        self.assertEqual(self.store.list_pending_approvals(session.id), [])

    def test_startup_marks_only_active_sessions_interrupted(self):
        running = self.store.create_session(provider="codex", workspace="/workspace")
        complete = self.store.create_session(provider="claude", workspace="/workspace")
        self.store.update_session(running.id, status="running")
        self.store.update_session(complete.id, status="completed")

        self.assertEqual(self.store.mark_unfinished_interrupted(), 1)
        self.assertEqual(self.store.get_session(running.id).status, "interrupted")
        self.assertEqual(self.store.get_session(complete.id).status, "completed")

    def test_startup_cancels_orphaned_approval(self):
        session = self.store.create_session(provider="codex", workspace="/workspace")
        self.store.update_session(session.id, status="waiting_approval")
        approval = self.store.create_approval(session.id, action="Bash")

        self.store.mark_unfinished_interrupted()

        self.assertEqual(self.store.get_approval(approval.id).status, "cancelled")

    def test_payload_limits_reject_unbounded_events(self):
        session = self.store.create_session(provider="codex", workspace="/workspace")
        with self.assertRaisesRegex(ValueError, "too large"):
            self.store.append_event(
                session.id,
                type="command_output",
                text="x" * 1_000_001,
            )


if __name__ == "__main__":
    unittest.main()
