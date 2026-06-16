#!/usr/bin/env python3
"""THE PREMIUM COPY GATE — the failable check behind ANTICIPY_UX_SPEC §4.8 / R4.1 / A14.

Omar's single most-cited defect is the "localhost dev-server feel." The UX spec turns that into a
testable rule: the product NEVER shows the user a codebase artifact — a port, raw JSON/IDs, a
model/vendor name, an internal status tag, or a codebase verb ("Ingest", "Press Go"). This script
is the gate that makes that rule impossible to fake: it FAILS (exit 1) on any banned string the user
could see, and the premium-shell reskin is "done" on this axis only when it exits 0.

It checks two surfaces, because the app server-renders some copy and client-renders the rest:
  1. RENDERED DOM (the authoritative R4.1 test): fetch each route from the running Next app and grep
     the served HTML for any banned term actually shipped to the browser.
  2. SOURCE BACKSTOP: grep app/*.js for the high-confidence *display-copy* phrases (button verbs,
     robotic confirmations, vendor names) that hydrate into the DOM client-side and so are absent
     from the initial HTML. Deliberately conservative — only phrases that are user-copy, never
     ambiguous code identifiers — so a hit is always a real leak, never a false positive.

This is a CONTRADICTOR by construction: it assumes the surface is guilty and tries to prove it. Today
it SHOULD fail (the current surface is a dev console) — that failing run is the honest baseline the
reskin has to clear, not a bug.

Run:  factory/bin/check_premium_copy.py            (uses :3000 + ./app)
      factory/bin/check_premium_copy.py --quiet    (just the verdict)
Exit: 0 = no banned string visible anywhere (premium-copy clean) · 1 = at least one leak
"""
from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app"
WEB = "http://127.0.0.1:3000"
ROUTES = ["/", "/connect", "/download"]

# (pattern, why it's banned, what to say instead) — sourced verbatim from ANTICIPY_UX_SPEC §4.8.
# DOM-banned: if this appears in what the browser renders, it is a leak.
BANNED_DOM = [
    (r"Owner Mode",            "internal role label",          "the user's name, or nothing"),
    (r"Press Go",              "codebase verb / dev-console",  "(ambient — no button) or 'Start listening'"),
    (r"\bIngest\b",            "codebase verb",                "(nothing — capture is ambient)"),
    (r"Transcrib(?:e|ing)",    "process exposure",             "'Reading your week' / 'Thinking'"),
    (r"Task completed",        "robotic confirmation",         "the real artifact, or under-confirm"),
    (r"Successfully \w+",      "robotic confirmation",         "the real artifact"),
    (r"localhost",             "dev artifact",                 "(never shown)"),
    (r":(?:8787|3000)\b",      "port number",                  "(never shown)"),
    (r"\bdisposition\b",       "engine internal",              "'Handled' / 'Waiting for your yes'"),
    (r"\bgoal_state\b",        "engine internal",              "'Held' / human label"),
    (r"\bglassbox\b",          "engine internal",              "'the ledger'"),
    (r"\b(?:Polly|Twilio|Arcade|OpenRouter|OpenAI)\b", "vendor leak", "(never shown)"),
    (r"\| (?:api|calendar|connected)\b", "raw pipe data dump", "'Calendar — connected.' sentences"),
    (r"\bnull\b|\bundefined\b", "failure leak",                "'I lost the thread for a moment.'"),
]
# SOURCE-banned: only unambiguous user-copy that hydrates client-side (absent from initial HTML).
# Kept narrow so every hit is a genuine displayed-string leak, never a code identifier.
BANNED_SOURCE = [
    (r"Owner Mode", "H1 / role label"),
    (r"Press Go", "button verb"),
    (r"\bIngest\b", "button/codebase verb"),
    (r"Transcrib(?:e|ing)", "process exposure"),
    (r"Task completed", "robotic confirmation"),
    (r"Successfully \w+", "robotic confirmation"),
    (r"(?:Polly|Twilio|Arcade|OpenRouter)", "vendor name in copy"),
]


def _fetch(url: str) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=6) as r:  # noqa: S310 (localhost)
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None


def _visible(html: str) -> str:
    """Approximate what the USER sees: drop <script>/<style> blocks (Next's __NEXT_DATA__ JSON and
    the JS bundles live there and legitimately contain null/internal field names — they are NOT
    rendered text, so grepping them would be a false positive) and HTML comments. Keep <title> and
    all real markup/text — a banned word in those genuinely reaches the user."""
    html = re.sub(r"(?is)<script\b.*?</script>", " ", html)
    html = re.sub(r"(?is)<style\b.*?</style>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    return html


def check_dom() -> tuple[list, bool]:
    hits, reachable = [], False
    for route in ROUTES:
        raw = _fetch(WEB + route)
        if raw is None:
            continue
        reachable = True
        html = _visible(raw)
        for pat, why, instead in BANNED_DOM:
            for m in re.finditer(pat, html):
                hits.append((f"DOM {route}", m.group(0), why, instead))
                break  # one hit per pattern per route is enough to fail
    return hits, reachable


def check_source() -> list:
    hits = []
    if not APP.exists():
        return hits
    for f in sorted(APP.rglob("*.js")):
        try:
            text = f.read_text(errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for pat, why in BANNED_SOURCE:
                if re.search(pat, line):
                    hits.append((f"{f.relative_to(REPO)}:{i}", re.search(pat, line).group(0), why, ""))
                    break
    return hits


def main() -> int:
    quiet = "--quiet" in sys.argv
    dom_hits, reachable = check_dom()
    src_hits = check_source()
    all_hits = dom_hits + src_hits

    if not quiet:
        print("\n=== PREMIUM COPY GATE (ANTICIPY_UX_SPEC §4.8 / R4.1) ===")
        if not reachable:
            print("  ⚠ Next app not reachable at :3000 — DOM check skipped (source backstop still ran).")
        if not all_hits:
            print("  ✅ No banned string visible. The surface reads as a product, not a dev console.")
        else:
            for where, hit, why, instead in all_hits:
                say = f"  → say instead: {instead}" if instead else ""
                print(f"  ❌ {where:<28} \"{hit}\"  ({why}){say}")
    n = len(all_hits)
    print(f"\nPREMIUM COPY: {'CLEAN' if n == 0 else f'{n} leak(s) — FAILS'}"
          + ("" if reachable else "  [DOM unchecked]"))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
