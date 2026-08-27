/// <reference path="../pb_data/types.d.ts" />
//
// Two founder asks, one migration:
//
// internal_expenses — "anytime they make an expense, they need their own easy
// expense tracker, and then there can be a company expense log we can know."
// One table serves both: rows carry the person, the page shows Mine and
// Company as two lenses on the same data. Amount is a plain number in
// dollars; currency is a short code (CAD/USD) because the team sits in
// Vancouver and buys from the US, and a log that guesses the currency is a
// log nobody trusts at tax time.
//
// internal_passwords — the company vault for tool logins. THE SECRET COLUMN
// NEVER HOLDS PLAINTEXT: secret_enc is $security.encrypt output keyed by
// ANTICIPY_VAULT_KEY from the environment, so a copied database file (or a
// filled Railway volume shipped to support) exposes nothing without the env.
// Secrets leave the server only through the reveal route, per item, to a
// signed-in teammate. /internal/state carries metadata alone.
//
// Both collections have all-null API rules — every touch goes through the
// hook routes, same as everything else in HQ.
migrate((app) => {
  const mk = (name, fields) => {
    try { app.findCollectionByNameOrId(name); return; } catch (_) {}
    const c = new Collection({ type: "base", name: name, fields: fields, indexes: [] });
    app.save(c);
  };
  mk("internal_expenses", [
    { name: "title",      type: "text", max: 200 },
    { name: "amount",     type: "number" },
    { name: "currency",   type: "text", max: 8 },
    { name: "date",       type: "text", max: 10 },
    { name: "track",      type: "text", max: 32 },
    { name: "person",     type: "text", max: 32 },
    { name: "created_by", type: "text", max: 32 },
    { name: "created",    type: "autodate", onCreate: true },
    { name: "updated",    type: "autodate", onCreate: true, onUpdate: true },
  ]);
  mk("internal_passwords", [
    { name: "service",    type: "text", max: 120 },
    { name: "username",   type: "text", max: 200 },
    { name: "secret_enc", type: "text", max: 2000 },
    { name: "url",        type: "text", max: 500 },
    { name: "notes",      type: "text", max: 2000 },
    { name: "updated_by", type: "text", max: 32 },
    { name: "created",    type: "autodate", onCreate: true },
    { name: "updated",    type: "autodate", onCreate: true, onUpdate: true },
  ]);
}, (app) => {
  for (const n of ["internal_expenses", "internal_passwords"]) {
    try { app.delete(app.findCollectionByNameOrId(n)); } catch (_) {}
  }
});
