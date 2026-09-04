# Anticipy roadmap

Source: synthesized from the 7 planning docs in this folder, the existing-code map, and the 12-competitor scan. Drafted 2026-05-29. Reviewed by Omar: pending.

This is a "build this in this order" doc. Not a wish list. Every item has a leverage rationale, a dependency, and an estimated effort. The order is chosen so each item unlocks the next.

## The "do these 5 first" set

These are the highest-leverage items. If we ship only these in the next 2-3 weeks, the product is genuinely usable for a Donna-style daily flow.

### 1. Fix `_cdp_navigate` tab hijack (P0, 0.5 day)

`scripts/v7/anticipy_bridge_fallback_cdp.py:528-554` reuses an existing tab when the URL prefix matches. So when the user is reading their own Gmail and the agent calls `navigate(mail.google.com/...)`, the agent takes over the user's tab. This is a real product bug that will burn early users immediately. Fix: always create a new tab in the Anticipy tab group, never in-place reuse on the user's tabs.

Unblocks: every cross-app flow, because today we can't safely act in any app the user might also be looking at.

### 2. Engine stability + scale-bug paths (P0, 1 day)

Three things bundled:

- One canonical engine on port 8731. The launchd race (`com.anticipy.human-ready-loop` and `com.anticipy.finish-overnight` both spawn source uvicorn; packaged `Anticipy.app` spawns its sidecar; they fight) gets resolved by either booting out the two loops permanently OR pointing them at the packaged binary instead of pyenv source.
- Remove `/Users/omarebrahim/.anticipy/chrome-real-clone`, `/tmp/anticipy-omar-flow-home.EsPus7`, and `omarkebrahim+anticipy-{dana,priya,maya}@gmail.com` from shipped code paths. Move to env vars defaulting to user-agnostic locations. Per `MAP.md` these are in `com.anticipy.chrome.plist`, the acceptance harness lines 200/960/1017, and several test recipients.
- Resolve the `engine/app/anticipy/handoff` ghost import at `server.py:73`. Either the file ships (build the module) or the import goes away (delete the try/except and the lines that depend on it). The web side at `src/lib/handoff-token-store.ts` is the real handoff; the engine-side import is dead.

Unblocks: any reliable measurement. Today's CHECK 16 = 17/30 score is partly because we measure whichever engine happened to be on port 8731 that minute.

### 3. Planner latency + reliability (P0, 1 day, requires unfreezing `engine/app/anticipy/platform_adapter.py`)

Per the earlier agent latency audit: `platform_adapter.py:205` has `timeout_s=90`, `platform_adapter.py:285` has backoff cascade `[1, 2, 4, 8]` (15s), `server.py:5561` has a 2x outer retry, and `platform_adapter.py:343-348` recursively re-calls with doubled tokens on empty content. Worst-case is 211 seconds per planner call. Empty-mode return on half the resolvable scenarios is the dominant CHECK 16 failure (10 of 20). Fix: cut `timeout_s` to 15, cascade to `[0.5, 1.0]`, drop the outer retry, drop the recursive doubling, add OpenRouter `cache_control: ephemeral` on the `_COMPOSE_SYS` system message and profile JSON (both are stable across calls).

This is in a frozen path. Omar explicitly authorized unfreezing in conversation 2026-05-29 ("Who froze it in ice? You can just unfreeze it. Just don't break it.") The verifier-first prep already lives at `verifier/lib/` so we have proposal-script scaffolding for this change.

Projected lift: CHECK 16 from 17/30 to 25-27/30, planner p50 from 5s to 1s. Reliability becomes the floor not the ceiling.

### 4. Five-minute cold-start MVP (P0, 3 days)

From cold-start OPTIONS.md combination (E + slice-of-A): a single voice question via Twilio ("In one sentence, what do you do for work and who do you do it with?"), match against the `roles/` template library, simultaneously read the user's Gmail signature via CDP `Runtime.evaluate` on `mail.google.com/mail/u/0/#settings/general`, and walk the next 7 days of `calendar.google.com` for attendees. Writes everything to the active dossier at `~/.anticipy/v7/dossiers/<acct>/dossier.json` via the existing `dossier_active_loader.py` seam, marked with provenance="role_prior" so observations overwrite.

The bar: a new user installs, takes a 90-second call, and within 5 minutes the agent can resolve "remind me to prep for the Sarah meeting tomorrow" because Sarah is the only Sarah on the user's calendar this week and the user is a "founder" so the agent knows to draft prep notes into the right Google Doc.

Unblocks: literally any day-0 use. Today the dossier is empty for new users; they have to onboard for weeks.

### 5. Trivia-fire end-to-end (P1, 4 days)

