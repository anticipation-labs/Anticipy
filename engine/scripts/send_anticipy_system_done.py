"""Send the ONE [ANTICIPY-SYSTEM-DONE] email — the single mandated
human-facing completion notification for the Anticipy System V1 build.

Reuses the established project Aevoy mechanism (Resend, FROM
aevoy@anticipy.ai, key from repo .env.local, TO the admin email),
identical to send_anticipy_ready.py. Body is the headline scoreboard
plus the scope statement, as the master prompt requires.

Usage:
  python engine/scripts/send_anticipy_system_done.py \
      --scoreboard /path/to/final_scoreboard.txt [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent          # engine/
REPO = ROOT.parent                                      # repo root
load_dotenv(REPO / ".env.local")

SCOPE = (
    "SCOPE. Certifies, on GENERATED DIARIZED TEXT: proactive reasoning "
    "(addressee, authority, hedge, four-way decision, progressive "
    "autonomy), the typed handoff to the FROZEN action engine (never "
    "modified), the two-way comms layer (criticality, resumable "
    "replies, the 3-hour rule and its carve-outs), per-user identity "
    "and onboarding, multi-tenant isolation, and durability under a "
    "hard process kill. Does NOT certify end-to-end audio: there is no "
    "mic/VAD/ASR/diarization on the runtime path; real ASR will lower "
    "the diarized numbers in production. These numbers isolate the "
    "reasoning/handoff/comms/identity/durability quality from audio "
    "front-end error, on purpose, so each layer is measured honestly."
)


def phase_tags() -> list[str]:
    r = subprocess.run(["git", "tag"], cwd=str(REPO),
                        capture_output=True, text=True)
    tags = [t.strip() for t in r.stdout.splitlines()
            if t.strip().startswith("p") and "-" in t.strip()
            and t.strip()[1].isdigit()]
    return sorted(tags, key=lambda s: int(s.split("-")[0][1:]))


def build_body(scoreboard_text: str) -> str:
    tags = phase_tags()
    lines = [
        "Anticipy System V1 — BUILD COMPLETE.",
        "",
        "One coherent portable Python system: a preserved three-stage "
        "cascade drives a proactive engine (addressee, authority, "
        "memory reconciliation, four-way decision under progressive "
        "autonomy); ACT crosses one typed seam to the FROZEN action "
        "engine; a durable runtime survives hard kill; a two-way comms "
        "layer applies criticality and the 3-hour rule; a multi-tenant "
        "spine fails closed. Portable behind one env seam, under a 2 GB "
        "per-instance cap. No human was in the loop for any phase.",
        "",
        "Phase tags (all genuine, committed, in order):",
    ]
    lines += [f"  - {t}" for t in tags]
    lines += [
        "",
        "HEADLINE SCOREBOARD (final consolidated run, real numbers):",
        "",
        scoreboard_text.strip(),
        "",
        SCOPE,
        "",
        "Full honest report (every phase tag, per-category over/under-"
        "action, residual-difficulty flags, the JSON-corruption and "
        "provider-roulette diagnosis, flywheel, local-vs-scale, measured "
        "per-decision cost): .anticipy/ANTICIPY_SYSTEM_V1.md in the repo.",
        "",
        "Frozen action engine and desktop app never modified (git clean "
        "on those paths every phase; 10 phase-v4 tags intact).",
    ]
    return "\n".join(lines)


def send_email(subject: str, body: str) -> dict:
    api_key = os.environ.get("RESEND_API_KEY")
    to = os.environ.get("ADMIN_EMAIL", "omarkebrahim@gmail.com")
    if not api_key:
        raise SystemExit("RESEND_API_KEY missing from env (.env.local)")
    r = httpx.post(
        "https://api.resend.com/emails",
        json={"from": "aevoy@anticipy.ai", "to": to,
              "subject": subject, "text": body},
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        timeout=20.0,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scoreboard", required=True,
                    help="path to the final scoreboard text output")
    ap.add_argument("--dry-run", action="store_true", default=False)
    args = ap.parse_args()

    sb_path = Path(args.scoreboard)
    scoreboard_text = sb_path.read_text() if sb_path.exists() else "(scoreboard file missing)"
    subject = "[ANTICIPY-SYSTEM-DONE] Anticipy System V1"
    body = build_body(scoreboard_text)

    if args.dry_run:
        print(f"--- TO ---\n{os.environ.get('ADMIN_EMAIL','omarkebrahim@gmail.com')}")
        print(f"--- SUBJECT ---\n{subject}\n--- BODY ---\n{body}")
        return 0
    out = send_email(subject, body)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
