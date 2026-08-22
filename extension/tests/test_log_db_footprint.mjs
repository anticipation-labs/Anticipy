// The request log must not be able to fill the volume the product runs on.
//
// Measured on production 2026-08-21, from start.sh's own boot du:
// /pb_data/auxiliary.db was 3.96GB against a 264MB data.db on a 5GB volume.
// PocketBase's request log, fifteen times the size of the actual data, with no
// retention ceiling. SQLite then refused every write while serving every read,
// so the brain kept texting the owner the same question and could never record
// that it had — see brain/worker.py:2199, which describes this exact failure a
// year before it happened, and 1700000038_log_db_footprint.js for the cost.
//
// Same shape as test_backup_volume_footprint.mjs and the same reasoning: run
// the migrations rather than read them, in filename order, so a later one
// raising the ceiling back to unbounded fails HERE and not on the volume.
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

// PocketBase's own default: 0 means keep forever, which is how this happened.
const settings = { logs: { maxDays: 0, minLevel: 0, logIP: true, logAuthId: false } };

const files = readdirSync(dir).filter((f) => f.endsWith(".js")).sort();
const touching = files.filter((f) =>
  readFileSync(join(dir, f), "utf8").indexOf("settings.logs") >= 0);

check("at least one migration bounds the request log", touching.length >= 1);

const applied = [];
for (const file of touching) {
  const src = readFileSync(join(dir, file), "utf8");
  const globals = {
    // Only the up function: migrations are applied forward at container boot
    // and the down function is never reached there.
    migrate: (up) => { up({ settings: () => settings, save: () => {} }); },
  };
  const names = Object.keys(globals);
  new Function(...names, src)(...names.map((n) => globals[n]));
  applied.push(file);
}
console.log(`applied in order: ${applied.join(", ")}`);

// 0 is PocketBase's "keep forever". That is the condition that took the product
// down, so it is the one value that must never survive the migration chain.
check("the request log has a retention ceiling at all", settings.logs.maxDays > 0);

// The ceiling has to be low enough to matter on a 5GB volume that already
// carries data.db and up to two backup archives.
check("retention is short enough to bound the volume", settings.logs.maxDays <= 7);

// But not so short that an incident is undiagnosable the morning after: the
// request log is the only record of what the agent and the phone actually
// asked for, and it is what named the culprit in the fill above.
check("yesterday is still readable", settings.logs.maxDays >= 2);

if (failures) { console.error(`test_log_db_footprint: ${failures} failed`); process.exit(1); }
console.log("test_log_db_footprint: all passed");
