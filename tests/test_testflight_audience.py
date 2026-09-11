"""Read-only audience inventory: fake Apple transport, never real credentials."""
from copy import deepcopy
import json
import urllib.error

import pytest

from proof.audit.testflight_audience import (
    InventoryError, ReadOnly, audit_audience, main,
)


def resource(kind, identifier, **attributes):
    return {"type": kind, "id": identifier, "attributes": attributes}


def page(data, *, total=None, next_link=None):
    return {"data": data, "links": {"next": next_link},
            "meta": {"paging": {"total": len(data) if total is None else total}}}


class Apple:
    def __init__(self):
        self.calls = []
        self.t1 = resource("betaTesters", "t1", email="alice@example.invalid",
                           firstName="PrivateAlice", lastName="PrivateSurname", state="INSTALLED")
        self.t2 = resource("betaTesters", "t2", email="bob@example.invalid", state="ACCEPTED")
        self.g1 = resource("betaGroups", "g1", name="Internal", isInternalGroup=True, publicLinkEnabled=False)
        self.g2 = resource("betaGroups", "g2", name="Private pilot", isInternalGroup=False, publicLinkEnabled=False)
        self.pages = {
            "/v1/apps": page([resource("apps", "app", bundleId="ai.anticipy.app")]),
            "/v1/builds": page([resource("builds", "b175", version="175", processingState="VALID", expired=False)]),
            "/v1/apps/app/betaGroups": page([self.g1, self.g2]),
            "/v1/betaTesters": page([self.t1, self.t2]),
            "/v1/betaGroups/g1/betaTesters": page([self.t1]),
            "/v1/betaGroups/g2/betaTesters": page([self.t2]),
            "/v1/betaGroups": page([self.g1]),
            "/v1/builds/b175/individualTesters": page([self.t2]),
            "/v1/builds/b175/buildBetaDetail": {"data": resource(
                "buildBetaDetails", "detail", internalBuildState="IN_BETA_TESTING", externalBuildState="IN_BETA_TESTING")},
        }

    def request(self, method, path, params=None, body=None):
        assert method == "GET" and body is None
        self.calls.append((method, path, params))
        if path == "/v1/betaTesters":
            assert params["filter[apps]"] == "app"
        if path == "/v1/betaGroups":
            assert params == {"filter[app]": "app", "filter[builds]": "b175", "limit": 200}
        reply = self.pages[path]
        if isinstance(reply, Exception):
            raise reply
        return deepcopy(reply)


def audit(client):
    return audit_audience(client, bundle="ai.anticipy.app", build_number="175")


def test_group_and_direct_union_covers_actual_app_audience_without_writes():
    apple = Apple(); result = audit(apple)
    assert result["inventory_complete"] and result["all_existing_testers_covered"]
    assert result["all_existing_testers_ready"]
    assert result["app_tester_count"] == result["covered_tester_count"] == 2
    assert result["direct_build_tester_count"] == 1
    assert result["tester_state_counts"] == {"ACCEPTED": 1, "INSTALLED": 1}
    assert result["groups"][1]["linked_to_build"] is False
    assert result["groups"][1]["members_covered_by_build"] == 1
    assert all(method == "GET" for method, _, _ in apple.calls)
    assert not any("/users" in path for _, path, _ in apple.calls)


def test_unlinked_group_is_not_coverage_and_uncovered_identity_is_masked():
    apple = Apple(); apple.pages["/v1/builds/b175/individualTesters"] = page([])
    result = audit(apple)
    assert result["inventory_complete"] and not result["all_existing_testers_covered"]
    assert result["uncovered_testers"] == [{"id": "t2", "email_masked": "b***@example.invalid", "state": "ACCEPTED"}]
    encoded = json.dumps(result)
    assert "bob@example.invalid" not in encoded and "alice@example.invalid" not in encoded
    assert "PrivateAlice" not in encoded and "PrivateSurname" not in encoded


def test_no_groups_does_not_mean_nobody_when_individual_testers_cover_app():
    apple = Apple()
    apple.pages["/v1/apps/app/betaGroups"] = page([])
    apple.pages["/v1/betaGroups"] = page([])
    apple.pages["/v1/builds/b175/individualTesters"] = page([apple.t1, apple.t2])
    result = audit(apple)
    assert result["all_existing_testers_covered"] and result["all_existing_testers_ready"]
    assert result["direct_build_tester_count"] == 2 and result["groups"] == []


