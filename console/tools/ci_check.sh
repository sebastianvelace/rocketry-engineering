#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

.venv/bin/python -m compileall -q . \
  -x '/(\.venv|node_modules|target|dist)/'
.venv/bin/python -m unittest discover -s tests -v
pnpm --dir desktop test
pnpm --dir desktop build
cargo check --manifest-path desktop/src-tauri/Cargo.toml
git diff --check
