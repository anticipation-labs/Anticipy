"""Browser-use BRIDGE RUNNER — the open-source browser arm as a SEPARATE PROCESS.

Slice 6 step 3. This file is EXECUTED by the durable 3.11 bridge venv
(engine/.bu-venv), NEVER imported by the 3.10 engine. It is the only place
`browser_use` is imported, because browser-use needs Python >=3.11 and the
engine runs on 3.10.14.

Protocol (dead simple, language-agnostic, subprocess-friendly):
  - stdin : ONE JSON object {"task": str, "url"?: str, "structured"?: bool,
            "max_steps"?: int}
  - stdout: ONE JSON object {"success": bool, "result": str|None,
            "steps": int, "url": str|None, "urls": [...], "actions": [...],
            "structured": bool, "error"?: str}
            (a single line tagged with a sentinel so the engine can parse it
            even if browser-use logs noise to stdout/stderr)

It reuses the PROVEN /tmp/bu-spike harness exactly:
  browser-use 0.13.1 (MIT) + OUR OpenRouter model (ANTICIPY_MODEL_SMART) +
  cached chromium-1161 + a throwaway temp profile, READ-ONLY.

Guardrails honored:
  - READ-ONLY public pages only; the task text forbids login/form/write/money.
  - browser-use's OWN throwaway browser (cached Chromium + a unique temp
    user_data_dir under the system temp dir), NEVER the user's real Chrome.
  - never touches engine/.venv.
"""
import asyncio
import json
import os
import sys
import tempfile
import time

# Sentinel so the engine can find OUR json line amid any browser-use log noise.
RESULT_SENTINEL = "__ANTICIPY_BU_RESULT__"

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-2.5-flash"
# Proven cached Chromium (classic chromium-1161 layout works under
# --single-process here, unlike the newer Chrome-for-Testing build).
CHROME_BIN = (
    "/Users/omarebrahim/Library/Caches/ms-playwright/chromium-1161/"
    "chrome-mac/Chromium.app/Contents/MacOS/Chromium"
)

# Appended to every task so the model is told, in-band, this is read-only.
_READONLY_GUARD = (
    " This is READ-ONLY: do not log in, do not submit any form, do not click "
    "buttons that change state, do not upvote/post/purchase/checkout, do not "
    "solve captchas. Only read the page."
)
_STRUCTURED_GUARD = " Return ONLY a single JSON object, no prose."


def _load_env(env_path: str) -> dict:
    env = {}
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def _emit(payload: dict) -> None:
    """Print exactly one sentinel-tagged JSON line; the engine parses this."""
    sys.stdout.write(RESULT_SENTINEL + json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def _build_task(req: dict) -> str:
    task = str(req.get("task") or "").strip()
    url = str(req.get("url") or "").strip()
    # If a url is given but the task doesn't already point there, prepend a
    # concrete navigation so the agent has a destination (mirrors the spike).
    if url and url not in task:
        task = f"Go to {url} . {task}"
    task = task + _READONLY_GUARD
    if req.get("structured"):
        task = task + _STRUCTURED_GUARD
    return task


async def _run(req: dict) -> dict:
    # Import here (not at module top) so a malformed request still produces a
    # clean json error without paying browser-use import cost first.
    from browser_use import Agent, BrowserProfile, BrowserSession, ChatOpenAI

    repo_env_path = os.environ.get(
        "ANTICIPY_ENV_PATH", "/Users/omarebrahim/Anticipy/.env.local"
    )
    env = _load_env(repo_env_path)
    api_key = os.environ.get("OPENROUTER_API_KEY") or env.get("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "success": False,
            "result": None,
            "steps": 0,
            "url": req.get("url"),
            "error": "OPENROUTER_API_KEY missing (not in env or .env.local)",
        }
    model = (
        os.environ.get("ANTICIPY_MODEL_SMART")
        or env.get("ANTICIPY_MODEL_SMART")
        or DEFAULT_MODEL
    )

    chrome_bin = os.environ.get("ANTICIPY_BU_CHROME_BIN", CHROME_BIN)
    if not os.path.exists(chrome_bin):
        return {
            "success": False,
            "result": None,
            "steps": 0,
            "url": req.get("url"),
            "error": f"chrome binary missing: {chrome_bin}",
        }

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=OPENROUTER_BASE,
        temperature=0.0,
        default_headers={
            "HTTP-Referer": "https://anticipy.local/bridge",
            "X-Title": "Anticipy Slice6 BrowserBridge",
        },
    )

    # Unique throwaway profile under the system temp dir; NEVER user's Chrome.
    prof_dir = tempfile.mkdtemp(prefix="anticipy-bu-profile-")
    profile = BrowserProfile(
        executable_path=chrome_bin,
        user_data_dir=prof_dir,
        headless=True,
        chromium_sandbox=False,
        args=[
            "--no-zygote",
            "--single-process",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
        ],
    )

    max_steps = int(req.get("max_steps") or 10)
    task = _build_task(req)

    session = BrowserSession(browser_profile=profile)
    out = {
        "success": False,
        "result": None,
        "steps": 0,
        "url": req.get("url"),
        "urls": [],
        "actions": [],
        "structured": bool(req.get("structured")),
    }
    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser_session=session,
            max_actions_per_step=3,
            use_vision=False,  # text-only DOM extraction: cheap + deterministic
        )
        history = await agent.run(max_steps=max_steps)
        out["result"] = history.final_result()
        try:
            out["urls"] = history.urls()
            if out["urls"]:
                out["url"] = out["urls"][-1]
        except Exception:
            pass
        try:
            out["actions"] = history.action_names()
        except Exception:
            pass
        try:
            out["steps"] = len(history.urls() or [])
        except Exception:
            out["steps"] = max_steps
        # Honest success: the runner only claims success when browser-use
        # itself reports done WITH a non-empty final result. Never invent it.
        is_done = False
        try:
            is_done = bool(history.is_done())
        except Exception:
            is_done = bool(out["result"])
        out["success"] = bool(is_done and out["result"])
    except Exception as e:
        out["success"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        try:
            await session.kill()
        except Exception:
            pass
    return out


def main() -> None:
    raw = sys.stdin.read()
    t0 = time.time()
    try:
        req = json.loads(raw)
        if not isinstance(req, dict):
            raise ValueError("request must be a JSON object")
    except Exception as e:
        _emit(
            {
                "success": False,
                "result": None,
                "steps": 0,
                "url": None,
                "error": f"bad request json: {type(e).__name__}: {e}",
            }
        )
        return
    try:
        out = asyncio.run(_run(req))
    except Exception as e:
        out = {
            "success": False,
            "result": None,
            "steps": 0,
            "url": req.get("url"),
            "error": f"runner crash: {type(e).__name__}: {e}",
        }
    out["elapsed_s"] = round(time.time() - t0, 1)
    _emit(out)


if __name__ == "__main__":
    main()
