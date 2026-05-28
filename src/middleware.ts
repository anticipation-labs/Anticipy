import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // /download is handled by src/app/download/route.ts which redirects
  // to the canonical packaged DMG. Do NOT intercept it here.
  if (pathname === "/engine" || pathname.startsWith("/engine/")) {
    const url = request.nextUrl.clone();
    url.pathname = "/app";
    url.search = "";
    return NextResponse.redirect(url, 301);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/engine", "/engine/:path*"],
};
