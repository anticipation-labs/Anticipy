"""Push proof/ambient/corpus.json through the LIVE rig, one utterance at a
time, exactly the way the phone does, and record what the brain decided.

    ~/.anticipy-rig/venv/bin/python proof/ambient/run.py            # all of it
    ~/.anticipy-rig/venv/bin/python proof/ambient/run.py --limit 20 # a taste
    ~/.anticipy-rig/venv/bin/python proof/ambient/run.py --only amb-0001,amb-0044
    ~/.anticipy-rig/venv/bin/python proof/ambient/run.py --fresh    # ignore prior results

Then:  ~/.anticipy-rig/venv/bin/python proof/ambient/score.py

WHAT IT WRITES: proof/ambient/results.jsonl, one JSON object per utterance,
appended and fsynced as it goes. Append-only is the whole resumability story —
a run that dies at line 180 has 180 real answers on disk, and rerunning skips
every id already present. No partial-state file to get out of step with the
database.

WHAT IT SENDS, and why it is shaped like this:

  kind="transcript", device_id, owner_ref, decision="", source="phone_mic",
  explicit=false

  That is the app's own payload (app/ios/Anticipy/AnticipyApp.swift:249-275,
  mirrored in proof/local_rig.sh:308-310) with ONE deliberate difference:
  local_rig.sh sends explicit=true because a human typed the line into a test
  harness. Ambient speech is never explicit — the owner is not addressing the
  device — and explicit rides all the way into the consequential-action gate
  (brain/anticipy_core.py:1708). Sending true would quietly hand the brain the
  answer to the question this corpus exists to ask.

  `speaker` is left EMPTY on purpose, including for the lines a bystander says.
  The phone's roster is measured at 97% never-seen-before voices
  (anticipy_core.py:1178-1183), so a real pendant hands the brain no usable
  verdict on who spoke. Stamping speaker="other" on those rows would test a
  signal the product does not have.

WHY IT STAMPS capture_started_at: because otherwise every one of these 320
lines lands inside a single conversation. brain/segmenter.py:159-169 closes a
segment after 45s of silence and place_turn measures that against the CAPTURE
time, not arrival — so lines pushed eight seconds apart are one long
conversation, and unrelated corpus items would be fed to each other as context.
A virtual clock (50s between corpus items, 10s between turns of one authored
conversation) makes the segmentation match the corpus. The phone stamps this
field itself, so this is faithfulness, not a trick.

  The clock starts FIVE MINUTES AHEAD of now, so the first line is guaranteed
  to close whatever segment somebody else left open on the shared rig, and it
  stays inside the worker's six-hour skew tolerance (worker.py:1802,1843) so
  capture_key keeps believing it.

RATE LIMIT: one utterance in flight at a time, and the next is not pushed until
the previous has a stamped decision (or times out). Plus --gap seconds of
deliberate idle. There is a live model behind this; a stampede measures the
provider's rate limiter, not the brain.

LOOPBACK ONLY: the backend URL is checked before anything is sent and the
process refuses to run against a host that is not this machine. Production is
the owner's real life.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RIG = os.environ.get("ANTICIPY_RIG_DIR", os.path.expanduser("~/.anticipy-rig"))

# Only this machine. Anything else is somebody's real life.
LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


def check_loopback(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in LOOPBACK:
        raise SystemExit(
            f"REFUSING TO RUN against {url!r}. This harness posts hundreds of "
            "transcript events and mints jobs; the only place that is safe is "
            "the local rig.")
    return url.rstrip("/")


def check_worker_is_current(repo: str) -> str:
    """Refuse to measure a worker that predates the code under test.

    Python binds its imports at process start. `brain.worker` running since
    14:15 does not contain an orchestrator.py edited at 14:38, and NOTHING
    says so: the log line is identical, the decisions look plausible, and an
    hour of live model calls scores the wrong brain. This happened twice in
    one afternoon on this rig — once from a 24-hour-old process, once from a
    23-minute-old edit — and both times the numbers were believed first.

    A fingerprint check at rig startup cannot see the second case, because the
    edit lands after startup. Comparing file mtimes to the process start time
    catches both. Returns a human-readable description of what is running.
    """
    try:
        out = subprocess.run(["pgrep", "-f", "brain.worker"],
                             capture_output=True, text=True, timeout=10)
        pids = [p for p in out.stdout.split() if p.isdigit()]
    except Exception:
        return "worker: could not be inspected"
    if not pids:
        raise SystemExit("no brain.worker process is running — nothing will "
                         "ever stamp these events. Start the rig first.")
    started = None
    for pid in pids:
        ps = subprocess.run(["ps", "-o", "lstart=", "-p", pid],
                            capture_output=True, text=True)
        stamp = ps.stdout.strip()
        if not stamp:
            continue
        try:
            when = datetime.strptime(stamp, "%a %b %d %H:%M:%S %Y").timestamp()
        except ValueError:
            continue
        started = when if started is None else min(started, when)
    if started is None:
        return f"worker: pid {','.join(pids)}, start time unreadable"

    newest, newest_path = 0.0, ""
    for root, _dirs, files in os.walk(os.path.join(repo, "brain")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            mtime = os.path.getmtime(path)
            if mtime > newest:
                newest, newest_path = mtime, path
    if newest > started:
        raise SystemExit(
            "REFUSING TO RUN against a stale worker.\n"
            f"  {os.path.relpath(newest_path, repo)} was modified "
            f"{time.strftime('%H:%M:%S', time.localtime(newest))}\n"
            f"  brain.worker (pid {','.join(pids)}) started "
            f"{time.strftime('%H:%M:%S', time.localtime(started))}\n"
            "The running process cannot contain that edit. Restart the worker "
            "or you will spend an hour of live model calls scoring code that "
            "is not the code under test.")
    return (f"worker: pid {','.join(pids)} up since "
            f"{time.strftime('%H:%M:%S', time.localtime(started))}, newer than "
            f"every file in brain/")


def _refused(err: Exception) -> bool:
    """Did the request never reach the server?

    PocketBase watches backend/pb_hooks and restarts itself whenever anything
    in there changes — which, on a rig several agents are sharing, is often.
    The restart is a few seconds of ECONNREFUSED. A retry is safe precisely
    because the connection was refused: nothing was sent, so nothing can be
    duplicated. Any other error is real and is allowed to surface.
    """
    reason = getattr(err, "reason", None)
    return isinstance(err, urllib.error.URLError) and isinstance(
        reason, (ConnectionRefusedError, ConnectionResetError, TimeoutError))


def _req(method, url, body=None, timeout=15, tries=8):
    data = json.dumps(body).encode() if body is not None else None
    last: Exception | None = None
    for attempt in range(tries):
        req = urllib.request.Request(url, method=method, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
            return json.loads(raw) if raw else {}
        except Exception as e:
            last = e
            if not _refused(e):
                raise
            time.sleep(min(2.0 * (attempt + 1), 8.0))
    raise last if last else RuntimeError("unreachable")


def get(base, path, **params):
    q = urllib.parse.urlencode(params)
    return _req("GET", f"{base}{path}?{q}" if q else f"{base}{path}")


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def pb_ts(dt: datetime) -> str:
    """The ONLY timestamp shape PocketBase compares correctly in a filter.

    A `created>="2026-08-20T21:52:00.000Z"` filter does not error and does not
    match — it silently returns zero rows, which reads exactly like "she
    created no job". Measured against a table holding 37: the T form returned
    0, the space form returned 25. Two hours of "she never queues anything"
    came out of that. capture_started_at keeps the T form because the brain
    parses it with datetime.fromisoformat (brain/segmenter.py:76-87); only
    FILTER operands need this.
    """
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"


def load_done(path: str) -> dict:
    """Every id already answered, so a resumed run costs nothing twice."""
    done = {}
    if not os.path.exists(path):
        return done
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # A run killed mid-write leaves one torn line. Drop it and
                # keep the 179 good ones rather than refusing to resume.
                continue
            if rec.get("id"):
                done[rec["id"]] = rec
    return done


def append(path: str, rec: dict) -> None:
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def consequences(base, owner_ref, since_iso, until_iso=""):
    """WHAT ACTUALLY HAPPENED, as opposed to what she decided.

    The stamped decision is her verdict. These two are what a person would
    feel: a card in the queue and a message on the phone. They have to be read
    separately because decision="ignore" does NOT mean nothing happened —
    brain/anticipy_core.py:1358-1372 queues a non-consequential errand UNHELD
    and then overwrites the verdict with "ignore" ("quiet research, saying
    nothing"). The goal and the job both survive. Grading on the verdict alone
    scores her silence as failure when silence is the intended behaviour.

    `since`/`until` bracket the utterance, so a job minted by the NEXT line
    cannot be credited to this one.
    """
    out: dict = {}
    # NORMALISE HERE, not at the call sites. pb_ts() above documents why the
    # `T` form silently matches nothing, and backfill() duly converted its two
    # operands — but the LIVE path at the bottom of this file passed
    # `pushed_at` (an iso() string, T-separated) straight through, so every
    # row written by a live run carried said=[] and jobs=[] no matter what the
    # brain actually did. score.py reads exactly those two keys to decide
    # whether anything reached the owner, so every `act` line graded as lane
    # `silent`: 88 of 173 errands reported as MISSES that had in fact produced
    # a job. The measurement invented the failure it was built to detect.
    #
    # Two call sites, one already patched and one not, is the whole story. So
    # the conversion now lives at the single point every caller must pass
    # through, and callers may hand this function either shape.
    fix = lambda s: str(s or "").replace("T", " ")
    since_iso, until_iso = fix(since_iso), fix(until_iso)
    window = f'created>="{since_iso}"'
    if until_iso:
        window += f' && created<"{until_iso}"'
    try:
        said = get(base, "/api/collections/events/records",
                   filter=(f'kind="anticipy_says" && owner_ref="{owner_ref}" '
                           f'&& {window}'), perPage=5, sort="created")
        # Keep the says row's OWN goal and decision, not just its words.
        # This rig is shared: a browser job finished for another agent posts
        # an anticipy_says inside the same few seconds, and attributing it to
        # whatever line happened to be in flight invented two false pings out
        # of "The heading on example.com is Example Domain". The goal is what
        # tells the two apart.
        out["said"] = [{"text": i.get("text", "")[:200],
                        "goal": i.get("goal", ""),
                        "decision": i.get("decision", "")}
                       for i in said.get("items", [])]
    except Exception as e:
        out["said_error"] = str(e)[:120]
    try:
        jobs = get(base, "/api/collections/jobs/records",
                   filter=f'owner_ref="{owner_ref}" && {window}',
                   perPage=10, sort="created")
        out["jobs"] = [{"id": j["id"], "status": j.get("status"),
                        "lane": j.get("lane"), "goal": j.get("goal")}
                       for j in jobs.get("items", [])]
    except Exception as e:
        out["jobs_error"] = str(e)[:120]
    return out


def backfill(base, owner_ref, path):
    """Re-read the cards and messages for results already on disk.

    Exists because the first live run recorded them with a `T`-separated
    timestamp, which PocketBase accepts and never matches (see pb_ts). The
    verdicts in that file are real and expensive; only the consequence columns
    were blank, and they are recoverable from each row's pushed_at. Rerunning
    320 live model calls to recover a column that is sitting in the database
    would be waste, not rigour.
    """
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    rows.sort(key=lambda r: r.get("pushed_at") or "")
    filled = 0
    for i, r in enumerate(rows):
        since = r.get("pushed_at")
        if not since:
            continue
        since_pb = since.replace("T", " ")
        nxt = rows[i + 1].get("pushed_at") if i + 1 < len(rows) else ""
        r.update(consequences(base, owner_ref, since_pb,
                              (nxt or "").replace("T", " ")))
        filled += 1
        if filled % 25 == 0:
            print(f"  backfilled {filled}/{len(rows)}")
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    os.replace(tmp, path)
    with_job = sum(1 for r in rows if r.get("jobs"))
    with_said = sum(1 for r in rows if r.get("said"))
    print(f"backfilled {filled} rows in {path}: "
          f"{with_job} produced a job, {with_said} produced a message")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pb", default=os.environ.get("ANTICIPY_PB",
                                                   "http://127.0.0.1:8090"))
    ap.add_argument("--owner-ref", default="")
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "results.jsonl"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="",
                    help="comma-separated corpus ids, or @file with one per line")
    ap.add_argument("--gap", type=float, default=1.5,
                    help="idle seconds between utterances")
    ap.add_argument("--timeout", type=float, default=240.0,
                    help="seconds to wait for the worker to stamp a decision")
    ap.add_argument("--convo-gap", type=float, default=50.0,
                    help="virtual seconds between unrelated corpus items "
                         "(must exceed segmenter.CONTINUE_S = 45)")
    ap.add_argument("--turn-gap", type=float, default=10.0,
                    help="virtual seconds between turns of one conversation")
    ap.add_argument("--fresh", action="store_true",
                    help="start a new results file instead of resuming")
    ap.add_argument("--allow-stale-worker", action="store_true",
                    help="skip the check that the running worker contains the "
                         "current brain/ (only for deliberate A/B of an old "
                         "process)")
    ap.add_argument("--backfill", action="store_true",
                    help="re-read jobs/messages for results already on disk "
                         "and exit; pushes nothing")
    args = ap.parse_args()

    base = check_loopback(args.pb)
    owner_ref = args.owner_ref or os.environ.get("ANTICIPY_OWNER_REF") or ""
    if not owner_ref:
        ref_file = os.path.join(RIG, "state", "owner_ref")
        if os.path.exists(ref_file):
            owner_ref = open(ref_file).read().strip()
    if not owner_ref:
        raise SystemExit("no owner_ref: pass --owner-ref or set ANTICIPY_OWNER_REF")
    if args.convo_gap <= 45:
        raise SystemExit("--convo-gap must exceed 45s or the segmenter will "
                         "glue unrelated corpus items into one conversation")

    if args.backfill:
        backfill(base, owner_ref, args.out)
        return 0

    corpus = json.load(open(args.corpus))
    if args.only:
        if args.only.startswith("@"):
            wanted = {ln.strip() for ln in open(args.only[1:]) if ln.strip()}
        else:
            wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        corpus = [c for c in corpus if c["id"] in wanted]

    if args.fresh and os.path.exists(args.out):
        os.rename(args.out, args.out + f".{int(time.time())}.bak")
    done = load_done(args.out)
    todo = [c for c in corpus if c["id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    if not todo:
        print(f"nothing to do: {len(done)} results already in {args.out}")
        return 0

    # The virtual capture clock. Starts ahead of real time so the first line
    # closes any segment another agent left open on this shared rig.
    vclock = datetime.now(timezone.utc) + timedelta(seconds=300)
    for rec in done.values():
        prior = rec.get("capture_started_at")
        if prior:
            try:
                got = datetime.fromisoformat(prior.replace("Z", "+00:00"))
                vclock = max(vclock, got + timedelta(seconds=args.convo_gap))
            except ValueError:
                pass

    worker = ("worker: staleness check skipped by --allow-stale-worker"
              if args.allow_stale_worker
              else check_worker_is_current(REPO))
    print(f"pb        {base}")
    print(f"owner_ref {owner_ref}")
    print(f"brain     {worker}")
    print(f"corpus    {len(corpus)} utterances, {len(done)} already done, "
          f"{len(todo)} to push")
    print(f"pacing    gap={args.gap}s  timeout={args.timeout}s  "
          f"virtual convo gap={args.convo_gap}s")

    last_convo = None
    consecutive_timeouts = 0
    counts: dict[str, int] = {}
    t_start = time.time()

    for n, item in enumerate(todo, 1):
        convo = item.get("convo") or f"solo:{item['id']}"
        step = args.turn_gap if convo == last_convo else args.convo_gap
        vclock = vclock + timedelta(seconds=step)
        last_convo = convo
        started = iso(vclock)
        ended = iso(vclock + timedelta(seconds=3))

        body = {
            "kind": "transcript",
            "device_id": "iphone-rig",
            "owner_ref": owner_ref,
            "decision": "",
            "source": "phone_mic",
            # NEVER true. See the module docstring: explicit is the answer to
            # the question this corpus is asking.
            "explicit": False,
            "text": item["text"],
            "capture_started_at": started,
            "capture_ended_at": ended,
        }
        pushed_at = iso(datetime.now(timezone.utc))
        t0 = time.time()
        try:
            ev = _req("POST", f"{base}/api/collections/events/records", body)
        except Exception as e:
            append(args.out, {"id": item["id"], "text": item["text"],
                              "gold": item["gold"], "error": f"post: {e}",
                              "capture_started_at": started})
            print(f"[{n}/{len(todo)}] {item['id']} POST FAILED: {e}")
            continue
        event_id = ev["id"]

        # Wait for the worker to stamp it. "processing" is its claim marker
        # (worker.py:2017-2020), not an answer, so keep waiting through it.
        decision, goal, addressee, segment = "", "", "", ""
        deadline = t0 + args.timeout
        while time.time() < deadline:
            time.sleep(1.0)
            try:
                row = get(base, f"/api/collections/events/records/{event_id}")
            except Exception:
                continue
            d = (row.get("decision") or "").strip()
            if d and d != "processing":
                decision, goal = d, row.get("goal") or ""
                addressee = row.get("addressee") or ""
                segment = row.get("segment") or ""
                break

        elapsed = round(time.time() - t0, 1)
        rec = {
            "id": item["id"], "text": item["text"], "gold": item["gold"],
            "event_id": event_id, "decision": decision, "goal": goal,
            "addressee": addressee, "segment": segment,
            "elapsed_s": elapsed, "capture_started_at": started,
            "pushed_at": pushed_at,
        }

        if not decision:
            rec["error"] = f"no decision within {args.timeout}s"
            consecutive_timeouts += 1
        else:
            consecutive_timeouts = 0
            rec.update(consequences(base, owner_ref, pushed_at))

        append(args.out, rec)
        key = decision or "TIMEOUT"
        counts[key] = counts.get(key, 0) + 1
        mark = "  " if decision == item["gold"] else "!!"
        print(f"[{n}/{len(todo)}] {mark} {item['id']} want={item['gold']:6} "
              f"got={key:10} {elapsed:5.1f}s  {item['text'][:58]!r}")
        if goal:
            print(f"            goal: {goal[:100]}")

        if consecutive_timeouts >= 3:
            print("\nTHREE TIMEOUTS IN A ROW. The worker is not stamping "
                  f"anything — check {RIG}/brain.log. Stopping rather than "
                  "filling the results file with silence that looks like data.")
            return 2

        time.sleep(args.gap)

    mins = (time.time() - t_start) / 60
    print(f"\npushed {len(todo)} in {mins:.1f} min -> {args.out}")
    print("  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("\nNow: ~/.anticipy-rig/venv/bin/python proof/ambient/score.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
