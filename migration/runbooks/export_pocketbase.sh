#!/usr/bin/env bash
#
# export_pocketbase.sh — take everything out of the live PocketBase instance
# before anything is decommissioned.
#
# WHAT THIS PRODUCES
#   $OUT_DIR/collections.json            every collection definition, as the
#                                        SERVER reports it (not as the repo
#                                        claims it). This is how collections
#                                        that exist in production but not in
#                                        backend/pb_migrations/ are found --
#                                        NINE fellowship collections are known
#                                        to be in that category: fellows,
#                                        fellow_applications, fellow_submissions,
#                                        fellow_payouts, fellow_conversions,
#                                        fellow_codes, fellow_clicks,
#                                        fellow_progress, fellow_meter -- see
#                                        migration/d1/FELLOWSHIP-PRECEDENT.md and
#                                        migration/d1/GAPS.md
#                                        (research/2026-08-31-founder-identity-reset.md:112-114
#                                        names the first two independently).
#                                        The repo-known list inside this script
#                                        is a DIFF AID, NEVER A FILTER.
#   $OUT_DIR/schema/<name>.json          one collection definition per file
#   $OUT_DIR/records/<name>.ndjson       one JSON object per line, one line per row
#   $OUT_DIR/files/<name>/<id>/<file>    every file-field blob (today: evidence.image)
#   $OUT_DIR/backup/<key>.zip            PocketBase's own native archive (see WHY below)
#   $OUT_DIR/manifest.json               per-collection row counts + SHA-256 per file
#   $OUT_DIR/SHA256SUMS                  flat digest list over the whole export
#   $OUT_DIR/logs/export.log             full transcript
#
# WHY THE NATIVE ARCHIVE IS NOT OPTIONAL
#   The REST export CANNOT carry every byte. PocketBase strips two classes of
#   field from every API response:
#     * auth-collection system fields -- `owners` is `type: "auth"`
#       (backend/pb_migrations/1700000008_owners.js:19-23), and PocketBase
#       injects `password` and `tokenKey` itself. They are never serialised.
#       No password hash comes out through REST. Ever.
#     * fields explicitly declared hidden -- `agents.agent_token`
#       (backend/pb_migrations/1700000026_agent_tokens.js:11), the per-agent
#       256-bit credential each paired Chrome install authenticates with.
#   So the archive of /pb_data (which contains data.db verbatim, plus
#   /pb_data/storage) is the only artifact that holds them. This script pulls
#   BOTH and records in manifest.json exactly which fields were missing from
#   the REST side, so the gap is written down rather than discovered later.
#
# CREDENTIALS THE OWNER MUST SUPPLY (names only; never paste values into a
# shell that records history -- see EXPORT.md "Credentials"):
#   PB_URL                    https origin of the live backend
#   PB_SUPERUSER_EMAIL        a PocketBase superuser (_superusers collection)
#   PB_SUPERUSER_PASSWORD     that superuser's password
#
# Superuser, specifically, and nothing less:
#   * guard.pb.js:395 short-circuits the production lock for superusers.
#     The shared ANTICIPY_SERVICE_TOKEN gets past guard.pb.js:25,37 too, BUT it
#     does not bypass PocketBase's own API rules, and all fourteen internal_*
#     collections were created with every rule null on purpose
#     (backend/pb_migrations/1700000038_internal_hq.js:22-27,
#      backend/pb_migrations/1700000048_hq_v2.js:184-192). A service-token
#     export would silently return zero HQ rows.
#   * evidence.pb.js:60,66 lets a superuser past the /api/files/ door without
#     spending the share-window fetch counter (evidence.pb.js:131-132).
#
# Usage:
#   PB_URL=https://... PB_SUPERUSER_EMAIL=... PB_SUPERUSER_PASSWORD=... \
#     ./export_pocketbase.sh /path/to/export-dir
#
# Exit codes: 0 ok | 2 preflight/usage | 3 verification mismatch | 4 transport

