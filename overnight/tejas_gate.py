"""THE TEJAS GATE. One leg per fix in the Tejas-call plan, red until it lands.

The plan (research/evals/call-2026-08-23-tejas/PLAN.md) ranks six fixes by one
question: does the next call like this one work? This gate is that plan as a
scoreboard — the same walking-skeleton discipline as done_gate.py and
fellowship_gate.py, pointed at one recorded 28-minute call where five of six
acts were wrong.

Rules, same as the other gates:
  * A leg that cannot be tested FAILS.
  * Legs are deterministic — no model calls, no network. They test the actual
    source (including executing the brain's real regexes extracted from it)
    and the actual recorded call data.
  * Report the FIRST failure; later legs still run.
  * When a leg needs code that does not exist yet, its message names the plan
    item that builds it. This gate being all red today is correct: it is the
    plan, restated as something that cannot quietly go stale.

Run:  python3 overnight/tejas_gate.py
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVAL = os.path.join(ROOT, "research", "evals", "call-2026-08-23-tejas")

CORE = os.path.join(ROOT, "brain", "anticipy_core.py")
ORCH = os.path.join(ROOT, "brain", "orchestrator.py")
PBX = os.path.join(ROOT, "app", "ios", "Anticipy.xcodeproj", "project.pbxproj")
LISTENER = os.path.join(ROOT, "app", "ios", "Anticipy", "Audio", "PhoneListener.swift")


class LegFailed(Exception):
    """The message is what the owner reads."""


def read(path: str) -> str:
    if not os.path.exists(path):
        raise LegFailed(f"{os.path.relpath(path, ROOT)} does not exist")
    with open(path, encoding="utf-8") as f:
        return f.read()


def extract_regex(source: str, name: str) -> re.Pattern:
    """Pull a compiled regex OUT OF THE REAL SOURCE and compile it here, so the
    leg tests what ships without importing the module's heavy dependencies.
    Handles the house style: multi-line re.compile with adjacent r"..." string
    literals AND inline # comments between them, closed by a ')' on its own
    line."""
    m = re.search(name + r"\s*=\s*re\.compile\((.*?)\n\)", source, re.S)
    if not m:
        raise LegFailed(f"could not find {name} in the source — the leg cannot "
                        "be tested, which counts as failing")
    body = re.sub(r"#[^\n]*", "", m.group(1))  # the strings hold no '#'
    pattern = "".join(re.findall(r'r?"((?:[^"\\]|\\.)*)"', body))
    return re.compile(pattern, re.I)


def extract_function(source: str, name: str, prelude: str = ""):
    """Pull a top-level def out of the real source and exec it standalone —
    behavioral testing without importing the module's heavy dependencies."""
    m = re.search(rf"\ndef {name}\(.*?\n(?=\ndef |\n# ---|\nclass )", source,
                  re.S)
    if not m:
        raise LegFailed(f"could not find def {name} in the source — the leg "
                        "cannot be tested, which counts as failing")
    ns: dict = {"re": re}
    exec(prelude + m.group(0), ns)  # noqa: S102 — our own source, read-only
    return ns[name]


