"""V7 person resolver tests. Direct API + HTTP smoke."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[2] / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

ENGINE_BASE = os.environ.get(
    "ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731").rstrip("/")

_PASS: list[str] = []
_FAIL: list[tuple[str, str]] = []
_SKIP: list[tuple[str, str]] = []


def _ok(n): _PASS.append(n); print(f"PASS  {n}")
def _fail(n, r): _FAIL.append((n, r)); print(f"FAIL  {n}: {r}")
def _skip(n, r): _SKIP.append((n, r)); print(f"SKIP  {n}: {r}")


def _assert(cond, name, reason=""):
    if cond:
        _ok(name); return True
    _fail(name, reason or "assertion failed"); return False


def _seed(acct="ptest", dev="dev1"):
    from app.product.scoped_memory import KIND_PERSON, ScopedMemory
    scope = ScopedMemory(acct, dev)
    for name, email, gender, role in [
        ("Maya Chen", "maya.chen@example.com", "f", "investor"),
        ("Maya Patel", "maya.patel@example.com", "f", "designer"),
        ("Marcus Lee", "marcus@example.com", "m", "engineer"),
    ]:
        scope.write(kind=KIND_PERSON, key=name, value=email,
                    source="test", provenance="seed",
                    extra={"email": email, "gender": gender,
                           "role": role})


def test_direct_api():
    from app.product.person_resolver import PersonResolver
    _seed()
    pr = PersonResolver("ptest", "dev1")

    res = pr.resolve("Marcus")
    _assert(res.person and res.person.name == "Marcus Lee"
            and res.confidence >= 0.9,
            "resolve('Marcus') -> Marcus Lee with high confidence",
            f"got={res.to_dict()}")

    res = pr.resolve("Maya")
    _assert(res.person is None
            and {a.name for a in res.alternatives}
                == {"Maya Chen", "Maya Patel"},
            "resolve('Maya') no context -> ambiguous with both Mayas",
            f"got={res.to_dict()}")
    _assert("ambiguous" in (res.reason or "").lower(),
            "ambiguous reason mentions 'ambiguous'",
            f"reason={res.reason}")

    res = pr.resolve(
        "Maya",
        context_text="I was just talking to Maya Patel about the rebrand")
    _assert(res.person and res.person.name == "Maya Patel"
            and res.confidence >= 0.9,
            "resolve('Maya') with Patel context -> Maya Patel",
            f"got={res.to_dict()}")

    res = pr.resolve(
        "her",
        context_text=("Earlier Maya Chen mentioned the Series A timeline."))
    _assert(res.person and res.person.name == "Maya Chen"
            and res.confidence >= 0.85,
            "resolve('her') with Maya Chen context -> Maya Chen",
            f"got={res.to_dict()}")

    res = pr.resolve("the investor")
    _assert(res.person and res.person.name == "Maya Chen"
            and res.confidence >= 0.85,
            "resolve('the investor') -> Maya Chen via role",
            f"got={res.to_dict()}")

    res = pr.resolve("maya.patel@example.com")
    _assert(res.person and res.person.name == "Maya Patel"
            and res.confidence >= 0.99,
            "resolve(email) -> exact email match",
            f"got={res.to_dict()}")

    res = pr.disambiguate("Maya", "Maya Chen")
    _assert(res.person and res.person.name == "Maya Chen",
            "disambiguate('Maya', 'Maya Chen') records choice",
            f"got={res.to_dict()}")

    pr2 = PersonResolver("ptest", "dev1")
    res = pr2.resolve("Maya")
    _assert(res.person and res.person.name == "Maya Chen",
            "stored alias survives reload (learned alias)",
            f"got={res.to_dict()}")


def _http(method, path, body=None, timeout=4.0):
    headers = {"Content-Type": "application/json"} if body else {}
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(f"{ENGINE_BASE}{path}", data=data,
                                 method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8") or "{}")


def test_http_endpoints():
    try:
        status, body = _http("POST", "/api/person/resolve",
                             {"account_id": "ptest-http",
                              "device_id": "dev1",
                              "reference": "Marcus"})
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _skip("http endpoints",
                  "router not wired; engine restart required")
            return
        _fail("http resolve POST",
              f"HTTPError {exc.code}: {exc.reason}")
        return
    except Exception as exc:
        _skip("http endpoints", f"engine unreachable: {exc}")
        return
    if status != 200 or not body.get("ok"):
        _fail("http resolve POST", f"status={status} body={body}")
        return
    _ok("http resolve POST returns ok")

    try:
        s, _ = _http("POST", "/api/memory/seed", {
            "account_id": "ptest-http", "device_id": "dev1",
            "people": [
                {"name": "Marcus Lee", "email": "marcus@example.com",
                 "gender": "m", "role": "engineer"},
                {"name": "Maya Chen", "email": "mc@example.com",
                 "gender": "f", "role": "investor"},
                {"name": "Maya Patel", "email": "mp@example.com",
                 "gender": "f", "role": "designer"},
            ]})
        _assert(s == 200, "http seed for HTTP resolver", f"status={s}")
        s, b = _http("POST", "/api/person/resolve", {
            "account_id": "ptest-http", "device_id": "dev1",
            "reference": "Marcus"})
        res = (b or {}).get("resolution") or {}
        person = res.get("person") or {}
        _assert(s == 200 and person.get("name") == "Marcus Lee"
                and float(res.get("confidence") or 0) >= 0.9,
                "http resolve returns Marcus Lee", f"body={b}")
        s, b = _http("POST", "/api/person/resolve", {
            "account_id": "ptest-http", "device_id": "dev1",
            "reference": "Maya"})
        res = (b or {}).get("resolution") or {}
        _assert(s == 200 and res.get("person") is None
                and len(res.get("alternatives") or []) >= 2,
                "http resolve('Maya') returns ambiguous", f"body={b}")
        s, b = _http("POST", "/api/person/disambiguate", {
            "account_id": "ptest-http", "device_id": "dev1",
            "reference": "Maya", "person_id": "Maya Chen"})
        res = (b or {}).get("resolution") or {}
        person = res.get("person") or {}
        _assert(s == 200 and person.get("name") == "Maya Chen",
                "http disambiguate records choice", f"body={b}")
    except Exception as exc:
        _fail("http endpoints", f"unexpected: {exc}")


def main():
    with tempfile.TemporaryDirectory(prefix="v7_person_test_") as td:
        os.environ["ANTICIPY_V7_MEMORY_ROOT"] = td
        try:
            test_direct_api()
        except Exception as exc:
            _fail("direct api", f"crashed: {exc}")
        finally:
            os.environ.pop("ANTICIPY_V7_MEMORY_ROOT", None)

    test_http_endpoints()
    total = len(_PASS) + len(_FAIL) + len(_SKIP)
    print()
    print(f"summary: {len(_PASS)} passed, {len(_FAIL)} failed, "
          f"{len(_SKIP)} skipped ({total} total)")
    return 0 if not _FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
