/// <reference path="../pb_data/types.d.ts" />
//
// ANTICIPY HQ — every /internal/* route and both crons for the team dashboard.
//
// THE ONE RULE OF THIS FILE: every handler redeclares EVERYTHING it uses inside
// its own body — the auth check, the helpers, the base64 encoder, all of it.
// PocketBase JSVM handlers run in isolated contexts and cannot see anything
// declared outside themselves; that trap has bitten this codebase at least
// three times. Cron handlers additionally have no `e` — they use the global
// $app. Nothing lives at file top level except these comments.
//
// Auth: header X-Internal-Key vs env ANTICIPY_INTERNAL_KEY, timing-safe, and
// FAIL-CLOSED — if the env var is missing the routes answer 503, they do not
// open. That is the deliberate inversion of guard.pb.js's fail-open: a fresh
// deploy that forgot one variable must not publish the team's phone numbers.

// --------------------------------------------------------------------------
// GET /internal/health — liveness + "is the lock installed", leaks nothing.
// --------------------------------------------------------------------------
routerAdd("GET", "/internal/health", (e) => {
  const gated = !!($os.getenv("ANTICIPY_INTERNAL_KEY") || "");
  // channels are DERIVED FROM ENV PRESENCE, never from a literal.
  //
  // The Settings screen used to draw two rows reading "Email delivery —
  // Connected" and "SMS delivery — Connected" from hardcoded strings in the
  // client. That is the same failure shape that made gate leg 7 green three
  // times: a surface reporting the claim instead of asking it. So the page
  // gets booleans it cannot fake, and the only thing they assert is the one
  // thing this process can actually know — whether the credential is present.
  // Never the values. A boolean cannot leak a key.
  const channels = {
    email: !!($os.getenv("RESEND_API_KEY") || ""),
    sms: !!(($os.getenv("TWILIO_ACCOUNT_SID") || "") && ($os.getenv("TWILIO_AUTH_TOKEN") || "")
      && (($os.getenv("TWILIO_PHONE_NUMBER") || "") || ($os.getenv("TWILIO_FROM") || ""))),
  };
  return e.json(200, { ok: true, gated: gated, version: "hq-2", channels: channels });
});

// --------------------------------------------------------------------------
// POST /internal/login — lets the gate screen validate before storing.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/login", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const sent = String(body.key || "");
  if (!$security.equal(sent, key)) return e.json(401, { error: "wrong key" });
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// GET /internal/state — everything the page needs, one round trip.
// --------------------------------------------------------------------------
routerAdd("GET", "/internal/state", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });

  // ---- DUAL AUTH, and the reason it is not "key only, plus a session hint" --
  //
  // The spec said keep this route keyed and merely resolve a session for
  // scoping. That cannot be right: the whole point of the onboarding is that
  // Ari is handed an eight-character code and NOTHING else — he never holds
  // the shared key, so a key-only /internal/state means his first screen is a
  // 401. So the session is a first-class credential HERE, and the key path
  // below is byte-for-byte what it was, so nothing that works today stops.
  //
  // A session that fails to resolve answers 401 {reauth:true} and NEVER falls
  // through to the key branch. A silent downgrade from "this is Ari" to
  // "whoever holds the key says they are Ari" is the attack: an expired token
  // must log you out, not quietly demote you to client-asserted identity.
  const sha256 = (s) => $security.sha256(s);
  let actor = null, viaSession = false;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";   // the ZZ/NaN trap
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) { actor = p; viaSession = true; }
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    // Shared-key mode keeps client-asserted identity, visibly. actor_id is a
    // query param here because a GET has no body; it is optional, exactly as
    // it was, and its only effect is scoping the caller's own notifications.
    try {
      const who = e.request.url.query().get("actor_id") || "";
      if (who) actor = e.app.findRecordById("internal_people", who);
    } catch (_) { actor = null; }
  }

  const out = { people: [], tracks: [], todos: [], events: [], activity: [],
    comments: [], notifs: [], reminders: [], signins: [], expenses: [], passwords: [], notes: [], config: {}, channels: {},
    me: actor ? actor.get("id") : "", via_session: viaSession, meters: {} };

  try {
    const people = e.app.findRecordsByFilter("internal_people", "id != ''", "+name", 200, 0);
    for (const p of people) {
      // EXPLICIT PROJECTION, and `has_code` is the whole reason it stays
      // explicit: code_hash lives on this record and a `return p` here would
      // hand every offline cracker the hash of every login code in the
      // building. The page needs to know whether a code EXISTS, never what it
      // is and never what it hashes to.
      out.people.push({ id: p.get("id"), name: p.getString("name"),
        email: p.getString("email"), phone: p.getString("phone"),
        is_admin: !!p.get("is_admin"), active: !!p.get("active"),
        role: p.getString("role"), focus: p.getString("focus"),
        tz: p.getString("tz"), remind_pref: p.getString("remind_pref"),
        email_on: p.get("email_on") !== false, sms_on: p.get("sms_on") !== false,
        last_in: p.getString("last_in"), code_set_at: p.getString("code_set_at"),
        has_code: !!p.getString("code_hash") });
    }
  } catch (_) {}

  try {
    const tracks = e.app.findRecordsByFilter("internal_tracks", "id != ''", "+created", 50, 0);
    for (const t of tracks) {
      out.tracks.push({ id: t.get("id"), name: t.getString("name"),
        kind: t.getString("kind"), members: t.getString("members") || "[]",
        active: !!t.get("active"),
        // internal_tracks IS the design's Projects. Renamed in the UI only:
        // internal_todos.track already carries the id on every live row, so a
        // separate internal_projects would have meant a data migration on the
        // whole board to buy exactly nothing.
        desc: t.getString("desc"), owner: t.getString("owner"),
        archived: !!t.get("archived"), notes: t.getString("notes") });
    }
  } catch (_) {}

  const todoIds = {};
  try {
    const cut = new Date(Date.now() - 14 * 24 * 3600 * 1000).toISOString();
    // One line moved, and only one: `done_at >= cut` instead of
    // `status = 'done' && done_at >= cut`, so a CANCELLED row is visible for
    // its fourteen days too instead of vanishing the instant someone drops it.
    //
    // THE COLUMN THAT IS NOT HERE: there is no `status = 'doing'`. The design's
    // board vocabulary lives in a separate `stage` column precisely so this
    // filter, the cron's reminder filter and the assistant's board dump — all
    // three of which key off status = 'open' — do not have to change. Widening
    // status to {todo,doing,waiting,blocked,...} would have made a task moved to
    // "In progress" silently stop being reminded about, with nothing red
    // anywhere. That is the single worst failure available in this file.
    const todos = e.app.findRecordsByFilter("internal_todos",
      "status = 'open' || done_at >= {:cut}",
      "-created", 500, 0, { cut: cut });
    for (const t of todos) {
      todoIds[t.get("id")] = true;
      out.todos.push({ id: t.get("id"), title: t.getString("title"),
        notes: t.getString("notes"), track: t.getString("track"),
        assignees: t.getString("assignees") || "[]", due: t.getString("due"),
        status: t.getString("status"), done_at: t.getString("done_at"),
        done_by: t.getString("done_by"), created_by: t.getString("created_by"),
        remind_at: t.getString("remind_at"), remind_channel: t.getString("remind_channel"),
        remind_sent_at: t.getString("remind_sent_at"),
        research_job_id: t.getString("research_job_id"),
        stage: t.getString("stage") || "todo",
        priority: t.getString("priority") || "normal",
        position: Number(t.get("position")) || 0,
        due_time: t.getString("due_time"), repeat_rule: t.getString("repeat_rule"),
        hold_reason: t.getString("hold_reason"),
        watchers: t.getString("watchers") || "[]",
        subtasks: t.getString("subtasks") || "[]",
        attachments: t.getString("attachments") || "[]",
        cmt_count: Number(t.get("cmt_count")) || 0,
        created: t.getString("created"), updated: t.getString("updated") });
    }
  } catch (_) {}

  try {
    const cut = new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 10);
    const events = e.app.findRecordsByFilter("internal_events",
      "date >= {:cut}", "+date", 200, 0, { cut: cut });
    for (const ev of events) {
      out.events.push({ id: ev.get("id"), title: ev.getString("title"),
        date: ev.getString("date"), notes: ev.getString("notes"),
        countdown: !!ev.get("countdown"), created_by: ev.getString("created_by") });
    }
  } catch (_) {}

  try {
    const acts = e.app.findRecordsByFilter("internal_activity", "id != ''", "-created", 50, 0);
    for (const a of acts) {
      // `ref` already carried the todo id on every task event, so the Task
      // panel's Activity tab is a filter over this array, not a new table.
      // `verb` is new and exists so that tab can render actor_name + verb
      // instead of string-parsing `subject` back apart, which is what it would
      // otherwise have had to do.
      out.activity.push({ actor_name: a.getString("actor_name"),
        action: a.getString("action"), subject: a.getString("subject"),
        verb: a.getString("verb"), ref: a.getString("ref"),
        created: a.getString("created") });
    }
  } catch (_) {}

  // ---- comments, but only for todos already in this payload ----------------
  // Scoped to todoIds so this cannot become a keyed window onto the comment
  // history of tasks the caller was never shown.
  try {
    const cmts = e.app.findRecordsByFilter("internal_comments", "id != ''", "-created", 400, 0);
    for (const c of cmts) {
      if (!todoIds[c.getString("todo")]) continue;
      out.comments.push({ id: c.get("id"), todo: c.getString("todo"),
        author: c.getString("author"), author_name: c.getString("author_name"),
        // A tombstoned comment carries no text. Blanking it on the way out as
        // well as on delete means a stale row can never resurrect a deleted
        // sentence into somebody's browser.
        text: c.get("deleted") ? "" : c.getString("text"),
        parent: c.getString("parent"), edited_at: c.getString("edited_at"),
        deleted: !!c.get("deleted"), created: c.getString("created") });
    }
  } catch (_) {}

  // ---- this person's notifications, and nobody else's ----------------------
  if (actor) {
    try {
      const ns = e.app.findRecordsByFilter("internal_notifs",
        "person = {:p}", "-created", 100, 0, { p: actor.get("id") });
      for (const n of ns) {
        out.notifs.push({ id: n.get("id"), kind: n.getString("kind"),
          text: n.getString("text"), sub: n.getString("sub"),
          todo: n.getString("todo"), actor: n.getString("actor"),
          read: !!n.get("read"), created: n.getString("created") });
      }
    } catch (_) {}
  }

  // ---- armed reminders on the todos above ---------------------------------
  try {
    const rems = e.app.findRecordsByFilter("internal_reminders",
      "sent_at = ''", "+fire_at", 300, 0);
    for (const r of rems) {
      if (!todoIds[r.getString("todo")]) continue;
      out.reminders.push({ id: r.get("id"), todo: r.getString("todo"),
        person: r.getString("person"), rule: r.getString("rule"),
        fire_at: r.getString("fire_at"), channel: r.getString("channel"),
        label: r.getString("label"), sent_at: r.getString("sent_at") });
    }
  } catch (_) {}

  // ---- team config --------------------------------------------------------
  try {
    const exps = e.app.findRecordsByFilter("internal_expenses", "id != ''", "-date", 500, 0);
    for (const x of exps) {
      out.expenses.push({ id: x.get("id"), title: x.getString("title"),
        amount: Number(x.get("amount")) || 0, currency: x.getString("currency") || "CAD",
        date: x.getString("date"), track: x.getString("track"),
        person: x.getString("person"), created_by: x.getString("created_by") });
    }
  } catch (_) {}
  try {
    const pws = e.app.findRecordsByFilter("internal_passwords", "id != ''", "+service", 200, 0);
    for (const w of pws) {
      // Metadata only. secret_enc never rides in state — not even encrypted,
      // because nothing on the page needs it and habits start somewhere.
      out.passwords.push({ id: w.get("id"), service: w.getString("service"),
        username: w.getString("username"), url: w.getString("url"),
        notes: w.getString("notes"), updated: w.getString("updated"),
        updated_by: w.getString("updated_by") });
    }
  } catch (_) {}

  try {
    const nts = e.app.findRecordsByFilter("internal_notes", "id != ''", "-updated", 300, 0);
    for (const n of nts) {
      out.notes.push({ id: n.get("id"), title: n.getString("title"),
        body: n.getString("body"), track: n.getString("track"),
        created_by: n.getString("created_by"), updated_by: n.getString("updated_by"),
        updated: n.getString("updated") });
    }
  } catch (_) {}

  out.config = { team_name: "Anticipy", perm_assign: "everyone", perm_delete: "creator" };
  try {
    const cfgs = e.app.findRecordsByFilter("internal_config", "id != ''", "+key", 20, 0);
    for (const c of cfgs) {
      const k = c.getString("key");
      if (k === "team_name" || k === "perm_assign" || k === "perm_delete") {
        out.config[k] = c.getString("value");
      }
    }
  } catch (_) {}

  // ---- "Who's been in lately" — admins only -------------------------------
  // Sign-in history is a list of when each teammate was at their desk. That is
  // an admin's answer to "did the code land", not a thing every member gets to
  // read about every other member.
  if (actor && actor.get("is_admin")) {
    try {
      const ss = e.app.findRecordsByFilter("internal_sessions", "id != ''", "-created", 10, 0);
      for (const s of ss) {
        // token_hash and ip are NOT projected. The screen prints a name and a
        // when; it has never needed either, and a hash on the wire is a hash
        // somebody can grind offline.
        out.signins.push({ person: s.getString("person"), created: s.getString("created") });
      }
    } catch (_) {}
  }

  // ---- delivery channels: env presence, booleans, never the values ---------
  out.channels = {
    email: !!($os.getenv("RESEND_API_KEY") || ""),
    sms: !!(($os.getenv("TWILIO_ACCOUNT_SID") || "") && ($os.getenv("TWILIO_AUTH_TOKEN") || "")
      && (($os.getenv("TWILIO_PHONE_NUMBER") || "") || ($os.getenv("TWILIO_FROM") || ""))),
  };

  try {
    const llm = e.app.findFirstRecordByFilter("internal_meter", "name = 'llm'");
    const hourNow = new Date().toISOString().slice(0, 13);
    out.meters.llm_used = llm.getString("hour") === hourNow ? (Number(llm.get("calls")) || 0) : 0;
    out.meters.llm_ceiling = parseInt($os.getenv("ANTICIPY_INTERNAL_LLM_CEILING") || "60", 10);
  } catch (_) {}
  try {
    const res = e.app.findFirstRecordByFilter("internal_meter", "name = 'research'");
    out.meters.research_job_id = res.getString("live_job_id") || "";
  } catch (_) {}

  return e.json(200, out);
});

// --------------------------------------------------------------------------
// POST /internal/people — self-serve join. Anyone with the key adds themselves.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/people", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const name = String(body.name || "").trim();
  const email = String(body.email || "").trim();
  const phone = String(body.phone || "").trim().replace(/[\s()-]/g, "");
  if (!name || name.length > 120) return e.json(400, { error: "a name between 1 and 120 characters, please" });
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return e.json(400, { error: "that email doesn't look right" });
  if (phone && !/^\+?\d{8,15}$/.test(phone)) return e.json(400, { error: "phone should be digits with an optional +, like +16045550142" });
  try {
    const dupes = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 200, 0);
    for (const d of dupes) {
      if (d.getString("name").toLowerCase() === name.toLowerCase()) {
        return e.json(400, { error: name + " is already on the team — pick yourself from the list instead" });
      }
    }
  } catch (_) {}
  // ---- the added fields, all optional, all defaulted ----------------------
  const role = String(body.role || "").trim().slice(0, 80);
  const focus = String(body.focus || "").trim().slice(0, 140);
  // IANA id, not "Pacific (PT)". The reminder engine turns "9am" into UTC with
  // this string; a friendly label is a thing the page renders, not a thing the
  // server can compute an hour from.
  const tz = String(body.tz || "").trim().slice(0, 60);
  const pref = String(body.remind_pref || "").trim();
  if (pref && ["inapp", "email", "sms", "both"].indexOf(pref) < 0) {
    return e.json(400, { error: "reminders are in-app, email, sms or both" });
  }

  // ---- minting a login code is an ADMIN act, and only an admin act --------
  // Self-serve join stays exactly as it was when mint_code is absent: anyone
  // holding the shared key can still add themselves. But a code is a
  // credential, so the branch that mints one demands a named admin. Without
  // this, anyone with the key could mint a code for a NEW admin account and
  // convert "holds the shared key" into "is a person with a durable session"
  // — a privilege upgrade the shared key was never meant to grant.
  const wantsCode = !!body.mint_code;
  let minter = null;
  if (wantsCode) {
    try { minter = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!minter.get("active")) return e.json(400, { error: "that person is deactivated" });
    if (!minter.get("is_admin")) return e.json(403, { error: "only an admin can hand out login codes" });
  }
  if (("is_admin" in body) && !!body.is_admin && !(minter && minter.get("is_admin"))) {
    return e.json(403, { error: "only an admin can make someone an administrator" });
  }

  const col = e.app.findCollectionByNameOrId("internal_people");
  const r = new Record(col);
  r.set("name", name); r.set("email", email); r.set("phone", phone);
  r.set("role", role); r.set("focus", focus); r.set("tz", tz);
  r.set("remind_pref", pref || "inapp");
  r.set("email_on", body.email_on !== false);
  r.set("sms_on", body.sms_on !== false);
  r.set("is_admin", !!(minter && minter.get("is_admin") && body.is_admin));
  r.set("active", true);
  r.set("code_hash", ""); r.set("code_set_at", ""); r.set("last_in", "");

  let plain = "";
  if (wantsCode) {
    // CROCKFORD BASE32, EIGHT CHARACTERS, HASHED — never three digits.
    //
    // The design prototyped this as a 3-digit code compared with === and
    // printed the codes on its own login screen. Three things are wrong with
    // that and each is fixed here on purpose:
    //
    //  - 3 digits is 1000 possibilities. Eight Crockford characters is
    //    32^8 ~= 1.1e12, which against the 40-attempts-an-hour ceiling in
    //    POST /internal/session is not a brute force, it is a geological era.
    //  - The alphabet excludes I, L, O and U, so there is no such thing as
    //    reading a code aloud and landing on the wrong character. That is not
    //    cosmetic: every login failure returns the SAME sentence, so a
    //    transcription slip would be indistinguishable from a revoked code and
    //    the person would have no way to tell which happened.
    //  - Only sha256 is stored. internal.html is world-readable and this
    //    database gets backed up nightly; a dump must not be a pile of live
    //    credentials, and there is deliberately NO route anywhere in this file
    //    that can read a code back out. It is returned here, once, and then it
    //    exists only in the admin's clipboard.
    plain = $security.randomStringWithAlphabet(8, "0123456789ABCDEFGHJKMNPQRSTVWXYZ");
    r.set("code_hash", $security.sha256(plain));
    r.set("code_set_at", new Date().toISOString());
  }
  e.app.save(r);
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", minter ? minter.get("id") : r.get("id"));
    act.set("actor_name", minter ? minter.getString("name") : name);
    act.set("action", "person.join");
    act.set("subject", minter ? (minter.getString("name") + " added " + name + " to the team")
      : (name + " joined the team"));
    act.set("verb", minter ? "added " + name + " to the team" : "joined the team");
    act.set("ref", r.get("id"));
    e.app.save(act);
  } catch (_) {}
  const res = { id: r.get("id"), name: name, email: email, phone: phone,
    role: role, focus: focus, tz: tz, remind_pref: pref || "inapp",
    is_admin: !!r.get("is_admin"), active: true };
  // The plaintext leaves the building exactly here, exactly once. It is not
  // logged, not written to activity, and not in /internal/state.
  if (plain) res.code = plain.slice(0, 4) + "-" + plain.slice(4);
  return e.json(200, res);
});

