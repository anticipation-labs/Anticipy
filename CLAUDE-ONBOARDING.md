# CLAUDE CODE — START HERE. READ AND INTERNALIZE BEFORE TOUCHING ANYTHING.

You are taking over Anticipy from Devin. You know nothing about this project yet.
Your first job is NOT to write code. It is to read, research, and internalize —
then explain the whole system back to Omar in plain, simple language (he will say
"talk to me like I'm a two-year-old" — he means it) and wait for his direction.

---

## 1. WHAT ANTICIPY IS

A proactive personal assistant with a name and a warm, human, first-person voice.
She hears Omar's day (phone mic now, a BLE pendant later), remembers it in a real
temporal knowledge graph (not a JSON file, not plain RAG), and acts proactively:

- **Texts him** like a real person (two-way SMS via Twilio, +1 619 658 4447).
- **Drives his own Chrome** through an extension (research, bookings, forms).
- **Closes loops**: follows up, asks when she's missing something, reports honestly.
- **Never acts irreversibly without his yes** — that gate lives in deterministic
  code, never in the model.

End state: consumer product — iPhone app (TestFlight now), hosted multi-user
backend, jewelry-grade BLE pendant. BLE is explicitly out of scope right now.

## 2. THE FEEL (this matters as much as the code)

Her texting personality was built from research on Tomo.ai and Boardy.ai:
short like a friend, contractions, names the specific thing ("the 7:30 at Cactus
Club", not "your reservation"), one question max, matches his energy, no corporate
filler ("Just checking in!" is banned), owns mistakes plainly ("my fault —
scrapping it"). There are NO command words: he can swear, use slang, sarcasm,
half-sentences — the LLM understands like a person and asks a human clarification
only when genuinely unsure. It lives in the `TEXTING_STYLE` block in
`brain/anticipy_core.py`. Protect this feel in everything you build.

## 3. REQUIRED READING, IN ORDER (all in this repo, branch `pendant-system`)

1. `HANDOFF.md` — §0.4 first (current state as of 2026-08-03: security lockdown,
   token flow, what's verified, known issues ranked, how deploys work), then §0.5,
   then the whole original document below it. It is the map of everything.
2. `WHAT-CHANGED-2026-08-02.md` — your own previous overnight session, in plain
   language (yes, Claude Code worked on this before; the transcript of that whole
   session is `HANDOFF-TRANSCRIPT.md`).
3. `AUDIT-2026-07-21.md` and `PROOF_REPORT.md` — the audit systems and what has
   actually been PROVEN vs. merely written.
4. The proof/test harness: `proof/verify_all.py` (the production standing check),
   `proof/test_group_choice.py`, `proof/test_sms_flows.py`, `proof/test_anticipy.py`,
   `proof/test_says_when_it_cannot_run.py`, `proof/audit_conversation.py` (audits
   every text she ever sent for repeats/spam/unanswered messages).
5. The core code, until you can explain it without looking: `brain/anticipy_core.py`
   (triage, risk gate, memory extraction), `brain/conversation.py` (LLM-first SMS
   understanding, deterministic queue flips), `brain/worker.py` (production loop),
   `brain/pb.py` (ALL PocketBase access — never bypass it), `brain/memory.py`
   (temporal graph), `extension/background.js` + `extension/agent_loop.js` (browser
   arm), `backend/pb_hooks/` (guard.pb.js = the security lock, sms.pb.js = inbound
   SMS, agent_key.pb.js = how paired devices get their keys),
   `app/ios/Anticipy/` (the iPhone app).

## 4. HOW WE WORK (Omar's rules — these ARE the spec)

- **Do all of it, end to end, with proof.** He has been burned by agents doing 1 of
  10 things asked. Never claim done from source code alone — run it, show output.
- **Research deeply before building.** Primary sources, not skimming.
- **Two-year-old-proof.** Both the product (a first-timer must never get stuck) and
  your explanations to him (plain language, no jargon, step-by-step).
- **Never break production.** Test locally first (local PocketBase lives at
  `backend/pocketbase`, port 8090); deploy only after the gates pass; verify worker
  logs after every deploy. A guard-hook mistake once took production down — read
  the commit history's lessons before touching pb_hooks.
- **Safety gates live in code, not the model:** nothing irreversible without his
  confirmed yes; she never claims an action happened unless the job status proves
  it; identical texts are suppressed in code.
- **Secrets never in the repo.** They live in Railway variables and the Mac
  keychain. Never print or commit the service token, Twilio, OpenRouter, or Apple
  keys.
- **Everything on branch `pendant-system`, always pushed.** Before handing back:
  run every test gate, push every commit, and update HANDOFF.md §0.4 with what you
  did — the next agent (Devin or you) starts from that section.

## 5. THE SYSTEM IN ONE PARAGRAPH

Omar texts the Twilio number → PocketBase hook (`sms.pb.js`) stores an event → the
Railway **worker** (brain) picks it up, hands the raw text to the LLM
(gemini-2.5-flash via OpenRouter) with the thread + every pending job + memory →
the LLM returns intent + reply → **deterministic code** applies the queue change
(release/cancel/modify) and Twilio sends her reply. Browser tasks become `jobs`
rows that his paired Chrome **extension** claims and executes with its own LLM
loop, reporting honest results back. The **iPhone app** does mic listening
(transcripts → same brain), pairing (6-digit codes), and the feed. Everything
talks to one PocketBase **backend** on Railway, and since 2026-08-03 every data
API call requires the `X-Anticipy-Token` service token (see HANDOFF.md §0.4 for
exactly how each client gets it).

## 6. YOUR FIRST SESSION, IN ORDER

1. `git pull` on `pendant-system`. Read everything in §3 above. Do not skip.
2. Run the audits and gates yourself so you trust them: the four `proof/test_*.py`
   suites locally, then `railway run --service worker python3 proof/verify_all.py
   --no-browser` against production.
3. Explain the whole system back to Omar in plain language — what exists, what is
   proven, what is broken, what you'd do first — and WAIT for his direction.
4. Known open items, ranked (details in HANDOFF.md §0.4): iOS build 18 (token on
   reads — code is committed, just needs building/uploading from this Mac), status
   blindness (she says "nothing pending" while jobs are queued/running),
   phone-number onboarding, extension Web Store packaging, pair-code rate limiting,
   physical-device proofs (Listen on the real iPhone; one real completed booking).
