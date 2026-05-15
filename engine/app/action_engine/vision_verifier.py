"""Vision verifier. Phase V4-3.

After every state-changing action the runner asks a SEPARATE model
call, with a separate prompt and separate context, whether the action
made visible progress toward the sub-goal. before-screenshot and
after-screenshot plus the dispatched action go in; a CERTIFIED or
DIVERGED verdict with one-sentence evidence and a confidence float
comes out.

Routing reality (V4-0, verified live 2026-05-15): no DeepSeek V4
variant has vision on OpenRouter. The only multimodal model in the
locked set is moonshotai/kimi-k2.6, which the master prompt itself
calls "Multimodal native". So the verifier runs on Kimi K2.6. The
prompt's low-confidence fallback was also "Kimi K2.6"; since that is
already the primary here, the fallback is a SECOND independent Kimi
call with a stricter rephrased prompt (separate context, separate
call) and the two verdicts are reconciled conservatively: mixed
resolves to DIVERGED.

This is the vision-woven rule: the verifier fires on every action
that changes page state. It is never skipped.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Literal, Optional

from .openrouter_client import OpenRouterClient, VISION_MODEL


@dataclass
class Verdict:
    status: Literal["CERTIFIED", "DIVERGED"]
    evidence: str
    confidence: float
    raw: str = ""
    fellback: bool = False


_PRIMARY_PROMPT = (
    "You are verifying whether a browser agent's action accomplished "
    "its sub-goal.\n"
    "Sub-goal: {subgoal}\n"
    "Action dispatched: {action}\n\n"
    "The first image is BEFORE the action. The second image is AFTER "
    "the action.\n\n"
    "Did the action make visible progress toward the sub-goal? Reply "
    "ONLY with JSON in exactly this shape:\n"
    '{{"status": "CERTIFIED" or "DIVERGED", "evidence": "one sentence", '
    '"confidence": 0.0 to 1.0}}\n\n'
    "CERTIFIED means visible progress was made. DIVERGED means the "
    "action produced no expected change, or an unexpected/ wrong change."
)

_STRICT_PROMPT = (
    "Be skeptical. A browser agent claims its action advanced a "
    "sub-goal. Assume it failed unless the AFTER image clearly proves "
    "progress.\n"
    "Sub-goal: {subgoal}\n"
    "Action dispatched: {action}\n\n"
    "First image BEFORE, second image AFTER. Reply ONLY JSON: "
    '{{"status":"CERTIFIED|DIVERGED","evidence":"one sentence",'
    '"confidence":0.0-1.0}}. Only CERTIFIED if the AFTER image shows '
    "unambiguous progress toward the sub-goal."
)


def _img_block(png: bytes) -> dict:
    b64 = base64.b64encode(png).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def _parse_verdict(text: str) -> Optional[Verdict]:
    raw = (text or "").strip()
    obj = None
    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
            except Exception:
                obj = None
    if not isinstance(obj, dict):
        return None
    status = str(obj.get("status", "")).upper().strip()
    if status not in ("CERTIFIED", "DIVERGED"):
        return None
    try:
        conf = float(obj.get("confidence", 0.0))
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    return Verdict(status=status, evidence=str(obj.get("evidence", ""))[:240],
                   confidence=conf, raw=raw[:300])


class VisionVerifier:
    LOW_CONF = 0.6

    def __init__(self, client: Optional[OpenRouterClient] = None,
                 model: str = VISION_MODEL):
        self.client = client or OpenRouterClient()
        self.model = model

    def _one_call(self, prompt_tmpl: str, action: dict, before: bytes,
                  after: bytes, subgoal: str) -> Optional[Verdict]:
        text = prompt_tmpl.format(subgoal=subgoal,
                                  action=json.dumps(action)[:300])
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "text", "text": "BEFORE:"},
                _img_block(before),
                {"type": "text", "text": "AFTER:"},
                _img_block(after),
            ],
        }]
        resp = self.client.chat(
            messages, model=self.model, max_tokens=512, temperature=0.0,
            response_format={"type": "json_object"},
        )
        if not resp.ok:
            return None
        return _parse_verdict(resp.content)

    def verify(self, action: dict, before_png: bytes, after_png: bytes,
               subgoal: str) -> Verdict:
        """Primary verdict. If it fails to parse or confidence is below
        LOW_CONF, a second independent stricter call is made and the
        two are reconciled conservatively (mixed -> DIVERGED)."""
        primary = self._one_call(_PRIMARY_PROMPT, action, before_png,
                                 after_png, subgoal)

        if primary is None:
            # Could not get/parse a verdict: stricter retry, else
            # DIVERGED (conservative: never fabricate CERTIFIED).
            strict = self._one_call(_STRICT_PROMPT, action, before_png,
                                    after_png, subgoal)
            if strict is None:
                return Verdict("DIVERGED",
                               "verifier returned no parseable verdict",
                               0.0, fellback=True)
            strict.fellback = True
            return strict

        if primary.confidence >= self.LOW_CONF:
            return primary

        # Low confidence: independent stricter second opinion.
        strict = self._one_call(_STRICT_PROMPT, action, before_png,
                                after_png, subgoal)
        if strict is None:
            primary.fellback = True
            primary.evidence = f"low-conf, no second opinion: {primary.evidence}"
            return primary

        if primary.status == strict.status:
            return Verdict(primary.status,
                           f"both agree: {strict.evidence}",
                           max(primary.confidence, strict.confidence),
                           fellback=True)
        # Mixed signals -> conservative DIVERGED.
        return Verdict("DIVERGED",
                       f"mixed verdicts (primary {primary.status}, "
                       f"strict {strict.status}); conservative DIVERGED",
                       min(primary.confidence, strict.confidence),
                       fellback=True)


if __name__ == "__main__":
    import sys
    import urllib.request
    import time
    from websockets.sync.client import connect

    # Real smoke: capture a frame, scroll, capture again, verify.
    d = json.load(urllib.request.urlopen("http://localhost:9222/json/list", timeout=6))
    pg = next(x for x in d if x.get("type") == "page")
    ws = connect(pg["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024)

    def shot() -> bytes:
        ws.send(json.dumps({"id": 1, "method": "Page.captureScreenshot",
                            "params": {"format": "png"}}))
        t = time.time()
        while time.time() - t < 10:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                return base64.b64decode(m["result"]["data"])
        raise RuntimeError("no shot")

    before = shot()
    ws.send(json.dumps({"id": 2, "method": "Input.dispatchKeyEvent",
                        "params": {"type": "rawKeyDown", "key": "PageDown",
                                   "code": "PageDown"}}))
    time.sleep(1.0)
    after = shot()
    ws.close()

    v = VisionVerifier()
    verdict = v.verify({"action": "scroll", "direction": "down"},
                       before, after, "Scroll the page down")
    print(json.dumps({"status": verdict.status, "evidence": verdict.evidence,
                       "confidence": verdict.confidence,
                       "fellback": verdict.fellback}, indent=2))
    sys.exit(0)
