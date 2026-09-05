import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app/ios/scripts/app_store_connect.py"
SPEC = importlib.util.spec_from_file_location("app_store_connect", MODULE_PATH)
asc = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = asc
SPEC.loader.exec_module(asc)


def _certificate(kind: str, name: str, expires: str, identifier: str):
    return {
        "id": identifier,
        "attributes": {
            "certificateType": kind,
            "displayName": name,
            "expirationDate": expires,
        },
    }


def test_next_build_uses_apple_not_the_stale_repo_number():
    # The tree says 113 while Apple already holds 114: the upload cannot be
    # 113 or 114, so it is one past Apple's highest.
    assert asc.next_build_number(["112", "113", "114"], source=113) == 115


def test_a_source_above_every_live_build_uploads_as_itself():
    # Audit F22 (2026-09-05): every CI upload had been labelled one or two
    # above the tree that produced it, because the rule added one whether or
    # not Apple held the number. The phone stamps device_id
    # iphone-b<CFBundleVersion> and the ledgers name the committed number, so
    # 124 in the tree against Apple's 123 must upload as 124, not 125.
    assert asc.next_build_number(["122", "123"], source=124) == 124
    assert asc.next_build_number(["112"], source=114) == 114
    assert asc.next_build_number([], source=124) == 124


def test_only_a_collision_moves_the_number_and_only_to_one_past_apple():
    assert asc.next_build_number(["124"], source=124) == 125
    assert asc.next_build_number(["124", "125"], source=124) == 126
    # A tree BEHIND Apple (a stale branch) still cannot reuse a live number.
    assert asc.next_build_number(["124", "125"], source=110) == 126
    # Non-numeric versions (Apple lets a build be "1.0.3") do not count.
    assert asc.next_build_number(["1.0.3", "124"], source=124) == 125


class _Client:
    """Just enough of app_store_connect.Client to answer the three GETs."""

    def __init__(self, responses):
        self.responses = responses

    def request(self, method, path, params=None):
        return self.responses[path]


def _live(prerelease_versions, builds):
    return _Client({
        "/v1/apps": {"data": [{"id": "app-1"}]},
        "/v1/preReleaseVersions": {"data": prerelease_versions},
        "/v1/builds": {"data": builds},
    })


def test_no_prerelease_version_yet_keeps_the_source_number():
    # live_next_build used to answer source + 1 here too, so even a first
    # upload under a new marketing version could not carry its own number.
    client = _live([], [])
    assert asc.live_next_build(client, "ai.anticipy.app", "1.1.0",
                               source=124) == 124


def test_live_builds_decide_the_collision():
    client = _live([{"id": "rel-1"}],
                   [_build("123", "VALID"), _build("124", "VALID")])
    assert asc.live_next_build(client, "ai.anticipy.app", "1.1.0",
                               source=124) == 125
    client = _live([{"id": "rel-1"}], [_build("123", "VALID")])
    assert asc.live_next_build(client, "ai.anticipy.app", "1.1.0",
                               source=124) == 124


def _build(version: str, state: str):
    return {"attributes": {"version": version, "processingState": state}}


def test_upload_is_not_green_until_apple_marks_the_exact_build_valid():
    assert asc.processing_verdict([], "117")[0] == "waiting"
    assert asc.processing_verdict(
        [_build("116", "VALID"), _build("117", "PROCESSING")],
        "117")[0] == "waiting"
    assert asc.processing_verdict(
        [_build("117", "VALID")], "117") == (
            "ready", "build 117 is VALID")


def test_apple_processing_rejection_and_unknown_states_fail_closed():
    assert asc.processing_verdict(
        [_build("117", "INVALID")], "117")[0] == "failed"
    assert asc.processing_verdict(
        [_build("117", "SOMETHING_NEW")], "117")[0] == "failed"


def test_an_empty_certificate_pool_deletes_nothing():
    assert asc.select_certificates_to_revoke([]) == []


def test_every_ci_leftover_but_no_named_or_distribution_key_is_eligible():
    rows = [
        _certificate("DEVELOPMENT", "Created via API",
                     f"2027-08-{day:02d}", f"ci-{day}")
        for day in range(1, 13)
    ]
    rows += [
        _certificate("DEVELOPMENT", "Jose's Mac", "2027-01-01", "jose"),
        _certificate("IOS_DISTRIBUTION", "Omar Ebrahim",
                     "2027-01-01", "distribution"),
    ]
    assert [item["id"] for item in
            asc.select_certificates_to_revoke(rows)] == [
                f"ci-{day}" for day in range(1, 13)
            ]


def test_a_full_named_pool_fails_instead_of_revoking_a_developer():
    rows = [_certificate("DEVELOPMENT", f"Developer {i}", str(i), str(i))
            for i in range(13)]
    try:
        asc.select_certificates_to_revoke(rows)
    except RuntimeError as error:
        assert "refusing to revoke a named key" in str(error)
    else:
        raise AssertionError("a named development certificate was eligible")


def test_der_signature_conversion_pads_and_strips_sign_bytes():
    # Sequence(Integer(1), Integer(0x80 with DER's positive sign byte)).
    der = bytes.fromhex("300702010102020080")
    raw = asc.der_signature_to_raw(der)
    assert len(raw) == 64
    assert raw[:32] == b"\0" * 31 + b"\x01"
    assert raw[32:] == b"\0" * 31 + b"\x80"
