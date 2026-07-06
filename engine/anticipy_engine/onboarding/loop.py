"""The four-layer onboarding LOOP conductor.

Layer 1 is GUIDED — the owner allows each service (the permission gate) and logs in. From there it runs
AUTONOMOUSLY: each pass scrapes the ALLOWED + reachable surfaces a little deeper, the smart model rebuilds
the dossier, and the loop reports what still needs login + the gaps a short call should fill. It stops
when there's nothing left to log into and the dossier is confident, after MAX_LAYERS, or when a pass adds
nothing new. Genuine + honest throughout — it reuses owner_scrape, which never fakes a read.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from ..core.navwall import nav_block_reason
from . import dossier as _dossier
from .owner_scrape import DEFAULT_SURFACES, scrape_owner
from .permissions import SURFACE_SERVICE


def _onboard_call_enabled() -> bool:
    """Config gate: after the inhale, does the loop AUTO-INITIATE the outbound clarifying call?

    OFF by default (mirrors channels/inbound/voice-execute gating) so run_loop's existing behavior —
    and the whole suite — is byte-identical unless the call arm is deliberately turned on with
    ANTICIPY_ONBOARD_CALL truthy. When on, a loop that finished with nothing left to log into but
    still-open dossier gaps places the gap-filling call (mock-simulated in mock channels, a real
    Twilio dial when ANTICIPY_CHANNELS_MODE=live) and writes the answers back — closing the loop."""
    return (os.environ.get("ANTICIPY_ONBOARD_CALL", "") or "").strip().lower() in {"1", "true", "yes", "on"}

# FIX-11 (2026-07-02): layer 2+ EXPANDS. Before this, every layer re-scrolled the same fixed
# surface set deeper — "layer 2/3" was depth on identical inputs, not the graph expansion the
# name promised. Now each layer unions in the systems the DOSSIER actually discovered (the CRM /
# Notion / billing links seen inside the owner's own accounts), gated by the single "discovered"
# consent. Hard rules: a discovered surface must carry a REAL https URL the model SAW (never a
# name→domain guess), the nav/money wall refuses banks/checkout per-URL, hosts already allowed or
# already bounced (needs_login) are skipped, and each layer adds at most MAX_DISCOVERED_PER_LAYER.
MAX_DISCOVERED_PER_LAYER = 4


def _discovered_surfaces(doss: dict, current: list, bounced_hosts: set) -> list:
    """The dossier's act_on_sites -> new scrape surfaces, filtered hard (see module note)."""
    have_hosts = {s.get("host", "") for s in current} | set(bounced_hosts)
    out: list = []
    for site in (doss.get("dossier", {}) or {}).get("act_on_sites", []) or []:
        if not isinstance(site, dict):
            continue   # a bare name has no URL the model actually saw — tools, not a surface
        url = str(site.get("url") or "").strip()
        name = str(site.get("name") or "").strip() or url
        if not url.startswith("https://"):
            continue
        try:
            host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        except Exception:
            continue
        if not host or host in have_hosts:
            continue
        if nav_block_reason(url):
            continue   # the money/nav wall: banks, checkout, payments never enter the loop
        have_hosts.add(host)
        out.append({"key": f"disc_{host.replace('.', '_')}", "label": f"Discovered — {name}",
                    "url": url, "host": host})
        if len(out) >= MAX_DISCOVERED_PER_LAYER:
            break
    return out

MAX_LAYERS = 4
# each layer reads DEEPER: (max_chars, scroll_steps). Layer 1 catalogues the surface; later layers
# scroll further and dwell to pull in more emails/events/contacts/posts (it takes its time).
# each layer reads DEEPER: (max_chars, scroll_steps, dwell, settle) — sweep #3 threads dwell+settle so
# later passes actually linger longer on slow surfaces, not just scroll more.
_DEPTH = {1: (4000, 6, 1.8, 3.5), 2: (8000, 10, 2.0, 4.5), 3: (14000, 16, 2.2, 5.5), 4: (20000, 22, 2.4, 6.0)}
_CONFIDENT = 0.7
_BUDGET_S = 300.0  # sweep #4: overall wall-clock budget so the loop can never block indefinitely


