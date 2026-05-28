"""Honest metrics. Both rates reported TOGETHER, per category, no
rounding. The binding HARD metrics (CHATTER false-action,
double-action, cancel-after-execute, flood) are never relaxed.

outcome vocabulary (what the pipeline did with an event):
  ACTED      proceeded to a real action (through the frozen engine)
  CONFIRMED  asked the wearer one question (uncertain reference/slot)
  LIFE_LOG   recorded, never actioned
  DEFERRED   scheduled against a time condition, not done now
  KILLED     pending action detected already-satisfied and killed
  CANCELLED  live queued action retracted by ambient cancel
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ItemResult:
    ev_id: str
    category: str
    label: str
    outcome: str
    content_ok: bool = True          # for ACTION: refs resolved correctly
    acted_after_cancel: bool = False  # HARD: must never be True
    double_acted: bool = False        # HARD: must never be True
    immediate_deferred: bool = False  # WHEN_DEFERRED executed now (bad)
    dropped_deferred: bool = False    # WHEN_DEFERRED silently lost (bad)
    flood: bool = False               # SURFACING flood event (HARD)
    deadline_missed: bool = False     # time-critical missed via debounce


def _rate(num: int, den: int) -> float:
    return (num / den) if den else 0.0


def scoreboard(results: list[ItemResult]) -> dict:
    by: dict[str, list[ItemResult]] = {}
    for r in results:
        by.setdefault(r.category, []).append(r)

    cats = {}
    for c, items in sorted(by.items()):
        n = len(items)
        acted = [i for i in items if i.outcome == "ACTED"]
        pos = [i for i in items if i.label == "ACTION"]
        pos_ok = [i for i in pos if i.outcome == "ACTED" and i.content_ok]
        cats[c] = {
            "n": n,
            "false_action": _rate(
                len([i for i in items
                     if i.label in ("LIFE_LOG",) and i.outcome == "ACTED"]),
                len([i for i in items if i.label == "LIFE_LOG"])),
            "true_pass": _rate(len(pos_ok), len(pos)),
            "confirm_rate": _rate(
                len([i for i in items if i.outcome == "CONFIRMED"]), n),
            "double_actions": sum(1 for i in items if i.double_acted),
            "acted_after_cancel": sum(1 for i in items if i.acted_after_cancel),
            "deferred_immediate": sum(1 for i in items if i.immediate_deferred),
            "deferred_dropped": sum(1 for i in items if i.dropped_deferred),
            "floods": sum(1 for i in items if i.flood),
            "deadline_missed": sum(1 for i in items if i.deadline_missed),
        }

    chat = [r for r in results if r.label == "LIFE_LOG"]
    chat_fa = _rate(len([r for r in chat if r.outcome == "ACTED"]), len(chat))
    return {
        "categories": cats,
        "chatter_false_action": chat_fa,
        "total_double_actions": sum(1 for r in results if r.double_acted),
        "total_acted_after_cancel": sum(1 for r in results
                                        if r.acted_after_cancel),
        "total_floods": sum(1 for r in results if r.flood),
        "total_deadline_missed": sum(1 for r in results if r.deadline_missed),
        "n": len(results),
    }


def render(sb: dict) -> str:
    L = ["CATEGORY                  n  false_action  true_pass  confirm  "
         "dbl  cancelX  defImm  defDrop  flood"]
    for c, s in sb["categories"].items():
        L.append(
            f"{c:24s} {s['n']:3d}  {s['false_action']!r:<11}  "
            f"{s['true_pass']!r:<8}  {s['confirm_rate']!r:<6}  "
            f"{s['double_actions']}    {s['acted_after_cancel']}       "
            f"{s['deferred_immediate']}      {s['deferred_dropped']}      "
            f"{s['floods']}")
    L.append(
        f"BINDING chatter_false_action={sb['chatter_false_action']!r} "
        f"(<=0.02) double_actions={sb['total_double_actions']} (==0) "
        f"acted_after_cancel={sb['total_acted_after_cancel']} (==0) "
        f"floods={sb['total_floods']} (==0) "
        f"deadline_missed={sb['total_deadline_missed']} (==0)")
    return "\n".join(L)