# --------------------------------------------------------------------------
# LEG 1 — A MEETING IS A POSTURE, NOT A SURPRISE  (plan #1, ~2d)
#
# During the 28-minute call the system acted six times and texted four times.
# in_conversation() exists and never fired once, because its backchannel-ratio
# design assumes a one-sided call; at 100% speaker volume both voices arrive
# as content. The fix is a posture: detect the two-way conversation (calendar
# overlap, alternating short turns, greeting openers) and act on NOTHING
# inside it — one digest after.
# --------------------------------------------------------------------------
def leg_1_meeting_posture() -> str:
    core = read(CORE)
    worker = read(os.path.join(ROOT, "brain", "worker.py"))
    if "in_meeting" not in core or "_meeting_held" not in core:
        raise LegFailed("no meeting posture exists anywhere in the brain. "
                        "in_conversation() (anticipy_core.py ~:296) never fired on "
                        "this call; a posture that queues instead of acting is plan #1")
    if "meeting posture is armed" not in core:
        raise LegFailed("a posture flag exists but the triage prompt is never told "
                        "about it — the model cannot honor a state it never sees")
    if "def meeting_digest" not in core:
        raise LegFailed("posture exists but no post-call digest does — suppressing "
                        "mid-call acts without the digest just loses the Tuesday call, "
                        "the one act that was right")
    # The detector, RUN: the recorded call's density (137 lines / 28 min ≈ a
    # line every 12s) must arm it; a lone person thinking out loud must not.
    # Only the THRESHOLDS come from source (they are what this leg tests);
    # the two state cells are re-declared clean, because grabbing them by
    # regex also grabs the comprehension inside the function body.
    consts = "\n".join(m.group(0) for m in re.finditer(
        r"^MEETING_(?:DENSITY_N|DENSITY_S|SETTLE_S|SETTLE_FLOOR_S"
        r"|SETTLE_CEIL_S)\s*=\s*[^\n]+",
        worker, re.M))
    if not consts:
        raise LegFailed("the meeting thresholds are gone from worker.py")
    prelude = ("import time\nMEETING_ARRIVALS: list = []\n"
               "MEETING_ARMED = False\nMEETING_MAX_GAP = 0.0\n" + consts + "\n")
    fn = extract_function(worker, "meeting_heard", prelude=prelude)
    armed = False
    for i in range(12):
        armed = fn(now=1000.0 + i * 12.0)        # the Tejas cadence
    if not armed:
        raise LegFailed("meeting_heard() does not arm at the recorded call's "
                        "own line density — the posture would have missed "
                        "the exact call it was built from")
    fn2 = extract_function(worker, "meeting_heard", prelude=prelude)
    sparse = False
    for i in range(12):
        sparse = fn2(now=1000.0 + i * 300.0)     # one mutter every 5 min
    if sparse:
        raise LegFailed("meeting_heard() arms on one line every five minutes — "
                        "a person alone in a room would live in permanent "
                        "meeting posture and every act would queue forever")
    if "in_meeting=in_meeting" not in worker or "maybe_meeting_digest(anticipy)" not in worker:
        raise LegFailed("the posture exists but the worker never feeds it into "
                        "hear() or never emits the digest — organs without "
                        "nerves")
    return "detector arms on the recorded cadence, spares the quiet room; digest wired"


