// Brief 03 grep proof — zero focus-stealing calls outside owner-gesture paths.
//
// The contract: every focus-granting property (`active: true`, `focused: true`,
// `highlighted/selected/drawAttention: true`) in the extension must sit
// directly under a FOCUS-OK marker naming why it is the owner's own gesture:
//   FOCUS-OK(owner-click)    — the owner clicked the notification/popup button
//   FOCUS-OK(owner-install)  — the pairing page on the owner's own install
//   FOCUS-OK(focus-restore)  — handing focus BACK to the owner's tab
// The allowed count per file is pinned, so a new focus effect cannot ride in
// without failing this check and forcing a re-audit.
//
// Also enforced here: node --check on agent_loop.js + background.js as .mjs
// (the brief's own syntax gate), tabs.create defaulting-to-focused misuse,
// any window creation except the one pinned unfocused/minimized recovery path,
// tab highlighting, manifest version + notifications perm.
//
// Run: node extension/tests/check_never_foreground.mjs

import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { join, dirname } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

const ext = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (f) => readFileSync(join(ext, f), "utf8");
const failures = [];

const FILES = ["agent_loop.js", "background.js", "popup.js", "onboarding.js", "page_map.js"];
const ALLOWED_GRANTS = { "agent_loop.js": 1, "background.js": 5 }; // pinned: re-audit to change
const MARKER = /FOCUS-OK\((owner-click|owner-install|focus-restore)\)/;

// 1. Syntax: both service-worker modules must parse as ES modules.
const tmp = mkdtempSync(join(tmpdir(), "anticipy-nf-"));
for (const f of ["agent_loop.js", "background.js"]) {
  const p = join(tmp, f.replace(/\.js$/, ".mjs"));
  writeFileSync(p, read(f));
  try { execFileSync(process.execPath, ["--check", p], { stdio: "pipe" }); }
  catch (e) { failures.push(`${f}: node --check failed:\n${e.stderr}`); }
}
rmSync(tmp, { recursive: true, force: true });

// 2. Every focus grant carries a FOCUS-OK marker within the 3 lines above it.
const GRANT = /\b(active|focused|highlighted|selected|drawAttention)\s*:\s*true\b/;
for (const f of FILES) {
  const lines = read(f).split("\n");
  let granted = 0;
  lines.forEach((line, i) => {
    if (!GRANT.test(line)) return;
    if (/\.query\(/.test(line)) return; // tabs.query({active:true}) is a filter, not a grant
    granted++;
    const context = lines.slice(Math.max(0, i - 3), i + 1).join("\n");
    if (!MARKER.test(context)) {
      failures.push(`${f}:${i + 1}: focus grant without a FOCUS-OK(owner-…) marker: ${line.trim()}`);
    }
  });
  const allowed = ALLOWED_GRANTS[f] || 0;
  if (granted !== allowed) {
    failures.push(`${f}: ${granted} focus-grant site(s), audit pinned ${allowed} — every change here needs a §9 re-audit (and this number updated)`);
  }
}

// 3. Every chrome.tabs.create must say active:false — Chrome's default is to
// FOCUS the new tab — unless it is a marked owner gesture.
for (const f of FILES) {
  const lines = read(f).split("\n");
  lines.forEach((line, i) => {
    if (!line.includes("chrome.tabs.create(")) return;
    const call = lines.slice(i, i + 3).join("\n");
    const context = lines.slice(Math.max(0, i - 3), i + 1).join("\n");
    if (!/active\s*:\s*false/.test(call) && !MARKER.test(context)) {
      failures.push(`${f}:${i + 1}: tabs.create without active:false (Chrome defaults to stealing focus): ${line.trim()}`);
    }
  });
}

// 4. No tab highlighting, ever. Window creation is permitted only for the
// audited no-current-window recovery path, and it must be both unfocused and
// minimized. The per-file count is pinned so a second path cannot slip in.
const ALLOWED_WINDOW_CREATES = { "agent_loop.js": 1 };
for (const f of FILES) {
  const src = read(f);
  if (src.includes("chrome.tabs.highlight")) {
    failures.push(`${f}: uses chrome.tabs.highlight — nothing we do may highlight tabs`);
  }
  const lines = src.split("\n");
  let creates = 0;
  lines.forEach((line, i) => {
    if (!line.includes("chrome.windows.create(")) return;
    creates++;
    const marker = lines.slice(Math.max(0, i - 3), i + 1).join("\n");
    const call = lines.slice(i, i + 7).join("\n");
    if (!/WINDOW-OK\(no-current-window\)/.test(marker)
        || !/focused\s*:\s*false/.test(call)
        || !/state\s*:\s*["']minimized["']/.test(call)) {
      failures.push(`${f}:${i + 1}: window creation is not the audited unfocused/minimized recovery path`);
    }
  });
  const allowed = ALLOWED_WINDOW_CREATES[f] || 0;
  if (creates !== allowed) {
    failures.push(`${f}: ${creates} window-creation site(s), audit pinned ${allowed}`);
  }
}

// 5. Manifest: version bumped past 0.2.3, notifications permission present.
const manifest = JSON.parse(read("manifest.json"));
const [ma, mi, pa] = manifest.version.split(".").map(Number);
if (ma * 1e6 + mi * 1e3 + pa <= 2003) failures.push(`manifest.json: version ${manifest.version} not bumped past 0.2.3`);
if (!manifest.permissions.includes("notifications")) failures.push("manifest.json: missing the notifications permission the hand-back path needs");

if (failures.length) {
  console.error(`check_never_foreground: FAIL (${failures.length})`);
  for (const f of failures) console.error("  - " + f);
  process.exit(1);
}
console.log("check_never_foreground: PASS — zero focus-stealing calls outside owner-gesture paths; syntax + manifest checks green");
