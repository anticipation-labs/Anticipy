"""The release writer may link only already-authorized, app-scoped testers.

Fake Apple transport; no credentials, real invitations, uploads, or network.
The payload follows Apple's BuildIndividualTestersLinkagesRequest contract.
"""
from copy import deepcopy
import importlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.test_testflight_audience import page, resource


SENTINEL = "private-provider-body-and-secret"


def module():
    return importlib.import_module("proof.audit.testflight_assign_existing")


class Apple:
    def __init__(self):
        self.calls = []
        self.snapshots = 0
        self.on_snapshot = lambda _client, _number: None
        self.post_error = None
        self.apply_before_error = False
        self.omit_assignment = False
        self.paginate = False
        self.broken_next = None
        self.app = resource("apps", "app-selected", bundleId="ai.anticipy.app")
        self.build = resource("builds", "build-selected", version="176",
                              processingState="VALID", expired=False,
                              buildAudienceType="APP_STORE_ELIGIBLE")
        self.detail = resource("buildBetaDetails", "detail-selected",
                               internalBuildState="IN_BETA_TESTING",
                               externalBuildState="IN_BETA_TESTING")
        self.testers = [resource("betaTesters", f"tester-{i}",
                                email=f"private-person-{i}@example.invalid",
                                firstName="PrivatePerson", state="INSTALLED" if i < 4 else "INVITED")
                        for i in range(6)]
        self.groups = [resource("betaGroups", f"group-{i}", name=f"PrivateGroup-{i}",
                                isInternalGroup=i == 0, publicLinkEnabled=i == 3)
                       for i in range(5)]
        self.members = {"group-0": ["tester-0", "tester-1"], "group-1": ["tester-2"],
                        "group-2": ["tester-3"], "group-3": ["tester-4"], "group-4": ["tester-5"]}
        self.linked = {"group-0", "group-1", "group-2"}
        self.direct = set()

    def rows(self, ids):
        return [tester for tester in self.testers if tester["id"] in ids]

    def request(self, method, path, params=None, body=None):
        self.calls.append((method, path, deepcopy(params), deepcopy(body)))
        if method == "POST":
            assert path == f"/v1/builds/{self.build['id']}/relationships/individualTesters"
            assert params is None and set(body) == {"data"}
            assert all(set(item) == {"type", "id"} and item["type"] == "betaTesters" for item in body["data"])
            ids = {item["id"] for item in body["data"]}
            assert ids <= {tester["id"] for tester in self.testers}
            if not self.omit_assignment and (self.post_error is None or self.apply_before_error):
                self.direct.update(ids)
            if self.post_error:
                raise self.post_error
            return None  # Existing ASC Client represents Apple's 204 this way.
        assert method == "GET" and body is None
        base = urlsplit(path).path
        if base == "/v1/apps":
            self.snapshots += 1
            self.on_snapshot(self, self.snapshots)
            assert params == {"filter[bundleId]": "ai.anticipy.app", "limit": 200}
            reply = page([self.app])
        elif base == "/v1/builds":
            assert params == {"filter[app]": self.app["id"], "filter[version]": "176", "limit": 200}
            reply = page([self.build])
        elif base == f"/v1/apps/{self.app['id']}/betaGroups":
            reply = page(self.groups)
        elif base == "/v1/betaTesters":
            if "?" not in path:
                assert params == {"filter[apps]": self.app["id"], "limit": 200}
            if self.paginate and "?" not in path:
                nxt = self.broken_next or ("https://api.appstoreconnect.apple.com/v1/betaTesters"
                                           f"?filter%5Bapps%5D={self.app['id']}&cursor=second")
                reply = page(self.testers[:2], total=len(self.testers), next_link=nxt)
            else:
                reply = page(self.testers[2:] if self.paginate else self.testers, total=len(self.testers))
        elif base == "/v1/betaGroups":
            assert params == {"filter[builds]": self.build["id"], "limit": 200}
            reply = page([g for g in self.groups if g["id"] in self.linked])
        elif base == f"/v1/builds/{self.build['id']}/individualTesters":
            reply = page(self.rows(self.direct))
        elif base == f"/v1/builds/{self.build['id']}/buildBetaDetail":
            reply = {"data": self.detail}
        elif base.startswith("/v1/betaGroups/") and base.endswith("/betaTesters"):
            reply = page(self.rows(self.members[base.split("/")[3]]))
        else:
            raise AssertionError("Unexpected endpoint")
        return deepcopy(reply)


def run(apple, **kwargs):
    return module().assign_existing(apple, bundle="ai.anticipy.app", build_number="176", **kwargs)


def writes(apple):
    return [call for call in apple.calls if call[0] != "GET"]


def test_default_dry_run_is_read_only_and_reports_missing_not_installed():
    apple = Apple()
    result = run(apple)
    assert result["result"] == "dry_run" and result["write_attempted"] is False
    assert result["existing_tester_count"] == 6 and result["missing_tester_count"] == 2
    assert result["pending_invitation_count"] == 2
    assert result["all_existing_testers_covered"] is False
    assert result["all_existing_testers_ready"] is False
    assert result["installation_verified"] is False
    assert writes(apple) == []