# --------------------------------------------------------------------------
# LEG 2 — A SHARD CANNOT MINT A MEETING  (plan #2a, part of ~1d)
#
# "At 5:15" — two words of TEJAS saying when HIS meeting ends — became
# "meeting with Dr. Evans, Monday 5:15 PM". 54% of captured lines were ≤4
# words. A line that short, without independent support in its segment, may
# produce ignore or ask. Never act.
# --------------------------------------------------------------------------
def leg_2_shard_floor() -> str:
    core = read(CORE)
    if "shard_too_thin" not in core:
        raise LegFailed('nothing stops a 2-word line from acting. "At 5:15" '
                        '(event nbeb6oze5bmyrge) minted a calendar goal; the shard '
                        "floor is plan #2a")
    # The real function with its real deps (goal_tokens): the module imports
    # clean offline — the pytest suite proves that on every run.
    import sys as _sys
    if ROOT not in _sys.path:
        _sys.path.insert(0, ROOT)
    from brain.anticipy_core import shard_too_thin as fn
    mk = lambda d, c, g=None: type("D", (), {"decision": d, "continues": c,
                                             "goal": g})()
    evans_goal = "Schedule meeting for Monday, August 24, 2026 at 5:15 PM PDT"
    if not fn("At 5:15", mk("act", 0, evans_goal)):
        raise LegFailed('shard_too_thin() lets "At 5:15" mint a meeting full '
                        "of words the audio never held — the exact recorded "
                        "failure is back")
    if fn("seven works", mk("act", 2, "dinner Thursday at 7pm")):
        raise LegFailed('shard_too_thin() kills "seven works" even when the '
                        "model linked it to an established thread — the "
                        "firming-up lane is dead")
    if fn("At 5:15", mk("act", 0, evans_goal), explicit=True):
        raise LegFailed("the floor blocks EXPLICIT owner instructions — he "
                        "typed it and she refused")
    if fn("book us Earls tomorrow",
          mk("ask", None, "Book dinner at Earls for tomorrow")):
        raise LegFailed("the floor blocks a thin line acting on ITS OWN words "
                        '("book us Earls tomorrow") — brevity is not the '
                        "tell, invention is")
    if "shard_too_thin(line, decision" not in core:
        raise LegFailed("the floor exists but the ambient lane never calls it")
    # THIS LEG IS A REGRESSION PIN, NOT AN EXPIRY. Read the polarity before
    # you trust it: everything above fails when shard_too_thin is REMOVED or
    # stops blocking "At 5:15". That is correct for what this leg is — plan
    # #2a's fix, held in place until segment-granularity triage replaces it.
    # It is NOT the Law-2 leg. The 2026-08-24 audit found the repo reading it
    # as one, and the earlier comment here promised the leg would "flip to
    # testing its REMOVAL" one day — a promise to edit a gate later is not a
    # mechanism, and while it stood, tejas_gate read 8/8 green with five
    # pieces of undeclared tape in the tree.
    # The expiry that goes RED because this tape EXISTS is
    # overnight/tape_gate.py leg 2. Both legs are correct and both are needed:
    # this one says "do not remove it yet", that one says "do not keep it".
    if "TAPE" not in core.split("def shard_too_thin", 1)[-1][:900]:
        raise LegFailed("the shard floor lost its TAPE marking — tape without "
                        "an expiry is how the last three months happened "
                        "(HARNESS-LAWS.md Law 2)")
    return "the real floor blocks the recorded shard, spares confirmations"


# --------------------------------------------------------------------------
# LEG 3 — AN UNRESOLVED NAME GOES TO ASK, NEVER ACT  (plan #2b)
#
# "Dr. Evans" appears in no transcript line, no contact, no memory. A goal
# naming a person resolvable nowhere must ask, never act. This leg runs the
# REAL unsupported_names() (extracted from orchestrator.py, executed here)
# against the recorded case, and confirms the ambient act path actually
# calls it (anticipy_core.py ~:1532).
#
# CORRECTED 2026-08-23 (late): the deployed brain HAS this guard — it was
# fingerprint-verified as this very lineage. The guard held: the recorded
# GOAL for event nbeb6oze5bmyrge contains no "Dr. Evans" at all. The name
# was invented downstream, in the outgoing-text voice pass — which is LEG 5's
# territory. This leg stays green because the goal-level guard works; the
# earlier "deploy drift" note here was wrong and is retracted.
# --------------------------------------------------------------------------
def leg_3_entity_guard() -> str:
    core = read(CORE)
    orch = read(ORCH)
    mg = re.search(r"_GOAL_VERBS\s*=\s*\{.*?\n\}", orch, re.S)
    if not mg:
        raise LegFailed("_GOAL_VERBS not found — the leg cannot be tested")
    fn = extract_function(orch, "unsupported_names", prelude=mg.group(0) + "\n")
    # the recorded case: event nbeb6oze5bmyrge — goal named a person the
    # audio never contained
    flagged = fn("meeting with Dr. Evans, Monday 5:15 PM",
                 "at 5:15", "so I have a hard stop", "")
    if not any("Evans" in f for f in flagged):
        raise LegFailed('unsupported_names() no longer flags "Dr. Evans" against '
                        "audio that never contained it — the Earl's regression "
                        "is back (plan #2b)")
    if not re.search(r"made_up\s*=\s*\(?\s*unsupported_names", core):
        raise LegFailed("unsupported_names() catches the case but the ambient act "
                        "path no longer calls it (was anticipy_core.py ~:1808)")
    return ('goal-level name guard works and is wired — "Dr. Evans" was '
            "invented at the VOICE layer, which leg 5 tracks")


