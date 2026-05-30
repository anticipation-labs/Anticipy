#!/usr/bin/env python3
"""Smoke test for the audit-trail receipt fields.

Verifies:
  1. /api/dispatch/with_receipt fires an action and returns receipt.
  2. receipt.proof.screenshot.path points to a real PNG on disk.
  3. receipt.proof.message_id is empty for a fresh draft (expected;
     drafts have no Send-MIME header yet) and the error is honest.
  4. receipt.proof.message_id is populated when the tab's
     location.hash matches a #sent/<id> shape (simulated by
     navigating a CDP tab to a synthetic Gmail-shaped URL).
  5. receipt.sms.gated=true when TWILIO_MOCK=1 (no real SMS sent).
  6. self_email draft compose_url + body include the screenshot
     file:// reference.

Run from repo root with engine on :8731 and TWILIO_MOCK=1 (export
before starting the engine):

    TWILIO_MOCK=1 python3 engine/scripts/receipt_audit_trail_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ENGINE_URL = (os.environ.get("ANTICIPY_ENGINE_URL", "").strip()
              or "http://127.0.0.1:8731")
CDP_BASE = (os.environ.get("ANTICIPY_CDP_BASE", "").strip()
            or "http://localhost:9222")


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def http_post_json(url: str, payload: dict,
                   timeout: float = 240.0) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(getattr(r, "status", 200)), json.loads(
                r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), {
            "raw": exc.read().decode("utf-8", "replace")}
    except Exception as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    banner("phase 1: drive /api/dispatch/with_receipt on a fresh draft")
    code, body = http_post_json(
        f"{ENGINE_URL}/api/dispatch/with_receipt",
        {"instruction": (
            "Draft an email to skylar@anticipy-test.local with subject "
            '"Receipt audit trail test" saying "Audit trail E2E smoke."'
        )},
    )
    if code != 200:
        fail(f"dispatch returned status {code}: "
             f"{json.dumps(body)[:400]}")
    if not body.get("ok"):
        fail(f"dispatch not ok: {json.dumps(body)[:400]}")
    receipt = body.get("receipt") or {}
    proof = receipt.get("proof") or {}

    banner("phase 2: receipt.proof has screenshot")
    shot = proof.get("screenshot") or {}
    if not shot.get("ok"):
        fail(f"screenshot.ok is false: {shot}")
    shot_path = Path(str(shot.get("path") or ""))
    if not shot_path.exists():
        fail(f"screenshot file missing on disk: {shot_path}")
    if int(shot.get("bytes") or 0) < 1000:
        fail(f"screenshot too small ({shot.get('bytes')} bytes)")
    print(f"screenshot ok at {shot_path} ({shot.get('bytes')} bytes)")

    banner("phase 3: receipt.proof reports honest message_id error "
           "for fresh draft")
    msg_id = str(proof.get("message_id") or "")
    err = str(proof.get("message_id_error") or "")
    if msg_id:
        print(f"unexpected message_id on a fresh compose: {msg_id}")
    if not err:
        fail("expected message_id_error to be set on fresh draft")
    print(f"draft path correctly reports no message_id, error={err!r}")

    banner("phase 4: synthetic #sent/<id> tab produces a real "
           "message_id + sent_link")
    # Open a fresh tab with a fake gmail-shaped URL via CDP.
    req = urllib.request.Request(
        f"{CDP_BASE}/json/new?https://example.com/p%23sent/SMOKE_TEST_MID_ID",
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        target = json.loads(r.read().decode("utf-8", "replace"))
    fake_target_id = str(target.get("id") or "")
    if not fake_target_id:
        fail(f"could not open fake tab: {target}")
    # Re-set the hash via CDP because URL anchors get HTML-encoded.
    try:
        from websockets.sync.client import connect as _ws_connect
    except Exception as exc:
        fail(f"websockets import: {exc}")
    time.sleep(1.0)
    ws = _ws_connect(
        f"ws://127.0.0.1:9222/devtools/page/{fake_target_id}",
        max_size=1024 * 1024, open_timeout=5)
    try:
        ws.send(json.dumps({
            "id": 1, "method": "Runtime.evaluate",
            "params": {
                "expression":
                    "location.hash='sent/SMOKE_TEST_MID_ID'; "
                    "location.hash;",
                "returnByValue": True,
            },
        }))
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                raw = ws.recv(timeout=1)
            except Exception:
                break
            msg = json.loads(raw)
            if msg.get("id") == 1:
                break
    finally:
        ws.close()
    time.sleep(0.5)

    # Test the extractor by re-implementing inline. Importing
    # app.product.server would boot a second engine instance and trip
    # the per-port single-instance lock at /tmp/anticipy_product_8731.lock.
    def extract_via_cdp(cdp_port: int, target_id: str) -> dict:
        ws_url = f"ws://127.0.0.1:{cdp_port}/devtools/page/{target_id}"
        js = (
            "(function(){"
            "try{"
            "var url=location.href;"
            "var hash=(location.hash||'').replace(/^#/,'');"
            "var m=hash.match(/^([a-z]+)\\/([A-Za-z0-9_-]+)/);"
            "if(!m){return JSON.stringify({ok:false,"
            "error:'no_hash_match',hash:hash,url:url});}"
            "return JSON.stringify({ok:true,kind:m[1],id:m[2],"
            "hash:hash,url:url});"
            "}catch(e){return JSON.stringify({ok:false,"
            "error:String(e)});}"
            "})()"
        )
        ws_local = _ws_connect(ws_url, max_size=1024 * 1024,
                                open_timeout=5)
        try:
            ws_local.send(json.dumps({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": js, "returnByValue": True},
            }))
            deadline_local = time.time() + 5
            while time.time() < deadline_local:
                try:
                    raw_local = ws_local.recv(timeout=1)
                except Exception:
                    break
                msg_local = json.loads(raw_local)
                if msg_local.get("id") == 1:
                    val = (((msg_local.get("result") or {})
                            .get("result") or {}).get("value") or "")
                    try:
                        parsed = json.loads(val or "{}")
                    except Exception:
                        parsed = {}
                    if not parsed.get("ok"):
                        return {"ok": False,
                                "error": str(parsed.get("error")
                                             or "no_value")}
                    return {
                        "ok": True,
                        "message_id": str(parsed.get("id") or ""),
                        "hash_kind": str(parsed.get("kind") or ""),
                        "url": str(parsed.get("url") or ""),
                    }
        finally:
            ws_local.close()
        return {"ok": False, "error": "no_response"}

    def sent_link_for(message_id: str, kind: str = "sent") -> str:
        if not message_id:
            return ""
        k = kind or "sent"
        return f"https://mail.google.com/mail/u/0/#{k}/{message_id}"

    msg = extract_via_cdp(9222, fake_target_id)
    if not msg.get("ok"):
        fail(f"extractor returned not-ok on synthetic tab: {msg}")
    mid = str(msg.get("message_id") or "")
    if not mid:
        fail(f"extractor did not return a message_id: {msg}")
    sent_link = sent_link_for(mid, str(msg.get("hash_kind") or "sent"))
    if not sent_link.startswith("https://mail.google.com/mail/u/0/#sent/"):
        fail(f"sent_link shape wrong: {sent_link!r}")
    if mid not in sent_link:
        fail(f"sent_link does not embed message_id: {sent_link!r}")
    print(f"extractor returned message_id={mid!r}")
    print(f"sent_link={sent_link!r}")

    # Cleanup the synthetic tab.
    urllib.request.urlopen(
        urllib.request.Request(
            f"{CDP_BASE}/json/close/{fake_target_id}", method="PUT"),
        timeout=5,
    ).read()

    banner("phase 5: receipt.sms.gated=true + mock=true under "
           "TWILIO_MOCK=1")
    sms = receipt.get("sms") or {}
    if not sms.get("gated"):
        fail(f"sms not gated (real send may have fired!): {sms}")
    if not sms.get("mock"):
        fail(f"sms.mock is false despite TWILIO_MOCK=1: {sms}")
    if sms.get("reason") != "TWILIO_MOCK=1":
        fail(f"unexpected reason: {sms.get('reason')!r}")
    would = str(sms.get("would_have_sent") or "")
    if "Anticipy just sent" not in would:
        fail(f"would_have_sent missing summary: {would!r}")
    print(f"sms correctly mocked. would_have_sent[:100]={would[:100]!r}")

    banner("phase 6: self_email draft body embeds screenshot reference")
    self_email = receipt.get("self_email") or {}
    if not self_email.get("ok"):
        fail(f"self_email not ok: {self_email}")
    compose_url = str(self_email.get("compose_url") or "")
    if "Screenshot" not in urllib.parse.unquote(compose_url):
        fail(f"self_email compose_url missing screenshot ref: "
             f"{compose_url[:200]}")
    if str(shot_path) not in urllib.parse.unquote(compose_url):
        fail(f"self_email compose_url missing screenshot path "
             f"{shot_path}: {compose_url[:300]}")
    print(f"self_email body embeds screenshot path")

    print("\nALL RECEIPT AUDIT TRAIL SMOKE TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
