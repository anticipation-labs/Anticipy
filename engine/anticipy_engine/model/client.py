"""Swappable model client.

The engine reaches reasoning through OUR endpoint (``ANTICIPY_MODEL_ENDPOINT``),
not a provider SDK, so the model is swappable and cost is controlled centrally.

Scaffold behavior: with no endpoint configured, ``think()`` returns a
deterministic local stub — no network, no provider call, no keys touched. When
our endpoint exists (pinned in a later chunk) it POSTs an OpenAI-compatible
request. Callers never change.
"""
from __future__ import annotations

import os
from typing import Final


class Tier:
    """Cost discipline: pick the cheapest tier that can do the step."""

    CHEAP: Final = "cheap"   # easy/cheap steps
    SMART: Final = "smart"   # hard reasoning only


class ModelClient:
    def __init__(self, endpoint: str | None = None, timeout: float = 30.0) -> None:
        # Swappable: our own endpoint, configured by env. None => scaffold stub.
        self.endpoint = endpoint if endpoint is not None else os.environ.get("ANTICIPY_MODEL_ENDPOINT")
        self.timeout = timeout

    @property
    def mode(self) -> str:
        return "endpoint" if self.endpoint else "stub"

    def think(self, prompt: str, *, tier: str = Tier.SMART) -> str:
        """Single reasoning call. Returns model text."""
        if not self.endpoint:
            # Deterministic scaffold stub — proves the wire without a provider.
            return f"[stub:{tier}] {prompt.strip()[:160]}"

        # Real path (active once our endpoint is pinned). OpenAI-compatible.
        import httpx

        resp = httpx.post(
            self.endpoint,
            json={"tier": tier, "messages": [{"role": "user", "content": prompt}]},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


# Module-level convenience: the engine's single think() call.
_default = ModelClient()


def think(prompt: str, *, tier: str = Tier.SMART) -> str:
    return _default.think(prompt, tier=tier)
