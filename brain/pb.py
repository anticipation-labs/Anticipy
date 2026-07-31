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
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    return {"X-Anticipy-Token": token} if token else {}


def get(url: str, **kw):
    return requests.get(url, headers=headers(), timeout=kw.pop("timeout", TIMEOUT), **kw)


def post(url: str, **kw):
    return requests.post(url, headers=headers(), timeout=kw.pop("timeout", TIMEOUT), **kw)


def patch(url: str, **kw):
    return requests.patch(url, headers=headers(), timeout=kw.pop("timeout", TIMEOUT), **kw)
