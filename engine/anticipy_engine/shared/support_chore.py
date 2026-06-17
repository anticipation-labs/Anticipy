"""Reversible external-service chore detection (THE AUTONOMY LAW, AUTO_DO_WITH_OPT_OUT).

"Call Amazon about that plant I ordered", "contact support about my refund", "chase the
delivery with the courier", "follow up with the airline about my cancelled flight" — these are
the reversible-external-service-chore class: contacting / calling a COMPANY or its SUPPORT about
an ORDER / refund / return / delivery / cancellation / issue. By the autonomy law these must
START (AUTO_DO_WITH_OPT_OUT: "I'm on it — tell me to stop"), not wait for a yes. The engine
routes them to the browser/support arm (route=browser, action=browser_action), which
autonomy.py maps to AUTO_DO_WITH_OPT_OUT.

This is the OPPOSITE of an approval-machine ask: a low-risk reversible chore the assistant just
gets on with. It still hard-stops at the true irreversible boundary — money / pay / checkout /
send to a third party — those are detected and excluded here so they stay blocked /
prepare-then-stop. A third-party SEND to a PERSON (email/text Sam) is NOT this class either.

Deliberately TIGHT (deny-direction): it requires BOTH (a) a contact verb aimed at a company /
support, AND (b) an order/service-issue subject — so a bare "call mom", "call the dentist", or
"email the lawyer" never matches. Pure-Python, deterministic, no model calls.
"""
from __future__ import annotations

import re
from typing import Optional

# A contact/reach-out verb. "call/contact/reach out to/get in touch/follow up with/chase/
# check with/ask/get hold of" — the spoken ways you reach a company about a problem.
_CONTACT_VERB = (
    r"(?:call|calls|calling|called|"
    r"contact|contacts|contacting|contacted|"
    r"reach\s+out\s+to|reach\s+out|get\s+(?:in\s+touch\s+with|in\s+touch|hold\s+of|back\s+to)|"
    r"follow\s+up\s+with|follow\s+up\s+on|chase(?:\s+up)?|chases|chasing|chased|"
    r"check\s+(?:in\s+)?with|ping|message|email|emails|emailing)"
)

# A COMPANY / support endpoint — a named brand-ish company, the generic word "support"/
# "customer service"/"the company"/"the seller"/"the store"/"the carrier", or a service the
# chore is plainly about. Bare lowercase common nouns ("mom", "the dentist", "the office") are
# NOT companies, so they do not match here.
_COMPANY = (
    r"(?:[A-Z][\w&.-]+(?:\s+[A-Z][\w&.-]+)?"  # a Capitalized brand-ish name (Amazon, Best Buy, FedEx)
    r"|support|customer\s+(?:service|support|care)|"
    r"the\s+(?:company|seller|store|shop|vendor|merchant|retailer|carrier|courier|"
    r"airline|bank|provider|helpline|help\s*desk|call\s+cent(?:er|re)))"
)

# The ORDER / service-issue SUBJECT — what the chore is ABOUT. An order/refund/return/
# delivery/shipment/cancellation/charge dispute/booking/reservation/account/billing issue/
# warranty/repair/complaint/ticket. (A money WORD here describes the dispute subject, not a
# payment action — the spend-verb guard below is what keeps real payments out.)
_ISSUE_SUBJECT = re.compile(
    r"\b(?:order(?:ed|s)?|refund(?:s|ed)?|return(?:s|ed)?|exchange|replacement|"
    r"deliver(?:y|ies)|shipment|shipping|package|parcel|tracking|"
    r"cancel(?:l?ed|l?ation|ling)?|reschedul\w*|booking|reservation|"
    r"account|subscription|membership|billing|invoice\s+(?:error|issue|problem|dispute)|"
    r"charge\s+(?:dispute|error|issue)|overcharge|dispute|"
    r"warranty|repair|defect(?:ive)?|broken|damaged|missing|wrong\s+item|"
    r"complaint|issue|problem|ticket|case|claim|appointment)\b",
    re.I,
)

# A real money/transaction verb makes the line a TRUE irreversible boundary (pay/checkout/
# send-money), never an auto-startable chore — it stays blocked / prepare-then-stop. Listing a
# refund/charge as the SUBJECT (above) is fine; instructing a PAYMENT is not.
_SPEND_VERB = re.compile(
    r"\b(?:pay|paid|pays|paying|buy|buys|buying|bought|purchase|purchasing|"
    r"checkout|check\s+out|wire|venmo|zelle|cashapp|cash\s?app|paypal|"
    r"deposit|withdraw|transfer\s+(?:money|\$|funds)|reimburse)\b",
    re.I,
)

_CONTACT_COMPANY_RE = re.compile(
    r"\b" + _CONTACT_VERB + r"\b[\s,]*" + _COMPANY,
)


def match_support_chore(text: str) -> Optional[str]:
    """Return the cleaned line iff it is a reversible external-service chore: contact a company /
    support ABOUT an order / refund / return / delivery / cancellation / issue. Returns None for a
    real payment (any spend verb), and None when there is no company-contact + service-issue pair —
    so "call mom", "call the dentist at 3", "email Sam the deck" never match. Used by the spine to
    route the chore to the support/browser arm (AUTO_DO_WITH_OPT_OUT) instead of an approval ask."""
    line = re.sub(r"\s+", " ", text or "").strip()
    if not line:
        return None
    m = _CONTACT_COMPANY_RE.search(line)
    if not m:
        return None
    if not _ISSUE_SUBJECT.search(line):
        return None
    # The spend-verb guard runs on the line with the matched contact+company span NEUTRALIZED, so a
    # brand whose name contains a spend word ("Best Buy", "PayPal") never reads as a payment
    # instruction. A real spend verb elsewhere ("call Amazon and pay the balance") still gates -> None.
    rest = line[:m.start()] + " " + line[m.end():]
    if _SPEND_VERB.search(rest):
        return None
    return line
