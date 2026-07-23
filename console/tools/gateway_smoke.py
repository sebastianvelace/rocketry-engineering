#!/usr/bin/env python3
"""Quota-free HTTP/WebSocket smoke test for a running local gateway."""
from __future__ import annotations

import argparse
import asyncio
import json
import urllib.request
from pathlib import Path

import websockets


def request(url: str, token: str, *, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


async def run(host: str, port: int, token: str, workspace: Path) -> dict:
    base = f"http://{host}:{port}"
    health = request(f"{base}/health", token)
    created = request(
        f"{base}/api/sessions",
        token,
        payload={
            "provider": "codex",
            "workspace": str(workspace.resolve()),
            "title": "Gateway smoke test",
        },
    )
    session = created["session"]
    uri = f"ws://{host}:{port}/ws/sessions/{session['id']}?after=0"
    async with websockets.connect(
        uri,
        subprotocols=["rocketry", token],
        open_timeout=5,
    ) as websocket:
        event = json.loads(await asyncio.wait_for(websocket.recv(), timeout=5))
    if event.get("text") != "Session created":
        raise RuntimeError(f"Unexpected replay event: {event}")
    return {
        "ok": True,
        "version": health["version"],
        "session_id": session["id"],
        "websocket_event_sequence": event["sequence"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", required=True)
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                run(args.host, args.port, args.token, args.workspace)
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
