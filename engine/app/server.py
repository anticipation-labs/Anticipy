"""The real engine HTTP server. Phase 2 integration.

Wraps the ALREADY-PROVEN end-to-end flow (app.e2e.flow.run_flow,
the MH-P1 path: real synthetic-wearer-voice audio -> real parakeet
ASR + four-layer stack -> real frozen reasoning -> real
proactive_day resolution/timing/completion/cancel/personalization
-> real comms decision -> real frozen browser action -> a real
proposal). Read-only over the frozen engines; nothing frozen is
modified. This is the process the new frontend talks to for real.

Endpoints:
  GET  /health         liveness, so the frontend reports LIVE
  POST /journey/run     runs the whole real customer pipeline once
                        and returns the real per-stage result + the
                        real proposal. Honest gated edges (a human
                        physically present, real accounts) are
                        reported as their real state, never faked.
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Anticipy Engine", version="phase2")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"])


@app.get("/health")
def health() -> dict:
    return {"ok": True, "ts": time.time(), "service": "anticipy-engine"}


@app.post("/journey/run")
def journey_run(body: dict | None = None) -> dict:
    """The whole real pipeline, one run. The frontend's Listen press
    calls this. Returns the real stages + the real proposal.
    """
    body = body or {}
    spoken = body.get(
        "spoken_text",
        "I'll send Dana the budget before the Thursday review")
    from app.e2e.flow import run_flow

    fr = run_flow(spoken_text=spoken,
                  safe_url=body.get("safe_url", "https://example.com"),
                  do_mic=bool(body.get("do_mic", True)))
    return {
        "ok": True,
        "transcript": fr.transcript,
        "engine_decision": fr.engine_decision,
        "proposal": fr.proposal,
        "stages": [
            {"name": s.name, "real": s.real, "gated": s.gated,
             "detail": s.detail, "data": s.data}
            for s in fr.stages
        ],
    }
