# The brain

The server-side mind. One process per owner reads that owner's `events`,
updates their memory, decides ask / act / ignore with a model given full
context, mints and closes `jobs`, and writes back everything Anticipy says.
Nothing in here decides meaning with a pattern (HARNESS-LAWS.md Law 1).

## One image, two roles

`brain/Dockerfile` builds one `python:3.11-slim` image whose `CMD` chooses
the role at start:

| `ANTICIPY_OWNER_REF` | Entry point | Role |
| --- | --- | --- |
| unset | `python -m brain.supervisor` | The fleet supervisor: discovers owners through the service-authenticated `/worker/owners` route and runs one OS process per owner (`python -m brain.worker`), each with its own state directory. Turns owners away above the cap rather than evicting them. |
| set | `python -m brain.container_entry` | One owner's brain on Cloudflare Containers: pulls that owner's `memory.db` and `clock_state.json` from R2, serves a control endpoint so the Durable Object can see the container is up, runs `brain.worker` unchanged, snapshots back to R2, takes a daily verified backup, and on SIGTERM stops the child and snapshots once more. |

The Durable Objects that start the containers (`OwnerBrain`,
`BrainSupervisor`) live in `migration/workers/brain/`; the deploy is
`.github/workflows/brain-deploy.yml` with `component=brain`
([docs/RELEASE.md](../docs/RELEASE.md)).

## The memory boundary

`memory.db` (`brain/memory.py`) is a temporal knowledge graph in SQLite:
episodes, entities, typed timestamped edges, commitments with a lifecycle,
and a profile layer distilled on top. It is one real person's mind. On
Cloudflare the container's disk dies with the instance, so the **durable copy
is the object in R2**; the container's file is a working copy pulled at boot
and snapshotted back. `container_entry.py` aborts loudly on a failed R2 read
and continues only on a genuine 404 (a new owner), because booting on an
empty directory when the object exists is silent memory loss.

None of this is ever committed: `.gitignore` excludes
`migration/workers/owners/` and `**/owners/*/memory.db`, where a local run
writes them. `overnight/is_memory_durable.py` is the gate that reads the R2
copy against each owner's newest decided row.

## Module map

| Module | Role |
| --- | --- |
| `worker.py` | The per-owner loop: poll events, hear, decide, mint, close loops, run api-lane jobs (`run_api_jobs`). |
| `anticipy_core.py`, `orchestrator.py` | The core decision and the model-asked verdicts: whose promise, ends in the world, sufficiency, licensed. |
| `memory.py` | The graph and the profile layer. |
| `workflow.py` | Deterministic workflow law: plans, consequence, approval, leases; `params._workflow`. |
| `hands.py` | Which hand takes a step — browser, api, research, hold — asked of a model; `params._hand`. |
| `conversation.py`, `reply_delivery.py`, `reply_authority.py`, `task_delivery.py` | The text channel and durable reply delivery. |
| `segmenter.py`, `sorter.py`, `links.py` | Where a conversation begins and ends; judging closed conversations, not lines. |
| `research.py`, `server_work.py`, `compute.py` | The read-only server arm; arithmetic is computed, never searched. |
| `connection_dispatch.py` | Connection HTTP kept off the serial reasoning loop. |
| `sendblue_arm.py`, `voice_arm.py` | The only places that talk to the messaging providers. |
| `supervisor.py`, `container_entry.py`, `state_backup.py`, `runtime_status.py` | Roles, snapshots, backups, and the running-source hash the deploy verifies. |
| `EXEMPLARS.md`, `EXEMPLARS-A-LIFE.md` | Worked examples wired into the prompt (Law 5: examples before structure). |

## Tests

```sh
PYTHON_DOTENV_DISABLED=1 python -m pytest -q
```

`tests/` holds the pytest suites over the modules here, plus the gates' own
logic and the local-D1 tests. `overnight/*.py` are the scoreboards; several
reach live systems and load a root `.env.local` if present, so read
[docs/TESTING.md](../docs/TESTING.md) before running one. The brain Worker's
own suites are `npm test --prefix migration/workers/brain`.