// --------------------------------------------------------------------------
// PATCH /internal/people — self-edit contacts; admin-only role/active changes.
// --------------------------------------------------------------------------
routerAdd("PATCH", "/internal/people", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor, target;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "who is making this change? actor_id missing" }); }
  if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  try { target = e.app.findRecordById("internal_people", String(body.person_id || "")); }
  catch (_) { return e.json(404, { error: "no such person" }); }

  const isSelf = actor.get("id") === target.get("id");
  const isAdmin = !!actor.get("is_admin");
  const wantsRoleChange = ("is_admin" in body) || ("active" in body);
  if (wantsRoleChange && !isAdmin) return e.json(403, { error: "only an admin can change roles" });
  if (!isSelf && !isAdmin) return e.json(403, { error: "you can only edit your own details" });

  if ("email" in body) {
    const email = String(body.email || "").trim();
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return e.json(400, { error: "that email doesn't look right" });
    target.set("email", email);
  }
  if ("phone" in body) {
    const phone = String(body.phone || "").trim().replace(/[\s()-]/g, "");
    if (phone && !/^\+?\d{8,15}$/.test(phone)) return e.json(400, { error: "phone should be digits with an optional +" });
    target.set("phone", phone);
  }
  // Personal settings. These ride the existing self-or-admin rule above:
  // `role` and `focus` are what the Team card shows about you, `tz` is what
  // turns "9am" into a real hour, and the three preference fields decide
  // whether anything can reach you at all.
  if ("role" in body) target.set("role", String(body.role || "").trim().slice(0, 80));
  if ("focus" in body) target.set("focus", String(body.focus || "").trim().slice(0, 140));
  if ("tz" in body) target.set("tz", String(body.tz || "").trim().slice(0, 60));
  if ("remind_pref" in body) {
    const pref = String(body.remind_pref || "").trim();
    if (["inapp", "email", "sms", "both"].indexOf(pref) < 0) {
      return e.json(400, { error: "reminders are in-app, email, sms or both" });
    }
    target.set("remind_pref", pref);
  }
  if ("email_on" in body) target.set("email_on", !!body.email_on);
  if ("sms_on" in body) target.set("sms_on", !!body.sms_on);
  // code_hash is deliberately NOT patchable here. Rotating a credential has to
  // sign the old sessions out, and that only happens in one place:
  // POST /internal/people/code. A second door onto this field would be a
  // second door that forgets to close them.
  if ("is_admin" in body) target.set("is_admin", !!body.is_admin);
  if ("active" in body) {
    // Never let the last admin lock everyone out.
    if (!body.active && target.get("is_admin")) {
      let admins = 0;
      try {
        const all = e.app.findRecordsByFilter("internal_people", "active = true && is_admin = true", "+name", 50, 0);
        admins = all.length;
      } catch (_) {}
      if (admins <= 1) return e.json(400, { error: "that's the last admin — promote someone else first" });
    }
    target.set("active", !!body.active);
    // DEACTIVATING SOMEONE SIGNS THEM OUT NOW, not when their token expires.
    // The dual-auth block re-checks `active` on every request, so a live
    // session would already be refused — but leaving the rows behind means a
    // reactivation silently restores a thirty-day-old token somebody may have
    // pasted somewhere. Deleting them makes reinstatement a fresh sign-in.
    if (!body.active) {
      try {
        const live = e.app.findRecordsByFilter("internal_sessions",
          "person = {:p}", "-created", 200, 0, { p: target.get("id") });
        for (const s of live) { try { e.app.delete(s); } catch (_) {} }
      } catch (_) {}
    }
  }
  e.app.save(target);
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "person.update");
    act.set("subject", actor.getString("name") + " updated " + target.getString("name"));
    act.set("ref", target.get("id"));
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/todos — create, flag to people, arm a reminder.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/todos", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "who is creating this? pick yourself first" }); }

  const title = String(body.title || "").trim();
  if (!title || title.length > 500) return e.json(400, { error: "a title between 1 and 500 characters, please" });

  let track;
  try { track = e.app.findRecordById("internal_tracks", String(body.track || "")); }
  catch (_) { return e.json(400, { error: "that board doesn't exist" }); }
  if (!track.get("active")) return e.json(400, { error: "that board is archived" });

  let assignees = [];
  if (Array.isArray(body.assignees)) {
    for (const id of body.assignees) {
      try {
        const p = e.app.findRecordById("internal_people", String(id));
        assignees.push(p.get("id"));
      } catch (_) { return e.json(400, { error: "one of the flagged people doesn't exist" }); }
    }
  }

  const due = String(body.due || "").trim();
  if (due && !/^\d{4}-\d{2}-\d{2}$/.test(due)) return e.json(400, { error: "due date should be YYYY-MM-DD" });

  // ---- the design's board vocabulary, kept OFF `status` --------------------
  const stage = String(body.stage || "todo").trim() || "todo";
  if (["todo", "doing", "waiting", "blocked"].indexOf(stage) < 0) return e.json(400, { error: "pick a stage" });
  const priority = String(body.priority || "normal").trim() || "normal";
  if (["urgent", "important", "normal", "later"].indexOf(priority) < 0) return e.json(400, { error: "priority is urgent, important, normal or later" });
  const dueTime = String(body.due_time || "").trim();
  if (dueTime && !/^\d{2}:\d{2}$/.test(dueTime)) return e.json(400, { error: "a time looks like 14:30" });
  const repeatRule = String(body.repeat_rule || "").trim();
  if (repeatRule && !/^(none|daily|weekdays|weekly|monthly|every:[2-9]|every:[12]\d|weekly:(mon|tue|wed|thu|fri|sat|sun))$/.test(repeatRule)) {
    return e.json(400, { error: "that repeat isn't one I know" });
  }
  const holdReason = String(body.hold_reason || "").trim().slice(0, 200);

  const watchers = [];
  if (Array.isArray(body.watchers)) {
    for (const id of body.watchers) {
      try { watchers.push(e.app.findRecordById("internal_people", String(id)).get("id")); }
      catch (_) { return e.json(400, { error: "one of the watchers doesn't exist" }); }
    }
  }
  // Subtasks are a JSON column, not a collection, on purpose: they are tiny,
  // ordered, always read with the parent, and nobody on a three-person team
  // edits two of them at once. Comments got their own collection precisely
  // because none of that is true of comments.
  let subtasks = [];
  if (Array.isArray(body.subtasks)) {
    if (body.subtasks.length > 40) return e.json(400, { error: "forty subtasks is plenty — the rest are their own task" });
    for (const s of body.subtasks) {
      const t = String((s && s.t) || "").trim().slice(0, 200);
      if (!t) continue;
      subtasks.push({ t: t, done: !!(s && s.done) });
    }
  }

  const remindAt = String(body.remind_at || "").trim();
  const remindChannel = String(body.remind_channel || "").trim();
  if (remindAt) {
    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(remindAt)) return e.json(400, { error: "reminder time looks malformed" });
    if (["email", "sms", "both"].indexOf(remindChannel) < 0) return e.json(400, { error: "pick a reminder channel: email, sms or both" });
    // The reminder must be able to REACH someone, or it is a lie on a card.
    const recipients = [];
    const ids = assignees.length ? assignees : [actor.get("id")];
    for (const id of ids) {
      try { recipients.push(e.app.findRecordById("internal_people", id)); } catch (_) {}
    }
    const needEmail = remindChannel === "email" || remindChannel === "both";
    const needPhone = remindChannel === "sms" || remindChannel === "both";
    let reachable = false;
    const missing = [];
    for (const p of recipients) {
      const okE = !needEmail || !!p.getString("email");
      const okP = !needPhone || !!p.getString("phone");
      if (okE || okP) reachable = true;
      if (needEmail && !p.getString("email")) missing.push(p.getString("name") + " has no email on file");
      if (needPhone && !p.getString("phone")) missing.push(p.getString("name") + " has no phone number on file");
    }
    if (!reachable) return e.json(400, { error: missing.join("; ") || "nobody flagged has contact details yet" });
  }

  const col = e.app.findCollectionByNameOrId("internal_todos");
  const r = new Record(col);
  r.set("title", title);
  r.set("notes", String(body.notes || "").slice(0, 20000));
  r.set("track", track.get("id"));
  r.set("assignees", JSON.stringify(assignees));
  r.set("due", due);
  r.set("status", "open");
  r.set("created_by", actor.get("id"));
  r.set("remind_at", remindAt);
  r.set("remind_channel", remindAt ? remindChannel : "");
  r.set("remind_sent_at", "");
  r.set("followup_sent_at", "");
  r.set("remind_attempts", 0);
  r.set("stage", stage);
  r.set("priority", priority);
  r.set("due_time", dueTime);
  r.set("repeat_rule", repeatRule);
  r.set("hold_reason", stage === "blocked" || stage === "waiting" ? holdReason : "");
  r.set("watchers", JSON.stringify(watchers));
  r.set("subtasks", JSON.stringify(subtasks));
  r.set("attachments", "[]");
  r.set("cmt_count", 0);
  e.app.save(r);

  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "todo.create");
    act.set("subject", actor.getString("name") + " added “" + title.slice(0, 80) + "”");
    act.set("verb", "created this task");
    act.set("ref", r.get("id"));
    e.app.save(act);
  } catch (_) {}

  // Tell the assignee, unless the assignee is the person typing. Nobody needs
  // an inbox row saying they did the thing they are doing.
  try {
    const ncol = e.app.findCollectionByNameOrId("internal_notifs");
    for (const id of assignees) {
      if (id === actor.get("id")) continue;
      const n = new Record(ncol);
      n.set("person", id); n.set("kind", "assign");
      n.set("text", actor.getString("name") + " gave you a task");
      n.set("sub", title.slice(0, 300));
      n.set("todo", r.get("id")); n.set("actor", actor.get("id"));
      n.set("read", false); n.set("emailed_at", ""); n.set("smsed_at", "");
      e.app.save(n);
    }
  } catch (_) {}
  return e.json(200, { id: r.get("id") });
});

// --------------------------------------------------------------------------
// PATCH /internal/todos — changed fields only; done stamps; re-arm on retime.
// --------------------------------------------------------------------------
routerAdd("PATCH", "/internal/todos", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor, todo;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "pick yourself first" }); }
  try { todo = e.app.findRecordById("internal_todos", String(body.todo_id || "")); }
  catch (_) { return e.json(404, { error: "that item is gone" }); }

  // Snapshot BEFORE anything is written. Every notification below is guarded
  // on a real transition against these values, not on the field merely being
  // present in the body — otherwise a page that PATCHes its whole form on
  // every keystroke would text the assignee about a deadline that never moved.
  const wasAssignees = todo.getString("assignees") || "[]";
  const wasDue = todo.getString("due");
  const wasStage = todo.getString("stage") || "todo";
  const wasStatus = todo.getString("status");

  if ("title" in body) {
    const t = String(body.title || "").trim();
    if (!t || t.length > 500) return e.json(400, { error: "a title between 1 and 500 characters" });
    todo.set("title", t);
  }
  if ("notes" in body) todo.set("notes", String(body.notes || "").slice(0, 20000));
  if ("due" in body) {
    const due = String(body.due || "").trim();
    if (due && !/^\d{4}-\d{2}-\d{2}$/.test(due)) return e.json(400, { error: "due date should be YYYY-MM-DD" });
    todo.set("due", due);
  }
  if ("assignees" in body && Array.isArray(body.assignees)) {
    const ids = [];
    for (const id of body.assignees) {
      try { ids.push(e.app.findRecordById("internal_people", String(id)).get("id")); }
      catch (_) { return e.json(400, { error: "one of the flagged people doesn't exist" }); }
    }
    todo.set("assignees", JSON.stringify(ids));
  }
  if ("watchers" in body && Array.isArray(body.watchers)) {
    const ws = [];
    for (const id of body.watchers) {
      try { ws.push(e.app.findRecordById("internal_people", String(id)).get("id")); }
      catch (_) { return e.json(400, { error: "one of the watchers doesn't exist" }); }
    }
    todo.set("watchers", JSON.stringify(ws));
  }
  if ("stage" in body) {
    const st = String(body.stage || "").trim();
    if (["todo", "doing", "waiting", "blocked"].indexOf(st) < 0) return e.json(400, { error: "pick a stage" });
    todo.set("stage", st);
    // The hold line belongs to the held stages. Leaving a stale "waiting on
    // Jose's dock rig" attached to a task that is moving again is a chip that
    // lies on the board.
    if (st !== "blocked" && st !== "waiting") todo.set("hold_reason", "");
  }
  if ("hold_reason" in body) todo.set("hold_reason", String(body.hold_reason || "").trim().slice(0, 200));
  if ("priority" in body) {
    const pr = String(body.priority || "").trim();
    if (["urgent", "important", "normal", "later"].indexOf(pr) < 0) return e.json(400, { error: "priority is urgent, important, normal or later" });
    todo.set("priority", pr);
  }
  if ("position" in body) {
    // Hand-ordering. A float so a drop writes ONE row (midpoint of its new
    // neighbours). Clamped, not rejected: a NaN from a broken client should
    // become "unordered", never a 400 that kills the rest of the patch.
    let pos = Number(body.position);
    if (!isFinite(pos) || pos < 0) pos = 0;
    todo.set("position", pos);
  }
  if ("due_time" in body) {
    const dt = String(body.due_time || "").trim();
    if (dt && !/^\d{2}:\d{2}$/.test(dt)) return e.json(400, { error: "a time looks like 14:30" });
    todo.set("due_time", dt);
  }
  if ("repeat_rule" in body) {
    const rr = String(body.repeat_rule || "").trim();
    if (rr && !/^(none|daily|weekdays|weekly|monthly|every:[2-9]|every:[12]\d|weekly:(mon|tue|wed|thu|fri|sat|sun))$/.test(rr)) {
      return e.json(400, { error: "that repeat isn't one I know" });
    }
    todo.set("repeat_rule", rr);
  }
  if ("subtasks" in body && Array.isArray(body.subtasks)) {
    if (body.subtasks.length > 40) return e.json(400, { error: "forty subtasks is plenty — the rest are their own task" });
    const subs = [];
    for (const s of body.subtasks) {
      const t = String((s && s.t) || "").trim().slice(0, 200);
      if (!t) continue;
      subs.push({ t: t, done: !!(s && s.done) });
    }
    todo.set("subtasks", JSON.stringify(subs));
  }
  if ("attachments" in body && Array.isArray(body.attachments)) {
    if (body.attachments.length > 20) return e.json(400, { error: "twenty links is the ceiling" });
    const files = [];
    for (const f of body.attachments) {
      const n = String((f && f.n) || "").trim().slice(0, 200);
      if (!n) continue;
      // A LINK AND A NAME, NEVER AN UPLOAD. The design's own "Attach file or
      // link" is a window.prompt() that stores a typed string, and the Railway
      // volume has already been filled once by the activity ledger — which is
      // the entire reason internal_hq_prune exists. Only http(s) is stored, so
      // a pasted javascript: or data: URL cannot become a click target on a
      // page three people trust.
      let url = String((f && f.url) || "").trim().slice(0, 500);
      if (url && !/^https?:\/\//i.test(url)) return e.json(400, { error: "a link has to start with http:// or https://" });
      files.push({ n: n, url: url, by: actor.get("id"), at: new Date().toISOString() });
    }
    todo.set("attachments", JSON.stringify(files));
  }
  if ("remind_at" in body) {
    const ra = String(body.remind_at || "").trim();
    if (ra && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(ra)) return e.json(400, { error: "reminder time looks malformed" });
    todo.set("remind_at", ra);
    todo.set("remind_sent_at", "");   // re-arm: a moved reminder fires again
    todo.set("remind_attempts", 0);  // and it gets its full retry budget back
    if ("remind_channel" in body) {
      const rc = String(body.remind_channel || "");
      if (ra && ["email", "sms", "both"].indexOf(rc) < 0) return e.json(400, { error: "pick email, sms or both" });
      todo.set("remind_channel", ra ? rc : "");
    }
  }
  // Finishing something is idempotent. Arav's first minutes on the board
  // produced SIX todo.done rows for three todos — same actor, same second:
  // a double click, or a client retry, sends the mutation twice and this
  // route logged both and let the second overwrite done_at/done_by. The
  // activity feed is the audit trail; a trail that says a thing happened
  // twice is simply wrong. Only a real transition counts.
  let justFinished = false;
  if ("status" in body) {
    const s = String(body.status || "");
    // Three values, and only three. `doing`, `waiting` and `blocked` are NOT
    // status — they are `stage`, above. Accepting them here would take the row
    // out of "status = 'open'" and out of the reminder cron, /internal/state
    // and the assistant's board in one keystroke.
    if (["open", "done", "cancelled"].indexOf(s) < 0) return e.json(400, { error: "status is open, done or cancelled" });
    const wasOpen = todo.getString("status") === "open";
    todo.set("status", s);
    if (s !== "open" && wasOpen) {
      // done_at is stamped for a cancellation too — it is "the day this left
      // the board", and it is what keeps a cancelled row visible in
      // /internal/state's fourteen-day window instead of vanishing mid-week.
      todo.set("done_at", new Date().toISOString());
      todo.set("done_by", actor.get("id"));
      justFinished = s === "done";
    } else if (s === "open" && !wasOpen) {
      todo.set("done_at", ""); todo.set("done_by", "");
    }
  }
  e.app.save(todo);
  if (justFinished) {
    try {
      const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
      act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
      act.set("action", "todo.done");
      act.set("subject", actor.getString("name") + " finished “" + todo.getString("title").slice(0, 80) + "”");
      act.set("verb", "finished this");
      act.set("ref", todo.get("id"));
      e.app.save(act);
    } catch (_) {}
  }

  // ---- notifications, one per REAL transition -----------------------------
  // Written here and nowhere else in this handler, so the guards above are the
  // only thing standing between a form re-submit and someone's phone.
  try {
    const ncol = e.app.findCollectionByNameOrId("internal_notifs");
    const title = todo.getString("title").slice(0, 300);
    const nowAssignees = todo.getString("assignees") || "[]";
    const list = (s) => { try { return JSON.parse(s || "[]") || []; } catch (_) { return []; } };
    const push = (person, kind, text, sub) => {
      if (!person || person === actor.get("id")) return;
      const n = new Record(ncol);
      n.set("person", person); n.set("kind", kind);
      n.set("text", text); n.set("sub", sub);
      n.set("todo", todo.get("id")); n.set("actor", actor.get("id"));
      n.set("read", false); n.set("emailed_at", ""); n.set("smsed_at", "");
      e.app.save(n);
    };
    const watchers = list(todo.getString("watchers"));
    if (nowAssignees !== wasAssignees) {
      const had = {}; for (const id of list(wasAssignees)) had[id] = true;
      for (const id of list(nowAssignees)) if (!had[id]) push(id, "assign", actor.getString("name") + " gave you a task", title);
    }
    if (todo.getString("due") !== wasDue) {
      const when = todo.getString("due") ? "moved a deadline to " + todo.getString("due") : "took the deadline off";
      for (const id of list(nowAssignees)) push(id, "deadline", actor.getString("name") + " " + when, title);
      for (const id of watchers) push(id, "deadline", actor.getString("name") + " " + when, title);
    }
    if ((todo.getString("stage") || "todo") === "blocked" && wasStage !== "blocked") {
      push(todo.getString("created_by"), "task", actor.getString("name") + " is blocked",
        (todo.getString("hold_reason") || title).slice(0, 300));
    }
    if (justFinished && wasStatus === "open") {
      push(todo.getString("created_by"), "done", actor.getString("name") + " finished a task", title);
      for (const id of watchers) push(id, "done", actor.getString("name") + " finished a task", title);
    }
  } catch (_) {}
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/todos/delete — creator or admin only. Destruction stays human.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/todos/delete", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor, todo;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "pick yourself first" }); }
  try { todo = e.app.findRecordById("internal_todos", String(body.todo_id || "")); }
  catch (_) { return e.json(404, { error: "already gone" }); }
  const mine = todo.getString("created_by") === actor.get("id");
  if (!mine && !actor.get("is_admin")) {
    return e.json(403, { error: "only the person who added it — or an admin — can delete it" });
  }
  const title = todo.getString("title");
  e.app.delete(todo);
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "todo.delete");
    act.set("subject", actor.getString("name") + " deleted “" + title.slice(0, 80) + "”");
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/events (+ /delete) — calendar entries and countdown chips.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/events", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "pick yourself first" }); }
  const title = String(body.title || "").trim();
  const date = String(body.date || "").trim();
  if (!title || title.length > 300) return e.json(400, { error: "a title between 1 and 300 characters" });
  if (!/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(date)) return e.json(400, { error: "date should be YYYY-MM-DD (optionally THH:mm)" });
  const col = e.app.findCollectionByNameOrId("internal_events");
  const r = new Record(col);
  r.set("title", title); r.set("date", date);
  r.set("notes", String(body.notes || "").slice(0, 5000));
  r.set("countdown", !!body.countdown);
  r.set("created_by", actor.get("id"));
  e.app.save(r);
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "event.create");
    act.set("subject", actor.getString("name") + " added event “" + title.slice(0, 80) + "” (" + date + ")");
    act.set("ref", r.get("id"));
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { id: r.get("id") });
});