set -Eeuo pipefail

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------
OUT_DIR="${1:-${OUT_DIR:-}}"
PB_URL="${PB_URL:-}"
PB_SUPERUSER_EMAIL="${PB_SUPERUSER_EMAIL:-}"
PB_SUPERUSER_PASSWORD="${PB_SUPERUSER_PASSWORD:-}"
PER_PAGE="${PER_PAGE:-200}"
RETRIES="${RETRIES:-5}"
HTTP_MAX_TIME="${HTTP_MAX_TIME:-900}"
# 1 = ask PocketBase for a fresh native archive before downloading (default).
# 0 = download the newest archive that already exists. Use 0 only if the
#     volume is known to be tight; a stale archive is a worse failure than a
#     tight disk, and migration 1700000053 sends archives straight to R2
#     rather than to /pb_data (research/2026-08-31-database-resilience.md:39-42).
PB_CREATE_BACKUP="${PB_CREATE_BACKUP:-1}"
# 1 = fail the run if the native archive could not be obtained (default).
PB_REQUIRE_BACKUP="${PB_REQUIRE_BACKUP:-1}"

usage() {
  cat >&2 <<'USAGE'
usage: PB_URL=... PB_SUPERUSER_EMAIL=... PB_SUPERUSER_PASSWORD=... \
         export_pocketbase.sh <output-directory>

optional env:
  PER_PAGE=200            rows per request
  RETRIES=5               retries per request on 429/5xx/transport failure
  HTTP_MAX_TIME=900       per-request curl --max-time, seconds
  PB_CREATE_BACKUP=1      1 = create a fresh native archive first
  PB_REQUIRE_BACKUP=1     1 = a missing native archive fails the run
USAGE
  exit 2
}

[ -n "$OUT_DIR" ] || usage
[ -n "$PB_URL" ] || { echo "PB_URL is not set" >&2; usage; }
[ -n "$PB_SUPERUSER_EMAIL" ] || { echo "PB_SUPERUSER_EMAIL is not set" >&2; usage; }
[ -n "$PB_SUPERUSER_PASSWORD" ] || { echo "PB_SUPERUSER_PASSWORD is not set" >&2; usage; }

case "$PB_URL" in
  https://*) : ;;
  http://127.0.0.1*|http://localhost*) : ;;
  *) echo "refusing: PB_URL must be https (or an explicit loopback for a rehearsal)" >&2; exit 2 ;;
esac
PB_URL="${PB_URL%/}"

# The export contains transcripts, phone numbers, email addresses and password
# reset hashes. It is not a world-readable directory.
umask 077

for tool in curl jq; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 2; }
done
if command -v sha256sum >/dev/null 2>&1; then
  SHA_CMD="sha256sum"
elif command -v shasum >/dev/null 2>&1; then
  SHA_CMD="shasum -a 256"
else
  echo "missing required tool: sha256sum or shasum" >&2; exit 2
fi

mkdir -p "$OUT_DIR"/{schema,records,files,backup,logs}
chmod 700 "$OUT_DIR"
LOG="$OUT_DIR/logs/export.log"
: > "$LOG"

