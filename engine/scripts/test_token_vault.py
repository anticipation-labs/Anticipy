"""Per-person API mesh foundation test: the encrypted token vault + broker + registry.

Proves the slice's contract with NO real OAuth and NO network:
  - store a fake OAuth token -> the plaintext is NOT present in the on-disk bytes
  - the non-LLM broker fetches + decrypts -> the same usable token comes back
  - a second user's token is fully isolated (no cross-read; wrong-owner decrypt fails)
  - tamper / wrong-key detection (encrypt-then-MAC), empty-token + missing-key refusal
  - the connector registry dispatches on the stored route (api / browser / voice_text)
  - SecretToken never leaks the plaintext via str/repr/format/json/pickle

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_token_vault.py
"""
import json
import os
import pickle
import tempfile
from pathlib import Path

from anticipy_engine.hands.token_vault import (
    ConnectorRegistry,
    ROUTE_API,
    ROUTE_BROWSER,
    ROUTE_VOICE_TEXT,
    SecretToken,
    TokenBroker,
    TokenNotFound,
    TokenVault,
    VaultError,
)

# a realistic-looking (but fake) OAuth access token — never a real credential
FAKE_TOKEN_A = "ya29.A0AfH-FAKE-alice-3f9c2b1e7d6a5849c0b1d2e3f4a5b6c7d8e9f0"
FAKE_TOKEN_B = "ya29.A0AfH-FAKE-bob-9988776655443322110aabbccddeeff00112233"


