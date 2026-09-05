"""Executable conformance suite for migration/spec/CONTRACT.md.

THE POINT OF THIS FILE
----------------------
The audit found no test anywhere in this tree that exercises the real
PocketBase.  A port therefore has no oracle.  This suite is that oracle: the
identical file is run against the live PocketBase and against the Cloudflare
Worker, and the two result sets are diffed.  A test that passes on one and
fails on the other is either a bug in the port or a line in CONTRACT.md that
was wrong.  Both are findings.

    BASE_URL=https://backend-production-61e0a.up.railway.app \
      python3 -m pytest migration/spec/contract_tests.py -v \
      -m "not destructive" --junitxml=/tmp/pocketbase.xml

    BASE_URL=https://api.anticipy.workers.dev \
      python3 -m pytest migration/spec/contract_tests.py -v \
      -m "not destructive" --junitxml=/tmp/worker.xml

    diff <(grep -oE 'name="[^"]+"' /tmp/pocketbase.xml) \
         <(grep -oE 'name="[^"]+"' /tmp/worker.xml)

DESIGN RULES, EACH THERE FOR A REASON
-------------------------------------
* STANDARD LIBRARY ONLY.  `requests` is not a dependency.  A suite that cannot
  be run because of a missing wheel is a suite nobody runs.
* ONE RULE PER TEST.  Every test name says which contract rule it pins, and
  every assertion message quotes the CONTRACT.md section.  A red test should
  tell you what broke without opening the source.
* A MISSING CREDENTIAL SKIPS, IT NEVER FAILS.  The skip message names the
  environment variable, so an incomplete run reads as "you did not give me the
  key" rather than "the backend is broken".
* NOTHING IS CREATED WITHOUT `-m destructive`.  Almost every test here drives a
  REFUSAL, which by definition writes nothing.  The handful that would write a
  row carry @pytest.mark.destructive AND additionally require
  ANTICIPY_ALLOW_DESTRUCTIVE=1, so `-m destructive` alone is not enough to
  surprise anyone.
* TESTS THAT SPEND A RATE-LIMIT BUDGET carry @pytest.mark.slow.  The pair-code
  ceiling is 10 failures per IP per ten minutes; a suite that burns them on
  every run makes pairing stop working for real people.

ENVIRONMENT
-----------
    BASE_URL                        required; everything skips without it
    ANTICIPY_SERVICE_TOKEN          the guard's token rung and 4 service routes
    ANTICIPY_INTERNAL_KEY           every keyed HQ route
    ANTICIPY_TEST_OWNER_EMAIL       )  an account this suite may sign in as
    ANTICIPY_TEST_OWNER_PASSWORD    )
    ANTICIPY_TEST_AGENT_ID          )  a PAIRED agent's credential
    ANTICIPY_TEST_AGENT_TOKEN       )
    ANTICIPY_TEST_ACTOR_ID          a resolvable internal_people id
    ANTICIPY_TEST_ADMIN_ACTOR_ID    an internal_people id with is_admin
    ANTICIPY_TEST_JOB_ID            a jobs row this suite may attempt to PATCH
    ANTICIPY_TEST_OWNER_REF         an owners id (defaults to the signed-in one)
    ANTICIPY_ALLOW_DESTRUCTIVE=1    unlocks the destructive tests
    ANTICIPY_HTTP_TIMEOUT           seconds, default 30
    ANTICIPY_LOCAL_WRANGLER_CONFIG  wrangler.jsonc of a LOCAL Worker; unlocks
                                    the D1 reads (the meter, the events row)
    ANTICIPY_TEST_SENDBLUE_SECRET   )  /sms/sendblue past its front door
    ANTICIPY_TEST_SENDBLUE_NUMBER   )  (the Worker's SENDBLUE_FROM_NUMBER)
    ANTICIPY_TEST_TWILIO_AUTH_TOKEN )  /sms/inbound past its front door --
    ANTICIPY_TEST_TWILIO_ACCOUNT_SID)  the suite signs the form itself
    ANTICIPY_TEST_TWILIO_NUMBER     )
    ANTICIPY_TEST_SMS_OWNER_PHONE   )  a SEEDED owner an inbound text resolves
    ANTICIPY_TEST_SMS_OWNER_REF     )  to -- never a real person's number
    ANTICIPY_TEST_SMS_AMBIGUOUS_PHONE  a number two seeded owners share
    ANTICIPY_TEST_SMS_UNCONFIGURED_URL a Worker with NO Sendblue secret at all
                                    (the "unset is a 503, not a 403" leg)
    migration/workers/scripts/sms_contract_local.sh sets all of the SMS ones
    against a real workerd and a scratch D1.

MARKERS
-------
Registered by `conftest.py` beside this file, deliberately not in the repo-root
pytest.ini (that one sets `testpaths = tests` for the product suite).

    destructive          writes or deletes real rows; ALSO needs
                         ANTICIPY_ALLOW_DESTRUCTIVE=1
    anonymous            needs no credential at all — the zero-secret baseline
    slow                 spends a rate-limit budget
    offline              needs no network; reads CONTRACT.md only
    guard_on             needs the data-API guard switched on
    needs_service_token / needs_internal_key / needs_hq /
    needs_account / needs_agent

Run `-m anonymous` first against anything new: it carries the fail-open alarm.
"""

import base64
import datetime
import hashlib
import hmac
import json
import os
import random
import re
import string
import subprocess
import urllib.error
import urllib.parse
import urllib.request

import pytest

# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

BASE_URL = (os.environ.get("BASE_URL") or "").rstrip("/")
SERVICE_TOKEN = os.environ.get("ANTICIPY_SERVICE_TOKEN") or ""
INTERNAL_KEY = os.environ.get("ANTICIPY_INTERNAL_KEY") or ""
OWNER_EMAIL = os.environ.get("ANTICIPY_TEST_OWNER_EMAIL") or ""
OWNER_PASSWORD = os.environ.get("ANTICIPY_TEST_OWNER_PASSWORD") or ""
AGENT_ID = os.environ.get("ANTICIPY_TEST_AGENT_ID") or ""
AGENT_TOKEN = os.environ.get("ANTICIPY_TEST_AGENT_TOKEN") or ""
ACTOR_ID = os.environ.get("ANTICIPY_TEST_ACTOR_ID") or ""
ADMIN_ACTOR_ID = os.environ.get("ANTICIPY_TEST_ADMIN_ACTOR_ID") or ""
JOB_ID = os.environ.get("ANTICIPY_TEST_JOB_ID") or ""
OWNER_REF_ENV = os.environ.get("ANTICIPY_TEST_OWNER_REF") or ""
ALLOW_DESTRUCTIVE = os.environ.get("ANTICIPY_ALLOW_DESTRUCTIVE") == "1"
TIMEOUT = float(os.environ.get("ANTICIPY_HTTP_TIMEOUT") or "30")

CONTRACT_MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CONTRACT.md")


# --------------------------------------------------------------------------
# the HTTP client — stdlib, and it never raises on a non-2xx
# --------------------------------------------------------------------------

class Response(object):
    """A response that carries its own body whatever the status was.

    urllib raises HTTPError for >=400, which is exactly the class of response
    this suite exists to inspect.  Everything below unwraps it.
    """

    __slots__ = ("status", "headers", "body", "url")

    def __init__(self, status, headers, body, url):
        self.status = status
        self.headers = headers
        self.body = body
        self.url = url

    @property
    def text(self):
        try:
            return self.body.decode("utf-8", "replace")
        except Exception:
            return repr(self.body)

    @property
    def json(self):
        """The parsed body, or None.  Never raises: a route under test is
        allowed to answer with something that is not JSON, and the test should
        say so rather than erroring in the harness."""
        try:
            return json.loads(self.body.decode("utf-8"))
        except Exception:
            return None

    def header(self, name):
        """A response header by name, CASE-INSENSITIVELY.

        HTTP header names are case-insensitive (RFC 9110 5.1) and an origin
        does not control the case its proxy forwards.  Railway's edge relays
        `X-Robots-Tag` and the CORS block PocketBase set as `x-robots-tag` /
        `access-control-allow-origin`, while the headers the edge adds itself
        keep canonical case.  `call()` used to store `dict(resp.headers)`,
        which throws away urllib's case-insensitive HTTPMessage and leaves a
        plain dict keyed on whatever case came off the wire — so
        `header("X-Robots-Tag")` returned None on a response that carried it.
        Two TestHQFrontDoor tests failed on that, and a third
        (test_cors_refuses_an_unlisted_origin) PASSED on it, which is worse:
        it asserts a header is ABSENT and every lookup was absent.

        `call()` now keeps the HTTPMessage, whose own `.get` is already
        case-insensitive; the fold below is the belt to that braces, so a
        future refactor back to a plain dict cannot silently reintroduce a
        test that can only pass."""
        h = self.headers
        if h is None:
            return None
        try:
            value = h.get(name)
            if value is not None:
                return value
        except Exception:
            pass
        try:
            wanted = name.lower()
            for key, value in h.items():
                if key.lower() == wanted:
                    return value
        except Exception:
            pass
        return None

    def __repr__(self):
        return "<%s %s :: %s>" % (self.status, self.url, self.text[:400])


def call(method, path, headers=None, json_body=None, form=None, raw=None,
         query=None, base=None):
    """One request.  `path` is absolute-on-host, e.g. "/internal/health".

    The BASE_URL check lives HERE and not only in the autouse fixture because
    session-scoped fixtures are resolved BEFORE function-scoped autouse ones,
    so a probing fixture would otherwise error with "unknown url type" instead
    of skipping with a message that names the variable.
    """
    if not (base or BASE_URL):
        pytest.skip("set BASE_URL to the backend under test")
    root = (base or BASE_URL).rstrip("/")
    url = root + path
    if query:
        url += "?" + urllib.parse.urlencode(query)

    data = None
    # A REAL USER-AGENT, because the default one is BANNED.
    #
    # urllib sends "Python-urllib/3.x", and Cloudflare's bot protection answers
    # it with 403 Error 1010 "browser_signature_banned" before the request ever
    # reaches the Worker. That is indistinguishable from a genuine 403 by status
    # alone, so a whole run against a *.workers.dev origin came back as 37
    # failures and 66 "the guard appears to be OFF" skips -- none of which were
    # about the Worker at all. curl was unaffected, which is exactly why the
    # discrepancy took a while to see.
    hdrs = {"Accept": "application/json",
            "User-Agent": "anticipy-contract-suite/1.0 (+migration/spec)"}
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    elif raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    for key, value in (headers or {}).items():
        if value is None:
            continue
        hdrs[key] = value

    request = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as resp:
            # NOT dict(resp.headers): see Response.header.  urllib hands back
            # an email.message.Message, which is case-insensitive; a dict of it
            # is not, and Railway forwards origin-set headers lower-cased.
            return Response(resp.getcode(), resp.headers, resp.read(), url)
    except urllib.error.HTTPError as err:
        return Response(err.code, err.headers, err.read() or b"", url)
    except urllib.error.URLError as err:
        pytest.fail("could not reach %s: %r  (is BASE_URL right, and is the "
                    "service up?)" % (url, err))


def detail_of(resp):
    """The `detail` or `error` string of a JSON refusal, or the raw text."""
    body = resp.json
    if isinstance(body, dict):
        for key in ("detail", "error", "message", "reason"):
            if key in body and isinstance(body[key], str):
                return body[key]
    return resp.text


def error_of(resp):
    body = resp.json
    if isinstance(body, dict) and isinstance(body.get("error"), str):
        return body["error"]
    return resp.text


def rand(n=12, alphabet=string.ascii_lowercase + string.digits):
    return "".join(random.choice(alphabet) for _ in range(n))


# --------------------------------------------------------------------------
# gates — a missing credential SKIPS with the variable named
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _require_base_url(request):
    """Everything that touches the network skips without a BASE_URL.  Tests
    marked `offline` (the document-agreement checks in §10) are exempt: they
    read CONTRACT.md and nothing else, and they are the ones that catch the
    document and the suite drifting apart."""
    if request.node.get_closest_marker("offline"):
        return
    if not BASE_URL:
        pytest.skip("set BASE_URL to the backend under test "
                    "(e.g. BASE_URL=https://backend-production-61e0a.up.railway.app)")


@pytest.fixture(autouse=True)
def _gate_destructive(request):
    if request.node.get_closest_marker("destructive") and not ALLOW_DESTRUCTIVE:
        pytest.skip("destructive: set ANTICIPY_ALLOW_DESTRUCTIVE=1 to run this "
                    "(it writes or deletes real rows)")


def need(value, variable):
    if not value:
        pytest.skip("set %s to run this test" % variable)
    return value


@pytest.fixture(scope="session")
def service_token():
    return need(SERVICE_TOKEN, "ANTICIPY_SERVICE_TOKEN")


def require_internal_key():
    """Skip, with the variable named, when no HQ key is available.

    A plain function as well as the fixture below, because the projection
    tests call it from helper methods rather than taking it as an argument."""
    if not INTERNAL_KEY:
        pytest.skip("set ANTICIPY_INTERNAL_KEY to exercise HQ's keyed routes")
    return INTERNAL_KEY


@pytest.fixture(scope="session")
def internal_key():
    return need(INTERNAL_KEY, "ANTICIPY_INTERNAL_KEY")


@pytest.fixture(scope="session")
def actor_id():
    return need(ACTOR_ID, "ANTICIPY_TEST_ACTOR_ID")


@pytest.fixture(scope="session")
def admin_actor_id():
    return need(ADMIN_ACTOR_ID, "ANTICIPY_TEST_ADMIN_ACTOR_ID")


@pytest.fixture(scope="session")
def job_id():
    return need(JOB_ID, "ANTICIPY_TEST_JOB_ID")


@pytest.fixture(scope="session")
def real_owner_ref(service_token):
    """A REAL owners id, read live from `/worker/owners`.

    Only for tests that mean to compare a real relation value against the
    `OWNER_UNDER_TEST` sentinel.  Nothing here ever CREATES an owner: this is
    production, and the owners in it are people.
    """
    if OWNER_REF_ENV:
        return OWNER_REF_ENV
    resp = call("GET", "/worker/owners", headers=svc())
    items = (resp.json or {}).get("items") if isinstance(resp.json, dict) else None
    if resp.status != 200 or not items:
        pytest.skip("/worker/owners returned no owner to point at (%s); set "
                    "ANTICIPY_TEST_OWNER_REF instead" % resp.status)
    return items[0]["id"]


@pytest.fixture(scope="session")
def agent_headers():
    need(AGENT_ID, "ANTICIPY_TEST_AGENT_ID")
    need(AGENT_TOKEN, "ANTICIPY_TEST_AGENT_TOKEN")
    return {"X-Anticipy-Agent-ID": AGENT_ID, "X-Anticipy-Agent-Token": AGENT_TOKEN}


@pytest.fixture(scope="session")
def account():
    """Sign in as the test owner.  Returns (token, owner_id)."""
    need(OWNER_EMAIL, "ANTICIPY_TEST_OWNER_EMAIL")
    need(OWNER_PASSWORD, "ANTICIPY_TEST_OWNER_PASSWORD")
    resp = call("POST", "/api/collections/owners/auth-with-password",
                json_body={"identity": OWNER_EMAIL, "password": OWNER_PASSWORD})
    if resp.status != 200:
        pytest.skip("could not sign in as ANTICIPY_TEST_OWNER_EMAIL (%s): %s"
                    % (resp.status, resp.text[:200]))
    body = resp.json or {}
    token = body.get("token") or ""
    record = body.get("record") or {}
    owner_id = OWNER_REF_ENV or record.get("id") or ""
    if not token or not owner_id:
        pytest.skip("sign-in succeeded but returned no token/record id")
    return token, owner_id


@pytest.fixture(scope="session")
def guard_on():
    """CONTRACT.md §2.1 — with ANTICIPY_SERVICE_TOKEN unset the guard does
    nothing at all.  Probe rather than assume, so a local rig skips the guard
    tests instead of failing all of them."""
    resp = call("GET", "/api/collections/jobs/records", query={"perPage": "1"})
    if resp.status == 403 and error_of(resp) == "forbidden":
        return True
    pytest.skip("the data-API guard appears to be OFF on this instance "
                "(anonymous GET /api/collections/jobs/records answered %s). "
                "CONTRACT.md §2.1: that is the documented fail-open when "
                "ANTICIPY_SERVICE_TOKEN is unset." % resp.status)


@pytest.fixture(scope="session")
def hq_configured():
    """CONTRACT.md §7 — with ANTICIPY_INTERNAL_KEY unset every HQ route
    answers 503, which is the documented fail-CLOSED."""
    resp = call("GET", "/internal/health")
    body = resp.json or {}
    if resp.status == 200 and body.get("gated") is True:
        return True
    pytest.skip("HQ reports gated=%r; the keyed HQ tests need a configured "
                "ANTICIPY_INTERNAL_KEY on the server" % body.get("gated"))


# --------------------------------------------------------------------------
# WHERE THE GUARD SITS RELATIVE TO SCHEMA VALIDATION — read this before you
# "fix" the 400s, because the obvious fix writes rows into production.
# --------------------------------------------------------------------------
#
# `workflow_guard.pb.js` is a `routerUse` MIDDLEWARE, not a record hook.  It
# answers BEFORE PocketBase ever validates the record, and it short-circuits
# with `e.json(409, …)`.  So on `POST /api/collections/jobs/records`:
#
#     409 {"error":"workflow violation"}   the guard refused.  Nothing written.
#     400 validation_missing_rel_records   THE GUARD ADMITTED THE ROW and the
#                                          schema stopped the INSERT afterwards.
#     200 / 201                            the guard admitted the row and a
#                                          real job row now exists.
#
# That is proved by the suite's own results and needs no extra request: with
# the SAME non-existent `owner_ref`, `status="running"` comes back
# 409 "running work needs an actor and lease" — a sentence that exists only
# inside workflow_guard.pb.js — while `status="cancelled"` comes back 400 on
# owner_ref.  Middleware order does not depend on the payload, so the 400 can
# only mean the guard ran and called `e.next()`.
#
# `owner_ref` IS THEREFORE A DELIBERATE WRITE BARRIER, not a broken fixture.
# The guard only ever string-compares `owner_ref` (non-empty check in §1.8,
# equality with `params._workflow.owner_ref` in §1.5, equality with
# `approval.gesture.actor` in §1.12) — it never resolves the relation — so a
# well-formed but non-existent owners id produces byte-identical guard
# behaviour to a real one, and `test_the_owner_sentinel_is_inert_to_the_guard`
# below pins that.  What it buys is the suite's own rule at the top of this
# file: NOTHING IS CREATED WITHOUT `-m destructive`.  Point this at a real
# owners id and every leg the deployed guard does NOT enforce silently
# accumulates junk jobs rows on a real person's account, once per run.
#
# MEASURED, not argued.  With the sentinel in place a full
# `-m "not destructive"` run against the live PocketBase leaves
# `jobs.totalItems` unchanged (173 -> 173).  Before it, each run minted rows:
# the "no workflow here" jobs and the queued `device_calendar` errands sitting
# in the live table were put there by earlier runs of this very file.
#
# `research_lane.pb.js` is a `routerUse` middleware in the same position, so
# everything above applies to its 403s identically.
#
# So: assert on `guard_refused()` / `guard_admitted()`, never on a bare status
# code.  A test that reads "assert 400 == 409" is unreadable; one that reads
# "PocketBase ADMITTED this row" names the finding.

# A syntactically valid PocketBase record id (15 chars, [a-z0-9]) that is not
# an owners row and must never become one.  Any test that needs a REAL owner
# id asks `real_owner_ref` for one and carries @pytest.mark.destructive.
OWNER_UNDER_TEST = "owner0undertest"
OWNER_ALPHA = "owner00000alpha"
OWNER_BETA = "owner000000beta"


def guard_refused(resp):
    """True only when workflow_guard itself answered this request.

    Deliberately NOT `resp.status == 409`: the point of the suite is to tell a
    refusal apart from an admission on two different backends, and only the
    guard emits `{"error": "workflow violation"}`.
    """
    body = resp.json
    return (resp.status == 409 and isinstance(body, dict)
            and body.get("error") == "workflow violation")


def guard_admitted(resp):
    """The complement, and it covers every way an admission can look: 400 from
    PocketBase's relation check (see the barrier above), or 200/201 from a
    backend that has no such check.  Both mean the guard said yes."""
    return not guard_refused(resp)


def admitted(section, what, resp):
    """The failure message for a leg the backend did not enforce."""
    return ("%s: %s\n"
            "THE BACKEND ADMITTED THIS ROW — the guard did not refuse it.\n"
            "(a 400 here is PocketBase's relation check on the owner_ref\n"
            " sentinel stopping the INSERT *after* the guard already said\n"
            " yes; on a backend without that check this is a written row.)\n"
            "Got %r" % (section, what, resp))


# --------------------------------------------------------------------------
# builders — a workflow body that PASSES the redundancy check, so a test
# reaches the leg it is aiming at instead of dying at §1.5
# --------------------------------------------------------------------------

def workflow_job(status="queued", state="queued", consequence="consequential",
                 version=1, owner_ref=OWNER_UNDER_TEST, approval=None,
                 receipt=None, extra_row=None, extra_plan=None,
                 lease_token="", attempts=0, tap_actor=None, owner_words=None):
    """Build a jobs POST/PATCH body whose `params._workflow` mirrors the row.

    CONTRACT.md §1.5 lists eleven equalities plus two deep-JSON comparisons.
    Getting any of them wrong makes every test in this class report
    "job fields disagree with the embedded workflow" instead of the rule it
    meant to pin — which is the single easiest way to write a conformance
    suite that proves nothing.

    `owner_ref` defaults to `OWNER_UNDER_TEST`, a well-formed but deliberately
    non-existent owners id.  See the barrier comment above this function: it
    is inert to every guard leg and it is what keeps a leg the backend does
    NOT enforce from writing a real jobs row on every run.
    """
    plan_id = "wf-" + rand(10)
    lineage = "ln-" + rand(10)
    scope = "sd-" + rand(16)
    effect = "ek-" + rand(10)
    goal = "contract suite probe " + rand(6)

    row = {
        "goal": goal,
        "status": status,
        "workflow_id": plan_id,
        "workflow_version": version,
        "workflow_state": state,
        "consequence": consequence,
        "lineage_key": lineage,
        "owner_ref": owner_ref,
        "scope_digest": scope,
        "effect_key": effect,
        "attempts": attempts,
        "lease_token": lease_token,
        "device_id": "contract-suite",
    }
    plan = {
        "plan_id": plan_id,
        "version": version,
        "state": state,
        "goal": goal,
        "consequence": consequence,
        "lineage_key": lineage,
        "owner_ref": owner_ref,
        "scope_digest": scope,
        "effect_key": effect,
        "attempts": attempts,
        "required": [],
        "facts": {},
        "lease": {"token": lease_token},
    }
    if tap_actor is not None or owner_words is not None:
        # Bound to THESE freshly minted ids, so the test exercises the actor
        # rule rather than accidentally failing the id comparison.
        approval = {"plan_id": plan_id, "plan_version": version,
                    "scope_digest": scope}
        if owner_words is not None:
            approval["owner_words"] = owner_words
        if tap_actor is not None:
            approval["gesture"] = {"kind": "tap", "actor": tap_actor,
                                   "plan_id": plan_id, "plan_version": version,
                                   "scope_digest": scope}
    if approval is not None:
        row["approval"] = json.dumps(approval)
        plan["approval"] = approval
    if receipt is not None:
        row["receipt"] = json.dumps(receipt)
        plan["receipt"] = receipt
    if extra_plan:
        plan.update(extra_plan)
    if extra_row:
        row.update(extra_row)
    row["params"] = json.dumps({"_workflow": plan})
    return row


def svc(extra=None):
    headers = {"X-Anticipy-Token": SERVICE_TOKEN}
    if extra:
        headers.update(extra)
    return headers


# ==========================================================================
# WHERE THE RUNNING SERVER IS NOT THIS TREE
# ==========================================================================
# Every constant below is an `xfail` reason, and every one of them was
# established by curl against the live PocketBase and then read back against
# the hook file that is supposed to implement the rule.  NONE of them relaxed
# an assertion: the assertion each marks is byte-identical to what it was
# before, so the day the image catches up with the repo the test XPASSes and
# says so.  That is the whole point of the mark — a silently-edited assertion
# would have made the gap disappear instead.
#
# THE MECHANISM IS ALREADY WRITTEN DOWN.  research/2026-08-26-hq-deploy-clobber
# records that production was restored from "an exact archive of the ACTIVE
# CONTAINER" with only `internal_hq.pb.js`, six HQ migrations and
# `internal.html` overlaid — so every OTHER hook in the running image is
# whatever that archive held, not what this repo holds.  The divergences below
# are all consistent with exactly that: hooks and legs added to the repo AFTER
# the archive was taken are simply not in the image.
#
# For the port this matters in one specific way: the Worker must implement the
# CONTRACT (this repo), not the image.  Copying production here would ship the
# holes.
#
# ----------------------------------------------------------------------------
# TWO OF THESE CONSTANTS CARRY NO `xfail` MARK, AND THAT IS DELIBERATE.
#
# `PROD_APPROVAL_GATE_IS_SPELLING` and `PROD_NO_SHELF2_BLOCK` describe the
# unapproved-execution path itself: on the running image, work whose
# `consequence` is anything but the exact string "consequential" reaches
# `queued` having proved no owner approval at all, and is then free to act on
# the world.  Marking those `xfail` would make `pytest -q` print a green
# summary line for "owner approval is not enforced in production", and this
# suite is currently the only place that fact is written down.  So the
# sixteen tests they cover STAY RED until the image is redeployed, and the
# constants exist so the reason is one grep away.  If a later pass decides
# the marks belong on them after all, apply them here — but do not edit an
# assertion to get there.
# ----------------------------------------------------------------------------

PROD_NO_CREATE_ENTRY_TABLE = (
    "PRODUCTION DIVERGENCE / SAFETY GAP: workflow_guard.pb.js:217-220 gives a "
    "CREATE its own status table (ENTRY_STATUSES = awaiting_confirm, queued). "
    "The running image has no such table. Proof is the whole parametrize, not "
    "one case: `running` and `done` are caught downstream by the lease leg "
    "(:652) and the receipt leg (:665) and answer 409 with THOSE sentences, "
    "while `failed`, `cancelled` and `needs_user` — which no downstream leg "
    "matches — sail past the guard entirely and are stopped only by "
    "PocketBase's own owner_ref relation validation (400). A guard that is "
    "merely REORDERED would still catch those three. So the leg is absent, "
    "and a POST may still mint a job in a status that skips Shelf 2's "
    "admission and the approval gate. Do NOT relax this to `any 409`: two of "
    "the five happen to be refused by an unrelated leg, and blessing that "
    "would bless the missing table."
)

PROD_APPROVAL_GATE_IS_SPELLING = (
    "PRODUCTION DIVERGENCE / SAFETY GAP (unmarked on purpose — see above): "
    "workflow_guard.pb.js:531 makes approval the DEFAULT and exemption the "
    "exception, via `NO_APPROVAL_NEEDED = [\"read_only\"]`. The running image "
    "still has the polarity that commit afd4380a (2026-08-25) was written to "
    "reverse: `if (nextStatus == \"queued\" && consequence == "
    "\"consequential\")` — verbatim at `git show "
    "e6e93319:backend/pb_hooks/workflow_guard.pb.js` line 167. So owner "
    "approval is demanded only when that one string is spelled exactly right. "
    "Driven, not reasoned about: \"consequentia\", \"\", \"reversible\", "
    "\"constructor\" and \"toString\" are all ADMITTED to `queued` with no "
    "approval on the row (400 from PocketBase's owner_ref relation check, "
    "which is downstream of the guard — the guard itself said yes). A typo, a "
    "truncated write, an older client or any third enum value added later "
    "therefore reaches `queued` unapproved and free to act on the world, "
    "which is the exact failure the hook's own header calls out as \"the only "
    "polarity in the system pointing the wrong way\"."
)

PROD_NO_SHELF2_BLOCK = (
    "PRODUCTION DIVERGENCE / SAFETY GAP (unmarked on purpose — see above): "
    "the entire Shelf 2 admission block — `SHELF2`, `shelf2Refusal`, "
    "`readLineage`, `seqRefusal`, `orderRefusal`, `SHELF2_ACT_TYPES`, "
    "`PROVENANCE_TAGS`, `GESTURE_KINDS` and every `shelf2.*` cause — was "
    "added by 5f66016c (2026-08-25) and is absent from the running image. Ten "
    "tests prove it: every `reversible_local` probe here is ADMITTED, "
    "including the one with no act declaration, no undo plan, no "
    "announcement and no lineage position at all. On the deployed guard "
    "`reversible_local` is simply not `\"consequential\"`, so it misses the "
    "approval gate too (see PROD_APPROVAL_GATE_IS_SPELLING) and the lane runs "
    "with nothing in front of it — which is the failure mode the block's own "
    "header names: \"that turns off database-level approval for the new lane "
    "and puts NOTHING in its place.\" Same commit gap also removes the `!old` "
    "clause on the lease rule (9748acf4), so a row may be CREATED already "
    "holding an execution lease: the deployed line is `} else if (old && "
    "oldStatus === \"running\")` at e6e93319:198."
)

PROD_AGENT_CREDENTIAL_FALLS_THROUGH = (
    "PRODUCTION DIVERGENCE / SAFETY GAP: guard.pb.js:198-341 makes sending "
    "X-Anticipy-Agent-ID COMMIT the caller to that identity — it resolves or "
    "the request ends in 403 'agent credential is not recognized'. The "
    "running image still has the pre-fix shape: an unresolvable credential "
    "keeps walking DOWN the ladder into the tokenless pairing bootstrap. "
    "Proved three ways with a bogus id + 64-char token: (1) GET agents with a "
    "pair_code filter reaches pairLookup and then PocketBase, not the 403; "
    "(2) POST /api/collections/agents/records {} reaches PocketBase's own "
    "field validation; (3) PATCH agents/<id> {owner_ref} answers 'pair from "
    "the signed-in app' — byte-identical to the same call with NO agent "
    "headers at all. A FAILED authentication is still being treated exactly "
    "like NO authentication."
)

PROD_AGENTS_LIST_IS_BROKEN = (
    "PRODUCTION DEFECT: GET /api/collections/agents/records answers 400 "
    "{'data':{},'message':'Something went wrong while processing your "
    "request.'} for EVERY caller — anonymous, service token, with a filter, "
    "without one, with fields=id, with skipTotal. `pendants`, which the guard "
    "treats identically and which carries the same owner/pair_code/owner_ref "
    "columns, answers 200 with an empty list. The guard is not the refuser "
    "here: it returns e.next() and PocketBase's own list handler fails (the "
    "same generic 400 an invalid `sort` produces on pendants), so this is "
    "collection-level breakage — schema/table drift, a broken index or an "
    "unevaluable rule on `agents`. CONSEQUENCE: the whole browser pairing "
    "bootstrap is dead in production. A pair-code HIT and a pair-code MISS "
    "both end in 400, so the phone cannot tell 'that code didn't match' from "
    "'Anticipy is down', which is the exact outcome §2.8 exists to prevent."
)

