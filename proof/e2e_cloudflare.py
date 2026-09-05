#!/usr/bin/env python3
"""THE WHOLE PENDANT SYSTEM, ON CLOUDFLARE, ONE OWNER, ONE RUN.

    python3 proof/e2e_cloudflare.py --owner qeuy6sv1raof9rw
    python3 proof/e2e_cloudflare.py --dry-run          # print the bodies, post nothing
    python3 proof/e2e_cloudflare.py --sweep            # tidy an earlier run, post nothing

This is step 5 of research/2026-09-05-cloudflare-era-plan.md — the "End-to-end
test design" table, one row per hop, driven from this machine against
PRODUCTION (api.anticipy.ai = Worker + D1; the brain on Containers). Every
other proof in this folder measured one organ on the local rig. This one asks
whether the organs are wired to each other on the backend that serves users:

    ears -> API        three lines posted exactly the way the phone posts them
    API -> brain       the container for this owner hears them and stamps a decision
    brain -> mouth     what she says back lands as an anticipy_says row
    brain -> hands     the spoken errand becomes a job row with workflow metadata
    hands              a paired Chrome claims it, thinks through /agent/llm, finishes
    hands -> mouth     the done-text            (NOT PROVABLE HERE — see below)
    memory             tomorrow's recall        (NOT PROVABLE IN ONE RUN)

Pass = every row filled with a live artefact id. Anything mocked is a fail.
Exit 0 only when every hop that CAN be proven from here is proven; exit 2 when
any of them is not (UNPROVEN is a third state, not a soft fail — CLAUDE.md);
exit 1 when the run itself could not be carried out (preflight, a refused
write, the seatbelt).

WHO IT IS ALLOWED TO BE. One disposable owner on D1, created for this purpose
on 2026-09-05: `qeuy6sv1raof9rw`, e2e-2026-09-05@anticipy-test.invalid, whose
profile carries a fictional 555 number (+1 604 555 0142). The `.invalid` suffix
is the seatbelt, and it is checked, not assumed: the run REFUSES any owner whose
profile email does not end in `.invalid`, because a real owner's phone would
receive whatever the brain decides to text, and the fictional number is what
makes the "hands -> mouth" row unprovable here — Twilio refuses a 555 number,
so nobody is ever texted by this file. Every row it writes carries that
owner_ref; it reads no other owner's rows.

WHY THE PHONE IS MIRRORED BYTE FOR BYTE. The design's first row wants a real
phone (the api-pointed build is not on one yet — plan §"Measured"), and names
the fallback: post speech the way the app does. `phone_body()` below is
AnticipyBackend.pushEvent (app/ios/Anticipy/Backend/AnticipyBackend.swift:~710)
field for field, INCLUDING its omissions — no `speaker` key without a voice
verdict, no `explicit` key unless typed, no `boot_id`/`seq` (the columns exist
since migration 1700000004; no shipped build writes them), `spoken_at` equal to
`capture_started_at` (CaptureEnvelope.wireFields). A row that differs from the
phone's proves the wrong thing.

WHAT IT LEAVES BEHIND, ON PURPOSE. The three transcript rows (the brain stamps
them; that stamp IS the evidence), every anticipy_says / uninvited_slot row the
brain wrote, every job that reached an ending, the audit rows. What it tidies:
a job that never reached an ending is cancelled the way extension_smoke.mjs
cancels one (columns and embedded plan together, or workflow_guard refuses), so
nothing fires later in a Chrome that pairs to this owner. `--keep` leaves it.

BEFORE THE BRAIN SERVES THIS OWNER. The supervisor spawns one container per
real-email owner and skips `.invalid` signups by design
(migration/workers/brain/src/index.ts:170-183); an allowlist for this owner is
being taught to it in parallel. Until that lands, the API -> brain hop times
out with "no decision within N s" — expected, and reported as NOT PROVEN, not
as green. The rows stay unheard on D1 and will be heard by the first container
that serves the owner; `--sweep` afterwards cancels whatever it minted.

No pattern in this file decides what words MEAN (HARNESS-LAWS Law 1). The
three lines are chosen inputs; what the brain makes of them is the measurement.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from typing import Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from overnight import _env  # noqa: E402  (sets the gate User-Agent on urllib; loads .env.local)

DEFAULT_BASE = "https://api.anticipy.ai"
DEFAULT_OWNER = "qeuy6sv1raof9rw"
DEFAULT_PROFILE = "119d9hkfzycv9m6"
DEVICE_ID = "e2e-phone-2026-09-05"
SOURCE = "phone_mic"
USER_AGENT = "anticipy-e2e/1.0 (+https://github.com/anticipation-labs/Anticipy proof/e2e_cloudflare.py)"
# The production-capable arm is a scratch copy of proof/chrome_arm.mjs: the
# repo's own file refuses every non-loopback base by design, and the copy adds
# exactly one exception (api.anticipy.ai with this owner and no other). See
# research/2026-09-05-hands-live-run.md.
DEFAULT_ARM_SCRIPT = os.environ.get(
    "ANTICIPY_ARM_SCRIPT",
    "/private/tmp/claude-501/-Users-cjxsez-Desktop-Anticipy/"
    "ec1dc949-2c23-41d9-b42f-42443cfb4bb3/scratchpad/cf-smoke/chrome_arm_cf.mjs")
WRANGLER_CONFIG = os.path.join(REPO, "migration", "workers", "wrangler.jsonc")
D1_NAME = "anticipy-backend"

# The three moments, in the order they are spoken. (a) a fact worth remembering,
# said to the room; (b) an errand aimed at her that names the browser, so
# anticipy_core.job_lane keeps it on the browser lane whether or not the
# container carries a Brave key (anticipy_core.py:4036), and read-only, so a
# read-declaring triage queues it without an approval card; (c) a direct
# question, punctuated the way the phone's recognizer punctuates
# (PhoneListener.swift:1023 addsPunctuation = true).
LINES = (
    ("a", "ambient fact",
     "my dentist moved to Thursdays at 3, the one on Broadway"),
    ("b", "errand for the hands",
     "Anticipy, open example.com in my browser and tell me what the page heading says"),
    ("c", "direct question",
     "Anticipy, when is my dentist appointment now?"),
)

TERMINAL_JOB = ("done", "failed", "cancelled", "needs_user")
HEARTBEAT_LIVE_S = 120          # extension_smoke.mjs HEARTBEAT_LIVE_MS
OWNER_ID_RE = re.compile(r"^[a-z0-9]{15}$")
PB_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}Z$")


# ---------------------------------------------------------------- pure pieces
# Everything above the network is a plain function so tests/test_e2e_cloudflare.py
# can drive it with fakes. Nothing here decides meaning; it formats, compares
# and tabulates.

def wire_stamp(when: dt.datetime) -> str:
    """ISO8601DateFormatter.anticipyUTC: internet date-time with fractional
    seconds, always Z (AnticipyBackend.swift:1050)."""
    when = when.astimezone(dt.timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{when.microsecond // 1000:03d}Z"


def pb_stamp(when: dt.datetime) -> str:
    """The space-separated form PocketBase and the Worker compare correctly in
    a filter (proof/live_day.py:consequences; migration/workers/test/filter-dsl.test.ts:102)."""
    when = when.astimezone(dt.timezone.utc)
    return when.strftime("%Y-%m-%d %H:%M:%S.") + f"{when.microsecond // 1000:03d}Z"


def parse_pb_ts(value) -> Optional[dt.datetime]:
    """'YYYY-MM-DD HH:MM:SS.mmmZ' or the T form -> aware datetime, or None."""
    if not value:
        return None
    v = str(value).replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def capture_wire_fields(started_at: dt.datetime, ended_at: dt.datetime) -> dict:
    """CaptureEnvelope.wireFields: the start under BOTH names, the end once."""
    start = wire_stamp(started_at)
    return {"capture_started_at": start, "spoken_at": start,
            "capture_ended_at": wire_stamp(ended_at)}


def phone_body(text: str, owner_ref: str, started_at: dt.datetime,
               ended_at: dt.datetime, device_id: str = DEVICE_ID,
               source: str = SOURCE, speaker: Optional[str] = None,
               explicit: bool = False, parent_line: str = "",
               external_event_id: str = "") -> dict:
    """AnticipyBackend.pushEvent(kind: "transcript", ...), field for field.

    The ORDER of the optional keys and the rule for each omission are the
    Swift method's, so the row is byte-comparable with a real phone's:
      decision/goal   always sent, always ""  (the phone never stamps them)
      capture fields  the envelope's three columns
      parent_line     only when the 8s ceiling cut a sentence in half
      speaker         only when the voice check gave a verdict
      explicit        only when TRUE (typed at her); speech never sets it
      source          which ear; omitted when unknown, never sent empty
      external_event_id  only for idempotent app replies
      importance      day-zero paths only; a transcript never claims one
      owner_ref       whose words these are
    """
    body = {"device_id": device_id, "kind": "transcript", "text": text,
            "decision": "", "goal": ""}
    body.update(capture_wire_fields(started_at, ended_at))
    if parent_line:
        body["parent_line"] = parent_line
    if speaker:
        body["speaker"] = speaker
    if explicit:
        body["explicit"] = True
    if source:
        body["source"] = source
    if external_event_id:
        body["external_event_id"] = external_event_id
    if owner_ref:
        body["owner_ref"] = owner_ref
    return body


def decision_state(row: dict) -> str:
    """What the brain has written on a transcript row.
    unheard    decision "" — the poll has not picked it up (or no container)
    processing the brain claimed it (worker.claim) and has not decided yet
    stamped    a decision landed"""
    d = str((row or {}).get("decision") or "").strip()
    if not d:
        return "unheard"
    if d == "processing":
        return "processing"
    return "stamped"


def heard_state(row: dict) -> str:
    """Omi port 06 on the row: did the measurement land, and if not, WHY NOT.

    absent      the response carries no heard_ms/heard_calls key at all (or
                null): D1 has no such column yet — the ALTER waits for the
                owner. Distinct from the next line on purpose: the brain then
                PATCHes without the measurement (worker._HEARD_COLUMNS_ACCEPTED)
                and the decision still lands.
    unstamped   the columns exist and read 0 on a decided row: the worker that
                decided did not measure (an older build, or the retry path).
    measured:<ms>/<calls>
    unheard     no decision yet, so nothing was expected here."""
    if decision_state(row) != "stamped":
        return "unheard"
    ms = (row or {}).get("heard_ms", None)
    calls = (row or {}).get("heard_calls", None)
    if "heard_ms" not in (row or {}) or ms is None:
        return "absent"
    try:
        ms_n = int(float(ms))
        calls_n = int(float(calls if calls is not None else 0))
    except (TypeError, ValueError):
        return "unstamped"
    if ms_n <= 0 and calls_n <= 0:
        return "unstamped"
    return f"measured:{ms_n}/{calls_n}"


def is_beating(agent: dict, now: Optional[dt.datetime] = None,
               live_s: int = HEARTBEAT_LIVE_S) -> bool:
    """Paired is not live: the heartbeat alarm beats every 30 s, so a row whose
    last_seen is minutes old is a closed Chrome (extension_smoke.mjs)."""
    if not (agent or {}).get("paired"):
        return False
    seen = parse_pb_ts(agent.get("last_seen"))
    if not seen:
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    return (now - seen).total_seconds() < live_s


def audit_sql(owner_ref: str, since: str) -> str:
    """The read-only D1 query for the hands' model calls. agent_llm_audit is
    not served over HTTP (migration/workers/src/llm.ts:370), so it is read with
    wrangler. The two values interpolated are format-checked first: an owner
    id is 15 [a-z0-9] and a stamp is one exact shape, so nothing else can be
    spliced into the string."""
    if not OWNER_ID_RE.match(owner_ref or ""):
        raise ValueError(f"not an owner id: {owner_ref!r}")
    if not PB_STAMP_RE.match(since or ""):
        raise ValueError(f"not a record stamp: {since!r}")
    return ("SELECT id, created, agent_id, provider, model, provider_model, status, "
            "http_status, duration_ms, proxy_version, client_request_json, "
            "provider_request_json FROM agent_llm_audit "
            f"WHERE owner_ref = '{owner_ref}' AND created >= '{since}' "
            "ORDER BY created")


def audit_summary(row: dict) -> dict:
    """One audit row -> the fields the plan's hands row asks for. max_tokens is
    read from the client's request AND the provider's, because the proxy's
    512 floor is the difference between them."""
    def cap(raw):
        try:
            return json.loads(raw or "").get("max_tokens")
        except (ValueError, AttributeError, TypeError):
            return None
    return {
        "id": row.get("id"), "created": row.get("created"),
        "agent_id": row.get("agent_id"),
        "provider": row.get("provider"), "model": row.get("model"),
        "provider_model": row.get("provider_model"),
        "status": row.get("status"), "http_status": row.get("http_status"),
        "duration_ms": row.get("duration_ms"),
        "max_tokens_client": cap(row.get("client_request_json")),
        "max_tokens_provider": cap(row.get("provider_request_json")),
    }


HOPS = (
    # (name, provable from this machine)
    ("ears -> API", True),
    ("API -> brain", True),
    ("brain -> mouth", True),
    ("brain -> hands", True),
    ("hands", True),
    ("hands -> mouth", False),
    ("memory", False),
)


class HopTable:
    """One row per hop of the plan's design table. A hop is PROVEN only with
    an artefact id; NOT PROVEN carries the exact reason; a hop that cannot be
    proven from here says so and never counts toward the exit code."""

    def __init__(self):
        self.rows = {name: {"provable": provable, "proven": False,
                            "detail": "not reached"} for name, provable in HOPS}

    def proven(self, hop: str, artefact: str):
        self.rows[hop].update(proven=True, detail=artefact)

    def not_proven(self, hop: str, reason: str):
        self.rows[hop].update(proven=False, detail=reason)

    def exit_code(self) -> int:
        provable = [r for r in self.rows.values() if r["provable"]]
        return 0 if provable and all(r["proven"] for r in provable) else 2

    def lines(self) -> list:
        out = []
        for name, _ in HOPS:
            r = self.rows[name]
            if r["proven"]:
                state = "PROVEN     "
            elif not r["provable"]:
                state = "NOT HERE   "
            else:
                state = "NOT PROVEN "
            out.append(f"  {name:<16} {state} {r['detail']}")
        return out


# ------------------------------------------------------------------- plumbing

def env_root(start: str = REPO) -> str:
    """Where .env.local lives. A git worktree under .claude/worktrees/ has no
    copy of its own, so walk up until one appears (ANTICIPY_ENV_ROOT wins)."""
    forced = os.environ.get("ANTICIPY_ENV_ROOT", "").strip()
    if forced:
        return forced
    here = start
    while True:
        if os.path.exists(os.path.join(here, _env.FILENAME)):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            return start
        here = parent


class Api:
    """The service principal, the way the gates and the brain speak: the
    routing marker plus the token (brain/pb.py), and a named User-Agent
    because Cloudflare answers 403 1010 to Python-urllib's (overnight/_env.py)."""

    def __init__(self, base: str, token: str):
        import requests  # already a dependency of brain/ and the gates
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"X-Anticipy-Worker": "1", "User-Agent": USER_AGENT,
                               "Content-Type": "application/json"})
        if token:
            self.s.headers["X-Anticipy-Token"] = token

    def get(self, path: str, **params):
        return self.s.get(f"{self.base}{path}", params=params or None, timeout=30)

    def post(self, path: str, body: dict):
        return self.s.post(f"{self.base}{path}", data=json.dumps(body), timeout=30)

    def patch(self, path: str, body: dict):
        return self.s.patch(f"{self.base}{path}", data=json.dumps(body), timeout=30)

    def delete(self, path: str):
        return self.s.delete(f"{self.base}{path}", timeout=30)

    def record(self, collection: str, rid: str) -> dict:
        r = self.get(f"/api/collections/{collection}/records/{rid}")
        return r.json() if r.ok else {"_status": r.status_code, "_body": r.text[:200]}

    def list(self, collection: str, filt: str, sort: str = "created",
             per_page: int = 50, fields: str = "") -> list:
        params = {"filter": filt, "sort": sort, "perPage": per_page}
        if fields:
            params["fields"] = fields
        r = self.get(f"/api/collections/{collection}/records", **params)
        if not r.ok:
            raise RuntimeError(f"GET {collection} {filt!r} -> {r.status_code} {r.text[:200]}")
        return r.json().get("items", [])


