#!/usr/bin/env python3
"""Small App Store Connect release helpers with no third-party dependency.

GitHub's macOS runner owns an ephemeral private key for every development
certificate Xcode creates through the API. When that runner disappears the
certificate remains but its private key does not, so enough successful uploads
eventually fill Apple's development-certificate pool. This script removes only
the oldest exact ``DEVELOPMENT / Created via API`` record when the pool is full.
Named development and every distribution certificate are outside its reach.

It also chooses the next build number from App Store Connect's live authority,
instead of assuming the number committed in git is still Apple's latest.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


API = "https://api.appstoreconnect.apple.com"
DEVELOPMENT_CERTIFICATE_LIMIT = 13
CI_CERTIFICATE_NAME = "Created via API"


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _der_length(data: bytes, index: int) -> tuple[int, int]:
    first = data[index]
    if first < 0x80:
        return first, index + 1
    count = first & 0x7F
    if count == 0 or count > 4:
        raise ValueError("unsupported DER length")
    start = index + 1
    return int.from_bytes(data[start:start + count], "big"), start + count


def der_signature_to_raw(signature: bytes) -> bytes:
    """Convert OpenSSL's ASN.1 ECDSA signature to JWT's 32-byte r + s."""
    if not signature or signature[0] != 0x30:
        raise ValueError("ECDSA signature is not a DER sequence")
    sequence_length, index = _der_length(signature, 1)
    if index + sequence_length != len(signature):
        raise ValueError("malformed DER sequence length")

    values = []
    for _ in range(2):
        if index >= len(signature) or signature[index] != 0x02:
            raise ValueError("ECDSA signature is missing an integer")
        length, index = _der_length(signature, index + 1)
        value = signature[index:index + length]
        index += length
        value = value.lstrip(b"\0")
        if len(value) > 32:
            raise ValueError("ECDSA integer is wider than P-256")
        values.append(value.rjust(32, b"\0"))
    if index != len(signature):
        raise ValueError("trailing bytes in ECDSA signature")
    return b"".join(values)


@dataclass(frozen=True)
class Credentials:
    key_id: str
    issuer_id: str
    private_key: Path

    @classmethod
    def environment(cls) -> "Credentials":
        required = {
            "ASC_KEY_ID": os.environ.get("ASC_KEY_ID", ""),
            "ASC_ISSUER_ID": os.environ.get("ASC_ISSUER_ID", ""),
            "ASC_KEY_PATH": os.environ.get("ASC_KEY_PATH", ""),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise SystemExit("missing " + ", ".join(missing))
        path = Path(required["ASC_KEY_PATH"])
        if not path.is_file():
            raise SystemExit(f"ASC_KEY_PATH does not exist: {path}")
        return cls(required["ASC_KEY_ID"], required["ASC_ISSUER_ID"], path)

    def token(self) -> str:
        now = int(time.time())
        header = _b64url(json.dumps(
            {"alg": "ES256", "kid": self.key_id, "typ": "JWT"},
            separators=(",", ":")).encode())
        payload = _b64url(json.dumps(
            {"iss": self.issuer_id, "iat": now - 20,
             "exp": now + 600, "aud": "appstoreconnect-v1"},
            separators=(",", ":")).encode())
        signing_input = header + b"." + payload
        signed = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(self.private_key)],
            input=signing_input, capture_output=True, check=True).stdout
        return (signing_input + b"." + _b64url(
            der_signature_to_raw(signed))).decode()


class Client:
    def __init__(self, credentials: Credentials):
        self.credentials = credentials

    def request(self, method: str, path: str,
                params: dict[str, str | int] | None = None) -> Any:
        url = API + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url, method=method,
            headers={"Authorization": "Bearer " + self.credentials.token()})
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status == 204:
                return None
            return json.load(response)


def next_build_number(live_versions: list[str], source: int) -> int:
    numeric = [int(version) for version in live_versions if version.isdigit()]
    return max([source, *numeric]) + 1


def select_certificate_to_revoke(certificates: list[dict[str, Any]],
                                 limit: int = DEVELOPMENT_CERTIFICATE_LIMIT
                                 ) -> dict[str, Any] | None:
    development = [item for item in certificates
                   if (item.get("attributes") or {}).get("certificateType")
                   == "DEVELOPMENT"]
    if len(development) < limit:
        return None
    disposable = [item for item in development
                  if (item.get("attributes") or {}).get("displayName")
                  == CI_CERTIFICATE_NAME]
    if not disposable:
        raise RuntimeError(
            "development certificate pool is full, but none are exact "
            f"{CI_CERTIFICATE_NAME!r} CI records; refusing to revoke a named key")
    return min(disposable,
               key=lambda item: (item.get("attributes") or {})
               .get("expirationDate", ""))


def live_next_build(client: Client, bundle_id: str,
                    marketing_version: str, source: int) -> int:
    apps = client.request("GET", "/v1/apps", {
        "filter[bundleId]": bundle_id, "limit": 1})["data"]
    if len(apps) != 1:
        raise RuntimeError(f"expected one app for {bundle_id}, found {len(apps)}")
    releases = client.request("GET", "/v1/preReleaseVersions", {
        "filter[app]": apps[0]["id"],
        "filter[version]": marketing_version,
        "limit": 1,
    })["data"]
    if not releases:
        return source + 1
    builds = client.request("GET", "/v1/builds", {
        "filter[preReleaseVersion]": releases[0]["id"], "limit": 200})["data"]
    return next_build_number(
        [(item.get("attributes") or {}).get("version", "") for item in builds],
        source)


def free_signing_slot(client: Client, dry_run: bool) -> None:
    certificates = client.request(
        "GET", "/v1/certificates", {"limit": 200})["data"]
    target = select_certificate_to_revoke(certificates)
    if target is None:
        print("App Store Connect development-certificate slot is already free")
        return
    attributes = target.get("attributes") or {}
    if dry_run:
        verb = "Would revoke"
    else:
        client.request("DELETE", "/v1/certificates/" + target["id"])
        verb = "Revoked"
    print(f"{verb} one orphaned CI development certificate "
          f"(expires {attributes.get('expirationDate', 'unknown')}); "
          "named and distribution certificates were not eligible")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    number = sub.add_parser("next-build")
    number.add_argument("--bundle", required=True)
    number.add_argument("--marketing", required=True)
    number.add_argument("--source", required=True, type=int)
    slot = sub.add_parser("free-signing-slot")
    slot.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = Client(Credentials.environment())
    if args.command == "next-build":
        print(live_next_build(
            client, args.bundle, args.marketing, args.source))
    else:
        free_signing_slot(client, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
