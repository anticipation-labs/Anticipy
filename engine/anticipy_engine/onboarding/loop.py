"""The four-layer onboarding LOOP conductor.

Layer 1 is GUIDED — the owner allows each service (the permission gate) and logs in. From there it runs
AUTONOMOUSLY: each pass scrapes the ALLOWED + reachable surfaces a little deeper, the smart model rebuilds
the dossier, and the loop reports what still needs login + the gaps a short call should fill. It stops
when there's nothing left to log into and the dossier is confident, after MAX_LAYERS, or when a pass adds
nothing new. Genuine + honest throughout — it reuses owner_scrape, which never fakes a read.
"""
from __future__ import annotations

from . import dossier as _dossier
from .owner_scrape import DEFAULT_SURFACES, scrape_owner
from .permissions import SURFACE_SERVICE

MAX_LAYERS = 4
_DEPTH = {1: 2500, 2: 5000, 3: 8000, 4: 12000}  # each layer reads deeper
_CONFIDENT = 0.7


async def run_loop(core, cdp_url: str | None = None, max_layers: int = MAX_LAYERS) -> dict:
    from fastapi.concurrency import run_in_threadpool

    perms = core.onboard_permissions
    allowed = [s for s in DEFAULT_SURFACES if perms.is_allowed(SURFACE_SERVICE.get(s["key"], ""))]
    if not allowed:
        return {"ok": False, "reason": "no service allowed yet — approve at least one account first",
                "layers": [], "done": False, "permissions": perms.state()}

    layers: list = []
    doss: dict = {}
    last_conf = -1.0
    for layer in range(1, min(max_layers, MAX_LAYERS) + 1):
        # GENUINE read of the allowed surfaces (honest needs_login; never faked)
        signals = await run_in_threadpool(scrape_owner, cdp_url, allowed, _DEPTH.get(layer, 6000))
        doss = await _dossier.synthesize_dossier(signals, core.gateway)
        counts = _dossier.write_dossier_to_memory(doss, core.memory)
        conf = float(doss.get("confidence", 0.0) or 0.0)
        needs_login = signals.get("needs_login", [])
        layers.append({
            "layer": layer,
            "scraped": signals.get("logged_in", []),
            "needs_login": needs_login,
            "gaps": doss.get("gaps", []),
            "confidence": conf,
            "memory_written": counts,
        })
        core.glassbox.log("onboard_loop_layer", {"layer": layer, "scraped": signals.get("logged_in"),
                                                 "needs_login": needs_login, "confidence": conf})
        # stop: nothing left to log into AND confident
        if not needs_login and conf >= _CONFIDENT:
            break
        # stop: a deeper pass that added nothing (no progress)
        if layer > 1 and conf <= last_conf:
            break
        last_conf = conf

    final = layers[-1] if layers else {}
    done = bool(final and not final.get("needs_login") and final.get("confidence", 0) >= _CONFIDENT)
    return {
        "ok": True,
        "layers": layers,
        "done": done,
        "dossier": doss.get("dossier", {}),
        "confidence": final.get("confidence", 0),
        "needs_login": final.get("needs_login", []),
        "gaps": final.get("gaps", []),
        "permissions": perms.state(),
        "confirm_prompt": ("Here's what I learned about you — confirm and we're set."
                           if done else
                           "Log into the accounts above in the Anticipy browser and I'll go deeper."),
    }
