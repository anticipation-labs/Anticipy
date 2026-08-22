/// <reference path="../pb_data/types.d.ts" />

// THE REQUEST-LOG DATABASE TOOK THE WHOLE PRODUCT DOWN. Again.
//
// 2026-08-21, measured off the boot guard's own du on the production volume:
//
//   boot: /pb_data free 0KB
//   boot: du 3960824  /pb_data/auxiliary.db     <- 3.96 GB
//   boot: du  475688  /pb_data/backups
//   boot: du  264328  /pb_data/data.db
//
// auxiliary.db is PocketBase's own request log. It was FIFTEEN TIMES the size
// of the actual data, it filled a 5GB volume, and SQLite then answered every
// single write with `database or disk is full (13)` while reads kept working
// perfectly — which is the worst possible shape for this product.
//
// WHAT THAT COST, and why a log database is a product bug and not housekeeping.
// brain/worker.py's stuck-job ask sends the text and THEN writes the durable
// "already asked" record. The comment at worker.py:2199 already spells out what
// happens when that write fails: "the text has been sent and nothing knows it,
// so two seconds later this reads 'never asked' and asks again." With the disk
// full that write could never land, so every guard read "never asked" forever.
// The owner got the same question about one reminder, worded four different
// ways, from a system that believed it had never asked. He had to ask for it to
// be cancelled by hand, and the cancel ALSO failed, because cancelling is a
// write.
//
// It is a feedback loop, which is why it ran away: writes start failing, the
// worker retries in a tight loop, every retry is another logged request, the
// log database grows, and the disk gets fuller.
//
// start.sh already drops auxiliary.db on every boot and says why. That is a
// mitigation, not a fix — it only helps if somebody restarts the container, and
// between two boots this thing put away 3.96GB. Retention is the fix: with a
// ceiling in days, PocketBase prunes it itself and no operator has to notice.
//
// Two days, not one: an incident is usually diagnosed the morning after, and
// the request log is the only record of what the agent and the phone actually
// asked for. Two days keeps yesterday available and still bounds the file at
// roughly a fiftieth of what was measured above.
//
// minLevel is left alone deliberately. Dropping to WARN would shrink the file
// faster and would also throw away the successful-request trail that made this
// diagnosable at all — the du above is the only reason this file names the
// right culprit instead of blaming the backups, which were 8x smaller.
migrate((app) => {
  const settings = app.settings();
  settings.logs.maxDays = 2;
  app.save(settings);
  console.log("request-log retention capped: 2 days (auxiliary.db reached 3.96GB unbounded)");
}, (app) => {
  const settings = app.settings();
  settings.logs.maxDays = 0;
  app.save(settings);
});