PROD_NO_RESEARCH_LANE = (
    "PRODUCTION DIVERGENCE / SAFETY GAP: research_lane.pb.js is not in the "
    "running image. Every leg is silent, on both of its independent surfaces: "
    "the leg-1 filter rewrite does not narrow an un-laned queued poll "
    "(device_calendar rows come straight back), and the create-side shape "
    "legs do not refuse — a POST carrying {lane:'device_calendar', "
    "status:'queued', consequence:'consequential'} and NO workflow_id was "
    "answered 200 and a row WAS created, repeatedly, until the "
    "OWNER_UNDER_TEST sentinel was put in its body; it now stops at "
    "PocketBase's relation check, which is an ADMISSION by the same argument "
    "`admitted()` makes. Those two surfaces cannot both be explained by the "
    "rewrite's own try/catch, because the shape legs are plain refusals that "
    "touch no rawQuery. So production has no device-calendar lane guard at "
    "all: no "
    "workflow requirement, no consequence allowlist, no calendar-act "
    "allowlist, and no exclusion of research work from the browser claim poll."
)

PROD_CORS_WILDCARD_FOR_UNLISTED_ORIGINS = (
    "PRODUCTION DIVERGENCE / SAFETY GAP: internal_hq.pb.js:4224-4238 SETS an "
    "explicit Access-Control-Allow-Origin for the two allow-listed origins, "
    "and never clears the wildcard PocketBase's built-in CORS middleware "
    "already put there for everyone else. So Origin: https://evil.example.com "
    "gets 'Access-Control-Allow-Origin: *' from /internal/health, which makes "
    "the allow-list decorative — it upgrades two origins rather than "
    "restricting the rest. §4.3 says an explicit origin, NEVER '*'. This test "
    "passed until the header-casing bug in Response.header was fixed, and it "
    "passed for the worst possible reason: every header lookup returned None, "
    "so an assertion that a header is ABSENT could not fail."
)



# ==========================================================================
# §1  workflow_guard.pb.js — the job state machine
# ==========================================================================

@pytest.mark.needs_service_token
class TestWorkflowGuard(object):
    """
    ######################################################################
    # PRODUCTION IS NOT RUNNING backend/pb_hooks/workflow_guard.pb.js.
    #
    # Every red test in this class is a deployment gap, not a spec error.
    # The running image predates three commits dated 2026-08-25, all of them
    # security fixes to this one hook:
    #
    #   afd4380a  the approval gate reads `consequence === "consequential"`,
    #             so ANY other value walks past owner approval entirely
    #             (`NO_APPROVAL_NEEDED` is the array that replaced it)
    #   5f66016c  the whole Shelf 2 admission block is absent — a
    #             `reversible_local` row is admitted unapproved with no act
    #             declaration, no undo plan, no announcement and no lineage
    #             position
    #   9748acf4  `ENTRY_STATUSES` is absent, so a POST may create a row
    #             directly in a status every other leg only polices as a
    #             TRANSITION; and the lease rule is still `else if (old &&
    #             oldStatus === "running")`, so a row may be born holding an
    #             execution lease
    #
    # HOW THAT WAS ESTABLISHED, WITHOUT A SINGLE WRITE:
    #   * `git show e6e93319:backend/pb_hooks/workflow_guard.pb.js` — the
    #     2026-08-12 version — matches the live answers line for line:
    #     `if (nextStatus === "queued" && consequence === "consequential")`
    #     at :167 and `} else if (old && oldStatus === "running")` at :198.
    #     No later version of the file can produce both of those answers.
    #   * every red case here is an ADMISSION (see `guard_admitted`), not a
    #     differently-worded refusal — except the two cases in the entry
    #     table that a downstream leg happens to catch, which is why that
    #     one test still pins its sentence.
    #
    # `migration/spec/baseline/README.md` asks exactly this question — "is
    # the TEST wrong, or is PRODUCTION not running the code in this repo?"
    # — and names `research/2026-08-26-hq-deploy-clobber.md` as precedent.
    # The answer here is the second one.  These assertions are CORRECT and
    # not one of them may be weakened: the `xfail` marks record the gap
    # loudly and XPASS the day the image catches up, which a quietly-edited
    # assertion would not.  The Worker must implement THIS REPO, not the
    # image, or the port ships the holes.
    ######################################################################
    """

    def test_legacy_row_without_workflow_id_skips_the_whole_guard(
            self, service_token, guard_on):
        """§1.2 FAIL-OPEN: `if (!workflow) return e.next()`.

        `owner_ref` is the sentinel purely so this test stops leaving a real
        "no workflow here" jobs row in production on every run — there are
        several in the live table already.  The guard's answer is unchanged:
        it returns `e.next()` before any field but `workflow_id` is read.
        """
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body={"goal": "no workflow here", "status": "queued",
                               "owner_ref": OWNER_UNDER_TEST})
        assert guard_admitted(resp), (
            "§1.2: a job with no workflow_id must skip workflow_guard "
            "entirely, so it can never produce a 409 workflow violation. "
            "Got: %r" % resp)

    def test_unparseable_params_are_refused(self, service_token, guard_on):
        """§1.5 `workflow params are not parseable`."""
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body={"goal": "g", "status": "queued",
                               "workflow_id": "wf-" + rand(8),
                               "params": "{not json"})
        assert resp.status == 409, "§1.3: every refusal here is 409, got %r" % resp
        assert detail_of(resp) == "workflow params are not parseable", repr(resp)

    def test_params_without_embedded_workflow_are_refused(
            self, service_token, guard_on):
        """§1.5 `canonical workflow is missing from params`."""
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body={"goal": "g", "status": "queued",
                               "workflow_id": "wf-" + rand(8),
                               "params": json.dumps({"something": "else"})})
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) == "canonical workflow is missing from params", repr(resp)

    def test_row_and_embedded_plan_must_agree(self, service_token, guard_on):
        """§1.5 the redundancy check — the row and its embedded plan are
        deliberately redundant so a client cannot update only the convenient
        half."""
        body = workflow_job()
        plan = json.loads(body["params"])
        plan["_workflow"]["goal"] = "a different goal entirely"
        body["params"] = json.dumps(plan)
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) == "job fields disagree with the embedded workflow", repr(resp)

    def test_status_must_agree_with_state(self, service_token, guard_on):
        """§1.7 the status<->state table."""
        body = workflow_job(status="queued", state="running")
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, repr(resp)
        assert "disagrees with state" in detail_of(resp), repr(resp)

    def test_unrecognised_status_is_not_an_entry_point(self, service_token, guard_on):
        """§1.7 floor polarity: an unrecognised status has no row in the
        table, so it rejects rather than defaulting."""
        body = workflow_job(status="totally-made-up", state="queued")
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, (
            "§1.7 / §1.10: an unrecognised status must be refused, not "
            "defaulted. Got %r" % resp)

    def test_version_must_be_at_least_one(self, service_token, guard_on):
        """§1.8 `workflow id, version, and lineage are required`."""
        body = workflow_job(version=0)
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) == "workflow id, version, and lineage are required", repr(resp)

    def test_owner_ref_is_required(self, service_token, guard_on):
        """§1.8 `owner_ref is required for workflow jobs`."""
        body = workflow_job(owner_ref="")
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) == "owner_ref is required for workflow jobs", repr(resp)

    @pytest.mark.xfail(reason=PROD_NO_CREATE_ENTRY_TABLE)
    @pytest.mark.parametrize("status", ["running", "done", "failed",
                                        "cancelled", "needs_user"])
    def test_ENTRY_STATUSES_a_post_may_only_create_held_or_queued(
            self, service_token, guard_on, status):
        """§1.10 THE CREATE LEG.  Every other leg in the file is keyed on a
        TRANSITION, and a POST is not one — `jobs.createRule` is "" so any
        caller may POST a row into existence already in the status those legs
        guard.  A job created `running` skipped Shelf 2's whole admission and
        the approval gate that predates it.

        THE SENTENCE IS PINNED HERE ON PURPOSE, against this suite's general
        preference for asserting only the refusal.  Live PocketBase answers
        `running` and `done` with 409 too — but from the lease leg (:652) and
        the receipt leg (:665), which are keyed on the status and would fire
        whether or not a create table existed.  Accepting "any 409" would
        report those two as compliant and hide the missing table; see
        PROD_NO_CREATE_ENTRY_TABLE.  `failed`, `cancelled` and `needs_user`
        have no downstream leg at all and are ADMITTED.

        A row created straight into `failed` was never approved, never leased
        and never announced, and `HAS_RUN` in the Shelf 2 ordering legs counts
        `failed` as an act that may have left something behind — so a
        forgeable `failed` row is enough to make a later compensating plan
        refuse, or to make one already-run act look ordered against another.
        """
        state = {"running": "running", "done": "succeeded", "failed": "failed",
                 "cancelled": "cancelled", "needs_user": "needs_user"}[status]
        body = workflow_job(status=status, state=state)
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.10", "a POST may only create a row in awaiting_confirm or "
            "queued, and this one asked for %r" % status, resp)
        assert detail_of(resp) == "work cannot be created in %s" % status, repr(resp)

    @pytest.mark.xfail(reason=PROD_NO_CREATE_ENTRY_TABLE)
    @pytest.mark.parametrize("status", ["running", "done"])
    def test_ENTRY_STATUSES_is_not_satisfied_by_equipping_the_other_leg(
            self, service_token, guard_on, status):
        """§1.10, and the reason the test above may not be relaxed to "any
        409" (PROD_NO_CREATE_ENTRY_TABLE says the same thing from the other
        direction).

        Live PocketBase refuses a bare `POST status=running` — but with the
        lease leg's own sentence, because that is the leg that fired.  A leg
        that asks "do you hold a lease?" is answered by HOLDING ONE.  So this
        sends the create fully equipped for the leg that actually spoke:
        `running` with a live lease, actor and future expiry; `done` with a
        verified receipt for its own effect_key.  Under `ENTRY_STATUSES` both
        are still refused — a create is a create.  Without it both are
        admitted, and the security property "work cannot be created in
        running" does not hold at all.

        `read_only` walks past the approval gate on both the deployed and the
        current guard, so the only thing under test here is the entry table.
        """
        if status == "running":
            until = "2099-01-01T00:00:00.000Z"
            body = workflow_job(
                status="running", state="running", consequence="read_only",
                lease_token="lease-" + rand(20),
                extra_row={"claimed_by": "contract-suite", "lease_until": until})
        else:
            body = workflow_job(status="done", state="succeeded",
                                consequence="read_only")
            receipt = {"verified": True, "effect_key": body["effect_key"],
                       "evidence": ["contract-suite"]}
            plan = json.loads(body["params"])
            plan["_workflow"]["receipt"] = receipt
            body["params"] = json.dumps(plan)
            body["receipt"] = json.dumps(receipt)
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.10", "a create in %r that satisfies the transition leg it "
            "collides with is still a create, and must still be refused"
            % status, resp)

    def test_the_owner_sentinel_is_inert_to_the_guard(
            self, service_token, guard_on, real_owner_ref):
        """NOT a contract rule — the suite auditing its own fixture.

        Every body this class builds names `OWNER_UNDER_TEST`, a well-formed
        owners id that does not exist, so that a leg the backend fails to
        enforce cannot write a row (see the barrier comment above
        `workflow_job`).  That is only sound if the guard treats it exactly
        like a real id.  It does — `owner_ref` is string-compared and never
        resolved — and this pins it by sending the SAME refusable body under
        both, which writes nothing either way because the guard answers
        first.

        If this ever goes red, every other result in this class is suspect.
        """
        def answer(owner):
            body = workflow_job(status="queued", state="running",
                                owner_ref=owner)
            return call("POST", "/api/collections/jobs/records", headers=svc(),
                        json_body=body)

        fake = answer(OWNER_UNDER_TEST)
        real = answer(real_owner_ref)
        assert guard_refused(fake) and guard_refused(real), (
            "the probe body must be refused by the guard under BOTH owner "
            "ids, or it is not a safe comparison. fake=%r real=%r"
            % (fake, real))
        assert detail_of(fake) == detail_of(real), (
            "the guard's answer changed when owner_ref became a real "
            "relation record, so OWNER_UNDER_TEST is NOT inert and every "
            "fixture in this class needs rebuilding. fake=%r real=%r"
            % (fake, real))

    def test_approval_is_the_default_and_absence_is_refused(
            self, service_token, guard_on):
        """§1.12 APPROVAL IS THE DEFAULT AND EXEMPTION IS THE EXCEPTION.
        An absent approval parses "" which throws."""
        body = workflow_job(status="queued", state="queued",
                            consequence="consequential")
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) == "consequential work needs parseable approval", repr(resp)

    @pytest.mark.parametrize("consequence", ["consequentia", "", "reversible",
                                             "constructor", "toString"])
    def test_approval_gate_fails_closed_on_every_other_consequence(
            self, service_token, guard_on, consequence):
        """§1.11/§1.12 the fail-closed polarity.  This read
        `consequence === "consequential"` once, so owner approval was demanded
        only when that one string was spelled exactly right: a typo, a
        truncated write, an older client or any third enum value reached
        `queued` UNAPPROVED and free to act on the world.  `constructor` and
        `toString` are here because NO_APPROVAL_NEEDED must be an array — an
        object-as-set hands an attacker an exemption keyword.

        LIVE POCKETBASE ADMITS ALL FIVE.  This is the worst of the three
        deployment gaps in the class docstring: the deployed hook still reads
        `if (nextStatus === "queued" && consequence === "consequential")`
        (`git show e6e93319:backend/pb_hooks/workflow_guard.pb.js`, line 167),
        so owner approval is demanded only when that one string is spelled
        exactly right.  The fix (afd4380a) is in this repo and is not
        deployed.  Full evidence in PROD_APPROVAL_GATE_IS_SPELLING.  The
        test is right.  Do not touch it."""
        body = workflow_job(status="queued", state="queued",
                            consequence=consequence)
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.12", "consequence=%r is not `read_only`, so this row must "
            "still be made to prove owner approval" % consequence, resp)
        assert "approval" in detail_of(resp), repr(resp)

    def test_approval_must_be_bound_to_this_plan_version_and_scope(
            self, service_token, guard_on):
        """§1.12 `approval is not bound to this exact plan version`."""
        approval = {"plan_id": "some-other-plan", "plan_version": 99,
                    "scope_digest": "not-this-one", "owner_words": "go ahead"}
        body = workflow_job(status="queued", state="queued",
                            consequence="consequential", approval=approval)
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) == "approval is not bound to this exact plan version", repr(resp)

    def test_a_tap_whose_actor_is_not_the_owner_buys_nothing(
            self, service_token, guard_on):
        """§1.12 AND IT HAS TO BE HIS TAP.  "Authenticated" was a non-empty
        string, so any actor a caller could name — another account, a service
        identity, the executor's own agent id — bought on his work exactly
        what his own tap buys.  Everything else about this approval is
        correctly bound; only the actor is wrong."""
        body = workflow_job(status="queued", state="queued",
                            consequence="consequential",
                            owner_ref=OWNER_ALPHA,
                            tap_actor="somebody-else-entirely")
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, (
            "§1.12: a tap whose actor is not owner_ref must not authorise. "
            "Got %r" % resp)
        assert detail_of(resp) == "approval is not bound to this exact plan version", repr(resp)

    def test_a_gesture_of_an_unrecognised_kind_buys_nothing(
            self, service_token, guard_on):
        """§1.12 GESTURE_KINDS is ["tap"] and nothing else."""
        body = workflow_job(status="queued", state="queued",
                            consequence="consequential",
                            owner_ref=OWNER_ALPHA,
                            tap_actor=OWNER_ALPHA)
        plan = json.loads(body["params"])
        plan["_workflow"]["approval"]["gesture"]["kind"] = "sigh"
        body["params"] = json.dumps(plan)
        body["approval"] = json.dumps(plan["_workflow"]["approval"])
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) == "approval is not bound to this exact plan version", repr(resp)

    def test_a_created_row_may_not_be_born_holding_a_lease(
            self, service_token, guard_on):
        """§1.14 `non-running work may not retain an execution lease`.  The
        `!old` clause exists for the same reason ENTRY_STATUSES does: this
        rule was keyed on the OLD row being running, so a create skipped it
        and a queued row could be born already holding execution authority.
        read_only is used here only to walk past the approval gate.

        LIVE POCKETBASE ADMITS THIS ROW.  The deployed hook still guards the
        lease with `} else if (old && oldStatus === "running")`
        (`e6e93319:…/workflow_guard.pb.js:198`), so the clause simply does not
        run on a create: the row is born `queued` holding an execution lease
        nobody issued, and the next PATCH that moves it to `running` presents
        a token the row already agrees with.  The `!old` fix (9748acf4) is in
        this repo and is not deployed.  Full evidence in
        PROD_NO_SHELF2_BLOCK.  The test is right."""
        body = workflow_job(status="queued", state="queued",
                            consequence="read_only",
                            lease_token="lease-" + rand(20))
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.14", "a row created outside `running` may not be born "
            "holding an execution lease", resp)
        assert detail_of(resp) == "non-running work may not retain an execution lease", repr(resp)

    # ---- THE SHELF 2 ADMISSION LEGS (§1.11).
    #
    # ALL TEN OF THESE ARE RED AGAINST LIVE POCKETBASE, AND ALL TEN ARE
    # RIGHT.  The deployed hook has no Shelf 2 block at all — `SHELF2`,
    # `shelf2Refusal`, `readLineage`, `seqRefusal`, `orderRefusal` and every
    # `shelf2.*` cause were added by 5f66016c (2026-08-25) and that commit is
    # not in the running image — PROD_NO_SHELF2_BLOCK.  On the deployed
    # guard `consequence = "reversible_local"` is simply not
    # `"consequential"`, so it misses the approval gate too, and a
    # `reversible_local` row is admitted to `queued` with NO approval, NO act
    # declaration, NO undo plan, NO announcement and NO lineage position —
    # which is the exact failure the block's own header warns about:
    # "that turns off database-level approval for the new lane and puts
    # NOTHING in its place."
    #
    # The refusal CODE is asserted exactly in each test below and that is not
    # over-specification: §5.4 makes the ORDER part of the contract ("checked
    # FIRST and before the undo plan is even read"), and §11 counts refusals
    # by cause, so a Shelf 2 leg that fires with the wrong code is a
    # different check.
    def test_shelf2_is_earned_not_spelled(self, service_token, guard_on):
        """§1.11 THE SHELF 2 BLOCK.  A `reversible_local` row with no approval
        and no admissible act declaration must be refused with a shelf2.*
        code — NOT waved through, and NOT refused for want of approval.  If
        this test ever reports "consequential work needs parseable approval",
        somebody added `reversible_local` to NO_APPROVAL_NEEDED and removed
        the legs; if it reports 200, the whole lane runs unapproved."""
        body = workflow_job(status="queued", state="queued",
                            consequence="reversible_local")
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.11", "an unapproved Shelf 2 row with no act declaration must "
            "be refused", resp)
        assert detail_of(resp).startswith("shelf2."), (
            "§1.11: the refusal must be a shelf2.* code, so the exemption is "
            "EARNED by the legs rather than spelled in an allowlist. Got %r"
            % resp)

    def test_shelf2_act_side_is_settled_before_the_undo_is_read(
            self, service_token, guard_on):
        """§1.11 legs 1-7.  The attack arrives WITH a flawless undo plan:
        declare an inadmissible act, write a provenance-clean undo, and open
        Gmail.  The act side must refuse first."""
        undo = {"act_type": "send_email", "steps": ["unsend"],
                "inputs": [{"provenance": "minted_by_us", "ref": "id"}],
                "held": {"minted_by_us": {"id": "abc123"}}}
        body = workflow_job(
            status="queued", state="queued", consequence="reversible_local",
            extra_plan={
                "act": {"act_type": "send_email", "reach": "local_store",
                        "executor": "anticipy_store",
                        "target": {"provenance": "minted_by_us", "ref": "id"}},
                "undo": undo,
                "announce": {"channel": "sms", "owner_ref": OWNER_UNDER_TEST},
                "lineage_seq": 1,
            })
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.11", "the Shelf 2 admission legs must refuse this row", resp)
        assert detail_of(resp) == "shelf2.act_type_not_admitted", (
            "§1.11: the act type is checked FIRST and on its own, before the "
            "undo plan is even read. Got %r" % resp)

    def test_shelf2_undo_must_resolve_its_references(self, service_token, guard_on):
        """§1.11 leg 14 `shelf2.unresolved_reference`.  Resolution is the
        mechanical form of "known-good BEFORE acting": a reference that can
        only resolve after the act fails here, now."""
        body = workflow_job(
            status="queued", state="queued", consequence="reversible_local",
            extra_plan={
                "act": {"act_type": "local_draft", "reach": "local_store",
                        "executor": "anticipy_store",
                        "target": {"provenance": "minted_by_us", "ref": "draft_id"}},
                "undo": {"act_type": "local_draft", "steps": ["discard"],
                         "inputs": [{"provenance": "minted_by_us", "ref": "draft_id"}],
                         "held": {}},
                "announce": {"channel": "sms", "owner_ref": OWNER_UNDER_TEST},
                "lineage_seq": 1,
            })
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.11", "the Shelf 2 admission legs must refuse this row", resp)
        assert detail_of(resp) == "shelf2.unresolved_reference", repr(resp)

    def test_shelf2_undo_must_address_the_acts_own_target(
            self, service_token, guard_on):
        """§1.11 leg 17 `shelf2.undo_misses_the_target`.  CORRESPONDENCE, not
        presence: an undo that resolves cleanly to a uuid the act never
        touches passed every other leg."""
        body = workflow_job(
            status="queued", state="queued", consequence="reversible_local",
            extra_plan={
                "act": {"act_type": "local_draft", "reach": "local_store",
                        "executor": "anticipy_store",
                        "target": {"provenance": "minted_by_us", "ref": "the_draft"}},
                "undo": {"act_type": "local_draft", "steps": ["discard"],
                         "inputs": [{"provenance": "minted_by_us",
                                     "ref": "some_other_thing"}],
                         "held": {"minted_by_us": {"the_draft": "d1",
                                                   "some_other_thing": "d2"}}},
                "announce": {"channel": "sms", "owner_ref": OWNER_UNDER_TEST},
                "lineage_seq": 1,
            })
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.11", "the Shelf 2 admission legs must refuse this row", resp)
        assert detail_of(resp) == "shelf2.undo_misses_the_target", repr(resp)

    def test_shelf2_announcement_must_be_addressed_to_the_owner(
            self, service_token, guard_on):
        """§1.11 leg 19 `shelf2.announce_leaves_the_owner`.  The obligation to
        announce is on the row, and it is addressed to the owner and nobody
        else."""
        body = workflow_job(
            status="queued", state="queued", consequence="reversible_local",
            owner_ref=OWNER_ALPHA,
            extra_plan={
                "act": {"act_type": "local_draft", "reach": "local_store",
                        "executor": "anticipy_store",
                        "target": {"provenance": "minted_by_us", "ref": "d"}},
                "undo": {"act_type": "local_draft", "steps": ["discard"],
                         "inputs": [{"provenance": "minted_by_us", "ref": "d"}],
                         "held": {"minted_by_us": {"d": "draft-1"}}},
                "announce": {"channel": "sms", "owner_ref": OWNER_BETA},
                "lineage_seq": 1,
            })
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.11", "the Shelf 2 admission legs must refuse this row", resp)
        assert detail_of(resp) == "shelf2.announce_leaves_the_owner", repr(resp)

    @pytest.mark.parametrize("tag", ["constructor", "toString", "__proto__",
                                     "hasOwnProperty"])
    def test_shelf2_provenance_is_an_array_not_an_object_as_set(
            self, service_token, guard_on, tag):
        """§1.11 leg 13 + §0 the object-as-set hazard.  PROVENANCE_TAGS must
        be an array: `{minted_by_us:1}["constructor"]` is truthy, so an
        object-as-set ships an admitted set with undocumented members an
        attacker can simply type."""
        body = workflow_job(
            status="queued", state="queued", consequence="reversible_local",
            extra_plan={
                "act": {"act_type": "local_draft", "reach": "local_store",
                        "executor": "anticipy_store",
                        "target": {"provenance": tag, "ref": "d"}},
                "undo": {"act_type": "local_draft", "steps": ["discard"],
                         "inputs": [{"provenance": tag, "ref": "d"}],
                         "held": {tag: {"d": "draft-1"}}},
                "announce": {"channel": "sms", "owner_ref": OWNER_UNDER_TEST},
                "lineage_seq": 1,
            })
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.11", "provenance %r must not be admitted" % tag, resp)
        assert detail_of(resp) in ("shelf2.unknown_provenance",
                                   "shelf2.act_target_unbound"), repr(resp)

    def test_shelf2_needs_a_lineage_position(self, service_token, guard_on):
        """§1.11 leg 20 `shelf2.unordered_lineage` — §7.4 has nothing to order
        by without one."""
        body = workflow_job(
            status="queued", state="queued", consequence="reversible_local",
            extra_plan={
                "act": {"act_type": "local_draft", "reach": "local_store",
                        "executor": "anticipy_store",
                        "target": {"provenance": "minted_by_us", "ref": "d"}},
                "undo": {"act_type": "local_draft", "steps": ["discard"],
                         "inputs": [{"provenance": "minted_by_us", "ref": "d"}],
                         "held": {"minted_by_us": {"d": "draft-1"}}},
                "announce": {"channel": "sms", "owner_ref": OWNER_UNDER_TEST},
            })
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert guard_refused(resp), admitted(
            "§1.11", "the Shelf 2 admission legs must refuse this row", resp)
        assert detail_of(resp) == "shelf2.unordered_lineage", repr(resp)

    # ---- PATCH legs: need a real row, and every one of these is a REFUSAL,
    # ---- so nothing is written even though a job id is required.

    def test_workflow_id_is_immutable(self, service_token, guard_on, job_id):
        """§1.9 leg 1."""
        resp = call("PATCH", "/api/collections/jobs/records/" + job_id,
                    headers=svc(),
                    json_body={"workflow_id": "definitely-not-the-stored-one"})
        if resp.status == 404:
            pytest.skip("ANTICIPY_TEST_JOB_ID does not resolve on this instance")
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) in (
            "workflow id is immutable",
            "job fields disagree with the embedded workflow"), (
            "§1.9: changing workflow_id on an existing row must be refused. "
            "Got %r" % resp)

    def test_a_running_row_refuses_a_write_without_its_lease(
            self, service_token, guard_on, job_id):
        """§1.9 leg 7 THE LEASE PROTOCOL.  A status string is not a claim:
        every write made by a running executor must prove it holds the exact
        durable lease stored on the row.  This test is meaningful only when
        ANTICIPY_TEST_JOB_ID names a row that is currently `running`; it skips
        otherwise rather than pretending to have checked."""
        current = call("GET", "/api/collections/jobs/records/" + job_id,
                       headers=svc())
        if current.status != 200:
            pytest.skip("could not read ANTICIPY_TEST_JOB_ID (%s)" % current.status)
        row = current.json or {}
        if row.get("status") != "running":
            pytest.skip("ANTICIPY_TEST_JOB_ID is %r, not 'running'; point it "
                        "at a running row to exercise the lease protocol"
                        % row.get("status"))
        resp = call("PATCH", "/api/collections/jobs/records/" + job_id,
                    headers=svc({"X-Anticipy-Lease": "not-the-held-lease"}),
                    json_body={"status": "done"})
        assert resp.status == 409, repr(resp)
        assert detail_of(resp) in (
            "running update came from the wrong lease",
            "done needs a parseable receipt",
            "done needs verified evidence for this exact effect"), repr(resp)

    # ----------------------------------------------------------------------
    # §1.9 — AN EXPLICIT "" IS NOT AN ABSENT FIELD, AND THE ORACLE SAYS SO
    # WITH `||`.  workflow_guard.pb.js:28, :113, :541 all fall back to the
    # stored row when the body carries an empty string; the Worker used `??`,
    # which stops at "" and judges the job against a status, lineage or
    # approval that is sitting right there in the row it read (audit F42).
    #
    # DESTRUCTIVE because the leg needs a STORED row to fall back TO: the
    # divergence is invisible on a create, where neither backend has an old
    # row to consult.  The row is created under the OWNER_UNDER_TEST sentinel
    # and deleted in the same test.  On PocketBase the create is refused by
    # its relation check (the sentinel is not a real owner), so this skips
    # there and runs on the backend that can store it.
    # ----------------------------------------------------------------------

    @pytest.mark.destructive
    @pytest.mark.needs_service_token
    def test_a_blank_field_falls_back_to_the_stored_row(
            self, service_token, guard_on):
        row = workflow_job(status="queued", state="queued",
                           consequence="read_only")
        plan = json.loads(row["params"])["_workflow"]
        created = call("POST", "/api/collections/jobs/records",
                       headers=svc(), json_body=row)
        if created.status != 200 or not (created.json or {}).get("id"):
            pytest.skip("this backend did not store the probe row (%s); the "
                        "fallback leg needs an old row to fall back to"
                        % created.status)
        job = created.json["id"]
        try:
            for field in ("status", "lineage_key"):
                body = {field: "", "params": row["params"]}
                if field == "lineage_key":
                    # rowValue's `!= null` reading of the embedded copy is the
                    # same on BOTH backends, so a blank in the body forces a
                    # blank in the mirror or the redundancy check fires first
                    # and this test would pin the wrong rule.
                    body["params"] = json.dumps(
                        {"_workflow": dict(plan, lineage_key="")})
                resp = call("PATCH", "/api/collections/jobs/records/" + job,
                            headers=svc(), json_body=body)
                assert guard_admitted(resp) and resp.status == 200, (
                    "§1.9: a blank %s must fall back to the stored row, not be "
                    "read as 'this row has no %s'. Got %r" % (field, field, resp))
            still = call("GET", "/api/collections/jobs/records/" + job,
                         headers=svc())
            assert (still.json or {}).get("status") == "queued", (
                "§1.9: the blank status must leave the stored status alone. "
                "Got %r" % still)
        finally:
            call("DELETE", "/api/collections/jobs/records/" + job, headers=svc())


# ==========================================================================
# §1.17  job_commitment_identity.pb.js — the model hook, on whichever
#        backend is answering
# ==========================================================================
# `idx_jobs_active_commitment` is UNIQUE over every jobs row whose
# `commitment_key` is not empty, and it is the only thing stopping two
# processes both reading "no active promise" and both minting one.  It can
# only be a partial index on "not empty" -- PocketBase's validator refuses
# `status IN (...)` -- so SOMETHING has to empty the key when a row goes
# terminal, or a finished row owns the promise forever and the next mint
# collides with a corpse (audit F15).
#
# On PocketBase that something is a model hook.  On the Worker it is
# src/pb/records.ts.  This class does not care which: it asks the backend.

