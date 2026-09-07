"""Read rollout and instance metadata; never expose container environments."""
import json
import os
from urllib.parse import quote

from proof.audit.live_api_release import request


def main():
    base = ("https://api.cloudflare.com/client/v4/accounts/"
            + os.environ["CLOUDFLARE_ACCOUNT_ID"] + "/containers")

    def read(path):
        status, body, _ = request(base, "GET", path,
                                  token=os.environ["CLOUDFLARE_API_TOKEN"])
        if status != 200:
            raise RuntimeError(f"Container metadata HTTP {status}")
        return body.get("result", body) if isinstance(body, dict) else body

    def rows(body):
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for key in ("applications", "rollouts", "data", "items"):
                if isinstance(body.get(key), list):
                    return body[key]
        raise RuntimeError("Unexpected metadata shape; no content printed")

    def facts(record):
        # Whitelist scalar operational metadata. Configuration may contain
        # secrets and must never be emitted, even during error diagnosis.
        allowed = ("id", "name", "status", "state", "created_at", "updated_at",
                   "started_at", "completed_at", "version", "image", "deployment_id",
                   "rollout_id", "current_step", "active_grace_period", "health")
        return {k: record[k] for k in allowed if k in record
                and isinstance(record[k], (str, int, float, bool, type(None)))}

    apps = [a for a in rows(read("/applications"))
            if a.get("name") == "anticipy-brain-owner"]
    if len(apps) != 1:
        raise RuntimeError("Expected one Anticipy brain container application")
    app = apps[0]
    identifier = quote(app["id"], safe="")
    print(json.dumps({"application": facts(app)}))
    rollouts = rows(read(f"/applications/{identifier}/rollouts?limit=8"))
    print(json.dumps({"rollouts": [facts(r) for r in rollouts]}))
    body = read(f"/dash/applications/{identifier}/instances?per_page=100")
    data = body.get("data", body)
    print(json.dumps({"instance_metadata_keys": sorted(data)}))
    for key in ("instances", "durable_objects"):
        print(json.dumps({key: [facts(row) for row in data.get(key, [])]}))


if __name__ == "__main__":
    main()
