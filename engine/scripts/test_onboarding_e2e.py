"""Onboarding END-TO-END proof — drive the FULL onboarding flow through the real engine, assert every step.

The deterministic spine (no model, no browser): permissions gate -> /owner/onboard (typed mesh) ->
/onboard/discover -> /onboard/complete -> /onboard/status (cwd-stable). The model+browser loop
(/onboard/loop -> dossier) is enrichment ON TOP, proven hermetically via an injected gateway + fake scrape.

Honesty law (mirrors owner_test_run.py): --selftest first runs the happy path (every check must be GREEN),
then a planted-failure battery — for each break it corrupts ONE input and asserts the matching NAMED check
flips to False. A harness that cannot catch a planted onboarding failure must never certify onboarding.

  test_onboarding_e2e.py            # happy path -> PASS/FAIL
  test_onboarding_e2e.py --selftest # happy path + planted-failure battery
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Env MUST be set before importing anticipy_engine.main (it builds a default core at import time).
_TMP0 = tempfile.mkdtemp(prefix="anticipy-onb-import-")
os.environ["ANTICIPY_DATA_DIR"] = _TMP0
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_HANDS_MODE"] = "mock"
os.environ["ANTICIPY_CHANNELS_MODE"] = "mock"
os.environ["ANTICIPY_NATIVE_BRIDGE_FALLBACK"] = "0"
os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)   # keep routes unauthenticated (default core)
os.environ.pop("OPENROUTER_API_KEY", None)         # no real network model call is possible

from fastapi.testclient import TestClient  # noqa: E402
from anticipy_engine import main as engmain  # noqa: E402
from anticipy_engine.core import registry  # noqa: E402
from anticipy_engine.core.control_core import ControlCore, _base  # noqa: E402
from anticipy_engine.core.gateway import PROVIDER_OPENROUTER  # noqa: E402
from anticipy_engine.onboarding import loop as onb_loop  # noqa: E402
from anticipy_engine.onboarding import owner_scrape as onb_scrape  # noqa: E402

CLIENT = TestClient(engmain.app)   # no context manager -> no lifespan -> no schedulers/bus (onboarding needs none)

# ---- fixtures -------------------------------------------------------------------------------------
OWNER_PAYLOAD = {
    "owner_name": "Dana Rivers", "timezone": "America/Los_Angeles", "email": "dana@example.com",
    "people": [
        {"name": "Jordan", "relationship": "cofounder"},
        {"name": "Priya", "relationship": "investor"},
    ],
    "connections": [
        {"name": "Gmail", "status": "needs_auth", "route": "api"},
        {"name": "Target", "status": "needs_auth", "route": "browser"},
    ],
    "stores": [{"name": "Costco", "url": "costco.com"}],
    "source": "first_run",
}
DISCOVERED = [
    {"service": "Gmail", "logged_in": True},
    {"service": "Google Calendar", "logged_in": True},
    {"service": "Cosmolex", "logged_in": True},
    {"service": "Reddit", "logged_in": False},   # logged-out -> dropped
]
# The inner dossier JSON the (faked) smart model returns. write_dossier_to_memory ->
# identity(1)+work(1)+people(2)+family(1)=5 profile ; tools(2)+sites(1)=3 derived.
CANNED_DOSSIER = {
    "identity": {"name": "Dana Rivers", "role": "Founder", "location": "SF", "email": "dana@example.com"},
    "work": "Runs a small legal-tech startup.",
    "people": [
        {"name": "Jordan", "relationship": "cofounder", "why_they_matter": "builds the product"},
        {"name": "Priya", "relationship": "investor", "why_they_matter": "lead seed investor"},
    ],
    "family": ["Jordan"],
    "tools": ["Gmail", "Cosmolex"],
    "act_on_sites": ["target.com"],
    "gaps": [],
    "confidence": 0.9,
}


class _FakeScrape:
    """A stand-in for the CDP browser scrape — no Chrome. Counts calls (STEP 1 asserts 0 pre-consent)."""
    def __init__(self, mode="ok"):
        self.calls = 0
        self.mode = mode   # "ok" -> readable; "needs_login" -> walled

    def __call__(self, cdp_url=None, surfaces=None, max_chars=0, scroll_steps=0, dwell=0, settle=0):
        self.calls += 1
        if self.mode == "needs_login":
            return {"ok": True, "logged_in": [], "needs_login": ["gmail_inbox"],
                    "surfaces": [{"key": "gmail_inbox", "label": "Gmail", "status": "needs_login",
                                  "needs_login": True, "text": "", "chars": 0}]}
        return {"ok": True, "logged_in": ["gmail_inbox"], "needs_login": [],
                "surfaces": [{"key": "gmail_inbox", "label": "Gmail", "status": "ok",
                              "needs_login": False,
                              "text": "From: Priya — re: seed round. From: Jordan — product sync.", "chars": 60}]}


def _install_core_and_fakes(*, dossier, scrape_mode):
    """Fresh core at a fresh temp dir (clean state), wired with the fake scrape + fake gateway."""
    tmp = tempfile.mkdtemp(prefix="anticipy-onb-run-")
    os.environ["ANTICIPY_DATA_DIR"] = tmp
    core = ControlCore(data_dir=tmp)
    registry.register_default(core)
    # fake scrape on BOTH bind sites (loop imported it at module load; the route imports at call time)
    fs = _FakeScrape(mode=scrape_mode)
    onb_loop.scrape_owner = fs
    onb_scrape.scrape_owner = fs
    # fake gateway: provider flips dossier.py into the synthesis branch; think() returns the canned JSON

    async def _think(*a, **k):
        return json.dumps(dossier)
    core.gateway.provider = PROVIDER_OPENROUTER
    core.gateway.think = _think
    return core, tmp, fs


# ---- the flow -------------------------------------------------------------------------------------
def run_flow(*, allow=True, dossier=None, do_complete=True, scrape_mode="ok"):
    """Drive the whole onboarding flow once; return (checks dict, core). Each named check is a load-bearing
    unit the selftest can flip by corrupting one input."""
    dossier = CANNED_DOSSIER if dossier is None else dossier
    core, tmp, fs = _install_core_and_fakes(dossier=dossier, scrape_mode=scrape_mode)
    chk: dict[str, bool] = {}

    # STEP 0 — fresh state
    st0 = CLIENT.get("/onboard/status").json()
    perm0 = CLIENT.get("/onboard/permissions").json()
    chk["fresh_state"] = (st0.get("onboarding_complete") is False
                          and len(perm0.get("services", [])) == 4
                          and perm0.get("any_allowed") is False)

    # STEP 1 — the consent gate fires before any read
    loop_pre = CLIENT.post("/onboard/loop", json={"max_layers": 4}).json()
    scrape_pre = CLIENT.post("/onboard/owner-scrape", json={}).json()
    chk["gate_blocks_before_consent"] = (
        loop_pre.get("ok") is False and "no service allowed" in (loop_pre.get("reason") or "")
        and "no service allowed" in (scrape_pre.get("reason") or "")
        and fs.calls == 0)

    # STEP 2 — record permissions (the gate) + persistence + invalid-service rejection
    if allow:
        for s in ("gmail", "calendar", "contacts", "linkedin"):
            CLIENT.post("/onboard/permissions", json={"service": s, "allowed": True})
    perm_after = CLIENT.get("/onboard/permissions").json()
    bad = CLIENT.post("/onboard/permissions", json={"service": "notreal", "allowed": True}).json()
    perm_file = Path(tmp) / "onboard_permissions.json"
    disk_ok = False
    if perm_file.exists():
        disk = json.loads(perm_file.read_text())
        disk_ok = (set(disk.keys()) == {"gmail", "calendar", "contacts", "linkedin"}) if allow else True
    chk["permissions_persisted"] = (
        (perm_after.get("any_allowed") is (True if allow else False))
        and len(bad.get("services", [])) == 4
        and not any(x["service"] == "notreal" for x in bad.get("services", []))
        and disk_ok)

    # STEP 3 — typed owner mesh (deterministic spine: no model, no browser)
    own = CLIENT.post("/owner/onboard", json=OWNER_PAYLOAD).json()
    disc = CLIENT.post("/onboard/discover", json={"discovered": DISCOVERED, "source": "chrome_scrape"}).json()
    prof_txt = [i.text for i in core.memory.profile.all()]
    loops = core.memory.open_loops.all()
    loop_txt = [l.text for l in loops]
    chk["spine_missing_connections"] = (own.get("missing_connections") == ["Gmail", "Target"]
                                        and all(w["fields"].get("source") == "first_run" for w in own.get("written", [])))
    chk["spine_profile_cards"] = (
        any(t.startswith("Owner identity:") for t in prof_txt)
        and any("Important person: Jordan" in t for t in prof_txt)
        and any("Important person: Priya" in t for t in prof_txt)
        and any("App connection: Gmail" in t for t in prof_txt)
        and any("Common store/account: Costco" in t for t in prof_txt))
    chk["spine_open_loops"] = (
        any("Connect Gmail" in t for t in loop_txt)
        and any("Connect Target" in t for t in loop_txt)
        and all((l.fields or {}).get("action") == "connect_account"
                for l in loops if "Connect " in (l.text or "")))
    chk["discover_connections"] = (
        disc.get("discovered_count") == 4
        and [c["name"] for c in disc.get("connections", [])] == ["Gmail", "Google Calendar", "Cosmolex"]
        and set(disc.get("missing_connections", [])) == {"Gmail", "Google Calendar", "Cosmolex"})

    # STEP 4 — loop -> dossier -> profile (enrichment, hermetic)
    lp = CLIENT.post("/onboard/loop", json={"max_layers": 4}).json()
    layers = lp.get("layers", [])
    counts = layers[0].get("memory_written") if layers else {}
    prof_ids = {i.id for i in core.memory.profile.all()}
    der_ids = {i.id for i in core.memory.derived.all()}
    chk["loop_ok_done"] = (lp.get("ok") is True and lp.get("done") is True
                           and lp.get("needs_login") == [] and float(lp.get("confidence") or 0) >= 0.7)
    chk["loop_memory_written_counts"] = (counts == {"profile": 5, "derived": 3})
    chk["profile_has_onb_identity"] = ("onb:identity" in prof_ids and "onb:work" in prof_ids)
    chk["profile_has_people"] = ({"onb:person:jordan", "onb:person:priya", "onb:family:jordan"} <= prof_ids)
    chk["derived_has_tools"] = ({"onb:tool:gmail", "onb:tool:cosmolex", "onb:site:targetcom"} <= der_ids)

    # STEP 5 — completion is the ONLY done flag (the loop must NOT auto-complete)
    st_mid = CLIENT.get("/onboard/status").json()
    chk["status_false_before_complete"] = (st_mid.get("onboarding_complete") is False)
    if do_complete:
        comp = CLIENT.post("/onboard/complete", json={"complete": True}).json()
    else:
        comp = {"onboarding_complete": False}
    st_fin = CLIENT.get("/onboard/status").json()
    comp_file = Path(tmp) / "onboard_complete.json"
    chk["status_complete_true"] = (do_complete and comp.get("onboarding_complete") is True
                                   and st_fin.get("onboarding_complete") is True)
    chk["complete_file_on_disk"] = (comp_file.exists()
                                    and json.loads(comp_file.read_text()).get("onboarding_complete") is True) if do_complete \
        else (not comp_file.exists())

    # STEP 5b — B3: data dir is ABSOLUTE at construction (cwd-stable; FIX 1). Red before .resolve(), green after.
    chk["data_dir_absolute"] = (_base("some-relative-dir").is_absolute() and core.data_dir.is_absolute())

    # STEP 6 — idempotency: re-running the spine + loop must not duplicate
    n_prof, n_der, n_loop = len(core.memory.profile.all()), len(core.memory.derived.all()), len(core.memory.open_loops.all())
    CLIENT.post("/owner/onboard", json=OWNER_PAYLOAD)
    CLIENT.post("/onboard/loop", json={"max_layers": 4})
    chk["idempotent"] = (len(core.memory.profile.all()) == n_prof
                         and len(core.memory.derived.all()) == n_der
                         and len(core.memory.open_loops.all()) == n_loop)
    # STEP 6b — store_account URL canonicalization: the SAME store typed with/without scheme or www must
    # upsert to ONE card, not duplicate (overnight bug-hunt #3). Re-post Costco with a scheme+www variant.
    CLIENT.post("/owner/onboard", json={"stores": [{"name": "Costco", "url": "https://www.costco.com/"}], "source": "first_run"})
    costco_cards = [i for i in core.memory.profile.all()
                    if (i.fields or {}).get("kind") == "store_account"
                    and "costco" in (i.text or "").lower()]
    chk["store_url_dedup"] = (len(costco_cards) == 1)
    # STEP 6c — app_connection dedup: the same service re-seen WITH an identifier (typed no-id Gmail in
    # STEP 3, then a Chrome scan with the email) must UPSERT one card, not duplicate (bug-hunt #2).
    CLIENT.post("/onboard/discover", json={"discovered": [{"service": "Gmail", "logged_in": True, "identifier": "owner@example.com"}]})
    gmail_cards = [i for i in core.memory.profile.all()
                   if (i.fields or {}).get("kind") == "app_connection"
                   and "gmail" in (i.text or "").lower()]
    chk["app_connection_dedup"] = (len(gmail_cards) == 1)

    # STEP 7 — honest "not connected": no extension -> triggered:False, never a faked read
    scan = CLIENT.post("/onboard/scan", json={"services": []}).json()
    deep = CLIENT.post("/onboard/deep-scan", json={}).json()
    chk["honest_not_connected"] = (scan.get("triggered") is False and deep.get("triggered") is False)

    return chk, core


def _bad(chk: dict) -> list:
    return [k for k, v in chk.items() if not v]


# ---- entrypoints ----------------------------------------------------------------------------------
def _run_happy() -> int:
    chk, _ = run_flow()
    bad = _bad(chk)
    if bad:
        print("FAIL onboarding_e2e — these checks were False:", bad)
        print(json.dumps(chk, indent=2))
        return 1
    print(f"PASS onboarding_e2e: spine permissions->owner/onboard->discover->loop->complete, "
          f"status cwd-stable, every step asserted ({len(chk)} checks green)")
    return 0


def _selftest() -> int:
    # 1) happy path — everything green
    chk, _ = run_flow()
    if _bad(chk):
        print("EVAL_BROKEN: happy path not green:", _bad(chk)); print(json.dumps(chk, indent=2)); return 2

    # planted failures: (corruption, checks that MUST flip to False, checks that MUST stay True)
    planted = [
        ("empty_dossier", dict(dossier={}),
         ["loop_memory_written_counts", "profile_has_onb_identity", "profile_has_people", "loop_ok_done"], []),
        ("skip_complete", dict(do_complete=False),
         ["status_complete_true"], ["status_false_before_complete", "complete_file_on_disk"]),
        ("no_consent", dict(allow=False),
         ["loop_ok_done", "loop_memory_written_counts"], ["gate_blocks_before_consent"]),
        ("login_walled", dict(scrape_mode="needs_login"),
         ["loop_ok_done", "profile_has_onb_identity"], []),
    ]
    for name, kwargs, must_fail, must_hold in planted:
        c, _ = run_flow(**kwargs)
        leaked = [k for k in must_fail if c.get(k)]          # should have flipped False but didn't
        broke = [k for k in must_hold if not c.get(k)]       # should have stayed True but didn't
        if leaked or broke:
            print(f"EVAL_BROKEN: planted '{name}' not caught. did-not-flip={leaked} wrongly-broke={broke}")
            print(json.dumps(c, indent=2))
            return 2
        print(f"  planted '{name}' CAUGHT (flipped {must_fail})")

    print("PASS onboarding_e2e --selftest: full spine green AND every planted failure "
          "(empty dossier / skipped complete / no consent / login-walled scrape) is CAUGHT")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    return _selftest() if args.selftest else _run_happy()


if __name__ == "__main__":
    sys.exit(main())
