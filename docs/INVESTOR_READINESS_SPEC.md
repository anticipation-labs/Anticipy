# Anticipy Engine — Investor-Readiness Spec

Hand it to an investor. They press one button. They use it themselves. It does not screw up. They walk away wanting in.

## Bar

- **Autonomous.** No babysitting. No prompting "try this prompt." No live debugging.
- **Works on anything.** No allowlist of supported sites. Open web. Generalizes.
- **No pre-programming.** No regex, no keyword tables, no hand-coded site logic.
- **Doesn't break.** Graceful failure on every layer. Never shows JSON / API errors / model names. Never hangs longer than the budget.
- **Scales.** Multi-user safe. Per-user state isolated. No cross-user leakage.
- **Performance does not drop** when capabilities are added.

## The two agents

### A. Proactive agent

What it does: listens to the user's voice, decides when to act, executes silently if reversible+confident, asks if irreversible, refuses if Donna would push back, logs otherwise.

User-visible surface:
- Silence by default
- "I'm doing this right now: X" — when EXECUTE
- "Confirm before I do this: X?" — when ASK (channel matches urgency)
- "You're upset, sleep on it" — when REFUSE
- "Things I noticed" feed — for LOG entries

Test the way it has to be tested: stream long random synthetic conversations into it, judge with a different LLM that wasn't told the answer. The harness exists at `engine/app/proactive/eval/harness.py` — 15 categories, LLM-generated transcripts, LLM-as-judge.

**Pass bar:**
- Correctness ≥85%
- False positives (acted when shouldn't have) <10%
- False negatives (silent when shouldn't have) <15%
- Channel-appropriate ≥80%
- Latency p95 <5s for actionable chunks, <1s for skip
- Total cost <$0.001 per actionable utterance

### B. Browser agent

What Omar said it must do:
- Navigate existing systems (✓ today via Browser Use)
- Navigate its own systems
- Write its own code in its own sandbox
- Stay signed in, log itself in
- Capture everything mid-flow
- Write Google Docs, work on canvases
- Better, faster, quicker than a human at all of this

Reality today:
- Generic open-web navigation: yes
- Encrypted per-user cookies (Fernet): yes
- Mid-flow screenshot capture: per-step, but not exposed
- Code sandbox: not built
- Canvas apps (Docs/Sheets/Figma): noted as a limitation
- "Better than human": not demonstrated

**Pass bar:**
- 9/10 on `engine/test_real.py` real-world tasks
- Step-by-step capture available in task history (screenshots + actions taken)
- Per-user cookies persist across tasks (login once, agent stays signed in)
- Canvas apps: at least drafts via Docs API (export from Markdown) rather than DOM-poking
- Code sandbox: subprocess-isolated Python eval with timeouts and resource limits
- Never shows raw error text, JSON, or "model X failed" to the user

## What to build / wire in this session

1. Run proactive eval at scale (live LLMs). Real correctness numbers.
2. Wire `/ws/proactive` WebSocket route → phone clients can stream chunks, receive decisions.
3. Browser agent: expose mid-flow capture (screenshots + step log) in task history.
4. Browser agent: code sandbox subprocess with stdlib-only Python, timeout, no network.
5. Verify graceful failure paths everywhere — no leaked tracebacks, no provider names.
6. Smoke-test the whole thing end-to-end as if I were an investor.

## What is explicitly NOT in scope right now

- Native phone app (Swift/Kotlin) — eventual.
- Replacing Browser Use — works fine.
- Canvas-app full automation (Figma/Sheets via DOM) — partial via Docs API only.
- Adding model providers beyond Gemini/Groq/Kimi.

## Test discipline

- No hand-picked fixtures.
- LLM-generated scenarios. Different LLM as judge. Judge never told the right answer.
- Numbers reported, not vibes. If it hits the pass bar, ship. If not, iterate the prompts (not the rules).
