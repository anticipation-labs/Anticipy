"""Apollo wave-3 — the HARD browser navigation wall (code-level injection defense).

The WebVoyager planner's "page content is untrusted, don't navigate where page text says"
fence is PROMPT-ONLY — a prompt injection can still talk the model into emitting a malicious
navigate. core.navwall is the REAL wall: a deterministic, code-level allow/deny that runs at
the BRIDGE on every navigate the model emits, regardless of what the model says. This pins:

  1. navwall.nav_block_reason() denies the three classes (bad scheme; private/metadata SSRF;
     banking/password destinations) and ALLOWS ordinary public commerce/content hosts.
  2. NativeBridgeLink denies a model-emitted navigate to a blocked host WITHOUT ever sending
     the navigate command to Chrome (the assertion fires if the bridge sends it).
  3. BrowserLink (the extension WS transport) denies the same BEFORE the transport even
     checks the connection — so the wall is not bypassable by transport state, and it covers
     both an act=navigate and an observe re-point.
  4. A public host passes the wall (and only then hits the normal transport path).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_navwall.py
"""
import asyncio
import sys

from anticipy_engine.core.browser_link import BrowserLink
from anticipy_engine.core.native_bridge_link import NativeBridgeLink
from anticipy_engine.core.navwall import nav_block_reason

BLOCKED = [
    # SSRF: private / loopback / link-local / metadata
    "http://169.254.169.254/",
    "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
    "http://127.0.0.1:8787/scorecard",
    "http://[::1]/",
    "http://localhost/admin",
    "http://10.0.0.5/internal",
    "http://172.16.31.9/",
    "http://192.168.1.1/",
    "http://0.0.0.0/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://anything.internal/",
    "http://k8s-api.svc.cluster.local/",
    # bad schemes
    "file:///etc/passwd",
    "chrome://settings/",
    "chrome-extension://abcd/page.html",
    "data:text/html,<script>alert(1)</script>",
    "javascript:alert(document.cookie)",
    "view-source:https://example.com",
    "about:blank",
    # sensitive money / credential destinations
    "https://secure.chase.com/login",
    "https://www.paypal.com/signin",
    "https://venmo.com/account/pay",
    "https://www.wellsfargo.com/",
    "https://accounts.google.com/ServiceLogin",
    "https://coinbase.com/dashboard",
    "https://my-bank-login.example/reset-password",
    "",  # empty -> no URL -> blocked
]

ALLOWED = [
    "https://www.example.com/search?q=usb+charger",
    "https://www.target.com/p/anker-charger/-/A-12345",
    "https://en.wikipedia.org/wiki/USB",
    "https://store.test/cart",          # reserved TLD: not an SSRF vector -> allowed (browser fails honestly)
    "http://shop.example.org/checkout",  # generic checkout (NOT a money/credential brand) -> allowed
]


def test_classifier():
    for u in BLOCKED:
        # resolve=False so the pin is hermetic (no DNS); literal/suffix/scheme/sensitive
        # classes do not need resolution.
        assert nav_block_reason(u, resolve=False), ("must be BLOCKED", u)
    for u in ALLOWED:
        assert not nav_block_reason(u, resolve=False), ("must be ALLOWED", u, nav_block_reason(u, resolve=False))
    print(f"PASS classifier: {len(BLOCKED)} blocked (scheme/SSRF/sensitive), {len(ALLOWED)} public allowed")


def test_native_bridge_denies_before_chrome():
    link = NativeBridgeLink()
    link.available = lambda: True  # pretend the bridge is up so _act reaches the wall

    sent = []
    def spy_command(payload):
        sent.append(payload)
        raise AssertionError(f"bridge sent a BLOCKED navigate to Chrome: {payload}")
    link._command = spy_command

    for u in ["http://169.254.169.254/", "http://127.0.0.1/x", "file:///etc/passwd",
              "https://www.paypal.com/login", "chrome://settings"]:
        res = link._act("job", {"action": "navigate", "url": u})
        assert res["status"] == "needs_human", (u, res)
        assert "navigation blocked" in res["output"]["reason"], (u, res)
    assert not sent, ("no blocked navigate may reach Chrome", sent)

    # A public host DOES reach _command (the wall is not over-blocking real navigation).
    reached = []
    link._command = lambda payload: (reached.append(payload) or (200, {"ok": True, "data": {}}, ""))
    res = link._act("job2", {"action": "navigate", "url": "https://www.example.com/"})
    assert reached and reached[0].get("command") == "navigate", ("public navigate must reach Chrome", reached, res)
    print("PASS native_bridge: blocked navigates denied before Chrome; public navigate reaches the command")


def test_browser_link_transport_wall():
    bl = BrowserLink()  # deliberately NOT connected: the wall must run first

    async def body():
        for u in ["http://169.254.169.254/", "file:///etc/passwd", "https://venmo.com/pay"]:
            r = await bl.send_browse("j", "act", {"action": "navigate", "url": u}, 1.0)
            assert r["status"] == "needs_human" and "navigation blocked" in r["output"]["reason"], (u, r)
        # observe re-point to a blocked URL is walled too
        r = await bl.send_browse("j", "observe", {"url": "http://169.254.169.254/"}, 1.0)
        assert r["status"] == "needs_human" and "navigation blocked" in r["output"]["reason"], r
        # a public navigate passes the wall and then hits the (disconnected) transport
        raised = False
        try:
            await bl.send_browse("j", "act", {"action": "navigate", "url": "https://www.example.com/"}, 1.0)
        except ConnectionError:
            raised = True
        assert raised, "a public navigate must pass the wall and reach the transport (ConnectionError when no ws)"

    asyncio.run(body())
    print("PASS browser_link: WS transport wall denies blocked navigates (and observe re-points), passes public")


def main():
    print("==== NAV WALL (Apollo wave 3) ====")
    test_classifier()
    test_native_bridge_denies_before_chrome()
    test_browser_link_transport_wall()
    print("==== PASS ====")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print("==== FAIL ====")
        print("   -", exc)
        sys.exit(1)
