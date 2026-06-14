"""Endpoint test: POST /onboarding/profile — make the profile builder USABLE.

The builder's assembly logic is unit-tested in test_onboarding_profile.py. This
test proves the HTTP surface the app talks to:

  - POST /onboarding/profile {name, sources:[urls]} returns a real STRUCTURED
    profile (name/role/org/location + key_facts each carrying source + trust +
    needs_cross_check), exercised through an injected fake browser reader so no
    live browser is touched in CI (the real arm is the production default).
  - it is OWNER-GATED: with ANTICIPY_OWNER_API_TOKEN set, an anonymous POST is
    401; the same POST with the token succeeds.
  - it DEGRADES HONESTLY: with NO reader injected and NO browser bridge present,
    every read fails -> sources become blockers, NO facts are invented, and the
    response carries browser_available=false so the caller never mistakes an
    empty honestly-degraded profile for a real one.
  - input validation: empty name / no public http source -> 422.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_onboarding_profile_endpoint.py
"""
import os
import tempfile
from dataclasses import dataclass
from typing import Optional

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy-onb-ep-")
# Make the browser bridge probe deterministically UNAVAILABLE so the honest-degrade
# branch is real (point the bridge python at a path that does not exist).
os.environ["ANTICIPY_BROWSERUSE_PYTHON"] = "/nonexistent/anticipy/bridge/python"

from fastapi.testclient import TestClient  # noqa: E402

from anticipy_engine.main import app  # noqa: E402


WIKI = "https://en.wikipedia.org/wiki/Example_Person"
COMPANY = "https://acme.example/about"


@dataclass
class FakeResult:
    success: bool
    result: Optional[str]
    url: Optional[str]
    steps: int = 1
    structured: bool = False
    needs_cross_check: bool = True
    trust: str = "coarse"
    error: Optional[str] = None


def fake_reader(task, *, url=None, structured=False, max_steps=10, timeout_s=180):
    """A scripted, NETWORK-FREE browse_read: realistic answers for a bio page."""
    t = task.lower()
    if not structured:
        if url == WIKI:
            return FakeResult(
                success=True,
                result="Example Person is an engineer and the founder of Acme Corp, based in Austin, Texas.",
                url=url,
                trust="coarse",
            )
        return FakeResult(success=True, result="A public overview.", url=url, trust="coarse")
    if "role" in t:
        return FakeResult(success=True, result="Founder and engineer", url=url, structured=True, trust="fine")
    if "organization" in t or "company" in t:
        return FakeResult(success=True, result="Acme Corp", url=url, structured=True, trust="fine")
    if "location" in t:
        return FakeResult(success=True, result="Austin, Texas", url=url, structured=True, trust="fine")
    return FakeResult(success=False, result=None, url=url, error="unscripted")


