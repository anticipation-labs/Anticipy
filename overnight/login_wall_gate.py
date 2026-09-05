"""THE WALL GATE. Law 3 for Audit #70: the judgement that left the regexes is
measured where it now lives — in a model, over the transport the extension
uses — not in an offline test that can only pin the plumbing.

login_wall.js used to decide "is this page a login wall?" with sixteen
vocabulary regexes summed against a threshold. On 2026-09-05 that became ONE
question to a model (login_wall.js WALL_QUESTION), asked in the extension
through /agent/llm. extension/tests/test_wall_is_not_a_word_match.mjs pins
everything deterministic about it — when it is asked, what is sent, how the
four states are read, that nobody answering never parks. It cannot pin what
the model ANSWERS, and that is the whole point of the change. This gate does.

It sends the golden set (research/evals/login-wall-2026-09-05/fixtures.mjs —
every page the old regex suite pinned, plus the audit's own permit-form
example) through the extension's own message builder, so the bytes measured
are the bytes the extension sends, and compares each reply to the token a
person would give. RUNS times each, all of which must agree: a live model
varies run to run, and one green pass is not evidence.

Three verdicts, because a gate that cannot tell "green" from "could not look"
is the failure Law 3 exists to name:

    exit 0  PASS      every fixture right RUNS/RUNS, over the LIVE proxy
    exit 1  FAIL      a fixture wrong, on whichever transport was measured
    exit 2  UNPROVEN  the judgement could not be measured over the live proxy —
                      either no transport at all, or only the question was
                      measured (OpenRouter direct, not /agent/llm)

Transport, in order:
  * ANTICIPY_AGENT_ID + ANTICIPY_AGENT_TOKEN + ANTICIPY_BACKEND_URL — a paired
    agent's own credentials, the exact headers the extension sends. LIVE.
  * OPENROUTER_API_KEY — the same payload, straight to the provider. This
    measures the question and NOT the proxy (its model allowlist, its bounds,
    its audit row), so a green here is UNPROVEN, said out loud.
  The model is ANTICIPY_BROWSER_MODEL, else the extension's own default.

Run:
    python3 overnight/login_wall_gate.py
    python3 overnight/login_wall_gate.py --runs 1 --only permit_form_members_only_sidebar --verbose
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _env  # noqa: E402  sibling module; gates are run as scripts
_env.load_and_announce(ROOT)

DRIVER = os.path.join(ROOT, "research", "evals", "login-wall-2026-09-05", "messages.mjs")
# agent_loop.runAgentGoal's own default when the server names no model.
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


def arg(name: str, default: str) -> str:
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


RUNS = max(1, int(arg("--runs", "3")))
ONLY = arg("--only", "")


def note(msg: str) -> None:
    if VERBOSE:
        print(f"      {msg}")


class Unproven(Exception):
    """The gate could not look. Not a fail, not a pass."""


def golden() -> list[dict]:
    """The exact messages the extension builds, one per fixture."""
    from shutil import which
    if not which("node"):
        raise Unproven("node is not on PATH, so the extension's own message builder cannot run")
    out = subprocess.run(["node", DRIVER], capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0:
        raise Unproven(f"messages.mjs failed: {out.stderr.strip()[:300]}")
    rows = [json.loads(line) for line in out.stdout.splitlines() if line.strip()]
    if not rows:
        raise Unproven("messages.mjs printed no fixtures")
    if ONLY:
        rows = [r for r in rows if r["name"] == ONLY]
        if not rows:
            raise Unproven(f"no fixture named {ONLY!r}")
    return rows


def transport() -> tuple[str, str, dict, bool]:
    """(label, url, headers, live)."""
    agent_id = os.environ.get("ANTICIPY_AGENT_ID", "").strip()
    token = os.environ.get("ANTICIPY_AGENT_TOKEN", "").strip()
    base = (os.environ.get("ANTICIPY_BACKEND_URL") or "").strip().rstrip("/")
    if agent_id and token and base:
        return (f"LIVE {base}/agent/llm", f"{base}/agent/llm",
                {"Content-Type": "application/json",
                 "X-Anticipy-Agent-ID": agent_id,
                 "X-Anticipy-Agent-Token": token}, True)
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return ("OpenRouter direct — the QUESTION, not the proxy",
                "https://openrouter.ai/api/v1/chat/completions",
                {"Content-Type": "application/json", "Authorization": f"Bearer {key}",
                 "HTTP-Referer": "https://anticipy.ai", "X-Title": "Anticipy"}, False)
    raise Unproven(
        "no transport: set ANTICIPY_AGENT_ID + ANTICIPY_AGENT_TOKEN (+ ANTICIPY_BACKEND_URL) "
        "for the live proxy, or OPENROUTER_API_KEY to measure the question alone")


def ask(url: str, headers: dict, model: str, system: str, user: str) -> str:
    # The same payload agent_loop.wallJudge sends through modelFetch:
    # temperature 0, max_tokens 512 (a thinking model spends its budget on
    # reasoning before the one-line answer — at 64 this gate measured "PAY",
    # "SS" and empty replies on 15 of 22 pages), messages system + user.
    # If wallJudge's cap changes, change this with it.
    payload = {"model": model, "temperature": 0, "max_tokens": 512,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=90) as r:
        body = json.loads(r.read().decode("utf-8", errors="replace"))
    try:
        return str(body["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError):
        return ""


def right(reply: str, expect: str) -> bool:
    """The same read login_wall.wallVerdict makes: exact tokens, and for SSO
    the provider compared case-insensitively — a gate may compare strings."""
    token = reply.strip()
    if expect.startswith("SSO "):
        m = re.match(r"^SSO (.{1,40})$", token)
        return bool(m) and m.group(1).strip().lower() == expect[4:].strip().lower()
    return token == expect


def main() -> int:
    print()
    print(f"  WALL GATE    tree: {ROOT}")
    print("               law:  HARNESS-LAWS.md Law 3 — Audit #70 is fixed when this is green LIVE")
    print("  " + "-" * 62)
    try:
        rows = golden()
        label, url, headers, live = transport()
    except Unproven as e:
        print(f"  UNPROVEN  {e}")
        print()
        return 2
    model = os.environ.get("ANTICIPY_BROWSER_MODEL", "").strip() or DEFAULT_MODEL
    print(f"  transport: {label}")
    print(f"  model:     {model}   fixtures: {len(rows)}   runs each: {RUNS}")
    print("  " + "-" * 62)

    wrong: list[str] = []
    errors: list[str] = []
    for row in rows:
        got: list[str] = []
        for _ in range(RUNS):
            try:
                got.append(ask(url, headers, model, row["system"], row["user"]))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")[:160]
                errors.append(f"{row['name']}: HTTP {e.code} {detail}")
                got.append("")
            except Exception as e:                       # noqa: BLE001
                errors.append(f"{row['name']}: {e}")
                got.append("")
        agreed = sum(1 for g in got if right(g, row["expect"]))
        mark = "ok  " if agreed == RUNS else "WRONG"
        shown = " | ".join(g.strip()[:28] or "(empty)" for g in got)
        print(f"  {mark}  {agreed}/{RUNS}  {row['name']:<36} want {row['expect']:<16} got {shown}")
        if agreed != RUNS:
            wrong.append(f"{row['name']} -> wanted {row['expect']}, got it {agreed}/{RUNS}")

    print("  " + "-" * 62)
    if errors:
        # A transport that would not answer is not a model that answered
        # wrongly — but it is not a pass either.
        for line in errors[:6]:
            print(f"  transport error: {line}")
        if len(errors) == len(rows) * RUNS:
            print("  UNPROVEN  every call failed; nothing was measured")
            print()
            return 2
    if wrong:
        print(f"  FAIL  {len(wrong)} fixture(s) wrong on {label}:")
        for w in wrong:
            print(f"        {w}")
        print()
        return 1
    if not live:
        print(f"  UNPROVEN  the question is right {RUNS}/{RUNS} on all {len(rows)} fixtures — "
              "but over OpenRouter directly, NOT the live /agent/llm proxy. Law 3 wants the proxy.")
        print()
        return 2
    print(f"  PASS  all {len(rows)} fixtures right {RUNS}/{RUNS} over the live proxy")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
