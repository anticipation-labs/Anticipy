"""Do this Mac, GitHub, and the running container agree?

Three places each believe they are the truth, and nothing forces them to
agree. Every "you said you fixed it and it's still broken" in this project
traces back to that: work committed here but never pushed, work pushed but
never deployed, work deployed from a tree that was missing someone else's
commits. On 2026-08-11 it caught me too — I reasoned about "the last 20
commits" on this Mac while production was correctly running a commit that
only existed on GitHub, and briefly deployed over it.

So stop reasoning about it and ask. Ten seconds, no arguments:

    python3 proof/is_it_live.py

It prints one verdict. Anything other than IN SYNC names what to do.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

BACKEND = "https://backend-production-61e0a.up.railway.app"
REMOTE = "github"
BRANCH = "pendant-system"


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def local_brain() -> str:
    from brain.worker import _brain_fingerprint
    return _brain_fingerprint()


def running_brain() -> str | None:
    """What the container itself says it is running. The deploy status is a
    claim about a container; this is the code."""
    out = subprocess.run(["railway", "logs", "--service", "worker"], cwd=ROOT,
                         capture_output=True, text=True, timeout=120).stdout
    marks = [w for line in out.splitlines() for w in line.split()
             if w.startswith("brain=")]
    return marks[-1].split("=", 1)[1] if marks else None


def served_extension() -> str | None:
    """The version a person actually downloads — not the one in the folder."""
    import io
    import zipfile
    try:
        with urllib.request.urlopen(f"{BACKEND}/anticipy-extension.zip", timeout=40) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
            return json.loads(z.read("manifest.json"))["version"]
    except Exception:
        return None


def source_extension() -> str:
    with open(os.path.join(ROOT, "extension", "manifest.json")) as f:
        return json.load(f)["version"]


def main() -> int:
    problems = []

    sh("git", "fetch", REMOTE, BRANCH)
    ahead = sh("git", "rev-list", "--count", f"{REMOTE}/{BRANCH}..HEAD")
    behind = sh("git", "rev-list", "--count", f"HEAD..{REMOTE}/{BRANCH}")
    dirty = bool(sh("git", "status", "--porcelain"))
    print(f"  git      : {ahead} ahead, {behind} behind {REMOTE}/{BRANCH}"
          f"{', WORKING TREE DIRTY' if dirty else ''}")
    if ahead != "0":
        problems.append(f"{ahead} commit(s) exist only on this Mac — push them")
    if behind != "0":
        problems.append(f"{behind} commit(s) exist only on {REMOTE} — pull them "
                        "BEFORE deploying, or you will deploy over someone's work")

    want = local_brain()
    live = running_brain()
    print(f"  brain    : local {want}   live {live or '(unknown)'}")
    if live is None:
        problems.append("could not read the running brain — is the railway CLI logged in?")
    elif live != want:
        problems.append(f"production is running {live}, this tree is {want} — "
                        "deploy (railway up --service worker) or find out whose code that is")

    src, served = source_extension(), served_extension()
    print(f"  extension: source {src}   served {served or '(unreachable)'}")
    if served and served != src:
        problems.append(f"users download {served} while the source is {src} — "
                        "run extension/build-zip.sh, commit, deploy the backend")

    print()
    if problems:
        print("  NOT IN SYNC:")
        for p in problems:
            print(f"    - {p}")
        return 1
    print("  IN SYNC — this Mac, GitHub and production are the same code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
