# The repair tool would swap in a database that had lost a table

Found 2026-09-06 by chasing a CI failure that had been red for five pushes and
looked like a broken test.

## What it was

`backend/repair_data_db.sh` is the tool for the failure production actually had
on 2026-09-05: `agents` answering every read with "database disk image is
malformed (11)". It runs SQLite's `.recover`, and it is careful — it keeps the
original byte for byte, it refuses to swap unless the recovered file passes
`PRAGMA integrity_check`, and it is one-shot per tag.

The integrity check is the hole. **An empty database passes `integrity_check`
as "ok"**, because an empty database is a valid one. So step 4 cannot tell a
repaired file from a file with nothing left in it.

Step 5 counted every table on both sides and PRINTED the counts. That is all it
did. On GitHub's runner:

    repair: rows owners: original=50 recovered=missing
    repair: 't1' done: data.db is the recovered file

It said `recovered=missing` and then swapped it in and called it done.

## Why `.recover` lost a table that was never damaged

The test's fixture punched holes in what it believed were `agents` pages, then
satisfied itself that `owners` was intact with `SELECT count(*) FROM owners`.

`owners` is `id TEXT PRIMARY KEY`, so it carries `sqlite_autoindex_owners_1`,
and SQLite answers a bare `count(*)` by counting the INDEX. The index was
perfect. The table's own b-tree was full of holes. `.recover` reads TABLE
pages, found nothing, and correctly produced a file without that table.

So three things were wrong at once and each hid the next:

1. The fixture guessed page layout (`root+3 .. root+6`) from one SQLite
   version's allocator, so on the runner the holes landed outside `agents`.
2. Its intactness check read an index, so it never noticed.
3. The script printed the loss instead of refusing it.

Only the third one is a production defect. It is the one that matters.

## Fixed

- The script's step 5 is a GATE. A table the original can still count that is
  GONE from the recovered file stops the swap: nothing is moved, the original
  stays where it is, and the recovered file is left for a person.
- FEWER rows deliberately does not stop it. Losing rows out of the damaged
  table is what `.recover` is for — they go to `lost_and_found`, which is the
  next line of output. A gate that refused on any shortfall would refuse every
  real repair it exists for. The shortfall is now named per table.
- The fixture finds its pages instead of guessing: punch, keep the hole only if
  `owners` and `events` still read whole AND the file is damaged, put the bytes
  back otherwise. `NOT INDEXED` on those reads, which is what the script itself
  had said all along and the test had not.
- `test_a_recovery_that_lost_a_table_is_refused` drives the branch with a
  `sqlite3` shim that is the real thing except for counting `owners` in the
  recovered file. Mutating the gate back to a bare report kills that leg alone.

## The part worth remembering

The failure was visible in the script's own output, in the words
`recovered=missing`, on every run. Printing a number is not checking it. A
report that nobody has written an assertion against is decoration.

And the CI message was `sqlite3.OperationalError: no such table: owners` — a
production-data-loss defect that read like a rotted test, which is why it sat
red across five pushes with everyone walking past it.
