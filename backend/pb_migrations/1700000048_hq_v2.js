/// <reference path="../pb_data/types.d.ts" />
//
// ANTICIPY HQ v2 — the data model the new dashboard needs, as a pure delta.
//
// Additive only. Six collections already hold live rows (internal_people,
// internal_todos, internal_tracks, internal_events, internal_activity,
// internal_meter) and not one existing column is renamed, retyped, widened or
// dropped here. Every add is guarded, every create is guarded, every backfill
// is idempotent, and down() removes only what up() added.
//
// ── THE ONE DECISION THAT PROTECTS EVERY OTHER ONE ────────────────────────
// `internal_todos.status` IS NOT WIDENED. It stays {open, done, cancelled}.
//
// The new board vocabulary (todo/doing/waiting/blocked) arrives as a SEPARATE
// column, `stage`. This is not a style preference. Three live queries key off
// the exact string 'open':
//
//   internal_hq.pb.js:1235  the sweep  "status = 'open' && remind_at != '' …"
//   internal_hq.pb.js:1286  follow-ups "status = 'open' && due != '' …"
//   internal_hq.pb.js:716   assistant  "status = 'open'"
//   internal_hq.pb.js:71    /state     "status = 'open' || (status = 'done' …)"
//
// Had `status` been widened to carry 'doing', the first person to drag a task
// out of the todo column would have had it vanish from the payload, vanish
// from the assistant's context, and STOP BEING REMINDED — with nothing red
// anywhere and no error in any log. In a file whose entire job is reminders,
// that is the worst failure available. With `stage`, no existing line changes.
// stage is meaningful only while status='open'.
//
// ── WHAT EACH FIELD IS ACTUALLY FOR ───────────────────────────────────────
// Named by the failure it prevents, not by restating the column name.
//
// internal_people
//   role, focus       Today's team card can say what someone is CARRYING, not
//                     just that they exist. Without them the admin view is a
//                     list of names, which answers no question anyone asks.
//   tz                Deliberately IANA ('America/Toronto'), never a friendly
//                     label. The reminder engine has to turn "9am" into a UTC
//                     instant; "Pacific (PT)" cannot be computed with, so a
//                     display string here means reminders fire at the wrong
//                     hour for everyone who is not in the server's zone.
//   remind_pref       The default channel a NEW reminder is armed on. Without
//                     it every reminder silently defaults to whatever the
//                     composer happened to send, which is how a person who
//                     only reads texts gets email forever.
//   email_on, sms_on  The per-person off switch. The digest pass must have a
//                     way to stop mailing someone that is not "delete their
//                     address" — because deleting the address also breaks the
//                     one-shot reminders they still want.
//   code_hash         sha256 of the login code. NEVER the code. internal.html
//                     is world-readable and the design mock literally printed
//                     "Prototype codes — Omar 123 · Ari 456 · Jose 789" on its
//                     own login screen; a plaintext column is the same leak
//                     one layer down.
//   code_set_at       Lets People say "code set 3d ago". A code with no age is
//                     a code nobody can reason about rotating.
//   last_in           The ONLY confirmation an admin gets that the person he
//                     handed a code to actually made it in. Without it,
//                     onboarding ends in silence and he re-sends the code.
//
// internal_tracks — these are the design's Projects. No new collection: a
//   parallel internal_projects would need a data migration on every live todo
//   (internal_todos.track already carries the id) to buy nothing.
//   desc              A project called "Hardware" tells a new person nothing.
//   owner             Answers "who do I ask about this" without a meeting.
//   archived          Distinct from `active` ON PURPOSE and both are kept:
//                     active=false hides a track from the New Task picker;
//                     archived=true greys the card and drops it from default
//                     lists. Collapsing them means archiving a finished
//                     project also makes its still-open tasks unfilable.
//   notes             The project's own scratch space, so per-project context
//                     stops being pasted into every task's description.
//
// internal_todos
//   stage             See above. The board column, orthogonal to status.
//   priority          Without it "what needs me first" is answered by due date
//                     alone, so anything undated is invisible and anything
//                     urgent-but-next-week sorts below trivia due today.
//   due_time          A deadline of "Friday" cannot be reminded on at the
//                     right hour, and cannot become a calendar entry that is
//                     anything but all-day.
//   repeat_rule       A weekly task recreated by hand is a task that stops
//                     being recreated the first busy week.
//   hold_reason       'blocked' with no reason is a status nobody can clear;
//                     the person who set it is the only one who knows why, and
//                     they are the person who is not there.
//   watchers          The person who ASKED for the work is not the assignee
//                     and is not the creator. Without this column they find
//                     out it shipped by asking.
//   subtasks          JSON [{t,done}] on the row, not a table: they are tiny,
//                     ordered, always read with the parent, and never edited
//                     concurrently on a three-person team.
//   attachments       JSON [{n,url,by,at}]. LINKS AND NAMES, NEVER UPLOADS —
//                     the Railway volume has already been filled once by the
//                     activity ledger, which is the reason internal_hq_prune
//                     exists at all.
//   cmt_count         Denormalized so drawing a list of 200 rows costs one
//                     query instead of 200. Maintained by the comment routes
//                     only; nothing else may write it.
//
// internal_comments — the one new thing that earns its own collection, because
//   comments have identity, edits, deletes, replies and drive mentions, and
//   because two people commenting at once must not clobber each other the way
//   a JSON blob read-modify-write does.
//   author_name       Denormalized for the same reason internal_activity does
//                     it: the thread must still read correctly after someone
//                     is deactivated.
//   parent            "" for top-level, a comment id for a reply.
//   deleted           A TOMBSTONE, not a DELETE. Hard-deleting a comment that
//                     has replies orphans them.
//
// internal_notifs     The design generated every notification client-side, so
//   nothing ever reached email or SMS — while the founder's first acceptance
//   line is "SMS updates from the twilio, resend updates of email systems".
//   emailed_at/smsed_at are the digest's CLAIM stamps, in the same
//   claim-first-then-send shape as remind_sent_at, for the same reason: send
//   first here means unbounded duplicate texts every five minutes forever.
//
// internal_reminders  todo.remind_at stays and keeps working — it is the
//   one-shot bell. This exists because "one hour before" and "daily until
//   done" cannot be expressed in a single column, and bolting a second
//   meaning onto remind_at would break the bell that already works.
//   fire_at is precomputed on write so the cron's due query stays a plain
//   indexed comparison and never has to do timezone maths per row.
//
// internal_sessions   Per-person identity. token_hash only — a stealable
//   plaintext session table is worse than the shared key it replaces. Doubles
//   as the sign-in history Settings shows, which is why it is a table and not
//   a column on the person.
//
// internal_config     Two or three rows, ever. Team name and the two
//   permission switches. A config ROW means changing them is a route call
//   instead of a redeploy.
//
// internal_activity
//   verb              The global feed keeps rendering `subject`. The Task
//                     panel's Activity tab renders actor_name + " " + verb.
//                     Without a verb column that tab has to string-parse
//                     `subject` back apart, which breaks the first time
//                     somebody's name contains a word the parser looks for.
//   idx (ref,created) `ref` ALREADY holds the todo id on every task event, so
//                     per-task activity is a filter — but without this index
//                     it is a filter over the whole ledger.
//
// ── WHAT THIS MIGRATION DELIBERATELY DOES NOT DO ──────────────────────────
//   * Does not backfill `tz`. Empty is the signal the onboarding checklist
//     reads to show "Confirm your timezone"; guessing a zone would silently
//     retire that line and quietly fire reminders in the wrong hour instead.
//   * Does not add `sched`. It exists only to serve drag-to-schedule on the
//     Calendar screen, which is cut from v1.
//   * Does not add a Google Calendar column. That integration is a 900ms
//     setTimeout in the mock; a column for it is a claim we cannot back.
//   * Does not touch any route, cron or page. Deploy this alone and the old
//     page keeps working unchanged — that is the point of shipping it first.
migrate((app) => {
  // ---- guarded adders ------------------------------------------------------
  // One proven constructor per type: TextField and NumberField are used by the
  // fellowship migrations, and `new Field({type:"bool"})` is the shape
  // 1700000029_event_intent.js used to add a bool to a live collection.
  const addText = (c, name, max) => {
    if (!c.fields.getByName(name)) c.fields.add(new TextField({ name: name, max: max }));
  };
  const addNum = (c, name) => {
    if (!c.fields.getByName(name)) c.fields.add(new NumberField({ name: name, min: 0 }));
  };
  const addBool = (c, name) => {
    if (!c.fields.getByName(name)) c.fields.add(new Field({ name: name, type: "bool" }));
  };
  // Filter-then-push, so re-running never stacks duplicate index definitions.
  // Every identifier is backticked: `key` and `desc` are SQLite keywords and an
  // unquoted one in a column list is a syntax error, not a warning.
  const putIndex = (c, marker, sql) => {
    c.indexes = (c.indexes || []).filter((i) => i.indexOf(marker) === -1);
    c.indexes.push(sql);
  };

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
        // All-null API rules, exactly like the existing six. These rows are
        // reachable ONLY through /internal/* hook routes — never through
        // /api/collections/, not even with the service token.
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

  // ========================================================================
  // 1.1 internal_people
  // ========================================================================
  const people = app.findCollectionByNameOrId("internal_people");
  addText(people, "role", 80);
  addText(people, "focus", 140);
  addText(people, "tz", 60);
  addText(people, "remind_pref", 20);   // inapp | email | sms | both
  addBool(people, "email_on");
  addBool(people, "sms_on");
  addText(people, "code_hash", 80);     // sha256 ONLY, never the code
  addText(people, "code_set_at", 40);
  addText(people, "last_in", 40);
  // The login route looks a person up BY the hash of the code they typed.
  // Unindexed, every sign-in is a full scan of the people table.
  putIndex(people, "idx_hq_people_code",
    "CREATE INDEX `idx_hq_people_code` ON `internal_people` (`code_hash`)");
  app.save(people);

  // ========================================================================
  // 1.2 internal_tracks — these are Projects
  // ========================================================================
  const tracks = app.findCollectionByNameOrId("internal_tracks");
  // NOTE: `desc` is a SQLite keyword. PocketBase always emits column names
  // quoted, so filters and sorts on it are safe — but never hand-write raw SQL
  // against this column without backticks.
  addText(tracks, "desc", 300);
  addText(tracks, "owner", 40);
  addBool(tracks, "archived");
  // 20000, not the 5KB text default. That default has broken this codebase
  // twice by silently truncating on save.
  addText(tracks, "notes", 20000);
  app.save(tracks);

  // ========================================================================
  // 1.3 internal_todos
  // ========================================================================
  const todos = app.findCollectionByNameOrId("internal_todos");
  addText(todos, "stage", 12);         // todo | doing | waiting | blocked
  addText(todos, "priority", 12);      // urgent | important | normal | later
  addText(todos, "due_time", 5);       // "HH:mm", local to the assignee
  addText(todos, "repeat_rule", 40);
  addText(todos, "hold_reason", 200);
  addText(todos, "watchers", 2000);    // JSON id array, same shape as assignees
  addText(todos, "subtasks", 4000);    // JSON [{t, done}]
  addText(todos, "attachments", 4000); // JSON [{n, url, by, at}] — links, not files
  addNum(todos, "cmt_count");
  // idx_hq_todos_due (status, due) already exists from 1700000038 and is not
  // redeclared here. This one serves the board's per-stage columns.
  putIndex(todos, "idx_hq_todos_stage",
    "CREATE INDEX `idx_hq_todos_stage` ON `internal_todos` (`status`, `stage`)");
  app.save(todos);

  // ========================================================================
  // 1.9 internal_activity
  // ========================================================================
  const activity = app.findCollectionByNameOrId("internal_activity");
  addText(activity, "verb", 120);
  putIndex(activity, "idx_hq_activity_ref",
    "CREATE INDEX `idx_hq_activity_ref` ON `internal_activity` (`ref`, `created`)");
  app.save(activity);

  // ========================================================================
  // 1.4 – 1.8 the new collections
  // ========================================================================
  mk("internal_comments", [
    { name: "todo", type: "text", required: true, max: 40 },
    { name: "author", type: "text", max: 40 },
    { name: "author_name", type: "text", max: 120 },
    { name: "text", type: "text", max: 4000, presentable: true },
    { name: "parent", type: "text", max: 40 },   // "" = top level, else a comment id
    { name: "edited_at", type: "text", max: 40 },// "" or ISO -> renders "· edited"
    { name: "deleted", type: "bool" },           // tombstone: a reply must not orphan
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ], ["CREATE INDEX `idx_hq_cmt_todo` ON `internal_comments` (`todo`, `created`)"]);

  mk("internal_notifs", [
    { name: "person", type: "text", required: true, max: 40 },
    // assign | mention | comment | deadline | done | file | overdue
    { name: "kind", type: "text", max: 20 },
    { name: "text", type: "text", max: 200, presentable: true },
    { name: "sub", type: "text", max: 300 },
    { name: "todo", type: "text", max: 40 },     // "" or the click target
    { name: "actor", type: "text", max: 40 },
    { name: "read", type: "bool" },
    // The digest's claim stamps. Written BEFORE the send, never after.
    { name: "emailed_at", type: "text", max: 40 },
    { name: "smsed_at", type: "text", max: 40 },
    { name: "created", type: "autodate", onCreate: true },
  ], ["CREATE INDEX `idx_hq_notif_person` ON `internal_notifs` (`person`, `read`, `created`)"]);

  mk("internal_reminders", [
    { name: "todo", type: "text", required: true, max: 40 },
    { name: "person", type: "text", max: 40 },   // "" = every recipient of the todo
    // at | one_hour_before | one_day_before | when_overdue | daily_until_done
    { name: "rule", type: "text", max: 24 },
    // UTC ISO, computed on write and recomputed whenever due/due_time changes.
    { name: "fire_at", type: "text", max: 40 },
    { name: "channel", type: "text", max: 20 },
    { name: "label", type: "text", max: 60, presentable: true },
    { name: "sent_at", type: "text", max: 40 },  // the cron's claim
    { name: "attempts", type: "number", min: 0 },// bounded retry, same as remind_attempts
    { name: "created_by", type: "text", max: 40 },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ], ["CREATE INDEX `idx_hq_rem_fire` ON `internal_reminders` (`sent_at`, `fire_at`)"]);

  mk("internal_sessions", [
    { name: "person", type: "text", required: true, max: 40 },
    { name: "token_hash", type: "text", required: true, max: 80 }, // sha256 only
    { name: "expires", type: "text", max: 40 },
    { name: "ip", type: "text", max: 60 },
    { name: "ua", type: "text", max: 200 },
    { name: "created", type: "autodate", onCreate: true },
  ], [
    // UNIQUE: one row per token. Two rows sharing a hash would make "sign out"
    // ambiguous and leave a live session behind after a code reset.
    "CREATE UNIQUE INDEX `idx_hq_sess_token` ON `internal_sessions` (`token_hash`)",
    "CREATE INDEX `idx_hq_sess_person` ON `internal_sessions` (`person`, `created`)",
  ]);

  mk("internal_config", [
    { name: "key", type: "text", required: true, max: 60, presentable: true },
    { name: "value", type: "text", max: 2000 },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ], ["CREATE UNIQUE INDEX `idx_hq_config_key` ON `internal_config` (`key`)"]);

  // ========================================================================
  // SEEDS — each guarded by its own probe, so a partial seed heals on reboot
  // ========================================================================
  const seedRow = (col, probeFilter, values) => {
    try { app.findFirstRecordByFilter(col, probeFilter); return 0; } catch (_) {}
    try {
      const r = new Record(app.findCollectionByNameOrId(col));
      for (const k in values) r.set(k, values[k]);
      app.save(r);
      return 1;
    } catch (_) { return 0; }
  };

  seedRow("internal_config", "key = 'team_name'",   { key: "team_name",   value: "Anticipy" });
  seedRow("internal_config", "key = 'perm_assign'", { key: "perm_assign", value: "everyone" });
  seedRow("internal_config", "key = 'perm_delete'", { key: "perm_delete", value: "creator" });

  // 1.10 — the login-attempt ceiling. A brute-force guard with no counter row
  // is a brute-force guard that fails open on the first attempt.
  seedRow("internal_meter", "name = 'login'",
    { name: "login", hour: "", calls: 0, live_job_id: "" });

  // The founder asked for a "brilliant idea tab" and also said it must not
  // feel cluttered. A project called Ideas is a place to put a thought and a
  // filter to browse it, for zero new surface. active=true so it appears in
  // the New Task picker; it is an ordinary track in every other respect.
  seedRow("internal_tracks", "name = 'Ideas'",
    { name: "Ideas", kind: "company", members: "[]", active: true,
      desc: "Half-formed things. No due dates, no owners.", archived: false });

  // ========================================================================
  // BACKFILLS
  // ========================================================================
  // Two kinds, and the difference decides whether each needs a run-once guard.
  //
  // (a) EMPTY-CHECKED backfills are idempotent by construction: '' is
  //     unambiguously "never set", so filling it can never overwrite a choice.
  //     These run every boot and are self-healing.
  //
  // (b) BOOLEAN backfills are NOT. A bool column added to a live table reads
  //     false on every existing row, and false is indistinguishable from "Ari
  //     turned this off on purpose". Re-running would silently switch his
  //     email back on. So the bool pass runs exactly once, gated on a marker
  //     row, and never touches those columns again.

  // ---- (a) stage + priority: every live todo, empty-checked ---------------
  // A row with an empty stage renders in no board column and sorts nowhere.
  let staged = 0;
  for (let pass = 0; pass < 40; pass++) {   // hard cap: 40 x 500 = 20k rows
    let batch = [];
    try {
      batch = app.findRecordsByFilter("internal_todos",
        "stage = '' || priority = ''", "+created", 500, 0);
    } catch (_) { batch = []; }
    if (!batch.length) break;
    let touched = 0;
    for (const t of batch) {
      try {
        let dirty = false;
        if (!t.getString("stage"))    { t.set("stage", "todo");      dirty = true; }
        if (!t.getString("priority")) { t.set("priority", "normal"); dirty = true; }
        if (dirty) { app.save(t); staged++; touched++; }
      } catch (_) {}
    }
    // Nothing in the batch could be fixed — stop rather than spin on it.
    if (!touched) break;
  }

  // ---- (a) remind_pref: empty-checked ------------------------------------
  // Empty means the digest has no default channel to fall back on, which reads
  // as "in-app only" and quietly removes people who only ever read texts.
  // 'both' preserves the reach these people have TODAY; a later choice sticks
  // because it is no longer empty.
  let prefed = 0;
  try {
    const noPref = app.findRecordsByFilter("internal_people", "remind_pref = ''", "+name", 200, 0);
    for (const p of noPref) {
      try { p.set("remind_pref", "both"); app.save(p); prefed++; } catch (_) {}
    }
  } catch (_) {}

  // ---- (b) email_on + sms_on: run once, ever -----------------------------
  let channelled = 0;
  let firstRun = false;
  try { app.findFirstRecordByFilter("internal_config", "key = 'hq_v2_backfill'"); }
  catch (_) { firstRun = true; }

  if (firstRun) {
    try {
      const all = app.findRecordsByFilter("internal_people", "id != ''", "+name", 500, 0);
      for (const p of all) {
        try { p.set("email_on", true); p.set("sms_on", true); app.save(p); channelled++; }
        catch (_) {}
      }
    } catch (_) {}

    // The marker is written LAST and unconditionally, so a crash halfway
    // through leaves it absent and the whole pass retries on the next boot.
    seedRow("internal_config", "key = 'hq_v2_backfill'",
      { key: "hq_v2_backfill", value: new Date().toISOString() });

    try {
      const act = new Record(app.findCollectionByNameOrId("internal_activity"));
      act.set("actor", ""); act.set("actor_name", "HQ");
      act.set("action", "hq.v2_migration");
      act.set("verb", "installed the v2 data model");
      act.set("subject", "HQ v2 data model installed: sessions, login codes, comments, "
        + "notifications and reminders. " + staged + " task(s) given a stage, "
        + channelled + " person/people kept on email and SMS. status was not widened.");
      app.save(act);
    } catch (_) {}
  }

  console.log("hq v2: " + staged + " todos staged, " + prefed + " remind_pref set, "
    + channelled + " people channelled, first_run=" + firstRun);
}, (app) => {
  // ---- down(): removes ONLY what up() added -------------------------------
  // Field drops take their data with them, so the stage/priority/channel
  // backfills need no separate undo.
  //
  // Two things are deliberately NOT undone:
  //   * The seeded Ideas track stays. By the time anyone rolls back it may
  //     hold real tasks, and deleting it would leave internal_todos.track
  //     pointing at nothing — orphaning work to tidy up a seed row.
  //   * remind_pref is left as written. Blanking it would hand the digest an
  //     empty default again, which is the failure it was set to prevent.
  const dropFields = (name, fieldNames, indexMarkers) => {
    try {
      const c = app.findCollectionByNameOrId(name);
      for (const marker of (indexMarkers || [])) {
        c.indexes = (c.indexes || []).filter((i) => i.indexOf(marker) === -1);
      }
      for (const f of fieldNames) {
        const found = c.fields.getByName(f);
        if (found) c.fields.removeById(found.id);
      }
      app.save(c);
    } catch (_) {}
  };

  dropFields("internal_people",
    ["role", "focus", "tz", "remind_pref", "email_on", "sms_on",
     "code_hash", "code_set_at", "last_in"],
    ["idx_hq_people_code"]);

  dropFields("internal_tracks", ["desc", "owner", "archived", "notes"], []);

  dropFields("internal_todos",
    ["stage", "priority", "due_time", "repeat_rule", "hold_reason",
     "watchers", "subtasks", "attachments", "cmt_count"],
    ["idx_hq_todos_stage"]);

  dropFields("internal_activity", ["verb"], ["idx_hq_activity_ref"]);

  // Dropping internal_config also drops the hq_v2_backfill marker, so a later
  // up() correctly re-runs the bool pass against the re-added columns.
  for (const name of ["internal_comments", "internal_notifs", "internal_reminders",
                      "internal_sessions", "internal_config"]) {
    try { app.delete(app.findCollectionByNameOrId(name)); } catch (_) {}
  }

  // The login meter row is a counter this migration introduced; the other
  // meter rows predate it and are left alone.
  try {
    app.delete(app.findFirstRecordByFilter("internal_meter", "name = 'login'"));
  } catch (_) {}
});
