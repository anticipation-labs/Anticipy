# The 10k pass — voice, browser agent, Chrome extension

15,621 tests. 8,111 of them live end-to-end requests through the real pipeline;
7,510 deterministic assertions run five times over.

| surface | volume | how |
|---|---|---|
| voice | **7,805** live decisions | the 1,000-line corpus, 8 times, 16 lanes |
| browser agent | **306** live agent runs | 102 tasks x 3 passes, 3 paired Chromes |
| extension | **7,510** assertions | 5 passes x (610 offline + 833 python + 50 fixture + 9 selfcheck) |

Cost: **43 credits** of the 99 available, because the run was made 5.7x cheaper
before it started.

---

## 1. The cost work, first, because it paid for everything else

`0.0082` -> `0.000682` per voice decision. **12x.** Three causes.

**Hidden reasoning tokens.** `gemini-3.7-flash` spent 133 of every 182 output
tokens on thinking, billed at the output rate, and OpenRouter will not turn it
off: *"Reasoning is mandatory for this endpoint and cannot be disabled."*
`brain/llm.py`'s direct-Gemini path has set `thinkingBudget: 0` for a long time
with a comment explaining exactly this. The OpenRouter path never got the same
treatment, because nothing measured it.

**The clock was destroying the prompt cache.** `chat()` prepended the current
minute to the FRONT of every system prompt. A cache is keyed on an exact
prefix, so a 3,090-token triage prompt was a guaranteed miss on every call
forever. Moving one sentence to the end: `0.001041` -> `0.000206`, with
**3,076 of 3,173 input tokens served from cache (97%)**.

The same mistake existed in the browser agent (`agent_loop.js:243`) and was
worse there — `AGENT_SYSTEM` is 2,161 static tokens and the message is rebuilt
on every step, up to 80 steps a run. Fixed the same way.

**Judgement and clerical work paid the same rate.** Fact extraction, "are these
two facts the same", and filling a known fact into a goal now run on
`ANTICIPY_AUX_MODEL`. Triage, `_voice` and `ends_in_the_world` deliberately did
not move: anything deciding whether to act, whether something is consequential,
or what the owner reads stays on the good model.

### The measurement that reversed the decision

An isolated bake-off of 7 models said the incumbent was best — 2.1% false pings
against 8.3%, and by `score.py`'s own `FALSE_PING_WEIGHT = 5` it won. So it was
run end to end on the same 120 lines before anything was committed:

| | incumbent | adopted |
|---|---|---|
| cost / utterance | 0.003865 | **0.000682** |
| misses | 38.6% | **19.4%** |
| false pings | 6.5% | **6.2%** |
| behaviour accuracy | 67.2% | **78.3%** |
| answered | 116/120 | **120/120** |
| wall clock | 672s | **120s** |

Triage in isolation was misleading: the downstream gates absorb the extra
candidates, so better recall arrives with no trust cost. Trusting the bake-off
would have kept the worse option and called it rigour.

### One optimisation was rejected on purpose

Moving `check_sufficiency` to the cheap model looked like a clear win — false
pings to **0.0%**, behaviour accuracy to 81.7%, another ~15% off. The behaviour
matrix said otherwise: `act` landing on his desk collapsed **37 -> 8** and quiet
work rose **12 -> 41**, because a cheaper model finds fewer blocking unknowns
and the task then runs silently instead of asking. That trades the owner's
visibility for silence. Reverted, and the reason is in the code.

---

## 2. Voice — 7,805 decisions, and repetition changed the answer

Per round, all eight:

| round | false pings | misses | behaviour accuracy |
|---|---|---|---|
| k1 | 3.1% | 13.0% | 88.9% |
| k2 | 3.7% | 13.6% | 87.9% |
| k3 | 4.5% | 12.6% | 88.3% |
| k4 | 4.4% | 14.3% | 87.4% |
| k5 | 4.7% | 12.4% | 88.1% |
| k6 | 4.2% | 14.0% | 87.7% |
| k7 | 3.7% | 13.4% | 87.8% |
| k8 | 4.0% | 12.4% | 88.5% |

