"""Test: the clarifying-call BRAIN (onboarding/clarify.py) + its HTTP surface.

Omar's onboarding: "it jumps on a phone call to clarify — can I ask you a couple
of questions?" clarify.py decides WHAT Anticipy asks and IN WHAT ORDER, given a
built Profile. The phone delivery (Twilio voice) is live-deferred; this proves
the planner and the endpoint, deterministically, with NO live browser.

Covers:
  - a fixture Profile carrying (a) a SOURCE DISAGREEMENT (two locations), (b) a
    BLOCKER (a source that couldn't be read), and (c) a LOW-CONFIDENCE fact
    (needs_cross_check role) yields exactly the right questions, ordered
    most-uncertain first: disagreement -> low_confidence -> blocker -> gap.
  - each question carries {field, question_text, why, candidates} and the
    disagreement carries the conflicting values as candidates.
  - honesty: a clean, high-confidence, agreeing field earns NO question; we never
    invent a disagreement; a field covered by a disagreement isn't re-asked as a
    low-confidence question.
  - the ~5 cap holds (most-uncertain kept).
  - GET/POST /onboarding/clarify returns the questions for a built profile
    (through an injected fake reader, no live browser), owner-gated, and degrades
    honestly (no browser -> blocker question, browser_available=false).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_clarify.py
"""
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ.setdefault("ANTICIPY_DATA_DIR", tempfile.mkdtemp(prefix="anticipy-clarify-"))
os.environ.setdefault("ANTICIPY_BROWSERUSE_PYTHON", "/nonexistent/anticipy/bridge/python")

from anticipy_engine.onboarding.profile_builder import Profile, ProfileFact, Source  # noqa: E402
from anticipy_engine.onboarding.clarify import (  # noqa: E402
    clarifying_questions,
    clarify_payload,
    ClarifyingQuestion,
)


WIKI = "https://en.wikipedia.org/wiki/Example_Person"
COMPANY = "https://acme.example/about"
BLOCKED = "https://walled.example/private"


def _fixture_profile() -> Profile:
    """A built profile with the three uncertainties a real call must resolve:

      - org agrees across both sources (Acme Corp) and is fine/needs_cross_check
        on its own, but since both sources gave the SAME value we still confirm
        it as low-confidence — and it must NOT be a disagreement.
      - location DISAGREES: WIKI says 'Austin, Texas', COMPANY says 'Seattle'.
      - role is a single LOW-CONFIDENCE fine pull (needs_cross_check) -> confirm.
      - BLOCKED source could not be read -> a blocker.
      - 'overview' coarse facts are clean/high-trust and must earn NO question.
    """
    facts = [
        # coarse overview facts — clean, must NOT generate questions
        ProfileFact("overview", "Example Person, an engineer at Acme.", WIKI, "medium", False, "coarse"),
        ProfileFact("overview", "Acme Corp, founded by Example Person.", COMPANY, "medium", False, "coarse"),
        # role: single low-confidence fine pull -> confirm
        ProfileFact("role", "Founder and engineer", WIKI, "low", True, "fine"),
        # org: agrees across sources -> low-confidence confirm, NOT a disagreement
        ProfileFact("org", "Acme Corp", WIKI, "low", True, "fine"),
        ProfileFact("org", "Acme Corp", COMPANY, "low", True, "fine"),
        # location: DISAGREES across sources
        ProfileFact("location", "Austin, Texas", WIKI, "low", True, "fine"),
        ProfileFact("location", "Seattle", COMPANY, "low", True, "fine"),
    ]
    sources = [
        Source(url=WIKI, read_ok=True, overview="...", steps=4),
        Source(url=COMPANY, kind="company", read_ok=True, overview="...", steps=3),
        Source(url=BLOCKED, read_ok=False, error="login wall"),
    ]
    prof = Profile(
        name="Example Person",
        role="Founder and engineer",
        org="Acme Corp",
        location="Austin, Texas",
        key_facts=facts,
        sources=sources,
        blockers=[f"could not read {BLOCKED}: login wall"],
    )
    return prof


