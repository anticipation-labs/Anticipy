#!/usr/bin/env python3
"""Score memory precision on the V7 hard-transcript run.

Five dimensions, each 0.0 to 1.0:
  1. intent_precision     verb-category match between engine plan and gold
  2. entity_precision     coverage of expected_memory_used entities (after alignment)
  3. action_faithfulness  LLM judge: does the engine plan match what the user asked
  4. memory_write         did the engine write memory when it should have
  5. memory_write_skip    did the engine correctly skip writing for chatter

Inputs:
  state/v7/hard_proactive_transcripts.json   gold
  state/v7/test_dossier_rich.json            rich dossier with aliases
  state/v7/e2e_hard_transcripts_<ts>/T*_inject.json    engine outputs

Outputs:
  state/v7/memory_precision_<run_ts>.json    per-transcript verdicts + aggregate
  state/v7/memory_precision_<run_ts>.md      human-readable summary
  state/v7/gold_key_to_dossier.json          alignment map (built once, reused)

Judge cascade: deepseek/deepseek-chat-v4-flash, moonshotai/kimi-k2.6-instruct,
google/gemini-flash-2.5. Temperature 0.0, response_format json_object.

Budget cap: $2 OpenRouter (default; override with ANTICIPY_BUDGET_USD env var).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ---------- paths --------------------------------------------------------- #
REPO = Path(__file__).resolve().parents[2]
GOLD = REPO / "state/v7/hard_proactive_transcripts.json"
DOSSIER = REPO / "state/v7/test_dossier_rich.json"
RUN_DIR = REPO / "state/v7/e2e_hard_transcripts_20260528T031414Z"
GOLD_MAP = REPO / "state/v7/gold_key_to_dossier.json"

# ---------- judge cascade ------------------------------------------------- #
CASCADE = (
    # Brief specified deepseek-chat-v4-flash; the live OpenRouter catalog has
    # 'deepseek/deepseek-v4-flash' as the matching slug. Same for kimi-k2.6
    # (no '-instruct' suffix exists on OpenRouter) and gemini-flash-latest.
    "deepseek/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "google/gemini-flash-latest",
)
# Approx prices per 1M tokens (USD) for cascade. Used only for cost tracking.
PRICES_PER_MTOK = {
    "deepseek/deepseek-v4-flash": {"in": 0.10, "out": 0.20},
    "moonshotai/kimi-k2.6": {"in": 0.73, "out": 3.49},
    "google/gemini-flash-latest": {"in": 1.50, "out": 9.00},
}
DEFAULT_BUDGET = float(os.environ.get("ANTICIPY_BUDGET_USD", "2.0"))


# ---------- intent category map ------------------------------------------ #
# Engine plan.intent strings: calendar_event, send_email, message, search, other, ...
# Map verb categories from the gold expected_intent text into a canonical bucket.
CANONICAL_INTENTS = (
    "calendar_event",
    "send_email",
    "send_message",
    "draft_email",
    "draft_message",
    "search",
    "reminder",
    "purchase",
    "noop_chatter",
    "clarify",
    "other",
)

# Adjacency: pairs that count as 0.5 instead of 1.0/0.0.
ADJACENT_INTENTS = {
    frozenset({"send_email", "draft_email"}),
    frozenset({"send_message", "draft_message"}),
    frozenset({"draft_email", "draft_message"}),
    frozenset({"send_email", "send_message"}),
    frozenset({"calendar_event", "reminder"}),
    frozenset({"reminder", "other"}),
    frozenset({"search", "other"}),
}


def classify_intent_from_text(text: str) -> str:
    t = (text or "").lower()
    if not t:
        return "other"
    if re.search(r"\b(book|schedule|calendar|block|reserv|add (to|an?) calendar|set up.*meeting|set up.*session|create.*event)\b", t):
        return "calendar_event"
    if re.search(r"\bdraft (an? )?(email|message|reply|note)\b", t):
        if "message" in t or "whatsapp" in t or "imessage" in t or "slack" in t:
            return "draft_message"
        return "draft_email"
    if re.search(r"\b(send|forward|email|reply)\b.*\b(email|gmail|reply)\b", t) and "draft" not in t:
        return "send_email"
    if "draft" in t and ("email" in t or "letter" in t):
        return "draft_email"
    if "draft" in t and ("message" in t or "whatsapp" in t or "text" in t or "imessage" in t or "slack" in t):
        return "draft_message"
    if re.search(r"\b(send|text|whatsapp|imessage|slack|message)\b", t):
        return "send_message"
    if re.search(r"\b(remind|nudge|surface|capture|check-?in|set a (quiet )?check)\b", t):
        return "reminder"
    if re.search(r"\b(search|locate|find|look up|search gmail)\b", t):
        return "search"
    if re.search(r"\b(order|buy|purchase|ship)\b", t):
        return "purchase"
    if re.search(r"\b(do not act|take no action|do nothing|ignore)\b", t):
        return "noop_chatter"
    return "other"


def classify_engine_intent(plan: dict) -> str:
    """Map the engine plan onto the canonical intent set."""
    if not plan:
        return "noop_chatter"
    mode = (plan.get("mode") or "").lower()
    intent = (plan.get("intent") or "").lower()
    task = (plan.get("task") or "").strip()
    thing = (plan.get("thing") or "").strip()
    # clarify mode means engine asked a question. Use thing+task fallback.
    blob = " ".join([intent, task, thing]).lower()
    if intent == "calendar_event":
        return "calendar_event"
    if intent in ("send_email", "draft_email"):
        return "draft_email" if "draft" in blob else "send_email"
    if intent in ("send_message", "draft_message", "message"):
        return "draft_message" if "draft" in blob else "send_message"
    if intent == "search":
        return "search"
    if intent == "reminder":
        return "reminder"
    if intent in ("noop", "noop_chatter", "skip"):
        return "noop_chatter"
    if mode == "clarify":
        # Engine asked a clarifying question; classify by thing/task content.
        return classify_intent_from_text(blob)
    # mode == act, intent empty or "other".
    return classify_intent_from_text(blob)


def score_intent(gold_intent_text: str, plan: dict) -> tuple[float, str, str]:
    gold = classify_intent_from_text(gold_intent_text)
    pred = classify_engine_intent(plan)
    if pred == gold:
        return 1.0, pred, gold
    if frozenset({pred, gold}) in ADJACENT_INTENTS:
        return 0.5, pred, gold
    return 0.0, pred, gold


# ---------- gold-key alignment ------------------------------------------- #
ROLE_HINTS = {
    "ops": ["operations", "ops", "head of operations", "operations partner", "vp operations", "head of people"],
    "finance": ["finance", "bookkeeping", "billing", "ar", "ops partner"],
    "legal": ["legal", "counsel", "lawyer", "law"],
    "designer": ["designer", "design", "creative", "design lead", "vp"],
    "brother": ["brother"],
    "sister": ["sister"],
    "dad": ["dad", "father"],
    "mom": ["mom", "mother"],
    "husband": ["husband"],
    "manager": ["manager"],
    "engineer": ["engineer", "engineering"],
    "cfo": ["cfo", "finance", "founder"],
    "ceo": ["ceo", "founder"],
    "dentist": ["dentist"],
    "doctor": ["doctor", "dr."],
}

# Cross-cast aliases: the gold transcripts use a different cast (Marcus, Jordan,
# Priya-as-designer, etc.) than the rich dossier (Devon, Andre, Priya-as-VP-Ops).
# This is documented in hard_proactive_transcripts.json itself: the downstream
# phase reconciles dossier IDs against the rich dossier. These pairs encode
# the canonical reconciliation.
CROSS_CAST_NAME_TO_DOSSIER = {
    "marcus": "Devon Park",      # finance role
    "jordan": "Andre Kowalski",  # legal role
    "david": "James Ortega",     # acme deal counterpart
    "rena": "Maya Chen",         # standing-in for Maya's manager (no row in dossier)
    "elena": None,               # sister-in-law: no dossier row
    "sam": None,                 # brother: no dossier row
    "mom": None,
    "dad": None,
    "dr": "Dr. Sara Nakamura",   # the dentist
    "chen": "Dr. Sara Nakamura", # gold person_dr_chen → dentist
    "priya": "Priya Patel",      # name match holds
    "maya": "Maya Chen",         # name match holds
}


def tokens_from_key(key: str) -> list[str]:
    """Split a gold key like 'person_priya_designer' into useful tokens."""
    parts = key.split("_")
    return [p for p in parts if p]


def keytype(key: str) -> str:
    parts = key.split("_")
    if parts and parts[0] in ("person", "place", "project", "event", "preference",
                              "recurring", "constraint", "fact", "trait", "template",
                              "decision", "address", "task"):
        return parts[0]
    return "other"


def build_dossier_index(dossier: dict) -> dict[str, list[dict]]:
    """Group dossier entries by key type, attaching searchable text blobs."""
    idx: dict[str, list[dict]] = {"person": [], "place": [], "project": [], "preference": [],
                                  "recurring": [], "other": []}
    for p in dossier.get("people", []) or []:
        idx["person"].append({
            "id": "person:" + p["name"],
            "name": p.get("name", ""),
            "role": p.get("role", ""),
            "tags": p.get("tags", []) or [],
            "aliases": p.get("aliases", []) or [],
            "raw": p,
        })
    places = (dossier.get("places") or {})
    for p in (places.get("named_places") or []) + (places.get("frequented_locations") or []):
        idx["place"].append({
            "id": "place:" + p["name"],
            "name": p.get("name", ""),
            "context": p.get("context", ""),
            "address": p.get("address", ""),
            "raw": p,
        })
    for pr in dossier.get("projects", []) or []:
        idx["project"].append({
            "id": "project:" + pr["name"],
            "name": pr.get("name", ""),
            "status": pr.get("status", ""),
            "blockers": pr.get("blockers", ""),
            "stakeholders": pr.get("stakeholders", []) or [],
            "raw": pr,
        })
    for rec in dossier.get("recurring_patterns", []) or []:
        idx["recurring"].append({
            "id": "recurring:" + rec["name"],
            "name": rec.get("name", ""),
            "trigger": rec.get("trigger", ""),
            "behavior": rec.get("behavior", ""),
            "raw": rec,
        })
    return idx


def align_one(key: str, idx: dict[str, list[dict]]) -> dict:
    """Best-match a single gold key against dossier entries.

    Returns dict with: matched (bool), dossier_id (str|None), score (float), reason (str).
    """
    ktype = keytype(key)
    toks = [t.lower() for t in tokens_from_key(key)]

    # Map gold key type to dossier bucket(s) to search.
    bucket = {
        "person": ["person"],
        "place": ["place"],
        "project": ["project"],
        "recurring": ["recurring"],
        "event": ["project", "recurring"],
        "preference": [],
        "constraint": [],
        "fact": [],
        "trait": [],
        "template": [],
        "decision": [],
        "address": ["place"],
        "task": [],
    }.get(ktype, [])

    best = {"score": 0.0, "id": None, "reason": "no candidates"}

    # Cross-cast alias hard-coded mapping for people: when a gold person key
    # uses a name not in the dossier but stands in for a documented role.
    if ktype == "person":
        for tok in toks[1:]:
            if tok in CROSS_CAST_NAME_TO_DOSSIER:
                target = CROSS_CAST_NAME_TO_DOSSIER[tok]
                if target is None:
                    # Documented as out-of-dossier.
                    return {
                        "gold_key": key,
                        "matched": False,
                        "dossier_id": None,
                        "matched_name": None,
                        "score": 0.0,
                        "reason": f"cross-cast: '{tok}' explicitly out of dossier",
                    }
                # Find the dossier entry with that name.
                for cand in idx.get("person", []):
                    if cand.get("name", "").lower() == target.lower():
                        return {
                            "gold_key": key,
                            "matched": True,
                            "dossier_id": cand["id"],
                            "matched_name": cand["name"],
                            "score": 0.90,
                            "reason": f"cross-cast: '{tok}' -> {target}",
                        }

    for b in bucket:
        for cand in idx.get(b, []):
            score, reason = _score_candidate(toks, cand, ktype)
            if score > best["score"]:
                best = {"score": score, "id": cand["id"], "reason": reason,
                        "matched_name": cand.get("name", "")}

    threshold = 0.40
    if best["score"] >= threshold:
        return {
            "gold_key": key,
            "matched": True,
            "dossier_id": best["id"],
            "matched_name": best.get("matched_name", ""),
            "score": round(best["score"], 3),
            "reason": best["reason"],
        }
    return {
        "gold_key": key,
        "matched": False,
        "dossier_id": None,
        "matched_name": None,
        "score": round(best["score"], 3),
        "reason": "below threshold; " + best["reason"],
    }


def _score_candidate(toks: list[str], cand: dict, ktype: str) -> tuple[float, str]:
    """Heuristic match score in [0, 1] with a short reason string."""
    name = cand.get("name", "").lower()
    role = cand.get("role", "").lower() if "role" in cand else ""
    tags = [t.lower() for t in cand.get("tags", [])] if "tags" in cand else []
    aliases = [a.lower() for a in cand.get("aliases", [])] if "aliases" in cand else []
    context = (cand.get("context", "") + " " + cand.get("status", "") + " " +
               cand.get("blockers", "") + " " + cand.get("behavior", "") + " " +
               cand.get("address", "")).lower()
    stakeholders = " ".join(cand.get("stakeholders", [])).lower() if "stakeholders" in cand else ""

    blob = " ".join([name, role, " ".join(tags), " ".join(aliases), context, stakeholders])

    name_tokens = set(re.findall(r"[a-z]+", name))
    score = 0.0
    reasons = []
    tail_toks = [t for t in toks[1:] if len(t) >= 3]  # drop short tail noise

    # Direct first-name token match (highest signal for persons).
    if ktype == "person":
        for tok in toks[1:]:  # short tokens like "dr" still allowed for titles
            if tok in name_tokens:
                score += 0.55
                reasons.append(f"name token '{tok}' in name")
                break

    # Alias match - require alias to actually be a key token (not substring match)
    if ktype == "person":
        for alias in aliases:
            alias_clean = alias.strip().lower()
            if len(alias_clean) < 3:
                continue  # skip single-letter aliases like "M", "D", "P", "L"
            # Require alias to share at least one non-trivial token with the gold key.
            alias_tokens = set(re.findall(r"[a-z]+", alias_clean))
            shared = alias_tokens & set(tail_toks)
            if shared:
                score += 0.20
                reasons.append(f"alias token overlap '{','.join(sorted(shared))}'")
                break

    # Role / tag hints from key tail
    for tok in toks[1:]:
        if tok in ROLE_HINTS:
            hints = ROLE_HINTS[tok]
            if any(h in role or h in " ".join(tags) for h in hints):
                score += 0.45
                reasons.append(f"role-hint '{tok}' matches")
            elif any(h in context for h in hints):
                score += 0.20
                reasons.append(f"role-hint '{tok}' in context")
            break

    # Tag direct hits
    for tok in toks[1:]:
        if tok in tags:
            score += 0.20
            reasons.append(f"tag '{tok}'")
            break

    # Place/project: token overlap with name+context
    if ktype in ("place", "project", "event", "recurring", "address"):
        STOP = {"the", "and", "for", "tue", "wed", "thu", "fri", "sat", "sun", "mon",
                "close", "noon", "default", "date", "shipping", "afternoon"}
        type_tokens = {tok for tok in toks[1:] if len(tok) >= 3 and tok not in STOP}
        hits = 0
        for tok in type_tokens:
            if tok in blob:
                hits += 1
                reasons.append(f"token '{tok}' in blob")
        if type_tokens:
            # Boost for places/projects: tokens are much more discriminating.
            score += 0.75 * (hits / max(1, len(type_tokens)))
        # Strong bonus if a critical cuisine/role token matches (e.g. "italian", "yoga", "dental")
        for crit in ("italian", "korean", "yoga", "dental", "clinic", "wedding",
                     "onboarding", "acme", "northbridge", "kissa", "speech"):
            if crit in type_tokens and crit in blob:
                score += 0.20
                reasons.append(f"critical token '{crit}' present")
                break

    return min(1.0, score), "; ".join(reasons) or "no signal"


def build_alignment(gold: dict, dossier: dict, force_rebuild: bool = False) -> dict:
    """Build state/v7/gold_key_to_dossier.json once and reuse."""
    if GOLD_MAP.exists() and not force_rebuild:
        try:
            cached = json.loads(GOLD_MAP.read_text())
            if cached.get("schema") == "anticipy.v7.gold_key_alignment":
                return cached
        except Exception:
            pass
    idx = build_dossier_index(dossier)
    all_keys: set[str] = set()
    for t in gold.get("transcripts", []):
        for k in t.get("expected_memory_used", []) or []:
            all_keys.add(k)
    mapping = {}
    for k in sorted(all_keys):
        mapping[k] = align_one(k, idx)
    out = {
        "schema": "anticipy.v7.gold_key_alignment",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dossier_path": str(DOSSIER.relative_to(REPO)),
        "gold_path": str(GOLD.relative_to(REPO)),
        "total_keys": len(mapping),
        "matched": sum(1 for v in mapping.values() if v["matched"]),
        "unmatched": sum(1 for v in mapping.values() if not v["matched"]),
        "mapping": mapping,
    }
    GOLD_MAP.parent.mkdir(parents=True, exist_ok=True)
    GOLD_MAP.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


# ---------- entity precision --------------------------------------------- #
def score_entity_precision(expected_keys: list[str], plan: dict,
                           transcript: str, alignment: dict) -> tuple[float, list[dict]]:
    """Score whether engine plan resolved the right entities.

    Strategy: for each expected_memory_used key, look up the aligned dossier
    entry; check if any of (matched_name, aliases of that entry, key tokens)
    appears in the engine plan task/thing/person blob. Score is the fraction
    of expected keys that have a verifiable mention.
    """
    if not expected_keys:
        return 1.0, []
    plan_blob = " ".join([
        (plan or {}).get("person", "") or "",
        (plan or {}).get("thing", "") or "",
        (plan or {}).get("task", "") or "",
        (plan or {}).get("question", "") or "",
    ]).lower()
    mapping = alignment.get("mapping", {})
    hits = []
    for key in expected_keys:
        info = mapping.get(key, {"matched": False, "matched_name": None})
        signals = []
        if info.get("matched") and info.get("matched_name"):
            first_name = (info["matched_name"].split()[0]).lower()
            if first_name and first_name in plan_blob:
                signals.append(f"name '{first_name}' in plan")
        # Also try the gold key's own tokens (e.g., "priya" from person_priya).
        for tok in tokens_from_key(key)[1:]:
            tok_l = tok.lower()
            if len(tok_l) >= 4 and tok_l in plan_blob and tok_l not in {"ops", "finance", "legal",
                                                                       "designer", "manager",
                                                                       "brother", "sister",
                                                                       "shipping", "default"}:
                signals.append(f"token '{tok_l}' in plan")
                break
        hits.append({"key": key, "found": bool(signals), "signals": signals,
                     "aligned_to": info.get("dossier_id")})
    found = sum(1 for h in hits if h["found"])
    score = found / len(expected_keys)
    return score, hits


# ---------- memory write scoring ----------------------------------------- #
def score_memory_write(outcome: str, expected_keys: list[str], memory: dict,
                       plan: dict) -> tuple[float, float, str]:
    """Return (memory_write, memory_write_skip, reason).

    memory_write applies when expected_keys is non-empty AND the transcript is
    actionable (CONFIRMED). 1.0 if engine wrote (ADD/UPDATE), 0.0 if NOOP.

    memory_write_skip applies when the transcript is chatter (LIFE_LOG) or
    CANCELLED with no expected_memory_used or with content the engine should
    skip. 1.0 if engine NOOPed, 0.0 if it wrote anyway.

    Each dimension returns NaN-like (None semantics via -1.0) when it does not
    apply to this transcript; aggregation filters those out.
    """
    op = (memory or {}).get("op", "").upper()
    wrote = op in {"ADD", "UPDATE"}

    outcome = (outcome or "").upper()
    expected_nonempty = bool(expected_keys)
    actionable = outcome == "CONFIRMED"

    mw_score = -1.0
    mws_score = -1.0
    reason = ""

    # Memory write applies when transcript is actionable and grounded in dossier.
    if actionable and expected_nonempty:
        mw_score = 1.0 if wrote else 0.0
        reason = f"actionable; expected memory; op={op or 'none'}"
    elif actionable and not expected_nonempty:
        # Actionable but gold says no memory grounding needed - skip dim.
        reason = "actionable but no expected memory"
    # Memory write skip applies for non-actionable outcomes.
    if outcome in {"LIFE_LOG", "CANCELLED"}:
        mws_score = 1.0 if not wrote else 0.0
        reason = (reason + "; " if reason else "") + f"non-actionable; op={op or 'none'}"
    return mw_score, mws_score, reason


# ---------- LLM judge for action faithfulness ---------------------------- #
JUDGE_PROMPT = """You are an evaluator for an ambient AI assistant called Anticipy. \
You are given the user's raw speech, the gold-standard expected intent, and \
what Anticipy actually planned to do. Score how well the plan matches what \
the user asked for, on a 0.0 to 1.0 scale.

