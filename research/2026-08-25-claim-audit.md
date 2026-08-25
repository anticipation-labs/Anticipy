# Claim audit — 2026-08-25

Adversarial re-derivation of eight claims that decisions are resting on.
Read-only pass; nothing in this audit fixed anything. Law 6.

Run at **2026-08-25 08:51–09:20 UTC**, tree
`/Users/josegaelcruzlopez/Desktop/anticipy-omize`, branch
`jose_anticipy_system` @ `8a58e14e`, against LIVE
`https://backend-production-61e0a.up.railway.app`.

**Every verdict below is re-runnable.** Where a command needs credentials, it
needs `.env.local` in the tree root — the gates self-load it as of `8a58e14e`
(see claim 8), everything else in `proof/` does not, so those are shown with an
explicit loader.

A note on method, because it nearly cost me a false verdict: my first check of
the extension zip ran `mkdir -p X && rm -rf X/* && unzip …`, and zsh aborts the
whole `&&` chain when `X/*` matches nothing. The `unzip` never ran, and the
import checker then walked an empty directory and printed a clean bill of
health. **A green result from a command that silently did not execute looks
exactly like a green result.** Every zip finding below is from the re-run.

---

## Verdict table

| # | Claim | Verdict |
|---|---|---|
| 1 | Outcome rate is 6.1% — 16 of 263 lines produced an outcome at 48h | **CONFIRMED** (exactly), with a denominator caveat and a ~19h shelf life |
| 2 | Zero lines arrived in the last 24 hours | **CONFIRMED** independently of the script |
| 3 | Production serves extension 0.8.4 while source is 0.11.0 | **CONFIRMED** |
| 4 | The committed zip is missing `private_places.js` | **CONFIRMED**, and worse than stated |
| 5 | `SpeechTranscriber` silently ignores `AnalysisContext.contextualStrings` | **CONFIRMED as an external fact, MISCATEGORISED as a repo observation** — and its load-bearing consequence is prospective, not current |
| 6 | `speaker` is 0% across 221 production events, cause "enrollment unreachable" | **SUBSTANCE CONFIRMED; the number 221 is UNVERIFIABLE today** |
| 7 | `MediaUrl` appears in no `.py`, `.js` or `.swift` in the repository | **FALSE** (the conclusion it supports survives) |
| 8 | done_gate legs 1–5 pass and only leg 6 fails; gates self-load `.env.local`; environment wins over the file | **CONFIRMED** on all three, with one operational trap |

---

## 1. Outcome rate 6.1% — 16 of 263 at 48h

**Verdict: CONFIRMED.** Reproduced to the digit.

```
  lines that arrived            263
  produced something            16   (6%)   <- THE NUMBER
  ...
  {"outcome_rate": 0.061, "rows_bucketed": 263, "rows_unread": 0, "jobs_read": 19}
```

### Does the script measure what the number claims?

Checked four ways, and it survived all four:

1. **The denominator was fully read.** `rows_unread: 0`, and an independent raw
   query returns `totalItems=263` for `kind="transcript"` in the same window —
   the same 263, not a coincidence of a paging cap.
2. **Nothing fell out of the buckets.** `rows_bucketed == lines == 263`.
3. **The 16 recompute by hand.** 15 rows carry `decision=act` (7) or a
   non-empty `goal` (8); zero carry `decision=ask`. The 16th is the `job_only`
   join. Recomputed with my own code, not the script's: 19 jobs in window name
   16 distinct transcript ids, 15 of which are inside the window, and exactly
   1 of those 15 has neither act/ask nor a goal on its own row —
   `o5g1vcjl7r2kkoi`, `"I don't know yet"`, `decision=ignore`.
4. **The job join is the careful one.** The docstring warns that a naive
   substring match on `params` would invent the join. Verified: **19 of 19**
   jobs' `params` string contains `source_event_id`, and **0 of 19** carry it
   as a top-level key — it lives inside `_workflow`, a JSON string nested
   inside the params JSON string. The script parses; it does not grep.
5. `tests/test_outcome_rate.py` — **54 passed**.

### What I could not falsify it by

I tried to break the number by: re-reading the window raw and counting rows
myself; checking for a paging cap; checking for rows lost between the read and
the buckets; recomputing the job join with independent code; enumerating every
`kind` in the window to see whether some other kind is a line that arrived; and
running its own test suite. None of it moved the number.

