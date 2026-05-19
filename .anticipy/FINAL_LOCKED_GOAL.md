# ANTICIPY — FINAL LOCKED /goal: CLEAN-ROOM, MULTI-COLD-RUN, ZERO-NURSING

This is the hard bar. Read every line. "Done" is defined so that ANY
caveat, ANY manual intervention, ANY hand-cleanup, ANY "worked once",
or ANY "should work" is AUTOMATIC FAILURE. You do not get to soften the
threshold, reclassify a product failure as transient, or nurse a run by
hand. If you find yourself manually killing a server or closing a Gmail
window to make it pass, the run has already FAILED and you must fix the
ROOT CAUSE and start the clean-room over. The goal is not "produce
artifacts." The goal is "the product actually works, cold, repeatedly,
untouched, everywhere it can run today."

## ARCHITECTURE PREMISE (this is the intended design — build to it)
Local-first. Vercel hosts only the static app shell + the
download/launch path. The user's own device IS the server: the engine
runs on the device (Mac now; same entrypoint that the pendant would
call). No hosted backend. Memory/RAG layer, the proactive engine, the
intent engine, the handoff engine, and the action engine all run on the
device and cooperate. The deployed app connects to the local engine on
localhost. This is the pendant-and-Mac-and-home-base-in-one model.

## DEFINITION OF DONE — all must hold; any miss = FAIL, no partial

### A. Clean-room (the anti-cheat core)
Run as a FRESH OS user account (or a pristine HOME + TMPDIR with PATH
stripped of every dev venv), with NO preexisting: venv, cached models,
chrome-clone, launchd/launch agents, prior trajectories, prior profile,
prior memory. The provisioning must build from NOTHING. Artifact: the
full from-zero provisioning log + proof the dev scaffolding was absent
at start (env dump, `which` misses, empty dirs).

### B. Real deployed entry, real handoff
Hit the REAL deployed Vercel app. The Continue path must yield BOTH the
real macOS download AND the real curl one-liner, and BOTH must be
exercised in separate clean-rooms (two independent cold installs, mac
download path and curl path, each from zero). Artifact: fetched
installer(s) + checksums + the exact deployed build id/commit they came
from.

### C. Cold launch, self-provision, connect
On each clean machine the downloaded artifact self-installs and starts
the engine with NO manual steps. The deployed app, in a real browser
driven via CDP from the terminal, connects to the local engine on
localhost. Artifact: first-run log, process list, version, the
browser-to-localhost handshake captured.

### D. Real account + profile + always-on mic
Real production Supabase signup from the fresh instance (anon key
only). Real onboarding to a real profile (the people + the do-not-touch
list). Real device microphone, always-on until the user stops it.
Artifacts: real user row, profile JSON, mic authorized + continuous
windows.

### E. The full four-engine chain, REAL high-stakes action
An INDIRECT instruction that names neither the person nor the address/
target must flow proactive -> intent -> handoff -> action and complete
a REAL authenticated state-changing action (Gmail draft or Calendar
event) in the real logged-in account, to the CORRECTLY resolved person.
Test mode is allowed ONLY for the speech-input substitution: the
pipeline may accept a typed transcript injected at the exact real
post-ASR boundary (the same code path a real mic transcript takes — not
a bypass that skips resolution/compose). Everything after that boundary
must be the real path. Artifact: screenshot of the real Gmail/Calendar
item with correct recipient/content. A SUCCESS string, toast, log line,
or ITERATION_EXHAUSTED-with-"the draft exists anyway" DOES NOT COUNT
and is a FAIL. The engine must formally confirm the saved state within
its own iteration budget. If it cannot, that is a real defect — fix the
root cause, do not caveat it.

### F. Ambiguity trap, named contenders, zero state change
A genuinely ambiguous indirect instruction (two established people both
plausibly match) must make it ASK, NAMING the real contenders, and
create ZERO state change. Artifact: the question + before/after proof
of no Gmail/Calendar change.

### G. Pendant parity
The identical engine entrypoint the pendant would call, run from the
packaged artifact AND from source on the same scenario, must produce
identical resolution and the same real action. Artifact: both runs,
asserted identical.

