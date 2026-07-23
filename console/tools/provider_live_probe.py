#!/usr/bin/env python3
"""Run minimal, quota-consuming provider turns for integration validation.

This command is intentionally excluded from CI and refuses to run unless the
caller supplies ``--allow-token-use``. It never grants tools or write access.
"""
from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROBE_ONE = "Reply with exactly ROCKetry_PROBE_OK and nothing else."
PROBE_TWO = "Reply with exactly ROCKetry_PROBE_RESUMED and nothing else."


def json_lines(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def claude_turn(
    prompt: str,
    *,
    session_id: str | None = None,
    resume: str | None = None,
    remote_control: bool = False,
) -> dict[str, Any]:
    command = [
        "claude",
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
        "--include-hook-events",
        "--permission-mode",
        "dontAsk",
        "--tools",
        "",
    ]
    if remote_control:
        command.append("--remote-control")
    if session_id:
        command.extend(("--session-id", session_id))
    if resume:
        command.extend(("--resume", resume))
    command.append(prompt)

    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    events = json_lines(result.stdout)
    observed_session = next(
        (
            event.get("session_id")
            for event in events
            if isinstance(event.get("session_id"), str)
        ),
        session_id or resume,
    )
    result_text = next(
        (
            event.get("result")
            for event in reversed(events)
            if isinstance(event.get("result"), str)
        ),
        "",
    )
    return {
        "returnCode": result.returncode,
        "sessionId": observed_session,
        "result": result_text,
        "eventTypes": sorted(
            {
                str(event.get("type"))
                for event in events
                if event.get("type") is not None
            }
        ),
        "stderr": result.stderr.strip()[-1000:],
    }


class ClaudePersistentClient:
    """Minimal bidirectional CLI transport used only for the feasibility gate."""

    def __init__(self, session_id: str, *, remote_control: bool) -> None:
        command = [
            "claude",
            "-p",
            "--verbose",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--include-partial-messages",
            "--include-hook-events",
            "--replay-user-messages",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--session-id",
            session_id,
        ]
        if remote_control:
            command.append("--remote-control")
        self.session_id = session_id
        self.process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.messages: queue.Queue[dict[str, Any] | BaseException | None] = (
            queue.Queue()
        )
        self.reader = threading.Thread(
            target=self._read_stdout,
            name="claude-probe-reader",
            daemon=True,
        )
        self.reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except BaseException as exc:
            self.messages.put(exc)
        finally:
            self.messages.put(None)

    def send_turn(self, prompt: str) -> dict[str, Any]:
        assert self.process.stdin is not None
        self.process.stdin.write(
            json.dumps(
                {
                    "type": "user",
                    "message": {"role": "user", "content": prompt},
                    "parent_tool_use_id": None,
                    "session_id": self.session_id,
                },
                separators=(",", ":"),
            )
            + "\n"
        )
        self.process.stdin.flush()

        events: list[dict[str, Any]] = []
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                message = self.messages.get(
                    timeout=max(0.1, deadline - time.monotonic())
                )
            except queue.Empty as exc:
                raise TimeoutError("Timed out waiting for persistent Claude") from exc
            if message is None:
                raise RuntimeError("Persistent Claude process closed its output")
            if isinstance(message, BaseException):
                raise RuntimeError("Persistent Claude reader failed") from message
            events.append(message)
            if message.get("type") == "result":
                system_keys = sorted(
                    {
                        key
                        for event in events
                        if event.get("type") == "system"
                        for key in event
                        if key
                        not in {
                            "apiKeySource",
                            "cwd",
                            "mcp_servers",
                            "model",
                            "permissionMode",
                            "plugins",
                            "session_id",
                            "slash_commands",
                            "tools",
                        }
                    }
                )
                return {
                    "result": message.get("result"),
                    "eventTypes": sorted(
                        {
                            str(event.get("type"))
                            for event in events
                            if event.get("type") is not None
                        }
                    ),
                    "systemEventKeys": system_keys,
                }
        raise TimeoutError("Timed out waiting for persistent Claude result")

    def close(self) -> None:
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)


