/// <reference path="../pb_data/types.d.ts" />

// Twilio inbound-SMS webhook. Twilio POSTs form-encoded From/Body here;
// the record it creates is picked up by the brain worker, which understands
// the reply and texts back over the live Twilio transport.
routerAdd("POST", "/sms/inbound", (e) => {
  const authToken = $os.getenv("TWILIO_AUTH_TOKEN") || "";
  const webhookUrl = $os.getenv("ANTICIPY_TWILIO_WEBHOOK_URL") || "";
  const signature = e.request.header.get("X-Twilio-Signature") || "";
  const contentType = (e.request.header.get("Content-Type") || "").toLowerCase();
  if (!authToken || !webhookUrl) {
    return e.string(503, "sms webhook is not configured");
  }
  if (contentType.indexOf("application/x-www-form-urlencoded") !== 0) {
    return e.string(415, "unsupported content type");
  }
  const info = e.requestInfo();
  const validator = require(`${__hooks}/twilio_signature.js`);
  if (!signature || !validator.validate(authToken, webhookUrl, info.body, signature)) {
    // A dead inbound lane must be visible in the logs. This exact rejection
    // fired silently on every text for three days (2026-08-12→15) while the
    // only symptom lived on Twilio's side as error 11200.
    console.log("sms/inbound 403: signature mismatch — Twilio's configured",
      "URL must equal ANTICIPY_TWILIO_WEBHOOK_URL byte-for-byte; MessageSid=",
      String(info.body["MessageSid"] || ""), "From=",
      String(info.body["From"] || "").slice(0, 6) + "…");
    return e.string(403, "forbidden");
  }
  const from = (info.body["From"] || "").toString();
  const body = (info.body["Body"] || "").toString().trim();
  const messageSid = (info.body["MessageSid"] || info.body["SmsSid"] || "").toString();
  const accountSid = (info.body["AccountSid"] || "").toString();
  const to = (info.body["To"] || "").toString();
  const expectedAccount = $os.getenv("TWILIO_ACCOUNT_SID") || "";
  const expectedNumber = $os.getenv("TWILIO_PHONE_NUMBER") || $os.getenv("TWILIO_FROM") || "";
  if ((expectedAccount && accountSid !== expectedAccount) ||
      (expectedNumber && to !== expectedNumber) ||
      !/^SM[a-fA-F0-9]{32}$/.test(messageSid)) {
    return e.string(403, "forbidden");
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

  if (from && body && messageSid && !duplicate && matches.length === 1) {
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
  }
  e.response.header().set("Content-Type", "application/xml");
  return e.string(200, "<?xml version='1.0' encoding='UTF-8'?><Response></Response>");
});
