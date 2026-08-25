/// <reference path="../pb_data/types.d.ts" />

// THE DOOR ON THE EVIDENCE HOST.
//
// `1700000045_evidence.js` gives a receipt photo somewhere to live. This is
// the only way it comes back out, and the reason it needs a file of its own is
// that the picture has to be fetchable by a stranger's server.
//
// WHY A STRANGER'S SERVER. "Done = evidence" ends with a text message carrying
// the screenshot. On SMS the only mechanism for that is Twilio's `MediaUrl`,
// and Twilio does not accept bytes, a `data:` URI or an authenticated URL: it
// takes a URL, fetches it from its own infrastructure with no credential of
// ours, and attaches what comes back. So somewhere in this system there has to
// be an https URL that answers an anonymous GET with a photograph of a page
// the owner was logged into. That is the whole exposure, it is unavoidable if
// the photo is to reach a phone at all, and everything below exists to make
// the window it is open for as small as it can be.
//
// WHAT THAT WINDOW IS.
//   * DEFAULT DENY. `share_expires` empty means NO public URL exists. A row
//     that nobody deliberately shared is unreachable to anyone holding the
//     exact path. This is the property everything else rests on: the normal
//     state of an evidence photo is "not on the internet".
//   * The path is unguessable to begin with — PocketBase's 15-character record
//     id plus the 10 random characters it appends to every stored filename —
//     but unguessability is not a lock, it is a delay, so it is not relied on.
//   * A window is minutes long (SHARE_WINDOW_MS) and is opened one record at a
//     time by POST /evidence/share, service token only. Twilio fetches within
//     seconds of the API call.
//   * A window also dies after SHARE_FETCH_LIMIT fetches, because expiry alone
//     leaves a leaked URL an unlimited download until it lapses.
//
// WHAT IT DOES NOT PROTECT AGAINST, SAID PLAINLY. Once Twilio has fetched the
// image it holds its own copy and delivers it to a handset; nothing here can
// expire that. Shortening our window does not shorten theirs. The decision to
// send a picture at all is therefore the owner's, not this file's — this file
// only makes sure that the picture is not ALSO sitting on an open URL for the
// rest of its life.
//
// LOCAL-FIRST. `design/LOCAL-FIRST.md` rule 3: "What travels is the smallest
// conclusion that works." A full page capture is not a conclusion, and this
// backend's own posture on image bytes elsewhere is to redact them and keep a
// hash (agent_key.pb.js:70-90 does exactly that to every screenshot passing
// through the model proxy). So the host is built, and it is built closed: no
// picture is uploaded by anything in this tree, and no window is opened unless
// something holding the service token asks for one, deliberately, per message.
//
// EVERY CONSTANT IS DECLARED INSIDE ITS HANDLER. A `const` at the top of a
// pb_hooks file is NOT in scope inside the callback — the PocketBase JSVM
// gives each handler its own execution context. That cost the whole
// account-delete feature once, measured against a local 0.30.4
// (account_delete.pb.js:42-56), and password_reset.pb.js:23-26 and
// audit_retention.pb.js:24-27 carry the same warning.

