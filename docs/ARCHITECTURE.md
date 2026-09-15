# Anticipy architecture

A system-level view: which runtimes exist, what they share, and how a claim
about the product climbs from "the source says so" to "a customer saw it".
Component-level references are linked, not repeated.

## Runtimes

| Runtime | Where | Role |
| --- | --- | --- |
| iPhone app | `app/ios/` | The owner's ears and face. Captures speech (phone microphone; pendant over BLE, see below), posts `events`, shows the feed and confirm cards, delivers replies, runs the device hand (calendar), and pairs the browser. |
| Mac app | `app/macos/` | The meeting recorder. Both sides of a call transcribed on device; lines are posted as `events` with `source = "mac"`. Raw audio never leaves the Mac. |
| Chrome extension | `extension/` | The browser hand. Polls the API for jobs on the browser lane and runs them in the owner's own logged-in Chrome. Never foregrounds itself. |
| API Worker | `migration/workers/` | The one backend: Cloudflare Worker over D1 (`migration/d1/schema.sql`), R2 (evidence) and the `PairCodeCounter` Durable Object. Serves the records API, the product routes, HQ, and the static downloads (Worker assets under `migration/workers/public/`). |
| Brain Worker | `migration/workers/brain/` | The fleet controller on Cloudflare Containers: `BrainSupervisor` discovers owners from D1 and reconciles the running set; `OwnerBrain` is one container per owner. |
| Python brain | `brain/` | The mind. One image, two roles (see [brain/README.md](../brain/README.md)): `container_entry.py` pulls the owner's `memory.db` from R2 and runs `worker.py`, the per-owner loop. |
| Pendant firmware | `firmware/` | A Zephyr candidate for the XIAO nRF52840 Sense that streams Opus over encrypted BLE. Host-checked in this tree; not built, flashed, or proven on hardware here. |

Deeper references:

- Worker design and the PocketBase baseline it replaced:
  [migration/workers/ARCHITECTURE.md](../migration/workers/ARCHITECTURE.md)
- The behavioural oracle every route is held to:
  [migration/spec/CONTRACT.md](../migration/spec/CONTRACT.md)
- The internal dashboard (HQ) routes: [migration/workers/HQ.md](../migration/workers/HQ.md)
- The brain on Containers: [migration/workers/BRAIN.md](../migration/workers/BRAIN.md)
  and [migration/BRAIN-ON-CONTAINERS.md](../migration/BRAIN-ON-CONTAINERS.md)
- The pendant/phone boundary: [docs/FIRMWARE-COLLABORATION.md](FIRMWARE-COLLABORATION.md)
- The Two Hands and connections spec: [docs/spec-connections.txt](spec-connections.txt)

## One pass through the system

```text
 capture                 inbox                   mind                      work                    outcome
 ───────                 ─────                   ────                      ────                    ───────
 iPhone mic ─┐
 pendant ─BLE┤─► events row ──► brain/worker.py ──► jobs row ──► which hand? (brain/hands.py)
 Mac recorder┘   kind=transcript   (one process       params._workflow        │
 typed reply     source=...         per owner,        params._hand      ┌─────┼──────────┐
                                    memory.db)                          ▼     ▼          ▼
                                                                    browser  API hand   device
                                                                    (ext.)  /hands/api/run (phone)
                                                                        │     │          │
                                                                        └─────┴──────────┘
                                                                              ▼
                                                                  receipt on the jobs row
                                                                              ▼
                                                        iPhone feed, reply, text message (reply_delivery)
```

1. **Capture.** The phone posts one `events` row per utterance with `kind =
   "transcript"` and `source` set to `phone_mic`, `pendant` or `typed`
   (`app/ios/Anticipy/AnticipyApp.swift`); the Mac posts `source = "mac"`.
   The pendant path currently stops at the phone: the app receives Opus
   frames but does not decode them (see the firmware handoff).
2. **Inbox.** The `events` table is the inbox. Every row carries `owner_ref`;
   the brain reads only its own owner's rows.
3. **Mind.** `brain/worker.py` polls, runs each line through the core
   (`brain/anticipy_core.py`, `brain/orchestrator.py`), updates the owner's
   memory graph (`brain/memory.py`, a SQLite file), and writes decisions and
   anything Anticipy wants to say back as `events` the phone renders.
4. **Work.** A decision to act mints a `jobs` row. `params._workflow`
   (`brain/workflow.py`) carries the plan, consequence class, approval and
   lease facts the Worker's `workflow_guard` policy checks on every write.
   `params._hand` (`brain/hands.py`) carries the model's verdict on which hand
   takes the step: browser, api, research, or hold. Hold and no-verdict land
   on the research lane, which no browser may claim.