routerAdd("POST", "/internal/events/delete", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor, ev;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "pick yourself first" }); }
  try { ev = e.app.findRecordById("internal_events", String(body.event_id || "")); }
  catch (_) { return e.json(404, { error: "already gone" }); }
  if (ev.getString("created_by") !== actor.get("id") && !actor.get("is_admin")) {
    return e.json(403, { error: "only its creator or an admin can delete it" });
  }
  e.app.delete(ev);
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/tracks — admin-only fellowship track upsert.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/tracks", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }

  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "pick yourself first" }); }
  if (!actor.get("is_admin")) return e.json(403, { error: "only an admin can manage boards" });

  let members = null;
  if (Array.isArray(body.members)) {
    members = [];
    for (const id of body.members) {
      try { members.push(e.app.findRecordById("internal_people", String(id)).get("id")); }
      catch (_) { return e.json(400, { error: "one of those members doesn't exist" }); }
    }
  }

  let track;
  if (body.track_id) {
    try { track = e.app.findRecordById("internal_tracks", String(body.track_id)); }
    catch (_) { return e.json(404, { error: "no such board" }); }
    if ("name" in body) {
      const n = String(body.name || "").trim();
      if (!n) return e.json(400, { error: "a board needs a name" });
      track.set("name", n);
    }
    if (members !== null) track.set("members", JSON.stringify(members));
    if ("active" in body) track.set("active", !!body.active);
  } else {
    const n = String(body.name || "").trim();
    if (!n || n.length > 120) return e.json(400, { error: "a board name between 1 and 120 characters" });
    track = new Record(e.app.findCollectionByNameOrId("internal_tracks"));
    track.set("name", n); track.set("kind", String(body.kind || "fellowship"));
    track.set("members", JSON.stringify(members || [])); track.set("active", true);
    track.set("archived", false);
  }
  // `active` and `archived` are different things and both are kept. active=false
  // takes a project out of the New Task picker (the existing guard in POST
  // /internal/todos already refuses "that board is archived"); archived=true
  // only greys the card and drops it from default lists. Collapsing them would
  // mean you cannot put a project away without breaking every task on it.
  if ("desc" in body) track.set("desc", String(body.desc || "").trim().slice(0, 300));
  if ("archived" in body) track.set("archived", !!body.archived);
  if ("notes" in body) track.set("notes", String(body.notes || "").slice(0, 20000));
  if ("owner" in body) {
    const own = String(body.owner || "").trim();
    if (own) {
      try { track.set("owner", e.app.findRecordById("internal_people", own).get("id")); }
      catch (_) { return e.json(400, { error: "that owner isn't on the team" }); }
    } else track.set("owner", "");
  }
  e.app.save(track);
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "track.update");
    act.set("subject", actor.getString("name") + " updated board “" + track.getString("name") + "”");
    act.set("ref", track.get("id"));
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { id: track.get("id") });
});

// --------------------------------------------------------------------------
// POST /internal/router — the task-routing concierge.
// Stateless: the client sends the whole transcript each turn. The model asks
// at most 3 clarifying questions, then decides which agent the task belongs
// to and writes the prompt to paste there.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/router", (e) => {
  // GONE. The AI surface was removed from HQ on 2026-08-23 — no assistant,
  // no task router, no research lane, no dictation, no read-aloud. Nothing in
  // the product calls this any more and the rewrite that reached it from
  // anticipy.ai has been deleted.
  //
  // The handler is closed here rather than deleted outright because this file
  // is 3,113 lines and cutting a block out of it by hand is how you take the
  // whole of HQ down with a stray brace. One line, checked, is the safer kill.
  // If it stays dead through a release or two, delete the body.
  return e.json(410, { error: "the AI surface was removed from HQ" });
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const msgs = Array.isArray(body.messages) ? body.messages : [];
  if (!msgs.length || msgs.length > 16) return e.json(400, { error: "between 1 and 16 messages" });

  // ---- hourly meter (house two-field pattern; count the attempt) ----
  try {
    const meter = e.app.findFirstRecordByFilter("internal_meter", "name = 'llm'");
    const hourNow = new Date().toISOString().slice(0, 13);
    const used = meter.getString("hour") === hourNow ? (Number(meter.get("calls")) || 0) : 0;
    const ceiling = parseInt($os.getenv("ANTICIPY_INTERNAL_LLM_CEILING") || "60", 10);
    if (used >= ceiling) {
      return e.json(429, { error: "the team's AI budget for this hour is used up", resumes: "top of the hour" });
    }
    meter.set("hour", hourNow); meter.set("calls", used + 1);
    e.app.save(meter);
  } catch (err) { console.log("internal_hq: llm meter failed (never blocking): " + err); }

  const system = [
    "You route tasks to the right AI agent for a small startup team. The agents:",
    "- claude_code: multi-file coding inside the repo on a Mac — refactors, features, debugging with tests.",
    "- claude_chat: thinking, writing, analysis, review. No hands, no repo.",
    "- codex: background/parallel coding tasks, PR-shaped work.",
    "- browser_agent: Anticipy's own hands in a logged-in Chrome — forms, bookings, purchases, account tasks.",
    "- research: a cheap cited web lookup (one search, three pages, one model pass) — facts in minutes.",
    "Ask AT MOST 3 clarifying questions total, one per turn, and only when the answer changes the routing or the prompt.",
    "Reply with STRICT JSON only, no prose around it. Either:",
    '{"question":"..."} or {"decision":{"agent":"claude_code|claude_chat|codex|browser_agent|research","why":"one line","prompt":"a complete ready-to-paste prompt crafted for that agent, carrying every detail the user gave"}}',
  ].join("\n");

  const messages = [{ role: "system", content: system }];
  let total = 0;
  for (const m of msgs) {
    const role = m.role === "assistant" ? "assistant" : "user";
    const content = String(m.content || "").slice(0, 2000);
    total += content.length;
    messages.push({ role: role, content: content });
  }
  if (total > 8000) return e.json(400, { error: "that conversation got too long — start a fresh one" });

  const orKey = $os.getenv("OPENROUTER_API_KEY") || "";
  if (!orKey) return e.json(503, { error: "no AI key configured on the server" });
  const model = $os.getenv("ANTICIPY_INTERNAL_MODEL") || "google/gemini-3.7-flash";
  let res;
  try {
    res = $http.send({
      url: "https://openrouter.ai/api/v1/chat/completions",
      method: "POST",
      headers: {
        "Authorization": "Bearer " + orKey,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy HQ",
      },
      // JSON mode AND a generous ceiling — both are load-bearing.
      //
      // At max_tokens 700 this failed roughly two times in five with
      // finish_reason "length": gemini-3.7-flash spends reasoning tokens
      // against the same budget, so the JSON was being truncated mid-object
      // and the person just saw "say that again?". Measured directly: 700 →
      // 3/5 parsed, 2000 → 5/5. Billing is by tokens actually used, not the
      // ceiling, so the headroom is free.
      //
      // Do NOT "optimise" this by excluding reasoning — tried, and it drops
      // to 0/5. The model needs to think before it answers.
      body: JSON.stringify({ model: model, messages: messages, temperature: 0,
        max_tokens: 2000, response_format: { type: "json_object" } }),
      timeout: 60,
    });
  } catch (err) {
    return e.json(502, { error: "the AI didn't answer — try again" });
  }
  let text = "";
  try { text = res.json.choices[0].message.content || ""; } catch (_) {}
  let parsed = null;
  try { parsed = JSON.parse(text); } catch (_) {
    const a = text.indexOf("{"), b = text.lastIndexOf("}");
    if (a >= 0 && b > a) { try { parsed = JSON.parse(text.slice(a, b + 1)); } catch (_) {} }
  }
  if (!parsed) return e.json(200, { say: "I couldn't parse that — try rephrasing." });
  if (parsed.question) return e.json(200, { question: String(parsed.question).slice(0, 500) });
  if (parsed.decision && parsed.decision.agent) {
    const d = parsed.decision;
    const agents = ["claude_code", "claude_chat", "codex", "browser_agent", "research"];
    if (agents.indexOf(d.agent) < 0) d.agent = "claude_chat";
    return e.json(200, { decision: {
      agent: d.agent,
      why: String(d.why || "").slice(0, 300),
      prompt: String(d.prompt || "").slice(0, 4000),
    } });
  }
  return e.json(200, { say: "I couldn't decide — add a little more detail." });
});

