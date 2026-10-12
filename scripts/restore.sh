#!/usr/bin/env bash
# Restore a backup over the current database file. Stops the app first
# if it is running in docker compose.
# Usage: BACKUP_FILE=/path/to/backup.db ./scripts/restore.sh
set -euo pipefail

DB_FILE="${DB_FILE:-/data/pocketledger.db}"
BACKUP_FILE="${BACKUP_FILE:?Set BACKUP_FILE to the backup to restore}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup not found: $BACKUP_FILE" >&2
  exit 1
fi

# Stop the running app if present, so SQLite isn't holding the file.
if command -v docker >/dev/null 2>&1; then
  docker compose down || true
fi

cp -f "$BACKUP_FILE" "$DB_FILE"
echo "Restored $BACKUP_FILE -> $DB_FILE"
