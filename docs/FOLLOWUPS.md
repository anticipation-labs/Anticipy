# Standing follow-ups (non-blocking, from the Law-6 review of 2026-08-24)

1. Tag parked-ask events with a params marker so the uninvited-cap
   discriminator (decision="ask" && goal="") becomes exact — a native
   goalless direct-lane ask that sends would today burn one slot.
2. The degraded-path third-person drop in asking.question_line is standing
   tape with no red gate leg — add a leg tracking composer-owned
   person-flip, then delete the drop.
3. Watch the first week's `asked:` log lines — ambient self-talk questions
   now park while direct-lane self-talk questions still die (deliberate;
   the valve's governance is the difference). Live counts decide.
4. Digest sends post no anticipy_says event (pre-existing): a redeploy
   between the digest and a numbered reply loses the offer from the
   durable thread rebuild.
5. Steady >=3-lines/180s ambience (a TV) can sustain the meeting latch;
   the armed-duration disarm log makes this measurable — read it after a
   few home evenings.
6. ~~`agent_auth.pb.js:20-24` treats ANY exception from
   `findFirstRecordByFilter` as "this code is free"~~ — FIXED 2026-08-24.
   Neither proposed fix was needed: the third option is not to use an
   exception as the answer at all. `findRecordsByFilter` returns an ARRAY,
   so an empty array means "nothing matched" and a throw goes back to
   meaning only that the query failed. Both lookups in that handler moved
   to it — the agent_id one had the same defect and was only saved by
   accident, because `agent_id` carries a unique index and `pair_code`
   does not. A failed lookup now refuses the registration (503 / 500)
   rather than minting a collision, which is the one outcome here that a
   retry cannot undo: by then the code is on a screen and somebody has
   typed it. Pinned by `extension/tests/test_pair_code_collision.mjs`,
   whose bites-check restores the original try/catch and requires the
   collision to reappear. Still unverified live (LAW 3).
7. The pair-code throttle keys on `e.realIP()`. Behind Railway with no
   trusted proxy configured that is the connecting address, so every
   caller shares one bucket: ten failed guesses from anyone delays all
   pairing for ten minutes. Correct at one owner, a landmine at scale.
   Configure the trusted proxy header, or key on something better, before
   the second owner.
8. LOCAL-FIRST is violated in shipped code. `TranscriberClient.swift:27-29`
   streams raw pendant Opus to `wss://api.deepgram.com`, while
   `design/LOCAL-FIRST.md` rule 1 says raw audio never leaves a device and
   its own scoreboard asserts the pendant path is "law-abiding by design —
   phone does ALL processing". Latent only because the firmware is
   BUILT_AND_VERIFIED_NOT_FLASHED. The law-abiding replacement is already
   written and unplugged (`LocalTranscriber.swift`, never instantiated,
   whose header claims a Settings toggle that does not exist). Decide —
   restore the law with a phone-side Opus decoder, or amend the law and
   say so — BEFORE the pendant goes live, not after.
9. `_GO_AHEAD_RE` (`brain/anticipy_core.py:1025-1028`), gating :1372, is a
   regex deciding that the owner's words MEAN consent. That is meaning, in
   code: a standing LAW 1 violation. The fix is LAW 5 — a model with
   conversation context decides consent — never a wider regex.
10. `brain/llm.py:263-266` returns `_gemini(...)` before the `aux` branch,
   so with `GEMINI_API_KEY` set `ANTICIPY_AUX_MODEL` is unreachable AND the
   grounding is prepended again, reversing the measured 5x prompt-cache
   saving the comment directly above it describes. Dormant today (no Gemini
   key configured) but it is a trap, and the comment claims an "explicit
   CachedContent" mechanism that exists nowhere in `brain/`.
11. The conversation link graph is built and dark: `LINKS_ON` defaults off
   (`brain/worker.py:2445`) and `parent_line` has no reader. Phase 3 of
   `design/NO-MORE-TIMERS.md` is already built as `proof/score_links.py`
   (timer arm vs link arm over 244 real logged lines) and has never been
   run. One live-key run decides whether to switch or delete. Do neither
   blind.

Law 3 binds every item above: each one is fixed only when verified live.
