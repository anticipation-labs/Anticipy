"""A card may only be amended by the conversation it came from, while that
conversation is still happening.

Live, 2026-08-22. Two events with nothing whatsoever to do with each other:

    8vgi69wwx4r6s9s  "Take a picture it's all right"
                     segment ptxmmgv7njxqyko, 2026-08-21 08:15
    y0d54yrinmj40l1  "ugh, I never checked what time the pharmacy on Broadway
                     closes tonight"
                     segment 8vnxpybae7lt1y8, 2026-08-22 02:39

18h24m and two segments apart, and they landed on ONE job, ja12rda9nexgfbw.
The picture request was overwritten out of existence, workflow_version went
to 2, the card stayed `consequential`, and the authority text the owner would
have been asked to approve read, literally:

    "Take a picture it's all right … then: ugh, I never checked what time the
     pharmacy on Broadway closes"

The lineage lookup exists as the durable stand-in for the in-memory open-plan
pointer — nothing more — and it had no clock on it at all. The merge prompt
has always said "two task descriptions from the SAME conversation, minutes
apart"; these tests are that sentence made enforceable, without disabling the
seconds-apart refinement the feature exists for.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
from brain.anticipy_core import (Anticipy, LINEAGE_AMEND_WINDOW,  # noqa: E402
                                 OPEN_PLAN_WINDOW)

OLD_SEG = "ptxmmgv7njxqyko"
NEW_SEG = "8vnxpybae7lt1y8"
PICTURE = "Take a picture of the whiteboard"
PHARMACY = "Look up what time the pharmacy on Broadway closes tonight"


def _stamp(seconds_ago: float) -> str:
    """PocketBase's own format, which is what _last_touched parses."""
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds_ago)
    return when.strftime("%Y-%m-%d %H:%M:%S") + ".000Z"


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class Rig:
    """An in-memory jobs table that answers the three filters _queue_job asks:
    the pending pool, 'the card this lineage is holding', and the running
    pool."""

    def __init__(self, card=None, lineage_hit=True):
        self.jobs = [card] if card else []
        # Whether the backend honours the lineage filter. False reproduces a
        # lookup that reaches a row belonging to another conversation.
        self.lineage_hit = lineage_hit

    def get(self, url, params=None, timeout=None, **kw):
        flt = (params or {}).get("filter", "")
        if "lineage_key=" in flt:
            if not self.lineage_hit:
                return _R({"items": []})
            return _R({"items": [j for j in self.jobs
                                 if j.get("status") == "awaiting_confirm"]})
        if 'status="running"' in flt:
            return _R({"items": [j for j in self.jobs
                                 if j.get("status") == "running"]})
        return _R({"items": [j for j in self.jobs
                             if j.get("status") in ("awaiting_confirm",
                                                    "queued")]})

    def post(self, url, json_=None, timeout=None, **kw):
        rec = dict(kw.get("json") or json_ or {})
        rec.setdefault("status", "awaiting_confirm")
        rec["id"] = f"new{len(self.jobs) + 1}"
        self.jobs.append(rec)
        return _R(rec)

    def patch(self, url, json_=None, timeout=None, **kw):
        body = kw.get("json") or json_ or {}
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for j in self.jobs:
            if j.get("id") == jid:
                j.update(body)
        return _R({})

    def goals(self):
        return [j.get("goal") for j in self.jobs]


def _card(lineage, age_seconds):
    return {"id": "ja12rda9nexgfbw", "goal": PICTURE,
            "status": "awaiting_confirm", "lineage_key": lineage,
            "params": json.dumps({"source": "Take a picture it's all right",
                                  "lineage_key": lineage}),
            "created": _stamp(age_seconds), "updated": _stamp(age_seconds)}


def _anticipy(monkeypatch, rig, lineage):
    monkeypatch.setattr(pb, "get", rig.get)
    monkeypatch.setattr(pb, "post", lambda url, json=None, timeout=None, **k:
                        rig.post(url, json=json, timeout=timeout, **k))
    monkeypatch.setattr(pb, "patch", lambda url, json=None, timeout=None, **k:
                        rig.patch(url, json=json, timeout=timeout, **k))
    a = Anticipy(owner_id="t")
    a._lineage_key = lineage
    # The subject and containment guards are neutralised on purpose. Both are
    # already-working, independently tested filters that simply did not catch
    # the live pair, and leaving them in would let this test pass for the
    # wrong reason. What is under test here is the clock and the lineage.
    monkeypatch.setattr(Anticipy, "_same_subject",
                        classmethod(lambda cls, a_, b_: True))
    monkeypatch.setattr(Anticipy, "_covered_by",
                        lambda self, new, old: False)
    return a


