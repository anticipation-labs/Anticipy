"""
Unit tests for the non-browser helper functions in app.agent.

The browser-driven path (`execute_task`, `BrowserAgent.run`) needs Browser
Use + a real Chromium and is exercised by `test_torture_browser.py`. This
file covers the small deterministic helpers that ship with agent.py and
the env-var initialization side effects on import:

  - `_clean_chromium_lock_files(profile_dir)` — removes Singleton* files
    (the cluster that blocked F-TBR-1's retry recovery)
  - `_get_domain(url)` — URL → bare domain helper used for cookie scoping
  - `_looks_like_login(url, page_text)` — generic login-wall sniffer used
    by the safety / graceful-decline path
  - `_sanitize_status(text)` — strips technical noise from agent status
    messages before they hit the user-facing channel
  - `os.environ` side effects on import: TIMEOUT_BrowserStartEvent and
    TIMEOUT_BrowserLaunchEvent must be set so Browser Use's import-time
    `_get_timeout(...)` reads them

These tests run without spawning Chromium. They cover the shape that
`test_torture_browser` depends on (so a regression here would manifest as
infrastructure failures in the heavier suite — much cheaper to catch here).
"""

from __future__ import annotations

import os
import sys
import tempfile

# Required env BEFORE importing app.agent (which imports browser_use, which
# touches PROFILE_ENCRYPTION_KEY / JWT_SECRET via app.config).
os.environ.setdefault("JWT_SECRET", "x" * 48)
os.environ.setdefault(
    "PROFILE_ENCRYPTION_KEY",
    "RoUzc1lJ3gkPkHrxoYQzv1trmEJSQbgo6mNhlQYgfJk=",
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import agent as agent_module  # noqa: E402


# --- _clean_chromium_lock_files ----------------------------------------------


def test_clean_lock_files_removes_singleton_files():
    """All three Singleton* files in a profile dir get removed."""
    with tempfile.TemporaryDirectory() as d:
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            with open(os.path.join(d, name), "w") as f:
                f.write("stale")
        # Drop a non-Singleton file too — it must NOT be touched
        with open(os.path.join(d, "Cookies"), "w") as f:
            f.write("real cookies")

        agent_module._clean_chromium_lock_files(d)

        assert not os.path.exists(os.path.join(d, "SingletonLock"))
        assert not os.path.exists(os.path.join(d, "SingletonCookie"))
        assert not os.path.exists(os.path.join(d, "SingletonSocket"))
        # Non-singleton state is preserved — losing real cookies on retry
        # would re-prompt every login the user already completed.
        assert os.path.exists(os.path.join(d, "Cookies"))
        with open(os.path.join(d, "Cookies")) as f:
            assert f.read() == "real cookies"


def test_clean_lock_files_handles_missing_dir():
    """Pointing at a non-existent directory must not raise."""
    agent_module._clean_chromium_lock_files("/tmp/this-does-not-exist-aaaaaa")
    agent_module._clean_chromium_lock_files("")
    agent_module._clean_chromium_lock_files(None)  # type: ignore[arg-type]


def test_clean_lock_files_handles_empty_dir():
    """Empty profile dir → no-op, no exception."""
    with tempfile.TemporaryDirectory() as d:
        agent_module._clean_chromium_lock_files(d)
        # Dir still exists, still empty
        assert os.listdir(d) == []


def test_clean_lock_files_handles_partial_singletons():
    """Only one of the three present → only that one removed, no error."""
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "SingletonLock"), "w") as f:
            f.write("")
        agent_module._clean_chromium_lock_files(d)
        assert not os.path.exists(os.path.join(d, "SingletonLock"))


def test_clean_lock_files_handles_singleton_as_symlink():
    """SingletonLock can be a dangling symlink (Chromium sometimes writes
    it that way). `os.lexists` + `os.remove` must handle it — never raise."""
    with tempfile.TemporaryDirectory() as d:
        target = os.path.join(d, "non-existent-target")
        link_path = os.path.join(d, "SingletonLock")
        os.symlink(target, link_path)
        assert os.path.lexists(link_path)
        agent_module._clean_chromium_lock_files(d)
        assert not os.path.lexists(link_path)


# --- import-time env vars ----------------------------------------------------


def test_browser_start_event_timeout_env_set():
    """The import of agent.py must have set the 90s timeout vars (if they
    weren't already set). browser-use 0.11.13's `_get_timeout` reads these
    at module-import time on its side, so we guarantee they're set before
    `from browser_use import ...` lands."""
    v = os.environ.get("TIMEOUT_BrowserStartEvent")
    assert v is not None and v != "", "TIMEOUT_BrowserStartEvent must be set"
    assert float(v) >= 60, f"timeout {v} must be ≥ 60s for slow codespaces"


def test_browser_launch_event_timeout_env_set():
    v = os.environ.get("TIMEOUT_BrowserLaunchEvent")
    assert v is not None and v != ""
    assert float(v) >= 60


