#!/usr/bin/env bash
# Fresh-clone test: prove the README commands work in a brand-new checkout.
#
# This script is intentionally self-contained: it copies the working
# tree into a temp directory, builds a venv, installs the project
# editable, runs the lint + test suite, boots uvicorn, hits /health,
# then tears everything down. If any step fails the script exits
# non-zero so CI (or the developer) sees a real signal.
#
# Usage:
#   ./scripts/fresh_clone_test.sh
#
# Override which directory is copied (default: the repo root) by
# setting PROJECT_ROOT. Useful for CI where the workspace path is
# not where you think it is.
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
WORK_DIR="$(mktemp -d -t pocketledger-fresh-clone-XXXXXX)"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"

cleanup() {
    if [ -n "${SERVER_PID:-}" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

echo "==> Copying $PROJECT_ROOT -> $WORK_DIR"
mkdir -p "$WORK_DIR"
# Copy everything but the venv and the user-level caches.
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' \
    --exclude='.ruff_cache' --exclude='*.egg-info' --exclude='pocketledger.db*' \
    "$PROJECT_ROOT"/ "$WORK_DIR"/

cd "$WORK_DIR"

echo "==> Creating venv with $PYTHON_BIN"
$PYTHON_BIN -m venv .venv

echo "==> Installing (editable, with dev extras)"
.venv/bin/pip install -U pip >/dev/null
.venv/bin/pip install -e ".[dev]"

echo "==> Lint"
.venv/bin/ruff check app tests alembic

echo "==> Tests (unit + e2e skipped if browser is not installed)"
.venv/bin/pytest --browser chromium -q || .venv/bin/pytest -q

echo "==> Smoke: start uvicorn, hit /health"
PORT=18765
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --log-level warning &
SERVER_PID=$!
# Wait for the server to come up.
for _ in $(seq 1 50); do
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done
HEALTH=$(curl -fsS "http://127.0.0.1:$PORT/health")
echo "    /health -> $HEALTH"
case "$HEALTH" in
    *'"status":"ok"'*) ;;
    *) echo "health check failed: $HEALTH" >&2; exit 1 ;;
esac

echo "==> Fresh-clone test passed."
