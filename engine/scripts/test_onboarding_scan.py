"""Slice 1 (engine side): a logged-in-Chrome connection scan becomes the per-person mesh.

Proves the discover->mesh bridge with NO Chrome and NO network: a simulated scrape payload
(what the extension's discover_connections intent will report) maps to OwnerOnboardingIn and
flows through the EXISTING build_onboarding_plan, so each discovered service becomes a profile
card + a "Connect X" open-loop with the right route — and a service Anticipy already holds a
vault token for is marked connected (no Connect loop).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_onboarding_scan.py
"""
from anticipy_engine.onboarding.connection_scan import scan_to_onboarding
from anticipy_engine.owner_onboarding import build_onboarding_plan


def main():
    discovered = [
        {"service": "Gmail", "logged_in": True, "identifier": "omar@gmail.com",
         "url": "https://mail.google.com"},
        {"service": "Google Calendar", "logged_in": True},
        {"service": "Cosmolex", "logged_in": True, "url": "https://app.cosmolex.com"},  # niche CRM
        {"service": "Gmail", "logged_in": True},       # duplicate -> deduped by canonical key
        {"service": "Reddit", "logged_in": False},     # logged out -> skipped (nothing to connect)
        {"service": "", "logged_in": True},            # empty -> skipped
        "not-a-dict",                                  # junk -> skipped
    ]

    onb = scan_to_onboarding(discovered)
    names = [c.name for c in onb.connections]
    assert names == ["Gmail", "Google Calendar", "Cosmolex"], names
    routes = {c.name: c.route for c in onb.connections}
    assert routes["Gmail"] == "api" and routes["Google Calendar"] == "api", routes
    assert routes["Cosmolex"] == "browser", routes        # no API connector -> browser arm
    assert all(c.status == "needs_auth" for c in onb.connections), onb.connections
    assert onb.source == "chrome_scrape"

    # the EXISTING mesh builder turns each discovered (un-connected) service into a Connect loop
    plan = build_onboarding_plan(onb)
    assert set(plan.missing_connections) == {"Gmail", "Google Calendar", "Cosmolex"}, plan.missing_connections
    open_loops = [m for m in plan.memories if m.drawer == "open_loops"]
    assert len(open_loops) == 3 and all(m.text.startswith("Connect ") for m in open_loops), open_loops

    # a vault token already held -> that service is CONNECTED, no Connect loop generated
    onb2 = scan_to_onboarding(discovered, vault_has=lambda k: k == "gmail")
    gmail = [c for c in onb2.connections if c.name == "Gmail"][0]
    assert gmail.status == "connected", gmail.status
    plan2 = build_onboarding_plan(onb2)
    assert "Gmail" not in plan2.missing_connections, plan2.missing_connections
    assert set(plan2.missing_connections) == {"Google Calendar", "Cosmolex"}, plan2.missing_connections

    # robustness: a vault_has that RAISES must not crash the scan (degrades to needs_auth)
    def boom(_k):
        raise RuntimeError("vault down")
    onb3 = scan_to_onboarding([{"service": "Gmail", "logged_in": True}], vault_has=boom)
    assert onb3.connections[0].status == "needs_auth", onb3.connections[0].status

    # robustness: non-string identifier/url are dropped, never stringified into the mesh
    onb4 = scan_to_onboarding([{"service": "Gmail", "logged_in": True, "identifier": {"x": 1}, "url": 123}])
    assert onb4.connections[0].identifier == "", onb4.connections[0].identifier
    assert "123" not in onb4.connections[0].notes, onb4.connections[0].notes

    print("PASS: Chrome connection-scan -> onboarding mesh")
    print("  discover logged-in services -> Connect open-loops (api/browser route); held token -> connected")


if __name__ == "__main__":
    main()
