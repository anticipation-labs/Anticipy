// Discovery belongs to the browser, not to one vendor baked into the agent.
// The reservation incident left multiple Bing tabs behind because every
// default and fallback literally named Bing.  An internal search target must
// instead call Chrome's configured provider, carrying only sanitized terms.
import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";
import {
  createBackgroundTab, isSearchTarget, searchTarget,
} from "../agent_loop.js";

const harness = installChrome();
harness.addTab({ url: "https://owner.example/work", active: true });

const target = searchTarget(
  "The Keg downtown Vancouver reservations omar@example.com +1 604 555 0142");
assert.ok(isSearchTarget(target));
assert.ok(!target.includes("bing.com"));
assert.ok(!target.includes("@"), "an email must not enter the internal target");

const tab = await createBackgroundTab(target);
assert.equal(harness.searches.length, 1,
  "provider-neutral discovery must use chrome.search exactly once");
assert.match(harness.searches[0].text, /The Keg downtown Vancouver reservations/i);
assert.ok(!harness.searches[0].text.includes("@"));
assert.ok(!/604.*0142/.test(harness.searches[0].text));
assert.equal(tab.url.startsWith("https://search.test/"), true,
  "the browser—not Anticipy—chooses the resulting provider URL");
assert.deepEqual(harness.focusGrants, [], "background discovery never steals focus");

console.log("test_search_provider: all passed");