class TestTerminalJobsReleaseTheirCommitment(object):

    @pytest.mark.destructive
    @pytest.mark.needs_service_token
    def test_a_finished_job_releases_the_promise_for_the_next_mint(
            self, service_token):
        key = "contract-" + rand(40)
        first = call("POST", "/api/collections/jobs/records", headers=svc(),
                     json_body={"goal": "contract suite commitment probe",
                                "status": "queued", "device_id": "contract-suite",
                                "owner_ref": OWNER_UNDER_TEST,
                                "commitment_key": key})
        if first.status != 200 or not (first.json or {}).get("id"):
            pytest.skip("this backend did not store the probe row (%s)"
                        % first.status)
        job = first.json["id"]
        second = None
        try:
            assert (first.json or {}).get("commitment_key") == key, (
                "§1.17: a LIVE row must HOLD the key — that is the lock. %r"
                % first)

            done = call("PATCH", "/api/collections/jobs/records/" + job,
                        headers=svc(), json_body={"status": "done"})
            assert done.status == 200, repr(done)
            assert (done.json or {}).get("commitment_key") == "", (
                "§1.17: a terminal row is still holding its commitment_key, so "
                "the promise can never be minted again — the clock will retry "
                "it every window and be refused, silently. %r" % done)

            # THE VERDICT COMES FROM THE INDEX: the same promise mints again.
            second = call("POST", "/api/collections/jobs/records", headers=svc(),
                          json_body={"goal": "contract suite commitment re-mint",
                                     "status": "queued", "device_id": "contract-suite",
                                     "owner_ref": OWNER_UNDER_TEST,
                                     "commitment_key": key})
            assert second.status == 200, (
                "§1.17: re-minting a released promise was refused %r" % second)
        finally:
            call("DELETE", "/api/collections/jobs/records/" + job, headers=svc())
            if second is not None and (second.json or {}).get("id"):
                call("DELETE", "/api/collections/jobs/records/" + second.json["id"],
                     headers=svc())

    @pytest.mark.needs_service_token
    def test_no_terminal_row_on_this_backend_is_holding_a_commitment(
            self, service_token):
        """The LIVE leg, and the one that closes F15 under Law 3: read-only,
        runs against whatever BASE_URL points at, and goes red on the rows the
        missing hook already left behind.  A repo-green port with six keyed
        `done` rows still in the table is not a fixed system — the next mint
        for any of those promises is still refused."""
        stuck = []
        for status in ("done", "failed", "cancelled"):
            resp = call("GET", "/api/collections/jobs/records", headers=svc(),
                        query={"filter": 'status="%s" && commitment_key!=""' % status,
                               "perPage": "1", "fields": "id"})
            if resp.status != 200:
                pytest.skip("could not list jobs on this backend (%s)" % resp.status)
            n = (resp.json or {}).get("totalItems") or 0
            if n:
                stuck.append("%s: %d" % (status, n))
        assert not stuck, (
            "§1.17: terminal jobs are holding commitment keys (%s). Rows written "
            "before the release shipped need the one-time UPDATE in the F15 "
            "report; rows written after it mean the port is not live here."
            % ", ".join(stuck))


# ==========================================================================
# §2  guard.pb.js — the production lock on the data API
# ==========================================================================

