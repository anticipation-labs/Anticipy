"""One-off probe: confirm the engine reads ARCADE_API_KEY and the real Arcade SDK
authorize() flow works (returns a status + connect URL). No send happens here.
"""
import os

from anticipy_engine.core.env import load_local_env

load_local_env()
key = os.environ.get("ARCADE_API_KEY")
print("ARCADE_API_KEY set:", bool(key), (key[:12] + "…") if key else None)

from arcadepy import Arcade

client = Arcade(api_key=key)
auth = client.tools.authorize(tool_name="Gmail.SendEmail", user_id="omar@anticipy.ai")
print("authorize.status:", getattr(auth, "status", None))
print("authorize.url:", getattr(auth, "url", None))
print("authorize attrs:", [a for a in dir(auth) if not a.startswith("_")])
