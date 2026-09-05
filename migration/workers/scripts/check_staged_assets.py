#!/usr/bin/env python3
"""Are the zips the Worker would ship the zips the repo committed?

    python3 migration/workers/scripts/check_staged_assets.py

WHY THIS EXISTS. migration/workers/public/ is gitignored on purpose (it is
1.3 MB of zips that already live in backend/pb_public/) and is populated by
`npm run stage:assets` at deploy time. That makes it a copy that can go stale
without any diff showing it: on 2026-09-05 the deployed Worker was serving an
extension zip at 0.12.0 while backend/pb_public/ held 0.13.0. Law 3 — stale
code has shipped twice before — and this is the check that makes the copy
visible. overnight/stranger_gate.py compares the LIVE zip against the source;
this compares the STAGED zip against the committed one, which is the step
before it.

WHAT IT CHECKS. Every *.zip under backend/pb_public/ (recursively) has a
byte-identical twin under migration/workers/public/ — sha256, not size — and
public/ carries no zip the source does not. It also prints the version from
each zip's manifest.json when it has one, so a stale copy is named by number.

EXIT
  0  every zip is staged and byte-identical
  1  public/ is missing, or a zip is missing, differs, or is an extra
  2  could not run (backend/pb_public/ is not where this script expects)
"""
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
WORKERS = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(WORKERS))
SRC = os.path.join(ROOT, "backend", "pb_public")
DST = os.path.join(WORKERS, "public")


def zips_under(root):
    out = []
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".zip"):
                out.append(os.path.relpath(os.path.join(base, name), root))
    return sorted(out)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def version_of(path):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            manifest = "manifest.json" if "manifest.json" in names else next(
                (n for n in names if n.endswith("/manifest.json")), None)
            if not manifest:
                return ""
            return str(json.loads(z.read(manifest).decode("utf-8")).get("version") or "")
    except Exception:
        return ""


def main():
    if not os.path.isdir(SRC):
        print("check-assets: %s is missing; run from a full checkout" % SRC, file=sys.stderr)
        return 2
    if not os.path.isdir(DST):
        print("check-assets: %s is not staged — run `npm run stage:assets` in migration/workers"
              % DST, file=sys.stderr)
        return 1

    problems = 0
    wanted = zips_under(SRC)
    staged = zips_under(DST)
    if not wanted:
        print("check-assets: no zips under %s — nothing to compare" % SRC, file=sys.stderr)
        return 2
    for rel in wanted:
        src = os.path.join(SRC, rel)
        dst = os.path.join(DST, rel)
        s_sha = sha256(src)
        s_ver = version_of(src)
        label = "%s  v=%s" % (rel, s_ver or "-")
        if not os.path.isfile(dst):
            problems += 1
            print("MISSING  %s  (repo %s)" % (label, s_sha[:12]))
            continue
        d_sha = sha256(dst)
        if d_sha != s_sha:
            problems += 1
            print("DIFFERS  %s  repo %s v=%s  staged %s v=%s" % (
                rel, s_sha[:12], s_ver or "-", d_sha[:12], version_of(dst) or "-"))
            continue
        print("OK       %s  %s" % (label, s_sha[:12]))
    for rel in staged:
        if rel not in wanted:
            problems += 1
            print("EXTRA    %s  (staged, not in backend/pb_public)" % rel)

    if problems:
        print("check-assets: %d problem(s); run `npm run stage:assets` in migration/workers"
              % problems, file=sys.stderr)
        return 1
    print("check-assets: %d zip(s) staged byte-identical" % len(wanted))
    return 0


if __name__ == "__main__":
    sys.exit(main())
