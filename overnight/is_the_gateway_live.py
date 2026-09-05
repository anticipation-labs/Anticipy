#!/usr/bin/env python3
"""Does the second credential carry her when the first machine is absent?

brain/llm.py used to choose its transport by which KEY existed — Gemini if
GEMINI_API_KEY, else OpenRouter — so with both keys set a Gemini outage raised
straight out of LLM.chat() while a working OpenRouter credential idled: held
lines, a climbing deaf streak, and a text saying she "cannot reach the model"
about a model she could reach. Omi port 09b (2026-09-05) made the second
credential a fallback; tests/test_gateway_fallthrough.py drives that code
offline. This file asks whether it is true of the WORKER THAT IS RUNNING,
because repo-green has been mistaken for deployed twice in this repo's
history (HARNESS-LAWS.md LAW 3).

WHICH MACHINE THIS READS, and why it changed (audit F25/F33/F34). Until
2026-09-05 this file shelled `railway logs -s worker`. Production is
Cloudflare now, and the Railway worker it was grading is a different machine
on a retired backend — run that day, it reported FAIL about a worker whose own
banner said `pb=…railway.app`. A wrong-machine verdict is worse than UNPROVEN,
because somebody acts on it.

The Cloudflare container's stdout is not readable from any terminal:
`wrangler tail anticipy-brain` carries the DO's RPC events and not the
container's stdout (measured over 150 s with nine live instances: zero lines
containing "worker up"), `wrangler containers` has no logs command, and the
Workers Observability telemetry API answers 403 with a developer's OAuth
token. So the brain writes its boot line to a `worker_status` events row
instead (brain/worker.py publish_worker_status), refreshed in place every five
minutes, and this file reads that row from the same backend every other live
leg reads. `--source railway` keeps the old log path for the Railway worker,
which is now the thing it is honest about: that worker, not this one.

Three legs, the first two over the running brain's status text (or, with
`--source railway`, over `railway logs -s worker -n 5000 --json`; flags
confirmed on railway 5.49.2, lines arrive oldest first):

  1  THE BANNER. The newest `worker up ·` line must carry
     `fallback=<name>:<model>`, not `fallback=none` and not nothing.
     Deployed-but-inert is not done: one credential has nothing to fall
     through to, and no field at all means a build from before the port.

  2  THE BEHAVIOUR. The worker prints `llm: gateway tally primary_ok=N
     rescued=N skipped=N reissued=N both_dead=N` on every tick a model call
     ran, and this leg SUMS those over the window. primary_ok is the
     denominator the first draft of this leg lacked: without it, "the
     primary answered 900 and the fallback 3" and "the primary answered
     nothing and the fallback carried everything" were the same log.

       rescued>0 and primary_ok>0        PROVEN   a real fall-through, and back
       primary_ok==0, rescued/skipped>0  FAIL     the configured primary answered
                                                  nothing all window — a revoked
                                                  key, a dead endpoint, a broken
                                                  parser; the log cannot tell
                                                  which, and all deserve it
       primary_ok==0, reissued>0         FAIL     every primary answer truncated
       both_dead>0 and nothing else      FAIL     no transport answered any call
       a `-> trying` with no outcome     FAIL     the fall-through started and
                                                  never finished
       no tally line at all              UNPROVEN nothing was measured
       primary_ok>0, no fall-through     UNPROVEN a healthy window proves the
                                                  primary, not the fallback;
                                                  run --probe

  3  --probe, THE MEASUREMENT. Loads .env.local, requires both keys, points
     brain.llm's OpenRouter URL at a closed local port, puts OpenRouter first
     in the order, and makes ONE real call: it passes iff Gemini answered
     for OpenRouter — real code, real fallback credential, real endpoint, a
     primary made unreachable the way an outage makes it. One Gemini call,
     well under a cent, and only when a human runs it.

Law 3 is met only when leg 1 passes on the RUNNING brain AND (leg 2 is PROVEN
or leg 3 passes against the deployed commit's env). The live precondition is
an ops change the owner must make, and it is TWO changes, not one
(audit F32): `wrangler secret put GEMINI_API_KEY` on the anticipy-brain
Worker, AND `ANTICIPY_LLM_ORDER=openrouter,gemini` reaching the container —
brain/llm.py's default order is ("gemini", "openrouter"), so the secret ALONE
silently promotes Gemini to primary and demotes the configured
deepseek model to fallback. As of 2026-09-05 that variable is in neither
wrangler.brain.jsonc's vars nor the DO's FORWARD_KEYS, so it cannot reach the
container yet: adding the secret first would move production's model.

A stale or absent status row is UNPROVEN, never PASS and never FAIL. It means
the container is gone, or is running a build from before the row existed —
a different fact from "the fallback is broken", and one no verdict about the
gateway may be built on.

WHY THIS IS NOT A LAW 1 VIOLATION: every count here is over the worker's
own structured log lines — a banner, a tally, a gateway provenance line —
never over the words of a transcript. The one line family that carries
speech (`heard: … holding the line`) is COUNTED and never printed.

Read-only against the backend (and against Railway with --source railway).
Exit code is the verdict:

    0   PROVEN
    1   FAIL
    2   UNPROVEN — the row/logs could not be read, the status is stale, there
        is no banner, or there was nothing to measure

    python3 overnight/is_the_gateway_live.py
    python3 overnight/is_the_gateway_live.py --source railway
    python3 overnight/is_the_gateway_live.py --probe
    python3 overnight/is_the_gateway_live.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)
import _env  # noqa: E402  sibling module; gates are run as scripts

# .env.local is loaded in main()/probe(), NOT at import: the pure verdicts
# below are imported by tests/test_gateway_fallthrough.py, and a test process
# must never pick up production credentials as a side effect of a collection.

import datetime as dt  # noqa: E402

import requests  # noqa: E402

OK, BAD, INFO = "PASS", "FAIL", "...."
SERVICE = "worker"
LINES = 5000

# Where the running brain writes the line its log cannot carry.
STATUS_KIND = "worker_status"
# brain/worker.py refreshes the row every WORKER_STATUS_REFRESH_SECONDS (300).
# Three missed refreshes is not a blip: it is a container that is gone, or one
# running a build from before the row existed. Either way nothing about the
# gateway can be read off it, so the verdict is UNPROVEN and says which.
STATUS_STALE_SECONDS = 900

TALLY_KEYS = ("primary_ok", "rescued", "skipped", "reissued", "both_dead")
_TALLY_RE = re.compile(r"llm: gateway tally "
                       + " ".join(rf"{k}=(\d+)" for k in TALLY_KEYS))
_FALLBACK_RE = re.compile(r"\bfallback=(\S+)")
_PRIMARY_RE = re.compile(r"\bprimary=(\S+)")
# The provenance lines brain/llm.py _fall_through prints, by shape. A start
# must be followed by an outcome; a reissue need not be (the primary's own
# flagged reply is a legitimate end), so it is not a start here.
START_MARKS = (" -> trying ", " -> probing ")
END_MARKS = (" answered the probe", "no transport answered")
RESCUE_MARK = " answered for "
TRUNCATION_MARK = "(truncation)"
HELD_MARK = "holding the line for a retry"


def fetch_messages(lines: int = LINES, service: str = SERVICE):
    """The worker's log lines, oldest first, or None when they cannot be
    read — which is a different fact from "the log is empty"."""
    try:
        proc = subprocess.run(
            ["railway", "logs", "-s", service, "-n", str(lines), "--json"],
            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    out: list[str] = []
    for raw in proc.stdout.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            out.append(raw)
            continue
        out.append(str(row.get("message", "")) if isinstance(row, dict) else str(row))
    return out


def backend_url() -> str:
    return (os.environ.get("ANTICIPY_PB")
            or os.environ.get("ANTICIPY_BACKEND_URL")
            or "https://api.anticipy.ai").rstrip("/")


def fetch_status_rows(pb: str = ""):
    """The status rows the running brains refresh, newest first, or None when
    they could not be read — which is a different fact from "there are none"."""
    pb = pb or backend_url()
    headers = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        headers["X-Anticipy-Token"] = token
    try:
        r = requests.get(f"{pb}/api/collections/events/records",
                         headers=headers, timeout=30,
                         params={"perPage": 20, "sort": "-updated",
                                 "filter": f'kind="{STATUS_KIND}"',
                                 "fields": "text,updated,owner_ref"})
        if r.status_code != 200:
            return None
        return list((r.json() or {}).get("items", []))
    except Exception:
        return None


def _age_seconds(stamp: str, now: dt.datetime) -> float | None:
    if not stamp:
        return None
    v = str(stamp).replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        when = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    if not when.tzinfo:
        when = when.replace(tzinfo=dt.timezone.utc)
    return (now - when).total_seconds()


def status_verdict(rows, now=None, stale_after: int = STATUS_STALE_SECONDS):
    """Which status rows may be graded. (exit_code, status, sentence, texts).

    Pure, so the shapes below are tested without a network. POLARITY: an
    absent or stale row yields NO texts and exit 2. It can never be a PASS
    (nothing was proven) and never a FAIL (nothing was measured) — the same
    rule are_the_ears_live.py keeps for a control it cannot see.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    if rows is None:
        return 2, INFO, ("the backend could not be read, so which brain is "
                         "running is unknown"), []
    if not rows:
        return 2, INFO, (f"no `{STATUS_KIND}` row on this backend — no brain "
                         "has written one, so either none is running or the "
                         "running one predates the row (audit F34)"), []
    fresh, ages = [], []
    for row in rows:
        age = _age_seconds(str(row.get("updated") or ""), now)
        if age is None:
            continue
        ages.append(age)
        if age <= stale_after:
            fresh.append(str(row.get("text") or ""))
    if not fresh:
        youngest = min(ages) if ages else float("nan")
        return 2, INFO, (f"every {STATUS_KIND} row is stale (newest "
                         f"{youngest / 60:.0f} min old, refresh is "
                         f"{stale_after // 60} min): the container is gone or "
                         "is running a build from before the row existed"), []
    return 0, INFO, (f"{len(fresh)} brain(s) refreshed their status inside "
                     f"{stale_after // 60} min"), fresh


