"""V7 dossier-active loader test. Seeds Maya/Marcus + payroll DNT under
a temp root; asserts people/pronoun/block/context/refresh. HTTP block
runs only if a live engine is reachable. Exit 0 on full pass.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

ENGINE_BASE = os.environ.get(
    "ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731").rstrip("/")

_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []
_SKIPPED: list[tuple[str, str]] = []


def _ok(n): _PASSED.append(n); print(f"PASS  {n}")
def _fail(n, r): _FAILED.append((n, r)); print(f"FAIL  {n}: {r}")
def _skip(n, r): _SKIPPED.append((n, r)); print(f"SKIP  {n}: {r}")


def _assert(cond, name, reason=""):
    if cond:
        _ok(name); return True
    _fail(name, reason or "assertion failed"); return False


def _seed(root: Path, account: str) -> Path:
    target = root / account
    target.mkdir(parents=True, exist_ok=True)
    now = time.time()
    payload = {
        "people": [
            {"name": "Maya", "role": "ops partner",
             "email": "maya@anticipy.ai", "pronouns": "she/her",
             "aliases": ["the boss"], "last_mentioned": now},
            {"name": "Marcus", "role": "finance",
             "email": "marcus@anticipy.ai", "pronouns": "he/him",
             "last_mentioned": now - 600},
        ],
        "preferences": {"comms": "WhatsApp over SMS"},
        "do_not_touch": [{"pattern": "payroll",
                          "reason": "never edit payroll sheets"}],
        "recent_topics": [{"topic": "Friday demo", "ts": now}],
    }
    path = target / "dossier.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_direct() -> None:
    from app.product.dossier_active_loader import DossierLoader
    with tempfile.TemporaryDirectory(prefix="v7_dossier_test_") as td:
        root = Path(td)
        os.environ["ANTICIPY_V7_DOSSIER_ROOT"] = str(root)
        try:
            _seed(root, "acct-test")
            loader = DossierLoader("acct-test", "device-1")

            people = loader.people()
            _assert(len(people) == 2, "people() returns 2",
                    f"got {[p.name for p in people]}")
            names = {p.name for p in people}
            _assert(names == {"Maya", "Marcus"},
                    "people() includes Maya and Marcus", f"got={names}")

            blocked, rule = loader.is_blocked("edit payroll spreadsheet")
            _assert(blocked and rule is not None,
                    "do_not_touch blocks 'edit payroll spreadsheet'")
            ok2, _ = loader.is_blocked("send draft to Maya")
            _assert(not ok2,
                    "do_not_touch does NOT block a benign task")

            pmap = loader.pronoun_map()
            _assert(pmap.get("her") == "Maya",
                    "pronoun_map 'her' -> Maya (most recent female)",
                    f"got={pmap}")
            _assert(pmap.get("him") == "Marcus",
                    "pronoun_map 'him' -> Marcus", f"got={pmap}")

            block = loader.as_context_block(max_chars=2000)
            _assert("Maya" in block and "Marcus" in block,
                    "context block includes both people")
            _assert("DO NOT TOUCH" in block and "payroll" in block,
                    "context block includes do_not_touch section")
            _assert("WhatsApp" in block,
                    "context block includes preferences")
            _assert(len(block) <= 2000, "context block honours max_chars",
                    f"len={len(block)}")

            path = root / "acct-test" / "dossier.json"
            data = json.loads(path.read_text())
            data["people"].append({"name": "Priya", "pronouns": "she/her",
                                   "last_mentioned": time.time() + 10})
            path.write_text(json.dumps(data), encoding="utf-8")
            loader.refresh()
            _assert(len(loader.people()) == 3,
                    "refresh() picks up the new person on disk")
            _assert(loader.pronoun_map().get("her") == "Priya",
                    "pronoun_map updates after refresh",
                    f"got={loader.pronoun_map()}")
        finally:
            os.environ.pop("ANTICIPY_V7_DOSSIER_ROOT", None)


def test_http() -> None:
    try:
        url = f"{ENGINE_BASE}/api/dossier/context?account_id=ping&max_chars=200"
        with urllib.request.urlopen(url, timeout=4) as r:
            body = json.loads(r.read().decode("utf-8") or "{}")
            _assert(r.status == 200 and body.get("ok"),
                    "http context GET returns ok", f"body={body}")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _skip("http endpoints", "router not wired; restart engine")
        else:
            _fail("http context GET", f"HTTPError {exc.code}: {exc.reason}")
    except Exception as exc:
        _skip("http endpoints", f"engine unreachable: {exc}")


def main() -> int:
    try:
        test_direct()
    except Exception as exc:
        _fail("direct api", f"crashed: {exc}")
    test_http()
    print()
    print(f"summary: {len(_PASSED)} passed, "
          f"{len(_FAILED)} failed, {len(_SKIPPED)} skipped")
    return 0 if not _FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
