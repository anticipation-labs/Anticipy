#!/bin/sh
# Boot guard: never let a full volume keep the whole product down.
set -e
FREE_KB=$(df -Pk /pb_data | awk 'NR==2 {print $4}')
echo "boot: /pb_data free ${FREE_KB}KB"
if [ "${FREE_KB:-0}" -lt 262144 ]; then          # under 256MB of headroom
  echo "boot: low headroom — dropping PocketBase request-log db (recreated on start)"
  ls -la /pb_data | head -20
  rm -f /pb_data/auxiliary.db /pb_data/auxiliary.db-wal /pb_data/auxiliary.db-shm
  echo "boot: /pb_data free now $(df -Pk /pb_data | awk 'NR==2 {print $4}')KB"
fi
exec ./pocketbase serve --http 0.0.0.0:${PORT:-8090} --dir /pb_data \
  --migrationsDir /app/pb_migrations --publicDir /app/pb_public --hooksDir /app/pb_hooks