# Hand-driven loop depth: scroll rounds per layer. Layer 1 catalogues the first screen; later
# layers scroll further through each surface (older mail, further events) before re-synthesizing.
_HAND_DEPTH = {1: 0, 2: 2, 3: 4, 4: 6}


async def run_loop_via_hand(core, targets: list, max_layers: int = MAX_LAYERS) -> dict:
    """The SAME multi-round get-to-know-you loop, driven through the user's OWN paired Chrome
    (the extension) instead of a CDP debug browser — the only hands available on the cloud
    engine. Each layer re-opens the allowed surfaces, scrolls DEEPER (see _HAND_DEPTH),
    re-synthesizes the dossier, expands into the systems the dossier discovered (consent-gated),
    and stops when confident / no progress / out of layers / over budget. Honest throughout:
    a login wall is reported needs_login, never faked."""
    import time
    if not targets:
        return {"ok": False, "reason": "no service allowed yet — approve at least one account first",
                "layers": [], "done": False, "permissions": core.onboard_permissions.state()}
    if not getattr(core.browser_link, "connected", False):
        return {"ok": False, "reason": "no browser extension connected — pair Chrome first",
                "layers": [], "done": False, "permissions": core.onboard_permissions.state()}

    layers: list = []
    doss: dict = {}
    last_conf = -1.0
    started = time.monotonic()
    timed_out = False
    current = [dict(t) for t in targets]
    bounced: set = set()
    for layer in range(1, min(max_layers, MAX_LAYERS) + 1):
        if time.monotonic() - started > _BUDGET_S:
            timed_out = True
            break
        res = await core.onboard_deep_read_via_hand(
            current, source=f"hand_loop_layer_{layer}", scroll_rounds=_HAND_DEPTH.get(layer, 4))
        doss = res.get("dossier") or {}
        conf = float(doss.get("confidence", 0.0) or 0.0)
        needs_login = [s["key"] for s in (res.get("surfaces") or []) if s.get("status") == "needs_login"]
        bounced |= set(needs_login)
        layers.append({
            "layer": layer,
            "scraped": [s["key"] for s in (res.get("surfaces") or []) if s.get("status") == "ok"],
            "needs_login": needs_login,
            "gaps": doss.get("gaps", []),
            "confidence": conf,
            "memory_written": res.get("memory_written"),
        })
        core.glassbox.log("onboard_hand_loop_layer", {"layer": layer, "scraped": layers[-1]["scraped"],
                                                      "needs_login": needs_login, "confidence": conf})
        if core.onboard_permissions.is_allowed("discovered"):
            new_surfaces = _discovered_surfaces(doss, [{"host": (urlparse(t.get("url") or "").hostname or "")
                                                        .lower().removeprefix("www.")} for t in current], bounced)
            if new_surfaces:
                current = current + [{"url": s["url"], "label": s["label"]} for s in new_surfaces]
                layers[-1]["discovered"] = [s["host"] for s in new_surfaces]
                core.glassbox.log("onboard_hand_loop_expanded", {"layer": layer,
                                                                 "added": [s["host"] for s in new_surfaces]})
        if not needs_login and conf >= _CONFIDENT:
            break
        if layer > 1 and conf <= last_conf:
            break
        last_conf = conf

    final = layers[-1] if layers else {}
    done = bool(final and not final.get("needs_login") and final.get("confidence", 0) >= _CONFIDENT)

    onboarding_call = None
    gaps_final = final.get("gaps") or []
    if _onboard_call_enabled() and gaps_final and not final.get("needs_login"):
        try:
            onboarding_call = await core.run_onboarding_call(doss)
        except Exception as e:
            onboarding_call = {"ok": False, "initiated": False, "error": str(e)[:180]}
        core.glassbox.log("onboard_loop_call",
                          {"initiated": bool((onboarding_call or {}).get("initiated")),
                           "questions": len((onboarding_call or {}).get("questions") or [])})

    return {
        "ok": True,
        "via": "hand",
        "layers": layers,
        "done": done,
        "timed_out": timed_out,
        "dossier": doss.get("dossier", {}),
        "confidence": final.get("confidence", 0),
        "needs_login": final.get("needs_login", []),
        "gaps": final.get("gaps", []),
        "onboarding_call": onboarding_call,
        "permissions": core.onboard_permissions.state(),
        "confirm_prompt": ("Here's what I learned about you — confirm and we're set."
                           if done else
                           "Log into the accounts above in your Chrome and I'll go deeper."),
    }