The killer demo. 30-second couch scene that lands on the X feed and converts pre-orders. Implementation per `planning/07-trivia-fire/DESIGN.md`: 4-feature trigger classifier in the existing engine (lexical openers + question prosody + group context + recent-answer absence), local 120MB Wikidata SQLite cache for the common 35-45% of questions, Perplexity Sonar Small Online via the website broker for the rest, direct local BLE + APNs surface bypass. Pendant haptic ack at t=0, earbud TTS, phone notification with the answer as title for lock-screen glance.

Why this first and not the "send Maya the deck" path: trivia-fire is 80% of the wow factor, 20% of the engineering. Sending an email is something the user understands they could do themselves; getting a fact whispered into their ear feels like magic. We need one shareable magic moment.

Unblocks: marketing surface area. Also forces the BLE pendant interface even though no pendant exists yet (we'll simulate from the Mac's bluetooth output to AirPods).

## The "do these 10 next" set

Once 1-5 are shipped, these expand the product from "one magic moment + one common flow" to "real daily usage."

### 6. Implicit-object fastpath (0.5 day)

The cold-start audit agent's Addition 3 from earlier: add `_fastpath_implicit_object_resolve` in `engine/app/product/server.py` after line 5464, wired in `_compose_task_from_memory` around line 5535. Pattern: when trigger has no name and no pronoun but contains "the deck" / "those notes" / "the doc" / "the runbook" etc., AND exactly one dossier person appears in last 1-2 context windows, build the same `mode=act` plan. Lifts CHECK 16 by 2-3 more scenarios.

### 7. Reversal log + 30 surface recipes (1 week)

From confidence-ladder DESIGN. Every silent action must produce a `ReversalLog` JSONL entry at `~/.anticipy/v7/memory/<acct>/<dev>/reversal_log.jsonl` with a revert recipe (delete-draft, cancel-booking, restore-calendar-snapshot, etc.). If no recipe exists, the action is not eligible for silent. First 30 recipes: Gmail draft delete, Calendar event delete, Reminders complete-undo, OpenTable cancel, Notes delete-paragraph, etc. Without this, silent mode is too dangerous to enable.

### 8. PersonClassifier (recipient_class for calibration) (3 days)

The confidence-ladder calibration scores by `(surface, recipient_class, verb)`. Today `person_resolver.py` returns identity but not class (coworker / client / family / vendor / unknown). Build `engine/app/product/person_classifier.py` that joins dossier signals (email domain, frequency of contact, calendar relationship, "spouse" / "boss" type labels from onboarding). Unblocks per-user calibration.

### 9. Per-app config registry (3 days)

From cross-app-auth DESIGN. `engine/config/auth_profiles/<app>.json` per supported SaaS, each declaring: login URL, MFA shape, session refresh interval, tab-group color, allowed actions, recovery URLs. Lets us scale to "Anticipy supports app X" as a config change, not a code change. First 10 apps: Gmail, Calendar, Drive, OpenTable, Salesforce, Canvas, Notion, Slack, Linear, Asana.

### 10. Twilio MFA `<Gather speech>` for 6-digit codes (1 day)

`engine/app/product/login_wall_responder.py` today only knows "type your password." Add the Twilio Programmable Voice `<Gather speech>` flow: when a 6-digit MFA challenge is detected on a logged-in app, place outbound voice call to user, ask them to read the code, ASR the response, type it into the page. Closes the MFA loop without storing TOTP seeds (which we keep as an opt-in advanced setting).

### 11. Tab-ownership tagging (1 day)

Bridge tracks which tabs are Anticipy-owned via the existing "Anticipy" tab group in `extension_v4/background.js:504-517`. Every CDP action filters tab list to owned-only. No more risk of typing into the user's tabs. Lives alongside item 1.

### 12. Real DeliveryRoutes wiring (2 days)

The `engine/app/proactive/notifier.py` cascade has `DeliveryRoutes.push`, `.sms`, `.voice` slots that are empty in prod wiring. Wire: APNs for push (need anticipy.ai server-side certificate), Twilio for SMS + voice (Twilio account already exists), local Mac `osascript` for notifications during desktop sessions. Without this, every "notify-after" decision is a tree falling in the forest.

### 13. Calendar busy-window detector (2 days)

The `engine/app/proactive_day/timing.py` already understands "after the meeting" against `world.calendar`. Build the live adapter: read user's Google Calendar via CDP every 5 min, expose `is_busy(now)`, `next_free_window(min_duration)`. Quietness UX depends on this.

### 14. Port silent_queue + debounce merging to proactive/notifier (1 day)

`engine/app/proactive_day/comms.py` has `silent_queue` and `DEBOUNCE_S` window for merging items into one composed proposal. The newer `engine/app/proactive/notifier.py` doesn't have this yet. Port it forward so the between-meetings digest is one notification, not nine.

