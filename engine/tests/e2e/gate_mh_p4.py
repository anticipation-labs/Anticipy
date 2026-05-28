"""MH-P4 gate: offline buffer + sync.

Scripted pendant disconnect -> capture -> flaky/partial/duplicated
reconnect. Binds on:

  ZERO LOSS         every distinct captured event is delivered
                    exactly once across a partial sync + full resync
                    + a redelivery storm.
  ZERO DOUBLE       no event delivered twice; a delayed
                    double-capture (same content) and an
                    already-synced item are skipped.
  ENCRYPTED AT REST no plaintext event payload appears in the
                    on-disk buffer; decrypt round-trips.
  frozen action engine + reasoning + cascade git-clean.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.offline.buffer import OfflineBuffer

    print("== MH-P4 GATE (offline buffer + sync) ==")
    log, ok = [], True

    tmp = tempfile.NamedTemporaryFile(suffix=".buf", delete=False)
    tmp.close()
    buf = OfflineBuffer(tmp.name)

    # --- disconnected capture: 20 distinct + 1 exact redelivery ---
    secret_marker = "BUDGET-Q3-SECRET-PAYLOAD"
    N = 20
    for i in range(N):
        buf.capture({"kind": "utterance", "seq": i,
                     "text": f"{secret_marker} event {i}"})
    buf.capture({"kind": "utterance", "seq": 7,
                 "text": f"{secret_marker} event 7"})   # exact dupe
    log.append(f"  captured tokens on disk = {buf.count()} "
               f"(20 distinct + 1 redelivered)")

    # --- encrypted at rest ---
    enc_ok = buf.plaintext_absent([secret_marker, "utterance",
                                   "event 7"])
    log.append(f"  BINDING encrypted-at-rest (no plaintext payload on "
               f"disk) -> {enc_ok}")
    ok &= enc_ok

    # --- flaky reconnect ---
    received: list = []
    delivered = set()                       # the DURABLE delivered-set

    s1 = buf.sync(lambda e: received.append(e["seq"]),
                  delivered_ids=delivered, fail_after=8)   # drop @ 8
    s2 = buf.sync(lambda e: received.append(e["seq"]),
                  delivered_ids=delivered)                 # full resync
    s3 = buf.sync(lambda e: received.append(e["seq"]),
                  delivered_ids=delivered)                 # storm: noop

    distinct = sorted(set(received))
    zero_loss = distinct == list(range(N))
    zero_double = len(received) == N         # exactly N deliveries total
    log.append(f"  partial s1.delivered={s1.delivered} "
               f"s2.delivered={s2.delivered} s3.delivered={s3.delivered} "
               f"s3.skipped_dupes={s3.skipped_dupes}")
    log.append(f"  BINDING zero-loss: {len(distinct)}/{N} distinct "
               f"events delivered -> {zero_loss}")
    log.append(f"  BINDING zero-double: total deliveries={len(received)} "
               f"(==N={N}) skipped(dupe+resynced)="
               f"{s1.skipped_dupes + s2.skipped_dupes + s3.skipped_dupes}"
               f" -> {zero_double}")
    ok &= zero_loss and zero_double

    # idempotent: a 4th sync delivers nothing more
    before = len(received)
    buf.sync(lambda e: received.append(e["seq"]), delivered_ids=delivered)
    idem_ok = len(received) == before
    log.append(f"  BINDING idempotent re-sync: deliveries unchanged "
               f"({before}=={len(received)}) -> {idem_ok}")
    ok &= idem_ok

    Path(tmp.name).unlink(missing_ok=True)

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"MH_P4_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