def banner_verdict(messages) -> tuple:
    """Leg 1, pure. (exit_code, status, sentence)."""
    banners = [m for m in messages if "worker up ·" in m]
    if not banners:
        return 2, INFO, ("no `worker up ·` banner in the window — which build "
                         "is running is unknown")
    newest = banners[-1]
    fallback = _FALLBACK_RE.search(newest)
    primary = _PRIMARY_RE.search(newest)
    who = primary.group(1) if primary else "?"
    if not fallback:
        return 1, BAD, ("the newest banner carries no fallback= field — a "
                        "worker from before port 09b is what is running")
    if fallback.group(1) == "none":
        return 1, BAD, (f"fallback=none (primary={who}): deployed, and inert "
                        "— one credential has nothing to fall through to")
    return 0, OK, f"primary={who} fallback={fallback.group(1)}"


def tally_verdict(messages) -> tuple:
    """Leg 2, pure. (exit_code, status, sentence)."""
    totals = dict.fromkeys(TALLY_KEYS, 0)
    tally_lines = 0
    pending = 0
    last_gateway_was_start = False
    for m in messages:
        hit = _TALLY_RE.search(m)
        if hit:
            tally_lines += 1
            for key, value in zip(TALLY_KEYS, hit.groups()):
                totals[key] += int(value)
            continue
        if "llm: gateway" not in m:
            continue
        if any(s in m for s in START_MARKS):
            pending += 1
            last_gateway_was_start = True
            continue
        if (any(e in m for e in END_MARKS)
                or (RESCUE_MARK in m and TRUNCATION_MARK not in m)):
            pending = max(0, pending - 1)
        last_gateway_was_start = False
    held = sum(1 for m in messages if HELD_MARK in m)
    counts = " ".join(f"{k}={totals[k]}" for k in TALLY_KEYS)

    if tally_lines == 0:
        return 2, INFO, ("no `llm: gateway tally` line in the window — nothing "
                         "about the gateway was measured")
    # One start with nothing after it is a call in flight at fetch time.
    if pending > 0 and not (pending == 1 and last_gateway_was_start):
        return 1, BAD, (f"{pending} fall-through(s) started and never finished "
                        f"({counts})")
    if totals["primary_ok"] == 0 and (totals["rescued"] + totals["skipped"]) > 0:
        return 1, BAD, ("the configured primary answered nothing all window; "
                        f"the fallback carried her ({counts}) — a revoked key, "
                        "a dead endpoint or a broken parser, and the log "
                        "cannot tell which")
    if totals["primary_ok"] == 0 and totals["reissued"] > 0:
        return 1, BAD, ("every primary answer in the window was truncated and "
                        f"reissued on the fallback ({counts}) — raise its "
                        "output ceiling; the fallback is composing his texts")
    if totals["primary_ok"] == 0 and totals["both_dead"] > 0:
        return 1, BAD, (f"no transport answered any call ({counts}; lines "
                        f"held for the sweep={held})")
    if totals["rescued"] > 0:
        return 0, OK, (f"the fallback carried {totals['rescued']} call(s) and "
                       f"the primary {totals['primary_ok']} ({counts}; lines "
                       f"held for the sweep={held})")
    if totals["reissued"] > 0:
        return 0, OK, (f"{totals['reissued']} truncated primary reply(ies) were "
                       f"reissued on the fallback and the primary carried "
                       f"{totals['primary_ok']} ({counts}) — on an ordinary "
                       "day this is the cue to raise the primary's output "
                       "ceiling rather than keep paying twice")
    return 2, INFO, (f"no primary failure in the window ({counts}) — a healthy "
                     "window proves the primary, not the fallback; run --probe")


