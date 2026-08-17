/// <reference path="../pb_data/types.d.ts" />

// Seven whole-database snapshots, kept on the volume they are snapshots OF.
//
// 1700000018 turned backups on with cronMaxKeep = 7 and no `settings.backups.s3`,
// so PocketBase zips pb_data into <dataDir>/backups — which is /pb_data, the
// same 5GB Railway volume. Peak footprint is eight copies: seven kept plus the
// one being written. Nothing reclaims them either; start.sh's boot guard drops
// auxiliary.db and never looks inside /pb_data/backups, so a snapshot taken at
// 09:00 while a table was oversized pins that size on the volume for the next
// six days, and restarting the container cannot undo it.
//
// This is not the 2026-08-15 fill — that one is named and fixed at the source
// (the audit ledger, see audit_retention.pb.js). It is the same failure MODE,
// and that failure mode takes the entire product down rather than one feature:
// once SQLite cannot write a row, a password-reset text still goes out and the
// code behind it can never be saved, so the correct code is rejected forever.
// An archive must not be able to cause that by itself.
//
// Two, not one: yesterday's copy has to still be there when today's was taken
// mid-corruption, which is most of what a backup is for. Off-volume storage is
// the right long-term answer and needs S3 credentials this image does not have.
migrate((app) => {
  const settings = app.settings();
  settings.backups.cronMaxKeep = 2;
  app.save(settings);
  console.log("backup retention capped: keep 2 (was 7), still on the data volume");
}, (app) => {
  const settings = app.settings();
  settings.backups.cronMaxKeep = 7;
  app.save(settings);
});
