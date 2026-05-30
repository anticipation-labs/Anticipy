import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/**
 * GET /dl/Anticipy_1.0.0_aarch64.dmg
 *
 * Redirects to the public R2 bucket URL. Previously used a presigned S3-style
 * URL that expired (7-day SigV4 cap). The public bucket URL never expires.
 */
const R2_PUBLIC_URL =
  "https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/Anticipy_1.0.0_aarch64.dmg";

const DMG_BYTES = 2516060536;

export function GET(): NextResponse {
  return NextResponse.redirect(R2_PUBLIC_URL, { status: 302 });
}

export function HEAD(): Response {
  return new Response(null, {
    status: 200,
    headers: {
      "Content-Length": String(DMG_BYTES),
      "Content-Type": "application/x-apple-diskimage",
      "Accept-Ranges": "bytes",
    },
  });
}
