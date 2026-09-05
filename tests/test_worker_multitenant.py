"""The worker must have a hard account boundary, not an owner-shaped prompt."""
from __future__ import annotations

from brain import supervisor as S
from brain import worker as W


class Reply:
    ok = True

    def __init__(self, payload=None):
        self.payload = payload or {"items": []}

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def test_every_history_and_profile_read_is_bound_to_active_owner(monkeypatch):
    reads = []

    def fake_get(url, **kwargs):
        reads.append((url, (kwargs.get("params") or {}).get("filter", "")))
        return Reply()

    monkeypatch.setattr(W, "ACTIVE_OWNER_REF", "owner_alpha")
    monkeypatch.setattr(W.pb, "get", fake_get)
    W.fetch_owner_phone()
    W.fetch_owner_timezone()
    W.browser_reachable()
    W.is_echo_of_her("these are enough words to run the echo history check")
    W.asked_about_recently("renew the permit")
    W.need_already_asked("renew the permit", "need account 1234")
    W.already_raised("renew the permit")
    W.already_said("this is a meaningful earlier message")
    W.raised_and_ignored("renew the parking permit")
    W.link_candidates()

    # Ten collection/history reads use an owner_ref filter. fetch_owner_phone
    # additionally falls back to the exact owners/<account-id> record only
    # when no profile row exists; that URL is itself account-scoped.
    filtered = [filt for url, filt in reads if "/owners/records/" not in url]
    exact_owner = [url for url, _ in reads if "/owners/records/" in url]
    assert len(filtered) == 10
    assert all('owner_ref="owner_alpha"' in filt for filt in filtered), reads
    assert exact_owner == [
        f"{W.PB}/api/collections/owners/records/owner_alpha"
    ]


def test_an_existing_profile_with_an_empty_phone_is_authoritative(monkeypatch):
    reads = []

    def fake_get(url, **kwargs):
        reads.append(url)
        if "/owner_profile/records" in url:
            return Reply({"items": [{"phone": ""}]})
        return Reply({"phone": "+16045550101"})

    monkeypatch.setattr(W.pb, "get", fake_get)
    assert W.fetch_owner_phone("owner_alpha") == ""
    assert not any("/owners/records/" in url for url in reads), (
        "an explicit profile clear must not resurrect the sign-up number")


def test_a_missing_profile_uses_the_account_seed_and_a_failed_read_is_unknown(
        monkeypatch):
    class Refused(Reply):
        ok = False

    def seeded(url, **kwargs):
        if "/owner_profile/records" in url:
            return Reply({"items": []})
        return Reply({"phone": "+16045550101"})

    monkeypatch.setattr(W.pb, "get", seeded)
    assert W.fetch_owner_phone("owner_alpha") == "+16045550101"

    monkeypatch.setattr(W.pb, "get", lambda *args, **kwargs: Refused())
    assert W.fetch_owner_phone("owner_alpha") is None


def test_brain_output_is_scoped_by_owner_ref_and_never_sends_the_owner_column(
        monkeypatch):
    """Audit F04. This test used to assert the opposite — that the brain
    stamps `owner` as well as `owner_ref` — and that assertion is what kept
    a 400 in production invisible.

    events has no `owner` column on this backend (the Worker's column map,
    and `pragma_table_info('events')` on live D1), so the Worker answered
    400 unknown_field before the INSERT and EVERY row the brain tried to
    write since the cutover was rejected: no reply in the feed, and no text,
    because the SMS fence is only won on a 2xx from this call. Scope is
    carried by owner_ref alone.
    """
    sent = {}
    monkeypatch.setattr(W, "ACTIVE_OWNER_REF", "owner_alpha")
    monkeypatch.setattr(W, "ACTIVE_OWNER_ID", "legacy-alpha")
    def fake_post(_url, **kwargs):
        sent.update(kwargs)
        return Reply()
    monkeypatch.setattr(W.pb, "post", fake_post)
    W.post_event("anticipy_says", "Done", decision="done", goal="renew permit")
    assert sent["json"]["owner_ref"] == "owner_alpha"
    assert "owner" not in sent["json"], (
        "events has no `owner` column: sending one is a 400 and the row is lost")


def test_new_accounts_get_distinct_memory_and_clock_files(tmp_path):
    base = {
        "ANTICIPY_STATE_ROOT": str(tmp_path / "owners"),
        "ANTICIPY_OWNER_ID": "founder-device",
        "ANTICIPY_MEMORY_DB": "/data/memory.db",
        "ANTICIPY_CLOCK_STATE": "/data/clock_state.json",
    }
    a = S.child_environment({"id": "owner_alpha", "legacy_uuid": "device-a"}, base)
    b = S.child_environment({"id": "owner_bravo", "legacy_uuid": "device-b"}, base)
    assert a["ANTICIPY_MEMORY_DB"] != b["ANTICIPY_MEMORY_DB"]
    assert a["ANTICIPY_CLOCK_STATE"] != b["ANTICIPY_CLOCK_STATE"]
    assert "owner_alpha" in a["ANTICIPY_MEMORY_DB"]
    assert "owner_bravo" in b["ANTICIPY_MEMORY_DB"]


def test_founder_memory_is_preserved_but_never_shared(tmp_path):
    base = {
        "ANTICIPY_STATE_ROOT": str(tmp_path / "owners"),
        "ANTICIPY_OWNER_ID": "founder-device",
        "ANTICIPY_MEMORY_DB": "/data/memory.db",
        "ANTICIPY_CLOCK_STATE": "/data/clock_state.json",
    }
    founder = S.child_environment(
        {"id": "owner_founder", "legacy_uuid": "founder-device"}, base)
    customer = S.child_environment(
        {"id": "owner_customer", "legacy_uuid": "customer-device"}, base)
    assert founder["ANTICIPY_MEMORY_DB"] == "/data/memory.db"
    assert founder["ANTICIPY_CLOCK_STATE"] == "/data/clock_state.json"
    assert customer["ANTICIPY_MEMORY_DB"] != founder["ANTICIPY_MEMORY_DB"]
    assert customer["ANTICIPY_CLOCK_STATE"] != founder["ANTICIPY_CLOCK_STATE"]


def test_discovery_accepts_only_safe_ids_and_returns_no_account_data(monkeypatch):
    pages = [
        Reply({"items": [
            {"id": "owner_alpha", "legacy_uuid": "device-a", "email": "must-not-flow"},
            {"id": "../../escape", "legacy_uuid": "bad"},
        ], "totalPages": 2}),
        Reply({"items": [
            {"id": "owner_bravo", "legacy_uuid": "device-b"},
        ], "totalPages": 2}),
    ]
    monkeypatch.setattr(S.pb, "get", lambda *_a, **_k: pages.pop(0))
    found = S.discover_owners()
    assert found == [
        {"id": "owner_alpha", "legacy_uuid": "device-a"},
        {"id": "owner_bravo", "legacy_uuid": "device-b"},
    ]
    assert all("email" not in owner for owner in found)