# --------------------------------------------------------------------------
# LEG 4 — ARITHMETIC IS COMPUTED, NEVER SEARCHED, NEVER HELD  (plan #3, ~0.5d)
#
# "5 PM CST is what PST" wanted one number: 3 PM. It became a web-research
# answer whose only time was a 6 AM example, AND a job held for approval —
# "i'm holding the 5 pm cst conversion to pst". This leg executes the REAL
# regex from the shipped source: if "Convert 5 PM CST to PST" does not match
# _READ_ONLY_RE, is_consequential's fallback holds it, verbatim:
#     return not _READ_ONLY_RE.search(g)
# --------------------------------------------------------------------------
def leg_4_compute_lane() -> str:
    core = read(CORE)
    # The REAL organ, end to end — never the word list. An earlier version
    # of this leg tested that _READ_ONLY_RE contained compute verbs, which
    # invited exactly the fix HARNESS-LAWS forbids (extending the tape). The
    # honest question is behavioral: does the shipped is_consequential()
    # hold a timezone conversion? Does it still hold a SEND that merely
    # wears computation words?
    import sys as _sys
    if ROOT not in _sys.path:
        _sys.path.insert(0, ROOT)
    from brain.anticipy_core import is_consequential
    goal = "Convert 5 PM CST to PST"
    if is_consequential(goal):
        raise LegFailed(f'is_consequential({goal!r}) still holds a timezone '
                        "conversion for approval, exactly as it did live "
                        "(outbound auv9ieyhcvhy1nu) — classify by CAPABILITY "
                        "(can the calculator satisfy it?), not by verb (plan #3)")
    if not is_consequential("send the 5 PM CST to PST conversion to Tejas"):
        raise LegFailed("a goal that wears computation words but SENDS is no "
                        "longer held — the capability test must never outrank "
                        "the irreversible check")
    # The brain's own channel declaration is the primary classification —
    # meaning from the model, enforcement from the gate, deny-list on top.
    if is_consequential("work out what 5 PM CST is out west",
                        touches="compute"):
        raise LegFailed("a declared compute goal is still held when no word "
                        "list recognises the phrasing — the model's channel "
                        "declaration is not being honored")
    if not is_consequential("plan dinner with the team Thursday",
                            touches="world"):
        raise LegFailed('a declared "world" goal runs unattended because its '
                        "wording reads read-only — the declaration must hold it")
    if not is_consequential("send the update to Tejas", touches="compute"):
        raise LegFailed('declaring "compute" on a SEND makes it run — the '
                        "deny-list no longer outranks the model")
    if '"touches"' not in read(ORCH):
        raise LegFailed("the triage contract no longer asks for the channel — "
                        "the gate is enforcing a declaration nobody makes")
    # The other half of plan #3 is run, not grepped: the real compute organ
    # must produce the actual number the owner wanted (3 PM), and the core
    # must call it. It is stdlib-only by contract, so importing it is safe.
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tejas_gate_compute", os.path.join(ROOT, "brain", "compute.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except FileNotFoundError:
        raise LegFailed("the conversion is no longer held, but nothing COMPUTES "
                        "it either — brain/compute.py does not exist, so it "
                        "still goes to web research and comes back without "
                        "the number (plan #3)")
    answer = mod.compute_answer("Convert 5 PM CST to PST")
    if not answer or "3 PM" not in answer:
        raise LegFailed(f"compute_answer() returned {answer!r} for the recorded "
                        'goal — the owner wanted "3 PM" and still is not '
                        "getting it")
    if "compute_answer" not in core:
        raise LegFailed("the compute organ exists and is right, but the brain "
                        "never calls it — anticipy_core.py has no reference "
                        "to compute_answer")
    return f'read-only, and computed: {answer!r}'


