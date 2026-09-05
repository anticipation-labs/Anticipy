# The hands, run live — 2026-09-05

**The first live end-to-end run of the browser agent on this tree, and the
first on any build since 0.8.4.** Production cannot host the run (the
`agents` table is malformed; see `research/2026-09-05-agents-table-malformed.md`),
so it was done on this machine against the repo's own local rig, with
production DNS blackholed inside the browser, on the real browser model.

## What was stood up

| piece | state | how |
|---|---|---|
| PocketBase 0.30.4 + this tree's hooks and migrations | up on 127.0.0.1:8090 | `sh proof/local_rig.sh up` — after the fix below |
| a local owner, the brain worker | up, `sms=mock`, `llm=live:google/gemini-2.5-flash` | same |
| Chrome for Testing 148.0.7778.97 | headed, fresh profile, `--host-resolver-rules` blackhole verified | `node proof/chrome_arm.mjs up --headed` |
| the extension | loaded unpacked from a frozen snapshot of the tree (not the live working tree, which the release chain was rewriting) | snapshot roots under the session scratchpad |

**The rig was dead.** `local_rig.sh up` had exited 0 on a PocketBase that
never came up: `1700000053_off_volume_backups.js` refuses to boot without the
four `ANTICIPY_BACKUP_S3_*` variables (correct in production), and a laptop
has none. The rig now supplies loopback placeholders. Commit `d53286a0`.

## Proof 2 — the install path (`proof/extension_smoke.mjs`)

Run twice, once per build, each against the rig with a freshly paired arm:

| leg | 0.12.0 (9eccebd6) | 0.13.0 (1bb4dc59) |
|---|---|---|
| backend answers | PASS | PASS |
| rig knows the owner | PASS | PASS |
| a fresh install can register (agents row, pair code, token server-side) | PASS | PASS |
| the phone can claim the pair code | PASS | PASS |
| a paired browser is given a model | `gemini-3.1-pro-preview`, `llm_proxy on` | same |
| a job queued the way the brain queues one | PASS | PASS |
| the queued job survived the write (params a JSON string) | PASS | PASS |
| Chrome's own poll filter finds it | PASS | PASS |
| a Chrome claims it | 4s, `ext/0.12.0` | 6s, `ext/0.13.0` |
| the run reaches an ending | `done: Example Domain` | `done: Example Domain` |

    VERDICT: the whole chain works — backend, pairing, model, queue, and a
    real Chrome ran the job to a finish.

Both times. The registration went through the rewritten `agent_auth.pb.js`
(the one that now logs and refuses on a thrown lookup), the model came
through the proxy with the floor at 512, and the claim went through the
guard. Nothing in this chain is a mock.

## Proof 1 — the hands battery (`proof/hands_battery.py`)

Eight scenarios built from failures Omar watched live, each graded on the
SITE's final state. The first run stalled every scenario at
`status=queued … [300s]`: the extension never claimed. Not the hands — the
harness: `claimJob` reads `ownerRef` from storage and refuses with "this
browser is linked, but the link has no owner id" when it is absent, and the
battery still wrote the key's old name, `owner`. Fixed in the harness (both
names written, plus the agent-credential keys the newer claim path expects).

Results: **see the table appended below when the run completes.**

## What this proves and what it does not

Proven: a browser install can register, pair, get a model, claim and run a
job on this tree, twice, on the real model, through the real hooks. The
extension is not broken.

Not proven: how WELL it does the errands that matter (the battery is the
instrument for that, running), and anything about production — where the
same hooks refuse every install until the `agents` table is repaired.
