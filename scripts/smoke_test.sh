#!/usr/bin/env bash
# Smoke test: boot uvicorn, hit the public pages and the export
# endpoint, then shut down. Used by Render's post-deploy check and
# by anyone who wants a quick "is it running?" check.
#
# The smoke test is intentionally cheap: a few HTTP GETs that
# confirm the process is alive, the templates render, and the
# export endpoints don't 500. It does not exercise CSRF or the
# import wizard - the full pytest suite covers those.
#
# Usage:
#   ./scripts/smoke_test.sh                  # uses PORT=18765
#   PORT=8000 ./scripts/smoke_test.sh        # use a real port
set -euo pipefail

PORT="${PORT:-18765}"
HOST="${HOST:-127.0.0.1}"
BASE="http://${HOST}:${PORT}"

cleanup() {
    if [ -n "${SERVER_PID:-}" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Start it.
.venv/bin/uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level warning &
SERVER_PID=$!

# Wait up to 5s for the server to come up.
for _ in $(seq 1 50); do
    if curl -fsS "$BASE/health" >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done

expect_status() {
    local path="$1"
    local want="$2"
    local got
    got=$(curl -s -o /dev/null -w '%{http_code}' "$BASE$path")
    if [ "$got" != "$want" ]; then
        echo "smoke: $path expected $want got $got" >&2
        exit 1
    fi
    echo "smoke: $path -> $got"
}

expect_status "/health" 200
expect_status "/auth/login" 200
expect_status "/" 303   # redirects to /auth/login when not logged in
expect_status "/exports/transactions.csv" 303   # must be signed in

# Now log in via the real form (with cookies), then hit an export.
COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"; cleanup' EXIT

curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE/auth/login" -o /dev/null
CSRF=$(awk '$6=="pocketledger_csrf"{print $7}' "$COOKIE_JAR")
curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" \
    --data-urlencode "username=demo" \
    --data-urlencode "password=demo1234" \
    --data-urlencode "csrf_token=$CSRF" \
    "$BASE/auth/login" -o /dev/null
curl -sS -b "$COOKIE_JAR" "$BASE/exports/transactions.csv" -o /dev/null
echo "smoke: /exports/transactions.csv (signed in) -> 200"

echo "smoke: all checks passed"