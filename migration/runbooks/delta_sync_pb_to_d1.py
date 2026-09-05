#!/usr/bin/env python3
"""ONE-TIME delta re-sync: PocketBase (Railway) -> D1 (Cloudflare).

PURPOSE
  D1 was seeded from PocketBase at the original migration, but both have been
  live since, so PocketBase holds recent records D1 never got (events, jobs,
  profile edits, etc.). Before retiring Railway, copy those recent records into
  D1 so users who update their app don't lose anything. After this runs and
  Railway is retired, PocketBase is never read again — Cloudflare/D1 is the only
  datastore. This is a RECONCILIATION, not ongoing PocketBase use.

WHAT IT DOES
  For each collection that exists in BOTH PocketBase and D1, pull the records
  whose `updated` (or `created`) is newer than --since, and INSERT OR REPLACE
  them into D1 by primary key `id`. Idempotent: re-running is safe (same rows,
  same bytes). Never deletes anything in D1. Bound parameters (not SQL text) so
  large rows (agent_llm_audit, jobs) are not rejected — same trick as
  load_d1_api.py.

SAFETY / SEMANTICS
  * READ-ONLY on PocketBase. WRITE-ONLY (upsert) on D1. No deletes anywhere.
  * "Last write wins" by id: a PB record newer than --since overwrites the D1
    row with the same id. Rows only edited on the D1 side since the cutoff and
    NOT touched on PB are left alone (PB won't return them). If a row was edited
    on BOTH sides since the cutoff, PB wins — acceptable because during the
    transition PB is the system of record for already-shipped clients.
  * Datetimes are written through verbatim from PB (space-format, e.g.
    "2026-09-05 07:32:00.000Z"), which matches the Worker's pbNow() format — so
    text comparisons in D1 stay consistent (see migration notes on the T-format
    vs space-format hazard).
  * Run it in CI (customer data touches only the ephemeral runner, never a
    laptop) via .github/workflows/delta-sync.yml. Run it at the FREEZE moment,
    just before flipping clients / retiring Railway, with --since set to a bit
    before the original migration (safe: idempotent upsert).

ENV (provide via CI secrets; never printed):
  PB_BASE                 https://backend-production-61e0a.up.railway.app
  POCKETBASE_ADMIN_EMAIL  a superuser email (auth-with-password)
  POCKETBASE_ADMIN_PASSWORD
  CLOUDFLARE_API_TOKEN    D1:Edit on the account
  CLOUDFLARE_ACCOUNT_ID   114587b715e702461766369b01d42fc7
  D1_DATABASE_ID          f341f23d-ec52-4b2f-9a2d-13117ebee86e

USAGE
  python3 delta_sync_pb_to_d1.py --since "2026-09-04 00:00:00" [--dry-run]
                                 [--collections owners,events,jobs,...]
  --dry-run reads + counts but writes NOTHING to D1 (use it first).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CF_API = "https://api.cloudflare.com/client/v4"

# Collections to reconcile: the user/brain-mutable ones present in both stores.
# System/auth-internal and immutable-config tables are excluded. Order matters
# only for readability; upserts are independent.
DEFAULT_COLLECTIONS = [
    "owners", "owner_profile", "agents", "pendants", "segments",
    "events", "jobs", "evidence", "purges",
    "agent_audit_sessions", "agent_llm_audit",
    "fellows", "fellow_applications", "fellow_submissions", "fellow_conversions",
    "fellow_codes", "fellow_clicks", "fellow_meter", "fellow_progress",
    "fellow_payouts",
    "internal_people", "internal_todos", "internal_events", "internal_notes",
    "internal_comments", "internal_notifs", "internal_reminders",
    "internal_activity", "internal_expenses", "internal_meter",
    "internal_sessions", "internal_tracks", "internal_config",
    "password_resets", "users",
]

# PocketBase envelope fields that are not D1 columns.
DROP = {"collectionId", "collectionName", "expand"}


def _req(url: str, data=None, headers=None, method="GET"):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return True, json.load(r)
    except urllib.error.HTTPError as e:
        return False, e.read().decode()[:400]
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:300]


def pb_admin_token(pb_base: str, email: str, password: str) -> str:
    # PocketBase 0.23+ superuser auth. Falls back to the legacy admins route.
    for path in ("/api/collections/_superusers/auth-with-password",
                 "/api/admins/auth-with-password"):
        ok, resp = _req(pb_base + path,
                        data={"identity": email, "password": password},
                        headers={"Content-Type": "application/json"}, method="POST")
        if ok and isinstance(resp, dict) and resp.get("token"):
            return resp["token"]
    raise SystemExit("could not authenticate to PocketBase as superuser "
                     "(check POCKETBASE_ADMIN_EMAIL / _PASSWORD)")


def pb_fetch(pb_base: str, token: str, coll: str, since: str, ts_field: str):
    """Return (rows, ok). rows = all PB records for `coll` with ts_field > since,
    paginated. ok=False means the request errored (e.g. ts_field/collection
    absent) — caller should try another timestamp field or skip. Never raises."""
    rows = []
    page = 1
    while True:
        q = urllib.parse.urlencode({
            "page": page, "perPage": 200, "sort": ts_field,
            "filter": f'{ts_field} > "{since}"',
        })
        ok, resp = _req(f"{pb_base}/api/collections/{coll}/records?{q}",
                        headers={"Authorization": token})
        if not ok or not isinstance(resp, dict):
            return rows, False
        items = resp.get("items", [])
        rows.extend(items)
        if page >= resp.get("totalPages", 1) or not items:
            return rows, True
        page += 1


def d1_query(account: str, database: str, token: str, sql: str, params):
    ok, resp = _req(f"{CF_API}/accounts/{account}/d1/database/{database}/query",
                    data={"sql": sql, "params": params},
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"}, method="POST")
    return ok, resp


def upsert(account, database, token, coll, row) -> tuple[bool, str]:
    cols = [c for c in row if c not in DROP]
    vals = []
    for c in cols:
        v = row[c]
        if isinstance(v, bool):
            v = 1 if v else 0
        elif isinstance(v, (dict, list)):
            v = json.dumps(v, separators=(",", ":"))
        vals.append(v)
    sql = 'INSERT OR REPLACE INTO "%s" (%s) VALUES (%s)' % (
        coll, ",".join('"%s"' % c for c in cols), ",".join("?" * len(cols)))
    ok, resp = d1_query(account, database, token, sql, vals)
    return ok, ("" if ok else str(resp)[:200])


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True,
                    help='cutoff, e.g. "2026-09-04 00:00:00" (space-format, UTC)')
    ap.add_argument("--collections", default="",
                    help="comma list; default = the curated mutable set")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    pb_base = (os.environ.get("PB_BASE") or
               "https://backend-production-61e0a.up.railway.app").rstrip("/")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "114587b715e702461766369b01d42fc7"
    database = os.environ.get("D1_DATABASE_ID") or "f341f23d-ec52-4b2f-9a2d-13117ebee86e"
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN") or ""
    pb_email = os.environ.get("POCKETBASE_ADMIN_EMAIL") or ""
    pb_pass = os.environ.get("POCKETBASE_ADMIN_PASSWORD") or ""

    if not a.dry_run and not cf_token:
        raise SystemExit("CLOUDFLARE_API_TOKEN required to write D1 (or use --dry-run)")
    if not (pb_email and pb_pass):
        raise SystemExit("POCKETBASE_ADMIN_EMAIL and POCKETBASE_ADMIN_PASSWORD required")

    token = pb_admin_token(pb_base, pb_email, pb_pass)
    colls = [c.strip() for c in a.collections.split(",") if c.strip()] or DEFAULT_COLLECTIONS

    print(f"delta-sync {pb_base} -> D1 {database}")
    print(f"since={a.since}  dry_run={a.dry_run}  collections={len(colls)}")
    grand_scanned = grand_upserted = grand_failed = 0
    for coll in colls:
        scanned = upserted = failed = 0
        used_field = None
        for ts_field in ("updated", "created"):
            rows, ok = pb_fetch(pb_base, token, coll, a.since, ts_field)
            if not ok:
                continue  # ts_field/collection not queryable → try next field
            used_field = ts_field
            for rec in rows:
                scanned += 1
                if a.dry_run:
                    continue
                good, err = upsert(account, database, cf_token, coll, rec)
                if good:
                    upserted += 1
                else:
                    failed += 1
                    if failed <= 2:
                        print(f"    {coll} {rec.get('id')}: {err}")
            break  # first queryable field wins (prefer 'updated')
        tag = f"(by {used_field})" if used_field else "(collection absent / not queryable)"
        print(f"  {coll:24s} scanned={scanned:5d} upserted={upserted:5d} failed={failed:3d} {tag}")
        grand_scanned += scanned
        grand_upserted += upserted
        grand_failed += failed

    print(f"---- TOTAL scanned={grand_scanned} upserted={grand_upserted} failed={grand_failed}")
    if grand_failed:
        print("::error:: some upserts failed — investigate before retiring Railway")
        return 1
    print("delta-sync complete; D1 now has PocketBase's recent records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
