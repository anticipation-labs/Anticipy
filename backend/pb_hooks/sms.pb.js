/// <reference path="../pb_data/types.d.ts" />

// Twilio inbound-SMS webhook. Twilio POSTs form-encoded From/Body here;
// the record it creates is picked up by the brain worker, which understands
// the reply and texts back over the live Twilio transport.

// EVERYTHING THIS ROUTE NEEDS IS DEFINED INSIDE THE HANDLER. PocketBase runs a
// registered handler in its own pooled JS runtime, so the enclosing file's
// top-level scope does not exist by the time a request arrives. Hoisting these
// helpers out of the function reads better and returns HTTP 400 "Something went
// wrong while processing your request" on every inbound text, with the
// ReferenceError visible nowhere useful (verified against a live PocketBase
// 0.30.4 on 2026-08-19). Only the runtime globals — $os, require, console,
// __hooks, Record — and `require()`d modules cross that boundary.
//
// TWILIO_AUTH_TOKEN IS LOAD-BEARING HERE AND CANNOT BE MIGRATED TO AN API KEY.
// Twilio signs an inbound webhook with the ACCOUNT AUTH TOKEN and with nothing
// else — there is no API-key equivalent for X-Twilio-Signature. Outbound has
// moved to TWILIO_API_KEY_SID + TWILIO_API_KEY_SECRET (brain/voice_arm.py
// `rest_credential`) precisely because a scoped key can be revoked, but this
// check has no such option. Anyone who "finishes" that migration by deleting
// TWILIO_AUTH_TOKEN from the backend service turns every text the owner sends
// into a 503 below, with the product looking simply deaf. Keep it set.
routerAdd("POST", "/sms/inbound", (e) => {
  // Twilio signs the EXACT URL it requested, so that URL is the one thing we
  // never have to be told. Deriving it from the request instead of from an env
  // var removes a whole class of dead-inbound outages: this endpoint lives on
  // the PocketBase service and the process that binds the number to it lives
  // on the worker service (brain/worker.py:340), so ANTICIPY_TWILIO_WEBHOOK_URL
  // had to be identical in two places nobody diffs. It was not, and the symptom
  // was zero inbound events from 2026-08-12 to 08-15, every text 403-ing, a
  // stale "?token=..." binding compared against a clean env URL
  // (brain/worker.py:382-387).
  //
  // Railway terminates TLS in front of us, so the scheme has to come from
  // X-Forwarded-Proto and the host from X-Forwarded-Host when the proxy
  // rewrites Host. Both scheme orders are tried because a wrong guess here is
  // a silent outage, and extra candidates cannot weaken anything: each one
  // still has to produce a matching HMAC under TWILIO_AUTH_TOKEN, which an
  // attacker who can set a Host header still does not have.
  const requestedUrls = () => {
    const out = [];
    const push = (url) => {
      if (url && out.indexOf(url) < 0) out.push(url);
    };
    try {
      const header = (name) =>
        String(e.request.header.get(name) || "").split(",")[0].trim();
      const host = header("X-Forwarded-Host") || String(e.request.host || "");
      const path = String(e.request.url.path || "");
      const rawQuery = String(e.request.url.rawQuery || "");
      const suffix = path + (rawQuery ? "?" + rawQuery : "");
      if (host && path) {
        const forwarded = header("X-Forwarded-Proto").toLowerCase();
        const schemes = forwarded === "http" ? ["http", "https"] : ["https", "http"];
        for (const scheme of schemes) push(scheme + "://" + host + suffix);
      }
    } catch (_) {
      // A runtime that stops exposing the request URL must not take inbound SMS
      // down with it; the pinned override below is the fallback, and having no
      // candidate at all is logged and refused rather than waved through.
    }
    // Still honoured, and still the escape hatch when a proxy mangles Host
    // beyond recognition: ANTICIPY_TWILIO_WEBHOOK_URL pins the exact URL.
    push($os.getenv("ANTICIPY_TWILIO_WEBHOOK_URL") || "");
    return out;
  };

  // Logged URLs never carry a query. The historical binding kept the shared
  // secret in "?token=...", and a log line is the one place it must not come back.
  const safeUrl = (url) => {
    const text = String(url || "");
    const cut = text.indexOf("?");
    return cut < 0 ? text : text.slice(0, cut) + "?<query redacted>";
  };

  // "Silent failures: zero, ever" (MVP spec §09). Every refusal says which
  // check refused, because the only symptom of the last inbound outage lived on
  // Twilio's side of the wire as error 11200.
  const refuse = (status, check, detail) => {
    console.log("sms/inbound " + status + ": " + check + " — " + detail);
    return e.string(status,
      status === 503 ? "sms webhook is not configured" : "forbidden");
  };

  // NOT interchangeable with TWILIO_API_KEY_SECRET, however tempting: an
  // inbound signature is HMAC-SHA1 under the account auth token, full stop.
  const authToken = $os.getenv("TWILIO_AUTH_TOKEN") || "";
  const signature = e.request.header.get("X-Twilio-Signature") || "";
  const contentType = (e.request.header.get("Content-Type") || "").toLowerCase();
  if (!authToken) {
    return refuse(503, "not configured",
      "TWILIO_AUTH_TOKEN is unset on this PocketBase service, so EVERY inbound " +
      "text is being refused. An API key cannot stand in for it — Twilio signs " +
      "webhooks with the account auth token only. Set it here and redeploy.");
  }
  if (contentType.indexOf("application/x-www-form-urlencoded") !== 0) {
    return e.string(415, "unsupported content type");
  }
  const info = e.requestInfo();
  const validator = require(`${__hooks}/twilio_signature.js`);
  const candidates = requestedUrls();

  // Twilio signs the POST BODY parameters only; the query string is already
  // accounted for inside the URL. PocketBase's requestInfo().body merges the
  // URL query INTO the form (Go's ParseForm does that), so a binding carrying
  // a query string can never validate until the query keys come back out.
  // Verified against a live PocketBase 0.30.4 on 2026-08-19: a request to
  // ".../sms/inbound?token=abc123" only passed when "token" was signed as if
  // it were a form field, which Twilio will never do. This is the other half
  // of the three-day outage — the number carried a "?token=..." binding, so no
  // value of ANTICIPY_TWILIO_WEBHOOK_URL could have rescued it.
  const params = {};
  for (const key of Object.keys(info.body || {})) params[key] = info.body[key];
  const rawQuery = String(e.request.url.rawQuery || "");
  if (rawQuery) {
    for (const pair of rawQuery.split("&")) {
      if (!pair) continue;
      delete params[decodeURIComponent(pair.split("=")[0].replace(/\+/g, " "))];
    }
  }

  let signedFor = "";
  if (signature) {
    for (const url of candidates) {
      if (validator.validate(authToken, url, params, signature)) {
        signedFor = url;
        break;
      }
    }
  }
  if (!signedFor) {
    return refuse(403, signature ? "signature mismatch" : "signature missing",
      "Twilio's configured URL must be one of [" +
      candidates.map(safeUrl).join(", ") + "]; MessageSid=" +
      String(info.body["MessageSid"] || "(none)") + " From=" +
      String(info.body["From"] || "").slice(0, 6) + "…");
  }
  const from = (info.body["From"] || "").toString();
  const body = (info.body["Body"] || "").toString().trim();
  const messageSid = (info.body["MessageSid"] || info.body["SmsSid"] || "").toString();
  const accountSid = (info.body["AccountSid"] || "").toString();
  const to = (info.body["To"] || "").toString();
  const expectedAccount = $os.getenv("TWILIO_ACCOUNT_SID") || "";
  const expectedNumber = $os.getenv("TWILIO_PHONE_NUMBER") || $os.getenv("TWILIO_FROM") || "";
  if (expectedAccount && accountSid !== expectedAccount) {
    return refuse(403, "wrong account",
      "AccountSid on the message is not TWILIO_ACCOUNT_SID for this deployment");
  }
  if (expectedNumber && to !== expectedNumber) {
    return refuse(403, "wrong number",
      "To=" + to.slice(0, 6) + "… is not this deployment's TWILIO_PHONE_NUMBER");
  }
  if (!/^SM[a-fA-F0-9]{32}$/.test(messageSid)) {
    return refuse(403, "malformed MessageSid",
      "a signed Twilio SMS always carries SM + 32 hex; got " +
      String(messageSid || "(none)").slice(0, 8) + "…");
  }

  // A phone number is a routing address, not an identity. Resolve it to one
  // and only one signed-in account, then stamp that canonical owner on the
  // event. Shared/recycled/ambiguous numbers fail closed; an SMS must never
  // choose which person's browser to control.
  const ownerRefs = {};
  try {
    const profiles = e.app.findRecordsByFilter(
      "owner_profile", "phone = {:phone}", "-updated", 3, 0, { phone: from });
    for (const profile of profiles) {
      const ref = profile.getString("owner_ref");
      if (ref) ownerRefs[ref] = true;
    }
  } catch (_) {}
  if (Object.keys(ownerRefs).length === 0) {
    try {
      const owners = e.app.findRecordsByFilter(
        "owners", "phone = {:phone}", "-updated", 3, 0, { phone: from });
      for (const owner of owners) ownerRefs[owner.id] = true;
    } catch (_) {}
  }
  const matches = Object.keys(ownerRefs);

  // Twilio retries webhooks. Persisting MessageSid before the worker sees the
  // row makes those retries one command, not two.
  let duplicate = false;
  if (messageSid) {
    try {
      e.app.findFirstRecordByFilter(
        "events", "external_event_id = {:sid}", { sid: messageSid });
      duplicate = true;
    } catch (_) {}
  }

  // Everything above this line refuses. Everything below ACCEPTS the request
  // and then decides whether it becomes an event, so this is the last place a
  // real text can disappear behind a 200. It used to do exactly that: an
  // unrecognised sender produced empty TwiML and no log at all, which reads
  // from Twilio's console as a perfectly healthy webhook.
  if (!from || !body) {
    console.log("sms/inbound 200 but dropped: empty From or Body; MessageSid=" + messageSid);
  } else if (duplicate) {
    console.log("sms/inbound 200, already handled: MessageSid=" + messageSid);
  } else if (matches.length === 0) {
    console.log("sms/inbound 200 but DROPPED: no account owns " + from.slice(0, 6) +
      "… — the sender's number is on no owner_profile or owners row, so every " +
      "text from it vanishes. Set the phone on that account.");
  } else if (matches.length > 1) {
    console.log("sms/inbound 200 but DROPPED: " + matches.length + " accounts claim " +
      from.slice(0, 6) + "… — ambiguous, refusing to pick whose browser to drive.");
  } else {
    try {
      const collection = e.app.findCollectionByNameOrId("events");
      const record = new Record(collection);
      record.set("device_id", "sms");
      record.set("kind", "sms_reply");
      record.set("text", body);
      record.set("decision", "");
      record.set("goal", from); // sender phone; the worker replies to it
      record.set("owner_ref", matches[0]);
      record.set("external_event_id", messageSid);
      e.app.save(record);
    } catch (err) {
      // A 500 here makes Twilio retry, which is the right outcome, but an
      // unexplained 500 is the same invisible outage in a different costume.
      console.log("sms/inbound 500: could not persist MessageSid=" + messageSid +
        ": " + String(err));
      throw err;
    }
  }
  e.response.header().set("Content-Type", "application/xml");
  return e.string(200, "<?xml version='1.0' encoding='UTF-8'?><Response></Response>");
});
