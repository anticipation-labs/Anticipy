/// <reference path="../pb_data/types.d.ts" />
//
// ANTICIPY HQ — the team's own desk.
//
// Five collections, every API rule null on purpose: these rows are reachable
// ONLY through the /internal/* hook routes in internal_hq.pb.js — never through
// /api/collections/, not even with the service token. The team dashboard is a
// separate room from the product, and the door between them stays shut.
//
// Seeds carry NAMES ONLY. Emails and phone numbers are typed in by each person
// from the People view — contact details for real humans do not belong in git.
migrate((app) => {
  const mk = (name, fields, indexes) => {
    try {
      app.findCollectionByNameOrId(name);
      return null; // already exists — migrations re-run on every boot
    } catch (_) {
      const c = new Collection({
        type: "base",
        name: name,
        fields: fields,
        indexes: indexes || [],
        listRule: null,
        viewRule: null,
        createRule: null,
        updateRule: null,
        deleteRule: null,
      });
      app.save(c);
      return app.findCollectionByNameOrId(name);
    }
  };

  mk("internal_people", [
    { name: "name", type: "text", required: true, max: 120, presentable: true },
    { name: "email", type: "text", max: 254 },
    { name: "phone", type: "text", max: 32 },
    { name: "is_admin", type: "bool" },
    { name: "active", type: "bool" },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ], ["CREATE INDEX idx_hq_people_name ON internal_people (name)"]);

  mk("internal_tracks", [
    { name: "name", type: "text", required: true, max: 120, presentable: true },
    { name: "kind", type: "text", max: 20 },       // company | fellowship
    { name: "members", type: "text", max: 2000 },  // JSON array of person ids
    { name: "active", type: "bool" },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ]);

  mk("internal_todos", [
    { name: "title", type: "text", required: true, max: 500, presentable: true },
    // 20K on purpose — the 5KB text default has broken this codebase twice.
    { name: "notes", type: "text", max: 20000 },
    { name: "track", type: "text", max: 40 },
    { name: "assignees", type: "text", max: 2000 },     // JSON array of person ids
    { name: "due", type: "text", max: 40 },             // ISO YYYY-MM-DD
    { name: "status", type: "text", max: 20 },          // open | done
    { name: "done_at", type: "text", max: 40 },
    { name: "done_by", type: "text", max: 40 },
    { name: "created_by", type: "text", max: 40 },
    { name: "remind_at", type: "text", max: 40 },       // UTC ISO datetime
    { name: "remind_channel", type: "text", max: 10 },  // email | sms | both | ""
    { name: "remind_sent_at", type: "text", max: 40 },  // the cron's idempotency claim
    { name: "followup_sent_at", type: "text", max: 40 },// one nudge, ever
    { name: "research_job_id", type: "text", max: 40 },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ], [
    "CREATE INDEX idx_hq_todos_track ON internal_todos (track, status)",
    "CREATE INDEX idx_hq_todos_remind ON internal_todos (status, remind_at)",
    "CREATE INDEX idx_hq_todos_due ON internal_todos (status, due)",
  ]);

  mk("internal_events", [
    { name: "title", type: "text", required: true, max: 300, presentable: true },
    { name: "date", type: "text", max: 40 },            // ISO date, optional THH:mm
    { name: "notes", type: "text", max: 5000 },
    { name: "countdown", type: "bool" },
    { name: "created_by", type: "text", max: 40 },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ], ["CREATE INDEX idx_hq_events_date ON internal_events (date)"]);

  mk("internal_activity", [
    { name: "actor", type: "text", max: 40 },
    // Denormalized so the feed still reads right after someone is deactivated.
    { name: "actor_name", type: "text", max: 120 },
    { name: "action", type: "text", max: 40 },
    { name: "subject", type: "text", max: 500 },
    { name: "ref", type: "text", max: 40 },
    { name: "created", type: "autodate", onCreate: true },
  ], ["CREATE INDEX idx_hq_activity_created ON internal_activity (created)"]);

  mk("internal_meter", [
    { name: "name", type: "text", required: true, max: 60 },
    { name: "hour", type: "text", max: 20 },  // YYYY-MM-DDTHH
    { name: "calls", type: "number", min: 0 },
    { name: "live_job_id", type: "text", max: 40 },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ], ["CREATE UNIQUE INDEX idx_hq_meter_name ON internal_meter (name)"]);

  // ---- seeds (idempotent: only when the table is empty) --------------------
  const seed = (col, rows, probeField, probeValue) => {
    try {
      app.findFirstRecordByFilter(col, probeField + " = {:v}", { v: probeValue });
      return; // seeded already
    } catch (_) { /* not found — seed */ }
    const c = app.findCollectionByNameOrId(col);
    for (const row of rows) {
      const r = new Record(c);
      for (const k in row) r.set(k, row[k]);
      app.save(r);
    }
  };

  seed("internal_people", [
    { name: "Omar", is_admin: true, active: true },
    { name: "Jose", is_admin: false, active: true },
    { name: "Arav", is_admin: false, active: true },
  ], "name", "Omar");

  seed("internal_tracks", [
    { name: "Company", kind: "company", members: "[]", active: true },
    { name: "Fellowship Growth", kind: "fellowship", members: "[]", active: true },
    { name: "Fellowship Software", kind: "fellowship", members: "[]", active: true },
  ], "name", "Company");

  seed("internal_meter", [
    { name: "llm", hour: "", calls: 0, live_job_id: "" },
    { name: "research", hour: "", calls: 0, live_job_id: "" },
  ], "name", "llm");
}, (app) => {
  try {
    for (const name of ["internal_meter", "internal_activity", "internal_events",
                        "internal_todos", "internal_tracks", "internal_people"]) {
      try { app.delete(app.findCollectionByNameOrId(name)); } catch (_) {}
    }
  } catch (_) {}
});
