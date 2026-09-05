#!/usr/bin/env python3
"""Extract the owners-collection auth-token secret from PocketBase's data.db and
emit ONLY that value on stdout, for piping straight into `wrangler secret put`.

WHY THIS EXISTS
  The Worker signs owner auth tokens HS256 with `ANTICIPY_AUTH_SECRET + tokenKey`
  (migration/workers/src/pb/auth.ts:80). PocketBase signs the same tokens with
  `<owners collection authToken.secret> + tokenKey`. tokenKey migrated to D1; the
  secret is a SETTING, not a column, so it did NOT. Until ANTICIPY_AUTH_SECRET on
  anticipy-api equals that collection secret, EVERY existing token fails on the
  Worker and cutover logs everyone out. See
  research/2026-09-04-the-auth-secret-nobody-set.md.

WHY NOT THE OBVIOUS ONE-LINER
  The first attempt pulled /app/pb_data/data.db — the 156 KB EMPTY image default,
  not the 17 MB volume at /pb_data/data.db — so _collections was empty, the JSON
  lookup returned None, and `wrangler secret put` was fed an EMPTY STRING. This
  script guards BOTH failure modes that break auth silently:
    1. wrong / empty DB  -> it aborts loudly instead of emitting nothing;
    2. trailing newline   -> it writes the secret with NO newline, because
                             `secret\n` + tokenKey != `secret` + tokenKey.
  It NEVER prints the secret value to a human-readable stream. Proof-of-life on
  stderr is length + a short sha256 prefix only.

USAGE  (run on the Railway container if it has python3, so the customer DB never
        leaves the box; otherwise on an approved local copy):

    # DRY CHECK FIRST — proof-of-life to stderr, nothing set:
    python3 extract_auth_secret.py /pb_data/data.db --check

    # THEN set it, guarded so a failed extract can NEVER feed wrangler an empty
    # value. Do NOT use a bare `python3 ... | wrangler ...` pipe: in a pipe the
    # consumer (wrangler) still runs on empty stdin when the producer aborts,
    # which is precisely how the secret got set to "" last time. Capture, check,
    # then set:
    set -euo pipefail
    SECRET="$(python3 extract_auth_secret.py /pb_data/data.db)"   # aborts here if extract fails
    [ -n "$SECRET" ] || { echo "empty secret — refusing to set"; exit 1; }
    printf %s "$SECRET" | npx wrangler secret put ANTICIPY_AUTH_SECRET --name anticipy-api
    unset SECRET

  `printf %s` adds no trailing newline (a newline would corrupt the HMAC key).
  `--name anticipy-api` must match the deployed API Worker. Confirm afterward
  with `npx wrangler secret list --name anticipy-api` (name only shows), then run
  the cross-origin auth leg in the contract suite, which goes green only once the
  secret matches.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys


def _search_secret(obj) -> str | None:
    """Recursively find an authToken.secret. Robust to PocketBase schema drift:
    it does not assume WHICH column or nesting holds the options JSON. Returns
    the first non-empty string sitting at `...->authToken->secret`, else the
    first non-empty string at any key literally named `secret` under a parent
    whose key contains 'token'. Values are never logged here."""
    # exact path: {..., "authToken": {"secret": "..."}}
    if isinstance(obj, dict):
        at = obj.get("authToken")
        if isinstance(at, dict):
            sec = at.get("secret")
            if isinstance(sec, str) and sec.strip():
                return sec
        for k, v in obj.items():
            found = _search_secret(v)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _search_secret(v)
            if found:
                return found
    return None


def _keys_present(obj, depth=0) -> list[str]:
    """Key NAMES only (never values), for the diagnostic when nothing is found."""
    out: list[str] = []
    if isinstance(obj, dict) and depth < 3:
        for k, v in obj.items():
            out.append(k)
            out.extend(_keys_present(v, depth + 1))
    return out


def extract(db_path: str) -> str:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        # Sanity: a real data.db has a populated _collections. The empty image
        # default does not — refuse it rather than emit nothing.
        try:
            n = cur.execute("SELECT count(*) FROM _collections").fetchone()[0]
        except sqlite3.OperationalError as e:
            raise SystemExit(
                f"ABORT: {db_path} has no _collections table ({e}). This is not a "
                f"PocketBase data.db. The real one is the 17 MB volume mount at "
                f"/pb_data/data.db, NOT /app/pb_data/data.db (the empty default)."
            )
        if not n:
            raise SystemExit(
                f"ABORT: _collections is EMPTY in {db_path}. You are almost "
                f"certainly on /app/pb_data/data.db (image default). Use "
                f"/pb_data/data.db (the Railway volume)."
            )

        # Pull every column of the owners collection row and search each for the
        # secret — no assumption about which column holds the options JSON.
        cur.execute("PRAGMA table_info(_collections)")
        cols = [r[1] for r in cur.fetchall()]
        cur.execute("SELECT * FROM _collections WHERE name = 'owners'")
        row = cur.fetchone()
        if row is None:
            raise SystemExit("ABORT: no _collections row named 'owners'.")

        seen_keys: list[str] = []
        for col, val in zip(cols, row):
            if not isinstance(val, (str, bytes)):
                continue
            try:
                parsed = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                continue
            seen_keys.extend(_keys_present(parsed))
            sec = _search_secret(parsed)
            if sec:
                return sec

        # Older PocketBase kept app settings in _params — try there as a fallback.
        try:
            for (val,) in cur.execute("SELECT value FROM _params"):
                try:
                    parsed = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    continue
                sec = _search_secret(parsed)
                if sec:
                    return sec
        except sqlite3.OperationalError:
            pass

        raise SystemExit(
            "ABORT: found the owners collection but no authToken.secret in it. "
            "This PocketBase version stores it elsewhere — do NOT guess. Keys seen "
            "on the owners row (names only, no values): "
            + ", ".join(sorted(set(seen_keys))[:40])
        )
    finally:
        con.close()


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    check_only = "--check" in argv[1:]
    if not args:
        sys.stderr.write("usage: extract_auth_secret.py <path-to-data.db> [--check]\n")
        return 2
    secret = extract(args[0])
    # proof-of-life WITHOUT disclosure: length + short hash prefix, to stderr.
    digest = hashlib.sha256(secret.encode()).hexdigest()[:12]
    sys.stderr.write(f"found authToken.secret: len={len(secret)} sha256[:12]={digest}\n")
    if check_only:
        sys.stderr.write("--check: not emitting the secret. Re-run without --check to set it.\n")
        return 0
    # THE secret, no trailing newline — a newline would corrupt the HMAC key.
    sys.stdout.write(secret)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
