"""Context attacher for the V7 action planner. Gathers scoped memory,
recent surface, learned recipes, and resolved people into one bundle
for `ActionPlanner.plan_next_primitive`. Each planning step calls
`ContextAttacher(account_id, device_id).attach(...)` then prepends
`as_planner_prompt_block(ctx)` to its prompt. Collaborators imported
lazily; missing ones yield empty defaults instead of crashing."""

from __future__ import annotations

import json
from typing import Any, Optional

# Lazy collaborator imports. Missing classes stay None; that field then
# falls back to its empty/default value instead of crashing the planner.
try: from app.product.scoped_memory import ScopedMemory as _ScopedMemory
except Exception: _ScopedMemory = None  # type: ignore[assignment]
try: from app.product.action_recipes import RecipeStore as _RecipeStore
except Exception: _RecipeStore = None  # type: ignore[assignment]
try: from app.product.dossier_loader import DossierLoader as _DossierLoader  # type: ignore
except Exception: _DossierLoader = None  # type: ignore[assignment]
try: from app.product.person_resolver import PersonResolver as _PersonResolver  # type: ignore
except Exception: _PersonResolver = None  # type: ignore[assignment]

# Memory kinds promoted into the planner's relevant_memories list.
_PLANNER_MEMORY_KINDS = {"preference", "accepted_action", "learned_recipe"}

_EMPTY: dict[str, Any] = {
    "dossier_context": "", "relevant_memories": [],
    "resolved_people": {}, "recent_surface_snapshots": [],
    "learned_recipes": [], "do_not_touch_warnings": [],
    "action_history_summary": ""}


def _safe(fn, default):
    """Call fn(); return default on any exception."""
    try: return fn()
    except Exception: return default


