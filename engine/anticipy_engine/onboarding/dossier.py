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
    '"family":[""],"tools":[""],"act_on_sites":[{"name":"","url":""}],'
    '"gaps":["the most useful things still unknown that a short call should ask"],'
    '"confidence":0.0}\n'
    "For act_on_sites: these are the OTHER systems this person's life actually lives in (their CRM, "
    "Notion, billing dashboard, project tracker) — include the exact https URL you actually SAW in "
    "the text (a link in an email, a calendar entry, a signature). NEVER invent or guess a URL; if "
    "you only saw a tool's name with no link, put it in tools, not act_on_sites.\n\nRAW ACCOUNT TEXT:\n"
)


async def synthesize_dossier(signals: dict, gateway, per_surface_chars: int = 4000) -> dict:
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

    # sweep r3: budget per surface = the LAYER's max_chars (threaded from loop.py), so a deep layer-4
    # scrape actually feeds the deeper catalogue to the model instead of being re-cut to the layer-1 head.
    blob = "\n\n".join(f"=== {s.get('label', s['key'])} ===\n{(s.get('text') or '')[:max(2000, per_surface_chars)]}"
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
    _conf = doss.get("confidence")
    return {"dossier": doss,
            "confidence": float(_conf) if isinstance(_conf, (int, float)) else 0.5,
            "needs_login": needs_login, "sources": [s["key"] for s in readable],
            "gaps": doss.get("gaps", []) or [],
            "clarify": "" if doss else "I couldn't make sense of what I read — let's go over it on a call.",
            "model": "smart"}


def _as_list(v) -> list:
    """The model may return a list, a bare string, or null — never iterate a string char-by-char."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, list):
        return v
    return [v]


def _name_of(item) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("name") or item.get("url") or item.get("label") or "").strip()
    return ""


def _k(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())[:40]


def write_dossier_to_memory(doss: dict, memory) -> dict:
    """Persist the dossier: STATED facts (identity/work/people/family) -> profile drawer (provenance
    'stated'), INFERRED (tools/sites) -> derived drawer (provenance 'inferred', confidence < 1).
    IDEMPOTENT (sweep #8): each logical fact has a STABLE id, so a re-run/another layer REPLACES it in
    place instead of duplicating. Robust to model shape drift; writes NOTHING when empty (honest)."""
    d = (doss or {}).get("dossier") or {}
    if not isinstance(d, dict) or not d:
        return {"profile": 0, "derived": 0}
    p = c = 0

    ident = d.get("identity")
    if isinstance(ident, dict):
        bits = [f"{k}: {v}" for k, v in ident.items() if v]
        if bits:
            memory.profile.write_text("Owner identity — " + "; ".join(bits),
                                      provenance="stated", confidence=0.9, id="onb:identity"); p += 1
    elif isinstance(ident, str) and ident.strip():
        memory.profile.write_text(f"Owner identity — {ident.strip()}",
                                  provenance="stated", confidence=0.9, id="onb:identity"); p += 1

    if isinstance(d.get("work"), str) and d["work"].strip():
        memory.profile.write_text(f"Owner work: {d['work'].strip()}",
                                  provenance="stated", confidence=0.85, id="onb:work"); p += 1

    for person in _as_list(d.get("people")):
        if isinstance(person, str):
            person = {"name": person}
        if not isinstance(person, dict):
            continue
        name = str(person.get("name") or "").strip()
        if not name:
            continue
        rel = str(person.get("relationship") or "")
        why = str(person.get("why_they_matter") or "")
        txt = "Important person: " + name + (f" — {rel}" if rel else "") + (f"; {why}" if why else "")
        memory.profile.write_text(txt, people=[name], provenance="stated", confidence=0.85,
                                  id="onb:person:" + _k(name)); p += 1

    for fam in _as_list(d.get("family")):
        n = _name_of(fam)
        if n:
            memory.profile.write_text(f"Family: {n}", provenance="stated", confidence=0.8,
                                      id="onb:family:" + _k(n)); p += 1

    for tool in _as_list(d.get("tools")):
        n = _name_of(tool)
        if n:
            memory.derived.write_text(f"Tool the owner uses: {n}", provenance="inferred",
                                      confidence=0.6, id="onb:tool:" + _k(n)); c += 1

    for site in _as_list(d.get("act_on_sites")):
        n = _name_of(site)
        if n:
            memory.derived.write_text(f"Site the browser arm may act on: {n}",
                                      provenance="inferred", confidence=0.6, id="onb:site:" + _k(n)); c += 1
    return {"profile": p, "derived": c}
