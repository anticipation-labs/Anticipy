"""Instant cold start orchestrator.

Implements the day-zero inhale described in
``planning/10-instant-cold-start/DESIGN.md``. Triggered by the
onboarding flow (via ``/api/coldstart/start``), the orchestrator
walks the user's already-logged-in Gmail (inbox + sent) and Google
Calendar in NEW background tabs through the existing CDP bridge,
batches the raw row text to DeepSeek V4 Flash with a stable system
prompt (prompt caching warms on the second batch), parses the
returned JSON into people / projects / tools, and merges each
delta atomically into the active dossier.

What this module does NOT do:

  - It does not redefine the dossier schema. It uses the SAME
    ``DossierLoader`` shape already loaded by the planner, adds
    new entries to the existing ``people`` / ``projects`` /
    ``tools_used`` lists, and never drops anything that was already
    there.
  - It does not hardcode any per-app recipe. The walker JS is a
    generic "find rows, take their text" extraction; the LLM
    figures out what kind of row it is.
  - It does not send raw email bodies or calendar descriptions to
    the LLM. Only the visible row metadata Gmail already shows in
    the inbox list.

The orchestrator runs in a background thread launched from the
endpoint handler. Status is observable through the module-level
``run_state()`` accessor (the ``/api/coldstart/status`` route reads
this).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import sources as inhale_sources
from .cdp_walker import CDPWalker, WalkerRow


_logger = logging.getLogger("anticipy.coldstart.auto_inhale")


# ---------------------------------------------------------------------------
# Prompt + LLM contract
# ---------------------------------------------------------------------------
# This system prompt is the cache anchor. It is sent verbatim on every
# batch so the broker can serve it as a warm cache hit after the first
# call (per platform_adapter.model_call: it auto-attaches
# cache_control:ephemeral when the system block crosses 1000 chars).
# Keep this above the floor so caching engages.
SYSTEM_PROMPT = (
    "You are Anticipy's cold-start extractor. The user just installed a "
    "new AI pendant and the engine is silently inhaling their open "
    "Chrome surfaces (Gmail inbox / sent / Google Calendar agenda) so "
    "the pendant can be useful from minute one. Your job is to read a "
    "batch of visible row metadata and pull out three kinds of entities: "
    "people the user interacts with, projects they are working on, and "
    "tools / SaaS apps they use.\n\n"
    "INPUT shape. The user message is a JSON object with two fields: "
    "``source`` (which surface the rows came from, e.g. ``gmail.inbox`` "
    "or ``google.calendar``) and ``rows`` (an array of short text rows). "
    "Each row is at most one Gmail inbox line or one Calendar event "
    "label, no raw bodies, no signatures, no full email content.\n\n"
    "OUTPUT shape. Return ONE JSON object exactly matching this shape, "
    "no prose, no markdown fences:\n"
    "{\n"
    "  \"people\": [\n"
    "    {\"name\": str, \"email\": str, \"role_inferred\": str, "
    "\"frequency\": int}\n"
    "  ],\n"
    "  \"projects\": [\n"
    "    {\"name\": str, \"why\": str, \"related_people\": [str], "
    "\"evidence_count\": int}\n"
    "  ],\n"
    "  \"tools\": [\n"
    "    {\"name\": str, \"why\": str, \"evidence_count\": int}\n"
    "  ]\n"
    "}\n\n"
    "RULES.\n"
    "1. People: only humans, never mailing-list addresses, never "
    "no-reply addresses. If a sender looks like ``newsletter@x.com`` "
    "or ``notifications@y.com``, do NOT include them as a person. "
    "Distinguish first vs full names: ``Sarah`` is OK but prefer "
    "``Sarah Chen`` when the row shows both. Email field must be "
    "lowercase and only included if it actually appears in the row.\n"
    "2. role_inferred: a SHORT phrase based on the rows (e.g. "
    "``recurring meeting attendee``, ``coworker at Acme``, "
    "``family``). Empty string if you cannot tell. Never guess a "
    "title that is not supported by the rows.\n"
    "3. frequency: count of distinct rows in THIS batch that "
    "mention the person.\n"
    "4. Projects: only multi-word phrases that look like real "
    "project names (subject prefixes like ``[Q3 roadmap]``, "
    "recurring meeting titles like ``Q3 roadmap sync``, document "
    "titles repeated across rows). Skip generic words "
    "(``meeting``, ``call``, ``update``). evidence_count = number of "
    "rows in this batch that reference the project.\n"
    "5. Tools: SaaS / app names you see surfaced (e.g. ``Linear``, "
    "``Figma``, ``Notion``, ``Salesforce``, ``Slack``). Only when "
    "the rows actually mention them. Skip Google's own products "
    "unless the row references a specific URL.\n"
    "6. Never invent entries that are not justified by the input "
    "rows. An empty people / projects / tools array is a CORRECT "
    "answer when the batch has nothing extractable.\n"
    "7. DO NOT use em dashes anywhere in your output.\n"
    "8. Output MUST be valid JSON parseable with json.loads.\n"
)


# ---------------------------------------------------------------------------
# State (module level so the status endpoint can read it without ceremony)
# ---------------------------------------------------------------------------
@dataclass
class InhaleState:
    state: str = "idle"   # idle | running | done | failed
    started_at: float = 0.0
    finished_at: float = 0.0
    elapsed_ms: int = 0
    people_count: int = 0
    projects_count: int = 0
    tools_count: int = 0
    rows_collected: int = 0
    batches_sent: int = 0
    llm_calls_ok: int = 0
    llm_calls_failed: int = 0
    errors: list[str] = field(default_factory=list)
    last_error: str = ""
    bridge_ready: bool = False
    account_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_ms": self.elapsed_ms,
            "people_count": self.people_count,
            "projects_count": self.projects_count,
            "tools_count": self.tools_count,
            "rows_collected": self.rows_collected,
            "batches_sent": self.batches_sent,
            "llm_calls_ok": self.llm_calls_ok,
            "llm_calls_failed": self.llm_calls_failed,
            "errors": list(self.errors[-10:]),
            "last_error": self.last_error,
            "bridge_ready": self.bridge_ready,
            "account_id": self.account_id,
        }


_STATE = InhaleState()
_STATE_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None


def run_state() -> dict[str, Any]:
    """Snapshot the current orchestrator state for the status endpoint."""
    with _STATE_LOCK:
        s = _STATE.to_dict()
        # Compute elapsed_ms live while running.
        if _STATE.state == "running" and _STATE.started_at:
            s["elapsed_ms"] = int(
                max(0.0, (time.time() - _STATE.started_at) * 1000.0))
        return s


def _set_state(**kwargs: Any) -> None:
    with _STATE_LOCK:
        for k, v in kwargs.items():
            if hasattr(_STATE, k):
                setattr(_STATE, k, v)


def _bump_state(**kwargs: int) -> None:
    with _STATE_LOCK:
        for k, v in kwargs.items():
            if hasattr(_STATE, k):
                cur = getattr(_STATE, k) or 0
                setattr(_STATE, k, int(cur) + int(v))


def _record_error(msg: str) -> None:
    with _STATE_LOCK:
        _STATE.errors.append(str(msg)[:240])
        _STATE.last_error = str(msg)[:240]


# ---------------------------------------------------------------------------
# Dossier merge primitive
# ---------------------------------------------------------------------------
def _dossier_path(account_id: str) -> Path:
    """Resolve the canonical dossier file for the account.

    Mirrors ``dossier_active_loader._candidate_paths`` priority order:
    per-account dir first, then global fallbacks. We write to the
    per-account file (creating its directory) so the loader picks up
    the freshest version.
    """
    raw = os.environ.get("ANTICIPY_V7_DOSSIER_ROOT", "").strip()
    if raw:
        root = Path(raw).expanduser()
    else:
        root = Path.home() / ".anticipy" / "v7" / "dossiers"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (account_id or "default")).strip()
    if not safe:
        safe = "default"
    return root / safe[:128] / "dossier.json"


def _normalize_email(raw: str) -> str:
    cleaned = (raw or "").strip().lower()
    m = re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", cleaned)
    return m.group(0) if m else ""


def _person_key(entry: dict) -> str:
    """Stable key used to dedupe people across batches and prior dossier."""
    email = _normalize_email(str(entry.get("email") or ""))
    if email:
        return f"email:{email}"
    name = re.sub(r"\s+", " ", str(entry.get("name") or "")).strip().lower()
    return f"name:{name}" if name else ""


def _project_key(entry: dict) -> str:
    name = re.sub(r"[^a-z0-9]+", " ",
                  str(entry.get("name") or "").lower()).strip()
    return f"project:{name}" if name else ""


def _tool_key(entry: dict) -> str:
    name = re.sub(r"\s+", " ",
                  str(entry.get("name") or "").lower()).strip()
    return f"tool:{name}" if name else ""


def _load_dossier(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def _write_dossier_atomic(path: Path, data: dict[str, Any]) -> None:
    """Atomic write via temp file + os.replace (POSIX guaranteed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=False),
                   encoding="utf-8")
    os.replace(tmp, path)


