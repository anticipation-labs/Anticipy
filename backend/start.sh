#!/bin/sh
# Boot guard: never let a full volume keep the whole product down.
set -e
if [ "${#PB_SETTINGS_ENCRYPTION_KEY}" -ne 32 ]; then
  echo "boot: PB_SETTINGS_ENCRYPTION_KEY must be exactly 32 characters" >&2
  exit 1
fi
FREE_KB=$(df -Pk /pb_data | awk 'NR==2 {print $4}')
echo "boot: /pb_data free ${FREE_KB}KB"
# Name the filler every boot: the volume went 2.9GB-free to 4MB-free in two
# hours on 2026-08-15 and nothing in the logs said what grew. Size every
# file so the next refill is a one-line diagnosis, not a forensic project.
du -sk /pb_data/* 2>/dev/null | sort -rn | head -12 | sed 's/^/boot: du /'
# The request-log DB is disposable diagnostics and the proven runaway
# grower. Drop it EVERY boot, not only under low headroom — losing request
# logs at deploy time is nothing; losing the product to a full disk is not.
rm -f /pb_data/auxiliary.db /pb_data/auxiliary.db-wal /pb_data/auxiliary.db-shm
echo "boot: /pb_data free after log-db drop $(df -Pk /pb_data | awk 'NR==2 {print $4}')KB"
# 2026-08-30, second full-volume incident: the scheduled backup zips pin
# multiple copies of pb_data on the same volume (1700000037's documented
# footprint). A backup that fills the disk it is supposed to protect is the
# failure it exists to prevent, so keep the NEWEST snapshot and let the
# older ones go. A backup is regenerable by definition; a day of the
# owner's life is not.
BACKUPS_DIR="/pb_data/backups"
if [ -d "$BACKUPS_DIR" ]; then
  ls -t "$BACKUPS_DIR"/*.zip 2>/dev/null | tail -n +2 | while read -r old; do
    rm -f "$old"
  done
  echo "boot: kept newest backup, freed older snapshots"
fi
echo "boot: /pb_data free after backup trim $(df -Pk /pb_data | awk 'NR==2 {print $4}')KB"
# 2026-09-05: after a deploy the `agents` collection answered every read with
# "database disk image is malformed (11)" and NOTHING on the host could say how
# far the rot went — the image had no sqlite3, the logs had no integrity line,
# and the last successful agent row was dated 2026-08-14, the day before the
# full-disk incident above. Ask SQLite itself, every boot, before PocketBase
# opens the file. Read-only: integrity_check writes nothing, the forced table
# scan proves whether the ROWS are still readable when the index is not, and
# index_list names what a REINDEX would rebuild. This is the sense that was
# missing; a repair is a separate, deliberate act and does not live here.
if [ -f /pb_data/data.db ] && command -v sqlite3 >/dev/null 2>&1; then
  echo "boot: integrity_check begins $(date -u +%H:%M:%SZ)"
  sqlite3 /pb_data/data.db 'PRAGMA integrity_check;' 2>&1 | head -40 | sed 's/^/boot: integrity /'
  sqlite3 /pb_data/data.db "SELECT 'agents rows by table scan: ' || count(*) FROM agents NOT INDEXED;" 2>&1 | sed 's/^/boot: integrity /'
  sqlite3 /pb_data/data.db "SELECT 'agents index: ' || name FROM pragma_index_list('agents');" 2>&1 | sed 's/^/boot: integrity /'
  echo "boot: integrity_check ends $(date -u +%H:%M:%SZ)"
fi
# The repair is a hand-thrown switch, never automatic: set
# ANTICIPY_REPAIR_DATA_DB=<tag> on the service and this boot rebuilds data.db
# from what SQLite can still read, keeping the original beside it, once per
# tag. repair_data_db.sh explains itself; tests/test_repair_data_db.py proves it.
if [ -n "${ANTICIPY_REPAIR_DATA_DB:-}" ] && [ -f /app/repair_data_db.sh ]; then
  sh /app/repair_data_db.sh /pb_data "$ANTICIPY_REPAIR_DATA_DB" 2>&1 | sed 's/^/boot: /'
  echo "boot: integrity after repair: $(sqlite3 /pb_data/data.db 'PRAGMA integrity_check;' 2>&1 | head -3 | tr '\n' ' ')"
fi
exec ./pocketbase serve --http 0.0.0.0:${PORT:-8090} --dir /pb_data \
  --migrationsDir /app/pb_migrations --publicDir /app/pb_public --hooksDir /app/pb_hooks \
  --encryptionEnv=PB_SETTINGS_ENCRYPTION_KEY
