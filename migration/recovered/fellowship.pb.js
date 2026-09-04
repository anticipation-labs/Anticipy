/// <reference path="../pb_data/types.d.ts" />
//
// ANTICIPY FELLOWSHIPS — public routes.
//
// JSVM RULE, the one that has bitten this codebase three times: every handler
// gets its own copy of every constant and helper it uses. Route handlers share
// no scope with each other or with the file. Crons additionally have no `e` —
// they use $app. Do not "tidy" these into shared functions.
//
// THE FAIL STANCE IS INVERTED FROM internal_hq.
//
// HQ is private and fails CLOSED: no key configured, nobody gets in. These
// routes are public by design, so "closed" means something different here:
//   - never mint a code we could not deliver
//   - never act on something we could not verify
//   - degrade warmly, in a sentence a sixteen-year-old can act on
//   - never leak an internal name, an env var, or a stack trace
// A stranger hitting these routes should be able to learn nothing about the
// inside of the system from any error we return.
//
// AND THE RULE THAT OVERRIDES CONVENIENCE: if the person is under 13 we write
// NOTHING — not the email, not even the birth month we were just told. Under
// COPPA the act of storing it is the regulated thing, so the check happens
// before the first save, not after.

// --------------------------------------------------------------------------
// GET /fellows/health
// --------------------------------------------------------------------------
routerAdd("GET", "/fellows/health", (e) => {
  const hasResend = !!$os.getenv("RESEND_API_KEY");
  const hasModel = !!$os.getenv("OPENROUTER_API_KEY");
  let realIP = "";
  try {
    const xff = String(e.request.header.get("X-Forwarded-For") || "");
    if (xff) realIP = xff.split(",")[0].trim();
  } catch (_) {}
  if (!realIP) { try { realIP = e.realIP() || ""; } catch (_) {} }
  return e.json(200, {
    ok: true,
    can_email: hasResend,
    can_review: hasModel,
    // If this is false the per-IP throttle is disabled on purpose — see the
    // comment in /fellows/code. It is reported so the deploy checklist can be
    // verified from outside without a superuser login.
    ip_resolves: !!realIP && realIP !== "127.0.0.1" && realIP !== "::1",
  });
});

// --------------------------------------------------------------------------
// POST /fellows/code  {email, birth_month, birth_year, country}
// Sends a six-digit sign-in code. Also the age gate and the geo gate.
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/code", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const nowMs = Date.now();
  const nowISO = new Date().toISOString();

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const email = String(body.email || "").trim().toLowerCase();
  const bm = parseInt(body.birth_month, 10);
  const by = parseInt(body.birth_year, 10);
  const country = String(body.country || "").trim().toLowerCase();

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) || email.length > 254) {
    return e.json(200, { ok: false, message: "That email doesn't look right. Mind checking it?" });
  }

  // ---- AGE FIRST. Nothing is written before this passes. ------------------
  if (!(bm >= 1 && bm <= 12) || !(by >= 1900 && by <= 2100)) {
    return e.json(200, { ok: false, message: "Pick the month and year you were born and we'll carry on." });
  }
  const now = new Date();
  let age = now.getUTCFullYear() - by;
  if (now.getUTCMonth() + 1 < bm) age -= 1;
  if (age < 13) {
    // Deliberately warm, deliberately final, and NOTHING is saved — not the
    // email, not the birth month. Storing it is the regulated act.
    return e.json(200, {
      ok: false, stop: true,
      message: "You have to be 13 to join this one. Come back on your birthday — we'll still be here, and we'd genuinely like to have you."
    });
  }
  if (country !== "us" && country !== "ca") {
    return e.json(200, {
      ok: false, stop: true,
      message: "Right now we can only take fellows in the US and Canada, because that's where we can pay people properly. We'll open it up — leave us your email at anticipy.ai and we'll tell you when."
    });
  }

  // ---- throttles ----------------------------------------------------------
  // Every outcome below returns the SAME message. A stranger must not be able
  // to learn whether an address is already on file, or which limit they hit.
  const uniform = { ok: true, message: "Check your email — your code is on the way." };

  try {
    const recent = e.app.findRecordsByFilter("fellow_codes",
      "email = {:em}", "-created", 10, 0, { em: email });
    let lastMs = 0, inHour = 0;
    for (const r of recent) {
      const t = Date.parse(String(r.getString("created")).replace(" ", "T"));
      if (!isNaN(t)) {
        if (t > lastMs) lastMs = t;
        if (nowMs - t < 3600000) inHour++;
      }
    }
    if (lastMs && nowMs - lastMs < 60000) return e.json(200, uniform);   // one a minute
    if (inHour >= 5) return e.json(200, uniform);                        // five an hour
  } catch (_) {}

  // WHOSE ADDRESS IS THIS, REALLY?
  //
  // These pages are served from anticipy.ai through a Vercel rewrite, so the
  // request that reaches us has been forwarded twice. realIP() then reports
  // VERCEL's address, identically for every visitor on earth — which would
  // make this bucket the whole internet and silently lock everyone out after
  // the eighth signup of the hour.
  //
  // So take the first entry of X-Forwarded-For, which is the original client,
  // and fall back to realIP() only when there is no chain. The leftmost entry
  // is client-settable, but the worst a forger achieves is dodging their own
  // rate limit — which anyone with a second network can do anyway — whereas
  // getting this wrong the other way punishes people who did nothing.
  let ip = "";
  try {
    const xff = String(e.request.header.get("X-Forwarded-For") || "");
    if (xff) ip = xff.split(",")[0].trim();
  } catch (_) {}
  if (!ip) { try { ip = e.realIP() || ""; } catch (_) {} }
  // And it still disables itself entirely when no usable address arrives,
  // rather than treating "unknown" as one shared bucket.
  const ipUsable = ip && ip !== "127.0.0.1" && ip !== "::1";
  if (ipUsable) {
    try {
      const byIP = e.app.findRecordsByFilter("fellow_codes", "ip = {:ip}", "-created", 20, 0, { ip: ip });
      let n = 0;
      for (const r of byIP) {
        const t = Date.parse(String(r.getString("created")).replace(" ", "T"));
        if (!isNaN(t) && nowMs - t < 3600000) n++;
      }
      if (n >= 8) return e.json(200, uniform);
    } catch (_) {}
  }

  // Layer 3: the global circuit breaker. If this trips it is either real
  // traffic or an attack, and either way a human needs to know — so it
  // shouts once per hour rather than silently throttling forever.
  const ceiling = parseInt($os.getenv("ANTICIPY_FELLOW_EMAIL_CEILING") || "50", 10);
  const hourNow = nowISO.slice(0, 13);
  try {
    const meter = e.app.findFirstRecordByFilter("fellow_meter", "name = 'email'");
    const used = meter.getString("hour") === hourNow ? (Number(meter.get("calls")) || 0) : 0;
    if (used >= ceiling) {
      try {
        const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
        act.set("actor", ""); act.set("actor_name", "Fellowships");
        act.set("action", "fellowship.email_meter");
        act.set("subject", "The fellowship sign-in email meter tripped at " + ceiling + "/hour");
        e.app.save(act);
      } catch (_) {}
      return e.json(200, { ok: false, message: "We're getting a lot of signups right now — try again in a few minutes." });
    }
    meter.set("hour", hourNow); meter.set("calls", used + 1);
    e.app.save(meter);
  } catch (_) {}

  // ---- SEND FIRST, THEN SAVE ---------------------------------------------
  // The other way round leaves a live code sitting in the database pretending
  // it was delivered, and the person waits for an email that never comes.
  const code = String(Math.floor(100000 + Math.random() * 900000));
  const rk = $os.getenv("RESEND_API_KEY") || "";
  if (!rk) {
    return e.json(200, { ok: false, message: "We can't send codes this minute. Try again shortly — it's us, not you." });
  }
  let sent = false;
  try {
    const res = $http.send({
      url: "https://api.resend.com/emails",
      method: "POST",
      headers: { "Authorization": "Bearer " + rk, "Content-Type": "application/json" },
      body: JSON.stringify({
        from: "Anticipy Fellowships <notifications@aevoy.com>",
        to: [email],
        subject: code + " is your Anticipy code",
        text: "Here's your code: " + code + "\n\nIt works for 10 minutes.\n\nIf you didn't ask for this, you can ignore this email — nothing has been created."
      }),
      timeout: 20,
    });
    sent = res.statusCode >= 200 && res.statusCode < 300;
  } catch (_) { sent = false; }
  if (!sent) {
    return e.json(200, { ok: false, message: "That email didn't go through. Check the address, or try again in a minute." });
  }

  try {
    const c = new Record(e.app.findCollectionByNameOrId("fellow_codes"));
    c.set("email", email);
    c.set("code_hash", sha256(code));      // only ever the hash
    c.set("expires", new Date(nowMs + 10 * 60000).toISOString());
    c.set("attempts", 0);
    c.set("used", false);
    c.set("ip", ipUsable ? ip : "");
    e.app.save(c);
  } catch (_) {}

  return e.json(200, uniform);
});

// --------------------------------------------------------------------------
// POST /fellows/verify  {email, code, birth_month, birth_year, country, name?}
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/verify", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const nowMs = Date.now();
  const randomToken = () => {
    const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let out = "";
    for (let i = 0; i < 48; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
    return out;
  };
  const makeCode = () => {
    // LOWERCASE, and this is not cosmetic. anticipy.ai's checkout route does
    // ap_ref.toLowerCase().replace(/[^a-z0-9-]/g,"") before the value reaches
    // Stripe metadata, so an uppercase code comes back from the webhook as
    // something our exact-match lookup will never find. The click would still
    // count and the SALE would silently not — a fellow does the work, drives a
    // purchase, and is never credited. Found by reading the site's own
    // checkout route rather than by a payout dispute.
    // No i/l/o/0/1 — they are the characters people mistype off a screen.
    const chars = "abcdefghjkmnpqrstuvwxyz23456789";
    let out = "";
    for (let i = 0; i < 6; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
    return out;
  };

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const email = String(body.email || "").trim().toLowerCase();
  const code = String(body.code || "").trim();
  const bm = parseInt(body.birth_month, 10);
  const by = parseInt(body.birth_year, 10);
  const country = String(body.country || "").trim().toLowerCase();

  if (!email || !/^\d{6}$/.test(code)) {
    return e.json(200, { ok: false, message: "That code doesn't look right — it's the six digits from the email." });
  }

  let row = null;
  try {
    const rows = e.app.findRecordsByFilter("fellow_codes",
      "email = {:em} && used = false", "-created", 1, 0, { em: email });
    row = rows[0] || null;
  } catch (_) {}
  // Covers both "already used" and "there was never one for this address",
  // deliberately, because saying which would let someone probe for addresses.
  // It just needs to be true for both, and confusing for neither.
  if (!row) return e.json(200, { ok: false, message: "That code isn't live any more. Ask for a fresh one and we'll start again." });

  const exp = Date.parse(row.getString("expires"));
  if (isNaN(exp) || nowMs > exp) {
    row.set("used", true); try { e.app.save(row); } catch (_) {}
    return e.json(200, { ok: false, message: "That code expired — they only last ten minutes. Ask for a new one." });
  }
  const attempts = (Number(row.get("attempts")) || 0) + 1;
  row.set("attempts", attempts);
  if (attempts > 5) {
    row.set("used", true); try { e.app.save(row); } catch (_) {}
    return e.json(200, { ok: false, message: "Too many tries on that code. Ask for a new one and we'll start again." });
  }
  try { e.app.save(row); } catch (_) {}

  if (!$security.equal(sha256(code), row.getString("code_hash"))) {
    return e.json(200, { ok: false, message: "That's not the code in the email. Try again." });
  }
  row.set("used", true); try { e.app.save(row); } catch (_) {}

  // The age check runs again HERE, server-side, on the values sent with the
  // verify. The first check was on the client's word before anything existed;
  // this one guards the row we are about to create.
  const now = new Date();
  let age = now.getUTCFullYear() - by;
  if (now.getUTCMonth() + 1 < bm) age -= 1;
  if (!(bm >= 1 && bm <= 12) || !(by >= 1900 && by <= 2100) || age < 13) {
    return e.json(200, { ok: false, stop: true, message: "You have to be 13 to join this one. Come back on your birthday." });
  }
  const band = age >= 18 ? "18_plus" : (age >= 16 ? "16_17" : "13_15");

  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "email = {:em}", { em: email }); } catch (_) {}
  if (!fellow) {
    try {
      fellow = new Record(e.app.findCollectionByNameOrId("fellows"));
      fellow.set("email", email);
      fellow.set("name", String(body.name || "").trim().slice(0, 120));
      fellow.set("birth_month", bm); fellow.set("birth_year", by);
      fellow.set("age_band", band);
      fellow.set("country", country === "ca" ? "ca" : "us");
      fellow.set("parental_consent", band === "18_plus" ? "not_required" : "pending");
      // HOW THEY GET PAID, DEFAULTED AT CREATION. Card is the default rail, the
      // only legal value under 18, and what the decision doc promises everyone —
      // so it is the ANSWER, not a question. Nothing but POST /fellows/payout-method
      // ever wrote this field, and the payout rail refused to send while it was
      // empty, so every fellow who never went looking for that route was
      // unpayable for the life of the programme.
      fellow.set("payout_method", "card");
      fellow.set("status", "new");
      fellow.set("clicks_total", 0);
      fellow.set("code_active", false);
      fellow.set("code_revoked", false);
      fellow.set("referral_code", makeCode());
      e.app.save(fellow);
    } catch (err) {
      return e.json(200, { ok: false, message: "Something went wrong making your account. Try once more?" });
    }
  } else {
    fellow.set("age_band", band);
    if (!fellow.getString("referral_code")) fellow.set("referral_code", makeCode());
  }

  // One session per fellow: minting a new one kills the old.
  const token = randomToken();
  fellow.set("session_hash", sha256(token));
  fellow.set("session_expires", new Date(nowMs + 30 * 86400000).toISOString());
  try { e.app.save(fellow); } catch (_) {}

  return e.json(200, {
    ok: true,
    token: token,                                   // returned exactly once
    fellow: {
      id: fellow.get("id"), email: fellow.getString("email"), name: fellow.getString("name"),
      age_band: fellow.getString("age_band"), country: fellow.getString("country"),
      parental_consent: fellow.getString("parental_consent"),
      fellowship: fellow.getString("fellowship"), status: fellow.getString("status"),
      referral_code: fellow.getString("referral_code"), code_active: !!fellow.get("code_active"),
    }
  });
});

