// The picture must arrive when the LABEL LIST is failing, and not otherwise.
//
// Both previous answers were wrong. "After two unproductive steps, send the
// picture" lost date pickers — by the time two steps were wasted the run had
// already misclicked into a wrong month. "ALWAYS look" fixed that and quietly
// billed a vision model on every step of every run, including the long tail of
// ordinary text-and-form pages a label list describes perfectly. The MVP spec
// asks for both halves: "accessibility tree first, vision second... screenshots
// only when structure is missing or misleading" AND "cost per task under $0.05".
//
// Run: node extension/tests/test_vision_cost.mjs
import { installChrome } from "./chrome_mock.mjs";
installChrome();
const { needsEyes } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const lines = (...l) => l.join("\n");

// ------------------------------------------------- 1. LOOK: structure is weak
// A picker is open. The map has just been scoped to its contents, so the one
// thing on screen is the one thing a label list is worst at — and this must fire
// on the FIRST step, not after two wasted ones.
check("an open dialog or picker earns a look",
  !!needsEyes({ overlay: true, elements: "[0] <button> 17" }));

// page_map emits `calendar=September 17` when it recovers month context for a
// bare day number: its presence means the page IS a date grid.
check("a date grid earns a look",
  !!needsEyes({ elements: lines("[0] <button> 17 (calendar=September 17) @(10,10)") }));

check("clickable graphics earn a look",
  !!needsEyes({ elements: lines("[0] <canvas> seat map @(10,10)") })
    && !!needsEyes({ elements: lines("[0] <svg> floor plan @(10,10)") })
    && !!needsEyes({ elements: lines("[0] <graphics-document> chart @(1,1)") }));

// A wall of UNLABELLED controls is an icon grid, a seat map or a keypad: the map
// knows something is clickable and nothing about what it means.
check("mostly-unlabelled controls earn a look",
  !!needsEyes({ elements: lines(
    "[0] <button> @(1,1)", "[1] <button> @(2,2)", "[2] <button> @(3,3)",
    "[3] <button> @(4,4)", "[4] <button> Continue @(5,5)", "[5] <button> Back @(6,6)") }));

// A truncated map is worse than a missing one: the model cannot tell what it was
// not shown.
check("a truncated element map earns a look",
  !!needsEyes({ elements: Array.from({ length: 400 }, (_, i) => `[${i}] <link> item ${i} @(1,1)`).join("\n") }));

// The original escalation survives as a floor, at ONE wasted step rather than
// two — two was already too late.
check("one wasted step earns a look whatever the page looks like",
  !!needsEyes({ elements: "[0] <textbox> Name @(1,1)" }, { stuckStreak: 1 }));

// ------------------------------------- 2. DON'T LOOK: the label list is fine
// This is the half that saves the money, and it is most steps of most runs.
check("an ordinary form page reads fine without a picture",
  needsEyes({ elements: lines(
    "[0] <textbox> First name @(1,1)",
    "[1] <textbox> Last name @(2,2)",
    "[2] <textbox> Email @(3,3)",
    "[3] <combobox> Party size (options: \"2\", \"4\") @(4,4)",
    "[4] <button> Continue @(5,5)"), text: "Booking details" }) === null);

check("a page of links and prose reads fine without a picture",
  needsEyes({ elements: lines(
    "[0] <link> Menus [href=https://x.test/menus] @(1,1)",
    "[1] <link> Hours [href=https://x.test/hours] @(2,2)",
    "[2] <button> Reserve @(3,3)"), text: "Happy hour 3-6pm." }) === null);

// A couple of unlabelled controls is a close X and a menu toggle, not a keypad.
check("a couple of unlabelled controls is not a keypad",
  needsEyes({ elements: lines(
    "[0] <button> @(1,1)", "[1] <button> @(2,2)",
    "[2] <textbox> Email @(3,3)", "[3] <button> Sign in @(4,4)",
    "[4] <link> Help @(5,5)", "[5] <link> Terms @(6,6)",
    "[6] <button> Continue @(7,7)") }) === null);

check("an empty map does not earn a look on its own",
  needsEyes({ elements: "" }) === null);
check("a missing state is survivable", needsEyes(null) === null
  && needsEyes(undefined) === null);

// ------------------------------------------------- 3. it says WHY, in words
// The reason goes into the run's history, which a person reads.
{
  const reason = needsEyes({ overlay: true, elements: "[0] <button> 17" });
  check("the reason is a readable phrase, not a code",
    typeof reason === "string" && /dialog|picker/.test(reason) && !/^[A-Z_]+$/.test(reason));
}

// ------------------------------------- 4. the loop actually consults it
{
  const { readFileSync } = await import("node:fs");
  const loop = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  check("the step loop asks needsEyes instead of always capturing",
    /const eyesReason = needsEyes\(state, \{ stuckStreak \}\);/.test(loop));
  check("no picture is taken when the label list suffices",
    /const eyes = eyesReason \? await screenshot\(tab\.id\) : null;/.test(loop));
  check("the unconditional capture is gone",
    !/^\s*const eyes = await screenshot\(tab\.id\);\s*$/m.test(loop));
  // llmStep chooses the vision model only when an image is present, so a null
  // image is also what keeps the cheap model on ordinary steps.
  check("a null image leaves the prompt text-only",
    /return image\s*\n?\s*\?/.test(loop));
}

if (failures) {
  console.error(`test_vision_cost: ${failures} failed`);
  process.exit(1);
}
console.log("test_vision_cost: all passed");
