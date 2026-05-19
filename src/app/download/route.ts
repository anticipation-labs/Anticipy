import { NextResponse } from "next/server";

export const dynamic = "force-static";

/**
 * GET /download — serve the latest Anticipy Mac .dmg.
 *
 * The .dmg is uploaded to GitHub Releases because it exceeds GitHub's
 * normal repository file-size limit. The shell installer removes the
 * quarantine flag before terminal-launching the local engine, so the
 * first-run path does not require a Gatekeeper click.
 */
const LATEST_DMG_URL =
  "https://github.com/omize10/Anticipy/releases/download/v1.0.1-terminal-engine/Anticipy.dmg";

export function GET(): NextResponse {
  return NextResponse.redirect(LATEST_DMG_URL, { status: 302 });
}
