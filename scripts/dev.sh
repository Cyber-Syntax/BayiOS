#!/usr/bin/env bash
# Dev runner: PostgreSQL up -> optional DB reset -> migrate -> serve with reload.
set -euo pipefail

# Run from repo root
cd "$(dirname "${BASH_SOURCE[0]}")/.."

HOST="${DEV_HOST:-0.0.0.0}"
PORT="${DEV_PORT:-8000}"
RESET_DB="${DEV_RESET_DB:-0}"

if command -v podman >/dev/null 2>&1; then
  compose=(podman compose)
elif command -v docker >/dev/null 2>&1; then
  compose=(docker compose)
else
  echo "error: neither podman nor docker found" >&2
  exit 1
fi

compose+=(-f compose.dev.yaml)

echo "==> Starting PostgreSQL"
"${compose[@]}" up -d

echo "==> Waiting for PostgreSQL"
ready=0

for _ in $(seq 1 30); do
  if "${compose[@]}" exec -T postgres \
    pg_isready -q -U bayios -d bayios; then
    ready=1
    break
  fi

  sleep 1
done

if (( ! ready )); then
  echo "error: PostgreSQL not ready after 30s" >&2
  "${compose[@]}" logs --tail 30 postgres >&2 || true
  exit 1
fi

# Optional database reset for development
if [[ "$RESET_DB" == "1" ]]; then
  echo "==> WARNING: Dropping development database: bayios"

  "${compose[@]}" exec -T postgres \
    dropdb -U bayios --if-exists --force bayios

  echo "==> Creating fresh database: bayios"

  "${compose[@]}" exec -T postgres \
    createdb -U bayios bayios

  echo "==> Database reset completed"
fi

echo "==> Applying migrations"
uv run alembic upgrade head

lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"

echo "==> Serving on http://${HOST}:${PORT}${lan_ip:+  (LAN: http://${lan_ip}:${PORT})}"

exec uv run uvicorn bayios.main:create_app --factory \
  --reload --reload-dir src --reload-dir alembic \
  --host "$HOST" --port "$PORT"