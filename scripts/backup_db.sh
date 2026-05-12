#!/usr/bin/env bash
# Online backup of the WebUiWhisper SQLite state DB.
#
# Uses sqlite3's .backup command (works while the app is running). Schedule
# from cron, for example:
#   30 4 * * *  /opt/webuiwhisper/scripts/backup_db.sh /var/backups/webuiwhisper
#
# Keeps the 14 most recent backups.

set -euo pipefail

DEST_DIR="${1:-/var/backups/webuiwhisper}"
SOURCE_DB="${STATE_DB_PATH:-/var/lib/webuiwhisper/state.db}"
RETENTION="${RETENTION:-14}"

if [ ! -f "$SOURCE_DB" ]; then
    echo "source db not found: $SOURCE_DB" >&2
    exit 1
fi

mkdir -p "$DEST_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$DEST_DIR/state-$stamp.db"

sqlite3 "$SOURCE_DB" ".backup '$out'"
echo "backed up to $out"

# Trim oldest files beyond retention. Use find -printf for portability.
mapfile -t files < <(ls -1t "$DEST_DIR"/state-*.db 2>/dev/null || true)
for ((i=RETENTION; i<${#files[@]}; i++)); do
    echo "removing $((${#files[@]} - i)) old: ${files[i]}"
    rm -f -- "${files[i]}"
done