// --------------------------------------------------------------------------
// POST /internal/assistant — the on-page helper that can DO things.
// STRICT JSON out: {say} or {action}. The action is validated and executed
// here with the same rules as the CRUD routes. No delete tool, by design.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/assistant", (e) => {
  // REVIVED 2026-08-23 (same day it was killed): Omar asked for "a little
  // chat button on the side that can control the to-dos — not an AI-first
  // interface". The route is back; the router/research/dictation surfaces
  // stay dead. Now wearing the session door like every living route.
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "pick yourself first" }); }
  const msgs = Array.isArray(body.messages) ? body.messages : [];
  if (!msgs.length || msgs.length > 12) return e.json(400, { error: "between 1 and 12 messages" });

  // ---- meter (shared with the router) ----
  try {
    const meter = e.app.findFirstRecordByFilter("internal_meter", "name = 'llm'");
    const hourNow = new Date().toISOString().slice(0, 13);
    const used = meter.getString("hour") === hourNow ? (Number(meter.get("calls")) || 0) : 0;
    const ceiling = parseInt($os.getenv("ANTICIPY_INTERNAL_LLM_CEILING") || "60", 10);
    if (used >= ceiling) {
      return e.json(429, { error: "the team's AI budget for this hour is used up", resumes: "top of the hour" });
    }
    meter.set("hour", hourNow); meter.set("calls", used + 1);
    e.app.save(meter);
  } catch (err) { console.log("internal_hq: llm meter failed (never blocking): " + err); }

  // ---- live context: people and tracks, so "flag it to Ari" resolves ----
  const peopleLines = [];
  try {
    const people = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 100, 0);
    for (const p of people) peopleLines.push(p.getString("name"));
  } catch (_) {}
  const trackLines = [];
  try {
    const tracks = e.app.findRecordsByFilter("internal_tracks", "active = true", "+created", 20, 0);
    for (const t of tracks) trackLines.push(t.getString("name"));
  } catch (_) {}
  const tz = $os.getenv("ANTICIPY_INTERNAL_TZ") || "America/New_York";

  // THE ASSISTANT WAS BLIND.
  //
  // It was handed the team's NAMES and the BOARD NAMES and nothing else — not
  // one todo. Asked "what is on the board right now?" it answered, from inside
  // the dashboard, "I don't have direct visibility into the current live tasks
  // ... you can check the dashboard directly." Three different questions, three
  // versions of go-look-yourself. That single fact is most of why the product
  // reads as having no intelligence in it: the intelligence could not see.
  //
  // So it gets the board. Bounded on purpose — open items only, newest 60,
  // titles clipped — because this rides on every message and tokens are not
  // free. Roughly 400-900 tokens of context buys an assistant that can
  // actually answer.
  const nowMs = Date.now();
  const nameOf = {};
  const contactless = [];
  try {
    const all = e.app.findRecordsByFilter("internal_people", "active = true", "+created", 60, 0);
    for (const p of all) {
      nameOf[p.get("id")] = p.getString("name");
      if (!p.getString("email") && !p.getString("phone")) contactless.push(p.getString("name"));
    }
  } catch (_) {}
  const trackName = {};
  try {
    const ts = e.app.findRecordsByFilter("internal_tracks", "active = true", "+created", 20, 0);
    for (const t of ts) trackName[t.get("id")] = t.getString("name");
  } catch (_) {}

  const boardLines = [];
  let openCount = 0;
  try {
    const open = e.app.findRecordsByFilter("internal_todos", "status = 'open'", "+created", 60, 0);
    openCount = open.length;
    for (const t of open) {
      let who = [];
      try {
        who = (JSON.parse(t.getString("assignees") || "[]") || [])
          .map((id) => nameOf[id]).filter(Boolean);
      } catch (_) {}
      const days = Math.floor((nowMs - new Date(t.getString("created")).getTime()) / 86400000);
      const bits = [
        "- " + t.getString("title").slice(0, 90),
        "[" + (trackName[t.getString("track")] || "?") + "]",
        who.length ? "-> " + who.join(", ") : "-> nobody",
      ];
      // stage and priority ride along because the assistant can now SET them,
      // and a tool that can set a field it cannot see will happily "change" a
      // task to the state it is already in and report that it did something.
      const stg = t.getString("stage") || "todo";
      if (stg !== "todo") bits.push("(" + stg + ")");
      const pri = t.getString("priority") || "normal";
      if (pri !== "normal") bits.push("[" + pri + "]");
      if (t.getString("due")) bits.push("due " + t.getString("due"));
      if (isFinite(days) && days >= 1) bits.push(days + "d old");
      boardLines.push(bits.join(" "));
    }
  } catch (_) {}

  const recent = [];
  try {
    const acts = e.app.findRecordsByFilter("internal_activity", "", "-created", 12, 0);
    for (const a of acts) recent.push("- " + a.getString("subject").slice(0, 90));
  } catch (_) {}

  const system = [
    "You are the assistant inside Anticipy HQ, a small team dashboard. You can talk, or you can act.",
    "Now (UTC): " + new Date().toISOString() + ". The team's timezone: " + tz + ". Interpret spoken times in that timezone and output remind_at as UTC ISO (YYYY-MM-DDTHH:mm).",
    "Team members: " + (peopleLines.join(", ") || "none yet") + ".",
    "Boards: " + (trackLines.join(", ") || "none") + ".",
    "The person speaking to you is: " + actor.getString("name") + ".",
    "",
    "THE BOARD RIGHT NOW (" + openCount + " open):",
    (boardLines.join("\n") || "- nothing open"),
    "",
    "LATELY:",
    (recent.join("\n") || "- nothing yet"),
    (contactless.length
      ? "\nNOTE: these people have no email and no phone, so no reminder can ever reach them: "
        + contactless.join(", ") + ". Say so if it is relevant to what is being asked."
      : ""),
    "",
    "Answer questions about the board from the list above — you can see it, so never tell",
    "anyone to go and look at the dashboard themselves.",
    "Reply with STRICT JSON only. Either {\"say\":\"...\"} to talk, or ONE action:",
    '{"action":{"type":"create_todo","title":"...","track_name":"...","assignee_names":["..."],"due":"YYYY-MM-DD","notes":"...","remind_at":"...","remind_channel":"email|sms|both"}}',
    '{"action":{"type":"complete_todo","match":"substring of the todo title"}}',
    '{"action":{"type":"assign_todo","match":"...","assignee_names":["..."]}}',
    '{"action":{"type":"set_reminder","match":"...","remind_at":"...","remind_channel":"email|sms|both"}}',
    '{"action":{"type":"create_event","title":"...","date":"YYYY-MM-DD","countdown":true}}',
    '{"action":{"type":"add_person","name":"...","email":"...","phone":"..."}}',
    '{"action":{"type":"set_contact","person_name":"...","email":"...","phone":"..."}}',
    '{"action":{"type":"set_priority","match":"...","priority":"urgent|important|normal|later"}}',
    '{"action":{"type":"set_stage","match":"...","stage":"todo|doing|waiting|blocked","hold_reason":"..."}}',
    '{"action":{"type":"add_subtask","match":"...","text":"..."}}',
    '{"action":{"type":"comment","match":"...","text":"..."}}',
    '{"action":{"type":"create_project","name":"...","desc":"..."}}',
    '{"action":{"type":"delete_todo","match":"..."}}',
    "Optional fields may be omitted. delete_todo is for 'remove/delete this' — it erases the",
    "item; complete_todo is for 'done/finished'. Never guess between them from vague wording.",
    "If a name or match is ambiguous or unknown, do NOT act — say so and ask which one.",
  ].join("\n");

  const messages = [{ role: "system", content: system }];
  let total = 0;
  for (const m of msgs) {
    const role = m.role === "assistant" ? "assistant" : "user";
    const content = String(m.content || "").slice(0, 1500);
    total += content.length;
    messages.push({ role: role, content: content });
  }
  if (total > 6000) return e.json(400, { error: "that conversation got long — start fresh" });

  const orKey = $os.getenv("OPENROUTER_API_KEY") || "";
  if (!orKey) return e.json(503, { error: "no AI key configured on the server" });
  const model = $os.getenv("ANTICIPY_INTERNAL_MODEL") || "google/gemini-3.7-flash";
  let res;
  try {
    res = $http.send({
      url: "https://openrouter.ai/api/v1/chat/completions",
      method: "POST",
      headers: {
        "Authorization": "Bearer " + orKey,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://anticipy.ai",
        "X-Title": "Anticipy HQ",
      },
      // JSON mode AND a generous ceiling — both are load-bearing.
      //
      // At max_tokens 700 this failed roughly two times in five with
      // finish_reason "length": gemini-3.7-flash spends reasoning tokens
      // against the same budget, so the JSON was being truncated mid-object
      // and the person just saw "say that again?". Measured directly: 700 →
      // 3/5 parsed, 2000 → 5/5. Billing is by tokens actually used, not the
      // ceiling, so the headroom is free.
      //
      // Do NOT "optimise" this by excluding reasoning — tried, and it drops
      // to 0/5. The model needs to think before it answers.
      body: JSON.stringify({ model: model, messages: messages, temperature: 0,
        max_tokens: 2000, response_format: { type: "json_object" } }),
      timeout: 60,
    });
  } catch (err) {
    return e.json(502, { error: "the AI didn't answer — try again" });
  }
  let text = "";
  try { text = res.json.choices[0].message.content || ""; } catch (_) {}
  let parsed = null;
  try { parsed = JSON.parse(text); } catch (_) {
    const a = text.indexOf("{"), b = text.lastIndexOf("}");
    if (a >= 0 && b > a) { try { parsed = JSON.parse(text.slice(a, b + 1)); } catch (_) {} }
  }
  if (!parsed) return e.json(200, { say: "Sorry — say that again?" });
  if (parsed.say) return e.json(200, { say: String(parsed.say).slice(0, 800) });
  const action = parsed.action || null;
  if (!action || !action.type) return e.json(200, { say: "Sorry — say that again?" });

  // ---- helpers, declared here because JSVM isolation demands it ----
  const findPersonByName = (name) => {
    const want = String(name || "").trim().toLowerCase();
    if (!want) return { err: "no name given" };
    const hits = [];
    try {
      const people = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 100, 0);
      for (const p of people) {
        const n = p.getString("name").toLowerCase();
        if (n === want || n.indexOf(want) === 0) hits.push(p);
      }
    } catch (_) {}
    if (hits.length === 1) return { rec: hits[0] };
    if (!hits.length) return { err: "I don't know anyone called " + name };
    return { err: "which " + name + " — " + hits.map((h) => h.getString("name")).join(" or ") + "?" };
  };
  const findTrackByName = (name) => {
    const want = String(name || "").trim().toLowerCase();
    const hits = [];
    try {
      const tracks = e.app.findRecordsByFilter("internal_tracks", "active = true", "+created", 20, 0);
      for (const t of tracks) {
        const n = t.getString("name").toLowerCase();
        if (n === want || n.indexOf(want) >= 0) hits.push(t);
      }
    } catch (_) {}
    if (hits.length === 1) return { rec: hits[0] };
    if (!hits.length) return { err: "no board called " + name };
    return { err: "which board — " + hits.map((h) => h.getString("name")).join(" or ") + "?" };
  };
  const findTodoByMatch = (match) => {
    const want = String(match || "").trim().toLowerCase();
    if (want.length < 3) return { err: "give me a few words of the title" };
    const hits = [];
    try {
      const todos = e.app.findRecordsByFilter("internal_todos", "status = 'open'", "-created", 200, 0);
      for (const t of todos) {
        if (t.getString("title").toLowerCase().indexOf(want) >= 0) hits.push(t);
      }
    } catch (_) {}
    if (hits.length === 1) return { rec: hits[0] };
    if (!hits.length) return { err: "I can't find an open item matching “" + match + "”" };
    return { err: "that matches " + hits.length + " items — be more specific" };
  };
  const logAct = (action2, subject, ref) => {
    try {
      const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
      act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
      act.set("action", action2); act.set("subject", subject); act.set("ref", ref || "");
      e.app.save(act);
    } catch (_) {}
  };

  try {
    if (action.type === "create_todo") {
      const title = String(action.title || "").trim().slice(0, 500);
      if (!title) return e.json(200, { say: "What should the item say?" });
      const tr = findTrackByName(action.track_name || "Company");
      if (tr.err) return e.json(200, { say: tr.err });
      const ids = [];
      const names = [];
      if (Array.isArray(action.assignee_names)) {
        for (const n of action.assignee_names) {
          const f = findPersonByName(n);
          if (f.err) return e.json(200, { say: f.err });
          ids.push(f.rec.get("id")); names.push(f.rec.getString("name"));
        }
      }
      const due = /^\d{4}-\d{2}-\d{2}$/.test(String(action.due || "")) ? String(action.due) : "";
      const ra = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(String(action.remind_at || "")) ? String(action.remind_at) : "";
      const rc = ["email", "sms", "both"].indexOf(String(action.remind_channel || "")) >= 0 ? String(action.remind_channel) : (ra ? "email" : "");
      const r = new Record(e.app.findCollectionByNameOrId("internal_todos"));
      r.set("title", title); r.set("notes", String(action.notes || "").slice(0, 20000));
      r.set("track", tr.rec.get("id")); r.set("assignees", JSON.stringify(ids));
      r.set("due", due); r.set("status", "open"); r.set("created_by", actor.get("id"));
      r.set("remind_at", ra); r.set("remind_channel", ra ? rc : "");
      r.set("remind_sent_at", ""); r.set("followup_sent_at", ""); r.set("remind_attempts", 0);
      e.app.save(r);
      const summary = "Created “" + title + "” on " + tr.rec.getString("name")
        + (names.length ? " — flagged to " + names.join(", ") : "")
        + (due ? ", due " + due : "") + (ra ? ", reminder armed" : "");
      logAct("assistant.action", summary, r.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "complete_todo") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      f.rec.set("status", "done"); f.rec.set("done_at", new Date().toISOString());
      f.rec.set("done_by", actor.get("id"));
      e.app.save(f.rec);
      const summary = "Marked “" + f.rec.getString("title") + "” done";
      logAct("assistant.action", summary, f.rec.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "delete_todo") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      // Same rule as the delete button: yours, or an admin's broom. The
      // assistant gets no more power than the person talking to it has.
      const mine = f.rec.getString("created_by") === actor.get("id");
      if (!mine && !actor.get("is_admin")) {
        return e.json(200, { say: "Only " + (nameOf[f.rec.getString("created_by")] || "whoever added it")
          + " or an admin can delete “" + f.rec.getString("title").slice(0, 60) + "”." });
      }
      const title2 = f.rec.getString("title");
      e.app.delete(f.rec);
      const summary = "Deleted “" + title2.slice(0, 80) + "”";
      logAct("assistant.action", summary, "");
      return e.json(200, { done: { summary: summary, action: action } });
    }
        if (action.type === "assign_todo") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      const ids = []; const names = [];
      for (const n of (action.assignee_names || [])) {
        const p = findPersonByName(n);
        if (p.err) return e.json(200, { say: p.err });
        ids.push(p.rec.get("id")); names.push(p.rec.getString("name"));
      }
      if (!ids.length) return e.json(200, { say: "Flag it to whom?" });
      f.rec.set("assignees", JSON.stringify(ids));
      e.app.save(f.rec);
      const summary = "Flagged “" + f.rec.getString("title") + "” to " + names.join(", ");
      logAct("assistant.action", summary, f.rec.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "set_reminder") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      const ra = String(action.remind_at || "");
      if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(ra)) return e.json(200, { say: "When exactly? Give me a date and time." });
      const rc = ["email", "sms", "both"].indexOf(String(action.remind_channel || "")) >= 0 ? String(action.remind_channel) : "email";
      f.rec.set("remind_at", ra); f.rec.set("remind_channel", rc); f.rec.set("remind_sent_at", "");
      f.rec.set("remind_attempts", 0);
      e.app.save(f.rec);
      const summary = "Reminder set on “" + f.rec.getString("title") + "” (" + rc + ")";
      logAct("assistant.action", summary, f.rec.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "create_event") {
      const title = String(action.title || "").trim().slice(0, 300);
      const date = String(action.date || "");
      if (!title) return e.json(200, { say: "What's the event called?" });
      if (!/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/.test(date)) return e.json(200, { say: "What date is that? (YYYY-MM-DD)" });
      const r = new Record(e.app.findCollectionByNameOrId("internal_events"));
      r.set("title", title); r.set("date", date);
      r.set("countdown", action.countdown !== false); r.set("created_by", actor.get("id"));
      r.set("notes", String(action.notes || "").slice(0, 5000));
      e.app.save(r);
      const summary = "Added event “" + title + "” on " + date;
      logAct("assistant.action", summary, r.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "add_person") {
      const name = String(action.name || "").trim().slice(0, 120);
      if (!name) return e.json(200, { say: "What's their name?" });
      try {
        const dupes = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 200, 0);
        for (const d of dupes) {
          if (d.getString("name").toLowerCase() === name.toLowerCase()) {
            return e.json(200, { say: name + " is already on the team." });
          }
        }
      } catch (_) {}
      const email = String(action.email || "").trim();
      const phone = String(action.phone || "").trim().replace(/[\s()-]/g, "");
      if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) return e.json(200, { say: "That email doesn't look right." });
      if (phone && !/^\+?\d{8,15}$/.test(phone)) return e.json(200, { say: "That phone number doesn't look right." });
      const r = new Record(e.app.findCollectionByNameOrId("internal_people"));
      r.set("name", name); r.set("email", email); r.set("phone", phone);
      r.set("is_admin", false); r.set("active", true);
      e.app.save(r);
      const summary = "Added " + name + " to the team";
      logAct("assistant.action", summary, r.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    // The assistant could DIAGNOSE that nobody on the team is reachable and
    // then do nothing about it — the same inert-insight problem the People
    // view has, where "no email — reminders can't reach them" is printed
    // three times and never actionable. If it can name the problem it should
    // be able to close it: "my email is x@y.com" now lands.
    if (action.type === "set_contact") {
      const who = String(action.person_name || "").trim();
      let target = null;
      try {
        const all = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 200, 0);
        const hits = all.filter((p) => p.getString("name").toLowerCase() === who.toLowerCase());
        if (hits.length === 1) target = hits[0];
        else if (hits.length > 1) return e.json(200, { say: "There's more than one " + who + " — which?" });
      } catch (_) {}
      if (!target) return e.json(200, { say: who ? "I don't know a " + who + " on the team." : "Whose details are these?" });

      const hasEmail = "email" in action, hasPhone = "phone" in action;
      if (!hasEmail && !hasPhone) return e.json(200, { say: "An email, a phone number, or both?" });
      const email = String(action.email || "").trim();
      const phone = String(action.phone || "").trim().replace(/[\s()-]/g, "");
      if (hasEmail && email && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
        return e.json(200, { say: "That email doesn't look right." });
      }
      if (hasPhone && phone && !/^\+?\d{8,15}$/.test(phone)) {
        return e.json(200, { say: "That phone number doesn't look right — include the country code." });
      }
      if (hasEmail) target.set("email", email);
      if (hasPhone) target.set("phone", phone);
      e.app.save(target);
      const bits = [];
      if (hasEmail && email) bits.push("email");
      if (hasPhone && phone) bits.push("phone");
      const summary = bits.length
        ? "Saved " + target.getString("name") + "'s " + bits.join(" and ") + " — reminders can reach them now"
        : "Cleared " + target.getString("name") + "'s contact details";
      logAct("assistant.action", summary, target.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    // ---- the five new verbs -------------------------------------------
    // Validated here with the same lists the CRUD routes use, copied inline
    // rather than shared, because a const at file top level is invisible in
    // here. A model that returns stage:"done" must be refused by CODE — the
    // system prompt above is a wish, this branch is the guarantee, and
    // "done" on `stage` would silently take the row out of the reminder cron.
    if (action.type === "set_priority") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      const pr = String(action.priority || "");
      if (["urgent", "important", "normal", "later"].indexOf(pr) < 0) return e.json(200, { say: "Urgent, important, normal or later?" });
      f.rec.set("priority", pr);
      e.app.save(f.rec);
      const summary = "Set “" + f.rec.getString("title") + "” to " + pr;
      logAct("assistant.action", summary, f.rec.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "set_stage") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      const st = String(action.stage || "");
      if (["todo", "doing", "waiting", "blocked"].indexOf(st) < 0) return e.json(200, { say: "To do, in progress, waiting or blocked?" });
      f.rec.set("stage", st);
      const hr = String(action.hold_reason || "").trim().slice(0, 200);
      f.rec.set("hold_reason", (st === "blocked" || st === "waiting") ? hr : "");
      e.app.save(f.rec);
      const summary = "Moved “" + f.rec.getString("title") + "” to " + st + (hr ? " — " + hr : "");
      logAct("assistant.action", summary, f.rec.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "add_subtask") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      const txt = String(action.text || "").trim().slice(0, 200);
      if (!txt) return e.json(200, { say: "What's the step?" });
      let subs = [];
      try { subs = JSON.parse(f.rec.getString("subtasks") || "[]") || []; } catch (_) {}
      if (subs.length >= 40) return e.json(200, { say: "That one already has forty steps — it wants to be its own task." });
      subs.push({ t: txt, done: false });
      f.rec.set("subtasks", JSON.stringify(subs));
      e.app.save(f.rec);
      const summary = "Added a step to “" + f.rec.getString("title") + "”: " + txt;
      logAct("assistant.action", summary, f.rec.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "comment") {
      const f = findTodoByMatch(action.match);
      if (f.err) return e.json(200, { say: f.err });
      const txt = String(action.text || "").trim().slice(0, 4000);
      if (!txt) return e.json(200, { say: "What should it say?" });
      const c = new Record(e.app.findCollectionByNameOrId("internal_comments"));
      c.set("todo", f.rec.get("id"));
      c.set("author", actor.get("id"));
      c.set("author_name", actor.getString("name"));
      c.set("text", txt); c.set("parent", ""); c.set("edited_at", ""); c.set("deleted", false);
      e.app.save(c);
      f.rec.set("cmt_count", (Number(f.rec.get("cmt_count")) || 0) + 1);
      e.app.save(f.rec);
      const summary = "Commented on “" + f.rec.getString("title") + "”";
      logAct("assistant.action", summary, f.rec.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
    if (action.type === "create_project") {
      // Same admin guard POST /internal/tracks has. A misheard "new project
      // called Ari" out of "new task for Ari" creates a container that then
      // swallows work, so the one person who can undo it is the only person
      // who can cause it.
      if (!actor.get("is_admin")) return e.json(200, { say: "Only an admin can start a project — ask Omar." });
      const nm = String(action.name || "").trim().slice(0, 120);
      if (!nm) return e.json(200, { say: "What's the project called?" });
      try {
        const ex = e.app.findRecordsByFilter("internal_tracks", "id != ''", "+created", 50, 0);
        for (const t of ex) {
          if (t.getString("name").toLowerCase() === nm.toLowerCase()) return e.json(200, { say: "There's already a project called " + nm + "." });
        }
      } catch (_) {}
      const tr = new Record(e.app.findCollectionByNameOrId("internal_tracks"));
      tr.set("name", nm); tr.set("kind", "company"); tr.set("members", "[]");
      tr.set("active", true); tr.set("archived", false);
      tr.set("desc", String(action.desc || "").trim().slice(0, 300));
      tr.set("owner", actor.get("id")); tr.set("notes", "");
      e.app.save(tr);
      const summary = "Started the project “" + nm + "”";
      logAct("assistant.action", summary, tr.get("id"));
      return e.json(200, { done: { summary: summary, action: action } });
    }
  } catch (err) {
    console.log("internal_hq: assistant action failed: " + err);
    return e.json(200, { say: "That didn't go through — try it by hand?" });
  }
  return e.json(200, { say: "I don't know how to do that yet." });
});

// --------------------------------------------------------------------------
// POST /internal/research — launch ONE cheap research task on the worker.
// The job is created server-side (e.app.save), so the collection guard and
// the research-lane guard never see it. params.internal=true keeps the
// worker from texting Omar about it — the dashboard reads the row itself.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/research", (e) => {
  // GONE. The AI surface was removed from HQ on 2026-08-23 — no assistant,
  // no task router, no research lane, no dictation, no read-aloud. Nothing in
  // the product calls this any more and the rewrite that reached it from
  // anticipy.ai has been deleted.
  //
  // The handler is closed here rather than deleted outright because this file
  // is 3,113 lines and cutting a block out of it by hand is how you take the
  // whole of HQ down with a stray brace. One line, checked, is the safer kill.
  // If it stays dead through a release or two, delete the body.
  return e.json(410, { error: "the AI surface was removed from HQ" });
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
  catch (_) { return e.json(400, { error: "pick yourself first" }); }
  const goal = String(body.goal || "").trim();
  if (goal.length < 5 || goal.length > 500) return e.json(400, { error: "a goal between 5 and 500 characters" });

  const ownerRef = $os.getenv("ANTICIPY_RESEARCH_OWNER_REF") || "";
  if (!ownerRef) return e.json(503, { error: "research is not configured on this server" });

  // One slot: research runs serially inside the worker's loop and blocks the
  // product's own hearing while it does — a burst from the dashboard would be
  // a denial of service on the assistant itself.
  let meter = null;
  try {
    meter = e.app.findFirstRecordByFilter("internal_meter", "name = 'research'");
    const liveId = meter.getString("live_job_id");
    if (liveId) {
      let stillLive = false;
      try {
        const j = e.app.findRecordById("jobs", liveId);
        const s = j.getString("status");
        stillLive = s === "queued" || s === "running";
      } catch (_) {}
      if (stillLive) return e.json(409, { error: "a research task is already running — give it a minute", job_id: liveId });
    }
  } catch (_) {}

  const jobs = e.app.findCollectionByNameOrId("jobs");
  const r = new Record(jobs);
  r.set("goal", goal);
  r.set("params", JSON.stringify({ internal: true, hq_actor: actor.get("id") }));
  r.set("status", "queued");
  r.set("lane", "research");
  r.set("owner_ref", ownerRef);
  r.set("device_id", "anticipy");
  e.app.save(r);

  if (meter) {
    try { meter.set("live_job_id", r.get("id")); e.app.save(meter); } catch (_) {}
  }
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "research.launch");
    act.set("subject", actor.getString("name") + " launched research: “" + goal.slice(0, 80) + "”");
    act.set("ref", r.get("id"));
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { job_id: r.get("id") });
});

