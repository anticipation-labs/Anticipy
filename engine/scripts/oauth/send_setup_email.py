"""Send the consolidated [ANTICIPY-Q] setup email — one batched ask
covering every service that needs Omar's hands.

Run after the setup_form server is started locally on :53118.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(REPO_ROOT / ".env.local")


SUBJECT = "[ANTICIPY-Q] OAuth + token setup for Phase 6 real-prod runs"

BODY = """Blocked on: 9 of the 10 reference skills need real auth before I can do 10-in-a-row real-production runs against them. Only navigate_fact_lookup is currently real-prod verified (against Wikipedia, no auth needed). Per Rule 1/13 of the master prompt — real tests only — the prior "Phase 6 complete" tag is overstated; verifier-against-fixture-world is not the same as real production.

What I tried:
- Found .env.local has GOOGLE_OAUTH_CLIENT_ID + SECRET (single Google OAuth client covers Gmail, Calendar, Sheets, Maps).
- No tokens / API keys for Slack, Notion, Linear, Spotify in env or anywhere on disk.
- Resy + Amazon use session cookies, not OAuth — they need browser logins.
- Chrome on :9222 is the SANDBOX profile (~/.anticipy/chrome-profile/), not your real Chrome — fresh, no logins, no cookies. OAuth + new logins per service in that Chrome window. (Switching :9222 to your real profile would require quitting your real Chrome — more invasive than fresh sign-ins.)

What I need from you (one sitting, ~15 min total):

A. Google Cloud Console — add my localhost callback so the agent's standalone OAuth works:
   https://console.cloud.google.com/apis/credentials
   - Click the OAuth 2.0 Client ID matching "245459497405-7mmivb2uvaht1i1t12i8iaeul18c03o3.apps.googleusercontent.com"
   - Authorized redirect URIs → ADD: http://localhost:53117/oauth2callback
   - Save
   (After this, I trigger consent in :9222 and you just click Allow once — covers all 4 Google skills.)

B. Slack workspace bot:
   https://api.slack.com/apps → Create New App → From scratch
   - Name: anticipy-test, pick a workspace you control
   - OAuth & Permissions → Bot Token Scopes → add chat:write + chat:write.public
   - Install to workspace → Allow
   - Copy "Bot User OAuth Token" (xoxb-...)
   - Pick a test channel (e.g. #anticipy-test, or any channel you can write to)
   - Paste both at: http://localhost:53118/

C. Notion:
   https://www.notion.so/my-integrations → New integration
   - Name: anticipy-test → Submit
   - Copy "Internal Integration Token" (secret_...)
   - Pick a test database (or create one) → ⋯ → Connections → connect "anticipy-test"
   - The database ID is the 32 hex chars in its URL: notion.so/<workspace>/<DATABASE_ID>?v=...
   - Paste both at: http://localhost:53118/

D. Linear:
   https://linear.app/settings/api → New API key
   - Label: anticipy-test → Create
   - Copy the key (lin_api_...)
   - Find your team ID: any team page URL, or settings → Teams → API
   - Paste both at: http://localhost:53118/

E. Spotify:
   https://developer.spotify.com/dashboard → Create app
   - Redirect URI: http://localhost:53117/oauth2callback
   - Copy Client ID + Client Secret
   - Paste both at: http://localhost:53118/
   (After paste, I'll open the user-auth flow in :9222 and you click Allow there.)

F. Resy: Cmd+Tab to the Anticipy sandbox Chrome window (it's already running on :9222 with no logins). Open https://resy.com → sign in with your Resy account. Then check the "Logged in to resy.com" box at http://localhost:53118/ and submit.

G. Amazon: same Chrome window. Open https://www.amazon.com → sign in (with 2FA). Then check the "Logged in to amazon.com" box at http://localhost:53118/ and submit.

Question ID: {qid}
Sent: {ts}
Setup form: http://localhost:53118/  ← this URL is live now; submit each section independently as you complete it
"""


def main() -> int:
    api_key = os.environ.get("RESEND_API_KEY")
    to = os.environ.get("ADMIN_EMAIL", "omarkebrahim@gmail.com")
    if not api_key:
        raise SystemExit("RESEND_API_KEY missing")
    qid = str(uuid.uuid4())
    body = BODY.format(qid=qid, ts=datetime.now(timezone.utc).isoformat())
    r = httpx.post(
        "https://api.resend.com/emails",
        json={
            # anticipy.ai isn't verified in Resend yet — using the
            # default onboarding sender. Once Omar verifies the
            # domain at https://resend.com/domains, we switch to
            # aevoy@anticipy.ai per correction #5.
            "from": "Anticipy Aevoy <onboarding@resend.dev>",
            "to": to,
            "reply_to": "omarkebrahim@gmail.com",
            "subject": SUBJECT,
            "text": body,
        },
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=15.0,
    )
    print(f"status={r.status_code}")
    print(r.text)
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
