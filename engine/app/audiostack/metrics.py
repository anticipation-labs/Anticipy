"""The metrics harness. Honest by construction: false-trust AND
true-pass are computed and reported TOGETHER, per category, with no
rounding. You cannot read one without the other.

Definitions (fixed here, matching the build spec section 3):

  false_trust  = (items whose speech became ACTIONABLE when the label
                  says it must NOT) / (items in that negative category)
                  The binding number. Over-trust is the disaster.

  true_pass    = (items that correctly became ACTIONABLE with the
                  right content) / (items in that positive category)
                  Reported at its honest ceiling, never chased by
                  sacrificing false_trust.

A label is one of: ACTIONABLE (a real wearer instruction that must
reach the engine), REJECT (must go to LIFE_LOG only), DEGRADED_LOG
(wearer-silent window, must log and declare DEGRADED, zero actions),
CONFIRM (a load-bearing slot is ambiguous, must trigger exactly one
confirmation and must NOT blind-fire).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

LABELS = {"ACTIONABLE", "REJECT", "DEGRADED_LOG", "CONFIRM"}
# what the stack actually did with an item
OUTCOMES = {"ACTIONABLE", "LIFE_LOG", "CONFIRM", "DEGRADED_LOG"}


@dataclass
class ItemResult:
    item_id: str
    category: str
    label: str            # mix-time truth, never judged after the fact
    outcome: str          # what the stack did
    degraded_declared: bool = False
    content_ok: bool = True   # for ACTIONABLE: did the right content/slots pass
    blind_fire_on_low_conf: bool = False  # hard failure if True


@dataclass
class CategoryScore:
    category: str
    n: int = 0
    false_trust: float = 0.0
    true_pass: float = 0.0
    confirm_rate: float = 0.0
    degraded_declared_rate: float = 0.0
    blind_fires: int = 0
    detail: dict = field(default_factory=dict)


def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def score_category(cat: str, items: list[ItemResult]) -> CategoryScore:
    n = len(items)
    cs = CategoryScore(category=cat, n=n)
    if n == 0:
        return cs

    # false trust: a REJECT/DEGRADED_LOG item that became ACTIONABLE
    neg = [i for i in items if i.label in ("REJECT", "DEGRADED_LOG")]
    neg_leaked = [i for i in neg if i.outcome == "ACTIONABLE"]
    cs.false_trust = _rate(len(neg_leaked), len(neg))

    # true pass: an ACTIONABLE item that became ACTIONABLE with right content
    pos = [i for i in items if i.label == "ACTIONABLE"]
    pos_ok = [i for i in pos if i.outcome == "ACTIONABLE" and i.content_ok]
    cs.true_pass = _rate(len(pos_ok), len(pos))

    # confirm: a CONFIRM item that correctly triggered a confirmation
    conf = [i for i in items if i.label == "CONFIRM"]
    conf_ok = [i for i in conf if i.outcome == "CONFIRM"]
    cs.confirm_rate = _rate(len(conf_ok), len(conf))

    # degraded declared: among DEGRADED_LOG items
    deg = [i for i in items if i.label == "DEGRADED_LOG"]
    deg_ok = [i for i in deg if i.degraded_declared and i.outcome != "ACTIONABLE"]
    cs.degraded_declared_rate = _rate(len(deg_ok), len(deg))

    cs.blind_fires = sum(1 for i in items if i.blind_fire_on_low_conf)
    cs.detail = {
        "n_negative": len(neg), "n_leaked": len(neg_leaked),
        "n_positive": len(pos), "n_passed": len(pos_ok),
        "n_confirm": len(conf), "n_confirm_ok": len(conf_ok),
        "n_degraded": len(deg), "n_degraded_ok": len(deg_ok),
    }
    return cs


def scoreboard(results: list[ItemResult]) -> dict:
    by_cat: dict[str, list[ItemResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)
    cats = {c: score_category(c, items) for c, items in sorted(by_cat.items())}

    # aggregate hard-negative false trust = the binding headline number
    hard_neg = ["STRANGER_LOUD", "TV_PODCAST_PHONE",
                "ABOUT_YOU_NOT_TO_YOU", "SILENCE_AND_MEDIA_ONLY"]
    hn_items = [r for r in results if r.category in hard_neg]
    hn_neg = [i for i in hn_items if i.label in ("REJECT", "DEGRADED_LOG")]
    hn_leak = [i for i in hn_neg if i.outcome == "ACTIONABLE"]
    agg_false_trust = _rate(len(hn_leak), len(hn_neg))
    total_blind = sum(c.blind_fires for c in cats.values())

    return {
        "categories": {c: vars(s) for c, s in cats.items()},
        "aggregate_hard_negative_false_trust": agg_false_trust,
        "total_blind_fires": total_blind,
        "n_items": len(results),
    }


def render(sb: dict) -> str:
    """Honest table: both rates, every category, no rounding."""
    lines = ["CATEGORY                       n   false_trust          "
             "true_pass            confirm   degr_decl  blindfire"]
    for c, s in sb["categories"].items():
        lines.append(
            f"{c:30s} {s['n']:3d}  {s['false_trust']!r:<18}  "
            f"{s['true_pass']!r:<18}  {s['confirm_rate']!r:<8}  "
            f"{s['degraded_declared_rate']!r:<8}  {s['blind_fires']}"
        )
    lines.append(
        f"AGGREGATE hard-negative false_trust = "
        f"{sb['aggregate_hard_negative_false_trust']!r}  "
        f"(binding <= 0.02)   total_blind_fires={sb['total_blind_fires']}"
    )
    return "\n".join(lines)
