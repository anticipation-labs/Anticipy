import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { createBackgroundTab } = await import("../agent_loop.js");

const ordinary = await createBackgroundTab("https://example.com/ordinary");
assert.equal(harness.tabs.get(ordinary.id).url, "https://example.com/ordinary");
assert.equal(harness.focusGrants.length, 0, "ordinary background tab never focuses");
console.log("PASS 1: existing-window path creates an unfocused tab");

harness.setCurrentWindowExists(false);
const recovered = await createBackgroundTab("https://example.com/recovered");
assert.equal(harness.tabs.get(recovered.id).url, "https://example.com/recovered");
assert.equal(harness.windowFocused(), false, "fallback window stays unfocused");
assert.equal(harness.focusGrants.length, 0, "no-window recovery never steals focus");
console.log("PASS 2: no-current-window path creates a quiet agent window");

console.log("test_background_tab_fallback: all 2 scenarios passed");
