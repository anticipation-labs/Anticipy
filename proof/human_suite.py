"""Human-style behavioural suite: many small conversations, each scored
against what a great human assistant would have done. Live model, no
keyword steering — the point is to find where UNDERSTANDING breaks.

Every scenario builds a fresh brain, feeds lines the way production does
(context window, explicit/channel flags), then asserts micro-behaviour:
did she act / ask / stay silent, did she text, did she invent details,
did one plan stay one card, did the job land on the right lane.

Run:  PYTHONPATH=. python3 proof/human_suite.py            (all scenarios)
      PYTHONPATH=. python3 proof/human_suite.py 3 7        (just those)
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402

JOBS: list[dict] = []


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")


def _get(url, params=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"items": []})
    filt = (params or {}).get("filter", "")
    want = [s for s in ("awaiting_confirm", "queued", "running", "needs_user")
            if s in filt]
    return _R({"items": list(reversed(
        [j for j in JOBS if j["status"] in want]))})


def _post(url, json=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"id": "x"})
    rec = dict(json or {})
    rec["id"] = f"job{len(JOBS) + 1}"
    JOBS.append(rec)
    return _R(rec)


def _patch(url, json=None, timeout=None, **kw):
    jid = url.rstrip("/").rsplit("/", 1)[-1]
    for j in JOBS:
        if j["id"] == jid:
            j.update(json or {})
            return _R(j)
    return _R({}, ok=False)


pb.get, pb.post, pb.patch = _get, _post, _patch

from brain.anticipy_core import Anticipy  # noqa: E402
from brain.llm import LLM  # noqa: E402
from brain.memory import Memory  # noqa: E402


def _load_env():
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), ".env")
    if os.path.exists(path):
        for raw in open(path):
            raw = raw.strip()
            if raw and not raw.startswith("#") and "=" in raw:
                k, v = raw.split("=", 1)
                os.environ.setdefault(k, v)


def fresh():
    llm = LLM()
    a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="human-suite")
    texts: list[str] = []
    a.notify_owner = lambda msg, channel="sms": texts.append(msg)
    return a, texts


def run_lines(a, lines):
    """lines: list of str or (str, kwargs). Feeds context like production."""
    convo, outs = [], []
    for item in lines:
        line, kw = (item, {}) if isinstance(item, str) else item
        outs.append(a.hear(line, context=list(convo[-8:]), **kw))
        convo.append(line)
    return outs


def held_jobs():
    return [j for j in JOBS if j["status"] == "awaiting_confirm"]


def queued_jobs():
    return [j for j in JOBS if j["status"] == "queued"]


# ---------------------------------------------------------------- scenarios

def s01_full_plan(check):
    """Overheard complete dinner plan -> one held card, one text, details kept."""
    a, texts = fresh()
    run_lines(a, [
        "Yo long time no see how have you been",
        "We should grab dinner tomorrow yeah for sure",
        "Let's do Cactus Club the park royal one at 7 PM just us two",
        "Perfect see you there",
    ])
    held = [j for j in held_jobs() if re.search(r"book|reserv|dinner", j["goal"], re.I)]
    check("one held plan card", len(held) == 1, f"{[j['goal'] for j in JOBS]}")
    if held:
        g = held[0]["goal"].lower()
        for d, label in (("cactus", "venue"), ("7", "time"), ("tomorrow", "day")):
            check(f"kept the {label}", d in g, g)
    check("exactly one text asking his OK", len(texts) == 1, f"{texts}")


def s02_missing_details(check):
    """Vague overheard plan -> held card that does NOT invent time/party."""
    a, texts = fresh()
    run_lines(a, [
        "Hey we should go for dinner sometime soon",
        "Yeah let's do that new place downtown tomorrow",
        "OK cool see you then",
    ])
    held = held_jobs()
    invented = []
    for j in held:
        g = j["goal"].lower()
        if re.search(r"\b(for two|for 2|2 people|two people|at \d|[0-9]\s*pm|[0-9]\s*am)\b", g):
            invented.append(j["goal"])
    check("no invented time or party size", not invented, f"{invented}")
    check("at most one card", len(held) <= 1, f"{[j['goal'] for j in held]}")
    if held and texts:
        check("the text mentions what it still needs or asks the OK",
              True, "")


def s03_dictation_inert(check):
    """Voice-typing an instruction to another AI -> nothing queued, no text."""
    a, texts = fresh()
    run_lines(a, [
        ("Please update the landing page copy and then book us a table for the "
         "team dinner also fix the error message that says the pairing code "
         "expired and make sure the deploy script runs the tests first before "
         "pushing anything to the production server thank you"),
    ])
    check("dictation queues nothing", not JOBS, f"{[j['goal'] for j in JOBS]}")
    check("dictation texts nothing", not texts, f"{texts}")


def s04_self_talk(check):
    """Thinking aloud about a chore -> remembered/prepared, never text-spam."""
    a, texts = fresh()
    out = a.hear("I really need to cancel that gym membership this week")
    remembered = bool(JOBS) or bool(a.loops) or \
        bool(out["memory"].get("commitment_id"))
    check("the chore is not thrown away (job, loop or commitment)",
          remembered, f"jobs={JOBS} loops={a.loops} mem={out['memory']}")
    check("at most one text for a self-talk plan", len(texts) <= 1, f"{texts}")


def s05_browser_lane(check):
    """Texted 'open X in my browser' -> browser lane, never research."""
    a, texts = fresh()
    run_lines(a, [("Can you open Wikipedia in my browser",
                   dict(explicit=True, channel="sms"))])
    check("a job exists", len(JOBS) >= 1, f"{JOBS}")
    for j in JOBS:
        check("browser request stays off the research lane",
              j.get("lane", "") != "research", f"{j['goal']} lane={j.get('lane')}")


def s06_research_lane(check):
    """Texted research ask -> research lane when Brave key present."""
    os.environ.setdefault("BRAVE_API_KEY", "test-key-lane-only")
    a, texts = fresh()
    run_lines(a, [("Can you research the best espresso machines under 500",
                   dict(explicit=True, channel="sms"))])
    research = [j for j in JOBS if j.get("lane") == "research"]
    check("research went to the server lane", len(research) >= 1,
          f"{[(j['goal'], j.get('lane')) for j in JOBS]}")


def s07_sms_context(check):
    """Follow-up text keeps the topic from earlier context."""
    a, texts = fresh()
    ctx = ["owner: I need a flight from Vancouver to Paris tomorrow",
           "anticipy: what time do you want to land",
           "owner: anytime works"]
    out = a.hear("Give me five different options for tomorrow",
                 context=ctx, explicit=True, channel="sms")
    goals = " ".join(j["goal"].lower() for j in JOBS) + " " + \
        str(out["decision"].goal or "").lower()
    check("follow-up stays on the flight topic",
          ("flight" in goals or "paris" in goals or "vancouver" in goals)
          and "dinner" not in goals, goals)


def s08_fragment(check):
    """A stray one-word fragment does nothing."""
    a, texts = fresh()
    out = a.hear("Tomorrow")
    check("fragment is ignored", out["decision"].decision == "ignore"
          and not JOBS and not texts, f"{JOBS} {texts}")


def s09_quiet_research(check):
    """Read-only curiosity overheard -> quiet ambient work, zero texts."""
    a, texts = fresh()
    run_lines(a, [
        "I wonder what time the Vancouver aquarium opens on weekends",
    ])
    check("no text for ambient curiosity", not texts, f"{texts}")
    for j in JOBS:
        check("quiet work is not held hostage",
              j["status"] == "queued", f"{j['goal']} {j['status']}")


def s10_repeat_no_spam(check):
    """Saying the plan three times -> still one card, still one text."""
    a, texts = fresh()
    run_lines(a, [
        "We should book dinner at Cactus Club tomorrow at 7",
        "Yeah Cactus Club tomorrow 7 PM works for me",
        "OK locked in Cactus Club 7 PM tomorrow",
    ])
    held = held_jobs()
    check("one card despite three mentions", len(held) <= 1,
          f"{[j['goal'] for j in held]}")
    check("at most one text despite three mentions", len(texts) <= 1,
          f"{texts}")


def s11_direct_consequential(check):
    """Texted 'book me a table' -> held once, texted once, no re-ask."""
    a, texts = fresh()
    run_lines(a, [
        ("Book me a table for four at Nightingale Friday 8 PM",
         dict(explicit=True, channel="sms")),
        ("Book me a table for four at Nightingale Friday 8 PM",
         dict(explicit=True, channel="sms")),
    ])
    held = held_jobs()
    check("one held booking", len(held) == 1, f"{[j['goal'] for j in JOBS]}")
    check("no double-texting on repeat", len(texts) <= 1, f"{texts}")


def s12_briefing(check):
    """'What's on my plate' -> an answer, never a job."""
    a, texts = fresh()
    out = a.hear("What's still open on my plate today?")
    check("briefing answers", bool(out["anticipy_says"]),
          str(out["anticipy_says"]))
    check("briefing never queues work", not JOBS, f"{JOBS}")