class ContextAttacher:
    """Build a context bundle for one planner step."""

    def __init__(self, account_id: str, device_id: str) -> None:
        self.account_id = str(account_id or "").strip() or "unknown"
        self.device_id = str(device_id or "").strip() or "unknown"
        _mk = lambda cls: (None if cls is None else _safe(
            lambda: cls(self.account_id, self.device_id), None))
        self._memory = _mk(_ScopedMemory)
        self._recipes = _mk(_RecipeStore)
        self._dossier = _mk(_DossierLoader)
        self._people = _mk(_PersonResolver)

    # ----------------------------------------------------------- public API

    def attach(self, intent: Any, current_surface: Any,
               history: Any) -> dict[str, Any]:
        """Return the planner context bundle for one planning step."""
        out: dict[str, Any] = {k: (list(v) if isinstance(v, list)
                                   else dict(v) if isinstance(v, dict) else v)
                               for k, v in _EMPTY.items()}
        summary = self._intent_summary(intent)
        refs = self._person_refs(intent)
        url = (str(current_surface.get("url") or "")
               if isinstance(current_surface, dict) else "")

        if self._dossier is not None:
            out["dossier_context"] = str(
                _safe(self._dossier.as_context_block, "") or "")
        if self._memory is not None:
            out["relevant_memories"] = self._gather_memories(limit=5)
        if refs:
            out["resolved_people"] = self._resolve_people(refs)
        out["recent_surface_snapshots"] = self._recent_surfaces(
            current_surface, history, limit=3)
        if self._recipes is not None and summary:
            out["learned_recipes"] = self._recall_recipes(summary, url, top_k=3)
        if self._memory is not None:
            out["do_not_touch_warnings"] = self._dnt_warnings(
                refs, out["resolved_people"], url)
        out["action_history_summary"] = self._history_summary(history, limit=5)
        return out

    @staticmethod
    def as_planner_prompt_block(context_dict: dict[str, Any],
                                max_chars: int = 3000) -> str:
        """Format the dict as a compact text block. Order: dnt warnings,
        resolved_people, dossier, learned_recipes, recent_surfaces, history."""
        ctx = context_dict or {}
        max_chars = int(max_chars or 0) or 3000
        people = ctx.get("resolved_people") or {}
        recipes = ctx.get("learned_recipes") or []
        snaps = ctx.get("recent_surface_snapshots") or []
        sections: list[tuple[str, str]] = []
        dnt = ctx.get("do_not_touch_warnings") or []
        if dnt:
            sections.append(("DO NOT TOUCH WARNINGS", "\n".join(
                f"  - {str(w)[:200]}" for w in dnt[:12])))
        if isinstance(people, dict) and people:
            sections.append(("RESOLVED PEOPLE", "\n".join(
                f"  - {str(ref)[:80]}: {_summarize_person(info)[:200]}"
                for ref, info in list(people.items())[:12])))
        dossier = str(ctx.get("dossier_context") or "").strip()
        if dossier:
            sections.append(("DOSSIER", dossier[:800]))
        if recipes:
            sections.append(("LEARNED RECIPES", "\n".join(
                f"  - {_summarize_recipe(r)[:240]}" for r in recipes[:5])))
        if snaps:
            sections.append(("RECENT SURFACES", "\n".join(
                f"  - {_summarize_surface(s)[:200]}" for s in snaps[:5])))
        hist = str(ctx.get("action_history_summary") or "").strip()
        if hist:
            sections.append(("ACTION HISTORY", hist[:600]))
        parts: list[str] = []
        running = 0
        for title, body in sections:
            chunk = f"## {title}\n{body}\n"
            if running + len(chunk) > max_chars:
                remaining = max_chars - running
                if remaining > len(title) + 8:
                    parts.append(chunk[:remaining].rstrip() + "\n")
                break
            parts.append(chunk); running += len(chunk)
        return "".join(parts).rstrip()

    # ------------------------------------------------------- internals

    @staticmethod
    def _intent_summary(intent: Any) -> str:
        if isinstance(intent, str): return intent.strip()
        if isinstance(intent, dict):
            for k in ("summary", "intent", "text", "description"):
                v = intent.get(k)
                if isinstance(v, str) and v.strip(): return v.strip()
        return ""

    @staticmethod
    def _person_refs(intent: Any) -> list[str]:
        if not isinstance(intent, dict):
            return []
        refs: list[str] = []
        for k in ("target_person_refs", "target_person_ref",
                  "people", "recipients"):
            v = intent.get(k)
            if isinstance(v, str) and v.strip():
                refs.append(v.strip())
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item.strip():
                        refs.append(item.strip())
                    elif isinstance(item, dict):
                        for kk in ("ref", "name", "id"):
                            vv = item.get(kk)
                            if isinstance(vv, str) and vv.strip():
                                refs.append(vv.strip()); break
        seen: set[str] = set(); out: list[str] = []
        for r in refs:
            if r.lower() not in seen:
                seen.add(r.lower()); out.append(r)
        return out

    def _gather_memories(self, *, limit: int) -> list[str]:
        items: list[dict[str, Any]] = []
        for kind in _PLANNER_MEMORY_KINDS:
            chunk = _safe(lambda k=kind: self._memory.read(
                kind=k, active_only=True), [])
            if chunk:
                items.extend(chunk)
        items.sort(key=lambda x: float(x.get("timestamp") or 0.0), reverse=True)
        out: list[str] = []
        for it in items[:limit]:
            out.append(f"[{it.get('kind') or ''}] "
                       f"{it.get('key') or ''}: {it.get('value') or ''}"[:240])
        return out

    def _resolve_people(self, refs: list[str]) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for ref in refs:
            person: Optional[Any] = None
            if self._people is not None:
                person = _safe(lambda r=ref: self._people.resolve(r), None)
            if person is None and self._memory is not None:
                person = (_safe(lambda r=ref: self._memory.resolve_person(r), None)
                          or _safe(lambda r=ref: self._memory.resolve_alias(r), None))
            if not person:
                continue
            if hasattr(person, "to_dict") and callable(getattr(person, "to_dict")):
                person = _safe(person.to_dict, person) or person
            # Unwrap Resolution {person, confidence, ...} -> inner person dict.
            if isinstance(person, dict) and isinstance(
                    person.get("person"), dict):
                inner = dict(person["person"])
                inner["_confidence"] = person.get("confidence")
                person = inner
            resolved[ref] = person
        return resolved

    @staticmethod
    def _recent_surfaces(current_surface: Any, history: Any,
                         *, limit: int) -> list[dict[str, Any]]:
        snaps: list[dict[str, Any]] = []
        if isinstance(current_surface, dict):
            snaps.append({"url": str(current_surface.get("url") or ""),
                          "title": str(current_surface.get("title") or ""),
                          "when": "current"})
        if isinstance(history, list):
            for h in reversed(history):
                if not isinstance(h, dict): continue
                s = h.get("surface") or h.get("current_surface")
                if not isinstance(s, dict): continue
                snaps.append({"url": str(s.get("url") or ""),
                              "title": str(s.get("title") or ""),
                              "primitive": str(h.get("primitive") or ""),
                              "when": "history"})
                if len(snaps) >= limit: break
        return snaps[:limit]

    def _recall_recipes(self, summary: str, url: str,
                        *, top_k: int) -> list[Any]:
        recipes = _safe(lambda: self._recipes.recall(
            summary, url, top_k=top_k), [])
        if recipes:
            return list(recipes)
        try:
            from urllib.parse import urlsplit
            host = urlsplit(url).hostname or ""
        except Exception:
            host = ""
        if host:
            return list(_safe(lambda: self._recipes.recall(
                summary, host, top_k=top_k), []))
        return []

    def _dnt_warnings(self, refs: list[str],
                      resolved: dict[str, Any], url: str) -> list[str]:
        warnings: list[str] = []
        seen: set[str] = set()
        def _check(label: str, needle: str) -> None:
            key = (needle or "").strip().lower()
            if not key or key in seen: return
            if _safe(lambda: self._memory.is_do_not_touch(needle), False):
                seen.add(key); warnings.append(f"{label}: {needle}")
        if url: _check("surface", url)
        for ref in refs: _check("recipient_ref", ref)
        for _ref, info in (resolved or {}).items():
            if not isinstance(info, dict): continue
            for k in ("email", "value", "key", "name"):
                val = info.get(k)
                if isinstance(val, str) and val:
                    _check(f"recipient.{k}", val)
        return warnings

    @staticmethod
    def _history_summary(history: Any, *, limit: int) -> str:
        if not isinstance(history, list):
            return ""
        rows: list[str] = []
        for h in (history or [])[-limit:]:
            if not isinstance(h, dict): continue
            ok = h.get("ok")
            status = "ok" if ok else ("FAIL" if ok is False else "?")
            rows.append(f"  - {str(h.get('primitive') or '?')} [{status}] "
                        f"{str(h.get('why') or '')[:80]} "
                        f"{str(h.get('error') or '')[:80]}".rstrip())
        return "\n".join(rows)


