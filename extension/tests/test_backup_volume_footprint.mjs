// Backups must not be able to fill the volume they are backups of.
//
// 1700000018 switched PocketBase's scheduled backup on with cronMaxKeep = 7
// and no S3 target, so every snapshot is a zip of pb_data written into
// /pb_data/backups — the same 5GB Railway volume, up to eight copies at peak.
// start.sh's boot reclaim drops auxiliary.db and never looks in backups, so
// restarting the container cannot undo a snapshot taken while the database was
// oversized. That is the same shape as the 2026-08-15 fill, where SQLite ran
// out of room and a password-reset text went out whose code could never be
// saved — the whole product, not one feature.
//
// This runs the migrations rather than reading them, and it runs ALL of them
// that touch settings.backups in filename order, so a later migration raising
// the number back up fails here instead of on the volume.
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const dir = join(here, "..", "..", "backend", "pb_migrations");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// PocketBase's own defaults, before any migration has spoken.
const settings = {
  backups: { cron: "", cronMaxKeep: 0, s3: { enabled: false } },
};

const files = readdirSync(dir).filter((f) => f.endsWith(".js")).sort();
const touching = files.filter((f) =>
  readFileSync(join(dir, f), "utf8").indexOf("settings.backups") >= 0);

check("at least one migration configures backups", touching.length >= 1);

const applied = [];
for (const file of touching) {
  const src = readFileSync(join(dir, file), "utf8");
  const globals = {
    // Migrations are applied forward at container boot; the down function is
    // never reached there, so only the up function is exercised here.
    migrate: (up) => { up({ settings: () => settings, save: () => {} }); },
  };
  const names = Object.keys(globals);
  new Function(...names, src)(...names.map((n) => globals[n]));
  applied.push(file);
}
console.log(`applied in order: ${applied.join(", ")}`);

check("scheduled backups are still switched on",
  typeof settings.backups.cron === "string" && settings.backups.cron.trim() !== "");

// The rule fires on the real condition — archives living on the data volume —
// not on the number alone. With an S3 target configured they are off-volume
// and a long retention costs the volume nothing, so keeping seven there would
// be fine and this check correctly stops applying.
const offVolume = !!(settings.backups.s3 && settings.backups.s3.enabled);
check("archives kept on the data volume are capped at two",
  offVolume || settings.backups.cronMaxKeep <= 2);

// Two is a cap, not a switch-off: one surviving copy is no backup at all when
// the newest snapshot was taken mid-corruption.
check("at least two generations are still kept",
  offVolume || settings.backups.cronMaxKeep >= 2);

if (failures) { console.error(`test_backup_volume_footprint: ${failures} failed`); process.exit(1); }
console.log("test_backup_volume_footprint: all passed");
