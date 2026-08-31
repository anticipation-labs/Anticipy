// The hosted setup page is allowed to see the disposable six-digit code and
// linked state, but never the per-agent credential or owner identity.
// Run: node extension/tests/test_hosted_setup_bridge.mjs
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
const bridgeSource = readFileSync(join(here, "../setup_bridge.js"), "utf8");
const backgroundSource = readFileSync(join(here, "../background.js"), "utf8");
const setupPage = readFileSync(join(here, "../../backend/pb_public/setup.html"), "utf8");

let state = { code: "274901", linked: false, agent_token: "never-publish-me" };
let storageListener = null;
let pageListener = null;
const posts = [];
const location = { origin: "https://backend-production-61e0a.up.railway.app" };
const window = {
  location,
  addEventListener(type, listener) { if (type === "message") pageListener = listener; },
  postMessage(message, target) { posts.push({ message, target }); },
};
const chrome = {
  runtime: { sendMessage: async () => state },
  storage: { onChanged: { addListener(listener) { storageListener = listener; } } },
};

vm.runInNewContext(bridgeSource, { chrome, window, globalThis: {}, Promise });
await new Promise((resolve) => setTimeout(resolve, 0));

assert.equal(posts.length, 1, "the bridge must publish without making the page refresh");
assert.deepEqual(JSON.parse(JSON.stringify(posts[0].message)), {
  type: "anticipy-setup-state",
  source: "anticipy-extension",
  installed: true,
  code: "274901",
  linked: false,
});
assert.equal(posts[0].target, location.origin, "setup state must target this page's origin");
assert.ok(!JSON.stringify(posts).includes("never-publish-me"),
  "the private agent credential must never enter hosted page JavaScript");

state = { code: "274901", linked: true };
storageListener({ paired: { newValue: true } }, "local");
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(posts.at(-1).message.linked, true,
  "the page must become a completion receipt as soon as pairing lands");

const before = posts.length;
pageListener({
  source: window,
  origin: location.origin,
  data: { type: "anticipy-setup-request", source: "anticipy-page" },
});
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(posts.length, before + 1, "the page can explicitly request fresh setup state");

assert.match(backgroundSource, /candidate\.origin === expected\.origin/,
  "the background must bind bridge injection to the configured backend origin");
assert.match(backgroundSource, /candidate\.pathname === expected\.pathname/,
  "the background must bind bridge injection to the setup page path");
assert.match(backgroundSource, /files: \["setup_bridge\.js"\]/,
  "the checked setup page must receive the bridge");
assert.match(setupPage, /id="pairCode"/,
  "the hosted page needs a real pairing-code surface");
assert.match(setupPage, /navigator\.share/,
  "the hosted page needs the system share sheet on an iPhone");

console.log("PASS: hosted setup shows only disposable pairing state and updates live");