// --------------------------------------------------------------------------
// POST /fellows/start  {email, name, birth_month, birth_year, country}
//
// SIGNING UP IS ONE STEP. No password, no emailed code, no second screen.
// You type your email and you are in.
//
// The six-digit code that used to sit here was friction in the one place a
// programme like this cannot afford it: between a curious sixteen-year-old
// and the first lesson. Most people who bounce, bounce there.
//
// The email is NOT verified at this point, deliberately, and that is safe
// because of where the verification boundary actually sits: LEARNING needs
// no proof of anything, and MONEY does. A referral code is minted straight
// away and works for clicks, but it cannot pay out until the address has
// been confirmed by clicking the link in the welcome email. So an unverified
// or mistyped address costs someone nothing but their own progress sync, and
// costs us nothing at all.
//
// The old code routes stay alive underneath for anyone returning on a new
// device, where a one-time code is the honest way back in.
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/start", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const nowMs = Date.now();
  const randomToken = () => {
    const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    let out = "";
    for (let i = 0; i < 48; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
    return out;
  };
  const makeCode = () => {
    const chars = "abcdefghjkmnpqrstuvwxyz23456789";   // lowercase — see /fellows/start
    let out = "";
    for (let i = 0; i < 6; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
    return out;
  };

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const email = String(body.email || "").trim().toLowerCase();
  const name = String(body.name || "").trim().slice(0, 120);
  const bm = parseInt(body.birth_month, 10);
  const by = parseInt(body.birth_year, 10);
  const country = String(body.country || "").trim().toLowerCase();

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) || email.length > 254) {
    return e.json(200, { ok: false, field: "email", message: "That email doesn't look right." });
  }
  // A throwaway address cannot be paid, so it is refused here rather than
  // discovered at payout time when someone has already done the work.
  const domain = email.split("@")[1] || "";
  const BURNER = ["mailinator.com","guerrillamail.com","10minutemail.com","tempmail.com",
                  "yopmail.com","trashmail.com","sharklasers.com","getnada.com","temp-mail.org"];
  if (BURNER.indexOf(domain) >= 0) {
    return e.json(200, { ok: false, field: "email",
      message: "We can't pay a throwaway address. Use one you'll still have in a month." });
  }

  // ---- AGE FIRST. Nothing is written before this passes. ------------------
  if (!(bm >= 1 && bm <= 12) || !(by >= 1900 && by <= 2100)) {
    return e.json(200, { ok: false, field: "birth", message: "Pick the month and year you were born." });
  }
  const now = new Date();
  let age = now.getUTCFullYear() - by;
  if (now.getUTCMonth() + 1 < bm) age -= 1;
  if (age < 13) {
    return e.json(200, { ok: false, stop: true,
      message: "You have to be 13 to join this one. Come back on your birthday — we'll still be here, and we'd genuinely like to have you." });
  }
  if (country !== "us" && country !== "ca") {
    return e.json(200, { ok: false, stop: true,
      message: "Right now we can only take fellows in the US and Canada, because that's where we can pay people properly." });
  }
  const band = age >= 18 ? "18_plus" : (age >= 16 ? "16_17" : "13_15");

  // Per-address throttle, so this route cannot be used as a spam cannon.
  let ip = "";
  try {
    const xff = String(e.request.header.get("X-Forwarded-For") || "");
    if (xff) ip = xff.split(",")[0].trim();
  } catch (_) {}
  if (!ip) { try { ip = e.realIP() || ""; } catch (_) {} }
  if (ip && ip !== "127.0.0.1" && ip !== "::1") {
    try {
      const recent = e.app.findRecordsByFilter("fellows", "ip_address = {:ip}", "-created", 30, 0, { ip: ip });
      let n = 0;
      for (const r of recent) {
        const t = Date.parse(String(r.getString("created")).replace(" ", "T"));
        if (!isNaN(t) && nowMs - t < 3600000) n++;
      }
      if (n >= 6) {
        return e.json(200, { ok: false,
          message: "That's a lot of signups from one place. Give it an hour." });
      }
    } catch (_) {}
  }

  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "email = {:em}", { em: email }); } catch (_) {}
  const isNew = !fellow;

  // REMOVAL HAS TO BE REMOVAL. Nothing outside the internal listing ever read
  // this status, so somebody taken out for spam or abuse could type the same
  // address back in, be handed a fresh session, re-apply, and — at 18+ — have
  // /fellows/apply set code_active back to true. Removal was undoable by the
  // person who was removed. The message deliberately does not confirm that an
  // address is on file; it routes to a human, which is the only correct way
  // back in.
  if (fellow && fellow.getString("status") === "removed") {
    return e.json(200, { ok: false,
      message: "We can't set that up from here. Write to hello@anticipy.ai and a person will sort it." });
  }
  if (!fellow) {
    try {
      fellow = new Record(e.app.findCollectionByNameOrId("fellows"));
      fellow.set("email", email);
      fellow.set("birth_month", bm);
      fellow.set("birth_year", by);
      fellow.set("clicks_total", 0);
      fellow.set("code_revoked", false);
      fellow.set("referral_code", makeCode());
      fellow.set("ip_address", ip);
      // HOW THEY GET PAID, DEFAULTED AT CREATION. Card is the default rail, the
      // only legal value under 18, and what the decision doc promises everyone —
      // so it is the ANSWER, not a question. Nothing but POST /fellows/payout-method
      // ever wrote this field, and the payout rail refused to send while it was
      // empty, so every fellow who never went looking for that route was
      // unpayable for the life of the programme.
      fellow.set("payout_method", "card");
    } catch (_) {
      return e.json(200, { ok: false, message: "Something went wrong. Try once more?" });
    }
  }
  if (name) fellow.set("name", name);
  fellow.set("age_band", band);
  fellow.set("country", country === "ca" ? "ca" : "us");
  // This used to be unconditional, so a minor whose guardian had ALREADY
  // completed the payout setup had that consent silently reset to pending by
  // the act of typing their own email address again. Turning 18 still clears
  // the requirement; nothing else touches a confirmed consent.
  if (band === "18_plus") fellow.set("parental_consent", "not_required");
  else if (fellow.getString("parental_consent") !== "confirmed") fellow.set("parental_consent", "pending");
  // NOT accepted here. Typing an email creates an ACCOUNT; the application is
  // what gets you in. The previous version stamped "accepted" and emailed
  // "you're in" the instant someone typed an address, which made every
  // question that followed theatre — and it was obvious to the first person
  // who used it.
  if (!fellow.getString("status")) fellow.set("status", "new");
  // The code exists immediately and counts clicks immediately. It only PAYS
  // once the address is confirmed — and, under 18, once a guardian has done
  // the payout setup. Only ever on a NEW row: unconditionally, this switched
  // OFF the payouts of an existing, confirmed, earning fellow the moment they
  // typed their email again.
  if (isNew) fellow.set("code_active", false);

  // Nothing mints a confirm token here any more. No email leaves at signup,
  // so the token created here could never reach anybody — but overwriting the
  // hash DID invalidate the confirm link already sitting in the inbox of
  // someone who signed up, got the welcome, and came back before tapping it.
  // That link is the payout switch. It is minted in /fellows/apply, where it
  // is actually written into an email.

  const token = randomToken();
  fellow.set("session_hash", sha256(token));
  fellow.set("session_expires", new Date(nowMs + 90 * 86400000).toISOString());
  try { e.app.save(fellow); } catch (_) {
    return e.json(200, { ok: false, message: "Something went wrong saving that. Try once more?" });
  }

  // The welcome email carries the confirm link. Not awaited-on for success:
  // a mail hiccup must never stand between someone and the first lesson.
  // No email at signup. Nothing has happened yet worth an email, and an
  // inbox arrival that says "you're in" before the questions is exactly the
  // incoherence being fixed. The welcome goes out from /fellows/apply, once
  // someone is actually in.
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", ""); act.set("actor_name", "Fellowships");
    act.set("action", "fellow.started");
    act.set("subject", (name || email) + " started a fellowship application");
    act.set("ref", fellow.get("id"));
    e.app.save(act);
  } catch (_) {}

  return e.json(200, {
    ok: true, token: token,
    fellow: {
      id: fellow.get("id"), email: email, name: fellow.getString("name"),
      age_band: band, country: fellow.getString("country"),
      // These three were hard-coded, so a member who was already in came back
      // looking brand new to the client — which walked them through the
      // picker, the four questions and the wait, and then told them "You're
      // in." about an account that was already in. The client branches on
      // status; the server has to tell it the truth for that to work.
      status: fellow.getString("status") || "new",
      fellowship: fellow.getString("fellowship") || "",
      referral_code: fellow.getString("referral_code"),
      code_active: !!fellow.get("code_active"),
      email_confirmed: !!fellow.getString("email_confirmed_at"),
    }
  });
});

// --------------------------------------------------------------------------
// GET /fellows/confirm?t=  — one tap in the welcome email. This is the only
// gate on money, and it is nowhere near the learning.
// --------------------------------------------------------------------------
routerAdd("GET", "/fellows/confirm", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const site = $os.getenv("ANTICIPY_SITE_URL") || "https://www.anticipy.ai";
  let t = "";
  try { t = String(e.requestInfo().query.t || ""); } catch (_) {}
  if (!t) return e.redirect(302, site + "/fellowships");
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "consent_token_hash = {:h}", { h: sha256(t) }); } catch (_) {}
  if (fellow) {
    fellow.set("email_confirmed_at", new Date().toISOString());
    fellow.set("consent_token_hash", "");
    // 18+ can be paid the moment their address is real. Under 18 still waits
    // on the guardian payout setup, which is the law, not our preference.
    if (fellow.getString("age_band") === "18_plus") fellow.set("code_active", true);
    try { e.app.save(fellow); } catch (_) {}
  }
  return e.redirect(302, site + "/fellowships?confirmed=1");
});

