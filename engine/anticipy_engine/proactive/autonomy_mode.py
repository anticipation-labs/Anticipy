"""User-facing AUTONOMY DIAL (Full-Send / Regular / Limited) + per-task-type TRUST LEDGER.

The brain first decides a SAFE disposition (do / ask / blocked / remember). This layer ADJUSTS that to
the user's chosen mode and the trust earned for that kind of task — but NEVER crosses two hard invariants:

  1. money / external-send-to-a-person / delete / binding  -> ALWAYS confirm, in EVERY mode (Full-Send too).
  2. below the confidence floor                            -> every mode drops a level (do -> ask).

Trust builds autonomy the honest way: a task-type the user has approved cleanly N times can promote from
ask -> auto; one rejection demotes it hard. Money/send NEVER promote — they are invariant. This is the
trust floor expressed as code, not a vibe: a $4,200 spend stays CONFIRM in every mode including Full-Send.
"""
from __future__ import annotations

import json
from pathlib import Path

MODES = ("full_send", "regular", "limited")
DEFAULT_MODE = "regular"
CONFIDENCE_FLOOR = 0.55
PROMOTE_AFTER = 5          # clean approvals before a task-type may auto-run
DEMOTE_PENALTY = 3         # a rejection costs this many clean reps

# external send to a real person — invariant confirm (binding/irreversible-social, even with no money)
_SEND_ACTIONS = {"draft_or_confirm_message"}
# the tiny always-reversible whitelist Limited still auto-does without asking
_LIMITED_AUTO = {"create_calendar_or_reminder", "timed_reminder", "write_memory", "write_profile_memory"}
# reversible actions Full-Send may upgrade ask -> do (no money, no external send, throwaway browser)
_FULLSEND_UPGRADE = {"research_or_find_item", "browser_action", "find_or_cart_without_purchase",
                     "browse_task", "execute_owner_task"}


_BROWSERISH = {"research_or_find_item", "browser_action", "find_or_cart_without_purchase", "browse_task"}


def task_type(card: dict) -> str:
    """Stable trust key. Browser-ish actions normalize to "browser" so trust accrues consistently
    whether the card is read before or after the browser-ask conversion (research_or_find_item ->
    browser_action). This keeps the dial's tier lookup and the YES/NO trust record on the SAME key."""
    a = card.get("action") or card.get("route") or "generic"
    return "browser" if a in _BROWSERISH else a


def is_invariant_locked(card: dict) -> bool:
    """Money / external-send / delete / binding => confirm in EVERY mode. The trust floor."""
    if card.get("disposition") == "blocked":          # money / checkout — absolute
        return True
    if card.get("action") in _SEND_ACTIONS:           # send to a real person
        return True
    if card.get("is_irreversible") or card.get("binding") or card.get("is_delete"):
        return True
    return False


def adjust(card: dict, mode: str, trust_tier: int = 0, confidence: float = 1.0) -> dict:
    """Return {disposition, why, changed} after applying mode + trust under the two invariants.
    Never mutates the card; the caller applies the returned disposition."""
    mode = mode if mode in MODES else DEFAULT_MODE
    disp = card.get("disposition")
    action = card.get("action")

    # INVARIANT 1 — money / send / delete / binding: confirm in every mode, no exceptions.
    if is_invariant_locked(card):
        return {"disposition": disp, "why": "always confirm — money/send/irreversible overrides every mode",
                "changed": False}

    # INVARIANT 2 — below the confidence floor, every mode drops a level.
    floor_hit = confidence is not None and confidence < CONFIDENCE_FLOOR
    if floor_hit and disp == "do":
        return {"disposition": "ask", "why": "not confident enough yet — confirming first", "changed": True}

    if mode == "limited":
        if disp == "do" and action not in _LIMITED_AUTO:
            return {"disposition": "ask", "why": "Limited mode — I'll check before this one", "changed": True}
        return {"disposition": disp, "why": "Limited mode", "changed": False}

    if mode == "full_send" and not floor_hit:
        if disp == "ask" and (action in _FULLSEND_UPGRADE or trust_tier >= 2):
            return {"disposition": "do", "why": "Full-Send — I'll just handle it (reversible, no money)",
                    "changed": True}
        return {"disposition": disp, "why": "Full-Send mode", "changed": False}

    # regular: trust earned over reps can promote a repeatedly-approved reversible ask -> do
    if mode == "regular" and disp == "ask" and trust_tier >= 2 and action not in _SEND_ACTIONS:
        return {"disposition": "do", "why": "you've okayed this kind of thing enough — I'll just do it",
                "changed": True}
    return {"disposition": disp, "why": "Regular mode", "changed": False}


class TrustLedger:
    """Per-task-type clean-rep counter, persisted to JSON. tier: 0 = always ask, 1 = notify, 2 = auto-eligible."""

    def __init__(self, path):
        self.path = Path(path)
        self._d = {}
        try:
            if self.path.exists():
                self._d = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self._d = {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._d, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            pass

    def reps(self, tt: str) -> int:
        return int(self._d.get(tt, {}).get("clean", 0))

    def tier(self, tt: str) -> int:
        r = self.reps(tt)
        return 2 if r >= PROMOTE_AFTER else (1 if r >= 2 else 0)

    def record_clean(self, tt: str) -> int:
        e = self._d.setdefault(tt, {"clean": 0})
        e["clean"] = e.get("clean", 0) + 1
        self._save()
        return self.tier(tt)

    def record_rejection(self, tt: str) -> int:
        e = self._d.setdefault(tt, {"clean": 0})
        e["clean"] = max(0, e.get("clean", 0) - DEMOTE_PENALTY)
        self._save()
        return self.tier(tt)
