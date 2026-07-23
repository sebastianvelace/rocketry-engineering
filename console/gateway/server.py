"""Authenticated localhost API and WebSocket for the desktop client."""
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.responses import FileResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from gateway.manager import SessionManager
from gateway.store import GatewayStore

VERSION = "0.1.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONSOLE_ROOT = Path(__file__).resolve().parents[1]
CORE_ROOT = CONSOLE_ROOT / "core"
sys.path.insert(0, str(CORE_ROOT))

import artifacts  # noqa: E402
import services  # noqa: E402


@dataclass(frozen=True)
class GatewayConfig:
    token: str
    host: str = "127.0.0.1"
    port: int = 8765


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": {"code": code, "message": message}},
        status_code=status,
    )


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    return authorization[len(prefix):] if authorization.startswith(prefix) else ""


def websocket_credentials(protocol_header: str) -> tuple[str, str | None]:
    protocols = [
        value.strip()
        for value in protocol_header.split(",")
        if value.strip()
    ]
    if len(protocols) >= 2 and protocols[0] == "rocketry":
        return protocols[1], "rocketry"
    return "", None


def create_app(
    config: GatewayConfig,
    *,
    store: GatewayStore | None = None,
    manager: SessionManager | None = None,
) -> Starlette:
    gateway_store = store or GatewayStore()
    session_manager = manager or SessionManager(
        gateway_store,
        allowed_workspaces=[REPOSITORY_ROOT],
    )
    artifact_store = artifacts.ArtifactStore()
    history_service = services.HistoryService()
    bench_service = services.BenchService()

    def authorized(request: Request) -> bool:
        return secrets.compare_digest(bearer_token(request), config.token)

    async def health(request: Request):
        return JSONResponse({"ok": True, "version": VERSION})

    async def list_sessions(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            limit = int(request.query_params.get("limit", "100"))
            sessions = gateway_store.list_sessions(limit=limit)
            return JSONResponse(
                {"ok": True, "sessions": [gateway_store.serialize(item) for item in sessions]}
            )
        except ValueError as exc:
            return error_response("invalid_request", str(exc), 400)

    async def create_session(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            payload = await request.json()
            session = await session_manager.create_session(
                provider=payload.get("provider"),
                workspace=payload.get("workspace") or str(REPOSITORY_ROOT),
                title=payload.get("title") or "New session",
            )
            return JSONResponse(
                {"ok": True, "session": gateway_store.serialize(session)},
                status_code=201,
            )
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return error_response("invalid_request", str(exc), 400)

    async def get_session(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            session = gateway_store.get_session(request.path_params["session_id"])
            return JSONResponse({"ok": True, "session": gateway_store.serialize(session)})
        except KeyError as exc:
            return error_response("not_found", str(exc), 404)

    async def list_events(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            session_id = request.path_params["session_id"]
            gateway_store.get_session(session_id)
            after = int(request.query_params.get("after", "0"))
            limit = int(request.query_params.get("limit", "500"))
            events = gateway_store.list_events(
                session_id,
                after_sequence=after,
                limit=limit,
            )
            return JSONResponse(
                {"ok": True, "events": [gateway_store.serialize(item) for item in events]}
            )
        except KeyError as exc:
            return error_response("not_found", str(exc), 404)
        except ValueError as exc:
            return error_response("invalid_request", str(exc), 400)

    async def send_message(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            payload = await request.json()
            event = await session_manager.send_message(
                request.path_params["session_id"],
                str(payload.get("text") or ""),
            )
            return JSONResponse({"ok": True, "event": gateway_store.serialize(event)}, status_code=202)
        except KeyError as exc:
            return error_response("not_found", str(exc), 404)
        except ValueError as exc:
            return error_response("invalid_request", str(exc), 400)
        except RuntimeError as exc:
            return error_response("session_busy", str(exc), 409)

    async def interrupt(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            await session_manager.interrupt(request.path_params["session_id"])
            return JSONResponse({"ok": True})
        except KeyError as exc:
            return error_response("not_found", str(exc), 404)

    async def pending_approvals(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            session_id = request.path_params["session_id"]
            gateway_store.get_session(session_id)
            approvals = gateway_store.list_pending_approvals(session_id)
            return JSONResponse(
                {
                    "ok": True,
                    "approvals": [gateway_store.serialize(item) for item in approvals],
                }
            )
        except KeyError as exc:
            return error_response("not_found", str(exc), 404)

    async def resolve_approval(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            payload = await request.json()
            if not isinstance(payload.get("approved"), bool):
                raise ValueError("approved must be a boolean.")
            approval = await session_manager.resolve_approval(
                request.path_params["approval_id"],
                approved=payload["approved"],
                for_session=bool(payload.get("for_session", False)),
            )
            return JSONResponse(
                {"ok": True, "approval": gateway_store.serialize(approval)}
            )
        except KeyError as exc:
            return error_response("not_found", str(exc), 404)
        except ValueError as exc:
            return error_response("invalid_request", str(exc), 400)

    async def engineering_status(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            ports = bench_service.list_ports()
        except services.ServiceError:
            ports = []
        return JSONResponse(
            {
                "ok": True,
                "ports": ports,
                "saved_runs": history_service.count(),
                "openmotor_ready": (
                    Path.home() / "openMotor" / ".venv" / "bin" / "python"
                ).is_file(),
                "openrocket_ready": (
                    Path.home() / "openrocket" / ".venv" / "bin" / "python"
                ).is_file(),
            }
        )

    async def list_runs(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        kind = request.query_params.get("kind") or None
        runs = history_service.list(kind)
        return JSONResponse(
            {
                "ok": True,
                "runs": [
                    {
                        "id": run.id,
                        "created_at": run.created_at,
                        "kind": run.kind,
                        "meta": run.meta,
                        "note": run.note,
                    }
                    for run in runs[:500]
                ],
            }
        )

    async def get_run(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            offset = int(request.query_params.get("offset", "0"))
            limit = int(request.query_params.get("limit", "2000"))
            if offset < 0 or limit < 1 or limit > 10000:
                raise ValueError("Invalid run page.")
            run = history_service.get(int(request.path_params["run_id"]))
            return JSONResponse(
                {
                    "ok": True,
                    "run": {
                        "id": run.id,
                        "created_at": run.created_at,
                        "kind": run.kind,
                        "meta": run.meta,
                        "columns": run.columns,
                        "rows": run.rows[offset:offset + limit],
                        "row_count": len(run.rows),
                        "offset": offset,
                        "note": run.note,
                    },
                }
            )
        except services.ServiceError as exc:
            return error_response(exc.code, exc.message, 404)
        except (TypeError, ValueError) as exc:
            return error_response("invalid_request", str(exc), 400)

    async def list_artifacts(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        try:
            limit = int(request.query_params.get("limit", "100"))
            items = artifact_store.list(limit=limit)
            return JSONResponse(
                {
                    "ok": True,
                    "artifacts": [
                        {
                            **artifact.__dict__,
                            "download_url": f"/api/artifacts/{artifact.id}/content",
                        }
                        for artifact in items
                    ],
                }
            )
        except ValueError as exc:
            return error_response("invalid_request", str(exc), 400)

    async def artifact_content(request: Request):
        if not authorized(request):
            return error_response("unauthorized", "A valid gateway token is required.", 401)
        artifact = artifact_store.get(request.path_params["artifact_id"])
        if artifact is None:
            return error_response("not_found", "Artifact does not exist.", 404)
        path = Path(artifact.path).resolve()
        if artifact_store.root.resolve() not in path.parents or not path.is_file():
            return error_response("not_found", "Artifact file is unavailable.", 404)
        return FileResponse(
            path,
            media_type=artifact.media_type,
            filename=path.name,
        )

    async def session_stream(websocket: WebSocket):
        token, protocol = websocket_credentials(
            websocket.headers.get("sec-websocket-protocol", "")
        )
        if not secrets.compare_digest(token, config.token):
            await websocket.close(code=4401)
            return
        session_id = websocket.path_params["session_id"]
        try:
            gateway_store.get_session(session_id)
        except KeyError:
            await websocket.close(code=4404)
            return
        await websocket.accept(subprotocol=protocol)
        queue = session_manager.subscribe(session_id)
        try:
            after = int(websocket.query_params.get("after", "0"))
            last_sequence = after
            replay = gateway_store.list_events(
                session_id,
                after_sequence=after,
                limit=2000,
            )
            for event in replay:
                payload = gateway_store.serialize(event)
                last_sequence = max(last_sequence, event.sequence)
                await websocket.send_json(payload)
            while True:
                event_task = asyncio.create_task(queue.get())
                receive_task = asyncio.create_task(websocket.receive())
                done, pending = await asyncio.wait(
                    {event_task, receive_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                if receive_task in done:
                    incoming = receive_task.result()
                    if incoming.get("type") == "websocket.disconnect":
                        break
                    continue
                payload = event_task.result()
                sequence = int(payload.get("sequence", 0))
                if sequence <= last_sequence:
                    continue
                last_sequence = sequence
                await websocket.send_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            session_manager.unsubscribe(session_id, queue)

    @asynccontextmanager
    async def lifespan(app: Starlette):
        await session_manager.recover()
        yield
        await session_manager.close()

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/api/sessions", list_sessions, methods=["GET"]),
        Route("/api/sessions", create_session, methods=["POST"]),
        Route("/api/sessions/{session_id:str}", get_session, methods=["GET"]),
        Route("/api/sessions/{session_id:str}/events", list_events, methods=["GET"]),
        Route("/api/sessions/{session_id:str}/messages", send_message, methods=["POST"]),
        Route("/api/sessions/{session_id:str}/interrupt", interrupt, methods=["POST"]),
        Route("/api/sessions/{session_id:str}/approvals", pending_approvals, methods=["GET"]),
        Route("/api/approvals/{approval_id:str}", resolve_approval, methods=["POST"]),
        Route("/api/status", engineering_status, methods=["GET"]),
        Route("/api/runs", list_runs, methods=["GET"]),
        Route("/api/runs/{run_id:int}", get_run, methods=["GET"]),
        Route("/api/artifacts", list_artifacts, methods=["GET"]),
        Route(
            "/api/artifacts/{artifact_id:str}/content",
            artifact_content,
            methods=["GET"],
        ),
        WebSocketRoute("/ws/sessions/{session_id:str}", session_stream),
    ]
    app = Starlette(routes=routes, lifespan=lifespan)
    app.state.gateway_store = gateway_store
    app.state.session_manager = session_manager
    return CORSMiddleware(
        app,
        allow_origins=["tauri://localhost", "http://localhost", "http://127.0.0.1"],
        allow_origin_regex=r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?$",
        allow_methods=["GET", "POST"],
        allow_headers=["authorization", "content-type"],
    )


def main() -> None:
    token = os.environ.get("ROCKETRY_GATEWAY_TOKEN") or secrets.token_urlsafe(32)
    port = int(os.environ.get("ROCKETRY_GATEWAY_PORT", "8765"))
    database_path = os.environ.get("ROCKETRY_GATEWAY_DB")
    config = GatewayConfig(token=token, port=port)
    print(
        json.dumps(
            {
                "event": "gateway_ready",
                "host": config.host,
                "port": config.port,
                "token": config.token,
            }
        ),
        flush=True,
    )
    store = GatewayStore(Path(database_path)) if database_path else GatewayStore()
    manager = SessionManager(store, allowed_workspaces=[REPOSITORY_ROOT])
    uvicorn.run(
        create_app(config, store=store, manager=manager),
        host=config.host,
        port=config.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
