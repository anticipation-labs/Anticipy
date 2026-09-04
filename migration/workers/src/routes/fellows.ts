/**
 * Fellowship routes — ported from migration/recovered/fellowship.pb.js and
 * fellowship_guardian.pb.js (recovered from a backup archive; see that README).
 *
 * 17 handlers, ported in parallel each from its slice of the recovered source,
 * every UNAUTHENTICATED contract diffed against live production. The
 * authenticated / email / oembed / payout / minor-consent paths ship UNPROVEN
 * exactly as HQ's authenticated half did — the recovered source is the
 * most-recent-committed ancestor of what Railway runs, not provably identical
 * to it, so production remains the arbiter and these must be diffed there
 * before the fellowship site is repointed. Per-route risk is noted at each fn.
 *
 * All shared helpers live in fellows_base.ts; nothing here redefines them.
 */
import {
  type FellowsEnv, json, readBody, sha256Hex, timingEqual, newRecordId, pbNow,
  isoNow, resolveClientIP, sendResendEmail, randomDigits, randomHex, boolTrue,
} from "./fellows_base.ts";


// --- /fellows/health   risk=LOW ---
export async function fellowsHealth(req: Request, env: FellowsEnv): Promise<Response> {
  const hasResend = !!env.RESEND_API_KEY;
  const hasModel = !!env.OPENROUTER_API_KEY;

  let realIP = "";
  try {
    const xff = String(req.headers.get("X-Forwarded-For") || "");
    if (xff) realIP = xff.split(",")[0].trim();
  } catch (_) {}
  if (!realIP) {
    try {
      realIP = resolveClientIP(req) || "";
    } catch (_) {}
  }

  return json(200, {
    ok: true,
    can_email: hasResend,
    can_review: hasModel,
    // If this is false the per-IP throttle is disabled on purpose — see the
    // comment in /fellows/code. It is reported so the deploy checklist can be
    // verified from outside without a superuser login.
    ip_resolves: !!realIP && realIP !== "127.0.0.1" && realIP !== "::1",
  });
}


// --- /fellows/confirm   risk=HIGH ---
export async function fellowsConfirm(req: Request, env: FellowsEnv): Promise<Response> {
  const site = env.ANTICIPY_SITE_URL || "https://www.anticipy.ai";

  let t = "";
  try {
    t = String(new URL(req.url).searchParams.get("t") || "");
  } catch (_) {}
  if (!t) return new Response(null, { status: 302, headers: { Location: site + "/fellowships" } });

  let fellow: Record<string, unknown> | null = null;
  try {
    fellow = await env.DB
      .prepare("SELECT * FROM fellows WHERE consent_token_hash = ?1 LIMIT 1")
      .bind(await sha256Hex(t))
      .first();
  } catch (_) {
    fellow = null;
  }

  if (fellow) {
    // 18+ can be paid the moment their address is real. Under 18 still waits
    // on the guardian payout setup, which is the law, not our preference.
    const activate = String(fellow.age_band ?? "") === "18_plus";
    try {
      await env.DB
        .prepare(
          "UPDATE fellows SET email_confirmed_at = ?1, consent_token_hash = ?2, code_active = ?3, updated = ?4 WHERE id = ?5"
        )
        .bind(
          isoNow(),
          "",
          activate ? 1 : boolTrue(fellow.code_active) ? 1 : 0,
          pbNow(),
          String(fellow.id)
        )
        .run();
    } catch (_) {}
  }

  return new Response(null, { status: 302, headers: { Location: site + "/fellowships?confirmed=1" } });
}


// --- /fellows/progress   risk=LOW ---
export async function fellowsProgress(req: Request, env: FellowsEnv): Promise<Response> {
  const token = req.headers.get("X-Fellow-Token") || "";
  if (!token) return json(401, { reauth: true });

  const sessionHash = await sha256Hex(token);
  let fellow: Record<string, unknown> | null = null;
  try {
    fellow = await env.DB.prepare(
      "SELECT * FROM fellows WHERE session_hash = ?1 LIMIT 1"
    ).bind(sessionHash).first();
  } catch (_) { fellow = null; }

  // A removal signs them out, but a token that is still in flight must not
  // outlive it either. Belt and braces: the same status check on every route
  // that takes a session.
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(401, { reauth: true });

  const sexp = Date.parse(String(fellow.session_expires ?? ""));
  if (isNaN(sexp) || Date.now() > sexp) return json(401, { reauth: true });

  let body: Record<string, unknown> = {};
  try { body = await readBody(req); } catch (_) { body = {}; }

  let ids: unknown[] = [];
  if (Array.isArray(body.lessons)) ids = body.lessons as unknown[];
  else if (body.lesson_id) ids = [body.lesson_id];
  const cleanIds = ids
    .map((x) => String(x ?? "").trim())
    .filter((x) => /^[a-z0-9-]{3,60}$/.test(x))
    .slice(0, 60);
  if (!cleanIds.length) return json(200, { ok: true, saved: 0 });

  const fellowId = String(fellow.id ?? "");
  let count = 0;
  try {
    const existingRes = await env.DB.prepare(
      "SELECT * FROM fellow_progress WHERE fellow = ?1 ORDER BY created ASC LIMIT ?2 OFFSET ?3"
    ).bind(fellowId, 500, 0).all();
    const existing = (existingRes.results || []) as Record<string, unknown>[];
    if (existing.length >= 500) return json(200, { ok: true, saved: 0 });
    const have: Record<string, boolean> = {};
    for (const r of existing) have[String(r.lesson_id ?? "")] = true;
    for (const id of cleanIds) {
      if (have[id]) continue;
      try {
        await env.DB.prepare(
          "INSERT INTO fellow_progress (id, fellow, lesson_id, completed_at, created) VALUES (?1, ?2, ?3, ?4, ?5)"
        ).bind(newRecordId(), fellowId, id, isoNow(), pbNow()).run();
        count++;
      } catch (_) {}
    }
  } catch (_) {}
  return json(200, { ok: true, saved: count });
}


// --- /fellows/profile   risk=MEDIUM ---
export async function fellowsProfile(req: Request, env: FellowsEnv): Promise<Response> {
  const token = req.headers.get("X-Fellow-Token") || "";
  if (!token) return json(401, { reauth: true });

  let fellow: Record<string, unknown> | null = null;
  try {
    const h = await sha256Hex(token);
    fellow = await env.DB
      .prepare("SELECT * FROM fellows WHERE session_hash = ?1 LIMIT 1")
      .bind(h)
      .first<Record<string, unknown>>();
  } catch (_) {}

  // A removal signs them out, but a token that is still in flight must not
  // outlive it either.
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(401, { reauth: true });

  const sexp = Date.parse(String(fellow.session_expires ?? ""));
  if (isNaN(sexp) || Date.now() > sexp) return json(401, { reauth: true });

  const body = await readBody(req);
  const band = String(fellow.age_band ?? "");

  // Accumulate the columns the source's record.set() calls would persist.
  const sets: Record<string, unknown> = {};

  if ("name" in body) {
    sets.name = String((body as any).name || "").trim().slice(0, 120);
  }

  // youtube shares this treatment: strip a leading @, cap it, store it.
  for (const k of ["instagram", "tiktok", "x_handle", "youtube"] as const) {
    if (k in body) {
      sets[k] = String((body as any)[k] || "").trim().replace(/^@/, "").slice(0, 200);
    }
  }

  if ("linkedin" in body) {
    // LinkedIn's own floor is 16.
    if (band === "13_15") {
      return json(200, { ok: false, message: "LinkedIn's own rules start at 16, so we'll skip that one for now." });
    }
    sets.linkedin = String((body as any).linkedin || "").trim().slice(0, 200);
  }

  if ("phone" in body) {
    const ph = String((body as any).phone || "").trim().replace(/[\s()-]/g, "");
    if (ph && !/^\+?\d{8,15}$/.test(ph)) {
      return json(200, { ok: false, message: "That number doesn't look right — include the country code." });
    }
    sets.phone = ph;
  }

  if ("sms_opt_in" in body) {
    // Texts are 18+ only; the send helper checks again.
    if ((body as any).sms_opt_in === true && band !== "18_plus") {
      return json(200, { ok: false, message: "We only text fellows who are 18 or over. Email works for everything." });
    }
    sets.sms_opt_in = (body as any).sms_opt_in === true ? 1 : 0;
  }

  try {
    // PB's e.app.save() always touches `updated`, even with no changed fields.
    const cols = Object.keys(sets);
    const assignments: string[] = [];
    const params: unknown[] = [];
    let i = 1;
    for (const c of cols) {
      assignments.push(`${c} = ?${i++}`);
      params.push(sets[c]);
    }
    assignments.push(`updated = ?${i++}`);
    params.push(pbNow());
    params.push(String(fellow.id ?? ""));
    const res = await env.DB
      .prepare(`UPDATE fellows SET ${assignments.join(", ")} WHERE id = ?${i}`)
      .bind(...params)
      .run();
    if (!res.success) throw new Error("save failed");
  } catch (_) {
    return json(200, { ok: false, message: "That didn't save. Try once more?" });
  }

  return json(200, { ok: true });
}


