"""PRIVACY — the first-class privacy layer (M5), gated like the money hard-stop.

An always-listening device records other people, health, finances, and kids. Privacy is not a
polish pass; it is designed into the hot path:

  - **NEVER-STORE secrets** (SSN, card/account numbers, passwords/PINs): the raw VALUE is redacted
    at the source, BEFORE it is written to any durable table (drawers OR the inert remember-list),
    so a raw secret can never persist and can never leave the device. The masked line is kept so
    the *fact that it was said* is not lost — only the secret value is gone.
  - **SENSITIVE categories** (health, financial context): stored but TAGGED (fields["sensitivity"])
    and given a RETENTION window (valid_to) so they auto-expire via the same M3 bi-temporal filter,
    and are masked before egress.
  - **Redact-before-egress**: any context string leaving the device (to a model / the frontend) is
    run through `redact()` again — defense in depth on top of redaction-at-rest.
  - **Right-to-delete**: `Memory`-level purge wipes every drawer AND the remember-list (all traces).

Deterministic + local (no model on the hot path); the live seam can enrich detection later.
"""
from __future__ import annotations

import re
from typing import Set, Tuple

# secrets whose raw value must NEVER persist or leave the device.
NEVER_STORE: Set[str] = {"ssn", "credit_card", "password", "bank_account"}
# sensitive-but-keepable categories: stored, tagged, retention-bounded, masked on egress.
SENSITIVE: Set[str] = {"health", "financial"}
RETENTION_DAYS = 90.0                      # a tagged sensitive fact auto-expires after this

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC = re.compile(r"\b(?:\d[ -]?){13,16}\b")
# "my password is hunter2", "pin: 4432", "routing number is 021000021"
_SECRET_KV = re.compile(
    r"\b(password|passcode|passphrase|pin|routing\s+number|account\s+number)\b"
    r"\s*(?:is|are|=|:)?\s*(?P<val>[^\s.,;!?]+)", re.I)
_HEALTH = re.compile(
    r"\b(diagnos\w*|prescri\w*|medication|meds|dosage|\d+\s*mg|blood pressure|cholesterol|"
    r"therapy|therapist|depress\w*|anxiety|diabet\w*|cancer|pregnan\w*|hiv|std|surgery|chemo)\b",
    re.I)
_FINANCIAL = re.compile(
    r"\b(bank account|routing number|account number|iban|salary|net worth|credit score|"
    r"debit card|wire transfer|overdraft)\b", re.I)


def redact(text: str) -> Tuple[str, Set[str]]:
    """Mask NEVER-STORE secret VALUES in `text` and return (masked_text, categories_present).

    Categories include both never-store (masked here) and sensitive (health/financial, tagged
    but not value-masked because there is usually no discrete value to strip). Idempotent: a
    string already containing `[redacted:*]` is safe to run again (egress defense in depth)."""
    cats: Set[str] = set()
    out = text or ""

    if _SSN.search(out):
        cats.add("ssn")
        out = _SSN.sub("[redacted:ssn]", out)

    def _kv(m: "re.Match") -> str:
        key = re.sub(r"\s+", " ", m.group(1).lower())
        cat = "bank_account" if ("account" in key or "routing" in key) else "password"
        cats.add(cat)
        return f"{m.group(1)} [redacted:{cat}]"

    out = _SECRET_KV.sub(_kv, out)

    if _CC.search(out):
        cats.add("credit_card")
        out = _CC.sub("[redacted:card]", out)

    if _HEALTH.search(out):
        cats.add("health")
    if _FINANCIAL.search(out):
        cats.add("financial")
    return out, cats


def has_never_store(cats: Set[str]) -> bool:
    return bool(cats & NEVER_STORE)


def is_sensitive(cats: Set[str]) -> bool:
    return bool(cats & (NEVER_STORE | SENSITIVE))
