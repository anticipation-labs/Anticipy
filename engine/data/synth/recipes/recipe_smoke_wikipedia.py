"""Phase fara-4 framework smoke recipe: navigate Wikipedia and extract
the first paragraph. Not one of the eight proof scenarios; this is
just the tiniest end-to-end recipe to prove the recorder framework
records screenshots + actions to JSONL correctly.

Real proof recipes (Gmail compose, Sheets write, Canva draw, etc.)
live in this same directory once Fara is loaded and the recorder
mechanics are validated.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine"))

from data.synth.record_trajectory import Recipe, RecipeAction  # noqa: E402


def build_recipe() -> Recipe:
    return Recipe(
        scenario="smoke_wikipedia",
        goal="Open the Python (programming language) Wikipedia article and read the lead paragraph.",
        setup_url="https://en.wikipedia.org/wiki/Python_(programming_language)",
        actions=[
            # Just one wait; the page loaded in setup_url. The goal is to
            # see Wikipedia rendered. The verifier confirms.
            RecipeAction(
                action={"action": "wait", "time": 1.5},
                intent_hint="Wait for the Wikipedia article to fully render before reading.",
            ),
            RecipeAction(
                action={"action": "scroll", "pixels": -300},
                intent_hint="Scroll down a bit so the lead paragraph is centered.",
            ),
            RecipeAction(
                action={"action": "terminate", "status": "success"},
                intent_hint="The article is on screen with the lead text visible. Task done.",
            ),
        ],
        verifier=_verify,
    )


def _verify(sess) -> bool:
    """Verify the page is the Python Wikipedia article."""
    r = sess.send("Runtime.evaluate", {
        "expression": "document.title",
        "returnByValue": True,
    })
    title = r.get("result", {}).get("value", "")
    return "Python" in title and "Wikipedia" in title