// ------------------------------------------------------------- the fetch door
routerUse((e) => {
  const SHARE_FETCH_LIMIT = 5;

  const path = e.request.url.path;
  if (path.indexOf("/api/files/") !== 0) return e.next();

  // The dashboard, above everything else. A superuser session already has the
  // database; refusing it here would only make an evidence row impossible to
  // inspect when something has gone wrong. Same ordering argument, and the
  // same trap, as guard.pb.js:355-374.
  try { if (e.hasSuperuserAuth()) return e.next(); } catch (_) {}

  // "that evidence is not available" is the answer to every refusal below.
  // Telling an anonymous caller WHICH of "no such row", "never shared",
  // "expired" and "spent" they hit turns the endpoint into an oracle for
  // walking record ids.
  const gone = () => e.json(404, { error: "that evidence is not available" });

  // /api/files/{collectionIdOrName}/{recordId}/{filename}
  const parts = path.split("/");
  const collectionKey = String(parts[3] || "");
  const recordId = String(parts[4] || "");
  if (!collectionKey || !recordId) return gone();

  // RESOLVED, NOT COMPARED. PocketBase accepts the collection's 15-character
  // ID here as well as its name, so a gate that matched the literal string
  // "evidence" was walked past by anyone who had read the id off a collections
  // listing — which is not a secret.
  let name = "";
  try {
    name = String(e.app.findCollectionByNameOrId(collectionKey).name || "");
  } catch (_) {
    return gone();
  }
  // FAIL CLOSED FOR EVERY OTHER COLLECTION. Today none of them has a file
  // field, so nothing legitimate reaches this line. If a later migration adds
  // one it has to come here and say so, rather than inheriting an anonymous
  // public URL by accident — which is exactly how an evidence host turns into
  // a file host.
  if (name !== "evidence") return gone();

  let rec = null;
  try { rec = e.app.findRecordById("evidence", recordId); } catch (_) { rec = null; }
  // A lookup that THREW and a row that is GONE get the same answer, for the
  // reason guard.pb.js:326-333 gives about credentials: "I cannot prove this
  // may be served" is a no either way, and a gate that opens when the database
  // hiccups is a gate you open by making the database hiccup.
  if (!rec) return gone();

  // ---- the two doors that are not the public one ----
  // Neither spends Twilio's fetch ceiling and neither needs a share window:
  // the picture in his own app is not the picture on the public internet, and
  // must not need one to exist.
  const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  if (token && e.request.header.get("X-Anticipy-Token") === token) return e.next();
  try {
    // `e.auth` is populated for ANY auth record in PocketBase 0.30.4
    // (guard.pb.js:358-366), so the collection has to be checked as well as
    // the id — otherwise a paired agent row whose id happened to match an
    // owner_ref would read somebody's screenshots.
    if (e.auth && String(e.auth.collection().name || "") === "owners"
        && e.auth.id && String(e.auth.id) === rec.getString("owner_ref")) {
      return e.next();
    }
  } catch (_) {}

  // ---- the public door ----
  const expires = rec.getString("share_expires");
  if (!expires) return gone();
  const until = new Date(expires).getTime();
  // `new Date("soon").getTime()` is NaN and `NaN <= Date.now()` is FALSE, so
  // the obvious expiry test lets an unparseable date through as if it were the
  // far future. Same idiom and same trap as workflow_guard.pb.js:160-161.
  if (!until || isNaN(until) || until <= Date.now()) return gone();

  const spent = Number(rec.get("fetches") || 0);
  if (!(spent >= 0) || spent >= SHARE_FETCH_LIMIT) return gone();

  try {
    rec.set("fetches", spent + 1);
    e.app.save(rec);
  } catch (err) {
    // Serving what nobody is counting is the exact hole the ceiling closes,
    // so a fetch that cannot be counted is refused — the same posture the
    // pair-code throttle takes when it has nowhere to count guesses
    // (guard.pb.js:127-138). It costs a text that arrives without its picture,
    // which is the designed fallback, not a failure.
    console.log("evidence: refusing a fetch that could not be counted: " + String(err));
    return gone();
  }
  return e.next();
});

