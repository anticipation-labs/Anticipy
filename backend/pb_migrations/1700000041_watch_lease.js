/// <reference path="../pb_data/types.d.ts" />

// EVIDENCE THAT SOMEBODY IS WATCHING, with a thirty-second half-life.
//
// `ContextSource.mail.promises` opens with "You open it. I read it once, in the
// front window, while you watch." Until this column existed, not one word of
// that was enforced by anything — it was a sentence on a consent screen, and
// `design/day-zero.md` §2 is explicit that a silent failure behind that promise
// is the worst first impression this product can make.
//
// So supervision is a LEASE, not a flag. The phone writes `now + 30s` here every
// ten seconds, and only while `SupervisedReadView` is on screen with the scene
// phase `.active` (`AnticipySession.holdWatchLease`). The extension re-reads it
// before every action and `research_lane.pb.js` re-reads it on every claim.
// Background the app, lock the phone, or swipe the view away and the reader
// stops itself within thirty seconds — nobody has to remember to stop it.
//
// WHY A TIMESTAMP AND NOT A BOOLEAN. A boolean is something another process set,
// and `side_trip.js:194-198` already settled what that is worth: "another
// process decided I may read your inbox" is exactly the sentence this product
// cannot afford to be true. A flag survives the app dying. A lease cannot be
// forged by anything that is not a foregrounded app holding the phone open,
// because the only way to keep it in the future is to keep pushing it there.
//
// WHY NOT `lease_until`. That column already exists on `jobs` and means the
// opposite thing: it is the EXECUTOR's lease (`workflow_guard.pb.js:159-162`) —
// how long the worker or the browser holds the right to run a row. This one is
// the OWNER's presence. Overloading one column with two meanings would let a
// long executor lease read as a person standing there watching.
//
// Nullable, and every job written before today simply has none — which reads,
// correctly, as "nobody is watching this", and matters to nothing except the
// supervised_read lane where its absence is a refusal.
migrate((app) => {
  const jobs = app.findCollectionByNameOrId("jobs");
  if (!jobs.fields.getByName("watching_until")) {
    jobs.fields.add(new Field({
      name: "watching_until", type: "date", required: false,
    }));
    app.save(jobs);
  }
  console.log("jobs.watching_until added: a supervised read now has to prove somebody is there");
}, (app) => {
  try {
    const jobs = app.findCollectionByNameOrId("jobs");
    const field = jobs.fields.getByName("watching_until");
    if (field) {
      jobs.fields.removeById(field.id);
      app.save(jobs);
    }
  } catch (_) {}
});
