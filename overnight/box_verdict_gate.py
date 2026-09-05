#!/usr/bin/env python3
"""THE BOX VERDICT GATE — audit #68, HARNESS-LAWS.md law 3.

Until 2026-09-05 `approvedBoolean` (extension/agent_loop.js) decided whether a
ticked box was what the owner asked for with a three-token negation window
over whichever of his words equalled a word of the box's label. Six measured
sentences saying "no" to marketing emails all PASSED it. The window is gone;
ONE question goes to a model (boxVerdictJudge), in four states, and the gate
compares the verdict — as a CEILING, so a box nobody could judge passes and is
NAMED in the run's history.

Law 3: nothing is fixed until its leg is green against the LIVE system. This
file is that leg, in three parts, and it is honest about what it cannot see:

  [1] THE PATTERN IS GONE — `approvedBoolean` appears nowhere in extension/
      code (comments excluded: the record of what was here names it).
  [2] THE LIVE JUDGE ANSWERS THE MEASURED SENTENCES — the judge's EXACT
      messages (built by agent_loop.js's own boxVerdictMessages, through
      node) are POSTed to the live /agent/llm proxy with a paired agent's
      credentials, and the token is compared: YES for the six sentences the
      window passed, NO for two controls the null-flip was written for, YES
      for an unticked newsletter box he asked for.
  [3] THE JUDGE IS NOT SILENTLY DEAD — over the last N live job traces,
      "BOX VERDICT UNAVAILABLE" lines are counted against "BOX ..." verdict
      lines. A ceiling that fenced on silence would be a wall; one whose
      silence nobody counts is decoration. This is the count.

WHAT IT NEEDS, and where it looks. /agent/llm accepts only a PAIRED `agents`
record's agent_id + agent_token (backend/pb_hooks/agent_key.pb.js), and those
live in the browser's chrome.storage.local — not in .env.local. So leg 2 reads
ANTICIPY_PB + ANTICIPY_SERVICE_TOKEN (present in .env.local, loaded by _env)
to fetch the owner's paired agent record, and uses ITS credentials for the
POST. If nothing is paired, or the read is refused, the leg is UNPROVEN —
printed in red, exit 2 — never green.

  exit 0  CLEAN     every leg passed against live
  exit 1  BROKEN    a leg measured the wrong thing live (a wrong token, a
                    dead judge, the pattern back in the tree)
  exit 2  UNPROVEN  something could not be measured. Not a soft pass: the
                    item is not closed until this reads 0.

Run: python3 overnight/box_verdict_gate.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _env  # noqa: E402

CLEAN, BROKEN, UNPROVEN = 0, 1, 2
OK, BAD, UNP = "PASS", "FAIL", "UNPROVEN"
RED, END = "\033[31m", "\033[0m"
TRACES_TO_READ = 50
DEAD_RATIO = 0.5

MARKETING = {"label": "Send me marketing emails", "name": "marketing_emails",
             "required": False, "value": True}
CASES = [
    # The six sentences the window PASSED, measured 2026-09-04. The box is
    # ticked; every one of them says no; the honest token is YES (contrary).
    ("Book it, and I do not under any circumstances want the marketing emails.", MARKETING, "YES"),
    ("Book it, and I do not want the marketing emails.", MARKETING, "YES"),
    ("Book it, I don't want marketing emails.", MARKETING, "YES"),
    ("Marketing emails: absolutely not.", MARKETING, "YES"),
    ("Book the table and send the confirmation to my phone.", MARKETING, "YES"),
    ("Do not send me marketing emails. Send the confirmation to my phone.", MARKETING, "YES"),
    # The booking the null-flip was written for: words that never mention
    # either box. Terms in order to complete what he asked for is NO; an
    # unmentioned offers box is NO.
    ("Book a table tomorrow at 7:30 for 3",
     {"label": "I agree to the terms of service", "name": "terms", "required": True, "value": True}, "NO"),
    ("Book a table tomorrow at 7:30 for 3",
     {"label": "Send me offers", "name": "offers", "required": False, "value": True}, "NO"),
    # The other direction: he asked for it and the box is NOT ticked.
    ("yes please sign me up for the newsletter",
     {"label": "Subscribe to the newsletter", "name": "newsletter", "required": False, "value": False}, "YES"),
]

# Builds the judge's exact messages with agent_loop.js's own exported builder,
# so this leg can never drift from what the extension sends.
NODE_BUILDER = r"""
globalThis.chrome = {
  tabs: { query: async () => [], create: async () => ({ id: 1 }), remove: async () => {} },
  storage: { local: { get: async () => ({}), set: async () => {} } },
  runtime: {}, debugger: {}, tabGroups: {}, notifications: {}, alarms: {},
};
const { pathToFileURL } = await import("node:url");
const { boxVerdictMessages } = await import(pathToFileURL(process.env.BOX_LOOP).href);
const cases = JSON.parse(process.env.BOX_CASES);
process.stdout.write(JSON.stringify(cases.map((c) => boxVerdictMessages(c, "gate"))));
"""


def strip_js_comments(text: str) -> str:
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    return re.sub(r"//[^\n]*", "", text)


def leg_1_pattern_gone() -> tuple[str, str]:
    hits = []
    for base, dirs, files in os.walk(os.path.join(ROOT, "extension")):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "store")]
        for name in files:
            if not name.endswith((".js", ".mjs")):
                continue
            path = os.path.join(base, name)
            try:
                code = strip_js_comments(open(path, encoding="utf-8", errors="replace").read())
            except OSError:
                continue
            for number, line in enumerate(code.splitlines(), 1):
                if "approvedBoolean" in line:
                    hits.append(f"{os.path.relpath(path, ROOT)}:{number}")
    if hits:
        return BAD, "approvedBoolean is back in the code: " + ", ".join(hits[:6])
    return OK, "approvedBoolean survives only in the record of what was here"


def pb_get(pb: str, path: str, params: dict, token: str) -> dict:
    url = f"{pb}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={
        "X-Anticipy-Worker": "1", "X-Anticipy-Token": token,
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def paired_agent(pb: str, token: str) -> tuple[dict | None, str]:
    """The owner's most recently updated paired agent — id and token only."""
    try:
        data = pb_get(pb, "/api/collections/agents/records", {
            "perPage": 1, "filter": "paired = true", "sort": "-updated",
            "fields": "id,agent_id,agent_token,updated",
        }, token)
    except urllib.error.HTTPError as err:
        return None, f"reading agents answered HTTP {err.code}"
    except (urllib.error.URLError, OSError, ValueError) as err:
        return None, f"reading agents failed: {str(err)[:120]}"
    items = data.get("items") or []
    if not items:
        return None, "no paired agent record exists"
    rec = items[0]
    if not rec.get("agent_id") or not rec.get("agent_token"):
        return None, "the paired agent record carries no credentials the service token may read"
    return rec, ""


