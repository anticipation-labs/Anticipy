/// <reference path="../pb_data/types.d.ts" />
// Move database snapshots off the volume whose failure they must survive.
//
// This migration is deliberately strict: one missing field aborts the deploy
// instead of silently leaving customer backups on the same 5 GB disk. The
// credentials are bucket-scoped and PocketBase settings are encrypted by
// start.sh's PB_SETTINGS_ENCRYPTION_KEY before they are stored in data.db.
migrate((app) => {
  const required = [
    "ANTICIPY_BACKUP_S3_BUCKET",
    "ANTICIPY_BACKUP_S3_ENDPOINT",
    "ANTICIPY_BACKUP_S3_ACCESS_KEY",
    "ANTICIPY_BACKUP_S3_SECRET",
  ];
  const values = {};
  for (const name of required) values[name] = String($os.getenv(name) || "").trim();
  const missing = required.filter((name) => !values[name]);
  if (missing.length) {
    throw new Error("off-volume backup configuration missing: " + missing.join(", "));
  }

  const settings = app.settings();
  settings.backups.cron = "0 9 * * *";
  settings.backups.cronMaxKeep = 14;
  settings.backups.s3 = {
    enabled: true,
    bucket: values.ANTICIPY_BACKUP_S3_BUCKET,
    region: String($os.getenv("ANTICIPY_BACKUP_S3_REGION") || "auto").trim(),
    endpoint: values.ANTICIPY_BACKUP_S3_ENDPOINT,
    accessKey: values.ANTICIPY_BACKUP_S3_ACCESS_KEY,
    secret: values.ANTICIPY_BACKUP_S3_SECRET,
    forcePathStyle: true,
  };
  app.save(settings);
}, (app) => {
  const settings = app.settings();
  settings.backups.cronMaxKeep = 2;
  settings.backups.s3 = { enabled: false };
  app.save(settings);
});
