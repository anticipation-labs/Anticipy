"""The real hands — drop-in replacements for the stub workers, on the frozen
contract. The API hand (Arcade) for the cheap common 90%; the browser hand for
the per-person 10% with no API. Dumb executors: they receive fully-resolved,
already-gated jobs and just do them, with proof.
"""
from .api_hand import ApiHand, NotFundedError, MODE_LIVE, MODE_MOCK  # noqa: F401
from .browser_hand import BrowserHand  # noqa: F401
from .token_vault import (  # noqa: F401
    ConnectorRegistry,
    ROUTE_API,
    ROUTE_BROWSER,
    ROUTE_VOICE_TEXT,
    SecretToken,
    TokenBroker,
    TokenNotFound,
    TokenVault,
    VaultError,
)
