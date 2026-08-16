/// <reference path="../pb_data/types.d.ts" />

// "I forgot my password" — by text, because this image has no way to send mail.
//
// Two routes, both OUTSIDE /api/collections/, so guard.pb.js does not gate them
// (it protects the data API; these are the front door):
//
//   POST /auth/reset/request  { "email": "you@example.com" }
//   POST /auth/reset/confirm  { "email": "...", "code": "123456", "password": "..." }
//
// Deliberate properties, each one there because its absence is a real attack:
//   - The reply to /request is ALWAYS the same, whether or not that email
//     exists. Otherwise this endpoint becomes a way to ask "does Omar have an
//     account here?" one address at a time.
//   - Only a SHA-256 of the code is stored. A dump of the table is useless.
//   - The code expires (10 min), is single-use, and its guesses are counted.
//     Six digits is one-in-a-million per try only if the tries are limited.
//   - Requests per person are throttled, so nobody can be woken at 3am by
//     someone hammering the button.
//   - The message names the app and says plainly that it was not requested by
//     them if it wasn't — the standard phishing tell.
//
// PocketBase JSVM note, learned the hard way elsewhere in this repo: handlers
// run in an ISOLATED runtime and CANNOT see anything declared outside their own
// body. Everything below is therefore deliberately self-contained, duplicated
// between the two handlers rather than shared.

routerAdd("POST", "/auth/reset/request", (e) => {
  // Declared INSIDE the handler. The note at the top of this file says these
  // runtimes cannot see anything declared outside the handler body — and the
  // first version of this file put them outside anyway, so every reset logged
  // "RESET_TTL_SECONDS is not defined", saved no code, and then rejected the
  // correct one. The text still went out, so it looked like it worked.
  const RESET_TTL_SECONDS = 600;    // 10 minutes
  const RESET_MIN_GAP_SECONDS = 60; // between texts to the same person
  const RESET_MAX_PER_HOUR = 5;

  // One reply for every outcome. Never leak whether the account exists.
  const same = () => e.json(200, {
    ok: true,
    message: "If that account exists and has a phone number, a code is on its way by text.",
  });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) { return same(); }
  const email = String(body.email || "").trim().toLowerCase();
  if (!email) return same();

  let owner;
  try {
    owner = e.app.findFirstRecordByFilter("owners", "email = {:email}", { email: email });
  } catch (_) { return same(); }
  if (!owner) return same();

  let phone = String(owner.getString("phone") || "").trim();
  if (!phone) {
    // The account row is not the only place a phone lives: onboarding writes
    // owner_profile, and a person who signed up without a number (or changed
    // it in their profile afterwards) has one there and none here. Falling
    // through to same() made their ONLY recovery route silently do nothing —
    // a locked-out owner with no error to act on. Found 2026-08-15.
    try {
      const profile = e.app.findFirstRecordByFilter(
        "owner_profile", "owner_ref = {:ref}", { ref: owner.id });
      if (profile) phone = String(profile.getString("phone") || "").trim();
    } catch (_) {}
  }
  if (!phone) return same();   // nothing to text; still say the same thing

  const now = new Date();
  const nowMs = now.getTime();

  // Throttle: recent unexpired code, and an hourly ceiling.
  try {
    const recent = e.app.findRecordsByFilter(
      "password_resets", "owner = {:o}", "-created", 20, 0, { o: owner.id });
    let inHour = 0;
    for (const r of recent) {
      const createdMs = new Date(String(r.getString("created")).replace(" ", "T")).getTime();
      if (isNaN(createdMs)) continue;
      if (nowMs - createdMs < 3600 * 1000) inHour++;
      if (nowMs - createdMs < RESET_MIN_GAP_SECONDS * 1000 && !r.getBool("used")) {
        return same();   // one just went out; don't send another
      }
    }
    if (inHour >= RESET_MAX_PER_HOUR) return same();
  } catch (_) {}

  const code = $security.randomStringWithAlphabet(6, "0123456789");

  // Send FIRST. If the text cannot leave the building, do not leave a live code
  // sitting in the database pretending it did.
  const sid = $os.getenv("TWILIO_ACCOUNT_SID");
  const auth = $os.getenv("TWILIO_AUTH_TOKEN");
  const from = $os.getenv("TWILIO_PHONE_NUMBER") || $os.getenv("TWILIO_FROM");
  if (!sid || !auth || !from) {
    console.log("password reset: Twilio is not configured on this service — no code sent");
    return same();
  }
  try {
    // Base is overridable ONLY so the flow can be exercised end-to-end against
    // a stand-in during testing. Unset — which is what production is — it is
    // the real Twilio.
    const twilioBase = $os.getenv("TWILIO_API_BASE") || "https://api.twilio.com";
    const res = $http.send({
      url: twilioBase + "/2010-04-01/Accounts/" + sid + "/Messages.json",
      method: "POST",
      headers: {
        // This runtime has no base64 helper (probed: $security exposes hashing,
        // JWT and random only), and credentials must not go in the URL where
        // they end up in logs. So: encoded here, inside the handler, because
        // hook handlers cannot see anything declared outside their own body.
        "Authorization": "Basic " + (function (str) {
          const A = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
          let out = "", i = 0;
          while (i < str.length) {
            const c1 = str.charCodeAt(i++), c2 = str.charCodeAt(i++), c3 = str.charCodeAt(i++);
            out += A.charAt(c1 >> 2);
            out += A.charAt(((c1 & 3) << 4) | (isNaN(c2) ? 0 : c2 >> 4));
            out += isNaN(c2) ? "=" : A.charAt(((c2 & 15) << 2) | (isNaN(c3) ? 0 : c3 >> 6));
            out += isNaN(c3) ? "=" : A.charAt(c3 & 63);
          }
          return out;
        })(sid + ":" + auth),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: "From=" + encodeURIComponent(from) +
            "&To=" + encodeURIComponent(phone) +
            "&Body=" + encodeURIComponent(
              code + " is your Anticipy code to set a new password. " +
              "It works for 10 minutes. If you didn't ask for this, ignore it " +
              "and your password stays as it is."),
      timeout: 15,
    });
    if (res.statusCode < 200 || res.statusCode >= 300) {
      console.log("password reset: Twilio refused the send:", res.statusCode);
      return same();
    }
  } catch (err) {
    console.log("password reset: could not send the text:", String(err));
    return same();
  }

  try {
    const col = e.app.findCollectionByNameOrId("password_resets");
    const rec = new Record(col);
    rec.set("owner", owner.id);
    rec.set("code_hash", $security.sha256(code));
    rec.set("expires", new Date(nowMs + RESET_TTL_SECONDS * 1000).toISOString());
    rec.set("attempts", 0);
    rec.set("used", false);
    e.app.save(rec);
  } catch (err) {
    console.log("password reset: could not record the code:", String(err));
  }
  return same();
});