def test_confirmed_release_assigns_only_missing_existing_testers_never_groups():
    apple = Apple(); prior_groups = deepcopy((apple.groups, apple.members, apple.linked))
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "covered" and result["assigned_tester_count"] == 2
    assert result["all_existing_testers_covered"] is True
    assert result["all_existing_testers_ready"] is False  # Two invitations are still pending.
    assert result["pending_invitation_count"] == 2 and result["notification_delivery_verified"] is False
    assert writes(apple) == [("POST", "/v1/builds/build-selected/relationships/individualTesters", None,
                             {"data": [{"type": "betaTesters", "id": "tester-4"},
                                       {"type": "betaTesters", "id": "tester-5"}]})]
    assert (apple.groups, apple.members, apple.linked) == prior_groups
    assert apple.snapshots == 3  # Initial, fresh pre-write, fresh readback.


def test_covered_audience_is_idempotent_without_even_a_post():
    apple = Apple(); apple.direct = {"tester-4", "tester-5"}
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "covered" and result["assigned_tester_count"] == 0
    assert result["all_existing_testers_ready"] is False
    assert writes(apple) == []


def test_full_testers_inventory_paginates_before_each_phase():
    apple = Apple(); apple.paginate = True
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["all_existing_testers_covered"] is True
    assert len([c for c in apple.calls if "cursor=second" in c[1]]) == 3


@pytest.mark.parametrize("confirm", ["yes", "INVITE", "INVITE_EXTERNAL", "ASSIGN_EXISTING ", True])
def test_invalid_confirmation_refuses_before_read_or_write(confirm):
    apple = Apple(); result = run(apple, confirm=confirm)
    assert result["result"] == "refused" and result["reason"] == "invalid_confirmation"
    assert apple.calls == []