def probe() -> tuple:
    """Leg 3: one real call with the primary made unreachable."""
    if not (os.environ.get("GEMINI_API_KEY") and os.environ.get("OPENROUTER_API_KEY")):
        return 2, INFO, ("both GEMINI_API_KEY and OPENROUTER_API_KEY are needed "
                         "to measure a fall-through")
    sys.path.insert(0, ROOT)
    import brain.llm as llm_mod  # noqa: E402
    llm_mod.OPENROUTER_URL = "http://127.0.0.1:9/"     # a closed port: ConnectError x3
    llm_mod._TRANSPORT_ORDER = ("openrouter", "gemini")
    try:
        res = llm_mod.LLM().chat("Reply with the single word OK.", "hi")
    except Exception as exc:
        return 1, BAD, f"no transport answered: {type(exc).__name__}: {str(exc)[:120]}"
    if res.mode == "gemini" and res.fell_through_from == "openrouter":
        return 0, OK, (f"openrouter made unreachable; gemini ({res.used_model}) "
                       f"answered for it: {res.text.strip()[:24]!r}")
    return 1, BAD, (f"mode={res.mode} fell_through_from={res.fell_through_from!r} "
                    "— the fallback did not carry the call")


def _tally(**counts) -> str:
    return "llm: gateway tally " + " ".join(f"{k}={counts.get(k, 0)}" for k in TALLY_KEYS)


