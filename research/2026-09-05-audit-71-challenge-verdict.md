# Audit #71 — the CAPTCHA fence is a verdict, not a phrase — 2026-09-05

Law-1 item #71 from `research/2026-09-05-browser-region-audit.md`, built from
the reviewed brief's `corrected_mechanism` (the DESIGN alone was NEEDS-REWORK).
Repo-green with mutation-verified tests. **Not Law-3 done**: see the last
section.

## What decided, and what it cost

`looksLikeCaptcha(state)` in `extension/agent_loop.js` ran an English phrase
list — `just a moment`, `checking your browser`, `unusual traffic`, `verify you
are human`, `type the characters`, ... — over URL + title + the first 2000
chars of visible text, and on a hit the loop, with no model in the loop:

1. POSTed a paid solve to `/agent/solve-captcha` (`readChallenge` reads the v3
   sitekey off the badge that is on nearly every form on the web, so the solve
   went out for a challenge that did not exist);
2. on a read-only run at a host the owner never named, declared the host
   `UNUSABLE for the rest of this run` and navigated away (up to three);
3. otherwise parked the run with `needs_user` and texted the owner.

Measured: live, 2026-08-16, the Cactus Club booking — a v3 badge and a date
field, no challenge — parked, four texts over two hours, and the reservation
scrapped when he replied that there was no CAPTCHA. The 2026-08-16 patch
(`6aae24a2`) stripped the badge disclosure out of the blob and left the
predicate. `"Just a moment — we're holding your table for 5:00"` is a table
hold and `just a moment` was in the list. `login_wall.js` carried a SECOND
phrase list (`CHALLENGE`, different membership) for the same question, and the
loop called `detectsLoginWall(state)` without injecting the first — two keyword
verdicts on one question, which `login_wall.js`'s own header said must not
exist.

## What replaced it (all in `extension/agent_loop.js` unless noted)

**The deterministic half is what the page is MADE OF, never what it says.**

- `mapPage`'s injected `readFrame` (`:3182`) now keeps every `<iframe>` with
  its origin, box and a `hidden` flag computed from the ancestor chain
  (`display:none`, `visibility:hidden`, `opacity 0`), zero area, or a box off
  the document; and emits `widgets` for `.h-captcha`, `.cf-turnstile`,
  `.g-recaptcha` with their `data-size`. Both travel as `state.frames` /
  `state.widgets`. `iframes` (the >=80x60 subset feeding subframe click offsets
  and the mid-load wait) is unchanged, and the main-frame-only fallback keeps it
  empty exactly as before. `frameUrls[frameId]` (`:3276`) records each mapped
  subframe's own location.
- `challengeProvider(url)` (`:2715`) — a which-host check over
  `CHALLENGE_PROVIDERS` (`:2702`): challenges.cloudflare.com, hcaptcha.com,
  google.com and recaptcha.net under `/recaptcha/`, arkoselabs.com,
  funcaptcha.com, captcha-delivery.com, awswaf.com, px-cdn.net, px-cloud.net.
  Registrable-domain suffix match on a `.` boundary, so
  `challenges.cloudflare.com.attacker.example` is nothing. A provider missing
  costs an unasked question, never a wrong verdict.
- `challengeFurniture(state)` (`:2747`) — the sift. Painted provider frames
  and widgets only; a frame whose own URL declares `size=invisible` (query or
  fragment — reCAPTCHA's anchor, hCaptcha's invisible frame) is the badge and
  is excluded, as is a `.g-recaptcha` with `data-size=invisible`. On the real
  v3 page (anchor `size=invisible` + bframe in a `visibility:hidden` div) it
  returns `[]`: **zero calls, zero parks.**