Enumerating kinds is the one that came closest to a real objection. All events
in the 48h window: `transcript 263, profile 30, anticipy_says 19, sms_reply 2,
anticipy_text 2`. `sms_reply`/`app_reply` are inbound from the owner and are
**not** in the denominator — defensibly, since they are answers to her rather
than lines the ears delivered, and at 2 rows they cannot move 6.1%.

### The caveat that matters: 263 is a count of ASR rows, not of utterances

This does not make the number wrong. It makes what the number is *about*
narrower than "263 things he said."

- **111 of 263 (42%) are ≤4 words** — the exact length `shard_too_thin` is
  built to drop. Counting a designed drop as a line that failed to produce an
  outcome is counting the brain's own policy against it. `capture_day --hours
  72` independently reports a 41% shard rate, so this is not an artefact of my
  word-splitter.
- **16 rows are a strict prefix of a later row within 30s** — partial/final
  duplicates of one utterance: `'Mass'` → `'Massive 3-D printer case'`,
  `'Par'` → `'Pardon'`, `'con'` → `"context before the speech layer…"`,
  `'100+'` → `'100+2 RPM'`. Each such pair inflates the denominator by one.
- **Sensitivity.** Restricting to lines longer than the shard floor:

  | denominator | n | outcomes | rate |
  |---|---|---|---|
  | all rows (as claimed) | 263 | 16 | **6.1%** |
  | >0 words, act/ask/goal only | 263 | 15 | 5.7% |
  | >2 words | 181 | 15 | 8.3% |
  | >4 words (the brain's own shard floor) | 153 | 13 | **8.5%** |

  So the honest statement is **5.7%–8.5% depending on what counts as a line**,
  and 6.1% is a defensible point inside it, not a measurement error.

- **The script's own docstring says 5.7% at 48h.** That is exactly the 15 —
  act/ask/goal without the job join. The gap between the docstring and the
  headline is one judgment call about one row (`"I don't know yet"`, which a
  job named as its source while the brain stamped it ignore), not a
  disagreement about the data.

### The shelf life — the part most likely to burn someone

The window **rolls from now**, and production has been silent for a day. All
263 transcripts sit in two bursts:

```
segment okmt7r775yerfai  n=111  source=<empty>  08-23 19:41..19:54
segment sbu14r4v049jhqp  n=96   source=phone_mic 08-24 01:17..01:30
(+10 smaller segments; last transcript of any kind: 2026-08-24 03:34:24Z)
```

After **2026-08-26 03:34 UTC** the identical command returns `lines: 0` and
`outcome_rate: null`. The pair "16 of 263" is a snapshot with roughly 19 hours
left on it. Anyone quoting it after that will be quoting a number the command
no longer produces — quote the window's absolute edges, not "48h".

One more thing the rows say and nobody wrote down: **111 of the 263 (segment
`okmt7r775yerfai`, 13 minutes on 08-23) arrived with `source` empty**, not
`phone_mic`. `capture_day` renders that as `unknown`. Whether those are device
capture at all is not answerable from the row.

**Re-run:**
```sh
cd /Users/josegaelcruzlopez/Desktop/anticipy-omize
python3 -c "import sys;sys.path.insert(0,'.');from overnight import _env;_env.load('.');import runpy,sys;sys.argv=['proof/outcome_rate.py','--hours','48'];runpy.run_path('proof/outcome_rate.py',run_name='__main__')"
python3 -m pytest tests/test_outcome_rate.py -q
```

---

## 2. Zero lines arrived in the last 24 hours

**Verdict: CONFIRMED**, and confirmed *without* the script under test in claim 1.

Raw query against LIVE, all kinds, no filter but the window:

```
--- ALL events last 24h: fetched 3 totalItems=3
      anticipy_says            3
--- ALL events last 48h: fetched 316 totalItems=316
      transcript               263
      profile                   30
      anticipy_says             19
      sms_reply                  2
      anticipy_text              2
