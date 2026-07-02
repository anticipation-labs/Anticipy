"""Anticipatory research — the "hear a name, figure out who they are" chain.

When the brain hears someone mentioned in conversation (e.g., "I told Nicki about
the fundraising deck"), this module:

1. Extracts the person's name from the task context
2. Searches memory for past interactions with that person
3. Attempts IMAP search of owner's email (with timeout fallback)
4. Asks the model to synthesize who they are from available evidence
5. Generates a human-tone notification about what it found

This is the ANTICIPATORY piece — the system doesn't wait to be told who Nicki is.
It figures it out from the owner's own world and prepares the action.
"""
from __future__ import annotations

import asyncio
import imaplib
import email
import json
import os
import re
from dataclasses import dataclass, field
from email.header import decode_header
from typing import Any, Dict, List, Optional

from ..core.gateway import CHEAP, ModelGateway

# SnappyMail / Porkbun IMAP config
IMAP_HOST = os.environ.get("ANTICIPY_IMAP_HOST", "mail.porkbun.com")
IMAP_PORT = int(os.environ.get("ANTICIPY_IMAP_PORT", "993"))
IMAP_USER = os.environ.get("ANTICIPY_IMAP_USER", "")
IMAP_PASS = os.environ.get("ANTICIPY_IMAP_PASS", "")
IMAP_TIMEOUT = 8  # seconds — fail fast if IMAP is blocked


@dataclass
class PersonContext:
    """What the system figured out about a person mentioned in conversation."""
    name: str
    email_address: Optional[str] = None
    relationship: Optional[str] = None
    last_contact: Optional[str] = None
    email_snippets: List[str] = field(default_factory=list)
    memory_hits: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = "research"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "email": self.email_address,
            "relationship": self.relationship,
            "last_contact": self.last_contact,
            "snippets": self.email_snippets[:3],
            "memory_hits": self.memory_hits[:5],
            "confidence": self.confidence,
            "source": self.source,
        }


def _decode_mime_header(raw: str) -> str:
    parts = decode_header(raw or "")
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


def _imap_search(name: str, folder: str = "INBOX", max_results: int = 10) -> List[Dict[str, str]]:
    """Search one IMAP folder for messages involving a person. Timeout-guarded."""
    import socket
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(IMAP_TIMEOUT)
    results: List[Dict[str, str]] = []
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        conn.login(IMAP_USER, IMAP_PASS)
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            conn.logout()
            return []

        search_query = f'(OR (FROM "{name}") (OR (TO "{name}") (SUBJECT "{name}")))'
        status, msg_ids = conn.search(None, search_query)
        if status != "OK" or not msg_ids[0]:
            status, msg_ids = conn.search(None, f'(TEXT "{name}")')

        if status == "OK" and msg_ids[0]:
            ids = msg_ids[0].split()[-max_results:]
            for mid in reversed(ids):
                try:
                    status, data = conn.fetch(mid, "(BODY[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
                    if status != "OK":
                        continue
                    msg = email.message_from_bytes(data[0][1])
                    results.append({
                        "from": _decode_mime_header(msg.get("From", "")),
                        "to": _decode_mime_header(msg.get("To", "")),
                        "subject": _decode_mime_header(msg.get("Subject", "")),
                        "date": msg.get("Date", ""),
                    })
                except Exception:
                    continue
        conn.logout()
    except Exception:
        pass
    finally:
        socket.setdefaulttimeout(old_timeout)
    return results


def search_email_for_person(name: str) -> List[Dict[str, str]]:
    """Search inbox + sent for a person. Returns empty if IMAP unavailable."""
    if not IMAP_USER or not IMAP_PASS:
        return []
    inbox = _imap_search(name, "INBOX", 5)
    sent = _imap_search(name, "Sent", 3)
    return inbox + sent


def search_memory_for_person(name: str, remembered_items: List[Dict]) -> List[str]:
    """Search the in-memory remembered items for mentions of a person."""
    hits = []
    name_lower = name.lower()
    for item in remembered_items:
        text = item.get("text", "")
        people = item.get("people", [])
        # Check if this person is mentioned in the text or people list
        if name_lower in text.lower() or any(name_lower in p.lower() for p in people):
            hits.append(text)
    return hits


async def research_person(
    name: str,
    task_context: str,
    gateway: ModelGateway,
    remembered_items: Optional[List[Dict]] = None,
    *,
    caller: str = "anticipate",
) -> PersonContext:
    """The full anticipatory research chain for a mentioned person.

    1. Search memory for past mentions
    2. Attempt IMAP email search (with timeout)
    3. Ask the model to synthesize who they are from available evidence
    """
    # Step 1: Search memory
    memory_hits = []
    if remembered_items:
        memory_hits = search_memory_for_person(name, remembered_items)

    # Step 2: Attempt email search (with timeout so it doesn't block)
    email_results = []
    try:
        email_results = await asyncio.wait_for(
            asyncio.to_thread(search_email_for_person, name),
            timeout=IMAP_TIMEOUT + 2
        )
    except (asyncio.TimeoutError, Exception):
        pass

    # Build evidence
    evidence_parts = []
    if memory_hits:
        evidence_parts.append("FROM MEMORY (past interactions):")
        for h in memory_hits[:5]:
            evidence_parts.append(f"  - {h}")

    if email_results:
        evidence_parts.append("FROM EMAIL:")
        for e in email_results[:5]:
            evidence_parts.append(
                f"  From: {e.get('from','?')} | To: {e.get('to','?')} | "
                f"Subject: {e.get('subject','?')} | Date: {e.get('date','?')}"
            )

    if not evidence_parts:
        # No evidence from memory or email — use model inference from context alone
        return PersonContext(
            name=name,
            relationship="mentioned in conversation, no prior history found",
            confidence=0.2,
            source="context_only",
            memory_hits=memory_hits,
        )

    evidence = "\n".join(evidence_parts)

    # Step 3: Model synthesis
    prompt = f"""You are Anticipy, an anticipatory assistant. The owner mentioned "{name}" 
in the context: "{task_context}"

Here is what we know about "{name}" from the owner's world:

{evidence}

From ONLY what the evidence shows, answer in strict JSON (no prose, no code fence):
{{
  "email": "their email address if visible, or null",
  "relationship": "one-line: who they are to the owner",
  "last_contact": "when the most recent interaction was, or null",
  "confidence": 0.0-1.0,
  "summary": "one sentence about the owner's relationship with this person"
}}

Use ONLY what the evidence shows. Never invent."""

    try:
        raw = await gateway.think(
            prompt, tier=CHEAP, caller=caller,
            json_mode=True, temperature=0.1,
        )
        data = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.I | re.M))
    except Exception:
        data = {}

    return PersonContext(
        name=name,
        email_address=data.get("email"),
        relationship=data.get("relationship", "found in memory/email"),
        last_contact=data.get("last_contact"),
        email_snippets=[e.get("subject", "")[:100] for e in email_results[:3]],
        memory_hits=memory_hits[:5],
        confidence=data.get("confidence", 0.5),
        source="memory" if memory_hits and not email_results else "email" if email_results else "model",
    )