// --------------------------------------------------------------------------
// GET /fellows/me
// --------------------------------------------------------------------------
routerAdd("GET", "/fellows/me", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const token = e.request.header.get("X-Fellow-Token") || "";
  if (!token) return e.json(401, { reauth: true });
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "session_hash = {:h}", { h: sha256(token) }); } catch (_) {}
  // A removal signs them out, but a token that is still in flight must not
  // outlive it either. Belt and braces: the same status check on every route
  // that takes a session.
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(401, { reauth: true });
  const exp = Date.parse(fellow.getString("session_expires"));
  if (isNaN(exp) || Date.now() > exp) return e.json(401, { reauth: true });

  // Recompute the band on every read, so turning 16 or 18 takes effect on
  // its own without anyone running anything.
  const bm = Number(fellow.get("birth_month")), by = Number(fellow.get("birth_year"));
  if (bm && by) {
    const now = new Date();
    let age = now.getUTCFullYear() - by;
    if (now.getUTCMonth() + 1 < bm) age -= 1;
    const band = age >= 18 ? "18_plus" : (age >= 16 ? "16_17" : "13_15");
    if (band !== fellow.getString("age_band")) {
      fellow.set("age_band", band);
      if (band === "18_plus" && fellow.getString("parental_consent") !== "confirmed") {
        fellow.set("parental_consent", "not_required");
      }
      try { e.app.save(fellow); } catch (_) {}
    }
  }

  const done = [];
  try {
    const rows = e.app.findRecordsByFilter("fellow_progress", "fellow = {:f}", "+created", 500, 0, { f: fellow.get("id") });
    for (const r of rows) done.push(r.getString("lesson_id"));
  } catch (_) {}

  const conversions = [];
  try {
    const rows = e.app.findRecordsByFilter("fellow_conversions", "fellow = {:f}", "-created", 100, 0, { f: fellow.get("id") });
    for (const r of rows) conversions.push({
      status: r.getString("status"),
      commission_usd: Number(r.get("commission_usd")) || 0,
      created: r.getString("created"),
      hold_until: r.getString("hold_until"),
    });
  } catch (_) {}

  // The logbook, on the same call that already loads the dashboard. A second
  // round trip for a list this small would just be a second thing to fail.
  //
  // WHAT IS NOT IN HERE, and each absence is a decision rather than an
  // oversight:
  //   - no view count, because we cannot read one on any of the five platforms
  //     without asking a thirteen-year-old to connect an account to us. There
  //     is no field and no dash where a field would be.
  //   - no `unverified` and no `mismatch`. unverified is PERMANENT for
  //     Instagram and LinkedIn — neither will tell a server anything — so
  //     showing it would read as a mark against someone for using Instagram.
  //     mismatch would tell an attacker which check caught them. Only `gone`
  //     is surfaced, because "we couldn't find this when we looked" is useful
  //     to them and accuses them of nothing.
  //   - no count and no target anywhere. This is a logbook, not a scoreboard.
  const submissions = [];
  try {
    const rows = e.app.findRecordsByFilter("fellow_submissions",
      "fellow = {:f} && status != 'removed'", "-created", 50, 0, { f: fellow.get("id") });
    for (const r of rows) submissions.push({
      id: r.get("id"),
      platform: r.getString("platform"),
      kind: r.getString("kind"),
      url: r.getString("url"),
      title: r.getString("title"),
      thumbnail_url: r.getString("thumbnail_url"),
      note: r.getString("note"),
      verify_state: r.getString("verify_state") === "gone" ? "gone" : "",
      created: r.getString("created"),
    });
  } catch (_) {}

  return e.json(200, {
    ok: true,
    fellow: {
      id: fellow.get("id"), email: fellow.getString("email"), name: fellow.getString("name"),
      age_band: fellow.getString("age_band"), country: fellow.getString("country"),
      parental_consent: fellow.getString("parental_consent"),
      parent_email: fellow.getString("parent_email"),
      fellowship: fellow.getString("fellowship"), status: fellow.getString("status"),
      referral_code: fellow.getString("referral_code"),
      code_active: !!fellow.get("code_active"),
      clicks_total: Number(fellow.get("clicks_total")) || 0,
      instagram: fellow.getString("instagram"), tiktok: fellow.getString("tiktok"),
      x_handle: fellow.getString("x_handle"), linkedin: fellow.getString("linkedin"),
      // youtube joined the others in 1700000046. Without it a YouTube Short
      // could be logged and the author check would have nothing to compare
      // oEmbed's answer against, which is the same as having no check at all.
      youtube: fellow.getString("youtube"),
      payout_method: fellow.getString("payout_method"),
      sms_opt_in: !!fellow.get("sms_opt_in"),
    },
    progress: done,
    conversions: conversions,
    submissions: submissions,
  });
});

// --------------------------------------------------------------------------
// POST /fellows/apply  {fellowship, answers:{...}, terms:true}
//
// THE 25-SECOND REVIEW IS A REAL REVIEW.
//
// The founder wanted a beat where it looks like the system is thinking. The
// honest way to build that is to actually think: one cheap model call reads
// what they wrote and replies in their own terms. It costs about a tenth of a
// cent. Padding a fake wait would have been cheaper and would have been a lie
// the first time someone compared notes with a friend.
//
// It can answer `ask_more` — someone who typed "asdf" gets sent back to write
// one real sentence. Without that, "you're a really good fit" is something we
// say to everybody, which is the same as saying nothing.
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/apply", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const token = e.request.header.get("X-Fellow-Token") || "";
  if (!token) return e.json(401, { reauth: true });
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "session_hash = {:h}", { h: sha256(token) }); } catch (_) {}
  // A removal signs them out, but a token that is still in flight must not
  // outlive it either. Belt and braces: the same status check on every route
  // that takes a session.
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(401, { reauth: true });
  const sexp = Date.parse(fellow.getString("session_expires"));
  if (isNaN(sexp) || Date.now() > sexp) return e.json(401, { reauth: true });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const fellowship = String(body.fellowship || "growth").trim().toLowerCase();
  if (fellowship !== "growth") {
    return e.json(200, { ok: false, message: "That one isn't open yet. Growth & Marketing is the one taking people right now." });
  }
  if (body.terms !== true) {
    return e.json(200, { ok: false, message: "Have a read of the terms and tick the box, then we'll carry on." });
  }
  const answers = body.answers && typeof body.answers === "object" ? body.answers : {};
  const flat = Object.keys(answers).map((k) => k + ": " + String(answers[k] || "").slice(0, 1200)).join("\n");
  if (flat.length > 8000) return e.json(200, { ok: false, message: "That's a lot of words. Trim it a little and send again." });

  // already in?
  try {
    const prior = e.app.findFirstRecordByFilter("fellow_applications",
      "email = {:em} && fellowship = {:f} && ai_verdict != 'ask_more'",
      { em: fellow.getString("email"), f: fellowship });
    if (prior) {
      // This used to return no fellow object at all, so the acceptance screen
      // rendered for a returning member with no referral link and no money
      // section on it. Return the real record and let the client route them
      // to their dashboard rather than to a second acceptance.
      return e.json(200, { ok: true, verdict: "accept", already: true,
        message: "You're already in. Head straight to the lessons.",
        fellow: {
          status: fellow.getString("status") || "accepted",
          fellowship: fellow.getString("fellowship") || fellowship,
          referral_code: fellow.getString("referral_code"),
          code_active: !!fellow.get("code_active"),
          age_band: fellow.getString("age_band"),
          name: fellow.getString("name"),
        } });
    }
  } catch (_) {}

  // A deterministic sanity check that runs whether or not the model is up.
  const words = flat.replace(/\w+:/g, " ").trim().split(/\s+/).filter(Boolean);
  const realish = words.length >= 12 && /[aeiou]{1,}/i.test(flat) && !/^(.)\1+$/.test(flat.replace(/\s/g, ""));

  const band = fellow.getString("age_band");
  const firstName = String(fellow.getString("name") || "").trim().split(/\s+/)[0] || "there";

  let verdict = realish ? "fallback_accept" : "ask_more";
  let message = realish
    ? "You're in, " + firstName + ". You said what you wanted out of this and that's the whole bar — the rest we teach you."
    : "Give us one more real sentence — just what you actually want out of this. That's genuinely all we need.";
  let modelUsed = "", aiOk = false;

  const orKey = $os.getenv("OPENROUTER_API_KEY") || "";
  const ceiling = parseInt($os.getenv("ANTICIPY_FELLOW_LLM_CEILING") || "120", 10);
  const hourNow = new Date().toISOString().slice(0, 13);
  let metered = false;
  try {
    const meter = e.app.findFirstRecordByFilter("fellow_meter", "name = 'llm'");
    const used = meter.getString("hour") === hourNow ? (Number(meter.get("calls")) || 0) : 0;
    if (used < ceiling) { meter.set("hour", hourNow); meter.set("calls", used + 1); e.app.save(meter); metered = true; }
  } catch (_) {}

  if (orKey && metered) {
    const model = $os.getenv("ANTICIPY_FELLOW_MODEL") || "google/gemini-3.7-flash";
    const system = [
      "You read applications to a marketing fellowship at a tiny startup and reply to the applicant.",
      "The bar is LOW ON PURPOSE: anyone who wrote a real, honest answer gets in. We teach the rest.",
      "Reply 'ask_more' ONLY if the answers are empty, gibberish, keyboard-mash, or a joke — never because",
      "someone lacks experience, followers, or ambition. Having no experience is the normal case here.",
      "",
      "Write 2 or 3 sentences, to them, in plain words a 15-year-old reads without effort.",
      "Name something SPECIFIC they actually wrote — that is the whole point of reading it.",
      "Do not flatter. Do not say 'impressive' or 'passionate' or 'excited'. Do not mention money or",
      "earnings. Do not promise anything. No exclamation marks. Sentence case.",
      "Their first name is: " + firstName + ".",
      'Reply STRICT JSON: {"verdict":"accept"|"ask_more","message":"..."}'
    ].join("\n");
    try {
      const res = $http.send({
        url: "https://openrouter.ai/api/v1/chat/completions",
        method: "POST",
        headers: { "Authorization": "Bearer " + orKey, "Content-Type": "application/json",
                   "HTTP-Referer": "https://anticipy.ai", "X-Title": "Anticipy Fellowships" },
        body: JSON.stringify({
          model: model, temperature: 0.3, max_tokens: 2000,
          response_format: { type: "json_object" },
          messages: [{ role: "system", content: system }, { role: "user", content: flat }]
        }),
        timeout: 14,   // the client no longer pads the wait, so this IS the wait
      });
      let text = "";
      try { text = res.json.choices[0].message.content || ""; } catch (_) {}
      let parsed = null; try { parsed = JSON.parse(text); } catch (_) {}
      if (parsed && (parsed.verdict === "accept" || parsed.verdict === "ask_more") && parsed.message) {
        // A model must never be able to turn someone away for the WRONG
        // reason. If our own sanity check says the answers were real, an
        // ask_more from the model is overruled.
        verdict = (parsed.verdict === "ask_more" && realish) ? "accept" : parsed.verdict;
        message = String(parsed.message).slice(0, 600);
        modelUsed = model; aiOk = true;
      }
    } catch (_) {}
  }

  try {
    const a = new Record(e.app.findCollectionByNameOrId("fellow_applications"));
    a.set("fellow", fellow.get("id"));
    a.set("email", fellow.getString("email"));
    a.set("fellowship", fellowship);
    a.set("answers", flat.slice(0, 8000));
    a.set("ai_verdict", verdict);
    a.set("ai_message", message);
    a.set("ai_ok", aiOk);
    a.set("model", modelUsed);
    a.set("terms_accepted_at", new Date().toISOString());
    e.app.save(a);
  } catch (_) {}

  if (verdict === "ask_more") {
    // Reversible, and re-applying past it is expected. Recorded so HQ can see
    // where people stop instead of guessing.
    try { fellow.set("status", "needs_more"); e.app.save(fellow); } catch (_) {}
    return e.json(200, { ok: true, verdict: "ask_more", message: message });
  }

  // THE ORDER HERE IS NOT NEGOTIABLE, and it was wrong.
  //
  // It used to be: set status -> send the email -> save the fellow. The email
  // is the one side effect in this system that cannot be rolled back, and it
  // was happening FIRST. A crash between the send and the save mails "you're
  // in" to somebody whose row still says otherwise — which is the original
  // bug, moved one step later.
  //
  // Status is a consequence of a written application. Email is a consequence
  // of a written status. Never the reverse.
  fellow.set("fellowship", fellowship);
  fellow.set("status", "accepted");
  // 18+ can earn immediately. Under 18 cannot, until a parent has done the
  // payout setup — the learning is open either way, and the difference is
  // stated plainly on screen rather than discovered later.
  if (fellow.getString("age_band") === "18_plus") fellow.set("code_active", true);

  // Mint the confirm token before the save, so its hash and the raw value in
  // the email are written in the same breath. Only the hash is stored, so the
  // raw value exists exactly once — in the email — and cannot be recovered
  // from the database.
  const rk2 = $os.getenv("RESEND_API_KEY") || "";
  const site2 = $os.getenv("ANTICIPY_SITE_URL") || "https://www.anticipy.ai";
  const first = String(fellow.getString("name") || "").trim().split(/\s+/)[0];
  let confirmRaw = "";
  if (!fellow.getString("email_confirmed_at")) {
    const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    for (let i = 0; i < 48; i++) confirmRaw += chars.charAt(Math.floor(Math.random() * chars.length));
    fellow.set("consent_token_hash", sha256(confirmRaw));
  }

  // NOTHING LEAVES THE BUILDING UNTIL THIS RETURNS.
  try { e.app.save(fellow); }
  catch (err) {
    return e.json(200, { ok: false,
      message: "We couldn't save that. Nothing's lost — press it once more." });
  }

  // Guarded, so a retry, a double-click or a re-send cannot mail anyone twice.
  if (rk2 && !fellow.getString("welcome_sent_at")) {
    const confirmLine = confirmRaw
      ? "\n\nWhen you're ready to get paid, tap this once so we know the address is yours:\n"
        + site2 + "/fellows/confirm?t=" + confirmRaw
      : "";
    let sent = false;
    try {
      const r = $http.send({
        url: "https://api.resend.com/emails", method: "POST",
        headers: { "Authorization": "Bearer " + rk2, "Content-Type": "application/json" },
        body: JSON.stringify({
          from: "Anticipy Fellowships <notifications@aevoy.com>",
          to: [fellow.getString("email")],
          // CAN-SPAM: this is transactional — it confirms a relationship the
          // recipient initiated — so it is exempt from the opt-out and postal
          // address requirements. The subject line still may not mislead, and
          // "you're in" is only non-misleading if they are, in fact, in. The
          // save above is what makes that true.
          subject: (first ? first + ", you're in" : "You're in"),
          text: (first ? first + ", you're in." : "You're in.")
            + "\n\nStart here — unit 0 is five minutes and it's just what this thing is.\n"
            + site2 + "/fellowship-growth-learning"
            + "\n\nYour link, for when you start posting:\n"
            + site2 + "/r/" + fellow.getString("referral_code")
            + "\n\n$30 when someone buys through it. $15 clears 14 days after they buy, and the"
            + "\nother $15 when their pendant actually ships — pendants ship late 2026, so that"
            + "\nhalf is a real wait. We split it so a refund never takes money back out of your"
            + "\naccount."
            + confirmLine
            + "\n\nThat's everything. Go make something."
        }),
        timeout: 15,
      });
      sent = r.statusCode >= 200 && r.statusCode < 300;
    } catch (_) {}
    if (sent) {
      fellow.set("welcome_sent_at", new Date().toISOString());
      try { e.app.save(fellow); } catch (_) {}
    }
  }

  // Tell HQ, so a real person knows someone joined.
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", ""); act.set("actor_name", "Fellowships");
    act.set("action", "fellow.joined");
    act.set("subject", (fellow.getString("name") || fellow.getString("email")) + " joined the Growth fellowship");
    act.set("ref", fellow.get("id"));
    e.app.save(act);
  } catch (_) {}

  return e.json(200, {
    ok: true, verdict: "accept", message: message,
    fellow: { status: "accepted", fellowship: fellowship,
              referral_code: fellow.getString("referral_code"),
              code_active: !!fellow.get("code_active"),
              age_band: fellow.getString("age_band") }
  });
});

