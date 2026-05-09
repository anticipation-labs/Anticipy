# Anticipy Cop-Outs — committed not to perform

Cop-outs are short-cuts that make a failing test green or a half-finished feature look done, without actually moving the product. They feel productive in the moment and are worthless. Naming them is the forcing function: a cop-out written down is a cop-out that cannot be unconsciously performed.

## From the spec (immutable)

1. **No synthetic-prompt testing of the proactive engine.** The engine's input is raw audio. If a test starts from a clean structured prompt I wrote, I tested the downstream API call, not the engine.

2. **No unit-only testing called "done."** Engine alone passing and browser alone passing does not equal the product working. The product is the chain. Every fix is validated against the full chain end-to-end on real audio + real sites before declaring done.

3. **No hardcoding under pressure.** When 5 tests fail, the answer is not `if site == "opentable.com"` with hardcoded selectors. If the same fix would have to be written 10 times for 10 sites, the fix is wrong. There is no scenario where hardcoding a site-specific branch is acceptable.

4. **No fake training data as substitute for real data.** Synthetic data is acceptable for cold-start bootstrapping a model. It is not acceptable as the eval set. Eval is real audio of real conversations on real microphones and real outcomes on real sites.

5. **No "the code looks right" as a pass condition.** Pass condition is "I ran the end-to-end and observed the outcome on the actual site / actual reminder / actual email sent."

6. **No silent half-completion.** Browser agent gets halfway through a task and returns success because the page loaded? That's a fail dressed as a success. The agent verifies the actual end-state — confirmation page contains expected text, email shows in sent folder, calendar event appears in wearer's calendar, reservation confirmation lands in inbox.

7. **No codespace-only deployment.** If it only runs because /workspaces/something exists, I built the wrong thing. The system runs on a clean macOS user machine with the dependencies installed. Test that.

## Anticipy-specific extensions (equal weight)

