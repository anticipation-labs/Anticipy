"""Learned-recipe cache (Pillar 4) — the cost-bend lever.

The cardinal sin was HAND-AUTHORED per-site recipes (an Amazon-return script). This is the
opposite: nothing is authored. A recipe is *discovered* — the first time the agent completes a
task and the judge verifies it, we record the action-trace keyed by (domain, normalized task).
The next time the SAME task runs on the SAME site, we REPLAY that trace with ZERO planner/actor
LLM calls (the expensive part), and only spend on the final read-back answer. The moment the page
diverges from the recording (an element we recorded is gone), we self-heal: abandon the replay and
fall back to the full live reasoning loop. So replay is a pure speed/cost optimization that can
never make the agent wrong — a bad replay just falls back to thinking.

Cost math: a multi-step navigation task that cost N cheap planner calls + 1 smart plan call the
first time costs ~1 cheap call (the answer read-back) on every repeat. That is the "$0 on repeats"
term in the 1/10th-cost stack, and it is the term that bends the curve DOWN over time as the
user's recurring tasks accumulate recipes — exactly what a frontier-per-step agent cannot do.

Recipes store STABLE element descriptors (role + visible name), never the volatile per-observe
index, so a replay re-resolves each step against the live DOM.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import time
import urllib.parse
from typing import List, Optional

# Default ON. The whole point is the compounding flywheel; flip to 0 to measure the no-cache cost.
RECIPE_CACHE = (os.environ.get("ANTICIPY_RECIPE_CACHE", "1") or "").strip().lower() not in ("0", "false", "no", "off")
_DIR = pathlib.Path(
    os.environ.get("ANTICIPY_RECIPE_DIR", str(pathlib.Path.home() / ".anticipy" / "recipes")))
# A replay step whose action moved us forward but whose target can't be re-resolved on the live
# page is a divergence: the recipe is stale. We never force a stale recipe.
_MAX_RECIPE_STEPS = 24


def _domain(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url or "").netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _norm_task(task: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", (task or "").lower())
    return re.sub(r"\s+", " ", t).strip()


def recipe_key(task: str, url: str) -> str:
    """Stable key for (site, task). Same task on the same domain -> same key."""
    raw = _domain(url) + "|" + _norm_task(task)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def descriptor(el: dict) -> dict:
    """The STABLE identity of an element across runs: role + visible name (normalized).
    Never the index (which is recomputed every observe)."""
    return {
        "role": str(el.get("role") or "").strip().lower(),
        "name": re.sub(r"\s+", " ", str(el.get("name") or "").strip().lower())[:80],
    }


def match_index(desc: dict, els: List[dict]) -> Optional[int]:
    """Re-resolve a recorded descriptor to a live element's index. Exact role+name first,
    then name-equal (any role), then name-startswith/contains. Returns None on divergence."""
    if not desc:
        return None
    want_role = desc.get("role") or ""
    want_name = desc.get("name") or ""
    if not want_name:
        return None

    def nm(e):
        return re.sub(r"\s+", " ", str(e.get("name") or "").strip().lower())[:80]

    for e in els:                                   # exact role + name
        if nm(e) == want_name and str(e.get("role") or "").strip().lower() == want_role:
            return e.get("idx")
    for e in els:                                   # exact name, any role
        if nm(e) == want_name:
            return e.get("idx")
    for e in els:                                   # prefix
        if nm(e).startswith(want_name) or want_name.startswith(nm(e)) and nm(e):
            return e.get("idx")
    for e in els:                                   # contains
        if want_name in nm(e) or (nm(e) and nm(e) in want_name):
            return e.get("idx")
    return None


class RecipeStore:
    """Tiny on-disk JSON store. One file per key under ANTICIPY_RECIPE_DIR."""

    def __init__(self, directory: Optional[pathlib.Path] = None) -> None:
        self.dir = pathlib.Path(directory) if directory else _DIR

    def _path(self, key: str) -> pathlib.Path:
        return self.dir / f"{key}.json"

    def get(self, key: str) -> Optional[dict]:
        try:
            p = self._path(key)
            if not p.exists():
                return None
            rec = json.loads(p.read_text())
            steps = rec.get("steps") or []
            if not steps or len(steps) > _MAX_RECIPE_STEPS:
                return None
            return rec
        except Exception:
            return None

    def save(self, key: str, task: str, url: str, steps: List[dict]) -> bool:
        """Persist a discovered, judge-verified trace. Steps that carry no usable descriptor
        (and aren't url-only navigates/scrolls) are dropped — a recipe must be replayable."""
        try:
            clean: List[dict] = []
            for s in steps or []:
                act = (s or {}).get("action") or {}
                a = act.get("action")
                if a in ("navigate", "scroll", "back"):
                    clean.append(s)
                elif a in ("click", "type", "select", "check") and (s.get("descriptor") or {}).get("name"):
                    clean.append(s)
            if not clean or len(clean) > _MAX_RECIPE_STEPS:
                return False
            self.dir.mkdir(parents=True, exist_ok=True)
            self._path(key).write_text(json.dumps({
                "key": key, "task": task, "domain": _domain(url), "start_url": url,
                "steps": clean, "saved_at": int(time.time()),
            }, indent=2))
            return True
        except Exception:
            return False
