"""Apollo wave-2 endpoint hardening — regression pins for main.py.

A second adversarial audit found three reachable holes on the HTTP/WS surface.
This test pins all three so a future change can't silently reopen them. It boots
the real ASGI app through a TestClient (free stub brain + mock hands; no Twilio,
no live browser, no model spend) and asserts behavior at the boundary.

  (1) WS ROBUSTNESS — /cr and /ws/extension must survive a malformed / non-object
      frame mid-connection instead of crashing the loop. A bad frame is skipped
      (mirrors the existing "unknown frame: stay silent" bias) and the NEXT good
      frame is still answered. For /cr that means a malformed frame, a bare-string
      frame, and an array frame are all ignored, then a real prompt streams the
      brain's reply. For /ws/extension a malformed/non-object frame is ignored and
      a following {"type":"ping"} still gets its pong.

  (2) REQUEST-SIZE CAP — an oversized POST body is rejected with 413 BEFORE the
      heavy synchronous triage->gate->act work runs; a normal body still flows and
      is correctly read by the handler (the cap middleware caches + replays the
      body, it doesn't eat it). The on-disk upload lane stays exempt.

  (3) SSRF — the owner-gated onboarding endpoints must reject a source URL whose
      host points at a NON-PUBLIC address: cloud-metadata (169.254.169.254),
      loopback (127.0.0.1, ::1, localhost), and private (10/172.16/192.168) ranges
      all 422. A reserved/NXDOMAIN public name (acme.example) is NOT an SSRF vector
      and is allowed through to the read-only browser arm (honest degrade), so the
      gate is about WHERE a host points, not whether it resolves today.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_endpoint_hardening.py
"""
import os
import tempfile

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_CR_BRAIN", "decider")  # this test asserts the decider verdict brain; the warm OnboardingCallBrain is the /cr default
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy-harden-")
# Force the browser bridge probe UNAVAILABLE so the onboarding endpoints take the
# honest-degrade path (no live browser is touched in CI).
os.environ["ANTICIPY_BROWSERUSE_PYTHON"] = "/nonexistent/anticipy/bridge/python"
# A small, explicit body cap so the oversized-body pin is cheap and deterministic.
os.environ["ANTICIPY_MAX_REQUEST_BYTES"] = "4096"

from fastapi.testclient import TestClient  # noqa: E402

from anticipy_engine.main import app  # noqa: E402


def _drain_reply(ws):
    """Read streamed {type:'text', token} frames until last:true; return the sentence."""
    parts = []
    while True:
        f = ws.receive_json()
        assert f["type"] == "text", f
        parts.append(f["token"])
        if f.get("last"):
            break
    return "".join(parts)


def test_cr_survives_malformed_frames(client):
    """A malformed JSON frame, a bare-string frame, and an array frame are each skipped
    mid-call; the connection stays open and the next REAL prompt still streams a reply."""
    with client.websocket_connect("/cr") as ws:
        ws.send_text("this is not json {{{")     # JSONDecodeError -> skipped
        ws.send_json("a bare string frame")        # valid JSON, non-object -> skipped
        ws.send_json(["array", "frame"])           # valid JSON, non-object -> skipped
        ws.send_json({"type": "prompt", "voicePrompt": "remind me to call the dentist tomorrow"})
        reply = _drain_reply(ws)
        assert "take care of that" in reply, ("the call must survive bad frames and still ACT", reply)
    print("PASS cr_malformed: /cr skips malformed/non-object frames and still answers the next prompt")


def test_extension_survives_malformed_frames(client):
    """/ws/extension skips a malformed/non-object frame and still answers a later ping.

    The link is owner-token gated by core.browser_link; in the deterministic suite the
    link token is readable, so we present it on the handshake exactly like the real
    extension does."""
    import anticipy_engine.main as m

    token = m.core.browser_link.token
    with client.websocket_connect(f"/ws/extension?token={token}") as ws:
        ws.send_text("garbage not json ]]]")       # JSONDecodeError -> skipped, link alive
        ws.send_json([1, 2, 3])                      # non-object -> skipped, link alive
        ws.send_json({"type": "ping"})              # a good frame still gets its pong
        pong = ws.receive_json()
        assert pong.get("type") == "pong", ("extension link must survive bad frames", pong)
    print("PASS extension_malformed: /ws/extension skips bad frames and still pongs a later ping")


