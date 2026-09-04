#!/usr/bin/env python3
"""Load a PocketBase export into D1 over the HTTP API, with BOUND parameters.

WHY THIS EXISTS, when import_d1.py already emits SQL.

`wrangler d1 execute --file` sends SQL as TEXT, and D1 rejects any single
statement over its size limit. agent_llm_audit stores whole LLM request and
response bodies -- measured on this export: 100 rows, median 128 KB, max 194 KB,
82 of them over 100 KB -- so even ONE row per INSERT is too long as text, and no
amount of re-chunking fixes it. jobs is the same shape one size down: no row
exceeds 96 KB on its own, but SQL escaping inflates it past the ceiling.

Bound parameters do not go through the SQL text, so the limit does not apply.
That is the whole trick.

Usage:
  python3 load_d1_api.py <export_dir> <collection> [--account ID] [--database UUID]
Env: CLOUDFLARE_API_TOKEN, or an OAuth token from wrangler's config.
"""
import argparse, json, os, re, sys, urllib.error, urllib.request

API = "https://api.cloudflare.com/client/v4"


def wrangler_oauth_token():
    p = os.path.expanduser("~/Library/Preferences/.wrangler/config/default.toml")
    try:
        m = re.search(r'oauth_token\s*=\s*"([^"]+)"', open(p).read())
        return m.group(1) if m else ""
    except OSError:
        return ""


def query(account, database, token, sql, params):
    body = json.dumps({"sql": sql, "params": params}).encode()
    req = urllib.request.Request(
        f"{API}/accounts/{account}/d1/database/{database}/query",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return True, json.load(r)
    except urllib.error.HTTPError as e:
        return False, e.read().decode()[:300]
    except Exception as e:                       # noqa: BLE001
        return False, str(e)[:200]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("export_dir")
    ap.add_argument("collection")
    ap.add_argument("--account", default="114587b715e702461766369b01d42fc7")
    ap.add_argument("--database", required=True)
    ap.add_argument("--token", default="")
    a = ap.parse_args(argv)

    token = a.token or os.environ.get("CLOUDFLARE_API_TOKEN") or wrangler_oauth_token()
    if not token:
        sys.exit("no API token: set CLOUDFLARE_API_TOKEN or run `wrangler login`")

    nd = os.path.join(a.export_dir, "records", a.collection + ".ndjson")
    rows = [json.loads(l) for l in open(nd) if l.strip()]
    if not rows:
        print(f"  {a.collection}: nothing to load")
        return 0

    # PocketBase envelope fields are not columns.
    drop = {"collectionId", "collectionName", "expand"}
    ok = failed = 0
    for row in rows:
        cols = [c for c in row if c not in drop]
        vals = []
        for c in cols:
            v = row[c]
            if isinstance(v, bool):
                v = 1 if v else 0
            elif isinstance(v, (dict, list)):
                v = json.dumps(v, separators=(",", ":"))
            vals.append(v)
        sql = 'INSERT OR REPLACE INTO "%s" (%s) VALUES (%s)' % (
            a.collection,
            ",".join('"%s"' % c for c in cols),
            ",".join("?" * len(cols)))
        good, resp = query(a.account, a.database, token, sql, vals)
        if good:
            ok += 1
        else:
            failed += 1
            if failed <= 3:
                print(f"    row {row.get('id')}: {resp}")
    print(f"  {a.collection}: {ok} loaded, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
