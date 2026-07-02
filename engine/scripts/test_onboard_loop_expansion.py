"""LOCK: the layered scrape EXPANDS (FIX-11) — layer 2+ picks its own sites, safely.

Pins the self-expansion contract of onboarding/loop.py:
  1. A layer-1 dossier that discovered a real system (Notion, with a URL the model SAW) makes
     layer 2's scrape call receive that surface — the loop follows the owner's graph.
  2. A money/bank URL (chase.com) NEVER enters the loop (nav wall), even when "discovered".
  3. Without the "discovered" consent, NOTHING expands — same fixed surfaces every layer.
  4. A bare tool name (no URL) never becomes a surface — no name→domain guessing, ever.
Deterministic: scrape_owner + synthesize_dossier are monkeypatched; no browser, no model.
"""
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.onboarding import loop as loop_mod  # noqa: E402

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        fails.append(f"{name}: {detail}")


def make_fakes(discovered_sites):
    """scrape_owner records the surfaces each call receives; the dossier plants discoveries."""
    calls: list[list] = []

    def fake_scrape(cdp_url, surfaces, max_chars, scroll_steps, dwell, settle):
        calls.append([dict(s) for s in surfaces])
        return {"surfaces": [{**s, "status": "ok", "text": f"text from {s['key']}", "chars": 100,
                              "needs_login": False} for s in surfaces],
                "logged_in": [s["key"] for s in surfaces], "needs_login": []}

    async def fake_dossier(signals, gateway, per_surface_chars=4000):
        # low confidence so the loop keeps going past layer 1; rising so no-progress stop doesn't fire
        conf = 0.3 + 0.1 * len(calls)
        return {"dossier": {"identity": {"name": "Omar"}, "act_on_sites": discovered_sites},
                "gaps": ["g"], "confidence": conf}

    return calls, fake_scrape, fake_dossier


async def run_loop(core, discovered_sites, max_layers=2):
    calls, fake_scrape, fake_dossier = make_fakes(discovered_sites)
    orig_scrape, orig_doss = loop_mod.scrape_owner, loop_mod._dossier.synthesize_dossier
    loop_mod.scrape_owner = fake_scrape
    loop_mod._dossier.synthesize_dossier = fake_dossier
    try:
        res = await loop_mod.run_loop(core, cdp_url=None, max_layers=max_layers)
    finally:
        loop_mod.scrape_owner = orig_scrape
        loop_mod._dossier.synthesize_dossier = orig_doss
    return calls, res


async def main() -> None:
    d = Path(tempfile.mkdtemp())
    core = ControlCore(data_dir=d)
    await core.start()
    try:
        core.onboard_permissions.set("gmail", True)

        # ---- (1) + (2) + (4): with consent, Notion expands in; chase + bare names never do ----
        core.onboard_permissions.set("discovered", True)
        calls, res = await run_loop(core, [
            {"name": "Notion", "url": "https://www.notion.so/acme/workspace"},
            {"name": "Chase", "url": "https://chase.com/dashboard"},
            "HubSpot",  # bare name, no URL the model saw
        ])
        check("two layers ran", len(calls) == 2, f"calls={len(calls)}")
        l2_hosts = {s.get("host") for s in (calls[1] if len(calls) > 1 else [])}
        check("layer 2 received the DISCOVERED Notion surface", "notion.so" in l2_hosts, str(l2_hosts))
        check("bank never enters the loop", not any("chase" in h for h in l2_hosts), str(l2_hosts))
        check("bare tool name never becomes a surface", not any("hubspot" in h for h in l2_hosts), str(l2_hosts))
        check("expansion recorded on the layer", "notion.so" in (res["layers"][0].get("discovered") or []),
              str(res["layers"][0].get("discovered")))

        # ---- (3) without consent: nothing expands ----
        core.onboard_permissions.set("discovered", False)
        calls2, _ = await run_loop(core, [{"name": "Notion", "url": "https://www.notion.so/x"}])
        h1 = {s.get("host") for s in calls2[0]}
        h2 = {s.get("host") for s in (calls2[1] if len(calls2) > 1 else calls2[0])}
        check("no consent -> no expansion", h1 == h2 and "notion.so" not in h2, f"{h1} vs {h2}")
    finally:
        await core.bus.stop()


asyncio.run(main())

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print("PASS onboard_loop_expansion: layer 2 follows the discovered graph; banks + bare names refused; consent-gated")
