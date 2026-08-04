"""One place that talks to PocketBase, so auth is impossible to forget.

The collections still carry dev-grade open rules; the backend's guard hook can
require a shared service token on every mutating request (see
backend/pb_hooks/guard.pb.js). Every brain-side request goes through here so
turning that enforcement on is an env change, not a code hunt.
"""
from __future__ import annotations

import os

import requests

TIMEOUT = 10


def headers() -> dict:
    # X-Anticipy-Worker names this process as the brain. The backend's
    # research_lane hook uses it to keep research-lane jobs out of every
    # browser agent's claim poll — including 0.2.3-and-older extensions in
    # the wild, whose filters cannot be recalled. It is a ROUTING marker,
    # not a credential; the service token is what authenticates.
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def get(url: str, **kw):
    return requests.get(url, headers=headers(), timeout=kw.pop("timeout", TIMEOUT), **kw)


def post(url: str, **kw):
    return requests.post(url, headers=headers(), timeout=kw.pop("timeout", TIMEOUT), **kw)


def patch(url: str, **kw):
    return requests.patch(url, headers=headers(), timeout=kw.pop("timeout", TIMEOUT), **kw)
