import { NextResponse } from "next/server";

export const dynamic = "force-static";

/**
 * GET /download — serve the latest Anticipy Mac .dmg.
 *
 * The .dmg is UNSIGNED per the v-final-prototype Phase 8 spec (2026-05-14).
 * On first launch, the user right-clicks → Open to bypass Gatekeeper;
 * after that, Gatekeeper trusts the app for that user.
 *
 * The .dmg is ~100 MB which exceeds GitHub's 100 MB file limit, so we
 * upload each build to GitHub Releases and redirect /download to the
 * latest release asset. The Releases URL pattern is stable; only the
 * version tag in the path changes per build.
 */
const LATEST_DMG_URL =
  "https://github.com/omize10/Anticipy/releases/latest/download/Anticipy.dmg";

export function GET(): NextResponse {
  return NextResponse.redirect(LATEST_DMG_URL, { status: 302 });
}