// --------------------------------------------------------------------------
// POST /fellows/progress  {lesson_id} or {lessons:[...]}
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/progress", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const token = e.request.header.get("X-Fellow-Token") || "";
  if (!token) return e.json(401, { reauth: true });
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "session_hash = {:h}", { h: sha256(token) }); } catch (_) {}
  // A removal signs them out, but a token that is still in flight must not
  // outlive it either. Belt and braces: the same status check on every route
  // that takes a session.
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(401, { reauth: true });
  const sexp = Date.parse(fellow.getString("session_expires"));
  if (isNaN(sexp) || Date.now() > sexp) return e.json(401, { reauth: true });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  let ids = [];
  if (Array.isArray(body.lessons)) ids = body.lessons;
  else if (body.lesson_id) ids = [body.lesson_id];
  ids = ids.map((x) => String(x || "").trim()).filter((x) => /^[a-z0-9-]{3,60}$/.test(x)).slice(0, 60);
  if (!ids.length) return e.json(200, { ok: true, saved: 0 });

  let count = 0;
  try {
    const existing = e.app.findRecordsByFilter("fellow_progress", "fellow = {:f}", "+created", 500, 0, { f: fellow.get("id") });
    if (existing.length >= 500) return e.json(200, { ok: true, saved: 0 });
    const have = {};
    for (const r of existing) have[r.getString("lesson_id")] = true;
    const col = e.app.findCollectionByNameOrId("fellow_progress");
    for (const id of ids) {
      if (have[id]) continue;
      const r = new Record(col);
      r.set("fellow", fellow.get("id"));
      r.set("lesson_id", id);
      r.set("completed_at", new Date().toISOString());
      try { e.app.save(r); count++; } catch (_) {}
    }
  } catch (_) {}
  return e.json(200, { ok: true, saved: count });
});

