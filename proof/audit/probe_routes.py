"""Inventory and exercise local HTTP dispatch without provider credentials.

Syntax matching here extracts CODE paths for an audit; it never classifies a
person's words or controls production behavior. A response is an observation,
not proof of a route's authenticated happy path or external integration.
"""
import hashlib
import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]


def routes():
    source = ROOT / "migration/workers/src/index.ts"
    text = source.read_text()
    found = {}
    for match in re.finditer(r'path === "([^"\n]+)" && method === "(GET|POST|PATCH|DELETE)"', text):
        found[(match[2], match[1])] = {"source": str(source.relative_to(ROOT)), "line": text[:match.start()].count("\n") + 1}
    # Named routes dispatch by their constant and check methods in the handler.
    for file in sorted((ROOT / "migration/workers/src/routes").glob("*.ts")):
        code = file.read_text()
        for match in re.finditer(r'export const (\w+_PATH) = "([^"\n]+)"', code):
            if match[1] not in text:
                continue
            found[("POST", match[2])] = {"source": str(file.relative_to(ROOT)), "line": code[:match.start()].count("\n") + 1}
    for method, path in [
        ("GET", "/me/connections"), ("DELETE", "/me/connections/audit-missing"),
        ("GET", "/c/audit-missing"), ("POST", "/c/audit-missing/verify"),
        ("GET", "/r/audit-missing"), ("GET", "/internal/cal/audit-missing"),
        ("GET", "/api/realtime"), ("POST", "/api/realtime"),
        ("GET", "/api/files/evidence/audit-missing/missing.png"),
        ("POST", "/api/collections/owners/records"),
    ]:
        found[(method, path)] = {"source": "migration/workers/src/index.ts", "line": None}
    schema = (ROOT / "migration/workers/src/pb/schema.ts").read_text()
    for name in re.findall(r'^  ([a-z_]+): \{', schema, re.M):
        for method, suffix in [("GET", ""), ("POST", ""), ("GET", "/auditmissing001"), ("PATCH", "/auditmissing001"), ("DELETE", "/auditmissing001")]:
            found.setdefault((method, f"/api/collections/{name}/records{suffix}"), {"source": "migration/workers/src/pb/schema.ts", "line": None})
    return found


def main():
    session = requests.Session()
    session.trust_env = False
    observations = []
    for (method, path), origin in sorted(routes().items()):
        response = session.request(method, "http://127.0.0.1:8787" + path,
                                   json={} if method != "GET" else None, timeout=20, allow_redirects=False)
        try:
            body = response.json()
        except ValueError:
            body = {"bytes": len(response.content), "sha256": hashlib.sha256(response.content).hexdigest()}
        observations.append({**origin, "method": method, "path": path, "status": response.status_code,
                             "response": body, "scope": "local unauthenticated request with empty input",
                             "review_status": "observed_not_happy_path_verified"})
    output = ROOT / "research/audit-2026-09-06/inventory/local-route-observations.json"
    output.write_text(json.dumps(observations, indent=2) + "\n")
    print(json.dumps({"routes_exercised": len(observations),
                      "statuses": {str(status): sum(o["status"] == status for o in observations) for status in sorted({o["status"] for o in observations})}}))


if __name__ == "__main__":
    main()
