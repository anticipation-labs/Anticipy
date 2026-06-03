"""Load local secrets from the repo's .env.local into the engine process.

Local-first: keys live in .env.local (gitignored). This makes them available via
os.environ without overriding anything already set in the real environment.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_local_env() -> Optional[Path]:
    # engine/anticipy_engine/core/env.py -> parents[3] == repo root
    root = Path(__file__).resolve().parents[3]
    env_path = root / ".env.local"
    if env_path.exists():
        load_dotenv(env_path, override=False)
        return env_path
    return None
