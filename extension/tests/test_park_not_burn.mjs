// Running out of room must PARK, never destroy the work.
//
// The run he watched die: eighty steps of progress on an application form,
// the last field unfilled, and the loop returned status "failed" with
// handBack unset. The teardown closes the working tab whenever handBack is
// false — so the filled form, the live session and the page itself were all
// thrown away, and he was handed "max steps reached; last steps: ..." with no
// question to answer. "It doesn't ask, and it just quits."
//
// The contract: an exit that happens AFTER the run has touched the page keeps
// the tab. The tab IS the progress.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "agent_loop.js"), "utf8");
const lines = src.split("\n");
// Comments explain the bugs by name, so assertions about what the OWNER is
// shown must read the code only — otherwise a comment describing the old
// message trips the test that forbids the old message.
const code = lines.filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");
let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// 1. The step ceiling parks rather than fails.
check("step exhaustion no longer reports failure",
  !/status: "failed", result: `max steps reached/.test(code));
check("step exhaustion parks for the owner",
  /ranOutOfSteps: true/.test(src));

// 2. Every parked exit keeps the tab. handBack is what the teardown reads.
const parked = [];
lines.forEach((line, i) => { if (/status: "needs_user"/.test(line)) parked.push(i); });
check("parked exits were found", parked.length >= 20);
const missing = parked.filter((at) => {
  const window = lines.slice(Math.max(0, at - 3), at + 1).join("\n");
  // The pre-flight refusal fires before a tab exists, so it has none to keep.
  if (/refused: operating financial accounts/.test(lines.slice(at, at + 3).join("\n"))) return false;
  return !/handBack = true/.test(window);
});
check(`every parked exit keeps its tab (${missing.length} would burn it)`,
  missing.length === 0);
if (missing.length) {
  for (const at of missing) console.error(`  line ${at + 1}: ${lines[at].trim()}`);
}

// 3. The owner is told where it got to, in words — not a step counter.
check("the parked message says where it got to and that nothing is lost",
  /I got as far as/.test(src) && /nothing is lost/.test(src));
check("no step counter is shown to the owner",
  !/max steps reached/.test(code));

if (failures) { console.error(`test_park_not_burn: ${failures} failed`); process.exit(1); }
console.log("test_park_not_burn: all passed");
