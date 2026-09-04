# Anticipy North Star

**This is the first thing every session reads. Everything else flows from this.**

---

## The 4-sentence vision

> Anticipy listens to your day, anticipates what you need, and silently does it for you. From construction worker to CEO, anyone downloads it from anticipy.ai/app and within 120 seconds it knows them, their people, and their tools. It works inside their real Chrome via extension and chrome.debugger (never raw APIs), costs under $200 a year, and follows through on every task across days and weeks without losing the thread. It feels like Donna from Suits, a real human at your side who just gets it done.

## The 3-word loop

**Listen. Anticipate. Act.**

Everything else is implementation detail under one of those three verbs.

---

## Non-negotiables

| Rule | Why |
|---|---|
| Universal user — corporate, construction, unemployed, pensioner, anyone | Not "for tech bros." Real human at your side, for any walk of life. |
| 120-second onboarding magic | If a stranger can't go download-to-working in 2 minutes, the product is dead. |
| Chrome is the action surface, the extension is the bridge, no third-party APIs | Generic action everywhere, scrape what's there, drive what user sees |
| Under $200/user/year all-in cost | LLM tokens + Twilio + Resend + R2 + Vercel + everything |
| Persistent — owns tasks across hours, days, weeks | Never silently gives up. Ralph loop with classified failure recovery. |
| SMS pre-confirm before anything irreversible | Default to draft on no reply within window |
| Apple-feel polish on every surface | Plain human English, real voice TTS, smooth animations |
| Feels like Donna | Anticipates, follows through, charming, never robotic |
| Local-first privacy | Audio + dossier stay on user's Mac. Cloud only for LLM calls and broker relays. |
| No em-dashes anywhere user-visible | Owner's #1 AI-writing tell. Periods, commas, parens only. |

## What we are NOT

- A trivia machine (trivia is a 30-second closer, not the product)
- A corporate productivity tool (we serve everyone)
- A native macOS automator (Chrome is our surface; native is out of scope for v1)
- An open-loop tool (every action is verified, every failure retried, every goal owned)
- A cloud agent (engine runs on user's Mac; broker relays only for SMS/voice/email)

## The 3 demo moments (investor video, in order)

1. **Silent execute** — user says "draft email to my boss about Friday", a Gmail draft appears in their real Gmail, no clicks
2. **Donna effect** — user is in a meeting, someone says "let's regroup Tuesday", within 60 seconds a calendar invite SMS lands asking YES/NO
3. **Trivia in ear** — closer only, 30 seconds, user drops "wait, when did the Roman Empire fall" mid-sentence and the earbud whispers the answer

Order matters. Silent execute and Donna are the product. Trivia is a sweetener at the end.

## Pointers to the rest

- [Architecture](ARCHITECTURE.md) — full system spec
- [Progress log](PROGRESS_LOG.md) — current state per phase with verification proofs
- [Verification protocol](VERIFICATION_PROTOCOL.md) — what counts as DONE
- [Ralph loop](RALPH_LOOP.md) — per-goal retry + persistence + recovery
- [Context handoff](CONTEXT_HANDOFF.md) — first-read after compaction
- [Research](RESEARCH/) — synthesized external research (Chrome APIs, Resend, Ralph loop patterns, A2P, LLM cost)
- [Master handoff](MASTER_HANDOFF.md) — earlier comprehensive snapshot

## How to read this North Star

If you are reading this fresh (after compaction or session start):

1. Read this file top to bottom (you just did)
2. Read CONTEXT_HANDOFF.md next for the current state
3. Read PROGRESS_LOG.md for what's done vs in flight
4. Then pick your next phase from ARCHITECTURE.md
5. Verify every claim in PROGRESS_LOG with the cited command before trusting it (memories can rot)
