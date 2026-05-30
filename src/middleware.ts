import { NextRequest, NextResponse } from "next/server";

// Cookie-name and verifier inline. Edge middleware can use the global
// Web Crypto API; the HMAC scheme matches src/lib/gate-cookie.ts byte-for-
// byte so a cookie minted by /api/internal-gate verifies here too.
const GATE_COOKIE_NAME = "anticipy_internal_gate";

function bytesToHex(bytes: ArrayBuffer): string {
  const view = new Uint8Array(bytes);
  let out = "";
  for (let i = 0; i < view.length; i += 1) {
    out += view[i].toString(16).padStart(2, "0");
  }
  return out;
}

function safeEqualHex(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

async function verifyGateCookie(
  value: string | undefined | null
): Promise<boolean> {
  if (!value || typeof value !== "string") return false;
  const [expStr, sig] = value.split(".");
  if (!expStr || !sig) return false;
  const exp = Number(expStr);
  if (!Number.isFinite(exp)) return false;
  if (exp < Math.floor(Date.now() / 1000)) return false;
  const secret =
    process.env.GATE_COOKIE_SECRET ||
    process.env.SUPABASE_SERVICE_ROLE_KEY ||
    "";
  if (!secret) return false;
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const macBytes = await crypto.subtle.sign("HMAC", key, enc.encode(String(exp)));
  const expected = bytesToHex(macBytes);
  return safeEqualHex(sig, expected);
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // /download is handled by src/app/download/route.ts which redirects
  // to the canonical packaged DMG. Do NOT intercept it here.
  if (pathname === "/engine" || pathname.startsWith("/engine/")) {
    const url = request.nextUrl.clone();
    url.pathname = "/app";
    url.search = "";
    return NextResponse.redirect(url, 301);
  }

  // B061: client-side PasswordGate previously rendered the full /internal
  // page HTML server-side (including hardware spec, block diagrams, BOM,
  // pinouts). Anyone could curl the URL to read the doc, because the gate
  // was JS-only. Enforce here in middleware, BEFORE the page renders.
  if (pathname.startsWith("/internal")) {
    const cookie = request.cookies.get(GATE_COOKIE_NAME)?.value;
    const ok = await verifyGateCookie(cookie);
    if (!ok) {
      // Return a minimal 401 page rather than redirecting so search
      // engines and curl-based scrapers don't get a 200 with content.
      return new NextResponse(
        "Internal area. Pass the gate at /api/internal-gate first.",
        { status: 401, headers: { "content-type": "text/plain" } }
      );
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/engine",
    "/engine/:path*",
    "/internal",
    "/internal/:path*",
  ],
};
