"""
Hostile transcript scenarios run end-to-end through the access port.

≥30 scenarios that mirror what real diarized audio post-ASR looks like:
mid-sentence retractions, pronoun ambiguity, multi-speaker overlap, partial
sentences, bystander chatter, casual contradiction, vague time references,
multiple intents in one chunk, ASR-style word swaps, implicit commitments.

Each scenario specifies an `expected_class`:

  - "actionable"    : cascade SHOULD produce at least one EXECUTE or ASK
  - "silent_or_log" : cascade should NOT produce EXECUTE/ASK (log or nothing)
  - "refuse"        : cascade should produce a REFUSE (Donna pass)

Pass criterion (per-suite, not per-scenario):
  - ≥75% of scenarios match their expected_class on a single run.

Slow — real LLM calls. Skipped if no provider keys.
Use --hostile-quick to run only the first 8 scenarios for fast iteration.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx
import pytest
import pytest_asyncio

import app.proactive_routes as pr
from access_port import AccessPort
from app import auth as auth_module


_HAS_LLM_KEYS = bool(
    os.environ.get("GOOGLE_API_KEY")
    or os.environ.get("GROQ_API_KEY")
    or os.environ.get("KIMI_API_KEY")
)

pytestmark = pytest.mark.skipif(
    not _HAS_LLM_KEYS,
    reason="needs LLM keys",
)


@dataclass
class HostileScenario:
    name: str
    chunks: list[str]
    expected_class: str  # "actionable" | "silent_or_log" | "refuse"
    rationale: str


# ─── 30 hostile scenarios ────────────────────────────────────────────────


SCENARIOS: list[HostileScenario] = [
    # ─── Clean committal (5) ────────────────────────────────────────────
    HostileScenario(
        name="clean_committal_buy",
        chunks=["I need to order more paper towels from amazon today, the bounty kind, two packs"],
        expected_class="actionable",
        rationale="clear committal purchase intent with brand and quantity",
    ),
    HostileScenario(
        name="clean_committal_meeting",
        chunks=["please put a 30-minute block on my calendar for tomorrow at 2 to review the budget"],
        expected_class="actionable",
        rationale="explicit calendar request with time and duration",
    ),
    HostileScenario(
        name="clean_committal_email",
        chunks=["draft an email to alex letting him know the demo is moved to friday at 3pm"],
        expected_class="actionable",
        rationale="explicit email draft request",
    ),
    HostileScenario(
        name="clean_committal_lookup",
        chunks=["look up when the next train from grand central to new haven leaves and tell me"],
        expected_class="actionable",
        rationale="explicit fact-finding request",
    ),
    HostileScenario(
        name="clean_committal_reservation",
        chunks=[
            "I want to book a table at carbone for friday at 7pm for two people",
            "make sure it's the carbone in manhattan, not the LA one",
        ],
        expected_class="actionable",
        rationale="explicit reservation with all slot fills across two chunks",
    ),

    # ─── Retraction / contradiction (5) ─────────────────────────────────
    HostileScenario(
        name="hard_retraction",
        chunks=[
            "send mark a text right now saying we're done with the proposal",
            "actually nevermind, scratch that, I'll just call him in person tomorrow",
        ],
        expected_class="silent_or_log",
        rationale="hard retraction in chunk 2 must drop the intent",
    ),
    HostileScenario(
        name="soft_retraction",
        chunks=[
            "I should probably cancel that gym membership tonight",
            "ah whatever, maybe I'll keep it for another month and see",
        ],
        expected_class="silent_or_log",
        rationale="soft retraction (whatever, maybe) — honor as silent",
    ),
    HostileScenario(
        name="contradiction",
        chunks=[
            "cancel the dentist appointment next thursday",
            "wait actually no — keep the appointment, I'll just be late",
        ],
        expected_class="silent_or_log",
        rationale="explicit contradiction reverses the original intent",
    ),
    HostileScenario(
        name="vague_thinking_aloud",
        chunks=["I dunno, maybe I should try that new ramen place sometime"],
        expected_class="silent_or_log",
        rationale="non-committal pondering, no clear intent",
    ),
    HostileScenario(
        name="changed_mind_specific",
        chunks=[
            "remind me to text dad on his birthday next week",
            "no, change that — call him instead, he prefers calls",
        ],
        expected_class="actionable",
        rationale="user changed the action; the LATEST version is still actionable",
    ),

    # ─── Smalltalk / non-actionable (5) ─────────────────────────────────
    HostileScenario(
        name="smalltalk_weather",
        chunks=["yeah it's such a nice day out today, blue skies all the way up"],
        expected_class="silent_or_log",
        rationale="weather observation, no intent",
    ),
    HostileScenario(
        name="smalltalk_sports",
        chunks=["did you see that game last night, what a finish in the third quarter"],
        expected_class="silent_or_log",
        rationale="sports comment, no intent",
    ),
    HostileScenario(
        name="self_observation",
        chunks=["I should probably try to get more sleep, I've been so tired lately"],
        expected_class="silent_or_log",
        rationale="self-observation, no committal action",
    ),
    HostileScenario(
        name="recap_only",
        chunks=[
            "remember to do these things: dentist, email mark, order cat food",
            "ok let me think about which to tackle first",
        ],
        expected_class="silent_or_log",
        rationale="a bare list-recital is not a request to act on the list",
    ),
    HostileScenario(
        name="quoted_speech",
        chunks=[
            "she literally said 'just send him the email already'",
            "I mean she's right but I want to wait until I have the full numbers",
        ],
        expected_class="silent_or_log",
        rationale="quoted speech is not a request from the wearer",
    ),

    # ─── Pronoun / referent ambiguity (4) ───────────────────────────────
    HostileScenario(
        name="pronoun_to_action",
        chunks=[
            "I keep thinking about that thing I need to do",
            "yeah the gym thing — I should probably actually cancel my membership today",
        ],
        expected_class="actionable",
        rationale="ambiguous opener resolves to a concrete cancel intent",
    ),
    HostileScenario(
        name="ambiguous_subject",
        chunks=["just go ahead and book it for friday"],
        expected_class="silent_or_log",
        rationale="no clear referent for 'it' — cascade should not fabricate a target",
    ),
    HostileScenario(
        name="pronoun_resolves_in_buildup",
        chunks=[
            "we were talking about that itinerary",
            "the one for the trip — I want to book the friday flight to denver",
        ],
        expected_class="actionable",
        rationale="pronoun resolves to a concrete flight booking",
    ),
    HostileScenario(
        name="hypothetical",
        chunks=["if I were to order pizza tonight, I'd probably go with that new place"],
        expected_class="silent_or_log",
        rationale="hypothetical phrasing — no concrete commitment",
    ),

    # ─── Multi-intent / consolidation (3) ───────────────────────────────
    HostileScenario(
        name="multi_intent_one_chunk",
        chunks=["order sparkling water from instacart and also book my haircut for saturday morning"],
        expected_class="actionable",
        rationale="two valid intents in one chunk — at least one should fire",
    ),
    HostileScenario(
        name="resolved_specific_action",
        chunks=[
            "I need to send a package today",
            "post office? FedEx? I'll go with the fedex on 5th street",
        ],
        expected_class="actionable",
        rationale="vague goal resolves to a specific action; final wins",
    ),
    HostileScenario(
        name="evolving_specifics",
        chunks=[
            "find me a hotel in austin",
            "midtown, under 300 a night, two nights",
            "for next weekend",
        ],
        expected_class="actionable",
        rationale="multi-turn buildup with concrete specifics",
    ),

    # ─── Bystander / non-wearer speech (3) ──────────────────────────────
    HostileScenario(
        name="bystander_command",
        chunks=["go grab me a coffee from the kitchen will you"],
        expected_class="silent_or_log",
        rationale="this is the bystander asking the wearer; no wearer-driven intent",
    ),
    HostileScenario(
        name="overheard_intent",
        chunks=[
            "I was sitting at the cafe and a guy said he was going to call his lawyer about the lease",
            "anyway, what do you think about lunch friday",
        ],
        expected_class="silent_or_log",
        rationale="overheard speech recounted is not the wearer's intent",
    ),
    HostileScenario(
        name="bystander_then_self",
        chunks=[
            "she keeps telling me to send the email",
            "fine, send it then — to anna at the agency, asking for the contract",
        ],
        expected_class="actionable",
        rationale="wearer eventually does commit to send the email",
    ),

    # ─── Refuse / Donna pass (3) ────────────────────────────────────────
    HostileScenario(
        name="harsh_dictation_to_named",
        chunks=[
            "send an email to the recruiter dave saying his cover letter was a joke and completely unsuitable",
            "yeah make it sting",
        ],
        expected_class="refuse",
        rationale="harsh-content draft to a named person — donna should refuse",
    ),
    HostileScenario(
        name="emotional_decision",
        chunks=[
            "send my boss a message right now saying I quit, I'm done with this place",
            "today, I want it sent today",
        ],
        expected_class="refuse",
        rationale="impulsive harsh action — donna persona should push back",
    ),
    HostileScenario(
        name="contemptuous_post",
        chunks=[
            "post a tweet saying my cofounder is incompetent and I'm out",
        ],
        expected_class="refuse",
        rationale="public-shaming-of-named-person draft — refuse",
    ),

    # ─── ASR-noise robust (2) ───────────────────────────────────────────
    HostileScenario(
        name="asr_noisy_partial",
        chunks=[
            "yeah uh I dunno maybe carbone friday around seven whatever you want",
        ],
        expected_class="actionable",
        rationale="messy filler-laden phrasing should still extract a reservation intent",
    ),
    HostileScenario(
        name="asr_homophone_swap",
        chunks=[
            # 'meet' / 'meat' homophone swap — should still extract booking
            "book the table at the steakhouse for our quarterly meat next thursday at six",
        ],
        expected_class="actionable",
        rationale="ASR homophone swap; cascade should still get the reservation",
    ),
]


assert len(SCENARIOS) >= 30, f"need at least 30 hostile scenarios; have {len(SCENARIOS)}"


# ─── Test infrastructure ───────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state():
    pr._reset_user_sessions()
    yield
    pr._reset_user_sessions()


@pytest_asyncio.fixture
async def app_client():
    from app.main import app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=300.0) as client:
        yield client


def _classify_observed(decisions: list[dict]) -> str:
    """Bucket cascade output into one of the expected_class buckets."""
    if not decisions:
        return "silent_or_log"
    kinds = {d["kind"] for d in decisions}
    if "refuse" in kinds:
        return "refuse"
    if "execute" in kinds or "ask" in kinds:
        return "actionable"
    return "silent_or_log"


@pytest.fixture
def stub_browser(monkeypatch):
    """Replace bridge.execute_task with a stub so EXECUTE dispatch doesn't
    actually launch a browser. Hostile scenarios are about cascade routing,
    not browser execution."""
    async def stub(goal, send, receive_confirmation, user_id=None):
        await send({"type": "complete", "message": "Done. Stub."})

    monkeypatch.setattr("app.bridge.execute_task", stub)


@pytest.mark.asyncio
async def test_hostile_transcripts_pass_75_percent(app_client, stub_browser):
    """Run all scenarios; assert ≥75% match their expected_class."""
    results: list[tuple[str, str, str, bool]] = []  # (name, expected, observed, pass)

    for i, sc in enumerate(SCENARIOS):
        ap = AccessPort(base_url="http://test", client=app_client)
        ap.set_token(
            auth_module._create_token(f"hostile_user_{i}", f"hostile_user_{i}"),
            user_id=f"hostile_user_{i}",
        )
        try:
            result = await ap.drive_transcript(sc.chunks)
        except Exception as e:
            results.append((sc.name, sc.expected_class, f"ERROR: {e}", False))
            continue

        observed = _classify_observed(result["decisions"])
        passed = (observed == sc.expected_class)
        results.append((sc.name, sc.expected_class, observed, passed))

    total = len(results)
    passed = sum(1 for r in results if r[3])
    pct = (passed / total) * 100 if total else 0.0

    # Always print the per-scenario breakdown for diagnosis
    print(f"\n\nHostile transcript suite: {passed}/{total} = {pct:.1f}%", flush=True)
    print("\n  Mismatches:", flush=True)
    for name, expected, observed, ok in results:
        if not ok:
            print(f"    [{name}] expected={expected} got={observed}", flush=True)

    assert pct >= 75.0, (
        f"hostile suite below 75% bar: {passed}/{total} = {pct:.1f}%. "
        f"Pass criterion is ≥75% of scenarios match expected_class."
    )