def test_oversized_body_rejected(client):
    """A POST /event body over the cap is rejected with 413; a normal body still flows
    and is read correctly by the handler (the size middleware caches + replays it)."""
    # Normal small body: handled (decision shape returned, body reached the handler).
    ok = client.post("/event", json={"text": "remind me to grab milk", "source": "app", "meta": {}})
    assert ok.status_code == 200, ("a normal body must still be processed", ok.status_code, ok.text)
    assert "decision" in ok.json(), ("the handler must have read the cached body", ok.json())

    # Oversized body: rejected with 413 before any heavy work.
    big = "x" * 20000  # well over the 4096-byte cap set above
    too_big = client.post("/event", json={"text": big, "source": "app", "meta": {}})
    assert too_big.status_code == 413, ("an oversized body must be 413", too_big.status_code)
    body = too_big.json()
    assert body.get("error") == "payload_too_large", body
    assert body.get("limit") == 4096, ("the 413 must report the active cap", body)
    print("PASS oversized_body: /event over the cap -> 413 (limit reported); a normal body still flows")


def test_ssrf_rejects_nonpublic_sources(client):
    """The onboarding endpoints reject a source URL whose host points at a non-public
    address (metadata/loopback/localhost/private) and allow a reserved public name."""
    # No injected reader -> honest-degrade path for the allowed cases.
    app.state.profile_browse_reader = None

    blocked = [
        "http://169.254.169.254/",          # cloud metadata (link-local)
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/",                 # IPv4 loopback
        "http://[::1]/",                     # IPv6 loopback
        "http://localhost/admin",            # resolves to loopback
        "http://10.0.0.5/internal",          # private 10/8
        "http://172.16.0.1/",                # private 172.16/12
        "http://192.168.1.1/",               # private 192.168/16
        "http://0.0.0.0/",                   # unspecified
    ]
    for url in blocked:
        for path in ("/onboarding/profile", "/onboarding/clarify"):
            r = client.post(path, json={"name": "X", "sources": [url]})
            assert r.status_code == 422, (f"SSRF: {path} {url} must be 422", r.status_code, r.text)

    # A bad source ANYWHERE in the list still rejects the whole request.
    mixed = client.post(
        "/onboarding/profile",
        json={"name": "X", "sources": ["https://acme.example/about", "http://169.254.169.254/"]},
    )
    assert mixed.status_code == 422, ("one private source in a list must reject all", mixed.status_code)

    # A reserved/NXDOMAIN public name is NOT an SSRF target: it passes normalization and
    # the endpoint degrades honestly (200) rather than 422 — nothing internal is reachable.
    allowed = client.post("/onboarding/profile", json={"name": "X", "sources": ["https://acme.example/about"]})
    assert allowed.status_code == 200, ("a reserved public name must reach honest degrade, not 422", allowed.status_code, allowed.text)
    ap = allowed.json()
    assert ap.get("browser_available") is False, ("no browser -> honest degrade", ap.get("browser_available"))
    assert not ap.get("key_facts"), ("honest degrade invents no facts", ap.get("key_facts"))
    print("PASS ssrf: metadata/loopback/localhost/private hosts -> 422; reserved public name -> honest 200")


def main():
    print("==== ENDPOINT HARDENING (Apollo wave 2) ====")
    with TestClient(app) as client:
        # WS tests share ONE TestClient (the engine `core` is a module singleton; a second
        # client would rebind its bus to a new event loop).
        test_cr_survives_malformed_frames(client)
        test_extension_survives_malformed_frames(client)
        test_oversized_body_rejected(client)
        test_ssrf_rejects_nonpublic_sources(client)
    print("==== PASS ====")


if __name__ == "__main__":
    main()
