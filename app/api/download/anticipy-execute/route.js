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

const PREVIEW_NOTICE = `Anticipy Execute — developer preview
=====================================

The desktop app bundle has not been built in this deployment yet, so there is
nothing to download right now. This is an honest 200 (not a 404 and not a fake
binary): the real app is built from source and is an UNSIGNED developer preview.

To build it locally:

  1. Build the macOS app (SwiftUI, no Xcode required — Command Line Tools are enough):
       bash macapp/scripts/build_app.sh
     This produces  macapp/dist/Anticipy.app

  2. (Optional) Run the packaging helper to also build the web front-end:
       bash scripts/package_app.sh

  3. Re-request this URL. It will then serve  Anticipy.app.zip  (the unsigned
     developer preview). Open it via right-click -> Open on first launch, since
     it is not yet Apple-notarized.

A signed, one-click public download ships once an Apple Developer ID is in place
(Omar-gated: Apple enrollment + notarization). That step is never faked here.
`;

export async function GET() {
  if (!bundleExists()) {
    return new Response(PREVIEW_NOTICE, {
      status: 200,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "cache-control": "no-store",
        "x-anticipy-build": "developer-preview-pending-build",
      },
    });
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
  } catch (error) {
    // Packaging the existing bundle failed — surface it honestly (still not a 404
    // for the button, and never a fabricated artifact).
    return new Response(
      `Could not package the developer-preview bundle: ${
        error instanceof Error ? error.message : String(error)
      }\n\nThe bundle exists at macapp/dist/Anticipy.app — rebuild with:\n  bash macapp/scripts/build_app.sh\n`,
      {
        status: 500,
        headers: {
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "no-store",
          "x-anticipy-build": "developer-preview-package-error",
        },
      },
    );
  }
}
