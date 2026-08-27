/// <reference path="../pb_data/types.d.ts" />
//
// A reminder that cannot be delivered used to retry forever.
//
// The sweep claims a reminder by stamping remind_sent_at BEFORE sending, then
// rolls the stamp back if every channel failed, so a transient Resend/Twilio
// blip gets another go on the next sweep. That is right for a blip and wrong
// for a permanently unreachable recipient: the row comes back due every 5
// minutes, forever, burning a real Twilio/Resend call and writing a
// reminder.failed activity row each time — 288 a day, per stuck todo.
//
// This is the same unbounded-retry shape claim-first was chosen to avoid; it
// just moved from the recipient's phone to the activity feed and the API bill.
// remind_attempts bounds it: retry twice, then give up and say so once.
migrate((app) => {
  const c = app.findCollectionByNameOrId("internal_todos");
  if (!c.fields.getByName("remind_attempts")) {
    c.fields.add(new NumberField({ name: "remind_attempts", min: 0 }));
    app.save(c);
  }
}, (app) => {
  try {
    const c = app.findCollectionByNameOrId("internal_todos");
    const f = c.fields.getByName("remind_attempts");
    if (f) { c.fields.removeById(f.id); app.save(c); }
  } catch (_) {}
});