def _summarize_person(info: Any) -> str:
    if not isinstance(info, dict): return str(info)
    extra = info.get("extra") if isinstance(info.get("extra"), dict) else {}
    bits = [b for b in (
        str(info.get("name") or info.get("key") or ""),
        str(info.get("email") or extra.get("email")
            or info.get("value") or ""),
        str(info.get("role") or extra.get("role") or "")) if b]
    return " | ".join(bits) if bits else json.dumps(info, ensure_ascii=False)


def _summarize_recipe(recipe: Any) -> str:
    if hasattr(recipe, "to_dict") and callable(getattr(recipe, "to_dict")):
        obj = _safe(recipe.to_dict, {}) or {}
    elif isinstance(recipe, dict):
        obj = recipe
    else:
        return str(recipe)
    name = str(obj.get("intent_summary") or obj.get("name") or "")
    surface = str(obj.get("surface_key") or "")
    n = len(obj.get("primitives") or obj.get("steps") or [])
    return f"{name} (surface={surface}, steps={n}, used={obj.get('success_count') or 0})"


def _summarize_surface(snap: Any) -> str:
    if not isinstance(snap, dict):
        return str(snap)
    bits = [str(snap.get(k) or "") for k in ("when", "primitive", "title", "url")]
    return " | ".join(b for b in bits if b)


__all__ = ["ContextAttacher"]