// --------------------------------------------------------------------------
// POST /fellows/profile  {name?, instagram?, tiktok?, x_handle?, linkedin?, phone?, sms_opt_in?}
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/profile", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const token = e.request.header.get("X-Fellow-Token") || "";
  if (!token) return e.json(401, { reauth: true });
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "session_hash = {:h}", { h: sha256(token) }); } catch (_) {}
  // A removal signs them out, but a token that is still in flight must not
  // outlive it either. Belt and braces: the same status check on every route
  // that takes a session.
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(401, { reauth: true });
  const sexp = Date.parse(fellow.getString("session_expires"));
  if (isNaN(sexp) || Date.now() > sexp) return e.json(401, { reauth: true });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const band = fellow.getString("age_band");

  if ("name" in body) fellow.set("name", String(body.name || "").trim().slice(0, 120));
  // youtube is here rather than in its own branch because it needs exactly the
  // same treatment: strip a leading @, cap it, store it. It is the handle the
  // submissions route compares oEmbed's answer against for a YouTube Short.
  for (const k of ["instagram", "tiktok", "x_handle", "youtube"]) {
    if (k in body) fellow.set(k, String(body[k] || "").trim().replace(/^@/, "").slice(0, 200));
  }
  if ("linkedin" in body) {
    // LinkedIn's own floor is 16. We never point someone at an account they
    // are not allowed to have.
    if (band === "13_15") return e.json(200, { ok: false, message: "LinkedIn's own rules start at 16, so we'll skip that one for now." });
    fellow.set("linkedin", String(body.linkedin || "").trim().slice(0, 200));
  }
  if ("phone" in body) {
    const ph = String(body.phone || "").trim().replace(/[\s()-]/g, "");
    if (ph && !/^\+?\d{8,15}$/.test(ph)) return e.json(200, { ok: false, message: "That number doesn't look right — include the country code." });
    fellow.set("phone", ph);
  }
  if ("sms_opt_in" in body) {
    // Texts are 18+ only, and this is the first of the two places that
    // enforce it. The send helper checks again.
    if (body.sms_opt_in === true && band !== "18_plus") {
      return e.json(200, { ok: false, message: "We only text fellows who are 18 or over. Email works for everything." });
    }
    fellow.set("sms_opt_in", body.sms_opt_in === true);
  }
  try { e.app.save(fellow); } catch (_) {
    return e.json(200, { ok: false, message: "That didn't save. Try once more?" });
  }
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// GET /r/{code} — the minted link. It must NEVER dead-end: an unknown or
// revoked code still sends the visitor to the site, it just isn't credited.
// --------------------------------------------------------------------------
routerAdd("GET", "/r/{code}", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const site = $os.getenv("ANTICIPY_SITE_URL") || "https://anticipy.ai";
  // Two ways to read the code, because this is the first route in the codebase
  // to use a path parameter and a wrong guess about the JSVM's API would mean
  // every referral link silently stops crediting anyone. The fallback reads it
  // straight off the URL, which cannot be wrong.
  let raw = "";
  try { raw = String(e.request.pathValue("code") || ""); } catch (_) {}
  if (!raw) {
    try {
      const path = String(e.request.url.path || e.request.url || "");
      const m = path.match(/\/r\/([^\/?#]+)/);
      if (m) raw = decodeURIComponent(m[1]);
    } catch (_) {}
  }
  // Normalise exactly as anticipy.ai's checkout does, so a code survives the
  // whole round trip — link, cookie, Stripe metadata, webhook — unchanged.
  raw = raw.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 24);
  const clean = /^[a-z0-9-]{4,24}$/.test(raw) ? raw : "";

  if (clean) {
    try {
      const fellow = e.app.findFirstRecordByFilter("fellows", "referral_code = {:c}", { c: clean });
      if (fellow && !fellow.get("code_revoked")) {
        // Same reasoning as the throttle: behind the anticipy.ai rewrite,
        // realIP() is Vercel for everyone, so per-visitor click dedupe would
        // collapse into "one click per code per hour, globally" and a fellow
        // would be credited once no matter how many people tapped.
        let ip = "";
        try {
          const xff = String(e.request.header.get("X-Forwarded-For") || "");
          if (xff) ip = xff.split(",")[0].trim();
        } catch (_) {}
        if (!ip) { try { ip = e.realIP() || ""; } catch (_) {} }
        const salt = $os.getenv("ANTICIPY_FELLOW_SALT") || "anticipy-fellows";
        const ipHash = ip ? sha256(ip + salt) : "";
        // One click per code per address per hour, so a refresh loop cannot
        // inflate anyone's numbers.
        let dupe = false;
        if (ipHash) {
          try {
            const recent = e.app.findRecordsByFilter("fellow_clicks",
              "code = {:c} && ip_hash = {:h}", "-created", 1, 0, { c: clean, h: ipHash });
            if (recent[0]) {
              const t = Date.parse(String(recent[0].getString("created")).replace(" ", "T"));
              if (!isNaN(t) && Date.now() - t < 3600000) dupe = true;
            }
          } catch (_) {}
        }
        if (!dupe) {
          try {
            const c = new Record(e.app.findCollectionByNameOrId("fellow_clicks"));
            c.set("code", clean); c.set("ip_hash", ipHash);
            c.set("ua", String(e.request.header.get("User-Agent") || "").slice(0, 200));
            e.app.save(c);
            fellow.set("clicks_total", (Number(fellow.get("clicks_total")) || 0) + 1);
            e.app.save(fellow);
          } catch (_) {}
        }
      }
    } catch (_) {}
  }
  const url = site + "/?ref=" + encodeURIComponent(clean || "") +
              "&utm_source=fellow&utm_medium=referral&utm_campaign=" + encodeURIComponent(clean || "none");
  try {
    return e.redirect(302, url);
  } catch (_) {
    // If redirect() is not what this runtime calls it, send a tiny page that
    // goes to the same place. A referral link must never show an error.
    e.response.header().set("Content-Type", "text/html; charset=utf-8");
    return e.html(200,
      '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=' + url + '">'
      + '<title>Anticipy</title><p>Taking you to Anticipy… <a href="' + url + '">tap here</a> if nothing happens.</p>');
  }
});

// --------------------------------------------------------------------------
// POST /fellows/submissions  {url, note?}
//
// THE LOGBOOK. A fellow pastes the link to something they made and it is kept.
//
// WHAT THIS IS NOT: it is not a quota, a target, or a thing that pays. Money
// comes from fellow_conversions, which come from a purchase through /r/<code>,
// which needs a click on their own link. Logging a video earns exactly $0 —
// which is what makes pasting a stranger's viral video pointless, and is the
// reason the defences below can be as light as they are. Nothing in this route
// or on any screen it feeds may ever read as something they have to do.
//
// WE STORE ONLY WHAT WE VERIFIED. There is no view count here, no like count,
// and no dash where one would go. Reading views on any of the five platforms
// needs the fellow to grant an app permission on their own account — a token
// we would then hold, for a vanity number. So the screen shows the numbers we
// actually own (clicks, sales) and says plainly why the other one is absent.
//
// THREE PLATFORMS WILL TELL US WHO MADE IT; TWO WILL NOT, EVER. TikTok,
// YouTube and X all answer an unauthenticated oEmbed call with the TRUE author
// — TikTok and X even correct a deliberately wrong handle in the pasted URL,
// which is exactly why the handle in an address bar is treated as a claim and
// never as a fact. Instagram serves a logged-out server a shell with no og:
// tags and its oEmbed needs a reviewed Meta app; LinkedIn has no oEmbed at all
// and answers a machine with HTTP 999. Those two are `unverified` forever, and
// that word is never shown to a fellow — it would be a scarlet letter for
// using Instagram.
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/submissions", (e) => {
  // JSVM ISOLATION: a helper at file top-level is not visible in here. Every
  // one of these is redeclared on purpose. Do not tidy them out.
  const sha256 = (s) => $security.sha256(s);
  const pbTime = (v) => {
    if (!v) return NaN;
    let t = String(v).trim().replace(" ", "T");
    if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(t)) t += "Z";
    return new Date(t).getTime();
  };
  // Everything that comes off a person or off a third party goes through this
  // before it touches a column: control characters out, length capped. The
  // HTML escaping happens again at every render site — this is the belt, that
  // is the braces.
  const scrub = (s, n) => String(s == null ? "" : s)
    .replace(/[\u0000-\u001F\u007F]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
  const nowISO = new Date().toISOString();

  const token = e.request.header.get("X-Fellow-Token") || "";
  if (!token) return e.json(401, { reauth: true });
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "session_hash = {:h}", { h: sha256(token) }); } catch (_) {}
  // A removal signs them out, but a token that is still in flight must not
  // outlive it either. Belt and braces: the same status check on every route
  // that takes a session.
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(401, { reauth: true });
  const sexp = Date.parse(fellow.getString("session_expires"));
  if (isNaN(sexp) || Date.now() > sexp) return e.json(401, { reauth: true });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const pasted = String(body.url == null ? "" : body.url);
  const note = scrub(body.note, 500);
  // The age band is read here because the parser takes it: LinkedIn's own
  // minimum age is 16 and a 13-15 fellow is not offered it anywhere.
  const band = fellow.getString("age_band");

  // ==== fellowship url parser 8<==========================================
  // tests/test_fellowship_submissions.mjs slices the source between this
  // marker and its closing twin and runs it in a vm, so the table of real URL
  // shapes below is EXECUTED against real URLs rather than grepped for. Keep
  // both markers, and keep this block closed over nothing outside itself.
  const parseSubmittedUrl = (input, ageBand) => {
    // LINKEDIN'S OWN MINIMUM AGE IS 16, so a 13-15 fellow is never offered it.
    // Not in the sentence that lists where we track — naming a platform they
    // are not allowed to join is an invitation to go and join it — and not in
    // the parser either. This is the FIRST of the two places that enforce it;
    // the route checks again after the parse returns, which is the same
    // belt-and-braces shape sms_opt_in already has.
    const UNDER_16 = ageBand === "13_15";
    const PLATFORMS = UNDER_16
      ? "TikTok, Instagram, YouTube and X"
      : "TikTok, Instagram, YouTube, X and LinkedIn";

    // parse1 does the whole job once. parseSubmittedUrl then runs it a SECOND
    // time over its own canonical output — see the bottom of this block.
    const parse1 = (input2) => {
      const no = (code, message, platform) =>
        ({ ok: false, code: code, message: message, platform: platform || "" });
      // EVERY NUMERIC ID IS NORMALISED BEFORE IT CAN BECOME A KEY. A pasted
      // urn:li:activity:0712... and urn:li:activity:712... are ONE post, and
      // so are x.com/jack/status/020 and .../status/20 — both resolve, on
      // both platforms, and without this both would mint a second url_key for
      // a post that already has one, which is a duplicate hole and a way to
      // walk straight past the unique index. Leading zeros out; an id that is
      // all zeros stays "0" rather than becoming the empty string.
      const num = (s) => { const t = String(s).replace(/^0+/, ""); return t === "" ? "0" : t; };

      // ---- 1. the normalisation preamble, before any regex sees anything --
      let u = String(input2 == null ? "" : input2).trim();
      if (!u) {
        return no("junk", "Paste the link to what you made. We track " + PLATFORMS + ".");
      }
      if (u.length > 2048) {
        return no("junk", "That's far too long to be a link — paste just the address of the post.");
      }
      // A share sheet on a phone really does hand over zero-width joiners, and
      // an RTL keyboard really does add bidi marks. They are invisible on
      // screen and they break every regex below.
      u = u.replace(/[\u200B-\u200D\u2060\uFEFF\u202A-\u202E\u2066-\u2069]/g, "");
      // Anything declaring a scheme we do not serve is refused before it can
      // reach a regex at all: javascript:, data:, mailto:, ftp:.
      const scheme = u.match(/^([A-Za-z][A-Za-z0-9+.\-]*):/);
      if (scheme && !/^https?$/i.test(scheme[1])) {
        return no("junk", "That isn't a web link. Paste the address of the post, starting with https.");
      }
      if (!/^https?:\/\//i.test(u)) u = "https://" + u;
      // Upgrades http AND lowercases the scheme in one step. Both halves
      // matter: every pattern below is anchored on a literal lowercase
      // "https://", so a pasted "HTTPS://WWW.YOUTUBE.COM/..." — which is what
      // a desktop address bar gives you if you type it in caps — would
      // otherwise fall through every single one of them and be refused as junk.
      u = u.replace(/^https?:\/\//i, "https://");

      // LOWERCASE THE SCHEME AND HOST ONLY, NEVER THE PATH. YouTube ids
      // (dQw4w9WgXcQ) and Instagram shortcodes are case-sensitive; a blanket
      // toLowerCase() turns every one of them into a 404, and the failure then
      // looks like the platform being down instead of like our bug.
      const split = u.match(/^https:\/\/([^\/?#]+)(.*)$/);
      if (!split || !split[1]) {
        return no("junk", "That doesn't look like a link. Paste the whole thing, starting with https. We track " + PLATFORMS + ".");
      }
      let host = split[1].toLowerCase();
      let rest = split[2] || "";
      // The authority may contain a hostname and nothing else. This one line
      // is what refuses https://tiktok.com@evil.com/... , where the real host
      // is evil.com and every host pattern below would otherwise be reading a
      // username. It also refuses ports, IPv6 literals and unicode homographs.
      if (!/^[a-z0-9.\-]+$/.test(host)) {
        return no("junk", "There's something odd in that address. Copy it again from the post itself.");
      }
      // "not-a-url", "hello", "my video" — anything with no dot in it is not a
      // hostname, and calling it an unknown PLATFORM would be the wrong
      // sentence. It is a bad request and it gets a 400.
      if (host.indexOf(".") < 0) {
        return no("junk", "That doesn't look like a link. Paste the whole thing, starting with https. We track " + PLATFORMS + ".");
      }
      rest = rest.split("#")[0];                       // the fragment is never ours
      host = host.replace(/^(?:www|m|mobile)\./, "");
      if (host === "instagr.am") host = "instagram.com";
      if (host === "twitter.com") host = "x.com";
      const url = "https://" + host + rest;

      // ---- 1b. the one platform an age band can remove from the table -----
      // Refused here, before any LinkedIn pattern is even considered, so that
      // no LinkedIn url_key can be written for a thirteen-year-old by any
      // path through this parser. The sentence is the same one /fellows/me
      // gives when they try to add a LinkedIn profile: it is about LinkedIn's
      // rule, not about them, and it does not accuse them of anything.
      if (UNDER_16 && (host === "linkedin.com" || host === "lnkd.in")) {
        return no("age", "LinkedIn's own rules start at 16, so we'll skip that one for now.", "linkedin");
      }

      // ---- 2. the table. Every shape each platform actually produces ------
      //
      // EVERY pattern is anchored ^https:\/\/ with escaped-dot hosts. That
      // anchor plus the escaped dots is the entire defence against
      // tiktok.com.evil.com (a dot where a slash must be), eviltiktok.com (a
      // prefix in front of the anchor), and https://evil.com/?x=https://
      // tiktok.com/@a/video/1 (the real host comes first and does not match).
      // The trailing (?:[\/?]|$) is not decoration either: without it a
      // 40-digit id would match on its first 25 digits, and two different
      // posts could then collide on one key.
      //
      // TikTok       /@user/video/<19 digits>   the desktop and app share form
      //              /@user/photo/<id>          a slideshow post
      //              m.tiktok.com/v/<id>.html   the old mobile form, no handle
      //              ?is_from_webapp=1&sender_device=pc&_r=1&_t=...  junk tail
      const TIKTOK_POST  = /^https:\/\/tiktok\.com\/@([A-Za-z0-9._]{1,24})\/(video|photo)\/(\d{6,25})(?:[\/?]|$)/;
      const TIKTOK_V     = /^https:\/\/tiktok\.com\/v\/(\d{6,25})(?:\.html)?(?:[\/?]|$)/;
      // The three TikTok short forms. Matched only so they can be refused with
      // a sentence that tells the person what to do instead.
      const TIKTOK_SHORT = /^https:\/\/(?:vm|vt)\.tiktok\.com\/[A-Za-z0-9]{4,24}/;
      const TIKTOK_T     = /^https:\/\/tiktok\.com\/t\/[A-Za-z0-9]{4,24}/;
      // Instagram    /p/<code>/  /reel/<code>/  /reels/<code>/  /tv/<code>/
      //              /<username>/p/<code>/   /<username>/reel/<code>/
      //              ?igsh=  ?igshid=  ?img_index=   instagr.am/p/<code>/
      const INSTAGRAM    = /^https:\/\/instagram\.com\/(?:([A-Za-z0-9._]{1,30})\/)?(p|reel|reels|tv)\/([A-Za-z0-9_-]{5,24})(?:[\/?]|$)/;
      // YouTube      /shorts/<11>  /watch?v=<11>  /live/<11>  /embed/<11>
      //              /v/<11>  youtu.be/<11>   ?si=  &feature=  &t=  &pp=
      const YT_BE        = /^https:\/\/youtu\.be\/([A-Za-z0-9_-]{11})(?:[\/?]|$)/;
      const YT_PATH      = /^https:\/\/youtube\.com\/(shorts|embed|live|v)\/([A-Za-z0-9_-]{11})(?:[\/?]|$)/;
      const YT_WATCH     = /^https:\/\/youtube\.com\/watch\?(?:[^#]*&)?v=([A-Za-z0-9_-]{11})(?:&|$)/;
      // X            x.com/<handle>/status/<id>   twitter.com/... (rewritten)
      //              .../status/<id>/photo/1   ?s=20&t=...  ?ref_src=
      // \d{1,25} rather than a higher floor: today's ids are 19 digits, but
      // x.com/jack/status/20 is the oldest post on the platform and is a real,
      // live, two-digit URL. A floor tuned to modern ids refuses it.
      const X_STATUS     = /^https:\/\/x\.com\/([A-Za-z0-9_]{1,15})\/status(?:es)?\/(\d{1,25})(?:[\/?]|$)/;
      const X_SHORT      = /^https:\/\/t\.co\/[A-Za-z0-9]{4,24}/;
      // LinkedIn     /posts/<vanity>_<words>-activity-<19 digits>-<4 chars>/
      //              /feed/update/urn:li:activity:<id>/
      //              /feed/update/urn:li:share:<id>   .../urn:li:ugcPost:<id>
      //              /pulse/<slug>  ?trackingId= ?rcm= ?lipi= ?originalSubdomain=
      const LI_POSTS     = /^https:\/\/linkedin\.com\/posts\/[^\/?#]*?activity-(\d{10,25})/;
      const LI_UPDATE    = /^https:\/\/linkedin\.com\/feed\/update\/urn:li:(?:activity|share|ugcPost):(\d{10,25})/;
      // THE PULSE SLUG IS CUT TO THE NARROWEST COLUMN IT HAS TO FIT IN.
      // The slug becomes BOTH native_id (max 80) and the tail of url_key
      // ("linkedin:pulse:" is 15 characters, url_key is max 120, so the slug
      // has 105 there). 80 is the tighter of the two and is therefore the
      // number, because a capture wider than a column does not fail loudly —
      // SQLite/PocketBase would truncate on the way in, and a truncated
      // url_key is a KEY FOR A DIFFERENT ARTICLE: two Pulse posts sharing
      // their first 105 characters would collide on one key and the second
      // author would be told, wrongly, that somebody else already has it.
      const LI_PULSE     = /^https:\/\/linkedin\.com\/pulse\/([A-Za-z0-9\-]{3,80})(?:[\/?]|$)/;
      // Longer than that is matched only so it can be refused in a sentence
      // that says what actually happened and where to go, rather than falling
      // through to "that points at a profile or a page", which would be false.
      const LI_PULSE_LONG = /^https:\/\/linkedin\.com\/pulse\/[A-Za-z0-9\-]{81,}/;
      const LI_SHORT     = /^https:\/\/lnkd\.in\/[A-Za-z0-9_\-]{3,24}/;

      // ---- 3. short links are REFUSED, not resolved -----------------------
      //
      // Three measured reasons, and each on its own is enough. (a) An invalid
      // vm.tiktok.com code 302s to the TikTok HOMEPAGE rather than erroring,
      // so a resolver "successfully" resolves a dead link into a link to
      // nothing. (b) $http.send follows redirects and exposes neither the
      // final URL nor an intermediate Location header, so a hook cannot read a
      // redirect target without downloading the destination page into a bot
      // wall from Railway's IP. (c) TikTok's own oEmbed returns 400 for every
      // short form, so even a resolved link buys no verification.
      //
      // And it matters beyond tidiness: TikTok mints a FRESH vm code every
      // time a video is shared, so storing short links means one video has
      // unlimited distinct keys and dedupe silently stops working.
      //
      // youtu.be is the sole exception, because the id is already in the path
      // and no network call is needed to read it.
      if (TIKTOK_SHORT.test(url) || TIKTOK_T.test(url)) {
        return no("short", "That's TikTok's short link — it doesn't say which video it is. Open it, then use Copy link from the video page; the one you want has your @name in it.", "tiktok");
      }
      if (X_SHORT.test(url)) {
        return no("short", "That's a t.co link, which doesn't say which post it is. Open it and copy the address from the top of the page.", "x");
      }
      if (LI_SHORT.test(url)) {
        return no("short", "That's an lnkd.in short link, which doesn't say which post it is. Open it and copy the address from the top of the page.", "linkedin");
      }

      // ---- 4. the match, and the canonical form built from it -------------
      //
      // THE CANONICAL URL IS REBUILT FROM THE PARSED ID, NEVER EDITED DOWN
      // FROM WHAT WAS PASTED. That is what strips tracking parameters: not a
      // list of parameters to remove — which is a list somebody has to
      // maintain, and which is wrong the week a platform adds one — but the
      // fact that nothing from the query string is carried across at all. The
      // only parameter that survives anywhere is YouTube's `v`, and it
      // survives as a captured id rather than as a parameter. For the record,
      // the junk this drops without ever naming it: is_from_webapp,
      // sender_device, sender_web_id, web_id, _r, _t, checksum, share_app_id,
      // share_item_id, share_link_id, igsh, igshid, img_index, si, feature, t,
      // pp, ab_channel, s, ref_src, ref_url, trackingId, rcm, lipi, licu,
      // originalSubdomain, and every utm_*.
      let m;
      if ((m = url.match(TIKTOK_POST))) {
        const handle = m[1], id = num(m[3]);
        return { ok: true, platform: "tiktok", kind: m[2] === "photo" ? "photo" : "video",
                 native_id: id, url_key: "tiktok:" + id, author_claimed: handle,
                 url: "https://www.tiktok.com/@" + handle + "/video/" + id,
                 probe_url: "https://www.tiktok.com/@" + handle + "/video/" + id };
      }
      if ((m = url.match(TIKTOK_V))) {
        const id = num(m[1]);
        // No handle in this shape, so the canonical stays the /v/ form — a URL
        // that genuinely resolves. Inventing an @name we do not know would be
        // storing something we never verified. The oEmbed PROBE uses @i,
        // because the handle there is provably decorative (a deliberately
        // wrong handle still returns the true author), and that probe URL is
        // never stored.
        return { ok: true, platform: "tiktok", kind: "video",
                 native_id: id, url_key: "tiktok:" + id, author_claimed: "",
                 url: "https://www.tiktok.com/v/" + id + ".html",
                 probe_url: "https://www.tiktok.com/@i/video/" + id };
      }
      if ((m = url.match(INSTAGRAM))) {
        const user = m[1] || "", surface = m[2], code = m[3];
        const isReel = surface === "reel" || surface === "reels";
        // THE SURFACE IS NOT IN THE KEY. /p/<code> and /reel/<code> serve the
        // same post, so putting it in would let anyone log one reel twice by
        // editing a single word.
        return { ok: true, platform: "instagram",
                 kind: isReel ? "reel" : (surface === "tv" ? "video" : "post"),
                 native_id: code, url_key: "instagram:" + code, author_claimed: user,
                 url: "https://www.instagram.com/" + (isReel ? "reel" : "p") + "/" + code + "/",
                 probe_url: "" };
      }
      if ((m = url.match(YT_BE))) {
        const id = m[1];
        return { ok: true, platform: "youtube", kind: "video", native_id: id,
                 url_key: "youtube:" + id, author_claimed: "",
                 url: "https://www.youtube.com/watch?v=" + id,
                 probe_url: "https://www.youtube.com/watch?v=" + id };
      }
      if ((m = url.match(YT_PATH))) {
        const surface = m[1], id = m[2];
        const canon = surface === "shorts"
          ? "https://www.youtube.com/shorts/" + id
          : "https://www.youtube.com/watch?v=" + id;
        // ONE key regardless of surface: /shorts/X and /watch?v=X are the same
        // video, and two keys would be a duplicate hole wide enough to drive
        // the whole logbook through.
        return { ok: true, platform: "youtube", kind: surface === "shorts" ? "short" : "video",
                 native_id: id, url_key: "youtube:" + id, author_claimed: "",
                 url: canon, probe_url: canon };
      }
      if ((m = url.match(YT_WATCH))) {
        const id = m[1];
        return { ok: true, platform: "youtube", kind: "video", native_id: id,
                 url_key: "youtube:" + id, author_claimed: "",
                 url: "https://www.youtube.com/watch?v=" + id,
                 probe_url: "https://www.youtube.com/watch?v=" + id };
      }
      if ((m = url.match(X_STATUS))) {
        const handle = m[1], id = num(m[2]);
        // The handle here is a CLAIM. oEmbed returns the real one and that is
        // what lands in author_handle; this value only ever lands in
        // author_claimed.
        return { ok: true, platform: "x", kind: "post", native_id: id,
                 url_key: "x:" + id, author_claimed: handle,
                 url: "https://x.com/" + handle + "/status/" + id,
                 probe_url: "https://x.com/" + handle + "/status/" + id };
      }
      if ((m = url.match(LI_POSTS)) || (m = url.match(LI_UPDATE))) {
        const id = num(m[1]);
        // Canonicalised to the urn form on purpose: the /posts/ slug carries
        // the author's vanity name and stops resolving the day they rename.
        return { ok: true, platform: "linkedin", kind: "post", native_id: id,
                 url_key: "linkedin:" + id, author_claimed: "",
                 url: "https://www.linkedin.com/feed/update/urn:li:activity:" + id + "/",
                 probe_url: "" };
      }
      if ((m = url.match(LI_PULSE))) {
        const slug = m[1];
        return { ok: true, platform: "linkedin", kind: "article", native_id: slug,
                 url_key: "linkedin:pulse:" + slug, author_claimed: "",
                 url: "https://www.linkedin.com/pulse/" + slug, probe_url: "" };
      }
      if (LI_PULSE_LONG.test(url)) {
        return no("too_long",
          "That article's address is longer than we can store. Paste the post you shared it in, or send it to hello@anticipy.ai and a person will add it by hand.",
          "linkedin");
      }

      // ---- 5. a platform we know, but not a post --------------------------
      // "We only track five platforms" would be a lie here and would send them
      // hunting for a sixth. Name the one they used and say what is wrong.
      const KNOWN = { "tiktok.com": "TikTok", "instagram.com": "Instagram",
                      "youtube.com": "YouTube", "youtu.be": "YouTube",
                      "x.com": "X", "linkedin.com": "LinkedIn" };
      if (KNOWN[host]) {
        return no("not_a_post",
          "That's a " + KNOWN[host] + " link, but it points at a profile or a page rather than at one post. Open the post itself and copy the address from there.",
          host === "youtu.be" ? "youtube" : host.replace(/\.com$/, ""));
      }

      // ---- 6. everything else ---------------------------------------------
      return no("unknown", "We only track " + PLATFORMS + " right now. If you made it somewhere else, tell us at hello@anticipy.ai — we'd genuinely like to know where you're posting.");
    };

    const first = parse1(input);
    if (!first.ok) return first;
    // RE-PARSE OUR OWN OUTPUT AND REQUIRE IT TO MATCH. A canonicaliser that
    // can emit something its own parser rejects will one day emit a URL that
    // points somewhere else — and that URL is the one we render as a link. A
    // canonical form has to be a fixed point of the parser or it is not
    // canonical. Compared on platform, key and URL; NOT on kind, because
    // /tv/<code> canonicalises to /p/<code> and changes kind on the way, which
    // is correct.
    const again = parse1(first.url);
    if (!again.ok || again.platform !== first.platform ||
        again.url_key !== first.url_key || again.url !== first.url) {
      return { ok: false, code: "junk", platform: first.platform,
               message: "We couldn't pin that down to a single post. Open it and copy the address from the top of the page." };
    }
    return first;
  };
  // ========================================================>8 end parser ===

  const p = parseSubmittedUrl(pasted, band);
  if (!p.ok) {
    // Junk gets a 400 because it IS a bad request, and because leg 5 of
    // fellowship_gate.py checks that this route refuses a junk link rather
    // than swallowing it. Everything else is a 200 with ok:false — the house
    // shape for "we understood you and the answer is no" — carrying `field` so
    // the input can highlight itself, exactly as /fellows/start does with
    // {ok:false, field:"email"}.
    if (p.code === "junk") return e.json(400, { ok: false, field: "url", message: p.message });
    return e.json(200, { ok: false, field: "url", message: p.message });
  }

  // ---- LinkedIn, enforced a SECOND time, here ------------------------------
  // The parser already refuses it for a 13-15 fellow. This is the wall behind
  // that wall, and it exists for the same reason the sms_opt_in rule is
  // checked in the route AND again in the send helper: the parser is a block
  // of source that a test slices out and runs on its own, so it is exactly the
  // kind of code that gets edited by somebody who cannot see this route. A
  // LinkedIn key must never be written for a thirteen-year-old.
  if (p.platform === "linkedin" && band === "13_15") {
    return e.json(200, { ok: false, field: "url",
      message: "LinkedIn's own rules start at 16, so we'll skip that one for now." });
  }

  // ---- and nothing wider than the column it lands in ------------------------
  // The parser's captures are already cut to these widths. This is the second
  // wall, and it refuses rather than truncating on purpose: a url_key that got
  // shortened on the way into the column is a key for a DIFFERENT post, and
  // the unique index would then be enforcing a lie — locking out an author
  // whose article merely shares a prefix with somebody else's.
  if (p.url_key.length > 120 || p.native_id.length > 80 || p.url.length > 500) {
    return e.json(200, { ok: false, field: "url",
      message: "That address is longer than we can store. Send it to hello@anticipy.ai and a person will add it by hand." });
  }

  // ---- a claimed handle first, on the platforms we can actually check -----
  // Without one there is nothing to compare oEmbed's answer against and the
  // author check is dead code. Framed as the profile step it already is, and
  // it asks for exactly one thing.
  const HANDLE_FIELD = { tiktok: "tiktok", youtube: "youtube", x: "x_handle" };
  const HANDLE_NAME = { tiktok: "TikTok", youtube: "YouTube", x: "X" };
  if (HANDLE_FIELD[p.platform]) {
    const claimed = String(fellow.getString(HANDLE_FIELD[p.platform]) || "").trim();
    if (!claimed) {
      return e.json(200, { ok: false, field: "handle", need_handle: p.platform,
        message: "What's your " + HANDLE_NAME[p.platform] + " @? We'll put your posts next to it." });
    }
  }

  // ---- limits, so the table cannot be flooded -----------------------------
  // Newest-first, so the 24-hour window is at the front of the same list that
  // answers the lifetime cap. One query does both — the /fellows/progress
  // shape.
  let mine = [];
  try {
    mine = e.app.findRecordsByFilter("fellow_submissions", "fellow = {:f}", "-created", 500, 0,
      { f: fellow.get("id") });
  } catch (_) { mine = []; }
  if (mine.length >= 500) {
    return e.json(200, { ok: false,
      message: "That's five hundred logged, which is as many as we keep in one list. Write to hello@anticipy.ai and a person will sort it." });
  }
  const DAY_MAX = parseInt($os.getenv("ANTICIPY_FELLOW_SUBMIT_MAX") || "20", 10);
  let inDay = 0;
  for (const r of mine) {
    const t = pbTime(r.getString("created"));
    if (!isNaN(t) && Date.now() - t < 86400000) inDay++;
  }
  if (inDay >= DAY_MAX) {
    // Deliberately not scolding, and deliberately not a number anyone is meant
    // to reach. It is a ceiling on the table, not a target for a person.
    return e.json(200, { ok: false, message: "That's a lot in one day. Try again tomorrow." });
  }

  // ---- a ceiling on ATTEMPTS, not only on rows that landed ------------------
  // BOTH limits above count rows this fellow OWNS, and a URL that belongs to
  // somebody else saves NO row — the unique index rejects it. So every one of
  // those attempts was free, and the two different sentences that come back
  // ("you already logged this" / "we can't add that one") answer the question
  // "is this video in the system, and is it mine?" for any URL on earth. That
  // is an oracle: paste a stranger's link, read the answer, repeat, and learn
  // which videos — and by elimination which fellows — the programme holds.
  //
  // This meter counts every attempt that gets as far as the write, whether it
  // lands or bounces, so a probe costs exactly what a real submission costs.
  // It is a per-fellow row in fellow_meter, made on first use, with `hour`
  // holding a DATE because the window here is a day rather than an hour.
  //
  // The refusal is the SAME SENTENCE as the daily cap above, deliberately: two
  // different sentences would tell an attacker which ceiling they hit, and
  // therefore how much of their probing had been counted.
  const ATTEMPT_MAX = parseInt($os.getenv("ANTICIPY_FELLOW_SUBMIT_ATTEMPT_MAX") || "60", 10);
  const dayNow = nowISO.slice(0, 10);
  const attemptName = "sub:" + String(fellow.get("id"));
  let attemptMeter = null;
  try {
    attemptMeter = e.app.findFirstRecordByFilter("fellow_meter", "name = {:n}", { n: attemptName });
  } catch (_) { attemptMeter = null; }
  if (!attemptMeter) {
    try {
      attemptMeter = new Record(e.app.findCollectionByNameOrId("fellow_meter"));
      attemptMeter.set("name", attemptName);
      attemptMeter.set("hour", dayNow);
      attemptMeter.set("calls", 0);
    } catch (_) { attemptMeter = null; }
  }
  if (attemptMeter) {
    const usedToday = attemptMeter.getString("hour") === dayNow
      ? (Number(attemptMeter.get("calls")) || 0) : 0;
    if (usedToday >= ATTEMPT_MAX) {
      return e.json(200, { ok: false, message: "That's a lot in one day. Try again tomorrow." });
    }
    // Counted BEFORE the write rather than after it, because the whole point
    // is to charge for the attempts that never become rows.
    try {
      attemptMeter.set("hour", dayNow);
      attemptMeter.set("calls", usedToday + 1);
      e.app.save(attemptMeter);
    } catch (_) {}
  }
  // If the meter itself cannot be read or written we do NOT refuse: a broken
  // meter must never stand between a fellow and their own logbook, which is
  // the same ruling the oEmbed ceiling below already makes.

  // ---- a released key does not go back to the fellow it was taken from ----
  // HQ can clear url_key on a row it removed (/internal/fellows/submissions/
  // release), which is what lets the real author log their own video after
  // somebody else claimed it. That release must not simply hand the link back
  // to the account it was taken from, so the row HQ removed remembers the key
  // it used to hold and this is where that memory is read. The trailing
  // semicolon in the pattern is load-bearing: without it "x:20" would match
  // inside a released "x:2012345".
  let barred = null;
  try {
    barred = e.app.findFirstRecordByFilter("fellow_submissions",
      "fellow = {:f} && removed_by = 'hq' && flags ~ {:k}",
      { f: fellow.get("id"), k: "key released by HQ: " + p.url_key + ";" });
  } catch (_) { barred = null; }
  if (barred) {
    // Word for word the collision sentence, so this refusal is indistinguish-
    // able from "somebody else has it" and confirms nothing about who does.
    return e.json(200, { ok: false,
      message: "We can't add that one. If it's yours, write to hello@anticipy.ai and a person will sort it." });
  }

  // ---- WRITE FIRST, INTERPRET THE ERROR SECOND ----------------------------
  // Not look-then-write. Two rapid taps both pass a lookup and both write. The
  // UNIQUE index is the only mutual-exclusion primitive this database actually
  // offers and it holds inside a single INSERT, so the insert IS the check:
  // save, and if it throws, go and find out what it collided with.
  const rec = new Record(e.app.findCollectionByNameOrId("fellow_submissions"));
  rec.set("fellow", fellow.get("id"));
  rec.set("platform", p.platform);
  rec.set("kind", p.kind);
  rec.set("url", p.url);
  rec.set("url_key", p.url_key);
  rec.set("submitted_url", scrub(pasted, 500));
  rec.set("native_id", p.native_id);
  rec.set("author_claimed", scrub(p.author_claimed, 120));
  rec.set("author_handle", "");
  rec.set("title", "");
  rec.set("thumbnail_url", "");
  rec.set("verify_state", "unverified");
  rec.set("oembed_status", 0);
  rec.set("status", "logged");
  rec.set("removed_by", "");
  rec.set("note", note);
  rec.set("flags", "");
  let saved = false;
  try { e.app.save(rec); saved = true; } catch (_) { saved = false; }

  if (!saved) {
    let other = null;
    try { other = e.app.findFirstRecordByFilter("fellow_submissions", "url_key = {:k}", { k: p.url_key }); } catch (_) {}
    if (other && other.getString("fellow") === String(fellow.get("id"))) {
      // Their own. No error styling and no scary word — they did nothing
      // wrong, they just already did it. `already:true` mirrors the shape
      // /fellows/apply already uses for exactly this situation.
      const M = ["January", "February", "March", "April", "May", "June", "July",
                 "August", "September", "October", "November", "December"];
      let when = "";
      const t = pbTime(other.getString("created"));
      if (!isNaN(t)) { const d = new Date(t); when = d.getUTCDate() + " " + M[d.getUTCMonth()]; }
      return e.json(200, { ok: true, already: true, id: other.get("id"),
        message: when ? "You've already logged this one — you added it on " + when + "."
                      : "You've already logged this one." });
    }
    if (other) {
      // SOMEBODY ELSE HAS IT. They are NOT told that, because telling them
      // confirms another fellow exists and confirms what that fellow made.
      // Same sentence-shape and same destination as the `removed` branch of
      // /fellows/start: route to a human, confirm nothing.
      //
      // The activity row is the actual detection mechanism for the
      // stranger-video attack — two people claiming one video means at least
      // one of them is not telling the truth — and it carries BOTH ids so the
      // pair can be looked at rather than merely counted.
      try {
        const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
        act.set("actor", ""); act.set("actor_name", "Fellowships");
        act.set("action", "fellow.submission_collision");
        act.set("subject", "Two fellows claim " + p.url_key + " — held by " + other.getString("fellow")
                         + ", also submitted by " + fellow.get("id"));
        act.set("ref", other.get("id"));
        e.app.save(act);
      } catch (_) {}
      return e.json(200, { ok: false,
        message: "We can't add that one. If it's yours, write to hello@anticipy.ai and a person will sort it." });
    }
    return e.json(200, { ok: false, message: "That didn't save. Try once more?" });
  }

  // ---- ONLY NOW do we ask the internet who made it ------------------------
  // The row is already safe. A slow TikTok costs a title and a thumbnail; it
  // must never stand between a fellow and their own logbook.
  const OEMBED = {
    tiktok:  "https://www.tiktok.com/oembed?url=",
    youtube: "https://www.youtube.com/oembed?format=json&url=",
    x:       "https://publish.x.com/oembed?url=",
  };
  // publish.twitter.com 301s away; publish.x.com is the live host. Instagram
  // and LinkedIn are absent from this table because no endpoint exists for
  // them — not because anybody forgot.
  let mayCall = false;
  if (OEMBED[p.platform] && p.probe_url) {
    const ceiling = parseInt($os.getenv("ANTICIPY_FELLOW_OEMBED_CEILING") || "300", 10);
    const hourNow = nowISO.slice(0, 13);
    try {
      const meter = e.app.findFirstRecordByFilter("fellow_meter", "name = 'oembed'");
      const used = meter.getString("hour") === hourNow ? (Number(meter.get("calls")) || 0) : 0;
      if (used < ceiling) {
        meter.set("hour", hourNow); meter.set("calls", used + 1);
        e.app.save(meter);
        mayCall = true;
      }
      // Over the ceiling the row stays exactly as saved: unverified. A meter
      // must never stop someone logging their own work.
    } catch (_) {}
  }

  let vstate = "unverified", vstatus = 0, author = "", title = "", thumb = "";
  if (mayCall) {
    let res = null;
    try {
      res = $http.send({ url: OEMBED[p.platform] + encodeURIComponent(p.probe_url),
                         method: "GET", timeout: 8 });
    } catch (_) { res = null; }
    if (res) {
      vstatus = Number(res.statusCode) || 0;
      if (vstatus >= 200 && vstatus < 300) {
        // NEVER dereference res.json before checking the status code. YouTube's
        // 400 is the plain text "Bad Request" and X's 404 is an HTML error
        // page; neither parses, and res.json is then undefined.
        let j = null;
        try { j = res.json; } catch (_) { j = null; }
        if (j) {
          try {
            if (p.platform === "tiktok") {
              const mm = String(j.author_url || "").match(/tiktok\.com\/@([A-Za-z0-9._]{1,24})/);
              author = mm ? mm[1] : "";
              title = String(j.title || "");            // the caption
              thumb = String(j.thumbnail_url || "");    // signed, and it expires
            } else if (p.platform === "youtube") {
              const mm = String(j.author_url || "").match(/youtube\.com\/@([A-Za-z0-9._\-]{1,120})/);
              author = mm ? mm[1] : String(j.author_name || "");
              title = String(j.title || "");
              // Deterministic from the id and it does not expire, unlike
              // TikTok's signed CDN URL. Preferred over the one in the body.
              thumb = "https://i.ytimg.com/vi/" + p.native_id + "/hqdefault.jpg";
            } else if (p.platform === "x") {
              author = String(j.author_name || "");
              if (!author) {
                const mm = String(j.author_url || "").match(/x\.com\/([A-Za-z0-9_]{1,15})/);
                author = mm ? mm[1] : "";
              }
              // X returns no title key at all; the post text lives inside the
              // embed html. Take the first paragraph and strip every tag —
              // this string is stored and later rendered.
              const pm = String(j.html || "").match(/<p[^>]*>([\s\S]*?)<\/p>/);
              if (pm) title = pm[1].replace(/<[^>]*>/g, " ");
              // and no thumbnail, ever.
            }
          } catch (_) {}
        }
        const claimed = String(fellow.getString(HANDLE_FIELD[p.platform] || "") || "")
          .trim().replace(/^@/, "").toLowerCase();
        const got = String(author || "").trim().replace(/^@/, "").toLowerCase();
        vstate = (claimed && got) ? (claimed === got ? "verified" : "mismatch") : "unverified";
      } else if (vstatus === 400 || vstatus === 404) {
        // A well-formed URL the platform will not acknowledge: deleted, made
        // private, or never there.
        vstate = "gone";
      }
      // Anything else — a 429, a 5xx, a timeout — leaves it `unverified`,
      // which is the honest word for "we did not find out".
    }
  }

  // ---- NEVER CARRY A RECORD ACROSS A NETWORK CALL --------------------------
  // `rec` is the object as it was BEFORE up to eight seconds inside TikTok's
  // oEmbed. Saving it again would write every one of those stale fields back
  // over whatever happened in the meantime — and the thing most likely to have
  // happened in the meantime is the fellow pressing Remove, because a request
  // that has been spinning for eight seconds is exactly when a person gives up
  // on it. That removal sets status and CLEARS url_key, and re-saving the old
  // object would silently resurrect both: the row would be back in their list,
  // and the key would be back under the unique index, locking the video away
  // from whoever actually made it. There are no transactions across an HTTP
  // call, so the only honest move is to go and look again.
  //
  // Re-read by id, and write only if the two fields a removal moves are still
  // where we left them. If they moved, the oEmbed answer is dropped on the
  // floor — a title and a thumbnail are worth nothing next to a removal that
  // a person asked for.
  let fresh = null;
  try { fresh = e.app.findRecordById("fellow_submissions", rec.get("id")); } catch (_) { fresh = null; }
  const stillOurs = !!fresh && fresh.getString("status") === "logged"
                            && fresh.getString("url_key") === p.url_key;
  if (stillOurs) {
    try {
      fresh.set("verify_state", vstate);
      fresh.set("oembed_status", vstatus);
      fresh.set("verified_at", mayCall ? nowISO : "");
      if (author) fresh.set("author_handle", scrub(author, 120));
      if (title) fresh.set("title", scrub(title, 500));
      if (thumb) fresh.set("thumbnail_url", scrub(thumb, 500));
      if (vstate === "mismatch") {
        // FLAGGED, NOT REFUSED. A fellow may genuinely have a second account, or
        // may have typed one handle and posted from another. It stays in their
        // list and reads as theirs; it is marked for HQ, and the row itself is
        // the durable evidence — internal_activity is pruned at 60 days, and a
        // mismatch is an investigation rather than an event.
        fresh.set("status", "flagged");
        // The flags column may have been written by HQ while we were away, so
        // this appends rather than replaces.
        const had = fresh.getString("flags");
        fresh.set("flags", (had ? had + " | " : "") + "author mismatch: the platform says "
                         + scrub(author, 60) + ", their profile says "
                         + scrub(fellow.getString(HANDLE_FIELD[p.platform] || ""), 60));
      }
      e.app.save(fresh);
    } catch (_) {}
  }

  if (!stillOurs) {
    // It was removed — by them or by HQ — while we were on the network. Say so
    // in the shape the page already knows how to handle without adding a row
    // to the list: ok, a sentence, and no `submission` object.
    return e.json(200, { ok: true, already: true, id: rec.get("id"),
      message: "That one came off your list while we were saving it." });
  }

  return e.json(200, {
    ok: true,
    submission: {
      id: fresh.get("id"),
      platform: fresh.getString("platform"),
      kind: fresh.getString("kind"),
      url: fresh.getString("url"),
      title: fresh.getString("title"),
      thumbnail_url: fresh.getString("thumbnail_url"),
      note: fresh.getString("note"),
      // ONLY "gone" ever reaches a fellow. "unverified" is permanent for
      // Instagram and LinkedIn and would read as a mark against them for using
      // those platforms; "mismatch" would tell someone which check caught
      // them, which is how you teach an attacker to pass it next time. "gone"
      // is useful to them and carries no accusation.
      verify_state: fresh.getString("verify_state") === "gone" ? "gone" : "",
      created: fresh.getString("created"),
    }
  });
});

// --------------------------------------------------------------------------
// POST /fellows/submissions/remove  {id}
//
// Their own row, taken out by them. THE ROW STAYS — a deleted row is a lost
// investigation, the same posture /internal/fellows/remove already argues for
// — but url_key is CLEARED, and that is the asymmetry the partial unique index
// exists for. Releasing the key means one mis-paste cannot lock a video out of
// the system forever, so the person who actually made it can still log it.
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/submissions/remove", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const token = e.request.header.get("X-Fellow-Token") || "";
  if (!token) return e.json(401, { reauth: true });
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "session_hash = {:h}", { h: sha256(token) }); } catch (_) {}
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(401, { reauth: true });
  const sexp = Date.parse(fellow.getString("session_expires"));
  if (isNaN(sexp) || Date.now() > sexp) return e.json(401, { reauth: true });

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const id = String(body.id || "").trim().slice(0, 40);
  if (!id) return e.json(404, { ok: false, message: "We couldn't find that one." });

  let row = null;
  try { row = e.app.findRecordById("fellow_submissions", id); } catch (_) {}
  // Same answer for "no such row" and "somebody else's row", deliberately, so
  // this cannot be used to probe whether an id exists.
  if (!row || row.getString("fellow") !== String(fellow.get("id"))) {
    return e.json(404, { ok: false, message: "We couldn't find that one." });
  }

  // AN HQ REMOVAL IS FINAL FROM THIS SIDE, AND THIS IS THE WHOLE POINT.
  //
  // The two removals are deliberately asymmetric: a fellow removing their own
  // row CLEARS url_key, so one mis-paste cannot lock a video out of the system
  // forever, while an HQ removal RETAINS it so a video taken down as
  // not-theirs stays locked. This route used to write removed_by and clear
  // url_key unconditionally on any row the caller owned — including one HQ had
  // already removed and barred. So the exact attacker the bar exists for could
  // dissolve it: log somebody else's video, wait for HQ to take it down, then
  // call your own remove on the same id. removed_by flips from 'hq' to
  // 'fellow', url_key empties, and the video is free to log again.
  //
  // Ownership is not authority over a decision somebody else made about the
  // row. The answer is the same 404 as a row that is not yours, because
  // telling a claimer that HQ has ruled on their row is information they can
  // only use.
  if (row.getString("removed_by") === "hq") {
    return e.json(404, { ok: false, message: "We couldn't find that one." });
  }

  row.set("status", "removed");
  row.set("removed_by", "fellow");
  row.set("url_key", "");
  try { e.app.save(row); } catch (_) {
    return e.json(200, { ok: false, message: "That didn't save. Try once more?" });
  }
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/fellows/submissions/remove  {id, reason?}
//
// HQ's removal, and it is the mirror image of the fellow's. url_key is
// RETAINED, because an HQ removal means "this was not yours" and the key
// staying locked is what stops the same link being pasted again five minutes
// later. That is also why no 90-day re-submission rule is needed anywhere.
//
// AND THE KEY MUST BE RELEASABLE, which is what the route below this one is
// for. Retention is right for the five minutes after a removal and wrong
// forever: when B falsely logs A's video and HQ removes it, the retained key
// locks out A — the person who actually made the thing — with no way back.
// The lockout is silent from A's side (they get the same "we can't add that
// one" a collision gives) so nobody would ever report it as a bug. HQ removes,
// then releases, and A can log their own video.
//
// What the fellow sees is nothing accusatory: it is simply gone from their
// list. An email goes out only if a human chooses to write one. A machine does
// not accuse a fifteen-year-old of fraud.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/fellows/submissions/remove", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const id = String(body.id || "").trim();
  if (!id) return e.json(400, { error: "which submission?" });
  const reason = String(body.reason || "").replace(/[\u0000-\u001F\u007F]/g, " ").slice(0, 500);

  let row = null;
  try { row = e.app.findRecordById("fellow_submissions", id); } catch (_) {}
  if (!row) return e.json(404, { error: "no such submission" });

  row.set("status", "removed");
  row.set("removed_by", "hq");
  // url_key deliberately untouched — see the header comment.
  const flags = row.getString("flags");
  row.set("flags", (flags ? flags + " | " : "") + "removed by HQ" + (reason ? ": " + reason : ""));
  try { e.app.save(row); } catch (_) {
    return e.json(500, { error: "couldn't save that" });
  }
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", ""); act.set("actor_name", "Fellowships");
    act.set("action", "fellow.submission_removed");
    act.set("subject", "Removed submission " + row.getString("url_key")
                     + (reason ? " — " + reason.slice(0, 80) : ""));
    act.set("ref", id);
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { ok: true });
});

// --------------------------------------------------------------------------
// POST /internal/fellows/submissions/release  {id, reason?}
//
// THE WAY BACK. An HQ removal keeps url_key, and the whole point of keeping it
// is that the link cannot be pasted again — by anyone. That is correct in the
// hour after a removal and wrong for the rest of time, because the commonest
// reason for an HQ removal is "B logged A's video", and the retained key then
// locks out A. A gets the collision sentence, which by design tells them
// nothing, so the person who actually made the video is silently unable to log
// it and has no way of finding out why. Before this route existed the only
// remedies were opening the database or leaving it broken.
//
// WHAT IS RELEASED AND WHAT IS NOT. url_key is cleared, so the video is
// loggable again by whoever really made it. THE REMOVAL STAYS — status stays
// "removed", removed_by stays "hq", and the flags stay and get one more line.
// Nothing about the row's history is erased, because the row is the durable
// evidence: internal_activity is pruned at 60 days and this is an
// investigation, not an event. The released key is written into the flags and
// into the activity feed so it survives being cleared from its column.
//
// AND THE PERSON IT WAS TAKEN FROM DOES NOT GET IT BACK. The submissions route
// reads that flags line and refuses the same key from the same fellow, so a
// release hands the video to everyone EXCEPT the one account HQ took it from.
// Without that, releasing would simply return the link to whoever was first to
// re-paste it, which is the attacker.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/fellows/submissions/release", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const id = String(body.id || "").trim();
  if (!id) return e.json(400, { error: "which submission?" });
  const reason = String(body.reason || "").replace(/[\u0000-\u001F\u007F]/g, " ").slice(0, 500);

  let row = null;
  try { row = e.app.findRecordById("fellow_submissions", id); } catch (_) {}
  if (!row) return e.json(404, { error: "no such submission" });

  // A LIVE ROW KEEPS ITS KEY. Releasing the key of a row that is still in
  // somebody's list would let the same video be logged twice — once by the row
  // that still shows it, once by the next person to paste it — and the unique
  // index is the only thing standing between us and that. Release is a thing
  // you do to a removal.
  if (row.getString("status") !== "removed") {
    return e.json(409, { error: "that one hasn't been removed — remove it first" });
  }
  const released = row.getString("url_key");
  if (!released) return e.json(200, { ok: true, already: true, released: "" });

  row.set("url_key", "");
  const flags = row.getString("flags");
  // The semicolon is not decoration: the submissions route matches on this
  // exact string and a terminator is what stops "key released by HQ: x:20"
  // matching inside "key released by HQ: x:2012345".
  row.set("flags", ((flags ? flags + " | " : "") + "key released by HQ: " + released + ";"
                   + (reason ? " " + reason : "")).slice(0, 1000));
  try { e.app.save(row); } catch (_) {
    return e.json(500, { error: "couldn't save that" });
  }
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", ""); act.set("actor_name", "Fellowships");
    act.set("action", "fellow.submission_released");
    act.set("subject", "Released " + released + " — anyone but " + row.getString("fellow")
                     + " may log it again" + (reason ? ": " + reason.slice(0, 80) : ""));
    act.set("ref", id);
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { ok: true, released: released });
});

