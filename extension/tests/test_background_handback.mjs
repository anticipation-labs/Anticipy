// Brief 03 — the hand-back surface: surfacing NEVER focuses anything (badge +
// notification only); the owner's click is the one thing that does. Also the
// lifecycle around it: badge counts, cleanup when a tab is closed by hand, and
// the reopen-by-URL fallback when the kept tab died before the click.
// Run: node extension/tests/test_background_handback.mjs

import assert from "node:assert/strict";
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
// Backend unreachable: the worker's import-time poll() must cope, as it does
// when Chrome starts offline.
globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });

const { surfaceHandBack, openHandBack } = await import("../background.js");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const owner = harness.addTab({ url: "https://news.site/read", active: true });

// ---- 1. Surfacing a needs_user tab: badge + notification, ZERO focus ------
const kept = harness.addTab({ url: "https://www.example.com/login", active: false });
await surfaceHandBack(kept.id, "stopped at a login wall — needs a human", "needs_user");

assert.equal(harness.focusGrants.length, 0, "surfacing must not focus anything");
assert.equal(harness.activeTabId(), owner.id, "owner's tab untouched");
assert.equal(harness.badge.text, "1", "badge shows one thing waiting");
const notif = harness.notifications.get(`anticipy-handback-${kept.id}`);
assert.ok(notif, "a notification was raised");
assert.equal(notif.message, "I need you on example.com — click to open.");
assert.ok(notif.contextMessage.includes("login wall"));
console.log("PASS 1: surface = badge + notification, no focus");

// ---- 2. The notification CLICK is what focuses — and only it --------------
harness.fireNotificationClick(`anticipy-handback-${kept.id}`);
await sleep(50);
assert.equal(harness.activeTabId(), kept.id, "owner's click brings the tab forward");
assert.equal(harness.tabs.get(kept.id).groupId, -1, "handed-over tab leaves the group");
assert.ok(harness.focusGrants.length >= 1, "the click path is the one that grants focus");
assert.equal(harness.badge.text, "", "badge clears once answered");
assert.ok(!harness.notifications.has(`anticipy-handback-${kept.id}`), "notification cleared");
assert.deepEqual(harness.storageData.handBacks, {}, "hand-back entry consumed");
console.log("PASS 2: owner click focuses tab, badge/notification consumed");

// ---- 3. Confirm-kind wording + owner closing the tab by hand --------------
harness.focusGrants.length = 0;
await chrome.tabs.update(owner.id, { active: true });
harness.focusGrants.length = 0; // that was test plumbing, not the extension
const prefill = harness.addTab({ url: "https://mail.google.com/mail/?view=cm", active: false });
await surfaceHandBack(prefill.id, "email to Sam about Thursday", "confirm");
assert.equal(harness.notifications.get(`anticipy-handback-${prefill.id}`).message,
  "Ready for your OK on mail.google.com — click to open.");
assert.equal(harness.badge.text, "1");
assert.equal(harness.focusGrants.length, 0, "prefill surface steals nothing");
await chrome.tabs.remove(prefill.id); // the owner closes it themselves
await sleep(50);
assert.equal(harness.badge.text, "", "closing the tab by hand clears its badge");
assert.deepEqual(harness.storageData.handBacks, {}, "entry cleaned up on tab close");
console.log("PASS 3: confirm wording right; hand-closed tab clears its badge");

// ---- 4. Chrome restarted: tab id is gone, the click still opens the page --
const ghost = harness.addTab({ url: "https://example.org/form", active: false });
await surfaceHandBack(ghost.id, "the form needs your date of birth", "needs_user");
harness.zapTab(ghost.id); // vanished with no onRemoved — a restart
harness.focusGrants.length = 0;
await openHandBack(ghost.id);
const reopened = [...harness.tabs.values()].find((t) => t.url === "https://example.org/form");
assert.ok(reopened, "the page reopens rather than the click doing nothing");
assert.equal(harness.activeTabId(), reopened.id, "reopened focused — it IS the owner's click");
assert.equal(harness.badge.text, "");
assert.deepEqual(harness.storageData.handBacks, {});
console.log("PASS 4: dead tab falls back to reopening the page on click");

console.log("test_background_handback: all 4 scenarios passed");
process.exit(0);
