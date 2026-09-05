# Watching build 122 — started 2026-09-05 00:00Z

Build 122 is the first build carrying this session's capture work: gap telemetry
that survives the process, a bounded unsent queue, and a flush that removes a
row only after the server confirms it. It reached a real phone and started
delivering on 2026-09-04 23:45Z. This directory is the record of what it did.

## How to add an observation

    python3 proof/capture_day.py --hours 24 | grep '^{' \
      > proof/watch-b122/$(date -u +%Y-%m-%dT%H%MZ).json

Run it once or twice a day. Each file is one JSON line from the real
instrument, so the series can be diffed without re-deriving anything.

## The baseline, 2026-09-05 00:00Z

| measure | value | note |
|---|---|---|
| lines arrived | 82 | one 11-minute session |
| thoughts after stitching | 68 | a `ceiling` cut chain counts once |
| words | 805 | |
| **short thoughts (<=4 words)** | **48%** | the Brief's recorded worst day is 54% |
| same, counting raw rows | 42% | what it looks like WITHOUT following cut marks |
| voice tags | 0% | expected — the speaker engine is unlinked on purpose |
| longest gap between lines | 57s | |
| ears | 100% `phone_mic` | expected — the pendant lane is still mute |

**48% is the honest number and 42% is the flattering one.** Counting raw rows
scores a stitched chain as several shards; `capture_day.py` follows
`parent_line` and counts thoughts. An earlier ad-hoc query in this session
reported 41% by not doing that, which would have read as a bigger improvement
than there is.

## What this series can and cannot answer

CAN: whether capture quality moves, whether delivery keeps up, whether the
stitching rate changes, whether the pendant ever starts contributing.

**CANNOT: anything about the new loss counters.** `airtimeLost`,
`speechDropped` and `linesDropped` live in `ListenJournal` on the phone and are
read from Settings -> Listening. They are deliberately not uploaded. So the
day's real question — *did the bounded queue ever drop a line, and did the radio
ever lose airtime* — is answerable only by opening that screen on the handset.
Nothing on the server can tell you, and this file will not pretend otherwise.

That is a gap worth closing, and it is the one open proposal from the port
review that survived with a clear shape: post a `kind="capture_health"` row
carrying only the ListenTally integers, so the counters stop being trapped on
the device. It has not been built.

## Known instrument defect, found while taking this baseline

`overnight/turn_envelope_gate.py` leg 5 FAILS on this data, and on build 113's
too — it predates this session's changes. It is a **false positive**. The leg
looks for 3+ rows arriving within 2s and fails if their spoken span is under
30s, on the theory that only a re-stamping flush produces that shape. Live
rapid speech produces it as well: the four rows it caught were "Yes.",
"Hey Siri.", "And, um,", "Yeah." — each posted in the same second it was
spoken, lag 0.0s, with **no row in the whole window buffered more than 60s**.
Leg 4, reading the same rows, correctly reports that no flush happened at all.

The obvious fix — restrict leg 5 to rows that were actually buffered — is
WRONG, and the gate's own self-test catches it: a flush that re-stamps sets the
capture instant to flush time, so the lag it would be filtered on is exactly
the evidence re-stamping destroys. A correct fix probably has to reason about
physical plausibility (a burst carrying more words than its span could
physically hold), and that was not attempted here rather than shipping a
half-understood change to an instrument. Filed, not fixed.
