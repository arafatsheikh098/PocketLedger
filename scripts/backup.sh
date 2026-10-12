#!/usr/bin/env bash
# Create a SQLite online backup of the running app database.
# Usage: BACKUP_FILE=/path/to/backup.db ./scripts/backup.sh
set -euo pipefail

DB_FILE="${DB_FILE:-/data/pocketledger.db}"
BACKUP_FILE="${BACKUP_FILE:-/data/backups/pocketledger-$(date -u +%Y%m%dT%H%M%SZ).db}"

mkdir -p "$(dirname "$BACKUP_FILE")"
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"
echo "Backup written to $BACKUP_FILE"