routerAdd("POST", "/auth/reset/confirm", (e) => {
  const RESET_MAX_ATTEMPTS = 5;   // guesses per code — see note above

  const nope = () => e.json(400, {
    ok: false,
    message: "That code isn't right, or it has expired. Ask for a new one.",
  });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) { return nope(); }
  const email = String(body.email || "").trim().toLowerCase();
  const code = String(body.code || "").trim();
  const password = String(body.password || "");
  if (!email || !code) return nope();
  // PocketBase's own minimum. Say it plainly rather than failing cryptically.
  if (password.length < 8) {
    return e.json(400, { ok: false, message: "Pick a password with at least 8 characters." });
  }

  let owner;
  try {
    owner = e.app.findFirstRecordByFilter("owners", "email = {:email}", { email: email });
  } catch (_) { return nope(); }
  if (!owner) return nope();

  let rec;
  try {
    const rows = e.app.findRecordsByFilter(
      "password_resets", "owner = {:o} && used = false", "-created", 1, 0, { o: owner.id });
    rec = rows && rows.length ? rows[0] : null;
  } catch (_) { return nope(); }
  if (!rec) return nope();

  // Expired?
  const expMs = new Date(String(rec.getString("expires"))).getTime();
  if (isNaN(expMs) || Date.now() > expMs) {
    rec.set("used", true);
    try { e.app.save(rec); } catch (_) {}
    return nope();
  }

  // Too many guesses? Burn it.
  const attempts = (rec.getInt("attempts") || 0) + 1;
  rec.set("attempts", attempts);
  if (attempts > RESET_MAX_ATTEMPTS) {
    rec.set("used", true);
    try { e.app.save(rec); } catch (_) {}
    return nope();
  }

  // Constant-time compare: a plain !== leaks how much of the hash matched
  // through timing, and this is the one comparison an attacker gets to repeat.
  if (!$security.equal($security.sha256(code), rec.getString("code_hash"))) {
    try { e.app.save(rec); } catch (_) {}   // keep the incremented count
    return nope();
  }

  // Correct. Set the password, burn the code.
  try {
    owner.setPassword(password);
    e.app.save(owner);
    rec.set("used", true);
    e.app.save(rec);
  } catch (err) {
    console.log("password reset: could not set the new password:", String(err));
    return e.json(500, { ok: false, message: "Something went wrong on my end. Try again." });
  }
  return e.json(200, { ok: true, message: "Done — sign in with your new password." });
});