// --------------------------------------------------------------------------
// GET /internal/research/status?id=… — poll ONE internal research job.
// Hard-refuses anything that is not an internal research job: this route
// must never become a keyed window into arbitrary product jobs.
// --------------------------------------------------------------------------
routerAdd("GET", "/internal/research/status", (e) => {
  // GONE. The AI surface was removed from HQ on 2026-08-23 — no assistant,
  // no task router, no research lane, no dictation, no read-aloud. Nothing in
  // the product calls this any more and the rewrite that reached it from
  // anticipy.ai has been deleted.
  //
  // The handler is closed here rather than deleted outright because this file
  // is 3,113 lines and cutting a block out of it by hand is how you take the
  // whole of HQ down with a stray brace. One line, checked, is the safer kill.
  // If it stays dead through a release or two, delete the body.
  return e.json(410, { error: "the AI surface was removed from HQ" });
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  const id = e.request.url.query().get("id") || "";
  if (!id) return e.json(400, { error: "which job?" });
  let job;
  try { job = e.app.findRecordById("jobs", id); }
  catch (_) { return e.json(404, { error: "no such job" }); }
  if (job.getString("lane") !== "research") return e.json(403, { error: "not an internal job" });
  let params = {};
  try { params = JSON.parse(job.getString("params") || "{}") || {}; } catch (_) {}
  if (params.internal !== true) return e.json(403, { error: "not an internal job" });

  const status = job.getString("status");
  if (status === "done" || status === "failed" || status === "cancelled") {
    try {
      const meter = e.app.findFirstRecordByFilter("internal_meter", "name = 'research'");
      if (meter.getString("live_job_id") === id) { meter.set("live_job_id", ""); e.app.save(meter); }
    } catch (_) {}
  }
  return e.json(200, { status: status, result: job.getString("result"),
    updated: job.getString("updated") });
});

// --------------------------------------------------------------------------
// CRON: reminders + follow-ups + research-slot backstop, every 5 minutes.
//
// CLAIM-FIRST, THEN SEND — the deliberate inversion of the password-reset
// rule, and here is why: this cron refires every five minutes forever, so
// send-first with a failed persist means UNBOUNDED duplicate texts (the
// worker lived precisely that loop). Claim-first with a failed send loses at
// most one nudge — and the todo still sits on the board with its due chip,
// so nothing disappears silently. The stamp rolls back only when EVERY
// channel failed, so the next sweep retries.
//
// NOTE: cron handlers have no `e` — everything goes through $app.
// --------------------------------------------------------------------------
cronAdd("internal_hq_sweep", "*/5 * * * *", () => {
  const REMIND_MAX_TRIES = 3;

  // Accepts a PocketBase datetime with or without its trailing Z, and any
  // explicit offset. Returns NaN only when the value is genuinely unparseable.
  const pbTime = (v) => {
    if (!v) return NaN;
    let t = String(v).trim().replace(" ", "T");
    if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(t)) t += "Z";
    return new Date(t).getTime();
  };
  const b64 = (str) => {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let out = "", i = 0;
    while (i < str.length) {
      const c1 = str.charCodeAt(i++), c2 = str.charCodeAt(i++), c3 = str.charCodeAt(i++);
      const e1 = c1 >> 2, e2 = ((c1 & 3) << 4) | (c2 >> 4);
      let e3 = ((c2 & 15) << 2) | (c3 >> 6), e4 = c3 & 63;
      if (isNaN(c2)) e3 = e4 = 64; else if (isNaN(c3)) e4 = 64;
      out += chars.charAt(e1) + chars.charAt(e2)
        + (e3 === 64 ? "=" : chars.charAt(e3)) + (e4 === 64 ? "=" : chars.charAt(e4));
    }
    return out;
  };

  const sendSMS = (to, text) => {
    const sid = $os.getenv("TWILIO_ACCOUNT_SID") || "";
    const auth = $os.getenv("TWILIO_AUTH_TOKEN") || "";
    const from = $os.getenv("TWILIO_PHONE_NUMBER") || $os.getenv("TWILIO_FROM") || "";
    if (!sid || !auth || !from) return false;
    try {
      const res = $http.send({
        url: "https://api.twilio.com/2010-04-01/Accounts/" + sid + "/Messages.json",
        method: "POST",
        headers: {
          "Authorization": "Basic " + b64(sid + ":" + auth),
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: "From=" + encodeURIComponent(from) + "&To=" + encodeURIComponent(to)
          + "&Body=" + encodeURIComponent(text),
        timeout: 15,
      });
      return res.statusCode >= 200 && res.statusCode < 300;
    } catch (_) { return false; }
  };

  const sendEmail = (to, subject, text) => {
    const rk = $os.getenv("RESEND_API_KEY") || "";
    if (!rk) return false;
    try {
      const res = $http.send({
        url: "https://api.resend.com/emails",
        method: "POST",
        headers: { "Authorization": "Bearer " + rk, "Content-Type": "application/json" },
        body: JSON.stringify({
          from: "Anticipy HQ <notifications@aevoy.com>",
          to: [to], subject: subject, text: text,
        }),
        timeout: 15,
      });
      return res.statusCode >= 200 && res.statusCode < 300;
    } catch (_) { return false; }
  };

  const logAct = (action, subject, ref) => {
    try {
      const act = new Record($app.findCollectionByNameOrId("internal_activity"));
      act.set("actor", ""); act.set("actor_name", "HQ");
      act.set("action", action); act.set("subject", subject); act.set("ref", ref || "");
      $app.save(act);
    } catch (_) {}
  };

  const recipientsOf = (todo) => {
    let ids = [];
    try { ids = JSON.parse(todo.getString("assignees") || "[]") || []; } catch (_) {}
    if (!ids.length && todo.getString("created_by")) ids = [todo.getString("created_by")];
    const out = [];
    for (const id of ids) {
      try {
        const p = $app.findRecordById("internal_people", id);
        if (p.get("active")) out.push(p);
      } catch (_) {}
    }
    return out;
  };

  const nowISO = new Date().toISOString();

  // ---- reminders ----
  let due = [];
  try {
    due = $app.findRecordsByFilter("internal_todos",
      "status = 'open' && remind_at != '' && remind_at <= {:now} && remind_sent_at = ''",
      "+remind_at", 20, 0, { now: nowISO });
  } catch (err) { console.log("internal_hq: reminder query failed: " + err); }
  for (const todo of due) {
    try {
      todo.set("remind_sent_at", nowISO);       // the claim — before any send
      $app.save(todo);
      const channel = todo.getString("remind_channel") || "email";
      const title = todo.getString("title");
      const dueDate = todo.getString("due");
      const text = "Reminder from Anticipy HQ: " + title
        + (dueDate ? " (due " + dueDate + ")" : "");
      let anySent = false;
      for (const p of recipientsOf(todo)) {
        if ((channel === "email" || channel === "both") && p.getString("email")) {
          if (sendEmail(p.getString("email"), "Reminder: " + title.slice(0, 120), text)) anySent = true;
        }
        if ((channel === "sms" || channel === "both") && p.getString("phone")) {
          if (sendSMS(p.getString("phone"), text.slice(0, 300))) anySent = true;
        }
      }
      if (anySent) {
        if (todo.get("remind_attempts")) { todo.set("remind_attempts", 0); $app.save(todo); }
        logAct("reminder.sent", "Reminder went out for “" + title.slice(0, 80) + "”", todo.get("id"));
      } else {
        // Every channel failed. A blip deserves another go; a permanently
        // unreachable recipient must NOT retry forever — that is a real
        // Twilio/Resend call and a reminder.failed row every 5 minutes until
        // someone notices. Two more tries, then give up and say so once.
        const tries = (todo.get("remind_attempts") || 0) + 1;
        todo.set("remind_attempts", tries);
        if (tries >= REMIND_MAX_TRIES) {
          // Keep the claim stamped: this is the give-up, not a delivery.
          $app.save(todo);
          logAct("reminder.gave_up", "Gave up reminding about “" + title.slice(0, 80)
            + "” after " + tries + " tries — check the contact details", todo.get("id"));
        } else {
          todo.set("remind_sent_at", "");        // roll the claim back — retry next sweep
          $app.save(todo);
          logAct("reminder.failed", "Reminder for “" + title.slice(0, 80)
            + "” could not be delivered (try " + tries + " of " + REMIND_MAX_TRIES + ")", todo.get("id"));
        }
      }
    } catch (err) { console.log("internal_hq: reminder send failed: " + err); }
  }

  // ---- follow-ups: one nudge, ever, 2 days past due ----
  const cutoff = new Date(Date.now() - 2 * 24 * 3600 * 1000).toISOString().slice(0, 10);
  let late = [];
  try {
    late = $app.findRecordsByFilter("internal_todos",
      "status = 'open' && due != '' && due <= {:cut} && followup_sent_at = ''",
      "+due", 10, 0, { cut: cutoff });
  } catch (err) { console.log("internal_hq: followup query failed: " + err); }
  for (const todo of late) {
    try {
      todo.set("followup_sent_at", nowISO);
      $app.save(todo);
      const title = todo.getString("title");
      const text = "Still open, past due: " + title + " (was due " + todo.getString("due") + ") — Anticipy HQ";
      let anySent = false;
      for (const p of recipientsOf(todo)) {
        if (p.getString("email")) { if (sendEmail(p.getString("email"), "Past due: " + title.slice(0, 120), text)) anySent = true; }
        else if (p.getString("phone")) { if (sendSMS(p.getString("phone"), text.slice(0, 300))) anySent = true; }
      }
      if (anySent) logAct("followup.sent", "Nudged about “" + title.slice(0, 80) + "” (past due)", todo.get("id"));
    } catch (err) { console.log("internal_hq: followup failed: " + err); }
  }

  // ---- PASS C: internal_reminders — the ones remind_at cannot express -----
  //
  // todo.remind_at above is the one-shot bell and it keeps working untouched.
  // This pass exists because "one hour before" and "daily until done" are two
  // reminders on one task, and one column cannot hold two times.
  //
  // Same claim-first-then-send discipline as Pass A, for the same reason and
  // not a weaker version of it: this cron refires every five minutes forever,
  // so send-first with a failed persist is unbounded duplicate texts. The
  // stamp rolls back only when EVERY channel failed, and after three goes it
  // stays stamped and logs the give-up, because a permanently wrong phone
  // number must not generate a real Twilio call every five minutes until
  // somebody happens to look.
  let rems = [];
  try {
    rems = $app.findRecordsByFilter("internal_reminders",
      "sent_at = '' && fire_at != '' && fire_at <= {:now}",
      "+fire_at", 20, 0, { now: nowISO });
  } catch (err) { console.log("internal_hq: reminder-row query failed: " + err); }
  for (const rem of rems) {
    try {
      let todo = null;
      try { todo = $app.findRecordById("internal_todos", rem.getString("todo")); } catch (_) {}
      // The task is gone or finished: retire the reminder quietly. Firing a
      // bell about a task nobody can open is worse than silence.
      if (!todo || todo.getString("status") !== "open") {
        rem.set("sent_at", nowISO); $app.save(rem);
        continue;
      }
      rem.set("sent_at", nowISO);            // the claim — before any send
      $app.save(rem);

      const channel = rem.getString("channel") || "inapp";
      const title = todo.getString("title");
      const label = rem.getString("label") || "Reminder";
      const text = label + ": " + title
        + (todo.getString("due") ? " (due " + todo.getString("due")
          + (todo.getString("due_time") ? " " + todo.getString("due_time") : "") + ")" : "")
        + " — Anticipy HQ";

      // person = "" means every recipient of the todo, which is exactly the
      // rule Pass A already uses. One definition of "who does this reach".
      let people = [];
      if (rem.getString("person")) {
        try {
          const p = $app.findRecordById("internal_people", rem.getString("person"));
          if (p.get("active")) people = [p];
        } catch (_) {}
      } else {
        people = recipientsOf(todo);
      }

      let anySent = false;
      for (const p of people) {
        // An in-app reminder is a row in the tray, not a send. It always
        // "succeeds", which is why it never touches the retry budget below.
        if (channel === "inapp") {
          try {
            const n = new Record($app.findCollectionByNameOrId("internal_notifs"));
            n.set("person", p.get("id")); n.set("kind", "deadline");
            n.set("text", label); n.set("sub", title.slice(0, 300));
            n.set("todo", todo.get("id")); n.set("actor", "");
            n.set("read", false); n.set("emailed_at", nowISO); n.set("smsed_at", nowISO);
            $app.save(n);
            anySent = true;
          } catch (_) {}
          continue;
        }
        if ((channel === "email" || channel === "both") && p.getString("email") && p.get("email_on") !== false) {
          if (sendEmail(p.getString("email"), label + ": " + title.slice(0, 120), text)) anySent = true;
        }
        if ((channel === "sms" || channel === "both") && p.getString("phone") && p.get("sms_on") !== false) {
          if (sendSMS(p.getString("phone"), text.slice(0, 300))) anySent = true;
        }
      }
      if (anySent) {
        logAct("reminder.sent", "Reminder went out for “" + title.slice(0, 80) + "”", todo.get("id"));
        // The one rule that comes back. Everything else is spent once; this
        // one re-arms for tomorrow and keeps re-arming until the task leaves
        // status='open', which the top of this loop checks before it sends.
        // Re-armed AFTER a successful send, never before — otherwise a rule
        // that can never be delivered walks its fire_at forward forever and
        // the give-up counter below never gets a chance to run.
        if (rem.getString("rule") === "daily_until_done") {
          try {
            rem.set("fire_at", new Date(Date.now() + 86400000).toISOString());
            rem.set("sent_at", ""); rem.set("attempts", 0);
            $app.save(rem);
          } catch (_) {}
        }
      } else {
        const tries = (Number(rem.get("attempts")) || 0) + 1;
        rem.set("attempts", tries);
        if (tries >= REMIND_MAX_TRIES) {
          $app.save(rem);                    // keep the claim: this is the give-up
          logAct("reminder.gave_up", "Gave up reminding about “" + title.slice(0, 80)
            + "” after " + tries + " tries — check the contact details", todo.get("id"));
        } else {
          rem.set("sent_at", "");            // roll back — retry next sweep
          $app.save(rem);
          logAct("reminder.failed", "Reminder for “" + title.slice(0, 80)
            + "” could not be delivered (try " + tries + " of " + REMIND_MAX_TRIES + ")", todo.get("id"));
        }
      }
    } catch (err) { console.log("internal_hq: scheduled reminder failed: " + err); }
  }

  // ---- PASS D: the notification digest ------------------------------------
  //
  // ONE MESSAGE PER PERSON PER SWEEP, never one per event. Three comments on a
  // task inside a minute is one email that says three things, not three emails.
  //
  // The ten-minute settle is what makes that true: a notification is not
  // eligible until it has sat unread for ten minutes, so a burst of activity
  // collects into a single digest instead of racing the first one out the door.
  //
  // The filter is on read/emailed_at only and the age is checked in JS. Not
  // laziness: `created` is an autodate and PocketBase writes it as
  // "2026-08-22 04:11:34.880Z", so comparing it against a JS toISOString()
  // with its T separator is the exact shape of bug that has already produced
  // NaN and a permanently jammed queue in this file. Reading the value and
  // parsing it with the same both-shapes rule everything else here uses
  // removes the question.
  const SETTLE_MS = 10 * 60 * 1000;
  let pending = [];
  try {
    pending = $app.findRecordsByFilter("internal_notifs",
      "read = false && emailed_at = ''", "+created", 200, 0);
  } catch (err) { console.log("internal_hq: notif digest query failed: " + err); }

  const byPerson = {};
  for (const n of pending) {
    const born = pbTime(n.getString("created"));
    if (isNaN(born) || Date.now() - born < SETTLE_MS) continue;
    const pid = n.getString("person");
    if (!pid) continue;
    if (!byPerson[pid]) byPerson[pid] = [];
    if (byPerson[pid].length < 20) byPerson[pid].push(n);
  }

  for (const pid in byPerson) {
    try {
      const rows = byPerson[pid];
      let person = null;
      try { person = $app.findRecordById("internal_people", pid); } catch (_) {}
      // No person, or a deactivated one: stamp the batch so it stops being
      // reconsidered every five minutes forever, and send nothing.
      if (!person || !person.get("active")) {
        for (const n of rows) { try { n.set("emailed_at", nowISO); n.set("smsed_at", nowISO); $app.save(n); } catch (_) {} }
        continue;
      }
      const pref = person.getString("remind_pref") || "inapp";
      const wantEmail = (pref === "email" || pref === "both") && person.get("email_on") !== false && !!person.getString("email");
      const wantSMS = (pref === "sms" || pref === "both") && person.get("sms_on") !== false && !!person.getString("phone");

      // THE CLAIM, ON EVERY ROW IN THE BATCH, BEFORE ANY SEND. If the process
      // dies between here and the Resend call, the person misses one digest —
      // and every one of these events is still sitting in their tray, unread,
      // where they will see it. If it were the other way round they would get
      // the same text every five minutes until somebody restarted the backend.
      for (const n of rows) {
        try { n.set("emailed_at", nowISO); if (wantSMS) n.set("smsed_at", nowISO); $app.save(n); } catch (_) {}
      }
      // "in-app only" is a real answer, not a failure. The rows are stamped
      // above so this person's tray fills and their phone stays quiet.
      if (!wantEmail && !wantSMS) continue;

      const lines = [];
      for (const n of rows) {
        lines.push("• " + n.getString("text") + (n.getString("sub") ? " — " + n.getString("sub") : ""));
      }
      const count = rows.length;
      const subject = count + (count === 1 ? " update" : " updates") + " in Anticipy HQ";
      // text/, not html/. A comment body is whatever somebody typed, and the
      // only safe thing to do with it at this boundary is send it as text so
      // no mail client is ever asked to parse it as markup.
      const bodyText = lines.join("\n") + "\n\nOpen HQ: https://www.anticipy.ai/hq";
      if (wantEmail) sendEmail(person.getString("email"), subject, bodyText);
      if (wantSMS) {
        const head = lines.slice(0, 2).join("\n");
        const rest = count - Math.min(2, count);
        sendSMS(person.getString("phone"),
          (head + (rest > 0 ? "\n…and " + rest + " more." : "") + "\nanticipy.ai/hq").slice(0, 300));
      }
      logAct("digest.sent", "Sent " + person.getString("name") + " a digest of "
        + count + (count === 1 ? " update" : " updates"), "");
    } catch (err) { console.log("internal_hq: digest failed: " + err); }
  }

  // ---- research slot backstop ----
  try {
    const meter = $app.findFirstRecordByFilter("internal_meter", "name = 'research'");
    const liveId = meter.getString("live_job_id");
    if (liveId) {
      let clear = false;
      try {
        const j = $app.findRecordById("jobs", liveId);
        const s = j.getString("status");
        if (s === "done" || s === "failed" || s === "cancelled") clear = true;
        else {
          // PocketBase 0.30.4 already ends its datetimes with Z:
          // "2026-08-22 04:11:34.880Z". The old line replaced the space and
          // then appended a SECOND Z, producing "…04:11:34.880ZZ" -> Invalid
          // Date -> NaN. isNaN(NaN) is true, so this branch could never fire
          // and the backstop never cleared anything: one worker dying
          // mid-research pinned the single slot forever, and every later
          // "run it here" answered 409 "a research task is already running"
          // until someone restarted the backend. Parse both shapes.
          const upd = pbTime(j.getString("updated"));
          if (!isNaN(upd) && Date.now() - upd > 30 * 60 * 1000) clear = true;
        }
      } catch (_) { clear = true; }
      if (clear) { meter.set("live_job_id", ""); $app.save(meter); }
    }
  } catch (_) {}

  // ---- REPEAT MOTOR --------------------------------------------------------
  // repeat_rule was stored and validated since hq_v2 but nothing ever acted
  // on it — a stored intention with no motor. Now it runs: for every series
  // (title+track+rule), once the latest instance's due date is behind the
  // local calendar, the sweep lays down the next occurrence. Completion does
  // NOT stop a series — "on his calendar every day" means every day, done or
  // not. To end a series, set its repeat to none (or delete the instances).
  //
  // "Local" is a fixed UTC-8: this VM has no timezone database (see the
  // reminders note), and for a day-granular generator the only cost of
  // ignoring DST is that new items appear at 1am Vancouver in summer
  // instead of midnight. Missed cycles are not backfilled — after downtime
  // the series resumes at the most recent scheduled date, one item, not a
  // pile of stale ones.
  try {
    const dayMs = 86400000;
    const localToday = new Date(Date.now() - 480 * 60000).toISOString().slice(0, 10);
    const parseDay = (v) => Date.parse(String(v).slice(0, 10) + "T00:00:00Z");
    const fmtDay = (ms) => new Date(ms).toISOString().slice(0, 10);
    const DOW = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
    // due date (ms) -> next scheduled date (ms) under a rule
    const nextAfter = (rule, dueMs) => {
      if (rule === "daily") return dueMs + dayMs;
      if (rule.indexOf("every:") === 0) {
        const n = parseInt(rule.slice(6), 10);
        return (n >= 2 && n <= 29) ? dueMs + n * dayMs : NaN;
      }
      if (rule === "weekdays") {
        let t = dueMs + dayMs;
        while ([0, 6].indexOf(new Date(t).getUTCDay()) >= 0) t += dayMs;
        return t;
      }
      if (rule === "weekly") return dueMs + 7 * dayMs;
      if (rule.indexOf("weekly:") === 0) {
        const want = DOW[rule.slice(7)];
        if (want === undefined) return NaN;
        let t = dueMs + dayMs;
        while (new Date(t).getUTCDay() !== want) t += dayMs;
        return t;
      }
      if (rule === "monthly") {
        const d = new Date(dueMs);
        const day = d.getUTCDate();
        const n = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1));
        const last = new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth() + 1, 0)).getUTCDate();
        n.setUTCDate(Math.min(day, last));
        return n.getTime();
      }
      return NaN;
    };
    const todayMs = parseDay(localToday);
    const reps = $app.findRecordsByFilter("internal_todos",
      "repeat_rule != '' && repeat_rule != 'none' && due != ''", "-due", 500, 0);
    // one row per series: the instance with the greatest due carries the torch
    const latest = {};
    for (const t of reps) {
      const k = t.getString("title") + "|" + t.getString("track") + "|" + t.getString("repeat_rule");
      if (!latest[k] || t.getString("due") > latest[k].getString("due")) latest[k] = t;
    }
    let made = 0;
    for (const k in latest) {
      const t = latest[k];
      const dueMs = parseDay(t.getString("due"));
      if (isNaN(dueMs)) continue;
      let next = nextAfter(t.getString("repeat_rule"), dueMs);
      if (isNaN(next) || next > todayMs) continue;
      // resume at the most recent scheduled date <= today (no backfill pile)
      let guard = 0;
      while (guard++ < 400) {
        const peek = nextAfter(t.getString("repeat_rule"), next);
        if (isNaN(peek) || peek > todayMs) break;
        next = peek;
      }
      const nextStr = fmtDay(next);
      try {
        $app.findFirstRecordByFilter("internal_todos",
          "title = {:ti} && track = {:tr} && due = {:du}",
          { ti: t.getString("title"), tr: t.getString("track"), du: nextStr });
        continue; // already laid down
      } catch (_) {}
      try {
        const r = new Record($app.findCollectionByNameOrId("internal_todos"));
        r.set("title", t.getString("title")); r.set("notes", t.getString("notes"));
        r.set("track", t.getString("track")); r.set("assignees", t.getString("assignees"));
        r.set("watchers", t.getString("watchers")); r.set("priority", t.getString("priority") || "normal");
        r.set("stage", "todo"); r.set("status", "open");
        r.set("due", nextStr); r.set("due_time", t.getString("due_time"));
        r.set("repeat_rule", t.getString("repeat_rule"));
        r.set("created_by", t.getString("created_by"));
        // subtasks come along with their checkmarks wiped — a fresh day
        let subs = [];
        try { subs = (JSON.parse(t.getString("subtasks") || "[]") || []).map((x) => ({ t: x.t, done: false })); } catch (_) {}
        r.set("subtasks", JSON.stringify(subs));
        // a reminder rides forward by the same distance the due date moved
        const ra = t.getString("remind_at");
        if (ra) {
          const raMs = Date.parse(ra.replace(" ", "T").replace(/([^Zz])$/, "$1Z"));
          if (!isNaN(raMs)) {
            r.set("remind_at", new Date(raMs + (next - dueMs)).toISOString().slice(0, 16));
            r.set("remind_channel", t.getString("remind_channel") || "email");
          }
        }
        r.set("remind_sent_at", ""); r.set("followup_sent_at", ""); r.set("remind_attempts", 0);
        r.set("cmt_count", 0); r.set("attachments", "[]"); r.set("hold_reason", "");
        $app.save(r);
        made++;
      } catch (err) { console.log("internal_hq: repeat motor could not lay down '" + t.getString("title") + "': " + err); }
    }
    if (made > 0) {
      try {
        const act = new Record($app.findCollectionByNameOrId("internal_activity"));
        act.set("actor", ""); act.set("actor_name", "HQ");
        act.set("action", "repeat.laydown");
        act.set("subject", "Laid down " + made + " repeating task" + (made === 1 ? "" : "s") + " for " + localToday);
        act.set("ref", "");
        $app.save(act);
      } catch (_) {}
    }
  } catch (err) { console.log("internal_hq: repeat motor failed (never blocking): " + err); }
});

