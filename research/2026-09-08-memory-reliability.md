# Memory reliability — local verification, 8 September 2026

Scope: two memory defects from the layer audit, plus one evidenced missing
checkpoint case in container startup. No production reads, deployment, or
real model calls were used. This is local verification, not Law-3 live proof.

## Reproductions and changes

The old episode query selected the newest 300 OR matches, then ranked what
survived. An old gate code was recalled with 299 later one-word matches and
lost with 300, 301, or 1,000. Both FTS and the fallback had the defect.

Retrieval now ranks the matching history before taking its bounded window.
Duplicate episode wording and retired provenance cannot fill that window.
The existing search score remains a retrieval ranking, never a verdict about
what an owner meant or permission to mutate a fact. An in-memory stress check
recalled the original code through 100,000 later matching lines in 0.1415
seconds on this Mac. It is a local measurement, not a production latency SLA.

An unanswered veto comparison previously raised a generic RuntimeError inside
the nightly transaction and rolled back every candidate. The known unanswered
write comparisons now raise MemoryWriteDeferred. Consolidation isolates that
candidate with a savepoint and persists its evidenced fields in the new
deferred_consolidation table in the same owner SQLite checkpoint. Successful
facts and the episode cursor commit together with this retry queue. Each pass
retries a bounded group, oldest-attempted first, at most once per nightly
timestamp, and still processes newer
episodes. A later positive veto discards the candidate; a later outside verdict
allows normal insertion. Original timestamps, episode provenance, speaker
source, and model-assigned stability survive the retry. Historical comparisons
that cannot yet rule out resurrection use the same deferred path.

Unexpected database or programming exceptions still roll back the whole pass.
The retry queue is not a profile and none of its candidate text is returned by
recall. Its additive CREATE TABLE runs when an existing Memory database opens;
it requires no standalone migration or production operation. The consolidate
result exposes the outstanding count as deferred, and the worker logs it.

## Container startup

The worker opens its memory before writing its outreach clock, and snapshots
upload memory before clock. A missing remote memory.db with an existing clock
therefore proves an incomplete established-owner checkpoint. Startup now
refuses this case before installing either staged file. Existing local files
remain intact.

Both objects missing still cannot distinguish a legitimate new owner from
lost state. Full protection requires an authoritative initialized/snapshot-seen
marker in OwnerBrain's Durable Object storage, or verified backend history,
checked before starting the container. The current owner environment has no
such signal. A nonempty bucket or a freshly initialized SQLite file alone does
not prove continuity of an owner's memory. That broader lifecycle change was
not inferred or implemented here.

## Offline verification

262 tests passed across memory, worker consolidation, container boot, profile
ranking/seeding, retired fact containment, and runtime health. The new tests
also cover restart retries, continued learning the next day, vetoed
supersession, guest provenance, unchanged confidence for facts already
committed, rollback on database failure, and incomplete checkpoint rejection.
git diff --check passed. Independent review caught an initial long-query SQL
depth regression and repeat retries within one nightly batch loop. Both were
corrected: VALUES supplies query terms without depth-growing expressions,
1,000/2,000-term FTS and fallback queries retain all terms, and same-timestamp
batches do not re-ask an already unavailable judge.

```sh
.venv/bin/python -m pytest tests/test_memory*.py \
  tests/test_worker_consolidation.py tests/test_container_boot_state.py \
  tests/test_profile_ranking_doctrine.py \
  tests/test_library_no_bare_wording_leaves_the_profile.py \
  tests/test_profile_seed.py tests/test_runtime_status.py -q
```

Remaining limits: extraction output failures retain the pre-existing batch
retry/skip policy. A long-lived unavailable judge can grow the durable deferred
queue; candidates remain withheld, and retries are bounded per pass. Production
retrieval, R2 restoration, snapshot durability, and actual model behavior have
not been exercised in this local pass.