def test_planner_orders_and_contents():
    fails = []
    qs = clarifying_questions(_fixture_profile(), max_questions=5)

    # every question is the right shape
    for q in qs:
        assert isinstance(q, ClarifyingQuestion)
        if not (q.field and q.question_text and q.why and q.reason):
            fails.append(f"malformed question: {q}")

    reasons = [q.reason for q in qs]
    fields = [q.field for q in qs]

    # (a) the disagreement (location) comes FIRST and carries both candidates
    if not reasons or reasons[0] != "disagreement":
        fails.append(f"disagreement must be asked first, got order {reasons}")
    loc_q = next((q for q in qs if q.field == "location"), None)
    if loc_q is None:
        fails.append("expected a location question")
    else:
        if loc_q.reason != "disagreement":
            fails.append(f"location should be a disagreement, got {loc_q.reason}")
        if set(c.lower() for c in loc_q.candidates) != {"austin, texas", "seattle"}:
            fails.append(f"disagreement candidates wrong: {loc_q.candidates}")
        if "Austin, Texas" not in loc_q.question_text or "Seattle" not in loc_q.question_text:
            fails.append(f"disagreement question must read back both values: {loc_q.question_text}")

    # (b) the low-confidence confirmations come after the disagreement
    #     (role + org are both fine/needs_cross_check but agree, so not disagreements)
    low_fields = {q.field for q in qs if q.reason == "low_confidence"}
    if "role" not in low_fields:
        fails.append(f"role (low-conf single pull) must be a low_confidence question: {low_fields}")
    if "org" not in low_fields:
        fails.append(f"org (agreeing low-conf) must be a low_confidence question: {low_fields}")
    # org agreed across sources -> must NOT be surfaced as a disagreement
    if any(q.field == "org" and q.reason == "disagreement" for q in qs):
        fails.append("org agreed across sources; must not be a disagreement")
    # location is covered by the disagreement -> not ALSO a low_confidence question
    if any(q.field == "location" and q.reason == "low_confidence" for q in qs):
        fails.append("location covered by disagreement must not be re-asked low_confidence")

    # role low-confidence question carries the value as a candidate to confirm
    role_q = next((q for q in qs if q.field == "role"), None)
    if role_q is None or role_q.candidates != ["Founder and engineer"]:
        fails.append(f"role confirm should carry its value as candidate: {role_q}")

    # (c) the blocker question is present and ordered AFTER low-confidence ones
    if "blocker" not in reasons:
        fails.append(f"unreadable source must earn a blocker question: {reasons}")
    else:
        last_low = max((i for i, r in enumerate(reasons) if r == "low_confidence"), default=-1)
        first_blocker = reasons.index("blocker")
        if last_low > first_blocker:
            fails.append(f"blocker must come after low_confidence: {reasons}")
        blocker_q = next(q for q in qs if q.reason == "blocker")
        if BLOCKED not in blocker_q.field and BLOCKED not in blocker_q.why:
            fails.append(f"blocker question must name the unreadable source: {blocker_q}")

    # (d) ordering is fully non-decreasing by reason rank
    rank = {"disagreement": 0, "low_confidence": 1, "blocker": 2, "gap": 3}
    rank_seq = [rank[r] for r in reasons]
    if rank_seq != sorted(rank_seq):
        fails.append(f"questions not ordered most-uncertain first: {reasons}")

    # (e) clean coarse 'overview' field earned NO question (honesty)
    if "overview" in fields:
        fails.append("a clean coarse overview field must not earn a question")

    if fails:
        raise AssertionError("planner contents/order:\n  - " + "\n  - ".join(fails))


def test_no_uncertainty_no_questions():
    """A profile where every core field read clean + high-confidence and agrees,
    with no blockers, needs NO call."""
    facts = [
        ProfileFact("role", "Engineer", WIKI, "high", False, "fine"),
        ProfileFact("org", "Acme Corp", WIKI, "high", False, "fine"),
        ProfileFact("location", "Austin", WIKI, "high", False, "fine"),
    ]
    prof = Profile(
        name="Clean Person",
        role="Engineer", org="Acme Corp", location="Austin",
        key_facts=facts,
        sources=[Source(url=WIKI, read_ok=True, overview="ok")],
        blockers=[],
    )
    qs = clarifying_questions(prof)
    assert qs == [], f"clean profile must need no questions, got {qs}"
    payload = clarify_payload(prof)
    assert payload["summary"]["needs_call"] is False, payload["summary"]
    assert payload["questions"] == []