// --------------------------------------------------------------------------
// CRON: nightly activity prune. The audit ledger once filled the 5GB volume;
// this feed never gets the chance.
// --------------------------------------------------------------------------
cronAdd("internal_hq_prune", "17 4 * * *", () => {
  const cutoff = new Date(Date.now() - 60 * 24 * 3600 * 1000).toISOString();
  try {
    const old = $app.findRecordsByFilter("internal_activity",
      "created <= {:cut}", "+created", 200, 0, { cut: cutoff });
    for (const r of old) { try { $app.delete(r); } catch (_) {} }
  } catch (err) { console.log("internal_hq: prune failed: " + err); }

  // Everything v2 added that grows without a ceiling gets pruned in the same
  // pass, for the same reason the activity ledger did: this volume has been
  // filled once already, and a full disk takes the reminders down with it.
  const nowISO = new Date().toISOString();

  // Expired sessions. They are already refused on every request — the
  // dual-auth block re-parses `expires` each time — so this is housekeeping,
  // not a security control, and it must not be mistaken for one.
  try {
    const dead = $app.findRecordsByFilter("internal_sessions",
      "expires != '' && expires <= {:now}", "+expires", 200, 0, { now: nowISO });
    for (const s of dead) { try { $app.delete(s); } catch (_) {} }
  } catch (_) {}

  // Read notifications older than 30 days. UNREAD ROWS ARE NEVER PRUNED, at
  // any age: a thing somebody was told and has not seen yet is the one row in
  // this collection that still has a job to do.
  try {
    const cut30 = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();
    const seen = $app.findRecordsByFilter("internal_notifs",
      "read = true && created <= {:cut}", "+created", 200, 0, { cut: cut30 });
    for (const n of seen) { try { $app.delete(n); } catch (_) {} }
  } catch (_) {}

  // Spent reminders older than 30 days. A live one (sent_at = '') is left
  // alone however far in the future it points.
  try {
    const cut30 = new Date(Date.now() - 30 * 24 * 3600 * 1000).toISOString();
    const spent = $app.findRecordsByFilter("internal_reminders",
      "sent_at != '' && sent_at <= {:cut}", "+sent_at", 200, 0, { cut: cut30 });
    for (const r of spent) { try { $app.delete(r); } catch (_) {} }
  } catch (_) {}
});

// ==========================================================================
// HQ v2 — sessions, per-person login codes, comments, reminders,
// notifications, project deletion, team settings, and the front door.
//
// EVERY handler below redeclares every helper it uses. Nothing here can see
// anything declared above it, including the auth block, including sha256.
// That is not style: a const at file top level is invisible inside a
// routerAdd callback in this runtime, and the failure is a 500 on one route,
// in production only, after it worked fine when you read it.
//
// THE DUAL-AUTH RULE, stated once and implemented separately in each handler:
//   - X-HQ-Session present  -> the session decides who the actor is, and
//                              body.actor_id is IGNORED. A real session may
//                              never impersonate.
//   - no session            -> X-Internal-Key, and the actor is whoever the
//                              client says it is. That is the founder's
//                              explicit v1 call and it stays visible in the
//                              activity feed. It is not quietly improved into
//                              something that looks like auth.
//   - a session that does not resolve -> 401 {reauth:true}. NEVER a fall
//                              through to the key branch: an expired token
//                              must sign you out, not silently demote you.
// Every route that existed before this block keeps the plain key check it had.
// ==========================================================================

// --------------------------------------------------------------------------
// POST /internal/session — exchange a login code for a session token.
// No auth: the code IS the credential. This is the one new security surface
// in the file, so every choice below says what it stops.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/session", (e) => {
  // 503 when the key is unset even though this route does not check the key.
  // STOPS: a half-configured deploy leaving one door open in an area every
  // other door has shut. The area is shut or it is not; it is not partly shut.
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}

  // ONE SENTENCE FOR EVERY FAILURE. Wrong code, revoked code, deactivated
  // person, tripped ceiling — all of it answers exactly this.
  // STOPS: the login screen becoming an oracle. Different messages would tell
  // a stranger whether a code exists, whether the person is still on the team,
  // and whether they are being rate limited — three facts they can only use.
  const no = () => e.json(200, { ok: false,
    message: "That code didn't match anyone. Check it and try again." });

  // Normalise the way Crockford intended: case-insensitive, separators are
  // decoration, and the four ambiguous glyphs fold onto what they look like.
  // STOPS: an unreadable failure. Codes get read aloud and typed by hand; if
  // O-for-0 produced the same sentence as a revoked code, nobody could ever
  // tell a typo from a real problem, and the identical-message rule above
  // would become a trap instead of a defence.
  const raw = String(body.code || "").toUpperCase().replace(/[^A-Z0-9]/g, "")
    .replace(/I/g, "1").replace(/L/g, "1").replace(/O/g, "0").replace(/U/g, "V");
  if (raw.length !== 8) return no();

  // GLOBAL HOURLY CEILING, COUNTED ON THE ATTEMPT, BEFORE THE COMPARISON.
  // STOPS: online brute force. Global rather than per-IP because an attacker
  // rotates addresses and a three-person team never reaches forty tries in an
  // hour; counted before the compare so a miss costs exactly what a hit does.
  const hourNow = new Date().toISOString().slice(0, 13);
  const ceiling = parseInt($os.getenv("ANTICIPY_HQ_LOGIN_CEILING") || "40", 10);
  let meter = null;
  try { meter = e.app.findFirstRecordByFilter("internal_meter", "name = 'login'"); } catch (_) {}
  if (!meter) {
    // The seed row is missing. Create it rather than skipping the ceiling:
    // a brute-force guard that silently stops counting is worse than none,
    // because everything downstream keeps reporting that it is guarded.
    try {
      meter = new Record(e.app.findCollectionByNameOrId("internal_meter"));
      meter.set("name", "login"); meter.set("hour", hourNow); meter.set("calls", 0);
      meter.set("live_job_id", "");
      e.app.save(meter);
    } catch (_) { return no(); }   // cannot count -> refuse. Fail closed.
  }
  try {
    const used = meter.getString("hour") === hourNow ? (Number(meter.get("calls")) || 0) : 0;
    if (used >= ceiling) return no();
    meter.set("hour", hourNow); meter.set("calls", used + 1);
    e.app.save(meter);
  } catch (_) { return no(); }

  // Look the person up BY HASH, and compare with $security.equal anyway.
  // STOPS: two things. Storing only sha256 means a database dump — and this
  // one is backed up nightly — is not a pile of live credentials, and there is
  // deliberately no route in this file that can read a code back out. The
  // timing-safe compare stops a byte-at-a-time timing oracle against the hash.
  let person = null;
  try {
    person = e.app.findFirstRecordByFilter("internal_people",
      "code_hash = {:h}", { h: sha256(raw) });
  } catch (_) {}
  if (!person) return no();
  if (!$security.equal(sha256(raw), person.getString("code_hash"))) return no();
  if (!person.get("active")) return no();

  // 64 hex characters, stored as sha256, thirty days.
  // STOPS: the same dump problem one level down — a stolen backup is not a
  // stolen session either. The expiry bounds how long a token found on an old
  // laptop is worth anything.
  const token = $security.randomStringWithAlphabet(64, "0123456789abcdef");
  const nowISO = new Date().toISOString();
  const expires = new Date(Date.now() + 30 * 86400000).toISOString();
  let ip = "";
  try {
    const xff = String(e.request.header.get("X-Forwarded-For") || "");
    if (xff) ip = xff.split(",")[0].trim();
  } catch (_) {}
  if (!ip) { try { ip = e.realIP() || ""; } catch (_) {} }
  try {
    const s = new Record(e.app.findCollectionByNameOrId("internal_sessions"));
    s.set("person", person.get("id"));
    s.set("token_hash", sha256(token));
    s.set("expires", expires);
    s.set("ip", String(ip).slice(0, 60));
    s.set("ua", String(e.request.header.get("User-Agent") || "").slice(0, 200));
    e.app.save(s);
  } catch (_) { return no(); }

  // Keep the last ten sign-ins per person and drop the rest. The collection
  // doubles as "Who's been in lately"; ten answers that question and stops it
  // growing without bound the way internal_activity once filled the volume.
  try {
    const mine = e.app.findRecordsByFilter("internal_sessions",
      "person = {:p}", "-created", 60, 0, { p: person.get("id") });
    for (let i = 10; i < mine.length; i++) { try { e.app.delete(mine[i]); } catch (_) {} }
  } catch (_) {}

  const first = !person.getString("last_in");
  try { person.set("last_in", nowISO); e.app.save(person); } catch (_) {}
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", person.get("id")); act.set("actor_name", person.getString("name"));
    act.set("action", "person.signin");
    // The admin's confirmation that a code landed, and it costs one row.
    act.set("subject", person.getString("name") + (first ? " signed in for the first time" : " signed in"));
    act.set("verb", first ? "signed in for the first time" : "signed in");
    act.set("ref", person.get("id"));
    e.app.save(act);
  } catch (_) {}

  return e.json(200, { ok: true, token: token, expires: expires, person: {
    id: person.get("id"), name: person.getString("name"),
    is_admin: !!person.get("is_admin"), role: person.getString("role"),
    focus: person.getString("focus"), tz: person.getString("tz"),
    remind_pref: person.getString("remind_pref") || "inapp",
    email_on: person.get("email_on") !== false, sms_on: person.get("sms_on") !== false,
  } });
});

// --------------------------------------------------------------------------
// POST /internal/session/end — "Sign out". Deletes the row, not the code.
// --------------------------------------------------------------------------
// --------------------------------------------------------------------------
// POST /internal/clerk/exchange — trade a verified Clerk sign-in for the HQ
// session everything else already speaks.
//
// WHY AN EXCHANGE AND NOT CLERK EVERYWHERE: fourteen handlers accept
// X-HQ-Session, each with its own inline copy of the check because of JSVM
// isolation. Teaching Clerk to all fourteen means fourteen edits per future
// change, and a Clerk outage would take down every request in flight. One
// exchange at the door means the rest of the file does not know Clerk exists,
// and an outage only stops NEW sign-ins.
//
// HOW VERIFICATION WORKS, and why it is HS256 rather than Clerk's default:
// the JSVM cannot check an RS256 signature, and Clerk's server-side verify
// endpoint answers 410 (deprecated, tried on 2026-08-23). So the page asks
// Clerk for a token minted from the "hq" JWT TEMPLATE — HS256, signed with a
// key only Clerk and this backend hold (CLERK_HQ_JWT_KEY), 60-second life,
// carrying the user's email as a claim. $security.parseJWT checks the
// signature and expiry right here. No Clerk API call, nothing deprecated,
// and the email comes from Clerk's signature rather than from the client.
//
// WHO GETS IN: that email must match an ACTIVE row in internal_people,
// case-insensitively. Signing up to Clerk is open to the world; membership
// of HQ is decided by the People page — this route is the wall between
// those two facts.
// --------------------------------------------------------------------------
// GET /internal/cal/{token}.ics — "Integrate with your calendars", the half
// that works TODAY with zero OAuth: a per-person feed any calendar app can
// subscribe to (Google: "From URL"; Apple/Outlook: subscribe). Carries the
// person's open dated tasks plus every team event, as all-day entries.
//
// AUTH IS THE TOKEN ITSELF: sha256(teamKey + personId). Deterministic on
// purpose — no new column, no minting flow, and rotating the team key
// revokes every feed at once. The cost, stated honestly: a leaked feed URL
// stays valid until the key rotates. For a three-person team whose feed
// contains task titles, that trade is taken knowingly.
//
// Served from the Railway origin directly (the page prints that URL) because
// the anticipy.ai edge sits behind the passcode gate and Google's fetcher
// will never have the cookie.
// ==========================================================================
// EXPENSES — one table, two lenses. Rows carry the person; the page shows
// "Mine" and "Company" as filters over the same honest data.
// ==========================================================================
routerAdd("POST", "/internal/expenses", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); } catch (_) {}
  if (!actor || !actor.get("active")) return e.json(400, { error: "pick yourself first" });

  const title = String(body.title || "").trim().slice(0, 200);
  if (!title) return e.json(400, { error: "what was the expense for?" });
  const amount = Math.round(Number(body.amount) * 100) / 100;
  if (!isFinite(amount) || amount <= 0) return e.json(400, { error: "amount has to be a positive number" });
  const cur = ["CAD", "USD"].indexOf(String(body.currency || "").toUpperCase()) >= 0
    ? String(body.currency).toUpperCase() : "CAD";
  const date = String(body.date || "").trim();
  if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) return e.json(400, { error: "date should be YYYY-MM-DD" });

  try {
    const r = new Record(e.app.findCollectionByNameOrId("internal_expenses"));
    r.set("title", title); r.set("amount", amount); r.set("currency", cur);
    r.set("date", date || new Date().toISOString().slice(0, 10));
    r.set("track", String(body.track || "").slice(0, 32));
    r.set("person", actor.get("id")); r.set("created_by", actor.get("id"));
    e.app.save(r);
    return e.json(200, { ok: true, id: r.get("id") });
  } catch (_) { return e.json(500, { error: "could not save the expense" }); }
});