# --------------------------------------------------------------------------
# LEG 5 — NO INVENTED NAMES IN OUTGOING TEXT  (plan #4, ~0.5d)
#
# The voice pass runs at temperature 0.7 under "name the actual thing (the
# person)". Asked to name a person when none exists, it wrote "Dr. Evans".
# The digit guard (anticipy_core.py ~:1349) already strips unheard numbers;
# this leg wants the same for name-shaped tokens.
# --------------------------------------------------------------------------
def leg_5_name_guard() -> str:
    core = read(CORE)
    if "invented_names" not in core:
        raise LegFailed('outgoing text has a guard for unheard digits and none for '
                        'unheard NAMES — "Dr. Evans" walked straight through '
                        "(plan #4)")
    # Run the REAL guard against the recorded invention: the voice pass wrote
    # "Dr. Evans" into a text whose entire allowed vocabulary named nobody.
    consts = "\n".join(m.group(0) for m in re.finditer(
        r"_(?:HONORIFIC|SENTENCE_START)_RE\s*=\s*re\.compile\([^\n]*\)", core))
    if not consts:
        raise LegFailed("invented_names exists but its regex constants are "
                        "gone — the leg cannot be tested")
    fn = extract_function(core, "invented_names",
                          prelude='import json\nNAME = "Anticipy"\n'
                                  + consts + "\n")
    ctx = {"heard": "At 5:15",
           "goal": "Schedule meeting for Monday, August 24 at 5:15 PM PDT"}
    flagged = fn("I'm holding the meeting with Dr. Evans, Monday 5:15 PM. "
                 "Want me to lock it in?", ctx)
    if not any("Evans" in f for f in flagged):
        raise LegFailed(f'invented_names() returned {flagged!r} — it no longer '
                        'catches "Dr. Evans", the exact recorded invention')
    if fn("Got the Monday 5:15 PM meeting ready. Want me to go ahead?", ctx):
        raise LegFailed("the guard flags clean text — every composition would "
                        "fall back to templates, which silently deletes her "
                        "voice")
    voice_tail = core.split("def _voice", 1)[-1][:1500]
    if "invented_names" not in voice_tail:
        raise LegFailed("invented_names exists but _voice() never consults it — "
                        "the mouth is still unguarded")
    return 'the real guard catches "Dr. Evans" and passes clean text'


# --------------------------------------------------------------------------
# LEG 6 — THE SPEAKER TAGGER IS ACTUALLY LINKED  (build 76)
#
# SpeakerTagger.swift exists. VoiceEnrollView.swift exists. A 25MB
# speaker-embedding.onnx ships in Resources of every build. And the target's
# packageProductDependencies is an EMPTY LIST, so the engine that runs it all
# is not linked. Second shipped-disconnected component in this app.
# --------------------------------------------------------------------------
def leg_6_speaker_linked() -> str:
    pbx = read(PBX)
    m = re.search(r"packageProductDependencies\s*=\s*\(([^)]*)\)", pbx)
    if not m:
        raise LegFailed("no packageProductDependencies section found in the project")
    body = m.group(1).strip().rstrip(",").strip()
    if not body:
        raise LegFailed("packageProductDependencies is an EMPTY LIST: the speaker "
                        "engine is not linked, while the 25MB model still ships in "
                        "every build. speaker stays empty on every event until "
                        "somebody adds the package product to the target (build 76)")
    if "sherpa" not in pbx.lower():
        raise LegFailed("a package product is linked but it is not the speech/"
                        "speaker engine")
    return "the speaker engine is linked into the target"