def test_gaps_for_missing_core_fields():
    """A profile that read a source but yielded no core fields -> obvious-gap
    questions for role/org/location, after any blockers."""
    prof = Profile(
        name="Sparse Person",
        key_facts=[ProfileFact("overview", "Some prose.", WIKI, "medium", False, "coarse")],
        sources=[Source(url=WIKI, read_ok=True, overview="Some prose.")],
        blockers=[],
    )
    qs = clarifying_questions(prof)
    gap_fields = {q.field for q in qs if q.reason == "gap"}
    assert gap_fields == {"role", "org", "location"}, gap_fields
    for q in qs:
        assert q.candidates == [], f"a gap has no candidates: {q}"


def test_cap_keeps_most_uncertain():
    """With more than `max` candidates, the cap keeps the most-uncertain ones
    (disagreement before gaps)."""
    qs = clarifying_questions(_fixture_profile(), max_questions=1)
    assert len(qs) == 1
    assert qs[0].reason == "disagreement", qs[0]


def test_payload_is_serializable_and_honest():
    import json
    payload = clarify_payload(_fixture_profile(), max_questions=5)
    json.loads(json.dumps(payload))  # serializable
    assert payload["name"] == "Example Person"
    assert payload["summary"]["count"] == len(payload["questions"])
    assert payload["summary"]["needs_call"] is True
    assert "disagreement" in payload["summary"]["by_reason"]
    # every serialized question keeps its provenance/why
    for q in payload["questions"]:
        assert q["field"] and q["question_text"] and q["why"] and "candidates" in q


# ---------------------------------------------------------------- endpoint ----

@dataclass
class FakeResult:
    success: bool
    result: Optional[str]
    url: Optional[str]
    steps: int = 1
    structured: bool = False
    needs_cross_check: bool = True
    trust: str = "coarse"
    error: Optional[str] = None


def fake_reader(task, *, url=None, structured=False, max_steps=10, timeout_s=180):
    """Scripted browse_read: WIKI says Austin, COMPANY says Seattle (a real
    location disagreement) so the endpoint produces a disagreement question."""
    t = task.lower()
    if not structured:
        return FakeResult(success=True, result="A public overview.", url=url, trust="coarse")
    if "role" in t:
        return FakeResult(success=True, result="Founder and engineer", url=url, structured=True, trust="fine")
    if "organization" in t or "company" in t:
        return FakeResult(success=True, result="Acme Corp", url=url, structured=True, trust="fine")
    if "location" in t:
        if url == COMPANY:
            return FakeResult(success=True, result="Seattle", url=url, structured=True, trust="fine")
        return FakeResult(success=True, result="Austin, Texas", url=url, structured=True, trust="fine")
    return FakeResult(success=False, result=None, url=url, error="unscripted")


