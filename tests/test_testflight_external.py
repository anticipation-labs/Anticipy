"""Audience and readiness boundaries for the manual external TestFlight path."""
import pytest

from proof.audit.testflight_external import prepare


ARGS = dict(bundle="ai.anticipy.app", build_number="159", group_name="Pilot",
            email="tester@example.invalid", first="Test", last="Person", confirm="INVITE_EXTERNAL")


class Apple:
    def __init__(self, *, state="READY_FOR_BETA_SUBMISSION", group=None, members=None):
        self.state = state
        self.group = group
        self.members = members or []
        self.build = {"id": "build-159", "attributes": {"version": "159", "processingState": "VALID", "expired": False}}
        self.linked = []
        self.calls = []

    def request(self, method, path, params=None, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            data = {
                "/v1/apps": [{"id": "app"}],
                "/v1/builds": [self.build],
                "/v1/apps/app/betaGroups": [self.group] if self.group else [],
                "/v1/betaGroups/group/builds": self.linked,
                "/v1/betaGroups/group/betaTesters": self.members,
                "/v1/betaTesters": [],
                "/v1/betaGroups/group": self.group,
                "/v1/builds/build-159/buildBetaDetail": {
                    "id": "detail", "attributes": {"externalBuildState": self.state}},
            }[path]
            return {"data": data}
        if path == "/v1/betaGroups":
            assert body["data"]["attributes"]["publicLinkEnabled"] is False
            assert body["data"]["attributes"]["isInternalGroup"] is False
            self.group = {"id": "group", "attributes": body["data"]["attributes"]}
            return {"data": self.group}
        if path == "/v1/betaGroups/group/relationships/builds":
            assert body["data"] == [{"type": "builds", "id": "build-159"}]
            self.linked = [self.build]
            return None
        if path == "/v1/betaTesters":
            self.members = [{"id": "tester", "attributes": {**body["data"]["attributes"], "state": "INVITED"}}]
            return {"data": self.members[0]}
        if path == "/v1/buildBetaDetails/detail":
            assert body["data"]["attributes"] == {"autoNotifyEnabled": True}
            return {"data": {"id": "detail"}}
        if path == "/v1/betaAppReviewSubmissions":
            assert body["data"]["relationships"]["build"]["data"]["id"] == "build-159"
            self.state = "WAITING_FOR_BETA_REVIEW"
            return {"data": {"id": "submission", "attributes": {"betaReviewState": self.state}}}
        raise AssertionError((method, path, body))


def group(**attrs):
    return {"id": "group", "attributes": {"name": "Pilot", "isInternalGroup": False,
                                          "publicLinkEnabled": False, **attrs}}


def test_review_pending_is_not_reported_installable_and_retry_does_not_reinvite():
    apple = Apple()
    result = prepare(apple, **ARGS)
    assert result["tester_assigned"] and result["private_external_group"]
    assert result["external_build_state"] == "WAITING_FOR_BETA_REVIEW"
    assert not result["ready_to_install"]
    before = sum(method != "GET" for method, _, _ in apple.calls)
    prepare(apple, **ARGS)
    assert sum(method != "GET" for method, _, _ in apple.calls) == before
    assert not any("/users" in path or "userInvitations" in path for _, path, _ in apple.calls)


@pytest.mark.parametrize("attributes", [{"isInternalGroup": True}, {"publicLinkEnabled": True}])
def test_refuses_internal_or_public_group_without_writes(attributes):
    apple = Apple(group=group(**attributes))
    with pytest.raises(RuntimeError, match="private external"):
        prepare(apple, **ARGS)
    assert all(method == "GET" for method, _, _ in apple.calls)


def test_does_not_distribute_a_build_to_somebody_else_in_the_group():
    apple = Apple(group=group(), members=[{"id": "other", "attributes": {"email": "other@example.invalid"}}])
    with pytest.raises(RuntimeError, match="another tester"):
        prepare(apple, **ARGS)
    assert all(method == "GET" for method, _, _ in apple.calls)


@pytest.mark.parametrize("attrs", [{"expired": True}, {"processingState": "PROCESSING"}, {"buildAudienceType": "INTERNAL_ONLY"}])
def test_invalid_or_internal_only_build_cannot_be_distributed(attrs):
    apple = Apple(); apple.build["attributes"].update(attrs)
    with pytest.raises(RuntimeError):
        prepare(apple, **ARGS)
    assert all(method == "GET" for method, _, _ in apple.calls)


def test_installable_state_is_read_from_apple():
    assert prepare(Apple(state="IN_BETA_TESTING"), **ARGS)["ready_to_install"] is True


def test_unconfirmed_invitation_does_not_even_read_apple():
    apple = Apple()
    with pytest.raises(ValueError):
        prepare(apple, **{**ARGS, "confirm": ""})
    assert apple.calls == []