# --- _get_domain -------------------------------------------------------------


def test_get_domain_strips_scheme_and_path():
    """Helper returns the netloc only (no scheme, no path)."""
    assert agent_module._get_domain("https://www.example.com/foo/bar?x=1") == "www.example.com"


def test_get_domain_keeps_subdomain():
    """Subdomains are preserved so cookies for mail.google.com and
    accounts.google.com are saved under distinct keys."""
    assert agent_module._get_domain("https://mail.google.com/inbox") == "mail.google.com"


def test_get_domain_handles_non_url():
    """Garbage input must not crash the cookie flow."""
    assert agent_module._get_domain("") == ""
    # urlparse is permissive; "not a url" returns "" netloc.
    assert agent_module._get_domain("not a url") == ""
    # http:// with no netloc → empty
    assert agent_module._get_domain("http://") == ""


# --- _looks_like_login -------------------------------------------------------


def test_looks_like_login_recognizes_login_url():
    """Generic — pattern in the URL path tells us we're at a login page."""
    assert agent_module._looks_like_login(
        "https://example.com/login",
        "Sign in to continue",
    )


def test_looks_like_login_recognizes_signin_text():
    assert agent_module._looks_like_login(
        "https://example.com/account",
        "Please sign in to continue",
    )


def test_looks_like_login_negative_for_normal_page():
    assert not agent_module._looks_like_login(
        "https://example.com/articles/foo",
        "This article is about how to log into your account.",
    )


# --- _sanitize_status --------------------------------------------------------


def test_sanitize_status_replaces_javascript_term():
    """LLMs leak technical terms. We swap them for end-user-friendly phrasing
    before the status hits the user-facing channel."""
    out = agent_module._sanitize_status("Run a JavaScript snippet to read the field")
    assert "javascript" not in out.lower()
    assert "script" in out.lower()


def test_sanitize_status_replaces_browser_terms():
    out = agent_module._sanitize_status("Use Playwright to access the iframe")
    assert "playwright" not in out.lower()
    assert "iframe" not in out.lower()


def test_sanitize_status_passthrough_clean_text():
    raw = "Opening the website..."
    assert agent_module._sanitize_status(raw) == raw


def test_sanitize_status_handles_empty():
    assert agent_module._sanitize_status("") == ""


# --- RAG context helpers -----------------------------------------------------
#
# `_format_retrieved_examples`, `_format_wearer_memories`, and
# `_build_system_rules_with_context` are all pure-string helpers on the
# agent module. They drive what shows up inside `<retrieved_examples>` and
# `<wearer_memories>` blocks before a Browser Use Agent is constructed.
# Lightweight tests here so a regression doesn't only surface as a
# silently-broken RAG path inside a 5-minute browser run.


def test_format_retrieved_examples_renders_basic_shape():
    out = agent_module._format_retrieved_examples([
        {
            "domain": "en.wikipedia.org",
            "task_summary": "Look up Python release year",
            "outcome": "success",
            "similarity": 0.91,
            "steps": [
                {"action": "navigate", "url": "https://en.wikipedia.org/wiki/Python"},
                {"action": "extract", "field": "release_year"},
                {"action": "done", "message": "1991"},
            ],
        }
    ])
    assert "en.wikipedia.org" in out
    assert "Python release year" in out
    assert "navigate" in out
    assert "extract" in out
    # similarity rendered with 2 decimals
    assert "0.91" in out


def test_format_retrieved_examples_empty_input_returns_empty_string():
    assert agent_module._format_retrieved_examples([]) == ""


def test_format_retrieved_examples_caps_step_count_at_three():
    """A 25-step trajectory must not blow up the system prompt."""
    steps = [
        {"action": "navigate", "url": f"https://example.com/{i}"}
        for i in range(25)
    ]
    out = agent_module._format_retrieved_examples([
        {"domain": "x.com", "task_summary": "long task",
         "outcome": "success", "similarity": 0.9, "steps": steps},
    ])
    # We render at most 3 steps per row → at most 3 navigate lines
    assert out.count("navigate") <= 3


def test_format_wearer_memories_renders_kind_key_and_value():
    class _M:
        kind = "person"
        key = "sarah"
        value = {"name": "Sarah", "relation": "friend",
                 "notes": "loves italian food"}
    out = agent_module._format_wearer_memories([_M()])
    assert "person" in out
    assert "sarah" in out
    assert "Sarah" in out
    assert "friend" in out


def test_format_wearer_memories_empty_returns_empty_string():
    assert agent_module._format_wearer_memories([]) == ""


def test_build_system_rules_omits_empty_blocks():
    """No examples / no memories → only the base rules, no empty headers
    polluting the prompt."""
    out = agent_module._build_system_rules_with_context("", "")
    assert "<retrieved_examples>" not in out
    assert "<wearer_memories>" not in out
    # And the base rules are still in there
    assert "ADDITIONAL RULES" in out


