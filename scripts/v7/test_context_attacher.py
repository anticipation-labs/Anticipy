"""V7 context attacher tests. Stubs collaborators, asserts attach()
shape, do_not_touch population, prompt block budget, and missing-dep
safety. Exits 0 on success, 1 on any assertion failure."""

from __future__ import annotations

import sys
from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[2] / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []


def _ok(n): _PASSED.append(n); print(f"PASS  {n}")
def _fail(n, r): _FAILED.append((n, r)); print(f"FAIL  {n}: {r}")


def _assert(cond, n, r=""):
    if cond: _ok(n); return True
    _fail(n, r or "assertion failed"); return False


_MAYA = {"key": "Maya", "value": "maya@anticipy.ai",
         "extra": {"email": "maya@anticipy.ai", "role": "ops"}}
_MEM_BAG = {
    "preference": [{"kind": "preference", "key": "tone",
                    "value": "warm", "timestamp": 100.0}],
    "accepted_action": [{"kind": "accepted_action", "key": "act-7",
                         "value": "ok", "timestamp": 200.0}],
    "learned_recipe": [{"kind": "learned_recipe", "key": "draft",
                        "value": "saved", "timestamp": 150.0}]}
_EXPECTED_KEYS = {"dossier_context", "relevant_memories", "resolved_people",
                  "recent_surface_snapshots", "learned_recipes",
                  "do_not_touch_warnings", "action_history_summary"}


class _StubMemory:
    def __init__(self, *_a, **_k): pass
    def read(self, *, kind=None, active_only=True, key=None): return _MEM_BAG.get(kind, [])
    def resolve_person(self, h): return _MAYA if h.lower() == "maya" else None
    def resolve_alias(self, *_a, **_k): return None
    def is_do_not_touch(self, n): n = (n or "").lower(); return "spouse" in n or "personal.example" in n
class _StubRecipes:
    def __init__(self, *_a, **_k): pass
    def recall(self, summary, surface, top_k=3):
        return [{"recipe_id": "rec-1", "intent_summary": "email someone",
                 "surface_key": "https://mail.google.com",
                 "primitives": [{"open": "gmail"}], "success_count": 4}]
class _StubDossier:
    def __init__(self, *_a, **_k): pass
    def as_context_block(self): return "Omar works ops at Anticipy. Partner Maya. Spouse private."
class _StubPeople:
    def __init__(self, *_a, **_k): pass
    def resolve(self, ref): return _MAYA if ref.lower() == "maya" else None


def _install(stubs=True):
    import app.product.context_attacher as m
    m._ScopedMemory = _StubMemory if stubs else None  # type: ignore[attr-defined]
    m._RecipeStore = _StubRecipes if stubs else None  # type: ignore[attr-defined]
    m._DossierLoader = _StubDossier if stubs else None  # type: ignore[attr-defined]
    m._PersonResolver = _StubPeople if stubs else None  # type: ignore[attr-defined]


def test_attach_with_stubs():
    _install(True)
    from app.product.context_attacher import ContextAttacher
    intent = {"summary": "email Maya about Friday",
              "target_person_refs": ["Maya", "spouse"]}
    history = [
        {"primitive": "open", "ok": True, "why": "load gmail",
         "surface": {"url": "https://google.com", "title": "Google"}},
        {"primitive": "click", "ok": False, "why": "missed", "error": "404"}]
    out = ContextAttacher("test-acct", "test-dev").attach(intent,
        {"url": "https://mail.google.com/inbox", "title": "Gmail"}, history)
    _assert(set(out.keys()) == _EXPECTED_KEYS,
            "attach returns every expected key", f"got {sorted(out.keys())}")
    _assert("Omar works ops" in out["dossier_context"],
            "dossier_context populated", out["dossier_context"][:80])
    _assert(out["relevant_memories"] and any(
            "preference" in m for m in out["relevant_memories"]),
            "relevant_memories includes preference",
            str(out["relevant_memories"]))
    _assert("Maya" in out["resolved_people"]
            and out["resolved_people"]["Maya"]["key"] == "Maya",
            "resolved_people resolves Maya", str(out["resolved_people"]))
    _assert(out["recent_surface_snapshots"]
            and out["recent_surface_snapshots"][0]["when"] == "current",
            "recent_surface_snapshots has current",
            str(out["recent_surface_snapshots"]))
    _assert(len(out["learned_recipes"]) >= 1,
            "learned_recipes populated", str(out["learned_recipes"]))
    _assert(any("spouse" in w for w in out["do_not_touch_warnings"]),
            "do_not_touch fires on spouse overlap",
            str(out["do_not_touch_warnings"]))
    _assert("click [FAIL]" in out["action_history_summary"]
            or "open [ok]" in out["action_history_summary"],
            "action_history_summary captures step results",
            out["action_history_summary"])


def test_prompt_block_format():
    _install(True)
    from app.product.context_attacher import ContextAttacher
    out = ContextAttacher("test-acct", "test-dev").attach(
        {"summary": "email spouse private", "target_person_refs": ["spouse"]},
        {"url": "https://mail.google.com"}, [])
    block = ContextAttacher.as_planner_prompt_block(out, max_chars=2000)
    _assert(len(block) <= 2000 and block.startswith("## DO NOT TOUCH WARNINGS"),
            "prompt block fits and starts with DO NOT TOUCH",
            f"len={len(block)} head={block[:80]!r}")
    tight = ContextAttacher.as_planner_prompt_block(out, max_chars=200)
    _assert(len(tight) <= 200 and "DO NOT TOUCH" in tight,
            "prompt block honors tight budget; dnt survives",
            f"len={len(tight)} block={tight!r}")


def test_missing_deps_safe():
    _install(False)
    from app.product.context_attacher import ContextAttacher
    out = ContextAttacher("acct", "dev").attach(
        "email someone", {"url": "https://x.test"}, [])
    _assert(set(out.keys()) == _EXPECTED_KEYS,
            "shape stable with all deps missing", f"got {sorted(out.keys())}")
    _assert(out["dossier_context"] == "" and out["relevant_memories"] == []
            and out["resolved_people"] == {}
            and out["do_not_touch_warnings"] == [],
            "fields default to empty when deps missing")
    block = ContextAttacher.as_planner_prompt_block(out, max_chars=500)
    _assert(isinstance(block, str),
            "block returns string on empty ctx", type(block).__name__)


def main():
    for fn in (test_attach_with_stubs, test_prompt_block_format,
               test_missing_deps_safe):
        try: fn()
        except Exception as exc: _fail(fn.__name__, f"crashed: {exc}")
    print(f"\nsummary: {len(_PASSED)} passed, {len(_FAILED)} failed "
          f"({len(_PASSED) + len(_FAILED)} total)")
    return 0 if not _FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
