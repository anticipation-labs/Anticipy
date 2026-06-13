"""Owner API auth gate.

When ANTICIPY_OWNER_API_TOKEN is set for a public deploy, private engine routes
must reject anonymous requests. The Next API proxy supplies the token server-side;
local development keeps the env unset and remains unchanged.
"""
import os
import tempfile

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy-api-auth-")

from fastapi.testclient import TestClient  # noqa: E402

from anticipy_engine.main import app  # noqa: E402


TOKEN = "owner-test-token-12345"


def main():
    old = os.environ.get("ANTICIPY_OWNER_API_TOKEN")
    os.environ["ANTICIPY_OWNER_API_TOKEN"] = TOKEN
    try:
        with TestClient(app) as client:
            health = client.get("/health")
            assert health.status_code == 200, health.text

            for path in ("/status", "/pending", "/owner/cards"):
                res = client.get(path)
                assert res.status_code == 401, (path, res.status_code, res.text)

            status = client.get("/status", headers={"x-anticipy-owner-token": TOKEN})
            assert status.status_code == 200, status.text

            pending = client.get("/pending", headers={"authorization": f"Bearer {TOKEN}"})
            assert pending.status_code == 200, pending.text

            bad = client.get("/status", headers={"x-anticipy-owner-token": "wrong"})
            assert bad.status_code == 401, bad.text

            os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
            open_status = client.get("/status")
            assert open_status.status_code == 200, open_status.text
    finally:
        if old is None:
            os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
        else:
            os.environ["ANTICIPY_OWNER_API_TOKEN"] = old

    print("PASS owner_api_auth: optional owner token protects private engine routes")


if __name__ == "__main__":
    main()