TMP="$(mktemp -d "${TMPDIR:-/tmp}/anticipy-pb-export.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log()  { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG" >&2; }
warn() { printf '%s WARN %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG" >&2; }
die()  { printf '%s FATAL %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "$LOG" >&2; exit "${2:-4}"; }

sha256_of() { $SHA_CMD "$1" | awk '{print $1}'; }
bytes_of()  { wc -c < "$1" | tr -d ' '; }
urlenc()    { jq -rn --arg s "$1" '$s|@uri'; }

# --------------------------------------------------------------------------
# transport
# --------------------------------------------------------------------------
LAST_CODE=""

_curl() {
  # _curl <outfile> <curl args...>  -> echoes the HTTP status, 000 on transport failure
  local out="$1"; shift
  local code
  if code=$(curl -sS -o "$out" -w '%{http_code}' \
              --connect-timeout 15 --max-time "$HTTP_MAX_TIME" \
              -L --max-redirs 3 "$@" 2>>"$LOG"); then
    printf '%s' "$code"
  else
    printf '000'
  fi
}

api_get() {
  # api_get <outfile> <path> [curl --data-urlencode args...]
  local out="$1" path="$2"; shift 2
  local attempt=0 code
  while :; do
    attempt=$((attempt + 1))
    code="$(_curl "$out" -G "${PB_URL}${path}" -H "Authorization: ${PB_TOKEN}" "$@")"
    LAST_CODE="$code"
    case "$code" in
      200) return 0 ;;
      429|500|502|503|504|000)
        if [ "$attempt" -ge "$RETRIES" ]; then
          warn "GET $path exhausted $attempt attempts (last HTTP $code)"
          return 1
        fi
        sleep $((attempt * 3))
        ;;
      *) return 1 ;;
    esac
  done
}

api_get_binary() {
  # api_get_binary <outfile> <full-path-with-query>
  local out="$1" path="$2"
  local attempt=0 code
  while :; do
    attempt=$((attempt + 1))
    code="$(_curl "$out" "${PB_URL}${path}" -H "Authorization: ${PB_TOKEN}")"
    LAST_CODE="$code"
    case "$code" in
      200) return 0 ;;
      429|500|502|503|504|000)
        if [ "$attempt" -ge "$RETRIES" ]; then return 1; fi
        sleep $((attempt * 3))
        ;;
      *) return 1 ;;
    esac
  done
}

# --------------------------------------------------------------------------
# 1. authenticate as superuser
# --------------------------------------------------------------------------
log "signing in as superuser at $PB_URL"
jq -n --arg i "$PB_SUPERUSER_EMAIL" --arg p "$PB_SUPERUSER_PASSWORD" \
  '{identity:$i,password:$p}' > "$TMP/auth_body.json"
AUTH_CODE="$(_curl "$TMP/auth.json" \
  -X POST "${PB_URL}/api/collections/_superusers/auth-with-password" \
  -H 'Content-Type: application/json' --data-binary @"$TMP/auth_body.json")"
rm -f "$TMP/auth_body.json"
[ "$AUTH_CODE" = "200" ] || die "superuser sign-in failed (HTTP $AUTH_CODE). Body withheld; see $LOG for transport errors."
PB_TOKEN="$(jq -r '.token // empty' "$TMP/auth.json")"
[ -n "$PB_TOKEN" ] || die "superuser sign-in returned no token"
rm -f "$TMP/auth.json"
log "superuser session established"   # the token itself is never printed

# health, for the record
if api_get "$OUT_DIR/logs/health.json" "/api/health"; then
  log "health: $(jq -c '.' "$OUT_DIR/logs/health.json")"
else
  warn "/api/health did not answer 200 (HTTP $LAST_CODE); continuing"
fi

# --------------------------------------------------------------------------
# 2. enumerate collections FROM THE SERVER
# --------------------------------------------------------------------------
log "enumerating collections"
: > "$TMP/collections.ndjson"
page=1
while :; do
  api_get "$TMP/coll_page.json" "/api/collections" \
    --data-urlencode "page=$page" --data-urlencode "perPage=200" \
    --data-urlencode "sort=name" \
    || die "could not list collections (HTTP $LAST_CODE) -- is this account a superuser?"
  jq -c '.items[]' "$TMP/coll_page.json" >> "$TMP/collections.ndjson"
  total_pages="$(jq -r '.totalPages // 1' "$TMP/coll_page.json")"
  [ "$page" -ge "$total_pages" ] && break
  page=$((page + 1))
done
jq -s '.' "$TMP/collections.ndjson" > "$OUT_DIR/collections.json"
COLL_COUNT="$(jq 'length' "$OUT_DIR/collections.json")"
log "server reports $COLL_COUNT collections"

