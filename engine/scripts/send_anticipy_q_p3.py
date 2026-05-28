"""The ONE [ANTICIPY-Q] audiostack blocker email for phase P3, per
build spec sec 7 (four sections: attempted+literal outputs / exact
failure / most likely cause / specific decision needed). Reuses the
established project Aevoy mechanism (Resend, FROM aevoy@anticipy.ai,
key from repo .env.local, TO the admin email), identical to
send_anticipy_ready.py / send_anticipy_system_done.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
load_dotenv(REPO / ".env.local")

SUBJECT = "[ANTICIPY-Q] audiostack blocker phase P3"

BODY = """\
Anticipy audio-stack build: P3/P4 blocked. Honest escalation per
build spec sec 2/7. P0, P1, P2 are genuine passes (tags astack-p0,
astack-p1-membership, astack-p2-gates); the frozen reasoning system
and action engine were never modified (git-clean every phase).

1) ATTEMPTED, WITH LITERAL OUTCOMES
The earlier astack-p3-trust PASS was discovered FALSE while wiring
P4: a subword token-matching bug made Layer 3 always CONFIRM
(no verb extracted), so nothing fired and zero-blind-fire was
vacuous. Three real pipeline bugs were then fixed (kept): subword
->word reconstruction; evaluate-all-candidates; emit the full
diarized conversation. End-to-end through the FROZEN engine then
genuinely worked for clean speech: WEARER_DIRECT 3/3 ACT,
BOSS_INSTRUCTION 2/3 ACT (frozen engine's real boss_to_wearer /
agent_direct logic). With the corrected real Layer 3, EIGHT
distinct principled load-bearing-slot-trust approaches were
implemented and measured:
  1 parakeet per-token confidence: ~0.99 even on destroyed audio
    -> 5/15 blind fires
  2 raw-vs-denoise re-decode: stably wrong -> 4/15 blind fires
  3 acoustic rate/SNR stress: distributions overlap, no separation
  4 time-warp consensus: kills clean true-pass 5/6, still misses
  5 genuine local slot corruption + confidence: 6/6 still FIRE
  6 slot-region acoustic clarity: ~equal corrupted vs clean
  7 cross-model exact agreement (parakeet + torchaudio HUBERT):
    clean OOV names never corroborate -> WEARER_DIRECT 6/6 CONFIRM
  8 cross-model phonetic/fuzzy agreement: still inseparable
    (LOADBEARING 2/6 FIRE, WEARER_DIRECT 5/6 CONFIRM)

2) EXACT FAILURE
Binding LOADBEARING requirement: zero blind actions on a low-
confidence load-bearing slot AND >=0.90 true-pass on clean
WEARER_DIRECT/BOSS. No measured approach achieves both: any signal
strict enough to catch a confidently-misheard name also confirms
clean names; any signal lax enough to pass clean names also passes
the corrupted ones. P2 (and its 0.000 false-trust) is unaffected.

3) MOST LIKELY CAUSE
The spec's Layer-3 design assumes the ASR exposes usable per-token
uncertainty. parakeet-mlx does not (confidence ~1.0 regardless of
audio quality; no n-best/lattice), and a second independent ASR
disagrees on clean out-of-vocabulary proper names even when both
heard them correctly. The binding guarantee is not reachable with
the offline ASR stack available in this environment. This is a
genuine architectural limit, not a tuning gap.

4) SPECIFIC DECISION NEEDED (choose one)
 (a) Adopt an ASR exposing real word/token uncertainty
     (lattice / n-best / calibrated confidence) or a word-confidence
     model as the load-bearing verifier (dependency/architecture
     change), then resume P3.
 (b) Accept the safe contract: ALWAYS confirm any instruction
     carrying a name/amount/date slot (zero blind fire by
     construction) and relax the WEARER_DIRECT/BOSS unconfirmed
     true-pass targets to that honest ceiling.
 (c) Descope LOADBEARING_WORD_STRESS as a known synthetic+offline-
     ASR limitation, certifying only that the system never blind-
     fires (it confirms all load-bearing slots).

Full literal evidence: .anticipy/PROGRESS.md (ASTACK P3/P4 BLOCKER
section). Build stopped at P3/P4 pending this decision; no pass was
faked and the binding zero-blind-fire requirement was not weakened.
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", default=False)
    args = ap.parse_args()
    to = os.environ.get("ADMIN_EMAIL", "omarkebrahim@gmail.com")
    if args.dry_run:
        print(f"--- TO ---\n{to}\n--- SUBJECT ---\n{SUBJECT}\n"
              f"--- BODY ---\n{BODY}")
        return 0
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise SystemExit("RESEND_API_KEY missing from .env.local")
    r = httpx.post(
        "https://api.resend.com/emails",
        json={"from": "aevoy@anticipy.ai", "to": to,
              "subject": SUBJECT, "text": BODY},
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        timeout=20.0,
    )
    print("HTTP", r.status_code, r.text[:300])
    r.raise_for_status()
    print(json.dumps(r.json(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
