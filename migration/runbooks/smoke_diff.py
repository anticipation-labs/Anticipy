#!/usr/bin/env python3
"""Diff two smoke.sh --json runs.

    ./migration/runbooks/smoke.sh https://www.anticipy.ai      --json prod.json
    ./migration/runbooks/smoke.sh https://<preview>.workers.dev --json cf.json
    ./migration/runbooks/smoke_diff.py prod.json cf.json

WHY A DIFF AND NOT JUST "BOTH GREEN". Both runs can pass and still disagree:
a route that answers 401 on Vercel because a secret is set, and 401 on Workers
because the secret is MISSING and the handler bailed earlier, are the same
number and not the same behaviour. Worse, a page that 200s with an error page
rendered inside it also 200s. So the gate is not "the new one is green", it is
"the new one is green AND it differs from the old one nowhere, except where a
human wrote the difference down below".

Exit 0 when the two runs agree (modulo ACCEPTED). Exit 1 otherwise.
"""
import json
import sys

# Differences that are CORRECT and expected on Cloudflare. Every entry needs a
# reason. An empty dict is the honest starting state: add a row only when you
# have followed the difference and understood it, never to get a green run.
ACCEPTED: dict[str, str] = {
    # "/api/geo": "cf-ipcity vs x-vercel-ip-city; see spike/website-verification.md",
}


def load(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def key(row: dict) -> str:
    return f"{row['kind']} {row['method']} {row['path']}"


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: smoke_diff.py <old.json> <new.json>", file=sys.stderr)
        return 2
    old, new = load(sys.argv[1]), load(sys.argv[2])
    o = {key(r): r for r in old["results"]}
    n = {key(r): r for r in new["results"]}

    drift, accepted, missing, added = [], [], [], []

    for k in sorted(set(o) | set(n)):
        if k not in n:
            missing.append(k)
            continue
        if k not in o:
            added.append(k)
            continue
        if o[k]["status"] != n[k]["status"]:
            path = n[k]["path"]
            row = (k, o[k]["status"], n[k]["status"])
            (accepted if path in ACCEPTED else drift).append(row)

    print(f"old  {old['base']}   pass {old['pass']} fail {old['fail']}")
    print(f"new  {new['base']}   pass {new['pass']} fail {new['fail']}")
    print()

    for k in missing:
        print(f"  MISSING FROM NEW   {k}")
    for k in added:
        print(f"  ONLY IN NEW        {k}")
    for k, a, b in accepted:
        print(f"  accepted           {k}: {a} -> {b}   ({ACCEPTED[k.split(' ',2)[2]]})")
    for k, a, b in drift:
        print(f"  DRIFT              {k}: {a} -> {b}")

    bad = len(drift) + len(missing) + len(added)
    print()
    print(f"{'DIFFERENCES: ' + str(bad) if bad else 'IDENTICAL (modulo accepted)'}")
    # A failing new run is a failure even if it matches the old one exactly --
    # two identically-broken backends is not a passing cutover.
    if new["fail"]:
        print(f"new run has {new['fail']} outright failures")
        bad += new["fail"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
