"""The gates were starved, not broken.

`done_gate` spent this session reporting "no model key, so her judgement
cannot be measured" and sending every agent at leg 3, while
`OPENROUTER_API_KEY` sat in `.env.local` in the same directory. With the file
loaded, legs 3 and 4 both pass and the first failing leg is 6 — the finish
line. A scoreboard that names the wrong leg is worse than no scoreboard,
because CLAUDE.md tells you to believe it and work only that leg.
"""
import os
import textwrap

import pytest

from overnight import _env


def _write(tmp_path, body):
    p = tmp_path / ".env.local"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_loads_plain_pairs(tmp_path, monkeypatch):
    _write(tmp_path, """
        OPENROUTER_API_KEY=sk-abc123
        ANTICIPY_MODEL=google/gemini-2.5-flash
    """)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTICIPY_MODEL", raising=False)
    loaded = _env.load(tmp_path)
    assert os.environ["OPENROUTER_API_KEY"] == "sk-abc123"
    assert os.environ["ANTICIPY_MODEL"] == "google/gemini-2.5-flash"
    assert "OPENROUTER_API_KEY" in loaded


def test_explicit_environment_wins(tmp_path, monkeypatch):
    """A key already in the environment is the operator being deliberate.

    CI sets a scratch key; the file holds the real one. If the file won, a
    run you believed was pointed at a test backend would quietly be pointed
    at production, and it would report green.
    """
    _write(tmp_path, "OPENROUTER_API_KEY=from-file\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-operator")
    loaded = _env.load(tmp_path)
    assert os.environ["OPENROUTER_API_KEY"] == "from-operator"
    assert "OPENROUTER_API_KEY" not in loaded


def test_quotes_comments_export_and_blank_lines(tmp_path, monkeypatch):
    _write(tmp_path, """
        # a comment
        export ANTICIPY_BACKEND_URL="https://example.test"

          ANTICIPY_OWNER_ID='omar'
        EMPTY=
    """)
    for k in ("ANTICIPY_BACKEND_URL", "ANTICIPY_OWNER_ID", "EMPTY"):
        monkeypatch.delenv(k, raising=False)
    _env.load(tmp_path)
    assert os.environ["ANTICIPY_BACKEND_URL"] == "https://example.test"
    assert os.environ["ANTICIPY_OWNER_ID"] == "omar"
    assert os.environ["EMPTY"] == ""


def test_value_containing_equals_survives(tmp_path, monkeypatch):
    """Base64 secrets and query strings both carry '='. Splitting on every
    '=' truncates the key and the gate authenticates with a corrupt token,
    which fails as 'backend unreachable' and sends you debugging the network.
    """
    _write(tmp_path, "ANTICIPY_SERVICE_TOKEN=abc==def=ghi\n")
    monkeypatch.delenv("ANTICIPY_SERVICE_TOKEN", raising=False)
    _env.load(tmp_path)
    assert os.environ["ANTICIPY_SERVICE_TOKEN"] == "abc==def=ghi"


def test_missing_file_is_not_an_error(tmp_path):
    """A tree with no .env.local is the normal CI case. The gates must still
    run and report 'cannot be tested' honestly rather than crashing."""
    assert _env.load(tmp_path) == []


def test_never_returns_values(tmp_path, monkeypatch):
    """The return value is printed by every gate that calls it. It carries
    NAMES so a reader can see which credentials are in play, and never
    values, so a pasted gate log cannot leak a key."""
    _write(tmp_path, "OPENROUTER_API_KEY=sk-supersecret\n")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    loaded = _env.load(tmp_path)
    assert "sk-supersecret" not in " ".join(loaded)
    assert loaded == ["OPENROUTER_API_KEY"]


def test_load_and_announce_prints_names_never_values(tmp_path, monkeypatch, capsys):
    """Loading and announcing are one act. A gate that loaded a production
    key without saying so would print exactly what a gate that found nothing
    prints — which is the confusion this whole module exists to end."""
    (tmp_path / ".env.local").write_text("OPENROUTER_API_KEY=sk-supersecret\n")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    _env.load_and_announce(tmp_path)
    captured = capsys.readouterr()
    assert "OPENROUTER_API_KEY" in captured.err
    assert "sk-supersecret" not in captured.err
    # stdout stays clean: gates that emit JSON are parsed by other tools
    assert captured.out == ""


def test_announce_is_silent_when_nothing_loaded(tmp_path, capsys):
    """A tree with no .env.local must read exactly as it did before this
    module existed — no new noise in a CI log."""
    _env.load_and_announce(tmp_path)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
