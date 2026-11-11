#!/usr/bin/env bash
# BayiOS production database restore — verification drill only.
# Restores a dump into a NEW database (bayios_restore_check) inside the running
# postgres service WITHOUT touching the production "bayios" database. Use it for
# the monthly restore drill and pre-migration checks; see docs/OPERATIONS.md.
set -euo pipefail

DUMP="${1:?usage: restore.sh <path-to-dump>}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DB="${TARGET_DB:-bayios_restore_check}"

if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
  COMPOSE=(podman compose)
else
  COMPOSE=(docker compose)
fi

if [[ ! -f "${DUMP}" ]]; then
  echo "restore failed: dump not found: ${DUMP}" >&2
  exit 1
fi

"${COMPOSE[@]}" -f "${ROOT}/compose.yaml" exec -T postgres \
  dropdb -U bayios --if-exists "${TARGET_DB}"

"${COMPOSE[@]}" -f "${ROOT}/compose.yaml" exec -T postgres \
  createdb -U bayios "${TARGET_DB}"

if ! "${COMPOSE[@]}" -f "${ROOT}/compose.yaml" exec -T postgres \
     pg_restore -U bayios -d "${TARGET_DB}" < "${DUMP}"; then
  echo "restore failed: pg_restore exited non-zero" >&2
  exit 1
fi

echo "restore ok into '${TARGET_DB}'. Running sanity checks:"
"${COMPOSE[@]}" -f "${ROOT}/compose.yaml" exec -T postgres \
  psql -U bayios -d "${TARGET_DB}" -Atc \
  "select 'products='||count(*) from products;"

echo "Verify, then drop the scratch DB with:"
echo "  ${COMPOSE[*]} -f ${ROOT}/compose.yaml exec -T postgres dropdb -U bayios ${TARGET_DB}"
