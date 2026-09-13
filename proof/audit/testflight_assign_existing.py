"""Assign one new Anticipy build to its already-authorized tester audience.

Default: read-only dry run. Explicit ASSIGN_EXISTING permits exactly one POST
to /v1/builds/{id}/relationships/individualTesters, containing only missing
IDs from the app's complete existing tester inventory. No invitations, groups,
public links, roles, review/notification settings, or old builds are changed.

Apple's canonical contract (verified 2026-09-13):
https://developer.apple.com/documentation/appstoreconnectapi/post-v1-builds-_id_-relationships-individualtesters
https://developer.apple.com/documentation/appstoreconnectapi/buildindividualtesterslinkagesrequest/data-data.dictionary
Body: {"data": [{"type": "betaTesters", "id": "<existing tester id>"}]}; 204.

The existing strict paginated inventory is the read authority. Two matching
observations precede a write, followed by fresh readback. This detects observed
drift, NOT an atomic lock on Apple's audience. An uncertain write is never
retried. Exit 0 means a valid dry run or verified coverage, not acceptance,
installation, notification delivery, or an end-to-end product test. Exit 2
means refused/unproven. Output contains only fixed codes, counts and booleans.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import math
import time
import urllib.request
from urllib.parse import urlsplit

from proof.audit import testflight_audience as audience


MAX_OBSERVATION_SECONDS = 120
MAX_ASSIGNMENTS = 200  # One bounded request; never a partly completed batch loop.
PROJECT_BUNDLE = "ai.anticipy.app"
MIN_RELEASE_BUILD = 176  # The prior 175 audience is evidence, never a repair target.


class Refused(Exception):
    """Fixed program-owned reason codes only."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise Refused("metadata_redirect_refused")


@contextmanager
def no_redirects():
    # The shared ASC Client calls urllib.request.urlopen. Scope its opener to
    # this CLI operation; preserve the surrounding process when called by tests.
    previous = urllib.request._opener
    urllib.request.install_opener(urllib.request.build_opener(NoRedirect()))
    try:
        yield
    finally:
        urllib.request._opener = previous


class ObservedReads:
    """Retain IDs/authority in memory while inventory's ReadOnly validates pages."""
    def __init__(self, client):
        self.client = client
        self.records = {}

    def request(self, method, path, params=None, body=None):
        require(method == "GET" and body is None, "read_only_violation")
        reply = self.client.request("GET", path, params)
        if isinstance(reply, dict) and isinstance(reply.get("data"), list):
            self.records.setdefault(urlsplit(path).path, []).extend(reply["data"])
        return reply


def snapshot(client, bundle, build_number):
    observed = ObservedReads(client)
    report = audience.inventory(observed, bundle=bundle, build_number=build_number)
    require(report["inventory_complete"] is True and report["app_tester_count"] > 0,
            "empty_or_incomplete_audience")
    require(report["build_processing_state"] == "VALID" and report["build_expired"] is False
            and report["internal_build_state"] == "IN_BETA_TESTING"
            and report["external_build_state"] == "IN_BETA_TESTING", "build_not_ready")
    selected = audience.only(observed.records["/v1/builds"])
    # A writer needs affirmative external eligibility; absent/future values
    # must not inherit permission merely because they are not INTERNAL_ONLY.
    require(selected["attributes"].get("buildAudienceType") == "APP_STORE_ELIGIBLE", "build_not_ready")
    testers = observed.records["/v1/betaTesters"]
    require(all(t["attributes"].get("state") in {"INVITED", "ACCEPTED", "INSTALLED"}
                for t in testers), "existing_invitation_required")
    # Email is a private identity consistency check, never a lookup or output.
    identities = tuple(sorted((t["id"], t["attributes"].get("state"), t["attributes"].get("email"))
                              for t in testers))
    tester_ids = frozenset(t["id"] for t in testers)
    missing = frozenset(t["id"] for t in report["uncovered_testers"])
    direct = frozenset(t["id"] for t in observed.records[f"/v1/builds/{report['build_id']}/individualTesters"])
    require(len(tester_ids) == report["app_tester_count"] and missing <= tester_ids
            and direct <= tester_ids, "audience_inconsistent")
    groups = []
    linked = {g["id"] for g in report["groups"] if g["linked_to_build"]}
    for group in observed.records[f"/v1/apps/{report['app_id']}/betaGroups"]:
        gid = group["id"]
        members = tuple(sorted(t["id"] for t in observed.records[f"/v1/betaGroups/{gid}/betaTesters"]))
        groups.append((gid, group["attributes"], members, gid in linked))
    target = (report["bundle"], report["app_id"], report["build_number"], report["build_id"])
    return {"report": report, "target": target, "identities": identities,
            "groups": sorted(groups, key=lambda g: g[0]), "missing": missing, "direct": direct}


