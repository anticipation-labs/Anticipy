"""Confirm-card / ask_user safety surface (never-decline directive).

For money or irreversible actions the engine surfaces a confirm card
the user approves or denies from /app, then executes or records.
The engine never flat-refuses.
Storage: ~/.anticipy/v7/confirm_cards/<account_id>/cards.jsonl
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional


_LOCK = threading.Lock()
DEFAULT_TTL_SECONDS = 60 * 60 * 24

RISK_LOW, RISK_MEDIUM, RISK_HIGH = "low", "medium", "high"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"
STATUS_EXPIRED = "expired"

RISKY_VERBS = {"purchase", "buy", "pay", "payment", "transfer", "wire",
               "subscribe", "checkout", "charge", "donate", "tip", "send",
               "delete", "remove", "drop", "destroy", "wipe", "cancel",
               "publish", "post", "share", "tweet", "submit", "book",
               "reserve", "order"}
FINANCE_HOST_HINTS = {"bank", "banking", "wellsfargo", "chase", "citi",
                      "bankofamerica", "paypal", "venmo", "cashapp",
                      "stripe", "square", "amazon.com", "shop.",
                      "checkout", "stripe.com", "robinhood", "fidelity",
                      "schwab", "etrade", "vanguard", "coinbase", "binance",
                      "kraken", "anthropic.com/billing",
                      "openrouter.ai/credits"}
_DRAFT_SAFE_BUSTERS = {"send", "publish", "post", "share", "submit",
                       "purchase", "buy", "checkout", "pay", "delete",
                       "cancel", "transfer"}


def _root() -> Path:
    raw = os.environ.get("ANTICIPY_V7_CONFIRM_ROOT", "").strip()
    return (Path(raw).expanduser() if raw
            else Path.home() / ".anticipy" / "v7" / "confirm_cards")


def _safe_id(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "unknown"
    return (re.sub(r"[^A-Za-z0-9._-]+", "_", s) or "unknown")[:128]


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z]+", text or "")}


def _step_text(step: Any) -> str:
    if isinstance(step, str):
        return step
    if isinstance(step, dict):
        try:
            return json.dumps(step, ensure_ascii=False)
        except Exception:
            pass
    return str(step)


def _looks_external_email(step_dict: dict[str, Any]) -> bool:
    text = _step_text(step_dict).lower()
    if "draft" in text and "send" not in text:
        return False
    if "send" not in text and "email" not in text:
        return False
    return bool(re.search(r"@[a-z0-9.-]+\.[a-z]{2,}", text))


def _is_finance_surface(s: str) -> bool:
    s = (s or "").lower()
    return bool(s) and any(h in s for h in FINANCE_HOST_HINTS)


@dataclass
class ConfirmCard:
    """One pending / decided confirm card."""
    card_id: str
    account_id: str
    intent_summary: str
    planned_steps: list[Any]
    risk_level: str
    money_amount: Optional[float]
    surface_target: str
    expires_at: float
    status: str = STATUS_PENDING
    created_at: float = 0.0
    decided_at: Optional[float] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ConfirmCard":
        of = lambda k: (None if d.get(k) in (None, "")
                        else float(d.get(k) or 0))
        return cls(card_id=str(d.get("card_id") or ""),
                   account_id=str(d.get("account_id") or ""),
                   intent_summary=str(d.get("intent_summary") or ""),
                   planned_steps=list(d.get("planned_steps") or []),
                   risk_level=str(d.get("risk_level") or RISK_MEDIUM),
                   money_amount=of("money_amount"),
                   surface_target=str(d.get("surface_target") or ""),
                   expires_at=float(d.get("expires_at") or 0.0),
                   status=str(d.get("status") or STATUS_PENDING),
                   created_at=float(d.get("created_at") or 0.0),
                   decided_at=of("decided_at"),
                   extra=dict(d.get("extra") or {}))


class ConfirmCardStore:
    """Per-account JSONL persistence for confirm cards."""

    _APPROVE = ("yes", "y", "approve", "approved", "true", "ok")
    _DENY = ("no", "n", "deny", "denied", "false", "cancel")

    def __init__(self, account_id: str) -> None:
        self.account_id = _safe_id(account_id)
        self.dir = _root() / self.account_id
        self.path = self.dir / "cards.jsonl"

    def _read_all(self) -> list[ConfirmCard]:
        if not self.path.exists():
            return []
        out: list[ConfirmCard] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(ConfirmCard.from_dict(json.loads(line)))
                except Exception:
                    continue
        except Exception:
            return []
        return out

    def _write_all(self, cards: Iterable[ConfirmCard]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for c in cards:
                fh.write(json.dumps(c.to_dict(),
                                    ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)

    def create(self, card: ConfirmCard) -> ConfirmCard:
        with _LOCK:
            self.dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(card.to_dict(),
                                    ensure_ascii=False) + "\n")
        return card

    def decide(self, card_id: str, choice: str) -> Optional[ConfirmCard]:
        c = (choice or "").strip().lower()
        new_status = (STATUS_APPROVED if c in self._APPROVE
                      else STATUS_DENIED if c in self._DENY else None)
        if new_status is None:
            return None
        with _LOCK:
            cards = self._read_all()
            updated: Optional[ConfirmCard] = None
            for card in cards:
                if (card.card_id == card_id
                        and card.status == STATUS_PENDING):
                    card.status = new_status
                    card.decided_at = time.time()
                    updated = card
                    break
            if updated is None:
                return None
            self._write_all(cards)
            return updated

    def expire_stale(self, *, now: Optional[float] = None) -> int:
        ts = float(now) if now is not None else time.time()
        with _LOCK:
            cards = self._read_all()
            changed = 0
            for c in cards:
                if (c.status == STATUS_PENDING and c.expires_at
                        and ts >= c.expires_at):
                    c.status = STATUS_EXPIRED
                    c.decided_at = ts
                    changed += 1
            if changed:
                self._write_all(cards)
            return changed

    def get(self, card_id: str) -> Optional[ConfirmCard]:
        with _LOCK:
            for c in self._read_all():
                if c.card_id == card_id:
                    return c
        return None

    def list_pending(self, account_id: Optional[str] = None
                     ) -> list[dict[str, Any]]:
        if account_id and _safe_id(account_id) != self.account_id:
            return []
        with _LOCK:
            cards = self._read_all()
        out = [c.to_dict() for c in cards if c.status == STATUS_PENDING]
        out.sort(key=lambda d: d.get("created_at", 0.0), reverse=True)
        return out


def _scoped_memory_for(account_id: str) -> Any:
    try:
        from app.product.scoped_memory import ScopedMemory  # type: ignore
        device_id = os.environ.get("ANTICIPY_DEVICE_ID", "local")
        return ScopedMemory(account_id=account_id, device_id=device_id)
    except Exception:
        return None


def _is_safe_draft(tokens: set[str]) -> bool:
    return "draft" in tokens and not (tokens & _DRAFT_SAFE_BUSTERS)


_NEST_KEYS = ("open", "navigate", "url", "surface", "host")


def needs_confirmation(intent: Any, planned_steps: Optional[list[Any]],
                       *, surface_target: str = "",
                       money_amount: Optional[float] = None,
                       account_id: str = "") -> bool:
    """True for money / irreversible / do-not-touch. False auto-runs."""
    steps = planned_steps or []
    try:
        if money_amount is not None and float(money_amount) > 0:
            return True
    except (TypeError, ValueError):
        pass
    if _is_finance_surface(surface_target):
        return True

    if isinstance(intent, str):
        itext = intent
    elif isinstance(intent, dict):
        itext = " ".join(str(v) for v in intent.values()
                         if isinstance(v, (str, int, float)))
    else:
        itext = ""
    itoks = _tokens(itext)
    if (itoks & RISKY_VERBS) and not _is_safe_draft(itoks):
        return True

    for step in steps:
        sd = step if isinstance(step, dict) else {"text": str(step)}
        stoks = _tokens(_step_text(sd))
        if _is_safe_draft(stoks):
            continue
        if stoks & RISKY_VERBS:
            return True
        if _looks_external_email(sd):
            return True
        if isinstance(step, dict):
            for k in _NEST_KEYS:
                v = step.get(k)
                if isinstance(v, str) and _is_finance_surface(v):
                    return True

    if account_id:
        scope = _scoped_memory_for(account_id)
        if scope is not None:
            try:
                if surface_target and scope.is_do_not_touch(surface_target):
                    return True
                for step in steps:
                    for tok in re.findall(r"[\w.@+-]+", _step_text(step)):
                        if scope.is_do_not_touch(tok):
                            return True
            except Exception:
                pass
    return False


_HIGH_VERBS = {"delete", "cancel", "transfer", "wire", "publish"}


def _risk_level_for(money: Optional[float], surface: str,
                    steps: list[Any]) -> str:
    m = float(money or 0) if money is not None else 0.0
    if m >= 100 or _is_finance_surface(surface):
        return RISK_HIGH
    for step in steps:
        if isinstance(step, dict) and _looks_external_email(step):
            return RISK_MEDIUM
        toks = _tokens(_step_text(step))
        if toks & _HIGH_VERBS:
            return RISK_HIGH
        if toks & RISKY_VERBS:
            return RISK_MEDIUM
    return RISK_MEDIUM if m > 0 else RISK_LOW


def _summarize(intent: Any) -> str:
    if isinstance(intent, str) and intent.strip():
        out = intent.strip()
    elif isinstance(intent, dict):
        out = str(intent.get("summary") or intent.get("text") or
                  intent.get("intent") or "").strip()
        if not out:
            out = json.dumps(intent, ensure_ascii=False)[:240]
    else:
        out = str(intent or "").strip()
    return out[:500] or "(no summary)"


def build_confirm_card(intent: Any, planned_steps: Optional[list[Any]],
                       surface_target: str,
                       memory_context: Optional[dict[str, Any]] = None,
                       *, account_id: str = "",
                       money_amount: Optional[float] = None,
                       ttl_seconds: int = DEFAULT_TTL_SECONDS
                       ) -> ConfirmCard:
    """Produce a `ConfirmCard` ready for /app to render."""
    steps = list(planned_steps or [])
    now = time.time()
    return ConfirmCard(
        card_id=f"cc-{int(now * 1000)}-{uuid.uuid4().hex[:8]}",
        account_id=_safe_id(account_id or "unknown"),
        intent_summary=_summarize(intent), planned_steps=steps,
        risk_level=_risk_level_for(money_amount, surface_target, steps),
        money_amount=(None if money_amount is None
                      else float(money_amount)),
        surface_target=str(surface_target or ""),
        expires_at=now + max(int(ttl_seconds), 60),
        status=STATUS_PENDING, created_at=now, decided_at=None,
        extra={"memory_context": dict(memory_context or {})})
