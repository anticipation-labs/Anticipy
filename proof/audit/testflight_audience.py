"""Read-only inventory of one build against the app's entire existing audience.

Uses the existing App Store Connect Client only for GETs. It never invites,
attaches, notifies, creates, or edits anything. CI output excludes full tester
emails/names. Exit 0 = complete and API-ready; 1 = complete but needs attention;
2 = incomplete/unproven. API readiness is not proof of device installation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import re
import sys
import urllib.error
from urllib.parse import parse_qsl, urlencode, urlsplit

HOST = "api.appstoreconnect.apple.com"
MAX_PAGES = 100
TESTER_STATES = {"NOT_INVITED", "INVITED", "ACCEPTED", "INSTALLED"}
BUILD_STATES = {
    "PROCESSING", "PROCESSING_EXCEPTION", "MISSING_EXPORT_COMPLIANCE",
    "READY_FOR_BETA_TESTING", "READY_FOR_BETA_SUBMISSION", "WAITING_FOR_BETA_REVIEW",
    "IN_BETA_REVIEW", "BETA_REJECTED", "BETA_APPROVED", "IN_BETA_TESTING",
    "EXPIRED", "NOT_BETA_TESTING",
}


class InventoryError(RuntimeError):
    def __init__(self, category, http_status=None):
        super().__init__(category)
        self.category, self.http_status = category, http_status


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,128}", value):
        raise InventoryError("malformed_resource")
    return value


def record(value, kind):
    if not isinstance(value, dict) or value.get("type") != kind or not isinstance(value.get("attributes"), dict):
        raise InventoryError("malformed_resource")
    identifier(value.get("id"))
    return value


def mask_email(value):
    if not isinstance(value, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+", value):
        return "[unavailable]"
    name, domain = value.split("@")
    return name[:1] + "***@" + domain


def group_label(value):
    if not isinstance(value, str):
        return "[unnamed]"
    # Names are requested metadata; email-looking content remains masked even
    # if someone placed a tester address in a group name.
    return re.sub(r"[^\s@]+@[^\s@]+", lambda m: mask_email(m.group()), " ".join(value.split()))[:160]


def state(value, allowed):
    return value if isinstance(value, str) and value in allowed else "UNKNOWN"


class ReadOnly:
    def __init__(self, client):
        self.client = client

    def request(self, method, path, params=None, body=None):
        if method != "GET" or body is not None:
            raise InventoryError("read_only_violation")
        if not isinstance(path, str) or not path.startswith("/v1/") or path.startswith("//"):
            raise InventoryError("pagination_invalid")
        try:
            return self.client.request("GET", path, params)
        except urllib.error.HTTPError as exc:
            status = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else None
            raise InventoryError("api_forbidden" if status == 403 else "api_http_error", status) from None
        except Exception:
            # Never render exception messages, provider bodies or credential paths.
            raise InventoryError("api_transport_error") from None

    def rows(self, path, kind, params=None):
        params = dict(params or {})
        initial_path = path
        filters = {k: str(v) for k, v in params.items() if k.startswith("filter[")}
        current = path + ("?" + urlencode(params) if params else "")
        seen_pages, seen_ids, rows = set(), set(), []
        expected_total = None
        for _ in range(MAX_PAGES):
            parts = urlsplit(current)
            query = parse_qsl(parts.query, keep_blank_values=True)
            if len({key for key, _ in query}) != len(query):
                raise InventoryError("pagination_invalid")
            canonical = (parts.path, tuple(sorted(query)))
            if canonical in seen_pages:
                raise InventoryError("pagination_cycle")
            seen_pages.add(canonical)
            reply = self.request("GET", path, params)
            if not isinstance(reply, dict) or not isinstance(reply.get("data"), list) or not isinstance(reply.get("links"), dict):
                raise InventoryError("pagination_incomplete")
            metadata = reply.get("meta", {})
            if not isinstance(metadata, dict) or not isinstance(metadata.get("paging", {}), dict):
                raise InventoryError("pagination_invalid")
            total = metadata.get("paging", {}).get("total")
            if total is not None:
                if type(total) is not int or total < 0:
                    raise InventoryError("pagination_invalid")
                if expected_total is not None and expected_total != total:
                    raise InventoryError("pagination_changed")
                expected_total = total
            for item in reply["data"]:
                record(item, kind)
                if item["id"] in seen_ids:
                    raise InventoryError("pagination_duplicate")
                seen_ids.add(item["id"]); rows.append(item)
            if expected_total is not None and len(rows) > expected_total:
                raise InventoryError("pagination_changed")
            links = reply["links"]
            nxt = links.get("next")
            if nxt is None:
                if expected_total is not None and len(rows) != expected_total:
                    raise InventoryError("pagination_incomplete")
                if expected_total is None and "next" not in links:
                    raise InventoryError("pagination_incomplete")
                return rows
            if not isinstance(nxt, str) or nxt.strip() != nxt or any(ord(c) < 32 for c in nxt):
                raise InventoryError("pagination_invalid")
            parsed = urlsplit(nxt)
            next_query = parse_qsl(parsed.query, keep_blank_values=True)
            next_filters = {k: v for k, v in next_query if k.startswith("filter[")}
            if (parsed.scheme != "https" or parsed.netloc != HOST or parsed.fragment
                    or parsed.path != initial_path or next_filters != filters):
                raise InventoryError("pagination_invalid")
            current = path = parsed.path + ("?" + parsed.query if parsed.query else "")
            params = None
        raise InventoryError("pagination_limit")


def only(items):
    if len(items) != 1:
        raise InventoryError("selection_ambiguous")
    return items[0]


def inventory(client, *, bundle, build_number):
    if (not isinstance(bundle, str) or not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", bundle)
            or not isinstance(build_number, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){0,2}", build_number)):
        raise InventoryError("invalid_arguments")
    api = ReadOnly(client)
    app = only(api.rows("/v1/apps", "apps", {"filter[bundleId]": bundle, "limit": 200}))
    if app["attributes"].get("bundleId") != bundle:
        raise InventoryError("selection_mismatch")
    app_id = app["id"]
    build = only(api.rows("/v1/builds", "builds", {"filter[app]": app_id, "filter[version]": build_number, "limit": 200}))
    if build["attributes"].get("version") != build_number:
        raise InventoryError("selection_mismatch")
    build_id = build["id"]
    groups = api.rows(f"/v1/apps/{app_id}/betaGroups", "betaGroups", {"limit": 200})
    testers = api.rows("/v1/betaTesters", "betaTesters", {"filter[apps]": app_id, "limit": 200})
    linked = api.rows("/v1/betaGroups", "betaGroups", {"filter[app]": app_id, "filter[builds]": build_id, "limit": 200})
    direct = api.rows(f"/v1/builds/{build_id}/individualTesters", "betaTesters", {"limit": 200})
    detail = record(api.request("GET", f"/v1/builds/{build_id}/buildBetaDetail").get("data"), "buildBetaDetails")
    group_by_id, tester_by_id = {g["id"]: g for g in groups}, {t["id"]: t for t in testers}
    linked_ids, direct_ids = {g["id"] for g in linked}, {t["id"] for t in direct}
    if not linked_ids <= group_by_id.keys() or not direct_ids <= tester_by_id.keys():
        raise InventoryError("inventory_inconsistent")
    members = {}
    for group in groups:
        rows = api.rows(f"/v1/betaGroups/{group['id']}/betaTesters", "betaTesters", {"limit": 200})
        members[group["id"]] = {row["id"] for row in rows}
        if not members[group["id"]] <= tester_by_id.keys():
            raise InventoryError("inventory_inconsistent")
        # Concurrent changes must not be silently presented as one coherent snapshot.
        for row in rows:
            reference = tester_by_id[row["id"]]["attributes"]
            if any(row["attributes"].get(k) != reference.get(k) for k in ("email", "state")):
                raise InventoryError("inventory_inconsistent")
    for row in direct:
        if any(row["attributes"].get(k) != tester_by_id[row["id"]]["attributes"].get(k) for k in ("email", "state")):
            raise InventoryError("inventory_inconsistent")
    for group in linked:
        reference = group_by_id[group["id"]]["attributes"]
        if any(group["attributes"].get(k) != reference.get(k) for k in ("isInternalGroup", "publicLinkEnabled")):
            raise InventoryError("inventory_inconsistent")
    ba, da = build["attributes"], detail["attributes"]
    processing = state(ba.get("processingState"), {"VALID", "PROCESSING", "FAILED", "INVALID"})
    build_ok = processing == "VALID" and ba.get("expired") is False
    internal = state(da.get("internalBuildState"), BUILD_STATES)
    external = state(da.get("externalBuildState"), BUILD_STATES)
    ready_kind = {True: internal == "IN_BETA_TESTING", False: external == "IN_BETA_TESTING" and ba.get("buildAudienceType") != "INTERNAL_ONLY"}
    covered, eligible = set(direct_ids), set()
    for gid in linked_ids:
        covered |= members[gid]
        kind = group_by_id[gid]["attributes"].get("isInternalGroup")
        if type(kind) is bool and ready_kind[kind]:
            eligible |= members[gid]
    for tid in direct_ids:
        # Individual testers may be internal OR external. Do not infer their
        # type from the individual relationship; existing group membership can
        # prove a usable lane. Without it, both lanes must be ready.
        kinds = {g["attributes"].get("isInternalGroup") for g in groups if tid in members[g["id"]] and type(g["attributes"].get("isInternalGroup")) is bool}
        if any(ready_kind[k] for k in kinds) or (not kinds and all(ready_kind.values())):
            eligible.add(tid)
    def tester_summary(t):
        a = t["attributes"]
        return {"id": t["id"], "email_masked": mask_email(a.get("email")), "state": state(a.get("state"), TESTER_STATES)}
    uncovered = [tester_summary(t) for t in testers if t["id"] not in covered]
    not_ready = [tester_summary(t) for t in testers if not build_ok or t["id"] not in eligible or t["attributes"].get("state") not in {"ACCEPTED", "INSTALLED"}]
    group_reports = []
    for g in sorted(groups, key=lambda row: row["id"]):
        a, gid = g["attributes"], g["id"]
        kind, public = a.get("isInternalGroup"), a.get("publicLinkEnabled")
        group_reports.append({"id": gid, "name": group_label(a.get("name")),
            "kind": ("internal" if kind else "external") if type(kind) is bool else "unknown",
            "visibility": ("public" if public else "private") if type(public) is bool else "unknown",
            "linked_to_build": gid in linked_ids, "member_count": len(members[gid]),
            "members_covered_by_build": len(members[gid] & covered)})
    return {"inventory_complete": True, "bundle": bundle, "app_id": app_id,
        "build_number": build_number, "build_id": build_id, "build_processing_state": processing,
        "build_expired": ba.get("expired") if type(ba.get("expired")) is bool else None,
        "internal_build_state": internal, "external_build_state": external,
        "app_group_count": len(groups), "linked_build_group_count": len(linked_ids),
        "direct_build_tester_count": len(direct_ids), "app_tester_count": len(testers),
        "covered_tester_count": len(covered),
        "tester_state_counts": dict(sorted(Counter(state(t["attributes"].get("state"), TESTER_STATES) for t in testers).items())),
        "all_existing_testers_covered": not uncovered,
        "all_existing_testers_ready": bool(testers) and not not_ready,
        "linked_groups_private": all(g["visibility"] == "private" for g in group_reports if g["linked_to_build"]),
        "groups": group_reports, "uncovered_testers": uncovered, "not_ready_testers": not_ready,
        "limits": "Sequential API inventory, not an atomic snapshot. Ready means observed API eligibility and acceptance, not selected-build installation or notification delivery."}


def incomplete(category, http_status=None):
    error = {"category": category}
    if http_status is not None:
        error["http_status"] = http_status
    return {"inventory_complete": False, "all_existing_testers_covered": None,
            "all_existing_testers_ready": False, "error": error}


def audit_audience(client, *, bundle, build_number):
    try:
        return inventory(client, bundle=bundle, build_number=build_number)
    except InventoryError as exc:
        return incomplete(exc.category, exc.http_status)
    except Exception:
        return incomplete("malformed_response")


def existing_client():
    path = Path(__file__).resolve().parents[2] / "app/ios/scripts/app_store_connect.py"
    spec = importlib.util.spec_from_file_location("anticipy_audience_asc", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.Client(module.Credentials.environment())


def main(argv=None, *, client_factory=existing_client):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--build", required=True)
    args = parser.parse_args(argv)
    try:
        client = client_factory()
    except (Exception, SystemExit):
        report = incomplete("credentials_unavailable")
    else:
        report = audit_audience(client, bundle=args.bundle, build_number=args.build)
    print(json.dumps(report, sort_keys=True), flush=True)
    return 2 if not report["inventory_complete"] else (0 if report["all_existing_testers_ready"] else 1)


if __name__ == "__main__":
    raise SystemExit(main())