def test_member_ids_deduplicate_across_groups_and_direct_relationships():
    apple = Apple()
    apple.pages["/v1/betaGroups/g2/betaTesters"] = page([apple.t1, apple.t2])
    apple.pages["/v1/betaGroups"] = page([apple.g1, apple.g2])
    apple.pages["/v1/builds/b175/individualTesters"] = page([apple.t1, apple.t2])
    result = audit(apple)
    assert result["covered_tester_count"] == result["app_tester_count"] == 2
    assert sum(g["member_count"] for g in result["groups"]) == 3


def test_paginates_app_testers_and_group_members_with_same_scope():
    apple = Apple()
    for path, first, second, query in [
        ("/v1/betaTesters", apple.t1, apple.t2, "filter%5Bapps%5D=app&cursor=next"),
        ("/v1/betaGroups/g2/betaTesters", apple.t1, apple.t2, "cursor=next"),
    ]:
        next_path = path + "?" + query
        apple.pages[path] = page([first], total=2, next_link="https://api.appstoreconnect.apple.com" + next_path)
        apple.pages[next_path] = page([second], total=2)
    result = audit(apple)
    assert result["inventory_complete"] and result["app_tester_count"] == 2
    assert result["groups"][1]["member_count"] == 2


@pytest.mark.parametrize("next_link", [
    "https://evil.invalid/v1/betaTesters?filter%5Bapps%5D=app",
    "http://api.appstoreconnect.apple.com/v1/betaTesters",
    "https://api.appstoreconnect.apple.com@evil.invalid/v1/betaTesters",
    "https://api.appstoreconnect.apple.com/v1/users",
    "https://api.appstoreconnect.apple.com/v1/betaTesters?filter%5Bapps%5D=other",
    "https://api.appstoreconnect.apple.com/v1/betaTesters?cursor=next",
    "https://api.appstoreconnect.apple.com/v1/betaTesters?filter%5Bapps%5D=app#fragment",
])
def test_foreign_or_scope_changing_next_is_refused_before_request(next_link):
    apple = Apple(); apple.pages["/v1/betaTesters"] = page([apple.t1], total=2, next_link=next_link)
    result = audit(apple)
    assert not result["inventory_complete"]
    assert result["error"]["category"] == "pagination_invalid"
    assert not any("?" in path for _, path, _ in apple.calls)


def test_cycle_and_duplicate_ids_refuse_completeness():
    apple = Apple()
    nxt = "/v1/betaTesters?filter%5Bapps%5D=app&limit=200"
    apple.pages["/v1/betaTesters"]["links"]["next"] = "https://api.appstoreconnect.apple.com" + nxt
    assert audit(apple)["error"]["category"] == "pagination_cycle"
    apple = Apple(); apple.pages["/v1/betaTesters"] = page([apple.t1, apple.t1])
    assert audit(apple)["error"]["category"] == "pagination_duplicate"


@pytest.mark.parametrize("replacement", [
    {"data": []}, {"data": [], "links": {}},
    {"data": [], "links": {"next": None}, "meta": {"paging": {"total": 4}}},
    {"data": "not-list", "links": {"next": None}},
    page([{"type": "betaTesters", "id": "../other", "attributes": {}}]),
    page([{"type": "wrong", "id": "t1", "attributes": {}}]),
])
def test_malformed_or_truncated_inventory_never_passes(replacement):
    apple = Apple(); apple.pages["/v1/betaTesters"] = replacement
    result = audit(apple)
    assert result["inventory_complete"] is False
    assert result["all_existing_testers_covered"] is None
    assert result["all_existing_testers_ready"] is False


def test_total_is_enough_to_prove_terminal_page_when_apple_omits_next():
    apple = Apple()
    for value in apple.pages.values():
        if "links" in value:
            value["links"] = {"self": "not-followed"}
    assert audit(apple)["inventory_complete"]


@pytest.mark.parametrize("state", ["NOT_INVITED", "INVITED", "FUTURE_APPLE_STATE", None])
def test_unknown_or_unaccepted_tester_is_not_all_ready(state):
    apple = Apple(); apple.t1["attributes"]["state"] = state
    result = audit(apple)
    assert result["inventory_complete"] and result["all_existing_testers_covered"]
    assert not result["all_existing_testers_ready"]
    assert result["not_ready_testers"][0]["id"] == "t1"


