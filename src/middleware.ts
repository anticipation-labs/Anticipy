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

// The unlock page. Served as the BODY of the 401 — the status stays 401 so
// scrapers and search engines still get a refusal, and the body carries no
// internal content at all, only a password box. That keeps B061's property
// (nothing readable without the cookie) while giving a human a way in.
//
// This exists because there was no way in. src/app/internal/PasswordGate.tsx
// is a real form, but it lives in the /internal LAYOUT — and this middleware
// returns before Next renders any layout, so that form could never appear on
// a deployed site. Every visitor, including the people who own the docs, got
// a plain-text sentence naming a JSON endpoint they cannot type into.
//
// Warm palette only, matching PasswordGate: ink #0C0C0C, champagne #C8A97E.
// No blue anywhere in this codebase, deliberately.
const UNLOCK_PAGE = `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Anticipy — Internal</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; display:flex; align-items:center;
         justify-content:center; background:#0C0C0C; color:#F5F0EB;
         font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .box { width:100%; max-width:360px; padding:40px 24px; text-align:center; }
  h1 { font:400 28px/1.2 Georgia,"Times New Roman",serif; color:#C8A97E;
       letter-spacing:.06em; margin:0 0 8px; }
  p.sub { color:#8A8A8A; font-size:14px; margin:0 0 32px; }
  input { width:100%; padding:14px 16px; border-radius:12px;
          border:1px solid #2A2A2A; background:#1E1E1E; color:#F5F0EB;
          font-size:17px; text-align:center; letter-spacing:.08em; }
  input:focus { outline:2px solid #C8A97E; outline-offset:2px; border-color:#C8A97E; }
  button { width:100%; margin-top:12px; padding:14px 16px; border:0;
           border-radius:999px; background:#C8A97E; color:#0C0C0C;
           font-size:16px; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.55; cursor:default; }
  button:focus-visible { outline:2px solid #F5F0EB; outline-offset:2px; }
  .msg { min-height:20px; margin-top:16px; font-size:14px; color:#C96A5A; }
  .hint { margin-top:28px; font-size:12px; color:#5A5A5A; }
</style>
</head><body>
<div class="box">
  <h1>ANTICIPY</h1>
  <p class="sub">Internal — enter access code</p>
  <form id="f" autocomplete="off">
    <input id="c" type="password" inputmode="text" enterkeyhint="go"
           aria-label="Access code" autofocus>
    <button id="b" type="submit">Unlock</button>
  </form>
  <div class="msg" id="m" role="status" aria-live="polite"></div>
  <p class="hint">This device stays unlocked for a month.</p>
</div>
<script>
(function () {
  var f = document.getElementById("f"), c = document.getElementById("c"),
      b = document.getElementById("b"), m = document.getElementById("m");
  f.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (b.disabled) return;
    b.disabled = true; m.textContent = "";
    fetch("/api/internal-gate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passcode: c.value.replace(/\\s+/g, "") })
    }).then(function (r) {
      if (r.ok) { location.reload(); return null; }
      if (r.status === 429) { m.textContent = "Too many tries. Wait a minute."; }
      else { m.textContent = "Wrong code."; }
      b.disabled = false; c.select();
      return null;
    }).catch(function () {
      m.textContent = "Network error. Try again.";
      b.disabled = false;
    });
  });
})();
</script>
</body></html>`;

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
      // Still a 401 either way, so search engines and curl-based scrapers
      // never get a 200 with content. What changes is the BODY: a browser
      // navigation gets the unlock form, everything else gets the sentence.
      //
      // Content negotiation rather than a redirect: a redirect to a /gate
      // page would be a 200 somewhere, and the whole point of B061 was that
      // no URL under here answers 200 without the cookie.
      const wantsHtml = (request.headers.get("accept") || "").includes("text/html");
      const headers: Record<string, string> = {
        "cache-control": "no-store",
        "x-robots-tag": "noindex, nofollow",
        "content-type": wantsHtml
          ? "text/html; charset=utf-8"
          : "text/plain; charset=utf-8",
      };
      return new NextResponse(
        wantsHtml
          ? UNLOCK_PAGE
          : "Internal area. Pass the gate at /api/internal-gate first.",
        { status: 401, headers }
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