**The meaning half is one question, asked alone.** `challengeVerdict`
(`:2826`): its own `modelFetch` through `/agent/llm`, `CHALLENGE_SYSTEM`,
temperature 0, `max_tokens: 8` (modelFetch's floor makes the wire value 64),
20 s bound (`CHALLENGE_VERDICT_TIMEOUT_MS`), never a key in the step reply. User
content: the errand (400 chars, fenced), URL, title, the furniture lines, the
element count with the first 40 lines cut to `[idx] <role> label` (labels are
value-redacted at the source; `[contains "..."]` / `currently "..."` extras and
`state.fields` are NOT sent), the visible text as a 3000-char prefix of the
same `state.text` the step prompt already sends whole, the last history line,
and whether the steady fingerprint moved. Four states by bare-token equality:
`BLOCKED`, `CLEAR`, `UNCLEAR` (a live model could not settle it), `UNANSWERED`
(no reply / non-2xx / timeout / cap / prose — every cause `console.log`ged).

**The caller compares, as a CEILING** (`:5966`–`:6073`): only
`verdict === CHALLENGE_BLOCKED` enters the old block — `trySolveChallenge`,
then the byte-identical `readOnly && !ownerNamedIt && walledSources.size < 3`
retreat, then the `needs_user` park. `CLEAR`, `UNCLEAR` and `UNANSWERED` all
continue; a fresh `UNCLEAR` pushes one history line naming the furniture. Why
a ceiling is right: every fence this gates — a paid solve, a navigate-away, a
park that texts the owner — is an over-fence when wrong, and 2026-08-16 was
exactly an over-fence. The backstops on a wrong CLEAR are a model with the
whole page (`AGENT_SYSTEM` names a CAPTCHA as a `needs_user` reason) and the
stall detector — not a deterministic click, because of the next item.

**The seatbelt that makes "no verdict → continue" safe.** `challengeFrameOf`
(`:3110`) resolves an index to its frame's origin; the click/type executor
(`:6661`) and the select executor (`:6473`) refuse any action whose target
lives in a provider's frame, push a `REFUSED — element N sits inside a
<provider> challenge frame` line, hide the index from the next map, and never
dispatch CDP input. Which frame a click TOUCHES — structure.

**Spend.** Per-run `challengeMemo` (steady fingerprint → answered verdict),
`challengeAsks` capped at `CHALLENGE_ASK_CAP = 8`, and `solvedPrints`: after a
successful solve the fingerprint is recorded and the BLOCKED branch is skipped
until the page moves, because a placed token moves neither text nor element
count and a memoised BLOCKED would otherwise re-fire the paid solver every
step. `UNANSWERED` is deliberately not memoised — nobody answering is not an
answer — and is re-asked next step under the cap.

**Deleted.** `looksLikeCaptcha` (record at `:2626`); in `login_wall.js` the
`CHALLENGE` regex, `stripBadge` and `looksLikeChallenge` (record at `:106`),
`detectsLoginWall`'s default `isChallenge` is now `() => false` (`:324`) and
`words` at `:341` no longer strips the badge (the disclosure matches none of the
remaining money/price/optional-account expressions — nothing in #70's scoring
changes). The loop injects `{ isChallenge: () => verdict === CHALLENGE_BLOCKED }`
(`:6094`), so the running system holds exactly one challenge judgement.
Touched in `login_wall.js`, and only this, so the #70 merge is clean: the
header's `captcha —` paragraph, the block between `AUTH_TITLE` and `Reading the
page map`, the `@param deps` JSDoc, the `isChallenge` default line, and the
`words` line.

## When the question fires on an ordinary run

Never, unless the page renders a painted challenge-provider frame or widget
that is not declared invisible. The badge page, a booking form, a search page,
a Cloudflare JS interstitial with no widget: zero calls. A page with a painted
Turnstile / hCaptcha / v2 checkbox pays one small call per distinct steady
fingerprint, at most 8 per run. The paid solve now needs a positive BLOCKED
plus a sitekey, once per fingerprint.

## Deliberately unasked, and still flagged

- Image CAPTCHAs that render no provider frame or container (an Amazon-style
  "type the characters" box) never reach the question: no furniture, no
  fence. The read-only retreat no longer fires on them; the step model parks
  them. Acceptable for a ceiling, named here on purpose.
- The comment after the old function ("a paid solving service used to sit
  here ... not something she should be able to do at all") still contradicts
  `trySolveChallenge` being live and pinned by `test_captcha_solving.mjs`. This
  diff resolves it neither way; it stays its own item.
- The ledger row for #71 in `research/2026-09-05-browser-region-audit.md` is
  left for the integrator to flip with the merge SHA — that file moved on
  `origin/cloudflare-backend` while this was built.

## Tests

`extension/tests/test_challenge_is_a_verdict.mjs` (registered in `run_all.mjs`)
drives the real loop through `chrome_mock`: the sift on the v3 page and on a
Turnstile; the audit's page (goal NAMES the host so a wrong BLOCKED parks and
cannot hide behind the read-only retreat) — never asked, no solve, no
navigation, done; the same page with a Turnstile and CLEAR — done, asked once
across three steps, the request never inside the step contract, max_tokens
<= 64, temperature 0, carries the furniture and the page text and the
`[idx] <role> label` structure and never the form value; BLOCKED — read-only
unnamed host retreats to search, named host parks with "prove you're human";
500 then prose — continues; a click on the Turnstile checkbox mapped as an
EMBEDDED WIDGET at index 1000 — refused, no CDP input, hidden from the next
map; BLOCKED with a sitekey — exactly one `/agent/solve-captcha` POST; a
changing page — asked at most 8 times; and a comment-stripped source pin as a
supplement. Updated: `test_captcha_solving.mjs:46` anchor,
`test_login_wall.mjs` (verdict injected where the fixtures assume a challenge;
new checks that with no verdict this file never calls a page a challenge and
reads a challenge-over-login as the login form it structurally is),
`test_walled_source.mjs` (the wall renders a Turnstile frame and the stub
answers BLOCKED). `test_hunt_round3.mjs`'s spelling pin on
`if (stallPrint !== lastFingerprint)` was kept byte-identical.

## Mutation testing (each: backup to an absolute path, mutate, run, restore, `diff -q` byte-identical, run green)

| mutation | red | green after restore |
|---|---|---|
| M1 the brief's: `if (/just a moment\|checking your browser/i.test(title+text)) verdict = CHALLENGE_BLOCKED;` ahead of the compare | `test_challenge_is_a_verdict: 18 failed` — `FAIL: the badge page finishes the errand -> needs_user: tablehold.example.com is asking for a "prove you're human" check`, `FAIL: a CLEAR verdict lets the errand finish -> needs_user ...` | `test_challenge_is_a_verdict: all passed` |
| M2 the model is never asked (`verdict = CHALLENGE_BLOCKED` whenever furniture exists) | `22 failed` — `FAIL: asked exactly once across three steps on one fingerprint -> 0`, `FAIL: a CLEAR verdict lets the errand finish -> needs_user ...` | `all passed` |
| M3 polarity: `UNANSWERED` treated as BLOCKED | `11 failed` — `FAIL: with no verdict the run continues to done -> needs_user ...`, `FAIL: a BLOCKED page with a sitekey is solved once -> 8`; and `test_walled_source: 3 failed` — `FAIL: a walled source nobody named does not end the errand` | both `all passed` |
| M3b polarity: `UNCLEAR` treated as BLOCKED | `4 failed` — `FAIL: ...and never fences -> needs_user`, `FAIL: a run asks at most 8 times -> 1` | `all passed` |
| M4 seatbelt removed | `3 failed` — `FAIL: the click into the challenge frame is refused`, `FAIL: ...and no in-frame click either`, `FAIL: ...the control is hidden from the next map` | `all passed` |
| M5 `solvedPrints.add` removed | `3 failed` — `FAIL: a BLOCKED page with a sitekey is solved once -> 8` | `all passed` |
| M6 sift counts unpainted frames | `5 failed` — `FAIL: the v3 badge page ... renders no furniture`, `FAIL: ...and the question was never asked -> 1` | `all passed` |
| M7 memo ignored | `1 failed` — `FAIL: asked exactly once across three steps on one fingerprint -> 3` | `all passed` |

`test_walled_source.mjs` stays green under M1 and M2 by design: its wall is a
true BLOCKED, so a phrase list or a furniture-only fence adds nothing there.
Under M3 its read-only retreat went red, which is the polarity leg the brief
asked for.

## What was NOT verified (Law 3)

No live browser run. Not observed against a real Turnstile page, a real
hCaptcha, a real v2 checkbox, or a real v3-badge booking page — the `painted`
computation in `readFrame` and the provider URL shapes are from the
providers' documented markup and this file's fixtures, not from a page this
change has mapped. The extension zip was not rebuilt and the version not
bumped (the integrator does). Until a live Turnstile page yields BLOCKED and a
live v3-badge booking page yields zero calls, this is repo-green only.