def main():
    fails = []
    with TestClient(app) as client:
        # ---- (1) injected fake reader -> a REAL structured profile over HTTP ----
        app.state.profile_browse_reader = fake_reader
        try:
            res = client.post("/onboarding/profile", json={"name": "Example Person", "sources": [WIKI]})
        finally:
            # leave it set for the gating test below; cleared at the very end
            pass
        if res.status_code != 200:
            fails.append(f"(1) expected 200, got {res.status_code}: {res.text}")
        else:
            prof = res.json()
            if prof.get("name") != "Example Person":
                fails.append(f"(1) name not echoed: {prof.get('name')}")
            if prof.get("role") != "Founder and engineer":
                fails.append(f"(1) role not hoisted: {prof.get('role')}")
            if prof.get("org") != "Acme Corp":
                fails.append(f"(1) org not hoisted: {prof.get('org')}")
            if prof.get("location") != "Austin, Texas":
                fails.append(f"(1) location not hoisted: {prof.get('location')}")
            facts = prof.get("key_facts") or []
            if not facts:
                fails.append("(1) expected key_facts")
            for f in facts:
                if not (f.get("source_url") and f.get("field") and "needs_cross_check" in f and f.get("trust")):
                    fails.append(f"(1) fact missing provenance/trust: {f}")
            # trust grading carried through the HTTP boundary
            coarse = [f for f in facts if f.get("trust") == "coarse"]
            fine = [f for f in facts if f.get("trust") == "fine"]
            if not (coarse and fine):
                fails.append(f"(1) expected both coarse and fine facts: {facts}")
            if any(f.get("needs_cross_check") for f in coarse):
                fails.append("(1) coarse facts must not need cross-check")
            if not all(f.get("needs_cross_check") for f in fine):
                fails.append("(1) fine facts must need cross-check")
            if prof.get("browser_available") is not True:
                fails.append(f"(1) injected reader should count as browser_available: {prof.get('browser_available')}")
            if prof.get("summary", {}).get("needs_cross_check") != len(fine):
                fails.append(f"(1) summary needs_cross_check mismatch: {prof.get('summary')}")

        # ---- (2) input validation: empty name and no public source -> 422 ----
        r_noname = client.post("/onboarding/profile", json={"name": "  ", "sources": [WIKI]})
        if r_noname.status_code != 422:
            fails.append(f"(2) empty name should 422: {r_noname.status_code}")
        r_nosrc = client.post("/onboarding/profile", json={"name": "X", "sources": ["ftp://nope", "not-a-url"]})
        if r_nosrc.status_code != 422:
            fails.append(f"(2) no public http source should 422: {r_nosrc.status_code}")

        # ---- (3) HONEST DEGRADE: no reader + no browser bridge -> blockers, no fakes ----
        app.state.profile_browse_reader = None
        deg = client.post("/onboarding/profile", json={"name": "Ghost", "sources": [WIKI]})
        if deg.status_code != 200:
            fails.append(f"(3) degrade path should still 200: {deg.status_code}: {deg.text}")
        else:
            dp = deg.json()
            if dp.get("browser_available") is not False:
                fails.append(f"(3) no browser -> browser_available must be false: {dp.get('browser_available')}")
            if dp.get("key_facts"):
                fails.append(f"(3) no facts may be invented when reads fail: {dp.get('key_facts')}")
            if not dp.get("blockers"):
                fails.append("(3) a failed read must surface a blocker, not a fake")
            if dp.get("role") or dp.get("org") or dp.get("location"):
                fails.append("(3) top-level fields must stay empty on honest degrade")

        # ---- (4) OWNER GATE: token set -> anonymous 401, with token -> 200 ----
        app.state.profile_browse_reader = fake_reader
        old = os.environ.get("ANTICIPY_OWNER_API_TOKEN")
        token = "owner-onb-token-98765"
        os.environ["ANTICIPY_OWNER_API_TOKEN"] = token
        try:
            anon = client.post("/onboarding/profile", json={"name": "Example Person", "sources": [WIKI]})
            if anon.status_code != 401:
                fails.append(f"(4) anonymous POST must be 401 when token set: {anon.status_code}")
            ok = client.post(
                "/onboarding/profile",
                json={"name": "Example Person", "sources": [WIKI]},
                headers={"x-anticipy-owner-token": token},
            )
            if ok.status_code != 200:
                fails.append(f"(4) tokened POST must be 200: {ok.status_code}: {ok.text}")
        finally:
            if old is None:
                os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
            else:
                os.environ["ANTICIPY_OWNER_API_TOKEN"] = old
            app.state.profile_browse_reader = None

    print("==== ONBOARDING /onboarding/profile (endpoint) ====")
    print("  (1) injected reader -> real structured profile over HTTP (facts+source+trust+needs_cross_check)")
    print("  (2) empty name / no public source -> 422")
    print("  (3) no browser bridge + no reader -> blockers, NO invented facts, browser_available=false")
    print("  (4) owner-gated: anonymous 401 / tokened 200 when ANTICIPY_OWNER_API_TOKEN set")
    if fails:
        print("==== FAIL ====")
        for f in fails:
            print("   -", f)
        raise SystemExit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    main()
