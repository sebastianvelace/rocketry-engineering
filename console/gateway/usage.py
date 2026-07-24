"""Real provider usage snapshots with a bounded refresh cadence."""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gateway.manager import SessionManager
from gateway.providers.codex import CodexAdapter
from gateway.store import GatewayStore


def parse_claude_usage(result: str) -> dict[str, Any]:
    windows = []
    for key, label in (("session", "Current session"), ("week", "Current week")):
        match = re.search(
            rf"^{re.escape(label)}(?: \(all models\))?:\s*(\d+)% used\s*·\s*resets (.+)$",
            result,
            flags=re.MULTILINE,
        )
        if match:
            windows.append(
                {
                    "id": key,
                    "used_percent": int(match.group(1)),
                    "resets_at_label": match.group(2).strip(),
                }
            )
    activity = {}
    for period, label in (("day", "Last 24h"), ("week", "Last 7d")):
        match = re.search(
            rf"^{re.escape(label)}\s*·\s*(\d+) requests\s*·\s*(\d+) sessions$",
            result,
            flags=re.MULTILINE,
        )
        if match:
            activity[period] = {
                "requests": int(match.group(1)),
                "sessions": int(match.group(2)),
            }
    return {
        "available": True,
        "source": "claude /usage",
        "subscription": "subscription" in result.lower(),
        "windows": windows,
        "activity": activity,
    }


class UsageService:
    def __init__(
        self,
        store: GatewayStore,
        manager: SessionManager,
        *,
        workspace: Path,
        ttl_seconds: float = 60.0,
    ):
        self.store = store
        self.manager = manager
        self.workspace = workspace
        self.ttl_seconds = ttl_seconds
        self._cached_at = 0.0
        self._cache: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def read(self, *, force: bool = False) -> dict[str, Any]:
        async with self._lock:
            if (
                not force
                and self._cache is not None
                and time.monotonic() - self._cached_at < self.ttl_seconds
            ):
                return {**self._cache, "cached": True}

            codex_result, claude_result = await asyncio.gather(
                self._safe(self._read_codex),
                self._safe(self._read_claude),
            )
            snapshot = {
                "ok": True,
                "refreshed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "cached": False,
                "providers": {
                    "codex": codex_result,
                    "claude": claude_result,
                },
                "local": self._local_usage(),
            }
            self._cache = snapshot
            self._cached_at = time.monotonic()
            return snapshot

    async def _safe(self, reader) -> dict[str, Any]:
        try:
            return await reader()
        except Exception as exc:
            return {
                "available": False,
                "error": str(exc),
            }

    async def _read_codex(self) -> dict[str, Any]:
        adapter = next(
            (
                item
                for item in self.manager.adapters.values()
                if isinstance(item, CodexAdapter)
            ),
            None,
        )
        temporary = adapter is None
        if adapter is None:
            async def ignore_event(_event):
                return None

            async def ignore_approval(_approval):
                return None

            adapter = CodexAdapter(
                workspace=self.workspace,
                event_sink=ignore_event,
                approval_sink=ignore_approval,
            )
        try:
            payload = await adapter.account_usage()
        finally:
            if temporary:
                await adapter.close()

        raw_limits = payload.get("rate_limits") or {}
        reset_credits = raw_limits.get("rateLimitResetCredits") or {}
        limits = {
            "rateLimits": raw_limits.get("rateLimits"),
            "rateLimitsByLimitId": raw_limits.get("rateLimitsByLimitId"),
            "rateLimitResetCredits": {
                "availableCount": int(reset_credits.get("availableCount") or 0)
            },
        }
        tokens = payload.get("token_usage") or {}
        return {
            "available": True,
            "source": "codex app-server",
            "rate_limits": limits,
            "token_usage": tokens,
        }

    async def _read_claude(self) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            "claude",
            "-p",
            "/usage",
            "--output-format",
            "json",
            "--tools",
            "",
            cwd=str(self.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("Claude /usage timed out.")
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or f"Claude /usage exited with {process.returncode}.")
        payload = json.loads(stdout.decode("utf-8"))
        result = str(payload.get("result") or "")
        return parse_claude_usage(result)

    def _local_usage(self) -> dict[str, Any]:
        totals: dict[str, dict[str, float | int]] = {
            "claude": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "cost_usd": 0.0,
                "turns": 0,
            },
            "codex": {
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_input_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
                "threads": 0,
            },
        }
        for session in self.store.list_sessions(limit=1000):
            events = self.store.list_events(session.id, limit=2000)
            if session.provider == "claude":
                for event in events:
                    if event.type != "usage" or event.text != "Turn usage":
                        continue
                    usage = event.data.get("usage") or {}
                    totals["claude"]["input_tokens"] += int(usage.get("input_tokens") or 0)
                    totals["claude"]["output_tokens"] += int(usage.get("output_tokens") or 0)
                    totals["claude"]["cached_input_tokens"] += int(usage.get("cache_read_input_tokens") or 0)
                    totals["claude"]["cost_usd"] += float(event.data.get("cost_usd") or 0)
                    totals["claude"]["turns"] += 1
            else:
                latest = next(
                    (
                        event
                        for event in reversed(events)
                        if event.type == "usage"
                        and event.text == "thread/tokenUsage/updated"
                    ),
                    None,
                )
                if latest is None:
                    continue
                total = (latest.data.get("tokenUsage") or {}).get("total") or {}
                totals["codex"]["input_tokens"] += int(total.get("inputTokens") or 0)
                totals["codex"]["output_tokens"] += int(total.get("outputTokens") or 0)
                totals["codex"]["cached_input_tokens"] += int(total.get("cachedInputTokens") or 0)
                totals["codex"]["reasoning_output_tokens"] += int(total.get("reasoningOutputTokens") or 0)
                totals["codex"]["total_tokens"] += int(total.get("totalTokens") or 0)
                totals["codex"]["threads"] += 1
        return totals