// --- /fellows/me   risk=HIGH ---
export async function fellowsMe(req: Request, env: FellowsEnv): Promise<Response> {
  const token = req.headers.get("X-Fellow-Token") || "";
  if (!token) return json(401, { reauth: true });

  let fellow: Record<string, unknown> | null = null;
  try {
    const h = await sha256Hex(token);
    fellow = await env.DB.prepare(
      "SELECT * FROM fellows WHERE session_hash = ?1 LIMIT 1"
    ).bind(h).first();
  } catch (_) {}

  // A removal signs them out, but a token that is still in flight must not
  // outlive it either. Belt and braces: the same status check on every route
  // that takes a session.
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(401, { reauth: true });

  const exp = Date.parse(String(fellow.session_expires ?? ""));
  if (isNaN(exp) || Date.now() > exp) return json(401, { reauth: true });

  // Recompute the band on every read, so turning 16 or 18 takes effect on
  // its own without anyone running anything.
  const bm = Number(fellow.birth_month) || 0, by = Number(fellow.birth_year) || 0;
  if (bm && by) {
    const now = new Date();
    let age = now.getUTCFullYear() - by;
    if (now.getUTCMonth() + 1 < bm) age -= 1;
    const band = age >= 18 ? "18_plus" : (age >= 16 ? "16_17" : "13_15");
    if (band !== String(fellow.age_band ?? "")) {
      fellow.age_band = band;
      if (band === "18_plus" && String(fellow.parental_consent ?? "") !== "confirmed") {
        fellow.parental_consent = "not_required";
      }
      try {
        await env.DB.prepare(
          "UPDATE fellows SET age_band = ?1, parental_consent = ?2, updated = ?3 WHERE id = ?4"
        ).bind(fellow.age_band, fellow.parental_consent, pbNow(), fellow.id).run();
      } catch (_) {}
    }
  }

  const done: string[] = [];
  try {
    const { results } = await env.DB.prepare(
      "SELECT * FROM fellow_progress WHERE fellow = ?1 ORDER BY created ASC LIMIT ?2 OFFSET ?3"
    ).bind(fellow.id, 500, 0).all();
    for (const r of (results ?? []) as Record<string, unknown>[]) done.push(String(r.lesson_id ?? ""));
  } catch (_) {}

  const conversions: unknown[] = [];
  try {
    const { results } = await env.DB.prepare(
      "SELECT * FROM fellow_conversions WHERE fellow = ?1 ORDER BY created DESC LIMIT ?2 OFFSET ?3"
    ).bind(fellow.id, 100, 0).all();
    for (const r of (results ?? []) as Record<string, unknown>[]) conversions.push({
      status: String(r.status ?? ""),
      commission_usd: Number(r.commission_usd) || 0,
      created: String(r.created ?? ""),
      hold_until: String(r.hold_until ?? ""),
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
  const submissions: unknown[] = [];
  try {
    const { results } = await env.DB.prepare(
      "SELECT * FROM fellow_submissions WHERE fellow = ?1 AND status != 'removed' ORDER BY created DESC LIMIT ?2 OFFSET ?3"
    ).bind(fellow.id, 50, 0).all();
    for (const r of (results ?? []) as Record<string, unknown>[]) submissions.push({
      id: r.id,
      platform: String(r.platform ?? ""),
      kind: String(r.kind ?? ""),
      url: String(r.url ?? ""),
      title: String(r.title ?? ""),
      thumbnail_url: String(r.thumbnail_url ?? ""),
      note: String(r.note ?? ""),
      verify_state: String(r.verify_state ?? "") === "gone" ? "gone" : "",
      created: String(r.created ?? ""),
    });
  } catch (_) {}

  return json(200, {
    ok: true,
    fellow: {
      id: fellow.id, email: String(fellow.email ?? ""), name: String(fellow.name ?? ""),
      age_band: String(fellow.age_band ?? ""), country: String(fellow.country ?? ""),
      parental_consent: String(fellow.parental_consent ?? ""),
      parent_email: String(fellow.parent_email ?? ""),
      fellowship: String(fellow.fellowship ?? ""), status: String(fellow.status ?? ""),
      referral_code: String(fellow.referral_code ?? ""),
      code_active: boolTrue(fellow.code_active),
      clicks_total: Number(fellow.clicks_total) || 0,
      instagram: String(fellow.instagram ?? ""), tiktok: String(fellow.tiktok ?? ""),
      x_handle: String(fellow.x_handle ?? ""), linkedin: String(fellow.linkedin ?? ""),
      // youtube joined the others in 1700000046. Without it a YouTube Short
      // could be logged and the author check would have nothing to compare
      // oEmbed's answer against, which is the same as having no check at all.
      youtube: String(fellow.youtube ?? ""),
      payout_method: String(fellow.payout_method ?? ""),
      sms_opt_in: boolTrue(fellow.sms_opt_in),
    },
    progress: done,
    conversions: conversions,
    submissions: submissions,
  });
}


// --- /fellows/code   risk=MEDIUM ---
export async function fellowsCode(req: Request, env: FellowsEnv): Promise<Response> {
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  const nowMs = Date.now();
  const nowISO = isoNow();

  const body = await readBody(req);
  const email = String(body.email ?? "").trim().toLowerCase();
  const bm = parseInt(String(body.birth_month), 10);
  const by = parseInt(String(body.birth_year), 10);
  const country = String(body.country ?? "").trim().toLowerCase();

  if (!EMAIL_RE.test(email) || email.length > 254) {
    return json(200, { ok: false, message: "That email doesn't look right. Mind checking it?" });
  }

  // ---- AGE FIRST. Nothing is written before this passes. ----
  if (!(bm >= 1 && bm <= 12) || !(by >= 1900 && by <= 2100)) {
    return json(200, { ok: false, message: "Pick the month and year you were born and we'll carry on." });
  }
  const now = new Date();
  let age = now.getUTCFullYear() - by;
  if (now.getUTCMonth() + 1 < bm) age -= 1;
  if (age < 13) {
    return json(200, {
      ok: false, stop: true,
      message: "You have to be 13 to join this one. Come back on your birthday — we'll still be here, and we'd genuinely like to have you."
    });
  }
  if (country !== "us" && country !== "ca") {
    return json(200, {
      ok: false, stop: true,
      message: "Right now we can only take fellows in the US and Canada, because that's where we can pay people properly. We'll open it up — leave us your email at anticipy.ai and we'll tell you when."
    });
  }

  // ---- throttles ----
  const uniform = { ok: true, message: "Check your email — your code is on the way." };

  try {
    const recent = await env.DB.prepare(
      "SELECT * FROM fellow_codes WHERE email = ?1 ORDER BY created DESC LIMIT ?2 OFFSET ?3"
    ).bind(email, 10, 0).all();
    let lastMs = 0, inHour = 0;
    for (const r of (recent.results ?? []) as Record<string, unknown>[]) {
      const t = Date.parse(String(r.created ?? "").replace(" ", "T"));
      if (!isNaN(t)) {
        if (t > lastMs) lastMs = t;
        if (nowMs - t < 3600000) inHour++;
      }
    }
    if (lastMs && nowMs - lastMs < 60000) return json(200, uniform);   // one a minute
    if (inHour >= 5) return json(200, uniform);                        // five an hour
  } catch (_) {}

  // WHOSE ADDRESS IS THIS, REALLY? — XFF leftmost, then realIP fallback.
  const ip = resolveClientIP(req);
  const ipUsable = !!ip && ip !== "127.0.0.1" && ip !== "::1";
  if (ipUsable) {
    try {
      const byIP = await env.DB.prepare(
        "SELECT * FROM fellow_codes WHERE ip = ?1 ORDER BY created DESC LIMIT ?2 OFFSET ?3"
      ).bind(ip, 20, 0).all();
      let n = 0;
      for (const r of (byIP.results ?? []) as Record<string, unknown>[]) {
        const t = Date.parse(String(r.created ?? "").replace(" ", "T"));
        if (!isNaN(t) && nowMs - t < 3600000) n++;
      }
      if (n >= 8) return json(200, uniform);
    } catch (_) {}
  }

  // Layer 3: the global circuit breaker.
  const ceiling = parseInt(env.ANTICIPY_FELLOW_EMAIL_CEILING || "50", 10);
  const hourNow = nowISO.slice(0, 13);
  try {
    const meter = await env.DB.prepare(
      "SELECT * FROM fellow_meter WHERE name = ?1 LIMIT 1"
    ).bind("email").first() as Record<string, unknown> | null;
    // Match source: a missing meter throws here and is swallowed by catch.
    const meterHour = String((meter as Record<string, unknown>).hour ?? "");
    const used = meterHour === hourNow ? (Number((meter as Record<string, unknown>).calls) || 0) : 0;
    if (used >= ceiling) {
      try {
        await env.DB.prepare(
          "INSERT INTO internal_activity (id, actor, actor_name, action, subject, created) VALUES (?1, ?2, ?3, ?4, ?5, ?6)"
        ).bind(
          newRecordId(), "", "Fellowships", "fellowship.email_meter",
          "The fellowship sign-in email meter tripped at " + ceiling + "/hour",
          pbNow()
        ).run();
      } catch (_) {}
      return json(200, { ok: false, message: "We're getting a lot of signups right now — try again in a few minutes." });
    }
    await env.DB.prepare(
      "UPDATE fellow_meter SET hour = ?1, calls = ?2, updated = ?3 WHERE id = ?4"
    ).bind(hourNow, used + 1, pbNow(), String((meter as Record<string, unknown>).id ?? "")).run();
  } catch (_) {}

  // ---- SEND FIRST, THEN SAVE ----
  const code = randomDigits(6);
  const rk = env.RESEND_API_KEY || "";
  if (!rk) {
    return json(200, { ok: false, message: "We can't send codes this minute. Try again shortly — it's us, not you." });
  }
  const sent = await sendResendEmail(
    env,
    email,
    code + " is your Anticipy code",
    "Here's your code: " + code + "\n\nIt works for 10 minutes.\n\nIf you didn't ask for this, you can ignore this email — nothing has been created."
  );
  if (!sent) {
    return json(200, { ok: false, message: "That email didn't go through. Check the address, or try again in a minute." });
  }

  try {
    await env.DB.prepare(
      "INSERT INTO fellow_codes (id, email, code_hash, expires, attempts, used, ip, created) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)"
    ).bind(
      newRecordId(),
      email,
      await sha256Hex(code),
      isoNow(new Date(nowMs + 10 * 60000)),
      0,
      0,
      ipUsable ? ip : "",
      pbNow()
    ).run();
  } catch (_) {}

  return json(200, uniform);
}


// --- /fellows/verify   risk=HIGH ---
export async function fellowsVerify(req: Request, env: FellowsEnv): Promise<Response> {
  // Route-local: referral code alphabet is load-bearing (must survive
  // anticipy.ai checkout's toLowerCase().replace(/[^a-z0-9-]/g,"") before it
  // reaches Stripe metadata). No i/l/o/0/1 — the characters people mistype.
  const makeCode = (): string => {
    const chars = "abcdefghjkmnpqrstuvwxyz23456789";
    const buf = new Uint8Array(6);
    crypto.getRandomValues(buf);
    let out = "";
    for (let i = 0; i < 6; i++) out += chars.charAt(buf[i] % chars.length);
    return out;
  };

  const nowMs = Date.now();

  const body = await readBody(req);
  const email = String(body.email || "").trim().toLowerCase();
  const code = String(body.code || "").trim();
  const bm = parseInt(String(body.birth_month ?? ""), 10);
  const by = parseInt(String(body.birth_year ?? ""), 10);
  const country = String(body.country || "").trim().toLowerCase();

  if (!email || !/^\d{6}$/.test(code)) {
    return json(200, { ok: false, message: "That code doesn't look right — it's the six digits from the email." });
  }

  let row: Record<string, unknown> | null = null;
  try {
    const r = await env.DB.prepare(
      "SELECT * FROM fellow_codes WHERE email = ?1 AND used = 0 ORDER BY created DESC LIMIT 1"
    ).bind(email).first();
    row = (r as Record<string, unknown>) || null;
  } catch (_) {}
  // Covers both "already used" and "there was never one for this address",
  // deliberately, because saying which would let someone probe for addresses.
  if (!row) return json(200, { ok: false, message: "That code isn't live any more. Ask for a fresh one and we'll start again." });

  const codeId = String(row.id ?? "");

  const exp = Date.parse(String(row.expires ?? ""));
  if (isNaN(exp) || nowMs > exp) {
    try { await env.DB.prepare("UPDATE fellow_codes SET used = 1 WHERE id = ?1").bind(codeId).run(); } catch (_) {}
    return json(200, { ok: false, message: "That code expired — they only last ten minutes. Ask for a new one." });
  }

  const attempts = (Number(row.attempts) || 0) + 1;
  if (attempts > 5) {
    try { await env.DB.prepare("UPDATE fellow_codes SET attempts = ?1, used = 1 WHERE id = ?2").bind(attempts, codeId).run(); } catch (_) {}
    return json(200, { ok: false, message: "Too many tries on that code. Ask for a new one and we'll start again." });
  }
  try { await env.DB.prepare("UPDATE fellow_codes SET attempts = ?1 WHERE id = ?2").bind(attempts, codeId).run(); } catch (_) {}

  if (!timingEqual(await sha256Hex(code), String(row.code_hash ?? ""))) {
    return json(200, { ok: false, message: "That's not the code in the email. Try again." });
  }
  try { await env.DB.prepare("UPDATE fellow_codes SET used = 1 WHERE id = ?1").bind(codeId).run(); } catch (_) {}

  // The age check runs again HERE, server-side, on the values sent with the
  // verify. This one guards the row we are about to create.
  const now = new Date();
  let age = now.getUTCFullYear() - by;
  if (now.getUTCMonth() + 1 < bm) age -= 1;
  if (!(bm >= 1 && bm <= 12) || !(by >= 1900 && by <= 2100) || age < 13) {
    return json(200, { ok: false, stop: true, message: "You have to be 13 to join this one. Come back on your birthday." });
  }
  const band = age >= 18 ? "18_plus" : (age >= 16 ? "16_17" : "13_15");

  let existing: Record<string, unknown> | null = null;
  try {
    const f = await env.DB.prepare("SELECT * FROM fellows WHERE email = ?1 LIMIT 1").bind(email).first();
    existing = (f as Record<string, unknown>) || null;
  } catch (_) {}

  // Session token minted for every fellow: minting a new one kills the old.
  const token = randomHex(48);
  const sessionHash = await sha256Hex(token);
  const sessionExpires = isoNow(new Date(nowMs + 30 * 86400000));

  let out: {
    id: string; email: string; name: string; age_band: string; country: string;
    parental_consent: string; fellowship: string; status: string;
    referral_code: string; code_active: boolean;
  };

  if (!existing) {
    const id = newRecordId();
    const nm = String(body.name || "").trim().slice(0, 120);
    const ctry = country === "ca" ? "ca" : "us";
    const consent = band === "18_plus" ? "not_required" : "pending";
    const referral = makeCode();
    const ts = pbNow();
    try {
      await env.DB.prepare(
        "INSERT INTO fellows (id, email, name, birth_month, birth_year, age_band, country, parental_consent, payout_method, status, clicks_total, code_active, code_revoked, referral_code, session_hash, session_expires, created, updated) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)"
      ).bind(id, email, nm, bm, by, band, ctry, consent, "card", "new", 0, 0, 0, referral, sessionHash, sessionExpires, ts, ts).run();
    } catch (err) {
      return json(200, { ok: false, message: "Something went wrong making your account. Try once more?" });
    }
    out = {
      id, email, name: nm, age_band: band, country: ctry,
      parental_consent: consent, fellowship: "", status: "new",
      referral_code: referral, code_active: false,
    };
  } else {
    const fid = String(existing.id ?? "");
    let referral = String(existing.referral_code ?? "");
    if (!referral) referral = makeCode();
    try {
      await env.DB.prepare(
        "UPDATE fellows SET age_band = ?1, referral_code = ?2, session_hash = ?3, session_expires = ?4, updated = ?5 WHERE id = ?6"
      ).bind(band, referral, sessionHash, sessionExpires, pbNow(), fid).run();
    } catch (_) {}
    out = {
      id: fid,
      email: String(existing.email ?? ""),
      name: String(existing.name ?? ""),
      age_band: band,
      country: String(existing.country ?? ""),
      parental_consent: String(existing.parental_consent ?? ""),
      fellowship: String(existing.fellowship ?? ""),
      status: String(existing.status ?? ""),
      referral_code: referral,
      code_active: boolTrue(existing.code_active),
    };
  }

  return json(200, {
    ok: true,
    token: token,
    fellow: {
      id: out.id, email: out.email, name: out.name,
      age_band: out.age_band, country: out.country,
      parental_consent: out.parental_consent,
      fellowship: out.fellowship, status: out.status,
      referral_code: out.referral_code, code_active: out.code_active,
    }
  });
}


// --- /fellows/submissions/remove, /internal/fellows/submissions/remove, /internal/fellows/submissions/release, /internal/fellows/remove   risk=MEDIUM ---
// ===========================================================================
// POST /fellows/submissions/remove  — a fellow removes their own submission.
// ===========================================================================
export async function fellowsSubmissionsRemove(req: Request, env: FellowsEnv): Promise<Response> {
  const token = req.headers.get("X-Fellow-Token") || "";
  if (!token) return json(401, { reauth: true });

  let fellow: Record<string, unknown> | null = null;
  try {
    fellow = await env.DB
      .prepare("SELECT * FROM fellows WHERE session_hash = ?1 LIMIT 1")
      .bind(await sha256Hex(token))
      .first();
  } catch (_) {}
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(401, { reauth: true });

  const sexp = Date.parse(String(fellow.session_expires ?? ""));
  if (isNaN(sexp) || Date.now() > sexp) return json(401, { reauth: true });

  let body: Record<string, unknown> = {};
  try { body = (await readBody(req)) || {}; } catch (_) {}
  const id = String(body.id ?? "").trim().slice(0, 40);
  if (!id) return json(404, { ok: false, message: "We couldn't find that one." });

  let row: Record<string, unknown> | null = null;
  try {
    row = await env.DB
      .prepare("SELECT * FROM fellow_submissions WHERE id = ?1 LIMIT 1")
      .bind(id)
      .first();
  } catch (_) {}
  // Same answer for "no such row" and "somebody else's row", deliberately, so
  // this cannot be used to probe whether an id exists.
  if (!row || String(row.fellow ?? "") !== String(fellow.id ?? "")) {
    return json(404, { ok: false, message: "We couldn't find that one." });
  }

  // An HQ removal is final from this side: a fellow's own remove must not
  // dissolve an HQ removal (which flips removed_by hq->fellow and clears the
  // retained url_key). Same 404 as a row that is not theirs.
  if (String(row.removed_by ?? "") === "hq") {
    return json(404, { ok: false, message: "We couldn't find that one." });
  }

  try {
    await env.DB
      .prepare("UPDATE fellow_submissions SET status = 'removed', removed_by = 'fellow', url_key = '', updated = ?1 WHERE id = ?2")
      .bind(pbNow(), id)
      .run();
  } catch (_) {
    return json(200, { ok: false, message: "That didn't save. Try once more?" });
  }
  return json(200, { ok: true });
}

// ===========================================================================
// POST /internal/fellows/submissions/remove  {id, reason?}  — HQ removal.
// url_key RETAINED. Requires internal key, fail-closed.
// ===========================================================================
export async function internalFellowsSubmissionsRemove(req: Request, env: FellowsEnv): Promise<Response> {
  const CTRL = /[ -]/g;
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal HQ is not configured" });
  if (!timingEqual(req.headers.get("X-Internal-Key") || "", key)) {
    return json(401, { error: "wrong key" });
  }

  let body: Record<string, unknown> = {};
  try { body = (await readBody(req)) || {}; } catch (_) {}
  const id = String(body.id ?? "").trim();
  if (!id) return json(400, { error: "which submission?" });
  const reason = String(body.reason ?? "").replace(CTRL, " ").slice(0, 500);

  let row: Record<string, unknown> | null = null;
  try {
    row = await env.DB
      .prepare("SELECT * FROM fellow_submissions WHERE id = ?1 LIMIT 1")
      .bind(id)
      .first();
  } catch (_) {}
  if (!row) return json(404, { error: "no such submission" });

  const flags = String(row.flags ?? "");
  const newFlags = (flags ? flags + " | " : "") + "removed by HQ" + (reason ? ": " + reason : "");
  try {
    await env.DB
      .prepare("UPDATE fellow_submissions SET status = 'removed', removed_by = 'hq', flags = ?1, updated = ?2 WHERE id = ?3")
      .bind(newFlags, pbNow(), id)
      .run();
  } catch (_) {
    return json(500, { error: "couldn't save that" });
  }

  try {
    const subject = "Removed submission " + String(row.url_key ?? "")
      + (reason ? " — " + reason.slice(0, 80) : "");
    await env.DB
      .prepare("INSERT INTO internal_activity (id, actor, actor_name, action, subject, ref, created) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)")
      .bind(newRecordId(), "", "Fellowships", "fellow.submission_removed", subject, id, pbNow())
      .run();
  } catch (_) {}

  return json(200, { ok: true });
}

// ===========================================================================
// POST /internal/fellows/submissions/release  {id, reason?}  — HQ releases a
// retained url_key. status stays "removed"; the released key is written into
// flags (terminated by ';') and the activity feed. Requires internal key.
// ===========================================================================
export async function internalFellowsSubmissionsRelease(req: Request, env: FellowsEnv): Promise<Response> {
  const CTRL = /[ -]/g;
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal HQ is not configured" });
  if (!timingEqual(req.headers.get("X-Internal-Key") || "", key)) {
    return json(401, { error: "wrong key" });
  }

  let body: Record<string, unknown> = {};
  try { body = (await readBody(req)) || {}; } catch (_) {}
  const id = String(body.id ?? "").trim();
  if (!id) return json(400, { error: "which submission?" });
  const reason = String(body.reason ?? "").replace(CTRL, " ").slice(0, 500);

  let row: Record<string, unknown> | null = null;
  try {
    row = await env.DB
      .prepare("SELECT * FROM fellow_submissions WHERE id = ?1 LIMIT 1")
      .bind(id)
      .first();
  } catch (_) {}
  if (!row) return json(404, { error: "no such submission" });

  // A live row keeps its key — release is a thing you do to a removal.
  if (String(row.status ?? "") !== "removed") {
    return json(409, { error: "that one hasn't been removed — remove it first" });
  }
  const released = String(row.url_key ?? "");
  if (!released) return json(200, { ok: true, already: true, released: "" });

  const flags = String(row.flags ?? "");
  // The semicolon terminator is load-bearing: the submissions route matches on
  // this exact string, and it stops "…: x:20" matching inside "…: x:2012345".
  const newFlags = ((flags ? flags + " | " : "") + "key released by HQ: " + released + ";"
    + (reason ? " " + reason : "")).slice(0, 1000);
  try {
    await env.DB
      .prepare("UPDATE fellow_submissions SET url_key = '', flags = ?1, updated = ?2 WHERE id = ?3")
      .bind(newFlags, pbNow(), id)
      .run();
  } catch (_) {
    return json(500, { error: "couldn't save that" });
  }

  try {
    const subject = "Released " + released + " — anyone but " + String(row.fellow ?? "")
      + " may log it again" + (reason ? ": " + reason.slice(0, 80) : "");
    await env.DB
      .prepare("INSERT INTO internal_activity (id, actor, actor_name, action, subject, ref, created) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)")
      .bind(newRecordId(), "", "Fellowships", "fellow.submission_released", subject, id, pbNow())
      .run();
  } catch (_) {}

  return json(200, { ok: true, released: released });
}

// ===========================================================================
// POST /internal/fellows/remove  {fellow_id, reason?}  — soft removal of a
// fellow. Row stays; code stops crediting; signed out everywhere. Internal key.
// ===========================================================================
export async function internalFellowsRemove(req: Request, env: FellowsEnv): Promise<Response> {
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal HQ is not configured" });
  if (!timingEqual(req.headers.get("X-Internal-Key") || "", key)) {
    return json(401, { error: "wrong key" });
  }

  let body: Record<string, unknown> = {};
  try { body = (await readBody(req)) || {}; } catch (_) {}
  const id = String(body.fellow_id ?? "").trim();
  if (!id) return json(400, { error: "which fellow?" });

  let fellow: Record<string, unknown> | null = null;
  try {
    fellow = await env.DB
      .prepare("SELECT * FROM fellows WHERE id = ?1 LIMIT 1")
      .bind(id)
      .first();
  } catch (_) {}
  if (!fellow) return json(404, { error: "no such fellow" });

  const who = String(fellow.name ?? "") || String(fellow.email ?? "");
  try {
    await env.DB
      .prepare("UPDATE fellows SET status = 'removed', code_active = 0, code_revoked = 1, session_hash = '', updated = ?1 WHERE id = ?2")
      .bind(pbNow(), id)
      .run();
  } catch (_) {
    return json(500, { error: "couldn't save that" });
  }

  try {
    const subject = "Removed " + who + (body.reason ? " — " + String(body.reason).slice(0, 80) : "");
    await env.DB
      .prepare("INSERT INTO internal_activity (id, actor, actor_name, action, subject, ref, created) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)")
      .bind(newRecordId(), "", "Fellowships", "fellow.removed", subject, id, pbNow())
      .run();
  } catch (_) {}

  return json(200, { ok: true, removed: who });
}


// --- /fellows/apply   risk=HIGH ---
export async function fellowsApply(req: Request, env: FellowsEnv): Promise<Response> {
  const sha256 = (s: string) => sha256Hex(s);

  const token = req.headers.get("X-Fellow-Token") || "";
  if (!token) return json(401, { reauth: true });

  let fellow: Record<string, unknown> | null = null;
  try {
    fellow = await env.DB.prepare(
      "SELECT * FROM fellows WHERE session_hash = ?1 LIMIT 1",
    ).bind(await sha256(token)).first();
  } catch (_) { fellow = null; }

  // A removal signs them out, but a token that is still in flight must not
  // outlive it either.
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(401, { reauth: true });
  const sexp = Date.parse(String(fellow.session_expires ?? ""));
  if (isNaN(sexp) || Date.now() > sexp) return json(401, { reauth: true });

  const body = await readBody(req);
  const fellowship = String(body.fellowship || "growth").trim().toLowerCase();
  if (fellowship !== "growth") {
    return json(200, { ok: false, message: "That one isn't open yet. Growth & Marketing is the one taking people right now." });
  }
  if (body.terms !== true) {
    return json(200, { ok: false, message: "Have a read of the terms and tick the box, then we'll carry on." });
  }
  const answers: Record<string, unknown> =
    body.answers && typeof body.answers === "object" ? (body.answers as Record<string, unknown>) : {};
  const flat = Object.keys(answers).map((k) => k + ": " + String(answers[k] || "").slice(0, 1200)).join("\n");
  if (flat.length > 8000) return json(200, { ok: false, message: "That's a lot of words. Trim it a little and send again." });

  const email = String(fellow.email ?? "");

  // already in?
  try {
    const prior = await env.DB.prepare(
      "SELECT * FROM fellow_applications WHERE email = ?1 AND fellowship = ?2 AND ai_verdict != 'ask_more' LIMIT 1",
    ).bind(email, fellowship).first();
    if (prior) {
      return json(200, {
        ok: true, verdict: "accept", already: true,
        message: "You're already in. Head straight to the lessons.",
        fellow: {
          status: String(fellow.status ?? "") || "accepted",
          fellowship: String(fellow.fellowship ?? "") || fellowship,
          referral_code: String(fellow.referral_code ?? ""),
          code_active: boolTrue(fellow.code_active),
          age_band: String(fellow.age_band ?? ""),
          name: String(fellow.name ?? ""),
        },
      });
    }
  } catch (_) {}

  // A deterministic sanity check that runs whether or not the model is up.
  const words = flat.replace(/\w+:/g, " ").trim().split(/\s+/).filter(Boolean);
  const realish = words.length >= 12 && /[aeiou]{1,}/i.test(flat) && !/^(.)\1+$/.test(flat.replace(/\s/g, ""));

  const band = String(fellow.age_band ?? "");
  const firstName = String(fellow.name ?? "").trim().split(/\s+/)[0] || "there";

  let verdict = realish ? "fallback_accept" : "ask_more";
  let message = realish
    ? "You're in, " + firstName + ". You said what you wanted out of this and that's the whole bar — the rest we teach you."
    : "Give us one more real sentence — just what you actually want out of this. That's genuinely all we need.";
  let modelUsed = "", aiOk = false;

  const orKey = env.OPENROUTER_API_KEY || "";
  const ceiling = parseInt(env.ANTICIPY_FELLOW_LLM_CEILING || "120", 10);
  const hourNow = new Date().toISOString().slice(0, 13);
  let metered = false;
  try {
    const meter = await env.DB.prepare(
      "SELECT * FROM fellow_meter WHERE name = 'llm' LIMIT 1",
    ).first();
    if (meter) {
      const used = String(meter.hour ?? "") === hourNow ? (Number(meter.calls) || 0) : 0;
      if (used < ceiling) {
        await env.DB.prepare(
          "UPDATE fellow_meter SET hour = ?1, calls = ?2, updated = ?3 WHERE id = ?4",
        ).bind(hourNow, used + 1, pbNow(), String(meter.id)).run();
        metered = true;
      }
    }
  } catch (_) {}

  if (orKey && metered) {
    const model = env.ANTICIPY_FELLOW_MODEL || "google/gemini-3.7-flash";
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
      'Reply STRICT JSON: {"verdict":"accept"|"ask_more","message":"..."}',
    ].join("\n");
    try {
      const res = await fetch("https://openrouter.ai/api/v1/chat/completions", {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + orKey, "Content-Type": "application/json",
          "HTTP-Referer": "https://anticipy.ai", "X-Title": "Anticipy Fellowships",
        },
        body: JSON.stringify({
          model: model, temperature: 0.3, max_tokens: 2000,
          response_format: { type: "json_object" },
          messages: [{ role: "system", content: system }, { role: "user", content: flat }],
        }),
        signal: AbortSignal.timeout(14_000),
      });
      let text = "";
      try { text = ((await res.json()) as any).choices[0].message.content || ""; } catch (_) {}
      let parsed: any = null; try { parsed = JSON.parse(text); } catch (_) {}
      if (parsed && (parsed.verdict === "accept" || parsed.verdict === "ask_more") && parsed.message) {
        // If our own sanity check says the answers were real, an ask_more from
        // the model is overruled.
        verdict = (parsed.verdict === "ask_more" && realish) ? "accept" : parsed.verdict;
        message = String(parsed.message).slice(0, 600);
        modelUsed = model; aiOk = true;
      }
    } catch (_) {}
  }

  try {
    await env.DB.prepare(
      "INSERT INTO fellow_applications (id, fellow, email, fellowship, answers, ai_verdict, ai_message, ai_ok, model, terms_accepted_at, created) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11)",
    ).bind(
      newRecordId(), String(fellow.id), email, fellowship, flat.slice(0, 8000),
      verdict, message, aiOk ? 1 : 0, modelUsed, isoNow(), pbNow(),
    ).run();
  } catch (_) {}

  if (verdict === "ask_more") {
    try {
      await env.DB.prepare(
        "UPDATE fellows SET status = ?1, updated = ?2 WHERE id = ?3",
      ).bind("needs_more", pbNow(), String(fellow.id)).run();
    } catch (_) {}
    return json(200, { ok: true, verdict: "ask_more", message: message });
  }

  // Status is a consequence of a written application. Email is a consequence
  // of a written status. Never the reverse.
  const setCols: string[] = ["fellowship = ?", "status = ?"];
  const setVals: unknown[] = [fellowship, "accepted"];
  let codeActive = boolTrue(fellow.code_active);
  if (String(fellow.age_band ?? "") === "18_plus") {
    setCols.push("code_active = ?");
    setVals.push(1);
    codeActive = true;
  }

  const rk2 = env.RESEND_API_KEY || "";
  const site2 = env.ANTICIPY_SITE_URL || "https://www.anticipy.ai";
  const first = String(fellow.name ?? "").trim().split(/\s+/)[0];
  let confirmRaw = "";
  if (!String(fellow.email_confirmed_at ?? "")) {
    confirmRaw = randomHex(48);
    setCols.push("consent_token_hash = ?");
    setVals.push(await sha256(confirmRaw));
  }

  setCols.push("updated = ?");
  setVals.push(pbNow());
  setVals.push(String(fellow.id));
  const setSql = setCols.map((c, i) => c.replace("?", "?" + (i + 1))).join(", ");

  // NOTHING LEAVES THE BUILDING UNTIL THIS RETURNS.
  try {
    await env.DB.prepare(
      "UPDATE fellows SET " + setSql + " WHERE id = ?" + setVals.length,
    ).bind(...setVals).run();
  } catch (err) {
    return json(200, { ok: false, message: "We couldn't save that. Nothing's lost — press it once more." });
  }

  // Guarded, so a retry, a double-click or a re-send cannot mail anyone twice.
  if (rk2 && !String(fellow.welcome_sent_at ?? "")) {
    const confirmLine = confirmRaw
      ? "\n\nWhen you're ready to get paid, tap this once so we know the address is yours:\n"
        + site2 + "/fellows/confirm?t=" + confirmRaw
      : "";
    const subject = (first ? first + ", you're in" : "You're in");
    const text = (first ? first + ", you're in." : "You're in.")
      + "\n\nStart here — unit 0 is five minutes and it's just what this thing is.\n"
      + site2 + "/fellowship-growth-learning"
      + "\n\nYour link, for when you start posting:\n"
      + site2 + "/r/" + String(fellow.referral_code ?? "")
      + "\n\n$30 when someone buys through it. $15 clears 14 days after they buy, and the"
      + "\nother $15 when their pendant actually ships — pendants ship late 2026, so that"
      + "\nhalf is a real wait. We split it so a refund never takes money back out of your"
      + "\naccount."
      + confirmLine
      + "\n\nThat's everything. Go make something.";
    const sent = await sendResendEmail(env, email, subject, text);
    if (sent) {
      try {
        await env.DB.prepare(
          "UPDATE fellows SET welcome_sent_at = ?1, updated = ?2 WHERE id = ?3",
        ).bind(isoNow(), pbNow(), String(fellow.id)).run();
      } catch (_) {}
    }
  }

  // Tell HQ, so a real person knows someone joined.
  try {
    await env.DB.prepare(
      "INSERT INTO internal_activity (id, actor, actor_name, action, subject, ref, created) VALUES (?1,?2,?3,?4,?5,?6,?7)",
    ).bind(
      newRecordId(), "", "Fellowships", "fellow.joined",
      (String(fellow.name ?? "") || email) + " joined the Growth fellowship",
      String(fellow.id), pbNow(),
    ).run();
  } catch (_) {}

  return json(200, {
    ok: true, verdict: "accept", message: message,
    fellow: {
      status: "accepted", fellowship: fellowship,
      referral_code: String(fellow.referral_code ?? ""),
      code_active: codeActive,
      age_band: String(fellow.age_band ?? ""),
    },
  });
}


// --- /fellows/start   risk=HIGH ---
export async function fellowsStart(req: Request, env: FellowsEnv): Promise<Response> {
  const nowMs = Date.now();

  // route-local: crypto-based generator over the source's ambiguity-free alphabet
  const CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789";
  const makeCode = (): string => {
    const bytes = new Uint8Array(6);
    crypto.getRandomValues(bytes);
    let out = "";
    for (let i = 0; i < 6; i++) out += CODE_ALPHABET.charAt(bytes[i] % CODE_ALPHABET.length);
    return out;
  };

  const body = (await readBody(req)) as Record<string, any>;
  const email = String(body.email || "").trim().toLowerCase();
  const name = String(body.name || "").trim().slice(0, 120);
  const bm = parseInt(String(body.birth_month ?? ""), 10);
  const by = parseInt(String(body.birth_year ?? ""), 10);
  const country = String(body.country || "").trim().toLowerCase();

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) || email.length > 254) {
    return json(200, { ok: false, field: "email", message: "That email doesn't look right." });
  }
  const domain = email.split("@")[1] || "";
  const BURNER = ["mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
                  "yopmail.com", "trashmail.com", "sharklasers.com", "getnada.com", "temp-mail.org"];
  if (BURNER.indexOf(domain) >= 0) {
    return json(200, { ok: false, field: "email",
      message: "We can't pay a throwaway address. Use one you'll still have in a month." });
  }

  // ---- AGE FIRST. Nothing is written before this passes. ------------------
  if (!(bm >= 1 && bm <= 12) || !(by >= 1900 && by <= 2100)) {
    return json(200, { ok: false, field: "birth", message: "Pick the month and year you were born." });
  }
  const now = new Date();
  let age = now.getUTCFullYear() - by;
  if (now.getUTCMonth() + 1 < bm) age -= 1;
  if (age < 13) {
    return json(200, { ok: false, stop: true,
      message: "You have to be 13 to join this one. Come back on your birthday — we'll still be here, and we'd genuinely like to have you." });
  }
  if (country !== "us" && country !== "ca") {
    return json(200, { ok: false, stop: true,
      message: "Right now we can only take fellows in the US and Canada, because that's where we can pay people properly." });
  }
  const band = age >= 18 ? "18_plus" : (age >= 16 ? "16_17" : "13_15");

  // Per-address throttle, so this route cannot be used as a spam cannon.
  const ip = resolveClientIP(req);
  if (ip && ip !== "127.0.0.1" && ip !== "::1") {
    try {
      const recent = await env.DB.prepare(
        "SELECT created FROM fellows WHERE ip_address = ?1 ORDER BY created DESC LIMIT ?2 OFFSET ?3",
      ).bind(ip, 30, 0).all();
      let n = 0;
      for (const r of (recent.results as Array<Record<string, any>>)) {
        const t = Date.parse(String(r.created ?? "").replace(" ", "T"));
        if (!isNaN(t) && nowMs - t < 3600000) n++;
      }
      if (n >= 6) {
        return json(200, { ok: false,
          message: "That's a lot of signups from one place. Give it an hour." });
      }
    } catch (_) { /* a throttle-check failure must not cost the signup */ }
  }

  let row: Record<string, any> | null = null;
  try {
    row = await env.DB.prepare(
      "SELECT * FROM fellows WHERE email = ?1 LIMIT 1").bind(email).first<Record<string, any>>();
  } catch (_) { row = null; }
  const isNew = !row;

  // REMOVAL HAS TO BE REMOVAL. Routes to a human; deliberately does not confirm
  // that an address is on file.
  if (row && String(row.status ?? "") === "removed") {
    return json(200, { ok: false,
      message: "We can't set that up from here. Write to hello@anticipy.ai and a person will sort it." });
  }

  const id = isNew ? newRecordId() : String(row!.id);
  const nowPb = pbNow();

  // Working record: defaults for a new row, a copy of the DB row otherwise.
  // Columns the source never touches keep their seeded (row/default) values,
  // so the UPDATE below can write the whole writable set without clobbering.
  const rec: Record<string, any> = isNew
    ? {
        id, email,
        name: "",
        birth_month: bm,
        birth_year: by,
        age_band: "",
        country: "",
        parental_consent: "",
        referral_code: makeCode(),
        code_active: 0,
        code_revoked: 0,
        clicks_total: 0,
        payout_method: "card",
        ip_address: ip,
        status: "",
        session_hash: "",
        session_expires: "",
        fellowship: "",
        email_confirmed_at: "",
      }
    : { ...row };

  if (name) rec.name = name;
  rec.age_band = band;
  rec.country = country === "ca" ? "ca" : "us";
  // Turning 18 clears the requirement; nothing else touches a confirmed consent.
  if (band === "18_plus") rec.parental_consent = "not_required";
  else if (String(rec.parental_consent ?? "") !== "confirmed") rec.parental_consent = "pending";
  // Typing an email creates an ACCOUNT, not an acceptance.
  if (!String(rec.status ?? "")) rec.status = "new";
  // Only ever on a NEW row: never switch off an existing earning fellow's code.
  if (isNew) rec.code_active = 0;

  // No email leaves at signup; this token only opens a session. Its hash is the
  // session, not the confirm link (that is minted in /fellows/apply).
  const token = randomHex(48);
  rec.session_hash = await sha256Hex(token);
  rec.session_expires = isoNow(new Date(nowMs + 90 * 86400000));

  try {
    if (isNew) {
      await env.DB.prepare(
        "INSERT INTO fellows (id, email, name, birth_month, birth_year, age_band, country, "
        + "parental_consent, referral_code, code_active, code_revoked, clicks_total, payout_method, "
        + "ip_address, status, session_hash, session_expires, created, updated) "
        + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,?17,?18,?19)",
      ).bind(
        id, email, String(rec.name ?? ""), bm, by, band, rec.country,
        rec.parental_consent, rec.referral_code, rec.code_active, 0, 0, "card",
        ip, rec.status, rec.session_hash, rec.session_expires, nowPb, nowPb,
      ).run();
    } else {
      await env.DB.prepare(
        "UPDATE fellows SET name = ?1, age_band = ?2, country = ?3, parental_consent = ?4, "
        + "status = ?5, session_hash = ?6, session_expires = ?7, updated = ?8 WHERE id = ?9",
      ).bind(
        String(rec.name ?? ""), band, rec.country, rec.parental_consent,
        rec.status, rec.session_hash, rec.session_expires, nowPb, id,
      ).run();
    }
  } catch (_) {
    return json(200, { ok: false, message: "Something went wrong saving that. Try once more?" });
  }

  // Best-effort activity log. No email at signup by design.
  try {
    await env.DB.prepare(
      "INSERT INTO internal_activity (id, created, actor, actor_name, action, subject, verb, ref) "
      + "VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
    ).bind(
      newRecordId(), pbNow(), "", "Fellowships", "fellow.started",
      (name || email) + " started a fellowship application", "", id,
    ).run();
  } catch (_) { /* the log is not the transaction */ }

  return json(200, {
    ok: true, token: token,
    fellow: {
      id: id, email: email, name: String(rec.name ?? ""),
      age_band: band, country: String(rec.country ?? ""),
      status: String(rec.status ?? "") || "new",
      fellowship: String(rec.fellowship ?? "") || "",
      referral_code: String(rec.referral_code ?? ""),
      code_active: boolTrue(rec.code_active),
      email_confirmed: String(rec.email_confirmed_at ?? "") !== "",
    },
  });
}


