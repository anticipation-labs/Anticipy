"""Read only the authored private-draft probe's historical runtime error.

No model calls or messages. No unfiltered logs, credentials, or customer text
are printed. Cloudflare's telemetry query uses dry=True (no saved query).
"""
import json
import os
import re
from datetime import datetime

from proof.audit.live_api_release import request


def main():
    marker = "Anticipy test retry:"
    stamp = lambda value: int(datetime.fromisoformat(value).timestamp() * 1000)
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    body = {
        "queryId": "private-draft-runtime-diagnostic", "dry": True,
        "view": "events", "limit": 20,
        "timeframe": {"from": stamp("2026-09-07T17:39:00+00:00"),
                      "to": stamp("2026-09-07T17:41:00+00:00")},
        "parameters": {"filters": [{"key": "$metadata.message",
            "operation": "includes", "type": "string", "value": marker}]},
    }
    status, result, _ = request("https://api.cloudflare.com/client/v4", "POST",
        f"/accounts/{account}/workers/observability/telemetry/query", body,
        os.environ["CLOUDFLARE_API_TOKEN"])
    print(json.dumps({"query_http_status": status,
                      "success": result.get("success"),
                      "error_codes": [e.get("code") for e in result.get("errors", [])]}))
    if status != 200 or not result.get("success"):
        raise SystemExit(1)

    found = set()
    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and marker in value and " -> error: " in value:
            error = value.split(" -> error: ", 1)[1]
            # Transport diagnostics, not meaning: redact phone/token-shaped
            # substrings even though SendBlue's wrapper already scrubs secrets.
            error = re.sub(r"\+\d{6,}", "[phone]", error)
            error = re.sub(r"[A-Za-z0-9_/-]{28,}", "[identifier]", error)
            found.add(error[:600])
    visit(result.get("result", {}))
    print(json.dumps({"probe_errors": sorted(found),
                      "response_sections": sorted(result.get("result", {}))}))


if __name__ == "__main__":
    main()
