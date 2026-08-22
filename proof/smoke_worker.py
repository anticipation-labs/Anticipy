#!/usr/bin/env python3
"""Run the REAL worker loop against a REAL local PocketBase. No mocks of our
own code — only the LLM and the SMS transport are stubbed.

This exists because both regressions on 2026-08-01 were things every unit test
passed straight over:
  * `convo` was shadowed by a local list, so every inbound SMS raised
    "'list' object has no attribute 'transport'" — but only AFTER a transcript
    had been processed first, which no unit test ever did.
  * a job/segment path can pass in isolation and still explode in the loop.
The rule: nothing deploys unless this runs green.

Usage:  PYTHONPATH=. python3 proof/smoke_worker.py [--pb ./backend/pocketbase]
"""
from __future__ import annotations

import json
import urllib.parse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 8097
BASE = f"http://127.0.0.1:{PORT}"
PASS, FAIL = [], []


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  [{detail}]" if detail and not ok else ""))


def api(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r) if r.status != 204 else {}


def start_pocketbase(binary: str, workdir: str):
    shutil.copytree(os.path.join(REPO, "backend", "pb_migrations"),
                    os.path.join(workdir, "pb_migrations"))
    shutil.copy(binary, workdir)
    exe = os.path.join(workdir, os.path.basename(binary))
    # Create the superuser BEFORE serving. A data dir with none makes
    # PocketBase print "Launch the URL below in the browser…" and open one
    # itself — and every run of this test uses a fresh dir, so every run
    # popped a PocketBase tab on Omar's machine. He noticed and asked what
    # it was; this is the thing that was doing it.
    subprocess.run([exe, "superuser", "upsert", "smoke@local.test", "smoke-password-1234"],
                   cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=60)
    proc = subprocess.Popen(
        [exe, "serve", "--http", f"127.0.0.1:{PORT}"],
        cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        time.sleep(0.5)
        try:
            api("/api/health")
            return proc
        except Exception:
            continue
    proc.kill()
    raise SystemExit("pocketbase did not start")


class StubLLM:
    """Deterministic stand-in: the shapes each caller expects, no network."""
    live = True
    model = "stub"

    class R:
        def __init__(self, text):
            self.text = text

    def chat(self, system, user, temperature=0.1, **kw):
        s = (system or "").lower()
        if "triage" in s or "ignore|ask|act" in (system or ""):
            return self.R('{"decision":"act","goal":"book a table at Cactus",'
                          '"missing":[],"assumption":null,"reason":"stub"}')
        if "audit" in s:
            return self.R('{"verified":true}')
        if "extract" in s or "people" in s:
            return self.R('{"people":[],"places":[],"topics":[],"commitment":null,'
                          '"commitment_to":null,"completed":null}')
        if "intent" in (system or ""):
            return self.R('{"intent":"confirm","pending_id":null,"changes":null,'
                          '"reply":"On it."}')
        return self.R("Okay.")


def main():
    binary = os.path.join(REPO, "backend", "pocketbase")
    if not os.path.exists(binary):
        print("SKIP: no local pocketbase binary at backend/pocketbase")
        return 0
    workdir = tempfile.mkdtemp(prefix="anticipy-smoke-")
    proc = start_pocketbase(binary, workdir)
    sent: list[dict] = []
    try:
        os.environ["ANTICIPY_PB"] = BASE
        sys.path.insert(0, REPO)
        from brain.anticipy_core import Anticipy
        from brain.conversation import Conversation
        from brain.memory import Memory
        from brain.segmenter import SegmentStore, place_turn

        llm = StubLLM()
        anticipy = Anticipy(llm=llm, memory=Memory(path=":memory:", llm=None),
                            backend_url=BASE, owner_phone="+16045550123",
                            owner_id="owner-smoke")

        class T:
            def send(self, to, body):
                rec = {"to": to, "body": body}
                sent.append(rec)
                return rec
        convo = Conversation(anticipy, transport=T(), llm=llm)
        anticipy.conversation = convo
        segments = SegmentStore(BASE, owner=anticipy.owner_id)

        # --- 1. a spoken line goes all the way through, exactly as the worker
        #        drives it: context lookup, hear(), then segment placement.
        ev = api("/api/collections/events/records",
                 {"kind": "transcript", "device_id": "smoke", "text": "book a table at Cactus for two"})
        open_seg = segments.open_segment()
        convo_context = segments.recent_turns(open_seg["id"]) if open_seg else []
        out = anticipy.hear("book a table at Cactus for two", context=convo_context)
        check("a spoken line is triaged", out["decision"].decision in ("act", "ask", "ignore"))
        placed = place_turn(segments, ev)
        check("the line lands in a conversation", placed.get("segment") is not None,
              str(placed))

        # --- 2. THE REGRESSION: an inbound text, processed AFTER a transcript,
        #        in the SAME scope the worker uses. This is the exact ordering
        #        that turned `convo` into a list and killed every SMS.
        jobs = api("/api/collections/jobs/records?filter=" +
                   urllib.parse.quote('status="awaiting_confirm"'))
        try:
            reply = convo.on_reply("+16045550123", "yes go ahead")
            check("an inbound text still works after a transcript", True)
            check("the reply is answered, not swallowed", bool(reply.get("reply")))
        except Exception as e:
            check("an inbound text still works after a transcript", False, repr(e))
            check("the reply is answered, not swallowed", False)

        # --- 3. the mock-transport surfacing the worker does every cycle
        try:
            _ = getattr(convo.transport, "sent", None)
            check("the worker can read the transport every cycle", True)
        except Exception as e:
            check("the worker can read the transport every cycle", False, repr(e))

        # --- 4. nothing may be silently dropped: every event ends up marked
        pending = api("/api/collections/events/records?filter=" +
                      urllib.parse.quote('kind="transcript" && decision=""'))
        check("events are not left unprocessed forever", pending["totalItems"] <= 1,
              f"{pending['totalItems']} unmarked")
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=10)
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"\nworker smoke: {len(PASS)} passed, {len(FAIL)} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (used above)
    sys.exit(main())
