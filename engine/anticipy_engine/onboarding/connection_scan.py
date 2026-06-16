"""Bridge: a logged-in-Chrome connection SCAN -> the owner onboarding mesh.

The extension's `discover_connections` DOM-scrape reports which services the user is
already signed into in their OWN Chrome. This module turns that raw scrape into the
`OwnerOnboardingIn` the existing mesh builder (owner_onboarding.build_onboarding_plan)
already understands — so a DISCOVERED connection becomes the same profile card + the
same "Connect X" open-loop a typed one would, with the right route and auth status.

Pure + deterministic (no Chrome, no network here): the scrape happens in the extension
(the trusted real-Chrome surface); this is the engine-side mapping. Known API services
(gmail, calendar, outlook, slack, notion, drive) route "api"; everything else the user
is logged into — a niche CRM like Cosmolex with no public connector — routes "browser"
(the per-person 10%). A logged-in service Anticipy does NOT yet hold a token for is
`needs_auth` (discovered, ready to connect); one with a vault token is `connected`;
logged-out/absent services are skipped (nothing to connect).
"""
from __future__ import annotations

from typing import Callable, Iterable, Optional

from ..owner_onboarding import OwnerConnectionIn, OwnerOnboardingIn

# Services Anticipy can drive through the API arm (Arcade connectors / known OAuth).
# Maps a normalized scrape label -> the canonical app key the token vault uses.
_API_SERVICES = {
    "gmail": "gmail", "google mail": "gmail", "googlemail": "gmail", "mail.google": "gmail",
    "google calendar": "googlecalendar", "googlecalendar": "googlecalendar", "calendar.google": "googlecalendar",
    "outlook": "outlook", "office 365": "outlook", "office365": "outlook", "microsoft 365": "outlook",
    "slack": "slack", "notion": "notion",
    "google drive": "googledrive", "googledrive": "googledrive", "drive.google": "googledrive",
}


def _canon(service: str) -> str:
    return " ".join((service or "").strip().lower().split())


def scan_to_onboarding(
    discovered: Iterable[dict],
    *,
    source: str = "chrome_scrape",
    vault_has: Optional[Callable[[str], bool]] = None,
) -> OwnerOnboardingIn:
    """Map a logged-in-Chrome connection scan into the onboarding mesh input.

    discovered: iterable of dicts {service, logged_in, identifier?, url?}.
    vault_has:  optional callable(app_key)->bool. When it returns True the service is
                already CONNECTED (Anticipy holds a token); otherwise a logged-in service
                is `needs_auth` (discovered, ready to connect). Logged-out services skipped.
    """
    conns: list[OwnerConnectionIn] = []
    seen: set[str] = set()
    for item in discovered or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("service") or "").strip()
        if not raw or not item.get("logged_in"):
            continue
        canon = _canon(raw)
        key = _API_SERVICES.get(canon, canon)  # canonical app key (vault lookup + dedupe)
        if key in seen:
            continue
        seen.add(key)
        route = "api" if canon in _API_SERVICES else "browser"
        connected = False
        if item.get("connected"):
            # the caller already CONFIRMED this account is connected (e.g. an Arcade
            # tools.authorize == completed in the api_scan path) — the managed-OAuth setup
            # holds the token, so the local vault is empty yet the account is fully connected.
            connected = True
        elif callable(vault_has):
            try:
                connected = bool(vault_has(key))
            except Exception:
                connected = False  # a vault hiccup must NOT crash the scan -> stays needs_auth
        # only trust string-typed scrape fields; non-strings are dropped, never stringified
        # into the durable mesh (garbage-in guard).
        ident = item.get("identifier")
        ident = ident.strip() if isinstance(ident, str) else ""
        url = item.get("url")
        url = url.strip() if isinstance(url, str) else ""
        conns.append(OwnerConnectionIn(
            name=raw,
            status="connected" if connected else "needs_auth",
            route=route,
            identifier=ident,
            notes="discovered logged-in via Chrome scan" + (f"; {url}" if url else ""),
        ))
    return OwnerOnboardingIn(connections=conns, source=source)
