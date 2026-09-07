"""Install the GitHub-held webhook secret without exposing its value.

The provider dashboard must use the same secret. This does not send a message,
read customers, change destinations, or alter any other Worker binding.
"""
import json
import os
import time
import urllib.error
import urllib.request


def request(url, *, method="POST", headers=None, body=b"["):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main():
    secret = os.environ["SENDBLUE_WEBHOOK_SECRET"]
    if len(secret) < 32:
        raise SystemExit("Webhook secret must contain at least 32 random characters")
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    status, body = request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/anticipy-api/secrets",
        method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        body=json.dumps({"name": "SENDBLUE_WEBHOOK_SECRET", "text": secret,
                         "type": "secret_text"}).encode(),
    )
    if status != 200 or not json.loads(body).get("success"):
        raise SystemExit(f"Cloudflare secret installation failed: HTTP {status}")
    url = "https://api.anticipy.ai/sms/sendblue"
    common = {"Content-Type": "application/json", "User-Agent": "Anticipy-release-proof/1"}
    for attempt in range(15):
        unsigned, _ = request(url, headers=common)
        signed, _ = request(url, headers=dict(common, **{"sb-signing-secret": secret}))
        if unsigned == 403 and signed == 400:
            break
        if attempt < 14:
            time.sleep(2)
    # Deliberately malformed JSON: an accepted secret reaches parsing but never
    # creates an event or contacts the model/provider. It must be a 400, not 403.
    print(json.dumps({"worker": "anticipy-api", "secret_installed": True,
                      "unsigned_status": unsigned, "signed_invalid_json_status": signed,
                      "customer_rows_written": False, "messages_sent": False}))
    if unsigned != 403 or signed != 400:
        raise SystemExit("Live webhook authentication did not match the configured secret")


if __name__ == "__main__":
    main()
