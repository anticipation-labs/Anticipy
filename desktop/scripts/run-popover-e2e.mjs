#!/usr/bin/env node
// Wrapper around Playwright for the desktop popover e2e suite.
// Playwright is installed at the repo root (see repo-root package.json),
// not in desktop/node_modules; this script locates the CLI and invokes
// it with desktop/playwright.config.ts so `pnpm test:e2e` works from
// `cd desktop` without a duplicate install.

import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const desktopDir = path.resolve(here, "..");
const repoRoot = path.resolve(desktopDir, "..");

const cliCandidates = [
  path.join(desktopDir, "node_modules", "@playwright", "test", "cli.js"),
  path.join(repoRoot, "node_modules", "@playwright", "test", "cli.js"),
];

let cli = null;
for (const c of cliCandidates) {
  if (existsSync(c)) {
    cli = c;
    break;
  }
}

if (!cli) {
  console.error(
    "[run-popover-e2e] Playwright CLI not found. Searched:\n" +
      cliCandidates.map((c) => "  - " + c).join("\n")
  );
  process.exit(2);
}

const passthrough = process.argv.slice(2);
const args = [
  cli,
  "test",
  "--config",
  path.join(desktopDir, "playwright.config.ts"),
  ...passthrough,
];

const child = spawn("node", args, {
  cwd: desktopDir,
  stdio: "inherit",
  env: { ...process.env },
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.exit(1);
  }
  process.exit(code ?? 1);
});

child.on("error", (err) => {
  console.error("[run-popover-e2e] failed to spawn playwright:", err);
  process.exit(1);
});
