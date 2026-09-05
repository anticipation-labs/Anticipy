# 2026-09-04 — Brain container code written (untested), Dockerfile deliberately not flipped

Authorized by the owner: "start writing the brain/ container code anyway,
marked untested." This records what was written, how far it was validated, and
the one change that was deliberately NOT made.

## What was written

Both files the deploy was blocked on (BRAIN-ON-CONTAINERS.md blocker table
rows 1 and 2) now exist:

1. **`migration/workers/brain/src/index.ts`** — the fleet on Cloudflare
   Containers. `OwnerBrain extends Container` (defaultPort 8731, requiredPorts,
   sleepAfter 24h, empty `onActivityExpired`, `envFor()` reproducing
   supervisor.py `child_environment()` including the `ANTICIPY_OWNER_PHONE` pop
   scar), `BrainSupervisor extends DurableObject` (`tick()` = discover every
   owner ordered by id, filter by the `/^[A-Za-z0-9_-]{8,64}$/` id guard,
   reconcile with the cap that TURNS OWNERS AWAY and never evicts, printing
   every over-capacity pass), and a `scheduled()` handler driving one
   fixed-name supervisor DO so two ticks never race.
2. **`brain/container_entry.py`** — one owner's brain with R2 standing in for
   the Railway volume. Pulls memory.db + clock_state.json before boot; a FAILED
   GET aborts loudly, only a genuine 404 continues (this is the whole safety
   property); control server on :8731; execs the UNCHANGED `python -m
   brain.worker`; 60s snapshot loop; daily verified zip; SIGTERM → final
   snapshot. Reuses `state_backup`'s tested routines (`_snapshot_sqlite`,
   `backup_config`, `_client`, `backup_state_to_s3`, `_sha256`) rather than
   re-implementing the dangerous parts.

## How far validated — and the honest ceiling

- `index.ts`: `tsc --noEmit` **exit 0** against `@cloudflare/containers@0.3.7`.
- `container_entry.py`: `python3 -m py_compile` **OK**; all 5 state_backup
  imports confirmed present.
- Wiring: new `migration/workers/brain/package.json` (declares the containers
  dep, keeps it OUT of the API Worker's package.json) + `brain/tsconfig.json`;
  0.3.7 vendored into `migration/workers/brain/node_modules` (offline copy from
  the spike stash).

**Neither file has run.** There is no Docker/container runtime and no R2 token
on this machine. Unlike every route ported this session, there is **no oracle** —
they could not be diffed against a working system. `container_entry.py`'s
failure mode is **silent data loss** (booting on an empty dir when the object
exists overwrites a live memory on the next snapshot). By CLAUDE.md law 3
("nothing is fixed until its gate leg is green against LIVE") these are NOT
done — they are faithful scaffolding for the validation session. Both carry a
prominent UNTESTED banner saying exactly this.

## The change deliberately NOT made: brain/Dockerfile:14

The runbook (BRAIN.md §8.2 / §10.4, BRAIN-ON-CONTAINERS.md §371) says to change
`brain/Dockerfile:14` from `CMD ["python","-m","brain.supervisor"]` to
`brain.container_entry`. **Not done, on purpose:**

- `brain/Dockerfile` is the LIVE Railway `worker` image (HANDOFF.md:330).
- `container_entry.main()` returns 2 ("Refusing to boot") when
  `ANTICIPY_OWNER_REF` is empty, and `_r2()` raises when the S3 config is
  absent — neither of which Railway provides. So the flip would **break the
  running brain** on the next Railway deploy/restart.
- BRAIN.md §10 places the flip at **cutover step 4**, after the R2 bucket
  exists (step 2) and one manual state upload is proven (step 3). It is a
  one-way change belonging to the cutover sequence, which the owner is driving.

## Still blocking a brain deploy (owner / cutover, not code)

3. No Docker engine here → build in CI.
4. R2 bucket `anticipy-owner-state` does not exist yet.
5. `brain/Dockerfile:14` CMD flip (cutover step, above).
6. Runtime validation of both files against a real container + R2 (§10.6).

None of these are writable from this machine. The code half of the brain
migration is as far as it goes without a container runtime.
