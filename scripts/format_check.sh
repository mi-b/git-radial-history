#!/usr/bin/env bash
# Single entry point for formatting and linting checks (local and CI).
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> ruff format --check"
uv run ruff format --check .

echo "==> ruff check"
uv run ruff check .

echo "==> ty check"
uv run ty check

echo "All format and lint checks passed."
