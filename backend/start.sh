#!/bin/sh
# Boot guard: never let a full volume keep the whole product down.
set -e
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
exec ./pocketbase serve --http 0.0.0.0:${PORT:-8090} --dir /pb_data \
  --migrationsDir /app/pb_migrations --publicDir /app/pb_public --hooksDir /app/pb_hooks