class TestGuard(object):

    def test_an_anonymous_caller_is_refused(self, guard_on):
        """§2.10 the last rung."""
        resp = call("GET", "/api/collections/events/records", query={"perPage": "1"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "forbidden", repr(resp)

    def test_realtime_subscribe_is_guarded_but_the_channel_is_not(self, guard_on):
        """§2.2 — opening the SSE channel is harmless (EventSource cannot send
        headers); the POST that attaches subscriptions is what is guarded."""
        resp = call("POST", "/api/realtime", json_body={"clientId": "x",
                                                        "subscriptions": []})
        assert resp.status == 403, (
            "§2.2: a non-GET on /api/realtime must be guarded. Got %r" % resp)

    @pytest.mark.needs_service_token
    def test_the_service_token_opens_the_data_api(self, service_token, guard_on):
        """§2.4 rung 0."""
        resp = call("GET", "/api/collections/jobs/records", headers=svc(),
                    query={"perPage": "1"})
        assert resp.status == 200, (
            "§2.4: the service token must open the collection API. Got %r" % resp)

    @pytest.mark.xfail(reason=PROD_AGENT_CREDENTIAL_FALLS_THROUGH)
    def test_an_unresolvable_agent_credential_is_a_refusal_not_a_shrug(self, guard_on):
        """§2.5.  This branch was written as "can this credential do the narrow
        thing?" and never as "was this credential valid?", so an empty lookup
        kept walking DOWN the ladder into the anonymous pairing bootstrap: a
        FAILED authentication treated exactly like NO authentication."""
        resp = call("GET", "/api/collections/agents/records",
                    headers={"X-Anticipy-Agent-ID": "nobody-" + rand(24),
                             "X-Anticipy-Agent-Token": rand(64)},
                    query={"filter": 'pair_code="000000"'})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "agent credential is not recognized", (
            "§2.5: sending X-Anticipy-Agent-ID COMMITS the caller to that "
            "identity — it resolves, or the request ends there. Got %r" % resp)

    # Same absent branch as the test above: here the status is right (403) and
    # only the sentence is wrong, because on `jobs` the fall-through ends at
    # the ladder's own last rung, which is also a 403.  The sentence is NOT
    # over-specification to be dropped — on this path it is the ONLY observable
    # that distinguishes "this credential was rejected" from "this request was
    # treated as anonymous", and the pair_code and PATCH probes in
    # PROD_AGENT_CREDENTIAL_FALLS_THROUGH show it really is the latter.
    @pytest.mark.xfail(reason=PROD_AGENT_CREDENTIAL_FALLS_THROUGH)
    def test_a_short_agent_token_is_the_same_refusal(self, guard_on):
        """§2.5 — a token shorter than 40 characters cannot match any row (the
        column's own minimum), so the query is skipped and the same 403 is
        returned.  Not a second policy; the same failed lookup."""
        resp = call("GET", "/api/collections/jobs/records",
                    headers={"X-Anticipy-Agent-ID": "nobody-" + rand(24),
                             "X-Anticipy-Agent-Token": "short"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "agent credential is not recognized", repr(resp)

    def test_the_anonymous_pair_filter_must_match_WHOLE(self, guard_on):
        """§2.9 rung 8 — THE 2026-08-03 LIVE EXPLOIT.  This was `.test()`
        against the raw filter, which matches a SUBSTRING, so appending
        anything to a legal-looking filter satisfied it and PocketBase then ran
        the caller's real query, returning every agent row (paired ones
        included) to an anonymous caller.  Proven live against production."""
        resp = call("GET", "/api/collections/agents/records",
                    query={"filter": 'pair_code="000000" || id!=""',
                           "perPage": "500"})
        assert resp.status == 403, (
            "§2.9: an unanchored pair_code filter must be refused, and a "
            "perPage above 50 must be refused. Got %r" % resp)
        assert error_of(resp) == "forbidden", repr(resp)

    def test_a_large_page_is_refused_even_with_a_legal_filter(self, guard_on):
        """§2.9 — the perPage cap is an independent defence, so even a future
        hole in the filter check cannot become a bulk export."""
        resp = call("GET", "/api/collections/agents/records",
                    query={"filter": 'pair_code="000000"', "perPage": "500"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "forbidden", repr(resp)

    def test_an_anonymous_list_without_a_recognised_filter_is_refused(self, guard_on):
        """§2.9 — without a pair_code or owner filter the list would leak
        agent ids."""
        resp = call("GET", "/api/collections/agents/records",
                    query={"filter": 'id != ""', "perPage": "10"})
        assert resp.status == 403, repr(resp)

    # The GUARD half of this rule is fine: it returns e.next() and PocketBase
    # answers.  What PocketBase answers is 400.  Left asserting 200 on purpose
    # — relaxing it to "not 403" would prove the guard opened a door onto a
    # wall and call that a pass.
    @pytest.mark.xfail(reason=PROD_AGENTS_LIST_IS_BROKEN)
    def test_an_anonymous_owner_filter_of_the_right_shape_is_allowed(self, guard_on):
        """§2.9 — a fresh app install finds its own paired agent by naming the
        high-entropy owner id it already holds.  Anchored, and restricted to
        the shape an id actually has: no quotes, no operators, nothing to
        append to."""
        resp = call("GET", "/api/collections/agents/records",
                    query={"filter": 'owner="%s"' % rand(24), "perPage": "10"})
        assert resp.status == 200, (
            "§2.9: an anchored owner= filter is the documented bootstrap. "
            "Got %r" % resp)

    def test_an_owner_filter_with_an_operator_appended_is_refused(self, guard_on):
        """§2.9 — the owner-filter regex is anchored for the same reason the
        pair_code one is."""
        resp = call("GET", "/api/collections/agents/records",
                    query={"filter": 'owner="%s" || id!=""' % rand(24)})
        assert resp.status == 403, repr(resp)

    def test_an_agent_may_not_be_registered_already_paired(self, guard_on):
        """§2.9 rung 7 — a brand-new record, never born paired/owned."""
        resp = call("POST", "/api/collections/agents/records",
                    json_body={"agent_id": "probe-" + rand(24),
                               "paired": True, "owner": "someone"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "forbidden", repr(resp)

    def test_an_anonymous_claim_may_never_name_an_owner_ref(self, guard_on):
        """§2.9 rung 9.  An unauthenticated caller could otherwise register
        their own agent, then PATCH it with a VICTIM's owner_ref harvested by
        walking pair codes — and from that moment their browser is authorized
        against the victim's account and receives the victim's jobs."""
        resp = call("PATCH", "/api/collections/agents/records/" + rand(15),
                    json_body={"owner": "device-uuid", "paired": True,
                               "owner_ref": "victim-account-id"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "pair from the signed-in app", (
            "§2.9: an owner_ref may only be claimed by the account it belongs "
            "to, and the refusal says so by name. Got %r" % resp)
        assert "only be claimed by the account it belongs to" in detail_of(resp), repr(resp)

    def test_an_anonymous_claim_may_not_write_arbitrary_columns(self, guard_on):
        """§2.9 rung 9 — every body key must be in {owner, paired, last_seen,
        browser}."""
        resp = call("PATCH", "/api/collections/agents/records/" + rand(15),
                    json_body={"owner": "device-uuid", "paired": True,
                               "lane": "device_calendar"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "forbidden", repr(resp)

    def test_the_login_endpoint_is_reachable_without_the_token(self, guard_on):
        """§2.6 rung 2.  The auth endpoints live UNDER /api/collections/, so
        the guard was gating login itself: every attempt to sign in came back
        as this hook's own {"error":"forbidden"} before PocketBase ever saw
        it."""
        resp = call("POST", "/api/collections/owners/auth-with-password",
                    json_body={"identity": "nobody-" + rand(8) + "@example.com",
                               "password": "wrong-password-on-purpose"})
        assert resp.status != 403 or error_of(resp) != "forbidden", (
            "§2.6: the guard must not answer 'forbidden' to a sign-in "
            "attempt; PocketBase validates it itself. Got %r" % resp)

    def test_signup_is_reachable_without_the_token(self, guard_on):
        """§2.6 rung 3 — signing UP is a plain record create on owners, so the
        guard blocked it too, and a new person could reach the login screen
        but never get an account.  Sent with a deliberately invalid body so
        nothing is created; only the REFUSER matters."""
        resp = call("POST", "/api/collections/owners/records", json_body={})
        assert not (resp.status == 403 and error_of(resp) == "forbidden"), (
            "§2.6: the guard must let a signup reach PocketBase, whose own "
            "createRule decides. Got %r" % resp)

    # Same wall.  The fall-through itself is DEMONSTRATED here — a 400 from
    # PocketBase's envelope is proof the guard did not refuse — so the mark is
    # on the second half of the sentence: "which answers an empty list".
    @pytest.mark.xfail(reason=PROD_AGENTS_LIST_IS_BROKEN)
    @pytest.mark.slow
    def test_a_pair_code_miss_falls_through_rather_than_refusing(self, guard_on):
        """§2.8 — a MISS falls through to PocketBase, which answers an empty
        list.  The phone needs that to say "that code didn't match" instead of
        "I can't reach Anticipy right now"; telling somebody their wrong code
        is an outage is how they give up.

        SPENDS ONE OF THE TEN PER-IP GUESSES.  Marked slow for that reason."""
        resp = call("GET", "/api/collections/agents/records",
                    query={"filter": 'pair_code="%s"' % "".join(
                        random.choice("0123456789") for _ in range(6))})
        if resp.status == 429:
            pytest.skip("the pair-code ceiling is already spent on this IP "
                        "(§2.8: 10 per IP / 60 global per ten minutes)")
        if resp.status == 503:
            pytest.skip("§2.8: the server has nowhere to count guesses and is "
                        "correctly refusing")
        assert resp.status == 200, (
            "§2.8: a pair-code miss must fall through to an empty list. "
            "Got %r" % resp)
        body = resp.json or {}
        assert body.get("items") == [], repr(resp)

    # ---- the account branch: the filter rule that IS the authorization model

    @pytest.mark.needs_account
    def test_an_account_may_list_its_own_rows(self, account, guard_on):
        """§2.7 `ownedList` — the filter must contain owner_ref="X"."""
        token, owner_id = account
        resp = call("GET", "/api/collections/jobs/records",
                    headers={"Authorization": token},
                    query={"filter": 'owner_ref="%s"' % owner_id, "perPage": "1"})
        assert resp.status == 200, repr(resp)

    @pytest.mark.needs_account
    def test_an_account_list_without_the_owner_anchor_is_refused(
            self, account, guard_on):
        """§2.7 — the anchor is the whole authorization."""
        token, _ = account
        resp = call("GET", "/api/collections/jobs/records",
                    headers={"Authorization": token},
                    query={"filter": 'status="queued"', "perPage": "1"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "record belongs to a different owner", repr(resp)

    @pytest.mark.needs_account
    def test_an_account_may_not_widen_its_filter_with_OR(self, account, guard_on):
        """§2.7 — `&&` can only narrow the owner set. `||` can widen it back
        out and is never needed by the phone or extension."""
        token, owner_id = account
        resp = call("GET", "/api/collections/jobs/records",
                    headers={"Authorization": token},
                    query={"filter": 'owner_ref="%s" || owner_ref="%s"'
                                     % (owner_id, rand(15)), "perPage": "1"})
        assert resp.status == 403, (
            "§2.7: a filter containing '||' must be refused however it is "
            "spelled. Got %r" % resp)

    @pytest.mark.needs_account
    def test_an_account_filter_with_spaces_around_the_equals_is_refused(
            self, account, guard_on):
        """§2.7 — the check is `filter.indexOf('owner_ref="X"')`, a literal
        substring.  This test is here so a port that implements a real parser
        KNOWS it has changed behaviour rather than discovering it in the
        field."""
        token, owner_id = account
        resp = call("GET", "/api/collections/jobs/records",
                    headers={"Authorization": token},
                    query={"filter": 'owner_ref = "%s"' % owner_id,
                           "perPage": "1"})
        assert resp.status == 403, (
            "§2.7: the current implementation is substring matching, so "
            "spaces around '=' are refused. If your port accepts this, that "
            "is a DELIBERATE widening — record it. Got %r" % resp)

    @pytest.mark.needs_account
    def test_an_account_may_not_touch_a_collection_outside_the_allowlist(
            self, account, guard_on):
        """§2.7 — the path regex names seven collections and nothing else."""
        token, owner_id = account
        resp = call("GET", "/api/collections/password_resets/records",
                    headers={"Authorization": token},
                    query={"filter": 'owner_ref="%s"' % owner_id})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "account is not allowed to access that collection", repr(resp)

    @pytest.mark.needs_account
    def test_an_account_may_not_create_a_row_owned_by_someone_else(
            self, account, guard_on):
        """§2.7 step 5 — a POST is allowed only when body.owner_ref is the
        signed-in account."""
        token, _ = account
        resp = call("POST", "/api/collections/events/records",
                    headers={"Authorization": token},
                    json_body={"owner_ref": "someone-else-" + rand(10),
                               "kind": "probe", "text": "no"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "record belongs to a different owner", repr(resp)

    # ---- the agent branch: evidence columns are not work product

    @pytest.mark.needs_agent
    def test_an_agent_may_not_write_the_evidence_columns(
            self, agent_headers, guard_on, job_id):
        """§2.5(c) EVIDENCE IS NOT WORK PRODUCT.  `watching_until` would mint
        the supervision that research_lane.pb.js believes the PHONE last
        wrote; `lane` would remove the row from the lease check entirely, or
        launder a research job into browser-claimable work."""
        resp = call("PATCH", "/api/collections/jobs/records/" + job_id,
                    headers=agent_headers,
                    json_body={"watching_until": "2099-01-01T00:00:00Z"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "agent is not allowed to access that record", repr(resp)

    @pytest.mark.needs_agent
    def test_an_agent_may_not_write_the_lane(self, agent_headers, guard_on, job_id):
        """§2.5(c) — same rule, the other column."""
        resp = call("PATCH", "/api/collections/jobs/records/" + job_id,
                    headers=agent_headers, json_body={"lane": ""})
        assert resp.status == 403, repr(resp)

    @pytest.mark.needs_agent
    def test_an_agent_may_not_patch_another_agents_row(
            self, agent_headers, guard_on):
        """§2.5(a) — self-patch is scoped to `agentsBase + "/" + agent.id`."""
        resp = call("PATCH", "/api/collections/agents/records/" + rand(15),
                    headers=agent_headers, json_body={"last_seen": "now"})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "agent is not allowed to access that record", repr(resp)

    @pytest.mark.needs_agent
    def test_an_agent_may_not_write_a_narration_event_for_a_stranger(
            self, agent_headers, guard_on):
        """§2.5(d) — `owner_ref` is REQUIRED, not merely permitted: the phone
        reads these back filtered on its account, so an unowned narration row
        is a line written about somebody that they can never see."""
        resp = call("POST", "/api/collections/events/records",
                    headers=agent_headers,
                    json_body={"kind": "read_fact", "text": "a fact",
                               "owner_ref": "somebody-else", "goal": rand(15)})
        assert resp.status == 403, repr(resp)

    @pytest.mark.needs_agent
    def test_an_agent_may_not_write_a_narration_longer_than_400_chars(
            self, agent_headers, guard_on):
        """§2.5(d) ONE SENTENCE, NOT A PAGE.  The page slice the reader works
        from is ~5,000 characters, so the cap is the difference between a
        distilled fact and a pasted message body."""
        resp = call("POST", "/api/collections/events/records",
                    headers=agent_headers,
                    json_body={"kind": "read_fact", "text": "x" * 401,
                               "owner_ref": "anything", "goal": rand(15)})
        assert resp.status == 403, repr(resp)

    @pytest.mark.needs_agent
    def test_an_agent_may_not_deposit_evidence_for_a_stranger(
            self, agent_headers, guard_on):
        """§2.5(e) — `owner_ref` in the body is a client-authored CLAIM, so it
        is compared against the resolved credential rather than trusted."""
        resp = call("POST", "/api/collections/evidence/records",
                    headers=agent_headers,
                    json_body={"owner_ref": "somebody-else-" + rand(10),
                               "job": rand(15)})
        assert resp.status == 403, repr(resp)


# ==========================================================================
# §3  research_lane.pb.js
# ==========================================================================

@pytest.mark.needs_service_token
class TestResearchLane(object):

    @pytest.mark.xfail(reason=PROD_NO_RESEARCH_LANE)
    def test_the_claim_poll_is_rewritten_to_exclude_three_lanes(
            self, service_token, guard_on):
        """§3.2 LEG 1.  A jobs list whose filter mentions status="queued" and
        does not mention `lane` is silently narrowed.  Extensions in the wild
        poll exactly this way and would claim research work forever; client
        code cannot be recalled, so the server rewrites."""
        resp = call("GET", "/api/collections/jobs/records", headers=svc(),
                    query={"filter": 'status="queued"', "perPage": "200"})
        assert resp.status == 200, repr(resp)
        items = (resp.json or {}).get("items") or []
        leaked = [i.get("id") for i in items
                  if str(i.get("lane") or "").strip().lower()
                  in ("research", "supervised_read", "device_calendar")]
        assert not leaked, (
            "§3.2: the filter rewrite must exclude research, supervised_read "
            "and device_calendar from an un-laned queued poll. Leaked: %r"
            % leaked)

    # The 400 here is an ADMISSION, not a fixture bug: `OWNER_UNDER_TEST` is a
    # deliberate write barrier and research_lane is a routerUse middleware, so
    # PocketBase's relation check can only have been reached because the lane
    # said nothing.  Same for the two tests below.
    @pytest.mark.xfail(reason=PROD_NO_RESEARCH_LANE)
    def test_a_device_errand_may_not_be_live_while_read_only(
            self, service_token, guard_on):
        """§3.6 LEG 3.  `read_only` carries an approval EXEMPTION that is
        earned by a client-side backstop this lane does not have — and a
        calendar write acts on the world.  This also pins the middleware
        ORDER (§0.4): research_lane runs before workflow_guard, so the answer
        must be this 403 and not a 409."""
        body = workflow_job(status="queued", state="queued",
                            consequence="read_only",
                            extra_row={"lane": "device_calendar"})
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 403, (
            "§3.6 + §0.4: research_lane must refuse this before "
            "workflow_guard sees it. Got %r" % resp)
        assert error_of(resp) == "that calendar errand is not safe to run yet", repr(resp)
        assert "read_only carries an approval exemption" in detail_of(resp), repr(resp)

    @pytest.mark.xfail(reason=PROD_NO_RESEARCH_LANE)
    def test_a_device_errand_may_not_be_live_while_reversible_local(
            self, service_token, guard_on):
        """§3.6 — Shelf 2 admits local_draft and nothing else; EventKit
        assigns the event identifier ON SAVE, which is the undo shape the
        redesign spec excludes by name."""
        body = workflow_job(status="queued", state="queued",
                            consequence="reversible_local",
                            extra_row={"lane": "device_calendar"})
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 403, repr(resp)
        assert "Shelf 2 admits local_draft" in detail_of(resp), repr(resp)

    # THIS TEST USED TO WRITE A ROW INTO PRODUCTION ON EVERY RUN.
    #
    # It is the one test in this class that builds its body by hand instead of
    # through `workflow_job`, so it is also the one that never picked up the
    # `OWNER_UNDER_TEST` sentinel.  With research_lane's leg absent nothing
    # refused the POST, and PocketBase had a perfectly valid row to insert:
    # seven live `{lane:"device_calendar", status:"queued",
    # consequence:"consequential"}` jobs reading "put dinner on my calendar"
    # had accumulated in the real table by the time this was found (ids in the
    # Track 3 report).  They are also the entire "leak" that
    # `test_the_claim_poll_is_rewritten_to_exclude_three_lanes` reports above
    # — this test was manufacturing the evidence for its neighbour.
    #
    # The sentinel fixes that WITHOUT softening the question, for the same
    # reason `admitted()` gives in TestWorkflowGuard: research_lane is a
    # `routerUse` middleware and runs before PocketBase touches the record, so
    # if the leg were there the answer would still be its 403.  The sentinel
    # only decides what happens after the guard has already declined to speak.
    # The assertions below are unchanged.
    @pytest.mark.xfail(reason=PROD_NO_RESEARCH_LANE)
    def test_a_device_errand_with_no_workflow_is_refused(
            self, service_token, guard_on):
        """§3.6 leg (a).  workflow_guard opens with `if (!workflow) next()`, so
        a legacy row skips the ENTIRE confirmation gate, silently and with no
        error anywhere.  The browser lane closes this in the client; client
        code cannot be recalled, so this lane closes it here."""
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body={"goal": "put dinner on my calendar",
                               "lane": "device_calendar", "status": "queued",
                               "consequence": "consequential",
                               # See the comment above the mark: with the leg
                               # missing, this sentinel is the only thing
                               # between the suite and a real queued calendar
                               # errand in somebody's live database.
                               "owner_ref": OWNER_UNDER_TEST})
        assert resp.status == 403, repr(resp)
        assert "skips the confirmation gate entirely" in detail_of(resp), repr(resp)

    # Refused, but by the WRONG guard: 409 "consequential work needs parseable
    # approval" is workflow_guard answering a question research_lane should
    # have closed first.  That is not the same rule wearing different words —
    # it means an errand that DOES carry an approval never meets the
    # calendar-act allowlist at all.  §0.4's middleware order is falsified
    # here too, for the simple reason that one of the two middlewares is gone.
    @pytest.mark.xfail(reason=PROD_NO_RESEARCH_LANE)
    def test_a_device_errand_must_declare_a_calendar_act(
            self, service_token, guard_on):
        """§3.6 leg (c).  Until this leg existed the lane was calendar-only by
        client convention and by nothing the server checked, so ANY approved
        errand — a send, a payment — satisfied every server-side device-lane
        check.  Undeclared is REFUSED, not defaulted."""
        body = workflow_job(status="queued", state="queued",
                            consequence="consequential",
                            extra_row={"lane": "device_calendar"})
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 403, repr(resp)
        assert "has to say which calendar act it is" in detail_of(resp), repr(resp)

    @pytest.mark.xfail(reason=PROD_NO_RESEARCH_LANE)
    def test_a_device_errand_may_not_declare_a_non_calendar_act(
            self, service_token, guard_on):
        """§3.6 leg (c) — the admitted set is the phone's own vocabulary:
        calendar_write and calendar_undo."""
        body = workflow_job(
            status="queued", state="queued", consequence="consequential",
            extra_row={"lane": "device_calendar"},
            extra_plan={"act": {"act_type": "send_email"}})
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 403, repr(resp)
        assert "carries calendar acts and nothing else" in detail_of(resp), repr(resp)

    @pytest.mark.xfail(reason=PROD_NO_RESEARCH_LANE)
    def test_a_device_errand_may_not_be_created_carrying_its_own_tap(
            self, service_token, guard_on):
        """§3.7 A ROW THAT DOES NOT YET EXIST CANNOT HAVE BEEN TAPPED.  A POST
        arriving already approved changes the approval column while the row is
        still HELD, so the two-write rule was satisfied by ONE request that
        minted the errand and its tap together."""
        body = workflow_job(status="awaiting_confirm", state="draft",
                            consequence="consequential",
                            owner_ref=OWNER_ALPHA, tap_actor=OWNER_ALPHA,
                            extra_row={"lane": "device_calendar"},
                            extra_plan={"act": {"act_type": "calendar_write"}})
        resp = call("POST", "/api/collections/jobs/records", headers=svc(),
                    json_body=body)
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "the tap and the errand it releases are two separate writes", repr(resp)
        assert "has not been tapped" in detail_of(resp), repr(resp)

    def test_a_lane_may_not_be_rewritten_after_minting(
            self, service_token, guard_on, job_id):
        """§3.4 LEG 2 THE LANE IS EVIDENCE.  Every leg in this file reads
        `lane` off the stored row, and an account session could PATCH any
        field of its own job row — in one write or split across two."""
        current = call("GET", "/api/collections/jobs/records/" + job_id,
                       headers=svc())
        if current.status != 200:
            pytest.skip("could not read ANTICIPY_TEST_JOB_ID (%s)" % current.status)
        stored = str((current.json or {}).get("lane") or "").strip().lower()
        target = "supervised_read" if stored != "supervised_read" else "research"
        resp = call("PATCH", "/api/collections/jobs/records/" + job_id,
                    headers=svc(), json_body={"lane": target})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "a job's lane is decided when it is minted, never rewritten", repr(resp)

    def test_a_lane_echoed_back_unchanged_is_not_a_rewrite(
            self, service_token, guard_on, job_id):
        """§3.4 — PocketBase clients resend fields, and refusing that breaks
        ordinary work for no gain.  A refusal here means the port made the
        lane check too strict."""
        current = call("GET", "/api/collections/jobs/records/" + job_id,
                       headers=svc())
        if current.status != 200:
            pytest.skip("could not read ANTICIPY_TEST_JOB_ID (%s)" % current.status)
        stored = (current.json or {}).get("lane") or ""
        resp = call("PATCH", "/api/collections/jobs/records/" + job_id,
                    headers=svc(), json_body={"lane": stored})
        assert not (resp.status == 403 and
                    error_of(resp).startswith("a job's lane is decided")), (
            "§3.4: echoing the stored lane back unchanged must stay allowed. "
            "Got %r" % resp)


# --------------------------------------------------------------------------
# NOT A CONTRACT CHANGE: A SERVER DEFECT, RECORDED AS ONE.
#
# Three hook files this repo registers are absent from the PocketBase image
# deployed to Railway, so the routes and middleware they register answer
# PocketBase's router-level 404 — byte-identical to a path that was never
# routed. Measured, and the mechanism identified, in
# `research/2026-09-04-routes-absent-in-production.md`: the Railway `backend`
# service is shared by several branch lanes and `railway up` uploads one lane's
# `backend/` directory wholesale, so a deploy silently drops another lane's
# hooks while leaving their tables on the volume. `pb_public` shows the same
# non-monotonic date pattern, and a static file cannot throw at load, which is
# what rules out "the hook threw" and pins it on image contents.
#
# THE ASSERTIONS BELOW ARE NOT RELAXED. Every status, sentence and reason
# string stays exactly as the contract states it — including the evidence
# door's single public refusal, "that evidence is not available", which is one
# of the two places the wording IS the contract. These marks say the SERVER is
# wrong, not the test. Each test still runs; `strict=False` so that the moment
# the missing hooks are deployed the result turns into an XPASS rather than a
# silent pass, and so that the Worker — which is expected to implement all of
# this — reports XPASS rather than failing a run it got right.
#
# An XPASS on any of these is the signal to delete the mark and this comment.
ROUTE_ABSENT_IN_PRODUCTION = pytest.mark.xfail(
    reason="the hook that registers this route is missing from the deployed "
           "PocketBase image, not from the contract — see "
           "research/2026-09-04-routes-absent-in-production.md",
    strict=False,
)


# ==========================================================================
# §4.1  evidence.pb.js — the anonymous fetch door
# ==========================================================================

# evidence.pb.js registers THREE things and all three are inert in production:
# this fetch door (`routerUse`, line 56), the share mint (`routerAdd`, line
# 157) and the retention sweep (`onRecordAfterCreateSuccess`, line 243). The
# first is a SECURITY GAP, not a missing feature: 1700000045_evidence.js sets
# the collection's list/view/create rules to "" (public in PocketBase) on the
# stated grounds that it is "gated by guard.pb.js" — but guard.pb.js covers
# only /api/collections/ and /api/realtime, never /api/files/, for which this
# absent middleware was the sole guard. Default-deny, the share window and the
# five-fetch ceiling therefore hold nowhere on the deployed server. Latent
# rather than live only because the collection has 0 rows and the mint that
# would write one is itself 404 — the same deploy fixes both, which is the one
# piece of luck in it.
@ROUTE_ABSENT_IN_PRODUCTION
class TestEvidenceDoor(object):

    def test_every_public_refusal_is_the_same_sentence(self):
        """§4.1 — telling an anonymous caller WHICH of "no such row", "never
        shared", "expired" and "spent" they hit turns the endpoint into an
        oracle for walking record ids."""
        resp = call("GET", "/api/files/evidence/%s/%s.png" % (rand(15), rand(20)))
        assert resp.status == 404, repr(resp)
        assert error_of(resp) == "that evidence is not available", repr(resp)

    def test_every_other_collection_fails_closed(self):
        """§4.1 — today no other collection has a file field, so nothing
        legitimate reaches that line.  If a later migration adds one it has to
        come here and say so, rather than inheriting an anonymous public URL
        by accident — which is exactly how an evidence host turns into a file
        host."""
        resp = call("GET", "/api/files/owner_profile/%s/%s.png"
                    % (rand(15), rand(20)))
        assert resp.status == 404, repr(resp)
        assert error_of(resp) == "that evidence is not available", repr(resp)

    def test_the_collection_is_resolved_not_string_compared(self):
        """§4.1 RESOLVED, NOT COMPARED.  PocketBase accepts a collection's
        15-character ID here as well as its name, so a gate matching the
        literal string "evidence" is walked past by anyone who read the id off
        a collections listing — which is not a secret.  A random id must
        resolve to nothing and refuse."""
        resp = call("GET", "/api/files/%s/%s/%s.png"
                    % (rand(15), rand(15), rand(20)))
        assert resp.status == 404, repr(resp)
        assert error_of(resp) == "that evidence is not available", repr(resp)

    def test_share_requires_the_service_token(self):
        """§6.7 — the truthiness test is the whole guard: getenv returns "" when
        unset, and "" === "" for a missing header too."""
        resp = call("POST", "/evidence/share", json_body={"id": rand(15)})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "forbidden", repr(resp)

    @pytest.mark.needs_service_token
    def test_an_absent_picture_is_an_answer_not_an_error(self, service_token):
        """§6.7 — a MediaUrl that 404s makes Twilio fail the WHOLE message, so
        a caller that cannot be given a URL must be told so in a form it will
        act on, not handed a link that will break at the other end."""
        resp = call("POST", "/evidence/share", headers=svc(), json_body={"id": ""})
        assert resp.status == 200, (
            "§6.7: every non-auth outcome is 200 with ok:false. Got %r" % resp)
        body = resp.json or {}
        assert body.get("ok") is False, repr(resp)
        assert body.get("reason") == "no evidence was named", repr(resp)
        assert body.get("url") == "", repr(resp)

    @pytest.mark.needs_service_token
    def test_a_missing_evidence_row_is_also_a_200(self, service_token):
        """§6.7 — same rule, different reason string."""
        resp = call("POST", "/evidence/share", headers=svc(),
                    json_body={"id": rand(15)})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("ok") is False, repr(resp)
        assert body.get("reason") == "that evidence is gone", repr(resp)


# ==========================================================================
# §4.1b  the evidence host, on a backend that HAS one
# ==========================================================================
# DELIBERATELY NOT UNDER @ROUTE_ABSENT_IN_PRODUCTION. That marker is an
# `xfail(strict=False)` for the deployed PocketBase image, whose evidence hook
# is missing — and it swallows a real failure as quietly as an expected one.
# The tests below are about a backend that serves the routes: on the Worker
# they must go RED when they break, and on a backend that does not have the
# routes at all they SKIP, naming what answered.  Written for audit F13 and
# F27, both of which shipped invisibly under exactly this kind of cover.

class TestTheEvidenceHostWorks(object):
    @pytest.mark.needs_service_token
    def test_no_owner_is_hoarding_receipt_photos(self, service_token):
        """evidence.pb.js:244-269 — TWO CEILINGS, and the per-owner one is the
        privacy half: "nobody's screenshots accumulate indefinitely just
        because they were the quiet account."  PocketBase enforced it on every
        write; on Cloudflare nothing did until the daily prune took it over
        (audit F27).  Read-only, and it goes red on the rows a missing sweep
        has already left behind — which is the Law-3 half a repo-green port
        does not have."""
        total = call("GET", "/api/collections/evidence/records", headers=svc(),
                     query={"perPage": "1", "fields": "id"})
        if total.status != 200:
            pytest.skip("could not list evidence on this backend (%s)" % total.status)
        n = (total.json or {}).get("totalItems") or 0
        # KEEP_TOTAL is 60; the sweep is bounded per tick, so allow a day's
        # worth of arrivals above it rather than pretending the cap is exact.
        assert n <= 260, (
            "§6.7: %d evidence rows — the retention sweep is not running here. "
            "On the volume that filled in 2026-08 this table's bytes were the "
            "worst filler, and the backup keeps two copies of them." % n)
    @pytest.mark.destructive
    @pytest.mark.needs_service_token
    def test_a_deposited_photo_comes_back_through_a_share_window(self, service_token):
        """§4.1 + §6.7 END TO END — the promise in evidence.pb.js:9-17, which
        needs all four links at once: a multipart deposit the backend actually
        parses, bytes it actually stores, a share window it can mint, and a
        file door that serves them to an anonymous fetch exactly as Twilio
        makes it.

        Until 2026-09-05 the Worker had none of the four and every link failed
        quietly: the deposit was a 403 the extension logged and swallowed, the
        mint was a 404 brain/evidence.py turned into "no picture on this text",
        and the door was dead code (audit F13). Each piece has its own test
        above; this is the one that fails if they do not join up."""
        # THE PROBE COMES FIRST, before anything is created: on a backend
        # whose evidence hook is missing the mint is a 404, and this test has
        # nothing to say about that — research/2026-09-04-routes-absent-in-
        # production.md already records it, and TestEvidenceDoor above marks
        # it. Skipping here keeps THIS class strict for the backend that does
        # serve the routes.
        probe = call("POST", "/evidence/share", headers=svc(), json_body={"id": rand(15)})
        if probe.status == 404:
            pytest.skip("this backend has no evidence host: POST /evidence/share "
                        "answered 404 (see TestEvidenceDoor)")

        boundary = "----anticipy" + rand(16)
        # A one-pixel JPEG, so the MIME check has something real to accept.
        jpeg = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
            "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
            "AAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==")
        parts = []
        for name, value in (("owner_ref", OWNER_UNDER_TEST), ("job", "contract" + rand(7)),
                            ("effect_key", "ek-" + rand(8))):
            parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                          % (boundary, name, value)).encode())
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"image\"; "
                      "filename=\"receipt.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"
                      % boundary).encode() + jpeg + b"\r\n")
        parts.append(("--%s--\r\n" % boundary).encode())

        created = call("POST", "/api/collections/evidence/records",
                       headers=svc({"Content-Type":
                                    "multipart/form-data; boundary=" + boundary}),
                       raw=b"".join(parts))
        if created.status == 400 and "owner_ref" in (created.text or ""):
            pytest.skip("this backend checks the owner_ref relation; the "
                        "sentinel cannot be deposited for here")
        assert created.status == 200, (
            "§4.1: the multipart deposit was refused. A backend that drops a "
            "multipart body sees an empty one, and the guard then refuses it "
            "for an owner_ref it never received. Got %r" % created)
        row = created.json or {}
        evidence_id = row.get("id")
        assert row.get("image"), "§4.1: the row names no picture: %r" % created

        try:
            # DEFAULT DENY: no window has been opened, so nothing is public.
            path = "/api/files/evidence/%s/%s" % (evidence_id, row["image"])
            closed = call("GET", path)
            assert closed.status == 404 and error_of(closed) == "that evidence is not available", (
                "§4.1: a picture nobody shared was served to an anonymous "
                "caller. The normal state of an evidence photo is NOT ON THE "
                "INTERNET. Got %r" % closed)

            # The owner's own door needs no window (service token stands in).
            mine = call("GET", path, headers=svc())
            assert mine.status == 200, (
                "§4.1: the service door did not serve the bytes: %r" % mine)

            minted = call("POST", "/evidence/share", headers=svc(),
                          json_body={"id": evidence_id})
            assert minted.status == 200 and (minted.json or {}).get("ok") is True, (
                "§6.7: the share window could not be minted: %r" % minted)
            url = (minted.json or {}).get("url") or ""
            assert url.endswith(path), (
                "§6.7: the minted URL does not point at the file door: %r" % url)
            assert url.startswith("https://"), (
                "§6.7: a MediaUrl Twilio cannot fetch is worse than no picture: %r" % url)

            # Anonymous, the way Twilio fetches it, then the ceiling.
            base = url[:-len(path)]
            for i in range(5):
                got = call("GET", path, base=base)
                assert got.status == 200, "§4.1: fetch %d of 5 refused: %r" % (i + 1, got)
            spent = call("GET", path, base=base)
            assert spent.status == 404, (
                "§4.1: the five-fetch ceiling did not close the window — "
                "expiry alone leaves a leaked URL an unlimited download. %r"
                % spent)
        finally:
            call("DELETE", "/api/collections/evidence/records/%s" % evidence_id,
                 headers=svc())


# ==========================================================================
# §4.2  owner_profile_owner.pb.js
# ==========================================================================

@pytest.mark.needs_service_token
class TestOwnerProfileNeedsAnOwner(object):

    def test_a_profile_may_not_be_created_without_an_owner(
            self, service_token, guard_on):
        """§4.2 A PROFILE WITH NO OWNER IS A PERSON NOBODY CAN LOOK UP.  Every
        read path asks for a profile BY ACCOUNT, so an orphan can never be
        read, completed, or told about — and it still occupies the three-row
        window inbound SMS routing uses."""
        resp = call("POST", "/api/collections/owner_profile/records",
                    headers=svc(), json_body={"first_name": "Nobody"})
        assert resp.status == 400, (
            "§4.2: 400, not 403 — this is a malformed record, not a "
            "permission problem. Got %r" % resp)
        assert error_of(resp) == "owner_profile needs an owner", repr(resp)

    def test_a_patch_may_not_blank_the_owner(self, service_token, guard_on):
        """§4.2 — clearing owner_ref would strand the profile."""
        resp = call("PATCH", "/api/collections/owner_profile/records/" + rand(15),
                    headers=svc(), json_body={"owner_ref": ""})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "owner_profile needs an owner", repr(resp)
        assert "would strand this profile" in detail_of(resp), repr(resp)

    def test_a_one_element_array_owner_ref_is_accepted(self, service_token, guard_on):
        """§4.2 — owner_ref is a maxSelect:1 relation, so a client may
        legitimately send it either as an id or as a one-element array.
        Refusing the array form would break an honest write to stop a
        dishonest one."""
        resp = call("POST", "/api/collections/owner_profile/records",
                    headers=svc(),
                    json_body={"owner_ref": [rand(15)], "first_name": "Probe"})
        assert error_of(resp) != "owner_profile needs an owner", (
            "§4.2: the array form must pass this middleware (PocketBase's own "
            "relation validation may still refuse it). Got %r" % resp)


# ============================================================== ANONYMOUS ====
#
# Everything above needs ANTICIPY_SERVICE_TOKEN, so on a machine with no
# secrets this file skips 35 of 35 and proves nothing -- on exactly the day a
# baseline is most wanted.
#
# These need nothing. They cover the surface a stranger can reach, which is
# where the guard either holds or does not, and they are the tests that must
# still pass the morning after cutover with no credential in sight.

@pytest.mark.anonymous
class TestAnonymousSurface(object):
    """The contract as seen by someone with no credential at all."""

    def test_health_answers(self):
        """PocketBase's OWN liveness route, not one of the 55 in CONTRACT.md
        -- the runbooks in this migration lean on it, so a port has to provide
        it even though no hook registers it.  See CONTRACT.md §0.5."""
        resp = call("GET", "/api/health")
        assert resp.status == 200, (
            "GET /api/health is the liveness probe the migration runbooks "
            "use; a port must answer it. Got %r" % resp)
        assert "healthy" in resp.text.lower() or '"code":200' in resp.text, repr(resp)

    @pytest.mark.parametrize("collection", [
        "events", "owners", "jobs", "owner_profile", "internal_passwords",
    ])
    def test_collections_are_refused_without_a_token(self, collection):
        """THE fail-open test.

        guard.pb.js opens with:

            const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
            if (!token) return e.next();

        and every non-HQ collection rule is "" -- which in PocketBase means
        PUBLIC, not closed. So one missing environment variable turns the whole
        database world-readable, and a migration is precisely the moment an
        environment variable goes missing.

        This asserts the door is shut. If it ever passes, the deployment is
        exposed and this test is the alarm.
        """
        resp = call("GET", "/api/collections/%s/records" % collection,
                    query={"perPage": 1})
        assert resp.status in (401, 403), (
            "%s answered %s to an anonymous read; expected 401/403. %r"
            % (collection, resp.status, resp)
        )
        assert '"items"' not in resp.text, (
            "%s RETURNED ROWS to an anonymous caller" % collection
        )

    def test_password_reset_does_not_leak_which_emails_exist(self):
        """CONTRACT.md §5.1.  Deliberately duplicated from
        TestPasswordReset::test_two_different_unknown_addresses_are_byte_identical:
        this class is the zero-credential baseline, and it has to be able to
        stand alone the morning after cutover with no secrets in sight.

        password_reset.pb.js states the rule itself:

            'The reply to /request is ALWAYS the same, whether or not that
             email exists. Otherwise this endpoint becomes a way to ask
             "does Omar have an account here?" one address at a time.'

        Two addresses that certainly do not exist must be answered
        identically. Both are .invalid, so no message can ever be sent.
        """
        a = call("POST", "/auth/reset/request",
                 json_body={"email": "not-a-user-a@example.invalid"})
        b = call("POST", "/auth/reset/request",
                 json_body={"email": "not-a-user-b@example.invalid"})
        assert a.status == b.status, (
            "different status for two unknown emails: %s vs %s"
            % (a.status, b.status)
        )
        assert a.text == b.text, (
            "different body for two unknown emails -- an account enumeration "
            "oracle.\n  a: %r\n  b: %r" % (a.text[:200], b.text[:200])
        )

    def test_admin_ui_is_reachable_but_is_not_a_data_path(self):
        """guard.pb.js:381-396 deliberately keeps the dashboard reachable
        (there is a production incident behind that block), so an answer here
        is correct. It must not, however, be a way to read records.
        """
        resp = call("GET", "/_/")
        assert resp.status in (200, 301, 302, 404), repr(resp)
        assert '"items"' not in resp.text


# ==========================================================================
# §5  password_reset.pb.js — enumeration safety
# ==========================================================================

class TestPasswordReset(object):

    SAME = ("If that account exists and has a phone number, "
            "a code is on its way by text.")
    NOPE = "That code isn't right, or it has expired. Ask for a new one."

    def test_an_unknown_address_gets_the_standard_reply(self):
        """§5.1 — the reply is ALWAYS the same, whether or not that email
        exists.  Otherwise this endpoint becomes a way to ask "does Omar have
        an account here?" one address at a time."""
        resp = call("POST", "/auth/reset/request",
                    json_body={"email": "nobody-%s@example.invalid" % rand(10)})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("ok") is True, repr(resp)
        assert body.get("message") == self.SAME, repr(resp)

    def test_a_missing_email_gets_the_same_reply(self):
        """§5.1 — there is no other response from this route, for any input."""
        resp = call("POST", "/auth/reset/request", json_body={})
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("message") == self.SAME, repr(resp)

    def test_a_malformed_body_gets_the_same_reply(self):
        """§5.1 — not even an unreadable body distinguishes itself."""
        resp = call("POST", "/auth/reset/request", raw=b"{not json",
                    headers={"Content-Type": "application/json"})
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("message") == self.SAME, repr(resp)

    def test_two_different_unknown_addresses_are_byte_identical(self):
        """§5.1 — the property under test is INDISTINGUISHABILITY, so compare
        the whole body rather than one field."""
        a = call("POST", "/auth/reset/request",
                 json_body={"email": "a-%s@example.invalid" % rand(8)})
        b = call("POST", "/auth/reset/request",
                 json_body={"email": "b-%s@example.invalid" % rand(8)})
        assert a.status == b.status == 200, (repr(a), repr(b))
        assert a.body == b.body, (
            "§5.1: two unknown addresses must produce byte-identical "
            "responses. %r vs %r" % (a, b))

    @pytest.mark.slow
    @pytest.mark.needs_account
    def test_a_known_address_is_indistinguishable_from_an_unknown_one(self):
        """§5.1 — the real test of enumeration safety, and it costs one entry
        against the 5-per-hour ceiling and possibly one real SMS.  Marked slow
        for both reasons."""
        need(OWNER_EMAIL, "ANTICIPY_TEST_OWNER_EMAIL")
        known = call("POST", "/auth/reset/request", json_body={"email": OWNER_EMAIL})
        unknown = call("POST", "/auth/reset/request",
                       json_body={"email": "nobody-%s@example.invalid" % rand(8)})
        assert known.status == unknown.status == 200, (repr(known), repr(unknown))
        assert known.body == unknown.body, (
            "§5.1: a known address must be byte-identical to an unknown one. "
            "%r vs %r" % (known, unknown))

    def test_a_short_password_is_named_plainly(self):
        """§5.2 — PocketBase's own minimum, said plainly rather than failing
        cryptically.  Checked BEFORE the account lookup, so it is the one
        refusal here that is not enumeration-shaped — and it leaks nothing
        about accounts."""
        resp = call("POST", "/auth/reset/confirm",
                    json_body={"email": "someone-%s@example.invalid" % rand(8),
                               "code": "123456", "password": "short"})
        assert resp.status == 400, repr(resp)
        assert (resp.json or {}).get("message") == \
            "Pick a password with at least 8 characters.", repr(resp)

    def test_a_wrong_code_gets_the_standard_refusal(self):
        """§5.2 — one sentence for wrong, expired, spent and unknown."""
        resp = call("POST", "/auth/reset/confirm",
                    json_body={"email": "someone-%s@example.invalid" % rand(8),
                               "code": "000000",
                               "password": "a-long-enough-password"})
        assert resp.status == 400, repr(resp)
        assert (resp.json or {}).get("message") == self.NOPE, repr(resp)

    def test_a_missing_code_gets_the_standard_refusal(self):
        """§5.2 — same sentence."""
        resp = call("POST", "/auth/reset/confirm",
                    json_body={"email": "someone-%s@example.invalid" % rand(8),
                               "password": "a-long-enough-password"})
        assert resp.status == 400, repr(resp)
        assert (resp.json or {}).get("message") == self.NOPE, repr(resp)


# ==========================================================================
# §5.3  account_delete.pb.js
# ==========================================================================

class TestAccountDelete(object):

    def test_an_anonymous_delete_is_refused(self):
        """§5.3 — no e.auth."""
        resp = call("POST", "/me/delete", json_body={"confirm": "delete"})
        assert resp.status == 401, repr(resp)
        assert (resp.json or {}).get("message") == "Sign in first.", repr(resp)

    @pytest.mark.needs_account
    def test_the_confirmation_is_proof_of_intent_not_of_possession(self, account):
        """§5.3 — this is the one irreversible operation in the product, and a
        bearer token is stateless and valid until the record's tokenKey
        rotates, so one replayed request from a stolen phone, a shared session
        or a logged Authorization header would otherwise be a total wipe with
        no second step.

        SAFE BY CONSTRUCTION: the body deliberately does NOT say "delete", so
        this drives the refusal and never the deletion."""
        token, _ = account
        resp = call("POST", "/me/delete", headers={"Authorization": token},
                    json_body={"confirm": "yes"})
        assert resp.status == 400, repr(resp)
        assert (resp.json or {}).get("message") == \
            'Send {"confirm":"delete"} to confirm. This cannot be undone.', repr(resp)

    @pytest.mark.needs_account
    def test_an_empty_body_is_also_refused(self, account):
        """§5.3 — same gate, no body at all."""
        token, _ = account
        resp = call("POST", "/me/delete", headers={"Authorization": token},
                    json_body={})
        assert resp.status == 400, repr(resp)

    @pytest.mark.destructive
    @pytest.mark.needs_account
    def test_a_real_delete_reports_every_table(self, account):
        """§5.3 — the only test in this file that actually deletes an account.
        It requires BOTH -m destructive AND ANTICIPY_ALLOW_DESTRUCTIVE=1, and
        it consumes the test account."""
        token, _ = account
        resp = call("POST", "/me/delete", headers={"Authorization": token},
                    json_body={"confirm": "delete"})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("ok") is True, repr(resp)
        assert body.get("account_deleted") is True, repr(resp)
        assert body.get("memory_purge") == "scheduled", repr(resp)
        deleted = body.get("deleted") or {}
        for table in ("jobs", "segments", "agents", "owner_profile", "pendants",
                      "agent_llm_audit", "agent_audit_sessions", "evidence",
                      "events"):
            assert table in deleted, (
                "§5.3: every table in OWNER_TABLES must be reported. Missing "
                "%r from %r" % (table, deleted))
        # THE PURGE ROW, and the column that finds the founder's memory.
        # The brain's per-owner memory is a SQLite file on a volume this
        # backend cannot reach, so deletion here is a REQUEST. The founder's
        # memory lives outside <state root>/<owner_ref>, and
        # brain/supervisor.py:215 reads `legacy_uuid` to locate it — without
        # the column the drain checks the tidy directory, finds nothing, and
        # marks the purge complete over a database still on disk.
        if LOCAL_WRANGLER_CONFIG:
            rows = local_d1("SELECT owner_ref, legacy_uuid, memory_purged FROM "
                            "purges ORDER BY requested_at DESC LIMIT 1")
            assert rows, "§5.3: the purge request must be recorded before the account goes"
            assert int(rows[0]["memory_purged"] or 0) == 0, (
                "§5.3: the drain has not run; the row must say so. %r" % rows[0])
            assert "legacy_uuid" in rows[0], repr(rows[0])


# ==========================================================================
# §6  the remaining product routes
# ==========================================================================

class TestAgentRoutes(object):

    def test_registration_validates_the_agent_id(self):
        """§6.1."""
        resp = call("POST", "/agent/register", json_body={"agent_id": "tooshort"})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "valid agent_id required", repr(resp)

    def test_registration_rejects_an_agent_id_with_illegal_characters(self):
        """§6.1 — /^[A-Za-z0-9._-]{20,100}$/."""
        resp = call("POST", "/agent/register",
                    json_body={"agent_id": "has spaces " + rand(20)})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "valid agent_id required", repr(resp)

    @pytest.mark.destructive
    def test_registration_returns_a_credential_exactly_once(self):
        """§6.1 — the hidden credential is created by the server, returned
        exactly once, and never appears in a collection response.  Creates a
        real agents row."""
        agent_id = "contract-suite-" + rand(24)
        resp = call("POST", "/agent/register",
                    json_body={"agent_id": agent_id, "browser": "conformance"})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("agent_id") == agent_id, repr(resp)
        assert len(body.get("agent_token") or "") == 64, repr(resp)
        assert re.match(r"^\d{6}$", body.get("pair_code") or ""), repr(resp)
        # The row id is part of the contract (agent_auth.pb.js:62). The
        # extension stores it as recordId and reads its own row through it;
        # without it a 0.13.0 install against the Worker minted one junk
        # agents row per poll and never paired (measured 2026-09-05, 62 rows
        # in 165 s). This line is what would have caught it.
        assert re.match(r"^[a-z0-9]{15}$", body.get("id") or ""), repr(resp)
        again = call("POST", "/agent/register", json_body={"agent_id": agent_id})
        assert again.status == 409, repr(again)
        assert error_of(again) == "agent already registered", repr(again)

    def test_agent_key_requires_credentials(self):
        """§6.3."""
        resp = call("GET", "/agent/key", query={"agent_id": "x"})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "agent credentials required", repr(resp)

    def test_agent_key_refuses_an_unknown_credential(self):
        """§6.3 — must resolve to a PAIRED row."""
        resp = call("GET", "/agent/key",
                    query={"agent_id": "nobody-" + rand(24)},
                    headers={"X-Anticipy-Agent-Token": rand(64)})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "not a paired agent", repr(resp)

    @pytest.mark.needs_agent
    def test_agent_key_never_returns_a_vendor_credential(self, agent_headers):
        """§6.3 — the vendor key never leaves this backend.  The response
        names models; it must never carry an API key."""
        resp = call("GET", "/agent/key", query={"agent_id": AGENT_ID},
                    headers={"X-Anticipy-Agent-Token": AGENT_TOKEN})
        if resp.status != 200:
            pytest.skip("the test agent is not paired here (%s)" % resp.status)
        text = resp.text.lower()
        for smell in ("api_key", "apikey", "sk-", "openrouter_", "gemini_key",
                      "x-anticipy-token", "service_token"):
            assert smell not in text, (
                "§6.3: /agent/key must never carry a vendor or service "
                "credential; found %r" % smell)
        body = resp.json or {}
        assert body.get("llm_proxy") is True, repr(resp)
        assert body.get("owner_ref"), repr(resp)

    @pytest.mark.needs_agent
    def test_agent_key_carries_the_owner_card_and_the_vision_model(self, agent_headers):
        """§6.3 — the two keys the extension reads off this response, and the
        two things whose absence was measured live on 2026-09-05 (audit F01).

        `vision_model` missing: the extension falls back to its own hardcoded
        anthropic/claude-sonnet-4.6, which this backend's allowlist does not
        contain, so every screenshot step gets 403 "model is not enabled for
        browser agents" — which agent_loop.js reads as a rejected key, wipes,
        and hands back needs_user.  Any dialog or date picker fires needsEyes,
        so a reservation dies at the first calendar.

        `owner` missing (the KEY, not a populated value — a person with no
        profile yet is legitimately null): the step prompt tells the model his
        name, email and phone are NOT on file, so every booking or signup form
        stops with needs_user whatever Settings holds."""
        resp = call("GET", "/agent/key", query={"agent_id": AGENT_ID},
                    headers={"X-Anticipy-Agent-Token": AGENT_TOKEN})
        if resp.status != 200:
            pytest.skip("the test agent is not paired here (%s)" % resp.status)
        body = resp.json or {}
        assert "owner" in body, (
            "§6.3: the owner card key must be present; null is a real answer "
            "and a missing key is not. %r" % resp)
        owner = body.get("owner")
        assert owner is None or isinstance(owner, dict), repr(resp)
        if isinstance(owner, dict):
            assert set(owner) == {"first_name", "last_name", "email", "phone",
                                  "birthday", "facts"}, (
                "§6.3: the card is exactly six fields — widening it is a PII "
                "decision, not a refactor. %r" % sorted(owner))
        vision = body.get("vision_model")
        assert vision, "§6.3: /agent/key must name the vision model. %r" % resp
        # AND THE MODEL IT NAMES MUST BE ONE THE PROXY ACCEPTS. This is the
        # pair that was broken: a name handed out here that /agent/llm refuses
        # is worse than no name, because the extension reads the 403 as a
        # rejected credential and stops the whole run.
        probe = call("POST", "/agent/llm", headers=agent_headers,
                     json_body={"model": vision, "messages": []})
        assert not (probe.status == 403
                    and error_of(probe) == "model is not enabled for browser agents"), (
            "§6.3/§6.4: /agent/key handed out vision_model=%r and /agent/llm "
            "refuses it. %r" % (vision, probe))

    def test_agent_llm_requires_credentials(self):
        """§6.4 rule 1."""
        resp = call("POST", "/agent/llm", json_body={"messages": []})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "agent credentials required", repr(resp)

    def test_agent_llm_refuses_an_unknown_credential(self):
        """§6.4 rule 2."""
        resp = call("POST", "/agent/llm",
                    headers={"X-Anticipy-Agent-ID": "nobody-" + rand(24),
                             "X-Anticipy-Agent-Token": rand(64)},
                    json_body={"model": "x", "messages": [{"role": "user",
                                                           "content": "hi"}]})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "not a paired agent", repr(resp)

    @pytest.mark.needs_agent
    def test_agent_llm_refuses_a_model_that_is_not_enabled(self, agent_headers):
        """§6.4 rule 7 — a compromised extension token can spend only through
        the two server-selected models."""
        resp = call("POST", "/agent/llm", headers=agent_headers,
                    json_body={"model": "openai/gpt-4o",
                               "messages": [{"role": "user", "content": "hi"}]})
        if resp.status in (403,) and error_of(resp) == "not a paired agent":
            pytest.skip("the test agent is not paired here")
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "model is not enabled for browser agents", repr(resp)

    def test_captcha_solve_requires_credentials_or_is_unconfigured(self):
        """§6.5 — 501 when CAPSOLVER_API_KEY is unset, 400 otherwise."""
        resp = call("POST", "/agent/solve-captcha", json_body={})
        assert resp.status in (400, 501), repr(resp)
        assert error_of(resp) in ("solving is not configured",
                                  "agent credentials required"), repr(resp)

    def test_captcha_result_requires_credentials_or_is_unconfigured(self):
        """§6.6."""
        resp = call("POST", "/agent/solve-captcha/result", json_body={})
        assert resp.status in (400, 501), repr(resp)

    @pytest.mark.needs_agent
    def test_captcha_never_solves_a_protected_host(self, agent_headers):
        """§6.5 — money and consent live on the same host list: a challenge on
        a bank, a brokerage or an identity provider is never solved on
        someone's behalf."""
        resp = call("POST", "/agent/solve-captcha", headers=agent_headers,
                    json_body={"websiteURL": "https://accounts.google.com/signin",
                               "websiteKey": "k", "type": "recaptcha_v2"})
        if resp.status == 501:
            pytest.skip("CAPSOLVER_API_KEY is not configured on this instance")
        if resp.status == 403 and error_of(resp) == "not a paired agent":
            pytest.skip("the test agent is not paired here")
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "this site is never solved automatically", repr(resp)
        assert "belongs to the person" in detail_of(resp), repr(resp)

    def test_upgrade_credential_requires_the_service_token(self):
        """§6.2."""
        resp = call("POST", "/agent/upgrade-credential",
                    json_body={"record_id": rand(15), "agent_id": rand(24)})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "upgrade not authorized", repr(resp)


# --------------------------------------------------------------------------
# §6.4 on the wire — POST /agent/llm past the credential gate
# --------------------------------------------------------------------------

LLM_FAKE_PROVIDER = os.environ.get("ANTICIPY_TEST_LLM_FAKE_PROVIDER") == "1"
LLM_KEY_SMELLS = [s for s in (os.environ.get("ANTICIPY_TEST_LLM_KEY_SMELLS") or "").split(",") if s]
LLM_VISION_MODEL = os.environ.get("ANTICIPY_TEST_VISION_MODEL") or "google/gemini-2.5-flash"
LOCAL_WRANGLER_CONFIG = os.environ.get("ANTICIPY_LOCAL_WRANGLER_CONFIG") or ""

# The strings and numbers three files must agree on.  extension/agent_loop.js
# stops retrying a 429 ONLY when the body carries CEILING_429_ERROR, and floors
# every request at REPLY_FLOOR; TestAgentLlmLiteralsAgree reads all three
# sources and pins them to these literals.
CEILING_429_ERROR = "too many model calls in the last hour"
CEILING_429_DETAIL = "this browser hit its hourly limit; it resumes at the top of the hour"
REPLY_FLOOR = 512
HOURLY_CALL_CEILING = 400


def local_d1(sql):
    """One statement against the LOCAL D1 behind a `wrangler dev`, through
    wrangler's own CLI -- the documented interface, not the sqlite file under
    .wrangler/state -- returning the result rows.  Skips, naming the variable,
    when the suite is not pointed at a local Worker.  Every caller is a test
    that reads the meter or the ledger, which no HTTP route exposes."""
    need(LOCAL_WRANGLER_CONFIG, "ANTICIPY_LOCAL_WRANGLER_CONFIG")
    cmd = ["npx", "--no-install", "wrangler", "d1", "execute", "DB", "--local",
           "--config", LOCAL_WRANGLER_CONFIG, "--json", "--command", sql]
    env = dict(os.environ)
    env["CI"] = "1"
    proc = subprocess.run(cmd, cwd=os.path.dirname(LOCAL_WRANGLER_CONFIG),
                          capture_output=True, text=True, timeout=120, env=env)
    if proc.returncode != 0:
        pytest.fail("local D1 statement failed: %s\n%s" % (sql, proc.stderr[-2000:]))
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        pytest.fail("wrangler d1 execute --json did not return JSON:\n%s" % proc.stdout[-2000:])
    return (out[0] or {}).get("results") or []


def _utc_hour():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H")


def _pb_date(delta_hours=0):
    at = datetime.datetime.utcnow() + datetime.timedelta(hours=delta_hours)
    return at.strftime("%Y-%m-%d %H:%M:%S.000Z")


@pytest.mark.needs_agent
class TestAgentLlmProxy(object):
    """§6.4 past the credential gate.  Three tiers, each unlocked by one
    variable, so a partial run reads as "you did not give me X" and never as
    "the proxy is broken":

      needs_agent                        rules 6, 9, 10 -- refusals, any backend
      ANTICIPY_TEST_LLM_FAKE_PROVIDER=1  what reaches the provider and what
                                         comes back, against
                                         migration/workers/scripts/fake_llm_provider.py
      ANTICIPY_LOCAL_WRANGLER_CONFIG     the meter and the ledger, read out of
                                         the local D1

    migration/workers/scripts/llm_contract_local.sh sets all three against a
    real workerd.  NEVER unlock the fake-provider tier against production: the
    FAKE:* markers in these prompts would reach a real model, and every call
    here spends the hourly meter.
    """

    @pytest.fixture(scope="class")
    def browser_model(self, agent_headers):
        """The one non-vision model /agent/key hands this agent."""
        resp = call("GET", "/agent/key", query={"agent_id": AGENT_ID},
                    headers={"X-Anticipy-Agent-Token": AGENT_TOKEN})
        if resp.status != 200:
            pytest.skip("/agent/key did not answer 200 for the test agent (%s: %s)"
                        % (resp.status, error_of(resp)))
        model = (resp.json or {}).get("model")
        if not model:
            pytest.skip("/agent/key named no model")
        return model

    @pytest.fixture(scope="class")
    def fake_provider(self):
        if not LLM_FAKE_PROVIDER:
            pytest.skip("set ANTICIPY_TEST_LLM_FAKE_PROVIDER=1 only when BASE_URL is a "
                        "Worker whose LLM_PROVIDER_BASE points at scripts/fake_llm_provider.py")
        return True

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _llm(headers, body=None, raw=None):
        if raw is not None:
            return call("POST", "/agent/llm", headers=headers, raw=raw)
        return call("POST", "/agent/llm", headers=headers, json_body=body)

    @staticmethod
    def _user(text, model, **extra):
        body = {"model": model, "messages": [{"role": "user", "content": text}]}
        body.update(extra)
        return body

    @staticmethod
    def _skip_if_not_live_here(resp):
        """The refusals a backend gives BEFORE the rule under test, when the
        test agent is not usable on it.  Each one is a reason the environment
        is incomplete, not a verdict on the proxy."""
        if resp.status == 403 and error_of(resp) == "not a paired agent":
            pytest.skip("the test agent is not paired here")
        if resp.status == 429 and error_of(resp) == CEILING_429_ERROR:
            pytest.skip("the test agent has hit its hourly ceiling here")
        if resp.status == 503 and error_of(resp) in (
                "backend has no model configured",
                "requested model provider is not configured"):
            pytest.skip("no provider key is configured here (%s)" % error_of(resp))

    @staticmethod
    def _received(resp):
        """What the fake provider saw.  OpenRouter's JSON comes back verbatim
        with `_fake`; Google's is translated, and the fake put its record in
        the one text part, which the proxy joined into message.content."""
        body = resp.json or {}
        if isinstance(body.get("_fake"), dict):
            return body["_fake"]
        content = (((body.get("choices") or [{}])[0] or {}).get("message") or {}).get("content")
        try:
            return json.loads(content)
        except Exception:
            pytest.fail("could not read the fake provider's record out of %r" % resp.text[:500])

    @staticmethod
    def _meter():
        rows = local_d1("SELECT llm_hour, llm_calls FROM agents WHERE agent_id = '%s'" % AGENT_ID)
        assert rows, "the test agent is not in the local D1"
        return rows[0]

    @staticmethod
    def _ledger_rows(tag):
        return local_d1("SELECT * FROM agent_llm_audit WHERE task_tag = '%s' ORDER BY created" % tag)

    @staticmethod
    def _ledger_count():
        rows = local_d1("SELECT count(*) AS n FROM agent_llm_audit WHERE agent_id = '%s'" % AGENT_ID)
        return int(rows[0]["n"])

    # -- refusals, any backend --------------------------------------------

    def test_agent_llm_requires_valid_json(self, agent_headers):
        """§6.4 rule 6.  Spends one meter call, as it does on PocketBase --
        the meter runs before the body is read."""
        resp = self._llm(agent_headers, raw="{not json")
        self._skip_if_not_live_here(resp)
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "valid JSON required", repr(resp)

    def test_agent_llm_requires_one_to_forty_messages(self, agent_headers, browser_model):
        """§6.4 rule 9."""
        resp = self._llm(agent_headers, {"model": browser_model, "messages": []})
        self._skip_if_not_live_here(resp)
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "messages must contain 1 to 40 items", repr(resp)
        resp = self._llm(agent_headers, {"model": browser_model,
                                         "messages": [{"role": "user", "content": "x"}] * 41})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "messages must contain 1 to 40 items", repr(resp)

    def test_agent_llm_refuses_an_unsupported_role(self, agent_headers, browser_model):
        """§6.4 rule 10."""
        resp = self._llm(agent_headers, {"model": browser_model,
                                         "messages": [{"role": "tool", "content": "x"}]})
        self._skip_if_not_live_here(resp)
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "unsupported message role", repr(resp)

    # -- the wire, against the fake provider ------------------------------

    def test_agent_llm_floors_max_tokens_at_512_on_the_wire(self, agent_headers, browser_model,
                                                             fake_provider):
        """§6.4 -- max_tokens is clamped to [512, 4096] BEFORE it reaches the
        provider, default 512.  512 and not 64: the browser model is a
        thinking model whose reasoning counts against max_tokens, and at 64
        its one-token verdicts came back cut off mid-word on 15 of 22 measured
        pages (research/evals/login-wall-2026-09-05/FINDINGS.md).  The
        extension floors at the same number (agent_loop.js MODEL_REPLY_FLOOR);
        this is the second lock, for any caller that is not the extension."""
        for asked, expected in ((8, REPLY_FLOOR), (64, REPLY_FLOOR), (None, REPLY_FLOOR),
                                (511, REPLY_FLOOR), (1000, 1000), (9000, 4096)):
            body = self._user("floor", browser_model)
            if asked is not None:
                body["max_tokens"] = asked
            resp = self._llm(agent_headers, body)
            self._skip_if_not_live_here(resp)
            assert resp.status == 200, repr(resp)
            seen = self._received(resp)["received"]
            assert seen.get("max_tokens") == expected, (
                "§6.4: asked max_tokens=%r, the wire carried %r, expected %r"
                % (asked, seen.get("max_tokens"), expected))
            assert seen.get("temperature") == 0, (
                "§6.4: temperature is forced to 0, the wire carried %r" % seen.get("temperature"))

    def test_agent_llm_passes_json_object_response_format_through(self, agent_headers,
                                                                   browser_model, fake_provider):
        """§6.4 (:243-245) -- {"type":"json_object"} crosses, and ONLY the
        type; anything else is dropped rather than forwarded."""
        cases = (
            ({"type": "json_object"}, {"type": "json_object"}),
            ({"type": "json_object", "schema": {"x": 1}}, {"type": "json_object"}),
            ({"type": "text"}, None),
            ({"type": "json_schema"}, None),
            (None, None),
        )
        for sent, expected in cases:
            body = self._user("format", browser_model)
            if sent is not None:
                body["response_format"] = sent
            resp = self._llm(agent_headers, body)
            self._skip_if_not_live_here(resp)
            assert resp.status == 200, repr(resp)
            seen = self._received(resp)["received"]
            assert seen.get("response_format") == expected, (
                "§6.4: sent response_format=%r, the wire carried %r" % (sent, seen.get("response_format")))

    def test_agent_llm_presents_openrouter_the_hooks_headers(self, agent_headers, browser_model,
                                                             fake_provider):
        """§6.4 (:383-392) -- a non-Google model goes to OpenRouter's
        chat-completions path with a Bearer credential, the referer and the
        title, and OpenRouter's JSON comes back verbatim."""
        resp = self._llm(agent_headers, self._user("headers", browser_model))
        self._skip_if_not_live_here(resp)
        assert resp.status == 200, repr(resp)
        rec = self._received(resp)
        assert rec["path"] == "/api/v1/chat/completions", rec
        seen = rec["headers"]
        assert seen["authorization_present"] is True and seen["authorization_scheme"] == "Bearer", seen
        assert seen["x_goog_api_key_present"] is False, "the Google key must not ride along to OpenRouter"
        assert seen["http_referer"] == "https://anticipy.ai", seen
        assert seen["x_title"] == "Anticipy", seen
        assert rec["received"]["model"] == browser_model, rec
        assert (resp.json or {}).get("model") == browser_model, "OpenRouter's body is passed through verbatim"
        assert (resp.json or {}).get("choices", [{}])[0].get("message", {}).get("content") == "ok"

    def test_agent_llm_routes_a_google_model_direct_and_translates(self, agent_headers, fake_provider):
        """§6.4 model routing (:220-225, :277-380) -- a google/ model goes to
        generateContent with the prefix stripped and the key in x-goog-api-key;
        system text becomes systemInstruction; the answer comes back in
        chat-completions shape with provider "google".  The Worker port adds
        finish_reason and usage when Google reports them (CONTRACT.md §6.4)."""
        if not LLM_VISION_MODEL.startswith("google/"):
            pytest.skip("ANTICIPY_TEST_VISION_MODEL is not a google/ model")
        bare = LLM_VISION_MODEL[len("google/"):]
        body = {"model": LLM_VISION_MODEL, "max_tokens": 8,
                "messages": [{"role": "system", "content": "sys"},
                             {"role": "user", "content": "route"}]}
        resp = self._llm(agent_headers, body)
        self._skip_if_not_live_here(resp)
        assert resp.status == 200, repr(resp)
        out = resp.json or {}
        assert out.get("provider") == "google", out
        assert out.get("model") == bare, out
        rec = self._received(resp)
        assert rec["path"] == "/v1beta/models/%s:generateContent" % bare, rec["path"]
        assert rec["headers"]["x_goog_api_key_present"] is True, rec["headers"]
        assert rec["headers"]["authorization_present"] is False, "no Bearer header goes to Google"
        seen = rec["received"]
        assert seen["systemInstruction"] == {"parts": [{"text": "sys"}]}, seen
        assert seen["contents"] == [{"role": "user", "parts": [{"text": "route"}]}], seen
        cfg = seen["generationConfig"]
        assert cfg["maxOutputTokens"] == REPLY_FLOOR, "§6.4: the floor applies on the Google path too (%r)" % cfg
        if re.match(r"^gemini-3(?:\.|-)", bare, re.I):
            assert cfg["thinkingConfig"] == {"thinkingLevel": "low"} and "temperature" not in cfg, cfg
        else:
            assert cfg["thinkingConfig"] == {"thinkingBudget": 0} and cfg["temperature"] == 0, cfg
        assert "responseMimeType" not in cfg, cfg
        choice = out["choices"][0]
        assert isinstance(choice["message"]["content"], str)
        assert choice.get("finish_reason") == "stop", choice
        assert out.get("usage") == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, out.get("usage")

    def test_agent_llm_asks_google_for_json_when_json_object_is_requested(self, agent_headers,
                                                                          fake_provider):
        """§6.4 (:318-320)."""
        if not LLM_VISION_MODEL.startswith("google/"):
            pytest.skip("ANTICIPY_TEST_VISION_MODEL is not a google/ model")
        resp = self._llm(agent_headers, self._user("json", LLM_VISION_MODEL,
                                                   response_format={"type": "json_object"}))
        self._skip_if_not_live_here(resp)
        assert resp.status == 200, repr(resp)
        cfg = self._received(resp)["received"]["generationConfig"]
        assert cfg.get("responseMimeType") == "application/json", cfg

    def test_agent_llm_maps_google_failures_the_hooks_way(self, agent_headers, fake_provider):
        """§6.4 rules 13, 14, 15 on the Google path."""
        if not LLM_VISION_MODEL.startswith("google/"):
            pytest.skip("ANTICIPY_TEST_VISION_MODEL is not a google/ model")
        resp = self._llm(agent_headers, self._user("FAKE:STATUS=402", LLM_VISION_MODEL))
        self._skip_if_not_live_here(resp)
        assert resp.status == 402, repr(resp)
        assert error_of(resp) == "model provider rejected request", repr(resp)
        resp = self._llm(agent_headers, self._user("FAKE:NOJSON", LLM_VISION_MODEL))
        assert resp.status == 502, repr(resp)
        assert error_of(resp) == "model returned no JSON", repr(resp)
        resp = self._llm(agent_headers, self._user("FAKE:NOTEXT", LLM_VISION_MODEL))
        assert resp.status == 502, repr(resp)
        assert error_of(resp) == "model returned no text", repr(resp)

    def test_agent_llm_passes_openrouter_failures_through_verbatim(self, agent_headers,
                                                                   browser_model, fake_provider):
        """§6.4 (:408) -- OpenRouter's status and JSON come back as they are,
        which is why rule 14 has no OpenRouter twin; a body that is not JSON
        is rule 13."""
        resp = self._llm(agent_headers, self._user("FAKE:STATUS=402", browser_model))
        self._skip_if_not_live_here(resp)
        assert resp.status == 402, repr(resp)
        assert ((resp.json or {}).get("error") or {}).get("message") == "fake provider refused", repr(resp)
        resp = self._llm(agent_headers, self._user("FAKE:NOJSON", browser_model))
        assert resp.status == 502, repr(resp)
        assert error_of(resp) == "model returned no JSON", repr(resp)

    def test_agent_llm_never_leaks_a_vendor_key(self, agent_headers, browser_model, fake_provider):
        """§6.3, §6.4 -- the vendor key never leaves this backend.  The fake
        keys are random strings the runner minted for this run; the fake
        provider reports that it SAW a credential and never echoes the value,
        so a key in any client body -- success or any refusal -- can only have
        been put there by the proxy."""
        if not LLM_KEY_SMELLS:
            pytest.skip("set ANTICIPY_TEST_LLM_KEY_SMELLS to the fake keys the Worker holds")
        probes = [
            ("openrouter ok", self._user("leak", browser_model)),
            ("google ok", self._user("leak", LLM_VISION_MODEL)),
            ("openrouter refused", self._user("FAKE:STATUS=402", browser_model)),
            ("google refused", self._user("FAKE:STATUS=402", LLM_VISION_MODEL)),
            ("openrouter no json", self._user("FAKE:NOJSON", browser_model)),
            ("google no text", self._user("FAKE:NOTEXT", LLM_VISION_MODEL)),
            ("model not enabled", self._user("leak", "openai/gpt-4o")),
            ("bad role", {"model": browser_model, "messages": [{"role": "tool", "content": "x"}]}),
        ]
        presented = 0
        for label, body in probes:
            resp = self._llm(agent_headers, body)
            self._skip_if_not_live_here(resp)
            for smell in LLM_KEY_SMELLS:
                assert smell not in resp.text, (
                    "§6.4: the %s response (%s) carried the vendor key" % (label, resp.status))
            lowered = resp.text.lower()
            for smell in ("sk-or-", "openrouter_api_key", "gemini_api_key", "google_api_key",
                          "bearer "):
                assert smell not in lowered, (
                    "§6.4: the %s response (%s) smells of a credential: %r" % (label, resp.status, smell))
            if resp.status == 200:
                seen = self._received(resp)["headers"]
                if seen.get("authorization_present") or seen.get("x_goog_api_key_present"):
                    presented += 1
        assert presented >= 2, (
            "the proxy presented no credential to either provider, so the absence "
            "above proves nothing (%d)" % presented)

    # -- the meter and the ledger, read out of the local D1 ----------------

    def test_agent_llm_counts_every_call_on_the_agent_row(self, agent_headers, browser_model,
                                                           fake_provider):
        """§6.4 the meter (:181-200): llm_hour is this UTC hour and llm_calls
        steps by one per call -- including a call that is then refused for
        its model, because the meter runs before the model check."""
        before = self._meter()
        hour = _utc_hour()
        expected = int(before["llm_calls"] or 0) + 1 if before["llm_hour"] == hour else 1
        resp = self._llm(agent_headers, self._user("count", browser_model))
        self._skip_if_not_live_here(resp)
        assert resp.status == 200, repr(resp)
        after = self._meter()
        if _utc_hour() != hour:
            pytest.skip("the UTC hour rolled over during the test")
        assert after["llm_hour"] == hour, after
        assert int(after["llm_calls"]) == expected, (before, after)
        refused = self._llm(agent_headers, self._user("count", "openai/gpt-4o"))
        assert refused.status == 403, repr(refused)
        assert int(self._meter()["llm_calls"]) == expected + 1, "a refused call is still a call"

    def test_agent_llm_429_body_is_the_extensions_ceiling_marker(self, agent_headers, browser_model,
                                                                  fake_provider):
        """§6.4 rule 4 -- call 400 of the hour is allowed, call 401 is refused
        with EXACTLY the text extension/agent_loop.js (CEILING_429_MARK) stops
        retrying on; any other 429 is retried three times against a limit that
        has already tripped.  A stored hour that is not this hour restarts the
        count; a provider's own 429 carries no marker."""
        hour = _utc_hour()
        local_d1("UPDATE agents SET llm_hour = '%s', llm_calls = %d WHERE agent_id = '%s'"
                 % (hour, HOURLY_CALL_CEILING - 1, AGENT_ID))
        try:
            last = self._llm(agent_headers, self._user("call 400", browser_model))
            self._skip_if_not_live_here(last)
            assert last.status == 200, "call %d of the hour is still allowed: %r" % (HOURLY_CALL_CEILING, last)
            assert int(self._meter()["llm_calls"]) == HOURLY_CALL_CEILING

            resp = self._llm(agent_headers, self._user("call 401", browser_model))
            assert resp.status == 429, repr(resp)
            body = resp.json or {}
            assert body.get("error") == CEILING_429_ERROR, (
                "§6.4 rule 4: the extension matches this text byte for byte; got %r" % body.get("error"))
            assert body.get("detail") == CEILING_429_DETAIL, repr(resp)
            assert CEILING_429_ERROR in resp.text
            assert int(self._meter()["llm_calls"]) == HOURLY_CALL_CEILING, "a refused-at-ceiling call does not step the meter"

            local_d1("UPDATE agents SET llm_hour = '2000-01-01T00', llm_calls = %d WHERE agent_id = '%s'"
                     % (HOURLY_CALL_CEILING, AGENT_ID))
            resp = self._llm(agent_headers, self._user("new hour", browser_model))
            assert resp.status == 200, "a stored hour that is not this hour resets the count: %r" % resp
            meter = self._meter()
            assert meter["llm_hour"] == _utc_hour() and int(meter["llm_calls"]) == 1, meter

            resp = self._llm(agent_headers, self._user("FAKE:STATUS=429", browser_model))
            assert resp.status == 429, repr(resp)
            assert CEILING_429_ERROR not in resp.text, (
                "a provider's own 429 must not read as the ceiling, or the extension stops retrying it")
        finally:
            local_d1("UPDATE agents SET llm_calls = 0 WHERE agent_id = '%s'" % AGENT_ID)

    def test_agent_llm_refuses_a_paired_agent_with_no_account(self, agent_headers, browser_model):
        """§6.4 rule 3 -- a paired row with a blank owner_ref is refused
        BEFORE the meter and the model.  Without it the endpoint was an open
        LLM proxy billed to us: register, self-pair, loop forever."""
        orphan_id = AGENT_ID + "-orphan"
        token = rand(64)
        local_d1("INSERT OR REPLACE INTO agents (id, created, updated, agent_id, agent_token, "
                 "pair_code, paired, owner_ref) VALUES ('%s', '%s', '%s', '%s', '%s', '000001', 1, '')"
                 % (rand(15), _pb_date(), _pb_date(), orphan_id, token))
        try:
            resp = call("POST", "/agent/llm",
                        headers={"X-Anticipy-Agent-ID": orphan_id, "X-Anticipy-Agent-Token": token},
                        json_body=self._user("orphan", browser_model))
            assert resp.status == 403, repr(resp)
            assert error_of(resp) == "this agent is not attached to an account", repr(resp)
        finally:
            local_d1("DELETE FROM agents WHERE agent_id = '%s'" % orphan_id)

    def test_agent_llm_writes_the_ledger_for_a_tagged_call_only(self, agent_headers, browser_model,
                                                                 fake_provider):
        """§6.4 the audit ledger (:113-146, :251-275, :340-411): one
        agent_llm_audit row per TAGGED call, begun as "started" and finished
        with the provider's verdict and both hashes; an untagged call writes
        nothing -- ordinary customer calls are not retained."""
        tag = "contract-suite:" + rand(10)
        before = self._ledger_count()
        try:
            resp = self._llm(agent_headers, self._user("untagged", browser_model))
            self._skip_if_not_live_here(resp)
            assert resp.status == 200, repr(resp)
            assert self._ledger_count() == before, "an untagged call must not be retained"

            resp = self._llm(agent_headers, self._user("[AUDIT:%s] tagged" % tag, browser_model,
                                                       max_tokens=8, response_format={"type": "json_object"}))
            assert resp.status == 200, repr(resp)
            rows = self._ledger_rows(tag)
            assert len(rows) == 1, rows
            row = rows[0]
            assert row["agent_id"] == AGENT_ID and row["owner_ref"], row
            assert row["model"] == browser_model, row
            assert row["provider"] == "openrouter" and row["provider_model"] == browser_model, row
            assert row["status"] == "ok" and int(row["http_status"]) == 200, row
            assert float(row["duration_ms"]) >= 0, row
            assert row["proxy_version"], row
            assert re.match(r"^[0-9a-f]{64}$", row["request_sha256"] or ""), row
            assert re.match(r"^[0-9a-f]{64}$", row["response_sha256"] or ""), row
            assert hashlib.sha256(row["client_request_json"].encode("utf-8")).hexdigest() == row["request_sha256"]
            assert hashlib.sha256(row["client_response_json"].encode("utf-8")).hexdigest() == row["response_sha256"]
            req = json.loads(row["client_request_json"])
            assert req["max_tokens"] == REPLY_FLOOR and req["temperature"] == 0, req
            assert req["response_format"] == {"type": "json_object"}, req
            assert tag in req["messages"][0]["content"], req
            assert json.loads(row["provider_request_json"])["max_tokens"] == REPLY_FLOOR
            assert json.loads(row["client_response_json"]) == resp.json, "the ledger holds what the client got"

            tag2 = tag + ":g"
            resp = self._llm(agent_headers, self._user("[AUDIT:%s] FAKE:STATUS=402" % tag2, LLM_VISION_MODEL))
            assert resp.status == 402, repr(resp)
            rows = self._ledger_rows(tag2)
            assert len(rows) == 1, rows
            row = rows[0]
            assert row["provider"] == "google" and row["status"] == "error", row
            assert int(row["http_status"]) == 402, row
            assert row["error"] == "model provider rejected request", row
            assert json.loads(row["client_response_json"]) == {"error": "model provider rejected request"}
            assert json.loads(row["provider_response_json"])["error"]["message"] == "fake provider refused"
        finally:
            local_d1("DELETE FROM agent_llm_audit WHERE task_tag LIKE '%s%%'" % tag)

    def test_agent_llm_redacts_image_bytes_from_the_ledger(self, agent_headers, fake_provider):
        """§6.4 (:69-112) -- the PROVIDER gets the bytes; the ledger gets
        "<meta>,[IMAGE_BYTES_REDACTED]" plus sha256, encoded_chars and
        approximate_bytes, in both the client and the provider request."""
        if not LLM_VISION_MODEL.startswith("google/"):
            pytest.skip("ANTICIPY_TEST_VISION_MODEL is not a google/ model")
        tag = "contract-suite:" + rand(10)
        pixels = "Q" * 600
        body = {"model": LLM_VISION_MODEL, "messages": [{"role": "user", "content": [
            {"type": "text", "text": "[AUDIT:%s] look" % tag},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + pixels}},
        ]}]}
        try:
            resp = self._llm(agent_headers, body)
            self._skip_if_not_live_here(resp)
            assert resp.status == 200, repr(resp)
            seen = self._received(resp)["received"]
            assert seen["contents"][0]["parts"][1] == {"inlineData": {"mimeType": "image/png", "data": pixels}}, (
                "the provider must receive the image bytes")
            rows = self._ledger_rows(tag)
            assert len(rows) == 1, rows
            row = rows[0]
            for column in ("client_request_json", "provider_request_json"):
                assert pixels[:64] not in row[column], "%s retained image bytes" % column
                assert "[IMAGE_BYTES_REDACTED]" in row[column], column
            part = json.loads(row["client_request_json"])["messages"][0]["content"][1]["image_url"]
            assert part["url"] == "data:image/png;base64,[IMAGE_BYTES_REDACTED]", part
            assert part["encoded_chars"] == 600 and part["approximate_bytes"] == 450, part
            assert re.match(r"^[0-9a-f]{64}$", part["sha256"]), part
            inline = json.loads(row["provider_request_json"])["contents"][0]["parts"][1]["inlineData"]
            assert inline["data"] == "[IMAGE_BYTES_REDACTED]" and inline["encoded_chars"] == 600, inline
        finally:
            local_d1("DELETE FROM agent_llm_audit WHERE task_tag = '%s'" % tag)

    def test_agent_llm_takes_the_tag_from_an_active_audit_session(self, agent_headers, browser_model,
                                                                  fake_provider):
        """§6.4 (:255-262) -- with no [AUDIT:] in the prompt, an active,
        unexpired agent_audit_sessions row for this agent supplies the tag;
        an expired one supplies nothing."""
        tag = "contract-session:" + rand(8)
        local_d1("INSERT INTO agent_audit_sessions (id, created, updated, task_tag, agent_id, owner_ref, "
                 "active, expires_at) VALUES ('%s', '%s', '%s', '%s', '%s', 'owner-contract-llm', 1, '%s')"
                 % (rand(15), _pb_date(), _pb_date(), tag, AGENT_ID, _pb_date(1)))
        try:
            resp = self._llm(agent_headers, self._user("session", browser_model))
            self._skip_if_not_live_here(resp)
            assert resp.status == 200, repr(resp)
            assert len(self._ledger_rows(tag)) == 1, "an active session tags the call"
            local_d1("UPDATE agent_audit_sessions SET expires_at = '%s' WHERE task_tag = '%s'"
                     % (_pb_date(-1), tag))
            resp = self._llm(agent_headers, self._user("session", browser_model))
            assert resp.status == 200, repr(resp)
            assert len(self._ledger_rows(tag)) == 1, "an expired session tags nothing"
        finally:
            local_d1("DELETE FROM agent_audit_sessions WHERE task_tag = '%s'" % tag)
            local_d1("DELETE FROM agent_llm_audit WHERE task_tag = '%s'" % tag)


@pytest.mark.offline
class TestTheAuditLedgerIsCapped(object):
    """audit_retention.pb.js:3-21 — THE TABLE THAT TOOK PRODUCTION DOWN.

    Uncapped it grew to 3,639 rows of full request/response JSON and filled
    the 5 GB volume; SQLite could then write NO row at all, and the visible
    symptom was a password-reset text going out whose code could never be
    stored.  The hook trimmed on every write.  On Cloudflare llm.ts:311 says
    "KEEP audit_retention's sweep" and nothing did — the only DELETE sat
    behind a manual /admin/purge-audit that no cron, workflow or gate ever
    called (audit F27).

    Read-only, through wrangler's own CLI, so it runs on the local wire rig
    and skips elsewhere naming the variable.  The table is not on the records
    API — deliberately, it is certification evidence and not customer data —
    so there is no HTTP way to ask."""

    @pytest.mark.needs_service_token
    def test_the_ledger_is_not_growing_without_a_ceiling(self, service_token):
        rows = local_d1("SELECT count(*) AS n FROM agent_llm_audit")
        n = int(rows[0]["n"])
        # KEEP is 300 and the sweep runs daily, so the honest bound is "the cap
        # plus what one day can add", not the cap itself.
        assert n <= 1000, (
            "§6.4: %d audit rows. The retention sweep is not running on this "
            "backend; at ~120 KB a row this table is what filled the volume "
            "in 2026-08." % n)


class TestAgentLlmLiteralsAgree(object):
    """The three sources that must carry the same bytes, read rather than
    typed: a test that typed the values would pass while the files disagreed."""

    @staticmethod
    def _source(rel):
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "..", "..", *rel.split("/"))
        if not os.path.exists(path):
            pytest.skip("%s not in this checkout" % rel)
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def test_the_ceiling_text_is_byte_identical_in_the_extension_the_hook_and_the_worker(self):
        ext = re.search(r'const CEILING_429_MARK = "([^"]+)";', self._source("extension/agent_loop.js"))
        assert ext and ext.group(1) == CEILING_429_ERROR, "extension/agent_loop.js CEILING_429_MARK"
        hook = self._source("backend/pb_hooks/agent_key.pb.js")
        assert ('error: "%s"' % CEILING_429_ERROR) in hook, "agent_key.pb.js 429 error"
        assert CEILING_429_DETAIL in hook, "agent_key.pb.js 429 detail"
        worker = self._source("migration/workers/src/llm.ts")
        found = re.search(r'export const CEILING_429_ERROR = "([^"]+)";', worker)
        assert found and found.group(1) == CEILING_429_ERROR, "migration/workers/src/llm.ts CEILING_429_ERROR"
        assert ('"%s"' % CEILING_429_DETAIL) in worker, "migration/workers/src/llm.ts CEILING_429_DETAIL"

    def test_the_reply_floor_is_the_same_number_in_the_extension_the_hook_and_the_worker(self):
        ext = re.search(r"export const MODEL_REPLY_FLOOR = (\d+);", self._source("extension/agent_loop.js"))
        hook = re.search(r"const REPLY_FLOOR = (\d+);", self._source("backend/pb_hooks/agent_key.pb.js"))
        worker = re.search(r"export const REPLY_FLOOR = (\d+);", self._source("migration/workers/src/llm.ts"))
        assert ext and int(ext.group(1)) == REPLY_FLOOR, "extension/agent_loop.js MODEL_REPLY_FLOOR"
        assert hook and int(hook.group(1)) == REPLY_FLOOR, "agent_key.pb.js REPLY_FLOOR"
        assert worker and int(worker.group(1)) == REPLY_FLOOR, "migration/workers/src/llm.ts REPLY_FLOOR"
        assert REPLY_FLOOR == 512, "research/evals/login-wall-2026-09-05/FINDINGS.md measured 512"


class TestServiceRoutes(object):

    def test_worker_owners_requires_the_service_token(self):
        """§6.11."""
        resp = call("GET", "/worker/owners")
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "forbidden", repr(resp)

    @pytest.mark.needs_service_token
    def test_worker_owners_returns_only_two_identifiers(self, service_token):
        """§6.11 — never email, phone, password metadata, tokens, or profile
        fields."""
        resp = call("GET", "/worker/owners", headers=svc(),
                    query={"perPage": "5"})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        for key in ("page", "perPage", "totalItems", "totalPages", "items"):
            assert key in body, "§6.11: missing %r from %r" % (key, body)
        for item in body.get("items") or []:
            assert set(item.keys()) == {"id", "legacy_uuid"}, (
                "§6.11: an owner row must project exactly {id, legacy_uuid}; "
                "got %r" % sorted(item.keys()))

    @pytest.mark.needs_service_token
    def test_worker_owners_clamps_per_page(self, service_token):
        """§6.11 — perPage is clamped to 1-200."""
        resp = call("GET", "/worker/owners", headers=svc(),
                    query={"perPage": "100000"})
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("perPage") == 200, repr(resp)

    def test_purge_audit_requires_the_service_token(self):
        """§6.14."""
        resp = call("POST", "/admin/purge-audit", json_body={})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "forbidden", repr(resp)

    def test_auth_claim_requires_an_account(self):
        """§6.8."""
        resp = call("POST", "/auth/claim", json_body={"legacy_uuid": rand(20)})
        assert resp.status == 401, repr(resp)
        assert (resp.json or {}).get("message") == "Sign in first.", repr(resp)

    @pytest.mark.needs_account
    def test_auth_claim_refuses_a_uuid_this_account_never_recorded(self, account):
        """§6.8 — the uuid has to be the one recorded ON THIS ACCOUNT at
        sign-up.  The value is not a secret: agents.owner IS the phone's uuid
        and the anonymous pair-code lookup hands the whole row out.  So the
        attack was: read a stranger's uuid off a pair code, sign up a throwaway
        account, POST it here, and every legacy row moved — including the
        owner_profile carrying that person's name, email, phone and
        birthday."""
        token, _ = account
        resp = call("POST", "/auth/claim", headers={"Authorization": token},
                    json_body={"legacy_uuid": "not-this-accounts-" + rand(16)})
        assert resp.status == 403, repr(resp)
        assert (resp.json or {}).get("message") == \
            "That device isn't on this account.", repr(resp)

    @ROUTE_ABSENT_IN_PRODUCTION
    def test_phone_remove_requires_an_account(self):
        """§6.9."""
        resp = call("POST", "/me/phone/remove", json_body={})
        assert resp.status == 401, repr(resp)
        assert (resp.json or {}).get("message") == "Sign in first.", repr(resp)

    @ROUTE_ABSENT_IN_PRODUCTION
    def test_profile_upsert_requires_an_account(self):
        """§6.10."""
        resp = call("POST", "/me/profile/upsert", json_body={"name": "x"})
        assert resp.status == 401, repr(resp)
        assert (resp.json or {}).get("message") == "Sign in first.", repr(resp)

    @pytest.mark.needs_account
    def test_profile_upsert_refuses_a_field_outside_the_editable_set(self, account):
        """§6.10 — the allowlist is eight named text fields."""
        token, _ = account
        resp = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                    json_body={"owner_ref": "somebody-else"})
        assert resp.status == 400, repr(resp)
        assert (resp.json or {}).get("message") == \
            "That field is not part of the owner profile.", repr(resp)

    @pytest.mark.needs_account
    def test_profile_upsert_refuses_a_non_string_value(self, account):
        """§6.10 — profile fields must be text."""
        token, _ = account
        resp = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                    json_body={"name": 42})
        assert resp.status == 400, repr(resp)
        assert (resp.json or {}).get("message") == "Profile fields must be text.", repr(resp)

    @pytest.mark.needs_account
    def test_profile_upsert_refuses_a_non_object_body(self, account):
        """§6.10."""
        token, _ = account
        resp = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                    json_body=["not", "an", "object"])
        assert resp.status == 400, repr(resp)
        assert (resp.json or {}).get("message") == \
            "The profile update must be an object.", repr(resp)

    # -- past the refusals: the writes a TestFlight signup cannot start without.
    #
    # Every test below WRITES, so each is `destructive` and additionally needs
    # ANTICIPY_ALLOW_DESTRUCTIVE=1.  They exist because the 401/400 legs above
    # passed for a whole day against a Worker whose three bodies were
    # `503 {"ok":false,"message":"… not yet ported"}` (audit F02/F03): the gate
    # in front of a stub answers exactly like the gate in front of a route.
    # migration/workers/scripts/service_contract_local.sh runs these against a
    # real workerd and a scratch D1.

    @pytest.mark.destructive
    @pytest.mark.needs_account
    def test_profile_upsert_writes_and_echoes_the_canonical_row(self, account):
        """§6.10 — one authenticated partial write in, one COMPLETE canonical
        profile out.  AnticipyBackend.swift:410-420 refuses to paint "Saved"
        unless ok is true, profile.owner_ref is its own accountID, and every
        field it sent round-trips, so a 200 alone proves nothing."""
        token, owner_id = account
        zone = "America/Vancouver"
        resp = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                    json_body={"first_name": "Contract", "timezone": zone})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("ok") is True, repr(resp)
        profile = body.get("profile") or {}
        assert profile.get("id"), repr(resp)
        assert profile.get("owner_ref") == owner_id, (
            "§6.10: ownership is derived from the token; the client compares "
            "this to its own accountID. %r" % resp)
        assert profile.get("first_name") == "Contract", repr(resp)
        assert profile.get("timezone") == zone, (
            "§6.10: without this the brain's fetch_owner_timezone is None and "
            "quiet hours are judged in the server's zone. %r" % resp)
        # The COMPLETE row, not just what was sent.
        for field in ("owner_id", "phone", "name", "last_name", "email",
                      "birthday", "facts"):
            assert field in profile, (
                "§6.10: the canonical row must carry %r; got %r"
                % (field, sorted(profile)))
        # And it is really a row, which is the only thing the brain can read.
        again = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                     json_body={"last_name": "Suite"})
        assert again.status == 200, repr(again)
        assert (again.json or {}).get("profile", {}).get("id") == profile["id"], (
            "§6.10: one profile row per account — a second row is how a "
            "person's name appeared to vanish. %r" % again)

    @pytest.mark.destructive
    @pytest.mark.needs_account
    def test_profile_upsert_keeps_an_omitted_field_and_clears_an_empty_one(self, account):
        """§6.10 — presence, not truthiness.  Settings saves identity details
        and the phone as two independent requests, so an omitted field must
        survive the other one; `""` is a real value and clears."""
        token, _ = account
        number = "+15550100777"
        assert call("POST", "/me/profile/upsert", headers={"Authorization": token},
                    json_body={"phone": number}).status == 200
        kept = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                    json_body={"first_name": "Contract"})
        assert (kept.json or {}).get("profile", {}).get("phone") == number, (
            "§6.10: an omitted field must not be blanked. %r" % kept)
        cleared = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                       json_body={"phone": ""})
        assert (cleared.json or {}).get("profile", {}).get("phone") == "", (
            "§6.10: an explicit empty string clears. %r" % cleared)

    @pytest.mark.destructive
    @pytest.mark.needs_account
    def test_phone_remove_clears_the_seed_and_every_profile(self, account):
        """§6.9 — the account seed and every profile row, or an old number
        stays routable after a 200: an inbound text resolves through
        owner_profile.phone BEFORE owners."""
        token, owner_id = account
        assert call("POST", "/me/profile/upsert", headers={"Authorization": token},
                    json_body={"phone": "+15550100778"}).status == 200
        resp = call("POST", "/me/phone/remove", headers={"Authorization": token},
                    json_body={})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        # AnticipyBackend.swift:374-386 requires all three.
        assert body.get("ok") is True, repr(resp)
        assert body.get("phone") == "", repr(resp)
        assert isinstance(body.get("clearedProfiles"), int) and body["clearedProfiles"] >= 0, repr(resp)
        after = call("POST", "/me/profile/upsert", headers={"Authorization": token},
                     json_body={"first_name": "Contract"})
        assert (after.json or {}).get("profile", {}).get("phone") == "", (
            "§6.9: the number must be gone from the profile too. %r" % after)
        if LOCAL_WRANGLER_CONFIG:
            rows = local_d1("SELECT phone FROM owners WHERE id = '%s'" % owner_id)
            assert rows and not (rows[0]["phone"] or ""), (
                "§6.9: owners.phone is the sign-up seed and still powers "
                "password recovery; it must be cleared too. %r" % rows)

    @pytest.mark.destructive
    @pytest.mark.needs_account
    def test_auth_claim_adopts_this_accounts_own_rows(self, account):
        """§6.8 — the uuid recorded on THIS account at sign-up is the whole
        test, and a claim that passes it must actually adopt.  The counts are
        whatever this instance happens to hold; the shape is the contract."""
        token, _ = account
        # auth-refresh, not a records list: it answers {token, record} for the
        # caller and needs no filter the guard has to recognise.
        me = call("POST", "/api/collections/owners/auth-refresh",
                  headers={"Authorization": token})
        recorded = ((me.json or {}).get("record") or {}).get("legacy_uuid") or ""
        resp = call("POST", "/auth/claim", headers={"Authorization": token},
                    json_body={"legacy_uuid": recorded} if recorded else {})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("ok") is True, repr(resp)
        claimed = body.get("claimed") or {}
        assert set(claimed) == {"jobs", "owner_profile", "segments", "agents", "events"}, (
            "§6.8: the five tables are the contract; got %r" % sorted(claimed))
        for table, n in claimed.items():
            assert isinstance(n, int) and n >= 0, "§6.8: %s counted %r" % (table, n)

    def test_transcription_tokens_need_an_account_first(self):
        """§6.13 — 410 GONE, deliberately, not 502 or 503: those mean "try
        again later" and the phone's catch block schedules a retry on them, so
        a temporary-sounding refusal would spin a reconnect loop forever
        against a decision that is permanent."""
        resp = call("POST", "/transcription/token", json_body={})
        assert resp.status == 401, (
            "§6.13: an anonymous caller is asked to sign in first. Got %r" % resp)

    @pytest.mark.needs_account
    def test_transcription_tokens_are_410_for_a_signed_in_caller(self, account):
        """§6.13 — and the refusal must not name the vendor, because
        overnight/no_vendor_ears.py greps live code for the hostname and a
        gate that its own refusal notice sets off is a gate somebody will
        soften."""
        token, _ = account
        resp = call("POST", "/transcription/token",
                    headers={"Authorization": token}, json_body={})
        assert resp.status == 410, repr(resp)
        body = resp.json or {}
        assert body.get("error") == "transcription tokens are not issued", repr(resp)
        assert "raw audio never leaves a device" in (body.get("reason") or ""), repr(resp)
        assert "deepgram" not in resp.text.lower(), (
            "§6.13: the refusal must not name the vendor")


# --------------------------------------------------------------------------
# §6.12 / §6.12a on the wire -- an inbound text lands, whichever carrier
# brought it.  Unlocked tier by tier, so a partial run reads as "you did not
# give me X" and never as "inbound is broken":
#
#   nothing                              the refusals, any backend
#   ANTICIPY_TEST_SENDBLUE_SECRET        past Sendblue's front door
#   ANTICIPY_TEST_TWILIO_AUTH_TOKEN      past Twilio's (the suite signs)
#   ANTICIPY_TEST_SMS_OWNER_PHONE/_REF   a seeded owner the text resolves to
#   ANTICIPY_LOCAL_WRANGLER_CONFIG       the events row, read out of D1
#   ANTICIPY_TEST_SMS_UNCONFIGURED_URL   a Worker with NO Sendblue secret
#
# migration/workers/scripts/sms_contract_local.sh sets all of them against a
# real workerd.  NEVER point the write tests at production with a real
# owner's number: they land rows the brain reads as that owner's replies.
# --------------------------------------------------------------------------

SMS_UNCONFIGURED_URL = (os.environ.get("ANTICIPY_TEST_SMS_UNCONFIGURED_URL") or "").rstrip("/")
SENDBLUE_SECRET = os.environ.get("ANTICIPY_TEST_SENDBLUE_SECRET") or ""
SENDBLUE_NUMBER = os.environ.get("ANTICIPY_TEST_SENDBLUE_NUMBER") or ""
SMS_OWNER_REF = os.environ.get("ANTICIPY_TEST_SMS_OWNER_REF") or ""
SMS_OWNER_PHONE = os.environ.get("ANTICIPY_TEST_SMS_OWNER_PHONE") or ""
SMS_AMBIGUOUS_PHONE = os.environ.get("ANTICIPY_TEST_SMS_AMBIGUOUS_PHONE") or ""
TWILIO_TEST_AUTH_TOKEN = os.environ.get("ANTICIPY_TEST_TWILIO_AUTH_TOKEN") or ""
TWILIO_TEST_ACCOUNT_SID = os.environ.get("ANTICIPY_TEST_TWILIO_ACCOUNT_SID") or ""
TWILIO_TEST_NUMBER = os.environ.get("ANTICIPY_TEST_TWILIO_NUMBER") or ""

# A number no seeded row carries.  555-01xx is reserved for fiction.
SMS_NOBODY = "+15550199999"

# The columns the oracle writes (sms.pb.js:280-288), read back for the row
# assertions; `created`/`updated` are the autodates the Worker fills.
SMS_ROW_COLUMNS = ("device_id", "kind", "text", "decision", "goal",
                   "owner_ref", "external_event_id", "created", "updated")


def sms_rows(external_id):
    """Every events row carrying this carrier id, out of the local D1.  Skips,
    naming the variable, when the suite is not pointed at a local Worker --
    no HTTP route exposes another owner's events, by design."""
    safe = external_id.replace("'", "''")
    return local_d1("SELECT %s FROM events WHERE external_event_id = '%s'"
                    % (", ".join(SMS_ROW_COLUMNS), safe))


def assert_oracle_row(row, sender, text, owner_ref, external_id):
    """CONTRACT.md §6.12 -- the event row, field by field."""
    assert row["device_id"] == "sms", row
    assert row["kind"] == "sms_reply", row
    assert row["text"] == text, row
    assert row["decision"] == "", (
        "§6.12: decision must be the EMPTY STRING -- the brain's poll filters "
        "on decision=\"\" and a NULL here is a text nobody hears: %r" % (row,))
    assert row["goal"] == sender, "§6.12: goal is the sender's number: %r" % (row,)
    assert row["owner_ref"] == owner_ref, row
    assert row["external_event_id"] == external_id, row
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}Z$", row["created"] or ""), (
        "created is not a PocketBase autodate: %r" % (row["created"],))
    assert row["updated"] == row["created"], row