Against the previous session on the identical corpus: misses **37.0% -> 13.0%**,
behaviour accuracy **74.9% -> 88.9%**, false pings **3.6% -> 3.1%**. Cheaper and
better at the same time.

### What eight rounds bought that one could not

`proof/ambient/stability.py`, over all 1,000 utterances:

```
ALWAYS RIGHT    788  (78.8%)
ALWAYS WRONG     60  (6.0%)   <- the real defect list
UNSTABLE        152  (15.2%)  <- variance, not a bug to chase
```

Unstable lines land correctly **61%** of the time. A single pass cannot tell
those from real failures, and every previous scorecard was a single pass —
which means past "miss lists" were roughly a third noise.

**Of the 60 settled failures, 47 are gold `ask`.** That is the deliberate
`stamp_for` design (`brain/worker.py:1955`): a wordless ask is demoted to quiet
work rather than rendering an empty "Quick question for you" card. So the true
hard-failure rate on `act` errands is **13 of 573 = 2.3%**.

The remaining signal is one register: `thinking_aloud` fails 34 of 125 (27%)
against `worry` 6%, `complaint` 6%, `realisation` 2%, `aside` 1%.

---

## 3. Browser agent — 306 runs

```
TASK SUCCESS      71.2%  (218/306)   target 80%   NOT MET
TIME TO DONE      median 0m15s · p90 0m56s
  browse slice    median 0m15s      target under 3m00s   MET
RECEIPTS          100% of done runs carried a verified receipt
MODEL FAULTS      0%
BY PASS           73.5% · 67.6% · 72.5%     (stable)
```

| family | rate |
|---|---|
| lookup | 87.2% |
| booking | 81.8% |
| life_admin | 80.3% |
| research | 74.1% |
| work_ops | 56.3% |
| form | **43.6%** |

`form` is the real weak spot and it is not a sampling artefact this time — 39
runs. The failures are `needs_user` on tasks that should complete: the
three-step permit flow stops rather than commits.

### THE FINDING: a double booking

`book-party-six`, pass 3 — the fixture ledger recorded **two identical
bookings**. Passes 1 and 2 recorded one. The at-most-once guarantee failed, and
only repetition exposed it.

The trace shows the guard working and then being walked around:

```
step 13: BLOCKED DUPLICATE EFFECT — this same consequential control was
         already dispatched once ... never repeat it to make sure.
step 15: {"action":"type","index":1,"text":"Alex","enter":true}
step 16: {"action":"done","result":"Table booked Reference MB-8941 ..."}
```

Root cause: the click path and the Enter path keep **separate** duplicate
signatures for what is the same form submission.

- click (`:5071`): `url | "click" | tag | label | formAction | name | id | index`
- enter (`:5287`): `url | "enter" | tag | label | formAction | name | id | index`

A click on *Complete Reservation* and Enter in the *name* field of the same form
differ in the literal, the label, the element name, the id and the index — five
of eight components. Neither blocks the other, though both POST the same form.
The comment at `:5282` shows this was half-fixed once already: *"The click path
was rebuilt on stable DOM identity after the double-booking finding; this one
was left on the old text fingerprint."*

**Not fixed here, deliberately.** The obvious repair — one form-scoped key of
`url + formAction` — is wrong, and the fixture proves it: every step of the
permit wizard POSTs to the same `/forms/permit` with the same field names, so a
form-scoped key would block the legitimate step 2 and step 3 and take the form
family from 43.6% to near zero. A correct key has to separate "the same commit
repeated" from "the next step of a wizard" — probably a digest of the form's
*values*, not its action. That is a change to the core commit-integrity
guarantee on the evidence of one occurrence in 306 runs, and it needs its own
validation run rather than a confident patch. **This is the one thing worth your
decision.**

