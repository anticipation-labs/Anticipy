"""Per-person API mesh round-trip: the TokenBroker wired into ApiHand.

Proves the slice's contract with NO real OAuth and NO network:
  - an ApiHand with a broker + a seeded user token takes the PER-USER token path
    on a LIVE call (broker consulted; the shared-key path is NOT taken for that user),
    and the client that performs the real handshake is built from THAT user's token.
  - a second user who has NOT connected the app is isolated: they fall back to the
    shared ARCADE_API_KEY path (back-compat), never to the first user's token.
  - no broker at all -> the legacy shared-key path, unchanged (back-compat).
  - MOCK mode is untouched: the broker is never consulted (no live auth there).

The real Arcade client is replaced by a recording fake via ApiHand(client_factory=...)
for the per-user path and by an injected `client` for the shared-key path — no network,
no real token ever leaves the broker's SecretToken except the single .reveal() at the
handshake, which the fake records so the test can assert WHICH key authenticated.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_api_vault.py
"""
import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

from anticipy_engine.core.envelopes import Job, JobStatus
from anticipy_engine.hands.api_hand import ApiHand, MODE_LIVE, MODE_MOCK
from anticipy_engine.hands.token_vault import TokenBroker, TokenVault, ROUTE_API

# realistic-looking but FAKE per-user Arcade/OAuth tokens — never real credentials
TOKEN_ALICE = "arc_FAKE-alice-7c1f9b2e4d6a8c0e3f5a7b9d1c3e5f70"
TOKEN_BOB = "arc_FAKE-bob-1a2b3c4d5e6f70819a2b3c4d5e6f7081"
SHARED_KEY = "arc_FAKE-SHARED-KEY-do-not-use-in-prod-0000"

# the read-back leg for send_email; the same fake serves both write + read execute()
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
            # independent read-back re-observes the just-written id
            return SimpleNamespace(id="read-req-1",
                                   output=SimpleNamespace(value={"emails": [{"id": "msg-1"}]},
                                                          error=None))
        return SimpleNamespace(output=SimpleNamespace(value={"id": "msg-1"}, error=None))


class FakeArcade:
    """A recording stand-in for arcadepy.Arcade. Captures the api_key it was built
    with so the test can assert WHICH token actually authenticated the call."""

    def __init__(self, api_key):
        self.api_key = api_key   # the credential this client authenticates with
        self.executed = []
        self.tools = FakeTools(self)


def job(intent, **args):
    return Job(intent=intent, args=args, goal_id="g1")


async def main():
    os.environ["ANTICIPY_VAULT_KEY"] = "test-master-key-do-not-use-in-prod"
    # so any accidental shared-key fallback is observable (and never a NotFundedError)
    os.environ["ARCADE_API_KEY"] = SHARED_KEY

    built_clients = []  # every per-user client the factory builds, in order

    def recording_factory(api_key):
        c = FakeArcade(api_key)
        built_clients.append(c)
        return c

    with tempfile.TemporaryDirectory() as d:
        vault = TokenVault(data_dir=Path(d))
        broker = TokenBroker(vault)
        # alice connected her own Gmail via the vault; bob did NOT connect gmail.
        vault.store_token("alice@x.com", "gmail", TOKEN_ALICE, route=ROUTE_API,
                          scopes=["gmail.send"])

        # the shared-key client (used only when no per-user token applies)
        shared_client = FakeArcade(SHARED_KEY)

        # ---- PROOF 1: alice's LIVE call takes the PER-USER token path ----
        alice = ApiHand(user_id="alice@x.com", client=shared_client, mode=MODE_LIVE,
                        broker=broker, client_factory=recording_factory)
        r = await alice.handle(job("send_email", approved=True,
                                   recipient="t@x.com", subject="hi", body="yo"))
        assert r.status == JobStatus.success and r.proof["id"] == "msg-1", r
        # the broker was consulted and the shared-key path was NOT taken for alice
        assert alice.last_auth_path == {"path": "per_user", "app": "gmail",
                                        "broker_consulted": True, "shared_key": False}, \
            alice.last_auth_path
        # the client that authenticated was built from ALICE's vault token, not the shared key
        assert len(built_clients) == 1, built_clients
        assert built_clients[0].api_key == TOKEN_ALICE, "per-user client must use alice's token"
        assert built_clients[0].api_key != SHARED_KEY
        # alice's per-user client did the work; the shared client was never touched
        assert built_clients[0].executed, "per-user client should have executed the call"
        assert shared_client.executed == [], "shared-key client must NOT be used for alice"

        # ---- PROOF 2: a SECOND user (bob) is isolated -> shared-key fallback ----
        # bob never connected gmail in the vault; he must NOT get alice's token, and must
        # fall back to the shared-key path (back-compat) — never the per-user path.
        bob_shared = FakeArcade(SHARED_KEY)
        bob = ApiHand(user_id="bob@x.com", client=bob_shared, mode=MODE_LIVE,
                      broker=broker, client_factory=recording_factory)
        r = await bob.handle(job("send_email", approved=True,
                                 recipient="t@x.com", subject="hi", body="yo"))
        assert r.status == JobStatus.success and r.proof["id"] == "msg-1", r
        assert bob.last_auth_path == {"path": "shared_key", "app": "gmail",
                                      "broker_consulted": True, "shared_key": True}, \
            bob.last_auth_path
        # no NEW per-user client was built for bob (the factory was not invoked)
        assert len(built_clients) == 1, "bob must not build a per-user client"
        # bob authenticated with the shared key, never alice's token
        assert bob_shared.executed, "bob should run on the shared-key client"
        assert bob_shared.api_key == SHARED_KEY and bob_shared.api_key != TOKEN_ALICE

        # ---- PROOF 3: NO broker at all -> legacy shared-key path, unchanged ----
        legacy_shared = FakeArcade(SHARED_KEY)
        legacy = ApiHand(user_id="alice@x.com", client=legacy_shared, mode=MODE_LIVE,
                         client_factory=recording_factory)  # broker=None
        r = await legacy.handle(job("send_email", approved=True,
                                    recipient="t@x.com", subject="hi", body="yo"))
        assert r.status == JobStatus.success and r.proof["id"] == "msg-1", r
        assert legacy.last_auth_path == {"path": "shared_key", "app": "gmail",
                                         "broker_consulted": False, "shared_key": True}, \
            legacy.last_auth_path
        assert legacy_shared.executed and len(built_clients) == 1  # still no factory call

        # ---- PROOF 4: MOCK mode never consults the broker (unchanged) ----
        mock = ApiHand(user_id="alice@x.com", mode=MODE_MOCK, broker=broker,
                       client_factory=recording_factory)
        r = await mock.handle(job("send_email", approved=True,
                                  recipient="t@x.com", subject="hi", body="yo"))
        assert r.status == JobStatus.success and r.proof.get("mock") is True, r
        # mock path took no live auth: last_auth_path stays None, no per-user client built
        assert mock.last_auth_path is None, "MOCK must not run the live auth path"
        assert len(built_clients) == 1, "MOCK must not build a per-user client"

    print("PASS: token vault wired into ApiHand (per-person API mesh)")
    print("  alice -> per-user vault token | bob isolated -> shared-key fallback | "
          "no-broker legacy + MOCK unchanged")


if __name__ == "__main__":
    asyncio.run(main())