def extract_people_from_task(task_text: str) -> List[str]:
    """Extract person names from a task description."""
    skip = {
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
        "January", "February", "March", "April", "May", "June", "July", "August",
        "September", "October", "November", "December",
        "The", "This", "That", "Send", "Get", "Put", "Set", "Call", "Tell", "Ask",
        "Pay", "Buy", "Order", "Pick", "Drop", "Follow", "Check", "Make", "Take",
        "Draft", "Write", "Read", "Find", "Look", "Search", "Open", "Close",
        "Gmail", "Calendar", "LinkedIn", "Chrome", "Google", "Outlook",
        "Anticipy", "Ready", "Waiting", "Blocked", "Stopped",
        "Dr", "Mr", "Mrs", "Ms", "Prof", "Quick", "Just", "Need",
    }
    words = re.findall(r"\b([A-Z][a-z]+)\b", task_text)
    seen = set()
    names = []
    for c in words:
        if c not in skip and len(c) > 1 and c.lower() not in seen:
            seen.add(c.lower())
            names.append(c)
    return names


async def anticipatory_research(
    task_text: str,
    people: List[str],
    gateway: ModelGateway,
    remembered_items: Optional[List[Dict]] = None,
    *,
    caller: str = "anticipate",
) -> Dict[str, PersonContext]:
    """Research all mentioned people in parallel."""
    if not people:
        people = extract_people_from_task(task_text)
    if not people:
        return {}

    tasks = [
        research_person(name, task_text, gateway, remembered_items, caller=caller)
        for name in people
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: Dict[str, PersonContext] = {}
    for name, result in zip(people, results):
        if isinstance(result, PersonContext):
            out[name] = result
        else:
            out[name] = PersonContext(
                name=name, relationship="could not research",
                confidence=0.0, source="error",
            )
    return out


def format_human_notification(task_text: str, research: Dict[str, PersonContext]) -> str:
    """Format a human-tone notification about what the system found."""
    if not research:
        return ""

    parts = []
    for name, ctx in research.items():
        if ctx.confidence > 0.5 and ctx.email_address:
            parts.append(
                f"I found {name}'s email ({ctx.email_address}) — "
                f"looks like {ctx.relationship or 'someone you work with'}."
            )
        elif ctx.confidence > 0.3 and ctx.memory_hits:
            parts.append(
                f"I looked into {name} — "
                f"{ctx.relationship or 'they came up in past conversations'}. "
                f"You mentioned them {len(ctx.memory_hits)} time(s) before."
            )
        elif ctx.confidence > 0.3:
            parts.append(
                f"I looked into who {name} is — "
                f"{ctx.relationship or 'they came up in your emails'}."
            )
        else:
            parts.append(
                f"I don't have much on {name} yet — "
                f"want me to ask you about them?"
            )

    return " Also, ".join(parts) if parts else ""