def say(line: str = ""):
    print(line, flush=True)


def short(s, n: int = 200) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()[:n]


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def clock() -> str:
    return now_utc().strftime("%H:%M:%SZ")


def arm_commands(arm_script: str, base: str, owner: str) -> list:
    env_file = os.path.join(env_root(), _env.FILENAME)
    tok = f"ANTICIPY_SERVICE_TOKEN=$(grep '^ANTICIPY_SERVICE_TOKEN=' {env_file} | cut -d= -f2-)"
    return [
        f"{tok} node {arm_script} up --base={base} --owner-ref={owner} --headed",
        f"{tok} node {arm_script} status --base={base} --owner-ref={owner}",
        f"{tok} node {arm_script} down --base={base} --owner-ref={owner}",
        f"(proof/chrome_arm.mjs itself refuses a non-loopback base by design; the copy adds "
        f"one exception: {base} with --owner-ref={owner} and no other owner)",
    ]


# ---------------------------------------------------------------------- tidy

def cancel_job(api: Api, job: dict, why: str) -> bool:
    """extension_smoke.mjs:tidy — the columns and the embedded plan move
    together, or workflow_guard refuses the write."""
    jid = job.get("id")
    try:
        params = json.loads(job.get("params") or "{}")
    except ValueError:
        params = {}
    plan = dict(params.get("_workflow") or {})
    plan.update(state="cancelled", lease=None, attempts=int(job.get("attempts") or 0),
                reason=why, updated_at=now_utc().isoformat())
    body = {"status": "cancelled", "workflow_state": "cancelled",
            "workflow_version": int(job.get("workflow_version") or 1),
            "lease_token": "", "lease_until": "",
            "params": json.dumps({**params, "_workflow": plan}),
            "result": job.get("result") or why}
    r = api.patch(f"/api/collections/jobs/records/{jid}", body)
    if r.ok:
        return True
    d = api.delete(f"/api/collections/jobs/records/{jid}")
    return d.ok