// ------------------------------------------------------------ the share mint
//
// POST /evidence/share  { "id": "<evidence record id>" }
//   X-Anticipy-Token: <service token>
//
// Called by the worker in the moment it is about to send a text, and never
// speculatively: a window that is open before anybody needs it is exposure
// bought for nothing.
routerAdd("POST", "/evidence/share", (e) => {
  const SHARE_WINDOW_MS = 15 * 60 * 1000;
  const SHARE_FETCH_LIMIT = 5;

  const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  // `getenv` returns "" when unset, and "" === "" for a missing header too —
  // which is how a token check silently becomes an open door on a box where
  // the variable was never set. The truthiness test is the whole guard.
  if (!token || e.request.header.get("X-Anticipy-Token") !== token) {
    return e.json(403, { error: "forbidden" });
  }

  // AN ABSENT PICTURE IS AN ANSWER, NOT AN ERROR — and the distinction is the
  // difference between a text with no photo and no text at all. A `MediaUrl`
  // that 404s makes Twilio fail the WHOLE message, so a caller that cannot be
  // given a URL must be told so in a form it will act on, not handed a link
  // that will break at the other end.
  const nothing = (reason) => e.json(200, {
    ok: false, reason: reason, url: "", expires: "",
  });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) { body = {}; }
  const id = String(body.id || "").trim();
  if (!id) return nothing("no evidence was named");

  let rec = null;
  try { rec = e.app.findRecordById("evidence", id); } catch (_) { rec = null; }
  if (!rec) return nothing("that evidence is gone");
  const file = String(rec.getString("image") || "");
  if (!file) return nothing("that evidence has no picture");

  // Where this backend answers from. ANTICIPY_PUBLIC_URL if it is set;
  // otherwise the origin of the Twilio webhook URL, which is this same host
  // and is already required to be correct in production (sms.pb.js). A guess
  // is not acceptable here — a wrong origin is a MediaUrl Twilio cannot fetch,
  // and that fails the message rather than dropping the picture.
  let base = String($os.getenv("ANTICIPY_PUBLIC_URL") || "").trim();
  if (!base) {
    const hook = String($os.getenv("ANTICIPY_TWILIO_WEBHOOK_URL") || "").trim();
    const origin = hook.match(/^https:\/\/[^/]+/);
    base = origin ? origin[0] : "";
  }
  base = base.replace(/\/+$/, "");
  if (base.indexOf("https://") !== 0) {
    return nothing("no https base url is configured for this backend");
  }

  const expires = new Date(Date.now() + SHARE_WINDOW_MS).toISOString();
  try {
    rec.set("share_expires", expires);
    // A fresh window gets a fresh ceiling. Without this, re-sharing a picture
    // that had already been fetched five times would open a window nothing
    // could ever come through, and the second text would silently lose its
    // photo for a reason no log named.
    rec.set("fetches", 0);
    e.app.save(rec);
  } catch (err) {
    return nothing("could not open a share window: " + String(err));
  }

  return e.json(200, {
    ok: true,
    url: base + "/api/files/evidence/" + rec.id + "/" + file,
    expires: expires,
    fetches: SHARE_FETCH_LIMIT,
  });
});

// ---------------------------------------------------------------- retention
//
// TWO CEILINGS, BECAUSE ONE WAS NOT ENOUGH LAST TIME. The 5 GB production
// volume filled on 2026-08-15 and PocketBase could not open its database at
// all — "disk I/O error", crash loop, hard outage, and the visible symptom was
// password resets that texted a code the server could then never store
// (audit_retention.pb.js:3-18). Images are a worse filler than audit rows:
// PocketBase's scheduled backup zips pb_data — storage included — onto the
// same volume and keeps two (1700000037_backup_footprint.js), so peak
// footprint is three copies of every stored byte, and a snapshot taken while
// this table was oversized pins that size for two days.
//
// At the field's 400 KB ceiling the arithmetic is 60 x 400 KB = 24 MB live and
// about 72 MB at peak with both snapshots — a number that cannot take the
// product down even in the worst case, on a volume that has already been to
// 4 MB free once. The per-owner cap is the privacy half of the same sweep:
// nobody's screenshots accumulate indefinitely just because they were the
// quiet account.
onRecordAfterCreateSuccess((e) => {
  const KEEP_PER_OWNER = 20;
  const KEEP_TOTAL = 60;
  const SWEEP_BATCH = 25;
  try {
    const owner = e.record ? String(e.record.getString("owner_ref") || "") : "";
    if (owner) {
      const mine = e.app.findRecordsByFilter(
        "evidence", "owner_ref = {:o}", "-created", SWEEP_BATCH, KEEP_PER_OWNER,
        { o: owner });
      for (const rec of mine) {
        try { e.app.delete(rec); } catch (_) {}
      }
    }
    const surplus = e.app.findRecordsByFilter(
      "evidence", "id != ''", "-created", SWEEP_BATCH, KEEP_TOTAL);
    for (const rec of surplus) {
      try { e.app.delete(rec); } catch (_) {}
    }
  } catch (_) {
    // Never let housekeeping break the write that triggered it. A screenshot
    // that failed to upload is a text without a photo; a create that throws
    // out of a sweep is a job that can never be marked done.
  }
  e.next();
}, "evidence");
