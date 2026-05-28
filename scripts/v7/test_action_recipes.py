"""Tests for V7 per-user action recipe storage.

Covers record, recall ordering, increment_success, mark_failed
deprioritization, and prune. Uses ANTICIPY_V7_RECIPES_ROOT to isolate
storage. Exits 0 on full pass.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []


def _assert(cond: bool, name: str, reason: str = "") -> bool:
    if cond:
        _PASSED.append(name)
        print(f"PASS  {name}")
        return True
    _FAILED.append((name, reason))
    print(f"FAIL  {name}: {reason or 'assertion failed'}")
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="anticipy_v7_recipes_test_"))
    os.environ["ANTICIPY_V7_RECIPES_ROOT"] = str(tmp)
    try:
        from app.product.action_recipes import (
            DEPRIORITIZE_FAIL_COUNT, RecipeStore)
        store = RecipeStore("acct-test", "device-1")
        other = RecipeStore("acct-other", "device-1")
        surface = "mail.google.com/compose"
        intent = "email maya about friday meeting"

        recs = []
        for prim in (
            [{"primitive": "type", "args": {"text": "maya"}}],
            [{"primitive": "click", "args": {"target": "compose"}}],
            [{"primitive": "key", "args": {"key": "c"}}],
        ):
            recs.append(store.record(
                intent, surface,
                [{"primitive": "open", "args": {"url": surface}}, *prim],
                f"proof://run-{len(recs) + 1}"))
            time.sleep(0.01)
        rec1, rec2, rec3 = recs

        _assert(store.path.exists() and store.path.stat().st_size > 0,
                "record persists to disk", f"path={store.path}")
        _assert(len(store.all_recipes()) == 3,
                "three recipes on disk")
        _assert(len(other.all_recipes()) == 0,
                "cross-account isolation: other store empty")

        # Surface mismatch returns nothing.
        _assert(store.recall(intent, "evil.com/other", top_k=5) == [],
                "recall on unknown surface returns []")

        # Tied recipes: newest learned_at wins tie-break.
        recalled = store.recall(intent, surface, top_k=3)
        ids = [r.recipe_id for r in recalled]
        _assert(len(recalled) == 3, "recall returns three matches")
        _assert(ids[0] == rec3.recipe_id,
                "recall: newest first when tied", f"order={ids}")
        _assert(ids[-1] == rec1.recipe_id,
                "recall: oldest last when tied", f"order={ids}")

        # increment_success bumps and changes ranking.
        for _ in range(5):
            _assert(store.increment_success(rec1.recipe_id),
                    "increment_success True for known id")
        _assert(store.increment_success("nope") is False,
                "increment_success False for unknown id")
        bumped = [r for r in store.recall(intent, surface, top_k=3)
                  if r.recipe_id == rec1.recipe_id][0]
        _assert(bumped.success_count == 6,
                "success_count incremented five times above one",
                f"got={bumped.success_count}")
        _assert(store.recall(intent, surface, top_k=3)[0].recipe_id
                == rec1.recipe_id,
                "recall: rec1 promoted after success bumps")

        # mark_failed N times -> rec1 deprioritized to last.
        for i in range(DEPRIORITIZE_FAIL_COUNT):
            _assert(store.mark_failed(rec1.recipe_id, f"flaky {i}"),
                    f"mark_failed True for known id #{i}")
        _assert(store.mark_failed("nope", "n/a") is False,
                "mark_failed False for unknown id")
        after = store.recall(intent, surface, top_k=3)
        _assert(after[-1].recipe_id == rec1.recipe_id,
                "recall: rec1 deprioritized after recent failures",
                f"order={[r.recipe_id for r in after]}")

        # Persistence across instances.
        reloaded = RecipeStore("acct-test", "device-1")
        on_disk = {r.recipe_id: r for r in reloaded.all_recipes()}
        _assert(len(on_disk[rec1.recipe_id].failed_uses)
                == DEPRIORITIZE_FAIL_COUNT,
                "failed_uses persisted on disk")

        # prune: force one recipe stale; only it gets removed.
        stale = store.record("stale intent", surface,
                             [{"primitive": "open",
                               "args": {"url": surface}}],
                             "proof://stale")
        all_recipes = reloaded.all_recipes()
        for r in all_recipes:
            if r.recipe_id == stale.recipe_id:
                r.learned_at = time.time() - (400 * 86400)
        reloaded._write_all(all_recipes)
        removed = reloaded.prune(older_than_days=180)
        _assert(removed >= 1, "prune removes stale recipe",
                f"removed={removed}")
        keep_ids = {r.recipe_id for r in reloaded.all_recipes()}
        _assert(stale.recipe_id not in keep_ids,
                "prune dropped the stale recipe specifically")
        _assert(rec1.recipe_id in keep_ids,
                "prune keeps high-success recipes despite recent fails")
        _assert(rec2.recipe_id in keep_ids and rec3.recipe_id in keep_ids,
                "prune keeps the other normal recipes")
        _assert(store.recall(intent, surface, top_k=0) == [],
                "recall with top_k=0 returns []")
    finally:
        os.environ.pop("ANTICIPY_V7_RECIPES_ROOT", None)
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(f"passed={len(_PASSED)} failed={len(_FAILED)}")
    if _FAILED:
        for name, reason in _FAILED:
            print(f"  FAIL {name}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
