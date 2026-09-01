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
    assert asc.next_build_number(["112", "113", "114"], source=113) == 115
    assert asc.next_build_number(["112"], source=114) == 115


def test_a_free_certificate_pool_deletes_nothing():
    rows = [_certificate("DEVELOPMENT", "Created via API", str(i), str(i))
            for i in range(11)]
    assert asc.select_certificate_to_revoke(rows) is None


def test_twelve_certificates_is_already_full_for_cloud_signing():
    rows = [_certificate("DEVELOPMENT", "Created via API", str(i), str(i))
            for i in range(12)]
    assert asc.select_certificate_to_revoke(rows)["id"] == "0"


def test_only_the_oldest_exact_ci_development_certificate_is_eligible():
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
    assert asc.select_certificate_to_revoke(rows)["id"] == "ci-1"


def test_a_full_named_pool_fails_instead_of_revoking_a_developer():
    rows = [_certificate("DEVELOPMENT", f"Developer {i}", str(i), str(i))
            for i in range(13)]
    try:
        asc.select_certificate_to_revoke(rows)
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
