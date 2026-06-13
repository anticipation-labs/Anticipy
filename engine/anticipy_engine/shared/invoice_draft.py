"""Invoice-draft tasks that must stop at ask-first.

This is the money-adjacent admin shape where the owner is not asking to send or
finalize an invoice. They are asking for a draft/review step around an invoice,
which is still client/financial enough that the product should surface a waiting
ask card instead of silently acting.
"""
from __future__ import annotations

import re

_INVOICE = re.compile(r"\b(?:invoice|invoicing)\b", re.I)
_DRAFT = re.compile(
    r"\b(?:draft|drafts|drafted|drafting|prepare|prepares|preparing|"
    r"compose|composes|composing|write up|writes up|draw up|draws up)\b",
    re.I,
)
_REVIEW = re.compile(
    r"\b(?:review|approve|approval|sanity[- ]?check|look over|sign off|"
    r"confirm|check(?:ing|ed)?\s+(?:the\s+)?(?:hours|numbers|totals|line items))\b",
    re.I,
)
_SELF_CORRECTION = re.compile(
    r"(?:^|[.;!?\s])(?:no|not yet)\b"
    r"|\b(?:don'?t|do not)\s+(?:send|invoice|finali[sz]e)\b"
    r"|\bhold\s+off\b|\bbefore\s+(?:sending|finali[sz]ing|invoicing)\b"
    r"|\buntil\s+(?:[^.;!?]{0,40}\b(?:review|approve|approval|sanity[- ]?check|sign off|confirm))\b",
    re.I,
)


def match_invoice_draft_ask(text: str) -> bool:
    """True for invoice draft/review requests that should become waiting asks."""
    t = text or ""
    if not (_INVOICE.search(t) and _DRAFT.search(t)):
        return False
    return bool(_REVIEW.search(t) or _SELF_CORRECTION.search(t))
