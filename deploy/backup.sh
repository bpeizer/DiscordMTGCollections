#!/usr/bin/env bash
# Make a consistent copy of the database in backups/, keeping the newest 14.
# Safe to run while the bot is running (uses SQLite's online backup).
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB="$APP_DIR/${DB_PATH:-collections.db}"
OUT_DIR="$APP_DIR/backups"
mkdir -p "$OUT_DIR"
if [ ! -f "$DB" ]; then
  echo "$(date -Is) no database yet at $DB, nothing to back up"
  exit 0
fi
OUT="$OUT_DIR/collections-$(date +%Y%m%d-%H%M%S).db"
sqlite3 "$DB" ".backup '$OUT'"
ls -1t "$OUT_DIR"/collections-*.db | tail -n +15 | xargs -r rm --
echo "$(date -Is) backed up to $OUT"