```

Three events in 24 hours, every one of them her own speech. The newest
transcript of any source is **2026-08-24 03:34:24.685Z**; the audit ran at
2026-08-25 08:51 UTC — **29 hours** of nothing. The shape is precisely the one
`outcome_rate.py`'s docstring says `is_the_brain_live.py` exits 0 on.

**Re-run:**
```sh
cd /Users/josegaelcruzlopez/Desktop/anticipy-omize
python3 -c "
import os,sys,collections,datetime as dt;sys.path.insert(0,'.')
from overnight import _env;_env.load('.')
import requests
PB=os.environ['ANTICIPY_PB'].rstrip('/')
H={'X-Anticipy-Worker':'1','X-Anticipy-Token':os.environ['ANTICIPY_SERVICE_TOKEN']}
s=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
r=requests.get(f'{PB}/api/collections/events/records',headers=H,params={'filter':f'created>=\"{s}\"','perPage':200},timeout=40).json()
print(r['totalItems'],collections.Counter(i['kind'] for i in r['items']))"
```

---

## 3. Production serves 0.8.4 while source is 0.11.0

**Verdict: CONFIRMED.**

| | version | name | files | bytes | md5 |
|---|---|---|---|---|---|
| **DEPLOYED** `/anticipy-claude-version-extension.zip` | **0.8.4** | "Anticipy Claude Version" | 12 | 122,423 | `133c74a8a0fc64db231c5d6fa19c1e88` |
| committed `backend/pb_public/…zip` | 0.11.0 | "Anticipy" | 19 | 239,409 | `164decadf2dbb086ca0decc9123b7b44` |
| tree `extension/manifest.json` | 0.11.0 | "Anticipy" | — | — | — |

The deployed build is missing seven files the committed zip has — including
`login_wall.js`, `recipes.js`, `learn.js`, `side_trip.js`, `supervised_read.js`,
`config.js` and `theme.js` — and still carries the old product name. Note the
served path is `/anticipy-claude-version-extension.zip` at the root;
`/pb_public/…` is a 404.

**Re-run:**
```sh
curl -s -o /tmp/x.zip https://backend-production-61e0a.up.railway.app/anticipy-claude-version-extension.zip \
  && unzip -p /tmp/x.zip manifest.json | grep '"version"' \
  && grep '"version"' /Users/josegaelcruzlopez/Desktop/anticipy-omize/extension/manifest.json
```

---

## 4. The committed zip is missing `private_places.js`

**Verdict: CONFIRMED — and the interesting failure is not the missing file.**

The zip holds 19 files and `private_places.js` is not among them, while
`extension/private_places.js` (17,314 bytes) exists in the tree.
`package.json` is also absent, correctly.

**It did not change under me.** md5 `164decadf2dbb086ca0decc9123b7b44` at the
first read and identical at the last, mtime `Aug 24 22:56:39 2026`. No other
agent rebuilt it during this audit; this is not a stale read.

Two things nobody has written down:

**(a) The zip is not broken, it is old.** `extension/agent_loop.js:18` does
`… from "./private_places.js"` — a missing module import would kill an MV3
service worker at registration. But the zip's `agent_loop.js` contains **zero**
occurrences of `private_places`. It is a build that predates the second door
entirely. Checked every relative import in every `.js` in the zip against the
zip's own file list: **no missing imports.** It will load. It simply has no
private-places lock.

**(b) The zip is version-stamped 0.11.0 while carrying pre-0.11.0 code.** Its
`manifest.json` is byte-identical to the tree's, so it *announces* 0.11.0 — but
five of its files do not match the tree:

```
  DIFFERS  agent_loop.js       (zip 320430 / tree 363809)
  DIFFERS  background.js       (zip  87181 / tree  95579)
  DIFFERS  config.js           (zip   4843 / tree   7634)
  DIFFERS  side_trip.js        (zip  20388 / tree  32915)
  DIFFERS  supervised_read.js  (zip  33957 / tree  34644)
  MISSING-FROM-ZIP  private_places.js
