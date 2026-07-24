import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from gateway.manager import SessionManager
from gateway.server import GatewayConfig, create_app, websocket_credentials
from gateway.store import GatewayStore


class FakeAdapter:
    def __init__(
        self,
        *,
        provider,
        workspace,
        event_sink,
        provider_session_id=None,
    ):
        self.provider_session_id = provider_session_id or f"{provider}-thread"
        self.prompts = []
        self.models = []
        self.available_commands = [{"name": "compact"}]

    async def start(self):
        return self.provider_session_id

    async def send_turn(self, prompt):
        self.prompts.append(prompt)
        return "turn-1"

    async def interrupt(self):
        return None

    async def set_model(self, model):
        self.models.append(model)

    async def close(self):
        return None


class FakeUsageService:
    async def read(self, *, force=False):
        return {
            "ok": True,
            "refreshed_at": "2026-07-24T00:00:00+00:00",
            "cached": not force,
            "providers": {
                "claude": {"available": True, "windows": []},
                "codex": {"available": True, "rate_limits": {}},
            },
            "local": {"claude": {}, "codex": {}},
        }


class GatewayServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
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
        )
        self.config = GatewayConfig(token="test-token")
        self.app = create_app(
            self.config,
            store=self.store,
            manager=self.manager,
            usage_service=FakeUsageService(),
        )
        self.headers = {"Authorization": "Bearer test-token"}

    def tearDown(self):
        self.temporary.cleanup()

    async def request(self, method, path, **kwargs):
        transport = httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://gateway.test",
        ) as client:
            return await client.request(method, path, **kwargs)

    async def create_session(self, provider="codex"):
        response = await self.request(
            "POST",
            "/api/sessions",
            headers=self.headers,
            json={
                "provider": provider,
                "workspace": str(self.root),
                "title": "Gateway test",
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()["session"]

    def test_health_is_public_but_session_data_requires_token(self):
        async def exercise():
            health = await self.request("GET", "/health")
            response = await self.request("GET", "/api/sessions")
            return health, response

        health, response = asyncio.run(exercise())
        self.assertEqual(health.json()["version"], "0.1.0")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "unauthorized")

    def test_local_development_origin_is_allowed_with_dynamic_port(self):
        response = asyncio.run(
            self.request(
                "OPTIONS",
                "/api/status",
                headers={
                    "Origin": "http://127.0.0.1:1420",
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization",
                },
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://127.0.0.1:1420",
        )

    def test_session_message_and_event_history(self):
        async def exercise():
            session = await self.create_session()
            message = await self.request(
                "POST",
                f"/api/sessions/{session['id']}/messages",
                headers=self.headers,
                json={"text": "Run the checks"},
            )
            history = await self.request(
                "GET",
                f"/api/sessions/{session['id']}/events",
                headers=self.headers,
            )
            return message, history

        message, history = asyncio.run(exercise())

        self.assertEqual(message.status_code, 202)
        self.assertEqual(self.adapters[0].prompts, ["Run the checks"])
        texts = [event["text"] for event in history.json()["events"]]
        self.assertIn("Run the checks", texts)
        self.assertIn("Turn submitted", texts)

    def test_connect_prewarms_provider_without_submitting_a_turn(self):
        async def exercise():
            session = await self.create_session(provider="claude")
            connected = await self.request(
                "POST",
                f"/api/sessions/{session['id']}/connect",
                headers=self.headers,
            )
            return connected

        connected = asyncio.run(exercise())
        self.assertEqual(connected.status_code, 200)
        self.assertEqual(connected.json()["session"]["status"], "ready")
        self.assertEqual(self.adapters[0].prompts, [])

    def test_delete_session_removes_it_and_returns_not_found_afterward(self):
        async def exercise():
            session = await self.create_session()
            await self.request(
                "POST",
                f"/api/sessions/{session['id']}/connect",
                headers=self.headers,
            )
            deleted = await self.request(
                "DELETE",
                f"/api/sessions/{session['id']}",
                headers=self.headers,
            )
            missing = await self.request(
                "GET",
                f"/api/sessions/{session['id']}",
                headers=self.headers,
            )
            return session, deleted, missing

        session, deleted, missing = asyncio.run(exercise())

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted_session_id"], session["id"])
        self.assertEqual(missing.status_code, 404)

    def test_claude_model_change_is_persisted_without_a_turn(self):
        async def exercise():
            session = await self.create_session(provider="claude")
            changed = await self.request(
                "POST",
                f"/api/sessions/{session['id']}/model",
                headers=self.headers,
                json={"model": "opus"},
            )
            return changed

        changed = asyncio.run(exercise())
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["session"]["metadata"]["model"], "opus")
        self.assertEqual(self.adapters[0].models, ["opus"])
        self.assertEqual(self.adapters[0].prompts, [])

    def test_dispatchable_claude_command_uses_provider_without_becoming_plain_prompt(self):
        async def exercise():
            session = await self.create_session(provider="claude")
            response = await self.request(
                "POST",
                f"/api/sessions/{session['id']}/commands",
                headers=self.headers,
                json={"command": "compact", "arguments": "retain decisions"},
            )
            return response

        response = asyncio.run(exercise())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "running")
        self.assertEqual(self.adapters[0].prompts, ["/compact retain decisions"])

    def test_usage_endpoint_exposes_provider_snapshot(self):
        response = asyncio.run(
            self.request(
                "GET",
                "/api/usage?refresh=1",
                headers=self.headers,
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["cached"])
        self.assertTrue(response.json()["providers"]["codex"]["available"])

    def test_wiring_endpoint_returns_browser_safe_svg(self):
        response = asyncio.run(
            self.request(
                "GET",
                "/api/wiring?language=es",
                headers=self.headers,
            )
        )
        self.assertEqual(response.status_code, 200)
        guide = response.json()["guides"][0]
        self.assertIsInstance(guide["svg"], str)
        self.assertTrue(guide["svg"].startswith("<svg"))
        self.assertIn("cable", guide["pins"][0]["how"])

    def test_websocket_subprotocol_carries_token_without_query_string(self):
        self.assertEqual(
            websocket_credentials("rocketry, test-token"),
            ("test-token", "rocketry"),
        )
        self.assertEqual(websocket_credentials("wrong"), ("", None))

    def test_workspace_escape_is_rejected(self):
        response = asyncio.run(
            self.request(
                "POST",
                "/api/sessions",
                headers=self.headers,
                json={"provider": "codex", "workspace": "/"},
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()
