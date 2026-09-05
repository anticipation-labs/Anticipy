# The wall question, measured live — 2026-09-05

Audit #70. `extension/login_wall.js` decided "is this page a login wall?"
with sixteen vocabulary regexes summed against a threshold (WALL = 4) and
parked the errand on the count. It is now ONE question to a model
(`WALL_QUESTION`), asked through the extension's own `/agent/llm` transport,
answered in one of four states, with the loop parking only on an explicit
WALL. The offline suite (`extension/tests/test_wall_is_not_a_word_match.mjs`,
204 checks, 6 mutations) pins everything deterministic. This file is what it
cannot pin: what the model answers.

## What is here

- `fixtures.mjs` — 22 page maps in page_map's exact line format: every page
  the old regex suite pinned (minus three, below), plus the audit's own
  example, each with the errand and the token a person would give.
- `messages.mjs` — prints the exact system/user messages `login_wall.js`
  builds for each fixture, so the leg sends the extension's bytes, never a
  paraphrase.
- `overnight/login_wall_gate.py` — the leg. Three verdicts: PASS (live proxy),
  FAIL (a fixture wrong), UNPROVEN (could not measure over the proxy).

## The scoreboard

```
model      google/gemini-3.1-pro-preview   (ANTICIPY_BROWSER_MODEL)
transport  OpenRouter direct — the QUESTION, not the proxy
fixtures   22   runs each 3   right 66/66
verdict    UNPROVEN — right 3/3 on every fixture, but not over /agent/llm
```

Every positive (7 PASSWORD, 3 SSO, 2 PAYWALL) and every negative (10 NONE)
agreed three times out of three, including the audit's permit form —
"Members only parking permits — $45 per year" beside the form the errand
needs — which the regexes scored 3 + 1 = 4 = WALL and the model reads as
NONE, three times running.

## Finding 1: at the 64-token floor the fence was a decoration

The first live run, with the judge capped the way the other one-token judges
are (asked 16, floored to 64 by `modelFetch`), came back:

```
WRONG  2/3  login_page          want PASSWORD   got (empty) | PASSWORD | PASSWORD
WRONG  0/3  sso_page            want SSO Google got SS | SSO | SSO
WRONG  0/3  paywall             want PAYWALL    got PAY | PAY | PAY
WRONG  0/3  payment_form        want NONE       got (empty) | (empty) | (empty)
WRONG  0/3  unlabelled_password want PASSWORD   got (empty) | (empty) | (empty)
...  15 of 22 fixtures wrong
```

`PAY`, `SS`, `SSO`, empty: the model was cut off mid-token. Gemini 3.1 Pro is
a thinking model, its reasoning counts against `max_tokens`, and 64 was
spent before the visible answer. Every truncated reply is a **no-verdict**,
and a no-verdict never fences (CEILING polarity) — so on exactly the model
the browser runs, this question would have parked nothing, ever, and the
offline suite would have stayed green throughout. That is the failure Law 3
names, caught by the leg Law 3 demands.

Fixed by raising `wallJudge`'s cap to 512 (the answer is still one line at
temperature 0; the budget is for reasoning) and pinning the same number in
the leg and in the offline suite. Re-measured: 66/66.

The other one-token judges in `agent_loop.js` (`inboxConsentJudge`,
`placeConsentJudge`, `recallJudge`, `meantForTheOwner`, `calendarDateJudge`,
`authoredJudge`) ask for 8 tokens and are floored to 64. They were not
measured here. The proxy sends `thinkingLevel: "low"` for Gemini 3 over the
direct Google API, which may leave more of the 64 for the answer than
OpenRouter did — or may not. That is a separate measurement and it is owed.

## Finding 2: the model corrected a fixture

The old `LOGIN_MODAL` fixture — a login dialog over a cart — offered
"Continue as guest", and the regexes still called it a wall. The model
answered NONE three times out of three, which is right: a guest checkout is
a way through that needs nobody's thumb, and parking there would text the
owner about a door he does not need to open. The guest link is removed from
the fixture so it asks the question it means to ("a login modal mid-errand
IS a wall"); with it removed the model answers PASSWORD 3/3.

## What is not in the golden set, and why

Three old fixtures are left out because their old verdict came from the
vocabulary rather than from anything a person would call the truth:

- the signed-in security page with its "Sign out" link removed (the regexes
  called that a wall; a change-password page is not a credentials form);
- a `/login` page offering only "Continue with email" (the door is one click
  further on; either token is defensible);
- every CAPTCHA page (`agent_loop`'s `looksLikeCaptcha` runs before this
  question and owns them).

A golden set carries what is unambiguous, or it measures the labeller.

## What is UNPROVEN, said plainly

The leg could not reach the live proxy. `/agent/llm` requires a paired
agent's own `X-Anticipy-Agent-ID` / `X-Anticipy-Agent-Token`; no such
credential is in `.env.local` on this machine, and at HEAD (`676fbad3`) the
`agents` table is malformed, so the proxy is refusing every agent regardless.
What was measured is the QUESTION — the same bytes, the same model, straight
to the provider. What was not measured is the proxy's own path: its model
allowlist, its `boundedMax`, and for Google models its direct-API call with
`thinkingLevel: "low"`, which is where a 512-token cap could behave
differently from OpenRouter. Until the leg exits 0, Audit #70 is repo-green
and question-green, not Law-3 done.

To close it: set `ANTICIPY_AGENT_ID` and `ANTICIPY_AGENT_TOKEN` to a paired
agent's credentials (with `ANTICIPY_BACKEND_URL`) and run
`python3 overnight/login_wall_gate.py`. It prints which transport it used.