```

This matters because `stranger_gate` holds a leg on "the extension being
downloadable at the version the app demands", and that leg is named in
done_gate leg 6's own remedy text. **The version number cannot tell you whether
a rebuild worked.** A `manifest.json` copied forward makes a stale bundle
indistinguishable from a fresh one to any check that reads the version. Three
distinct extensions are in play right now — deployed 0.8.4, committed
"0.11.0"-but-stale, and the tree.

**Re-run:**
```sh
cd /Users/josegaelcruzlopez/Desktop/anticipy-omize
unzip -l backend/pb_public/anticipy-claude-version-extension.zip
rm -rf /tmp/z; mkdir -p /tmp/z
unzip -o -q backend/pb_public/anticipy-claude-version-extension.zip -d /tmp/z
for f in /tmp/z/*.js; do b=$(basename $f); \
  [ "$(md5 -q $f)" = "$(md5 -q extension/$b)" ] && echo "same $b" || echo "DIFFERS $b"; done
grep -c private_places /tmp/z/agent_loop.js extension/agent_loop.js
```

---

## 5. `SpeechTranscriber` silently ignores `AnalysisContext.contextualStrings`

**Verdict: CONFIRMED as a fact about Apple's API. MISCATEGORISED as a fact
about this repo. Its load-bearing consequence is prospective, not current.**

The question asked was: distinguish "we observed it do nothing" from "we
assumed it". **Neither is the right category.** The right one is *"Apple's own
engineer said so in an accepted answer, and I re-fetched the page and confirmed
the wording."*

### The evidence is sound, and I verified it independently

`research/2026-08-24-engine-options.md:342-352` quotes Apple Developer Forums
thread 811083. I fetched `https://developer.apple.com/forums/thread/811083`
myself and the quote is verbatim, by **Apple_Agent**, marked **Accepted Answer**:

> "However, currently, contextual strings only help transcriptions from the
> `DictationTranscriber` module. The `SpeechTranscriber` module does not
> currently take contextual strings into account."

The repo doc is also honest about the half it *could not* verify — it labels
the existence of `AnalysisContext.contextualStrings` as *"Relayed from a peer
session; Apple's doc pages render client-side and I could not read the prose
myself."* That is the right way to record a second-hand fact, and it is why
this verdict is not "unverifiable".

### But nothing in this repo uses that API, so nothing was observed

```
grep -rn "SpeechTranscriber|SpeechAnalyzer|AnalysisContext|DictationTranscriber" app/
→ (no matches)
```

Zero code hits **anywhere** in the tree. Every hit is prose: 21 lines in
`research/2026-08-24-engine-options.md`, 2 in `docs/DECISIONS-2026-08-24.md`,
2 in `research/solutions-2026-08-24/designs.json`, 1 in
`CAPTURE-ARCHITECTURE.md:150` (a design sketch).

Both shipping request sites use the **legacy** Speech API, where
`contextualStrings` is not in dispute:

- `app/ios/Anticipy/Audio/PhoneListener.swift:805` — `req.contextualStrings = AnticipyVocabulary.current()` on an `SFSpeechAudioBufferRecognitionRequest`
- `app/ios/Anticipy/Audio/LocalTranscriber.swift:23` — same

### Therefore the load-bearing reading is wrong as stated

"A vocabulary fix that looks right does nothing" is **not true of the code that
exists today**. `AnticipyVocabulary` is wired into `SFSpeechRecognizer`, which
is the module Apple says contextual strings *do* help. The correct statement is
conditional: *if* anyone migrates `PhoneListener` to `SpeechTranscriber`, the
biasing stops and the guard does not notice.

### The trap it warns about is real, and currently unguarded

Verified in `overnight/tejas_gate.py:384-393`. Leg 7 is two string tests
against `PhoneListener.swift`:

```python
if "contextualStrings" not in listener:
    raise LegFailed(...)
if "Anticipy" not in re.sub(r"//.*", "", listener).split("contextualStrings")[-1][:400]:
    raise LegFailed(...)
```

A `SpeechTranscriber` migration that sets `AnalysisContext.contextualStrings`
with `AnticipyVocabulary.current()` in that file satisfies both predicates
**and does no biasing**. The warning is correct and the leg cannot currently
tell the two APIs apart.

**Re-run:**
```sh
cd /Users/josegaelcruzlopez/Desktop/anticipy-omize
grep -rn "SpeechTranscriber\|SpeechAnalyzer\|AnalysisContext\|DictationTranscriber" app/   # expect: nothing
grep -rn "contextualStrings" app/ --include="*.swift"                                       # expect: the two SFSpeech sites
sed -n '378,394p' overnight/tejas_gate.py
# and the source itself: https://developer.apple.com/forums/thread/811083
```

---

## 6. `speaker` is 0% across 221 production events, cause "enrollment unreachable"

**Verdict: the 0% is CONFIRMED and over-determined. The denominator 221 is
UNVERIFIABLE today. The relayed wording drifted.**

Source: `research/2026-08-24-engine-options.md:142` — *"0 of 221 `phone_mic`
rows carry a speaker tag"*, and `:254` — *"`speaker` 0% | 100% — enrollment
unreachable | Certain. One call site, measured 0/221."*

### The 0% reproduces everywhere I looked

| window | rows with a speaker |
|---|---|
| `capture_day --hours 72` (live, today) | `speaker_coverage: 0.0`, and 0.0 for **each** owner separately |
| all events, last 48h (316 rows) | 0 |
| all events, last 168h (751 rows, 542 transcripts) | 0 |
| every 72h window I swept, ending 08-22 15:00 → 08-25 00:00 | **0, in all 20 of them** |

### The 417 tagged rows are the fixture the doc itself flags — corroborated

The doc cautions that `capture_day`'s 22%-over-720h reading is a proof-script
artefact. I checked it independently and it is right: **417** transcripts in
all of history carry a speaker; **all 417 have an empty `source`**; **409** of
them match `other:v<N>` across **370 distinct values**; and they are confined
to **2026-08-05 → 2026-08-08**. That is `proof/speaker_live_test.py` /
`voice_roster_proof.py` output, not device capture. Real device coverage is 0%.

### The cause reproduces at the tree level

`VoiceEnrollView` is referenced from exactly one place in live source —
`app/ios/Anticipy/Views/SettingsView.swift:584`. (Other hits are the struct's
own definition, a comment in `project.yml`, and mangled symbols in a committed
`.xcarchive` dSYM.) The onboarding entry point does not exist, so no profile is
ever enrolled.

### What I could not reproduce: 221

No 72h window produces 221 `phone_mic` rows. Swept in 3h steps:

```
  end 08-24 03:00  phone_mic=213      <- the maximum anywhere near the doc's date
  end 08-24 06:00  phone_mic=202
  end 08-24 09:00 .. 08-25 00:00  phone_mic=189
  end 08-24 00:00  phone_mic=76
```

`capture_day --hours 72` today reports `{'phone_mic': 161, 'unknown': 130}`.
The figure was true of a window that has since rolled past, and rows cannot be
re-created, so it is not re-derivable — only its 0% numerator is, and that is
the load-bearing half.

Two drifts worth correcting in the relay: the doc says **221 `phone_mic` rows**,
not "221 production events" — and `capture_day` maps empty-`source` rows to
`unknown`, which is a *different* 130 rows, so "events" over-counts the base
the claim was actually about.

**Re-run:**
```sh
cd /Users/josegaelcruzlopez/Desktop/anticipy-omize
python3 -c "import sys;sys.path.insert(0,'.');from overnight import _env;_env.load('.');import runpy,sys;sys.argv=['proof/capture_day.py','--hours','72'];runpy.run_path('proof/capture_day.py',run_name='__main__')"
grep -rn "VoiceEnrollView" app/ios/Anticipy/
```

---

## 7. `MediaUrl` appears in no `.py`, `.js` or `.swift` in the repository

**Verdict: FALSE.** Five files match, in three languages:

```
overnight/stranger_gate.py
tests/test_stranger_gate.py
tests/test_evidence_host.py
backend/pb_hooks/evidence.pb.js
backend/pb_migrations/1700000045_evidence.js
```

The claim was true when written (`research/2026-08-24-mouth-and-hands1.md:177`
records the grep returning only the gate and its tests). It was invalidated by
commit **`0d2ee640` — "The photo a done-text promises had nowhere in the
product to exist"**, which added the two `backend/` files. Both new hits are
comments, not a wiring.

**The conclusion the claim supports survives.** `brain/voice_arm.py:411-420`
still posts only `{"From", "To", "Body"}` to `Messages.json` and takes no media
argument, so the done-text still cannot carry a photo and `stranger_gate` leg 8
is still legitimately red. Note the gate itself does **not** rely on the false
predicate: `stranger_gate.py:1526` anchors on the payload builder — "can *this
payload* carry `MediaUrl`" — precisely so a comment elsewhere cannot turn it
green. The gate is sound; the tree-wide grep that was quoted as its rationale
is now stale.

**Re-run:**
```sh
cd /Users/josegaelcruzlopez/Desktop/anticipy-omize
grep -rln "MediaUrl" --include="*.py" --include="*.js" --include="*.swift" .
sed -n '411,420p' brain/voice_arm.py
git log --oneline -1 -- backend/pb_hooks/evidence.pb.js
```

---

## 8. done_gate legs 1–5 pass, only leg 6 fails; gates self-load `.env.local`; env wins

**Verdict: CONFIRMED on all three parts.** One operational trap to record.

```
  [1] PASS  SHE HEARS YOU
  [2] PASS  IT WAS ONE CONVERSATION
  [3] PASS  SHE JUDGES RIGHT              dictation stays silent and a real plan still fires, 3/3
  [4] PASS  SHE ACTUALLY DOES IT          … backend-production-61e0a is standing by to run it
  [5] PASS  SHE SHOWS ONE CARD
  [6] FAIL  A STRANGER
  NOT DONE — first failing leg: 6 (A STRANGER)
```

**(a) The self-load is real and it announces itself.** stderr, first line:
`(loaded 36 value(s) from …/.env.local: OPENROUTER_API_KEY, ANTICIPY_MODEL, …)`.
Seven gates wire it identically at import time —
`consolidation_gate, is_it_live, replay_call, done_gate, triage_eval,
is_the_brain_live, stranger_gate` — each as
`_ENV_LOADED = _env.load_and_announce(ROOT)`.

**(b) The environment wins over the file.** Two levels:

*Unit.* With `ANTICIPY_PB` exported to a sentinel, `_env.load()` leaves it
untouched and omits the name from its return:

```
  before: https://SENTINEL-STAGING.invalid
  after : https://SENTINEL-STAGING.invalid
  ANTICIPY_PB in loaded-names list? False
  VERDICT: ENV WINS
```

*End-to-end.* Exporting **both** backend names flips leg 4 off production:

```
  (loaded 34 value(s) …)      <- 36 minus the two I exported
  [4] FAIL  SHE ACTUALLY DOES IT
        nothing healthy at https://sentinel.invalid: /api/health -> nodename nor servname provided
```

**(c) THE TRAP — precedence is per-variable, and the backend has two names.**
Exporting *only* `ANTICIPY_PB` did **not** redirect done_gate. Leg 4 printed
`https://backend-production-61e0a.up.railway.app` and talked to production,
because `done_gate.py:322` resolves `… or os.environ.get("ANTICIPY_BACKEND_URL")`
and `.env.local` still supplied that one. Across the Python tree, 17 files read
`ANTICIPY_PB` and 7 read `ANTICIPY_BACKEND_URL`.

The precedence rule is not defective — it did exactly what it promises for the
variable it was given. But **"I pointed it at staging" is one variable away
from "it silently hit production"**, which is the failure `_env.py`'s own
docstring says the rule exists to prevent. Both names must be exported
together, every time.

**Re-run:**
```sh
cd /Users/josegaelcruzlopez/Desktop/anticipy-omize
python3 overnight/done_gate.py
ANTICIPY_PB=https://sentinel.invalid python3 overnight/done_gate.py 2>&1 | grep -i 'railway\|sentinel'   # still prod — the trap
ANTICIPY_PB=https://sentinel.invalid ANTICIPY_BACKEND_URL=https://sentinel.invalid \
  python3 overnight/done_gate.py 2>&1 | grep -i 'railway\|sentinel'                                      # follows
```

---

## What should change

Ordered by what a wrong belief costs, not by claim number.

1. **Stop repeating "a vocabulary fix that looks right does nothing."** It is
   not true of the shipped code — `AnticipyVocabulary` feeds `SFSpeech`, where
   biasing works. It becomes true only on a `SpeechTranscriber` migration.
   Acting on the unconditional version means ripping out working code.
2. **`tejas_gate` leg 7 cannot tell the two APIs apart.** It is a grep for the
   literal `contextualStrings`. Before any `SpeechTranscriber` work, the leg
   needs to fail on the new API, or the migration ships green and mute. This is
   Law 3's shape exactly, and it is unguarded today.
3. **A version number is not evidence a zip was rebuilt.** The committed zip
   says 0.11.0 and carries five pre-0.11.0 files plus no `private_places.js`.
   Any check on the leg-6 path that reads the manifest version will accept a
   stale bundle. Compare file hashes against `extension/`, not the version.
4. **Quote `outcome_rate` with absolute window edges, never "48h".** The
   command stops producing 16/263 after 2026-08-26 03:34 UTC.
5. **Export `ANTICIPY_PB` and `ANTICIPY_BACKEND_URL` together or neither.**
6. **Retire the `MediaUrl` tree-wide grep as a rationale** — it is now false.
   The gate leg that depends on the payload builder is unaffected.
