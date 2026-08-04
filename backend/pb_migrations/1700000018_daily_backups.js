/// <reference path="../pb_data/types.d.ts" />

// The database now backs itself up.
//
// Everything else in this system can be rebuilt from git — the code, the
// migrations, the extension — but the data (his accounts, transcripts,
// memory, jobs) exists only in pb_data on the Railway volume. Until now a
// bad deploy or a destructive bug had nothing to fall back on. PocketBase
// ships a built-in scheduled backup; this turns it on: one snapshot a day,
// keeping the last seven, stored on the same volume and restorable from the
// PocketBase dashboard.
migrate((app) => {
  const settings = app.settings();
  settings.backups.cron = "0 9 * * *";
  settings.backups.cronMaxKeep = 7;
  app.save(settings);
  console.log("daily backups enabled: 09:00 UTC, keep 7");
}, (app) => {
  const settings = app.settings();
  settings.backups.cron = "";
  app.save(settings);
});