// --- /fellows/guardian/link, /fellows/guardian   risk=HIGH ---
export async function fellowsGuardianLink(req: Request, env: FellowsEnv): Promise<Response> {
  const sha256 = (s: string) => sha256Hex(s);
  const site = (env.ANTICIPY_SITE_URL || "https://www.anticipy.ai");

  const token = req.headers.get("X-Fellow-Token") || "";
  if (!token) return json(401, { reauth: true });

  let fellow: Record<string, unknown> | null = null;
  try {
    fellow = await env.DB.prepare("SELECT * FROM fellows WHERE session_hash = ?1 LIMIT 1")
      .bind(await sha256(token)).first();
  } catch (_) {}
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(401, { reauth: true });

  if (String(fellow.age_band ?? "") === "18_plus") {
    return json(200, { ok: false, message: "You're 18 or over, so there's no guardian step." });
  }
  if (String(fellow.parental_consent ?? "") === "confirmed") {
    return json(200, { ok: true, done: true,
      message: "Already done — " + (String(fellow.guardian_name ?? "") || "your guardian") + " completed this." });
  }

  const raw = randomHex(48);
  try {
    await env.DB.prepare("UPDATE fellows SET guardian_token_hash = ?1, updated = ?2 WHERE id = ?3")
      .bind(await sha256(raw), pbNow(), String(fellow.id)).run();
  } catch (_) {
    return json(200, { ok: false, message: "Couldn't make that link. Try once more?" });
  }

  return json(200, { ok: true, url: site + "/fellows/guardian?t=" + raw });
}