# The repo's own list, for a difference report. 26 collections are created by
# backend/pb_migrations/ (12 product + 14 internal_*); anything else the server
# names is a collection this tree does not know about and MUST NOT be dropped.
REPO_KNOWN="agent_audit_sessions agent_llm_audit agents events evidence internal_activity internal_comments internal_config internal_events internal_expenses internal_meter internal_notes internal_notifs internal_passwords internal_people internal_reminders internal_sessions internal_todos internal_tracks jobs owner_profile owners password_resets pendants purges segments"
: > "$OUT_DIR/logs/unknown_collections.txt"
jq -r '.[] | select(.system != true) | .name' "$OUT_DIR/collections.json" | while read -r cname; do
  case " $REPO_KNOWN " in
    *" $cname "*) : ;;
    *) echo "$cname" >> "$OUT_DIR/logs/unknown_collections.txt" ;;
  esac
done
if [ -s "$OUT_DIR/logs/unknown_collections.txt" ]; then
  warn "collections present in production but NOT in backend/pb_migrations/:"
  while read -r u; do warn "    $u"; done < "$OUT_DIR/logs/unknown_collections.txt"
  warn "these are exported like every other collection; nothing is skipped."
fi

# --------------------------------------------------------------------------
# 3. page every collection out
# --------------------------------------------------------------------------
: > "$TMP/coll_manifest.ndjson"
: > "$TMP/file_manifest.ndjson"
: > "$TMP/gaps.ndjson"

ID_RE='^[A-Za-z0-9_-]{1,64}$'