routerAdd("POST", "/internal/expenses/delete", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); } catch (_) {}
  if (!actor || !actor.get("active")) return e.json(400, { error: "pick yourself first" });
  let row = null;
  try { row = e.app.findRecordById("internal_expenses", String(body.expense_id || "")); } catch (_) {}
  if (!row) return e.json(404, { error: "that expense is already gone" });
  // Your own expenses, or an admin's broom. Same shape as task deletion.
  if (row.getString("created_by") !== actor.get("id") && !actor.get("is_admin")) {
    return e.json(403, { error: "only whoever logged it (or an admin) can delete it" });
  }
  try { e.app.delete(row); } catch (_) {}
  return e.json(200, { ok: true });
});

// ==========================================================================
// VAULT — company logins for tools. secret_enc is AES via $security.encrypt
// keyed from the environment; plaintext exists only in a reveal response to
// a signed-in teammate, never in the database and never in /internal/state.
// ==========================================================================
routerAdd("POST", "/internal/passwords", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const vk = $os.getenv("ANTICIPY_VAULT_KEY") || "";
  if (vk.length !== 32) return e.json(503, { error: "the vault is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); } catch (_) {}
  if (!actor || !actor.get("active")) return e.json(400, { error: "pick yourself first" });

  let row = null;
  if (body.password_id) {
    try { row = e.app.findRecordById("internal_passwords", String(body.password_id)); } catch (_) {}
    if (!row) return e.json(404, { error: "that entry is gone" });
  } else {
    const service = String(body.service || "").trim();
    if (!service) return e.json(400, { error: "which tool is this for?" });
    row = new Record(e.app.findCollectionByNameOrId("internal_passwords"));
  }
  if ("service" in body)  row.set("service",  String(body.service  || "").trim().slice(0, 120));
  if ("username" in body) row.set("username", String(body.username || "").trim().slice(0, 200));
  if ("url" in body)      row.set("url",      String(body.url      || "").trim().slice(0, 500));
  if ("notes" in body)    row.set("notes",    String(body.notes    || "").slice(0, 2000));
  if ("secret" in body && String(body.secret || "") !== "") {
    // Absent or empty secret on an update means "keep what's there" — an
    // edit to fix a typo in the URL must never blank the password.
    try { row.set("secret_enc", $security.encrypt(String(body.secret).slice(0, 500), vk)); }
    catch (_) { return e.json(500, { error: "could not encrypt that" }); }
  }
  row.set("updated_by", actor.get("id"));
  try { e.app.save(row); } catch (_) { return e.json(500, { error: "could not save" }); }
  return e.json(200, { ok: true, id: row.get("id") });
});

routerAdd("POST", "/internal/passwords/reveal", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const vk = $os.getenv("ANTICIPY_VAULT_KEY") || "";
  if (vk.length !== 32) return e.json(503, { error: "the vault is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); } catch (_) {}
  if (!actor || !actor.get("active")) return e.json(400, { error: "pick yourself first" });
  let row = null;
  try { row = e.app.findRecordById("internal_passwords", String(body.password_id || "")); } catch (_) {}
  if (!row) return e.json(404, { error: "that entry is gone" });
  let plain = "";
  try { plain = $security.decrypt(row.getString("secret_enc"), vk); } catch (_) {
    return e.json(500, { error: "could not decrypt — was the vault key rotated?" });
  }
  return e.json(200, { ok: true, secret: plain });
});

routerAdd("POST", "/internal/passwords/delete", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); } catch (_) {}
  if (!actor || !actor.get("active")) return e.json(400, { error: "pick yourself first" });
  let row = null;
  try { row = e.app.findRecordById("internal_passwords", String(body.password_id || "")); } catch (_) {}
  if (!row) return e.json(404, { error: "already gone" });
  try { e.app.delete(row); } catch (_) {}
  return e.json(200, { ok: true });
});

// ==========================================================================
// NOTES — one shared notebook for the team. Anyone edits (updated_by says
// who touched it last); deleting stays with the creator or an admin.
// ==========================================================================
routerAdd("POST", "/internal/notes", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); } catch (_) {}
  if (!actor || !actor.get("active")) return e.json(400, { error: "pick yourself first" });

  let row = null;
  if (body.note_id) {
    try { row = e.app.findRecordById("internal_notes", String(body.note_id)); } catch (_) {}
    if (!row) return e.json(404, { error: "that note is gone" });
  } else {
    row = new Record(e.app.findCollectionByNameOrId("internal_notes"));
    row.set("created_by", actor.get("id"));
  }
  if ("title" in body) row.set("title", String(body.title || "").trim().slice(0, 200));
  if ("body" in body)  row.set("body",  String(body.body  || "").slice(0, 50000));
  if ("track" in body) row.set("track", String(body.track || "").slice(0, 32));
  if (!row.getString("title") && !row.getString("body")) {
    return e.json(400, { error: "an empty note isn't worth keeping" });
  }
  row.set("updated_by", actor.get("id"));
  try { e.app.save(row); } catch (_) { return e.json(500, { error: "could not save the note" }); }
  return e.json(200, { ok: true, id: row.get("id") });
});

routerAdd("POST", "/internal/notes/delete", (e) => {
  // ------------------------------------------------------------------
  // SESSION DOOR, added 2026-08-23. This handler predates personal
  // sessions and only knew the team key — which meant a Clerk or
  // code sign-in could read the board but got "wrong key" the moment
  // they tried to create anything. Found live: Omar, signed in through
  // Clerk, created a task and was thrown back to the login screen.
  //
  // A valid session is translated INTO the key path right here: the
  // actor becomes the session's person (overwriting whatever actor_id
  // the client claimed — a session must not impersonate), and the key
  // header is filled in so the check below passes untouched. Handlers
  // stay single-audited; the translation is the only new surface.
  // e.requestInfo() is cached per request, so the actor_id write below
  // is the one the rest of this handler sees.
  {
    const __k = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
    if (!__k) return e.json(503, { error: "internal HQ is not configured" });
    const __tok = e.request.header.get("X-HQ-Session") || "";
    if (__tok) {
      let __p = null;
      try {
        const __s = e.app.findFirstRecordByFilter("internal_sessions",
          "token_hash = {:h}", { h: $security.sha256(__tok) });
        let __e = String(__s.getString("expires")).trim().replace(" ", "T");
        if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(__e)) __e += "Z";
        const __t = Date.parse(__e);
        if (!isNaN(__t) && Date.now() < __t) {
          const __pp = e.app.findRecordById("internal_people", __s.getString("person"));
          if (__pp.get("active")) __p = __pp;
        }
      } catch (_) {}
      if (!__p) return e.json(401, { reauth: true });
      try { const __b = e.requestInfo().body || {}; __b.actor_id = __p.get("id"); } catch (_) {}
      e.request.header.set("X-Internal-Key", __k);
    }
  }
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); } catch (_) {}
  if (!actor || !actor.get("active")) return e.json(400, { error: "pick yourself first" });
  let row = null;
  try { row = e.app.findRecordById("internal_notes", String(body.note_id || "")); } catch (_) {}
  if (!row) return e.json(404, { error: "already gone" });
  if (row.getString("created_by") !== actor.get("id") && !actor.get("is_admin")) {
    return e.json(403, { error: "only whoever started it (or an admin) can delete a note" });
  }
  try { e.app.delete(row); } catch (_) {}
  return e.json(200, { ok: true });
});

routerAdd("GET", "/internal/cal/{token}", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  let tok = "";
  try { tok = String(e.request.pathValue("token") || ""); } catch (_) {}
  if (tok.slice(-4) === ".ics") tok = tok.slice(0, -4);
  if (!/^[0-9a-f]{64}$/.test(tok)) return e.json(404, { error: "not found" });

  let person = null;
  try {
    const people = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 200, 0);
    for (const p of people) {
      if ($security.equal($security.sha256(key + p.get("id")), tok)) { person = p; break; }
    }
  } catch (_) {}
  if (!person) return e.json(404, { error: "not found" });

  // ICS wants CRLF, escaped text, and dates as YYYYMMDD. All-day entries on
  // the due date: a feed that guesses at hours puts wrong hours on someone's
  // phone, and an all-day banner never lies.
  const esc = (t) => String(t || "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n").slice(0, 250);
  const day = (d) => String(d || "").replace(/-/g, "");
  const lines = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Anticipy//HQ//EN",
    "CALSCALE:GREGORIAN", "X-WR-CALNAME:Anticipy HQ", "METHOD:PUBLISH",
  ];
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";
  try {
    const todos = e.app.findRecordsByFilter("internal_todos",
      "status = 'open' && due != ''", "+due", 500, 0);
    for (const t of todos) {
      let mine = false;
      try { mine = (JSON.parse(t.getString("assignees") || "[]") || []).indexOf(person.get("id")) >= 0; } catch (_) {}
      if (!mine) continue;
      lines.push("BEGIN:VEVENT",
        "UID:todo-" + t.get("id") + "@anticipy-hq",
        "DTSTAMP:" + stamp,
        "DTSTART;VALUE=DATE:" + day(t.getString("due")),
        "SUMMARY:" + esc("HQ: " + t.getString("title")),
        "END:VEVENT");
    }
  } catch (_) {}
  try {
    const evs = e.app.findRecordsByFilter("internal_events", "date != ''", "+date", 200, 0);
    for (const ev of evs) {
      lines.push("BEGIN:VEVENT",
        "UID:event-" + ev.get("id") + "@anticipy-hq",
        "DTSTAMP:" + stamp,
        "DTSTART;VALUE=DATE:" + day(ev.getString("date")),
        "SUMMARY:" + esc(ev.getString("title")),
        "END:VEVENT");
    }
  } catch (_) {}
  lines.push("END:VCALENDAR");
  return e.blob(200, "text/calendar; charset=utf-8", lines.join("\r\n") + "\r\n");
});

routerAdd("POST", "/internal/clerk/exchange", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const jwtKey = $os.getenv("CLERK_HQ_JWT_KEY") || "";
  if (!jwtKey) return e.json(503, { error: "Clerk sign-in is not configured" });
  const sha256 = (x) => $security.sha256(x);

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const tok = String(body.token || "");
  if (!tok || tok.split(".").length !== 3) {
    return e.json(400, { error: "no Clerk token in the request" });
  }

  let claims = null;
  try { claims = $security.parseJWT(tok, jwtKey); } catch (_) {}
  if (!claims) return e.json(401, { error: "Clerk did not recognise that sign-in" });
  // parseJWT enforces exp; these two are re-checked because a claim that is
  // merely absent would otherwise sail through as an empty string.
  const email = String(claims.email || "").trim();
  if (!email || !claims.sub) {
    return e.json(401, { error: "Clerk did not recognise that sign-in" });
  }

  let person = null;
  try {
    person = e.app.findFirstRecordByFilter("internal_people",
      "active = true && email:lower = {:em}", { em: email.toLowerCase() });
  } catch (_) {}
  if (!person) {
    // Name the email so the fix is obvious, but only to someone who has just
    // proven to Clerk that they own it — this is their own address.
    return e.json(403, { error: "You signed in as " + email +
      ", but nobody in HQ has that email. Ask an admin to add it to your person on the People page." });
  }

  // From here this is /internal/session's mint, verbatim in shape: same
  // collection, same hash-only storage, same 30-day expiry, same keep-ten.
  const token = $security.randomStringWithAlphabet(64, "0123456789abcdef");
  const nowISO = new Date().toISOString();
  const expires = new Date(Date.now() + 30 * 86400000).toISOString();
  let ip = "";
  try {
    const xff = String(e.request.header.get("X-Forwarded-For") || "");
    if (xff) ip = xff.split(",")[0].trim();
  } catch (_) {}
  if (!ip) { try { ip = e.realIP() || ""; } catch (_) {} }
  try {
    const srow = new Record(e.app.findCollectionByNameOrId("internal_sessions"));
    srow.set("person", person.get("id"));
    srow.set("token_hash", sha256(token));
    srow.set("expires", expires);
    srow.set("ip", String(ip).slice(0, 60));
    srow.set("ua", String(e.request.header.get("User-Agent") || "").slice(0, 200));
    e.app.save(srow);
  } catch (_) { return e.json(500, { error: "could not start a session" }); }
  try {
    const mine = e.app.findRecordsByFilter("internal_sessions",
      "person = {:p}", "-created", 60, 0, { p: person.get("id") });
    for (let i = 10; i < mine.length; i++) { try { e.app.delete(mine[i]); } catch (_) {} }
  } catch (_) {}
  try { person.set("last_in", nowISO); e.app.save(person); } catch (_) {}

  return e.json(200, { ok: true, token: token, expires: expires, person: {
    id: person.get("id"), name: person.getString("name"),
    is_admin: !!person.get("is_admin") } });
});

routerAdd("POST", "/internal/session/end", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (!tok) return e.json(200, { ok: true });   // already signed out; say so plainly
  try {
    const sess = e.app.findFirstRecordByFilter("internal_sessions",
      "token_hash = {:h}", { h: sha256(tok) });
    e.app.delete(sess);
  } catch (_) {}
  // Always 200. Whether that token existed is not a thing this route reports.
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// GET /internal/me — who am I, and what are the team rules. Called once on
// boot so the page never has to guess.
// --------------------------------------------------------------------------
routerAdd("GET", "/internal/me", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let actor = null, viaSession = false;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) { actor = p; viaSession = true; }
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try {
      const who = e.request.url.query().get("actor_id") || "";
      if (who) actor = e.app.findRecordById("internal_people", who);
    } catch (_) { actor = null; }
    if (!actor) return e.json(400, { error: "pick yourself first" });
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }

  const cfg = { team_name: "Anticipy", perm_assign: "everyone", perm_delete: "creator" };
  try {
    const rows = e.app.findRecordsByFilter("internal_config", "id != ''", "+key", 20, 0);
    for (const c of rows) {
      const k = c.getString("key");
      if (k === "team_name" || k === "perm_assign" || k === "perm_delete") cfg[k] = c.getString("value");
    }
  } catch (_) {}

  return e.json(200, {
    // via_session is returned because the page hides the "You're looking at HQ
    // as Ari" switcher when it is true. A real session must not be able to
    // pretend to be somebody else, and the control that would let it simply
    // is not drawn.
    via_session: viaSession,
    person: { id: actor.get("id"), name: actor.getString("name"),
      is_admin: !!actor.get("is_admin"), role: actor.getString("role"),
      focus: actor.getString("focus"), tz: actor.getString("tz"),
      email: actor.getString("email"), phone: actor.getString("phone"),
      remind_pref: actor.getString("remind_pref") || "inapp",
      email_on: actor.get("email_on") !== false, sms_on: actor.get("sms_on") !== false,
      has_code: !!actor.getString("code_hash"),
      // The subscribe-from-URL feed. Railway origin on purpose — the edge
      // gate would 401 Google's fetcher. RAILWAY_PUBLIC_DOMAIN is set by the
      // platform; the request host is the fallback for local runs.
      cal_url: "https://" + ($os.getenv("RAILWAY_PUBLIC_DOMAIN") || e.request.host) +
        "/internal/cal/" + $security.sha256(key + actor.get("id")) + ".ics" },
    team_name: cfg.team_name, perm_assign: cfg.perm_assign, perm_delete: cfg.perm_delete,
  });
});

// --------------------------------------------------------------------------
// POST /internal/people/code — mint a new login code for somebody. Admin only.
// This is the "Reset login code" on People and the "Reset my code" in Settings.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/people/code", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }
  if (!actor.get("is_admin")) return e.json(403, { error: "only an admin can hand out login codes" });

  let target;
  try { target = e.app.findRecordById("internal_people", String(body.person_id || "")); }
  catch (_) { return e.json(404, { error: "no such person" }); }

  const plain = $security.randomStringWithAlphabet(8, "0123456789ABCDEFGHJKMNPQRSTVWXYZ");
  target.set("code_hash", sha256(plain));
  target.set("code_set_at", new Date().toISOString());
  e.app.save(target);

  // A RESET SIGNS THE OLD CODE OUT. Rotating code_hash alone would leave every
  // session minted with the previous code alive for up to thirty days, so a
  // reset would look like it worked and change nothing for the one person it
  // was aimed at. STOPS: a revoked credential outliving its revocation.
  let killed = 0;
  try {
    const live = e.app.findRecordsByFilter("internal_sessions",
      "person = {:p}", "-created", 200, 0, { p: target.get("id") });
    for (const s of live) { try { e.app.delete(s); killed++; } catch (_) {} }
  } catch (_) {}

  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "person.code");
    // The code itself never appears here. An activity feed is read by everyone.
    act.set("subject", actor.getString("name") + " reset " + target.getString("name") + "'s login code");
    act.set("verb", "reset the login code");
    act.set("ref", target.get("id"));
    e.app.save(act);
  } catch (_) {}

  // Shown once, on the admin's screen, and then it only exists in a clipboard.
  return e.json(200, { code: plain.slice(0, 4) + "-" + plain.slice(4),
    signed_out: killed, name: target.getString("name") });
});