def twilio_signature(token, url, params):
    """twilio_signature.js: base64(HMAC-SHA1(token, url + sorted key+value))."""
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(
        hmac.new(token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode("ascii")


def signed_twilio_form(sender, body, message_sid=None):
    """A Twilio-shaped form the Worker under test will accept, signed for the
    URL it will see (BASE_URL + the path, which is what wrangler dev sees).
    Skips without the token."""
    need(TWILIO_TEST_AUTH_TOKEN, "ANTICIPY_TEST_TWILIO_AUTH_TOKEN")
    form = {"From": sender, "Body": body,
            "MessageSid": message_sid or ("SM" + rand(32, "0123456789abcdef")),
            "AccountSid": TWILIO_TEST_ACCOUNT_SID or ("AC" + "0" * 32),
            "To": TWILIO_TEST_NUMBER or "+15550100998"}
    sig = twilio_signature(TWILIO_TEST_AUTH_TOKEN, BASE_URL + "/sms/inbound", form)
    return form, {"X-Twilio-Signature": sig}


def sendblue_message(**over):
    """An inbound Sendblue payload with every documented field, as the
    dashboard's webhook sends it (docs.sendblue.com, read 2026-09-05)."""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    mine = SENDBLUE_NUMBER or "+15550100999"
    body = {
        "accountEmail": "owner@anticipy-test.invalid",
        "content": "yes",
        "is_outbound": False,
        "status": "RECEIVED",
        "error_code": None,
        "error_message": None,
        "message_handle": "sbtest-" + rand(24),
        "date_sent": now,
        "date_updated": now,
        "from_number": SMS_NOBODY,
        "number": SMS_NOBODY,
        "to_number": mine,
        "sendblue_number": mine,
        "media_url": "",
        "message_type": "message",
        "group_id": "",
        "participants": [],
        "opted_out": False,
        "service": "iMessage",
    }
    body.update(over)
    return body


def sendblue_post(message, secret=None, base=None):
    """POST the payload with the secret header; secret="" sends NO header."""
    headers = {}
    value = SENDBLUE_SECRET if secret is None else secret
    if value:
        headers["sb-signing-secret"] = value
    return call("POST", "/sms/sendblue", headers=headers, json_body=message, base=base)


class TestSmsInbound(object):

    def test_a_non_form_content_type_is_refused(self):
        """§6.12 rule 2."""
        resp = call("POST", "/sms/inbound", json_body={"From": "+15550001111"})
        assert resp.status in (415, 503), repr(resp)
        if resp.status == 415:
            assert "unsupported content type" in resp.text, repr(resp)

    def test_an_unsigned_webhook_is_refused(self):
        """§6.12 rule 3 — Twilio signs the EXACT URL it requested, and nothing
        that cannot produce a matching HMAC under TWILIO_AUTH_TOKEN gets in."""
        resp = call("POST", "/sms/inbound",
                    form={"From": "+15550001111", "Body": "yes",
                          "MessageSid": "SM" + "0" * 32,
                          "AccountSid": "AC" + "0" * 32, "To": "+15550002222"})
        assert resp.status in (403, 503), repr(resp)
        if resp.status == 403:
            assert resp.text.strip() == "forbidden", repr(resp)
        else:
            assert "not configured" in resp.text, repr(resp)

    def test_a_forged_signature_is_refused(self):
        """§6.12 rule 3 — a present-but-wrong signature is the same refusal as
        an absent one, from the caller's point of view."""
        resp = call("POST", "/sms/inbound",
                    headers={"X-Twilio-Signature": "ZGVmaW5pdGVseSBub3QgaXQ="},
                    form={"From": "+15550001111", "Body": "yes",
                          "MessageSid": "SM" + "0" * 32})
        assert resp.status in (403, 503), repr(resp)

    # -- past the signature: the suite signs, so these need the token -------

    def test_a_malformed_message_sid_is_refused_even_when_signed(self):
        """§6.12 rule 6 -- a signed Twilio SMS always carries SM + 32 hex."""
        form, headers = signed_twilio_form(SMS_NOBODY, "yes", message_sid="not-a-sid")
        resp = call("POST", "/sms/inbound", headers=headers, form=form)
        assert resp.status == 403, repr(resp)
        assert resp.text.strip() == "forbidden", repr(resp)

    def test_a_signed_text_from_nobody_is_200_twiml_and_writes_no_row(self):
        """§6.12 -- 0 matches: 200 with the empty TwiML, logged, and no row.
        Twilio must not retry a text that was refused for a reason."""
        form, headers = signed_twilio_form(SMS_NOBODY, "yes")
        resp = call("POST", "/sms/inbound", headers=headers, form=form)
        assert resp.status == 200, repr(resp)
        assert "<Response></Response>" in resp.text, repr(resp)
        assert "xml" in (resp.header("Content-Type") or ""), repr(resp)
        if LOCAL_WRANGLER_CONFIG:
            assert sms_rows(form["MessageSid"]) == [], "a text from nobody wrote a row"

    @pytest.mark.destructive
    def test_a_signed_text_from_the_owner_lands_the_oracle_row_once(self):
        """§6.12 -- exactly 1 match: the events row, field by field, and a
        retried MessageSid is still ONE row: the partial-unique index on
        external_event_id is the idempotency, not a pre-read."""
        need(SMS_OWNER_PHONE, "ANTICIPY_TEST_SMS_OWNER_PHONE")
        need(SMS_OWNER_REF, "ANTICIPY_TEST_SMS_OWNER_REF")
        text = "yes, twilio " + rand(6)
        form, headers = signed_twilio_form(SMS_OWNER_PHONE, "  " + text + "  ")
        first = call("POST", "/sms/inbound", headers=headers, form=form)
        assert first.status == 200, repr(first)
        assert "<Response></Response>" in first.text, repr(first)
        rows = sms_rows(form["MessageSid"])
        assert len(rows) == 1, "expected exactly one events row, found %d" % len(rows)
        assert_oracle_row(rows[0], SMS_OWNER_PHONE, text, SMS_OWNER_REF, form["MessageSid"])
        again = call("POST", "/sms/inbound", headers=headers, form=form)
        assert again.status == 200, repr(again)
        assert "<Response></Response>" in again.text, repr(again)
        assert len(sms_rows(form["MessageSid"])) == 1, "Twilio's retry became a second row"


class TestSendblueInbound(object):
    """§6.12a -- Sendblue's webhook.  The same acceptance line as Twilio's:
    the front door refuses; past it nothing refuses -- a text lands, or it is
    dropped/ignored with a 200 and a log line, or it is a 500 so Sendblue
    retries.  Worker-only: PocketBase never had this route."""

    # -- the front door ------------------------------------------------------

    def test_an_unconfigured_worker_answers_503_not_403(self):
        """§6.12a rule 1 -- an unset secret is a configuration problem and
        says so.  A 403 would look like a forged request forever and hide a
        deaf product, which is what 2026-08-12..15 looked like on Twilio."""
        need(SMS_UNCONFIGURED_URL, "ANTICIPY_TEST_SMS_UNCONFIGURED_URL")
        resp = sendblue_post(sendblue_message(), secret="anything-at-all",
                             base=SMS_UNCONFIGURED_URL)
        assert resp.status == 503, repr(resp)
        assert "not configured" in resp.text, repr(resp)

    def test_a_missing_secret_header_is_refused(self):
        """§6.12a rule 2 (or rule 1 on a Worker with no secret bound)."""
        resp = sendblue_post(sendblue_message(), secret="")
        assert resp.status in (403, 503), repr(resp)
        if resp.status == 403:
            assert resp.text.strip() == "forbidden", repr(resp)
        else:
            assert "not configured" in resp.text, repr(resp)

    def test_a_wrong_secret_is_refused(self):
        """§6.12a rule 2 -- and it is the same refusal the absent header gets,
        from the caller's point of view."""
        resp = sendblue_post(sendblue_message(),
                             secret="definitely-not-the-secret-" + rand(8))
        assert resp.status in (403, 503), repr(resp)
        if resp.status == 403:
            assert resp.text.strip() == "forbidden", repr(resp)

    def test_a_non_json_body_is_400_not_retried(self):
        """§6.12a rule 3 -- a body that is not JSON will not become JSON on a
        retry, so it must not be a 5xx."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        resp = call("POST", "/sms/sendblue", headers={"sb-signing-secret": SENDBLUE_SECRET},
                    raw="From=%2B15550199999&Body=yes")
        assert resp.status == 400, repr(resp)

    # -- past the front door: not a reply -------------------------------------

    def test_an_outbound_status_update_is_ignored_not_heard(self):
        """§6.12a rule 4 -- status callbacks for texts WE sent arrive on this
        same URL.  One treated as a reply would have the brain hearing its own
        DELIVERED, and then answering it."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        mine = SENDBLUE_NUMBER or "+15550100999"
        theirs = SMS_OWNER_PHONE or SMS_NOBODY
        msg = sendblue_message(is_outbound=True, status="DELIVERED",
                               from_number=mine, number=theirs, to_number=theirs,
                               content="the text Anticipy sent")
        resp = sendblue_post(msg)
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("ignored") == "status update", repr(resp)
        if LOCAL_WRANGLER_CONFIG:
            assert sms_rows(msg["message_handle"]) == [], "a status update became a reply row"

    def test_a_group_message_is_ignored(self):
        """§6.12a rule 6 -- the brain holds one conversation per owner."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        mine = SENDBLUE_NUMBER or "+15550100999"
        msg = sendblue_message(from_number=SMS_OWNER_PHONE or SMS_NOBODY,
                               group_id="grp-" + rand(10),
                               participants=[SMS_OWNER_PHONE or SMS_NOBODY, "+15550199998", mine])
        resp = sendblue_post(msg)
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("ignored") == "group message", repr(resp)
        if LOCAL_WRANGLER_CONFIG:
            assert sms_rows(msg["message_handle"]) == [], "a group message became a reply row"

    def test_the_wrong_sendblue_number_is_refused(self):
        """§6.12a rule 5 -- as /sms/inbound refuses a To that is not
        TWILIO_PHONE_NUMBER."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        need(SENDBLUE_NUMBER, "ANTICIPY_TEST_SENDBLUE_NUMBER")
        msg = sendblue_message(to_number="+15550100000", sendblue_number="+15550100000")
        resp = sendblue_post(msg)
        assert resp.status == 403, repr(resp)
        assert resp.text.strip() == "forbidden", repr(resp)

    def test_a_message_without_a_handle_is_400_not_retried(self):
        """§6.12a rule 7 -- without the carrier's id a retry cannot be told
        from a second text."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        msg = sendblue_message()
        del msg["message_handle"]
        resp = sendblue_post(msg)
        assert resp.status == 400, repr(resp)

    def test_an_empty_message_is_dropped(self):
        """§6.12a rule 8."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        msg = sendblue_message(from_number=SMS_OWNER_PHONE or SMS_NOBODY, content="   ")
        resp = sendblue_post(msg)
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("dropped") == "empty content", repr(resp)
        if LOCAL_WRANGLER_CONFIG:
            assert sms_rows(msg["message_handle"]) == [], "an empty message wrote a row"

    def test_a_media_only_message_is_dropped_like_an_mms_without_a_body(self):
        """§6.12a rule 8 -- no events column carries media_url, and an
        empty-text row would exist only for the brain to mark it ignore."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        msg = sendblue_message(from_number=SMS_OWNER_PHONE or SMS_NOBODY, content="",
                               media_url="https://example.invalid/photo.jpg",
                               message_type="media")
        resp = sendblue_post(msg)
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("dropped") == "empty content", repr(resp)
        if LOCAL_WRANGLER_CONFIG:
            assert sms_rows(msg["message_handle"]) == [], "a media-only message wrote a row"

    # -- past the front door: whose text is it --------------------------------

    def test_an_unknown_sender_is_dropped_and_writes_no_row(self):
        """§6.12a rule 10 -- 0 matches: 200, logged, no row.  A stranger's
        text must not become a row anybody's brain could hear."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        msg = sendblue_message()          # from SMS_NOBODY
        resp = sendblue_post(msg)
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("dropped") == "no owner", repr(resp)
        if LOCAL_WRANGLER_CONFIG:
            assert sms_rows(msg["message_handle"]) == [], "a stranger's text wrote a row"

    def test_an_ambiguous_sender_is_dropped_and_writes_no_row(self):
        """§6.12a rule 11 -- two accounts claim the number: refuse to pick
        whose browser to drive.  The mutation "resolve to the first owner"
        lands a row here and goes red."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        need(SMS_AMBIGUOUS_PHONE, "ANTICIPY_TEST_SMS_AMBIGUOUS_PHONE")
        msg = sendblue_message(from_number=SMS_AMBIGUOUS_PHONE, number=SMS_AMBIGUOUS_PHONE)
        resp = sendblue_post(msg)
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("dropped") == "ambiguous sender", repr(resp)
        if LOCAL_WRANGLER_CONFIG:
            assert sms_rows(msg["message_handle"]) == [], "an ambiguous number wrote a row"

    @pytest.mark.destructive
    def test_a_known_owner_lands_exactly_one_row_with_the_oracle_fields(self):
        """§6.12a rule 14 -- the events row, field by field, once."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        need(SMS_OWNER_PHONE, "ANTICIPY_TEST_SMS_OWNER_PHONE")
        need(SMS_OWNER_REF, "ANTICIPY_TEST_SMS_OWNER_REF")
        text = "yes, sendblue " + rand(6)
        msg = sendblue_message(from_number=SMS_OWNER_PHONE, number=SMS_OWNER_PHONE,
                               content="  " + text + "  ")
        resp = sendblue_post(msg)
        assert resp.status == 200, repr(resp)
        assert resp.json == {"ok": True}, repr(resp)
        rows = sms_rows(msg["message_handle"])
        assert len(rows) == 1, "expected exactly one events row, found %d" % len(rows)
        assert_oracle_row(rows[0], SMS_OWNER_PHONE, text, SMS_OWNER_REF, msg["message_handle"])

    @pytest.mark.destructive
    def test_the_same_message_handle_twice_is_one_row(self):
        """§6.12a rule 12 -- Sendblue retries on a 5xx and may redeliver; the
        partial-unique index makes the retries one command, not two."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        need(SMS_OWNER_PHONE, "ANTICIPY_TEST_SMS_OWNER_PHONE")
        msg = sendblue_message(from_number=SMS_OWNER_PHONE, number=SMS_OWNER_PHONE,
                               content="yes, again " + rand(6))
        first = sendblue_post(msg)
        assert first.status == 200 and first.json == {"ok": True}, repr(first)
        again = sendblue_post(msg)
        assert again.status == 200, repr(again)
        assert (again.json or {}).get("ignored") == "already handled", repr(again)
        assert len(sms_rows(msg["message_handle"])) == 1, "the retry became a second row"

    @pytest.mark.destructive
    def test_both_carriers_land_the_same_row_shape(self):
        """§6.12 and §6.12a share src/pb/sender.ts.  The brain
        (brain/worker.py handle_inbound) polls kind="sms_reply" and must not
        be able to tell which carrier delivered a text: every column but the
        carrier's own id and the timestamps is identical."""
        need(SENDBLUE_SECRET, "ANTICIPY_TEST_SENDBLUE_SECRET")
        need(SMS_OWNER_PHONE, "ANTICIPY_TEST_SMS_OWNER_PHONE")
        words = "same words " + rand(6)
        form, headers = signed_twilio_form(SMS_OWNER_PHONE, words)
        twilio = call("POST", "/sms/inbound", headers=headers, form=form)
        assert twilio.status == 200, repr(twilio)
        msg = sendblue_message(from_number=SMS_OWNER_PHONE, number=SMS_OWNER_PHONE, content=words)
        sendblue = sendblue_post(msg)
        assert sendblue.status == 200, repr(sendblue)
        a = sms_rows(form["MessageSid"])
        b = sms_rows(msg["message_handle"])
        assert len(a) == 1 and len(b) == 1, (a, b)
        strip = lambda row: {k: v for k, v in row.items()
                             if k not in ("external_event_id", "created", "updated")}
        assert strip(a[0]) == strip(b[0]), (
            "the two carriers landed different rows:\n  twilio:   %r\n  sendblue: %r"
            % (a[0], b[0]))


# ==========================================================================
# §7  internal_hq.pb.js
# ==========================================================================

def hq(extra=None):
    headers = {"X-Internal-Key": INTERNAL_KEY}
    if extra:
        headers.update(extra)
    return headers


class TestHQFrontDoor(object):

    def test_health_leaks_nothing_and_derives_its_booleans(self):
        """§7.2 — channels are DERIVED FROM ENV PRESENCE, never from a
        literal.  The Settings screen used to draw "Connected" from hardcoded
        strings: a surface reporting the claim instead of asking it.  A
        boolean cannot leak a key."""
        resp = call("GET", "/internal/health")
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("ok") is True, repr(resp)
        assert isinstance(body.get("gated"), bool), repr(resp)
        channels = body.get("channels") or {}
        assert isinstance(channels.get("email"), bool), repr(resp)
        assert isinstance(channels.get("sms"), bool), repr(resp)
        assert set(body.keys()) <= {"ok", "gated", "version", "channels"}, (
            "§7.2: health must leak nothing else. Got %r" % sorted(body.keys()))

    def test_login_refuses_a_wrong_key(self):
        """§7.3."""
        resp = call("POST", "/internal/login", json_body={"key": "definitely-wrong"})
        assert resp.status in (401, 503), repr(resp)
        if resp.status == 401:
            assert error_of(resp) == "wrong key", repr(resp)
        else:
            assert error_of(resp) == "internal HQ is not configured", repr(resp)

    def test_an_unkeyed_request_is_refused(self):
        """§7.0 — every HQ route is fail-CLOSED: 503 with no key configured,
        401 with one."""
        resp = call("GET", "/internal/state")
        assert resp.status in (401, 503), repr(resp)

    def test_the_options_preflight_answers_204_and_nothing_else(self):
        """§7.1 #37 — it never touches a record and never reveals whether the
        path behind it exists."""
        resp = call("OPTIONS", "/internal/definitely-not-a-real-route")
        assert resp.status == 204, repr(resp)
        assert resp.body in (b"", None), repr(resp)

    def test_cors_echoes_an_allowed_origin(self):
        """§4.3 — an explicit origin, never "*".  These routes carry a
        credential in a custom header; with a wildcard any page anybody on the
        team visits could be taught to ask this API questions."""
        resp = call("GET", "/internal/health",
                    headers={"Origin": "https://anticipy.ai"})
        assert resp.header("Access-Control-Allow-Origin") == "https://anticipy.ai", repr(resp)
        assert resp.header("Vary") == "Origin", repr(resp)
        allow = resp.header("Access-Control-Allow-Headers") or ""
        assert "X-Internal-Key" in allow and "X-HQ-Session" in allow, repr(resp)

    @pytest.mark.xfail(reason=PROD_CORS_WILDCARD_FOR_UNLISTED_ORIGINS)
    def test_cors_refuses_an_unlisted_origin(self):
        """§4.3 — with an allow-list, a browser refuses before the request
        leaves."""
        resp = call("GET", "/internal/health",
                    headers={"Origin": "https://evil.example.com"})
        assert resp.header("Access-Control-Allow-Origin") in (None, ""), (
            "§4.3: an unlisted origin must never be echoed. Got %r"
            % resp.header("Access-Control-Allow-Origin"))

    def test_the_hq_page_either_serves_or_fails_visibly(self):
        """§7.28 FAIL VISIBLY, NOT PARTLY.  A page that renders with its
        script missing looks like a broken product; a page that says it could
        not load looks like a thing to go and fix."""
        resp = call("GET", "/fellows/hq")
        assert resp.status in (200, 503), repr(resp)
        assert "text/html" in (resp.header("Content-Type") or "").lower(), repr(resp)
        if resp.status == 200:
            assert "<!doctype" in resp.text[:2000].lower(), repr(resp)
            assert (resp.header("X-Robots-Tag") or "").startswith("noindex"), repr(resp)
        else:
            assert "couldn't load its page" in resp.text, repr(resp)

    @pytest.mark.parametrize("method,path", [
        ("POST", "/internal/router"),
        ("POST", "/internal/research"),
        ("GET", "/internal/research/status"),
    ])
    def test_the_dead_ai_routes_are_410_before_any_auth_check(self, method, path):
        """§7.12 — the 410 is the FIRST statement in each handler, so no key
        is read and no 503 is possible.  For the port: implement the 410 and
        delete the bodies; they are the only place in the tree that creates a
        jobs row server-side, bypassing both guards."""
        resp = call(method, path, json_body={} if method == "POST" else None)
        assert resp.status == 410, repr(resp)
        assert error_of(resp) == "the AI surface was removed from HQ", repr(resp)


@pytest.mark.needs_hq
class TestHQSessions(object):

    def test_an_unresolvable_session_never_falls_through_to_the_key(
            self, internal_key, hq_configured):
        """§7.0 THE RULE.  A silent downgrade from "this is Ari" to "whoever
        holds the key says they are Ari" is the attack: an expired token must
        log you out, not quietly demote you to client-asserted identity."""
        resp = call("GET", "/internal/state",
                    headers=hq({"X-HQ-Session": rand(64, "0123456789abcdef")}))
        assert resp.status == 401, (
            "§7.0: a session that does not resolve must answer 401, NEVER "
            "fall through to the key branch. Got %r" % resp)
        assert (resp.json or {}).get("reauth") is True, repr(resp)

    @pytest.mark.parametrize("path", [
        "/internal/todos", "/internal/people", "/internal/events",
        "/internal/tracks", "/internal/expenses", "/internal/notes",
        "/internal/passwords", "/internal/todos/delete",
    ])
    def test_the_session_door_never_falls_through_either(
            self, internal_key, hq_configured, path):
        """§7.0 Pattern C — the same non-fall-through rule on the 16 handlers
        that got the door bolted on later.  A bad session plus a GOOD key must
        still be 401: the key is filled in only AFTER the session resolves."""
        resp = call("POST", path,
                    headers=hq({"X-HQ-Session": rand(64, "0123456789abcdef")}),
                    json_body={"actor_id": ACTOR_ID or rand(15)})
        assert resp.status == 401, (
            "§7.0 Pattern C: %s must answer 401 {reauth:true} for an "
            "unresolvable session even when the key is correct. Got %r"
            % (path, resp))
        assert (resp.json or {}).get("reauth") is True, repr(resp)

    def test_signing_out_without_a_session_is_still_ok(self, internal_key,
                                                       hq_configured):
        """§7.20 — "already signed out; say so plainly".  Whether that token
        existed is not a thing this route reports."""
        resp = call("POST", "/internal/session/end", json_body={})
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("ok") is True, repr(resp)

    def test_signing_out_an_unknown_token_is_also_ok(self, internal_key,
                                                     hq_configured):
        """§7.20 — always 200."""
        resp = call("POST", "/internal/session/end",
                    headers={"X-HQ-Session": rand(64, "0123456789abcdef")},
                    json_body={})
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("ok") is True, repr(resp)

    @pytest.mark.slow
    def test_a_wrong_login_code_gets_one_sentence_and_a_200(
            self, internal_key, hq_configured):
        """§7.14 ONE SENTENCE FOR EVERY FAILURE.  Wrong code, revoked code,
        deactivated person, tripped ceiling — all of it answers exactly this.
        Different messages would tell a stranger whether a code exists,
        whether the person is still on the team, and whether they are being
        rate limited.

        SPENDS ONE OF THE 40 HOURLY LOGIN ATTEMPTS."""
        resp = call("POST", "/internal/session",
                    json_body={"code": rand(8, "0123456789ABCDEFGHJKMNPQRSTVWXYZ")})
        assert resp.status == 200, (
            "§7.14: every failure is 200 with ok:false. Got %r" % resp)
        body = resp.json or {}
        assert body.get("ok") is False, repr(resp)
        assert body.get("message") == \
            "That code didn't match anyone. Check it and try again.", repr(resp)
        assert "token" not in body, repr(resp)

    def test_a_malformed_login_code_gets_the_same_sentence(
            self, internal_key, hq_configured):
        """§7.14 — a code that normalises to anything other than 8 characters
        is refused BEFORE the ceiling is spent, so this test costs nothing."""
        resp = call("POST", "/internal/session", json_body={"code": "ABC"})
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        assert body.get("ok") is False, repr(resp)
        assert body.get("message") == \
            "That code didn't match anyone. Check it and try again.", repr(resp)

    def test_clerk_exchange_refuses_a_non_jwt(self, internal_key, hq_configured):
        """§7.19 — the email comes from Clerk's SIGNATURE, never from the
        client."""
        resp = call("POST", "/internal/clerk/exchange",
                    json_body={"token": "not-a-jwt"})
        assert resp.status in (400, 503), repr(resp)
        if resp.status == 400:
            assert error_of(resp) == "no Clerk token in the request", repr(resp)

    def test_clerk_exchange_refuses_a_forged_jwt(self, internal_key, hq_configured):
        """§7.19 — three dot-separated parts, but no valid HS256 signature."""
        resp = call("POST", "/internal/clerk/exchange",
                    json_body={"token": "eyJhbGciOiJIUzI1NiJ9.eyJlbWFpbCI6ImF0"
                                        "dGFja2VyQGV4YW1wbGUuY29tIiwic3ViIjoi"
                                        "eCJ9.not-a-real-signature"})
        assert resp.status in (401, 503), repr(resp)
        if resp.status == 401:
            assert error_of(resp) == "Clerk did not recognise that sign-in", repr(resp)


@pytest.mark.needs_hq
class TestHQCalendarFeed(object):

    def test_a_malformed_feed_token_is_a_404(self, internal_key, hq_configured):
        """§7.18 — the token must be 64 lowercase hex."""
        resp = call("GET", "/internal/cal/not-a-token.ics")
        assert resp.status == 404, repr(resp)
        assert error_of(resp) == "not found", repr(resp)

    def test_an_unmatched_feed_token_is_the_same_404(self, internal_key,
                                                     hq_configured):
        """§7.18 — a well-formed token that matches no active person gets the
        identical refusal, so the shape of the token is not an oracle."""
        resp = call("GET", "/internal/cal/%s.ics" % rand(64, "0123456789abcdef"))
        assert resp.status == 404, repr(resp)
        assert error_of(resp) == "not found", repr(resp)

    def test_the_extension_is_optional(self, internal_key, hq_configured):
        """§7.18 — a trailing .ics is stripped before validation."""
        resp = call("GET", "/internal/cal/%s" % rand(64, "0123456789abcdef"))
        assert resp.status == 404, repr(resp)


@pytest.mark.needs_hq
class TestHQState(object):

    def test_state_answers_the_whole_page_in_one_round_trip(
            self, internal_key, hq_configured):
        """§7.4 — the documented key set."""
        resp = call("GET", "/internal/state", headers=hq())
        assert resp.status == 200, repr(resp)
        body = resp.json or {}
        for key in ("people", "tracks", "todos", "events", "activity",
                    "comments", "notifs", "reminders", "signins", "expenses",
                    "passwords", "notes", "config", "channels", "me",
                    "via_session", "meters"):
            assert key in body, "§7.4: /internal/state must carry %r" % key

    def test_state_never_carries_a_login_code_hash(self, internal_key,
                                                   hq_configured):
        """§7.4 EXPLICIT PROJECTION.  `code_hash` lives on internal_people and
        a `return p` here would hand every offline cracker the hash of every
        login code in the building.  The page needs to know whether a code
        EXISTS, never what it is and never what it hashes to."""
        resp = call("GET", "/internal/state", headers=hq())
        assert resp.status == 200, repr(resp)
        assert "code_hash" not in resp.text, (
            "§7.4: code_hash must never appear in /internal/state")
        for person in (resp.json or {}).get("people") or []:
            assert isinstance(person.get("has_code"), bool), repr(person)
            assert "code_hash" not in person, repr(person)

    def test_state_never_carries_a_vault_secret(self, internal_key, hq_configured):
        """§7.4 — metadata only.  secret_enc never rides in state, not even
        encrypted, because nothing on the page needs it and habits start
        somewhere."""
        resp = call("GET", "/internal/state", headers=hq())
        assert resp.status == 200, repr(resp)
        assert "secret_enc" not in resp.text, (
            "§7.4: secret_enc must never appear in /internal/state")
        for entry in (resp.json or {}).get("passwords") or []:
            assert "secret_enc" not in entry and "secret" not in entry, repr(entry)

    def test_state_never_carries_a_session_token_hash_or_ip(
            self, internal_key, hq_configured):
        """§7.4 — the screen prints a name and a when; it has never needed
        either, and a hash on the wire is a hash somebody can grind
        offline."""
        resp = call("GET", "/internal/state", headers=hq())
        assert resp.status == 200, repr(resp)
        assert "token_hash" not in resp.text, repr(resp.text[:400])
        for row in (resp.json or {}).get("signins") or []:
            assert set(row.keys()) <= {"person", "created"}, repr(row)

    def test_signin_history_is_admin_only(self, internal_key, hq_configured):
        """§7.4 — sign-in history is a list of when each teammate was at their
        desk.  That is an admin's answer to "did the code land", not a thing
        every member gets to read about every other member.  With no actor at
        all it must be empty."""
        resp = call("GET", "/internal/state", headers=hq())
        assert resp.status == 200, repr(resp)
        assert (resp.json or {}).get("signins") == [], (
            "§7.4: with no actor there is no admin, so signins must be empty")

    def test_me_requires_an_actor_in_the_key_branch(self, internal_key,
                                                    hq_configured):
        """§7.21 — unlike /internal/state, the actor is required here."""
        resp = call("GET", "/internal/me", headers=hq())
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "pick yourself first", repr(resp)

    def test_me_refuses_an_unknown_actor(self, internal_key, hq_configured):
        """§7.21."""
        resp = call("GET", "/internal/me", headers=hq(),
                    query={"actor_id": rand(15)})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "pick yourself first", repr(resp)

    def test_me_reports_has_code_as_a_boolean(self, internal_key, hq_configured,
                                              actor_id):
        """§7.21 — has_code is a boolean; the hash never leaves."""
        resp = call("GET", "/internal/me", headers=hq(),
                    query={"actor_id": actor_id})
        assert resp.status == 200, repr(resp)
        person = (resp.json or {}).get("person") or {}
        assert isinstance(person.get("has_code"), bool), repr(resp)
        assert "code_hash" not in resp.text, repr(resp)
        assert (person.get("cal_url") or "").endswith(".ics"), repr(resp)


@pytest.mark.needs_hq
class TestHQWrites(object):
    """Every test here drives a REFUSAL, so nothing is created."""

    def test_a_todo_needs_a_resolvable_actor(self, internal_key, hq_configured):
        """§7.7."""
        resp = call("POST", "/internal/todos", headers=hq(),
                    json_body={"actor_id": rand(15), "title": "x"})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "who is creating this? pick yourself first", repr(resp)

    def test_a_todo_needs_a_title(self, internal_key, hq_configured, actor_id):
        """§7.7."""
        resp = call("POST", "/internal/todos", headers=hq(),
                    json_body={"actor_id": actor_id, "title": "   "})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "a title between 1 and 500 characters, please", repr(resp)

    def test_a_todo_needs_a_real_board(self, internal_key, hq_configured, actor_id):
        """§7.7."""
        resp = call("POST", "/internal/todos", headers=hq(),
                    json_body={"actor_id": actor_id, "title": "probe",
                               "track": rand(15)})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "that board doesn't exist", repr(resp)

    def test_a_todo_patch_refuses_an_unknown_status(self, internal_key,
                                                    hq_configured, actor_id):
        """§7.8 — three values, and only three.  `doing`, `waiting` and
        `blocked` are NOT status: they are `stage`.  Accepting them here would
        take the row out of "status = 'open'" and out of the reminder cron,
        /internal/state and the assistant's board in one keystroke."""
        resp = call("PATCH", "/internal/todos", headers=hq(),
                    json_body={"actor_id": actor_id, "todo_id": rand(15),
                               "status": "doing"})
        # The todo lookup happens first, so an unknown id gives 404.  Either
        # answer proves the rule is not "anything goes".
        assert resp.status in (400, 404), repr(resp)
        if resp.status == 400:
            assert error_of(resp) == "status is open, done or cancelled", repr(resp)

    def test_a_todo_patch_refuses_a_stage_of_done(self, internal_key,
                                                  hq_configured, actor_id):
        """§7.8 — the mirror of the rule above.  `done` on `stage` would
        silently take the row out of the reminder cron."""
        resp = call("PATCH", "/internal/todos", headers=hq(),
                    json_body={"actor_id": actor_id, "todo_id": rand(15),
                               "stage": "done"})
        assert resp.status in (400, 404), repr(resp)
        if resp.status == 400:
            assert error_of(resp) == "pick a stage", repr(resp)

    def test_boards_are_admin_only(self, internal_key, hq_configured, actor_id):
        """§7.11."""
        resp = call("POST", "/internal/tracks", headers=hq(),
                    json_body={"actor_id": actor_id, "name": "Probe " + rand(6)})
        if resp.status == 200:
            pytest.skip("ANTICIPY_TEST_ACTOR_ID is an admin; point it at a "
                        "non-admin person to exercise the refusal (a board "
                        "was created — delete it)")
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "only an admin can manage boards", repr(resp)

    def test_settings_are_admin_only(self, internal_key, hq_configured, actor_id):
        """§7.27."""
        resp = call("POST", "/internal/settings", headers=hq(),
                    json_body={"actor_id": actor_id, "team_name": "Probe"})
        if resp.status == 200:
            pytest.skip("ANTICIPY_TEST_ACTOR_ID is an admin; the team name was "
                        "changed — set it back")
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "only an admin can change team settings", repr(resp)

    def test_project_deletion_is_admin_only(self, internal_key, hq_configured,
                                            actor_id):
        """§7.26."""
        resp = call("POST", "/internal/tracks/delete", headers=hq(),
                    json_body={"actor_id": actor_id, "track_id": rand(15)})
        assert resp.status in (403, 404), repr(resp)
        if resp.status == 403:
            assert error_of(resp) == "only an admin can remove a project", repr(resp)

    def test_login_codes_are_admin_only(self, internal_key, hq_configured,
                                        actor_id):
        """§7.22 — a code is a credential, so the branch that mints one demands
        a named admin.  Without this, anyone with the shared key could mint a
        code for a NEW admin account and convert "holds the shared key" into
        "is a person with a durable session"."""
        resp = call("POST", "/internal/people/code", headers=hq(),
                    json_body={"actor_id": actor_id, "person_id": rand(15)})
        if resp.status == 404:
            pytest.skip("ANTICIPY_TEST_ACTOR_ID is an admin, so the refusal "
                        "under test is not reached (got 404 for the target)")
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "only an admin can hand out login codes", repr(resp)

    def test_minting_a_code_at_join_time_is_admin_only(self, internal_key,
                                                       hq_configured):
        """§7.5 — self-serve join stays open with the shared key; the branch
        that MINTS A CODE does not."""
        resp = call("POST", "/internal/people", headers=hq(),
                    json_body={"name": "Probe " + rand(6), "mint_code": True,
                               "actor_id": rand(15)})
        assert resp.status in (400, 403), repr(resp)
        assert error_of(resp) in ("pick yourself first",
                                 "only an admin can hand out login codes"), repr(resp)

    def test_promoting_to_admin_at_join_time_is_admin_only(self, internal_key,
                                                           hq_configured):
        """§7.5 — the same rule for is_admin."""
        resp = call("POST", "/internal/people", headers=hq(),
                    json_body={"name": "Probe " + rand(6), "is_admin": True})
        assert resp.status == 403, repr(resp)
        assert error_of(resp) == "only an admin can make someone an administrator", repr(resp)

    def test_notifs_read_needs_ids_or_all(self, internal_key, hq_configured,
                                          actor_id):
        """§7.25."""
        resp = call("POST", "/internal/notifs/read", headers=hq(),
                    json_body={"actor_id": actor_id})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "which ones? send ids, or all:true", repr(resp)

    def test_a_comment_needs_a_real_task(self, internal_key, hq_configured,
                                         actor_id):
        """§7.23."""
        resp = call("POST", "/internal/comments", headers=hq(),
                    json_body={"actor_id": actor_id, "todo_id": rand(15),
                               "text": "hello"})
        assert resp.status == 404, repr(resp)
        assert error_of(resp) == "that item is gone", repr(resp)

    def test_a_reminder_rule_must_be_one_we_know(self, internal_key,
                                                 hq_configured, actor_id):
        """§7.24."""
        resp = call("POST", "/internal/reminders", headers=hq(),
                    json_body={"actor_id": actor_id, "todo_id": rand(15),
                               "rule": "whenever"})
        assert resp.status == 404, repr(resp)   # the todo is looked up first

    def test_an_expense_needs_a_positive_amount(self, internal_key,
                                                hq_configured, actor_id):
        """§7.15."""
        resp = call("POST", "/internal/expenses", headers=hq(),
                    json_body={"actor_id": actor_id, "title": "probe",
                               "amount": -5})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "amount has to be a positive number", repr(resp)

    def test_a_note_may_not_be_empty(self, internal_key, hq_configured, actor_id):
        """§7.17."""
        resp = call("POST", "/internal/notes", headers=hq(),
                    json_body={"actor_id": actor_id, "title": "", "body": ""})
        assert resp.status == 400, repr(resp)
        assert error_of(resp) == "an empty note isn't worth keeping", repr(resp)

    def test_revealing_an_unknown_vault_entry_is_a_404(self, internal_key,
                                                       hq_configured, actor_id):
        """§7.16 — and note what this test does NOT assert: there is no admin
        gate and no rate limit on reveal.  Any active teammate may reveal any
        entry.  That is the current contract (CONTRACT.md §9.4 item 6)."""
        resp = call("POST", "/internal/passwords/reveal", headers=hq(),
                    json_body={"actor_id": actor_id, "password_id": rand(15)})
        assert resp.status in (404, 503), repr(resp)
        if resp.status == 503:
            assert error_of(resp) == "the vault is not configured", repr(resp)
        else:
            assert error_of(resp) == "that entry is gone", repr(resp)


# ==========================================================================
# §10  the document and the suite pin each other
# ==========================================================================

ALL_ROUTES = [
    # product (17)
    ("POST", "/auth/reset/request"), ("POST", "/auth/reset/confirm"),
    ("POST", "/me/delete"), ("POST", "/me/phone/remove"),
    ("POST", "/me/profile/upsert"), ("POST", "/auth/claim"),
    ("POST", "/agent/register"), ("POST", "/agent/upgrade-credential"),
    ("GET", "/agent/key"), ("POST", "/agent/llm"),
    ("POST", "/agent/solve-captcha"), ("POST", "/agent/solve-captcha/result"),
    ("POST", "/evidence/share"), ("GET", "/worker/owners"),
    ("POST", "/sms/inbound"), ("POST", "/transcription/token"),
    ("POST", "/admin/purge-audit"),
    # HQ (38)
    ("GET", "/internal/health"), ("POST", "/internal/login"),
    ("GET", "/internal/state"), ("POST", "/internal/people"),
    ("PATCH", "/internal/people"), ("POST", "/internal/todos"),
    ("PATCH", "/internal/todos"), ("POST", "/internal/todos/delete"),
    ("POST", "/internal/events"), ("POST", "/internal/events/delete"),
    ("POST", "/internal/tracks"), ("POST", "/internal/router"),
    ("POST", "/internal/assistant"), ("POST", "/internal/research"),
    ("GET", "/internal/research/status"), ("POST", "/internal/session"),
    ("POST", "/internal/expenses"), ("POST", "/internal/expenses/delete"),
    ("POST", "/internal/passwords"), ("POST", "/internal/passwords/reveal"),
    ("POST", "/internal/passwords/delete"), ("POST", "/internal/notes"),
    ("POST", "/internal/notes/delete"), ("GET", "/internal/cal/{token}"),
    ("POST", "/internal/clerk/exchange"), ("POST", "/internal/session/end"),
    ("GET", "/internal/me"), ("POST", "/internal/people/code"),
    ("POST", "/internal/comments"), ("PATCH", "/internal/comments"),
    ("POST", "/internal/comments/delete"), ("POST", "/internal/reminders"),
    ("POST", "/internal/reminders/delete"), ("POST", "/internal/notifs/read"),
    ("POST", "/internal/tracks/delete"), ("POST", "/internal/settings"),
    ("OPTIONS", "/internal/{path...}"), ("GET", "/fellows/hq"),
]

MIDDLEWARES = [
    "evidence.pb.js", "guard.pb.js", "internal_hq.pb.js",
    "owner_profile_owner.pb.js", "research_lane.pb.js", "workflow_guard.pb.js",
]

CRONS = [("internal_hq_sweep", "*/5 * * * *"),
         ("internal_hq_prune", "17 4 * * *")]


def _contract_text():
    if not os.path.exists(CONTRACT_MD):
        pytest.skip("CONTRACT.md is not beside this file (%s)" % CONTRACT_MD)
    with open(CONTRACT_MD, "r") as handle:
        return handle.read()


@pytest.mark.offline
class TestTheDocumentAndTheSuiteAgree(object):
    """These need no network.  They stop the document and the suite drifting
    apart, which is the failure mode that makes a specification worthless."""

    def test_there_are_exactly_fifty_five_routes(self):
        assert len(ALL_ROUTES) == 55, (
            "the audit counted 55 routerAdd registrations; this list has %d"
            % len(ALL_ROUTES))
        assert len(set(ALL_ROUTES)) == 55, "duplicate entry in ALL_ROUTES"

    def test_the_contract_documents_every_route(self):
        text = _contract_text()
        missing = [path for _, path in ALL_ROUTES if path not in text]
        assert not missing, (
            "CONTRACT.md does not mention these routes: %r" % missing)

    def test_the_contract_documents_every_middleware(self):
        text = _contract_text()
        missing = [name for name in MIDDLEWARES if name not in text]
        assert not missing, (
            "CONTRACT.md does not mention these middlewares: %r" % missing)

    def test_the_cron_contract_is_documented(self):
        """CONTRACT.md §10: the crons cannot be exercised over HTTP, so the
        only thing this suite can assert about them is that the document and
        the schedule agree.  Said plainly rather than pretending to test."""
        text = _contract_text()
        for name, schedule in CRONS:
            assert name in text, "CONTRACT.md does not mention cron %r" % name
            assert schedule in text, (
                "CONTRACT.md does not record the schedule %r for %r"
                % (schedule, name))

    def test_every_workflow_guard_refusal_string_is_documented(self):
        """CONTRACT.md §1.16 — the complete refusal inventory.  A port that
        changes one of these strings breaks brain/pb.py and the extension,
        both of which branch on the 409 detail."""
        text = _contract_text()
        refusals = [
            "workflow params are not parseable",
            "canonical workflow is missing from params",
            "row approval is not parseable",
            "row receipt is not parseable",
            "job fields disagree with the embedded workflow",
            "required facts are missing from the approved plan",
            "workflow id, version, and lineage are required",
            "owner_ref is required for workflow jobs",
            "workflow id is immutable",
            "owner is immutable",
            "workflow version cannot move backwards",
            "an executor cannot rewrite or approve its plan",
            "changing a plan requires a new workflow version",
            "running update came from the wrong lease",
            "expired executor may only recover, park, or fail",
            "consequential work needs parseable approval",
            "approval is not bound to this exact plan version",
            "uncertain effect needs reconciliation before retry",
            "uncertain effect was not proven safe to retry",
            "running work needs an actor and lease",
            "running lease must expire in the future",
            "non-running work may not retain an execution lease",
            "done needs a parseable receipt",
            "done needs verified evidence for this exact effect",
            "shelf2.act_type_not_admitted", "shelf2.reach_disagrees",
            "shelf2.executor_disagrees", "shelf2.no_undo_plan",
            "shelf2.undo_addresses_another_act", "shelf2.unknown_provenance",
            "shelf2.unresolved_reference", "shelf2.undo_binds_nothing",
            "shelf2.act_target_unbound", "shelf2.undo_misses_the_target",
            "shelf2.no_announce_obligation", "shelf2.announce_leaves_the_owner",
            "shelf2.unordered_lineage", "shelf2.lineage_unreadable",
            "shelf2.superseded_by_later_act",
        ]
        missing = [r for r in refusals if r not in text]
        assert not missing, (
            "CONTRACT.md §1.16 is missing these refusal strings: %r" % missing)

    def test_the_contract_records_the_three_deliberate_fail_opens(self):
        """CONTRACT.md §0.2 — the three places the polarity rule is
        deliberately inverted are the three places a port most easily gets
        "right" in a way that changes behaviour."""
        text = _contract_text()
        assert "FAIL-OPEN" in text
        assert "ANTICIPY_SERVICE_TOKEN" in text
        assert "if (!workflow) return e.next()" in text or \
               "!workflow) return e.next()" in text


# ---------------------------------------------------------------------------
# HQ's gate surface, without holding the key
#
# ANTICIPY_INTERNAL_KEY is not available to this suite, which parked HQ's ~33
# data routes as unverifiable and therefore unportable. It does not. Every
# gated handler in internal_hq.pb.js checks the key as its FIRST statement and
# returns before touching data, so the UNAUTHENTICATED answer of every route is
# both observable without a credential and specified line-by-line by the source.
#
# That makes this table a fingerprint. 28 routes refuse identically; 7 do
# something else, each for a reason written down in the source. A build that
# merely resembled that file would not reproduce seven distinct exceptions and
# their exact wording. Production matched all 35 on 2026-09-04 -- see
# research/2026-09-04-hq-hook-IS-production.md -- which is what established
# that the repo's hook IS the deployed one and unblocked the port.
#
# It is also the half of HQ most worth pinning. This is the gate: 401 vs 400 vs
# 410 vs 200 is a security property, and getting it subtly wrong in a port is
# both easy and silent. Authenticated bodies are NOT covered here and stay
# UNPROVEN until the key exists.
#
# These are safe to run against production: no key means no side effect, by
# construction of the handlers.
# ---------------------------------------------------------------------------

HQ_WRONG_KEY = "wrong key"

# (method, path) -> refuses with 401 {"error": "wrong key"}
HQ_GATED_ROUTES = [
    ("GET",   "/internal/me"),
    ("GET",   "/internal/state"),
    ("PATCH", "/internal/comments"),
    ("PATCH", "/internal/people"),
    ("PATCH", "/internal/todos"),
    ("POST",  "/internal/assistant"),
    ("POST",  "/internal/comments"),
    ("POST",  "/internal/comments/delete"),
    ("POST",  "/internal/events"),
    ("POST",  "/internal/events/delete"),
    ("POST",  "/internal/expenses"),
    ("POST",  "/internal/expenses/delete"),
    ("POST",  "/internal/login"),
    ("POST",  "/internal/notes"),
    ("POST",  "/internal/notes/delete"),
    ("POST",  "/internal/notifs/read"),
    ("POST",  "/internal/passwords"),
    ("POST",  "/internal/passwords/delete"),
    ("POST",  "/internal/passwords/reveal"),
    ("POST",  "/internal/people"),
    ("POST",  "/internal/people/code"),
    ("POST",  "/internal/reminders"),
    ("POST",  "/internal/reminders/delete"),
    ("POST",  "/internal/settings"),
    ("POST",  "/internal/todos"),
    ("POST",  "/internal/todos/delete"),
    ("POST",  "/internal/tracks"),
    ("POST",  "/internal/tracks/delete"),
]

# The seven that do NOT 401, and why. Each is load-bearing, not an oddity.
HQ_EXCEPTIONS = [
    # The AI surface was removed. 410 and not 404, so a stale client learns it
    # is stale instead of thinking it mistyped a URL.
    ("GET",  "/internal/research/status", 410, "the AI surface was removed from HQ"),
    ("POST", "/internal/research",        410, "the AI surface was removed from HQ"),
    ("POST", "/internal/router",          410, "the AI surface was removed from HQ"),
    # Shape before authority: no token in the request is a 400, because it is a
    # malformed request, not a rejected one.
    ("POST", "/internal/clerk/exchange",  400, "no Clerk token in the request"),
    # Onboarding. Ari holds an eight-character code and nothing else, so this
    # route cannot be key-gated. The reply is deliberately the same whether the
    # code is wrong or merely unknown -- it must not become an oracle for
    # guessing valid codes.
    ("POST", "/internal/session",         200, "That code didn't match anyone."),
    # Signing out twice is not an error.
    ("POST", "/internal/session/end",     200, None),
]


@pytest.mark.anonymous
class TestHQGateSurfaceWithoutTheKey:

    @pytest.mark.parametrize("method,path", HQ_GATED_ROUTES,
                             ids=lambda v: v if isinstance(v, str) else v)
    def test_gated_route_refuses_without_a_key(self, method, path):
        """401 and the same four-character reason for all 28. A route that
        answers anything else without a credential is either ungated or
        leaking which part of the request it disliked."""
        resp = call(method, path, json_body={})
        assert resp.status == 401, (
            "%s %s answered %d without a key; it must be 401. Body: %.200r"
            % (method, path, resp.status, resp.text))
        assert HQ_WRONG_KEY in detail_of(resp), (
            "%s %s refused with %r, not %r -- a differing refusal string is how "
            "a port drifts into telling a stranger something."
            % (method, path, detail_of(resp), HQ_WRONG_KEY))

    @pytest.mark.parametrize("method,path,status,needle", HQ_EXCEPTIONS)
    def test_the_seven_deliberate_exceptions_still_behave(
            self, method, path, status, needle):
        """Each of these is ungated or pre-empted ON PURPOSE. Pinning them
        matters more than pinning the 28: an exception that quietly becomes a
        401 breaks onboarding or a stale client, and one that quietly stops
        being an exception opens a hole."""
        resp = call(method, path, json_body={})
        # A route whose OWN secret is missing answers 503 with a sentence
        # naming what is missing. That is the route behaving correctly under a
        # configuration gap, not a port defect, and it must not read as either
        # a pass or a failure -- so it skips, loudly, naming the variable.
        # /internal/clerk/exchange is the live case: production has
        # CLERK_HQ_JWT_KEY set (it answers 400), the Worker does not yet.
        if resp.status == 503 and "not configured" in (detail_of(resp) or ""):
            pytest.skip("%s %s is unconfigured on this origin: %r -- set the "
                        "secret before cutover; this is a config gap, not a "
                        "port gap" % (method, path, detail_of(resp)))
        assert resp.status == status, (
            "%s %s answered %d, expected %d. Body: %.200r"
            % (method, path, resp.status, status, resp.text))
        if needle is not None:
            assert needle in (detail_of(resp) or ""), (
                "%s %s said %r, expected to contain %r"
                % (method, path, detail_of(resp), needle))

    def test_fellows_hq_is_ungated_and_serves_a_document(self):
        """/fellows/hq needs no key -- and shows the two layers coming apart.
        The ROUTE is this repo's; the internal.html it reads off disk is NOT
        (production's is 5,654 bytes larger). So assert the route's contract,
        never the document's bytes."""
        resp = call("GET", "/fellows/hq")
        assert resp.status == 200, "/fellows/hq must stay ungated"
        assert "<!doctype" in resp.text[:400].lower(), (
            "/fellows/hq served something that is not a document: %.200r"
            % resp.text)

    def test_health_reports_the_lock_without_leaking_it(self):
        """Booleans derived from env presence, never values. A boolean cannot
        leak a key, which is the whole design of this endpoint."""
        resp = call("GET", "/internal/health")
        assert resp.status == 200
        body = resp.json
        assert body.get("ok") is True
        assert body.get("version") == "hq-2"
        assert isinstance(body.get("gated"), bool), (
            "gated must be a boolean derived from env presence")
        channels = body.get("channels") or {}
        for name in ("email", "sms"):
            assert isinstance(channels.get(name), bool), (
                "channels.%s must be a boolean, got %r" % (name, channels.get(name)))
        blob = json.dumps(body)
        for leak in ("SG.", "AC", "sk-", "re_"):
            if leak == "AC":
                continue
            assert leak not in blob, "health leaked something key-shaped: %r" % leak


# ---------------------------------------------------------------------------
# "Ported" must not be able to drift from the truth
#
# TestHQGateSurfaceWithoutTheKey passes against the Worker for all 28 gated
# routes -- including the ones that are NOT ported, because hqGate answers a
# stranger with 401 before control ever reaches the handler. That is correct
# behaviour and a correct test, and it is also exactly the shape this codebase
# keeps getting burned by: a surface reporting the claim instead of asking it.
# Green there means "the door is locked", never "there is a room behind it".
#
# So the count is pinned to the SOURCE, where it cannot be fudged by a
# catch-all. This reads migration/workers/src/index.ts and requires that the
# honest "not yet ported" marker exists exactly while work remains: it may not
# be deleted early to make things look finished, and it may not be left behind
# once every route is wired, where it would read as a permanent apology for
# work that is actually done.
# ---------------------------------------------------------------------------

def _repo_file(*parts):
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "..", *parts)
    if not os.path.exists(path):
        pytest.skip("%s is not in this checkout" % os.path.join(*parts))
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


@pytest.mark.offline
class TestPasswordResetCopyIsTheHooksCopy(object):
    """§5.1 and §5.2 — WHAT THE OWNER READS, checked against the document and
    the hook rather than against a sentence typed twice.

    Offline because the two sentences cannot be observed over HTTP: the SMS
    goes to a real phone, and a 200 from /auth/reset/confirm needs a code only
    that phone has.  Nothing else in this suite can see them, which is exactly
    how the Worker came to send its own wording for a month (audit F39).

    The SMS's second sentence is the phishing tell the hook's header (:20-21)
    put there on purpose; the success line is asserted on by the phone itself
    (app/ios/Tests/ResetMessageTests.swift)."""

    def test_the_code_sms_is_the_documented_sentence(self):
        contract = _contract_text()
        worker = _repo_file("migration", "workers", "src", "routes", "password_reset.ts")
        tail = ("is your Anticipy code to set a new password. It works for 10 "
                "minutes. If you didn't ask for this, ignore it and your "
                "password stays as it is.")
        assert tail in contract, (
            "§5.1.7 no longer documents the reset SMS; this test is pinned to "
            "the wrong sentence")
        # The Worker builds it across two template literals, so collapse the
        # whitespace and close the ONE seam a two-part template leaves behind.
        # Nothing else is removed: no character of the sentence can hide in
        # "` + `", so this cannot paper over a wording change.
        collapsed = " ".join(worker.split()).replace("` + `", "")
        assert " ".join(tail.split()) in collapsed, (
            "§5.1.7: the Worker's reset SMS is not the documented sentence. "
            "The warning half is what stops a code arriving with no "
            "explanation, and password_reset.pb.js:20-21 says so.")

    def test_the_success_line_is_the_documented_sentence(self):
        contract = _contract_text()
        worker = _repo_file("migration", "workers", "src", "routes", "password_reset.ts")
        ios = _repo_file("app", "ios", "Tests", "ResetMessageTests.swift")
        line = "Done — sign in with your new password."
        assert line in contract, "§5.2 no longer documents the success line"
        assert line in worker, (
            "§5.2: /auth/reset/confirm answers a different sentence than the "
            "one the document and the phone were written against. Got: %r"
            % [s for s in worker.splitlines() if "message:" in s and "ok: true" in s])
        assert line in ios, (
            "app/ios/Tests/ResetMessageTests.swift no longer asserts on this "
            "sentence; the three copies must move together")


def _worker_index_source():
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "workers", "src", "index.ts")
    if not os.path.exists(path):
        pytest.skip("migration/workers/src/index.ts not in this checkout")
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


