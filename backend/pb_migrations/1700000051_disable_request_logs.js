/// <reference path="../pb_data/types.d.ts" />

// The request-log database is not allowed to share the product volume.
//
// Production measured this file at 3.96 GB on 2026-08-21 and 2.77 GB again on
// 2026-08-31, while data.db was 264 MB. Either growth episode can exhaust the
// 5 GB Railway volume and make every durable product write fail while reads
// keep answering. start.sh deleting auxiliary.db at boot is a recovery path,
// not prevention; the file can fill the disk between two deployments.
//
// PocketBase documents maxDays=0 as DISABLED, not unlimited. Migration 38 and
// its gate encoded the opposite assumption and therefore retained two days of
// a log stream that can consume gigabytes in hours. Railway still retains the
// process and hook logs used for operations; this disables PocketBase's second,
// per-request SQLite ledger so disposable diagnostics cannot take customer data
// offline again.
migrate((app) => {
  const settings = app.settings();
  settings.logs.maxDays = 0;
  app.save(settings);
  console.log("PocketBase request logging disabled: auxiliary.db repeatedly threatened the product volume");
}, (app) => {
  const settings = app.settings();
  settings.logs.maxDays = 2;
  app.save(settings);
});
