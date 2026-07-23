#!/usr/bin/env python3
"""Inspect local Codex and Claude integration readiness without using quota."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from provider_probe import probe_all, probe_claude, probe_codex  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Probe local provider versions, subscription authentication, CLI "
            "capabilities, and the Codex JSON-RPC handshake. No prompt is sent."
        )
    )
    parser.add_argument(
        "--provider",
        choices=("all", "codex", "claude"),
        default="all",
    )
    parser.add_argument(
        "--skip-codex-protocol",
        action="store_true",
        help="Do not launch the local Codex app-server handshake.",
    )
    args = parser.parse_args()

    if args.provider == "all":
        report = probe_all(ROOT, codex_protocol=not args.skip_codex_protocol)
        ready = all(provider["ready"] for provider in report["providers"])
    else:
        provider = (
            probe_codex(ROOT, protocol=not args.skip_codex_protocol)
            if args.provider == "codex"
            else probe_claude(ROOT)
        )
        report = {
            "schemaVersion": 1,
            "quotaConsumed": False,
            "root": str(ROOT),
            "providers": [provider.to_dict()],
        }
        ready = provider.ready

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