def same_authority(before, after):
    require(all(before[key] == after[key] for key in ("target", "identities", "groups")),
            "audience_changed")


def summary(observation, *, mode, assigned=0, attempted=False):
    report = observation["report"]
    return {"result": mode, "write_attempted": attempted,
            "existing_tester_count": report["app_tester_count"],
            "missing_tester_count": len(observation["missing"]),
            "assigned_tester_count": assigned,
            "all_existing_testers_covered": report["all_existing_testers_covered"],
            "all_existing_testers_ready": report["all_existing_testers_ready"],
            "pending_invitation_count": report["tester_state_counts"].get("INVITED", 0),
            "not_ready_tester_count": len(report["not_ready_testers"]),
            "installation_verified": False, "notification_delivery_verified": False,
            "snapshot_not_a_lock": True}


def refused(reason, attempted=False):
    return {"result": "refused", "reason": reason, "write_attempted": attempted,
            "assigned_tester_count": None if attempted else 0,
            "all_existing_testers_covered": None, "all_existing_testers_ready": False,
            "installation_verified": False, "notification_delivery_verified": False}


def assign_existing(client, *, bundle, build_number, confirm="", clock=time.monotonic):
    attempted = False
    try:
        require(type(confirm) is str and confirm in ("", "ASSIGN_EXISTING"), "invalid_confirmation")
        require(bundle == PROJECT_BUNDLE and isinstance(build_number, str)
                and build_number.isascii() and build_number.isdigit()
                and not build_number.startswith("0") and len(build_number) <= 9,
                "invalid_target")
        require(int(build_number) >= MIN_RELEASE_BUILD, "protected_build")
        started = clock()
        def fresh():
            age = clock() - started
            require(type(age) in (int, float) and math.isfinite(age)
                    and 0 <= age <= MAX_OBSERVATION_SECONDS, "observation_stale")
        initial = snapshot(client, bundle, build_number)
        fresh()
        if not confirm:
            return summary(initial, mode="dry_run")
        before = snapshot(client, bundle, build_number)
        fresh()
        same_authority(initial, before)
        require(initial["direct"] == before["direct"] and initial["missing"] == before["missing"],
                "audience_changed")
        if not before["missing"]:
            return summary(before, mode="covered")
        require(len(before["missing"]) <= MAX_ASSIGNMENTS, "assignment_batch_too_large")
        payload = {"data": [{"type": "betaTesters", "id": identifier}
                            for identifier in sorted(before["missing"])]}
        attempted = True
        try:
            acknowledgement = client.request("POST",
                f"/v1/builds/{before['report']['build_id']}/relationships/individualTesters", body=payload)
            require(acknowledgement is None, "write_outcome_unproven")
        except Exception:
            raise Refused("write_outcome_unproven") from None
        after = snapshot(client, bundle, build_number)
        fresh()
        same_authority(before, after)
        require(after["direct"] == before["direct"] | before["missing"]
                and not after["missing"] and after["report"]["all_existing_testers_covered"] is True,
                "assignment_not_observed")
        return summary(after, mode="covered", assigned=len(before["missing"]), attempted=True)
    except Refused as error:
        return refused(str(error), attempted)
    except audience.InventoryError:
        return refused("inventory_unproven", attempted)
    except Exception:
        return refused("operation_unproven", attempted)


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        raise Refused("invalid_arguments")


def main(argv=None, *, client_factory=audience.existing_client):
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("--bundle", required=True)
        parser.add_argument("--build", required=True)
        parser.add_argument("--confirm", default="")
        args = parser.parse_args(argv)
        with no_redirects():
            try:
                client = client_factory()
            except (Exception, SystemExit):
                raise Refused("credentials_unavailable") from None
            result = assign_existing(client, bundle=args.bundle, build_number=args.build, confirm=args.confirm)
    except Refused as error:
        result = refused(str(error))
    print(json.dumps(result, sort_keys=True), flush=True)
    return 2 if result["result"] == "refused" else 0


if __name__ == "__main__":
    raise SystemExit(main())