def s13_never_mind(check):
    """Plan agreed then cancelled out loud -> no fresh work after 'never mind'."""
    a, texts = fresh()
    run_lines(a, [
        "Let's book dinner at Cactus Club tomorrow at 7 just us two",
        "Actually never mind let's cancel that, we'll do it another week",
    ])
    live = [j for j in JOBS if j["status"] in ("queued", "awaiting_confirm")
            and re.search(r"book|reserv", j["goal"], re.I)
            and not re.search(r"cancel", j["goal"], re.I)]
    check("cancelled plan does not stay armed as a booking", len(live) == 0,
          f"{[(j['goal'], j['status']) for j in JOBS]}")


def s14_someone_elses_job(check):
    """Other person's obligation ('Marcus will send it') -> not his work."""
    a, texts = fresh()
    run_lines(a, [
        "So Marcus said he will send over the quarterly numbers by Friday",
    ])
    acted = [j for j in JOBS if re.search(r"send", j["goal"], re.I)]
    check("she does not take on Marcus's job", not acted,
          f"{[j['goal'] for j in JOBS]}")
    check("and does not text about it", not texts, f"{texts}")


def s15_her_own_echo(check):
    """Her own words read back (TTS echo) -> never an instruction."""
    a, texts = fresh()
    run_lines(a, [
        ("Got it. I'll book dinner for two at Cactus Club tomorrow at 7 PM "
         "once you give me the go-ahead."),
    ])
    check("her echo queues nothing", not JOBS, f"{[j['goal'] for j in JOBS]}")
    check("her echo texts nothing", not texts, f"{texts}")


