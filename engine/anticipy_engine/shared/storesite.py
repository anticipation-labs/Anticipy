"""Store-name -> site derivation for memory-resolved shopping targets.

People remember stores the way they speak ("the water table at Target", "a desk
lamp on Amazon"), never as hostnames — but the browser hand's no-search contract
requires action tasks to arrive with a resolved real site. For a PRODUCT-shaped
memory line, the single-word-brand web convention (<brand>.com) is derivable with
NO per-store table: this module holds that one closed-class shape plus its deny
bounds, and stays free of retailer literals.

Shared by proactive/harm.py (the memory-resolved cart-target ACT rule) and
core/orchestrator.py (the memory->browse-step resolver); shared/ is the neutral
import direction for both.

Deny direction (a junk derivation navigates a real browser somewhere wrong, so
every bound fails toward ""):
  - the line itself must be product/shopping-shaped (double-gated: callers gate
    too, but the helper never fires on a bare "at X" sentence by construction);
  - only after a literal at/on/from preposition (lowercase — sentence-initial
    "At ..." is not the spoken-store shape);
  - single Capitalized word only: a following Capitalized/numeric token means a
    multi-word proper noun ("Lincoln Elementary", "Best Buy", "Hoka Bondi 9") —
    not derivable, refuse;
  - possessives refuse ("at Bob's" is a person's place, not <bobs>.com);
  - closed-class non-store capitalized words refuse (weekdays, months, holidays,
    generic places people shop "at" figuratively);
  - mixed/upper-case brands (eBay, IKEA) miss by design — disclosed residual,
    not worth loosening the capitalization anchor for.
"""
from __future__ import annotations

import re

# The shopping-context shape (same verb family as the orchestrator's
# _PRODUCT_HINT_RE / harm.py's _MEM_PRODUCT — keep the three aligned).
PRODUCT_CONTEXT_RE = re.compile(
    r"\b(?:looked at|looking at|viewed|found|considered|considering|wanted|"
    r"shopping for|compared|comparing|researched|researching|checked out|"
    r"checking out|product|item|thing|cart)\b",
    re.I,
)

_STORE_AFTER_PREP_RE = re.compile(
    r"\b(?:at|on|from)\s+([A-Z][a-z0-9&-]{2,})\b(?!['’]s?\b)(?!\s+[A-Z0-9])"
)

_NOT_A_STORE = frozenset({
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
    "Christmas", "Thanksgiving", "Easter", "Halloween", "Noon", "Midnight",
    "School", "Work", "Home", "Church", "Lunch", "Dinner", "Breakfast",
    "Mom", "Dad", "Grandma", "Grandpa",
})


def derive_store_site(line: str) -> str:
    """The https://www.<store>.com a product-shaped memory line names by store
    name, or "" when nothing survives the deny bounds (never guesses past them)."""
    if not line or not PRODUCT_CONTEXT_RE.search(line):
        return ""
    for m in _STORE_AFTER_PREP_RE.finditer(line):
        token = m.group(1)
        if token in _NOT_A_STORE:
            continue
        return f"https://www.{token.lower()}.com"
    return ""
