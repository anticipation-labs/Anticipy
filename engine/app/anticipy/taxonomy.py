"""The fixed generated test taxonomy. Anti gaming, mandatory.

The deepest risk is the agent generating tests its own engine passes,
producing an inflated meaningless score. The defense is structural:

  1. The taxonomy, the minimum counts, and the expected decision per
     category are FIXED in this module from section 6 of the build
     spec. They are not invented per run and never reduced or reweighted
     away from the hard categories.
  2. The expected label is stamped from the category spec at generation
     time. The model that later decides never sees it and never relabels.
  3. The generator is asked only to produce realistic surface varied
     transcripts that fit a category definition. It does not assign
     labels.
  4. A separate adversarial second model reviews a sample of CORRECT
     graded answers (see grader). If it flags more than five percent,
     the grader itself is suspect and the phase fails.

Generated corpora are cached under the adapter data dir so a phase
generates its categories once and later phases reuse the exact same
cases, which keeps scores comparable across phases.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from app.anticipy import platform_adapter


@dataclass(frozen=True)
class CategorySpec:
    name: str
    min_count: int
    expected: str  # the stamped primary expected decision (always a real
                   # decision: ACT | STORE_AS_LATENT | ASK | IGNORE) or a
                   # structured rule tag for memory/whole-system checks
    definition: str
    grading: str  # which pass condition in the grader applies
    variants: tuple = field(default_factory=tuple)


# Valid decisions only. Pseudo tokens like ASK_OR_STORE are never used as
# an expected label: they leak into the adversarial reviewer as an
# invented decision and (correctly) trip the anti self deception check.
# Each category declares the SET of acceptable decisions and the single
# decision that is the hard error, in human terms, so the grader and the
# adversarial reviewer both judge against a real, meaningful criterion.
ACCEPTABLE: dict[str, dict] = {
    "EXPLICIT_COMMAND": {"accept": ("ACT",), "hard_error": None,
        "desc": "Acceptable: ACT. The WEARER directly commanded the agent."},
    "CLEAR_IMPLICIT": {"accept": ("ACT",), "hard_error": None,
        "desc": "Acceptable: ACT. A clear committed actionable WEARER task."},
    "DIRECT_USER_COMMAND": {"accept": ("ACT",), "hard_error": None,
        "desc": "Acceptable: ACT. The user deliberately addressed the agent."},
    "BOSS_DIRECTED": {"accept": ("ACT",), "hard_error": None,
        "desc": "Acceptable: ACT. A person with authority over the WEARER "
                "instructed the WEARER and the WEARER did not refuse, so it "
                "is a WEARER relevant task."},
    "HEDGED_SOCIAL": {"accept": ("STORE_AS_LATENT", "IGNORE"), "hard_error": "ACT",
        "desc": "Acceptable: STORE_AS_LATENT (best) or IGNORE. Hard error: "
                "ACT, because this is low commitment social hedging."},
    "AMBIGUOUS_ADDRESSEE": {"accept": ("ASK", "STORE_AS_LATENT"), "hard_error": "ACT",
        "desc": "Acceptable: ASK or STORE_AS_LATENT. Hard error: a silent "
                "ACT, because it is genuinely unclear whether the task was "
                "meant for the agent or for another human present."},
    "SARCASM_AND_NEGATION": {"accept": ("IGNORE", "STORE_AS_LATENT"), "hard_error": "ACT",
        "desc": "Acceptable: IGNORE or STORE_AS_LATENT. Hard error: ACT on "
                "the literal reading, because the real intent is sarcastic "
                "or negated."},
    "PURE_AMBIENT_NEGATIVE": {"accept": ("IGNORE",), "hard_error": "ACT",
        "desc": "Acceptable: IGNORE. There is no task for the agent. Hard "
                "error: ACT or ASK (a false trigger)."},
    "MULTI_SPEAKER_CROSSTALK": {"accept": ("ACT",), "hard_error": None,
        "desc": "Acceptable: ACT on the one embedded real WEARER task. Any "
                "error must be in the safe direction, never a silent wrong "
                "ACT on crosstalk."},
    "REFERENCE_RESOLUTION": {"accept": ("ACT", "ASK"), "hard_error": None,
        "desc": "Memory/profile present: ACT. Absent: ASK (never a guessed "
                "ACT)."},
    "NEVERMIND_RECONCILIATION": {"accept": ("IGNORE", "STORE_AS_LATENT"), "hard_error": "ACT",
        "desc": "The task was retracted. The final memory state must show "
                "no active intent. Hard error: ACT on the retracted task."},
}


def accept_set(category: str, variant=None) -> tuple:
    if category == "REFERENCE_RESOLUTION":
        return ("ACT",) if variant == "present" else ("ASK",)
    return ACCEPTABLE.get(category, {}).get("accept", ())


def criterion_text(category: str, variant=None) -> str:
    if category == "REFERENCE_RESOLUTION":
        return ("Acceptable: ACT (the reference resolves from memory or "
                "profile)." if variant == "present"
                else "Acceptable: ASK only. A guessed ACT is the hard error "
                "because the reference cannot be resolved.")
    return ACCEPTABLE.get(category, {}).get("desc", "")


# Engine core categories, phases P1 to P5.
ENGINE_CORE: dict[str, CategorySpec] = {
    "EXPLICIT_COMMAND": CategorySpec(
        "EXPLICIT_COMMAND", 60, "ACT",
        "The WEARER directly and unambiguously commands the agent to do a "
        "specific task, addressing the agent or stating the task as an "
        "imperative with enough specificity to execute. Example shape: "
        "book a table, send this email, set this reminder, order this.",
        "exact>=0.92",
    ),
    "CLEAR_IMPLICIT": CategorySpec(
        "CLEAR_IMPLICIT", 60, "ACT",
        "The WEARER clearly states an actionable task they need done, not "
        "addressed to the agent but plainly a concrete task with a clear "
        "object and near term intent. Example shape: I need to email Sarah "
        "the deck before end of day.",
        "exact>=0.92",
    ),
    "DIRECT_USER_COMMAND": CategorySpec(
        "DIRECT_USER_COMMAND", 60, "ACT",
        "The user deliberately addresses the agent through the direct "
        "command channel (typed in the app or texted to the agent) with "
        "an ACTION to perform in the world: book, schedule, reschedule, "
        "cancel, send, email, order, reorder, add to a list, set a "
        "reminder or timer, draft, post. Example: 'book the dinner', "
        "'reschedule my 3pm', 'add milk to my list', 'email Sam the "
        "deck'. It is a command to DO something, never a pure "
        "information question (no bare 'what is the weather', 'how many "
        "steps did I take'). One WEARER line only. Highest authority, "
        "lowest uncertainty path, addressee detection is bypassed.",
        "exact>=0.92",
    ),
    "BOSS_DIRECTED": CategorySpec(
        "BOSS_DIRECTED", 40, "ACT",
        "Another speaker who is the WEARER's boss or authority instructs "
        "the WEARER to do something, and the WEARER assents or does not "
        "object. The instruction to the WEARER is itself a WEARER relevant "
        "actionable task.",
        "exact>=0.92",
    ),
    "HEDGED_SOCIAL": CategorySpec(
        "HEDGED_SOCIAL", 60, "STORE_AS_LATENT",
        "Social hedging, hypotheticals, low commitment language: we should "
        "maybe grab dinner sometime, we could look into that at some point. "
        "A real but uncommitted signal. ACT here is a hard failure.",
        "overaction<=0.03",
    ),
    "AMBIGUOUS_ADDRESSEE": CategorySpec(
        "AMBIGUOUS_ADDRESSEE", 50, "ASK",
        "There MUST be at least one non WEARER speaker present and the "
        "target of a task shaped utterance MUST remain genuinely unclear "
        "even after reading the whole transcript. HARD EXCLUSIONS, never "
        "generate these here: (1) a person with authority over the "
        "WEARER instructing the WEARER who then accepts or acknowledges "
        "('Sure', 'On it', 'I'll take care of it') that is BOSS_DIRECTED, "
        "not ambiguous; (2) the WEARER clearly accepting or claiming the "
        "task themselves; (3) a clean solo request to an assistant. The "
        "ambiguity must persist: e.g. the WEARER says 'can you send that "
        "over?' with a colleague present and NOBODY clearly accepts or "
        "is named, or a speaker says 'can someone handle this?' with no "
        "named target and no clear acceptance. No speaker may clearly "
        "take ownership. The right outcomes are ASK or STORE_AS_LATENT, "
        "never a silent ACT.",
        "no_silent_act",
    ),
    "SARCASM_AND_NEGATION": CategorySpec(
        "SARCASM_AND_NEGATION", 40, "IGNORE",
        "Sarcasm or negation where the literal surface looks like a "
        "command but the real intent is the opposite or none. Oh great, "
        "let us definitely book the most expensive place. Never act on "
        "the literal reading.",
        "overaction<=0.03",
    ),
    "PURE_AMBIENT_NEGATIVE": CategorySpec(
        "PURE_AMBIENT_NEGATIVE", 100, "IGNORE",
        "Ordinary conversation with no task for the agent at all: small "
        "talk, observation, narration, third party gossip, opinions. The "
        "expected decision is IGNORE. This governs the false ACT budget.",
        "overaction<=0.03",
    ),
    "REFERENCE_RESOLUTION": CategorySpec(
        "REFERENCE_RESOLUTION", 50, "VARIANT",
        "A SINGLE speaker (WEARER only, no other speaker) states a clear "
        "actionable first person task whose key object is a vague "
        "reference that can ONLY be resolved from prior memory or the "
        "profile. The task itself must be unambiguous and clearly the "
        "WEARER's own (no 'us'/'we'/'our' group framing, no question to "
        "another person, that is a different category). Use ONE of these "
        "exact reference phrases verbatim somewhere in the line: 'the "
        "usual place', 'the usual order', 'my usual spot', 'the boss', "
        "'the team', 'my regular'. Example shapes: 'Book the usual place "
        "for Friday at 7.', 'Email the boss the Q3 report.', 'Reorder my "
        "usual order.'",
        "reference",
        ("present", "absent"),
    ),
    "MULTI_SPEAKER_CROSSTALK": CategorySpec(
        "MULTI_SPEAKER_CROSSTALK", 40, "ACT",
        "Three or more speakers, overlapping topics, with exactly one "
        "embedded real WEARER task. The engine must extract that one task "
        "and not silently act on crosstalk. Errors must be in the safe "
        "direction.",
        "no_silent_act",
    ),
    "NEVERMIND_RECONCILIATION": CategorySpec(
        "NEVERMIND_RECONCILIATION", 30, "RETRACTED",
        "The WEARER states a task then retracts it (actually forget that, "
        "never mind). The final memory state must show no active intent: "
        "the prior latent intent is DELETEd or UPDATEd, not duplicated.",
        "nevermind",
    ),
}

# Whole system categories, phases P7 to P9.
WHOLE_SYSTEM: dict[str, CategorySpec] = {
    "ONBOARDING_INTAKE": CategorySpec(
        "ONBOARDING_INTAKE", 30, "PROFILE",
        "A realistic 6 to 8 turn structured onboarding interview. Use "
        "speaker_id INTERVIEWER and WEARER, alternating. The INTERVIEWER "
        "asks for, and the WEARER answers with SPECIFIC concrete values: "
        "their name and role/title; one sentence on what they do; time "
        "zone and working hours; the important people, stating "
        "explicitly who 'the boss' is by name and who 'us' refers to "
        "(e.g. 'the boss is Dana, my lead investor; us means me and my "
        "cofounder Sam'); the 3 to 5 daily tools; what they want the "
        "assistant to do and an explicit do-not-touch list; how to be "
        "reached for non critical vs critical and quiet hours. The "
        "WEARER must give real specifics, never vague non answers, so a "
        "complete profile can be extracted.",
        "profile_populated",
    ),
    "COLD_START_RESOLUTION": CategorySpec(
        "COLD_START_RESOLUTION", 40, "ACT",
        "A single WEARER speaker, one clear actionable command whose "
        "object references a PERSON relation that only the onboarding "
        "profile can resolve and accumulated memory cannot, using "
        "exactly one of these relation phrases verbatim: 'the boss', "
        "'my manager', 'my cofounder', 'my assistant', 'us', 'the "
        "team'. Example shapes: 'Email the boss the Q3 deck.', 'Schedule "
        "a 1:1 with my cofounder for Friday.', 'Send the team the "
        "release notes.' The relation alone is the resolvable object, "
        "no other identifying detail, single actor, no other speakers.",
        "coldstart>=0.80",
    ),
    "THREE_INBOUND_ROUTING": CategorySpec(
        "THREE_INBOUND_ROUTING", 40, "ROUTING",
        "Mixed inputs across the three inbound paths (ambient overheard, "
        "direct user command, reply to the agent's own question). Expect "
        "correct path tagging and, for replies, correct suspended task "
        "match.",
        "routing_100",
    ),
    "ASYNC_REPLY_MATCH": CategorySpec(
        "ASYNC_REPLY_MATCH", 40, "REPLY_MATCH",
        "A freeform human reply arrives hours later and must be matched "
        "back to the correct suspended task, including the hard case of "
        "two open tasks and one vague reply (exactly one disambiguation, "
        "never a bombardment).",
        "reply_match>=0.90",
    ),
    "THREE_HOUR_RULE": CategorySpec(
        "THREE_HOUR_RULE", 40, "TIMING",
        "Simulated clock cases: default proceed on three hours of "
        "silence, money carve out waits indefinitely, ultra high risk "
        "comms carve out waits indefinitely, ambiguous high vs ultra "
        "high comms fails toward waiting.",
        "carveouts_100",
    ),
    "DURABILITY": CategorySpec(
        "DURABILITY", 30, "RESUME",
        "A workflow is killed mid execution at a journaled point. On "
        "restart it must reconstruct state and resume without re running "
        "completed steps.",
        "durability_100",
    ),
    "TENANT_ISOLATION": CategorySpec(
        "TENANT_ISOLATION", 20, "ISOLATED",
        "Two users write data. A real query proves neither can read the "
        "other's rows. A single cross tenant read is a hard build failure.",
        "isolation_100",
    ),
}

ALL_SPECS: dict[str, CategorySpec] = {**ENGINE_CORE, **WHOLE_SYSTEM}


_GEN_SYSTEM = """\
You generate realistic diarized conversation transcripts for testing an
ambient assistant's decision engine. You produce only the transcript
text. You never decide what the engine should do, you never output a
label, and you never reference the expected decision.

