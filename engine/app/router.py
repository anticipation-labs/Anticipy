"""
Task classifier (LLM-only).

After the keyword/regex pre-classifier was removed, every routing decision
is an LLM call. The deterministic surface is:

  - empty/whitespace input → ambiguous, no LLM call
  - parsed valid response → propagate the category
  - unknown category → ambiguous (defensive — never invent)
  - DegradedResponse → ambiguous + degraded=True (so callers can surface a
    "couldn't reach the model" message instead of dispatching a browser)
  - non-dict response → ambiguous

`needs_clarification` (the under-specified-action gate) lives in
`app.clarify` so that router.py stays free of regex pattern tables —
the no-hardcoding rule is checked by `test_router.test_no_keyword_or_regex_used`.

`classify` returns a `Classification` dataclass so callers can branch on
`.degraded`. The string-only legacy callers can read `.category`.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import CostTracker, DegradedResponse, llm_call_json, llm_call_text


VALID_CATEGORIES = ("chat", "question", "action", "ambiguous")


@dataclass
class Classification:
    """Result of `classify`. Iterating callers can compare `.category` to
    one of VALID_CATEGORIES; `.degraded` is True when the LLM cascade
    failed entirely so the category was forced to ambiguous."""

    category: str
    degraded: bool = False


CLASSIFICATION_TEMPLATE = (
    "Classify this user message into exactly one category.\n\n"
    "Categories:\n"
    "- \"chat\": casual conversation, greeting, thanks, small talk\n"
    "- \"question\": asking a factual question that can be answered without browsing\n"
    "- \"action\": wants something done on a website (search, book, buy, fill form, navigate, look up on specific site)\n"
    "- \"ambiguous\": unclear what they want\n\n"
    "Output ONLY valid JSON: {\"category\":\"chat\"} or {\"category\":\"question\"}"
    " or {\"category\":\"action\"} or {\"category\":\"ambiguous\"}\n\n"
    "User message: "
)


async def classify(text: str, tracker: CostTracker) -> Classification:
    """LLM-only classification. Returns Classification (.category, .degraded)."""
    if not text or not text.strip():
        return Classification(category="ambiguous", degraded=False)

    messages = [
        {
            "role": "user",
            "content": CLASSIFICATION_TEMPLATE + text[:200],
        }
    ]
    try:
        result = await llm_call_json(messages, tracker, temperature=0.0, max_tokens=32)
    except Exception:
        result = DegradedResponse()

    if isinstance(result, DegradedResponse):
        return Classification(category="ambiguous", degraded=True)

    if not isinstance(result, dict):
        return Classification(category="ambiguous", degraded=False)

    cat = result.get("category")
    if isinstance(cat, str) and cat in VALID_CATEGORIES:
        return Classification(category=cat, degraded=False)

    # Unknown / missing category: fail safely to ambiguous.
    return Classification(category="ambiguous", degraded=False)


async def handle_chat(text: str, tracker: CostTracker) -> str:
    """Generate a friendly chat response."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that can browse the web. "
                "Respond naturally and briefly. If the user seems to want "
                "you to do something on the web, let them know you can help "
                "with that. Keep replies under three sentences."
            ),
        },
        {"role": "user", "content": text[:300]},
    ]
    try:
        result = await llm_call_text(messages, tracker, temperature=0.7, max_tokens=150)
    except Exception:
        result = ""
    if isinstance(result, DegradedResponse):
        result = ""
    return (
        result.strip()
        if result
        else "I'm here to help. I can browse the web and complete tasks for you — what do you need?"
    )


async def handle_question(text: str, tracker: CostTracker) -> str:
    """Answer a factual question without browsing."""
    messages = [
        {
            "role": "system",
            "content": (
                "Answer the question briefly and helpfully. "
                "If you're not sure or the question requires current/live information, "
                "say you'd need to look it up on the web and offer to do so. "
                "Never mention that you are an AI, the model name, or any technical detail."
            ),
        },
        {"role": "user", "content": text[:300]},
    ]
    try:
        result = await llm_call_text(messages, tracker, temperature=0.3, max_tokens=200)
    except Exception:
        result = ""
    if isinstance(result, DegradedResponse):
        result = ""
    return (
        result.strip()
        if result
        else "I'm not sure about that. Want me to look it up for you?"
    )


# `needs_clarification` was moved to `app.clarify` so router.py can stay
# pure-LLM. The shim here keeps the existing import paths working without
# regressing main.py / tests.
from app.clarify import needs_clarification  # noqa: E402,F401