# Held across merge_delta calls so concurrent batches do not interleave
# read/modify/write. Same shape as dossier_active_loader._LOCK but local
# to the inhale; we do not import the other lock because we operate
# directly on disk and never hold the loader's in-memory cache.
_DISK_LOCK = threading.Lock()


def merge_delta(account_id: str, delta: dict[str, Any]) -> dict[str, int]:
    """Merge one LLM delta into the on-disk dossier.

    Returns ``{people_added, projects_added, tools_added}``. Field-by-field
    merge: existing people whose email or name match an incoming entry
    are updated in place (we bump ``frequency`` and fill empty fields),
    fully new entries are appended. The dossier's existing keys never
    get dropped.
    """
    path = _dossier_path(account_id)
    with _DISK_LOCK:
        doc = _load_dossier(path)
        if not isinstance(doc, dict):
            doc = {}
        # Per-account_id contract.
        if not doc.get("account_id"):
            doc["account_id"] = account_id
        # Track provenance from the inhale so we can re-walk later.
        prov = doc.setdefault("inhale_provenance", {})
        prov["last_inhale_at"] = time.time()
        prov.setdefault("source", "coldstart.auto_inhale")

        # People
        people = doc.get("people")
        if not isinstance(people, list):
            # Convert dict-shaped people (the legacy
            # {"role": "name"} format) into the list form. We do NOT
            # discard the old role labels; we copy them into ``role``.
            normalized: list[dict] = []
            if isinstance(people, dict):
                for role, name in people.items():
                    if not name:
                        continue
                    normalized.append({"name": str(name),
                                       "role": str(role)})
            people = normalized
        existing_keys: dict[str, int] = {}
        for idx, p in enumerate(people):
            key = _person_key(p) if isinstance(p, dict) else ""
            if key:
                existing_keys[key] = idx
        added_people = 0
        for entry in (delta.get("people") or []):
            if not isinstance(entry, dict):
                continue
            name = re.sub(r"\s+", " ",
                          str(entry.get("name") or "")).strip()
            if not name:
                continue
            email = _normalize_email(str(entry.get("email") or ""))
            role = str(entry.get("role_inferred")
                       or entry.get("role") or "")
            try:
                freq = int(entry.get("frequency") or 1)
            except Exception:
                freq = 1
            new_entry = {
                "name": name,
                "email": email,
                "role": role,
                "frequency": max(1, freq),
                "provenance": "inhaled_from_chrome_tab_inventory",
                "last_seen": time.time(),
            }
            key = _person_key(new_entry)
            if not key:
                continue
            if key in existing_keys:
                idx = existing_keys[key]
                target = people[idx] if isinstance(
                    people[idx], dict) else {}
                # In-place bump: never overwrite a non-empty name with
                # a partial name, never demote a role.
                if not target.get("email"):
                    target["email"] = email
                if not target.get("role"):
                    target["role"] = role
                try:
                    target["frequency"] = int(
                        target.get("frequency") or 0) + max(1, freq)
                except Exception:
                    target["frequency"] = max(1, freq)
                target["last_seen"] = time.time()
                people[idx] = target
            else:
                people.append(new_entry)
                existing_keys[key] = len(people) - 1
                added_people += 1
        doc["people"] = people

        # Projects
        projects = doc.get("projects")
        if not isinstance(projects, list):
            projects = []
        existing_proj: dict[str, int] = {}
        for idx, p in enumerate(projects):
            key = _project_key(p) if isinstance(p, dict) else ""
            if key:
                existing_proj[key] = idx
        added_projects = 0
        for entry in (delta.get("projects") or []):
            if not isinstance(entry, dict):
                continue
            name = re.sub(r"\s+", " ",
                          str(entry.get("name") or "")).strip()
            if not name or len(name) < 2:
                continue
            try:
                ec = int(entry.get("evidence_count") or 1)
            except Exception:
                ec = 1
            related = [str(x) for x in
                       (entry.get("related_people") or [])
                       if isinstance(x, str) and x.strip()]
            new_entry = {
                "name": name,
                "why": str(entry.get("why") or ""),
                "related_people": related[:10],
                "evidence_count": max(1, ec),
                "provenance": "inhaled_from_chrome_tab_inventory",
                "last_seen": time.time(),
            }
            key = _project_key(new_entry)
            if not key:
                continue
            if key in existing_proj:
                idx = existing_proj[key]
                target = projects[idx] if isinstance(
                    projects[idx], dict) else {}
                try:
                    target["evidence_count"] = int(
                        target.get("evidence_count") or 0) + max(1, ec)
                except Exception:
                    target["evidence_count"] = max(1, ec)
                # union of related people, capped.
                merged_related = list(dict.fromkeys(
                    list(target.get("related_people") or [])
                    + related))[:20]
                target["related_people"] = merged_related
                if not target.get("why"):
                    target["why"] = new_entry["why"]
                target["last_seen"] = time.time()
                projects[idx] = target
            else:
                projects.append(new_entry)
                existing_proj[key] = len(projects) - 1
                added_projects += 1
        doc["projects"] = projects

        # Tools
        tools = doc.get("tools_used")
        if not isinstance(tools, list):
            tools = []
        existing_tools: dict[str, int] = {}
        for idx, t in enumerate(tools):
            key = _tool_key(t) if isinstance(t, dict) else ""
            if key:
                existing_tools[key] = idx
        added_tools = 0
        for entry in (delta.get("tools") or []):
            if not isinstance(entry, dict):
                continue
            name = re.sub(r"\s+", " ",
                          str(entry.get("name") or "")).strip()
            if not name:
                continue
            try:
                ec = int(entry.get("evidence_count") or 1)
            except Exception:
                ec = 1
            new_entry = {
                "name": name,
                "why": str(entry.get("why") or ""),
                "evidence_count": max(1, ec),
                "provenance": "inhaled_from_chrome_tab_inventory",
                "last_seen": time.time(),
            }
            key = _tool_key(new_entry)
            if not key:
                continue
            if key in existing_tools:
                idx = existing_tools[key]
                target = tools[idx] if isinstance(
                    tools[idx], dict) else {}
                try:
                    target["evidence_count"] = int(
                        target.get("evidence_count") or 0) + max(1, ec)
                except Exception:
                    target["evidence_count"] = max(1, ec)
                if not target.get("why"):
                    target["why"] = new_entry["why"]
                target["last_seen"] = time.time()
                tools[idx] = target
            else:
                tools.append(new_entry)
                existing_tools[key] = len(tools) - 1
                added_tools += 1
        doc["tools_used"] = tools

        # Schema bump (additive; existing readers ignore unknown keys).
        doc.setdefault("schema", "anticipy.v7.dossier.rich.v1")
        existing_versions = doc.get("schema_extensions") or []
        if isinstance(existing_versions, list):
            if "coldstart.inhale.v1" not in existing_versions:
                existing_versions.append("coldstart.inhale.v1")
            doc["schema_extensions"] = existing_versions

        _write_dossier_atomic(path, doc)
        return {
            "people_added": added_people,
            "projects_added": added_projects,
            "tools_added": added_tools,
        }