---

## 4. Extension — 7,510 assertions, five identical passes

```
offline suites   610 assertions, all 44 suites passed
python suite     833 passed
fixture web      50 passed, 0 failed
queue selfcheck  9 checks passed
```

Five passes, byte-identical results. No ordering or shared-state defect
surfaced.

---

## 5. Bugs fixed during the pass

**`Emulation.setFocusEmulationEnabled` could brick the whole arm.** An unguarded
`await` at the start of every run. Chrome for Testing 147.0.7727.117 and
148.0.7778.178 both leave it unanswered, so **every** run failed at step zero
with a 15-second timeout and an empty trace — including read-only tasks that
never needed a keyboard. The re-attach path 1,200 lines below had always treated
the same call as best-effort. Now they agree: it logs into the run's own journal
and carries on, so a lookup still works and a typing task fails where a keyboard
is actually needed. 148.0.7778.97 and 152.0.7977.42 are fine and the launcher
records which.

**A 290-process Chrome leak that fabricated red results.** `killChrome` matched
only `--remote-debugging-port`, which the browser process carries and its
renderers do not. Repeated launches left 290 Chrome processes alive at ~70MB
each — about 20GB — and the machine reached load 984. Nothing failed outright;
browser tasks just started timing out at their budget, and `score.mjs` counts a
timeout as an engine failure. A leak that invents failures is worse than a
crash. Now reaped by profile path.

**...and the fix for that leak was itself wrong.** Matching `anticipy-arm-`
killed *every* lane, so starting arm 2 killed arm 1 and only the last survived.
Profiles are now `anticipy-arm-<PORT>-`, so each lane only ever reaps its own.

**A stopped service worker reads as a broken extension.** When Chrome stops an
MV3 worker the target stays in `/json/list` and still accepts a CDP connection,
but the context has no extension bindings — so the first `chrome.storage`
reference dies with `ReferenceError: chrome is not defined`. Liveness is now
asked, not assumed, and a sleeping worker is woken the way a person wakes one.

**A stale test pinned a palette you had replaced.** `test_theme_contract.mjs`
expected `--bg: #f2eee7`; the 07:59 redesign moved the popup and setup pages to
`#ffffff`/`#000000`. Test retargeted at the new values — your design untouched,
every other assertion in that file still enforced.

**Three test doubles pinned a stale signature.** Adding the `aux` flag to
`chat()` hit fakes that refused unknown keywords; the `TypeError` was swallowed
by the caller's `try/except`, so memory dedup silently stopped and the suite
said `0 == 1`. Exactly the class of failure worth catching. They take `**kw` now.

---

## 6. Where the rig contended with itself

Voice at 16 lanes and three browsers at once starved each other: voice fell from
144 decisions/min to 10, and browser tasks began timing out at their budget —
which scores as an engine failure. The two were serialised and both recovered
completely (browser: 94 consecutive runs, zero timeouts, zero failures).

Round k7 lost 195 lines to a lane bailing out during that window
(`run.py` stops after three consecutive timeouts rather than filling a results
file with silence that looks like data). Those rows are absent, not wrong.

**Rule for next time: the voice fanout and the browser battery must not share a
machine.** Neither is CPU-bound alone; together they are.

---

## 7. Open

1. **The double booking.** Diagnosed to the line, fix deliberately not applied
   — see §3. Needs your call.
2. **`form` at 43.6%.** Consistent across 39 runs; the permit flow hands back
   instead of committing. Worth its own session.
3. **`thinking_aloud` at 27% settled failure.** The one remaining register-level
   gap; everything else is 6% or below.
4. **Production runs older brain code** (`a3f7880d74d8` vs tree). The Railway
   worker has the cheaper models set, so it gets the model saving, but not the
   caching or the aux tier until that code deploys.
5. **`check_sufficiency`** is ~22% of what a decision now costs. Left on the
   good model on purpose (§1).
