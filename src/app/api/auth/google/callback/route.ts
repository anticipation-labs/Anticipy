import { NextRequest, NextResponse } from "next/server";
import { exchangeCodeForTokens, storeTokens } from "@/lib/google-calendar";
import { escapeHtml } from "@/lib/escape";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const code = request.nextUrl.searchParams.get("code");
  const error = request.nextUrl.searchParams.get("error");

  if (error) {
    return new Response(renderPage("Access Denied", "Google Calendar access was denied."), {
      headers: { "Content-Type": "text/html" },
    });
  }

  if (!code) {
    return new Response(renderPage("Error", "No authorization code received."), {
      headers: { "Content-Type": "text/html" },
      status: 400,
    });
  }

  // Validate state matches the cookie we set when starting OAuth — basic
  // CSRF protection so an attacker can't trick a logged-in user into
  // attaching a calendar they don't control.
  const returnedState = request.nextUrl.searchParams.get("state");
  const expectedState = request.cookies.get("anticipy_oauth_state")?.value;
  if (!expectedState || returnedState !== expectedState) {
    return new Response(
      renderPage(
        "Session Mismatch",
        "Couldn't verify this OAuth flow. Please start again from the Engine page."
      ),
      { headers: { "Content-Type": "text/html" }, status: 400 }
    );
  }

  // Prefer the app-user email from the cookie set in /api/auth/google.
  // Fallback to the Google account email only when no cookie is present
  // (e.g., pre-existing flows in flight at deploy time).
  const cookieEmail = request.cookies.get("anticipy_oauth_email")?.value;

  try {
    const tokens = await exchangeCodeForTokens(code);

    let email = cookieEmail;
    if (!email) {
      const userInfoRes = await fetch("https://www.googleapis.com/oauth2/v2/userinfo", {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      });
      const userInfo = await userInfoRes.json();
      email = userInfo.email;
    }

    // Fail closed: never store tokens under a fallback email — that would
    // attribute the connected calendar to the wrong user.
    if (!email) {
      return new Response(
        renderPage(
          "Couldn't identify account",
          "We couldn't determine which Anticipy account this calendar belongs to. Please start again from the Engine page."
        ),
        { headers: { "Content-Type": "text/html" }, status: 400 }
      );
    }

    await storeTokens(email, {
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expiry_date: Date.now() + (tokens.expires_in ?? 3600) * 1000,
    });

    const response = new Response(
      renderPage(
        "Connected",
        `Google Calendar connected for ${escapeHtml(email)}. You can close this tab.`
      ),
      { headers: { "Content-Type": "text/html" } }
    );
    // Clear the short-lived cookies so they can't be replayed.
    response.headers.append(
      "Set-Cookie",
      "anticipy_oauth_email=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
    );
    response.headers.append(
      "Set-Cookie",
      "anticipy_oauth_state=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
    );
    return response;
  } catch (err) {
    console.error("Google OAuth callback error:", err);
    // Avoid leaking raw provider error text into HTML — use a generic message.
    return new Response(
      renderPage(
        "Error",
        "Couldn't finish connecting Google Calendar. Please try again from the Engine page."
      ),
      {
        headers: { "Content-Type": "text/html" },
        status: 500,
      }
    );
  }
}

/**
 * Renders the post-OAuth page. `title` and `message` are caller-controlled and
 * MUST be safe (already escaped or static literals). All values from external
 * sources (Google response, error messages) must pass through escapeHtml first.
 */
function renderPage(title: string, message: string): string {
  return `<!DOCTYPE html>
<html>
<head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Anticipy — ${escapeHtml(title)}</title></head>
<body style="background:#0C0C0C;color:#FAFAFA;font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;">
  <div style="text-align:center;max-width:400px;padding:40px;">
    <h1 style="font-family:Georgia,serif;font-size:24px;color:#C8A97E;margin-bottom:12px;">Anticipy</h1>
    <p style="font-size:18px;margin-bottom:8px;">${escapeHtml(title)}</p>
    <p style="font-size:14px;color:#8A8A8A;">${message}</p>
    <a href="/engine" style="display:inline-block;margin-top:24px;padding:10px 24px;background:#C8A97E;color:#0C0C0C;text-decoration:none;border-radius:100px;font-size:14px;font-weight:600;">Back to Engine</a>
  </div>
</body>
</html>`;
}
