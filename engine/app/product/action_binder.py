"""Action binder: Intent + context -> Binding the dispatcher can execute.

Glue between intent_extractor and ActionDispatcher. Resolves person
refs, fills slots from memory, picks a surface route, asks
risk_assessor about confirm_required, seeds the planner with any
learned recipe.

No-decline contract: if a slot is missing the Binding's
planned_primitives is [{type: "ask_user", ...}] so the dispatcher asks.
Sibling agent modules (intent_extractor, context_attacher,
risk_assessor, person_resolver) are imported lazily and defaulted when
absent so this file loads and runs standalone.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


_BROWSER_DOMAINS: list[tuple[str, str]] = [
    ("gmail", "gmail"), ("mail.google", "gmail"),
    ("calendar.google", "google_calendar"),
    ("docs.google", "google_docs"), ("sheets.google", "google_sheets"),
    ("drive.google", "google_drive"), ("opentable", "opentable"),
    ("doordash", "doordash"), ("ubereats", "uber_eats"),
    ("amazon", "amazon"), ("notion", "notion"), ("linear.app", "linear"),
    ("slack.com", "slack"), ("zoom.us", "zoom"),
]
_NATIVE: list[tuple[str, str]] = [
    ("reminder", "native_macos_reminders"),
    ("notes app", "native_macos_notes"),
    ("imessage", "native_macos_messages"),
    ("apple calendar", "native_macos_calendar"),
]
_VISION = ("figma", "sketch", "photoshop", "illustrator", "after effects",
           "premiere", "canva", "miro")
_EMAIL = ("email", "draft", "send to", "reply to", "respond to",
          "write to", "message ")
_CAL = ("calendar", "schedule", "book", "meeting", "appointment", "remind me")
_PAY = ("pay", "venmo", "send $", "transfer", "wire ", "zelle")
_MSG = ("text ", "imessage", "slack", "dm ")
_REF_KWS = ("email ", "draft to ", "send to ", "reply to ", "write to ",
            "respond to ", "text ", "message ", "dm ", "pay ", "venmo ",
            "remind ")


@dataclass
class Binding:
    """A concrete bind result the dispatcher can execute."""

    binding_id: str
    intent_id: str
    surface_target: str
    prefilled_slots: dict[str, Any] = field(default_factory=dict)
    planned_primitives: list[dict[str, Any]] = field(default_factory=list)
    confirm_required: bool = False
    account_id: str = ""
    device_id: str = ""
    intent_text: str = ""
    risk_reason: str = ""
    missing_slots: list[str] = field(default_factory=list)
    recipe_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(obj: Any, key: str, default: Any = "") -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _text(intent: Any) -> str:
    for k in ("text", "raw_text", "utterance", "instruction", "intent"):
        v = _f(intent, k, "")
        if isinstance(v, str) and v.strip():
            return v.strip()
    return intent.strip() if isinstance(intent, str) else ""


def _required(intent: Any, text: str) -> list[str]:
    declared = _f(intent, "required_slots", None)
    if isinstance(declared, list) and declared:
        return [str(s) for s in declared if s]
    low = (text or "").lower()
    if any(k in low for k in _EMAIL):
        return ["recipient_email"]
    if any(k in low for k in _CAL):
        return ["title"]
    if any(k in low for k in _PAY):
        return ["recipient", "amount"]
    if any(k in low for k in _MSG):
        return ["recipient"]
    return []


def _refs(intent: Any, text: str) -> list[str]:
    declared = _f(intent, "target_person_refs", None)
    if isinstance(declared, list) and declared:
        return [str(p) for p in declared if p]
    out, seen, low = [], set(), text.lower()
    for kw in _REF_KWS:
        i = low.find(kw)
        if i < 0:
            continue
        tail = text[i + len(kw):].lstrip()
        for prefix in ("to ", "with ", "for "):
            if tail.lower().startswith(prefix):
                tail = tail[len(prefix):]; break
        m = (re.match(r"\$?\d+(?:\.\d+)?\s+(?:to\s+)?([A-Z][A-Za-z'.\-]+)",
                      tail) or re.match(r"([A-Z][A-Za-z'.\-]+)", tail))
        if m and m.group(1).lower() not in seen:
            seen.add(m.group(1).lower()); out.append(m.group(1))
    return out


def _pr_lookup(name: str, acct: str, dev: str) -> Optional[dict]:
    try:
        from app.product import person_resolver as _pr  # type: ignore
        fn = getattr(_pr, "resolve", None) or getattr(_pr, "lookup", None)
        if fn is None:
            return None
        try:
            out = fn(name, account_id=acct, device_id=dev)
        except TypeError:
            out = fn(name)
        return out if isinstance(out, dict) else None
    except Exception:
        return None


def _resolve(refs: list[str], context: Any, acct: str,
              dev: str) -> dict[str, dict]:
    resolved = _f(context, "resolved_people", None) or {}
    if not isinstance(resolved, dict):
        resolved = {}
    lookup = {str(k).lower(): v for k, v in resolved.items()
              if isinstance(v, dict)}
    out: dict[str, dict] = {}
    for r in refs:
        hit = lookup.get(r.lower()) or _pr_lookup(r, acct, dev)
        if isinstance(hit, dict):
            out[r] = hit
    return out


def _prefill(required: list[str], people: dict[str, dict], intent: Any,
              context: Any) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    declared = _f(intent, "slots", None)
    if isinstance(declared, dict):
        slots.update({k: v for k, v in declared.items() if v not in (None, "")})
    primary = next(iter(people.values()), None) if people else None
    if primary:
        if ("recipient_email" in required and "recipient_email" not in slots
                and primary.get("email")):
            slots["recipient_email"] = primary["email"]
        if "recipient" in required and "recipient" not in slots:
            slots["recipient"] = (primary.get("display_name") or
                                  primary.get("name") or next(iter(people)))
        if ("phone" in required and "phone" not in slots
                and primary.get("phone")):
            slots["phone"] = primary["phone"]
    for k in ("subject", "body", "title", "start_time"):
        if k in required and k not in slots:
            v = _f(intent, k, "")
            if v: slots[k] = v
    if "amount" in required and "amount" not in slots:
        m = re.search(r"\$?\s*(\d+(?:\.\d{1,2})?)", _text(intent))
        if m: slots["amount"] = float(m.group(1))
    ctx_slots = _f(context, "slots", None)
    if isinstance(ctx_slots, dict):
        for k, v in ctx_slots.items(): slots.setdefault(k, v)
    return slots


def _pick(intent: Any, text: str, context: Any) -> str:
    declared = _f(intent, "surface_target", "")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    low = text.lower()
    for kw, target in _BROWSER_DOMAINS + _NATIVE:
        if kw in low: return target
    if any(k in low for k in _VISION): return "vision_mode"
    if any(k in low for k in _EMAIL): return "gmail"
    if any(k in low for k in _CAL): return "google_calendar"
    if any(k in low for k in _PAY): return "venmo"
    if any(k in low for k in _MSG): return "native_macos_messages"
    surf = _f(context, "active_surface", None)
    if isinstance(surf, dict):
        url = (surf.get("url") or "").lower()
        for kw, target in _BROWSER_DOMAINS:
            if kw in url: return target
    return "browser"


def _risk(intent: Any, text: str, ra: Any,
           surface_target: str) -> tuple[bool, str]:
    if isinstance(ra, dict):
        if "confirm_required" in ra:
            return bool(ra["confirm_required"]), str(ra.get("reason") or "")
        lvl = str(ra.get("level") or "").lower()
        if lvl in ("high", "critical", "money", "irreversible"):
            return True, lvl
    elif ra is not None:
        cr = getattr(ra, "confirm_required", None)
        if cr is not None:
            return bool(cr), str(getattr(ra, "reason", ""))
    try:
        from app.product import risk_assessor as _ra  # type: ignore
        fn = getattr(_ra, "assess", None) or getattr(_ra, "evaluate", None)
        if fn is not None:
            out = fn(intent, surface_target=surface_target)
            if isinstance(out, dict) and "confirm_required" in out:
                return (bool(out["confirm_required"]),
                        str(out.get("reason") or ""))
    except Exception:
        pass
    low = text.lower()
    if any(k in low for k in _PAY): return True, "money_transfer"
    if "delete" in low or "remove " in low or "cancel " in low:
        return True, "destructive_action"
    if ("send " in low and "draft" not in low
            and any(k in low for k in _EMAIL + _MSG)):
        return True, "outbound_send"
    if surface_target in {"venmo", "zelle", "amazon"}:
        return True, "transactional_surface"
    return False, ""


def _seed(context: Any, text: str, surface: str) -> tuple[list[dict], str]:
    learned = _f(context, "learned_recipes", None) or []
    if not isinstance(learned, list) or not learned:
        return [], ""
    best, bs, li, ls = None, -1.0, text.lower(), surface.lower()
    for r in learned:
        if not isinstance(r, dict): continue
        rs = str(r.get("surface_key") or r.get("surface_target") or "").lower()
        ri = str(r.get("intent_summary") or r.get("intent") or "").lower()
        score = 1.0 if (rs and rs == ls) else (
            0.5 if (rs and rs in ls) else 0.0)
        ta = {w for w in re.findall(r"[a-z]+", ri) if len(w) > 2}
        tb = {w for w in re.findall(r"[a-z]+", li) if len(w) > 2}
        if ta and tb:
            score += len(ta & tb) / max(len(ta | tb), 1)
        if score > bs: bs, best = score, r
    if best is None or bs < 0.4: return [], ""
    prims = best.get("primitives") or []
    if not isinstance(prims, list): return [], ""
    return ([dict(p) for p in prims if isinstance(p, dict)],
            str(best.get("recipe_id") or ""))


def _ask(missing: list[str], text: str) -> dict:
    slot = missing[0] if missing else "details"
    pretty = slot.replace("_", " ")
    q = f"What's the {pretty}?"
    if len(missing) > 1:
        rest = ", ".join(m.replace("_", " ") for m in missing[1:])
        q = f"What's the {pretty}? I also need: {rest}."
    return {"type": "ask_user", "primitive": "ask_user", "question": q,
            "missing_slots": list(missing), "intent_text": text}


def bind(intent: Any, context: Any = None, risk_assessment: Any = None,
          *, account_id: str = "", device_id: str = "") -> Binding:
    """Produce a Binding for an intent. Never declines."""
    text = _text(intent)
    intent_id = str(_f(intent, "intent_id", "") or _f(intent, "id", "")
                      or f"intent-{uuid.uuid4().hex[:8]}")
    acct = account_id or str(_f(intent, "account_id", "") or
                              _f(context, "account_id", "") or "")
    dev = device_id or str(_f(intent, "device_id", "") or
                            _f(context, "device_id", "") or "")
    required = _required(intent, text)
    people = _resolve(_refs(intent, text), context, acct, dev)
    slots = _prefill(required, people, intent, context)
    surface_target = _pick(intent, text, context)
    confirm_required, reason = _risk(intent, text, risk_assessment,
                                       surface_target)
    missing = [s for s in required if s not in slots or slots[s] in ("", None)]
    recipe_prims, recipe_id = _seed(context, text, surface_target)
    planned = ([_ask(missing, text)] if missing
               else (recipe_prims if recipe_prims else []))
    return Binding(
        binding_id=f"bind-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}",
        intent_id=intent_id, surface_target=surface_target,
        prefilled_slots=slots, planned_primitives=planned,
        confirm_required=bool(confirm_required), account_id=acct,
        device_id=dev, intent_text=text, risk_reason=reason,
        missing_slots=missing, recipe_id=recipe_id)


def execute_binding(binding: Binding) -> dict[str, Any]:
    """Run the binding via ActionDispatcher.execute. Never declines."""
    if binding.planned_primitives and \
            binding.planned_primitives[0].get("primitive") == "ask_user":
        ask = binding.planned_primitives[0]
        return {"status": "ask_user", "intent": binding.intent_text,
                "question": ask.get("question", ""),
                "missing_slots": list(binding.missing_slots),
                "binding_id": binding.binding_id,
                "result": {"prefilled_slots": dict(binding.prefilled_slots)}}
    try:
        from app.product.action_dispatcher import (  # type: ignore
            ActionDispatcher,
        )
    except Exception as exc:
        return {"status": "notify_user", "intent": binding.intent_text,
                "result": {"error": "action_dispatcher_not_available",
                            "detail": str(exc)},
                "binding_id": binding.binding_id}
    try:
        outcome = ActionDispatcher().execute(
            binding.intent_text or binding.intent_id,
            account_id=binding.account_id, device_id=binding.device_id,
            memory_context={"binding_id": binding.binding_id,
                "surface_target": binding.surface_target,
                "prefilled_slots": dict(binding.prefilled_slots),
                "planned_primitives": list(binding.planned_primitives),
                "confirm_required": bool(binding.confirm_required),
                "recipe_id": binding.recipe_id})
    except Exception as exc:
        return {"status": "notify_user", "intent": binding.intent_text,
                "result": {"error": "dispatcher_execute_failed",
                            "detail": str(exc)},
                "binding_id": binding.binding_id}
    payload = (outcome.to_dict() if hasattr(outcome, "to_dict") else
               (dict(outcome) if isinstance(outcome, dict) else
                {"status": "notify_user",
                 "result": {"value": str(outcome)}}))
    if str(payload.get("status") or "").lower() == "declined":
        payload["status"] = "notify_user"
    payload.setdefault("binding_id", binding.binding_id)
    payload.setdefault("surface_target", binding.surface_target)
    return payload


__all__ = ["Binding", "bind", "execute_binding"]
