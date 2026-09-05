#!/usr/bin/env python3
"""Is it safe to retire Railway yet? Compares RECENT client-write volume on
PocketBase (Railway) vs D1 (Cloudflare).

THE SIGNAL
  Already-shipped clients (old iOS build, current extension) post to Railway's
  PocketBase. As users update to the api.anticipy.ai build, their writes move to
  D1. So: while PocketBase is still getting fresh client records, users remain on
  Railway — do NOT retire it. When PocketBase's recent-write count falls to ~0
  (and D1's has taken over), the fleet has migrated and Railway can be retired.

  This reads only COUNTS (totalItems / count(*)), never record contents — it's
  metadata, so it's safe to run anywhere.

WHAT IT CHECKS (per client-written collection, last --hours):
    events, jobs, agents, owner_profile, evidence
  PocketBase new-records (via list API totalItems) vs D1 new-records (count(*)).

VERDICT
  RETIRE-READY when PocketBase new-writes across those collections is 0 for the
  window (nothing new landing on Railway) AND D1 is receiving writes (clients are
  on Cloudflare). Otherwise HOLD.

ENV: POCKETBASE_ADMIN_EMAIL/_PASSWORD (PB superuser), CLOUDFLARE_API_TOKEN,
     CLOUDFLARE_ACCOUNT_ID, D1_DATABASE_ID, PB_BASE (defaults provided).
USAGE: python3 railway_retire_readiness.py [--hours 24]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

CF_API = "https://api.cloudflare.com/client/v4"
COLLECTIONS = ["events", "jobs", "agents", "owner_profile", "evidence"]


def _req(url, data=None, headers=None, method="GET"):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return True, json.load(r)
    except urllib.error.HTTPError as e:
        return False, e.read().decode()[:300]
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]


def pb_token(pb_base, email, password):
    for path in ("/api/collections/_superusers/auth-with-password",
                 "/api/admins/auth-with-password"):
        ok, resp = _req(pb_base + path, data={"identity": email, "password": password},
                        headers={"Content-Type": "application/json"}, method="POST")
        if ok and isinstance(resp, dict) and resp.get("token"):
            return resp["token"]
    raise SystemExit("PocketBase superuser auth failed")


def pb_count(pb_base, token, coll, since):
    q = urllib.parse.urlencode({"page": 1, "perPage": 1, "filter": f'created > "{since}"'})
    ok, resp = _req(f"{pb_base}/api/collections/{coll}/records?{q}",
                    headers={"Authorization": token})
    if not ok or not isinstance(resp, dict):
        return None
    return resp.get("totalItems", 0)


def d1_count(account, database, token, coll, since):
    sql = f'SELECT count(*) AS n FROM "{coll}" WHERE created > ?'
    ok, resp = _req(f"{CF_API}/accounts/{account}/d1/database/{database}/query",
                    data={"sql": sql, "params": [since]},
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"}, method="POST")
    if not ok:
        return None
    try:
        return resp["result"][0]["results"][0]["n"]
    except Exception:  # noqa: BLE001
        return None


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    a = ap.parse_args(argv)

    pb_base = (os.environ.get("PB_BASE") or
               "https://backend-production-61e0a.up.railway.app").rstrip("/")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or "114587b715e702461766369b01d42fc7"
    database = os.environ.get("D1_DATABASE_ID") or "f341f23d-ec52-4b2f-9a2d-13117ebee86e"
    cf_token = os.environ.get("CLOUDFLARE_API_TOKEN") or ""
    pb_email = os.environ.get("POCKETBASE_ADMIN_EMAIL") or ""
    pb_pass = os.environ.get("POCKETBASE_ADMIN_PASSWORD") or ""
    if not (pb_email and pb_pass and cf_token):
        raise SystemExit("need POCKETBASE_ADMIN_EMAIL/_PASSWORD and CLOUDFLARE_API_TOKEN")

    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=a.hours)) \
        .strftime("%Y-%m-%d %H:%M:%S")
    tok = pb_token(pb_base, pb_email, pb_pass)

    print(f"Railway-retirement readiness — new records since {since} UTC ({a.hours}h)")
    print(f"{'collection':16s} {'Railway(PB)':>12s} {'Cloudflare(D1)':>15s}")
    pb_total = d1_total = 0
    for coll in COLLECTIONS:
        p = pb_count(pb_base, tok, coll, since)
        d = d1_count(account, database, cf_token, coll, since)
        print(f"{coll:16s} {str(p):>12s} {str(d):>15s}")
        pb_total += p or 0
        d1_total += d or 0
    print(f"{'TOTAL':16s} {pb_total:>12d} {d1_total:>15d}")

    if pb_total == 0 and d1_total > 0:
        print("VERDICT: RETIRE-READY — no new Railway writes; clients are on Cloudflare.")
        return 0
    if pb_total == 0 and d1_total == 0:
        print("VERDICT: INCONCLUSIVE — no writes anywhere in the window (quiet period). "
              "Re-check during active hours.")
        return 2
    print(f"VERDICT: HOLD — Railway still received {pb_total} client writes; "
          f"users have not fully migrated. Keep Railway running.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
