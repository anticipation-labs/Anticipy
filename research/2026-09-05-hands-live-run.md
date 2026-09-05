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

## Proof 1, the result — `proof/hands_battery.py --rig`, 0.13.0, gemini-3.1-pro-preview

    hands battery (rig): 7/8
      ok   native_date    — status=done  site {'date':'2026-08-12','time':'2:00 PM'}                       [78s]
      ok   readonly_date  — status=done  site {'date':'Tue Aug 11','time':'1:30 PM','party':'3 people'}   [36s]
      ok   site_defaults  — status=done  site {'date':'Wed Aug 12','time':'12:00 PM','party':'4 people'}  [34s]
      ok   no_identity    — needs_user "I need your first and last name to finish the reservation." invented=None [10s]
      ok   unnamed_branch — needs_user "Which location would you like to book?" visited=[] booked=None   [10s]
      ok   otp_resume     — phase1 needs_user (resume_tab carried) → v2 resume accepted by the guard → phase2 done, site_verified=True [50s]
      ok   autocomplete   — status=done  picked {'city':'Vancouver (YVR)'}                                [20s]
      FAIL general_form  — needs_user "I am about to submit the ticket with the message: 'I was charged twice for order A-7741.'" ticket=None [32s]

Every claim landed in 2–4 s through `workflow_guard`; the OTP resume, version
2 with the approval re-bound, was accepted by the guard live and re-claimed in
2 s. Traces: `proof/hands_battery_traces.json` (committed with the port).

**The eighth row is the law working, not the hands failing.** A support ticket
is a message to another human — shelf 3 in Omar's ruling, tap first, forever —
and audit #66 made "a message the agent composed in his name is shown to him
before it goes out" a verdict. The hands stopped and showed the draft. The
grader, written before both rules, expected a silent submit. It now grades two
shapes: his words carry the text → submitted; his words do not → the draft is
shown and nothing is sent (commit alongside this note). Not yet re-run.

## The map moved while this ran

Production is on Cloudflare (`api.anticipy.ai` = Worker + D1; brain on
Containers; Railway is the fallback for shipped clients). Everything above
was measured on the repo's local rig, which runs the PocketBase hooks — the
Worker carries its own TypeScript port of them, and on the Worker
`POST /agent/llm` still answers 503 "llm proxy not yet ported". So on
Cloudflare the browser agent cannot make one model call until that port
lands. `research/2026-09-05-cloudflare-era-plan.md` is the plan from here.

## Proof 2 on PRODUCTION — `extension_smoke.mjs` against api.anticipy.ai

Same day, after the Worker gained the model proxy (`47c6f8d5`, deployed
`02aa186d`). One disposable owner, `e2e-2026-09-05@anticipy-test.invalid`
(`qeuy6sv1raof9rw`; the `.invalid` suffix keeps the brain fleet from ever
spawning a container for it), a Chrome for Testing paired to that owner and
only that owner, the Railway host blackholed inside it.

**First run: leg 3 FAILED, and it was real.** `POST /agent/register` on the
Worker returned `agent_id`, `agent_token` and `pair_code` but not the row
`id` that `agent_auth.pb.js:62` returns and `background.js:181-196` stores
as `recordId`. A real 0.13.0 install then re-registered on every poll — 409,
fresh agent_id, 200 without an id — one junk `agents` row per poll, **62 rows
in 165 s**, a browser that could never pair. The contract test for
registration had never asserted the id. Fixed in `640e8bc8` (register
returns `id`; the contract pins it), deployed as `f3d9da08`; the 85 junk
rows were tidied.

**Second run, the UNMODIFIED smoke, after the fix:**

    1. PASS  the backend answers
    2. PASS  this rig knows who the owner is
    3. PASS  a fresh install can register       agents row miamu5arakt40jb, pair code 403124
    4. PASS  the phone can claim that pair code
    5. PASS  a paired browser is given a model  gemini-3.1-pro-preview · llm_proxy on
    6. PASS  a job can be queued the way the brain queues one
    7. PASS  the queued job survived the write
    8. PASS  Chrome's own poll filter finds the job
    9. PASS  a Chrome claims the job            4 s
   10. PASS  the run reaches an ending          done: Example Domain
    VERDICT: the whole chain works

The model calls went through `/agent/llm` on the Worker: two `agent_llm_audit`
rows, provider **openrouter**, model gemini-3.1-pro-preview, status ok, the
caps the client asked for (4096, 1024) honoured, 127 and 96 output tokens of
which 117 and 87 were reasoning — the thinking model the 512 floor exists
for. No Gemini key is bound on the Worker, so Google models ride OpenRouter,
the transport the 66/66 measurement used.

Rows left on D1 as evidence: the test owner, its profile, two done jobs
(`aaccf4eyqx3lhwo`, `fnw42cqwht7lo8s`), the audit rows. Every agent row was
deleted.

**What this proves:** the hands work on the backend that serves users. What
it does not prove: a real errand on a real site through the Worker (the
battery ran on the local rig), and the 0.13.0 that users download still
DEFAULTS to Railway — 0.14.0 moves the default to api.anticipy.ai.
