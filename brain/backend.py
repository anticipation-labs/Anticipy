"""One place that talks to the backend, so auth is impossible to forget.

The backend is the Cloudflare Worker at api.anticipy.ai (migration/workers),
whose guard (src/policy/guard.ts) requires the shared service token on every
request the brain makes. Every brain-side request goes through here so a
change to that enforcement is an env change, not a code hunt. The module was
called `pb` while the backend served this API; the wire is unchanged.
"""
from __future__ import annotations

import os

import requests

TIMEOUT = 10


def headers() -> dict:
    # X-Anticipy-Worker names this process as the brain. The Worker's
    # research_lane policy uses it to keep research-lane jobs out of every
    # browser agent's claim poll — including 0.2.3-and-older extensions in
    # the wild, whose filters cannot be recalled. It is a ROUTING marker,
    # not a credential; the service token is what authenticates.
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def _headers(extra=None) -> dict:
    out = headers()
    out.update(extra or {})
    return out


def get(url: str, **kw):
    extra = kw.pop("headers", None)
    return requests.get(url, headers=_headers(extra),
                        timeout=kw.pop("timeout", TIMEOUT), **kw)


def post(url: str, **kw):
    extra = kw.pop("headers", None)
    return requests.post(url, headers=_headers(extra),
                         timeout=kw.pop("timeout", TIMEOUT), **kw)


def patch(url: str, **kw):
    extra = kw.pop("headers", None)
    return requests.patch(url, headers=_headers(extra),
                          timeout=kw.pop("timeout", TIMEOUT), **kw)