export async function fellowsGuardianGet(req: Request, env: FellowsEnv): Promise<Response> {
  const sha256 = (s: string) => sha256Hex(s);
  const esc = (s: unknown) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  const html = (status: number, s: string) =>
    new Response(s, { status, headers: { "Content-Type": "text/html; charset=utf-8" } });

  let raw = "";
  try { raw = String(new URL(req.url).searchParams.get("t") || ""); } catch (_) {}
  raw = raw.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);

  let fellow: Record<string, unknown> | null = null;
  if (raw) {
    try {
      fellow = await env.DB.prepare("SELECT * FROM fellows WHERE guardian_token_hash = ?1 LIMIT 1")
        .bind(await sha256(raw)).first();
    } catch (_) {}
  }
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;

  const first = fellow ? (String(fellow.name ?? "").trim().split(/\s+/)[0] || "your child") : "";
  const already = !!fellow && String(fellow.parental_consent ?? "") === "confirmed";

  const HEAD = '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1">'
    + '<title>Anticipy — one step for a parent or guardian</title>'
    + '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 32 32\'%3E%3Crect width=\'32\' height=\'32\' fill=\'%23FAF8F4\'/%3E%3Ccircle cx=\'16\' cy=\'16\' r=\'7\' fill=\'%23C8A97E\'/%3E%3C/svg%3E">'
    + '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    + '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">'
    + '<style>'
    + ':root{color-scheme:light;--ink:#171512;--ink-2:#6B665E;--paper:#FAF8F4;--paper-2:#F0EDE6;'
    + '--rule-2:#D6D0C4;--rule-3:#B6AC99;--accent:#C8A97E;--accent-ink:#8A6B44;--accent-ink-2:#7E6140;'
    + '--danger:#A33A3A;--ok:#2E6B4F;--field:#FFFFFF;'
    + "--serif:'DM Serif Display',Georgia,serif;--sans:'Plus Jakarta Sans',-apple-system,BlinkMacSystemFont,sans-serif;"
    + '--mono:ui-monospace,SFMono-Regular,Menlo,monospace}'
    + '*{box-sizing:border-box;margin:0;padding:0}'
    + 'body{background:var(--paper);color:var(--ink);font:300 17px/1.7 var(--sans);letter-spacing:.01em;'
    + '-webkit-font-smoothing:antialiased;padding:40px 24px 80px}'
    + 'main{max-width:620px;margin:0 auto}'
    + '.dot{width:7px;height:7px;border-radius:50%;background:var(--accent);display:inline-block;margin-right:9px}'
    + '.brand{font:400 15px/1 var(--serif)}'
    + '.rule38{width:38px;height:2px;background:var(--accent);margin:26px 0 18px}'
    + 'h1{font:400 clamp(30px,5.4vw,44px)/1.05 var(--serif);letter-spacing:-.035em}'
    + 'p{margin-top:14px;max-width:34em}.small{font-size:15.5px;color:var(--ink-2);line-height:1.65}'
    + '.tiny{font-size:13.5px;color:var(--ink-2);line-height:1.6;margin-top:10px}'
    + '.eyebrow{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;'
    + 'color:var(--accent-ink);display:block;margin-bottom:14px}'
    + '.card{background:var(--paper-2);border:1px solid var(--rule-2);border-radius:14px;padding:26px;margin-top:26px}'
    + '.card .eyebrow{color:var(--accent-ink-2)}'
    + '.rows{margin-top:8px;border-top:1px solid var(--rule-2)}'
    + '.row{padding:13px 0;border-bottom:1px solid var(--rule-2);font-size:15.5px;line-height:1.55}'
    + '.row b{font-weight:500}'
    + 'label{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.12em;'
    + 'text-transform:uppercase;color:var(--accent-ink);margin:22px 0 6px}'
    + 'input[type=text],input[type=email]{background:transparent;border:0;border-bottom:1px solid var(--rule-2);'
    + 'color:var(--ink);padding:10px 0 12px;font:300 18px var(--sans);width:100%;outline:none;border-radius:0}'
    + 'input:focus{border-bottom-color:var(--accent-ink)}'
    + '.check{display:flex;gap:12px;align-items:flex-start;margin-top:26px;background:var(--field);'
    + 'border:1px solid var(--rule-3);border-radius:10px;padding:16px}'
    + '.check input{margin-top:4px;width:18px;height:18px;flex:none;accent-color:var(--accent-ink)}'
    + '.check span{font-size:15px;line-height:1.55}'
    + '.btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;background:var(--ink);'
    + 'color:var(--paper);border:0;border-radius:999px;padding:17px 34px;font:600 16.5px/1 var(--sans);'
    + 'cursor:pointer;margin-top:26px;width:100%;text-decoration:none}'
    + '.btn:disabled{opacity:.55;cursor:default}'
    + '.msg{margin-top:12px;font-size:14.5px;min-height:20px;color:var(--ink-2)}'
    + '.msg.err{color:var(--danger)}.msg.ok{color:var(--ok)}'
    + ':focus-visible{outline:2px solid var(--accent-ink);outline-offset:3px}'
    + 'a{color:var(--accent-ink)}'
    + '</style></head><body><main>'
    + '<span class="brand"><span class="dot"></span>Anticipy</span>';

  const FOOT = '</main></body></html>';

  if (!fellow) {
    return html(200, HEAD + '<div class="rule38"></div>'
      + '<h1>This link has expired.</h1>'
      + '<p class="small">Guardian links are single-use and a new one replaces the last. Ask the '
      + 'person who sent it to open their fellowship page and tap <b>Get the link for my parent</b> '
      + 'again — it takes them a second.</p>'
      + '<p class="small">Nothing is lost, and nothing is wrong with their account.</p>'
      + '<p class="tiny">If you think you got this in error, write to '
      + '<a href="mailto:hello@anticipy.ai">hello@anticipy.ai</a>.</p>' + FOOT);
  }

  if (already) {
    return html(200, HEAD + '<div class="rule38"></div>'
      + '<h1>Already done.</h1>'
      + '<p class="small">' + esc(first) + '&rsquo;s payouts are switched on. There is nothing '
      + 'further for you to do, and we won&rsquo;t email you again about it.</p>' + FOOT);
  }

  return html(200, HEAD
    + '<div class="rule38"></div>'
    + '<span class="eyebrow">One step, about two minutes</span>'
    + '<h1>' + esc(first) + ' joined the Anticipy fellowship.</h1>'
    + '<p>They&rsquo;re learning how short video actually works, and everything in the course is '
    + 'already open to them. The only thing waiting on you is <b>getting paid</b> — that&rsquo;s '
    + 'the law about paying under-18s, not a rule of ours.</p>'

    + '<div class="card"><span class="eyebrow">What this is</span>'
    + '<div class="rows">'
    + '<div class="row"><b>What they do.</b> Make short videos about Anticipy on their own '
    + 'accounts, if they want to. Posting is always optional and there is no quota and no deadline.</div>'
    + '<div class="row"><b>What they earn.</b> $30 when somebody buys through their link. One '
    + 'payment, 30 days after the purchase, and we never take it back.</div>'
    + '<div class="row"><b>How it arrives.</b> A prepaid Visa card, sent to the email address you '
    + 'give below. No bank account and no ID is needed from your child — that is the whole '
    + 'reason we pay this way.</div>'
    + '<div class="row"><b>What we don&rsquo;t ask for.</b> No social security number, no bank '
    + 'details, no photo, no address, no school.</div>'
    + '</div></div>'

    + '<label for="g-name">Your full name</label>'
    + '<input type="text" id="g-name" autocomplete="name" placeholder="Alex Rivera">'
    + '<label for="g-email">Your email — this is where the card is sent</label>'
    + '<input type="email" id="g-email" autocomplete="email" inputmode="email" placeholder="you@example.com">'

    + '<div class="check"><input type="checkbox" id="g-affirm">'
    + '<span>I am ' + esc(first) + '&rsquo;s parent or legal guardian, I am over 18, and I accept '
    + 'these terms both on their behalf and in my own name as the person the money is paid to. '
    + 'I understand the reward is taxable income and that Anticipy does not give tax advice.</span></div>'

    + '<button class="btn" id="g-go">Switch on ' + esc(first) + '&rsquo;s payouts</button>'
    + '<div class="msg" id="g-msg" role="status"></div>'
    + '<p class="tiny">We keep your name, your email, the date, and which version of these terms '
    + 'you agreed to. That is all, and it is only so we can show this step happened. '
    + 'Questions: <a href="mailto:hello@anticipy.ai">hello@anticipy.ai</a>.</p>'

    + '<script>'
    + 'var T=' + JSON.stringify(raw) + ';'
    + 'function $(i){return document.getElementById(i)}'
    + 'function say(t,k){var m=$("g-msg");m.textContent=t||"";m.className="msg"+(t&&k?" "+k:"")}'
    + '$("g-go").addEventListener("click",function(){'
    + 'var n=$("g-name").value.trim(),em=$("g-email").value.trim(),a=$("g-affirm").checked;'
    + 'if(!n)return say("We need your name.","err");'
    + 'if(!/^[^\\s@]+@[^\\s@]+\\.[^\\s@]{2,}$/.test(em))return say("That email doesn\'t look right.","err");'
    + 'if(!a)return say("Please tick the box — it\'s the part that actually counts.","err");'
    + 'var b=this;b.disabled=true;b.textContent="One moment…";say("");'
    + 'fetch("/fellows/guardian",{method:"POST",headers:{"Content-Type":"application/json"},'
    + 'body:JSON.stringify({t:T,guardian_name:n,guardian_email:em,affirm:true})})'
    + '.then(function(r){return r.json()}).then(function(j){'
    + 'if(!j||!j.ok){b.disabled=false;b.textContent="Try that again";return say((j&&j.message)||"That didn\'t work.","err")}'
    + 'document.querySelector("main").innerHTML='
    + '\'<span class="brand"><span class="dot"></span>Anticipy</span><div class="rule38"></div>\''
    + '+\'<h1>Done — thank you.</h1><p class="small">\'+j.message+\'</p>\';'
    + '}).catch(function(){b.disabled=false;b.textContent="Try that again";say("We couldn\'t reach our end. Try once more.","err")});'
    + '});'
    + '</script>' + FOOT);
}

