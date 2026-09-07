"""Read deployed schema and aggregate counts; never print customer records."""
import json
import os
from proof.audit.live_api_release import request


def main():
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    path = f"/accounts/{account}/d1/database/f341f23d-ec52-4b2f-9a2d-13117ebee86e/query"
    queries = [
        "PRAGMA table_info('purges')",
        "SELECT count(*) AS triggers FROM sqlite_master WHERE type = 'trigger' AND name LIKE 'erasure_fence_%'",
        "SELECT count(*) AS pending_closed FROM purges p WHERE memory_purged = 0 AND NOT EXISTS (SELECT 1 FROM owners o WHERE o.id = p.owner_ref)",
        "SELECT count(*) AS pending_open FROM purges p WHERE memory_purged = 0 AND EXISTS (SELECT 1 FROM owners o WHERE o.id = p.owner_ref)",
    ]
    for sql in queries:
        status, body, _ = request("https://api.cloudflare.com/client/v4", "POST", path,
                                  {"sql": sql}, os.environ["CLOUDFLARE_API_TOKEN"])
        if status != 200 or not body.get("success"):
            raise RuntimeError("Structural query failed with HTTP " + str(status))
        print(json.dumps({"query": sql, "result": body["result"]}))


if __name__ == "__main__":
    main()
