"""Synthesize the raw owner-scrape signals into a GRADED dossier via the smart model.

Honest by construction: with NO readable (logged-in) surface, the dossier is empty and carries a
clarifying question + the list of surfaces that still need login — it never invents a profile. With
real text, the model is told to use ONLY what the text supports and to list the gaps a short call
should fill (the bridge into the four-layer scrape<->call loop).
"""
from __future__ import annotations

import json

from ..core.gateway import PROVIDER_OPENROUTER, SMART

_PROMPT = (
    "You are privately profiling ONE person from the raw text of THEIR OWN logged-in accounts "
    "(read-only, with their permission). Be accurate and grounded: use ONLY what the text actually "
    "supports, never guess or invent a fact. Return ONLY JSON of this shape:\n"
    '{"identity":{"name":"","role":"","location":"","email":""},'
    '"work":"one or two plain sentences",'
    '"people":[{"name":"","relationship":"","why_they_matter":""}],'
    '"family":[""],"tools":[""],"act_on_sites":[""],'
    '"gaps":["the most useful things still unknown that a short call should ask"],'
    '"confidence":0.0}\n\nRAW ACCOUNT TEXT:\n'
)


async def synthesize_dossier(signals: dict, gateway) -> dict:
    surfaces = (signals or {}).get("surfaces", []) or []
    readable = [s for s in surfaces if s.get("status") == "ok" and s.get("text")]
    needs_login = [s.get("key") for s in surfaces if s.get("needs_login")]

    # HONEST: nothing readable -> no invented profile, just say so + what to do.
    if not readable:
        return {"dossier": {}, "confidence": 0.0, "needs_login": needs_login, "sources": [],
                "gaps": ["everything — no account was readable yet"],
                "clarify": "I couldn't read any of your accounts yet — log into them in the Anticipy "
                           "browser and I'll build your profile from what's there."}

    # stub/keyless: no model behind the line -> report what we read, invent nothing.
    if getattr(gateway, "provider", None) != PROVIDER_OPENROUTER:
        return {"dossier": {"readable_surfaces": [s["key"] for s in readable]}, "confidence": 0.3,
                "needs_login": needs_login, "sources": [s["key"] for s in readable], "gaps": [],
                "clarify": "", "model": "none"}

    blob = "\n\n".join(f"=== {s.get('label', s['key'])} ===\n{(s.get('text') or '')[:4000]}"
                       for s in readable)
    try:
        raw = await gateway.think(_PROMPT + blob, tier=SMART, caller="gate", temperature=0, max_tokens=1300)
        a, b = raw.find("{"), raw.rfind("}")
        doss = json.loads(raw[a:b + 1]) if (a != -1 and b > a) else {}
    except Exception as e:
        return {"dossier": {}, "confidence": 0.0, "needs_login": needs_login,
                "sources": [s["key"] for s in readable], "gaps": [],
                "clarify": "I read your accounts but couldn't synthesize them just now — I'll retry.",
                "error": str(e)[:160]}
    return {"dossier": doss, "confidence": float(doss.get("confidence", 0.5) or 0.5),
            "needs_login": needs_login, "sources": [s["key"] for s in readable],
            "gaps": doss.get("gaps", []) or [],
            "clarify": "" if doss else "I couldn't make sense of what I read — let's go over it on a call.",
            "model": "smart"}


def write_dossier_to_memory(doss: dict, memory) -> dict:
    """Persist the dossier: STATED facts (identity/work/people/family) -> profile drawer,
    INFERRED (tools/sites) -> derived drawer. Writes NOTHING when the dossier is empty (honest)."""
    d = (doss or {}).get("dossier") or {}
    if not d:
        return {"profile": 0, "derived": 0}
    p = c = 0
    ident = d.get("identity") or {}
    bits = [f"{k}: {v}" for k, v in ident.items() if v]
    if bits:
        memory.profile.write_text("Owner identity — " + "; ".join(bits)); p += 1
    if d.get("work"):
        memory.profile.write_text(f"Owner work: {d['work']}"); p += 1
    for person in (d.get("people") or []):
        name = (person.get("name") or "").strip()
        if not name:
            continue
        rel = person.get("relationship") or ""
        why = person.get("why_they_matter") or ""
        txt = "Important person: " + name + (f" — {rel}" if rel else "") + (f"; {why}" if why else "")
        memory.profile.write_text(txt, people=[name]); p += 1
    for fam in (d.get("family") or []):
        if fam:
            memory.profile.write_text(f"Family: {fam}"); p += 1
    for tool in (d.get("tools") or []):
        if tool:
            memory.derived.write_text(f"Tool the owner uses: {tool}"); c += 1
    for site in (d.get("act_on_sites") or []):
        if site:
            memory.derived.write_text(f"Site the browser arm may act on: {site}"); c += 1
    return {"profile": p, "derived": c}