### 15. Stranger-flow proof on Omar's Mac (1 day)

Per Omar's directive 2026-05-29: stop bogged down on "clean machine" requirement. Use Omar's actual Mac. Create a brand-new macOS user account, download fresh DMG from anticipy.ai, click through onboarding, prove the agent drafts a real email within 5 minutes of install. This is the proof that the gates were trying to measure. Until this works, we have nothing.

## The "everything else" backlog

Ordered by leverage. Not the next 30 days, but the next 90.

### 16. Authenticator-app TOTP opt-in (1 day)
### 17. Per-org Salesforce/Epic subdomain matching (2 days)
### 18. Cross-device dossier merge protocol (1 week, needs the website broker side)
### 19. NopeCHA bundled into installer (0.5 day)
### 20. Bot-detection refusal list explicit (0.5 day)
### 21. First-week dial (action-count-based) implementation (2 days)
### 22. Cross-class transaction safety (the partial-failure reversal flow) (3 days)
### 23. Apple Critical Alerts entitlement (App Review + 1 week wall)
### 24. The 4 dead memory implementations: pick one and migrate (1 week, large surface)
### 25. The `proactive_engine.py` → `proactive/` cleanup (move dead files to `_archive/`) (1 day)
### 26. The handoff module ghost (build or delete) (0.5 day, depends on #2)
### 27. Native EHR path for Epic Hyperdrive (out of scope V1, plan for V2)
### 28. Voice-anchor binding for non-wearer speakers (2 weeks, research)
### 29. Per-job-change privacy reset (1 week)
### 30. Pendant hardware integration (someone else's problem, plan only)

## What to NOT do

Pulled from competitor-landscape anti-patterns and our own past misfires:

- No more 18-CHECK gate-chasing as the primary planning unit. The gates measured proxies; we shipped DMGs without ever running the stranger flow.
- No "Friend pendant" AI-companion parasocial chat. We do tasks, not relationships.
- No always-on capture without salience filter. The pendant only commits a transcript to memory when it's relevant. (Granola pattern, not Limitless.)
- No service APIs. Browser nav only. (Omar rule, also gives us the privacy moat.)
- No subscription-required core functionality. Pre-order is one-time + first year service. (Omar pricing rule.)
- No headless / scripted Chrome that gets DataDome-blocked. Use the user's real Chrome.
- No marketing the device as a friend or replacement smartphone. Both Humane and Rabbit died on that hill.
- No "build for stranger on clean machine." Per Omar 2026-05-29: nobody's machine is fresh and clean, prove it on the actual user's actual Mac.

## Open decisions for Omar

Things only Omar can call:

1. **Frozen-paths rule.** Confirmed unfrozen on 2026-05-29 ("you can just unfreeze it"). Are `engine/app/action_engine/`, `engine/app/proactive_day/`, `verifier/` also unfrozen, or only `anticipy/`?
2. **Tab hijack fix breaks Z-001.** Z-001 currently passes because the URL-prefix reuse happens to land on the same tab the harness expects. Fixing #1 means Z-001 will fail until we update the harness. OK?
3. **Trivia-fire LLM source.** Perplexity Sonar Small Online ($0.20 per 1k searches estimated) for the 60% miss path. OpenRouter as backup. Acceptable cost line?
4. **Apple Critical Alerts.** Requires App Store approval. Worth the time, or do we accept that money-irreversible + <2-min deadline + unreachable = best-effort?
5. **Cross-device dossier sync.** Server-side encrypted blob in Supabase, or end-to-end via the user's iCloud Drive? Privacy posture choice.
6. **Pendant hardware partner.** Out of our scope, but the BLE protocol design needs a fixed party on the other end. Who is building the pendant?

## Working agreement going forward

Per Omar 2026-05-29:

- No more "all green" claims without a real stranger-flow proof.
- Frozen-paths rule is "don't break it" not "don't touch it."
- Agents fan out for both diagnosis AND drafting. The "read-only" subagent rule from finish_loop_prompt.md is rescinded for planning work.
- Conversation > gate-chasing. Plan first in this folder, code second.
- 16-agent parallel work means agents writing into non-overlapping files concurrently. Today's session proved this works for planning. Next experiment: parallel CODE edits with merge-time review.

## Roadmap-to-shipped tracking

When an item gets built, mark it here with the commit and the date.

| # | Item | Status | Commit | Date |
|---|---|---|---|---|
| 1 | Fix _cdp_navigate tab hijack | pending | | |
| 2 | Engine stability + scale-bug paths | pending | | |
| 3 | Planner latency + reliability | pending | | |
| 4 | Five-minute cold-start MVP | pending | | |
| 5 | Trivia-fire end-to-end | pending | | |
