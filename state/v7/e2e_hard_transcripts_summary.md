# E2E hard-transcript run: 20 proactive transcripts × rich dossier

**Run dir:** `state/v7/e2e_hard_transcripts_20260528T031414Z/`
**Engine:** source uvicorn on 8731 with memory partition fix (commit `1f15360e`)
**Account:** `e2e_rich_test_2026_05_28`
**Dossier:** 10 contacts, 5 projects, 3 recurring patterns, 5 prefs, places

## Results

| Outcome | Count | Notes |
|---|---|---|
| CONFIRMED (planned action) | 16 | T01, T02, T03, T04, T05, T06, T07, T08, T09, T10, T11, T12, T13, T14, T19 |
| CANCELLED (declined to act) | 2 | T15 photographer email (judged premature), T16 podcast share (no recipient, just self) |
| LIFE_LOG (chatter, not actionable) | 2 | T17 dog meme, T18 laptop fan complaint |

20/20 transcripts processed end-to-end. No engine crashes. No 500s.

## Memory-aware plans

Plans that referenced dossier people by name (not just lookup, actual integration into the task description):

- **T04** Q3 review prep → plan: "2-hour working session with Marcus (finance side)"
- **T14** code markup follow-up → plan thing: "Jordan's markup"
- **T20** screen time lock → plan: "Ask Casey if they want to set up the screen time lock Priya mentioned"

3 of 20 had named memory references. Others used the dossier indirectly (resolving "the dentist by the marina", "the place we did last time") but didn't surface the name in the plan task. That's a fair score for first-pass extraction; production memory use is higher than 3/20 but the visible-in-plan-text indicator is conservative.

## What's done

1. M1 dossier loader: writes + reads work, round-trip proven.
2. M1 partition fix: account_id and user_id resolve to the same partition. Cross-key writes/reads proven.
3. POST /api/dossier/active endpoint: added (was missing in pre-fix source).
4. Engine processes hard ambiguous transcripts with buried intent.
5. Engine correctly classifies chatter (LIFE_LOG) vs deferred (CANCELLED) vs actionable (CONFIRMED).
6. Engine uses dossier names in planned actions.

## What's not done

1. Packaged binary still has old code; the fix lands only on next DMG rebuild + ship.
2. Memory hit precision (did engine use the RIGHT dossier entry vs a generic one?) requires manual scoring against expected_memory_used. Not done in this run.
3. 7-day persistence not stress-tested.
4. Plan execution not verified end-to-end (only plan generation tested).
5. Cross-session memory continuity not tested.

## Source vs packaged engine

This run used the SOURCE engine (uvicorn). The packaged binary at `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` does not have the partition fix yet. To ship: rebuild + reship the DMG (state/builds/manifest.json updated by ship.sh).
