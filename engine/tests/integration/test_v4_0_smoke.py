"""Phase V4-0 gate: confirm the environment reaches the locked models
via OpenRouter with text and vision.

Documented architecture reality (verified against the live OpenRouter
catalog on 2026-05-15):

  deepseek/deepseek-v4-flash : input_modalities = ['text']  (NO vision)
  deepseek/deepseek-v4-pro   : input_modalities = ['text']  (NO vision)
  moonshotai/kimi-k2.6       : input_modalities = ['text','image']

The master prompt anticipated this exact case: "If V4 Flash on
OpenRouter does not support vision yet ... fall back ... and keep V4
Flash for text-only steps. Document this in PROGRESS.md." The prompt's
suggested vision fallback was deepseek-v4-pro, but that is ALSO
text-only on OpenRouter. The only multimodal model in the locked set
(section 2) is Kimi K2.6, which the prompt itself calls "Multimodal
native". So the final routing, staying inside the two locked models:

  TEXT steps  (decide, completion, decompose) -> deepseek/deepseek-v4-flash
  VISION steps (the vision verifier)           -> moonshotai/kimi-k2.6

BOTH locked models are reasoning models on OpenRouter: every response
carries a `reasoning` field plus `content`. With a small max_tokens
the reasoning consumes the entire budget and `content` comes back
None (finish_reason=length). max_tokens must be generous (>=200) or
the answer is starved. This shapes the whole architecture: the
OpenRouter client always budgets for reasoning plus the answer.

This test exits 0 only if every check passes.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request

import requests
from dotenv import load_dotenv
from websockets.sync.client import connect

load_dotenv(os.path.expanduser("~/.anticipy/.env"))

OR_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OR_URL = "https://openrouter.ai/api/v1"
TEXT_MODEL = "deepseek/deepseek-v4-flash"
VISION_MODEL = "moonshotai/kimi-k2.6"


def _fail(msg: str):
    print(f"V4-0 FAIL: {msg}")
    sys.exit(1)


def _or_chat(model: str, content, max_tokens: int) -> str:
    r = requests.post(
        f"{OR_URL}/chat/completions",
        headers={"Authorization": f"Bearer {OR_KEY}", "Content-Type": "application/json"},
        json={"model": model,
              "messages": [{"role": "user", "content": content}],
              "max_tokens": max_tokens, "temperature": 0},
        timeout=60,
    )
    r.raise_for_status()
    j = r.json()
    if "choices" not in j:
        raise RuntimeError(f"no choices: {json.dumps(j)[:200]}")
    return (j["choices"][0]["message"].get("content") or "").strip()


def _screenshot_from_chrome() -> bytes:
    d = json.load(urllib.request.urlopen("http://localhost:9222/json/list", timeout=6))
    pg = next(x for x in d if x.get("type") == "page")
    ws = connect(pg["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024)
    try:
        ws.send(json.dumps({"id": 1, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
        deadline = time.time() + 10
        while time.time() < deadline:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                return base64.b64decode(m["result"]["data"])
    finally:
        ws.close()
    raise RuntimeError("no screenshot captured")


def test_v4_0_smoke():
    # 1. key
    if not OR_KEY.startswith("sk-or-"):
        _fail("OPENROUTER_API_KEY missing or malformed in ~/.anticipy/.env")
    print(f"1. OPENROUTER_API_KEY ok ({OR_KEY[:12]}...)")

    # 2. Chrome :9222
    try:
        ver = json.load(urllib.request.urlopen("http://localhost:9222/json/version", timeout=6))
        browser = ver.get("Browser", "")
    except Exception as e:
        _fail(f"Chrome :9222 unreachable: {e}")
    if "Chrome/" not in browser:
        _fail(f"unexpected browser: {browser}")
    print(f"2. Chrome :9222 ok ({browser})")

    # 3. profile clone cookies
    cookies = os.path.expanduser("~/.anticipy/chrome-real-clone/Default/Cookies")
    if not (os.path.exists(cookies) and os.path.getsize(cookies) > 100_000):
        _fail(f"profile clone cookies missing/too small: {cookies}")
    print(f"3. profile clone cookies ok ({os.path.getsize(cookies)} bytes)")

    # 4. V4 Flash text (reasoning model: generous budget required)
    t0 = time.time()
    out = _or_chat(TEXT_MODEL, "Reply with the single word READY.", 300)
    if "READY" not in out.upper():
        _fail(f"V4 Flash text smoke: expected READY, got {out!r}")
    print(f"4. {TEXT_MODEL} TEXT ok ({time.time()-t0:.1f}s) -> {out!r}")

    # 5. Kimi K2.6 text (reasoning model: needs generous tokens)
    t0 = time.time()
    out = _or_chat(VISION_MODEL, "Reply with the single word READY.", 400)
    if "READY" not in out.upper():
        _fail(f"Kimi text smoke: expected READY, got {out!r}")
    print(f"5. {VISION_MODEL} TEXT ok ({time.time()-t0:.1f}s) -> {out!r}")

    # 6. Kimi K2.6 vision against a real Chrome screenshot
    png = _screenshot_from_chrome()
    if len(png) < 5000:
        _fail(f"screenshot too small: {len(png)} bytes")
    b64 = base64.b64encode(png).decode("ascii")
    t0 = time.time()
    out = _or_chat(VISION_MODEL, [
        {"type": "text", "text": "In under 10 words, what is the main visible content on this page?"},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
    ], 400)
    if len(out) < 3:
        _fail(f"Kimi vision smoke: empty/short response {out!r}")
    print(f"6. {VISION_MODEL} VISION ok ({time.time()-t0:.1f}s, {len(png)}B png) -> {out!r}")

    # 7. Documented: V4 Flash has no vision on OpenRouter. Routing is
    #    text->V4Flash, vision->Kimi. This is recorded, not a failure.
    print("7. routing confirmed: TEXT=deepseek-v4-flash VISION=kimi-k2.6 "
          "(no DeepSeek V4 vision on OpenRouter, documented)")
    print("V4-0 PASS: all six checks green")


if __name__ == "__main__":
    test_v4_0_smoke()
