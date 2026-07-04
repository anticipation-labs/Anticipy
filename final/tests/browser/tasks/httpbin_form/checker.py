"""Functional checker for task (A) — httpbin.org/forms/post form-fill.

Independent re-read: httpbin echoes every POSTed field back as JSON. The harness
plants a fresh {NONCE} in `custname`/`comments`; that exact string can appear in
the resulting page ONLY if a real trusted submit actually happened. We assert the
nonce is present in the *page read-back the browser itself produced*
(`result.final_text` / `final_url` / `final_corpus`) — not in the agent's prose
answer, which could hallucinate success.

Contract shared by every task checker:
  check(result, ctx)  -> (ok: bool, detail: str)
  synth_pass(ctx)     -> a fake /agent/run result that MUST pass
  synth_fail(ctx)     -> a fake /agent/run result that MUST fail
  (optional) setup(ctx) / teardown(ctx) / start_url(ctx)
"""
from __future__ import annotations

import json


def _readback_blob(result: dict) -> str:
    """The independent evidence: what the BROWSER read back off the real page.
    Deliberately excludes result['answer'] (the model's self-report)."""
    parts = [
        str(result.get("final_text") or ""),
        str(result.get("final_url") or ""),
        str(result.get("final_corpus") or ""),
        str(result.get("final_state") or ""),
    ]
    return "\n".join(parts)


def check(result: dict, ctx: dict) -> tuple[bool, str]:
    nonce = ctx["nonce"]
    marker = f"ANTICIPY-{nonce}"
    blob = _readback_blob(result)
    if marker not in blob:
        # Fall back to the JSON of the whole result MINUS the answer field, so a
        # nonce captured in history/observation still counts, but a nonce that
        # only appears in the model's prose does not.
        scrub = dict(result)
        scrub.pop("answer", None)
        scrub.pop("judgment", None)
        if marker not in json.dumps(scrub):
            return False, f"planted marker {marker!r} not echoed back by the server (no real submit)"
    # httpbin nests submitted fields under "form"; if we can parse it, assert the
    # exact value, which is a stronger check than a substring hit.
    try:
        obj = json.loads(result.get("final_text") or "{}")
        form = obj.get("form") or {}
        got = form.get("custname")
        if got and got != marker:
            return False, f"custname echoed as {got!r}, expected {marker!r}"
    except Exception:
        pass  # final_text may be HTML-wrapped JSON; the substring check above still stands
    return True, f"server echoed the planted custname {marker!r}"


def synth_pass(ctx: dict) -> dict:
    nonce = ctx["nonce"]
    marker = f"ANTICIPY-{nonce}"
    echo = {"form": {"custname": marker, "custtel": "5551234567",
                     "custemail": f"eval-{nonce}@example.com", "size": "large",
                     "comments": f"order-{nonce}"}, "url": "https://httpbin.org/post"}
    return {
        "answer": f"The server echoed custname as {marker}.",
        "final_url": "https://httpbin.org/post",
        "final_text": json.dumps(echo),
        "metrics": {"steps": 7, "est_cost_usd": 0.0121, "frontier_pct": 14.0,
                    "vision_pct": 40.0, "region_pct": 85.0, "replayed": False},
        "task_succeeded": True,
    }


def synth_fail(ctx: dict) -> dict:
    # The failure mode we most care about: the agent CLAIMS success in prose, but
    # the real echo page never contains the planted marker (it never submitted).
    nonce = ctx["nonce"]
    return {
        "answer": f"Done — I submitted the form with custname ANTICIPY-{nonce}.",
        "final_url": "https://httpbin.org/forms/post",
        "final_text": "<html><body>... the empty form page, no submission echo ...</body></html>",
        "metrics": {"steps": 3, "est_cost_usd": 0.004, "frontier_pct": 0.0,
                    "vision_pct": 0.0, "region_pct": 0.0, "replayed": False},
        "task_succeeded": True,   # deliberately lies; the checker must override this
    }