// --------------------------------------------------------------------------
// POST /internal/fellows/remove  {fellow_id, reason?}
//
// Somebody has to be able to take a row out: a test signup, a duplicate, a
// spam address, or a person who asks to leave. There was no way to do that at
// all, which meant the only options were "live with it" or "open the
// database" — and the second one is how accidents happen.
//
// It is a soft removal. The row stays so a conversion that already exists
// still has something to point at, but the code stops working immediately and
// the person stops appearing anywhere. Actual erasure is a separate,
// deliberate act, and it should be, because it is the one that cannot be
// undone.
// --------------------------------------------------------------------------
routerAdd("POST", "/internal/fellows/remove", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const id = String(body.fellow_id || "").trim();
  if (!id) return e.json(400, { error: "which fellow?" });

  let fellow = null;
  try { fellow = e.app.findRecordById("fellows", id); } catch (_) {}
  if (!fellow) return e.json(404, { error: "no such fellow" });

  const who = fellow.getString("name") || fellow.getString("email");
  fellow.set("status", "removed");
  fellow.set("code_active", false);
  fellow.set("code_revoked", true);   // the link stops crediting from now on
  fellow.set("session_hash", "");     // and they are signed out everywhere
  try { e.app.save(fellow); } catch (_) {
    return e.json(500, { error: "couldn't save that" });
  }
  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", ""); act.set("actor_name", "Fellowships");
    act.set("action", "fellow.removed");
    act.set("subject", "Removed " + who + (body.reason ? " — " + String(body.reason).slice(0, 80) : ""));
    act.set("ref", id);
    e.app.save(act);
  } catch (_) {}
  return e.json(200, { ok: true, removed: who });
});