5. **Hands.** The browser lane is claimed by the paired extension; the API
   lane is claimed by the brain (`claimed_by = "worker-api"`) and executed by
   `POST /hands/api/run` in the Worker; the device lane is executed by the
   phone (`app/ios/Anticipy/Backend/NativeCalendarHand.swift`).
6. **Outcome.** `done` requires a verified receipt on the row
   (CONTRACT.md §1.15). The phone shows the receipt; `brain/reply_delivery.py`
   delivers the reply to the feed and, where configured, by text.

## Shared contracts

**Owner identity.** `owners` is the account table; the phone and Mac hold an
account token, the extension holds a per-agent credential, the brain and its
proofs hold the service token. `events`, `jobs` and `agents` all carry
`owner_ref`. The brain runs one OS process (one container) per owner so no
memory, clock, or cache is ever shared between people.

**`events` — the inbox.** Columns of note: `kind` (`transcript`, `decision`,
`action`, `confirm`), `source`, `speaker` (the phone's local voice verdict),
`capture_started_at` / `capture_ended_at` (the capture clock, not arrival
time), `segment`, `owner_ref`. See `migration/d1/schema.sql`.

**`jobs` — the work.** `status`, `lane` (`''` browser, `research`, `api`,
`device_calendar`),
`claimed_by`, `lease_token` / `lease_until` (the executor's lease),
`watching_until` (the owner's presence), `receipt`, `reconciliation`,
`effect_uncertain`, and the JSON `params` carrying `_workflow` and `_hand`.
The status ↔ state table and the complete refusal inventory are in
CONTRACT.md §1.

**Agents and pairing.** The extension registers itself (`POST /agent/register`)
and receives a permanent six-digit `pair_code` and a client-generated
`agent_token` that the API never returns. The phone claims the code with the
account token, which is the only caller allowed to set `owner_ref` on an
`agents` row. The other `/agent/*` routes — `GET /agent/key`,
`POST /agent/llm` (the model proxy), `POST /agent/solve-captcha`,
`POST /agent/upgrade-credential` — are authenticated by the per-agent
credential (CONTRACT.md §6). Unpairing clears the owner on the row; the
installed-extension rig's `phone-repair` and `phone-release-legacy` scenarios
check that the extension then wipes the owner's profile and key.

**`POST /hands/api/run`.** Runs one claimed api-lane job on the API hand
(`migration/workers/src/routes/hands_api.ts`). The body names a job id and an
owner as a check, never as an input: toolkit, tool, arguments, effect and
confirmation all come off the row.

**Connections.** `connections` rows are keyed by the provider's connected
account id and carry `user_id`, `toolkit`, `alias`, `status` and
`writes_enabled`, which is off by default: the Settings switch "let Anticipy
make changes" is the only thing that turns it on, and reads never need it.
Connect flows live under `migration/workers/src/connections/` and
`migration/workers/src/routes/connect*.ts`.

**Policy chain.** Every write to the records API passes `guard` →
`owner_profile_owner` → `research_lane` → `workflow_guard`, in that order,
so a credential failure is a 403 before a workflow refusal can be a 409
(CONTRACT.md §0.4; `migration/workers/src/policy/`).

## The evidence ladder

A claim about the product is only as strong as the highest rung it has been
carried to. Each rung has its own instruments; none of them stands in for the
one above it.

| Rung | What it proves | Instruments |
| --- | --- | --- |
| 1. Source | The code says so. | Reading the file; `git log`. |
| 2. Local gates | The logic holds offline. | The suites in [TESTING.md](TESTING.md); `overnight/*_gate.py` scoreboards. |
| 3. CI | The same suites hold on a clean runner; iOS and Mac compile. | `system-invariants.yml`, `ios-candidate.yml`. |
| 4. Deployment | The bytes are live. | `brain-deploy.yml` (api / brain) and its live release proofs; the `x-anticipy-revision` header; ZIP hashes; TestFlight processing. |
| 5. Installation | A person's device is running them. | App Store Connect readback (`asc-query.yml`); the installed-extension rig (`proof/audit/installed_extension/`); a signed Mac archive hash. |
| 6. Customer acceptance | It did the job for someone. | Cold onboarding and unscripted use recorded on the [readiness board](EOD-READINESS-2026-09-13.md). |

Three-state semantics apply on every rung: green (exit 0), red (non-zero), and
UNPROVEN (exit 2) when the instrument could not measure. UNPROVEN is a third
state, not a soft pass. HARNESS-LAWS.md Law 3 is the rule behind the ladder:
nothing is fixed until its gate leg is green against the live system.
