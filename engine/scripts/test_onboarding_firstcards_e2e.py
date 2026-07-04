"""Onboarding FIRST-CARDS proof — the "billion percent" payoff: after a fresh user runs the full
onboarding path (land -> sign -> connect -> INHALE -> complete), do REAL FIRST CARDS derived from the
INHALED accounts actually land on the board? The spine e2e (test_onboarding_e2e.py) proves the plumbing
transitions; this proves the PRODUCT PROMISE — the board is no longer empty and is NOT sample data.

Un-gameable by construction:
  * A THROWAWAY engine — its OWN fresh ANTICIPY_DATA_DIR, stub model, mock hands/channels, booted on its
    OWN ephemeral port (never :8787), so it can't touch the live dev engine or any real account.
  * The fake "smart model" is a DETERMINISTIC EXTRACTOR of the raw inhaled text — it invents nothing; the
    dossier it returns is a pure function of what the (faked) scrape read. So a card can only carry an
    entity that was genuinely in the inhaled bytes.
  * The payoff asserts cards bearing INHALE-EXCLUSIVE tokens (people "Venkataraman"/"Delacroix", the site
    "Ledgerwing") that appear NOWHERE in the typed onboarding payload — a card with one of those tokens
    could ONLY have come from the inhale, never from typed setup or sample/seed data.

Planted-failure battery (the honesty law): corrupt the inhale and assert NO fake cards appear.
  * inhale_unreadable — every surface bounces to a sign-in wall (needs_login) -> the dossier is honestly
    empty -> zero cards -> the board shows only the typed spine (identity + Connect-X loops), never a
    fabricated first card.
  * inhale_garbled — a surface reads but carries no entities (an empty inbox) -> the extractor finds
    nothing -> zero cards. Even WITH a readable page, nothing is invented from nothing.
A harness that cannot catch a fabricated card must never certify onboarding-done.

  test_onboarding_firstcards_e2e.py            # happy path -> PASS/FAIL
  test_onboarding_firstcards_e2e.py --selftest # happy path + planted-failure battery
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

# Env MUST be set before importing anticipy_engine.main (it builds a default core + reads the scheduler
# knobs at import/lifespan time). Force the free + deterministic + SILENT profile: stub model, mock
# hands/channels, and every background scheduler OFF so the booted engine is inert apart from the
# request we drive. No owner token -> routes are open (default core). No OpenRouter key -> the ONLY
# "smart model" is the deterministic extractor we install below.
_TMP0 = tempfile.mkdtemp(prefix="anticipy-fc-import-")
os.environ["ANTICIPY_DATA_DIR"] = _TMP0
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_HANDS_MODE"] = "mock"
os.environ["ANTICIPY_CHANNELS_MODE"] = "mock"
os.environ["ANTICIPY_NATIVE_BRIDGE_FALLBACK"] = "0"
os.environ["ANTICIPY_TICK_SECONDS"] = "0"
os.environ["ANTICIPY_DERIVE_SECONDS"] = "0"
os.environ["ANTICIPY_INBOUND_POLL_SECONDS"] = "0"
os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
os.environ.pop("OPENROUTER_API_KEY", None)

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from anticipy_engine import main as engmain  # noqa: E402
from anticipy_engine.core import registry  # noqa: E402
from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.core.gateway import PROVIDER_OPENROUTER  # noqa: E402
from anticipy_engine.onboarding import loop as onb_loop  # noqa: E402
from anticipy_engine.onboarding import owner_scrape as onb_scrape  # noqa: E402

# ---- fixtures -------------------------------------------------------------------------------------
# Typed first-run setup. NOTE the tokens here (Rivera, Gmail, Calendar) are deliberately DISJOINT from
# the inhaled tokens below, so any card bearing an inhaled token is provably from the inhale, not this.
OWNER_PAYLOAD = {
    "owner_name": "Dana Rivera", "timezone": "America/Los_Angeles", "email": "dana@lumenlabs.example",
    "connections": [
        {"name": "Gmail", "status": "needs_auth", "route": "api"},
        {"name": "Calendar", "status": "needs_auth", "route": "api"},
    ],
    "source": "first_run",
}

# What the (faked) browser scrape READS out of the owner's own logged-in Gmail. The distinctive tokens
# below are the whole point: they exist ONLY in this inhaled text.
INHALED_GMAIL_TEXT = (
    "You are signed in as Dana Okonkwo <dana@lumenlabs.example>.\n"
    "From: Priyanka Venkataraman <priyanka@auroracap.example> - re: Series Seed term sheet for Lumen Labs\n"
    "From: Marcus Delacroix <marcus@northwind.example> - product roadmap sync Thursday 2pm\n"
    "Heads up: your Ledgerwing billing dashboard is live at https://app.ledgerwing.example/billing\n"
)
# Tokens that can ONLY come from the inhale (absent from OWNER_PAYLOAD and from any sample/seed data).
INHALE_TOKENS = ("Venkataraman", "Delacroix", "Ledgerwing")
# The exact per-layer memory write the extractor's dossier must produce: identity(1)+person(2)=3 profile,
# tool(1)+site(1)=2 derived. Deterministic, so a drift in the derivation is a caught failure.
EXPECT_COUNTS = {"profile": 3, "derived": 2}


def _extract_dossier(prompt: str) -> dict:
    """The deterministic stand-in for the smart model: parse the RAW ACCOUNT TEXT and build a dossier
    from ONLY what the text supports. This is what makes the proof un-gameable — with no entities in the
    text (a walled or empty inhale) it returns an empty dossier, so no card can be fabricated."""
    raw = prompt.split("RAW ACCOUNT TEXT:", 1)[1] if "RAW ACCOUNT TEXT:" in prompt else prompt
    identity: dict = {}
    mi = re.search(r"signed in as\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\s*<([^>]+)>", raw)
    if mi:
        identity = {"name": mi.group(1).strip(), "role": "", "location": "", "email": mi.group(2).strip()}
    people, seen = [], set()
    for m in re.finditer(r"From:\s*([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)+)\s*<([^>]+)>([^\n]*)", raw):
        name = m.group(1).strip()
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        why = re.sub(r"^[\s\-—]+", "", m.group(3) or "").strip()[:80]
        people.append({"name": name, "relationship": "correspondent", "why_they_matter": why})
    sites, tools, site_seen = [], [], set()
    for m in re.finditer(r"https://([a-z0-9.\-]+)(/[^\s]*)?", raw):
        host = m.group(1).lower()
        if any(h in host for h in ("google.com", "linkedin.com", "gstatic", "googleapis")):
            continue
        brand = next((p for p in host.split(".") if p not in ("app", "www", "mail", "calendar",
                                                              "contacts", "example", "com", "io")), host)
        if brand in site_seen:
            continue
        site_seen.add(brand)
        sites.append({"name": brand, "url": "https://" + host + (m.group(2) or "")})
        tools.append(brand.capitalize())
    return {"identity": identity, "work": "", "people": people, "family": [],
            "tools": tools, "act_on_sites": sites, "gaps": [], "confidence": 0.85 if people else 0.0}


class _FakeScrape:
    """Stand-in for the CDP browser scrape — no Chrome. `.calls` lets the gate assert 0 reads pre-consent.
    mode: 'ok' -> a readable Gmail carrying the inhaled tokens; 'needs_login' -> walled (no text);
    'garbled' -> readable but entity-free (an empty inbox)."""

    def __init__(self, mode="ok"):
        self.calls = 0
        self.mode = mode

    def __call__(self, cdp_url=None, surfaces=None, max_chars=0, scroll_steps=0, dwell=0, settle=0):
        self.calls += 1
        if self.mode == "needs_login":
            return {"ok": True, "logged_in": [], "needs_login": ["gmail_inbox"],
                    "surfaces": [{"key": "gmail_inbox", "label": "Gmail - inbox", "status": "needs_login",
                                  "needs_login": True, "text": "", "chars": 0}]}
        text = (INHALED_GMAIL_TEXT if self.mode == "ok"
                else "Inbox synced. 0 conversations. Nothing to display.")
        return {"ok": True, "logged_in": ["gmail_inbox"], "needs_login": [],
                "surfaces": [{"key": "gmail_inbox", "label": "Gmail - inbox", "status": "ok",
                              "needs_login": False, "text": text, "chars": len(text)}]}


# ---- throwaway engine on its OWN ephemeral port (never :8787) --------------------------------------
_SERVER: uvicorn.Server | None = None
_BASE_URL: str = ""


def _boot_engine() -> str:
    """Boot the REAL engine (engmain.app) on an OS-assigned free port in a daemon thread, once. Same
    process, so the module-level fakes we install per flow are the objects the request handlers use."""
    global _SERVER, _BASE_URL
    if _SERVER is not None:
        return _BASE_URL
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(engmain.app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 25:
        time.sleep(0.03)
    if not server.started:
        raise RuntimeError("throwaway engine did not start")
    base = f"http://127.0.0.1:{port}"
    for _ in range(200):  # readiness poll on the public /health
        try:
            if httpx.get(base + "/health", timeout=2).status_code == 200:
                break
        except Exception:
            time.sleep(0.03)
    _SERVER, _BASE_URL = server, base

    @atexit.register
    def _stop() -> None:
        server.should_exit = True

    return base


def _install_core_and_fakes(*, scrape_mode: str):
    """A brand-new core at a brand-new temp dir (clean board), registered as the default the open routes
    resolve to, wired with the fake scrape + the deterministic extractor as the 'smart model'."""
    tmp = tempfile.mkdtemp(prefix="anticipy-fc-run-")
    os.environ["ANTICIPY_DATA_DIR"] = tmp
    core = ControlCore(data_dir=tmp)
    registry.register_default(core)
    fs = _FakeScrape(mode=scrape_mode)
    onb_loop.scrape_owner = fs   # run_loop calls this module global
    onb_scrape.scrape_owner = fs

    async def _think(prompt, *a, **k):
        return json.dumps(_extract_dossier(prompt))

    core.gateway.provider = PROVIDER_OPENROUTER   # flips dossier.py into the synthesis branch
    core.gateway.think = _think
    return core, tmp, fs


# ---- the flow -------------------------------------------------------------------------------------
def _texts(drawer: dict) -> list:
    return [i.get("text", "") for i in (drawer.get("recent") or [])]


def _has_token(texts: list, token: str) -> bool:
    t = token.lower()
    return any(t in (x or "").lower() for x in texts)


def run_flow(*, allow: bool = True, do_complete: bool = True, scrape_mode: str = "ok") -> dict:
    """Drive the whole onboarding path once over real HTTP; return named boolean checks. Each check is a
    load-bearing unit the selftest can flip by corrupting the inhale."""
    base = _boot_engine()
    core, tmp, fs = _install_core_and_fakes(scrape_mode=scrape_mode)
    http = httpx.Client(base_url=base, timeout=30)
    chk: dict[str, bool] = {}

    # STEP 0 — fresh board: nothing complete, nothing allowed yet.
    st0 = http.get("/onboard/status").json()
    perm0 = http.get("/onboard/permissions").json()
    chk["fresh_board"] = (st0.get("onboarding_complete") is False
                          and len(perm0.get("services", [])) == 5
                          and perm0.get("any_allowed") is False)

    # STEP 1 — the consent gate fires BEFORE any inhale (no read without an allowed account).
    loop_pre = http.post("/onboard/loop", json={"max_layers": 2}).json()
    chk["consent_gate_blocks"] = (loop_pre.get("ok") is False
                                  and "no service allowed" in (loop_pre.get("reason") or "")
                                  and fs.calls == 0)

    # STEP 2 — (a) permissions -> /owner/onboard writes a SOURCED profile + connect_account loops.
    own = http.post("/owner/onboard", json=OWNER_PAYLOAD).json()
    written = own.get("written", [])
    chk["spine_sourced_profile"] = (own.get("missing_connections") == ["Gmail", "Calendar"]
                                    and bool(written)
                                    and all(w["fields"].get("source") == "first_run" for w in written))

    # STEP 3 — record consent (the gate) for the read services.
    if allow:
        for s in ("gmail", "calendar", "contacts", "linkedin"):
            http.post("/onboard/permissions", json={"service": s, "allowed": True})
    perm_after = http.get("/onboard/permissions").json()
    chk["consent_recorded"] = (perm_after.get("any_allowed") is (True if allow else False))

    # STEP 4 — (b) the INHALE: /onboard/loop reads the seeded account and synthesizes the dossier.
    lp = http.post("/onboard/loop", json={"max_layers": 2}).json()
    layers = lp.get("layers", [])
    counts = layers[0].get("memory_written") if layers else {}
    chk["inhale_wrote_cards"] = (lp.get("ok") is True and lp.get("done") is True
                                 and counts == EXPECT_COUNTS
                                 and float(lp.get("confidence") or 0) >= 0.7)

    # STEP 5 — status must be False until the owner explicitly completes.
    st_mid = http.get("/onboard/status").json()
    chk["status_false_before_complete"] = (st_mid.get("onboarding_complete") is False)

    # STEP 6 — (c) /onboard/complete transitions to ready.
    if do_complete:
        comp = http.post("/onboard/complete", json={"complete": True}).json()
    else:
        comp = {"onboarding_complete": False}
    st_fin = http.get("/onboard/status").json()
    comp_file = Path(tmp) / "onboard_complete.json"
    chk["complete_ready"] = (do_complete and comp.get("onboarding_complete") is True
                             and st_fin.get("onboarding_complete") is True and comp_file.exists()) \
        if do_complete else (st_fin.get("onboarding_complete") is False and not comp_file.exists())

    # STEP 7 — (d) THE PAYOFF: the board (the drawers) now shows REAL first cards/open-loops derived from
    # what was inhaled — not empty, not sample data. /owner/cards is the durable ACTION-card board (empty
    # at onboarding); the memory drawers are where the first cards land, so that's the board we assert.
    drawers = http.get("/memory/drawers").json().get("drawers", {})
    profile_txt = _texts(drawers.get("profile", {}))
    derived_txt = _texts(drawers.get("derived", {}))
    loops_txt = _texts(drawers.get("open_loops", {}))
    cards_ok = http.get("/owner/cards").status_code == 200   # the action board is reachable (may be empty)

    chk["payoff_people_cards"] = (_has_token(profile_txt, "Venkataraman")
                                  and _has_token(profile_txt, "Delacroix"))
    chk["payoff_derived_cards"] = _has_token(derived_txt, "Ledgerwing")
    chk["payoff_open_loops"] = (_has_token(loops_txt, "Connect Gmail")
                                and _has_token(loops_txt, "Connect Calendar"))
    chk["cards_derived_from_inhale"] = (chk["payoff_people_cards"] and chk["payoff_derived_cards"]
                                        and chk["inhale_wrote_cards"] and cards_ok)

    # STEP 8 — the anti-fabrication invariant. When the inhale is CORRUPT, none of the inhale-exclusive
    # tokens may appear anywhere on the board. In the happy path they DO appear (so this is False) — that
    # asymmetry is exactly what the planted battery exploits: corrupt -> this stays True (no fakes).
    board_txt = profile_txt + derived_txt
    chk["no_fabricated_cards"] = not any(_has_token(board_txt, tok) for tok in INHALE_TOKENS)

    http.close()
    return chk


# ---- entrypoints ----------------------------------------------------------------------------------
# Green on the happy path (payoff present, board derived from the inhale). no_fabricated_cards is
# EXPECTED False here (the tokens ARE on the board) and so is checked only in the planted battery.
HAPPY_GREEN = ["fresh_board", "consent_gate_blocks", "spine_sourced_profile", "consent_recorded",
               "inhale_wrote_cards", "status_false_before_complete", "complete_ready",
               "payoff_people_cards", "payoff_derived_cards", "payoff_open_loops",
               "cards_derived_from_inhale"]


def _bad(chk: dict, keys) -> list:
    return [k for k in keys if not chk.get(k)]


def _run_happy() -> int:
    chk = run_flow()
    bad = _bad(chk, HAPPY_GREEN)
    if bad:
        print("FAIL onboarding_firstcards_e2e — these checks were False:", bad)
        print(json.dumps(chk, indent=2))
        return 1
    print("PASS onboarding_firstcards_e2e: full path land->connect->INHALE->complete; the board shows "
          f"REAL first cards derived from the inhaled account (people Venkataraman/Delacroix, site "
          f"Ledgerwing) + Connect-X loops — not empty, not sample data ({len(HAPPY_GREEN)} checks green)")
    return 0


def _selftest() -> int:
    # 1) happy path — everything the product promises is green.
    chk = run_flow()
    if _bad(chk, HAPPY_GREEN):
        print("EVAL_BROKEN: happy path not green:", _bad(chk, HAPPY_GREEN))
        print(json.dumps(chk, indent=2))
        return 2

    # 2) planted-failure battery: corrupt the inhale, assert NO fake cards appear. must_fail must flip
    # False (the derived payoff is gone), must_hold must stay True (the spine + the anti-fabrication
    # invariant survive: onboarding still completes, but nothing is invented).
    planted = [
        ("inhale_unreadable", dict(scrape_mode="needs_login"),
         ["inhale_wrote_cards", "payoff_people_cards", "payoff_derived_cards", "cards_derived_from_inhale"],
         ["spine_sourced_profile", "consent_gate_blocks", "complete_ready",
          "payoff_open_loops", "no_fabricated_cards"]),
        ("inhale_garbled", dict(scrape_mode="garbled"),
         ["inhale_wrote_cards", "payoff_people_cards", "payoff_derived_cards", "cards_derived_from_inhale"],
         ["spine_sourced_profile", "consent_gate_blocks", "complete_ready",
          "payoff_open_loops", "no_fabricated_cards"]),
    ]
    for name, kwargs, must_fail, must_hold in planted:
        c = run_flow(**kwargs)
        leaked = [k for k in must_fail if c.get(k)]     # should have flipped False but didn't
        broke = [k for k in must_hold if not c.get(k)]  # should have stayed True but didn't
        if leaked or broke:
            print(f"EVAL_BROKEN: planted '{name}' not caught. did-not-flip={leaked} wrongly-broke={broke}")
            print(json.dumps(c, indent=2))
            return 2
        print(f"  planted '{name}' CAUGHT — corrupt inhale produced NO fake cards (flipped {must_fail})")

    print("PASS onboarding_firstcards_e2e --selftest: real first cards derived from the inhale on the "
          "happy path AND every corrupt-inhale (walled / empty) fabricates NOTHING")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    return _selftest() if args.selftest else _run_happy()


if __name__ == "__main__":
    sys.exit(main())
