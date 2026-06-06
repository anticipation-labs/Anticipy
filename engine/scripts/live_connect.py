"""Connect a real app to the API hand (Arcade OAuth) — get the approve-URL for the user.

    PYTHONPATH=engine engine/.venv/bin/python engine/scripts/live_connect.py [Tool.Name ...]

Defaults to the Google Calendar tools the agent uses (read + create). For each, prints either
"already connected" or the Arcade OAuth URL to open + approve once, in the browser signed into the
same Arcade.dev account as ARCADE_USER_ID. This is a READ-ONLY authorize handshake — it executes
nothing. Re-run after approving to confirm "already connected".
"""
import os
import sys

from anticipy_engine.core.env import load_local_env

load_local_env()


def main():
    tools = sys.argv[1:] or ["GoogleCalendar.ListEvents", "GoogleCalendar.CreateEvent"]
    user_id = os.environ.get("ARCADE_USER_ID") or os.environ.get("ADMIN_EMAIL", "omar@anticipy.ai")
    key = os.environ.get("ARCADE_API_KEY")
    if not key:
        print("ARCADE_API_KEY not set in .env.local — can't authorize."); return
    from arcadepy import Arcade

    client = Arcade(api_key=key)
    print(f"Arcade user_id: {user_id}\n")
    pending = 0
    for tool in tools:
        try:
            auth = client.tools.authorize(tool_name=tool, user_id=user_id)
        except Exception as e:
            print(f"  {tool}: ERROR {type(e).__name__}: {e}"); continue
        if getattr(auth, "status", None) == "completed":
            print(f"  {tool}: already connected ✓")
        else:
            pending += 1
            print(f"  {tool}: NOT connected — open this URL, sign in, approve:")
            print(f"    {getattr(auth, 'url', None)}")
    print("\nApprove the URL(s) once in your browser, then re-run this to confirm 'already connected'."
          if pending else "\nAll requested tools are connected.")


if __name__ == "__main__":
    main()
