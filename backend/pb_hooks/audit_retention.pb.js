/// <reference path="../pb_data/types.d.ts" />

// The audit ledger is CERTIFICATION EVIDENCE, and evidence is not customer
// data: it is regenerable by re-running a cohort. Left uncapped it grew to
// 3,639 records of full request/response JSON (up to 1MB each) and filled the
// 5GB production volume to 4996MB — at which point SQLite could not write ANY
// row. The visible symptom was cruel: a password-reset text went out (the send
// happens before the save) but the code could never be stored, so the correct
// code was rejected every time; new signups failed the same way. Found
// 2026-08-15 when the owner could not get into his own account.
//
// Two defences, because one was clearly not enough:
//   1. A retention sweep on every audit write — the ledger can never again
//      exceed KEEP records, so the disk cannot fill from this source.
//   2. POST /admin/purge-audit (service token only) for the emergency now,
//      draining in batches small enough to finish inside one request.
//
// Deleting rows does NOT shrink the file, and that is fine: the freed pages
// are reused by the next writes, which is exactly what "the disk is full"
// needs. VACUUM would need free space equal to the database size, which is
// the one thing a full disk does not have.

routerAdd("POST", "/admin/purge-audit", (e) => {
  // Declared INSIDE the handler: this runtime cannot see anything declared
  // outside the handler body. The header note above says exactly that, and
  // the first version of this file put them outside anyway — every call died
  // as a generic 400 with no clue, precisely as password_reset.pb.js warns.
  const AUDIT_KEEP = 300;
  const PURGE_BATCH = 200;
  const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  if (!token || e.request.header.get("X-Anticipy-Token") !== token) {
    return e.json(403, { error: "forbidden" });
  }

  let keep = AUDIT_KEEP;
  try {
    const body = e.requestInfo().body || {};
    if (body.keep !== undefined) keep = Math.max(0, parseInt(body.keep, 10) || 0);
  } catch (_) {}

  let deleted = 0;
  let remaining = -1;
  const trace = [];
  try {
    // Oldest first, skipping the newest `keep`. findRecordsByFilter's offset
    // is applied to the sort, so sorting -created and offsetting by keep
    // leaves exactly the surplus.
    trace.push("finding surplus");
    const surplus = e.app.findRecordsByFilter(
      "agent_llm_audit", "id != ''", "-created", PURGE_BATCH, keep);
    trace.push("found " + surplus.length);
    for (const rec of surplus) {
      try { e.app.delete(rec); deleted++; } catch (err) {
        // A delete that fails on a wedged disk must not abort the drain:
        // the next record may well succeed and every freed page helps.
        if (trace.length < 6) trace.push("delete failed: " + String(err));
      }
    }
    const left = e.app.findRecordsByFilter(
      "agent_llm_audit", "id != ''", "-created", 1, keep);
    remaining = left && left.length ? 1 : 0;   // 1 => more surplus to drain
  } catch (err) {
    return e.json(200, { ok: false, deleted: deleted, error: String(err), trace: trace });
  }

  return e.json(200, { ok: true, deleted: deleted, more: remaining === 1, keep: keep });
});

// The standing cap. Runs after an audit record is created, so the ledger
// trims itself continuously instead of growing until an outage.
onRecordAfterCreateSuccess((e) => {
  const AUDIT_KEEP = 300;   // same isolation rule as above
  try {
    const surplus = e.app.findRecordsByFilter(
      "agent_llm_audit", "id != ''", "-created", 25, AUDIT_KEEP);
    for (const rec of surplus) {
      try { e.app.delete(rec); } catch (_) {}
    }
  } catch (_) {
    // Never let housekeeping break the write that triggered it.
  }
  e.next();
}, "agent_llm_audit");