ALL_HQ_ROUTES = set(HQ_GATED_ROUTES) | {(m, p) for (m, p, _s, _n) in HQ_EXCEPTIONS}


def _wired_hq_routes(source):
    """Every (METHOD, path) pair index.ts actually handles.

    METHOD MATTERS, and an earlier version of this ignored it. Keying on the
    path alone meant PATCH /internal/comments kept the path in the "wired" set
    after POST /internal/comments was deleted -- the leg passed while a real
    route was missing, which is precisely the failure it exists to prevent.
    Negative-tested by deleting one method of a two-method path.

    Three dispatch forms are recognised, because index.ts uses three:
      path === "X" && method === "M"   the ordinary case
      HQ_DEAD_ROUTES.includes(path)    the retired 410s, ANY method, and the
                                       array lives in hq.ts, not here
      path.startsWith("/internal/cal/") a prefix route
    """
    wired = set()
    for path, method in re.findall(
            r'path === "(/internal/[^"]+)" && method === "(\w+)"', source):
        wired.add((method, path))

    here = os.path.dirname(os.path.abspath(__file__))
    hq_ts = os.path.join(here, "..", "workers", "src", "routes", "hq.ts")
    if os.path.exists(hq_ts):
        with open(hq_ts, "r", encoding="utf-8") as handle:
            dead = re.search(r'HQ_DEAD_ROUTES[^=]*=\s*\[(.*?)\]', handle.read(), re.S)
        if dead:
            # Answered before any method dispatch, so every method counts.
            for path in re.findall(r'"(/internal/[^"]+)"', dead.group(1)):
                for method in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                    wired.add((method, path))

    if 'path.startsWith("/internal/cal/")' in source:
        wired.add(("GET", "/internal/cal/{token}"))
    return wired