@pytest.mark.parametrize("bundle,build", [
    ("other.app", "176"), ("ai.anticipy.app", "175"), ("ai.anticipy.app", "174"),
    ("ai.anticipy.app", "176/other"), ("ai.anticipy.app", "176\n"),
])
def test_wrong_app_or_protected_or_malformed_build_cannot_write(bundle, build):
    apple = Apple()
    result = module().assign_existing(apple, bundle=bundle, build_number=build, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and apple.calls == []


@pytest.mark.parametrize("mutation", [
    lambda a: a.build["attributes"].update(processingState="PROCESSING"),
    lambda a: a.build["attributes"].update(expired=True),
    lambda a: a.build["attributes"].update(expired=None),
    lambda a: a.build["attributes"].update(buildAudienceType="INTERNAL_ONLY"),
    lambda a: a.detail["attributes"].update(externalBuildState="WAITING_FOR_BETA_REVIEW"),
    lambda a: a.detail["attributes"].update(internalBuildState="NOT_BETA_TESTING"),
    lambda a: a.testers[4]["attributes"].update(state="NOT_INVITED"),
    lambda a: a.testers[4]["attributes"].update(state="UNKNOWN"),
])
def test_unready_build_or_not_previously_invited_audience_refuses(mutation):
    apple = Apple(); mutation(apple)
    assert run(apple, confirm="ASSIGN_EXISTING")["result"] == "refused"
    assert writes(apple) == []


@pytest.mark.parametrize("value", [None, "", "UNKNOWN", True, [], {}, 123])
def test_external_eligibility_requires_an_explicit_supported_wire_value(value):
    apple = Apple(); apple.build["attributes"]["buildAudienceType"] = value
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and result["reason"] == "build_not_ready"
    assert writes(apple) == []


def test_missing_external_eligibility_never_means_allowed():
    apple = Apple(); del apple.build["attributes"]["buildAudienceType"]
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and result["reason"] == "build_not_ready"
    assert writes(apple) == []


def replace_tester(apple):
    apple.testers[5]["id"] = "different-existing-tester"
    apple.members["group-4"] = ["different-existing-tester"]


@pytest.mark.parametrize("mutation", [
    replace_tester,
    lambda a: a.testers[5]["attributes"].update(state="ACCEPTED"),
    lambda a: a.members["group-3"].clear(),
    lambda a: a.groups[3]["attributes"].update(publicLinkEnabled=False),
    lambda a: a.linked.add("group-4"),
    lambda a: a.direct.add("tester-4"),
    lambda a: a.app.update(id="other-app"),
    lambda a: a.build.update(id="other-build"),
])
def test_equal_counts_do_not_hide_authority_drift_before_write(mutation):
    apple = Apple()
    apple.on_snapshot = lambda a, number: mutation(a) if number == 2 else None
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and result["reason"] == "audience_changed"
    assert writes(apple) == []


def test_stale_inventory_refuses_without_changing_the_clock_limit():
    apple = Apple(); ticks = iter([0, 121])
    result = run(apple, confirm="ASSIGN_EXISTING", clock=lambda: next(ticks))
    assert result["result"] == "refused" and result["reason"] == "observation_stale"
    assert writes(apple) == []


@pytest.mark.parametrize("next_link", [
    "https://evil.invalid/v1/betaTesters?filter%5Bapps%5D=app-selected",
    "https://api.appstoreconnect.apple.com/v1/betaTesters?filter%5Bapps%5D=other-app",
    "https://api.appstoreconnect.apple.com/v1/betaTesters?filter%5Bapps%5D=app-selected&limit=200",
])
def test_malformed_or_foreign_pagination_cannot_authorize_assignment(next_link):
    apple = Apple(); apple.paginate = True; apple.broken_next = next_link
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and writes(apple) == []
    assert not any(c[1].startswith("https:") for c in apple.calls)


@pytest.mark.parametrize("applied", [False, True])
def test_uncertain_post_is_never_retried_or_reported_as_success(applied):
    apple = Apple(); apple.post_error = RuntimeError(SENTINEL); apple.apply_before_error = applied
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and result["reason"] == "write_outcome_unproven"
    assert result["write_attempted"] is True and result["assigned_tester_count"] is None
    assert len(writes(apple)) == 1 and SENTINEL not in json.dumps(result)


def test_unconfirmed_readback_never_repeats_the_post():
    apple = Apple(); apple.omit_assignment = True
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and result["reason"] == "assignment_not_observed"
    assert len(writes(apple)) == 1


def test_same_size_audience_drift_after_write_is_not_false_success():
    apple = Apple()
    def mutate(a, number):
        if number == 3:
            replace_tester(a)
            a.direct.discard("tester-5"); a.direct.add("different-existing-tester")
    apple.on_snapshot = mutate
    result = run(apple, confirm="ASSIGN_EXISTING")
    assert result["result"] == "refused" and result["reason"] == "audience_changed"
    assert len(writes(apple)) == 1 and result["assigned_tester_count"] is None


def test_cli_has_separate_dry_run_coverage_and_readiness_results_without_identifiers(capsys):
    apple = Apple()
    args = ["--bundle", "ai.anticipy.app", "--build", "176"]
    assert module().main(args, client_factory=lambda: apple) == 0
    assert json.loads(capsys.readouterr().out)["result"] == "dry_run"
    assert module().main(args + ["--confirm", "ASSIGN_EXISTING"], client_factory=lambda: apple) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["all_existing_testers_covered"] is True and result["all_existing_testers_ready"] is False
    for private in ["@", "PrivatePerson", "PrivateGroup", "tester-", "group-", "app-selected", "build-selected"]:
        assert private not in output.out + output.err


def test_credentials_and_argument_errors_are_fixed_codes_not_raw_prose(capsys):
    def unavailable():
        raise SystemExit(SENTINEL)
    assert module().main(["--bundle", "ai.anticipy.app", "--build", "176"], client_factory=unavailable) == 2
    assert SENTINEL not in capsys.readouterr().out
    assert module().main(["--unknown", SENTINEL], client_factory=unavailable) == 2
    output = capsys.readouterr()
    assert SENTINEL not in output.out + output.err


def test_existing_workflow_keeps_default_read_only_and_scopes_new_assignment_step():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".github/workflows/asc-query.yml").read_text()
    triggers = text.split("\non:\n", 1)[1].split("\nconcurrency:", 1)[0]
    assert triggers.startswith("  workflow_dispatch:\n")
    assert "\n  push:" not in triggers and "\n  pull_request:" not in triggers
    confirm = triggers.split("      confirm:\n", 1)[1]
    assert 'default: ""' in confirm
    step = text.split("      - name: Assign this build to existing testers only\n", 1)[1].split("\n      - name:", 1)[0]
    assert "inputs.confirm == 'ASSIGN_EXISTING'" in step
    assert "inputs.email == ''" in step
    assert "github.ref == 'refs/heads/cloudflare-backend'" in step
    assert "permissions:\n  contents: read" in text and "cancel-in-progress: false" in text
    script = step.split("        run: |\n", 1)[1]
    assert "${{" not in script
    assert "--bundle \"$TESTFLIGHT_BUNDLE\"" in script
    assert "--build \"$TESTFLIGHT_BUILD\"" in script
    assert "--confirm ASSIGN_EXISTING" in script
    for forbidden in ["invite-tester", "INVITE_EXTERNAL", "wrangler", "altool", "xcodebuild", "secret put"]:
        assert forbidden not in script
    assert "if: inputs.confirm == 'INVITE' && inputs.email != ''" in text
    assert "if: inputs.confirm == 'INVITE_EXTERNAL' && inputs.email != ''" in text


def test_cli_disallows_credential_redirects_and_restores_existing_opener():
    import urllib.request
    previous = urllib.request._opener
    seen = []
    def factory():
        seen.extend(urllib.request._opener.handlers)
        return Apple()
    assert module().main(["--bundle", "ai.anticipy.app", "--build", "176"], client_factory=factory) == 0
    assert any(isinstance(handler, module().NoRedirect) for handler in seen)
    assert urllib.request._opener is previous
    with pytest.raises(module().Refused):
        module().NoRedirect().redirect_request(None, None, 302, "found", {}, "https://evil.invalid")
