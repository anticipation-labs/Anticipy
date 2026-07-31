"""Anticipy brain worker — the server-side mind loop.

The phone posts raw transcript lines to PocketBase (`events`, kind
"transcript"). This worker is the one place they all flow through:
each line -> Anticipy.hear() -> memory graph + triage + (held) job, then the
decision and anything Anticipy wants to say are written back as events the
app renders in its feed. It also closes loops as jobs finish.

Run:  .venv/bin/python -m brain.worker
"""
from __future__ import annotations

import json
import os
import time

import requests

from .anticipy_core import Anticipy
from .memory import Memory
from .conversation import Conversation, MockTransport, TwilioTransport
from .llm import LLM
from .voice_arm import VoiceArm

PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
POLL_SECONDS = 2


def post_event(kind: str, text: str, decision: str = "", goal: str = "") -> None:
    requests.post(f"{PB}/api/collections/events/records", json={
        "device_id": "anticipy-brain", "kind": kind, "text": text,
        "decision": decision, "goal": goal or "",
    }, timeout=10)


def fetch_unprocessed(kind: str = "transcript") -> list[dict]:
    r = requests.get(
        f"{PB}/api/collections/events/records",
        params={"filter": f'kind="{kind}" && decision=""',
                "perPage": 20, "sort": "created"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("items", [])


def mark_processed(event_id: str, decision: str) -> None:
    requests.patch(f"{PB}/api/collections/events/records/{event_id}",
                   json={"decision": decision}, timeout=10)


def main() -> None:
    llm = LLM()
    mem_db = os.environ.get("ANTICIPY_MEMORY_DB", ":memory:")
    memory = Memory(path=mem_db, llm=llm if llm.live else None)
    anticipy = Anticipy(llm=llm if llm.live else None, memory=memory, backend_url=PB,
                        owner_phone=os.environ.get("ANTICIPY_OWNER_PHONE", "owner"),
                        owner_id=os.environ.get("ANTICIPY_OWNER_ID", ""))
    # Live texting when Twilio credentials are present; mock otherwise.
    live_sms = all(os.environ.get(k) for k in
                   ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"))
    voice = VoiceArm() if live_sms else None
    if voice:
        anticipy.voice = voice
    convo = Conversation(anticipy, transport=TwilioTransport(voice) if voice else MockTransport())
    anticipy.conversation = convo
    print(f"worker up · llm={'live:' + llm.model if llm.live else 'heuristic'}"
          f" · sms={'live' if live_sms else 'mock'} · pb={PB}")

    sent_seen = 0
    while True:
        try:
            for ev in fetch_unprocessed():
                line = ev.get("text", "").strip()
                if not line:
                    mark_processed(ev["id"], "ignore")
                    continue
                # A crash mid-hear must not leave the event unmarked: the poll
                # would replay it every 2s, minting a duplicate job (and SMS)
                # per attempt — this happened live on 2026-07-30 (6 jobs from
                # one line when the owner-notify SMS failed).
                try:
                    out = anticipy.hear(line)
                except Exception as e:
                    mark_processed(ev["id"], "error")
                    print(f"heard: {line!r} -> error: {e}")
                    continue
                decision = out["decision"].decision
                mark_processed(ev["id"], decision)
                if out.get("anticipy_says"):
                    post_event("anticipy_says", out["anticipy_says"],
                               decision=decision, goal=out["decision"].goal or "")
                print(f"heard: {line!r} -> {decision}"
                      f" ({out['decision'].goal or 'no goal'})")

            # Inbound texts (Twilio webhook -> pb_hooks -> events) flow through
            # the same conversation the pendant path uses; the reply goes back
            # out over the live transport.
            for ev in fetch_unprocessed("sms_reply"):
                text = ev.get("text", "").strip()
                phone = ev.get("goal", "").strip() or anticipy.owner_phone
                if not text:
                    mark_processed(ev["id"], "ignore")
                    continue
                try:
                    out = convo.on_reply(phone, text)
                except Exception as e:
                    mark_processed(ev["id"], "error")
                    print(f"sms in: {text!r} -> error: {e}")
                    continue
                mark_processed(ev["id"], out["intent"])
                post_event("anticipy_text", out["reply"])
                print(f"sms in: {text!r} -> {out['intent']}")

            # Surface anything she "texted" (mock transport) into the feed too.
            sent = getattr(convo.transport, "sent", None)
            if sent is not None:
                for msg in sent[sent_seen:]:
                    post_event("anticipy_text", msg["body"])
                sent_seen = len(sent)

            anticipy.review_loops()
        except requests.RequestException as e:
            print(f"backend unreachable: {e}")
        except Exception as e:
            print(f"worker error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
