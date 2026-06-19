// GET /api/download/anticipy-execute — the target of the /download page button.
//
// HONEST CONTRACT (Laws 3 & 4 — no faked success, money/identity stays gated):
//   - If the real dev bundle (macapp/dist/Anticipy.app) is present, serve it as
//     a .zip (Anticipy.app.zip). It is an UNSIGNED, un-notarized developer
//     preview — every response says so in headers and the user opens it via
//     right-click -> Open (the banner on /download). We never claim it is signed.
//   - If no bundle has been built yet, return an HONEST 200 (text/plain) that
//     explains the developer-preview status and exactly how to build it. Never a
//     404 (the bug we are fixing), never a fake/placeholder binary.
//
// Apple Developer ID signing + notarization remain Omar-gated and are NOT done
// here. This route only hands over the artifact that actually exists.

import fs from "node:fs";
import path from "node:path";
import { zipDirectory } from "../zip";

export const dynamic = "force-dynamic";

function bundleDir() {
  // Next runs with cwd at the project root; the committed dev bundle lives here.
  return path.join(process.cwd(), "macapp", "dist", "Anticipy.app");
}

function bundleExists() {
  try {
    const dir = bundleDir();
    return (
      fs.existsSync(dir) &&
      fs.statSync(dir).isDirectory() &&
      fs.existsSync(path.join(dir, "Contents", "MacOS", "Anticipy"))
    );
  } catch {
    return false;
  }
}

// A real person who hits a not-yet-packaged build must NEVER see bash, ports, or
// monospace (R1.4 / §4.8). Serve the premium shell with one calm, human message and a
// way to reach a human — never a developer to-do list. (The honest contract is unchanged:
// we still never serve a 404 or a fake binary; we just say it in Donna's voice.)
function noticePage(line) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Anticipy</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Inter:wght@400;600&display=swap" rel="stylesheet" />
<style>
  :root{--ink:#0C0C0C;--cream:#F5F0EB;--warm:#6B635B;}
  *{box-sizing:border-box;}
  html,body{margin:0;min-height:100vh;background:var(--ink);color:var(--cream);
    font-family:Inter,system-ui,sans-serif;line-height:1.6;}
  main{min-height:100vh;display:grid;place-items:center;padding:48px 24px;}
  .col{max-width:560px;width:100%;}
  h1{font-family:"DM Serif Display",Georgia,serif;font-size:31px;line-height:1.2;margin:0 0 16px;}
  p{color:var(--cream);font-size:16px;margin:0 0 16px;}
  .sub{color:var(--warm);}
  a{color:var(--cream);text-underline-offset:3px;}
</style></head>
<body><main><div class="col">
  <h1>It&rsquo;s almost ready.</h1>
  <p>${line}</p>
  <p class="sub">Want it the moment it&rsquo;s ready? <a href="mailto:omarkebrahim@gmail.com?subject=Anticipy%20for%20Mac">Send a note</a> and you&rsquo;ll be on the next build.</p>
</div></main></body></html>`;
}

export async function GET() {
  if (!bundleExists()) {
    return new Response(
      noticePage("The Mac app isn&rsquo;t packaged on this server yet. A one-click version is on the way — nothing&rsquo;s broken on your end."),
      {
        status: 200,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
          "x-anticipy-build": "preview-pending-build",
        },
      },
    );
  }

  try {
    const zip = zipDirectory(bundleDir(), "Anticipy.app");
    return new Response(zip, {
      status: 200,
      headers: {
        "content-type": "application/zip",
        "content-disposition": 'attachment; filename="Anticipy.app.zip"',
        "content-length": String(zip.length),
        "cache-control": "no-store",
        // Honest provenance: this is the unsigned dev preview, not a notarized build.
        "x-anticipy-build": "developer-preview-unsigned",
      },
    });
  } catch {
    // Packaging the existing bundle failed — say so in Donna's voice, never a raw error
    // or a build command (still not a 404, still never a fabricated artifact).
    return new Response(
      noticePage("I hit a snag putting the download together. Try again in a moment."),
      {
        status: 500,
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
          "x-anticipy-build": "preview-package-error",
        },
      },
    );
  }
}
