# PENDING_DIAGNOSTIC

## TL;DR

The prompt's premise — "95% of intents stuck in `anticipy_intents.status='pending'`" — does not match the current Supabase state. `anticipy_intents` has **0 rows** as of 2026-05-13. There is nothing pending to diagnose.

## What's actually in production state (last 4 days, 2026-05-09 → 2026-05-11)

### `anticipy_intents`: 0 rows
Either was cleared, or no intents have been generated since the table was last queried. Either way, the dispatcher-vs-UX-vs-confirm-fail classification the prompt asks for is N/A.

### `engine_trajectories`: 138 rows (the real production signal)
- 9 success / 129 fail. **6.5% success rate.**
- All 9 successes are read-only fact-finding tasks on Wikipedia or DuckDuckGo. No real action (booking, sending email, ordering) is in the success set.
- Failure distribution by domain:

| domain | runs | wins | rate |
|---|---|---|---|
| en.wikipedia.org | 47 | 6 | 12.8% |
| newtab | 45 | 0 | 0% |
| www.wikipedia.org | 15 | 1 | 6.7% |
| duckduckgo.com | 11 | 1 | 9.1% |
| unknown | 10 | 0 | 0% |
| www.anticipy.ai | 5 | 0 | 0% |
| cats.com | 3 | 1 | 33% |
| www.google.com | 1 | 0 | 0% |
| example.com | 1 | 0 | 0% |

`newtab` (45 runs, 0 wins) = the agent is failing at the *initial navigation* step. The browser opens a new tab but the agent never gets to a real URL. This matches the prior round's finding (`agent.js` v4 with Cerebras-first + 2 s spacing → 429 → 0 steps).

### `engine_cost_log`: 322 rows
- Total spend: ~$0.07 across 4 days
- Providers actually called: **gemini-2.5-flash (218 calls), groq llama-3.3-70b (85 calls), cerebras qwen-3-235b (19 calls)**.
- Providers NOT called in this window: kimi, moonshot, claude, openai, deepgram. The forbidden-provider code paths exist but were dead in the production window.

## What this changes for the build plan

**Phase 5 (the prompt's "fix the 95% pending bug") is mooted.** There is no pending-intents bug in current state — there are no intents at all. The proactive cascade either:
1. Hasn't been invoked recently (most likely — no audio source running).
2. Was reset/cleared at some point in the last 2 days.

**The REAL production problem is the 93% browser-agent failure rate.** That's the work the user actually needs. The prompt's Phase 3 (skills like `book_resy_reservation`) presupposes the executor works on simple tasks. The data says it doesn't yet — even Wikipedia fact-finding fails 87% of the time on `en.wikipedia.org`.

The correct rephrasing of Phase 5 is: "fix the 93% browser-agent trajectory failure." The diagnostic from prior rounds points the finger at:
- Cerebras 30 RPM ceiling baked into `extension/agent.js`
- No call-density throttle that the server can change at runtime
- No effective recovery from the first 429

## Recommendation

Do not pretend to fix a bug that does not exist. The Phase 5 slot in the prompt should be rerouted to "ship a new extension build that fixes the Cerebras burst pattern" — which is the actual blocker, and which has been blocked for 4+ days on Omar reloading the extension at `chrome://extensions`. Surface this to Omar before doing anything else in Phase 5.
