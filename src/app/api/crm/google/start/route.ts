import { NextResponse } from "next/server";
import { requireCrmGate } from "@/lib/crm/auth";
import { getCrmGoogleAuthUrl, googleConfigured } from "@/lib/crm/google";

export async function GET(req: Request) {
  const gate = requireCrmGate(req);
  if (gate) return gate;
  if (!googleConfigured()) {
    return NextResponse.json(
      {
        error: "Google OAuth is not configured.",
        hint:
          "Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and ENCRYPTION_KEY (32-byte hex). Add the redirect URI <site>/api/auth/google/callback in your Google Cloud Console OAuth client.",
      },
      { status: 501 }
    );
  }
  return NextResponse.json({ url: getCrmGoogleAuthUrl("crm") });
}