class CodexClient:
    def __init__(self) -> None:
        self.process = subprocess.Popen(
            ["codex", "app-server", "--stdio"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.next_id = 1
        self.pending_events: list[dict[str, Any]] = []
        self.messages: queue.Queue[dict[str, Any] | BaseException | None] = (
            queue.Queue()
        )
        self.reader = threading.Thread(
            target=self._read_stdout,
            name="codex-probe-reader",
            daemon=True,
        )
        self.reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except BaseException as exc:  # surface reader failures to the caller
            self.messages.put(exc)
        finally:
            self.messages.put(None)

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)

    def send(self, payload: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def read(self, timeout: float = 120) -> dict[str, Any]:
        try:
            message = self.messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("Timed out waiting for Codex app-server") from exc
        if message is None:
            raise RuntimeError("Codex app-server closed its output stream")
        if isinstance(message, BaseException):
            raise RuntimeError("Codex app-server reader failed") from message
        return message

    def request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float = 120,
    ) -> dict[str, Any]:
        request_id = self.next_id
        self.next_id += 1
        self.send({"method": method, "id": request_id, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.read(max(0.1, deadline - time.monotonic()))
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message["result"]
            self.pending_events.append(message)
        raise TimeoutError(f"Timed out waiting for {method}")

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "rocketry_provider_probe",
                    "title": "Rocketry Provider Probe",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": False},
            },
        )
        self.send({"method": "initialized", "params": {}})

    def wait_for_turn(self, turn_id: str) -> dict[str, Any]:
        events = list(self.pending_events)
        self.pending_events.clear()
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            for event in events:
                if event.get("method") == "turn/completed":
                    turn = (event.get("params") or {}).get("turn") or {}
                    if turn.get("id") == turn_id:
                        return summarize_codex(events, turn)
            events.append(self.read(max(0.1, deadline - time.monotonic())))
        raise TimeoutError("Timed out waiting for Codex turn completion")


def summarize_codex(
    events: list[dict[str, Any]],
    turn: dict[str, Any],
) -> dict[str, Any]:
    deltas = [
        str((event.get("params") or {}).get("delta", ""))
        for event in events
        if event.get("method") == "item/agentMessage/delta"
    ]
    completed_messages = []
    for event in events:
        if event.get("method") != "item/completed":
            continue
        item = (event.get("params") or {}).get("item") or {}
        if item.get("type") == "agentMessage" and isinstance(item.get("text"), str):
            completed_messages.append(item["text"])
    text = completed_messages[-1] if completed_messages else "".join(deltas)
    return {
        "turnId": turn.get("id"),
        "status": turn.get("status"),
        "result": text,
        "eventTypes": sorted(
            {
                str(event.get("method"))
                for event in events
                if event.get("method") is not None
            }
        ),
    }


def codex_live_probe() -> dict[str, Any]:
    client = CodexClient()
    try:
        client.initialize()
        started = client.request(
            "thread/start",
            {
                "cwd": str(ROOT),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "serviceName": "rocketry_provider_probe",
            },
        )
        thread_id = started["thread"]["id"]
        first = client.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": PROBE_ONE}],
            },
        )
        first_result = client.wait_for_turn(first["turn"]["id"])
    finally:
        client.close()

    resumed = CodexClient()
    try:
        resumed.initialize()
        resumed.request(
            "thread/resume",
            {
                "threadId": thread_id,
                "approvalPolicy": "never",
                "sandbox": "read-only",
            },
        )
        second = resumed.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": PROBE_TWO}],
            },
        )
        second_result = resumed.wait_for_turn(second["turn"]["id"])
    finally:
        resumed.close()

    return {
        "provider": "codex",
        "threadId": thread_id,
        "firstTurn": first_result,
        "resumedTurn": second_result,
    }


def claude_persistent_probe() -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    client = ClaudePersistentClient(session_id, remote_control=True)
    try:
        first = client.send_turn(PROBE_ONE)
        alive_after_first = client.process.poll() is None
        second = client.send_turn(PROBE_TWO)
    finally:
        client.close()
    return {
        "provider": "claude",
        "sessionId": session_id,
        "transport": "persistent-stream-json",
        "remoteControlRequested": True,
        "aliveAfterFirstTurn": alive_after_first,
        "firstTurn": first,
        "resumedTurn": second,
    }


def claude_live_probe(
    test_remote_combination: bool,
    *,
    persistent: bool = False,
) -> dict[str, Any]:
    if persistent:
        return claude_persistent_probe()
    session_id = str(uuid.uuid4())
    remote_attempt = None
    if test_remote_combination:
        remote_attempt = claude_turn(
            PROBE_ONE,
            session_id=session_id,
            remote_control=True,
        )

    first = (
        remote_attempt
        if remote_attempt and remote_attempt["returnCode"] == 0
        else claude_turn(PROBE_ONE, session_id=session_id)
    )
    if first["returnCode"] != 0:
        raise RuntimeError(first["stderr"] or "Claude first turn failed")
    observed_session = first["sessionId"] or session_id
    second = claude_turn(PROBE_TWO, resume=observed_session)
    if second["returnCode"] != 0:
        raise RuntimeError(second["stderr"] or "Claude resume failed")
    return {
        "provider": "claude",
        "sessionId": observed_session,
        "remoteCombination": remote_attempt,
        "firstTurn": first,
        "resumedTurn": second,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("codex", "claude"), required=True)
    parser.add_argument(
        "--allow-token-use",
        action="store_true",
        help="Required acknowledgement that two minimal turns consume provider quota.",
    )
    parser.add_argument(
        "--test-remote-combination",
        action="store_true",
        help="For Claude, first try structured print mode with Remote Control.",
    )
    parser.add_argument(
        "--persistent",
        action="store_true",
        help="For Claude, keep one stream-json process alive for both turns.",
    )
    args = parser.parse_args()
    if not args.allow_token_use:
        parser.error("--allow-token-use is required; this probe submits two prompts")

    report = (
        codex_live_probe()
        if args.provider == "codex"
        else claude_live_probe(
            args.test_remote_combination,
            persistent=args.persistent,
        )
    )
    report["quotaConsumed"] = True
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"error": str(exc), "quotaConsumed": True}, indent=2))
        raise SystemExit(1)