async def run_loop(core, cdp_url: str | None = None, max_layers: int = MAX_LAYERS) -> dict:
    import time
    from fastapi.concurrency import run_in_threadpool

    perms = core.onboard_permissions
    allowed = [s for s in DEFAULT_SURFACES if perms.is_allowed(SURFACE_SERVICE.get(s["key"], ""))]
    if not allowed:
        return {"ok": False, "reason": "no service allowed yet — approve at least one account first",
                "layers": [], "done": False, "permissions": perms.state()}

    layers: list = []
    doss: dict = {}
    last_conf = -1.0
    started = time.monotonic()
    timed_out = False
    for layer in range(1, min(max_layers, MAX_LAYERS) + 1):
        if time.monotonic() - started > _BUDGET_S:  # sweep #4: stop gracefully on the wall-clock budget
            timed_out = True
            break
        # GENUINE read of the allowed surfaces — deeper each layer (honest needs_login; never faked)
        max_chars, scroll_steps, dwell, settle = _DEPTH.get(layer, (8000, 10, 2.0, 4.5))
        signals = await run_in_threadpool(scrape_owner, cdp_url, allowed, max_chars, scroll_steps, dwell, settle)
        doss = await _dossier.synthesize_dossier(signals, core.gateway, per_surface_chars=max_chars)
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
        # FIX-11: EXPAND — union in the systems this layer's dossier discovered, so the NEXT layer
        # follows the owner's real graph instead of re-scrolling the same five sites deeper.
        if perms.is_allowed("discovered"):
            new_surfaces = _discovered_surfaces(doss, allowed, set(needs_login or []))
            if new_surfaces:
                allowed = allowed + new_surfaces
                layers[-1]["discovered"] = [s["host"] for s in new_surfaces]
                core.glassbox.log("onboard_loop_expanded", {"layer": layer,
                                                            "added": [s["host"] for s in new_surfaces]})
        # stop: nothing left to log into AND confident
        if not needs_login and conf >= _CONFIDENT:
            break
        # stop: a deeper pass that added nothing (no progress)
        if layer > 1 and conf <= last_conf:
            break
        last_conf = conf

    final = layers[-1] if layers else {}
    done = bool(final and not final.get("needs_login") and final.get("confidence", 0) >= _CONFIDENT)

    # CLOSE THE LOOP: once there's nothing left to log into but the inhale left open gaps, hand the
    # dossier to the CALL arm — clarify ranks the dossier's gaps into a couple of spoken questions,
    # the outbound call is placed (CallChannel.send; mock-simulated / live-dialed), and the answers
    # are written back so the dossier + first cards are re-aimed. Gated OFF by default; a glassbox/
    # call hiccup can never break the inhale that already succeeded.
    onboarding_call = None
    gaps_final = final.get("gaps") or []
    if _onboard_call_enabled() and gaps_final and not final.get("needs_login"):
        try:
            onboarding_call = await core.run_onboarding_call(doss)
        except Exception as e:  # never let the call arm break a good inhale
            onboarding_call = {"ok": False, "initiated": False, "error": str(e)[:180]}
        core.glassbox.log("onboard_loop_call",
                          {"initiated": bool((onboarding_call or {}).get("initiated")),
                           "questions": len((onboarding_call or {}).get("questions") or [])})

    return {
        "ok": True,
        "layers": layers,
        "done": done,
        "timed_out": timed_out,
        "dossier": doss.get("dossier", {}),
        "confidence": final.get("confidence", 0),
        "needs_login": final.get("needs_login", []),
        "gaps": final.get("gaps", []),
        "onboarding_call": onboarding_call,
        "permissions": perms.state(),
        "confirm_prompt": ("Here's what I learned about you — confirm and we're set."
                           if done else
                           "Log into the accounts above in the Anticipy browser and I'll go deeper."),
    }
