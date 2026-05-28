"""V7 scoped memory integration tests. Direct API checks always run;
HTTP checks skip if the router isn't wired. Exit 0 when no failures.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
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


def test_direct_api() -> None:
    from app.product.scoped_memory import (
        KIND_ALIAS, KIND_DO_NOT_TOUCH, KIND_PERSON, KIND_PREFERENCE,
        ScopedMemory,
    )
    a = ScopedMemory("acct-A", "device-1")
    b = ScopedMemory("acct-B", "device-1")

    a.write(kind=KIND_PERSON, key="Maya", value="maya@anticipy.ai",
            source="test", provenance="direct",
            extra={"gender": "f", "role": "ops"})
    b.write(kind=KIND_PERSON, key="Jordan", value="jordan@example.com",
            source="test", provenance="direct", extra={"gender": "m"})
    a_names = {it["key"] for it in a.read(kind=KIND_PERSON)}
    b_names = {it["key"] for it in b.read(kind=KIND_PERSON)}
    _assert("Maya" in a_names and "Maya" not in b_names,
            "isolation: acct A sees Maya, acct B does not",
            f"a={a_names} b={b_names}")
    _assert("Jordan" in b_names and "Jordan" not in a_names,
            "isolation: acct B sees Jordan, acct A does not",
            f"a={a_names} b={b_names}")
    _assert(a.path != b.path,
            "isolation: distinct storage paths",
            f"{a.path} vs {b.path}")

    her = a.resolve_alias("her")
    _assert(her is not None and her["key"] == "Maya",
            "pronoun her resolves to Maya when context unambiguous",
            f"got={her}")

    a.write(kind=KIND_PERSON, key="Priya", value="priya@example.com",
            source="test", provenance="direct", extra={"gender": "f"})
    _assert(a.resolve_alias("her") is None,
            "pronoun her returns None when ambiguous")

    her_ctx = a.resolve_alias("her", context_people=["Maya"])
    _assert(her_ctx is not None and her_ctx["key"] == "Maya",
            "pronoun her resolves via context_people narrowing",
            f"got={her_ctx}")

    a.write(kind=KIND_ALIAS, key="the boss", value="Maya",
            source="test", provenance="direct")
    via_alias = a.resolve_alias("the boss")
    _assert(via_alias is not None and via_alias["key"] == "Maya",
            "stored alias resolves to person", f"got={via_alias}")

    p = a.resolve_person("Maya")
    _assert(p is not None and p["value"] == "maya@anticipy.ai",
            "resolve_person finds Maya by name", f"got={p}")

    a.write(kind=KIND_DO_NOT_TOUCH, key="spouse_email",
            value="lisa@personal.example",
            source="test", provenance="direct")
    _assert(a.is_do_not_touch("lisa@personal.example"),
            "is_do_not_touch matches the blocked recipient")
    _assert(not a.is_do_not_touch("maya@anticipy.ai"),
            "is_do_not_touch does NOT match a non-blocked recipient")
    _assert(not b.is_do_not_touch("lisa@personal.example"),
            "do_not_touch is scoped per account")

    a.record_recipe(name="email-maya-friday",
                    steps=[{"open": "gmail.com"}, {"compose": "Maya"}],
                    surfaces=["chrome", "gmail"])
    recipe = a.recall_recipe("email-maya-friday")
    _assert(recipe is not None
            and recipe["extra"]["steps"][0]["open"] == "gmail.com",
            "recipe round-trips through record/recall",
            f"got={recipe}")

    a.record_action_outcome(action_id="act-1", status="succeeded",
                            surface="chrome", notes="draft created")
    a.record_action_outcome(action_id="act-1", status="re-sent",
                            surface="chrome", notes="user redid")
    outs = a.read(kind="action_outcome", active_only=True)
    _assert(len([o for o in outs if o["key"] == "act-1"]) == 2,
            "action outcomes accumulate (no dedupe)")

    a.write(kind=KIND_PREFERENCE, key="coffee", value="oat latte",
            source="test", provenance="direct")
    a.write(kind=KIND_PREFERENCE, key="coffee", value="americano",
            source="test", provenance="direct")
    coffees = [it for it in a.read(kind=KIND_PREFERENCE)
               if it["key"].lower() == "coffee"]
    _assert(len(coffees) == 1 and coffees[0]["value"] == "americano",
            "dedupe replaces prior value for same kind+key",
            f"coffees={coffees}")


def _http(path, body=None, timeout=4.0):
    if body is None:
        req = urllib.request.Request(f"{ENGINE_BASE}{path}", method="GET")
    else:
        req = urllib.request.Request(
            f"{ENGINE_BASE}{path}",
            data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8") or "{}")


def test_http_endpoints() -> None:
    try:
        s, b = _http(
            "/api/memory/diag?account_id=http-acct&device_id=http-dev")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _skip("http endpoints", "router not wired; restart required")
        else:
            _fail("http diag GET", f"HTTPError {exc.code}: {exc.reason}")
        return
    except Exception as exc:
        _skip("http endpoints", f"engine unreachable: {exc}")
        return
    if s != 200 or not b.get("ok"):
        _fail("http diag GET", f"status={s} body={b}"); return
    _ok("http diag GET returns ok")
    try:
        s, b = _http("/api/memory/provision", {
            "account_id": "http-acct", "device_id": "http-dev",
            "build_id": "test"})
        _assert(s == 200 and b.get("ok"), "http provision", f"{s} {b}")
        s, b = _http("/api/memory/seed", {
            "account_id": "http-acct", "device_id": "http-dev",
            "people": [{"name": "HttpMaya",
                        "email": "hm@example.com", "gender": "f"}],
            "aliases": [{"alias": "http boss", "target": "HttpMaya"}]})
        _assert(s == 200 and b.get("ok"), "http seed", f"{s} {b}")
        s, b = _http(
            "/api/memory/read?account_id=http-acct&device_id=http-dev"
            "&kind=person")
        items = b.get("items") or []
        _assert(s == 200 and any(it["key"] == "HttpMaya" for it in items),
                "http read returns seeded person", f"items={items}")
    except Exception as exc:
        _fail("http endpoints", f"unexpected: {exc}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="v7_scoped_mem_test_") as td:
        os.environ["ANTICIPY_V7_MEMORY_ROOT"] = td
        try:
            test_direct_api()
        except Exception as exc:
            _fail("direct api", f"crashed: {exc}")
        finally:
            os.environ.pop("ANTICIPY_V7_MEMORY_ROOT", None)

    test_http_endpoints()
    total = len(_PASSED) + len(_FAILED) + len(_SKIPPED)
    print()
    print(f"summary: {len(_PASSED)} passed, "
          f"{len(_FAILED)} failed, {len(_SKIPPED)} skipped "
          f"({total} total)")
    return 0 if not _FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