// --------------------------------------------------------------------------
// POST /internal/comments — the Task panel's thread.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/comments", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }

  let todo;
  try { todo = e.app.findRecordById("internal_todos", String(body.todo_id || "")); }
  catch (_) { return e.json(404, { error: "that item is gone" }); }
  const text = String(body.text || "").trim().slice(0, 4000);
  if (!text) return e.json(400, { error: "say something first" });

  let parent = "";
  if (body.parent) {
    try {
      const p = e.app.findRecordById("internal_comments", String(body.parent));
      // A reply belongs to the thread it was written in. Letting one point at
      // a comment on a different task would put somebody's sentence under a
      // task they never opened.
      if (p.getString("todo") !== todo.get("id")) return e.json(400, { error: "that reply doesn't belong to this task" });
      parent = p.get("id");
    } catch (_) { return e.json(404, { error: "that comment is gone" }); }
  }

  const c = new Record(e.app.findCollectionByNameOrId("internal_comments"));
  c.set("todo", todo.get("id"));
  c.set("author", actor.get("id"));
  // Denormalized for the same reason internal_activity.actor_name is: the
  // thread has to still read right after somebody is deactivated.
  c.set("author_name", actor.getString("name"));
  c.set("text", text); c.set("parent", parent);
  c.set("edited_at", ""); c.set("deleted", false);
  e.app.save(c);

  try { todo.set("cmt_count", (Number(todo.get("cmt_count")) || 0) + 1); e.app.save(todo); } catch (_) {}

  // ---- mentions, then everybody else, and never both -----------------------
  try {
    const ncol = e.app.findCollectionByNameOrId("internal_notifs");
    const told = {};
    told[actor.get("id")] = true;               // never notify yourself
    const push = (person, kind, what) => {
      if (!person || told[person]) return;
      told[person] = true;
      const n = new Record(ncol);
      n.set("person", person); n.set("kind", kind);
      n.set("text", actor.getString("name") + " " + what);
      n.set("sub", text.slice(0, 300));
      n.set("todo", todo.get("id")); n.set("actor", actor.get("id"));
      n.set("read", false); n.set("emailed_at", ""); n.set("smsed_at", "");
      e.app.save(n);
    };
    // @Name against ACTIVE people only. Matching the longest name first so
    // "@Jose" inside "@Joseph" cannot claim the wrong person.
    let people = [];
    try { people = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 100, 0); } catch (_) {}
    people.sort((a, b) => b.getString("name").length - a.getString("name").length);
    const hay = text.toLowerCase();
    for (const p of people) {
      const first = p.getString("name").split(/\s+/)[0].toLowerCase();
      if (!first) continue;
      if (hay.indexOf("@" + p.getString("name").toLowerCase()) >= 0 || hay.indexOf("@" + first) >= 0) {
        push(p.get("id"), "mention", "mentioned you");
      }
    }
    const list = (s) => { try { return JSON.parse(s || "[]") || []; } catch (_) { return []; } };
    for (const id of list(todo.getString("assignees"))) push(id, "comment", "commented on your task");
    for (const id of list(todo.getString("watchers"))) push(id, "comment", "commented on a task you're watching");
  } catch (_) {}

  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "todo.comment");
    act.set("subject", actor.getString("name") + " commented on “" + todo.getString("title").slice(0, 80) + "”");
    act.set("verb", "commented");
    act.set("ref", todo.get("id"));
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { id: c.get("id"), created: c.getString("created") });
});

// --------------------------------------------------------------------------
// PATCH /internal/comments — the author, and only the author.
// --------------------------------------------------------------------------
routerAdd("PATCH", "/internal/comments", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }

  let c;
  try { c = e.app.findRecordById("internal_comments", String(body.comment_id || "")); }
  catch (_) { return e.json(404, { error: "that comment is gone" }); }
  // Editing is not an admin power. An admin can remove a comment; putting
  // different words in somebody else's mouth is a different thing entirely.
  if (c.getString("author") !== actor.get("id")) return e.json(403, { error: "only the person who wrote it can edit it" });
  if (c.get("deleted")) return e.json(404, { error: "that comment is gone" });
  const text = String(body.text || "").trim().slice(0, 4000);
  if (!text) return e.json(400, { error: "say something first" });
  c.set("text", text);
  // The mark that makes the thread honest: an edited sentence says so.
  c.set("edited_at", new Date().toISOString());
  e.app.save(c);
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/comments/delete — author or admin. A TOMBSTONE, not a DELETE.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/comments/delete", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }

  let c;
  try { c = e.app.findRecordById("internal_comments", String(body.comment_id || "")); }
  catch (_) { return e.json(404, { error: "already gone" }); }
  if (c.getString("author") !== actor.get("id") && !actor.get("is_admin")) {
    return e.json(403, { error: "only the person who wrote it — or an admin — can remove it" });
  }
  if (c.get("deleted")) return e.json(200, { ok: true });   // idempotent
  // A TOMBSTONE. Deleting the row would orphan every reply hanging off it, and
  // an orphaned reply is a sentence with no question above it — the thread
  // stops making sense and nobody can tell why. The text is blanked, which is
  // the part that actually needed to go.
  c.set("deleted", true); c.set("text", "");
  e.app.save(c);
  try {
    const todo = e.app.findRecordById("internal_todos", c.getString("todo"));
    const n = Number(todo.get("cmt_count")) || 0;
    todo.set("cmt_count", n > 0 ? n - 1 : 0);
    e.app.save(todo);
  } catch (_) {}
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/reminders — the ones remind_at cannot express.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/reminders", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }

  let todo;
  try { todo = e.app.findRecordById("internal_todos", String(body.todo_id || "")); }
  catch (_) { return e.json(404, { error: "that item is gone" }); }

  const rule = String(body.rule || "").trim();
  const RULES = ["at", "one_hour_before", "one_day_before", "when_overdue", "daily_until_done"];
  if (RULES.indexOf(rule) < 0) return e.json(400, { error: "I don't know that kind of reminder" });
  const channel = String(body.channel || "inapp").trim();
  if (["inapp", "email", "sms", "both"].indexOf(channel) < 0) return e.json(400, { error: "reminders are in-app, email, sms or both" });

  let person = "";
  if (body.person) {
    try { person = e.app.findRecordById("internal_people", String(body.person)).get("id"); }
    catch (_) { return e.json(400, { error: "that person isn't on the team" }); }
  }

  // ---- WHO WOULD THIS ACTUALLY REACH -------------------------------------
  // The same reachability refusal POST /internal/todos already makes, in the
  // same words, because a reminder that cannot reach anybody is a lie printed
  // on a card. In-app always reaches: it is a row in their tray.
  if (channel !== "inapp") {
    const ids = [];
    if (person) ids.push(person);
    else {
      try {
        const a = JSON.parse(todo.getString("assignees") || "[]") || [];
        for (const id of a) ids.push(id);
      } catch (_) {}
      if (!ids.length && todo.getString("created_by")) ids.push(todo.getString("created_by"));
    }
    const needEmail = channel === "email" || channel === "both";
    const needPhone = channel === "sms" || channel === "both";
    let reachable = false;
    const missing = [];
    for (const id of ids) {
      let p = null;
      try { p = e.app.findRecordById("internal_people", id); } catch (_) { continue; }
      const okE = needEmail && !!p.getString("email");
      const okP = needPhone && !!p.getString("phone");
      if (okE || okP) reachable = true;
      if (needEmail && !p.getString("email")) missing.push(p.getString("name") + " has no email on file");
      if (needPhone && !p.getString("phone")) missing.push(p.getString("name") + " has no phone number on file");
    }
    if (!reachable) return e.json(400, { error: missing.join("; ") || "nobody on this has contact details yet" });
  }

  // ---- when does it fire, in UTC -----------------------------------------
  // THE OFFSET COMES FROM THE BROWSER, and this is deliberate. This runtime has
  // no timezone database — there is no Intl here — so the only two options were
  // to hand-maintain a table of zone offsets, which is wrong twice a year and
  // silently, or to ask the one participant that genuinely knows: the page,
  // which computes the recipient's real offset including DST. It is validated
  // to a sane range so a malformed or hostile value cannot push a reminder
  // years away. When it is absent everything is treated as UTC and the label
  // says the UTC time, so nothing on screen claims an hour it cannot deliver.
  let offMin = 0;
  if ("tz_offset" in body) {
    const o = parseInt(body.tz_offset, 10);
    if (isNaN(o) || o < -840 || o > 840) return e.json(400, { error: "that timezone offset isn't a real one" });
    offMin = o;
  }
  let anchor = NaN;
  if (String(body.at || "")) {
    let s = String(body.at).trim().replace(" ", "T");
    if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(s)) s += "Z";
    anchor = Date.parse(s);
    if (isNaN(anchor)) return e.json(400, { error: "that time looks malformed" });
  } else {
    const due = todo.getString("due");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) return e.json(400, { error: "give the task a deadline first, or tell me a time" });
    const hm = /^\d{2}:\d{2}$/.test(todo.getString("due_time")) ? todo.getString("due_time") : "09:00";
    const p = due.split("-"), t = hm.split(":");
    anchor = Date.UTC(parseInt(p[0], 10), parseInt(p[1], 10) - 1, parseInt(p[2], 10),
      parseInt(t[0], 10), parseInt(t[1], 10), 0) - offMin * 60000;
  }

  let fire = anchor;
  let label = "At the deadline";
  if (rule === "one_hour_before") { fire = anchor - 3600000; label = "One hour before"; }
  else if (rule === "one_day_before") { fire = anchor - 86400000; label = "One day before"; }
  else if (rule === "when_overdue") { fire = anchor + 60000; label = "When it goes overdue"; }
  else if (rule === "daily_until_done") { label = "Every day until it's done"; }
  // A reminder armed for a moment that has already gone would fire on the very
  // next sweep and read as a bug. Push it to the next sweep boundary instead,
  // so "one hour before" on something due in ten minutes still says something.
  if (fire < Date.now()) fire = Date.now() + 60000;

  const r = new Record(e.app.findCollectionByNameOrId("internal_reminders"));
  r.set("todo", todo.get("id"));
  r.set("person", person);
  r.set("rule", rule);
  r.set("fire_at", new Date(fire).toISOString());
  r.set("channel", channel);
  r.set("label", label.slice(0, 60));
  r.set("sent_at", ""); r.set("attempts", 0);
  r.set("created_by", actor.get("id"));
  e.app.save(r);
  return e.json(200, { id: r.get("id"), fire_at: r.getString("fire_at"), label: r.getString("label") });
});

// --------------------------------------------------------------------------
// POST /internal/reminders/delete — whoever armed it, or an admin.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/reminders/delete", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }
  let rem;
  try { rem = e.app.findRecordById("internal_reminders", String(body.reminder_id || "")); }
  catch (_) { return e.json(404, { error: "already gone" }); }
  if (rem.getString("created_by") !== actor.get("id") && !actor.get("is_admin")) {
    return e.json(403, { error: "only the person who set it — or an admin — can take it off" });
  }
  e.app.delete(rem);
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/notifs/read — {ids:[…]} or {all:true}.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/notifs/read", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }

  const mine = actor.get("id");
  if (body.all === true) {
    try {
      const rows = e.app.findRecordsByFilter("internal_notifs",
        "person = {:p} && read = false", "-created", 500, 0, { p: mine });
      for (const n of rows) { try { n.set("read", true); e.app.save(n); } catch (_) {} }
    } catch (_) {}
  } else if (Array.isArray(body.ids)) {
    for (const id of body.ids.slice(0, 200)) {
      try {
        const n = e.app.findRecordById("internal_notifs", String(id));
        // Marking somebody else's notification read would hide a thing they
        // were told, from them, with no trace. The row has to be yours.
        if (n.getString("person") !== mine) continue;
        n.set("read", true); e.app.save(n);
      } catch (_) {}
    }
  } else {
    return e.json(400, { error: "which ones? send ids, or all:true" });
  }

  let unread = 0;
  try {
    unread = e.app.findRecordsByFilter("internal_notifs",
      "person = {:p} && read = false", "-created", 200, 0, { p: mine }).length;
  } catch (_) {}
  return e.json(200, { ok: true, unread: unread });
});

// --------------------------------------------------------------------------
// POST /internal/tracks/delete — admin only. Nothing is ever orphaned.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/tracks/delete", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }
  if (!actor.get("is_admin")) return e.json(403, { error: "only an admin can remove a project" });

  let track;
  try { track = e.app.findRecordById("internal_tracks", String(body.track_id || "")); }
  catch (_) { return e.json(404, { error: "already gone" }); }

  // Where the work goes. Company first, then any other project, and if there
  // is genuinely nowhere to put it the delete is refused. DELETING A PROJECT
  // MUST NEVER DELETE WORK, and a todo whose `track` points at a row that no
  // longer exists is invisible on every screen that groups by project — gone
  // without ever appearing in the activity feed as gone.
  let home = null;
  try {
    const all = e.app.findRecordsByFilter("internal_tracks", "id != ''", "+created", 50, 0);
    for (const t of all) {
      if (t.get("id") === track.get("id")) continue;
      if (t.getString("name").toLowerCase() === "company") { home = t; break; }
      if (!home) home = t;
    }
  } catch (_) {}
  if (!home) return e.json(400, { error: "that's the only project — make another one first" });

  let moved = 0;
  try {
    const rows = e.app.findRecordsByFilter("internal_todos",
      "track = {:t}", "-created", 500, 0, { t: track.get("id") });
    for (const r of rows) {
      try { r.set("track", home.get("id")); e.app.save(r); moved++; } catch (_) {}
    }
  } catch (_) {}
  const name = track.getString("name");
  e.app.delete(track);
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "track.delete");
    act.set("subject", actor.getString("name") + " removed the project “" + name.slice(0, 80)
      + "” — " + moved + (moved === 1 ? " task moved to " : " tasks moved to ") + home.getString("name"));
    act.set("verb", "removed the project " + name.slice(0, 60));
    act.set("ref", home.get("id"));
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { moved: moved, moved_to: home.get("id") });
});

// --------------------------------------------------------------------------
// POST /internal/settings — team name and the two permission questions.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/settings", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  const sha256 = (s) => $security.sha256(s);
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let actor = null;
  const tok = e.request.header.get("X-HQ-Session") || "";
  if (tok) {
    try {
      const sess = e.app.findFirstRecordByFilter("internal_sessions",
        "token_hash = {:h}", { h: sha256(tok) });
      let exp = String(sess.getString("expires")).trim().replace(" ", "T");
      if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
      const t = Date.parse(exp);
      if (!isNaN(t) && Date.now() < t) {
        const p = e.app.findRecordById("internal_people", sess.getString("person"));
        if (p.get("active")) actor = p;
      }
    } catch (_) {}
    if (!actor) return e.json(401, { reauth: true });
  } else {
    if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
      return e.json(401, { error: "wrong key" });
    }
    try { actor = e.app.findRecordById("internal_people", String(body.actor_id || "")); }
    catch (_) { return e.json(400, { error: "pick yourself first" }); }
    if (!actor.get("active")) return e.json(400, { error: "that person is deactivated" });
  }
  if (!actor.get("is_admin")) return e.json(403, { error: "only an admin can change team settings" });

  const put = (k, v) => {
    let row = null;
    try { row = e.app.findFirstRecordByFilter("internal_config", "key = {:k}", { k: k }); } catch (_) {}
    if (!row) row = new Record(e.app.findCollectionByNameOrId("internal_config"));
    row.set("key", k); row.set("value", v);
    e.app.save(row);
  };
  if ("team_name" in body) {
    const n = String(body.team_name || "").trim().slice(0, 120);
    if (!n) return e.json(400, { error: "the team needs a name" });
    put("team_name", n);
  }
  if ("perm_assign" in body) {
    const v = String(body.perm_assign || "");
    if (["everyone", "admins"].indexOf(v) < 0) return e.json(400, { error: "everyone, or admins only" });
    put("perm_assign", v);
  }
  if ("perm_delete" in body) {
    const v = String(body.perm_delete || "");
    if (["admins", "creator"].indexOf(v) < 0) return e.json(400, { error: "admins only, or the creator and admins" });
    put("perm_delete", v);
  }
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", actor.get("id")); act.set("actor_name", actor.getString("name"));
    act.set("action", "settings.update");
    act.set("subject", actor.getString("name") + " changed the team settings");
    act.set("verb", "changed the team settings");
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { ok: true });
});

// ==========================================================================
// THE FRONT DOOR
//
// https://www.anticipy.ai/internal.html is a 404 and always has been. Only
// four prefixes reach this backend through the site — /fellowships,
// /fellowship-growth-learning, /fellows/* and /r/* — and /internal/* is
// answered by the Next.js app itself. So a page dropped in pb_public is not
// reachable, which is exactly how the guardian link came to point at a path
// that 404'd at the edge for every parent who clicked it.
//
// PREFERRED, and it is not in this repo: two rewrites in omize10/Anticipy's
// next.config.mjs, /hq -> /fellows/hq and /internal/:path* -> /internal/:path*
// on the Railway origin. That makes the page and its data same-origin, which
// means no CORS at all and no Railway hostname baked into a world-readable
// file. It costs a second repo and a Vercel deploy.
//
// WHAT IS HERE is the fallback that needs neither: the page served from a
// prefix that is already forwarded, plus the CORS block that lets it call the
// Railway origin directly until the rewrites land.
// ==========================================================================

// CORS on the internal API, and an explicit origin — never "*".
// These routes carry a credential in a custom header. With a wildcard origin
// any page anybody on the team visits could be taught to ask this API
// questions; with an allow-list, a browser refuses before the request leaves.
routerUse((e) => {
  const path = e.request.url.path;
  if (path.indexOf("/internal/") !== 0 && path !== "/fellows/hq") return e.next();
  const allowed = [$os.getenv("ANTICIPY_HQ_ORIGIN") || "https://www.anticipy.ai",
    "https://anticipy.ai"];
  const origin = e.request.header.get("Origin") || "";
  if (origin && allowed.indexOf(origin) >= 0) {
    const h = e.response.header();
    h.set("Access-Control-Allow-Origin", origin);
    h.set("Vary", "Origin");
    h.set("Access-Control-Allow-Headers", "X-Internal-Key, X-HQ-Session, Content-Type");
    h.set("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS");
    h.set("Access-Control-Max-Age", "86400");
  }
  return e.next();
});

// The preflight. Answers 204 and nothing else — it never touches a record and
// never reveals whether the path behind it exists.
routerAdd("OPTIONS", "/internal/{path...}", (e) => {
  return e.string(204, "");
});

// --------------------------------------------------------------------------
// GET /fellows/hq — HQ itself, on a prefix the edge actually forwards.
// --------------------------------------------------------------------------
routerAdd("GET", "/fellows/hq", (e) => {
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const path = $os.getenv("ANTICIPY_HQ_PAGE") || "pb_public/internal.html";
  let html = "";
  try { html = String(toString($os.readFile(path))); } catch (_) {}
  // FAIL VISIBLY, NOT PARTLY. If the file could not be read — wrong working
  // directory, wrong deploy, a truncated copy — serve one honest sentence
  // instead of half a document. A page that renders with its script missing
  // looks like a broken product; a page that says it could not load looks
  // like a thing to go and fix, which is what it is.
  if (html.length < 200 || html.toLowerCase().indexOf("<!doctype") < 0) {
    e.response.header().set("Content-Type", "text/html; charset=utf-8");
    return e.html(503, "<!doctype html><meta charset=\"utf-8\">"
      + "<title>Anticipy HQ</title>"
      + "<body style=\"font:16px/1.5 system-ui;padding:48px;max-width:34em\">"
      + "<p>HQ couldn't load its page from <code>" + esc(path) + "</code> on this server.</p>"
      + "<p>Nothing is broken with your account — this is a deploy problem.</p>");
  }
  e.response.header().set("Content-Type", "text/html; charset=utf-8");
  // The page ships no data and no secrets. Everything it shows it fetches
  // through the keyed or session routes above, which is what makes it safe to
  // serve from a public prefix at all.
  e.response.header().set("X-Robots-Tag", "noindex, nofollow");
  return e.html(200, html);
});
