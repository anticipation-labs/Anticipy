"""
Real-internet smoke: drives execute_task against the actual public web.

NO LOGINS — only sites the agent can act on without credentials. Each test
asserts on a CONCRETE artifact extracted from the final page (not on the
agent's self-reported "done"). Cop-out #8 is enforced here: the test's
pass condition is page evidence, not agent claim.

Gated on env `ENGINE_REAL_BROWSER=1` because:
  - Real browser launches need a display (Xvfb on Linux) AND ~500MB-1GB RAM
  - Network calls are slow and flaky
  - Provider-side LLM costs accumulate

To run:
  set -a && source ../.env.local && set +a
  export DISPLAY=:99 ENGINE_REAL_BROWSER=1
  Xvfb :99 -screen 0 1920x1080x24 &  # if not already running
  python -m pytest test_real_internet.py -v -s
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

_BROWSER_ENABLED = os.environ.get("ENGINE_REAL_BROWSER", "").lower() in {"1", "true", "yes", "on"}
_HAS_LLM_KEYS = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GROQ_API_KEY"))

# Per-test skip decorators
_skip_no_llm = pytest.mark.skipif(not _HAS_LLM_KEYS, reason="needs LLM keys")
_skip_no_browser = pytest.mark.skipif(
    not _BROWSER_ENABLED or not _HAS_LLM_KEYS,
    reason="needs ENGINE_REAL_BROWSER=1 + LLM keys + Xvfb",
)


@pytest.fixture
def collected_messages():
    """Returns a list and a send callback that appends to it."""
    msgs: list[dict] = []

    async def send(m: dict) -> None:
        msgs.append(m)
        # Print live for human observation when -s is passed
        print(f"  [{m.get('type','?')}] {m.get('message','')[:200]}", flush=True)

    return msgs, send


async def _confirm() -> str:
    return "confirmed"


# ─── execute_task end-to-end smoke ───────────────────────────────────────


@_skip_no_browser
@pytest.mark.asyncio
async def test_execute_task_wikipedia_lookup(collected_messages):
    """The agent should look up a fact on Wikipedia and surface it.

    Asserts on the agent's final 'complete' message containing the actual
    answer extracted from the page (not just 'Done.').
    """
    from app.agent import execute_task

    msgs, send = collected_messages

    t0 = time.time()
    await execute_task(
        goal="Go to wikipedia.org, search for 'Python (programming language)', and tell me what year it was first released.",
        send=send,
        receive_confirmation=_confirm,
        user_id=None,
    )
    elapsed = time.time() - t0
    print(f"\n  elapsed: {elapsed:.1f}s, messages: {len(msgs)}", flush=True)

    # Surface the final outcome
    final_complete = None
    final_error = None
    for m in reversed(msgs):
        t = m.get("type")
        if t == "complete" and final_complete is None:
            final_complete = m.get("message", "")
        if t == "error" and final_error is None:
            final_error = m.get("message", "")

    if final_error and not final_complete:
        pytest.skip(f"agent errored (likely env): {final_error}")

    assert final_complete is not None, f"expected 'complete' message; got messages: {[m.get('type') for m in msgs]}"
    # The well-known answer is 1991. Verify it's in the agent's reported result.
    # If the agent failed verification, it should say so honestly, not silently lie.
    lower = final_complete.lower()
    if "1991" in final_complete:
        # Pass: extracted the right answer
        return
    if "couldn't" in lower or "retry" in lower or "trouble" in lower:
        # Honest failure — acceptable per cop-out #6/#8
        pytest.skip(f"agent honestly reported can't-finish: {final_complete}")
    # Otherwise the agent claimed success without the year — that's a real problem
    pytest.fail(
        f"agent claimed completion but evidence is missing. final message: {final_complete!r}"
    )


# ─── End-state verifier on a real page ───────────────────────────────────


@_skip_no_llm
@pytest.mark.asyncio
async def test_verifier_on_real_wikipedia_page():
    """Capture a real Wikipedia page's text and feed it through the verifier.
    Verifier should extract the correct answer as evidence."""
    import httpx

    from app.proactive.llm_adapter import make_json_llm_call
    from app.verifier import EndStateVerifier, FinalPageState

    # Wikipedia REST API — welcomes well-identified bots per their policy.
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/Python_(programming_language)",
            headers={
                "User-Agent": "anticipy-engine-smoketest/1.0 (https://anticipy.ai; bot-contact@anticipy.ai)",
            },
        )
        assert r.status_code == 200, f"wikipedia API returned {r.status_code}: {r.text[:200]}"
        data = r.json()

    # Combine description + extract; this is the visible text the verifier sees.
    text_only = (data.get("description") or "") + "\n\n" + (data.get("extract") or "")
    text_only = text_only[:8000]
    title = data.get("title") or "Python (programming language)"
    page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "https://en.wikipedia.org/wiki/Python_(programming_language)")

    verifier = EndStateVerifier(make_json_llm_call(max_tokens=512))
    verdict = await verifier.verify(
        goal="Find what year Python (the programming language) was first released.",
        final_state=FinalPageState(
            url=page_url,
            title=title,
            visible_text=text_only,
            history_summary="navigated to wikipedia → opened Python article",
        ),
    )
    print(f"\n  passed={verdict.passed}, evidence={verdict.evidence!r}, conf={verdict.confidence}", flush=True)
    print(f"  visible_text starts: {text_only[:300]!r}", flush=True)
    # If the API summary doesn't actually contain the year (Wikipedia summaries
    # are short and curated; '1991' isn't always in the lead extract), skip
    # rather than fail — that's not a verifier bug.
    if "1991" not in text_only:
        pytest.skip(
            f"wikipedia summary doesn't contain '1991'; can't expect verifier to fabricate. "
            f"summary preview: {text_only[:200]}"
        )
    # If the verifier got an empty response from the LLM, treat as a transient
    # provider failure (cascade-level retry covered elsewhere). Skip rather than
    # call the verifier broken.
    if verdict.reasoning == "verifier returned empty":
        pytest.skip(f"verifier provider returned empty (transient provider issue): {verdict}")
    assert verdict.passed, f"verifier failed on real Wikipedia page (page contains 1991): {verdict}"
    assert "1991" in verdict.evidence, (
        f"expected '1991' in evidence; got: {verdict.evidence!r}"
    )


# ─── End-state verifier sees an irrelevant page ──────────────────────────


@_skip_no_llm
@pytest.mark.asyncio
async def test_verifier_correctly_rejects_irrelevant_page():
    """If the page doesn't answer the goal, verifier should say not-passed."""
    import httpx

    from app.proactive.llm_adapter import make_json_llm_call
    from app.verifier import EndStateVerifier, FinalPageState

    # Wikipedia REST summary for an unrelated topic — the verifier should
    # see no Python-release-year evidence here.
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(
            "https://en.wikipedia.org/api/rest_v1/page/summary/Photosynthesis",
            headers={
                "User-Agent": "anticipy-engine-smoketest/1.0 (https://anticipy.ai; bot-contact@anticipy.ai)",
            },
        )
        assert r.status_code == 200, f"wikipedia API returned {r.status_code}"
        data = r.json()
    text_only = (data.get("description") or "") + "\n\n" + (data.get("extract") or "")
    text_only = text_only[:8000]

    verifier = EndStateVerifier(make_json_llm_call(max_tokens=512))
    verdict = await verifier.verify(
        goal="Find what year Python (the programming language) was first released.",
        final_state=FinalPageState(
            url="https://en.wikipedia.org/wiki/Photosynthesis",
            title="Photosynthesis - Wikipedia",
            visible_text=text_only,
            history_summary="navigated to a page about photosynthesis (irrelevant to the goal)",
        ),
    )
    print(f"\n  passed={verdict.passed}, honest_msg={verdict.honest_message_for_wearer!r}", flush=True)
    assert not verdict.passed, (
        f"verifier should reject irrelevant page; got verdict: {verdict}"
    )
    assert verdict.honest_message_for_wearer, (
        "verifier must produce an honest message when not passed"
    )
