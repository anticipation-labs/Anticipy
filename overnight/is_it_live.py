#!/usr/bin/env python3
"""Is what I fixed actually what people are running?

This exists because "fixed" has repeatedly meant "fixed on my screen". Twice
in one day: the setup page still told strangers to open a folder that does
not exist, hours after the file was corrected; and the extension the server
handed out said 0.8.2 while the source said 0.8.2 — with completely different
code inside, which no version check could ever catch.

So this compares LIVE REALITY against the source tree, and needs no trust in
anybody's report. Run it. It prints what is true.

    python3 overnight/is_it_live.py
"""
import json, os, re, subprocess, sys, tempfile, urllib.request, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The credentials were always next to the gate; nothing loaded them, so
# BASE below silently fell back to the hardcoded default even when
# .env.local named a different backend. Explicit environment still wins.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(ROOT)
BASE = os.environ.get("ANTICIPY_BACKEND_URL",
                      "https://backend-production-61e0a.up.railway.app")

OK, BAD = "PASS", "FAIL"
rows = []


def check(name, good, detail=""):
    rows.append((OK if good else BAD, name, detail))
    return good


def fetch(path, binary=False):
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as r:
        return r.read() if binary else r.read().decode("utf-8", "replace")


# 1. Is anything there at all?
try:
    fetch("/api/health")
    check("the backend is answering", True, BASE)
except Exception as e:
    check("the backend is answering", False, str(e)[:80])
    print("\n  nothing else can be checked while the backend is down.\n")
    sys.exit(1)

# 2. The page a stranger reads must name a folder that exists.
try:
    page = fetch("/setup.html")
    names = set(re.findall(r"anticipy-[a-z-]+-extension", page))
    zip_name = "anticipy-claude-version-extension"
    wrong = {n for n in names if n != zip_name}
    check("the setup page only names the folder the download produces",
          not wrong, f"also names {sorted(wrong)}" if wrong else f"{zip_name}")
except Exception as e:
    check("the setup page is readable", False, str(e)[:80])

# 3. The served extension must BE the source, not merely claim its version.
src_manifest = json.load(open(os.path.join(ROOT, "extension", "manifest.json")))
src_version = src_manifest["version"]
try:
    blob = fetch(f"/{zip_name}.zip", binary=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as fh:
        fh.write(blob); tmp = fh.name
    with zipfile.ZipFile(tmp) as z:
        names = z.namelist()
        man = next(n for n in names if n.endswith("manifest.json"))
        live_version = json.loads(z.read(man))["version"]
        loop = next(n for n in names if n.endswith("agent_loop.js"))
        live_loop = z.read(loop).decode("utf-8", "replace")
    os.unlink(tmp)

    check("the served extension's version matches source",
          live_version == src_version, f"served {live_version}, source {src_version}")

    # The version alone is not evidence. Compare the actual bytes of the file
    # that does the work -- this is the check that would have caught 0.8.2
    # being served with none of that day's code in it.
    src_loop = open(os.path.join(ROOT, "extension", "agent_loop.js")).read()
    same = live_loop.strip() == src_loop.strip()
    check("the served extension IS the source, byte for byte", same,
          "identical" if same else
          f"differs: served {len(live_loop)} chars, source {len(src_loop)}")
except Exception as e:
    check("the served extension is readable", False, str(e)[:80])

# 4. What his own Chrome is really running -- the copy Chrome reads, not a zip.
try:
    import glob
    chrome_base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    installed = ""
    for prefs in glob.glob(os.path.join(chrome_base, "*", "Secure Preferences")):
        try:
            d = json.load(open(prefs))
        except Exception:
            continue
        for _id, e in (((d.get("extensions") or {}).get("settings")) or {}).items():
            if not isinstance(e, dict):
                continue
            p = e.get("path") or ""
            n = ((e.get("manifest") or {}).get("name") or "")
            if "anticipy" in (n + p).lower() and os.path.isdir(p):
                installed = p
                break
        if installed:
            break
    if installed:
        chrome_loop = open(os.path.join(installed, "agent_loop.js")).read()
        same = chrome_loop.strip() == src_loop.strip()
        check("YOUR Chrome is running the current code", same,
              installed if same else f"{installed} is behind — run sh extension/sync-to-chrome.sh")
    else:
        rows.append(("....", "your Chrome install was not found (not loaded unpacked?)", ""))
except Exception as e:
    rows.append(("....", "could not inspect your Chrome", str(e)[:60]))

# 5. Nothing uncommitted pretending to be shipped.
try:
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    check("no uncommitted changes masquerading as shipped",
          not dirty, f"{len(dirty.splitlines())} file(s) uncommitted" if dirty else "clean")
except Exception:
    pass

width = max(len(r[1]) for r in rows) + 2
print(f"\n  IS IT ACTUALLY LIVE?   {BASE}")
print("  " + "-" * (width + 26))
for status, name, detail in rows:
    print(f"  [{status}] {name.ljust(width)} {detail}")
print("  " + "-" * (width + 26))
failed = [r for r in rows if r[0] == BAD]
print(f"  {'EVERYTHING SHIPPED' if not failed else str(len(failed)) + ' THING(S) NOT ACTUALLY LIVE'}\n")
sys.exit(1 if failed else 0)