export_collection() {
  local cname="$1" cid="$2" ctype="$3" csystem="$4"
  local enc; enc="$(urlenc "$cname")"
  local base="/api/collections/${enc}/records"
  local nd="$OUT_DIR/records/${cname}.ndjson"
  : > "$nd"

  # -- total, taken once, before paging --------------------------------------
  # NOTE ON `jobs`: research_lane.pb.js:436-442 REWRITES the filter of any
  # GET on /api/collections/jobs/records whose filter matches
  # /status\s*=\s*"queued"/ and does not mention `lane`, appending
  # `&& lane != "research" && lane != "supervised_read" && lane != "device_calendar"`.
  # It has no superuser exemption. An export that filtered on status would
  # silently lose three whole lanes of rows. Nothing below ever sends a
  # `status=` filter -- the only filter used is an id cursor.
  local total="-1"
  if api_get "$TMP/probe.json" "$base" \
       --data-urlencode "page=1" --data-urlencode "perPage=1" --data-urlencode "sort=id"; then
    total="$(jq -r '.totalItems // -1' "$TMP/probe.json")"
  else
    warn "$cname: could not read totalItems (HTTP $LAST_CODE)"
  fi

  # SORT IS NOT ALWAYS ALLOWED, AND NEITHER IS COUNTING.
  #
  # `agents` on production refuses BOTH: any request carrying sort= answers 403,
  # and any request that computes totalItems answers 403, while skipTotal=1 with
  # no sort returns rows normally -- 472 of them. Before this probe the export
  # died on that collection and took the whole run with it.
  #
  # Cursor paging needs a stable order, so where sort is refused we fall back to
  # page-number paging with no sort. That is weaker against concurrent writes;
  # the alternative is exporting none of a 472-row collection.
  local sort_ok=1
  if ! api_get "$TMP/sortprobe.json" "$base" \
       --data-urlencode "page=1" --data-urlencode "perPage=1" \
       --data-urlencode "skipTotal=1" --data-urlencode "sort=id"; then
    warn "$cname: sort= refused (HTTP $LAST_CODE); paging unsorted"
    sort_ok=0
    mode_start="nosort"
  fi

  local n=0 last="" mode="${mode_start:-cursor}" pageno=1 got
  unset mode_start
  while :; do
    if [ "$mode" = "cursor" ]; then
      if [ -z "$last" ]; then
        api_get "$TMP/page.json" "$base" \
          --data-urlencode "perPage=$PER_PAGE" --data-urlencode "sort=id" \
          --data-urlencode "skipTotal=1" \
        || { warn "$cname: first cursor page failed (HTTP $LAST_CODE); falling back to offset paging"; mode="offset"; pageno=1; n=0; : > "$nd"; continue; }
      else
        api_get "$TMP/page.json" "$base" \
          --data-urlencode "perPage=$PER_PAGE" --data-urlencode "sort=id" \
          --data-urlencode "skipTotal=1" \
          --data-urlencode "filter=id > \"$last\"" \
        || { warn "$cname: cursor paging rejected (HTTP $LAST_CODE); restarting with offset paging"; mode="offset"; pageno=1; n=0; last=""; : > "$nd"; continue; }
      fi
    elif [ "$mode" = "nosort" ]; then
      api_get "$TMP/page.json" "$base" \
        --data-urlencode "page=$pageno" --data-urlencode "perPage=$PER_PAGE" \
        --data-urlencode "skipTotal=1" \
      || die "$cname: unsorted page $pageno failed (HTTP $LAST_CODE)"
    else
      api_get "$TMP/page.json" "$base" \
        --data-urlencode "page=$pageno" --data-urlencode "perPage=$PER_PAGE" \
        --data-urlencode "sort=id" \
      || die "$cname: offset page $pageno failed (HTTP $LAST_CODE)"
    fi

    got="$(jq -r '.items | length' "$TMP/page.json")"
    if [ "$got" -gt 0 ]; then
      jq -c '.items[]' "$TMP/page.json" >> "$nd"
      n=$((n + got))
    fi
    [ "$got" -lt "$PER_PAGE" ] && break

    if [ "$mode" = "cursor" ]; then
      last="$(jq -r '.items[-1].id // empty' "$TMP/page.json")"
      if ! printf '%s' "$last" | grep -Eq "$ID_RE"; then
        warn "$cname: record id is not cursor-safe; restarting with offset paging"
        mode="offset"; pageno=1; n=0; last=""; : > "$nd"; continue
      fi
    else
      pageno=$((pageno + 1))
    fi
  done

  # -- which declared fields never appeared in the output ---------------------
  # This is how the password/tokenKey/agent_token gap gets WRITTEN DOWN instead
  # of assumed. Whether PocketBase 0.30.4 exempts superusers from hidden-field
  # stripping is not asserted here; it is measured.
  local declared missing=""
  declared="$(jq -r --arg c "$cname" '.[] | select(.name==$c) | .fields[]?.name' "$OUT_DIR/collections.json")"
  local present=""
  if [ "$n" -gt 0 ]; then
    present="$(head -n 200 "$nd" | jq -r 'keys[]' | sort -u)"
  fi
  local f
  for f in $declared; do
    if [ "$n" -gt 0 ] && ! printf '%s\n' "$present" | grep -qx "$f"; then
      missing="${missing}${missing:+,}${f}"
      jq -n --arg c "$cname" --arg f "$f" \
        '{collection:$c, field:$f, reason:"declared on the collection but absent from every exported row (hidden or system-stripped by PocketBase); recoverable only from the native archive"}' \
        >> "$TMP/gaps.ndjson"
    fi
  done

  # -- file-field blobs -------------------------------------------------------
  local filefields downloaded=0
  filefields="$(jq -r --arg c "$cname" '.[] | select(.name==$c) | .fields[]? | select(.type=="file") | .name' "$OUT_DIR/collections.json")"
  local ff
  for ff in $filefields; do
    log "$cname.$ff: downloading blobs"
    jq -r --arg f "$ff" '
      select(has($f)) | .id as $id | .[$f]
      | (if type=="array" then .[] elif type=="string" then . else empty end)
      | select(. != null and . != "")
      | "\($id)\t\(.)"' "$nd" > "$TMP/blobs.tsv" || : > "$TMP/blobs.tsv"
    while IFS=$'\t' read -r rid fname; do
      [ -n "$rid" ] && [ -n "$fname" ] || continue
      local dest="$OUT_DIR/files/${cname}/${rid}"
      mkdir -p "$dest"
      local target="$dest/$fname"
      if api_get_binary "$target" "/api/files/${enc}/$(urlenc "$rid")/$(urlenc "$fname")"; then
        downloaded=$((downloaded + 1))
        jq -n --arg p "files/${cname}/${rid}/${fname}" \
              --arg c "$cname" --arg r "$rid" \
              --argjson b "$(bytes_of "$target")" \
              --arg s "$(sha256_of "$target")" \
          '{path:$p, collection:$c, record:$r, bytes:$b, sha256:$s}' >> "$TMP/file_manifest.ndjson"
      else
        rm -f "$target"
        warn "$cname/$rid/$fname: download failed (HTTP $LAST_CODE)"
        jq -n --arg c "$cname" --arg f "$ff" --arg r "$rid" --arg n "$fname" --arg code "$LAST_CODE" \
          '{collection:$c, field:$f, record:$r, filename:$n, reason:("blob download failed, HTTP " + $code)}' \
          >> "$TMP/gaps.ndjson"
      fi
    done < "$TMP/blobs.tsv"
  done

  # -- per-collection manifest entry -----------------------------------------
  jq -n \
    --arg name "$cname" --arg id "$cid" --arg type "$ctype" \
    --argjson system "$csystem" \
    --argjson total "$total" --argjson rows "$n" \
    --arg missing "$missing" \
    --arg files "$(printf '%s' "$filefields" | tr '\n' ',' | sed 's/,$//')" \
    --argjson downloaded "$downloaded" \
    --arg ndpath "records/${cname}.ndjson" \
    --argjson ndbytes "$(bytes_of "$nd")" \
    --arg ndsha "$(sha256_of "$nd")" \
    '{
      name:$name, id:$id, type:$type, system:$system,
      total_items_reported:$total,
      rows_exported:$rows,
      reconciles: ($total == -1 or $total == $rows),
      fields_absent_from_output: (if $missing == "" then [] else ($missing|split(",")) end),
      file_fields: (if $files == "" then [] else ($files|split(",")) end),
      files_downloaded:$downloaded,
      ndjson: {path:$ndpath, bytes:$ndbytes, sha256:$ndsha}
    }' >> "$TMP/coll_manifest.ndjson"

  if [ "$total" != "-1" ] && [ "$n" != "$total" ]; then
    warn "$cname: exported $n rows but the server reported $total"
  fi
  log "$cname: $n rows (server said $total), $downloaded blob(s)"
}

