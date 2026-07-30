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
  if (from && body) {
    const collection = e.app.findCollectionByNameOrId("events");
    const record = new Record(collection);
    record.set("device_id", "sms");
    record.set("kind", "sms_reply");
    record.set("text", body);
    record.set("decision", "");
    record.set("goal", from); // sender phone; the worker replies to it
    e.app.save(record);
  }
  e.response.header().set("Content-Type", "application/xml");
  return e.string(200, "<?xml version='1.0' encoding='UTF-8'?><Response></Response>");
});