def test_build_system_rules_injects_blocks_when_present():
    out = agent_module._build_system_rules_with_context(
        examples_block="[1] domain=x.com\n    task: foo",
        memories_block="- (person) sarah: name=Sarah",
    )
    assert "<retrieved_examples>" in out
    assert "</retrieved_examples>" in out
    assert "<wearer_memories>" in out
    assert "</wearer_memories>" in out
    assert "[1]" in out
    assert "Sarah" in out


def test_build_system_rules_injects_only_examples():
    out = agent_module._build_system_rules_with_context(
        examples_block="[1] domain=x.com",
        memories_block="",
    )
    assert "<retrieved_examples>" in out
    assert "<wearer_memories>" not in out


# --- _prewarm_chromium -------------------------------------------------------
#
# These tests use a small context-manager helper instead of pytest's
# `monkeypatch` fixture so the file's standalone __main__ runner (which
# doesn't inject fixtures) can still execute every test the same way pytest
# does. The 17 tests above this section don't depend on monkeypatch — keep it
# that way.


class _Patch:
    """Tiny stand-in for monkeypatch — restores attrs on __exit__."""

    def __init__(self) -> None:
        self._undo: list[tuple[object, str, object, bool]] = []

    def setattr(self, target: object, name: str, value: object) -> None:
        had = hasattr(target, name)
        old = getattr(target, name, None)
        self._undo.append((target, name, old, had))
        setattr(target, name, value)

    def __enter__(self) -> "_Patch":
        return self

    def __exit__(self, *exc: object) -> None:
        for target, name, old, had in reversed(self._undo):
            if had:
                setattr(target, name, old)
            else:
                try:
                    delattr(target, name)
                except AttributeError:
                    pass


def test_prewarm_chromium_callable_and_idempotent():
    """Second call must NOT re-spawn the subprocess. The module-level
    `_PREWARM_DONE` guard short-circuits subsequent calls so we don't burn
    a 5s timeout on every task — just on the first one per process."""
    import subprocess as _subprocess

    spawn_calls: list[list[str]] = []

    def _fake_run(cmd, **kwargs):
        spawn_calls.append(list(cmd))

        class _R:
            returncode = 0

        return _R()

    with _Patch() as p:
        p.setattr(agent_module, "_PREWARM_DONE", False)
        p.setattr(_subprocess, "run", _fake_run)
        # Force a known-good binary path so we don't depend on the host env.
        p.setattr(
            agent_module, "_find_chromium_binary", lambda: "/usr/bin/fake-chrome"
        )

        agent_module._prewarm_chromium()
        assert len(spawn_calls) == 1, "first call must spawn"
        assert spawn_calls[0][0] == "/usr/bin/fake-chrome"

        agent_module._prewarm_chromium()
        agent_module._prewarm_chromium()
        assert len(spawn_calls) == 1, (
            "subsequent calls must be no-ops (idempotent guard broken)"
        )


def test_prewarm_chromium_skips_when_binary_missing():
    """If no Chromium can be found (unusual platform, fresh container before
    Playwright install) we must still return cleanly — engine startup must
    not be blocked by a missing optional pre-warm."""
    import subprocess as _subprocess

    spawn_calls: list[list[str]] = []

    def _track(cmd, **kwargs):
        spawn_calls.append(list(cmd))

    with _Patch() as p:
        p.setattr(agent_module, "_PREWARM_DONE", False)
        p.setattr(agent_module, "_find_chromium_binary", lambda: None)
        p.setattr(_subprocess, "run", _track)

        # Must not raise.
        agent_module._prewarm_chromium()
        assert spawn_calls == [], "no spawn when binary not found"


def test_prewarm_chromium_swallows_subprocess_errors():
    """A timeout / permission / OOM error from the spawn must NEVER raise
    out of _prewarm_chromium — pre-warming is best-effort."""
    import subprocess as _subprocess

    def _boom(*args, **kwargs):
        raise _subprocess.TimeoutExpired(cmd=args[0], timeout=5)

    with _Patch() as p:
        p.setattr(agent_module, "_PREWARM_DONE", False)
        p.setattr(
            agent_module, "_find_chromium_binary", lambda: "/usr/bin/fake-chrome"
        )
        p.setattr(_subprocess, "run", _boom)

        # Must not raise — the engine can't refuse to start because of a slow
        # or hung Chromium binary.
        agent_module._prewarm_chromium()


def test_find_chromium_binary_returns_string_or_none():
    """Result is either an executable path string or None — no
    exceptions, no other types."""
    result = agent_module._find_chromium_binary()
    assert result is None or isinstance(result, str)
    if result is not None:
        # If we report a path, it must actually exist and be executable.
        assert os.path.isfile(result), f"reported missing binary: {result}"
        assert os.access(result, os.X_OK), f"reported non-executable: {result}"


# --- runner ------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print(f"running {len(tests)} tests...")
    failed: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, f"AssertionError: {e}"))
            print(f"  FAIL  {name}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}  ({type(e).__name__}: {e})")

    print()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
