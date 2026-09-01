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
// On 2026-08-31 it had grown to 2.77GB again despite the two-day retention
// migration. PocketBase's documented meaning of maxDays=0 is DISABLED, not
// unlimited; the older version of this gate had that meaning backwards. Run
// the migrations in filename order so request logging being re-enabled fails
// here rather than on the production volume.
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

// PocketBase's current default is seven days. Zero explicitly disables the
// request ledger; it is the safe terminal state for this traffic volume.
const settings = { logs: { maxDays: 7, minLevel: 0, logIP: true, logAuthId: false } };

const files = readdirSync(dir).filter((f) => f.endsWith(".js")).sort();
const touching = files.filter((f) =>
  readFileSync(join(dir, f), "utf8").indexOf("settings.logs") >= 0);

check("at least one migration configures the request log", touching.length >= 1);

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

check("PocketBase's request ledger is disabled", settings.logs.maxDays === 0);
check("the disabled state survives every later migration", applied.at(-1) === "1700000051_disable_request_logs.js");

if (failures) { console.error(`test_log_db_footprint: ${failures} failed`); process.exit(1); }
console.log("test_log_db_footprint: all passed");