Scoring rubric:
  1.0  plan does what the user asked, addresses the key constraints, names the \
       right people/places where the user named them.
  0.8  plan does what the user asked but misses a non-critical constraint or \
       uses a generic stand-in for a named entity.
  0.5  plan addresses the topic but is materially incomplete or wrong on a \
       constraint the user stated explicitly.
  0.2  plan is in the right general area but missed the core intent (e.g. \
       asks a clarifying question when the user gave enough detail to act).
  0.0  plan is wrong (acts when user said don't act, or vice versa) or empty.

For chatter (gold says "don't act", "capture only" or "do not surface during \
work week"), a NOOP / capture-only plan is correct and should score 1.0; an \
attempt to act should score 0.0.

Respond with ONLY a JSON object of this exact shape, no prose:
{
  "score": <float in [0.0, 1.0]>,
  "reason": "<one sentence, no more than 30 words>"
}
"""

def _judge_payload(transcript_id: str, raw: str, gold_intent: str, plan: dict,
                   outcome: str) -> str:
    plan_summary = json.dumps(plan or {}, ensure_ascii=False)
    return JUDGE_PROMPT + (
        f"\n\nTranscript id: {transcript_id}\n"
        f"User said: {raw}\n\n"
        f"Gold expected intent: {gold_intent}\n\n"
        f"Engine outcome: {outcome}\n"
        f"Engine plan (JSON): {plan_summary}\n"
    )


class BudgetExceeded(Exception):
    pass


def call_judge(prompt: str, cost_meter: dict, budget: float, timeout: float = 60.0) -> tuple[dict, str, dict]:
    """Try the judge cascade. Return (parsed_dict, model_used, usage_info)."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    last_err = None
    for model in CASCADE:
        if cost_meter["usd_spent"] >= budget:
            raise BudgetExceeded(f"budget ${budget:.2f} exhausted (${cost_meter['usd_spent']:.4f})")
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            # Many of these models think before answering and burn output tokens
            # on reasoning. We need enough headroom so the final JSON content
            # still fits. 800 is a comfortable safety margin for a tiny verdict.
            "max_tokens": 800,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://anticipy.ai",
                "X-Title": "Anticipy V7 memory precision scorer",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_err = f"{model}: {exc}"
            continue
        except json.JSONDecodeError as exc:
            last_err = f"{model}: bad json {exc}"
            continue

        choices = payload.get("choices") or []
        usage = payload.get("usage") or {}
        if usage:
            in_tok = usage.get("prompt_tokens", 0)
            out_tok = usage.get("completion_tokens", 0)
            # OpenRouter returns the actual cost in the response. Prefer that
            # over price-table arithmetic so cascade re-routing is captured.
            actual_cost = usage.get("cost")
            if actual_cost is None:
                prices = PRICES_PER_MTOK.get(model, {"in": 0.50, "out": 1.00})
                actual_cost = (in_tok * prices["in"] + out_tok * prices["out"]) / 1_000_000.0
            cost_meter["usd_spent"] += float(actual_cost)
            cost_meter["calls"] += 1
            cost_meter["tokens_in"] += in_tok
            cost_meter["tokens_out"] += out_tok
        if not choices:
            last_err = f"{model}: no choices"
            continue
        finish = choices[0].get("finish_reason", "")
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            last_err = f"{model}: empty content (finish={finish})"
            continue
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract.
            m = re.search(r"\{.*\}", content, re.S)
            if m:
                try:
                    parsed = json.loads(m.group(0))
                except json.JSONDecodeError:
                    last_err = f"{model}: bad json: {content[:200]}"
                    continue
            else:
                last_err = f"{model}: no json: {content[:200]}"
                continue
        # Validate shape.
        if not isinstance(parsed, dict) or "score" not in parsed:
            last_err = f"{model}: missing score: {parsed}"
            continue
        try:
            parsed["score"] = float(parsed["score"])
        except (TypeError, ValueError):
            last_err = f"{model}: non-float score: {parsed['score']}"
            continue
        parsed["score"] = max(0.0, min(1.0, parsed["score"]))
        return parsed, model, usage
    raise RuntimeError(f"judge cascade exhausted; last error: {last_err}")


# ---------- per-transcript scoring --------------------------------------- #
def score_transcript(t: dict, inject: dict, alignment: dict, cost_meter: dict,
                     budget: float) -> dict:
    raw = t.get("raw", "")
    gold_intent = t.get("expected_intent", "")
    expected_keys = t.get("expected_memory_used", []) or []
    outcome = (inject.get("outcome") or "").upper()
    plan = inject.get("plan") or (inject.get("pending") or {}).get("plan") or {}
    memory = inject.get("memory") or {}

    intent_score, pred_intent, gold_intent_cat = score_intent(gold_intent, plan)
    entity_score, entity_hits = score_entity_precision(expected_keys, plan, raw, alignment)
    mw_score, mws_score, mw_reason = score_memory_write(outcome, expected_keys, memory, plan)

    # Action faithfulness via LLM judge.
    judge = {"score": None, "reason": "", "model": None}
    try:
        prompt = _judge_payload(t.get("id", "T??"), raw, gold_intent, plan, outcome)
        verdict, model_used, usage = call_judge(prompt, cost_meter, budget)
        judge = {"score": verdict.get("score"), "reason": verdict.get("reason", ""),
                 "model": model_used}
    except BudgetExceeded as exc:
        judge = {"score": None, "reason": f"BUDGET_EXCEEDED: {exc}", "model": None}
    except Exception as exc:
        judge = {"score": None, "reason": f"judge_error: {exc}", "model": None}

    return {
        "id": t.get("id"),
        "category": t.get("category"),
        "difficulty": t.get("difficulty"),
        "outcome": outcome,
        "gold_intent_text": gold_intent,
        "engine_plan": plan,
        "engine_memory_op": memory.get("op"),
        "scores": {
            "intent_precision": round(intent_score, 3),
            "entity_precision": round(entity_score, 3),
            "action_faithfulness": (round(judge["score"], 3)
                                    if judge["score"] is not None else None),
            "memory_write": round(mw_score, 3) if mw_score >= 0 else None,
            "memory_write_skip": round(mws_score, 3) if mws_score >= 0 else None,
        },
        "details": {
            "intent": {"predicted": pred_intent, "gold_category": gold_intent_cat},
            "entity": {"expected_keys": expected_keys, "hits": entity_hits},
            "memory": {"reason": mw_reason},
            "judge": judge,
        },
    }


def aggregate(verdicts: list[dict]) -> dict:
    dims = ("intent_precision", "entity_precision", "action_faithfulness",
            "memory_write", "memory_write_skip")
    out = {}
    for d in dims:
        vals = [v["scores"][d] for v in verdicts if v["scores"].get(d) is not None]
        out[d] = {
            "count": len(vals),
            "mean": round(sum(vals) / len(vals), 4) if vals else None,
            "min": round(min(vals), 3) if vals else None,
            "max": round(max(vals), 3) if vals else None,
        }
    # Per-difficulty breakdown.
    tiers = {}
    for v in verdicts:
        d = v.get("difficulty")
        if d is None:
            continue
        tiers.setdefault(d, []).append(v)
    by_tier = {}
    for d, items in sorted(tiers.items()):
        by_tier[str(d)] = {}
        for dim in dims:
            vals = [it["scores"][dim] for it in items if it["scores"].get(dim) is not None]
            by_tier[str(d)][dim] = round(sum(vals) / len(vals), 4) if vals else None
    out["_by_difficulty"] = by_tier
    return out


def per_transcript_total(v: dict) -> float:
    scores = [s for s in v["scores"].values() if s is not None]
    return sum(scores) / len(scores) if scores else 0.0


# ---------- markdown report ---------------------------------------------- #
def render_markdown(run_id: str, verdicts: list[dict], agg: dict,
                    cost_meter: dict, alignment: dict, budget: float) -> str:
    lines = [f"# Memory precision scorer run {run_id}", ""]
    lines.append(f"- Transcripts scored: {len(verdicts)}")
    lines.append(f"- Alignment: {alignment['matched']}/{alignment['total_keys']} "
                 f"gold keys matched to dossier")
    lines.append(f"- Judge cost: ${cost_meter['usd_spent']:.4f} of ${budget:.2f} budget")
    lines.append(f"- Judge calls: {cost_meter['calls']}; "
                 f"tokens in/out: {cost_meter['tokens_in']}/{cost_meter['tokens_out']}")
    lines.append("")
    lines.append("## Aggregate per-dimension means")
    lines.append("")
    lines.append("| Dimension | Mean | Count | Min | Max |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for d in ("intent_precision", "entity_precision", "action_faithfulness",
              "memory_write", "memory_write_skip"):
        a = agg[d]
        m = f"{a['mean']:.3f}" if a["mean"] is not None else "N/A"
        mn = f"{a['min']:.2f}" if a["min"] is not None else "N/A"
        mx = f"{a['max']:.2f}" if a["max"] is not None else "N/A"
        lines.append(f"| {d} | {m} | {a['count']} | {mn} | {mx} |")
    lines.append("")
    lines.append("## By difficulty tier")
    lines.append("")
    lines.append("| Difficulty | intent | entity | action | mem_write | mem_skip |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: |")
    for d, vals in agg["_by_difficulty"].items():
        def f(k):
            v = vals.get(k)
            return f"{v:.3f}" if v is not None else "N/A"
        lines.append(f"| {d} | {f('intent_precision')} | {f('entity_precision')} | "
                     f"{f('action_faithfulness')} | {f('memory_write')} | "
                     f"{f('memory_write_skip')} |")
    lines.append("")
    ranked = sorted(verdicts, key=per_transcript_total)
    def row(v):
        s = v["scores"]
        def fmt(k):
            x = s.get(k)
            return f"{x:.2f}" if x is not None else "-"
        reason = (v["details"]["judge"].get("reason") or v["details"]["memory"]["reason"]
                  or "").replace("|", "/")[:80]
        return (f"| {v['id']} | {v['difficulty']} | {v['outcome']} | "
                f"{per_transcript_total(v):.2f} | {fmt('intent_precision')} | "
                f"{fmt('entity_precision')} | {fmt('action_faithfulness')} | "
                f"{fmt('memory_write')} | {fmt('memory_write_skip')} | {reason} |")
    hdr_cols = ("| id | diff | outcome | composite | intent | entity | action | "
                "mem_write | mem_skip | one-line reason |")
    hdr_sep = "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"

    lines.append("## Top 3 transcripts (highest composite scores)")
    lines.append("")
    lines.append(hdr_cols)
    lines.append(hdr_sep)
    for v in ranked[::-1][:3]:
        lines.append(row(v))
    lines.append("")
    lines.append("## Bottom 10 transcripts (lowest composite scores)")
    lines.append("")
    lines.append(hdr_cols)
    lines.append(hdr_sep)
    for v in ranked[:10]:
        lines.append(row(v))
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------- main --------------------------------------------------------- #
def load_env_local():
    p = Path("/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local")
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, default=RUN_DIR,
                        help="directory containing T*_inject.json")
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET)
    parser.add_argument("--rebuild-alignment", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="skip OpenRouter calls; judge scores set to None")
    args = parser.parse_args(argv)

    load_env_local()

    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    dossier = json.loads(DOSSIER.read_text(encoding="utf-8"))
    alignment = build_alignment(gold, dossier, force_rebuild=args.rebuild_alignment)

    cost_meter = {"usd_spent": 0.0, "calls": 0, "tokens_in": 0, "tokens_out": 0}
    verdicts = []
    for t in gold.get("transcripts", []):
        inj_path = args.run_dir / f"{t['id']}_inject.json"
        if not inj_path.exists():
            print(f"warn: missing {inj_path}", file=sys.stderr)
            continue
        inject = json.loads(inj_path.read_text(encoding="utf-8"))
        if args.dry_run:
            # Skip judge calls.
            os.environ["OPENROUTER_API_KEY"] = ""  # forces RuntimeError → judge None
        v = score_transcript(t, inject, alignment, cost_meter,
                             args.budget if not args.dry_run else 0.0)
        verdicts.append(v)

    agg = aggregate(verdicts)
    run_id = args.run_dir.name.split("_")[-1] if "_" in args.run_dir.name else time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_json = REPO / f"state/v7/memory_precision_{run_id}.json"
    out_md = REPO / f"state/v7/memory_precision_{run_id}.md"

    payload = {
        "schema": "anticipy.v7.memory_precision.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_dir": str(args.run_dir.relative_to(REPO)),
        "alignment_path": str(GOLD_MAP.relative_to(REPO)),
        "judge_cascade": list(CASCADE),
        "budget_usd": args.budget,
        "cost": cost_meter,
        "aggregate": agg,
        "verdicts": verdicts,
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    out_md.write_text(render_markdown(run_id, verdicts, agg, cost_meter, alignment,
                                       args.budget), encoding="utf-8")
    print(json.dumps({
        "out_json": str(out_json),
        "out_md": str(out_md),
        "aggregate_means": {k: agg[k]["mean"] for k in
                            ("intent_precision", "entity_precision",
                             "action_faithfulness", "memory_write", "memory_write_skip")},
        "cost": cost_meter,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
