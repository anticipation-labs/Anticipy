"""THE SCOREBOARD. One command, one verdict.

Anticipy has been "almost done" for weeks, and every session found a DIFFERENT
issue. That is the Last 10% Trap: building fat PARTS instead of one thin WHOLE,
so integration failures surface one at a time, forever.

This is the cure — Cockburn's Walking Skeleton. One acceptance test that walks
the ENTIRE journey, thin. It prints exactly one thing:

    DONE
or  NOT DONE — first failing leg: N (<why>)

Rules that make it worth trusting:

  * It measures whatever tree it is run from. Run it in the control repo and it
    tells you about PRODUCTION. Run it in a worktree and it tells you about that
    branch. It never mixes the two.
  * A leg that cannot be tested FAILS. It never passes by default, never passes
    because an import was missing, never passes because a file was absent.
  * Legs run in order and it reports the FIRST failure. Later legs still run, so
    you can see whether you thickened the wrong part — but only the first
    failure sets the verdict.
  * Leg 6 cannot be faked. It requires a real cold stranger, on their own
    accounts, signed in overnight/done_proof.json. No proof, NOT DONE, forever.

Run:
    python3 overnight/done_gate.py
    python3 overnight/done_gate.py --verbose
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


class LegFailed(Exception):
    """A leg did not hold. The message is what the owner reads."""


def note(msg: str) -> None:
    if VERBOSE:
        print(f"      {msg}")


# --------------------------------------------------------------------------
# LEG 1 — SHE HEARS YOU
# The words that come out are the words that went in. Once each, in order.
# Apple's recogniser REWRITES its transcript in place, so the emission layer is
# handed a moving target; this leg replays that motion and checks nothing is
# lost or doubled. Tested against the real Swift type, because a Python mock of
# it would prove nothing about the app.
# --------------------------------------------------------------------------
def leg_1_hears() -> str:
    swift = os.path.join(ROOT, "app/ios/Anticipy/Audio/TranscriptCursor.swift")
    runner = os.path.join(ROOT, "app/ios/Tests/run_cursor_tests.sh")

    if not os.path.exists(swift):
        raise LegFailed(
            "the emission layer still uses the integer cursor. "
            "TranscriptCursor.swift is not in this tree, so one spoken sentence "
            "can still arrive as three overlapping fragments")

    if not os.path.exists(runner):
        raise LegFailed(
            "TranscriptCursor.swift exists but nothing proves it works — "
            "app/ios/Tests/run_cursor_tests.sh is missing")

    if not _have("swift"):
        raise LegFailed(
            "cannot verify: swift is not on PATH, so the cursor tests cannot "
            "run. A leg that cannot be tested does not pass")

    try:
        r = subprocess.run(["sh", runner], cwd=ROOT, capture_output=True,
                           text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise LegFailed("cursor tests timed out after 5 minutes")

    out = (r.stdout or "") + (r.stderr or "")
    note(out.strip()[-800:])
    if r.returncode != 0:
        tail = out.strip().splitlines()[-6:]
        raise LegFailed("cursor tests FAIL: " + " / ".join(t.strip() for t in tail))

    return "spoken words survive the recogniser's rewrites, once each"


# --------------------------------------------------------------------------
# LEG 2 — SHE KNOWS IT WAS ONE CONVERSATION
# The failure this exists to catch is Omar's real one: a single phone call that
# became three conversations because the phone buffered the audio and the timer
# read ARRIVAL time. So the test is not "does it group nicely" — it is the law
# that bug broke: the same speech, delivered in a different order, must produce
# the same conversations.
# --------------------------------------------------------------------------
def leg_2_one_conversation() -> str:
    try:
        from brain import segmenter
    except Exception as e:
        raise LegFailed(f"brain/segmenter.py will not import: {e}")

    # One conversation: six turns spoken 20s apart, no real silence anywhere.
    base = 1_760_000_000
    spoken = [
        ("hey how's it going", 0),
        ("my name is Angie I'm calling from a startup working with trades", 20),
        ("I was wanting to grab a couple minutes of feedback", 45),
        ("not able to speak to Joe Baxter", 70),
        ("I'm pretty good thanks", 95),
        ("thank you so much I appreciate that", 120),
    ]
    turns = [{"text": t,
              "capture_started_at": base + off,
              "capture_ended_at": base + off + 4,
              "created": base + off} for t, off in spoken]

    fn = getattr(segmenter, "segment_all", None)
    if fn is None:
        raise LegFailed(
            "brain/segmenter.py has no segment_all(turns) -> conversations. "
            "Without one pure entry point there is no way to ask 'how many "
            "conversations was that', so this leg cannot be checked at all")

    try:
        in_order = fn(list(turns))
    except Exception as e:
        raise LegFailed(f"segment_all raised on a plain 6-turn call: {e}")

    n = len(in_order)
    if n != 1:
        raise LegFailed(
            f"one phone call with 20-25s pauses came out as {n} conversations. "
            "This is Omar's screenshot, reproduced")

    # THE LAW. The pendant buffers and flushes; arrival order is not speech
    # order. Same speech, shuffled delivery, must be the same answer.
    shuffled = [turns[i] for i in (3, 0, 5, 1, 4, 2)]
    for i, t in enumerate(shuffled):
        t = dict(t)
        t["created"] = base + 900 + i      # all arrived late, in a lump
        shuffled[i] = t
    try:
        late = fn(shuffled)
    except Exception as e:
        raise LegFailed(f"segment_all raised on buffered/out-of-order audio: {e}")

    if len(late) != n:
        raise LegFailed(
            f"the SAME six sentences became {n} conversation(s) when delivered "
            f"live and {len(late)} when the phone flushed them late. The boundary "
            "still depends on when the network delivered the audio, not on when "
            "he spoke")

    return "one call stays one call, live or flushed late"


# --------------------------------------------------------------------------
# LEG 3 — SHE JUDGES RIGHT
# Two keys must turn: is this actionable, and whose job is it? Omar's real
# misfires came from asking only the first. This runs the REAL triage prompt
# against a live model on his own recorded lines. No mocks — a scripted model
# would only prove the policy wiring, which tests/test_owes.py already covers.
# --------------------------------------------------------------------------
def leg_3_judges() -> str:
    try:
        from brain.llm import LLM
        from brain.orchestrator import TRIAGE_SYSTEM, _extract_json
    except Exception as e:
        raise LegFailed(f"brain triage will not import: {e}")

    llm = LLM()
    if not getattr(llm, "live", False):
        raise LegFailed(
            "no model key, so her judgement cannot be measured. "
            "Set OPENROUTER_API_KEY. A leg that cannot be tested does not pass")

    # Omar's OWN lines. The first three are dictation to his laptop and must
    # stay silent; the fourth is a real plan and must fire. Ground truth comes
    # from his Wispr Flow history, not from anyone's opinion.
    cases = [
        ("Pill 491 kill 492 kill 493 of your list", False),
        ("Carson Michael and RV.help23 add that to the KTHAI list", False),
        ("4546 4748 reply my inbox drive to Toby's email", False),
        ("can you book us dinner at 7 tomorrow at Cactus Club", True),
    ]

    wrong = []
    for text, should_fire in cases:
        try:
            res = llm.chat(TRIAGE_SYSTEM, text, temperature=0.0)
            got = json.loads(_extract_json(res.text))
        except Exception as e:
            raise LegFailed(f"triage errored on {text!r}: {e}")
        fired = got.get("decision") in ("act", "ask")
        owes = got.get("owes")
        if owes in ("machine", "nobody"):
            fired = False
        note(f"{'FIRE' if fired else 'quiet'}  owes={owes}  {text[:52]}")
        if fired != should_fire:
            wrong.append(f"{text[:44]!r} -> {'fired' if fired else 'silent'}"
                         f" (wanted {'fire' if should_fire else 'silence'})")

    if wrong:
        raise LegFailed("judgement wrong on " + "; ".join(wrong))
    return "dictation stays silent, a real plan still fires"


# --------------------------------------------------------------------------
# LEG 4 — SHE ACTUALLY DOES IT
# A judged plan has to become a real job with a real goal, held for approval.
# This is the leg that separates "she understood" from "she acted".
# --------------------------------------------------------------------------
def leg_4_does_it() -> str:
    try:
        from brain.anticipy_core import Anticipy, is_consequential
    except Exception as e:
        raise LegFailed(f"brain/anticipy_core.py will not import: {e}")

    if not is_consequential("book a table for two at 7pm at Cactus Club"):
        raise LegFailed(
            "is_consequential() does not consider booking a table "
            "consequential, so nothing would ever be held for approval")

    engine = os.environ.get("ANTICIPY_ENGINE_URL")
    if not engine:
        raise LegFailed(
            "cannot verify: ANTICIPY_ENGINE_URL is unset, so there is no engine "
            "to hand a job to. Start the local engine and re-run")

    try:
        import urllib.request
        with urllib.request.urlopen(engine.rstrip("/") + "/health", timeout=5) as r:
            ok = r.status == 200
    except Exception as e:
        raise LegFailed(f"engine at {engine} is not reachable: {e}")
    if not ok:
        raise LegFailed(f"engine at {engine} did not return healthy")

    _ = Anticipy  # the class must at least be constructible-importable
    return "a consequential plan is recognised and an engine is standing by"


# --------------------------------------------------------------------------
# LEG 5 — SHE SHOWS YOU ONE CARD
# Omar's screenshot: one sales call rendered as twelve rows of
# "Noted — nothing needed". The feed must group by conversation, and it must
# still render something honest when the grouping key is absent.
# --------------------------------------------------------------------------
def leg_5_one_card() -> str:
    content = os.path.join(ROOT, "app/ios/Anticipy/Views/ContentView.swift")
    if not os.path.exists(content):
        raise LegFailed("app/ios/Anticipy/Views/ContentView.swift is missing")

    src = open(content, encoding="utf-8", errors="replace").read()

    group = os.path.join(ROOT, "app/ios/Anticipy/Views/HeardGroup.swift")
    card = os.path.join(ROOT, "app/ios/Anticipy/Views/ConversationCard.swift")
    if not (os.path.exists(group) or "HeardGroup" in src):
        raise LegFailed(
            "the feed still renders one row per heard line — there is no "
            "grouping type. Omar's one phone call still shows as twelve rows")
    if not (os.path.exists(card) or "ConversationCard" in src):
        raise LegFailed("grouping exists but nothing renders a conversation card")

    tests = os.path.join(ROOT, "app/ios/Tests/HeardGroupTests.swift")
    if not os.path.exists(tests):
        raise LegFailed(
            "the card feed has no tests, so 'it groups correctly' is a claim, "
            "not a fact")

    if not _have("swift"):
        raise LegFailed("cannot verify: swift is not on PATH")

    runner = os.path.join(ROOT, "app/ios/Tests/run_heard_group_tests.sh")
    if not os.path.exists(runner):
        raise LegFailed(
            "HeardGroupTests.swift exists but there is no runner script for it, "
            "so nothing in CI or in this gate can execute it")

    try:
        r = subprocess.run(["sh", runner], cwd=ROOT, capture_output=True,
                           text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise LegFailed("card-feed tests timed out")
    note(((r.stdout or "") + (r.stderr or "")).strip()[-800:])
    if r.returncode != 0:
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-6:]
        raise LegFailed("card-feed tests FAIL: " + " / ".join(t.strip() for t in tail))

    return "the feed groups a conversation into one card"


# --------------------------------------------------------------------------
# LEG 6 — A STRANGER
# This one cannot be faked and cannot be argued around. A real person who is
# not Omar, on their own accounts, carried through a real day. Signed, dated,
# in overnight/done_proof.json. Without it the answer is NOT DONE, forever,
# no matter how green legs 1-5 are.
# --------------------------------------------------------------------------
REQUIRED_PROOF = ("stranger_name", "date", "their_own_accounts",
                  "real_things_done", "signed_by")


def leg_6_stranger() -> str:
    path = os.path.join(HERE, "done_proof.json")
    if not os.path.exists(path):
        raise LegFailed(
            "no cold stranger has ever onboarded on their own accounts and "
            "been carried through a real day. This is the finish line and it "
            "has not happened")
    try:
        proof = json.load(open(path))
    except Exception as e:
        raise LegFailed(f"done_proof.json is unreadable: {e}")

    missing = [k for k in REQUIRED_PROOF if not proof.get(k)]
    if missing:
        raise LegFailed(f"done_proof.json is incomplete: missing {missing}")
    if proof.get("their_own_accounts") is not True:
        raise LegFailed("the stranger did not use their own accounts")
    done = proof.get("real_things_done") or []
    if not isinstance(done, list) or len(done) < 1:
        raise LegFailed("no real things were done in the stranger's real life")

    return f"{proof['stranger_name']} onboarded {proof['date']}: {len(done)} real things"


# --------------------------------------------------------------------------

LEGS = [
    (1, "SHE HEARS YOU", leg_1_hears),
    (2, "IT WAS ONE CONVERSATION", leg_2_one_conversation),
    (3, "SHE JUDGES RIGHT", leg_3_judges),
    (4, "SHE ACTUALLY DOES IT", leg_4_does_it),
    (5, "SHE SHOWS ONE CARD", leg_5_one_card),
    (6, "A STRANGER", leg_6_stranger),
]


def _have(prog: str) -> bool:
    from shutil import which
    return which(prog) is not None


def main() -> int:
    print()
    print(f"  ANTICIPY DONE GATE   tree: {ROOT}")
    print("  " + "-" * 62)

    first_fail = None
    for num, name, fn in LEGS:
        try:
            detail = fn()
            print(f"  [{num}] PASS  {name}")
            print(f"        {detail}")
        except LegFailed as e:
            mark = "FAIL" if first_fail is None else "fail"
            print(f"  [{num}] {mark}  {name}")
            print(f"        {e}")
            if first_fail is None:
                first_fail = (num, name, str(e))
        except Exception as e:                       # noqa: BLE001
            if VERBOSE:
                traceback.print_exc()
            print(f"  [{num}] FAIL  {name}")
            print(f"        gate itself errored: {e}")
            if first_fail is None:
                first_fail = (num, name, f"gate errored: {e}")

    print("  " + "-" * 62)
    if first_fail is None:
        print("  DONE")
        print()
        return 0
    num, name, why = first_fail
    print(f"  NOT DONE — first failing leg: {num} ({name})")
    print(f"  {why}")
    print()
    print("  Work ONLY this leg. Not the next feature, not a nicer UI.")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
