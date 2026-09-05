# The agents table is malformed — 2026-09-05, found by the deploy, not caused by it

**Status: OPEN, repair built and proven, waiting for the switch below to be
thrown. Production's `agents` collection cannot be read; the browser agent
cannot authenticate or register; the ears are unaffected.**

## What was seen

The 0.12.0 deploy (`fd538eaf`, 04:15Z) went SUCCESS, `is_it_live.py` went
green on the served extension (0.12.0, byte-identical), and the boot log then
filled with one line every thirty seconds:

    agent registration: agent_id lookup failed: GoError: database disk image is
    malformed (11); failed query: SELECT `agents`.* FROM `agents` WHERE
    [[agents.agent_id]] = {:tq6vQ8ACn} LIMIT 1

and, within one second of boot, `guard: unrecognized agent credential from
e7cff411-…` — an installed browser agent being refused. The guard refuses on a
THROWN lookup as well as an empty one, by design (guard.pb.js: "a guard that
fails open when the database hiccups is a guard you open by making the
database hiccup"), so a corrupt table reads to it as a bad credential.

Every other collection reads normally, measured with the service token after
the deploy: owner_profile 6, jobs 173, events 800, segments 16,
agent_audit_sessions 125, agent_llm_audit 100, purges 7, pendants 0,
evidence 0, owners 0. `agents` alone answers 400 on a plain list.

The volume is not full: 0.6 GB of 4.9 GB, `data.db` 270 MB, WAL 8 KB.

## Why the deploy did not cause it

- The three migrations it shipped touch `_params` (053), `owner_profile`
  (054 — 0 duplicates on live, so it deleted nothing; still 6 rows after) and
  `jobs` (055 — 173 rows, readable). None touches `agents`.
- Railway attaches a volume to one container at a time, so two PocketBase
  processes did not overlap on the file.
- **The newest row in `agent_audit_sessions` and in `agent_llm_audit` is
  dated 2026-08-14 06:59Z.** No browser agent has completed an authenticated
  act in production since. The full-disk incident recorded in `start.sh` and
  `Dockerfile` — "disk I/O error", crash loop — is dated 2026-08-15. SQLite
  under disk-I/O errors is exactly how a b-tree page goes bad. The timeline
  fits without a gap: the hands died with the disk on the 15th of August and
  nothing said so for three weeks, because the previous hooks turned a thrown
  lookup into a silent fall-through and the served extension (0.8.4) had no
  registration path that logged.
- The previous deployment's logs are gone (Railway keeps only the active
  deployment's), so this cannot be proven from the log side. It is the
  simplest story consistent with every fact above, and today's deploy is not
  in it.

## What the deploy changed about it

Only that it became visible. The rewritten `agent_auth.pb.js` logs the throw
and answers 503 instead of registering on top of it; the rewritten guard
refuses instead of passing. Both are correct, both are why this page exists.

## What SQLite said — the diagnostic boot, 04:38Z

The image had no `sqlite3` and the container shell is not available from this
session, so the answer was fetched the only legitimate way: `start.sh` now runs
a read-only `PRAGMA integrity_check`, a forced table scan of `agents`, and
`pragma_index_list('agents')` at every boot. The second deploy (`e2d3eb48`)
logged, verbatim:

    boot: integrity *** in database main ***
    boot: integrity Tree 49 page 273: btreeInitPage() returns error code 11
    boot: integrity Tree 49 page 693: btreeInitPage() returns error code 11
    boot: integrity Tree 51 page 582: btreeInitPage() returns error code 11
    boot: integrity Tree 51 page 587: btreeInitPage() returns error code 11
    boot: integrity Tree 51 page 319: btreeInitPage() returns error code 11
    boot: integrity Tree 51 page 236: btreeInitPage() returns error code 11
    boot: integrity Tree 50 page 590: btreeInitPage() returns error code 11
    boot: integrity Tree 50 page 573: btreeInitPage() returns error code 11
    boot: integrity Error: stepping, database disk image is malformed (11)
    boot: integrity Tree 50 page 572: btreeInitPage() returns error code 11
    boot: integrity Error: stepping, database disk image is malformed (11)
    boot: integrity agents index: idx_agent
    boot: integrity agents index: sqlite_autoindex_agents_1

Read it as: three b-trees with roots 49, 50 and 51 have pages whose headers
no longer parse. `agents` is exactly three b-trees (the table and its two
indexes, created together by `1700000002_agents.js`), and it is the only
collection the API cannot read, so those are its trees. The forced table scan
printed no count — the ROWS' own pages are among the bad ones, not only the
index — and integrity_check aborted before it had walked the whole file, so
trees after 51 in its order are unverified (the API reads every other
collection's first page fine; deeper pages have not been touched).

**A `REINDEX` cannot fix this** — it rebuilds indexes from rows, and the
rows are what is broken.

## When it happened, narrowed

- The six newest `jobs` rows, minted 2026-09-04 03:16–03:23Z, are all
  `queued` with `claimed_by` empty. No browser agent claimed a job on the 4th.
- The newest `agent_audit_sessions` / `agent_llm_audit` rows are 2026-08-14.
- PocketBase writes a backup with `VACUUM INTO`, which reads every page, and a
  backup dated 2026-09-01 02:27Z sits on the volume. If that backup is whole,
  the file was intact on the 1st and the damage is between the 1st and the
  4th; the 2026-08-30 full-volume incident that `start.sh` records is the
  nearest disk-level event either side of that window.

Either way: before today's deploy, and not by it.

## The repair, built and proven, waiting for a hand

`backend/repair_data_db.sh` runs SQLite's `.recover` — walk every page that
still parses, write what it finds as SQL, put orphaned cells in a
`lost_and_found` table — into a fresh file, and swaps it in only if SQLite
calls the new file `ok`. The original `data.db` (with its WAL and SHM) is
kept beside it under the tag, so the whole thing reverses with one `mv`.
A marker file makes each tag one-shot; a file that is already `ok` is left
untouched. `tests/test_repair_data_db.py` builds a real SQLite file, breaks
the pages under one table, and runs the very script `start.sh` runs; each of
its four guarantees was mutation-checked (copy skipped, marker skipped,
healthy guard removed, swap-on-not-ok) and each went red.

It runs only when told to. **To run it:** on the Railway service, set

    ANTICIPY_REPAIR_DATA_DB=2026-09-05-agents

Railway restarts the service on a variable change; the boot log will carry
`boot: repair:` lines ending in `done: data.db is the recovered file`, then
`boot: integrity after repair: ok`. Then unset the variable. The `agents`
rows that lived on the bad pages are gone — every browser install re-registers
and re-pairs, which the extension already does on a 403 — and whatever
`.recover` salvaged from them is in `lost_and_found` for a person to look at.
Expect the phone to need to pair with the browser again.

If the log says the recovered file is NOT clean, nothing was swapped, the
original is untouched, and the next step is a person with the 2026-09-01
backup, not this script.

## Blast radius while it stays open

Every browser-agent path: registration, pairing, `/agent/key`, jobs pickup by
the extension. The phone's capture and the brain's worker use the owner and
service credentials, not `agents`, and are unaffected — 82 lines arrived in
the last 24h after the deploy, both halves quiet together since 00:00Z.