export async function fellowsGuardianPost(req: Request, env: FellowsEnv): Promise<Response> {
  const sha256 = (s: string) => sha256Hex(s);
  const TERMS = "2026-08-22";

  const body = await readBody(req);
  const raw = String(body.t || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
  const name = String(body.guardian_name || "").trim().slice(0, 120);
  const email = String(body.guardian_email || "").trim().toLowerCase().slice(0, 254);

  if (!raw) return json(200, { ok: false, message: "That link is missing something. Ask for a fresh one." });
  if (!name) return json(200, { ok: false, message: "We need your name." });
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
    return json(200, { ok: false, message: "That email doesn't look right." });
  }
  if (body.affirm !== true) {
    return json(200, { ok: false, message: "Please tick the box — it's the part that actually counts." });
  }

  let fellow: Record<string, unknown> | null = null;
  try {
    fellow = await env.DB.prepare("SELECT * FROM fellows WHERE guardian_token_hash = ?1 LIMIT 1")
      .bind(await sha256(raw)).first();
  } catch (_) {}
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(200, { ok: false, message: "That link has expired. Ask for a fresh one." });

  if (String(fellow.age_band ?? "") === "18_plus") {
    return json(200, { ok: false, message: "This account doesn't need a guardian step." });
  }
  if (String(fellow.parental_consent ?? "") === "confirmed") {
    return json(200, { ok: true, message: "This was already done. Nothing further is needed." });
  }

  const ip = resolveClientIP(req);

  const payoutMethod = String(fellow.payout_method ?? "") || "card";

  try {
    await env.DB.prepare(
      "UPDATE fellows SET guardian_name = ?1, guardian_email = ?2, guardian_consent_at = ?3, "
      + "guardian_consent_ip = ?4, guardian_terms_version = ?5, parental_consent = ?6, code_active = ?7, "
      + "payout_method = ?8, guardian_token_hash = ?9, updated = ?10 WHERE id = ?11")
      .bind(name, email, isoNow(), ip, TERMS, "confirmed", 1, payoutMethod, "", pbNow(), String(fellow.id))
      .run();
  } catch (_) {
    return json(200, { ok: false, message: "We couldn't save that. Nothing's lost — press it once more." });
  }

  try {
    await env.DB.prepare(
      "INSERT INTO internal_activity (id, actor, actor_name, action, subject, ref, created) "
      + "VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)")
      .bind(newRecordId(), "", "Fellowships", "fellow.guardian_confirmed",
        name + " confirmed guardianship for " + (String(fellow.name ?? "") || String(fellow.email ?? "")),
        String(fellow.id), pbNow())
      .run();
  } catch (_) {}

  const first = String(fellow.name ?? "").trim().split(/\s+/)[0] || "They";
  return json(200, { ok: true,
    message: first + "'s payouts are switched on. When something they make sells one, the card comes to "
      + email + " thirty days later. There is nothing else for you to do." });
}


