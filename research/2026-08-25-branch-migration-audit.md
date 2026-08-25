# Is anything stranded on another branch? No.

**Date:** 2026-08-25
**Asked by:** the Brief — "MAKE SURE EVERYTHING IS BROUGHT BACK TO THIS BRANCH OF
`jose_anticipy_system` ... if you need to migrate any code from any other
branch do it"

**Answer: nothing needs migrating.** `jose_anticipy_system` is the most advanced
lineage in the repository. Evidence, so nobody has to re-derive it:

## harness/tejas-fixes — where the Brief lives

    git rev-list --left-right --count jose_anticipy_system...harness/tejas-fixes
    ours-only: 84    theirs-only: 0

Zero commits exist there that are not here; the merge base IS that branch's
HEAD (`e60946a4`). `docs/BRIEF.html` is byte-identical — same blob
`5d90c2bd7de3b6e9dff686180a1a9f4af6d9a9f5`.

One file it has that we do not: `…/swiftpm/Package.resolved`. That is a
DELIBERATE deletion by `d3ccb133` (unlinking sherpa-onnx), and the Brief itself
calls it "a stale inert leftover". Restoring it would undo the ears fix.

## origin/main and the 400-900 commit branches

    git merge-base jose_anticipy_system origin/main  ->  (none)

**Unrelated histories.** No shared root. That lineage is the anticipy.ai
website, not the product — which is why its commit counts look alarming and
mean nothing. Same for devin/*, hoe/build, deploy/*, feature/*, recon/*.

## pendant-system (8 commits) and codex/anticipy-v75 (4 commits)

These LOOK like product work and are the only two worth checking: build 51-52
and build 75 era respectively, against our build 82. Between them, 11 files
exist there and not here. Every one is superseded or refused:

| Their file | Status here |
|---|---|
| `agent/browser_agent.py` | superseded by `extension/agent_loop.js` |
| `backend/sms_server.py` | superseded by `backend/pb_hooks/sms.pb.js` |
| `app/core/audio_pipeline.py` | superseded by `app/ios/Anticipy/Audio/PhoneListener.swift` |
| `app/ios/Anticipy/Brain/BrainClient.swift` | DEAD CODE — zero call sites, and the Brief §4 names it vestigial |
| `app/ios/Anticipy/Audio/CloudEars.swift` | would stream audio to Deepgram — LOCAL-FIRST.md:28 "RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone" |
| `backend/pb_hooks/ears_key.pb.js` | serves the above; same refusal |
| `Package.resolved` | deliberately deleted, see above |
| proof/tests (`replay_ignore.py`, `replay_settled_e2e.py`, `test_end_to_end.py`, `test_bare_ack.py`) | older harnesses; the content landed here under different SHAs — e.g. `tests/test_twilio_auth_and_delivery.py` and `tests/test_webhook_reachability.py` from codex/v75 are both present |

## The trap this audit avoided

Commit counts do NOT answer "is content missing". Those branches show 4 and 8
commits we lack, but their content mostly arrived here under different SHAs, so
counting commits would have produced a migration nobody needed. The question is
answered by diffing TREES (`git diff --diff-filter=A A..B`), not by counting
commits — and note the filter direction: `D` on `A..B` lists what OURS has that
theirs lacks, which reads as the opposite of what you want and briefly did.