@pytest.mark.parametrize("updates", [{"processingState": "PROCESSING"}, {"expired": True}, {"expired": None}])
def test_build_not_valid_or_expired_never_ready(updates):
    apple = Apple(); apple.pages["/v1/builds"]["data"][0]["attributes"].update(updates)
    result = audit(apple)
    assert result["inventory_complete"] and not result["all_existing_testers_ready"]


def test_review_pending_is_coverage_not_installability():
    apple = Apple()
    apple.pages["/v1/builds/b175/buildBetaDetail"]["data"]["attributes"]["externalBuildState"] = "WAITING_FOR_BETA_REVIEW"
    result = audit(apple)
    assert result["all_existing_testers_covered"] and not result["all_existing_testers_ready"]
    assert [x["id"] for x in result["not_ready_testers"]] == ["t2"]


def test_direct_only_tester_type_not_guessed_external_or_internal():
    apple = Apple()
    apple.pages["/v1/apps/app/betaGroups"] = page([])
    apple.pages["/v1/betaGroups"] = page([])
    apple.pages["/v1/builds/b175/individualTesters"] = page([apple.t1, apple.t2])
    apple.pages["/v1/builds/b175/buildBetaDetail"]["data"]["attributes"]["externalBuildState"] = "WAITING_FOR_BETA_REVIEW"
    result = audit(apple)
    assert result["all_existing_testers_covered"] and not result["all_existing_testers_ready"]


@pytest.mark.parametrize("target", ["/v1/apps", "/v1/builds"])
def test_ambiguous_app_or_build_refuses(target):
    apple = Apple(); item = deepcopy(apple.pages[target]["data"][0]); item["id"] += "-other"
    apple.pages[target] = page([apple.pages[target]["data"][0], item])
    assert audit(apple)["error"]["category"] == "selection_ambiguous"


def test_missing_app_group_for_linked_build_refuses():
    apple = Apple(); apple.pages["/v1/apps/app/betaGroups"] = page([apple.g2])
    assert audit(apple)["error"]["category"] == "inventory_inconsistent"


def test_public_group_and_empty_audience_are_explicit():
    apple = Apple(); apple.g1["attributes"]["publicLinkEnabled"] = True
    result = audit(apple)
    assert result["groups"][0]["visibility"] == "public"
    assert result["linked_groups_private"] is False
    apple = Apple()
    for path in ["/v1/betaTesters", "/v1/betaGroups/g1/betaTesters", "/v1/betaGroups/g2/betaTesters", "/v1/builds/b175/individualTesters"]:
        apple.pages[path] = page([])
    result = audit(apple)
    assert result["inventory_complete"] and result["app_tester_count"] == 0
    assert result["all_existing_testers_ready"] is False


def test_forbidden_and_exception_messages_are_sanitized():
    apple = Apple()
    apple.pages["/v1/builds/b175/individualTesters"] = urllib.error.HTTPError(
        "https://secret.invalid", 403, "private@example.invalid", {}, None)
    result = audit(apple)
    assert result["error"] == {"category": "api_forbidden", "http_status": 403,
                               "endpoint": "/v1/builds/b175/individualTesters"}
    assert "private@example.invalid" not in json.dumps(result)
    apple.pages["/v1/builds/b175/individualTesters"] = ValueError("secret-token-do-not-print")
    assert "secret-token" not in json.dumps(audit(apple))


def test_read_only_adapter_rejects_any_write_before_client():
    apple = Apple()
    with pytest.raises(InventoryError, match="read_only_violation"):
        ReadOnly(apple).request("POST", "/v1/betaTesters", body={})
    assert apple.calls == []


def test_http_diagnostic_excludes_pagination_query_and_provider_details():
    apple = Apple()
    path = "/v1/betaGroups?cursor=opaque-private-cursor"
    apple.pages[path] = urllib.error.HTTPError(
        "https://provider.invalid/private", 400, "private provider details", {}, None)
    with pytest.raises(InventoryError) as raised:
        ReadOnly(apple).request("GET", path)
    assert raised.value.endpoint == "/v1/betaGroups"
    assert str(raised.value) == "api_http_error"


