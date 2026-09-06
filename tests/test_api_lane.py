"""THE LAST WIRE, brain side: `run_api_jobs` claims lane="api" the way the
research pass claims lane="research" — stamp, read back, walk away if the
stamp did not survive — and then hands the claimed id to the Worker's
/hands/api/run, which is the one thing that calls api_hand.ts.

Until 2026-09-06 the router's `api` verdict mapped to the browser lane
because nothing could run it (brain/hands.py, 6f62bc68). These legs pin the
executor half that now exists, and the polarity of every branch:

  * the poll is owner-scoped and lane-scoped; the claim is the extension's
    doctrine; a lost race means no POST;
  * a row on the lane WITHOUT an api verdict is never claimed (CONTROL: with
    one, it is) — nothing here may run what the router did not license;
  * THE WORKER WRITES THE ROW, NOT THE BRAIN: a settled answer costs the
    brain no second PATCH, because the route is the only thing that knows
    whether the vendor was called;
  * the body names an id and the process' own scope, never anything read
    off params;
  * a door that is not there (404) or refuses this token (401) releases the
    claim and pauses the lane; an UNREACHABLE door leaves the row running
    for the stranded sweep, because "unreachable" and "ran" look the same
    from here and re-running is the one thing never allowed;
  * the stranded sweep requeues a read and PARKS a write as needs_user with
    effect_uncertain, through recover_expired's own rule;
  * the browser stall notice and the device notice both skip this lane;
  * the main loop calls run_api_jobs EXACTLY ONCE (the mutation literal);
  * the constants the Worker route shares are the route's;
  * and the measured hole: the extension's claim filter names `lane` and
    does not exclude "api", so a shipped extension that polls first would
    list an api-lane row. Pinned as a MEASUREMENT with the reason it is
    tolerable (the workflow guard's lease keeps two hands off one row), so
    the day it changes is a visible day and the docstring that records it
    changes with it.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import types
from datetime import datetime, timedelta, timezone

import pytest

import brain.worker as W
from brain import hands
from brain.workflow import (Consequence, claim as claim_plan, from_params,
                            new_plan, put_in_params)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKERS = os.path.join(ROOT, "migration", "workers")


@pytest.fixture(autouse=True)
def _fresh_lane():
    W._api_hand_down_until = 0.0
    yield
    W._api_hand_down_until = 0.0


class Resp:
    def __init__(self, payload=None, ok=True, status_code=None):
        self.ok = ok
        self.status_code = status_code if status_code is not None else (200 if ok else 500)
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def make_anticipy(owner_ref=""):
    return types.SimpleNamespace(owner_id="own1", owner_ref=owner_ref,
                                 backend_url="http://pb", llm=None)


def wire(monkeypatch, job, patches, posts, stamp_survives=True, answer=None):
    """Point brain.pb at one in-memory job row; record every write. `answer`
    is what the Worker door says to the POST — a Resp, or an Exception."""
    state = dict(job)

    def fake_get(url, **kw):
        if url.endswith("/records"):
            filt = (kw.get("params") or {}).get("filter", "")
            fake_get.filters.append(filt)
            wanted = re.findall(r'status\s*=\s*"([a-z_]+)"', filt)
            if wanted and state.get("status") not in wanted:
                return Resp({"items": []})
            return Resp({"items": [dict(state)]})
        return Resp(dict(state))
    fake_get.filters = []

    def fake_patch(url, **kw):
        body = dict(kw.get("json") or {})
        body["_headers"] = dict(kw.get("headers") or {})
        patches.append(body)
        if stamp_survives:
            state.update(kw.get("json") or {})
        return Resp()

    def fake_post(url, **kw):
        posts.append({"url": url, "json": kw.get("json"), "timeout": kw.get("timeout")})
        if isinstance(answer, Exception):
            raise answer
        return answer if answer is not None else Resp(
            {"ok": True, "job": state.get("id"), "outcome": "ran", "status": "done",
             "lane": "api", "effect_uncertain": False})

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "patch", fake_patch)
    monkeypatch.setattr(W.pb, "post", fake_post)
    return fake_get


def note(**over):
    base = {"hand": "api", "reason": "his mail app is connected", "app": "mailer",
            "effect": "read", "asked": 1, "lane": "api"}
    base.update(over)
    return base


QUEUED = {"id": "a1", "goal": "what did Dana send me this week",
          "params": json.dumps({"source": "test", "_hand": note()}),
          "status": "queued", "lane": "api", "claimed_by": "", "owner": "own1"}


# ------------------------------------------------------------- the claim
def test_claims_like_the_extension_then_posts_the_id_to_the_worker(monkeypatch):
    patches, posts = [], []
    fake_get = wire(monkeypatch, QUEUED, patches, posts)
    W.run_api_jobs(make_anticipy())
    poll = next(f for f in fake_get.filters if 'status="queued"' in f)
    assert 'lane="api"' in poll
    assert 'owner="own1"' in poll
    assert patches[0]["status"] == "running"
    assert patches[0]["claimed_by"] == W.API_CLAIMANT == "worker-api"
    assert len(posts) == 1
    assert posts[0]["url"] == "http://pb" + W.API_HAND_RUN_PATH
    assert posts[0]["url"].endswith("/hands/api/run")
    # An id and nothing else: no goal, no params, no tool, no owner this
    # process does not itself hold.
    assert posts[0]["json"] == {"job": "a1"}


def test_the_body_names_an_id_and_the_process_scope_never_params(monkeypatch):
    decoy = dict(QUEUED, params=json.dumps({
        "source": "test", "owner_ref": "stranger00000000",
        "_hand": note(owner="stranger00000000")}))
    patches, posts = [], []
    wire(monkeypatch, decoy, patches, posts)
    W.run_api_jobs(make_anticipy(owner_ref="owner-a"))
    assert posts[0]["json"] == {"job": "a1", "owner": "owner-a"}
    assert set(posts[0]["json"]) <= {"job", "owner"}


def test_a_lost_claim_race_means_no_post(monkeypatch):
    patches, posts = [], []
    wire(monkeypatch, dict(QUEUED, claimed_by="ext-abc"), patches, posts,
         stamp_survives=False)
    W.run_api_jobs(make_anticipy())
    assert not posts
    assert len(patches) == 1


def test_a_row_without_an_api_verdict_is_never_claimed(monkeypatch):
    for bad in (note(hand="browser"), note(lane=""), {}, note(hand="research", lane="research")):
        patches, posts = [], []
        params = {"source": "test"}
        if bad:
            params["_hand"] = bad
        wire(monkeypatch, dict(QUEUED, params=json.dumps(params)), patches, posts)
        W.run_api_jobs(make_anticipy())
        assert not patches, bad
        assert not posts, bad
    # THE CONTROL: the same row with the verdict is claimed and posted.
    patches, posts = [], []
    wire(monkeypatch, QUEUED, patches, posts)
    W.run_api_jobs(make_anticipy())
    assert patches and posts


# ------------------------------------------------------ applying the answer
def test_the_worker_writes_the_row_and_the_brain_writes_nothing_after(monkeypatch):
    patches, posts = [], []
    wire(monkeypatch, QUEUED, patches, posts)
    W.run_api_jobs(make_anticipy())
    assert posts
    assert [p["status"] for p in patches] == ["running"], \
        "the brain PATCHed an outcome the route already wrote"
    assert W._api_hand_down_until == 0.0


@pytest.mark.parametrize("code", [404, 401])
def test_a_door_that_is_not_there_or_refuses_the_token_releases_and_pauses(monkeypatch, code):
    patches, posts = [], []
    fake_get = wire(monkeypatch, QUEUED, patches, posts,
                    answer=Resp({"ok": False, "message": "no"}, ok=False, status_code=code))
    W.run_api_jobs(make_anticipy())
    assert len(posts) == 1
    assert patches[-1]["status"] == "queued"
    assert patches[-1]["claimed_by"] == ""
    assert W._api_hand_down_until > 0
    # The lane is paused: the next pass does not even poll.
    polls = len(fake_get.filters)
    W.run_api_jobs(make_anticipy())
    assert len(fake_get.filters) == polls
    assert len(posts) == 1


def test_a_release_for_a_plan_goes_through_its_lease_and_stays_readable(monkeypatch):
    plan = new_plan(owner_ref="owner-a", lineage_key="lineage-a",
                    goal=QUEUED["goal"], consequence=Consequence.READ_ONLY,
                    source_event_id="event-a")
    row = dict(QUEUED, owner_ref="owner-a",
               params=json.dumps(put_in_params({"source": "test", "_hand": note()}, plan)))
    patches, posts = [], []
    wire(monkeypatch, row, patches, posts,
         answer=Resp({"ok": False}, ok=False, status_code=404))
    W.run_api_jobs(make_anticipy(owner_ref="owner-a"))
    claimed = from_params(json.loads(patches[0]["params"]))
    assert claimed.state.value == "running"
    assert claimed.lease.actor_id == W.API_CLAIMANT
    release = patches[-1]
    assert release["_headers"].get("X-Anticipy-Lease") == claimed.lease.token
    assert release["status"] == "queued"
    assert release["lease_token"] == ""
    released = from_params(json.loads(release["params"]))
    assert released.state.value == "queued"
    assert released.lease is None
    released.assert_valid()


def test_an_unreachable_door_leaves_the_row_running_for_the_sweep(monkeypatch):
    patches, posts = [], []
    wire(monkeypatch, QUEUED, patches, posts, answer=ConnectionError("dns"))
    W.run_api_jobs(make_anticipy())
    assert len(posts) == 1
    assert [p["status"] for p in patches] == ["running"]
    assert W._api_hand_down_until == 0.0, "an unreachable door is not a missing one"


@pytest.mark.parametrize("code", [409, 500])
def test_a_door_that_answered_without_settling_is_left_alone(monkeypatch, code):
    patches, posts = [], []
    wire(monkeypatch, QUEUED, patches, posts,
         answer=Resp({"ok": False, "message": "moved"}, ok=False, status_code=code))
    W.run_api_jobs(make_anticipy())
    assert [p["status"] for p in patches] == ["running"]
    assert W._api_hand_down_until == 0.0


# --------------------------------------------------------- the stranded sweep
def _stranded(effect, with_plan=True):
    ago = datetime.now(timezone.utc) - timedelta(minutes=40)
    params = {"source": "test", "_hand": note(effect=effect, lane="api")}
    row = dict(QUEUED, status="running", claimed_by=W.API_CLAIMANT,
               owner_ref="owner-a",
               updated=ago.strftime("%Y-%m-%d %H:%M:%S"))
    if with_plan:
        plan = new_plan(owner_ref="owner-a", lineage_key="lineage-a",
                        goal=QUEUED["goal"], consequence=Consequence.READ_ONLY,
                        source_event_id="event-a")
        plan = claim_plan(plan, expected_version=1, actor_id=W.API_CLAIMANT,
                          lease_seconds=5, now=ago)
        params = put_in_params(params, plan)
        row["lease_token"] = plan.lease.token
    row["params"] = json.dumps(params)
    return row


def test_a_stranded_read_is_requeued_and_a_stranded_write_is_parked(monkeypatch):
    for effect, status in (("read", "queued"), ("write", "needs_user"),
                           ("irreversible", "needs_user"), ("", "needs_user")):
        patches, posts = [], []
        fake_get = wire(monkeypatch, _stranded(effect), patches, posts)
        freed = W.release_stranded_api(make_anticipy(owner_ref="owner-a"))
        assert freed == 1, effect
        sweep = fake_get.filters[0]
        assert 'lane="api"' in sweep and f'claimed_by="{W.API_CLAIMANT}"' in sweep
        assert 'owner_ref="owner-a"' in sweep
        body = patches[0]
        assert body["status"] == status, effect
        assert body["_headers"].get("X-Anticipy-Lease"), "a plan is moved through its lease"
        recovered = from_params(json.loads(body["params"]))
        assert recovered.lease is None
        recovered.assert_valid()
        if status == "needs_user":
            assert body["effect_uncertain"] is True
            assert "check the app" in body["result"]
        else:
            assert "effect_uncertain" not in body
        assert not posts, "the sweep never runs anything"


def test_a_stranded_pre_workflow_row_follows_the_same_rule(monkeypatch):
    for effect, status in (("read", "queued"), ("write", "needs_user")):
        patches, posts = [], []
        wire(monkeypatch, _stranded(effect, with_plan=False), patches, posts)
        assert W.release_stranded_api(make_anticipy(owner_ref="owner-a")) == 1
        assert patches[0]["status"] == status, effect


def test_the_sweep_runs_before_the_poll(monkeypatch):
    patches, posts = [], []
    fake_get = wire(monkeypatch, QUEUED, patches, posts)
    W.run_api_jobs(make_anticipy())
    assert 'status="running"' in fake_get.filters[0]
    assert 'status="queued"' in fake_get.filters[1]


# ------------------------------------------------------------ the neighbours
def _no_quiet_hours(monkeypatch):
    monkeypatch.setattr(W, "browser_reachable", lambda: False)
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)


def test_the_browser_stall_notice_skips_the_api_lane(monkeypatch):
    _no_quiet_hours(monkeypatch)
    seen = {}

    def fake_get(url, **kw):
        seen["filter"] = (kw.get("params") or {}).get("filter", "")
        return Resp({"items": []})
    monkeypatch.setattr(W.pb, "get", fake_get)
    W.report_stalled_work(make_anticipy())
    assert 'lane!="api"' in seen["filter"]
    assert 'lane!="research"' in seen["filter"]


def test_the_device_notice_names_the_api_lane_out(monkeypatch):
    _no_quiet_hours(monkeypatch)
    seen = {}

    def fake_get(url, **kw):
        seen["filter"] = (kw.get("params") or {}).get("filter", "")
        return Resp({"items": []})
    monkeypatch.setattr(W.pb, "get", fake_get)
    W.report_unclaimed_device_work(make_anticipy())
    assert 'lane!="api"' in seen["filter"]


def test_the_worker_loop_actually_runs_the_api_pass_exactly_once():
    src = inspect.getsource(W.main)
    assert src.count("run_api_jobs(anticipy)") == 1
    # After research, whose pass hands held errands to the browser first.
    assert src.index("run_research_jobs(anticipy)") < src.index("run_api_jobs(anticipy)")


# ---------------------------------------------------- the two halves agree
def test_the_constants_the_worker_route_shares_are_the_routes():
    route = open(os.path.join(WORKERS, "src", "routes", "hands_api.ts"), encoding="utf-8").read()
    index = open(os.path.join(WORKERS, "src", "index.ts"), encoding="utf-8").read()
    assert f'export const API_CLAIMANT = "{W.API_CLAIMANT}"' in route
    assert f'export const API_LANE = "{hands.LANE_API}"' in route
    assert f'export const HANDS_API_RUN_PATH = "{W.API_HAND_RUN_PATH}"' in route
    assert index.count("path === HANDS_API_RUN_PATH") == 1
    assert hands.LANE_FOR[hands.HAND_API] == hands.LANE_API == W.LANE_API


def test_the_measured_hole_in_the_extensions_claim_filter_is_recorded():
    """A MEASUREMENT, not a wish. extension/background.js polls
    `workflow_id!="" && lane!="research"`: it names `lane`, so the Worker's
    research_lane hook appends nothing, and it excludes only research — an
    api-lane row is listable by a shipped extension. brain/hands.py's
    docstring records this and why it is tolerable. This leg goes red the
    day either file changes, which is the day that paragraph must too."""
    ext = open(os.path.join(ROOT, "extension", "background.js"), encoding="utf-8").read()
    hook = open(os.path.join(WORKERS, "src", "policy", "research_lane.ts"), encoding="utf-8").read()
    doc = hands.__doc__ or ""
    m = re.search(r'const BROWSER_LANE = \'([^\']+)\';', ext)
    assert m, "the extension's claim filter moved"
    assert m.group(1) == 'workflow_id!="" && lane!="research"'
    assert 'lane!="api"' not in m.group(1)
    assert 'EXCLUDED_LANES = ["research", SUPERVISED_LANE, DEVICE_LANE]' in hook
    assert 'lane === "research" && b.claimed_by !== WORKER_CLAIMANT' in hook
    assert '"api"' not in hook
    assert 'workflow_id!="" &&\nlane!="research"' in doc or \
        'workflow_id!="" && lane!="research"' in doc.replace("\n", " ")