# ---------------------------------------------------------------------------
# LLM call wrapper
# ---------------------------------------------------------------------------
def _llm_extract(rows: list[WalkerRow]) -> dict[str, Any]:
    """Send one batch to DeepSeek V4 Flash via the platform adapter.

    Returns the parsed JSON dict (empty arrays on failure) so the
    orchestrator never crashes on a single bad batch.
    """
    if not rows:
        return {"people": [], "projects": [], "tools": []}
    # Build a small per-batch user payload. Cap to keep prompt cheap.
    source = rows[0].source or ""
    row_texts = []
    for r in rows[:60]:
        line = (r.text or "").strip()
        if not line:
            continue
        if r.extra.get("sender") or r.extra.get("subject"):
            line = (
                f"from: {r.extra.get('sender','')[:120]} | "
                f"subj: {r.extra.get('subject','')[:160]} | "
                f"date: {r.extra.get('date','')[:60]} | "
                f"snippet: {line[:240]}"
            )
        elif r.extra.get("title"):
            line = (
                f"title: {r.extra.get('title','')[:200]} | "
                f"when: {r.extra.get('when','')[:60]} | "
                f"raw: {line[:200]}"
            )
        row_texts.append(line[:360])
    user_payload = json.dumps(
        {"source": source, "rows": row_texts}, ensure_ascii=False)
    try:
        from app.anticipy import platform_adapter
    except Exception as exc:
        _record_error(f"platform_adapter import: {exc}")
        return {"people": [], "projects": [], "tools": []}
    try:
        result = platform_adapter.model_call(
            SYSTEM_PROMPT,
            user_payload,
            max_tokens=900,
            temperature=0.0,
            json_mode=True,
            timeout_s=30.0,
        )
    except Exception as exc:
        _record_error(f"model_call: {exc}")
        _bump_state(llm_calls_failed=1)
        return {"people": [], "projects": [], "tools": []}
    if not result.ok or not result.content:
        _bump_state(llm_calls_failed=1)
        _record_error(f"llm empty: {result.error or 'no content'}")
        return {"people": [], "projects": [], "tools": []}
    _bump_state(llm_calls_ok=1)
    try:
        parsed = json.loads(result.content)
    except Exception as exc:
        _record_error(f"json parse: {exc}")
        return {"people": [], "projects": [], "tools": []}
    if not isinstance(parsed, dict):
        _record_error(f"non-dict llm output: {str(parsed)[:120]}")
        return {"people": [], "projects": [], "tools": []}
    parsed.setdefault("people", [])
    parsed.setdefault("projects", [])
    parsed.setdefault("tools", [])
    return parsed


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
DEFAULT_ACCOUNT_ID = "anticipy-user"