# --------------------------------------------------------------- the failure

def test_a_card_from_yesterday_is_not_amended_by_todays_line(monkeypatch):
    """THE 18h24m MERGE. The stale segment was still the open one, so the
    lookup found yesterday's card and wrote today's errand over it."""
    rig = Rig(_card(OLD_SEG, 18 * 3600 + 24 * 60))
    a = _anticipy(monkeypatch, rig, OLD_SEG)

    out = a._queue_job(PHARMACY,
                       {"source": "ugh, I never checked what time the "
                                  "pharmacy on Broadway closes tonight",
                        "lineage_key": OLD_SEG}, hold=True)

    assert out != "ja12rda9nexgfbw", \
        "an 18-hour-old card was amended by an unrelated line"
    assert rig.jobs[0]["goal"] == PICTURE, \
        f"the original request was destroyed: {rig.jobs[0]['goal']!r}"
    assert len(rig.jobs) == 2, f"two errands, two cards: {rig.goals()}"
    src = json.loads(rig.jobs[0]["params"]).get("source", "")
    assert "… then:" not in src, \
        f"two conversations were concatenated into one authority text: {src!r}"


def test_a_card_naming_another_conversation_is_never_amended(monkeypatch):
    """The second, independent condition: even reached, a row that says out
    loud it belongs to another segment is not this conversation's card."""
    rig = Rig(_card(OLD_SEG, 30))          # warm, but foreign
    a = _anticipy(monkeypatch, rig, NEW_SEG)

    out = a._queue_job(PHARMACY,
                       {"source": "ugh, I never checked what time the "
                                  "pharmacy on Broadway closes tonight",
                        "lineage_key": NEW_SEG}, hold=True)

    assert out != "ja12rda9nexgfbw", "wrote across two conversations"
    assert rig.jobs[0]["goal"] == PICTURE
    assert len(rig.jobs) == 2, f"two conversations, two cards: {rig.goals()}"


# --------------------------------------------------- what must NOT change

def test_a_refinement_seconds_later_still_lands_on_the_same_card(monkeypatch):
    """ONE CONVERSATION, ONE CARD still holds. This is the whole point of the
    lineage lookup and the ceiling may not cost it."""
    rig = Rig(_card(OLD_SEG, 20))
    a = _anticipy(monkeypatch, rig, OLD_SEG)

    out = a._queue_job("Take a picture of the whiteboard and email it to Dana",
                       {"source": "and email it to Dana",
                        "lineage_key": OLD_SEG}, hold=True)

    assert out == "ja12rda9nexgfbw", "a same-breath refinement stopped merging"
    assert len(rig.jobs) == 1, f"the refinement minted a second card: {rig.goals()}"
    assert "Dana" in rig.jobs[0]["goal"], rig.jobs[0]["goal"]


def test_a_card_still_being_worked_eight_minutes_in_is_still_warm(monkeypatch):
    """Age is measured from the LAST touch, not the first: a dinner talked
    into shape over ten minutes is one live conversation, and judging it by
    `created` alone would cut it off mid-sentence."""
    card = _card(OLD_SEG, 40 * 60)
    card["updated"] = _stamp(45)
    rig = Rig(card)
    a = _anticipy(monkeypatch, rig, OLD_SEG)

    out = a._queue_job("Take a picture of the whiteboard and email it to Dana",
                       {"source": "and email it to Dana",
                        "lineage_key": OLD_SEG}, hold=True)

    assert out == "ja12rda9nexgfbw", "a card touched 45s ago read as stale"


def test_a_row_with_no_readable_stamp_is_no_verdict(monkeypatch):
    """Every fake and every hand-built dict in this repo carries rows without
    timestamps. An unreadable stamp must block nothing."""
    card = _card(OLD_SEG, 30)
    card.pop("created")
    card.pop("updated")
    rig = Rig(card)
    a = _anticipy(monkeypatch, rig, OLD_SEG)

    out = a._queue_job("Take a picture of the whiteboard and email it to Dana",
                       {"source": "and email it to Dana",
                        "lineage_key": OLD_SEG}, hold=True)

    assert out == "ja12rda9nexgfbw"


def test_the_ceiling_is_minutes_and_never_outreaches_the_open_plan_pointer():
    """The lookup is the durable mirror of the in-memory pointer. It may not
    remember a conversation longer than the process would have."""
    assert LINEAGE_AMEND_WINDOW <= OPEN_PLAN_WINDOW
    assert LINEAGE_AMEND_WINDOW <= 15 * 60, "hours is what caused the incident"