def sweep(api: Api, owner: str, device_id: str, keep: bool) -> int:
    """Tidy an earlier run: list this device's unheard lines (they stay — a
    container that arrives later must be allowed to hear them) and cancel
    every job of this owner that never reached an ending."""
    unheard = api.list("events", f'owner_ref="{owner}" && kind="transcript" && '
                                 f'device_id="{device_id}" && decision=""',
                       fields="id,created,text")
    say(f"unheard lines from {device_id}: {len(unheard)}")
    for ev in unheard:
        say(f"  {ev.get('id')}  {ev.get('created')}  {short(ev.get('text'), 80)!r}")
    open_jobs = [j for j in api.list("jobs", f'owner_ref="{owner}"', sort="-created")
                 if j.get("status") not in TERMINAL_JOB]
    say(f"jobs of {owner} not at an ending: {len(open_jobs)}")
    for j in open_jobs:
        line = f"  {j.get('id')}  {j.get('status')}  {short(j.get('goal'), 80)!r}"
        if keep:
            say(line + "  (kept)")
            continue
        ok = cancel_job(api, j, "cancelled by proof/e2e_cloudflare.py --sweep")
        say(line + ("  -> cancelled" if ok else "  -> COULD NOT CANCEL; cancel it by hand"))
    return 0


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default=os.environ.get("ANTICIPY_BACKEND_URL") or DEFAULT_BASE)
    ap.add_argument("--owner", default=DEFAULT_OWNER, help="owners row id (default: the disposable e2e owner)")
    ap.add_argument("--profile-id", default=DEFAULT_PROFILE, help="owner_profile row id to GET by id")
    ap.add_argument("--device-id", default=DEVICE_ID)
    ap.add_argument("--speaker", default="", help='voice verdict to stamp ("owner"); default: none, as a phone without an enrolled voice sends')
    ap.add_argument("--gap", type=float, default=4.0, help="seconds between the three lines")
    ap.add_argument("--wait", type=int, default=420, help="seconds to wait for the brain's decisions")
    ap.add_argument("--poll", type=int, default=10, help="seconds between polls")
    ap.add_argument("--settle", type=int, default=8, help="seconds to wait after the last stamp for the reply rows")
    ap.add_argument("--job-wait", type=int, default=240, help="seconds to watch a job to an ending")
    ap.add_argument("--keep", action="store_true", help="leave an unfinished job in place")
    ap.add_argument("--no-wrangler", action="store_true", help="do not read agent_llm_audit through wrangler")
    ap.add_argument("--arm-script", default=DEFAULT_ARM_SCRIPT)
    ap.add_argument("--dry-run", action="store_true", help="print the phone-shaped bodies and stop")
    ap.add_argument("--sweep", action="store_true", help="tidy an earlier run; post nothing")
    args = ap.parse_args()

    root = env_root()
    loaded = _env.load(root)
    line = _env.announce(loaded, root)
    if line:
        say(line)
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN", "")
    if not token and not args.dry_run:
        say("FAIL  no ANTICIPY_SERVICE_TOKEN (in the environment or .env.local): every read is 403 without it")
        return 1
    if not OWNER_ID_RE.match(args.owner):
        say(f"FAIL  {args.owner!r} is not an owner id")
        return 1

    say(f"Anticipy end-to-end on Cloudflare — {now_utc().isoformat(timespec='seconds')}")
    say(f"base      {args.base}")
    say(f"owner     {args.owner}")
    say(f"device    {args.device_id} · source {SOURCE}")
    say()

    if args.dry_run:
        t = now_utc()
        for key, what, text in LINES:
            body = phone_body(text, args.owner, t - dt.timedelta(seconds=3), t,
                              device_id=args.device_id, speaker=args.speaker or None)
            say(f"({key}) {what}\n{json.dumps(body, indent=2)}")
        return 0

    api = Api(args.base, token)
    table = HopTable()

    if args.sweep:
        return sweep(api, args.owner, args.device_id, args.keep)

    # 1 ------------------------------------------------------------ preflight
    say("1. preflight")
    r = api.get("/api/health")
    if not (r.status_code == 200 and "healthy" in r.text.lower()):
        say(f"   FAIL  GET /api/health -> {r.status_code} {short(r.text, 120)}")
        return 1
    say("   PASS  the API answers (GET /api/health -> 200)")

    # The owner, from the service route the brain itself uses (owners by id
    # is 404 to the service principal on purpose: records.ts:103-119).
    found = False
    page = 1
    while page < 50:
        r = api.get("/worker/owners", page=page, perPage=200)
        if not r.ok:
            say(f"   FAIL  GET /worker/owners -> {r.status_code} {short(r.text, 120)}")
            return 1
        items = r.json().get("items", [])
        if any(o.get("id") == args.owner for o in items):
            found = True
            break
        if len(items) < 200:
            break
        page += 1
    if not found:
        say(f"   FAIL  /worker/owners does not list {args.owner}")
        return 1
    profile = api.record("owner_profile", args.profile_id)
    if profile.get("owner_ref") != args.owner:
        say(f"   FAIL  owner_profile {args.profile_id} is not {args.owner}'s: {short(profile, 160)}")
        return 1
    email = str(profile.get("email") or "")
    phone = str(profile.get("phone") or "")
    # THE SEATBELT. A real owner's phone would receive whatever the brain
    # decides to text about these lines. Refuse, do not warn.
    if not email.endswith(".invalid"):
        say(f"   FAIL  refusing: {args.owner}'s profile email is not a .invalid test address; "
            "this file only ever runs against a disposable owner")
        return 1
    say(f"   PASS  the owner exists: {args.owner} · profile {profile.get('id')} "
        f"({profile.get('first_name')} {profile.get('last_name')}, {email}, {phone})")
    say(f"         {phone} is a fictional 555 number: Twilio refuses it, so no text reaches anyone")

    # Do the Omi-06 columns exist on D1? A filter over the column errors when
    # it does not, which is a cleaner signal than a missing key on a row.
    r = api.get("/api/collections/events/records",
                filter=f'owner_ref="{args.owner}" && heard_ms>=0', perPage=1, fields="id")
    heard_cols = "present" if r.ok else f"absent ({r.status_code}: {short(r.text, 80)})"
    say(f"   ....  heard_ms/heard_calls on D1: {heard_cols}")

    def census() -> tuple:
        rows = api.list("agents", f'owner_ref="{args.owner}"', sort="-last_seen", per_page=50,
                        fields="id,agent_id,browser,paired,last_seen")
        paired = [a for a in rows if a.get("paired")]
        return paired, [a for a in paired if is_beating(a)]

    paired, beating = census()
    if beating:
        a = beating[0]
        say(f"   PASS  an arm is beating: agents row {a.get('id')} · {a.get('browser')} · "
            f"last_seen {a.get('last_seen')}")
    else:
        say(f"   ....  no arm is beating for this owner ({len(paired)} paired, none live in {HEARTBEAT_LIVE_S} s)")
        say("         the hands hops cannot be proven this run; to bring one up:")
        for c in arm_commands(args.arm_script, args.base, args.owner):
            say(f"           {c}")

    backlog = api.list("events", f'owner_ref="{args.owner}" && kind="transcript" && decision=""',
                       fields="id,created,device_id")
    if backlog:
        say(f"   ....  {len(backlog)} unheard transcript row(s) already wait for this owner "
            f"(oldest {backlog[0].get('created')}); a container hears those first")
    open_jobs = [j for j in api.list("jobs", f'owner_ref="{args.owner}"', sort="-created",
                                     fields="id,status,goal")
                 if j.get("status") not in TERMINAL_JOB]
    if open_jobs:
        say(f"   ....  {len(open_jobs)} job(s) of this owner not at an ending: "
            + ", ".join(f"{j.get('id')}={j.get('status')}" for j in open_jobs))
    say()

    # 2 -------------------------------------------------------- ears -> API
    say("2. ears -> API: three lines, posted as the phone posts them")
    posted = []      # (key, what, text, id, created)
    since = ""       # the earliest server `created` we wrote, minus a second
    for n, (key, what, text) in enumerate(LINES):
        if n:
            time.sleep(args.gap)
        ended = now_utc()
        started = ended - dt.timedelta(seconds=0.4 * len(text.split()))
        body = phone_body(text, args.owner, started, ended,
                          device_id=args.device_id, speaker=args.speaker or None)
        r = api.post("/api/collections/events/records", body)
        if not r.ok or not (r.json() or {}).get("id"):
            say(f"   FAIL  ({key}) POST /api/collections/events/records -> {r.status_code} {short(r.text, 240)}")
            table.not_proven("ears -> API", f"line ({key}) refused: {r.status_code}")
            break
        rid = r.json()["id"]
        back = api.record("events", rid)
        same = all(back.get(k) == body[k] for k in ("text", "device_id", "source", "owner_ref",
                                                    "capture_started_at", "kind"))
        if not same:
            say(f"   FAIL  ({key}) row {rid} did not read back as posted: {short(back, 240)}")
            table.not_proven("ears -> API", f"row {rid} differs from what was posted")
            break
        created = str(back.get("created") or "")
        if not since:
            first = parse_pb_ts(created) or now_utc()
            since = pb_stamp(first - dt.timedelta(seconds=1))
        posted.append((key, what, text, rid, created))
        say(f"   PASS  ({key}) {what}: events row {rid} · created {created}")
        say(f"         {text!r}")
    if len(posted) == len(LINES):
        table.proven("ears -> API", "events " + ", ".join(p[3] for p in posted)
                     + "  (the design's fallback: a phone-shaped POST, not a phone)")
    else:
        say()
        say("   the ears hop failed; nothing downstream can be measured")
        say()
        for l in table.lines():
            say(l)
        return 1
    say()

    # 3 --------------------------------------------------------- API -> brain
    say(f"3. API -> brain: polling every {args.poll} s for up to {args.wait} s")
    ids = [p[3] for p in posted]
    stamped: dict = {}
    processing_seen: set = set()
    says: dict = {}
    slots: dict = {}
    other_brain: dict = {}
    jobs: dict = {}
    t0 = time.time()

    def sweep_brain_rows():
        rows = api.list("events", f'owner_ref="{args.owner}" && device_id="anticipy-brain" '
                                  f'&& created>="{since}"')
        for ev in rows:
            k = ev.get("kind")
            bucket = says if k == "anticipy_says" else slots if k == "uninvited_slot" else other_brain
            if ev["id"] in bucket:
                continue
            bucket[ev["id"]] = ev
            say(f"   [{clock()}] {k} row {ev['id']} · created {ev.get('created')} · "
                f"decision {ev.get('decision')!r} · goal {short(ev.get('goal'), 60)!r}")
            if k in ("anticipy_says", "anticipy_text"):
                say(f"              she says: {short(ev.get('text'), 300)!r}")
            if ev.get("external_event_id"):
                say(f"              external_event_id {ev.get('external_event_id')}")
        for j in api.list("jobs", f'owner_ref="{args.owner}" && created>="{since}"'):
            if j["id"] in jobs:
                continue
            jobs[j["id"]] = j
            say(f"   [{clock()}] jobs row {j['id']} · created {j.get('created')} · status {j.get('status')} · "
                f"lane {j.get('lane')!r} · consequence {j.get('consequence')!r} · "
                f"workflow_id {'set' if j.get('workflow_id') else 'MISSING'}")
            say(f"              goal: {short(j.get('goal'), 200)!r}")

    while True:
        for key, what, text, rid, created in posted:
            if rid in stamped:
                continue
            row = api.record("events", rid)
            st = decision_state(row)
            if st == "stamped":
                stamped[rid] = row
                say(f"   [{clock()}] ({key}) {rid} decision {row.get('decision')!r} · "
                    f"addressee {row.get('addressee')!r} · goal {short(row.get('goal'), 80)!r} · "
                    f"heard {heard_state(row)}")
            elif st == "processing" and rid not in processing_seen:
                processing_seen.add(rid)
                say(f"   [{clock()}] ({key}) {rid} claimed by the brain (decision=processing)")
        sweep_brain_rows()
        if len(stamped) == len(ids):
            break
        if time.time() - t0 > args.wait:
            break
        time.sleep(args.poll)
    if len(stamped) == len(ids):
        # mark_processed lands BEFORE the anticipy_says row is posted
        # (worker.py:~4870-4885); give the reply a moment to appear.
        time.sleep(args.settle)
        sweep_brain_rows()
        heard = {rid: heard_state(row) for rid, row in stamped.items()}
        absent = [rid for rid, h in heard.items() if h == "absent"]
        unst = [rid for rid, h in heard.items() if h == "unstamped"]
        bounds = ("bounds measured" if not absent and not unst
                  else "heard_ms/heard_calls COLUMN ABSENT on D1 (the ALTER waits for the owner)" if absent
                  else "heard_ms/heard_calls present but NOT STAMPED")
        table.proven("API -> brain", "decisions on " + ", ".join(
            f"{rid}={row.get('decision')}" for rid, row in stamped.items()) + f"; {bounds}")
    else:
        waited = int(time.time() - t0)
        missing = [rid for rid in ids if rid not in stamped]
        claimed = [rid for rid in missing if rid in processing_seen]
        why = (f"no decision within {waited} s on {', '.join(missing)}"
               + (f" ({len(claimed)} claimed, never decided)" if claimed else "")
               + " — no container serves this owner yet, or the brain is not polling D1")
        say(f"   ....  {why}")
        table.not_proven("API -> brain", why)
    say()

    # 4 -------------------------------------------------------- brain -> hands
    say("4. brain -> hands: did the errand become a job, and did a Chrome run it")
    job = None
    if jobs:
        # THE ERRAND'S JOB IS THE ONE ON THE BROWSER LANE (lane ""). The ambient
        # line may mint a research card (lane "research") first — it did, on
        # 2026-09-05 — and taking the oldest job blindly graded the hands on a
        # card the hands never see. Prefer the browser-lane job; fall back to
        # the oldest only when there is none, and say so.
        ordered = sorted(jobs.values(), key=lambda j: str(j.get("created")))
        browser = [j for j in ordered if not str(j.get("lane") or "")]
        research = [j for j in ordered if str(j.get("lane") or "") == "research"]
        for card in research:
            say(f"   ....  research card {card['id']} (lane \"research\", {card.get('status')}): "
                f"{(card.get('goal') or '')[:80]!r} — the brain's own lane, not the hands'")
        job = (browser or ordered)[0]
        if job.get("workflow_id"):
            table.proven("brain -> hands", f"jobs row {job['id']} · lane {job.get('lane')!r} · "
                                           f"consequence {job.get('consequence')!r} · status at mint {job.get('status')}")
        else:
            table.not_proven("brain -> hands", f"jobs row {job['id']} carries no workflow metadata; "
                                               "the extension's poll filter can never see it")
    elif len(stamped) == len(ids):
        b_row = stamped.get(posted[1][3], {})
        table.not_proven("brain -> hands", f"no job minted; the errand line was stamped "
                                           f"{b_row.get('decision')!r} ({short(b_row.get('goal'), 80)!r})")
        table.not_proven("hands", "nothing to run: no job was minted")
    else:
        table.not_proven("brain -> hands", "no job: the brain never decided the errand line")
        table.not_proven("hands", "nothing to run: the brain never decided the errand line")

    if job:
        paired, beating = census()
        lane = str(job.get("lane") or "")
        if lane == "research":
            say(f"   ....  job {job['id']} is on the brain's own research lane (lane=\"research\"); "
                "Chrome is kept away from it by design — watching the brain run it instead")
        elif lane:
            say(f"   ....  job {job['id']} is on lane {lane!r}, which is not the browser's")
        if not beating and lane == "":
            say(f"   ....  job {job['id']} is queued and no arm is beating; nothing can claim it")
            for c in arm_commands(args.arm_script, args.base, args.owner):
                say(f"           {c}")
            table.not_proven("hands", f"job {job['id']} queued, no arm beating (bring one up: see above)")
        else:
            t1 = time.time()
            last = None
            ending = None
            while time.time() - t1 < args.job_wait:
                row = api.record("jobs", job["id"])
                sig = (row.get("status"), row.get("workflow_state"), row.get("claimed_by"),
                       int(float(row.get("attempts") or 0)))
                if sig != last:
                    last = sig
                    say(f"   [{clock()}] job {job['id']} status {sig[0]!r} · workflow_state {sig[1]!r} · "
                        f"claimed_by {sig[2] or '-'} · attempt {sig[3]} · lease_until {row.get('lease_until') or '-'}")
                if row.get("status") in TERMINAL_JOB:
                    ending = row
                    break
                if row.get("status") == "awaiting_confirm":
                    say("   ....  held for approval — a read-only errand should not land here, and "
                        "this file never approves on the owner's behalf")
                    ending = row
                    break
                time.sleep(3)
            if not ending:
                table.not_proven("hands", f"job {job['id']} still {last[0] if last else '?'} after {args.job_wait} s")
            elif ending.get("status") == "done":
                say(f"   PASS  done in {int(time.time() - t1)} s · result: {short(ending.get('result'), 300)!r}")
                say(f"         receipt: {short(ending.get('receipt'), 300) or '(empty)'}")
                say(f"         claimed_by {ending.get('claimed_by')} · attempts {ending.get('attempts')} · "
                    f"workflow_version {ending.get('workflow_version')}")
                who = "the brain's research arm" if ending.get("claimed_by") == "worker-research" else "a Chrome"
                if who != "a Chrome":
                    table.not_proven("hands", f"job {job['id']} was finished by {who}, not by the hands")
                else:
                    table.proven("hands", f"job {job['id']} done by {ending.get('claimed_by')} · receipt "
                                          f"{'present' if ending.get('receipt') else 'EMPTY'}")
            else:
                say(f"   ....  job ended as {ending.get('status')!r}: {short(ending.get('result'), 300)!r}")
                table.not_proven("hands", f"job {job['id']} ended as {ending.get('status')}: "
                                          f"{short(ending.get('result'), 120)}")
            # The model calls, from the ledger the Worker keeps off the HTTP surface.
            if not args.no_wrangler:
                say("   ....  agent_llm_audit rows for this owner since the run began (wrangler d1, read-only):")
                try:
                    out = subprocess.run(
                        ["npx", "--no-install", "wrangler", "d1", "execute", D1_NAME, "--remote",
                         "--json", "--config", WRANGLER_CONFIG, "--command",
                         audit_sql(args.owner, since)],
                        capture_output=True, text=True, timeout=120, cwd=REPO)
                    text = out.stdout[out.stdout.find("["):] if "[" in out.stdout else ""
                    results = json.loads(text)[0].get("results", []) if text else []
                    if out.returncode != 0:
                        say(f"         could not read: wrangler exit {out.returncode}: {short(out.stderr, 200)}")
                    elif not results:
                        say("         none — the run made no model call through /agent/llm")
                    for a in results:
                        s = audit_summary(a)
                        say(f"         {s['id']} · {s['created']} · provider {s['provider']} · model {s['model']} "
                            f"· status {s['status']} ({s['http_status']}) · {s['duration_ms']} ms · "
                            f"max_tokens client {s['max_tokens_client']} / provider {s['max_tokens_provider']} "
                            f"· agent {s['agent_id']}")
                except (OSError, ValueError, subprocess.TimeoutExpired, IndexError) as e:
                    say(f"         could not read: {e}")
    say()

    # 5 -------------------------------------------------------- brain -> mouth
    say("5. brain -> mouth: what she wrote back")
    if says:
        for ev in sorted(says.values(), key=lambda e: str(e.get("created"))):
            say(f"   anticipy_says {ev['id']} · {ev.get('created')} · decision {ev.get('decision')!r}")
            say(f"      {short(ev.get('text'), 400)!r}")
        table.proven("brain -> mouth", "anticipy_says " + ", ".join(sorted(says)))
    else:
        reason = ("no anticipy_says row for this owner since the run began"
                  + ("" if len(stamped) == len(ids) else " (the brain never decided)"))
        say(f"   ....  {reason}")
        table.not_proven("brain -> mouth", reason)
    if slots:
        say("   uninvited_slot rows (Omi port 10b — one per uninvited text, reserved before the send):")
        for ev in slots.values():
            say(f"      {ev['id']} · {ev.get('created')} · door {ev.get('decision')!r} · {ev.get('external_event_id')}")
    texts = [e for e in other_brain.values() if e.get("kind") in ("anticipy_text", "notification_status")]
    if texts:
        say("   text attempts (the number is fictional; none of these reached a phone):")
        for ev in texts:
            say(f"      {ev.get('kind')} {ev['id']} · {ev.get('created')} · {ev.get('decision')!r} · {short(ev.get('text'), 120)!r}")
    table.not_proven("hands -> mouth", f"not provable here: {phone} is a fictional 555 number, Twilio refuses it; "
                                       "the design wants the owner's own phone for this row")
    say()

    # 6 --------------------------------------------------------------- memory
    say("6. memory: not provable inside one run")
    say("   tomorrow, as this device: post 'Anticipy, when is my dentist appointment?' and expect an")
    say("   anticipy_says row naming Thursday at 3 on Broadway; or read the container's memory_notes")
    say("   (per-owner SQLite, pulled from R2 at boot). Skipped honestly.")
    table.not_proven("memory", "not provable in one run: the next morning's recall is the test")
    say()

    # ------------------------------------------------------------------ tidy
    left = []
    for j in jobs.values():
        row = api.record("jobs", j["id"])
        if row.get("status") in TERMINAL_JOB:
            say(f"tidy: job {j['id']} left as {row.get('status')} (it is the evidence)")
            continue
        if args.keep:
            say(f"tidy: --keep, job {j['id']} left at {row.get('status')}")
            left.append(j["id"])
            continue
        ok = cancel_job(api, row, "cancelled by proof/e2e_cloudflare.py: the run is over and nothing may fire later")
        say(f"tidy: job {j['id']} {'cancelled so it cannot fire later' if ok else 'COULD NOT BE CANCELLED — cancel it by hand'}")
        if not ok:
            left.append(j["id"])
    if len(stamped) < len(ids):
        say(f"tidy: {len(ids) - len(stamped)} transcript row(s) left unheard on purpose — the first container "
            "that serves this owner will hear them; run --sweep afterwards")
    say()

    # ----------------------------------------------------------------- table
    say("THE DESIGN TABLE (research/2026-09-05-cloudflare-era-plan.md, one row per hop)")
    for l in table.lines():
        say(l)
    say()
    say("evidence rows left on D1:")
    say("  events (transcript): " + ", ".join(ids))
    if says:
        say("  events (anticipy_says): " + ", ".join(sorted(says)))
    if slots:
        say("  events (uninvited_slot): " + ", ".join(sorted(slots)))
    if other_brain:
        say("  events (other brain rows): " + ", ".join(f"{k}={v.get('kind')}" for k, v in other_brain.items()))
    if jobs:
        say("  jobs: " + ", ".join(sorted(jobs)))
    if left:
        say("  jobs left NOT at an ending: " + ", ".join(left))
    code = table.exit_code()
    say()
    say("VERDICT: " + ("every hop that can be proven from here is proven" if code == 0
                       else "UNPROVEN — at least one hop that can be proven from here is not"))
    return code


if __name__ == "__main__":
    sys.exit(main())
