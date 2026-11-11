#!/usr/bin/env bash
# BayiOS production database backup.
# Runs pg_dump inside the Compose postgres service and writes the dump to the
# host backup directory. See docs/OPERATIONS.md for scheduling on Windows.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BACKUP_DIR="${BACKUP_DIR:-/var/lib/bayios-backups}"
RETENTION_DAILY="${RETENTION_DAILY:-14}"
RETENTION_WEEKLY="${RETENTION_WEEKLY:-8}"
RETENTION_MONTHLY="${RETENTION_MONTHLY:-12}"

# Prefer podman; fall back to docker only if podman is unavailable.
if command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1; then
  COMPOSE=(podman compose)
else
  COMPOSE=(docker compose)
fi

mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" "${BACKUP_DIR}/monthly"

# Refuse to run if there is less than ~1 GiB free in BACKUP_DIR.
if command -v df >/dev/null 2>&1; then
  free_kb="$(df -k --output=avail "${BACKUP_DIR}" 2>/dev/null | tail -n1 | tr -d ' ')"
  if [[ -n "${free_kb}" && "${free_kb}" -lt 1048576 ]]; then
    echo "backup failed: less than 1 GiB free in ${BACKUP_DIR}" >&2
    exit 1
  fi
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
FILE="bayios_${STAMP}.dump"
DEST="${BACKUP_DIR}/daily/${FILE}"

if ! "${COMPOSE[@]}" -f "${ROOT}/compose.yaml" exec -T postgres \
     pg_dump -U bayios -d bayios -Fc > "${DEST}"; then
  echo "backup failed: pg_dump exited non-zero" >&2
  rm -f "${DEST}" || true
  exit 1
fi

# External/second-disk copy, if configured.
if [[ -n "${BACKUP_EXTERNAL_DIR:-}" ]]; then
  mkdir -p "${BACKUP_EXTERNAL_DIR}"
  cp "${DEST}" "${BACKUP_EXTERNAL_DIR}/${FILE}"
fi

# Weekly/monthly rollover copies.
if [[ "$(date +%u)" == "7" ]]; then cp "${DEST}" "${BACKUP_DIR}/weekly/${FILE}"; fi
if [[ "$(date +%d)" == "01" ]]; then cp "${DEST}" "${BACKUP_DIR}/monthly/${FILE}"; fi

# Prune old dumps.
find "${BACKUP_DIR}/daily" -name 'bayios_*.dump' -mtime "+${RETENTION_DAILY}" -delete
find "${BACKUP_DIR}/weekly" -name 'bayios_*.dump' -mtime "+$((RETENTION_WEEKLY * 7))" -delete
find "${BACKUP_DIR}/monthly" -name 'bayios_*.dump' -mtime "+$((RETENTION_MONTHLY * 30))" -delete

echo "backup ok: ${DEST}"