def build_messages() -> tuple[list | None, str]:
    loop = os.path.join(ROOT, "extension", "agent_loop.js")
    asks = [{**box, "authority": said, "facts": ""} for said, box, _ in CASES]
    env = {**os.environ, "BOX_LOOP": loop, "BOX_CASES": json.dumps(asks)}
    try:
        run = subprocess.run(["node", "--input-type=module", "-e", NODE_BUILDER],
                             env=env, cwd=ROOT, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as err:
        return None, f"node could not build the messages: {str(err)[:120]}"
    if run.returncode != 0:
        return None, f"node could not build the messages: {run.stderr.strip()[-200:]}"
    try:
        return json.loads(run.stdout), ""
    except ValueError:
        return None, f"node returned something that is not JSON: {run.stdout[:120]}"


def leg_2_live_judge() -> tuple[str, str]:
    pb = (os.environ.get("ANTICIPY_PB") or "").rstrip("/")
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN") or ""
    if not pb or not token:
        return UNP, "ANTICIPY_PB and ANTICIPY_SERVICE_TOKEN are needed to find a paired agent"
    agent, why = paired_agent(pb, token)
    if not agent:
        return UNP, why + " — nothing can POST to /agent/llm without a paired agent"
    messages, why = build_messages()
    if messages is None:
        return UNP, why
    model = os.environ.get("ANTICIPY_BROWSER_MODEL") or "anthropic/claude-sonnet-4.6"
    wrong, unproven = [], []
    for (said, box, expected), msgs in zip(CASES, messages):
        payload = json.dumps({"model": model, "temperature": 0, "max_tokens": 8,
                              "messages": msgs}).encode("utf-8")
        req = urllib.request.Request(f"{pb}/agent/llm", data=payload, method="POST", headers={
            "Content-Type": "application/json",
            "X-Anticipy-Agent-ID": str(agent["agent_id"]),
            "X-Anticipy-Agent-Token": str(agent["agent_token"]),
        })
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                body = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as err:
            detail = ""
            try:
                detail = err.read().decode("utf-8", "replace")[:100]
            except Exception:  # noqa: BLE001
                pass
            unproven.append(f"HTTP {err.code} {detail!r} for {said[:40]!r}")
            continue
        except (urllib.error.URLError, OSError, ValueError) as err:
            unproven.append(f"{str(err)[:80]} for {said[:40]!r}")
            continue
        got = ""
        try:
            got = str(((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        except AttributeError:
            got = ""
        if got != expected:
            wrong.append(f"{said[:48]!r} × {box['label']!r} {'TICKED' if box['value'] else 'NOT TICKED'}: "
                         f"wanted {expected}, got {got[:20]!r}")
    if wrong:
        return BAD, f"{len(wrong)}/{len(CASES)} wrong against live: " + "; ".join(wrong[:4])
    if unproven:
        return UNP, f"{len(unproven)}/{len(CASES)} could not be asked: " + "; ".join(unproven[:3])
    return OK, f"all {len(CASES)} tokens exact against live /agent/llm ({model})"


def leg_3_silence_counted() -> tuple[str, str]:
    pb = (os.environ.get("ANTICIPY_PB") or "").rstrip("/")
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN") or ""
    if not pb or not token:
        return UNP, "ANTICIPY_PB and ANTICIPY_SERVICE_TOKEN are needed to read live traces"
    try:
        data = pb_get(pb, "/api/collections/jobs/records", {
            "perPage": TRACES_TO_READ, "sort": "-created", "fields": "id,created,trace",
        }, token)
    except urllib.error.HTTPError as err:
        return UNP, f"reading jobs answered HTTP {err.code}"
    except (urllib.error.URLError, OSError, ValueError) as err:
        return UNP, f"reading jobs failed: {str(err)[:120]}"
    items = data.get("items") or []
    judged = unavailable = 0
    for row in items:
        for line in str(row.get("trace") or "").splitlines():
            if "BOX VERDICT UNAVAILABLE" in line:
                unavailable += 1
            elif re.search(r'\bBOX "', line):
                judged += 1
    total = judged + unavailable
    if not items:
        return UNP, "no job traces to read"
    if total == 0:
        return UNP, (f"no box verdict in the newest {len(items)} live traces — the build carrying "
                     f"#68 has not run a form with a tick-box live yet")
    ratio = unavailable / total
    line = f"{judged} judged, {unavailable} unavailable over {len(items)} traces ({ratio:.0%} silent)"
    if ratio >= DEAD_RATIO:
        return BAD, "the judge is dead more often than not: " + line
    return OK, line


def main() -> int:
    _env.load_and_announce(ROOT)
    legs = [
        ("THE PATTERN IS GONE", leg_1_pattern_gone),
        ("THE LIVE JUDGE ANSWERS THE MEASURED SENTENCES", leg_2_live_judge),
        ("THE JUDGE IS NOT SILENTLY DEAD", leg_3_silence_counted),
    ]
    print("\n  BOX VERDICT GATE — audit #68, against LIVE")
    print("  --------------------------------------------------------------")
    worst = CLEAN
    for number, (title, fn) in enumerate(legs, 1):
        try:
            state, detail = fn()
        except Exception as err:  # noqa: BLE001 — a crashing leg is unproven, not green
            state, detail = UNP, f"the leg itself failed: {str(err)[:160]}"
        colour = RED if state != OK else ""
        print(f"  [{number}] {colour}{state}{END if colour else ''}  {title}")
        print(f"        {detail}")
        if state == BAD:
            worst = BROKEN
        elif state == UNP and worst != BROKEN:
            worst = UNPROVEN
    print("  --------------------------------------------------------------")
    if worst == CLEAN:
        print("  CLEAN — every leg green against live. #68 is closed.\n")
    elif worst == BROKEN:
        print(f"  {RED}BROKEN{END} — a leg measured the wrong thing. Fix it; do not soften the leg.\n")
    else:
        print(f"  {RED}UNPROVEN{END} — not green, not red: something could not be measured. "
              "Repo-green is not done; #68 stays open until this reads CLEAN.\n")
    return worst


if __name__ == "__main__":
    sys.exit(main())
