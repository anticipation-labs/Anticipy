# Testing pass, 2026-08-21 — voice, browser agent, Chrome extension

What was asked for: deep, repeated, high-volume testing of the three surfaces,
across every plausible field and speaker type, reusing the existing harnesses.

What is in this file: the numbers, where they came from, what is trustworthy in
them and what is not, and the one bug that made every previous ambient
scorecard wrong.

Raw artefacts:

| what | where |
|---|---|
| the corpus | `proof/ambient/corpus.big.json` (1000 lines) |
| voice results | `proof/ambient/rounds/round1/results.clean.jsonl` (713 scored) |
| voice scorecard | `proof/ambient/rounds/round1/scorecard.json` |
| browser results | `proof/battery/results/r1-clean.jsonl` (76 scored) |
| per-lane raw | `proof/ambient/rounds/round1/voice-*.jsonl`, `proof/battery/results/r1-arm-*.jsonl` |

---

## 0. The measurement was broken before the engine was

`proof/ambient/run.py` built `pushed_at` with `iso()` — a `T`-separated
timestamp — and passed it straight into a PocketBase filter operand.

Twelve lines above it, `pb_ts()` exists and its docstring says exactly what
that does:

> A `created>="2026-08-20T21:52:00.000Z"` filter does not error and does not
> match — it silently returns zero rows, which reads exactly like "she created
> no job". Measured against a table holding 37: the T form returned 0, the
> space form returned 25. Two hours of "she never queues anything" came out of
> that.

`backfill()` had been fixed. The live path had not. So every live run recorded
`said=[]` and `jobs=[]` regardless of what the brain actually did, and
`score.py` reads exactly those two keys to decide whether anything reached the
owner. **Every errand the brain caught was graded `silent`, i.e. a miss.**

That is the origin of the 50.9% miss rate in the previous scorecard. Re-run
against the same corpus with the current brain, the real figure is **23.8%**.

Fixed at the chokepoint — `consequences()` now normalises its own operands, so
a future caller cannot reintroduce it by forgetting a `.replace()`.

**Rule that follows:** a harness that can report a failure the system did not
commit is more dangerous than no harness. Two of the fixes below are the same
lesson in different clothes.

---

## 1. Voice / ambient intent

713 live decisions against a 1000-line corpus: 164 walks of life, 47
conversations, 278 hard cases, gold split act 500 / ignore 427 / ask 73.
Median decision latency 13.2s.

### The two that matter

```
FALSE PINGS :  11 of 307 silent lines   =   3.6%   <- reached him over nothing
MISSES      : 150 of 405 errands        =  37.0%   <- real need, nothing happened
behaviour accuracy : 74.9%  (533/712)
hard cases         : 96.3%  (187 lines)  vs 67.2% on the rest
```

### What is strong

Restraint. The nine hard kinds — the traps the product must not fall into —
hold at 96.3% overall, with retraction, media, ack and in-flight at 100%. It
does not act on a plan the owner took back, on a line quoted off the radio, on
a job somebody else already owns, or on a bare "yeah, no, totally".

False pings at 3.6% is the number the MVP is judged on, and it is low.

### What is weak, and it is one clean gradient

```
BY REGISTER   (the product claim: no imperative needed)
    thinking_aloud            56.8%   50/88
    worry                     58.4%   87/149
    complaint                 72.3%   68/94
    realisation               73.5%  100/136
    aside                     89.1%   90/101
    fragment                  94.8%   55/58
    direct                    96.5%   83/86
```

The closer speech gets to a request, the better it does. The further it gets
into unstructured worry — which is the product's own headline claim — the worse.

Every single miss is `decision=ignore` with an **empty goal**: no errand was
formed at all. The shared shape is an *impersonal statement of a gap*, with no
first-person commitment verb:

- "The temporary works design has not been signed by anyone competent."
- "We are going to be short on till float over the bank holiday."
- "We have not booked anything for half term and everything will be gone."
- "I am on nights all next week and I have not sorted anything for the kids."

There is no positional drift (early 28.9% vs late 29.9% within shared walks of
life), so this is a capability boundary, not degradation over a run.

### Two things that look like failures and are not

**The `ask` lane fired 4 times in 49.** This is deliberate.
`brain/worker.py:1955` demotes a wordless `ask` to quiet work, because the feed
renders any `ask` as the header "Quick question for you" and a header with no
question under it is a lie. The corpus's `ask` expectations are miscalibrated
against a design decision, not measuring a defect.

**Borderline lines are unstable across runs.** Fourteen lines that missed in
round 1 were re-pushed live: 5 of 14 were caught the second time. A clean-room
replay of the same 14 produced a goal for 12. So a meaningful share of the
"misses" are a coin flip, not a hard boundary — which matters more for "does it
hold up" than the headline rate does.

---

## 2. Browser agent

76 clean runs over 102 tasks (50 pre-existing + 52 authored this pass), against
the deterministic fixture web.

```
TASK SUCCESS      76.3%  (58/76)   target 80%   NOT MET
TIME TO DONE      median 0m18s · p90 1m40s
  browse slice    median 0m18s     target under 3m00s   MET
RECEIPTS          100% of done runs carried a verified receipt
FLAKY             none: every task that ran more than once landed the same way
MODEL FAULTS      0%
```

```
BY FAMILY
  booking      90.9%  10/11
  life_admin   87.5%  14/16
  lookup       81.8%   9/11
  research     72.2%  13/18
  work_ops     66.7%  10/15
  form           40%    2/5
```

Receipt verification at 100% and zero flakiness are the strong results: when it
says it did something, it carries evidence, and it behaves the same way twice.

`form` at 40% is the visible weak spot but rests on 5 clean runs — most form
tasks were lost to the credit cutoff below, so treat it as unmeasured rather
than as a 40% result.

