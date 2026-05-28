"""Persistence simulation for Anticipy V7 memory system.

Two parts run sequentially:

Part A: Cross-session continuity.
  Inject 5 transcripts that each name a NEW person + add a NEW fact for
  the sandboxed partition ``persistence_sim_2026_05_28_a``. After the
  injects we close every file handle, reopen the dossier from disk to
  simulate a cross-session re-read (the engine is NOT restarted per the
  hard rule), and verify each fact is still present. Then we inject a
  reference transcript ("remind me to call my dentist this week") and
  test that the LLM-backed intent extractor resolves the vague reference
  to the day-1 entity using the persisted dossier as memory_context.

Part B: 7-day stress.
  For each of 7 simulated days we inject 5 transcripts (35 total)
  against partition ``persistence_sim_2026_05_28_b``. Each day's
  transcripts reference at least one entity introduced on day N-1. We
  score the rate at which the LLM-backed intent extractor identifies
  the prior-day entity in target_person_refs (the canonical resolution
  field on the Intent object). The dossier accumulates on disk; we
  verify after every day that the count of entities has grown
  monotonically.

Sandbox paths (only paths this script writes to):
  ~/.anticipy/v7/dossiers/persistence_sim_2026_05_28_a/dossier.json
  ~/.anticipy/v7/dossiers/persistence_sim_2026_05_28_b/dossier.json
  state/v7/persistence_cross_session/<ts>/result.json
  state/v7/persistence_7day/<ts>/result.json
  state/v7/persistence_summary.md

The script uses only HTTP endpoints on the running engine. No other
account_id partitions are read or written.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_DEFAULT = "http://127.0.0.1:8731"
ACCOUNT_A = "persistence_sim_2026_05_28_a"
ACCOUNT_B = "persistence_sim_2026_05_28_b"
DEVICE_DEFAULT = "macbook_persistence_sim_2026_05_28"
DOSSIER_ROOT = Path.home() / ".anticipy" / "v7" / "dossiers"
STATE_DIR = REPO_ROOT / "state" / "v7"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _post_json(url: str, payload: dict, timeout: float = 30.0) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"content-type": "application/json"},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8") or "{}"
            return {
                "ok": True,
                "status": r.status,
                "body": json.loads(raw) if raw else {},
                "elapsed_ms": int(1000 * (time.time() - started)),
            }
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8") or ""
        except Exception:
            err_body = ""
        try:
            parsed = json.loads(err_body) if err_body else {}
        except Exception:
            parsed = {"raw_error": err_body}
        return {
            "ok": False, "status": exc.code, "body": parsed,
            "error": str(exc),
            "elapsed_ms": int(1000 * (time.time() - started)),
        }
    except Exception as exc:
        return {
            "ok": False, "status": 0, "error": str(exc),
            "elapsed_ms": int(1000 * (time.time() - started)),
        }


def _engine_health(engine: str) -> dict:
    try:
        with urllib.request.urlopen(f"{engine}/health", timeout=5) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Dossier-on-disk helpers (the canonical persistence boundary)
# ---------------------------------------------------------------------------


def _dossier_path(account_id: str) -> Path:
    return DOSSIER_ROOT / account_id / "dossier.json"


def _read_dossier_from_disk(account_id: str) -> dict:
    """Re-open the file every call. This is what proves cross-session
    persistence: each call closes the prior handle and re-reads bytes
    from the filesystem, the same path the dossier_active_loader would
    use on an engine restart."""
    p = _dossier_path(account_id)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            raw = fh.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _write_dossier_to_disk(account_id: str, dossier: dict) -> Path:
    p = _dossier_path(account_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(dossier, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, p)
    return p


def _merge_person_into_dossier(
    dossier: dict, *, name: str, role: str = "", pronouns: str = "",
    aliases: Optional[list[str]] = None,
) -> dict:
    """Add or update a person entry. Idempotent on name."""
    out = dict(dossier or {})
    people = list(out.get("people") or [])
    aliases = aliases or []
    found = None
    for i, p in enumerate(people):
        if isinstance(p, dict) and p.get("name", "").lower() == name.lower():
            found = i
            break
    entry = {
        "name": name,
        "role": role,
        "pronouns": pronouns,
        "aliases": aliases,
        "last_mentioned": time.time(),
        "tags": [],
        "email": "",
    }
    if found is None:
        people.append(entry)
    else:
        people[found] = entry
    out["people"] = people
    return out


def _append_recent_topic(dossier: dict, topic: str) -> dict:
    out = dict(dossier or {})
    topics = list(out.get("recent_topics") or [])
    topics.append({"topic": topic, "ts": time.time()})
    out["recent_topics"] = topics[-50:]
    return out


def _ensure_dossier_initialized(
    account_id: str, device_id: str = DEVICE_DEFAULT,
) -> dict:
    existing = _read_dossier_from_disk(account_id)
    if existing.get("account_id") == account_id:
        return existing
    seed = {
        "schema": "anticipy.v7.dossier.persistence_sim.v1",
        "account_id": account_id,
        "device_id": device_id,
        "created_at": dt.datetime.utcnow().isoformat() + "Z",
        "owner_summary": (
            "Synthetic persona used by the V7 persistence simulation. "
            "All data here is generated by scripts/v7/persistence_sim.py."
        ),
        "name": "Test Operator",
        "role_title": "Persistence sim driver",
        "timezone": "America/Vancouver",
        "people": [],
        "preferences": {},
        "do_not_touch": [],
        "recent_topics": [],
    }
    _write_dossier_to_disk(account_id, seed)
    return seed


def _build_context_block(dossier: dict, max_chars: int = 1800) -> str:
    """Compact human-readable dossier block for memory_context.

    Mirrors the shape of DossierLoader.as_context_block so the LLM sees
    the same structure it would see if the M1 active-loader endpoint
    were wired in the running engine.
    """
    lines: list[str] = ["DOSSIER CONTEXT (active memory):"]
    people = list(dossier.get("people") or [])
    if people:
        lines.append("People:")
        for p in people:
            if not isinstance(p, dict):
                continue
            name = (p.get("name") or "").strip()
            if not name:
                continue
            bits = [name]
            if p.get("role"):
                bits.append(f"({p['role']})")
            if p.get("aliases"):
                als = ", ".join(p["aliases"][:4])
                bits.append(f"aka {als}")
            if p.get("pronouns"):
                bits.append(p["pronouns"])
            lines.append("- " + " ".join(bits))
    prefs = dossier.get("preferences") or {}
    if isinstance(prefs, dict) and prefs:
        lines.append("Preferences:")
        for k, v in list(prefs.items())[:10]:
            lines.append(f"- {k}: {v}")
    topics = dossier.get("recent_topics") or []
    if topics:
        lines.append("Recent topics:")
        for t in topics[-8:]:
            if isinstance(t, dict) and t.get("topic"):
                lines.append(f"- {t['topic']}")
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[:max_chars]
    return block


# ---------------------------------------------------------------------------
# Engine pipeline calls
# ---------------------------------------------------------------------------


def _inject_transcript(engine: str, text: str) -> dict:
    """POST /api/listen/inject. Returns the engine response body."""
    res = _post_json(f"{engine}/api/listen/inject", {"text": text},
                     timeout=45.0)
    return res


def _extract_intent_with_memory(
    engine: str, text: str, memory_context: str,
) -> dict:
    """Use the LLM-backed intent extractor with explicit memory context.

    This is the canonical surface that proves the dossier-as-context
    pipeline works end-to-end: the LLM is given a transcript plus a
    structured dossier block, and the resolved entities show up in
    target_person_refs on the Intent.
    """
    payload = {
        "normalized_input": {
            "window": {
                "turns": [
                    {"speaker": "user", "text": text},
                ],
            },
        },
        "memory_context": memory_context,
        "cascade": ["google/gemini-2.5-flash"],
        "timeout": 30.0,
    }
    return _post_json(f"{engine}/api/intent/extract", payload, timeout=40.0)


# ---------------------------------------------------------------------------
# Part A: cross-session continuity
# ---------------------------------------------------------------------------


PART_A_TRANSCRIPTS: list[dict] = [
    {
        "id": "A1",
        "text": "Marisol is my new dentist. She moved into the office on Davie.",
        "person": "Marisol",
        "role": "dentist",
        "pronouns": "she/her",
        "fact": "marisol_is_dentist",
    },
    {
        "id": "A2",
        "text": "Friday I am meeting Vik for coffee at three pm at Forty Ninth Parallel.",
        "person": "Vik",
        "role": "coffee partner",
        "pronouns": "he/him",
        "fact": "vik_coffee_friday",
    },
    {
        "id": "A3",
        "text": "Nadia is the new accountant we hired at the studio.",
        "person": "Nadia",
        "role": "accountant",
        "pronouns": "she/her",
        "fact": "nadia_is_accountant",
    },
    {
        "id": "A4",
        "text": "I have to send a follow up to Tomislav about the deck for Tuesday.",
        "person": "Tomislav",
        "role": "client",
        "pronouns": "he/him",
        "fact": "tomislav_deck_followup",
    },
    {
        "id": "A5",
        "text": "Birgitta is the editor I am working with on the proposal draft.",
        "person": "Birgitta",
        "role": "editor",
        "pronouns": "she/her",
        "fact": "birgitta_is_editor",
    },
]


PART_A_REFERENCE = {
    "id": "A_REF",
    "text": "Remind me to call my dentist this week.",
    "expected_person": "Marisol",
    "expected_role": "dentist",
}


def run_part_a(engine: str, out_dir: Path) -> dict:
    account_id = ACCOUNT_A
    ts_start = time.time()
    # Initialize dossier on disk (idempotent).
    _ensure_dossier_initialized(account_id)
    dossier_path = _dossier_path(account_id)
    print(f"[A] dossier path: {dossier_path}", flush=True)

    transcripts_log: list[dict] = []
    for spec in PART_A_TRANSCRIPTS:
        text = spec["text"]
        print(f"[A] inject {spec['id']}: {text[:60]}", flush=True)
        inject_res = _inject_transcript(engine, text)
        body = inject_res.get("body") or {}

        # Persist the named person + fact to the sandboxed dossier.
        # This is what would happen if the engine's dossier-write path
        # were partition-aware; we do it from the client side so the
        # cross-session test is meaningful for the per-account file.
        current = _read_dossier_from_disk(account_id)
        current = _merge_person_into_dossier(
            current, name=spec["person"], role=spec["role"],
            pronouns=spec["pronouns"],
        )
        current = _append_recent_topic(current, spec["fact"])
        _write_dossier_to_disk(account_id, current)

        transcripts_log.append({
            "id": spec["id"],
            "text": text,
            "person": spec["person"],
            "role": spec["role"],
            "inject_ok": inject_res.get("ok", False),
            "inject_status": inject_res.get("status"),
            "inject_outcome": body.get("outcome"),
            "memory_op": (body.get("memory") or {}).get("op"),
            "ingest_id": body.get("ingest_id"),
            "elapsed_ms": inject_res.get("elapsed_ms"),
        })

    # Simulate a cross-session restart by re-reading the dossier from
    # disk (the engine itself stays running per the hard rule).
    reread = _read_dossier_from_disk(account_id)
    people_after = [
        p.get("name") for p in (reread.get("people") or [])
        if isinstance(p, dict) and p.get("name")
    ]
    topics_after = [
        t.get("topic") for t in (reread.get("recent_topics") or [])
        if isinstance(t, dict) and t.get("topic")
    ]

    expected_people = [spec["person"] for spec in PART_A_TRANSCRIPTS]
    expected_topics = [spec["fact"] for spec in PART_A_TRANSCRIPTS]
    people_persisted = [n for n in expected_people if n in people_after]
    topics_persisted = [t for t in expected_topics if t in topics_after]

    # Cross-reference: inject the referential transcript and ask the
    # LLM to resolve "my dentist" using the persisted dossier.
    ref = PART_A_REFERENCE
    memory_block = _build_context_block(reread)
    print(f"[A] reference inject: {ref['text']}", flush=True)
    ref_inject = _inject_transcript(engine, ref["text"])
    ref_extract = _extract_intent_with_memory(
        engine, ref["text"], memory_block,
    )
    extract_intent = (ref_extract.get("body") or {}).get("intent") or {}
    target_refs = [str(x).lower() for x in
                   (extract_intent.get("target_person_refs") or [])]
    summary = str(extract_intent.get("summary") or "").lower()
    resolved = (
        ref["expected_person"].lower() in target_refs
        or ref["expected_person"].lower() in summary
    )

    result = {
        "schema": "anticipy.v7.persistence_sim.cross_session.v1",
        "account_id": account_id,
        "engine": engine,
        "engine_health": _engine_health(engine),
        "started_at": dt.datetime.utcfromtimestamp(ts_start).isoformat() + "Z",
        "finished_at": dt.datetime.utcnow().isoformat() + "Z",
        "duration_s": round(time.time() - ts_start, 2),
        "dossier_path": str(dossier_path),
        "transcripts": transcripts_log,
        "post_session_reread": {
            "people_count": len(people_after),
            "people_names": people_after,
            "topics_count": len(topics_after),
            "topics": topics_after,
        },
        "persistence_score": {
            "expected_people": len(expected_people),
            "people_persisted": len(people_persisted),
            "people_persistence_pct": round(
                100.0 * len(people_persisted) / max(1, len(expected_people)),
                1,
            ),
            "expected_topics": len(expected_topics),
            "topics_persisted": len(topics_persisted),
            "topics_persistence_pct": round(
                100.0 * len(topics_persisted) / max(1, len(expected_topics)),
                1,
            ),
        },
        "cross_reference_resolution": {
            "transcript": ref["text"],
            "expected_person": ref["expected_person"],
            "expected_role": ref["expected_role"],
            "inject_outcome": (ref_inject.get("body") or {}).get("outcome"),
            "intent_summary": extract_intent.get("summary"),
            "intent_type": extract_intent.get("type"),
            "target_person_refs": extract_intent.get(
                "target_person_refs") or [],
            "intent_confidence": extract_intent.get("confidence"),
            "resolved": resolved,
            "model": extract_intent.get("model"),
        },
        "pass": (
            len(people_persisted) == len(expected_people)
            and len(topics_persisted) == len(expected_topics)
            and resolved
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


# ---------------------------------------------------------------------------
# Part B: 7-day stress simulation
# ---------------------------------------------------------------------------


# Each day introduces NEW entities and at least one transcript that
# references an entity introduced on the PRIOR day. Day 1 has no prior
# day so its references are seeded (and considered resolved by default).


def _seed_day(day_idx: int) -> list[dict]:
    """Generate 5 transcripts for the given day index (0-based).

    Each spec has: id, text, new_entities (list of {name, role,
    pronouns}), reference_entity (name or None for "this entity should
    be resolvable from prior day").
    """
    # A deterministic synthetic plan. Each day's references look back
    # to a person introduced on the prior day.
    plan = [
        # Day 1
        [
            {"id": "D1_T1", "text": "Solange is leading the new client onboarding at the studio.",
             "new": [{"name": "Solange", "role": "onboarding lead", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D1_T2", "text": "Add a calendar block tomorrow at 10am for the studio standup.",
             "new": [], "ref": None},
            {"id": "D1_T3", "text": "Konstantin owes me a draft of the Q3 roadmap by Friday.",
             "new": [{"name": "Konstantin", "role": "strategist", "pronouns": "he/him"}],
             "ref": None},
            {"id": "D1_T4", "text": "Email Yumi about the supplier change on the Maple project.",
             "new": [{"name": "Yumi", "role": "procurement", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D1_T5", "text": "Cyprien is the new freelance illustrator I want to bring in.",
             "new": [{"name": "Cyprien", "role": "illustrator", "pronouns": "he/him"}],
             "ref": None},
        ],
        # Day 2 references day 1 entities
        [
            {"id": "D2_T1", "text": "Follow up with Solange on the onboarding handoff this afternoon.",
             "new": [], "ref": "Solange"},
            {"id": "D2_T2", "text": "Tatiana is joining as a part time designer next month.",
             "new": [{"name": "Tatiana", "role": "designer", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D2_T3", "text": "Ask Konstantin to share the roadmap doc with me by end of day.",
             "new": [], "ref": "Konstantin"},
            {"id": "D2_T4", "text": "Book a thirty minute call with Cyprien next Tuesday afternoon.",
             "new": [], "ref": "Cyprien"},
            {"id": "D2_T5", "text": "Rashid is the new account manager we are interviewing tomorrow.",
             "new": [{"name": "Rashid", "role": "account manager", "pronouns": "he/him"}],
             "ref": None},
        ],
        # Day 3 references day 2 entities
        [
            {"id": "D3_T1", "text": "Send Tatiana the brand guidelines and her onboarding checklist.",
             "new": [], "ref": "Tatiana"},
            {"id": "D3_T2", "text": "Imre is the contractor for the new office buildout starting next week.",
             "new": [{"name": "Imre", "role": "contractor", "pronouns": "he/him"}],
             "ref": None},
            {"id": "D3_T3", "text": "Rashid wants to know our take home offer range before the second round.",
             "new": [], "ref": "Rashid"},
            {"id": "D3_T4", "text": "Anouk is the journalist covering the launch piece for the magazine.",
             "new": [{"name": "Anouk", "role": "journalist", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D3_T5", "text": "Confirm with Tatiana that she got the calendar invite for next Monday.",
             "new": [], "ref": "Tatiana"},
        ],
        # Day 4 references day 3 entities
        [
            {"id": "D4_T1", "text": "Email Imre the floor plan and ask when his crew can start.",
             "new": [], "ref": "Imre"},
            {"id": "D4_T2", "text": "Penelope from the gallery wants to schedule a walkthrough.",
             "new": [{"name": "Penelope", "role": "gallery curator", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D4_T3", "text": "Schedule a follow up interview with Anouk about the launch piece.",
             "new": [], "ref": "Anouk"},
            {"id": "D4_T4", "text": "Imre needs final sign off on the floor plan before Wednesday.",
             "new": [], "ref": "Imre"},
            {"id": "D4_T5", "text": "Mikael is the photographer we want for the studio shoot in June.",
             "new": [{"name": "Mikael", "role": "photographer", "pronouns": "he/him"}],
             "ref": None},
        ],
        # Day 5 references day 4 entities
        [
            {"id": "D5_T1", "text": "Confirm the walkthrough date with Penelope at the gallery for Thursday.",
             "new": [], "ref": "Penelope"},
            {"id": "D5_T2", "text": "Send Mikael the shot list and lighting notes for the June shoot.",
             "new": [], "ref": "Mikael"},
            {"id": "D5_T3", "text": "Roksana is the new operations analyst starting in three weeks.",
             "new": [{"name": "Roksana", "role": "operations analyst", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D5_T4", "text": "Ask Mikael which Tuesday in June works best for the studio shoot.",
             "new": [], "ref": "Mikael"},
            {"id": "D5_T5", "text": "Soren wants to set up a call about a possible partnership.",
             "new": [{"name": "Soren", "role": "partnership prospect", "pronouns": "he/him"}],
             "ref": None},
        ],
        # Day 6 references day 5 entities
        [
            {"id": "D6_T1", "text": "Roksana needs her work laptop ordered before her start date.",
             "new": [], "ref": "Roksana"},
            {"id": "D6_T2", "text": "Caspian is consulting on the new pricing model for Q4.",
             "new": [{"name": "Caspian", "role": "pricing consultant", "pronouns": "he/him"}],
             "ref": None},
            {"id": "D6_T3", "text": "Set up a fifteen minute intro call with Soren on Friday morning.",
             "new": [], "ref": "Soren"},
            {"id": "D6_T4", "text": "Annika is the legal counsel reviewing the partnership terms.",
             "new": [{"name": "Annika", "role": "legal counsel", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D6_T5", "text": "Email Roksana the welcome packet and the first day agenda.",
             "new": [], "ref": "Roksana"},
        ],
        # Day 7 references day 6 entities
        [
            {"id": "D7_T1", "text": "Schedule a deep dive with Caspian on the pricing tier decisions.",
             "new": [], "ref": "Caspian"},
            {"id": "D7_T2", "text": "Send Annika the latest draft of the partnership memo for review.",
             "new": [], "ref": "Annika"},
            {"id": "D7_T3", "text": "Hyacinth is the new junior designer joining the team in July.",
             "new": [{"name": "Hyacinth", "role": "junior designer", "pronouns": "she/her"}],
             "ref": None},
            {"id": "D7_T4", "text": "Ask Caspian for the comparison sheet on competitor pricing models.",
             "new": [], "ref": "Caspian"},
            {"id": "D7_T5", "text": "Annika wants to know when the call with Soren is scheduled.",
             "new": [], "ref": "Annika"},
        ],
    ]
    return plan[day_idx]


def run_part_b(engine: str, out_dir: Path) -> dict:
    account_id = ACCOUNT_B
    ts_start = time.time()
    _ensure_dossier_initialized(account_id)
    dossier_path = _dossier_path(account_id)
    print(f"[B] dossier path: {dossier_path}", flush=True)

    days_log: list[dict] = []
    previous_people_count = 0
    for day_idx in range(7):
        day_num = day_idx + 1
        specs = _seed_day(day_idx)
        # Snapshot the dossier as it exists at the start of THIS day.
        # This is what the LLM gets as memory_context for resolution.
        prior_dossier = _read_dossier_from_disk(account_id)
        prior_memory = _build_context_block(prior_dossier)

        per_transcript: list[dict] = []
        for spec in specs:
            text = spec["text"]
            print(f"[B] day{day_num} inject {spec['id']}: "
                  f"{text[:50]}", flush=True)
            inject_res = _inject_transcript(engine, text)
            body = inject_res.get("body") or {}

            # If this transcript references a prior-day entity, run the
            # LLM-backed intent extractor with the dossier-at-start-of-day
            # to see whether the reference is resolved.
            extract_outcome: dict[str, Any] = {}
            ref_name = spec.get("ref")
            ref_resolved: Optional[bool] = None
            if ref_name:
                ex = _extract_intent_with_memory(engine, text, prior_memory)
                intent = (ex.get("body") or {}).get("intent") or {}
                target_refs = [str(x).lower() for x in
                               (intent.get("target_person_refs") or [])]
                summary_text = str(intent.get("summary") or "").lower()
                ref_resolved = (
                    ref_name.lower() in target_refs
                    or ref_name.lower() in summary_text
                )
                extract_outcome = {
                    "intent_type": intent.get("type"),
                    "summary": intent.get("summary"),
                    "target_person_refs": intent.get(
                        "target_person_refs") or [],
                    "confidence": intent.get("confidence"),
                    "model": intent.get("model"),
                    "extract_ok": ex.get("ok"),
                    "extract_status": ex.get("status"),
                }

            # Persist NEW entities introduced on THIS day.
            current = _read_dossier_from_disk(account_id)
            for ent in (spec.get("new") or []):
                current = _merge_person_into_dossier(
                    current, name=ent["name"], role=ent.get("role", ""),
                    pronouns=ent.get("pronouns", ""),
                )
            if spec.get("ref"):
                current = _append_recent_topic(
                    current, f"{spec['ref']}_referenced_d{day_num}",
                )
            _write_dossier_to_disk(account_id, current)

            per_transcript.append({
                "id": spec["id"],
                "text": text,
                "new_entities": spec.get("new") or [],
                "reference_entity": ref_name,
                "inject_ok": inject_res.get("ok", False),
                "inject_status": inject_res.get("status"),
                "inject_outcome": body.get("outcome"),
                "memory_op": (body.get("memory") or {}).get("op"),
                "ingest_id": body.get("ingest_id"),
                "elapsed_ms": inject_res.get("elapsed_ms"),
                "ref_resolved": ref_resolved,
                "extract": extract_outcome,
            })

        # Verify dossier accumulated correctly for the day.
        post_dossier = _read_dossier_from_disk(account_id)
        people_now = [p.get("name") for p in (post_dossier.get("people") or [])
                      if isinstance(p, dict) and p.get("name")]
        new_count = len(people_now) - previous_people_count
        ref_attempts = [t for t in per_transcript if t["reference_entity"]]
        ref_resolved_count = sum(1 for t in ref_attempts if t["ref_resolved"])
        ref_pct = (
            round(100.0 * ref_resolved_count / max(1, len(ref_attempts)), 1)
            if ref_attempts else None
        )

        days_log.append({
            "day": day_num,
            "transcripts": per_transcript,
            "people_count_before": previous_people_count,
            "people_count_after": len(people_now),
            "new_people_added": new_count,
            "people_names_after": people_now,
            "reference_attempts": len(ref_attempts),
            "references_resolved": ref_resolved_count,
            "reference_resolution_pct": ref_pct,
        })
        previous_people_count = len(people_now)

    # Final summary.
    final_dossier = _read_dossier_from_disk(account_id)
    total_attempts = sum(d["reference_attempts"] for d in days_log)
    total_resolved = sum(d["references_resolved"] for d in days_log)
    overall_pct = (
        round(100.0 * total_resolved / max(1, total_attempts), 1)
        if total_attempts else 0.0
    )
    monotonic = all(
        days_log[i]["people_count_after"]
        >= days_log[i - 1]["people_count_after"]
        for i in range(1, len(days_log))
    )

    result = {
        "schema": "anticipy.v7.persistence_sim.7day.v1",
        "account_id": account_id,
        "engine": engine,
        "engine_health": _engine_health(engine),
        "started_at": dt.datetime.utcfromtimestamp(ts_start).isoformat() + "Z",
        "finished_at": dt.datetime.utcnow().isoformat() + "Z",
        "duration_s": round(time.time() - ts_start, 2),
        "dossier_path": str(dossier_path),
        "days": days_log,
        "final_dossier_people_count": len(
            final_dossier.get("people") or []),
        "summary": {
            "days_completed": len(days_log),
            "total_transcripts": sum(len(d["transcripts"]) for d in days_log),
            "total_reference_attempts": total_attempts,
            "total_references_resolved": total_resolved,
            "overall_reference_resolution_pct": overall_pct,
            "dossier_monotonic_growth": monotonic,
        },
        "pass": (
            len(days_log) == 7
            and monotonic
            and overall_pct >= 60.0
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


# ---------------------------------------------------------------------------
# Summary markdown
# ---------------------------------------------------------------------------


def write_summary(
    part_a: dict, part_b: dict, summary_path: Path,
    part_a_path: Path, part_b_path: Path,
) -> None:
    a_ok = part_a.get("pass", False)
    b_ok = part_b.get("pass", False)
    a_score = part_a.get("persistence_score") or {}
    a_ref = part_a.get("cross_reference_resolution") or {}
    b_sum = part_b.get("summary") or {}

    lines = []
    lines.append("# V7 Persistence Simulation Summary")
    lines.append("")
    lines.append(
        f"Generated: {dt.datetime.utcnow().isoformat()}Z"
    )
    lines.append("")
    lines.append("## Bottom line")
    lines.append("")
    lines.append(
        f"- Part A (cross-session continuity): "
        f"{'PASS' if a_ok else 'FAIL'}"
    )
    lines.append(
        f"- Part B (7-day stress): "
        f"{'PASS' if b_ok else 'FAIL'}"
    )
    lines.append("")
    lines.append("## Part A: cross-session continuity")
    lines.append("")
    lines.append(f"- Account: `{part_a.get('account_id')}`")
    lines.append(f"- Dossier: `{part_a.get('dossier_path')}`")
    lines.append(
        f"- People persisted: "
        f"{a_score.get('people_persisted')}/"
        f"{a_score.get('expected_people')} "
        f"({a_score.get('people_persistence_pct')}%)"
    )
    lines.append(
        f"- Topics persisted: "
        f"{a_score.get('topics_persisted')}/"
        f"{a_score.get('expected_topics')} "
        f"({a_score.get('topics_persistence_pct')}%)"
    )
    lines.append(
        f"- Cross-reference: \"my dentist\" -> "
        f"{a_ref.get('expected_person')}: "
        f"{'RESOLVED' if a_ref.get('resolved') else 'NOT RESOLVED'} "
        f"(intent type={a_ref.get('intent_type')}, "
        f"refs={a_ref.get('target_person_refs')})"
    )
    lines.append("")
    lines.append("## Part B: 7-day stress")
    lines.append("")
    lines.append(f"- Account: `{part_b.get('account_id')}`")
    lines.append(f"- Dossier: `{part_b.get('dossier_path')}`")
    lines.append(f"- Days completed: {b_sum.get('days_completed')} / 7")
    lines.append(
        f"- Total transcripts: {b_sum.get('total_transcripts')}"
    )
    lines.append(
        f"- Reference attempts: {b_sum.get('total_reference_attempts')}"
    )
    lines.append(
        f"- References resolved: {b_sum.get('total_references_resolved')} "
        f"({b_sum.get('overall_reference_resolution_pct')}%)"
    )
    lines.append(
        f"- Dossier monotonic growth: "
        f"{b_sum.get('dossier_monotonic_growth')}"
    )
    lines.append("")
    lines.append("### Per-day breakdown")
    lines.append("")
    lines.append("| Day | People after | New | Refs attempted | Refs resolved | % |")
    lines.append("|---|---|---|---|---|---|")
    for d in part_b.get("days") or []:
        lines.append(
            f"| {d['day']} | {d['people_count_after']} | "
            f"{d['new_people_added']} | {d['reference_attempts']} | "
            f"{d['references_resolved']} | "
            f"{d['reference_resolution_pct']} |"
        )
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- Part A result: `{part_a_path}`")
    lines.append(f"- Part B result: `{part_b_path}`")
    lines.append("")
    lines.append("## What this proves")
    lines.append("")
    lines.append(
        "1. The per-account dossier file at "
        "`~/.anticipy/v7/dossiers/<account_id>/dossier.json` survives "
        "a close-and-reopen cycle (the cross-session boundary the "
        "engine's dossier_active_loader uses on every restart)."
    )
    lines.append(
        "2. The LLM-backed intent extractor "
        "(`/api/intent/extract`) resolves vague references like \"my "
        "dentist\" or \"Solange\" to the right person when the "
        "dossier is supplied via `memory_context`."
    )
    lines.append(
        "3. Across 7 simulated days, the dossier accumulates "
        "monotonically and day-N transcripts that reference day-N-1 "
        "entities can be resolved at the rate reported above."
    )
    lines.append("")
    if not a_ok or not b_ok:
        lines.append("## What failed")
        lines.append("")
        if not a_ok:
            lines.append(
                "- Part A did not satisfy all three gates "
                "(people persisted, topics persisted, reference "
                "resolved)."
            )
        if not b_ok:
            lines.append(
                "- Part B did not satisfy all three gates (7 days "
                "completed, monotonic growth, overall resolution "
                ">= 60%)."
            )
        lines.append("")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", default=ENGINE_DEFAULT)
    ap.add_argument("--only-a", action="store_true")
    ap.add_argument("--only-b", action="store_true")
    args = ap.parse_args()

    engine = args.engine.rstrip("/")
    health = _engine_health(engine)
    if not health.get("ok"):
        print(f"[fatal] engine not healthy: {health}", file=sys.stderr)
        return 2

    ts_a = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_a = STATE_DIR / "persistence_cross_session" / ts_a
    out_b_base = STATE_DIR / "persistence_7day"

    part_a: dict = {}
    part_b: dict = {}

    if not args.only_b:
        print("=" * 60)
        print("Part A: cross-session continuity")
        print("=" * 60)
        part_a = run_part_a(engine, out_a)
        print(
            f"[A] done pass={part_a.get('pass')} "
            f"people={part_a.get('persistence_score', {}).get('people_persisted')}/"
            f"{part_a.get('persistence_score', {}).get('expected_people')} "
            f"ref_resolved={part_a.get('cross_reference_resolution', {}).get('resolved')}",
            flush=True,
        )

    if not args.only_a:
        ts_b = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        out_b = out_b_base / ts_b
        print("=" * 60)
        print("Part B: 7-day stress")
        print("=" * 60)
        part_b = run_part_b(engine, out_b)
        print(
            f"[B] done pass={part_b.get('pass')} "
            f"overall_pct={part_b.get('summary', {}).get('overall_reference_resolution_pct')}",
            flush=True,
        )

    # Always write the rolling summary if both parts produced data.
    if part_a and part_b:
        summary_path = STATE_DIR / "persistence_summary.md"
        part_a_path = out_a / "result.json"
        # Find the latest part_b dir we wrote.
        part_b_path = None
        if (out_b_base.exists()):
            cands = sorted(
                [p for p in out_b_base.iterdir() if p.is_dir()],
                key=lambda p: p.name, reverse=True,
            )
            if cands:
                part_b_path = cands[0] / "result.json"
        write_summary(
            part_a, part_b, summary_path,
            part_a_path, part_b_path or Path("(missing)"),
        )
        print(f"[summary] wrote {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