A transcript is a JSON array of lines. Each line is
{"speaker_id": "<label>", "text": "<spoken text>", "ts": <float seconds>}.
Exactly one speaker is the enrolled wearer and MUST use the literal
speaker_id "WEARER". Other speakers use short labels like "S2", "BOSS",
"COWORKER", "FRIEND", "SPOUSE".

Output STRICT JSON only: an array of objects, each
{"transcript": [<lines>], "tag": "<one short surface descriptor>"}.
No prose, no fences, no commentary. Vary domain widely across work,
personal, errands, travel, food, family, money talk that is not a money
action, scheduling, social plans. Vary length from one line to several
lines. Make them sound like real unscripted speech, not templated.
"""


def _corpus_path(category: str) -> "object":
    d = platform_adapter.data_dir() / "corpus"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{category}.jsonl"


def _stamp(category: str, spec: CategorySpec, case_obj: dict, variant: Optional[str]) -> dict:
    transcript = case_obj.get("transcript") or []
    expected = spec.expected
    if spec.name == "REFERENCE_RESOLUTION":
        expected = "ACT" if variant == "present" else "ASK"
    elif spec.name == "NEVERMIND_RECONCILIATION":
        expected = "RETRACTED"
    case_id = hashlib.sha1(
        (category + json.dumps(transcript, sort_keys=True)).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "case_id": case_id,
        "category": category,
        "expected": expected,
        "variant": variant,
        "grading": spec.grading,
        "transcript": transcript,
        "tag": case_obj.get("tag", ""),
    }


def _extract_json_array(raw: str) -> list:
    raw = raw.strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        arr = json.loads(raw[start : end + 1])
        return arr if isinstance(arr, list) else []
    except Exception:
        # one defensive repair pass: strip trailing commas
        repaired = re.sub(r",\s*([\]}])", r"\1", raw[start : end + 1])
        try:
            arr = json.loads(repaired)
            return arr if isinstance(arr, list) else []
        except Exception:
            return []


_VARIANT_HINT = {
    "present": (
        " For THIS batch, use EXACTLY one of these phrases verbatim as "
        "the COMPLETE object of the task, with NO domain qualifier after "
        "it: 'the usual place', 'the usual order', 'my usual spot', 'the "
        "boss', 'the team', 'my regular'. Correct: 'Reorder the usual "
        "order.', 'Book the usual place for Friday at 7.', 'Email the "
        "boss the Q3 report.', 'Schedule my regular for next week.'. "
        "WRONG, never do this: 'reorder the usual order FROM THE "
        "PHARMACY', 'book my usual spot AT THE GOLF COURSE' (a trailing "
        "domain contradicts the stored anchor and makes it a different "
        "category). The bare phrase is the whole resolvable object. "
        "Single actor WEARER command only, no other speakers, no "
        "'us'/'we'/'our', do not spell out the resolved value."
    ),
    "absent": (
        " For THIS batch, use EXACTLY one of these UNRESOLVABLE pointer "
        "phrases verbatim as the COMPLETE object, with NO other "
        "identifying detail: 'that place', 'the one we discussed', 'the "
        "thing from before', 'you know the spot', 'the place we always "
        "go', 'that thing from last time'. The WEARER issues a clear "
        "single actor command verb (book, email, send, schedule, "
        "reorder, cancel, remind me) on that bare pointer and NOTHING "
        "else identifying. Correct: 'Book that place for Friday.', "
        "'Reorder the thing from before.', 'Email the one we discussed.'. "
        "WRONG, never add a concrete handle that makes it actionable on "
        "its own ('cancel the reservation we made earlier for dinner', "
        "'update the spreadsheet from the meeting' read as complete "
        "commands). The pointer alone, genuinely unresolvable, IS the "
        "whole object. Single actor, no other speakers, no 'us'/'we'/"
        "'our'."
    ),
}


def _gen_user(category: str, spec: CategorySpec, variant: Optional[str], ask: int) -> str:
    return (
        f"CATEGORY: {category}\nDEFINITION: {spec.definition}"
        f"{_VARIANT_HINT.get(variant or '', '')}\n\n"
        f"Produce {ask} distinct cases as the specified JSON array. "
        f"Maximize surface variety. Do not reuse phrasings."
    )


def generate(category: str, n: Optional[int] = None, force: bool = False) -> list[dict]:
    """Generate (or load cached) at least the fixed minimum count of
    cases for a category. Expected labels are stamped here from the
    fixed spec, NEVER decided by a model. Cached to disk so later phases
    reuse the exact same cases.

    Generation batches are independent and their labels are stamped
    deterministically from the spec, so the batch calls run concurrently
    (model latency is the bottleneck and is highly variable; serial
    generation made the 590 case suite intractable). Concurrency is pure
    I/O wait, bounded by the resource gate.
    """
    from concurrent.futures import ThreadPoolExecutor

    spec = ALL_SPECS[category]
    target = max(n or spec.min_count, spec.min_count)
    path = _corpus_path(category)

    if path.exists() and not force:
        existing = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
        if len(existing) >= target:
            return existing[:target]

    variants = spec.variants or (None,)
    per_variant = max(1, target // len(variants))
    # Per category generation profile. Long multi turn transcripts
    # (a 6 to 8 turn onboarding interview, 3+ speaker crosstalk) do not
    # fit many per call, so use a small ask, a bigger token budget, and
    # more rounds, otherwise the run caps below the FIXED minimum count.
    # Reaching the floor honestly, never lowering it.
    profile = {
        "ONBOARDING_INTAKE": (2, 3600, 8),
        "MULTI_SPEAKER_CROSSTALK": (4, 2800, 6),
    }.get(category, (10, 2200, 4))
    chunk, gen_tokens, gen_rounds = profile

    cases: list[dict] = []
    seen: set[str] = set()

    def _add(arr, variant) -> None:
        for obj in arr:
            if not isinstance(obj, dict) or not obj.get("transcript"):
                continue
            stamped = _stamp(category, spec, obj, variant)
            if stamped["case_id"] in seen:
                continue
            seen.add(stamped["case_id"])
            cases.append(stamped)

    # Up to 4 concurrent rounds. Each round fires, for every variant,
    # enough parallel batches to cover the remaining need plus a buffer
    # for dedup and the occasional failed call.
    for _round in range(gen_rounds):
        if len(cases) >= target:
            break
        jobs: list[tuple] = []
        for variant in variants:
            have_v = sum(1 for c in cases if c.get("variant") == variant)
            need_v = max(0, per_variant - have_v)
            if need_v <= 0 and len(variants) > 1:
                continue
            n_batches = max(1, -(-need_v // chunk)) + 2  # ceil + buffer
            for _ in range(n_batches):
                jobs.append((variant, _gen_user(category, spec, variant, chunk)))
        if not jobs:
            break
        with ThreadPoolExecutor(max_workers=min(24, len(jobs))) as pool:
            futs = [
                (v, pool.submit(platform_adapter.model_call, _GEN_SYSTEM, u, gen_tokens, 0.0, False))
                for (v, u) in jobs
            ]
            for v, f in futs:
                try:
                    res = f.result()
                except Exception:
                    continue
                if res.ok:
                    _add(_extract_json_array(res.content), v)

    with path.open("w", encoding="utf-8") as fh:
        for c in cases[:target]:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return cases[:target]


def load_cached(category: str) -> list[dict]:
    path = _corpus_path(category)
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
