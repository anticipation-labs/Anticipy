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
from .conversation import Conversation, MockTransport
from .llm import LLM

PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
POLL_SECONDS = 2


def post_event(kind: str, text: str, decision: str = "", goal: str = "") -> None:
    requests.post(f"{PB}/api/collections/events/records", json={
        "device_id": "anticipy-brain", "kind": kind, "text": text,
        "decision": decision, "goal": goal or "",
    }, timeout=10)


def fetch_unprocessed() -> list[dict]:
    r = requests.get(
        f"{PB}/api/collections/events/records",
        params={"filter": 'kind="transcript" && decision=""',
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
    anticipy = Anticipy(llm=llm if llm.live else None, backend_url=PB,
                        owner_phone=os.environ.get("ANTICIPY_OWNER_PHONE", "owner"))
    convo = Conversation(anticipy, transport=MockTransport())
    anticipy.conversation = convo
    print(f"worker up · llm={'live:' + llm.model if llm.live else 'heuristic'} · pb={PB}")

    sent_seen = 0
    while True:
        try:
            for ev in fetch_unprocessed():
                line = ev.get("text", "").strip()
                if not line:
                    mark_processed(ev["id"], "ignore")
                    continue
                out = anticipy.hear(line)
                decision = out["decision"].decision
                mark_processed(ev["id"], decision)
                if out.get("anticipy_says"):
                    post_event("anticipy_says", out["anticipy_says"],
                               decision=decision, goal=out["decision"].goal or "")
                print(f"heard: {line!r} -> {decision}"
                      f" ({out['decision'].goal or 'no goal'})")

            # Surface anything she "texted" (mock transport) into the feed too.
            for msg in convo.transport.sent[sent_seen:]:
                post_event("anticipy_text", msg["body"])
            sent_seen = len(convo.transport.sent)

            anticipy.review_loops()
        except requests.RequestException as e:
            print(f"backend unreachable: {e}")
        except Exception as e:
            print(f"worker error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
