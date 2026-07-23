#!/usr/bin/env python3
"""Run Codex or Claude in the terminal while mirroring its JSON events to the UI."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from agent_feed import emit  # noqa: E402


def command(provider: str, prompt: str) -> list[str]:
    if provider == "codex":
        return ["codex", "exec", "--json", "-C", str(ROOT), prompt]
    return [
        "claude",
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        prompt,
    ]


def describe(provider: str, payload: dict) -> tuple[str, str]:
    event = str(payload.get("type") or payload.get("event") or "update")
    if provider == "codex":
        item = payload.get("item") or {}
        detail = item.get("text") or item.get("command") or item.get("name")
    else:
        message = payload.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        detail = payload.get("result")
        if not detail and isinstance(content, list) and content:
            detail = content[0].get("text") if isinstance(content[0], dict) else None
    return event, str(detail or event).strip()[:500]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("codex", "claude"), required=True)
    parser.add_argument("prompt")
    args = parser.parse_args()

    emit(args.provider, "started", args.prompt[:500])
    process = subprocess.Popen(
        command(args.provider, args.prompt),
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            emit(args.provider, "log", line.strip()[:500])
            continue
        event, message = describe(args.provider, payload)
        emit(args.provider, event, message)

    code = process.wait()
    emit(args.provider, "completed" if code == 0 else "failed", f"Exit code {code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