def _batch_rows(rows: list[WalkerRow],
                batch_size: int = 30) -> list[list[WalkerRow]]:
    """Group rows into LLM-sized batches."""
    out: list[list[WalkerRow]] = []
    if not rows:
        return out
    for i in range(0, len(rows), max(1, batch_size)):
        out.append(rows[i: i + batch_size])
    return out


def _process_batches(rows: list[WalkerRow],
                     account_id: str,
                     batch_size: int) -> dict[str, int]:
    """Send each batch to the LLM and merge the result into the dossier.

    Returns aggregate counters across all batches.
    """
    agg = {"people_added": 0, "projects_added": 0, "tools_added": 0}
    for batch in _batch_rows(rows, batch_size=batch_size):
        _bump_state(batches_sent=1)
        delta = _llm_extract(batch)
        try:
            added = merge_delta(account_id, delta)
        except Exception as exc:
            _record_error(f"merge_delta: {exc}")
            continue
        for k in agg:
            agg[k] += int(added.get(k, 0))
        _bump_state(people_count=int(added.get("people_added", 0)),
                    projects_count=int(added.get("projects_added", 0)),
                    tools_count=int(added.get("tools_added", 0)))
    return agg


def _run_inhale(account_id: str,
                walk_gmail: bool = True,
                walk_calendar: bool = True,
                walk_drive: bool = False,
                batch_size: int = 30) -> None:
    """Synchronous orchestrator body. Called inside a thread."""
    walker = CDPWalker()
    rows: list[WalkerRow] = []
    started = time.time()
    try:
        ready = walker.bridge_ready()
        _set_state(bridge_ready=ready)
        if not ready:
            _record_error(
                "loopback bridge or Chrome CDP not available; cannot inhale")
            _set_state(state="failed",
                       finished_at=time.time(),
                       elapsed_ms=int((time.time() - started) * 1000))
            return

        # Iterate every enabled source from the user config at
        # ~/.anticipy/inhale_sources.json. URL CHOICES live there,
        # NOT in this file (rule 1: no per-app code).
        #
        # Legacy walk_gmail / walk_calendar / walk_drive flags are
        # honored as opt-outs against the lane id (any id matching
        # the family name is skipped when the flag is False). This
        # preserves the existing /api/coldstart/start contract while
        # the URL list becomes user-editable data.
        try:
            enabled_sources = inhale_sources.load_enabled()
        except Exception as exc:
            _record_error(f"sources.load_enabled: {exc}")
            enabled_sources = []

        for source in enabled_sources:
            sid = str(source.get("id") or "").lower()
            family = (
                "calendar" if "calendar" in sid
                else "drive" if ("drive" in sid or "files" in sid)
                else "gmail"
            )
            if family == "gmail" and not walk_gmail:
                continue
            if family == "calendar" and not walk_calendar:
                continue
            if family == "drive" and not walk_drive:
                continue
            try:
                collected = walker.walk_source(
                    source=source,
                    per_tab_budget_s=18.0 if family == "gmail" else 12.0,
                )
                rows.extend(collected)
                _bump_state(rows_collected=len(collected))
            except Exception as exc:
                _record_error(
                    f"{sid or 'source'} walk: {exc}")

        if not rows:
            _record_error("walker collected no rows; nothing to extract")
            _set_state(state="done",
                       finished_at=time.time(),
                       elapsed_ms=int((time.time() - started) * 1000))
            return

        agg = _process_batches(rows, account_id, batch_size=batch_size)
        _logger.info(
            "coldstart.inhale done account=%s rows=%d added=%s",
            account_id, len(rows), agg)
        _set_state(state="done",
                   finished_at=time.time(),
                   elapsed_ms=int((time.time() - started) * 1000))
    except Exception as exc:
        _record_error(f"unhandled: {type(exc).__name__}: {exc}")
        _set_state(state="failed",
                   finished_at=time.time(),
                   elapsed_ms=int((time.time() - started) * 1000))
    finally:
        try:
            walker.close_all()
        except Exception as exc:
            _record_error(f"close_all: {exc}")


