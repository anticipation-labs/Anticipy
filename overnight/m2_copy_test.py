#!/usr/bin/env python3
"""M2 acceptance — every card the user sees is HUMAN: no engine templates, IDs, arrows, or jargon.
Run via overnight/run_m2_copy.sh (it restarts the engine on clean state first)."""
import json, os, re, urllib.request

ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8787")
JARGON = ("dispatching", "the engine", "ingest", "harm-line", "press-go", "pipeline",
          "task queue", "anticipy:", "reminder:", "open loop", "the system", "disposition",
          "goal_state", "glassbox", "card record")
BANNED = [
    (re.compile(r"\b[0-9a-f]{12,}\b", re.I), "raw id/uuid"),
    (re.compile(r"owner task\s*:", re.I), "Owner task: prefix"),
    (re.compile(r"confirm task\s*:", re.I), "Confirm task: prefix"),
    (re.compile(r"block money action", re.I), "engine template"),
    (re.compile(r"resolve browser task", re.I), "engine template"),
    (re.compile(r"left for you \(money\)", re.I), "engine template"),
    (re.compile(r"prepare message for", re.I), "engine template"),
    (re.compile(r"protect pickup or drop-off", re.I), "engine template"),
    (re.compile(r"->|→"), "route arrow"),
    (re.compile(r"fail-safe|cannot confirm safe", re.I), "engine rationale"),
]
LINES = [
    "My mom just walked in and told me to return that plant on Amazon.",
    "I told Sarah I'd send her the deck by Friday.",
    "After the deposition — file the satisfaction of judgment by the 25th.",
    "Ugh this traffic is going to make me scream. Pick up the kids at 2:45. Pay the $4,200 invoice whatever it costs.",
    "Let's grab dinner tonight at a nice place.",
    "Remember my wife Maya prefers texts after lunch.",
]

def ingest(text):
    req = urllib.request.Request(ENGINE + "/owner/ingest", method="POST",
        data=json.dumps({"text": text, "execute_actions": True}).encode(),
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())

def get_board():
    return json.loads(urllib.request.urlopen(ENGINE + "/owner/cards", timeout=20).read().decode())

leaks, titles, n = [], [], 0
for ln in LINES:
    for c in ingest(ln).get("cards", []):
        n += 1
        titles.append(c.get("title", ""))
        blob = ((c.get("title") or "") + " || " + (c.get("reason") or "")).strip()
        for rx, why in BANNED:
            if rx.search(blob):
                leaks.append((why, c.get("title"), c.get("reason")))
        low = blob.lower()
        for j in JARGON:
            if j in low:
                leaks.append((f"jargon:{j}", c.get("title"), c.get("reason")))

# board surface too (GET /owner/cards must match the human copy)
board = get_board()
bcards = board.get("cards", board) if isinstance(board, dict) else board
for c in (bcards or []):
    blob = ((c.get("title") or "") + " || " + (c.get("reason") or ""))
    for rx, why in BANNED:
        if rx.search(blob):
            leaks.append((f"BOARD:{why}", c.get("title"), c.get("reason")))

varied = len(set(titles)) >= max(2, int(len(titles) * 0.6)) if titles else False
print(f"cards checked: {n} | distinct titles: {len(set(titles))}/{len(titles)} | leaks: {len(leaks)}")
for t in titles[:8]:
    print("  TITLE:", repr(t))
for why, t, r in leaks[:10]:
    print(f"  LEAK [{why}]: title={t!r} reason={r!r}")
ok = (len(leaks) == 0) and varied and n > 0
print("\nM2 COPY:", "PASS" if ok else "FAIL")
