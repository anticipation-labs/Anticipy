#!/bin/sh
# Rebuild a malformed PocketBase data.db with SQLite's own `.recover`.
#
#   sh repair_data_db.sh <pb_data dir> <tag>
#
# Runs ONLY when start.sh is told to by hand (ANTICIPY_REPAIR_DATA_DB=<tag>),
# exactly once per tag, before PocketBase opens the file. It never deletes:
# the original data.db, its WAL and its SHM are moved aside under the tag,
# the recovered file takes their place only if SQLite says "ok" about it,
# and a marker file stops a second boot from doing it all again.
#
# Why it exists: 2026-09-05, `agents` answered every read with "database disk
# image is malformed (11)"; integrity_check named bad pages in three b-trees
# and a forced table scan of `agents` returned nothing. A REINDEX rebuilds
# indexes from rows and cannot help when the rows' own pages are bad.
# `.recover` walks every page it can still read, writes what it finds as
# SQL, and puts orphaned cells in `lost_and_found` — nothing readable is
# lost, and what was unreadable is listed for a person instead of vanishing.
#
# Proven on a deliberately corrupted file by tests/test_repair_data_db.py,
# which also pins: the original is kept byte for byte, a healthy file is
# left untouched, and the marker makes the tag one-shot.
set -u
DIR="${1:?pb_data dir}"
TAG="${2:?tag}"
DB="$DIR/data.db"
MARK="$DIR/repair-$TAG.done"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
say() { echo "repair: $*"; }

if [ -f "$MARK" ]; then
  say "'$TAG' already ran: $(head -c 300 "$MARK" | tr '\n' ' ')"
  say "unset ANTICIPY_REPAIR_DATA_DB, or choose a new tag for a new repair"
  exit 0
fi
if ! command -v sqlite3 >/dev/null 2>&1; then say "no sqlite3 in this image; nothing done"; exit 0; fi
if [ ! -f "$DB" ]; then say "$DB does not exist; nothing done"; exit 0; fi

say "'$TAG' begins $STAMP on $DB ($(wc -c < "$DB") bytes)"

# 0. A file SQLite already calls "ok" is not repaired. Say so and leave.
BEFORE=$(sqlite3 "$DB" 'PRAGMA integrity_check;' 2>&1 | head -1)
if [ "$BEFORE" = "ok" ]; then say "integrity_check says ok; nothing to repair, nothing done"; exit 0; fi
say "integrity_check before: $BEFORE"

# 1. Fold the WAL into the main file if it can be read, so the copy below and
#    the recovery both see one file. A failure here is information, not a stop.
sqlite3 "$DB" 'PRAGMA wal_checkpoint(TRUNCATE);' >/dev/null 2>&1 \
  && say "wal checkpointed" || say "wal checkpoint failed (continuing; wal/shm are copied alongside)"

# 2. Keep the original. Everything after this is reversible by moving it back.
KEEP="$DIR/data.db.malformed-$TAG-$STAMP"
if ! cp -p "$DB" "$KEEP"; then say "could not copy the original; STOPPING with nothing changed"; exit 0; fi
[ -f "$DB-wal" ] && cp -p "$DB-wal" "$KEEP-wal"
[ -f "$DB-shm" ] && cp -p "$DB-shm" "$KEEP-shm"
say "original kept at $KEEP"

# 3. Recover into a fresh file.
SQL="$DIR/repair-$TAG-$STAMP.sql"
NEW="$DIR/data.db.recovered-$TAG-$STAMP"
rm -f "$NEW" "$SQL"
sqlite3 "$DB" '.recover' > "$SQL" 2>"$SQL.err"
say ".recover wrote $(wc -c < "$SQL") bytes of SQL ($(wc -l < "$SQL.err") stderr lines)"
if [ ! -s "$SQL" ]; then say ".recover produced nothing; STOPPING, original untouched"; rm -f "$SQL" "$SQL.err"; exit 0; fi
sqlite3 "$NEW" < "$SQL" >/dev/null 2>"$NEW.err"
say "import finished ($(wc -l < "$NEW.err") stderr lines)"

# 4. Only a file SQLite calls "ok" may take the original's place.
VERDICT=$(sqlite3 "$NEW" 'PRAGMA integrity_check;' 2>&1 | head -5 | tr '\n' ' ')
say "recovered integrity_check: $VERDICT"
if [ "$VERDICT" != "ok " ] && [ "$VERDICT" != "ok" ]; then
  say "recovered file is NOT clean; STOPPING, original untouched, recovered file left for inspection"
  exit 0
fi

# 5. Say what came back, table by table, before swapping anything.
for T in _collections _params _migrations owners owner_profile jobs events segments agents; do
  OLD=$(sqlite3 "$DB" "SELECT count(*) FROM \"$T\" NOT INDEXED;" 2>/dev/null || echo "unreadable")
  NEWC=$(sqlite3 "$NEW" "SELECT count(*) FROM \"$T\";" 2>/dev/null || echo "missing")
  say "rows $T: original=$OLD recovered=$NEWC"
done
LOST=$(sqlite3 "$NEW" "SELECT count(*) FROM lost_and_found;" 2>/dev/null || echo 0)
say "lost_and_found rows (cells .recover could not place): $LOST"

# 6. Swap. The old WAL/SHM belong to the old file and must not sit beside the new one.
mv "$DB" "$KEEP.final" && rm -f "$KEEP.final" 2>/dev/null
[ -f "$DB-wal" ] && mv "$DB-wal" "$KEEP-wal.final"
[ -f "$DB-shm" ] && mv "$DB-shm" "$KEEP-shm.final"
if ! mv "$NEW" "$DB"; then
  say "swap FAILED; restoring the original"
  cp -p "$KEEP" "$DB"; [ -f "$KEEP-wal" ] && cp -p "$KEEP-wal" "$DB-wal"; [ -f "$KEEP-shm" ] && cp -p "$KEEP-shm" "$DB-shm"
  exit 0
fi
rm -f "$SQL" "$SQL.err" "$NEW.err"
printf 'tag=%s at=%s kept=%s lost_and_found=%s\n' "$TAG" "$STAMP" "$KEEP" "$LOST" > "$MARK"
say "'$TAG' done: data.db is the recovered file; the original is $KEEP; marker $MARK"
exit 0