def start_inhale(account_id: str = DEFAULT_ACCOUNT_ID,
                 walk_gmail: bool = True,
                 walk_calendar: bool = True,
                 walk_drive: bool = False,
                 batch_size: int = 30) -> dict[str, Any]:
    """Kick off the orchestrator in a background thread.

    Returns the initial state snapshot. If an inhale is already
    running the snapshot's ``state`` is ``"running"`` and the call
    is a no-op (we do NOT enqueue a second inhale; the user only
    needs one cold start).
    """
    global _THREAD
    # ANTICIPY_QUIET=1 disables every proactive tab-open path. The
    # cold-start inhale opens 2-4 Chrome tabs (Gmail inbox, Gmail
    # sent, Calendar agenda, optionally Drive recents). Skip the
    # thread spawn entirely and return an idle snapshot. Audit:
    # planning/00-handoff/TAB_OPEN_AUDIT.md.
    try:
        from app.config import _quiet_mode_enabled
    except Exception:
        _quiet_mode_enabled = lambda: False  # noqa: E731
    if _quiet_mode_enabled():
        _logger.info("quiet_mode_skipped path=coldstart_auto_inhale")
        print(
            "[anticipy.coldstart] quiet_mode_skipped "
            "path=coldstart_auto_inhale",
            flush=True,
        )
        return run_state() | {"quiet_mode_skipped": True}
    with _STATE_LOCK:
        if _STATE.state == "running":
            return _STATE.to_dict() | {"already_running": True}
        # Reset the counters so the next status read reflects only
        # this run.
        _STATE.state = "running"
        _STATE.started_at = time.time()
        _STATE.finished_at = 0.0
        _STATE.elapsed_ms = 0
        _STATE.people_count = 0
        _STATE.projects_count = 0
        _STATE.tools_count = 0
        _STATE.rows_collected = 0
        _STATE.batches_sent = 0
        _STATE.llm_calls_ok = 0
        _STATE.llm_calls_failed = 0
        _STATE.errors = []
        _STATE.last_error = ""
        _STATE.bridge_ready = False
        _STATE.account_id = account_id

    def _thread_main() -> None:
        _run_inhale(account_id=account_id, walk_gmail=walk_gmail,
                    walk_calendar=walk_calendar, walk_drive=walk_drive,
                    batch_size=batch_size)

    _THREAD = threading.Thread(target=_thread_main,
                               name="anticipy.coldstart.inhale",
                               daemon=True)
    _THREAD.start()
    return run_state()


__all__ = [
    "SYSTEM_PROMPT",
    "InhaleState",
    "merge_delta",
    "run_state",
    "start_inhale",
    "DEFAULT_ACCOUNT_ID",
]