// --------------------------------------------------------------------------
// GET /internal/fellows — the HQ view. Internal key, fail-closed, exactly the
// stance internal_hq uses (this half of the file is NOT public).
// --------------------------------------------------------------------------
routerAdd("GET", "/internal/fellows", (e) => {
  const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
  if (!key) return e.json(503, { error: "internal HQ is not configured" });
  if (!$security.equal(e.request.header.get("X-Internal-Key") || "", key)) {
    return e.json(401, { error: "wrong key" });
  }
  const fellows = [], conversions = [];
  try {
    const rows = e.app.findRecordsByFilter("fellows", "status != 'removed'", "-created", 500, 0);
    for (const f of rows) fellows.push({
      id: f.get("id"), name: f.getString("name"), email: f.getString("email"),
      age_band: f.getString("age_band"), country: f.getString("country"),
      status: f.getString("status"), fellowship: f.getString("fellowship"),
      parental_consent: f.getString("parental_consent"),
      payout_identity_verified: !!f.get("payout_identity_verified"),
      referral_code: f.getString("referral_code"), code_active: !!f.get("code_active"),
      clicks_total: Number(f.get("clicks_total")) || 0,
      instagram: f.getString("instagram"), tiktok: f.getString("tiktok"),
      created: f.getString("created"),
    });
  } catch (_) {}
  try {
    const rows = e.app.findRecordsByFilter("fellow_conversions", "", "-created", 300, 0);
    for (const c of rows) conversions.push({
      id: c.get("id"), fellow: c.getString("fellow"), code: c.getString("code"),
      order_ref: c.getString("order_ref"), amount_usd: Number(c.get("amount_usd")) || 0,
      commission_usd: Number(c.get("commission_usd")) || 0,
      status: c.getString("status"), flags: c.getString("flags"),
      hold_until: c.getString("hold_until"), created: c.getString("created"),
    });
  } catch (_) {}
  // The logbook, in full, INCLUDING removed rows — this is the only surface
  // where a removal is visible, and a removal is exactly the thing somebody
  // needs to be able to look at afterwards.
  //
  // Everything here is user-supplied or third-party text: submitted_url is
  // whatever was pasted, title is whatever the platform said, author_* are
  // handles. Whatever renders this MUST escape all of them. They are returned
  // as JSON so the transport is safe; the HTML is the caller's problem and
  // this comment is the warning.
  const submissions = [];
  try {
    const rows = e.app.findRecordsByFilter("fellow_submissions", "", "-created", 200, 0);
    for (const r of rows) submissions.push({
      id: r.get("id"), fellow: r.getString("fellow"),
      platform: r.getString("platform"), kind: r.getString("kind"),
      url: r.getString("url"), url_key: r.getString("url_key"),
      submitted_url: r.getString("submitted_url"),
      title: r.getString("title"), thumbnail_url: r.getString("thumbnail_url"),
      author_handle: r.getString("author_handle"),
      author_claimed: r.getString("author_claimed"),
      verify_state: r.getString("verify_state"),
      oembed_status: Number(r.get("oembed_status")) || 0,
      status: r.getString("status"), removed_by: r.getString("removed_by"),
      note: r.getString("note"), flags: r.getString("flags"),
      created: r.getString("created"),
    });
  } catch (_) {}
  return e.json(200, { fellows: fellows, conversions: conversions, submissions: submissions });
});