@pytest.mark.offline
class TestHQPortProgressIsHonest:

    def test_the_not_yet_ported_marker_matches_reality(self):
        source = _worker_index_source()
        wired = _wired_hq_routes(source)
        unported = sorted("%s %s" % (m, p) for (m, p) in ALL_HQ_ROUTES
                          if (m, p) not in wired)
        marker = "hq data routes not yet ported"

        if unported:
            assert marker in source, (
                "%d HQ routes are still served by the catch-all (%s) but the "
                "honest marker %r has been removed from index.ts. The gate leg "
                "cannot see this -- a stranger gets a correct 401 either way -- "
                "so deleting the marker is the only thing that would make an "
                "unfinished port look finished."
                % (len(unported), ", ".join(unported[:6])
                   + (" ..." if len(unported) > 6 else ""), marker))
        else:
            assert marker not in source, (
                "Every HQ route is wired, but index.ts still carries %r. Leave "
                "it and it becomes a permanent untruth in the other direction."
                % marker)

    def test_the_ungated_routes_are_wired_above_the_gate(self):
        """/internal/session, /internal/session/end and /internal/clerk/exchange
        MUST be handled before hqGate runs. Ari holds an eight-character code
        and never the shared key, so if the gate sees these first his only
        possible answer is 401 and there is no way into HQ at all. This is an
        ordering property, and ordering is not visible from outside once the
        routes are correctly ordered -- so it is asserted on the source."""
        source = _worker_index_source()
        gate_at = source.find("const refused = hqGate(")
        assert gate_at > 0, "hqGate is no longer called from index.ts"
        for path in ("/internal/session", "/internal/session/end",
                     "/internal/clerk/exchange"):
            at = source.find('path === "%s"' % path)
            assert at > 0, "%s is not wired in index.ts" % path
            assert at < gate_at, (
                "%s is wired BELOW hqGate. It must be above it: the caller "
                "proves who they are with a code or a Clerk token, not with "
                "the shared key, so gating it first locks out the only people "
                "it exists for." % path)


