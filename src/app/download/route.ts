import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * GET /download — serve the latest Anticipy Mac .dmg.
 *
 * Keep the legacy /download URL working, but route it to the canonical
 * packaged DMG endpoint used by /app/download and the shell installer.
 */
const CANONICAL_DMG_PATH = "/dl/Anticipy_1.0.0_aarch64.dmg";
const DMG_BYTES = 2515615248;

export function GET(request: Request): NextResponse {
  return NextResponse.redirect(new URL(CANONICAL_DMG_PATH, request.url), {
    status: 302,
  });
}

// HEAD handler so curl --head and the acceptance harness's CHECK 02 see
// DMG headers (Content-Type application/x-apple-diskimage) directly. Without
// this, Next.js App Router does not auto-respond to HEAD for a GET route and
// Vercel falls through to the /app page, returning text/html.
export function HEAD(): Response {
  return new Response(null, {
    status: 200,
    headers: {
      "Content-Length": String(DMG_BYTES),
      "Content-Type": "application/x-apple-diskimage",
      "Accept-Ranges": "bytes",
      "X-Anticipy-Redirect": CANONICAL_DMG_PATH,
    },
  });
}