def test_endpoint():
    from fastapi.testclient import TestClient
    from anticipy_engine.main import app

    fails = []
    with TestClient(app) as client:
        # ---- (1) POST with injected reader -> real questions for a built profile ----
        app.state.profile_browse_reader = fake_reader
        res = client.post(
            "/onboarding/clarify",
            json={"name": "Example Person", "sources": [WIKI, {"url": COMPANY, "kind": "company"}]},
        )
        if res.status_code != 200:
            fails.append(f"(1) expected 200, got {res.status_code}: {res.text}")
        else:
            body = res.json()
            qs = body.get("questions") or []
            if not qs:
                fails.append("(1) expected questions for an uncertain profile")
            if body.get("browser_available") is not True:
                fails.append(f"(1) injected reader -> browser_available true: {body.get('browser_available')}")
            # the WIKI/COMPANY location split must surface as the first question
            if qs and qs[0].get("reason") != "disagreement":
                fails.append(f"(1) disagreement should be first: {[q.get('reason') for q in qs]}")
            loc = next((q for q in qs if q.get("field") == "location"), None)
            if not loc or set(c.lower() for c in loc.get("candidates", [])) != {"austin, texas", "seattle"}:
                fails.append(f"(1) location disagreement candidates wrong: {loc}")
            for q in qs:
                if not (q.get("field") and q.get("question_text") and q.get("why") and "candidates" in q):
                    fails.append(f"(1) question missing fields: {q}")
            if body.get("summary", {}).get("count") != len(qs):
                fails.append(f"(1) summary count mismatch: {body.get('summary')}")

        # ---- (2) GET form returns the same questions for a built profile ----
        g = client.get(
            "/onboarding/clarify",
            params=[("name", "Example Person"), ("sources", WIKI), ("sources", COMPANY)],
        )
        if g.status_code != 200:
            fails.append(f"(2) GET expected 200, got {g.status_code}: {g.text}")
        else:
            gq = g.json().get("questions") or []
            if not gq or gq[0].get("reason") != "disagreement":
                fails.append(f"(2) GET should also produce the disagreement first: {gq}")

        # ---- (3) input validation ----
        if client.post("/onboarding/clarify", json={"name": "  ", "sources": [WIKI]}).status_code != 422:
            fails.append("(3) empty name should 422")
        if client.post("/onboarding/clarify", json={"name": "X", "sources": ["ftp://nope"]}).status_code != 422:
            fails.append("(3) no public http source should 422")

        # ---- (4) HONEST DEGRADE: no reader + no browser -> blocker question, no fakes ----
        app.state.profile_browse_reader = None
        deg = client.post("/onboarding/clarify", json={"name": "Ghost", "sources": [WIKI]})
        if deg.status_code != 200:
            fails.append(f"(4) degrade should 200: {deg.status_code}: {deg.text}")
        else:
            dp = deg.json()
            if dp.get("browser_available") is not False:
                fails.append(f"(4) no browser -> browser_available false: {dp.get('browser_available')}")
            reasons = [q.get("reason") for q in dp.get("questions") or []]
            if "blocker" not in reasons:
                fails.append(f"(4) unreadable source must yield a blocker question: {reasons}")
            # no fabricated disagreement/low-confidence facts on a fully-failed read
            if any(r in ("disagreement", "low_confidence") for r in reasons):
                fails.append(f"(4) failed reads must not invent fact questions: {reasons}")
            if not dp.get("blockers"):
                fails.append("(4) blockers must be surfaced honestly")

        # ---- (5) OWNER GATE: token set -> anonymous 401, tokened 200 ----
        app.state.profile_browse_reader = fake_reader
        old = os.environ.get("ANTICIPY_OWNER_API_TOKEN")
        token = "owner-clarify-token-54321"
        os.environ["ANTICIPY_OWNER_API_TOKEN"] = token
        try:
            anon = client.post("/onboarding/clarify", json={"name": "Example Person", "sources": [WIKI]})
            if anon.status_code != 401:
                fails.append(f"(5) anonymous must be 401 when token set: {anon.status_code}")
            ok = client.post(
                "/onboarding/clarify",
                json={"name": "Example Person", "sources": [WIKI]},
                headers={"x-anticipy-owner-token": token},
            )
            if ok.status_code != 200:
                fails.append(f"(5) tokened must be 200: {ok.status_code}: {ok.text}")
        finally:
            if old is None:
                os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
            else:
                os.environ["ANTICIPY_OWNER_API_TOKEN"] = old
            app.state.profile_browse_reader = None

    if fails:
        raise AssertionError("endpoint:\n  - " + "\n  - ".join(fails))


def main():
    test_planner_orders_and_contents()
    test_no_uncertainty_no_questions()
    test_gaps_for_missing_core_fields()
    test_cap_keeps_most_uncertain()
    test_payload_is_serializable_and_honest()
    test_endpoint()
    print(
        "PASS clarify (clarifying-call brain): ranked questions from a built "
        "Profile — disagreements (with read-back candidates) first, then "
        "low-confidence confirmations, then unreadable-source blockers, then "
        "missing-core-field gaps; clean fields earn no question; ~5 cap keeps "
        "most-uncertain; GET/POST /onboarding/clarify owner-gated + honest-degrade "
        "(no live browser)"
    )


if __name__ == "__main__":
    main()
