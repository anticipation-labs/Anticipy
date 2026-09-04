#!/usr/bin/env python3
"""THE FIRMWARE GATE. Is the pendant's capture path sound, and is it REAL?

Two questions, deliberately kept apart, because conflating them is how this
repo has been burned before.

  1. Does the pure logic hold?  Answerable here, on a host compiler.
  2. Is any of it running on a board?  NOT answerable here, and the honest
     answer today is no.

WHY THE SECOND QUESTION IS THE POINT.

On 2026-09-04 three firmware defects were fixed in this tree: a full ring or
one congested BLE connection event switched the microphone OFF for the rest of
the connection (`transport_audio_fault` on routine `-ENOSPC`/`-EAGAIN`), the
frame-size macro was unparenthesised, and the DMA-block-to-Opus-frame ratio
that keeps buffer boundaries aligned was load-bearing, undocumented and
unchecked. All three are fixed IN SOURCE. None of it has been compiled: this
machine has no `west`, no `arm-none-eabi-gcc`, no cmake and no Zephyr, and
there is no firmware CI. `firmware/source/ANTICIPY_SOURCE_RECEIPT.json` still
records artifact_built=false, flash_performed=false,
physical_hardware_verified=false, and the shipped `firmware/anticipy.uf2` does
not match the sha256 in its own `BUILD_RECEIPT.json`.

So this gate is RED, and red is it working. Law 3: nothing is fixed until its
leg is green against the LIVE system, and a fix nobody can build is further
from live than a fix nobody has deployed. Turning this green needs a build, a
flash, and a pendant that streams — not another commit.

WHAT IT REFUSES TO DO. It does not report the pure-logic checks as the
verdict. Those passing is a precondition, not an answer; a gate that went
green because some host-compiled asserts held would be telling you the
firmware works, which nobody knows. When the host checks pass and the receipts
still say unbuilt, the verdict is UNPROVEN (exit 2), which is a different
thing from broken (exit 1) and from done (exit 0).
"""

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FW = ROOT / "firmware"
SRC = FW / "source" / "src"

BROKEN, UNPROVEN, CLEAN = 1, 2, 0


def _say(mark, title, detail=""):
    print(f"  [{mark}] {title}")
    if detail:
        print(f"        {detail}")


def pure_logic_holds():
    """Run the host-compiled checks over the firmware's pure halves."""
    runner = FW / "source" / "tests" / "run_firmware_tests.sh"
    if not runner.exists():
        return False, "tests/run_firmware_tests.sh is gone"
    try:
        done = subprocess.run(
            ["bash", str(runner)], capture_output=True, text=True, timeout=180
        )
    except Exception as exc:  # a missing host compiler is a finding, not a crash
        return False, f"could not run: {type(exc).__name__}"
    if done.returncode != 0:
        tail = (done.stdout + done.stderr).strip().splitlines()
        return False, tail[-1] if tail else "non-zero exit, no output"
    return True, "backpressure classification, capture geometry, sequence commit"


def backpressure_is_survivable():
    """A REGRESSION PIN, not an expiry: red if the fix is taken back out.

    Law 2 draws that line and this file honours it. The check reads the two
    call sites that used to escalate a full ring into a permanent stop, and the
    pusher branch that used to escalate a busy controller the same way.
    """
    main_c = (SRC / "main.c").read_text()
    transport_c = (SRC / "transport.c").read_text()

    # Both ring-full paths must return, not fault.
    ring_paths = re.findall(
        r"if\s*\(\s*err\s*==\s*-ENOSPC\s*\)\s*\{[^}]*?return;", main_c, re.S
    )
    if len(ring_paths) < 2:
        return False, (
            "main.c no longer drops a full ring; a 320ms TX backlog or a 1s PCM "
            "backlog would switch the microphone off for the connection again"
        )

    if "transport_error_is_backpressure(err)" not in transport_c:
        return False, (
            "the pusher no longer classifies send failures; one congested "
            "connection event would end capture for the session again"
        )
    if "discard_pending_frame(&state)" not in transport_c:
        return False, "the pusher classifies backpressure but does not drop the frame"

    # The dropped frame must still step the sequence, or the phone cannot see
    # the hole — which is the whole reason the drop is allowed to exist.
    discard = re.search(
        r"static void discard_pending_frame\([^)]*\)\s*\{(.*?)\n\}", transport_c, re.S
    )
    if not discard or "sequence++" not in discard.group(1):
        return False, (
            "a dropped frame no longer steps the sequence, so the phone's gap "
            "detector sees a continuous stream over lost audio"
        )
    return True, "a full ring and a busy controller each lose one frame, counted and visible"


def artifact_is_real():
    """Has any of this been built, flashed, or seen on hardware?"""
    receipt = FW / "source" / "ANTICIPY_SOURCE_RECEIPT.json"
    build = FW / "BUILD_RECEIPT.json"
    if not receipt.exists():
        return False, "ANTICIPY_SOURCE_RECEIPT.json is missing; provenance unknown"
    data = json.loads(receipt.read_text())
    unmet = [
        key
        for key in ("artifact_built", "flash_performed", "physical_hardware_verified")
        if not data.get(key, False)
    ]
    if unmet:
        return False, "still false in the source receipt: " + ", ".join(unmet)

    # A receipt claiming a build must agree with the artifact on disk.
    if build.exists():
        claimed = json.loads(build.read_text())
        digest = claimed.get("uf2_sha256") or claimed.get("sha256")
        uf2 = FW / "anticipy.uf2"
        if digest and uf2.exists():
            import hashlib

            actual = hashlib.sha256(uf2.read_bytes()).hexdigest()
            if actual != digest:
                return False, "anticipy.uf2 does not match the sha256 in its own receipt"
    return True, "built, flashed, and seen on a board"


def main():
    print()
    print(f"  FIRMWARE GATE   tree: {ROOT}")
    print( "  --------------------------------------------------------------")

    logic_ok, logic_note = pure_logic_holds()
    _say("PASS" if logic_ok else "FAIL", "THE PURE LOGIC HOLDS", logic_note)

    pin_ok, pin_note = backpressure_is_survivable()
    _say("PASS" if pin_ok else "FAIL", "BACKPRESSURE CANNOT KILL THE MICROPHONE", pin_note)

    real_ok, real_note = artifact_is_real()
    _say("PASS" if real_ok else "fail", "ANY OF IT IS ACTUALLY RUNNING", real_note)

    print( "  --------------------------------------------------------------")
    if not (logic_ok and pin_ok):
        print("  BROKEN — a source-level check failed. Fix that before anything else;")
        print("  a board cannot rescue logic that is wrong on the page.")
        return BROKEN
    if not real_ok:
        print("  UNPROVEN — the logic holds and NOTHING HAS BEEN BUILT.")
        print("  This is the honest steady state, not a pass. There is no")
        print("  cross-toolchain on this machine and no firmware CI, so every")
        print("  fix in firmware/source/ is a claim about source and nothing")
        print("  more. Law 3 is explicit that repo-green is not done, and this")
        print("  is further back than that: it is repo-green without a compile.")
        print("  To move it: build with west, flash a XIAO nRF52840 Sense,")
        print("  update ANTICIPY_SOURCE_RECEIPT.json, and confirm the pendant")
        print("  streams while the phone reports frames and gaps.")
        return UNPROVEN
    print("  CLEAN — built, flashed, and seen on hardware.")
    return CLEAN


if __name__ == "__main__":
    sys.exit(main())