8. **No "verified by reading the agent's final message".** Browser Use says "done" on failure all the time. End-state verification = fetch a real artifact (final page text/screenshot, sent-folder row, calendar event present, reservation in wearer's account) and assert specific evidence — never trust the agent's self-report.

9. **No regex / keyword extraction of intent fields.** Brand names, dates, party sizes, locations — all model-extracted with confidence scores. Never `re.search(r'(\d+)\s*(?:people|ppl)')`. Never an ALLOWLIST of restaurants. The model handles ambiguity.

10. **No site-specific branches in prompts.** "If user mentions Carbone, navigate to OpenTable" is hardcoding wearing different clothes. Prompts describe categories of behavior ("for any restaurant booking…"), never named instances.

11. **No skipping the cascade gates (L0..L6) when they're inconvenient.** If L0/L5/L6 keep dropping a test scenario, that's the system working — debug whether the scenario is really actionable or whether the gate is overstrict. Never `if test_mode: skip_gate`.

12. **No "passes when the LLM happens to return happy JSON" as a real pass.** A green run today, red tomorrow because of provider drift, is a flaky pass. Real pass = same input, deterministic verification, repeatable across ≥3 consecutive runs.

13. **No moving the goalposts mid-fix.** If a test was passing on hostile audio and now fails after my "improvement," I revert or actually fix the regression. I do not tune the test threshold to pass again.

14. **No silently removing a scenario from the eval set when it consistently fails.** A scenario that fails 10 times in a row is a signal, not noise. It stays. The fix is the model/pipeline, not the eval set.

15. **No technical leakage in wearer-facing surface.** Wearer-facing strings are plain-English nudges, not status updates. "I noticed you mentioned dinner with Sarah Friday — Carbone at 7? I'll grab it if you nod." NOT "Booking dinner_reservation, status=pending." NOT "Action book_reservation_v2 dispatched."

16. **No deferring to "the wearer can verify on their machine" when I can verify from here.** Whatever I can run from this codespace — LLM-only proactive eval, integration test against mocked browser, end-state verification logic against fixtures, the full chain except the live-internet last mile — I run, log, and commit. I only push real-internet verification to the wearer's machine when it physically requires their browser session or microphone.

## Anticipy-specific extensions (Round 2 — added 2026-05-09 after the user called out cop-outs the previous round committed)

17. **Logging-is-the-cop-out.** Writing a problem into AUTONOMY_LOG.md and continuing is the same as not fixing it. Example: leaving `engine/app/agent.py:577-582` hardcoded to `/home/codespace/...` paths with a "flagged for next pass" note. The note is the cop-out. If I see a problem, I fix it before writing the next file.

18. **Provider exhaustion as an excuse.** "All four providers throttled simultaneously, results are throttle-corrupted" is not a valid completion state. A real product has retry-with-backoff, queue serialization, per-provider rate-aware scheduling, degraded-mode responses, and failover that doesn't cascade-fail. If the eval can't run because providers are throttled, fix the throttle handling; don't blame the providers.

19. **Localhost-as-access-port.** The previous "Python access port" connects to `http://localhost:8000` which means it drives whatever engine is sitting on the same host as the test. That's not a wearer's client — that's a localhost loopback. The real access port has to drive the engine from the wearer's actual machine, which means either tunneling, a wearer-side daemon that connects out, or running the agent locally and the brain remotely. Pick one and build it.

20. **Stub testing dressed as real testing.** Unit tests on functions I stubbed are not "the chain works." Mocked browsers in integration tests are not "the agent works." End-to-end means raw audio → real action on a real site → observable evidence on the user's actual account state. Anything else is theater.

21. **Code-looks-right as a pass condition.** Reading the code and saying "this should work" is not a test result. The only pass condition is observable real-world outcome: email landed in the user's sent folder, reservation visible in the user's restaurant account, calendar event present in their actual calendar.

22. **Synthetic prompt testing of the proactive engine.** Feeding the engine a structured intent JSON and watching it route is not testing the engine — it's testing the downstream API. The engine's job is to extract intent from messy ambient audio. If a test starts after extraction, the extraction is untested.

23. **The "next session will fix it" deferral.** Saying "I'll fix this next session" is what the user is calling out as the seven-week-cop-out pattern. This session ends with the bar met OR with concrete real-world evidence that's still missing AND a specific action that does not require human time.

24. **The "environmental constraint" excuse.** "RAM is too low," "Xvfb permission error," "this codespace can't launch Chrome" — if the constraint is real, the constraint is mine to solve, not to log. HEADLESS_BROWSER=1 path exists. Fresh display number. Tunneling out to the wearer's actual machine. The constraint is not an exit.

25. **Spawning a separate browser binary in production.** The wearer's browser is the wearer's actual Chrome. The Anticipy extension runs there, with their cookies, their profile, their residential IP. No Patchright/Playwright/Chromium subprocess in the production action path. Patchright is acceptable only for test fixtures and synthetic harnesses, never for real wearer execution. The bridge publishes Decisions to Supabase Realtime; the extension picks them up and clicks through in the wearer's browser.

26. **"Tested with zero tokens" is a tell.** I told Omar I'd "tested" the agent-team routes while I had only run TypeScript compile + JS parse + unit tests. Static checks find syntax errors. They do not find: model-name typos, "this model requires temperature=1" rejections, reasoning-content-eats-tokens budget surprises, HTTP CORS issues, latency. **Real test = an actual call to the actual upstream service.** If I want to claim "this works," I have to spend the tokens (small ones — a single ping costs $0.001 — but the real call). Static checks are necessary, not sufficient. (Discovered when the user pushed back: K2.6 actually requires temp=1 AND burns 150+ output tokens on reasoning before content; the static checks would never have caught either.)

27. **Picking the marketing-headline model over the engineering-fit model.** I picked Kimi K2.6 because the headline benchmarks were better. Real test showed K2.6 burns reasoning-token-overhead that nukes the per-task budget; K2.5 has shorter reasoning and is faster; moonshot-v1-128k has NO reasoning overhead and is 18x faster for the tight Executor loop. The right answer is **per-role model selection**: K2.5 for the strategic agents (Planner / Critic / Reflector) where reasoning quality matters, moonshot-v1-128k for the high-frequency Executor + Verifier where speed and per-call cost matter. I knew this pattern in the abstract; I didn't internalize it until the real call surfaced the latency.

28. **Local-pass-prod-fail parity gap.** Tested the Planner locally: 19.5s, returned a clean plan. Pushed to Vercel, smoke-tested in production: aborted at 60.4s — Vercel's serverless function deadline. Identical code, different deadline. Local testing has NO platform timeout; production does. **Real-call testing means PRODUCTION-call testing**, not localhost. The 19.5s "this works" claim was an environmental artifact — the model's actual latency was always racing the platform deadline, and only running in the actual production environment surfaced it. (Fix: switch the default model to moonshot-v1-128k everywhere — 1-2s latency, fits any reasonable deadline.)

29. **"This provider has a free trial" without verifying.** Told the user "Voyage gives $50 free trial" based on assumption — the dashboard showed Balance $0.00 and "Add payment details" required. There was no automatic trial. I sent the user to set up an account thinking it'd self-fund. Equivalent: assuming Gemini text-embedding-004 was the right model name (it 404s; the live ones are gemini-embedding-001/-2). Provider feature claims need actual API verification, not docs-from-memory. (Fix: the embedding fallback now tries Gemini-embedding-001 → Voyage → fail-degraded; the planner runs without RAG examples when both are out instead of crashing.)

## Re-read at start of every working pass.
