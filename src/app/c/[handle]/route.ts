import { NextRequest, NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { normalizeHandle, validateHandle } from "@/app/ugc/program";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** How long a creator stays credited for a visit they sent. */
const REF_COOKIE_DAYS = 90;

/**
 * A creator's link: anticipy.ai/c/<handle>.
 *
 * Drops a first-party cookie naming the creator, then sends the visitor to
 * the homepage, since that is where a pre-order starts and a pre-order is
 * what the creator earns a share of.
 *
 * An unknown handle redirects to the homepage rather than 404ing. The link
 * will be printed in bios and burned into video captions where it cannot be
 * corrected, so a typo or a since-removed creator must still land somebody on
 * the product instead of on an error.
 */
export async function GET(
  request: NextRequest,
  { params }: { params: { handle: string } }
) {
  const handle = normalizeHandle(params.handle ?? "");
  const home = new URL("/", request.url);

  if (validateHandle(handle)) {
    return NextResponse.redirect(home, { status: 307 });
  }

  let known = false;
  try {
    const { data } = await supabaseAdmin
      .from("anticipy_ugc_creators")
      .select("handle")
      .ilike("handle", handle)
      .maybeSingle();
    known = !!data;
  } catch {
    // Attribution is worth less than the visit. If the lookup fails, still
    // send them to the product.
  }

  if (!known) {
    return NextResponse.redirect(home, { status: 307 });
  }

  // ?ref stays on the URL so first-touch analytics sees it; the cookie is what
  // survives the visitor wandering the site before they act.
  home.searchParams.set("ref", handle);
  const res = NextResponse.redirect(home, { status: 307 });
  res.cookies.set("ap_ref", handle, {
    maxAge: REF_COOKIE_DAYS * 24 * 60 * 60,
    path: "/",
    sameSite: "lax",
    httpOnly: false, // analytics on the client reads this too
    secure: process.env.NODE_ENV === "production",
  });
  return res;
}
