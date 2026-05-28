"""V7 memory provenance enforcer tests. Exits 0 when no failures."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []

def _ok(n): _PASSED.append(n); print(f"PASS  {n}")
def _fail(n, r): _FAILED.append((n, r)); print(f"FAIL  {n}: {r}")

def _assert(cond, name, reason=""):
    if cond:
        _ok(name); return True
    _fail(name, reason or "assertion failed"); return False


def test_validate_item() -> None:
    from app.product.memory_provenance import validate_item
    full = {"account_id": "a", "device_id": "d", "source": "onboarding",
            "timestamp": "2026-05-26T12:00:00.000Z", "confidence": 0.9,
            "kind": "person", "active": True, "provenance": "ic-1"}
    v = validate_item(full)
    _assert(v["valid"] and not v["missing"] and not v["errors"],
            "validate_item: pass with all fields", str(v))
    bm = dict(full); bm.pop("source")
    v = validate_item(bm)
    _assert(not v["valid"] and "source" in v["missing"],
            "validate_item: fail with missing source", str(v))
    bc = dict(full); bc["confidence"] = 2.0
    v = validate_item(bc)
    _assert(not v["valid"]
            and any("confidence" in e for e in v["errors"]),
            "validate_item: fail with confidence=2.0", str(v))
    bs = dict(full); bs["source"] = "made-up"
    v = validate_item(bs)
    _assert(not v["valid"]
            and any("source must be one of" in e for e in v["errors"]),
            "validate_item: fail with non-enum source", str(v))
    ba = dict(full); ba["active"] = "yes"
    v = validate_item(ba)
    _assert(not v["valid"]
            and any("active must be bool" in e for e in v["errors"]),
            "validate_item: fail when active is not bool", str(v))


def test_normalize_item() -> None:
    from app.product.memory_provenance import (normalize_item,
                                               validate_item)
    base = {"account_id": "a", "device_id": "d", "kind": "fact",
            "key": "x", "value": "y", "source": "onboarding",
            "provenance": "ic-1"}
    out = normalize_item(dict(base))
    _assert(bool(out.get("timestamp")),
            "normalize_item: missing timestamp filled with now")
    _assert(out["active"] is True,
            "normalize_item: missing active filled True")
    _assert(abs(float(out["confidence"]) - 0.7) < 1e-6,
            "normalize_item: missing confidence defaults to 0.7")
    out2 = normalize_item(dict(base), defaults={"confidence": 0.95})
    _assert(abs(float(out2["confidence"]) - 0.95) < 1e-6,
            "normalize_item: defaults override confidence")
    raised = False
    try:
        normalize_item({"device_id": "d", "kind": "fact",
                        "source": "onboarding", "provenance": "p"})
    except ValueError:
        raised = True
    _assert(raised, "normalize_item: missing account_id raises")
    _assert(validate_item(out)["valid"],
            "normalize_item: result passes validate_item")


class _FakeScoped:
    """In-memory ScopedMemory stand-in matching the real signature."""

    def __init__(self, account_id, device_id):
        self.account_id = account_id; self.device_id = device_id
        self._items: list[dict] = []; self.path = None

    def write(self, *, kind, key, value, source, provenance,
              confidence, extra=None, dedupe=True):
        item = {"item_id": f"fake-{len(self._items)+1}",
                "account_id": self.account_id,
                "device_id": self.device_id, "kind": kind, "key": key,
                "value": value, "source": source, "provenance": provenance,
                "confidence": float(confidence), "active": True,
                "extra": dict(extra or {})}
        self._items.append(item)
        return item

    def read(self, *, kind=None, key=None, active_only=True):
        out = []
        for it in self._items:
            if active_only and not it.get("active"):
                continue
            if kind and it["kind"] != kind:
                continue
            if key and it["key"].lower() != key.lower():
                continue
            out.append(dict(it))
        return out


def test_provenance_wrapper() -> None:
    from app.product.memory_provenance import ProvenanceWrapper
    with tempfile.TemporaryDirectory(prefix="v7_prov_err_") as td:
        errs_path = Path(td) / "errors.jsonl"
        os.environ["ANTICIPY_V7_MEMORY_ERRORS_PATH"] = str(errs_path)
        try:
            inner = _FakeScoped("acct-a", "dev-1")
            wrap = ProvenanceWrapper(inner)
            res = wrap.write(kind="person", key="Maya", value="x",
                             source="not-an-enum", provenance="seed",
                             confidence=0.8)
            _assert(res is None and len(inner._items) == 0,
                    "ProvenanceWrapper: invalid write not stored",
                    f"res={res} items={inner._items}")
            _assert(errs_path.exists()
                    and errs_path.read_text().strip() != "",
                    "ProvenanceWrapper: invalid write logged")
            res2 = wrap.write(kind="person", key="Maya",
                              value="maya@anticipy.ai",
                              source="onboarding",
                              provenance="ic-1", confidence=0.9)
            _assert(res2 is not None and len(inner._items) == 1,
                    "ProvenanceWrapper: valid write reaches inner",
                    f"res2={res2}")
            rec = json.loads(errs_path.read_text().strip().splitlines()[-1])
            _assert("source must be one of" in " ".join(rec["errors"]),
                    "ProvenanceWrapper: error log captures reason")
        finally:
            os.environ.pop("ANTICIPY_V7_MEMORY_ERRORS_PATH", None)


def test_active_flag_enforcer() -> None:
    from app.product.scoped_memory import KIND_PERSON, ScopedMemory
    from app.product.memory_provenance import ActiveFlagEnforcer
    with tempfile.TemporaryDirectory(prefix="v7_active_") as td:
        os.environ["ANTICIPY_V7_MEMORY_ROOT"] = td
        try:
            inner = ScopedMemory("acct-a", "dev-1")
            m1 = inner.write(kind=KIND_PERSON, key="Maya",
                             value="maya@anticipy.ai", source="test",
                             provenance="direct", confidence=1.0)
            inner.write(kind=KIND_PERSON, key="Priya",
                        value="priya@example.com", source="test",
                        provenance="direct", confidence=1.0)
            enf = ActiveFlagEnforcer(inner)
            _assert(len(enf.read_active_only(kind=KIND_PERSON)) == 2,
                    "ActiveFlagEnforcer: read returns active items")
            _assert(enf.deactivate(m1.item_id),
                    "ActiveFlagEnforcer: deactivate returns True",
                    f"id={m1.item_id}")
            keys = {it["key"] for it
                    in enf.read_active_only(kind=KIND_PERSON)}
            _assert(keys == {"Priya"},
                    "ActiveFlagEnforcer: deactivated item hidden",
                    f"keys={keys}")
            allk = {it["key"] for it
                    in enf.read_all_including_inactive(kind=KIND_PERSON)}
            _assert(allk == {"Maya", "Priya"},
                    "ActiveFlagEnforcer: read_all returns inactive",
                    f"keys={allk}")
            enf.reactivate(m1.item_id)
            again = {it["key"] for it
                     in enf.read_active_only(kind=KIND_PERSON)}
            _assert(again == {"Maya", "Priya"},
                    "ActiveFlagEnforcer: reactivate restores item",
                    f"keys={again}")
        finally:
            os.environ.pop("ANTICIPY_V7_MEMORY_ROOT", None)


def main() -> int:
    for fn in (test_validate_item, test_normalize_item,
               test_provenance_wrapper, test_active_flag_enforcer):
        try:
            fn()
        except Exception as exc:
            _fail(fn.__name__, f"crashed: {exc}")
    total = len(_PASSED) + len(_FAILED)
    print(f"\nsummary: {len(_PASSED)} passed, {len(_FAILED)} failed "
          f"({total} total)")
    return 0 if not _FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