def test_cli_has_distinct_ready_attention_and_incomplete_exits(capsys):
    assert main(["--bundle", "ai.anticipy.app", "--build", "175"], client_factory=Apple) == 0
    assert json.loads(capsys.readouterr().out)["inventory_complete"]
    apple = Apple(); apple.pages["/v1/builds/b175/individualTesters"] = page([])
    assert main(["--bundle", "ai.anticipy.app", "--build", "175"], client_factory=lambda: apple) == 1
    assert not json.loads(capsys.readouterr().out)["all_existing_testers_covered"]
    def unavailable():
        raise SystemExit("private-key-path-and-secret")
    assert main(["--bundle", "ai.anticipy.app", "--build", "175"], client_factory=unavailable) == 2
    assert "private-key" not in capsys.readouterr().out


@pytest.mark.parametrize("metadata", [None, [], {"paging": []}, {"paging": {"total": True}}])
def test_malformed_pagination_metadata_is_not_ignored(metadata):
    apple = Apple(); apple.pages["/v1/betaTesters"]["meta"] = metadata
    assert not audit(apple)["inventory_complete"]


@pytest.mark.parametrize("fault", ["duplicate-id", "changed-total", "duplicate-query"])
def test_cross_page_consistency_guards(fault):
    apple = Apple(); next_path = "/v1/betaTesters?filter%5Bapps%5D=app&cursor=next"
    if fault == "duplicate-query":
        next_path += "&cursor=again"
    apple.pages["/v1/betaTesters"] = page([apple.t1], total=2, next_link="https://api.appstoreconnect.apple.com" + next_path)
    apple.pages[next_path] = page([apple.t1 if fault == "duplicate-id" else apple.t2], total=3 if fault == "changed-total" else 2)
    assert not audit(apple)["inventory_complete"]


def test_app_tester_without_any_group_or_direct_link_stays_uncovered():
    apple = Apple(); apple.pages["/v1/betaGroups/g2/betaTesters"] = page([])
    apple.pages["/v1/builds/b175/individualTesters"] = page([])
    result = audit(apple)
    assert result["app_tester_count"] == 2 and result["covered_tester_count"] == 1
    assert result["uncovered_testers"][0]["id"] == "t2"


@pytest.mark.parametrize("path", ["/v1/betaGroups/g1/betaTesters", "/v1/builds/b175/individualTesters"])
def test_membership_outside_app_inventory_refuses(path):
    apple = Apple(); apple.pages[path] = page([resource("betaTesters", "unrelated", email="other@example.invalid", state="ACCEPTED")])
    assert audit(apple)["error"]["category"] == "inventory_inconsistent"


def test_racing_tester_state_and_group_privacy_are_not_one_coherent_snapshot():
    apple = Apple(); changed = deepcopy(apple.t1); changed["attributes"]["state"] = "NOT_INVITED"
    apple.pages["/v1/betaGroups/g1/betaTesters"] = page([changed])
    assert audit(apple)["error"]["category"] == "inventory_inconsistent"
    apple = Apple(); changed = deepcopy(apple.g1); changed["attributes"]["publicLinkEnabled"] = True
    apple.pages["/v1/betaGroups"] = page([changed])
    assert audit(apple)["error"]["category"] == "inventory_inconsistent"


def test_group_name_cannot_leak_full_email_and_internal_only_is_not_external_ready():
    apple = Apple(); apple.g1["attributes"]["name"] = "Testers alice@example.invalid"
    apple.pages["/v1/builds"]["data"][0]["attributes"]["buildAudienceType"] = "INTERNAL_ONLY"
    result = audit(apple)
    assert "alice@example.invalid" not in json.dumps(result)
    assert result["not_ready_testers"][0]["id"] == "t2"


def test_page_bound_is_incomplete_not_truncated_success(monkeypatch):
    monkeypatch.setattr("proof.audit.testflight_audience.MAX_PAGES", 1)
    apple = Apple(); apple.pages["/v1/apps"]["links"]["next"] = "https://api.appstoreconnect.apple.com/v1/apps?filter%5BbundleId%5D=ai.anticipy.app&cursor=next"
    assert audit(apple)["error"]["category"] == "pagination_limit"


def test_exact_selection_attributes_and_missing_detail_refuse():
    apple = Apple(); apple.pages["/v1/apps"]["data"][0]["attributes"]["bundleId"] = "other.app"
    assert audit(apple)["error"]["category"] == "selection_mismatch"
    apple = Apple(); apple.pages["/v1/builds/b175/buildBetaDetail"] = {"data": None}
    assert not audit(apple)["inventory_complete"]