// --- /fellows/submissions   risk=MEDIUM ---
export async function fellowsSubmissions(req: Request, env: FellowsEnv): Promise<Response> {
  const scrub = (s: unknown, n: number) => String(s == null ? "" : s)
    .replace(/[ -]/g, " ").replace(/\s+/g, " ").trim().slice(0, n);
  const pbTime = (v: unknown) => {
    if (!v) return NaN;
    let t = String(v).trim().replace(" ", "T");
    if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(t)) t += "Z";
    return new Date(t).getTime();
  };
  const nowISO = isoNow();

  const token = req.headers.get("X-Fellow-Token") || "";
  if (!token) return json(401, { reauth: true });
  let fellow: any = null;
  try {
    fellow = await env.DB.prepare("SELECT * FROM fellows WHERE session_hash = ?1 LIMIT 1")
      .bind(await sha256Hex(token)).first<any>();
  } catch (_) { fellow = null; }
  if (fellow && String(fellow.status ?? "") === "removed") fellow = null;
  if (!fellow) return json(401, { reauth: true });
  const sexp = Date.parse(String(fellow.session_expires ?? ""));
  if (isNaN(sexp) || Date.now() > sexp) return json(401, { reauth: true });

  const body = await readBody(req);
  const pasted = String(body.url == null ? "" : body.url);
  const note = scrub(body.note, 500);
  const band = String(fellow.age_band ?? "");

  // ==== fellowship url parser 8<==========================================
  const parseSubmittedUrl = (input: string, ageBand: string): any => {
    const UNDER_16 = ageBand === "13_15";
    const PLATFORMS = UNDER_16
      ? "TikTok, Instagram, YouTube and X"
      : "TikTok, Instagram, YouTube, X and LinkedIn";

    const parse1 = (input2: string): any => {
      const no = (code: string, message: string, platform?: string) =>
        ({ ok: false, code: code, message: message, platform: platform || "" });
      const num = (s: string) => { const t = String(s).replace(/^0+/, ""); return t === "" ? "0" : t; };

      let u = String(input2 == null ? "" : input2).trim();
      if (!u) {
        return no("junk", "Paste the link to what you made. We track " + PLATFORMS + ".");
      }
      if (u.length > 2048) {
        return no("junk", "That's far too long to be a link — paste just the address of the post.");
      }
      u = u.replace(/[​-‍⁠﻿‪-‮⁦-⁩]/g, "");
      const scheme = u.match(/^([A-Za-z][A-Za-z0-9+.\-]*):/);
      if (scheme && !/^https?$/i.test(scheme[1])) {
        return no("junk", "That isn't a web link. Paste the address of the post, starting with https.");
      }
      if (!/^https?:\/\//i.test(u)) u = "https://" + u;
      u = u.replace(/^https?:\/\//i, "https://");

      const split = u.match(/^https:\/\/([^\/?#]+)(.*)$/);
      if (!split || !split[1]) {
        return no("junk", "That doesn't look like a link. Paste the whole thing, starting with https. We track " + PLATFORMS + ".");
      }
      let host = split[1].toLowerCase();
      let rest = split[2] || "";
      if (!/^[a-z0-9.\-]+$/.test(host)) {
        return no("junk", "There's something odd in that address. Copy it again from the post itself.");
      }
      if (host.indexOf(".") < 0) {
        return no("junk", "That doesn't look like a link. Paste the whole thing, starting with https. We track " + PLATFORMS + ".");
      }
      rest = rest.split("#")[0];
      host = host.replace(/^(?:www|m|mobile)\./, "");
      if (host === "instagr.am") host = "instagram.com";
      if (host === "twitter.com") host = "x.com";
      const url = "https://" + host + rest;

      if (UNDER_16 && (host === "linkedin.com" || host === "lnkd.in")) {
        return no("age", "LinkedIn's own rules start at 16, so we'll skip that one for now.", "linkedin");
      }

      const TIKTOK_POST  = /^https:\/\/tiktok\.com\/@([A-Za-z0-9._]{1,24})\/(video|photo)\/(\d{6,25})(?:[\/?]|$)/;
      const TIKTOK_V     = /^https:\/\/tiktok\.com\/v\/(\d{6,25})(?:\.html)?(?:[\/?]|$)/;
      const TIKTOK_SHORT = /^https:\/\/(?:vm|vt)\.tiktok\.com\/[A-Za-z0-9]{4,24}/;
      const TIKTOK_T     = /^https:\/\/tiktok\.com\/t\/[A-Za-z0-9]{4,24}/;
      const INSTAGRAM    = /^https:\/\/instagram\.com\/(?:([A-Za-z0-9._]{1,30})\/)?(p|reel|reels|tv)\/([A-Za-z0-9_-]{5,24})(?:[\/?]|$)/;
      const YT_BE        = /^https:\/\/youtu\.be\/([A-Za-z0-9_-]{11})(?:[\/?]|$)/;
      const YT_PATH      = /^https:\/\/youtube\.com\/(shorts|embed|live|v)\/([A-Za-z0-9_-]{11})(?:[\/?]|$)/;
      const YT_WATCH     = /^https:\/\/youtube\.com\/watch\?(?:[^#]*&)?v=([A-Za-z0-9_-]{11})(?:&|$)/;
      const X_STATUS     = /^https:\/\/x\.com\/([A-Za-z0-9_]{1,15})\/status(?:es)?\/(\d{1,25})(?:[\/?]|$)/;
      const X_SHORT      = /^https:\/\/t\.co\/[A-Za-z0-9]{4,24}/;
      const LI_POSTS     = /^https:\/\/linkedin\.com\/posts\/[^\/?#]*?activity-(\d{10,25})/;
      const LI_UPDATE    = /^https:\/\/linkedin\.com\/feed\/update\/urn:li:(?:activity|share|ugcPost):(\d{10,25})/;
      const LI_PULSE     = /^https:\/\/linkedin\.com\/pulse\/([A-Za-z0-9\-]{3,80})(?:[\/?]|$)/;
      const LI_PULSE_LONG = /^https:\/\/linkedin\.com\/pulse\/[A-Za-z0-9\-]{81,}/;
      const LI_SHORT     = /^https:\/\/lnkd\.in\/[A-Za-z0-9_\-]{3,24}/;

      if (TIKTOK_SHORT.test(url) || TIKTOK_T.test(url)) {
        return no("short", "That's TikTok's short link — it doesn't say which video it is. Open it, then use Copy link from the video page; the one you want has your @name in it.", "tiktok");
      }
      if (X_SHORT.test(url)) {
        return no("short", "That's a t.co link, which doesn't say which post it is. Open it and copy the address from the top of the page.", "x");
      }
      if (LI_SHORT.test(url)) {
        return no("short", "That's an lnkd.in short link, which doesn't say which post it is. Open it and copy the address from the top of the page.", "linkedin");
      }

      let m: RegExpMatchArray | null;
      if ((m = url.match(TIKTOK_POST))) {
        const handle = m[1], id = num(m[3]);
        return { ok: true, platform: "tiktok", kind: m[2] === "photo" ? "photo" : "video",
                 native_id: id, url_key: "tiktok:" + id, author_claimed: handle,
                 url: "https://www.tiktok.com/@" + handle + "/video/" + id,
                 probe_url: "https://www.tiktok.com/@" + handle + "/video/" + id };
      }
      if ((m = url.match(TIKTOK_V))) {
        const id = num(m[1]);
        return { ok: true, platform: "tiktok", kind: "video",
                 native_id: id, url_key: "tiktok:" + id, author_claimed: "",
                 url: "https://www.tiktok.com/v/" + id + ".html",
                 probe_url: "https://www.tiktok.com/@i/video/" + id };
      }
      if ((m = url.match(INSTAGRAM))) {
        const user = m[1] || "", surface = m[2], code = m[3];
        const isReel = surface === "reel" || surface === "reels";
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
        return { ok: true, platform: "x", kind: "post", native_id: id,
                 url_key: "x:" + id, author_claimed: handle,
                 url: "https://x.com/" + handle + "/status/" + id,
                 probe_url: "https://x.com/" + handle + "/status/" + id };
      }
      if ((m = url.match(LI_POSTS)) || (m = url.match(LI_UPDATE))) {
        const id = num(m[1]);
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

      const KNOWN: Record<string, string> = { "tiktok.com": "TikTok", "instagram.com": "Instagram",
                      "youtube.com": "YouTube", "youtu.be": "YouTube",
                      "x.com": "X", "linkedin.com": "LinkedIn" };
      if (KNOWN[host]) {
        return no("not_a_post",
          "That's a " + KNOWN[host] + " link, but it points at a profile or a page rather than at one post. Open the post itself and copy the address from there.",
          host === "youtu.be" ? "youtube" : host.replace(/\.com$/, ""));
      }

      return no("unknown", "We only track " + PLATFORMS + " right now. If you made it somewhere else, tell us at hello@anticipy.ai — we'd genuinely like to know where you're posting.");
    };

    const first = parse1(input);
    if (!first.ok) return first;
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
    if (p.code === "junk") return json(400, { ok: false, field: "url", message: p.message });
    return json(200, { ok: false, field: "url", message: p.message });
  }

  if (p.platform === "linkedin" && band === "13_15") {
    return json(200, { ok: false, field: "url",
      message: "LinkedIn's own rules start at 16, so we'll skip that one for now." });
  }

  if (p.url_key.length > 120 || p.native_id.length > 80 || p.url.length > 500) {
    return json(200, { ok: false, field: "url",
      message: "That address is longer than we can store. Send it to hello@anticipy.ai and a person will add it by hand." });
  }

  const HANDLE_FIELD: Record<string, string> = { tiktok: "tiktok", youtube: "youtube", x: "x_handle" };
  const HANDLE_NAME: Record<string, string> = { tiktok: "TikTok", youtube: "YouTube", x: "X" };
  if (HANDLE_FIELD[p.platform]) {
    const claimed = String(fellow[HANDLE_FIELD[p.platform]] ?? "").trim();
    if (!claimed) {
      return json(200, { ok: false, field: "handle", need_handle: p.platform,
        message: "What's your " + HANDLE_NAME[p.platform] + " @? We'll put your posts next to it." });
    }
  }

  const fid = String(fellow.id);
  let mine: any[] = [];
  try {
    const r = await env.DB.prepare(
      "SELECT * FROM fellow_submissions WHERE fellow = ?1 ORDER BY created DESC LIMIT 500 OFFSET 0")
      .bind(fid).all<any>();
    mine = r.results || [];
  } catch (_) { mine = []; }
  if (mine.length >= 500) {
    return json(200, { ok: false,
      message: "That's five hundred logged, which is as many as we keep in one list. Write to hello@anticipy.ai and a person will sort it." });
  }
  const DAY_MAX = parseInt(String((env as any).ANTICIPY_FELLOW_SUBMIT_MAX || "20"), 10);
  let inDay = 0;
  for (const r of mine) {
    const t = pbTime(String(r.created ?? ""));
    if (!isNaN(t) && Date.now() - t < 86400000) inDay++;
  }
  if (inDay >= DAY_MAX) {
    return json(200, { ok: false, message: "That's a lot in one day. Try again tomorrow." });
  }

  const ATTEMPT_MAX = parseInt(String((env as any).ANTICIPY_FELLOW_SUBMIT_ATTEMPT_MAX || "60"), 10);
  const dayNow = nowISO.slice(0, 10);
  const attemptName = "sub:" + fid;
  let attemptMeter: any = null;
  try {
    attemptMeter = await env.DB.prepare("SELECT * FROM fellow_meter WHERE name = ?1 LIMIT 1")
      .bind(attemptName).first<any>();
  } catch (_) { attemptMeter = null; }
  let attemptIsNew = false;
  if (!attemptMeter) {
    attemptMeter = { name: attemptName, hour: dayNow, calls: 0 };
    attemptIsNew = true;
  }
  if (attemptMeter) {
    const usedToday = String(attemptMeter.hour ?? "") === dayNow
      ? (Number(attemptMeter.calls) || 0) : 0;
    if (usedToday >= ATTEMPT_MAX) {
      return json(200, { ok: false, message: "That's a lot in one day. Try again tomorrow." });
    }
    try {
      if (attemptIsNew) {
        const mid = newRecordId(); const mnow = pbNow();
        await env.DB.prepare(
          "INSERT INTO fellow_meter (id, name, hour, calls, created, updated) VALUES (?1,?2,?3,?4,?5,?6)")
          .bind(mid, attemptName, dayNow, usedToday + 1, mnow, mnow).run();
      } else {
        await env.DB.prepare("UPDATE fellow_meter SET hour = ?1, calls = ?2, updated = ?3 WHERE id = ?4")
          .bind(dayNow, usedToday + 1, pbNow(), String(attemptMeter.id)).run();
      }
    } catch (_) {}
  }

  let barred: any = null;
  try {
    barred = await env.DB.prepare(
      "SELECT * FROM fellow_submissions WHERE fellow = ?1 AND removed_by = 'hq' AND flags LIKE '%' || ?2 || '%' LIMIT 1")
      .bind(fid, "key released by HQ: " + p.url_key + ";").first<any>();
  } catch (_) { barred = null; }
  if (barred) {
    return json(200, { ok: false,
      message: "We can't add that one. If it's yours, write to hello@anticipy.ai and a person will sort it." });
  }

  const recId = newRecordId();
  const insNow = pbNow();
  let saved = false;
  try {
    await env.DB.prepare(
      "INSERT INTO fellow_submissions (id, fellow, platform, kind, url, url_key, submitted_url, native_id, author_handle, author_claimed, title, thumbnail_url, verify_state, verified_at, oembed_status, status, removed_by, note, flags, created, updated) VALUES (?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14,?15,?16,?17,?18,?19,?20,?21)")
      .bind(recId, fid, p.platform, p.kind, p.url, p.url_key, scrub(pasted, 500), p.native_id,
            "", scrub(p.author_claimed, 120), "", "", "unverified", "", 0, "logged", "", note, "",
            insNow, insNow).run();
    saved = true;
  } catch (_) { saved = false; }

  if (!saved) {
    let other: any = null;
    try {
      other = await env.DB.prepare("SELECT * FROM fellow_submissions WHERE url_key = ?1 LIMIT 1")
        .bind(p.url_key).first<any>();
    } catch (_) {}
    if (other && String(other.fellow ?? "") === fid) {
      const M = ["January", "February", "March", "April", "May", "June", "July",
                 "August", "September", "October", "November", "December"];
      let when = "";
      const t = pbTime(String(other.created ?? ""));
      if (!isNaN(t)) { const d = new Date(t); when = d.getUTCDate() + " " + M[d.getUTCMonth()]; }
      return json(200, { ok: true, already: true, id: other.id,
        message: when ? "You've already logged this one — you added it on " + when + "."
                      : "You've already logged this one." });
    }
    if (other) {
      try {
        await env.DB.prepare(
          "INSERT INTO internal_activity (id, actor, actor_name, action, subject, ref, created) VALUES (?1,?2,?3,?4,?5,?6,?7)")
          .bind(newRecordId(), "", "Fellowships", "fellow.submission_collision",
                "Two fellows claim " + p.url_key + " — held by " + String(other.fellow ?? "")
                  + ", also submitted by " + fid,
                String(other.id), pbNow()).run();
      } catch (_) {}
      return json(200, { ok: false,
        message: "We can't add that one. If it's yours, write to hello@anticipy.ai and a person will sort it." });
    }
    return json(200, { ok: false, message: "That didn't save. Try once more?" });
  }

  const OEMBED: Record<string, string> = {
    tiktok:  "https://www.tiktok.com/oembed?url=",
    youtube: "https://www.youtube.com/oembed?format=json&url=",
    x:       "https://publish.x.com/oembed?url=",
  };
  let mayCall = false;
  if (OEMBED[p.platform] && p.probe_url) {
    const ceiling = parseInt(String((env as any).ANTICIPY_FELLOW_OEMBED_CEILING || "300"), 10);
    const hourNow = nowISO.slice(0, 13);
    try {
      const meter: any = await env.DB.prepare("SELECT * FROM fellow_meter WHERE name = 'oembed' LIMIT 1")
        .first<any>();
      if (!meter) throw new Error("no meter");
      const used = String(meter.hour ?? "") === hourNow ? (Number(meter.calls) || 0) : 0;
      if (used < ceiling) {
        await env.DB.prepare("UPDATE fellow_meter SET hour = ?1, calls = ?2, updated = ?3 WHERE id = ?4")
          .bind(hourNow, used + 1, pbNow(), String(meter.id)).run();
        mayCall = true;
      }
    } catch (_) {}
  }

  let vstate = "unverified", vstatus = 0, author = "", title = "", thumb = "";
  if (mayCall) {
    let res: Response | null = null;
    try {
      const ctrl = new AbortController();
      const tid = setTimeout(() => ctrl.abort(), 8000);
      res = await fetch(OEMBED[p.platform] + encodeURIComponent(p.probe_url),
                        { method: "GET", signal: ctrl.signal });
      clearTimeout(tid);
    } catch (_) { res = null; }
    if (res) {
      vstatus = Number(res.status) || 0;
      if (vstatus >= 200 && vstatus < 300) {
        let j: any = null;
        try { j = await res.json(); } catch (_) { j = null; }
        if (j) {
          try {
            if (p.platform === "tiktok") {
              const mm = String(j.author_url || "").match(/tiktok\.com\/@([A-Za-z0-9._]{1,24})/);
              author = mm ? mm[1] : "";
              title = String(j.title || "");
              thumb = String(j.thumbnail_url || "");
            } else if (p.platform === "youtube") {
              const mm = String(j.author_url || "").match(/youtube\.com\/@([A-Za-z0-9._\-]{1,120})/);
              author = mm ? mm[1] : String(j.author_name || "");
              title = String(j.title || "");
              thumb = "https://i.ytimg.com/vi/" + p.native_id + "/hqdefault.jpg";
            } else if (p.platform === "x") {
              author = String(j.author_name || "");
              if (!author) {
                const mm = String(j.author_url || "").match(/x\.com\/([A-Za-z0-9_]{1,15})/);
                author = mm ? mm[1] : "";
              }
              const pm = String(j.html || "").match(/<p[^>]*>([\s\S]*?)<\/p>/);
              if (pm) title = pm[1].replace(/<[^>]*>/g, " ");
            }
          } catch (_) {}
        }
        const claimed = String(fellow[HANDLE_FIELD[p.platform] || ""] ?? "")
          .trim().replace(/^@/, "").toLowerCase();
        const got = String(author || "").trim().replace(/^@/, "").toLowerCase();
        vstate = (claimed && got) ? (claimed === got ? "verified" : "mismatch") : "unverified";
      } else if (vstatus === 400 || vstatus === 404) {
        vstate = "gone";
      }
    }
  }

  let fresh: any = null;
  try {
    fresh = await env.DB.prepare("SELECT * FROM fellow_submissions WHERE id = ?1 LIMIT 1")
      .bind(recId).first<any>();
  } catch (_) { fresh = null; }
  const stillOurs = !!fresh && String(fresh.status ?? "") === "logged"
                            && String(fresh.url_key ?? "") === p.url_key;

  let outStatus = "logged", outFlags = "", outAuthorHandle = "", outTitle = "", outThumb = "";
  if (stillOurs) {
    outStatus = String(fresh.status ?? "");
    outFlags = String(fresh.flags ?? "");
    outAuthorHandle = String(fresh.author_handle ?? "");
    outTitle = String(fresh.title ?? "");
    outThumb = String(fresh.thumbnail_url ?? "");
    if (author) outAuthorHandle = scrub(author, 120);
    if (title) outTitle = scrub(title, 500);
    if (thumb) outThumb = scrub(thumb, 500);
    if (vstate === "mismatch") {
      outStatus = "flagged";
      const had = String(fresh.flags ?? "");
      outFlags = (had ? had + " | " : "") + "author mismatch: the platform says "
               + scrub(author, 60) + ", their profile says "
               + scrub(String(fellow[HANDLE_FIELD[p.platform] || ""] ?? ""), 60);
    }
    try {
      await env.DB.prepare(
        "UPDATE fellow_submissions SET verify_state = ?1, oembed_status = ?2, verified_at = ?3, author_handle = ?4, title = ?5, thumbnail_url = ?6, status = ?7, flags = ?8, updated = ?9 WHERE id = ?10")
        .bind(vstate, vstatus, mayCall ? nowISO : "", outAuthorHandle, outTitle, outThumb,
              outStatus, outFlags, pbNow(), recId).run();
    } catch (_) {}
  }

  if (!stillOurs) {
    return json(200, { ok: true, already: true, id: recId,
      message: "That one came off your list while we were saving it." });
  }

  return json(200, {
    ok: true,
    submission: {
      id: recId,
      platform: p.platform,
      kind: p.kind,
      url: p.url,
      title: outTitle,
      thumbnail_url: outThumb,
      note: note,
      verify_state: vstate === "gone" ? "gone" : "",
      created: String(fresh.created ?? ""),
    }
  });
}