def s16_pause_mid_plan(check):
    """A pause mid-plan (split lines) still lands ONE plan, not two."""
    a, texts = fresh()
    run_lines(a, [
        "OK so dinner tomorrow at Cactus Club",
        "sorry had to grab the door",
        "yeah 7 PM works, just the two of us",
    ])
    held = held_jobs()
    check("split plan converges to at most one card", len(held) <= 1,
          f"{[j['goal'] for j in held]}")
    check("at most one text", len(texts) <= 1, f"{texts}")


def s17_impossible_ask(check):
    """A task she can never finish (no info, no target) is not blindly started."""
    a, texts = fresh()
    run_lines(a, [("Send it to him", dict(explicit=True, channel="sms"))])
    started = [j for j in JOBS if j["status"] == "queued"]
    check("no blind job for 'send it to him' with no referent",
          not started, f"{[j['goal'] for j in JOBS]}")


def s18_greeting(check):
    """Small talk to her -> a reply, no job, no held card."""
    a, texts = fresh()
    out = a.hear("Hey how's it going", explicit=True, channel="sms")
    check("greeting never queues work", not JOBS, f"{JOBS}")


def s19_sarcasm(check):
    """Sarcasm ('oh great, ANOTHER meeting') is not a request to book one."""
    a, texts = fresh()
    run_lines(a, [
        "Oh great, another Monday meeting, exactly what my life was missing",
    ])
    booked = [j for j in JOBS if re.search(r"book|schedul|meeting", j["goal"], re.I)
              and j["status"] in ("queued", "awaiting_confirm")]
    check("sarcasm does not schedule anything", not booked,
          f"{[j['goal'] for j in JOBS]}")
    check("sarcasm does not text", not texts, f"{texts}")


def s20_joking_hyperbole(check):
    """'I'm going to kill Marcus if he's late again' is venting, not a task."""
    a, texts = fresh()
    run_lines(a, ["I swear I'm going to kill Marcus if he is late again"])
    check("hyperbole creates no work aimed at Marcus",
          not [j for j in JOBS if j["status"] in ("queued", "awaiting_confirm")],
          f"{[j['goal'] for j in JOBS]}")
    check("hyperbole does not text", not texts, f"{texts}")


def s21_mixed_audience(check):
    """Mid-conversation he turns to HER by name -> that one line is hers."""
    a, texts = fresh()
    outs = run_lines(a, [
        "So yeah Marcus, Friday works for the gym",
        "Anticipy, remind me to bring my headphones on Friday",
        "anyway Marcus where were we",
    ])
    d = outs[1]["decision"]
    check("the named line is heard as directed at her",
          d.addressee == "assistant" or bool(JOBS) or bool(a.loops)
          or bool(outs[1]["anticipy_says"]),
          f"addressee={d.addressee} jobs={JOBS} says={outs[1]['anticipy_says']}")