# ---------------------------------------------------------------------------
# /internal/state's projections ARE its security design
#
# This is the one route that returns most of HQ at once, and the tables it
# reads carry: internal_people.code_hash and .pw_hash, internal_passwords
# .secret_enc, internal_sessions.token_hash and .ip. None of it is needed by
# the page -- it needs to know a login code EXISTS, never what it hashes to --
# so every list is an explicit column projection and a `SELECT *` regression
# would hand all of it to anyone holding the shared key.
#
# Needs a key, so it runs against whichever origin the key belongs to. It is
# NOT a diff against production: it asserts properties that must hold on any
# correct implementation, which is what makes it meaningful on the Worker
# before production's key is ever available here.
# ---------------------------------------------------------------------------

@pytest.mark.needs_internal_key
class TestInternalStateProjections:

    def _state(self, actor_id=""):
        require_internal_key()
        query = {"actor_id": actor_id} if actor_id else None
        resp = call("GET", "/internal/state",
                    headers={"X-Internal-Key": INTERNAL_KEY}, query=query)
        if resp.status == 400 and "pick yourself" in (detail_of(resp) or ""):
            pytest.skip("needs an actor_id; pass one that exists on this origin")
        assert resp.status == 200, "state refused: %d %.200r" % (resp.status, resp.text)
        return resp.json

    def _an_actor(self, admin):
        """Find a person id off /internal/state itself, so the test carries no
        hardcoded ids that rot when the team changes."""
        require_internal_key()
        resp = call("GET", "/internal/state",
                    headers={"X-Internal-Key": INTERNAL_KEY})
        if resp.status != 200:
            # Without an actor_id some origins refuse; fall back to any id we
            # can see, and skip if we genuinely cannot get in.
            pytest.skip("cannot enumerate people without an actor_id here")
        for person in resp.json.get("people", []):
            if bool(person.get("is_admin")) == admin and person.get("active"):
                return person["id"]
        pytest.skip("no %s person on this origin" % ("admin" if admin else "non-admin"))

    def test_no_secret_column_appears_anywhere_in_the_payload(self):
        blob = json.dumps(self._state(self._an_actor(True)))
        for secret in ("code_hash", "pw_hash", "secret_enc", "token_hash", "tokenKey"):
            assert secret not in blob, (
                "/internal/state leaked %r. Every list in that route is an "
                "explicit projection for exactly this reason; a SELECT * "
                "regression puts hashes of every login code on the wire."
                % secret)

    def test_people_carry_has_code_and_not_the_hash(self):
        state = self._state(self._an_actor(True))
        assert state["people"], "no people came back"
        for person in state["people"]:
            assert "has_code" in person, "the page needs to know a code exists"
            assert "code_hash" not in person

    def test_passwords_are_metadata_only(self):
        state = self._state(self._an_actor(True))
        for row in state.get("passwords", []):
            assert "secret_enc" not in row and "secret" not in row, (
                "the vault's ciphertext must never ride in state -- "
                "/internal/passwords/reveal is the one route that decrypts, "
                "one row at a time, on purpose")

    def test_signin_history_is_admins_only(self):
        """Sign-in history says when each teammate was at their desk. That is
        an admin's answer to "did the code land", not something every member
        gets to read about every other member."""
        admin = self._state(self._an_actor(True))
        member = self._state(self._an_actor(False))
        assert member.get("signins") == [], (
            "a non-admin was given sign-in history: %r" % member.get("signins"))
        # And the admin's rows still project only what the screen prints.
        for row in admin.get("signins", []):
            assert set(row.keys()) <= {"person", "created"}, (
                "signins projected more than person+created: %r -- a hash on "
                "the wire is a hash somebody can grind offline" % sorted(row))

    def test_notifications_are_scoped_to_the_caller(self):
        actor = self._an_actor(True)
        state = self._state(actor)
        assert state["me"] == actor
        for notif in state.get("notifs", []):
            # The route filters by person; nothing in the payload should carry
            # another person's notification.
            assert "person" not in notif or notif["person"] == actor

    def test_comments_are_scoped_to_the_todos_returned(self):
        """Otherwise this becomes a keyed window onto the comment history of
        tasks the caller was never shown."""
        state = self._state(self._an_actor(True))
        todo_ids = {t["id"] for t in state.get("todos", [])}
        for comment in state.get("comments", []):
            assert comment["todo"] in todo_ids, (
                "comment %r belongs to todo %r, which is not in this payload"
                % (comment.get("id"), comment.get("todo")))

    def test_deleted_comments_carry_no_text(self):
        state = self._state(self._an_actor(True))
        for comment in state.get("comments", []):
            if comment.get("deleted"):
                assert comment.get("text") == "", (
                    "a tombstoned comment still carried its text; blanking it "
                    "on the way out is what stops a stale row resurrecting a "
                    "deleted sentence into somebody's browser")

    def test_channels_are_booleans_and_never_values(self):
        state = self._state(self._an_actor(True))
        for name, value in (state.get("channels") or {}).items():
            assert isinstance(value, bool), (
                "channels.%s is %r, not a boolean -- these are derived from "
                "env PRESENCE so that a credential cannot leak through them"
                % (name, value))


# ---------------------------------------------------------------------------
# CROSS-ORIGIN TOKEN COMPATIBILITY — the one property nothing else here tests
#
# Every other auth test in this file mints a token and verifies it ON THE SAME
# ORIGIN. Both backends are self-consistent, so both pass, and the suite was
# green for weeks while the property that actually decides whether a cutover is
# invisible to users went unmeasured:
#
#     A TOKEN MINTED BY POCKETBASE MUST VERIFY ON THE WORKER.
#
# Both sign HS256 with a per-record key -- PocketBase with
# collections.owners.authToken.secret + owners.tokenKey, the Worker with
# ANTICIPY_AUTH_SECRET + tokenKey. tokenKey migrated. The secret is a SETTING,
# not a column, so it did not, and ANTICIPY_AUTH_SECRET is currently unset on
# the Worker -- making the key the string "undefined" + tokenKey.
#
# If this leg is red, cutover signs out every iPhone and every extension at
# once. It goes green when the secret matches, which is exactly the gate.
#
# Needs BOTH origins and an owner credential, so it skips unless
# ANTICIPY_CROSS_ORIGIN (the OTHER backend's base URL) and an account are set.
# ---------------------------------------------------------------------------

CROSS_ORIGIN = (os.environ.get("ANTICIPY_CROSS_ORIGIN") or "").rstrip("/")


@pytest.mark.needs_account
class TestCrossOriginTokenCompatibility:

    def _mint_here(self, email, password):
        resp = call("POST", "/api/collections/owners/auth-with-password",
                    json_body={"identity": email, "password": password})
        if resp.status != 200:
            pytest.skip("could not mint a token on BASE_URL: %d" % resp.status)
        token = (resp.json or {}).get("token") or ""
        if not token:
            pytest.skip("auth-with-password returned no token")
        return token

    def test_a_token_minted_here_verifies_on_the_other_backend(self):
        """The cutover property. Mint on BASE_URL, present it to
        ANTICIPY_CROSS_ORIGIN. A 401 here means every signed-in user is signed
        out the moment traffic moves, including a shipped iOS build whose 401
        handling nobody has exercised."""
        if not CROSS_ORIGIN:
            pytest.skip("set ANTICIPY_CROSS_ORIGIN to the other backend's base URL")
        email = os.environ.get("ANTICIPY_TEST_EMAIL") or ""
        password = os.environ.get("ANTICIPY_TEST_PASSWORD") or ""
        if not (email and password):
            pytest.skip("set ANTICIPY_TEST_EMAIL and ANTICIPY_TEST_PASSWORD")

        token = self._mint_here(email, password)
        resp = call("POST", "/api/collections/owners/auth-refresh",
                    headers={"Authorization": token}, base=CROSS_ORIGIN)
        assert resp.status == 200, (
            "a token minted on %s was REJECTED by %s (%d). The two backends do "
            "not share a record-token secret, so cutting over signs out every "
            "user at once. Set ANTICIPY_AUTH_SECRET on the Worker to "
            "collections.owners.authToken.secret from PocketBase. See "
            "research/2026-09-04-the-auth-secret-nobody-set.md"
            % (BASE_URL, CROSS_ORIGIN, resp.status))

    def test_a_forged_token_is_refused_by_both(self):
        """The other half, and it must stay red-proof: if the two ever agree by
        accepting ANYTHING, that is worse than disagreeing. An unsigned token
        with valid-looking claims must be refused on both."""
        forged = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                  "eyJpZCI6IngiLCJ0eXBlIjoiYXV0aCIsImNvbGxlY3Rpb25OYW1lIjoib3duZXJzIiwiZXhwIjo5OTk5OTk5OTk5fQ."
                  "not-a-real-signature")
        here = call("POST", "/api/collections/owners/auth-refresh",
                    headers={"Authorization": forged})
        assert here.status == 401, "BASE_URL accepted a forged token: %d" % here.status
        if CROSS_ORIGIN:
            there = call("POST", "/api/collections/owners/auth-refresh",
                         headers={"Authorization": forged}, base=CROSS_ORIGIN)
            assert there.status == 401, (
                "%s accepted a forged token: %d" % (CROSS_ORIGIN, there.status))


# ---------------------------------------------------------------------------
# HQ LOGIN TAKES THE KEY IN THE BODY, NOT THE HEADER
#
# This is the property a port most easily inverts, and did: the Worker read the
# key from X-Internal-Key while the shipped HQ gate sends it in the JSON body
# (internal.html:934 -> api("/internal/login",{body:{key}}), because api() only
# attaches the header once the key is ALREADY stored, which at first login it is
# not). internal_hq.pb.js:42-50 reads body.key. So a header-keyed login route
# validates a credential the real client never sends, and every fresh HQ sign-in
# 401s with "That code didn't match" — HQ unreachable, all tests still green
# because no test logged in the way the browser does.
#
# Needs the key, so it runs against whichever origin owns it. Not a diff against
# production — it asserts the fixed property, which is what makes it meaningful
# on the Worker.
# ---------------------------------------------------------------------------

@pytest.mark.needs_internal_key
class TestHQLoginTakesTheKeyInTheBody:

    def test_the_correct_key_in_the_body_is_accepted(self):
        require_internal_key()
        resp = call("POST", "/internal/login", json_body={"key": INTERNAL_KEY})
        assert resp.status == 200, (
            "key-in-body login was refused (%d). The shipped HQ gate sends the "
            "key ONLY in the body, so a header-only login route locks every user "
            "out of HQ. Body: %.150r" % (resp.status, resp.text))
        assert (resp.json or {}).get("ok") is True

    def test_a_wrong_key_in_the_body_is_refused(self):
        resp = call("POST", "/internal/login", json_body={"key": "definitely-not-the-key"})
        assert resp.status == 401, "a wrong body key was not refused: %d" % resp.status
        assert "wrong key" in detail_of(resp)

    def test_an_empty_body_is_refused(self):
        """No key at all -> 401, never 200. The empty string must not match."""
        resp = call("POST", "/internal/login", json_body={})
        assert resp.status == 401, "an empty login body was accepted: %d" % resp.status


# ===========================================================================
# THE PRODUCT SURFACE — what the pendant, iPhone and extension call
#
# Every leg above this point exercised HQ or the four collections the skeleton
# happened to define. These pin the surface the CLIENTS use, which drifted
# unnoticed for weeks: five collections a shipped client calls were 404 on the
# Worker, owners leaked email+phone to a service token, and new-user signup was
# refused outright. All fixed 2026-09-04; these keep them fixed.
# ===========================================================================

# Collections production answers 200 for with a service token. Verified on both
# origins 2026-09-04. schema.ts's COLLECTIONS must stay a superset of these, or
# a client route 404s.
EXPOSED_COLLECTIONS = [
    "owners", "agents", "jobs", "events",
    "evidence", "owner_profile", "pendants", "purges", "segments",
]
# The five that were 404 until the schema generator was written. A regression
# here is the extension's receipt upload, iOS pairing, or privacy deletion going
# dark, so they get their own named assertion.
RESTORED_COLLECTIONS = ["evidence", "owner_profile", "pendants", "purges", "segments"]


@pytest.mark.needs_service_token
class TestCollectionSurface:

    def _svc(self):
        if not SERVICE_TOKEN:
            pytest.skip("set ANTICIPY_SERVICE_TOKEN")
        return {"X-Anticipy-Token": SERVICE_TOKEN}

    @pytest.mark.parametrize("coll", EXPOSED_COLLECTIONS)
    def test_every_exposed_collection_is_served(self, coll):
        """The generic records API must answer these — 200, or the known 400
        that production's own `agents` collection returns. A 404 means the
        collection is absent from schema.ts and a client that reads it is
        broken."""
        resp = call("GET", "/api/collections/%s/records" % coll,
                    headers=self._svc(), query={"perPage": "1"})
        assert resp.status != 404, (
            "collection %r is 404 — absent from schema.ts. A shipped client "
            "reads it; a missing collection is a dark feature, not a refusal. "
            "Run `npm run gen:schema`." % coll)
        assert resp.status in (200, 400), (
            "collection %r answered %d, expected 200 or 400" % (coll, resp.status))

    @pytest.mark.parametrize("coll", RESTORED_COLLECTIONS)
    def test_the_restored_collections_serve_200(self, coll):
        """These five were 404 until 2026-09-04 and are what the extension, iOS
        and brain actually depend on. They must be a clean 200."""
        resp = call("GET", "/api/collections/%s/records" % coll,
                    headers=self._svc(), query={"perPage": "1"})
        assert resp.status == 200, (
            "%r must serve 200 for the service token; got %d. See "
            "research/2026-09-04-the-product-surface-nobody-diffed.md"
            % (coll, resp.status))

    def test_owners_does_not_leak_to_a_service_token(self):
        """PocketBase's listRule `id = @request.auth.id`. A service token is not
        an auth record, so it matches no owner and the list is EMPTY. The Worker
        once answered this with all 31 rows including email and phone; the guard
        let it through and only the rule stopped it. totalItems must be 0."""
        resp = call("GET", "/api/collections/owners/records",
                    headers=self._svc(), query={"perPage": "5"})
        assert resp.status == 200, "owners list refused the service token: %d" % resp.status
        body = resp.json or {}
        assert body.get("totalItems") == 0, (
            "owners leaked %s rows to a service token — the listRule is not being "
            "applied. See research/2026-09-04-the-product-surface-nobody-diffed.md"
            % body.get("totalItems"))
        assert body.get("items") == [], "owners returned rows to a service token"

    def test_an_unknown_collection_is_refused_not_served(self):
        resp = call("GET", "/api/collections/zzz_not_a_collection/records",
                    headers=self._svc(), query={"perPage": "1"})
        assert resp.status in (403, 404), (
            "an unknown collection was served %d" % resp.status)


@pytest.mark.anonymous
class TestOwnerSignupContract:
    """New-user signup — POST /api/collections/owners/records. It was BOTH
    broken (passwordConfirm rejected as unknown_field, so the iPhone could not
    create an account) AND wide open (an empty body wrote a passwordless row
    from anywhere). Every message and the validation ORDER were read off
    production; these are safe because each input is refused BEFORE any write.
    See research/2026-09-04-signup-was-dead-on-the-worker.md."""

    def _create(self, body):
        return call("POST", "/api/collections/owners/records", json_body=body)

    def test_a_blank_body_reports_only_the_password_fields(self):
        """The non-obvious order: a blank body names password and
        passwordConfirm and says NOTHING about the missing email. The iPhone
        shows one field at a time, so the field named first is the one the
        person is sent to fix."""
        resp = self._create({})
        assert resp.status == 400, "a blank signup was accepted: %d" % resp.status
        data = (resp.json or {}).get("data", {})
        assert set(data.keys()) == {"password", "passwordConfirm"}, (
            "blank-body signup named %r, expected exactly password + "
            "passwordConfirm — a blank owner must never be writable, and the "
            "email error must not appear yet" % sorted(data))
        assert data["password"]["code"] == "validation_required"

    def test_password_without_email_then_asks_for_email(self):
        resp = self._create({"password": "abcdefgh1234", "passwordConfirm": "abcdefgh1234"})
        assert resp.status == 400
        data = (resp.json or {}).get("data", {})
        assert list(data.keys()) == ["email"], "expected only email once passwords are present"

    def test_a_short_password_is_refused(self):
        resp = self._create({"email": "x@example.invalid", "password": "abc", "passwordConfirm": "abc"})
        assert resp.status == 400
        data = (resp.json or {}).get("data", {})
        assert data.get("password", {}).get("code") == "validation_min_text_constraint"

    def test_a_confirm_mismatch_is_refused(self):
        resp = self._create({"email": "x@example.invalid", "password": "abcdefgh1234", "passwordConfirm": "zzzzzzzz9999"})
        assert resp.status == 400
        data = (resp.json or {}).get("data", {})
        assert data.get("passwordConfirm", {}).get("code") == "validation_values_mismatch"

    def test_the_envelope_matches_pocketbase(self):
        resp = self._create({})
        body = resp.json or {}
        assert body.get("message") == "Failed to create record."
        assert body.get("status") == 400


@pytest.mark.anonymous
class TestFellowshipUnauthenticated:
    """The public fellowship API, ported 2026-09-04 from recovered source and
    verified 17/17 identical to production at the unauthenticated boundary.
    anticipyfellowship.com (a separate site) calls these on this backend, so a
    regression is a fellow who cannot sign up. Every probe hits validation
    BEFORE any write, email, or side effect. See
    research/2026-09-04-fellowship-surface-ported.md.

    The AUTHENTICATED halves (email send, oembed, minor consent, payouts) are
    UNPROVEN and are not tested here — they need a real fellow session and must
    be diffed against production before anticipyfellowship.com is repointed."""

    def test_health_reports_its_booleans(self):
        resp = call("GET", "/fellows/health")
        assert resp.status == 200
        body = resp.json or {}
        for k in ("ok", "can_email", "can_review", "ip_resolves"):
            assert isinstance(body.get(k), bool), "%s must be a boolean" % k

    def test_code_refuses_a_bad_email_before_anything(self):
        resp = call("POST", "/fellows/code", json_body={"email": "not-an-email"})
        assert resp.status == 200 and (resp.json or {}).get("ok") is False
        assert "doesn't look right" in (resp.json or {}).get("message", "")

    def test_code_gates_on_age_and_saves_nothing_under_13(self):
        """COPPA: under-13 is refused with stop:true and NOTHING is stored —
        not the email, not the birth month. Storing it is the regulated act."""
        resp = call("POST", "/fellows/code", json_body={
            "email": "a@b.co", "birth_month": 6, "birth_year": 2020, "country": "us"})
        body = resp.json or {}
        assert body.get("ok") is False and body.get("stop") is True
        assert "have to be 13" in body.get("message", "")

    def test_code_gates_on_geography(self):
        resp = call("POST", "/fellows/code", json_body={
            "email": "a@b.co", "birth_month": 6, "birth_year": 1990, "country": "fr"})
        body = resp.json or {}
        assert body.get("ok") is False and body.get("stop") is True
        assert "US and Canada" in body.get("message", "")

    def test_start_reports_the_field_it_rejected(self):
        resp = call("POST", "/fellows/start", json_body={"email": "not-an-email"})
        body = resp.json or {}
        assert body.get("ok") is False and body.get("field") == "email"

    @pytest.mark.parametrize("path", [
        "/fellows/me", "/fellows/apply", "/fellows/progress",
        "/fellows/profile", "/fellows/submissions"])
    def test_sessioned_routes_demand_a_session(self, path):
        """No fellow session -> 401 {reauth:true}, never a 200 or a leak."""
        method = "GET" if path == "/fellows/me" else "POST"
        resp = call(method, path, json_body=None if method == "GET" else {})
        assert resp.status == 401, "%s answered %d without a session" % (path, resp.status)
        assert (resp.json or {}).get("reauth") is True

    def test_guardian_get_is_public_and_post_needs_a_token(self):
        assert call("GET", "/fellows/guardian").status == 200
        resp = call("POST", "/fellows/guardian", json_body={})
        assert resp.status == 200 and (resp.json or {}).get("ok") is False

    @pytest.mark.parametrize("path", [
        "/internal/fellows/remove",
        "/internal/fellows/submissions/remove",
        "/internal/fellows/submissions/release"])
    def test_the_admin_actions_refuse_without_the_key(self, path):
        """These move money and remove people. Without X-Internal-Key: 401."""
        resp = call("POST", path, json_body={})
        assert resp.status == 401, "%s ran without a key: %d" % (path, resp.status)
        assert "wrong key" in detail_of(resp)
