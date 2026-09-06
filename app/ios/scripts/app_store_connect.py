#!/usr/bin/env python3
"""Small App Store Connect release helpers with no third-party dependency.

GitHub's macOS runner owns an ephemeral private key for every development
certificate Xcode creates through the API. When that runner disappears the
certificate remains but its private key does not, so successful uploads fill
Apple's deliberately small development-certificate pool. The serialized iOS
release job cannot reuse any certificate from an earlier runner, so this script
removes its exact ``DEVELOPMENT / Created via API`` leftovers before signing.
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
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


API = "https://api.appstoreconnect.apple.com"
REVOCATION_SETTLE_SECONDS = 20
CI_CERTIFICATE_NAME = "Created via API"
BUILD_PROCESSING_POLL_SECONDS = 20
BUILD_PROCESSING_TIMEOUT_SECONDS = 20 * 60


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
    """The number the upload carries: the tree's own, unless Apple holds it.

    ``source`` is CURRENT_PROJECT_VERSION as committed, and it is the number
    the phone stamps on every row (``device_id`` is ``iphone-b<CFBundleVersion>``)
    and the ledgers name. App Store Connect refuses only a number it already
    holds, so the source is kept whenever it is above every live build, and
    moved to one past the highest live build only on a collision. The rule
    used to add one unconditionally, which labelled every CI upload one or two
    above the tree that produced it (119 uploaded as 121, 121 as 122, then
    121 as 123) so no TestFlight number matched its commit (audit F22,
    2026-09-05).
    """
    numeric = [int(version) for version in live_versions if version.isdigit()]
    return max([source, *(live + 1 for live in numeric)])


def select_certificates_to_revoke(
        certificates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    development = [item for item in certificates
                   if (item.get("attributes") or {}).get("certificateType")
                   == "DEVELOPMENT"]
    disposable = [item for item in development
                  if (item.get("attributes") or {}).get("displayName")
                  == CI_CERTIFICATE_NAME]
    # Apple documents two development certificates per individual. If both
    # visible records are named, this automation has no safe target and must
    # stop instead of taking somebody's working Mac identity.
    if len(development) >= 2 and not disposable:
        raise RuntimeError(
            "development certificate pool is full, but none are exact "
            f"{CI_CERTIFICATE_NAME!r} CI records; refusing to revoke a named key")
    return sorted(disposable,
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
        # Nothing live under this marketing version: nothing to collide with.
        return source
    builds = client.request("GET", "/v1/builds", {
        "filter[preReleaseVersion]": releases[0]["id"], "limit": 200})["data"]
    return next_build_number(
        [(item.get("attributes") or {}).get("version", "") for item in builds],
        source)


def who_can_install(client: Client, bundle_id: str, version: str) -> int:
    """Which tester groups can actually install one build — READ ONLY.

    A build can be VALID and still reach nobody. "VALID" is Apple's verdict on
    the BYTES: processing finished and the archive is installable. Whether a
    human sees it in TestFlight is a separate fact — the build has to be
    attached to a beta group, and an external group additionally needs a review
    that VALID says nothing about. On 2026-09-06 the owner's phone was on build
    88 while 153 was VALID, which is exactly the shape this answers.

    It asks and prints. It attaches nothing: assigning a build to testers
    distributes software to people, which is the owner's decision to make in
    App Store Connect, not a side effect of a status query.
    """
    apps = client.request("GET", "/v1/apps", {
        "filter[bundleId]": bundle_id, "limit": 1})["data"]
    if len(apps) != 1:
        raise RuntimeError(f"expected one app for {bundle_id}, found {len(apps)}")
    app_id = apps[0]["id"]

    builds = client.request("GET", "/v1/builds", {
        "filter[app]": app_id, "filter[version]": version, "limit": 5})["data"]
    if not builds:
        print(f"build {version} does not exist under {bundle_id}")
        return 1
    build = builds[0]
    attrs = build.get("attributes") or {}
    state = attrs.get("processingState", "?")
    expired = attrs.get("expired")
    print(f"build {version}: processingState={state} expired={expired} "
          f"uploaded={attrs.get('uploadedDate', '?')}")

    # EVERY QUERY BELOW IS ALLOWED TO FAIL SEPARATELY. The App Store Connect
    # key's role decides which of these routes it may read, and the first
    # attempt at this command died on a 403 from the beta-groups route after
    # having already learned the build was VALID -- printing a traceback
    # instead of the half of the answer it held. A status query that stops at
    # the first refusal tells the reader nothing, and "I was not allowed to
    # ask" is a different fact from "nobody can install it".
    def ask(path: str, params: dict[str, str | int]) -> tuple[Any, str]:
        try:
            return client.request("GET", path, params)["data"], ""
        except urllib.error.HTTPError as error:
            if error.code == 403:
                return None, ("403 Forbidden -- this API key's role may not "
                              "read " + path + ". A key with App Manager can.")
            return None, f"HTTP {error.code} from {path}"
        except Exception as error:            # noqa: BLE001 - report, never raise
            return None, f"{type(error).__name__} from {path}: {error}"

    groups, why = ask(f"/v1/builds/{build['id']}/betaGroups", {"limit": 50})
    if groups is None:
        # Second route to the same fact. It filters groups by build rather than
        # walking the build's relationship, and the role that refuses one
        # sometimes allows the other.
        groups, why2 = ask("/v1/betaGroups",
                           {"filter[builds]": build["id"], "limit": 50})
        if groups is None:
            print("could not read the tester groups: " + why)
            print("  and the other way round: " + why2)
    if groups is None:
        pass
    elif not groups:
        # The whole point of the command. Nobody is told anything by silence.
        print("NOBODY. This build is attached to no tester group, so it does "
              "not appear in anyone's TestFlight.")
    else:
        print(f"{len(groups)} group(s) can install it:")
        for group in groups:
            g = group.get("attributes") or {}
            kind = "internal" if g.get("isInternalGroup") else "external"
            print(f"  - {g.get('name', '?')} ({kind}), "
                  f"public link {'on' if g.get('publicLinkEnabled') else 'off'}")

    # An external group sees nothing until review clears, and that state does
    # not live on the group.
    review, why = ask("/v1/buildBetaDetails",
                      {"filter[build]": build["id"], "limit": 1})
    if review is None:
        print("could not read the tester states: " + why)
    elif review:
        r = review[0].get("attributes") or {}
        print(f"internal testers: {r.get('internalBuildState', '?')}")
        print(f"external testers: {r.get('externalBuildState', '?')}")

    # For context, so a reader can see whether an OLDER build is the one
    # testers are actually being offered.
    recent, why = ask("/v1/builds",
                      {"filter[app]": app_id, "limit": 8, "sort": "-version"})
    if recent is None:
        print("could not list recent builds: " + why)
        return 0
    print("most recent builds Apple holds:")
    for item in recent:
        a = item.get("attributes") or {}
        print(f"  {a.get('version', '?'):>5}  {a.get('processingState', '?')}"
              f"  expired={a.get('expired')}")
    return 0


def processing_verdict(builds: list[dict[str, Any]],
                       version: str) -> tuple[str, str]:
    """Return a fail-closed verdict for one uploaded build number.

    ``altool`` proves only that Apple received the bytes. App Store Connect
    then processes those bytes asynchronously and can still reject them. A
    green release needs Apple's later ``VALID`` state, not the upload command's
    earlier exit code.
    """
    exact = [item for item in builds
             if str((item.get("attributes") or {}).get("version", ""))
             == str(version)]
    if not exact:
        return "waiting", f"build {version} is not visible yet"

    states = {(item.get("attributes") or {}).get("processingState", "")
              for item in exact}
    if "VALID" in states:
        return "ready", f"build {version} is VALID"
    rejected = sorted(state for state in states
                      if state in {"FAILED", "INVALID"})
    if rejected:
        return "failed", (f"build {version} was rejected during processing: "
                          + ", ".join(rejected))
    if states <= {"PROCESSING", ""}:
        return "waiting", f"build {version} is still processing"
    return "failed", (f"build {version} returned an unknown processing state: "
                      + ", ".join(sorted(states)))


def wait_for_valid_build(client: Client, bundle_id: str, version: str,
                         timeout_seconds: int = BUILD_PROCESSING_TIMEOUT_SECONDS,
                         poll_seconds: int = BUILD_PROCESSING_POLL_SECONDS) -> None:
    apps = client.request("GET", "/v1/apps", {
        "filter[bundleId]": bundle_id, "limit": 1})["data"]
    if len(apps) != 1:
        raise RuntimeError(
            f"expected one app for {bundle_id}, found {len(apps)}")

    deadline = time.monotonic() + timeout_seconds
    while True:
        builds = client.request("GET", "/v1/builds", {
            "filter[app]": apps[0]["id"],
            "filter[version]": version,
            "limit": 10,
        })["data"]
        verdict, message = processing_verdict(builds, version)
        print(message, flush=True)
        if verdict == "ready":
            return
        if verdict == "failed":
            raise RuntimeError(message)
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"build {version} did not become VALID within "
                f"{timeout_seconds} seconds")
        time.sleep(poll_seconds)


def free_signing_slot(client: Client, dry_run: bool) -> None:
    certificates = client.request(
        "GET", "/v1/certificates", {"limit": 200})["data"]
    targets = select_certificates_to_revoke(certificates)
    if not targets:
        print("No orphaned CI development certificates need cleanup")
        return
    if not dry_run:
        for target in targets:
            client.request("DELETE", "/v1/certificates/" + target["id"])
    verb = "Would revoke" if dry_run else "Revoked"
    print(f"{verb} {len(targets)} orphaned CI development certificate(s); "
          "named and distribution certificates were not eligible")
    if not dry_run:
        # The REST listing reflects deletion before Xcode's signing backend
        # does. A run on 2026-09-01 reached archive nine seconds after DELETE
        # and was still told the pool was full, so wait outside that window.
        time.sleep(REVOCATION_SETTLE_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    number = sub.add_parser("next-build")
    number.add_argument("--bundle", required=True)
    number.add_argument("--marketing", required=True)
    number.add_argument("--source", required=True, type=int)
    wait = sub.add_parser("wait-build")
    wait.add_argument("--bundle", required=True)
    wait.add_argument("--build", required=True)
    wait.add_argument("--timeout", type=int,
                      default=BUILD_PROCESSING_TIMEOUT_SECONDS)
    slot = sub.add_parser("free-signing-slot")
    slot.add_argument("--dry-run", action="store_true")
    who = sub.add_parser("who-can-install")
    who.add_argument("--bundle", required=True)
    who.add_argument("--build", required=True)
    args = parser.parse_args()

    client = Client(Credentials.environment())
    if args.command == "next-build":
        print(live_next_build(
            client, args.bundle, args.marketing, args.source))
    elif args.command == "wait-build":
        wait_for_valid_build(client, args.bundle, args.build, args.timeout)
    elif args.command == "who-can-install":
        return who_can_install(client, args.bundle, args.build)
    else:
        free_signing_slot(client, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