### H. The two known fragility bugs must be ROOT-CAUSE FIXED
The double-uvicorn / split-empty-profile wedge, and the stale Gmail
compose-window pollution, are PRODUCT DEFECTS, not run hiccups. The
product must be incapable of entering either state on its own:
single-instance must be enforced in the product, and the action engine
must start from and guarantee a clean compose state itself. Proof: a
test that deliberately tries to induce each failure and shows the
product prevents/recovers WITHOUT any human or out-of-band cleanup
script. If the only way to pass is an external cleanup, it is a FAIL.

### I. Repeatability with ZERO nursing and ZERO clicks (what "works" means)
The ENTIRE clean-room chain (A through H) must pass 3 times in a row,
each from a brand-new clean-room, with ZERO human intervention of any
kind — no clicks, no prompts cleared, no spoken input, no manual server
kills, no window cleanup, no retry-by-hand, no re-seeding between runs.
If any of the 3 needs ANY human touch, the whole goal FAILS. Artifact:
3 independent full run logs + the artifact set for each.

## ZERO HUMAN CLICKS — FULLY AUTONOMOUS, TERMINAL-ONLY (hard mandate)
This goal requires ZERO human interaction of any kind. No "Open" click,
no "Allow" click, no spoken sentence, no GUI touch. The agent has only
the terminal and must stay terminal-native end to end. Specifically:

- Gatekeeper: build/stage the engine artifact LOCALLY on the clean-room
  machine so it is never quarantined (no browser download of the
  runnable binary). If any path produces a quarantined artifact, strip
  it from the terminal (remove the com.apple.quarantine attribute)
  BEFORE launch. Net: the Gatekeeper "Open" dialog must never appear. If
  it appears, the run FAILED — fix the provisioning so it cannot.
- Microphone: pre-grant microphone access from the terminal (seed the
  TCC permission for the terminal-rooted process that runs the engine,
  the same subsystem already used this project) so NO mic prompt ever
  fires. The engine runs as a terminal-launched process that already
  holds mic permission. If a mic permission dialog appears at any point,
  the run FAILED — fix the provisioning so it cannot.
- Speech input: the chain (E/F) uses the typed-transcript test mode
  injected at the EXACT real post-ASR boundary (same code path a real
  mic transcript takes; not a bypass of resolution/compose). The live
  mic hardware path (D) must still be proven once, from the terminal
  with terminal-seeded permission, by programmatically playing a real
  generated audio sample into the real device input path — never
  requiring a human to speak. If proving the live hardware path truly
  requires a human voice, that single fact is the ONE permitted residual
  note with the exact terminal reason — but the full A–I chain and 3/3
  repeatability must still complete fully autonomously without it.
- Browser: drive Chrome only via CDP from the terminal (already proven),
  never the GUI.

ANY human click, prompt, or manual step anywhere = the run FAILED. The
agent must engineer the clean-room so no GUI gate can occur, not wait
for a human to clear one. "It needs a click" is a provisioning defect to
fix at the root, not an allowed atom.

## ANTI-SOFTENING RULES (non-negotiable)
- No "honest caveat" section is acceptable. Not because you hide
  problems — because the bar is set so a real problem = FAIL. If you are
  writing a caveat, you are writing a failure. Report it AS a failure,
  fix the root cause, restart the clean-room.
- No "worked once". Only 3/3 untouched cold runs counts.
- No "should/likely/probably". Only a real artifact a human can
  reproduce in five minutes.
- No reclassifying a product failure as transient infra. A flaky model
  that breaks the chain is a product robustness defect to be handled IN
  the product (bounded self-recovery that actually works), not an
  excuse.
- No hand-cleanup, ever. The product fixes its own state or it FAILS.
- Frozen engine/reasoning/action paths and tags stay untouched (git
  diff over frozen dirs empty at the end). Only non-frozen integration/
  packaging/product layer may change.
- Do not commit unrelated prior-session files. Commit only the changes
  this goal required + the proof set, in logical chunks, then push to
  main.

## EXECUTION
Build and fix until A through I all hold across 3 untouched cold runs.
Two honest attempts per distinct root-cause defect, then a different
approach, never five alternatives, never a half-fixed state. When and
ONLY when every item holds with real artifacts across 3/3 runs: commit,
push to main, then write a plain "what a brand-new user on a brand-new
machine does, start to finish, and what proves each step" with the
artifact list. If you cannot reach 3/3, say "GOAL NOT MET" flatly with
the exact failing item and its root cause. Do not declare done with any
caveat. A caveat is a failure.
