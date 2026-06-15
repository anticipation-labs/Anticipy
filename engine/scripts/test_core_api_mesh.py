"""Integration: the PRODUCTION ControlCore wires the per-person token vault into its
ApiHand, so a user who connected their OWN app authenticates with THEIR vault token —
not the shared ARCADE_API_KEY. test_api_vault proves the ApiHand+broker contract in
isolation; THIS proves the real engine actually passes the broker (the wiring gap that
left the per-person mesh dormant: control_core built ApiHand with no broker).

No network, no real OAuth: the Arcade client is a recording fake injected via the hand's
client_factory; the only plaintext reveal is the single .reveal() at the fake handshake.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_core_api_mesh.py
"""
import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ["ARCADE_USER_ID"] = "mesh-test-user@x.com"
os.environ["ANTICIPY_VAULT_KEY"] = "test-master-key-do-not-use-in-prod"
os.environ["ARCADE_API_KEY"] = "arc_FAKE-SHARED-KEY-0000"
os.environ.pop("ANTICIPY_OWNER_INGEST", None)

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.core.envelopes import Job, JobStatus  # noqa: E402
from anticipy_engine.hands.api_hand import MODE_LIVE  # noqa: E402
from anticipy_engine.hands.token_vault import ROUTE_API, TokenBroker  # noqa: E402

USER = "mesh-test-user@x.com"
TOKEN_USER = "arc_FAKE-user-7c1f9b2e4d6a8c0e3f5a7b9d1c3e5f70"
SHARED_KEY = "arc_FAKE-SHARED-KEY-0000"
READ_TOOLS = {"Gmail.ListEmails"}


class FakeTools:
    """Records every execute() and authorizes everything. No network."""

    def __init__(self, client):
        self.c = client

    def authorize(self, tool_name, user_id):
        return SimpleNamespace(status="completed", url=None)

    def execute(self, tool_name, input, user_id):
        self.c.executed.append((tool_name, user_id))
        if tool_name in READ_TOOLS:
            return SimpleNamespace(id="read-req-1",
                                   output=SimpleNamespace(value={"emails": [{"id": "msg-1"}]},
                                                          error=None))
        return SimpleNamespace(output=SimpleNamespace(value={"id": "msg-1"}, error=None))


class FakeArcade:
    """Recording stand-in for arcadepy.Arcade; captures the api_key it was built with so
    the test can assert WHICH token authenticated the call."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.executed = []
        self.tools = FakeTools(self)


def job(intent, **args):
    return Job(intent=intent, args=args, goal_id="g1")


async def main():
    with tempfile.TemporaryDirectory() as d:
        core = ControlCore(data_dir=Path(d))

        # PROOF 1: the production wiring EXISTS (the gap that left the mesh dormant).
        assert core.api_hand._broker is not None, "ControlCore must wire a TokenBroker into ApiHand"
        assert core.token_vault is not None, "ControlCore must expose the per-user TokenVault"
        assert isinstance(core.api_hand._broker, TokenBroker)
        assert core.api_hand.user_id == USER, core.api_hand.user_id

        # the broker reads the SAME vault the core exposes (one mesh, not two)
        core.token_vault.store_token(USER, "gmail", TOKEN_USER, route=ROUTE_API, scopes=["gmail.send"])
        assert core.api_hand._broker.get_token(USER, "gmail").reveal() == TOKEN_USER

        # drive a real (fake-backed) LIVE call through the WIRED production hand
        built = []

        def factory(api_key):
            c = FakeArcade(api_key)
            built.append(c)
            return c

        core.api_hand._client_factory = factory
        core.api_hand.mode = MODE_LIVE

        # PROOF 2: a connected user's call authenticates with THEIR vault token, end to end
        r = await core.api_hand.handle(job("send_email", approved=True,
                                           recipient="t@x.com", subject="hi", body="yo"))
        assert r.status == JobStatus.success and r.proof["id"] == "msg-1", r
        assert core.api_hand.last_auth_path == {"path": "per_user", "app": "gmail",
                                                "broker_consulted": True, "shared_key": False}, \
            core.api_hand.last_auth_path
        assert built and built[0].api_key == TOKEN_USER, "wired hand must use the user's vault token"
        assert built[0].api_key != SHARED_KEY, "must NOT use the shared key for a connected user"

        # PROOF 3: an app the user did NOT connect falls back to the shared key (back-compat).
        core.api_hand._client = FakeArcade(SHARED_KEY)  # the shared-key client for fallback
        cl = core.api_hand._live_client("GoogleCalendar.ListEvents")  # app "googlecalendar" not connected
        assert core.api_hand.last_auth_path == {"path": "shared_key", "app": "googlecalendar",
                                                "broker_consulted": True, "shared_key": True}, \
            core.api_hand.last_auth_path
        assert cl.api_key == SHARED_KEY, "unconnected app must use the shared-key client"

        # PROOF 4: an EXPIRED at-rest token degrades to the shared key, never crashes the
        # call (skeptic edge — reveal() of a stale token must fall back, not raise out).
        import time
        core.token_vault.store_token(USER, "googledocs", TOKEN_USER, route=ROUTE_API,
                                     expires_at=time.time() - 3600)
        cl2 = core.api_hand._live_client("GoogleDocs.GetDocumentById")
        assert core.api_hand.last_auth_path["path"] == "shared_key", core.api_hand.last_auth_path
        assert cl2.api_key == SHARED_KEY, "expired token must fall back to shared key, not crash"

    print("PASS: ControlCore wires the per-person token mesh into ApiHand")
    print("  connected user -> own vault token | unconnected app -> shared-key fallback")


if __name__ == "__main__":
    asyncio.run(main())
