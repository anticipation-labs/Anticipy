"""
Configuration loaded from environment variables.
All budget limits and model fallback order defined here.
"""

import json
import logging
import os
import secrets as _stdsecrets
import stat
from pathlib import Path

from cryptography.fernet import Fernet


_logger = logging.getLogger("engine")


def _engine_secrets_path() -> Path:
    """Path to ~/.anticipy/secrets.json, created at first run.

    Stranger installs ship without env vars set. Instead of falling back to
    insecure dev defaults (B021), we mint random secrets on first boot and
    persist them with 0600 perms so subsequent restarts pick them up.
    """
    base = Path(os.environ.get("ANTICIPY_HOME") or
                (Path.home() / ".anticipy"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "secrets.json"


def _load_persisted_secrets() -> dict:
    p = _engine_secrets_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _persist_secrets(d: dict) -> None:
    p = _engine_secrets_path()
    try:
        p.write_text(json.dumps(d, sort_keys=True), encoding="utf-8")
        try:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        except Exception:
            pass
    except Exception as _e:
        _logger.warning("could not persist engine secrets: %s", _e)


_PERSISTED_SECRETS: dict = _load_persisted_secrets()

# Truthy values for environment booleans
_TRUTHY = {"1", "true", "yes", "on"}

ENVIRONMENT: str = os.environ.get("ENGINE_ENV", os.environ.get("NODE_ENV", "development")).lower()
IS_PRODUCTION: bool = ENVIRONMENT in ("production", "prod")


# --- Supabase ---
SUPABASE_URL: str = os.environ.get(
    "NEXT_PUBLIC_SUPABASE_URL",
    "https://ogbxpqkmsdrcuilafycn.supabase.co",
)
SUPABASE_ANON_KEY: str = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")

# --- LLM API keys ---
DEEPSEEK_API_KEY: str = os.environ.get("DEEPSEEK_API_KEY", "")
GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
KIMI_API_KEY: str = os.environ.get("KIMI_API_KEY", "")
# Mistral La Plateforme — used for the Critic role primary (mistral-small,
# 262K ctx, vision+tools+reasoning). Different family from the
# planner/executor so role diversity is preserved.
MISTRAL_API_KEY: str = os.environ.get("MISTRAL_API_KEY", "")
# Cerebras — used for the Executor role (very low-latency Llama hosted on
# wafer-scale silicon). Different family from the planner/critic so role
# diversity is preserved.
CEREBRAS_API_KEY: str = os.environ.get("CEREBRAS_API_KEY", "")

# --- CAPTCHA solving ---
CAPSOLVER_API_KEY: str = os.environ.get("CAPSOLVER_API_KEY", "")
TWOCAPTCHA_API_KEY: str = os.environ.get("TWOCAPTCHA_API_KEY", "")

# --- JWT ---
# Fail-closed posture (B021): if no env var is supplied, auto-mint a per-install
# random secret and persist it to ~/.anticipy/secrets.json (0600). This way the
# bundled DMG no longer logs the "insecure development default" warning at
# every startup, AND every stranger install gets its own unique signing key.
JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    JWT_SECRET = str(_PERSISTED_SECRETS.get("JWT_SECRET") or "")
    if not JWT_SECRET:
        JWT_SECRET = _stdsecrets.token_urlsafe(48)
        _PERSISTED_SECRETS["JWT_SECRET"] = JWT_SECRET
        _persist_secrets(_PERSISTED_SECRETS)
        _logger.info("Minted new JWT_SECRET and persisted to ~/.anticipy/secrets.json")
elif len(JWT_SECRET) < 32 and IS_PRODUCTION:
    raise RuntimeError("JWT_SECRET must be at least 32 characters in production.")

JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_HOURS: int = 72

# --- Server-to-server token for /execute-intent (Next.js → engine bridge) ---
ENGINE_INTERNAL_TOKEN: str = os.environ.get("ENGINE_INTERNAL_TOKEN", "")

# --- Budget limits (hard caps) ---
MAX_STEPS: int = 40
MAX_SECONDS: int = 300
MAX_COST_USD: float = 0.08

# --- Agent tuning ---
VERIFY_EVERY_N_STEPS: int = 7
LOOP_DETECTION_THRESHOLD: int = 3
MAX_LABELED_ELEMENTS: int = 20
MEMORY_MAX_CHARS: int = 300

# --- Security ---
# B021: If no env var supplied, mint a real Fernet key, persist it to
# ~/.anticipy/secrets.json (0600), and reuse across restarts so saved cookies
# keep decrypting. Stranger installs no longer get a "derived development key"
# warning, and the cookie store survives engine restarts.
_PROFILE_KEY_RAW: str = os.environ.get("PROFILE_ENCRYPTION_KEY", "")
if _PROFILE_KEY_RAW:
    PROFILE_ENCRYPTION_KEY: str = _PROFILE_KEY_RAW
else:
    _stored = str(_PERSISTED_SECRETS.get("PROFILE_ENCRYPTION_KEY") or "")
    if _stored:
        PROFILE_ENCRYPTION_KEY = _stored
    else:
        PROFILE_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
        _PERSISTED_SECRETS["PROFILE_ENCRYPTION_KEY"] = PROFILE_ENCRYPTION_KEY
        _persist_secrets(_PERSISTED_SECRETS)
        _logger.info("Minted new PROFILE_ENCRYPTION_KEY and persisted to ~/.anticipy/secrets.json")

# Validate the key actually loads as Fernet (catches malformed values early)
try:
    Fernet(PROFILE_ENCRYPTION_KEY.encode())
except Exception as _e:
    raise RuntimeError(f"PROFILE_ENCRYPTION_KEY is not a valid Fernet key: {_e}")

MAX_INPUT_LENGTH: int = 2000
MAX_TASKS_PER_HOUR: int = 20
MAX_TASKS_PER_DAY: int = 100
MAX_COST_PER_DAY_USD: float = 0.50
LOGIN_MAX_FAILURES: int = 5
LOGIN_BLOCK_MINUTES: int = 30

# --- WebSocket abuse limits ---
WS_MAX_MESSAGES_PER_MINUTE: int = 60
WS_MAX_MESSAGE_BYTES: int = 8 * 1024  # raw frame size cap
WS_REQUIRE_AUTH: bool = os.environ.get("WS_REQUIRE_AUTH", "true").lower() in _TRUTHY

# --- Username / password rules ---
USERNAME_MIN_LEN: int = 3
USERNAME_MAX_LEN: int = 32
PASSWORD_MIN_LEN: int = 8
PASSWORD_MAX_LEN: int = 256

# --- Admin allow-list (comma-separated usernames) ---
ADMIN_USERNAMES: list[str] = [
    u.strip() for u in os.environ.get("ENGINE_ADMIN_USERNAMES", "").split(",") if u.strip()
]

# --- Browser ---
BROWSER_PROFILE_BASE: str = "/tmp/engine_profiles"
BROWSER_ACTION_TIMEOUT: int = 10000
BROWSER_NAV_TIMEOUT: int = 15000
MAX_BROWSER_TASKS: int = 50  # restart browser after this many tasks

# --- Model fallback chain ---
# Each entry: (name, base_url, api_key_value, model_id, cost_per_1k_input, cost_per_1k_output)
MODEL_CHAIN: list[dict] = []


def _build_model_chain() -> list[dict]:
    """Build the ordered fallback chain from available keys.

    `min_interval_seconds` is the minimum spacing between requests to that
    provider. The shared throttle in app.models honors it on every call so
    fan-out (asyncio.gather) does not exceed the provider's free-tier rate
    limit. 0 means "no spacing" — the throttle is a no-op for that provider.
    """
    chain: list[dict] = []
    # 4-tier provider redundancy. Order is by historical reliability,
    # NOT capability — every plan uses that provider's best-available
    # model at the same instruction-following tier (70B-class) so a
    # fallover doesn't degrade quality.
    #
    # Plan A — Gemini 2.5 Flash. Primary speed/cost. 1M ctx.
    if GOOGLE_API_KEY:
        chain.append(
            {
                "name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "api_key": GOOGLE_API_KEY,
                "model": "gemini-2.5-flash",
                "cost_input": 0.0001,
                "cost_output": 0.0004,
                "min_interval_seconds": 0.0,
            }
        )
    # Plan B — Groq llama-3.3-70b-versatile. 128k ctx, very fast.
    if GROQ_API_KEY:
        chain.append(
            {
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": GROQ_API_KEY,
                "model": "llama-3.3-70b-versatile",
                "cost_input": 0.00059,
                "cost_output": 0.00079,
                "min_interval_seconds": 0.0,
            }
        )
    # Plan C — Mistral La Plateforme (replaces forbidden Kimi/Moonshot per
    # v-final-prototype whitelist 2026-05-13). 262K ctx, free tier.
    if MISTRAL_API_KEY:
        chain.append(
            {
                "name": "mistral",
                "base_url": "https://api.mistral.ai/v1",
                "api_key": MISTRAL_API_KEY,
                "model": "mistral-small-latest",
                "cost_input": 0.0,
                "cost_output": 0.0,
                "min_interval_seconds": 1.2,
            }
        )
    # Plan D — DeepSeek. OpenAI-compat API. 128k ctx. Positioned last
    # because the team's account has been credit-exhausted for stretches
    # — promotes to higher position when credits return (no code change
    # needed; just changes the order of the appends).
    if DEEPSEEK_API_KEY:
        chain.append(
            {
                "name": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": DEEPSEEK_API_KEY,
                "model": "deepseek-chat",
                "cost_input": 0.00014,
                "cost_output": 0.00028,
                "min_interval_seconds": 0.0,
            }
        )
    return chain


MODEL_CHAIN = _build_model_chain()


# ─────────────────────────────────────────────────────────────────────────
# Role-based chains — multi-agent diversity.
#
# Quality research (Online-Mind2Web, WebArena SOTA) shows scaffolding > model
# capability and that single-model self-critique degenerates: the same model
# rationalizes the same errors. Different families per role break the
# rationalization loop.
#
# Role assignments (each role's PRIMARY then FALLBACK). Refreshed
# 2026-05-13: Kimi/Moonshot removed (forbidden by v-final-prototype
# whitelist); Mistral now slots in via mistral-small-latest.
#   planner   : Gemini 2.5 Flash  → Cerebras Qwen3-235b → Mistral-small → Groq
#   critic    : Mistral-small     → Gemini 2.5 Flash    → Cerebras Qwen3 → Groq
#   reflector : Gemini 2.5 Flash  → Cerebras Qwen3-235b → Mistral-small → Groq
#   executor  : Cerebras Qwen3    → Mistral-small       → Gemini Flash  → Groq
#
# When the primary for a role is not configured (no key), we fall through
# in role order to the next configured provider rather than collapsing to a
# single chain — preserves diversity even with partial keys.
# ─────────────────────────────────────────────────────────────────────────


def _provider_gemini() -> dict | None:
    if not GOOGLE_API_KEY:
        return None
    return {
        "name": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key": GOOGLE_API_KEY,
        "model": "gemini-2.5-flash",
        "cost_input": 0.0001,
        "cost_output": 0.0004,
        "min_interval_seconds": 0.0,
    }


def _provider_groq() -> dict | None:
    if not GROQ_API_KEY:
        return None
    return {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": GROQ_API_KEY,
        "model": "llama-3.3-70b-versatile",
        "cost_input": 0.00059,
        "cost_output": 0.00079,
        "min_interval_seconds": 0.0,
    }


def _provider_kimi() -> dict | None:
    """Forbidden by v-final-prototype provider whitelist (2026-05-13).
    Permanent no-op; callers that import this get None back. Kept as a
    declared symbol so any lingering reference fails loud at runtime rather
    than silently."""
    return None


def _provider_mistral() -> dict | None:
    """Mistral La Plateforme. Verified live 2026-05-13 against /v1/models —
    `mistral-small-latest` aliases mistral-small-2603 (262K ctx, vision +
    tools + reasoning) and was the right balance of capability/cost for the
    role chain. The previous ``pixtral-12b-2409`` returned 404 against the
    current Mistral catalog (vision is now under pixtral-large-2411)."""
    if not MISTRAL_API_KEY:
        return None
    return {
        "name": "mistral",
        "base_url": "https://api.mistral.ai/v1",
        "api_key": MISTRAL_API_KEY,
        "model": "mistral-small-latest",
        "cost_input": 0.0,    # free tier
        "cost_output": 0.0,
        "min_interval_seconds": 1.2,  # free tier ~1 req/sec
    }


def _provider_cerebras() -> dict | None:
    """Cerebras inference — extremely low-latency. OpenAI-compat.

    Verified live 2026-05-10: catalog is gpt-oss-120b, qwen-3-235b-a22b-instruct-2507,
    zai-glm-4.7, llama3.1-8b. The previous ``llama-3.3-70b`` returned 404.
    """
    if not CEREBRAS_API_KEY:
        return None
    return {
        "name": "cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key": CEREBRAS_API_KEY,
        "model": "qwen-3-235b-a22b-instruct-2507",
        "cost_input": 0.0,    # free tier as of 2026-05
        "cost_output": 0.0,
        "min_interval_seconds": 0.0,
    }


def _filter_none(*entries: dict | None) -> list[dict]:
    return [e for e in entries if e is not None]


def _build_role_chains() -> dict[str, list[dict]]:
    """Order each role chain so the primary is FIRST. Fallbacks follow.

    A role chain that becomes empty (no providers configured at all)
    falls back to ``MODEL_CHAIN`` at runtime via ``_chain_for_role``.
    """
    return {
        "planner": _filter_none(
            _provider_gemini(),
            _provider_cerebras(),
            _provider_mistral(),
            _provider_groq(),
        ),
        "critic": _filter_none(
            _provider_mistral(),
            _provider_gemini(),
            _provider_cerebras(),
            _provider_groq(),
        ),
        "reflector": _filter_none(
            _provider_gemini(),
            _provider_cerebras(),
            _provider_mistral(),
            _provider_groq(),
        ),
        "executor": _filter_none(
            _provider_cerebras(),
            _provider_mistral(),
            _provider_gemini(),
            _provider_groq(),
        ),
    }


ROLE_CHAINS: dict[str, list[dict]] = _build_role_chains()


# --- Cost watch (audit trail) ---
# Hard cap on month-to-date paid LLM spend per process. Set to 0 to disable
# the runtime check. The cost watch logs every paid call to Supabase regardless.
COST_MONTHLY_CAP_USD: float = float(
    os.environ.get("COST_MONTHLY_CAP_USD", "10.0") or "10.0"
)

# Cerebras spend awareness (the L4 voter layer in v-final-prototype will read
# these). Real enforcement is configured at the Cerebras account dashboard;
# these constants exist so the runtime can log "approaching cap" warnings
# without inventing values. Set to 0.0 to disable awareness logging.
CEREBRAS_SOFT_CAP_USD: float = float(
    os.environ.get("CEREBRAS_SOFT_CAP_USD", "0.0") or "0.0"
)
CEREBRAS_HARD_CAP_USD: float = float(
    os.environ.get("CEREBRAS_HARD_CAP_USD", "0.0") or "0.0"
)


# --- Required env vars for production ---
REQUIRED_ENV_VARS: list[str] = [
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
]


# --- Quiet mode (passive engine) ---
# When ANTICIPY_QUIET=1, every proactive background path that opens a
# Chrome tab without an explicit user request is skipped. On-demand
# paths (user-issued action engine commands, surface runtime navigate
# triggered by a typed task) are unchanged. The audit at
# planning/00-handoff/TAB_OPEN_AUDIT.md lists every call site this
# affects.
def _quiet_mode_enabled() -> bool:
    """True when ANTICIPY_QUIET is set to a truthy value.

    Read fresh from the environment on every call so a process that
    inherits the env mid-life sees it consistently. The check is
    intentionally permissive: 1, true, yes, on (case-insensitive).
    """
    raw = (os.environ.get("ANTICIPY_QUIET") or "").strip().lower()
    return raw in _TRUTHY