**Observed, worth a look:** on several local-fixture tasks the agent left the
supplied `start_url` and ran a bing.com search instead
(`ext-a-dozen-mugs-cheapest`, `ext-a-guide-guy-line-length`). On a datacenter
IP that path ends at a CAPTCHA; here it merely burned steps.

---

## 3. Chrome extension

| check | result |
|---|---|
| `extension/tests/run_all.mjs` | **42/42** suites, no browser, ~60s |
| `pytest tests/` | **833 passed** in ~9s |
| `proof/fixtures/verify.sh` | **50/50**, byte-identical across restarts |
| `proof/battery/selfcheck.mjs` | 9/9 |
| `extension_smoke.mjs` checks 1-8 | pass (register, pair, model, queue, poll filter) |

Live stress (`proof/extension_stress.mjs`, new):

- **s1 — a banking errand is refused before the run starts.** PASS in 4s,
  `needs_user`, zero requests to the decoy bank. The refusal is pre-LLM, so it
  costs nothing and cannot be talked out of it.
- **s6 — one errand opens exactly one tab.** PASS.
- s2/s3/s4 staged but unrun — see the blocker.
- s5 cannot be staged at all: PocketBase owns `updated` as an autodate field
  and rewrites it on PATCH, so a stale row cannot be faked over the API. The
  scenario now reports SKIP and points at the offline suite that does cover it.

**Observed:** the browser accumulates a tab per finished job — 15 open after
~34 tasks. Keeping the tab is deliberate after a hand-back (the session and the
half-filled form survive); after a `done` ending it looks like a leak.

---

## 4. Blocker

The OpenRouter account is exhausted: **240.07 of 240 credits used**, HTTP 402.

It does not fail loudly. `brain/worker.py` stamps `decision="error"` and the
memory extractor "falls back to rules", so the results file keeps filling with
rows that look like judgements. Handling:

- every voice lane truncated at its **first** `error` row, not filtered — a
  rules-fallback `ignore` written after the cutoff is not a decision either.
  **188 of 901 rows discarded.**
- every battery run whose result or trace mentions 402 or a killed browser
  excluded. **20 of 96 discarded.**

`llm_errors`, which is regex archaeology over the trace, did **not** catch the
402. That is why the first battery scorecard read 63.5% and the honest one
reads 76.3%.

---

## 5. What was built

| file | what it does |
|---|---|
| `proof/chrome_arm.mjs` | cold → paired, model-armed browser in ~7s |
| `proof/lanes.py` | isolated owner / worker / fixture / browser per lane |
| `proof/ambient/fanout.py` | shards a corpus across voice lanes and merges |
| `proof/extension_stress.mjs` | six live scenarios a mock cannot reach |

Four traps `chrome_arm.mjs` exists to close, each of which cost a round here:

1. `extension/config.js` defaults to **production**, and `onInstalled`
   registers before any script can write storage. Launch now blackholes the
   production host with `--host-resolver-rules=MAP <host> ~NOTFOUND` and
   **verifies the blackhole before pairing anything**. No code change to the
   extension under test.
2. An unpacked extension's id is `sha256(absolute path)`, first 128 bits,
   nibbles mapped to `a..p`. Derive it. Taking "the first service worker" off
   `/json/list` latches onto one of Chrome's own component extensions and dies
   on `chrome.storage` being undefined.
3. MV3 workers are killed at ~30s idle and respawn with a **new target id**; a
   held socket goes silent forever. Re-resolve every call.
4. `import()` is banned in a service worker, so `background.js` exports are
   unreachable over CDP. Registration is triggered the way a person triggers
   it: open the setup page, whose `anticipy-ping` polls on the spot.

Measured speedups: **31s → 2.5s per utterance** (8 voice lanes); five minutes
of manual clicking → 7 seconds per browser.

### Harness fixes

- `proof/ambient/run.py` — the timestamp bug in §0.
- `proof/battery/run.mjs` — `--fixture` now also rewrites each fixture task's
  `start_url` at mint time. Without it the flag redirected only the harness's
  own bookkeeping while the agent, which reads `start_url` off the job row,
  kept browsing 8899 — so lane isolation was imaginary and the
  anti-recitation check was reading another lane's evidence.
- `proof/extension_stress.mjs` — fails closed on infrastructure endings. `s2`
  asserts "permits stayed 0", which is also true when the model 402'd before
  the run reached a button; it reported PASS off a run that proved nothing.
  Scenarios whose assertion is "nothing bad happened" must first establish
  that anything happened, or return SKIP.
- Same class again: `s6` counted every tab on the fixture origin and reported
  `peak_tabs=10` — ten leftovers from earlier tasks in a long-lived browser,
  not ten claims of one job. It now snapshots before queueing and diffs.
- `.agents/skills/testing-anticipy/SKILL.md` rewritten: the paths were Linux,
  and it claimed `BLOCKED_DOMAINS` parks at `awaiting_confirm` (it returns
  `needs_user`) and a 10s heartbeat (it is 30s).

---

## 6. What is still open

1. **Buy credit and re-run.** Everything is staged:
   `fanout.py --label round2` over the same 1000 lines gives the repeat pass,
   and `run.mjs --repeat3` gives the recipe-effect block.
2. **The `worry` / `thinking_aloud` gradient** is the one engine-level finding
   worth acting on. Deliberately not attempted here: it is a wide-blast-radius
   change, and it would have been tuned against a measurement that had just
   been found broken. The corpus and the A/B path now exist to do it honestly.
3. **`form` family** needs a clean re-run before its 40% means anything.
4. **Tab retention after a `done` ending** — confirm intended or fix.
5. **The agent leaving `start_url` for bing.com** on local tasks.
