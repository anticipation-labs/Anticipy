"""final/context/reference_resolver.py — memory-anchored reference resolution (deliverable a).

Grafted from DEV-FINAL ``engine/app/anticipy/memory.py:260`` (``resolve_reference``),
adapted from its JSONL + ``platform_adapter.model_call`` substrate onto the devin
memory drawers + gateway. Resolves a vague reference in a task ("my usual", "the
boss", "our spot") against stored anchors (profile facts) and people, so
"grab my usual coffee" becomes the concrete "large oat milk latte" the wearer
actually means — instead of a generic, useless "your coffee".

Discipline (same as the graft): deterministic anchor lookup first (fast, no model,
un-flaky); an optional model pass only for genuinely vague references the anchors
don't cover. On any miss it returns UNRESOLVED so the caller ASKs rather than
guesses — a wrong guess on someone's real task is worse than a small clarifying
question.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

# Reference triggers — the vague pointers a wearer uses for a thing they've told us
# about before. "the usual", "my usual order", "our spot", "the boss", "the office".
_USUAL = re.compile(r"\b(?:my|the)\s+usual\b|\busual\s+(?:order|coffee|spot|place|drink)\b", re.I)
_BARE_REF = re.compile(r"\b(?:the boss|our spot|the spot|the usual place|the office|my place)\b", re.I)


@dataclass
class ResolveResult:
    resolved: bool
    value: str
    confidence: float
    reason: str


def _anchors(memory) -> list[dict]:
    """All active anchor facts the context engine has stored, as {key,value}."""
    out: list[dict] = []
    try:
        items = memory.profile.all()
    except Exception:
        return out
    for it in items:
        f = getattr(it, "fields", None) or {}
        if f.get("ctype") not in ("anchor", "preference", "allergy", "address"):
            continue
        if getattr(it, "status", "active") not in ("active", "open", "", None):
            continue
        key = str(f.get("ckey") or "").strip()
        val = str(f.get("cvalue") or getattr(it, "text", "") or "").strip()
        if key and val:
            out.append({"key": key, "value": val})
    return out


def resolve_reference(memory, reference_text: str, gateway=None) -> ResolveResult:
    """Resolve one vague reference against stored anchors. Deterministic-first.

    Returns confidence; the caller treats >= 0.70 as resolved. Never invents a value.
    """
    text = reference_text or ""
    anchors = _anchors(memory)
    if not anchors:
        return ResolveResult(False, "", 0.0, "no_anchors")

    def anchor_for(*keys) -> Optional[str]:
        for a in anchors:
            if a["key"].lower() in keys:
                return a["value"]
        return None

    # 1) DETERMINISTIC — "my usual" -> the stored usual order (+ usual place if known)
    if _USUAL.search(text):
        usual = anchor_for("usual", "usual order", "usual coffee", "order")
        if usual:
            place = anchor_for("usual place", "cafe", "coffee shop")
            value = usual if not place else f"{usual}, {place}"
            return ResolveResult(True, value, 0.95, "matched stored 'usual' anchor")

    if _BARE_REF.search(text):
        m = _BARE_REF.search(text).group(0).lower()
        cand = anchor_for(m, m.replace("the ", "").replace("my ", ""))
        if cand:
            return ResolveResult(True, cand, 0.9, f"matched stored anchor '{m}'")

    # 2) MODEL FALLBACK — a genuinely vague ref not covered above, only if a gateway
    #    is available. Fails safe to unresolved (caller ASKs, never guesses).
    if gateway is None or not _looks_vague(text):
        return ResolveResult(False, "", 0.0, "no_deterministic_match")
    try:
        val, conf = _resolve_with_model(gateway, anchors, text)
        if val and conf >= 0.70:
            return ResolveResult(True, val, conf, "model resolved against anchors")
    except Exception:
        pass
    return ResolveResult(False, "", 0.0, "unresolved")


def _looks_vague(text: str) -> bool:
    low = (text or "").lower()
    return bool(_USUAL.search(low) or _BARE_REF.search(low)
                or re.search(r"\bthe (usual|regular|same)\b", low))


_RESOLVE_SYS = (
    "You resolve a vague reference in a task against the user's known anchors. "
    "Return STRICT JSON only: {\"resolved\":true|false,\"value\":\"<concrete value>\","
    "\"confidence\":0.0}. Only resolve true with a value if a specific anchor clearly "
    "matches. If nothing matches, resolved=false. Never invent a value."
)


def _resolve_with_model(gateway, anchors: list[dict], reference_text: str) -> tuple[str, float]:
    prompt = (
        _RESOLVE_SYS + "\n\nKNOWN ANCHORS:\n" + json.dumps(anchors, ensure_ascii=False)
        + f"\n\nREFERENCE TO RESOLVE: {reference_text}\n\nReturn the JSON now."
    )
    import asyncio
    raw = _gateway_think(gateway, prompt)
    if not raw:
        return "", 0.0
    a, b = raw.find("{"), raw.rfind("}")
    if a == -1 or b <= a:
        return "", 0.0
    try:
        p = json.loads(raw[a:b + 1])
    except Exception:
        return "", 0.0
    if not p.get("resolved"):
        return "", 0.0
    return str(p.get("value", "")), float(p.get("confidence", 0.0) or 0.0)


def _gateway_think(gateway, prompt: str) -> str:
    """Call the gateway's blocking/awaitable think() from sync code, safely."""
    import asyncio
    try:
        think = gateway.think(prompt, tier="cheap", caller="context_resolve")
    except TypeError:
        think = gateway.think(prompt)
    if asyncio.iscoroutine(think):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            # already inside an event loop — cannot block; skip the model pass
            think.close()
            return ""
        return asyncio.run(think) or ""
    return think or ""


__all__ = ["ResolveResult", "resolve_reference"]