def self_test() -> int:
    """The verdicts against the log shapes the code can actually produce."""
    banner_cases = [
        ([], 2, "no banner: unknown build"),
        (["worker up · llm=live:x · sms=mock · brain=a"], 1, "pre-port banner, no field"),
        (["worker up · llm=live:x · primary=openrouter:x fallback=none · brain=a"], 1,
         "one credential: deployed and inert"),
        (["worker up · llm=live:x · primary=openrouter:x fallback=none · brain=a",
          "worker up · llm=live:x · primary=openrouter:x fallback=gemini:y · brain=b"], 0,
         "the newest banner decides"),
    ]
    tally_cases = [
        (["heard: 'x' -> ignore"], 2, "no tally line: nothing measured"),
        ([_tally(primary_ok=40)], 2, "healthy day: proves the primary only"),
        ([_tally(primary_ok=40), _tally(rescued=2)], 0, "a rescue, and the primary back"),
        ([_tally(rescued=3), _tally(skipped=9, rescued=9)], 1, "primary answered nothing"),
        ([_tally(reissued=3)], 1, "every primary answer truncated"),
        ([_tally(both_dead=4)], 1, "no transport answered anything"),
        ([_tally(primary_ok=5), "llm: gateway openrouter HTTPStatusError -> trying gemini",
          "llm: gateway gemini answered for openrouter", _tally(rescued=1)], 0,
         "started and finished"),
        ([_tally(primary_ok=5), "llm: gateway openrouter HTTPStatusError -> trying gemini",
          _tally(rescued=1), "heard: 'x' -> ignore",
          "llm: gateway openrouter HTTPStatusError -> trying gemini", _tally(primary_ok=2)], 1,
         "started, never finished"),
        ([_tally(primary_ok=5), _tally(rescued=1),
          "llm: gateway openrouter HTTPStatusError -> trying gemini"], 0,
         "one start at the very end is a call in flight"),
        ([_tally(primary_ok=9), "llm: gateway openrouter truncated -> reissuing on gemini",
          _tally(primary_ok=1)], 2, "a reissue with no outcome is the primary's own reply"),
    ]
    status_cases = [
        (None, 2, "backend unreadable: not a verdict about the gateway"),
        ([], 2, "no status row: nothing is running, or it predates F34"),
        ([{"text": "worker up · primary=a:b fallback=c:d",
           "updated": "2026-09-05 10:00:00.000Z"}], 2, "one hour stale"),
        ([{"text": "worker up · primary=a:b fallback=c:d",
           "updated": "2026-09-05 10:55:00.000Z"}], 0, "refreshed five minutes ago"),
    ]
    bad = 0
    print("\n  SELF-TEST — the verdicts against log shapes the worker can produce")
    pinned_now = dt.datetime(2026, 9, 5, 11, 0, tzinfo=dt.timezone.utc)
    for rows, expected, why in status_cases:
        code = status_verdict(rows, now=pinned_now)[0]
        ok = code == expected
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] status -> exit {code} (want {expected})   {why}")
    print("  " + "-" * 76)
    for messages, expected, why in banner_cases:
        code, _, _ = banner_verdict(messages)
        ok = code == expected
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] banner -> exit {code} (want {expected})   {why}")
    for messages, expected, why in tally_cases:
        code, _, _ = tally_verdict(messages)
        ok = code == expected
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] tally  -> exit {code} (want {expected})   {why}")
    print("  " + "-" * 76)
    total = len(banner_cases) + len(tally_cases) + len(status_cases)
    print(f"  {total - bad}/{total} cases correct\n")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lines", type=int, default=LINES,
                    help="log lines to read from the worker (default 5000)")
    ap.add_argument("--service", default=SERVICE,
                    help="the Railway service name (default worker)")
    ap.add_argument("--source", choices=("cloudflare", "railway"),
                    default="cloudflare",
                    help="which brain to grade: the Cloudflare container via "
                         "its status row (default), or the Railway worker via "
                         "its logs")
    ap.add_argument("--probe", action="store_true",
                    help="also make ONE real call with the primary made unreachable")
    ap.add_argument("--self-test", action="store_true",
                    help="check the verdict logic offline and exit")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    _env.load_and_announce(ROOT)
    rows = []
    if args.source == "railway":
        where = f"railway service `{args.service}`"
        messages = fetch_messages(args.lines, args.service)
        if messages is None:
            rows.append((INFO, "railway logs", "could not be read — not logged "
                         "in, no linked project, or the CLI is missing"))
        else:
            rows.append((INFO, f"log lines read from `{args.service}`",
                         str(len(messages))))
    else:
        where = backend_url()
        code0, status0, detail0, messages = status_verdict(
            fetch_status_rows(where))
        rows.append((status0, "0 THE RUNNING BRAIN", detail0))
        if code0 != 0:
            messages = None

    if messages is None:
        code1 = code2 = 2
    else:
        code1, status1, detail1 = banner_verdict(messages)
        rows.append((status1, "1 THE BANNER", detail1))
        code2, status2, detail2 = tally_verdict(messages)
        rows.append((status2, "2 THE BEHAVIOUR", detail2))
    code3 = None
    if args.probe:
        code3, status3, detail3 = probe()
        rows.append((status3, "3 THE PROBE", detail3))

    codes = [c for c in (code1, code2, code3) if c is not None]
    if 1 in codes:
        final = 1
    elif code1 == 0 and (code2 == 0 or code3 == 0):
        final = 0
    else:
        final = 2

    width = max(len(r[1]) for r in rows) + 2
    print(f"\n  IS THE GATEWAY LIVE?   {where}")
    print("  " + "-" * (width + 34))
    for status, name, detail in rows:
        print(f"  [{status}] {name.ljust(width)} {detail}")
    print("  " + "-" * (width + 34))
    if final == 1:
        print("  THE FALLBACK IS NOT CARRYING HER. See the red row above.\n")
    elif final == 2:
        print("  UNPROVEN — a leg that cannot be tested does not pass. Leg 1 "
              "must pass on the\n  RUNNING brain AND (leg 2 PROVEN or --probe "
              "passing against the deployed env).\n"
              "  If leg 0 is the red one, the brain is not writing its status "
              "row: deploy a\n  build carrying publish_worker_status (audit "
              "F34) before reading anything below it.\n")
    else:
        print("  THE SECOND CREDENTIAL CARRIES HER WHEN THE FIRST MACHINE IS ABSENT\n")
    return final


if __name__ == "__main__":
    sys.exit(main())