# Views are derived, not stored. They are exported anyway (cheap, and it makes
# a diff possible), but marked so import_d1.py excludes them from row-count
# reconciliation instead of failing on a table that has no source of truth.
while IFS= read -r cjson; do
  cname="$(printf '%s' "$cjson" | jq -r '.name')"
  cid="$(printf '%s' "$cjson" | jq -r '.id')"
  ctype="$(printf '%s' "$cjson" | jq -r '.type')"
  csystem="$(printf '%s' "$cjson" | jq -r '.system // false')"
  printf '%s' "$cjson" | jq '.' > "$OUT_DIR/schema/${cname}.json"
  log "--- $cname (type=$ctype system=$csystem)"
  export_collection "$cname" "$cid" "$ctype" "$csystem"
done < "$TMP/collections.ndjson"

# --------------------------------------------------------------------------
# 4. the native archive (data.db + /pb_data/storage, verbatim)
# --------------------------------------------------------------------------
BACKUP_JSON='null'
if [ "$PB_CREATE_BACKUP" = "1" ]; then
  BK_NAME="anticipy-export-$(date -u +%Y%m%dT%H%M%SZ).zip"
  log "asking PocketBase for a fresh native archive: $BK_NAME"
  jq -n --arg n "$BK_NAME" '{name:$n}' > "$TMP/bk.json"
  BK_CODE="$(_curl "$TMP/bk_resp.json" -X POST "${PB_URL}/api/backups" \
      -H "Authorization: ${PB_TOKEN}" -H 'Content-Type: application/json' \
      --data-binary @"$TMP/bk.json")"
  case "$BK_CODE" in
    200|204) log "archive created" ;;
    *) warn "archive creation returned HTTP $BK_CODE: $(head -c 400 "$TMP/bk_resp.json" 2>/dev/null || true)" ;;
  esac