# --------------------------------------------------------------------------
# LEG 7 — THE RECOGNIZER KNOWS ITS OWN NAME  (build 76)
#
# ASR turned "anticipy growth ... dot com" into "anticipate growth there's
# something.com", and she offered to buy the misspelling of her own product.
# SFSpeechRecognizer accepts contextualStrings for exactly this.
# --------------------------------------------------------------------------
def leg_7_self_lexicon() -> str:
    listener = read(LISTENER)
    if "contextualStrings" not in listener:
        raise LegFailed('the recognizer is never given contextualStrings, so '
                        '"Anticipy" arrives as "anticipate" and its own name is '
                        "the word it mishears most (build 76)")
    if "Anticipy" not in re.sub(r"//.*", "", listener).split("contextualStrings")[-1][:400]:
        raise LegFailed("contextualStrings is set but the product's own name is "
                        "not in it")
    return "the recognizer is taught its own vocabulary"


# --------------------------------------------------------------------------
# LEG 8 — THE RECORDED CALL STAYS THE BASELINE
#
# The eval data must keep matching what this gate believes about it. If the
# files are edited or trimmed, every other leg is testing against a memory.
# --------------------------------------------------------------------------
def leg_8_eval_intact() -> str:
    tr = json.loads(read(os.path.join(EVAL, "call_transcripts.json")))
    if len(tr) != 137:
        raise LegFailed(f"call_transcripts.json has {len(tr)} lines, expected 137")
    acts = [t for t in tr if t.get("decision") == "act"]
    if len(acts) != 6:
        raise LegFailed(f"{len(acts)} recorded acts, expected 6")
    shards = sum(1 for t in tr if len((t.get("text") or "").split()) <= 4)
    if not (0.50 <= shards / len(tr) <= 0.60):
        raise LegFailed(f"shard rate {shards}/{len(tr)} drifted from the recorded 54%")
    goals = " | ".join((a.get("goal") or "") for a in acts)
    for needle in ("anticipate", "5:15", "CST"):
        if needle not in goals:
            raise LegFailed(f"the recorded act goals no longer contain {needle!r} — "
                            "the eval has been altered")
    return "137 lines, 6 acts, 54% shards — the baseline is intact"


LEGS = [
    (1, "A MEETING IS A POSTURE", leg_1_meeting_posture),
    (2, "A SHARD CANNOT MINT A MEETING", leg_2_shard_floor),
    (3, "UNRESOLVED NAMES ASK, NEVER ACT", leg_3_entity_guard),
    (4, "ARITHMETIC IS COMPUTED, NOT HELD", leg_4_compute_lane),
    (5, "NO INVENTED NAMES GO OUT", leg_5_name_guard),
    (6, "THE SPEAKER TAGGER IS LINKED", leg_6_speaker_linked),
    (7, "THE RECOGNIZER KNOWS ITS NAME", leg_7_self_lexicon),
    (8, "THE BASELINE IS INTACT", leg_8_eval_intact),
]


def main() -> int:
    print()
    print(f"  TEJAS GATE   tree: {ROOT}")
    print(f"               eval: research/evals/call-2026-08-23-tejas")
    print("  " + "-" * 62)
    first = None
    for num, name, fn in LEGS:
        try:
            detail = fn()
            print(f"  [{num}] PASS  {name}")
            print(f"        {detail}")
        except LegFailed as e:
            mark = "FAIL" if first is None else "fail"
            print(f"  [{num}] {mark}  {name}")
            print(f"        {e}")
            if first is None:
                first = (num, name, str(e))
        except Exception as e:  # noqa: BLE001
            print(f"  [{num}] FAIL  {name}")
            print(f"        gate itself errored: {e}")
            if first is None:
                first = (num, name, f"gate errored: {e}")
    print("  " + "-" * 62)
    if first is None:
        print("  DONE — the next call like this one works")
        print()
        return 0
    num, name, why = first
    print(f"  NOT DONE - first failing leg: {num} ({name})")
    print(f"  {why}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
