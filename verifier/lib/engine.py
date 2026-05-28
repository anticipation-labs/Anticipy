"""
Engine helpers for the verifier.

Start/stop the engine, query its state, inject transcripts, trigger actions.
The engine entrypoint is engine/app/product/server.py (FastAPI).

The verifier does not assume how the engine is launched; it tries:
1. Reading ~/.anticipy/engine.port if Anticipy.app is installed and running
2. Falling back to launching uvicorn engine.app.product.server:app on a free port
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests


HOME_ENGINE_PORT_FILE = Path.home() / ".anticipy" / "engine.port"
DEFAULT_ENGINE_PORT = 8731


@dataclass(frozen=True)
class EngineHandle:
    url: str
    port: int
    process: subprocess.Popen | None = None

    @property
    def started(self) -> bool:
        return self.process is not None


def discover_engine_url(timeout: int = 30) -> str | None:
    """
    Find a running engine and return its base URL.

    ANTICIPY_ENGINE_URL wins when it is already healthy. Otherwise this falls
    back to the installed app port file and the development default port.
    """
    env_url = os.environ.get("ANTICIPY_ENGINE_URL", "").strip()
    if env_url and engine_url_healthy(env_url):
        return _normalize_engine_url(env_url)
    port = discover_engine_port(timeout=timeout)
    if port is None:
        return None
    return f"http://127.0.0.1:{port}"


def discover_engine_port(timeout: int = 30) -> int | None:
    """
    Find a running engine.
    Priority:
    1. If ~/.anticipy/engine.port exists and the port responds to /healthz, use it.
    2. If port 8731 responds to /healthz, use it (dev default).
    3. None.
    """
    if HOME_ENGINE_PORT_FILE.exists():
        try:
            port = int(HOME_ENGINE_PORT_FILE.read_text().strip())
            if _healthz_ok(port):
                return port
        except (ValueError, OSError):
            pass
    if _healthz_ok(DEFAULT_ENGINE_PORT):
        return DEFAULT_ENGINE_PORT
    return None


def ensure_engine(
    repo_root: Path,
    preferred_port: int | None = None,
    log_path: Path | None = None,
) -> EngineHandle:
    """
    Return a healthy local engine, starting one when discovery finds none.
    """
    url = discover_engine_url(timeout=1)
    if url:
        return EngineHandle(url=url, port=_port_from_url(url))

    port = preferred_port or int(os.environ.get("ANTICIPY_ENGINE_PORT") or DEFAULT_ENGINE_PORT)
    if port != DEFAULT_ENGINE_PORT and port <= 0:
        port = DEFAULT_ENGINE_PORT
    if not _port_available(port):
        port = _find_free_port()
    process = start_engine_subprocess(repo_root, port=port, log_path=log_path)
    return EngineHandle(url=f"http://127.0.0.1:{port}", port=port, process=process)


def engine_url_healthy(url: str) -> bool:
    return _healthz_url_ok(_normalize_engine_url(url))


def _normalize_engine_url(url: str) -> str:
    return url.rstrip("/")


def _port_from_url(url: str) -> int:
    parsed = urlparse(url)
    if parsed.port is None:
        raise ValueError(f"engine URL does not include a port: {url}")
    return parsed.port


def _healthz_url_ok(url: str) -> bool:
    try:
        r = requests.get(f"{url}/healthz", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


def _healthz_ok(port: int) -> bool:
    return _healthz_url_ok(f"http://127.0.0.1:{port}")


def start_engine_subprocess(
    repo_root: Path,
    port: int | None = None,
    log_path: Path | None = None,
) -> subprocess.Popen:
    """
    Spawn the engine as a subprocess for verifier-only test runs.
    Returns the Popen handle. Caller is responsible for terminate().
    """
    if port is None:
        port = _find_free_port()
    env = os.environ.copy()
    env["ANTICIPY_ENGINE_PORT"] = str(port)
    engine_path = str(repo_root / "engine")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        engine_path
        if not existing_pythonpath
        else f"{engine_path}{os.pathsep}{existing_pythonpath}"
    )
    stdout = subprocess.DEVNULL
    stderr = subprocess.DEVNULL
    log_handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "a", encoding="utf-8")
        stdout = log_handle
        stderr = subprocess.STDOUT
    p = subprocess.Popen(
        [
            "uv", "run", "uvicorn",
            "engine.app.product.server:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ],
        cwd=str(repo_root),
        env=env,
        stdout=stdout,
        stderr=stderr,
    )
    if log_handle is not None:
        log_handle.close()
    # Wait up to 60s for healthz
    for _ in range(60):
        if _healthz_ok(port):
            return p
        time.sleep(1)
    p.terminate()
    raise RuntimeError(f"engine did not become healthy on port {port}")


def stop_engine(p: subprocess.Popen, grace_secs: int = 5) -> None:
    p.terminate()
    try:
        p.wait(timeout=grace_secs)
    except subprocess.TimeoutExpired:
        p.kill()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def inject_transcript(port: int, text: str, timeout: int = 30) -> dict:
    """POST a transcript chunk to /api/listen/inject. Returns the response JSON."""
    r = requests.post(
        f"http://127.0.0.1:{port}/api/listen/inject",
        json={"text": text, "ts": time.time()},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def call_act(port: int, timeout: int = 600) -> dict:
    """POST /api/act, wait for completion. Returns the action result."""
    r = requests.post(
        f"http://127.0.0.1:{port}/api/act",
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def get_state(port: int, timeout: int = 10) -> dict:
    r = requests.get(f"http://127.0.0.1:{port}/api/state", timeout=timeout)
    r.raise_for_status()
    return r.json()


def query_dossier(port: int, user_id: str, key: str | None = None, timeout: int = 10) -> dict:
    params = {"user_id": user_id}
    if key:
        params["key"] = key
    r = requests.get(f"http://127.0.0.1:{port}/api/dossier", params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def upload_audio(port: int, audio_path: Path, timeout: int = 600) -> dict:
    """POST a wav or mp3 to /api/listen/upload."""
    with open(audio_path, "rb") as f:
        r = requests.post(
            f"http://127.0.0.1:{port}/api/listen/upload",
            files={"audio": (audio_path.name, f, "audio/mpeg" if audio_path.suffix == ".mp3" else "audio/wav")},
            timeout=timeout,
        )
    r.raise_for_status()
    return r.json()