def main():
    os.environ["ANTICIPY_VAULT_KEY"] = "test-master-key-do-not-use-in-prod"
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        vault = TokenVault(data_dir=base)
        broker = TokenBroker(vault)

        # --- store a fake OAuth token for user A (their own Gmail) ---
        vault.store_token("alice@x.com", "gmail", FAKE_TOKEN_A, route=ROUTE_API,
                          scopes=["gmail.send", "gmail.readonly"])

        # --- PROOF 1: encrypted at rest — plaintext is NOT in the file bytes ---
        files = list((base / "vault").glob("*.json"))
        assert len(files) == 1, f"expected one per-user file, got {files}"
        raw = files[0].read_bytes()
        assert FAKE_TOKEN_A.encode() not in raw, "PLAINTEXT TOKEN LEAKED TO DISK"
        # the value on disk is a sealed record, not the token
        on_disk = json.loads(raw)
        assert "gmail" in on_disk and "sealed" in on_disk["gmail"], on_disk
        sealed = on_disk["gmail"]["sealed"]
        assert set(sealed) >= {"salt", "nonce", "ct", "tag"}, sealed
        assert FAKE_TOKEN_A not in json.dumps(on_disk), "token text found in record"
        # non-secret metadata IS readable (route/scopes) so the registry can route
        assert on_disk["gmail"]["route"] == ROUTE_API
        assert on_disk["gmail"]["scopes"] == ["gmail.readonly", "gmail.send"]

        # --- PROOF 2: the non-LLM broker fetches + decrypts -> usable token ---
        tok = broker.get_token("alice@x.com", "gmail")
        assert isinstance(tok, SecretToken)
        assert tok.reveal() == FAKE_TOKEN_A, "round-trip decrypt mismatch"
        assert tok.app == "gmail" and tok.user_id == "alice@x.com"

        # --- PROOF 3: a second user's token is isolated ---
        vault.store_token("bob@x.com", "gmail", FAKE_TOKEN_B, route=ROUTE_API)
        # two distinct files; bob's bytes never contain alice's token and vice versa
        assert len(list((base / "vault").glob("*.json"))) == 2
        a_bytes = vault._path("alice@x.com").read_bytes()
        b_bytes = vault._path("bob@x.com").read_bytes()
        assert FAKE_TOKEN_B.encode() not in a_bytes and FAKE_TOKEN_A.encode() not in b_bytes
        # broker keeps them separate
        assert broker.get_token("alice@x.com", "gmail").reveal() == FAKE_TOKEN_A
        assert broker.get_token("bob@x.com", "gmail").reveal() == FAKE_TOKEN_B
        # alice has no claim on an app she never connected
        try:
            broker.get_token("alice@x.com", "salesforce")
            raise AssertionError("expected TokenNotFound for an unconnected app")
        except TokenNotFound:
            pass

        # --- isolation is cryptographic, not just by filename: a record copied into
        #     another user's file fails the owner-bound integrity check on decrypt ---
        alice_blob = json.loads(vault._path("alice@x.com").read_text())
        bob_blob = json.loads(vault._path("bob@x.com").read_text())
        bob_blob["gmail_stolen"] = alice_blob["gmail"]  # try to graft alice's sealed token
        vault._path("bob@x.com").write_text(json.dumps(bob_blob))
        try:
            broker.get_token("bob@x.com", "gmail_stolen")
            raise AssertionError("a relocated token must fail the owner-bound MAC")
        except VaultError:
            pass

        # --- tamper detection: flip a ciphertext byte -> integrity check fails ---
        with tempfile.TemporaryDirectory() as d2:
            v2 = TokenVault(data_dir=Path(d2))
            v2.store_token("carol@x.com", "crm", FAKE_TOKEN_A, route=ROUTE_BROWSER)
            p = v2._path("carol@x.com")
            blob = json.loads(p.read_text())
            ct = blob["crm"]["sealed"]["ct"]
            blob["crm"]["sealed"]["ct"] = ("A" if ct[0] != "A" else "B") + ct[1:]
            p.write_text(json.dumps(blob))
            try:
                TokenBroker(v2).get_token("carol@x.com", "crm")
                raise AssertionError("tampered ciphertext must fail")
            except VaultError:
                pass

        # --- wrong master key cannot decrypt a record sealed under another key ---
        os.environ["ANTICIPY_VAULT_KEY"] = "a-completely-different-master-key"
        try:
            TokenBroker(vault).get_token("alice@x.com", "gmail")
            raise AssertionError("wrong master key must fail integrity check")
        except VaultError:
            pass
        os.environ["ANTICIPY_VAULT_KEY"] = "test-master-key-do-not-use-in-prod"

        # --- the connector registry dispatches on the STORED route ---
        # alice's gmail -> api; carol-style browser app; a voice_text app
        vault.store_token("alice@x.com", "niche_crm", FAKE_TOKEN_A, route=ROUTE_BROWSER)
        vault.store_token("alice@x.com", "twilio_line", FAKE_TOKEN_A, route=ROUTE_VOICE_TEXT)
        reg = ConnectorRegistry(vault)
        api_handler, browser_handler, voice_handler = object(), object(), object()
        reg.register_route(ROUTE_API, api_handler)
        reg.register_route(ROUTE_BROWSER, browser_handler)
        reg.register_route(ROUTE_VOICE_TEXT, voice_handler)

        d_gmail = reg.resolve("alice@x.com", "gmail")
        assert d_gmail["route"] == ROUTE_API and d_gmail["handler"] is api_handler
        assert d_gmail["token"].reveal() == FAKE_TOKEN_A
        assert d_gmail["metadata"]["scopes"] == ["gmail.readonly", "gmail.send"]

        d_crm = reg.resolve("alice@x.com", "niche_crm")
        assert d_crm["route"] == ROUTE_BROWSER and d_crm["handler"] is browser_handler

        d_voice = reg.resolve("alice@x.com", "twilio_line")
        assert d_voice["route"] == ROUTE_VOICE_TEXT and d_voice["handler"] is voice_handler

        # registry never returns a route for an app a user hasn't connected
        try:
            reg.resolve("bob@x.com", "niche_crm")
            raise AssertionError("bob never connected niche_crm")
        except TokenNotFound:
            pass

        # --- SecretToken never leaks the plaintext anywhere it could ---
        s = broker.get_token("alice@x.com", "gmail")
        assert FAKE_TOKEN_A not in str(s)
        assert FAKE_TOKEN_A not in repr(s)
        assert FAKE_TOKEN_A not in f"{s}" and FAKE_TOKEN_A not in format(s)
        assert FAKE_TOKEN_A not in json.dumps(str(s))
        try:
            pickle.dumps(s)
            raise AssertionError("SecretToken must refuse pickling out the plaintext")
        except TypeError:
            pass

        # --- guardrails: empty token refused; missing master key refused loudly ---
        try:
            vault.store_token("alice@x.com", "x", "", route=ROUTE_API)
            raise AssertionError("empty token must be refused")
        except VaultError:
            pass
        saved = os.environ.pop("ANTICIPY_VAULT_KEY", None)
        try:
            try:
                vault.store_token("dave@x.com", "gmail", FAKE_TOKEN_A)
                raise AssertionError("missing master key must raise")
            except VaultError:
                pass
        finally:
            if saved is not None:
                os.environ["ANTICIPY_VAULT_KEY"] = saved

        # --- metadata-only read never exposes the token; revoke works ---
        meta = vault.metadata("alice@x.com", "gmail")
        assert FAKE_TOKEN_A not in json.dumps(meta)
        assert vault.apps("alice@x.com") == ["gmail", "niche_crm", "twilio_line"]
        assert vault.revoke("alice@x.com", "twilio_line") is True
        assert "twilio_line" not in vault.apps("alice@x.com")

    print("PASS: per-person token vault (encrypted-at-rest, broker round-trip, "
          "user isolation, owner-bound MAC, route dispatch, no-leak SecretToken)")
    print(f"  on-disk bytes carry NO plaintext token; 2 users isolated; "
          f"3 routes ({ROUTE_API}/{ROUTE_BROWSER}/{ROUTE_VOICE_TEXT}) dispatch")


if __name__ == "__main__":
    main()