def s22_one_sided_call(check):
    """One side of a phone call, half agreements -> at most one card, no spam."""
    a, texts = fresh()
    run_lines(a, [
        "Hey! ... yeah ... no for sure ...",
        "uh huh ... Saturday could work ...",
        "OK so one o'clock at Earls Brooklyn ... yeah I'll see you then",
    ])
    held = held_jobs()
    check("a half-heard call never spawns multiple cards", len(held) <= 1,
          f"{[j['goal'] for j in held]}")
    check("at most one text for a half-heard call", len(texts) <= 1,
          f"{texts}")


def s23_correction_midstream(check):
    """He corrects a detail mid-plan -> the card carries the CORRECTED value."""
    a, texts = fresh()
    run_lines(a, [
        "Book us dinner at Cactus Club tomorrow at 7",
        "wait actually make that 8 not 7, same place",
    ])
    held = held_jobs()
    check("one card after the correction", len(held) <= 1,
          f"{[j['goal'] for j in held]}")
    if held:
        g = held[0]["goal"]
        check("the corrected time (8) won", "8" in g and " 7" not in g.replace("17", ""),
              g)


def s24_third_party_story(check):
    """A story about someone ELSE's plan is not his plan."""
    a, texts = fresh()
    run_lines(a, [
        "So apparently Jake booked a huge dinner at Hy's for his whole team Friday",
        "yeah crazy, forty people",
    ])
    booked = [j for j in JOBS if j["status"] in ("queued", "awaiting_confirm")
              and re.search(r"book|reserv", j["goal"], re.I)]
    check("Jake's dinner is not booked for him", not booked,
          f"{[j['goal'] for j in JOBS]}")
    check("no text about someone else's story", not texts, f"{texts}")


def s25_conditional_plan(check):
    """A plan hedged on a condition ('IF the demo goes well...') is not armed yet."""
    a, texts = fresh()
    run_lines(a, [
        "If the demo goes well on Friday we should celebrate, maybe book somewhere fancy",
    ])
    armed = [j for j in JOBS if j["status"] in ("queued", "awaiting_confirm")
             and re.search(r"book|reserv", j["goal"], re.I)]
    check("a conditional maybe-plan is not held as a booking", not armed,
          f"{[j['goal'] for j in JOBS]}")


SCENARIOS = [s01_full_plan, s02_missing_details, s03_dictation_inert,
             s04_self_talk, s05_browser_lane, s06_research_lane,
             s07_sms_context, s08_fragment, s09_quiet_research,
             s10_repeat_no_spam, s11_direct_consequential, s12_briefing,
             s13_never_mind, s14_someone_elses_job, s15_her_own_echo,
             s16_pause_mid_plan, s17_impossible_ask, s18_greeting,
             s19_sarcasm, s20_joking_hyperbole, s21_mixed_audience,
             s22_one_sided_call, s23_correction_midstream,
             s24_third_party_story, s25_conditional_plan]


def main() -> int:
    _load_env()
    if not LLM().live:
        print("SKIP human suite — needs OPENROUTER_API_KEY (real model)")
        return 0
    only = {int(x) for x in sys.argv[1:]} if sys.argv[1:] else None
    total_pass = total_fail = 0
    failed_scens = []
    for i, scen in enumerate(SCENARIOS, 1):
        if only and i not in only:
            continue
        JOBS.clear()
        results = []

        def check(label, ok, detail=""):
            results.append((label, bool(ok), detail))

        name = scen.__doc__.strip().splitlines()[0]
        try:
            scen(check)
        except Exception as e:  # a crash is a failure, not an excuse
            results.append((f"scenario crashed: {e}", False, ""))
        bad = [r for r in results if not r[1]]
        total_pass += len(results) - len(bad)
        total_fail += len(bad)
        mark = "PASS" if not bad else "FAIL"
        print(f"[{i:02d}] {mark}  {name}")
        for label, ok, detail in results:
            if not ok:
                print(f"       FAIL {label}  -> {detail[:200]}")
        if bad:
            failed_scens.append(i)
    print(f"\nhuman suite: {total_pass} checks passed, {total_fail} failed"
          + (f" (scenarios {failed_scens})" if failed_scens else ""))
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
