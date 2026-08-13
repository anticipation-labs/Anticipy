/// <reference path="../pb_data/types.d.ts" />

// Twilio inbound-SMS webhook. Twilio POSTs form-encoded From/Body here;
// the record it creates is picked up by the brain worker, which understands
// the reply and texts back over the live Twilio transport.
routerAdd("POST", "/sms/inbound", (e) => {
  const token = $os.getenv("ANTICIPY_SMS_TOKEN");
  if (!token || e.request.url.query().get("token") !== token) {
    return e.string(403, "forbidden");
  }
  const info = e.requestInfo();
  const from = (info.body["From"] || "").toString();
  const body = (info.body["Body"] || "").toString().trim();
  const messageSid = (info.body["MessageSid"] || info.body["SmsSid"] || "").toString();

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
