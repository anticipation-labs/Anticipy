"""Explicit private external-TestFlight handoff, using the runner's existing key.

No developer-account invitations, public links, binary uploads or production
App Store submission. Pending beta review is reported as pending, not installed.
The existing query workflow keeps its default read-only behavior.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import urllib.error
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("anticipy_asc", ROOT / "app/ios/scripts/app_store_connect.py")
asc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = asc
spec.loader.exec_module(asc)


def rows(client, path, params=None):
    result, seen = [], set()
    while path:
        if path in seen:
            raise RuntimeError("Apple pagination repeated a page")
        seen.add(path)
        reply = client.request("GET", path, params)
        result.extend(reply.get("data", []))
        nxt = (reply.get("links") or {}).get("next")
        if not nxt:
            break
        parsed = urlsplit(nxt)
        if parsed.scheme != "https" or parsed.netloc != "api.appstoreconnect.apple.com":
            raise RuntimeError("Unrecognized pagination destination")
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        params = None
    return result


def one(items, name):
    if len(items) != 1:
        raise RuntimeError(f"Expected exactly one {name}; found {len(items)}")
    return items[0]


def prepare(client, *, bundle, build_number, group_name, email, first, last, confirm):
    if confirm != "INVITE_EXTERNAL":
        raise ValueError("Explicit INVITE_EXTERNAL confirmation required")
    if not all([bundle, build_number, group_name, email]) or "@" not in email:
        raise ValueError("App, build, private group and tester email required")
    app = one(rows(client, "/v1/apps", {"filter[bundleId]": bundle, "limit": 2}), "app")
    build = one(rows(client, "/v1/builds", {
        "filter[app]": app["id"], "filter[version]": build_number, "limit": 5}), "build")
    attr = build.get("attributes") or {}
    if attr.get("processingState") != "VALID" or attr.get("expired") is not False:
        raise RuntimeError("The selected build is not valid and unexpired")
    if attr.get("buildAudienceType") == "INTERNAL_ONLY":
        raise RuntimeError("Apple marked this build internal-only; another CI upload is required")
    groups = rows(client, f"/v1/apps/{app['id']}/betaGroups", {"limit": 200})
    matches = [g for g in groups if g.get("attributes", {}).get("name") == group_name]
    if matches:
        group = one(matches, "named group")
        ga = group.get("attributes") or {}
        if ga.get("isInternalGroup") is not False or ga.get("publicLinkEnabled") is True:
            raise RuntimeError("The selected group is not a private external group")
        existing = rows(client, f"/v1/betaGroups/{group['id']}/betaTesters", {"limit": 200})
        if any(t.get("attributes", {}).get("email", "").lower() != email.lower() for t in existing):
            raise RuntimeError("The group includes another tester; use a dedicated private group")
    else:
        group = client.request("POST", "/v1/betaGroups", body={"data": {
            "type": "betaGroups", "attributes": {"name": group_name,
                "isInternalGroup": False, "publicLinkEnabled": False},
            "relationships": {"app": {"data": {"type": "apps", "id": app["id"]}}}}})["data"]
        print("Created private external group", flush=True)

    linked = rows(client, f"/v1/betaGroups/{group['id']}/builds", {"limit": 200})
    if build["id"] not in [item["id"] for item in linked]:
        client.request("POST", f"/v1/betaGroups/{group['id']}/relationships/builds",
                       body={"data": [{"type": "builds", "id": build["id"]}]})
    print("Exact build attached to private external group", flush=True)

    members = rows(client, f"/v1/betaGroups/{group['id']}/betaTesters", {"limit": 200})
    if not any(t.get("attributes", {}).get("email", "").lower() == email.lower() for t in members):
        found = rows(client, "/v1/betaTesters", {"filter[email]": email, "limit": 2})
        if found:
            tester = one(found, "tester")
            client.request("POST", f"/v1/betaGroups/{group['id']}/relationships/betaTesters",
                           body={"data": [{"type": "betaTesters", "id": tester["id"]}]})
        else:
            client.request("POST", "/v1/betaTesters", body={"data": {
                "type": "betaTesters", "attributes": {"email": email, "firstName": first, "lastName": last},
                "relationships": {"betaGroups": {"data": [{"type": "betaGroups", "id": group["id"]}]}}}})

    detail = client.request("GET", f"/v1/builds/{build['id']}/buildBetaDetail")["data"]
    state = detail.get("attributes", {}).get("externalBuildState")
    print("Apple external build state:", state, flush=True)
    if state in ("READY_FOR_BETA_SUBMISSION", "READY_FOR_BETA_TESTING"):
        # Apple will notify eligible testers after approval. This changes only
        # the selected build's beta notification preference, never its audience.
        client.request("PATCH", f"/v1/buildBetaDetails/{detail['id']}", body={"data": {
            "type": "buildBetaDetails", "id": detail["id"], "attributes": {"autoNotifyEnabled": True}}})
    if state == "READY_FOR_BETA_SUBMISSION":
        # Preserve all configured contact and demo credentials. A missing Apple
        # review field is a concrete blocker, not a reason to invent its value.
        submission = client.request("POST", "/v1/betaAppReviewSubmissions", body={"data": {
            "type": "betaAppReviewSubmissions", "relationships": {
                "build": {"data": {"type": "builds", "id": build["id"]}}}}})["data"]
        print("Beta review submitted:", submission.get("attributes", {}).get("betaReviewState"), flush=True)

    after_group = client.request("GET", f"/v1/betaGroups/{group['id']}")["data"]
    if after_group.get("attributes", {}).get("isInternalGroup") is not False or after_group.get("attributes", {}).get("publicLinkEnabled") is True:
        raise RuntimeError("External/private group readback failed")
    members = rows(client, f"/v1/betaGroups/{group['id']}/betaTesters", {"limit": 200})
    tester = one([t for t in members if t.get("attributes", {}).get("email", "").lower() == email.lower()], "assigned tester")
    linked = rows(client, f"/v1/betaGroups/{group['id']}/builds", {"limit": 200})
    if build["id"] not in [b["id"] for b in linked]:
        raise RuntimeError("Build association readback failed")
    detail = client.request("GET", f"/v1/builds/{build['id']}/buildBetaDetail")["data"]
    state = detail.get("attributes", {}).get("externalBuildState")
    result = {"build": build_number, "private_external_group": True, "tester_assigned": True,
              "tester_state": tester.get("attributes", {}).get("state"), "external_build_state": state,
              "auto_notify_enabled": detail.get("attributes", {}).get("autoNotifyEnabled") is True,
              "ready_to_install": state == "IN_BETA_TESTING"}
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        prepare(asc.Client(asc.Credentials.environment()),
            bundle=os.environ["TESTFLIGHT_BUNDLE"], build_number=os.environ["TESTFLIGHT_BUILD"],
            group_name=os.environ["TESTFLIGHT_GROUP"], email=os.environ["TESTFLIGHT_EMAIL"],
            first=os.environ.get("TESTFLIGHT_FIRST", ""), last=os.environ.get("TESTFLIGHT_LAST", ""),
            confirm=args.confirm)
    except urllib.error.HTTPError as exc:
        print("Apple refused this step:", exc.code, exc.read().decode()[:4000], flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
