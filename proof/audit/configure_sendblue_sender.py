"""Align API and brain with the operator-verified existing SendBlue line.

Only the sender binding is changed. A brain rollout is still needed because
existing containers retain their environment; its health reports the sender.
"""
import json
import os
import re
from proof.audit.live_api_release import request


def main():
    sender = os.environ["SENDBLUE_FROM_NUMBER"].strip()
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", sender):
        raise SystemExit("A verified E.164 sender is required")
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    base = "https://api.cloudflare.com/client/v4"
    for worker in ("anticipy-api", "anticipy-brain"):
        path = f"/accounts/{account}/workers/scripts/{worker}"
        status, body, _ = request(base, "GET", path + "/settings", token=token)
        if status != 200 or not body.get("success"):
            raise SystemExit(f"Cannot inspect {worker} settings: HTTP {status}")
        bindings = body.get("result", {}).get("bindings", [])
        before = next((b for b in bindings if b.get("name") == "SENDBLUE_FROM_NUMBER"), {})
        print(json.dumps({"worker": worker, "previous_binding_type": before.get("type"),
            "previous_sender": before.get("text") if before.get("type") == "plain_text" else None}))
        status, body, _ = request(base, "PUT", path + "/secrets", {
            "name": "SENDBLUE_FROM_NUMBER", "text": sender, "type": "secret_text"}, token)
        if status != 200 or not body.get("success"):
            raise SystemExit(f"Cannot set {worker} sender: HTTP {status}")
        print(json.dumps({"worker": worker, "configured_sender": sender,
                          "messages_sent": False}))


if __name__ == "__main__":
    main()
