#!/usr/bin/env python3
"""Did anything the OWNER said reach the server?

`is_the_brain_live.py` asks whether the deployed brain keeps its promises. Every
rule it has is an OVER-SPEAKING rule: too many texts, texts in quiet hours, a
stuck job that keeps asking. All of them fire when she says too much. None of
them can fire when she hears nothing, so it exits 0 on a phone that has been
deaf for thirty hours — which is exactly the shape production was in when this
file was written.

WHAT HAPPENED, since this file exists because of it:

  2026-08-24 03:34:24Z   the newest `kind="transcript"` row in production.
  2026-08-24 16:10:20Z   the newest `kind="anticipy_says"` row — TWELVE AND A
                         HALF HOURS LATER. The server, its auth, its
                         collections and its writes were all healthy long
                         after the ears went quiet.
  ~30 hours              before anybody noticed, and only then because someone
                         went looking for something else.

The two clocks are the instrument. A backend that is provably accepting writes
while zero speech arrives is not a quiet night — it is a one-directional
failure, and it is invisible to every check this repo had.

It had also happened at least three times before, unnoticed, in the recorded
rows: 2026-08-03 (0 transcripts, 16 server writes), 2026-08-09 (0 / 1) and
2026-08-13 (0 transcripts, SIXTY-THREE server writes).

HOW THIS TELLS A DEAF PHONE FROM A LEGITIMATELY SILENT NIGHT, which is the
whole difficulty and needs no clock arithmetic at all:

    A silent night is silent on BOTH halves. Deaf ears are silent on ONE.

Nobody speaks at 4am, and she answers nobody at 4am either, so both counts sit
at zero together and this leg stays green. When the machine is demonstrably
working — replying, texting, finishing errands — and NOTHING was heard across a
whole day, the asymmetry is the fault. So there is no quiet-hours calendar
here, no timezone, no expected-words-per-hour: the second count IS the control,
and it is a control the owner's sleep cannot move.

WHY THE NUMBERS BELOW ARE NOT A LAW 1 VIOLATION:

Law 1 forbids a regex, word list or threshold deciding what words MEAN, and
permits thresholds in deterministic gates. Every number here is over the
EXISTENCE and PROVENANCE of rows — how many, from which device — and never over
their content. This file never requests the `text` column at all (see `fields=`
on both counts), so it cannot read a word of anybody's speech even by accident.
It cannot be measuring meaning with a threshold when it cannot see the words.

Read-only. It creates nothing, patches nothing and touches no job. Safe against
production, which is the only place the answer exists.

    python3 overnight/are_the_ears_live.py
    python3 overnight/are_the_ears_live.py --hours 48
    python3 overnight/are_the_ears_live.py --self-test

Exit code is the verdict:

    0   the ears are proven alive — speech arrived inside the window
    1   EARS DEAF — nothing was heard while the machine was provably working
    2   UNPROVEN — the backend could not be read, or the whole system was idle
        so there was nothing to be asymmetric with. A leg that cannot be tested
        does not pass.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

# The credentials were always next to the gate and nothing loaded them.
import os as _os, sys as _sys  # noqa: E402
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import requests  # noqa: E402

PB = (os.environ.get("ANTICIPY_PB")
      or os.environ.get("ANTICIPY_BACKEND_URL")
      or "https://backend-production-61e0a.up.railway.app").rstrip("/")

# The device_id the worker stamps on everything IT writes. This is the control
# half: rows that exist because the server was alive and doing work, and that
# no phone had to deliver. brain/pb.py writes it; AnticipyApp.swift stamps
# "iphone-b<CFBundleVersion>" on the other half, which is why the report below
# can name the BUILD that last spoke.
SERVER_DEVICE = "anticipy-brain"

# How much server-originated work counts as "the machine was demonstrably
# working". DERIVED, not invented: on the recorded days where the ears were
# genuinely deaf the server wrote 16 and 63 rows; on 2026-08-09, a day nobody
# was using the product at all, it wrote exactly 1. Five sits above the
# one-scheduled-nudge-on-a-dead-day case and an order of magnitude below every
# real incident, so it separates the two populations the record actually
# contains rather than a population somebody imagined.
#
# It decides nothing about meaning. It decides how much evidence of a live
# machine is enough to call a silence one-directional.
MIN_SERVER_WRITES = 5

# Below this the leg would need the quiet-hours logic this design exists to
# avoid: a four-hour window can legitimately contain an empty afternoon. A full
# day always contains both a waking half and a sleeping half, so the asymmetry
# argument holds without a clock.
FULL_CYCLE_HOURS = 24

OK, BAD, INFO = "PASS", "FAIL", "...."


def headers() -> dict:
    """Same shape brain/pb.py uses. Without the token every read is 403 and
    this file would report healthy ears by reading nothing."""
    h = {"X-Anticipy-Worker": "1"}
    token = os.environ.get("ANTICIPY_SERVICE_TOKEN")
    if token:
        h["X-Anticipy-Token"] = token
    return h


def parse_ts(value: str):
    """PocketBase hands back 'YYYY-MM-DD HH:MM:SS.mmmZ' — tolerate both forms,
    and always return an AWARE datetime so no caller reads it in the zone of
    whatever laptop happened to run the gate."""
    if not value:
        return None
    v = value.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def count(filter_expr: str) -> int:
    """How many rows match, without fetching one of them.

    `perPage=1` plus `totalItems` is the whole answer, and `fields=id` keeps
    even that one row from carrying speech across the wire.
    """
    r = requests.get(f"{PB}/api/collections/events/records",
                     headers=headers(), timeout=30,
                     params={"perPage": 1, "filter": filter_expr, "fields": "id"})
    r.raise_for_status()
    return int(r.json().get("totalItems", 0))


def newest(filter_expr: str) -> dict:
    """The most recent matching row — metadata only, never `text`."""
    r = requests.get(f"{PB}/api/collections/events/records",
                     headers=headers(), timeout=30,
                     params={"perPage": 1, "filter": filter_expr,
                             "sort": "-created",
                             "fields": "created,device_id,owner_ref,source"})
    r.raise_for_status()
    items = r.json().get("items", [])
    return items[0] if items else {}


def verdict(transcripts: int, server_writes: int,
            min_server_writes: int = MIN_SERVER_WRITES,
            silence_hours: float | None = None,
            window_hours: float = FULL_CYCLE_HOURS) -> tuple[int, str, str]:
    """The whole decision, as a pure function so it can be tested without a
    network. Returns (exit_code, status, sentence).

    TWO ways to be red, and the second one exists because running this gate
    against the very outage it was written for exposed the hole in the first.

    At hour 30 of the 2026-08-24 silence the trailing day held THREE server
    writes — below the floor — because with nothing coming in there was nothing
    for the machine to answer. The control half evaporates as an outage ages,
    so a rule that needs a busy server catches the first day and then quietly
    downgrades to "unproven" for the rest of the week. That is the failure mode
    of the instrument this one replaces, arrived at by a different road.

    So a silence that has now spanned TWO full day/night cycles is red on its
    own evidence. One quiet day is a thing that happens to people; two
    consecutive ones, with a backend answering the whole time, is a microphone
    that is not working. It needs no busy server to be true.
    """
    if transcripts > 0:
        return 0, OK, f"{transcripts} line(s) of speech arrived — the ears are alive"
    if server_writes >= min_server_writes:
        return 1, BAD, (f"NOTHING was heard, while the server wrote "
                        f"{server_writes} row(s) of its own. The machine was "
                        f"working and the phone was not delivering.")
    if silence_hours is not None and silence_hours > 2 * window_hours:
        return 1, BAD, (f"NOTHING was heard for {silence_hours:.1f}h — more than "
                        f"two full day/night cycles — while the backend answered "
                        f"throughout. That is not a quiet spell.")
    return 2, INFO, (f"nothing was heard, and the server only wrote "
                     f"{server_writes} row(s) either — the whole system was "
                     f"idle, so this window proves nothing about the ears")


def self_test() -> int:
    """Exercise the verdict on the shapes the record actually contains.

    Every case below is a real day from production, named, so the gate's
    behaviour is pinned to the incidents it exists to catch rather than to
    invented numbers.
    """
    cases = [
        # (transcripts, server_writes, silence_hours, expected_exit, why)
        (140, 15, 2.0, 0, "2026-08-24 up to 03:34 — a working day"),
        (142, 7, 1.0, 0, "2026-08-23 — a working day"),
        (0, 63, 26.0, 1, "2026-08-13 — 63 server writes, nothing heard (MISSED)"),
        (0, 16, 26.0, 1, "2026-08-03 — 16 server writes, nothing heard (MISSED)"),
        (0, 5, 25.0, 1, "the machine at exactly the evidence floor"),
        (0, 1, 26.0, 2, "2026-08-09 — one nudge, nobody using it: NOT deaf ears"),
        (0, 0, 25.0, 2, "one quiet day, both halves quiet: people do that"),
        (1, 0, 0.5, 0, "one line is enough to prove the ears"),
        # The hole the live run found: hour 30 of this outage, server now idle
        # too. The first rule alone says "unproven"; two missed cycles say red.
        (0, 3, 49.0, 1, "2026-08-25 — hour 49, server gone idle too: still DEAF"),
        (0, 3, 30.0, 2, "hour 30 — one cycle, idle machine: honestly unproven"),
    ]
    bad = 0
    print("\n  SELF-TEST — the verdict against days production actually had")
    print("  " + "-" * 76)
    for transcripts, writes, silence, expected, why in cases:
        code, status, _ = verdict(transcripts, writes, silence_hours=silence)
        ok = code == expected
        bad += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] heard={transcripts:<4} "
              f"server={writes:<4} silent={silence:<5.1f}h -> exit {code} "
              f"(want {expected})   {why}")
    print("  " + "-" * 76)
    print(f"  {len(cases) - bad}/{len(cases)} cases correct\n")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=FULL_CYCLE_HOURS,
                    help="window to look back over (default 24)")
    ap.add_argument("--min-server-writes", type=int, default=MIN_SERVER_WRITES,
                    help="server rows that count as 'the machine was working'")
    ap.add_argument("--self-test", action="store_true",
                    help="check the verdict logic offline and exit")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    rows: list[tuple[str, str, str]] = []
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(hours=args.hours)
    since_s = since.strftime("%Y-%m-%d %H:%M:%S")

    # A backend that cannot be read is not a backend that is silent. Say which
    # one it was, or the gate reports deaf ears every time the network hiccups
    # and gets muted for crying wolf.
    try:
        health = requests.get(f"{PB}/api/health", timeout=20)
        healthy = health.status_code == 200
    except Exception as e:
        healthy = False
        rows.append((INFO, "backend reachable", str(e)[:70]))
    if not healthy:
        print(f"\n  ARE THE EARS LIVE?   {PB}")
        print("  [....] the backend could not be read, so nothing here was measured")
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
        return 2
    rows.append((INFO, "backend answers /api/health", "200"))

    try:
        heard = count(f'kind="transcript" && created >= "{since_s}"')
        server_writes = count(f'device_id="{SERVER_DEVICE}" && created >= "{since_s}"')
    except Exception as e:
        print(f"\n  ARE THE EARS LIVE?   {PB}")
        print(f"  [....] the events collection could not be counted: {str(e)[:70]}")
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
        return 2

    if args.hours < FULL_CYCLE_HOURS:
        rows.append((INFO, "window is shorter than a full day",
                     f"{args.hours}h can be legitimately empty; 24h cannot"))

    rows.append((INFO, f"speech heard in the last {args.hours:g}h", str(heard)))
    rows.append((INFO, f"rows the SERVER wrote in the last {args.hours:g}h",
                 f"{server_writes} (the control half)"))

    # The single most useful line on the screen, and it costs one request: WHEN
    # the ears last spoke and WHICH BUILD was wearing them. On 2026-08-24 this
    # would have read "30.3h ago, from iphone-b75" — and iphone-b75 is the
    # build that was replaced at that exact minute, which is the finding.
    last = newest('kind="transcript"')
    silence_hours = None
    if last:
        when = parse_ts(last.get("created", ""))
        if when:
            silence_hours = (now - when).total_seconds() / 3600.0
        age = silence_hours if silence_hours is not None else float("nan")
        rows.append((INFO, "newest speech of all time",
                     f"{last.get('created','?')} ({age:.1f}h ago) "
                     f"from {last.get('device_id') or 'unknown device'}"))
    last_server = newest(f'device_id="{SERVER_DEVICE}"')
    if last_server:
        when = parse_ts(last_server.get("created", ""))
        age = (now - when).total_seconds() / 3600.0 if when else float("nan")
        rows.append((INFO, "newest row the server wrote",
                     f"{last_server.get('created','?')} ({age:.1f}h ago)"))

    code, status, sentence = verdict(heard, server_writes, args.min_server_writes,
                                     silence_hours=silence_hours,
                                     window_hours=args.hours)
    rows.append((status, "THE EARS ARE HEARD FROM", sentence))

    width = max(len(r[1]) for r in rows) + 2
    print(f"\n  ARE THE EARS LIVE?   {PB}")
    print("  " + "-" * (width + 34))
    for st, name, detail in rows:
        print(f"  [{st}] {name.ljust(width)} {detail}")
    print("  " + "-" * (width + 34))
    if code == 1:
        print("  THE EARS ARE DEAF. Nothing downstream of them can be tested, "
              "because\n  nothing downstream can act on a line that never arrived.")
        print("  Whoever holds the phone: Settings -> Listening. `Words sent` and "
              "`Lines\n  that did not reach the server` separate a phone that never "
              "heard from one\n  that heard and could not deliver.\n")
    elif code == 2:
        print("  UNPROVEN — a leg that cannot be tested does not pass\n")
    else:
        print("  SPEECH IS REACHING THE SERVER\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