fi

if api_get "$TMP/backups.json" "/api/backups"; then
  # PocketBase returns either {items:[...]} or a bare array depending on version.
  jq -r 'if type=="array" then . else (.items // []) end
         | sort_by(.modified // "") | reverse | .[0].key // empty' \
    "$TMP/backups.json" > "$TMP/bkkey"
  BK_KEY="$(cat "$TMP/bkkey")"
  if [ -n "$BK_KEY" ]; then
    log "newest archive: $BK_KEY"
    # PocketBase's download route authenticates with a short-lived FILE TOKEN
    # in the query string. Try that first, then the Authorization header --
    # which of the two a given build accepts is version-dependent, so both are
    # attempted rather than assumed.
    FT=""
    FT_CODE="$(_curl "$TMP/ft.json" -X POST "${PB_URL}/api/files/token" -H "Authorization: ${PB_TOKEN}")"
    if [ "$FT_CODE" = "200" ]; then FT="$(jq -r '.token // empty' "$TMP/ft.json")"; fi
    rm -f "$TMP/ft.json"
    BK_DEST="$OUT_DIR/backup/${BK_KEY##*/}"
    OK=0
    if [ -n "$FT" ]; then
      if api_get_binary "$BK_DEST" "/api/backups/$(urlenc "$BK_KEY")?token=$(urlenc "$FT")"; then OK=1; fi
    fi
    if [ "$OK" != "1" ]; then
      if api_get_binary "$BK_DEST" "/api/backups/$(urlenc "$BK_KEY")"; then OK=1; fi
    fi
    if [ "$OK" = "1" ]; then
      # A zip that does not open is not a backup.
      if command -v unzip >/dev/null 2>&1; then
        if unzip -tqq "$BK_DEST" >>"$LOG" 2>&1; then
          log "archive CRC check passed"
        else
          warn "archive failed its CRC check -- DO NOT trust it"
          jq -n '{collection:"(native archive)", field:"-", reason:"downloaded archive failed unzip -t"}' >> "$TMP/gaps.ndjson"
          OK=0
        fi
      else
        warn "unzip not installed; archive CRC not checked"
      fi
    fi
    if [ "$OK" = "1" ]; then
      BACKUP_JSON="$(jq -n --arg k "$BK_KEY" --arg p "backup/${BK_KEY##*/}" \
        --argjson b "$(bytes_of "$BK_DEST")" --arg s "$(sha256_of "$BK_DEST")" \
        '{key:$k, path:$p, bytes:$b, sha256:$s, crc_checked:true}')"
      log "archive saved: $BK_DEST ($(bytes_of "$BK_DEST") bytes)"
    else
      rm -f "$BK_DEST"
      warn "could not download the native archive (last HTTP $LAST_CODE)"
    fi
  else
    warn "no native archive is listed on this instance"
  fi
else
  warn "could not list archives (HTTP $LAST_CODE)"
fi

if [ "$PB_REQUIRE_BACKUP" = "1" ] && [ "$BACKUP_JSON" = "null" ]; then
  jq -n '{collection:"(native archive)", field:"-", reason:"no native archive was obtained; password hashes, tokenKeys, agents.agent_token and /pb_data/storage are NOT in this export"}' >> "$TMP/gaps.ndjson"
fi

# --------------------------------------------------------------------------
# 5. manifest + digests + verdict
# --------------------------------------------------------------------------
log "writing manifest"
jq -n \
  --arg started "$STARTED_AT" \
  --arg finished "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg url "$PB_URL" \
  --argjson collections "$(jq -s '.' "$TMP/coll_manifest.ndjson")" \
  --argjson files "$(jq -s '.' "$TMP/file_manifest.ndjson")" \
  --argjson gaps "$(jq -s '.' "$TMP/gaps.ndjson")" \
  --argjson backup "$BACKUP_JSON" \
  --argjson unknown "$(jq -Rs 'split("\n") | map(select(length>0))' "$OUT_DIR/logs/unknown_collections.txt")" \
  '{
     format: "anticipy-pb-export-1",
     started_at: $started,
     finished_at: $finished,
     source: {url: $url},
     collections: $collections,
     collections_not_in_repo: $unknown,
     files: $files,
     backup: $backup,
     gaps: $gaps,
     totals: {
       collections: ($collections | length),
       rows: ($collections | map(.rows_exported) | add // 0),
       blobs: ($files | length)
     },
     reconciled: ($collections | map(.reconciles) | all)
   }' > "$OUT_DIR/manifest.json"

# logs/export.log is deliberately excluded: it is still being written when this
# runs, so hashing it produces a digest that is stale the moment the next line
# is logged. It is a transcript, not data -- nothing is recovered from it.
( cd "$OUT_DIR" && find . -type f ! -name SHA256SUMS ! -path './logs/export.log' -print0 \
    | sort -z | xargs -0 $SHA_CMD > SHA256SUMS )
log "SHA256SUMS written ($(wc -l < "$OUT_DIR/SHA256SUMS" | tr -d ' ') entries, excluding logs/export.log)"

echo
echo "================= EXPORT SUMMARY ================="
jq -r '
  "source        : " + .source.url,
  "collections   : " + (.totals.collections|tostring),
  "rows          : " + (.totals.rows|tostring),
  "blobs         : " + (.totals.blobs|tostring),
  "native archive: " + (if .backup == null then "MISSING" else (.backup.path + "  sha256=" + .backup.sha256) end),
  "reconciled    : " + (.reconciled|tostring),
  "",
  "per collection:",
  (.collections[] | "  " + (if .reconciles then "ok  " else "MISMATCH " end)
     + (.name|tostring) + "  rows=" + (.rows_exported|tostring)
     + "  server=" + (.total_items_reported|tostring)
     + (if (.fields_absent_from_output|length) > 0 then "  absent_fields=" + (.fields_absent_from_output|join("/")) else "" end)),
  "",
  (if (.collections_not_in_repo|length) > 0 then "collections in production but not in backend/pb_migrations/: " + (.collections_not_in_repo|join(", ")) else "every production collection is known to the repo" end),
  "",
  (if (.gaps|length) > 0 then "GAPS (" + (.gaps|length|tostring) + "):" else "no gaps recorded" end),
  (.gaps[]? | "  - " + .collection + "." + .field + ": " + .reason)
' "$OUT_DIR/manifest.json"
echo "=================================================="

RECONCILED="$(jq -r '.reconciled' "$OUT_DIR/manifest.json")"
if [ "$RECONCILED" != "true" ]; then
  die "row counts do not reconcile -- see manifest.json. NOTHING may be decommissioned on this export." 3
fi
if [ "$PB_REQUIRE_BACKUP" = "1" ] && [ "$BACKUP_JSON" = "null" ]; then
  die "no native archive was obtained and PB_REQUIRE_BACKUP=1. Password hashes and hidden fields are NOT in this export." 3
fi

log "export complete: $OUT_DIR"
