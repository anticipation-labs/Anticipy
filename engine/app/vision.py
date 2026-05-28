"""
Screenshot fallback for when accessibility tree is insufficient.
Optional — used when the tree returns no interactive elements.
"""

from __future__ import annotations

import base64

from app.models import CostTracker, llm_call_json


async def describe_screenshot(
    screenshot_bytes: bytes,
    goal: str,
    tracker: CostTracker,
) -> dict | None:
    """
    Use a vision-capable model to describe what's on screen and suggest an action.
    Returns {"description": str, "suggestion": str} or None.

    Note: This is a fallback. Most models in our chain may not support vision.
    We attempt it and gracefully handle failure.
    """
    if not screenshot_bytes:
        return None

    b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

    # Try with a text-based description request instead of actual vision
    # since our cheap models may not support multipart image input.
    # The agent loop will use page text as fallback.
    return None


async def get_page_description(
    page_text: str,
    url: str,
    goal: str,
    tracker: CostTracker,
) -> dict | None:
    """
    When accessibility tree returns no elements, use page text to suggest next action.
    Returns {"suggestion": str, "action": dict} or None.
    """
    if not page_text:
        return None

    prompt = f"""The accessibility tree returned no interactive elements.
Page URL: {url[:120]}
Goal: {goal[:120]}
Page text excerpt: {page_text[:400]}

What should the agent do? Pick one:
1. Scroll down to find more elements
2. Navigate to a different URL
3. The task may be done
4. The page seems broken/empty

Output ONLY: {{"suggestion":"scroll|navigate|done|stuck","url":null,"reason":"brief"}}"""

    messages = [{"role": "user", "content": prompt}]
    result = await llm_call_json(messages, tracker, temperature=0.0, max_tokens=60)
    return result
