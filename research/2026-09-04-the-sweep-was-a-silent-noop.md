# The Worker's sweep cron was a silent no-op, and nothing could have told us

2026-09-04. Found while diffing `/internal/state` between production and the
Worker after production's key arrived.

## How it surfaced

The two payloads matched on every list except todos: production had 8 more.
All 8 were created at `2026-09-04 08:00:00`, and production's activity feed
carried one row explaining them — `repeat.laydown`, "Laid down 8 repeating
tasks for 2026-09-04". Clean drift from a cron that ran after the migration
snapshot, not a port defect.

Except the Worker has that cron too, on `*/5 * * * *`, and it had laid down
nothing — ever.

## What was actually there

`src/cron.ts`'s sweep was a documented skeleton, which is fine. What was not
fine is what the skeleton did:

    const due = await env.DB.prepare(
      `SELECT * FROM "internal_reminders" WHERE "sent_at" = '' ...`).all();
    for (const row of due.results ?? []) {
      const ok = await sendSMS(env, String(row.to ?? ""), String(row.text ?? ""));
      if (!ok) continue;
      await env.DB.prepare(`UPDATE "internal_reminders" SET "sent_at" = ?1 ...`)
    }

`internal_reminders` has no `to` column and no `text` column. Its columns are
id, todo, person, rule, fire_at, channel, label, sent_at, attempts, created_by,
created, updated. So `row.to` was `undefined`, `String(undefined ?? "")` was
`""`, `sendSMS` refused on the empty recipient, and `continue` skipped the
`sent_at` write.

Every five minutes: select due reminders, send nothing, mark nothing, log
nothing, throw nothing. A cron that reports success by being quiet.

This is the shape `overnight/are_the_ears_live.py` exists for — the failure
where the only symptom is silence, and silence is also what healthy looks
like. It would have shipped as a working cron, and the first person to notice
would have been whoever eventually asked why HQ stopped reminding them.

## What the deployed sweep actually does

Six passes, ~500 lines, not one:

    A  todo.remind_at        the one-shot bell
    B  follow-ups            one nudge, ever, 2 days past due
    C  internal_reminders    the ones one column cannot express
    D  the notification digest, one message per person per sweep
    E  research slot backstop
    F  the repeat motor

All six are ported now. The discipline that matters throughout is CLAIM FIRST,
THEN SEND: this cron refires every five minutes forever, so send-first with a
failed persist is unbounded duplicate texts. The stamp rolls back only when
every channel failed, and after three tries it stays stamped and logs the
give-up, because a permanently wrong phone number must not generate a real
Twilio call every five minutes until somebody happens to look.

## How the port was verified, which was possible for once

The repeat motor has an oracle nothing else here had: production ran it at
08:00 today and its output is visible. The Worker's D1 was still at the
pre-laydown state, so a correct motor had to produce the same 8 rows.

It did. `146 vs 146 todos`, and the sets of `(title, track, due, status)` are
identical. Pass B independently selected the same 9 past-due todos production
nudged at 00:00, by title.

A second run changed nothing — 146 to 146, still one `repeat.laydown` row —
so the dedupe holds.

## One thing the test got wrong, recorded because it is a real property

The first trigger produced 14 rows, not 8. Two `repeat.laydown` activity rows
52 ms apart gave it away: the readiness probe in the test loop hit
`/__scheduled` and so did the explicit call, and `ctx.waitUntil` let both
sweeps run CONCURRENTLY. Both read a state with no 2026-09-04 rows, and both
laid down. Six duplicates, since deleted.

The motor's logic was right; the harness was wrong. But the underlying
property is real and worth writing down: `SELECT ... LIMIT 1` then `INSERT` is
not atomic, in this port or in PocketBase's original. Neither scheduler
overlaps its own runs, so it does not bite in practice — and it is one
`wrangler dev --test-scheduled` away from biting anybody who tests it the way
I did.

## The other bug fixed on the way

`sendSMS` read only `TWILIO_PHONE_NUMBER`. The source reads
`TWILIO_PHONE_NUMBER || TWILIO_FROM` (internal_hq.pb.js:2167). A deployment
that set only the second would have sent nothing and reported nothing — the
same silent shape, one variable away.
