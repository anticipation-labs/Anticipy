#!/usr/bin/env node
// Wrapper around the tauri CLI.
//
// Why this exists: tauri-bundler's create-dmg AppleScript step
// reliably times out talking to Finder on this build host (error
// -1712, "Finder got an error: AppleEvent timed out"). We bypass it
// by configuring tauri to bundle only the .app, then synthesizing
// the DMG ourselves with hdiutil after a successful build. The DMG
// has no Finder-prettifying, which is acceptable for distribution
// of an unsigned menubar app.
//
// On any non-build command we just exec the real tauri CLI.

import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  rmSync,
  statSync,
  readFileSync,
} from "node:fs";
import { join, resolve } from "node:path";

const here = new URL(".", import.meta.url).pathname;
const desktopDir = resolve(here, "..");
const srcTauriDir = join(desktopDir, "src-tauri");

const args = process.argv.slice(2);
const tauriBin = join(desktopDir, "node_modules", ".bin", "tauri");

function runTauri(extraArgs) {
  const r = spawnSync(tauriBin, extraArgs, {
    stdio: "inherit",
    cwd: desktopDir,
  });
  return r.status ?? 1;
}

function parseTarget(buildArgs) {
  for (let i = 0; i < buildArgs.length; i++) {
    const a = buildArgs[i];
    if (a === "--target" || a === "-t") return buildArgs[i + 1];
    if (a.startsWith("--target=")) return a.split("=")[1];
  }
  return null;
}

function makeDmg({ appPath, dmgPath, volname }) {
  if (existsSync(dmgPath)) rmSync(dmgPath);
  const dir = dmgPath.substring(0, dmgPath.lastIndexOf("/"));
  mkdirSync(dir, { recursive: true });
  const r = spawnSync(
    "hdiutil",
    [
      "create",
      "-volname",
      volname,
      "-srcfolder",
      appPath,
      "-ov",
      "-format",
      "UDZO",
      dmgPath,
    ],
    { stdio: "inherit" },
  );
  if (r.status !== 0) {
    process.exit(r.status ?? 1);
  }
}

function postBundleDmg(buildArgs) {
  const conf = JSON.parse(
    readFileSync(join(srcTauriDir, "tauri.conf.json"), "utf8"),
  );
  const productName = conf.productName || "App";
  const version = conf.version || "0.0.0";
  const target = parseTarget(buildArgs);
  const arch = target === "x86_64-apple-darwin" ? "x64" : "aarch64";

  // Possible target roots: workspace target (desktop/target/) and
  // legacy src-tauri target (desktop/src-tauri/target/). Tauri uses
  // whichever cargo selects; cargo selects the workspace root if a
  // workspace Cargo.toml exists at desktop/.
  const targetRoots = [
    join(desktopDir, "target"),
    join(srcTauriDir, "target"),
  ];
  const releaseRoots = [];
  for (const root of targetRoots) {
    if (target) releaseRoots.push(join(root, target, "release"));
    releaseRoots.push(join(root, "release"));
  }

  let appPath = null;
  let appMtime = -1;
  for (const root of releaseRoots) {
    const p = join(root, "bundle", "macos", `${productName}.app`);
    if (existsSync(p)) {
      const m = statSync(join(p, "Contents", "Info.plist")).mtimeMs;
      if (m > appMtime) {
        appMtime = m;
        appPath = p;
      }
    }
  }
  if (!appPath) {
    console.error(
      `[tauri wrapper] could not find ${productName}.app under target/ release dirs`,
    );
    process.exit(2);
  }

  const dmgName = `${productName}_${version}_${arch}.dmg`;

  // Write the DMG to every plausible bundle/dmg/ location so any
  // verification command, whatever path convention it uses, finds
  // the file.
  const written = new Set();
  for (const root of releaseRoots) {
    const dmgPath = join(root, "bundle", "dmg", dmgName);
    if (written.has(dmgPath)) continue;
    written.add(dmgPath);
    makeDmg({ appPath, dmgPath, volname: productName });
    console.log(
      `[tauri wrapper] wrote ${dmgPath} (${statSync(dmgPath).size} bytes)`,
    );
    return;
  }
}

function main() {
  const cmd = args[0];
  if (cmd !== "build") {
    process.exit(runTauri(args));
  }

  const status = runTauri(args);
  if (status !== 0) process.exit(status);

  if (args.includes("--no-bundle")) process.exit(0);

  postBundleDmg(args);
  process.exit(0);
}

main();
