> ⚠️ **SUPERSEDED — 2026-07-02.** Historical document. The living truth is **`CANON/00_START_HERE.md`**
> (+ `MISSION_LOCK.md` for live mission status). Do not follow this file's read-order, done-definition,
> or status claims. Indexed with context in `CANON/99_SUPERSEDED_INDEX.md`.

# ANTICIPY — THE PLAN TO FULLY FINISHED

> Grounded in a 10-subsystem audit of the **live code + running engine** (2026-06-24), each finding
> backed by `file:line` evidence or a live probe. Pairs with `ANTICIPY_SOURCE_OF_TRUTH.md` — the
> definition of done is **§4** there; this is the path to it. Rules: **verify by running, commit each
> win, and the exit gate of every phase is the INTEGRATED loop — not a piece in isolation (§4).**

---

## THE ONE-PARAGRAPH TRUTH (where we actually are)

The **brain** (infers act/ask/silent, never acts on a vent, money is a hard stop), **memory**,
the **safety floor** (money/vent/never-fake, code-enforced in both browser arms, suite 107/0, a
zero-breach adversarial corpus), and **per-user accounts** (Supabase auth + data isolation, proven
A≠B on disk) are **genuinely real**. But the loop today is **listen → infer → remember**, NOT
**listen → infer → act → close** — because the *act* half is hollow in three specific, pinned ways:

1. **The app fakes success.** The Board's Confirm/Deny POSTs `card.id` where the engine keys on
   `card.execution.ask_id`, so resolve returns `{"resolved":false}` — and the UI ignores that and
   plays the gold checkmark anyway. The card flies away; nothing executed. *(a literal §4 "never fake
   done" violation — web/app.js:441,471)*
2. **The self-verify judge is dead.** `/agent/judge` returns `false` on *correct* answers (scored
   0/4 live) because it shares the 96-token `AGENT_MAX_TOKENS` cap and its verdict JSON gets
   truncated → defaults to false. The arm that's supposed to certify "done" currently can't.
   *(webvoyager.py:2365-2368)*
3. **The YES→act path drives the wrong hand.** `_run_browser_and_confirm` runs a **throwaway,
   logged-out Chromium that refuses to act in your real Chrome** — while the fully-built connected
   extension (your real, logged-in hand: CDP click/type/navigate) is **never called from the owner
   path.** So it can read public pages but cannot operate your Gmail/Amazon/calendar. *(control_core.py
   :1200-1212, browser_use_link.py:303; the real hand `browser_link`/`WebVoyagerAgent` sits unused)*

Fix those three and the loop closes for real. Then deepen onboarding, turn voice on, make the hands
per-user in the cloud, and run the multi-day owner test — that last one **is** §4.

---

## HONEST SCORECARD (grounded in the audit)

| Subsystem | Real (proven) | The gap to §4 |
|---|---|---|
| **Brain / inference** | money hard-stop (3 layers), vents never acted, sends confirm-first, warm copy | sends confirm an *intention* not a real draft; splitter drops a task when a vent shares the line |
| **Memory** | 4 isolated drawers, real embeddings, hybrid recall, honest scrape→memory | dedup is read-view only → brain's inject path sees the same loop 11× and vents leak in |
| **Browser agent (SPINE)** | real multi-step operate loop, trusted CDP actions, code-enforced money/login stops, cart read-back | judge dead (0/4); extension `read_page` is first-screen-only; no "open email→read body" recipe |
| **Onboarding** | consent gate, honest login detection, graded dossier→memory, list-row extraction | only reads list rows (never opens items / follows graph); **no scrape↔call loop**; no autonomy/money-rule/do-not-touch capture; clarify is a disconnected island |
| **Voice** | full two-way `/cr` ConversationRelay, ElevenLabs, warm brain, inbound SMS — all dev-proven (7/7) | **OFF**: mock mode, no public wss URL, localhost-only, no inbound-call webhook |
| **Proactive** | self-fires every 30s, real act/ask/silent decider, autonomy dial + trust ledger | vents reach `/pending` as asks on the mock path; dead stub `proactive/engine.py` coexists |
| **Frontend / app** | Board built + wired (ingest, dial, swipe deck), flashing bug fixed | **resolve posts wrong id + fakes success**; Listen button is a stub; no receipt surface |
| **Cloud / per-user** | Supabase auth + data isolation REAL, proven A≠B over real HTTP | cloud has **no browser driver**; extension link is owner-global with no user identity → **per-user hands impossible as wired**; no persistent volume (redeploy wipes data) |
| **Integration (§4 heart)** | one shared brain+memory+judge across infer/verify/remember; floors thread through every branch | the centerpiece YES→act funnels into the logged-out hand; brain→hand drops structured args & re-derives the task |
| **Safety** | money/vent/never-fake **code-enforced** both arms; 107/0; zero-breach corpus — strongest subsystem | `is_vent` misses a directed threat in isolation; regex/locale-fragile; no amount tier; judge not yet on the voice/API arm |

---

## THE PLAN (ordered; each phase ends on a PROVABLE, integrated gate)

### Phase 0 — Stop faking, un-break the verifier (pure code, no Omar, highest leverage)
The loop is currently *lying*; make it honest first.
- **Frontend resolve:** send `card.execution.ask_id || card.id`, and **check `res.resolved`** — spring the card back on false instead of faking the checkmark. *(web/app.js:441,471)*
- **Revive the judge:** give it ~256 tokens (not the 96 cap), harden the empty/unparseable-JSON path (retry text-mode before defaulting false), pass the agent's `final_shot` in. *(webvoyager.py:2365-2368)*
- **Fix the splitter:** disaggregate multi-action lines *before* the vent `force_ask` merge, so "call the dentist **and** send Priya the deck" become two cards. *(control_core.py ~2119)*
- **Memory dedup:** content-deterministic open-loop ids (`_owner_card_dedupe_key`, not the random uuid), dedup in the **inject** path, and run the vent gate on the owner-card write. *(control_core.py:2484, inject.py:64)*
- **Exit gate (integrated):** re-run a real messy-day battery → every task survives, Confirm actually resolves (curl shows the card gone from `waiting`), the judge scores correct answers true, no vent/duplicate in the brain's context, suite stays 107/0. Commit.

### Phase 1 — THE SPINE: act in YOUR real Chrome (the #1 gap)
- **Repoint the act path:** `_run_browser_and_confirm` drives `WebVoyagerAgent(self.browser_link, …)` (the connected extension) when attached, falling back to the throwaway only when no extension. *(control_core.py:1200)*
- **Code-level pay/login click guard in the extension `doAct`**, then drop the `act+cdp_url` refusal so the logged-in Chrome can finally act on non-money tasks. *(extension/background.js:534, browser_use_link.py:303)*
- **Pass the card's structured args** (resolved referents, task_text, start_url) into the act instead of re-deriving from the raw sentence.
- **Build the "open email → read body" recipe** + a general post-action read-back proof (re-observe asserts the state changed) so non-commerce "done" never rests on the judge alone.
- **Collapse the three hands** (owner loop / `/agent/run` / onboarding) into one interface, extension-first.
- **Exit gate (integrated):** ingest a real logged-in task → YES → glassbox shows the job ran **over the extension WS in your real session**, it opened/read/acted, parked at money/send, and the judge verified it. That is listen→infer→**act→close** for real.

### Phase 2 — Real drafts + the send loop
- Route sends to `draft_or_confirm_message`; **compose a real body** (LLM + memory context, replacing the `body=f"Owner request: {line}"` placeholder); create a **real Gmail draft** via the hand; surface **"okay to send?"**; send only on the second YES. *(control_core.py:1494, gateway.py:314, api_hand.send_email_draft)*
- **Exit gate (integrated):** "send Priya the deck" → a real draft exists with a composed body, the Board shows "okay to send?", and it sends only on the second confirm.

### Phase 3 — Onboarding = the full §2 agentic flow
- Make the scrape **go in**: open the weighty threads/events, read bodies/attendees, click into discovered tools; **adaptive layers** (each find re-aims the next). *(owner_scrape._read_surface, loop.run_loop)*
- **Wire the scrape↔phone-call loop** (clarify → Twilio voice → re-aim the next scrape).
- **Capture the contract** the calls exist for: autonomy dial, money/irreversible rule, do-not-touch zones, phone number.
- **Unify the 3 ingestion tracks** (`/onboard/loop`, `/onboarding/clarify`, `ingest_deep_scrape`) onto one dossier+memory.
- **Exit gate (integrated):** a cold onboarding opens real items, calls to fill gaps, locks the autonomy contract, and ends with a profile rich enough that the first proactive moment lands as "how did it know?"

### Phase 4 — Voice on + reachable
- Public tunnel + `ANTICIPY_CHANNELS_MODE=live` + `ANTICIPY_CR_WSS_URL`; add the **inbound `/voice` webhook** (Twilio-signed) so the owner can call in and converse; confirm outbound takes the two-way `<Connect><ConversationRelay>` path; wire voice into the spine (`channel_pref="call"`).
- **Exit gate (integrated):** a real two-way call you can't tell is AI; a reminder rings at its time; the spoken/SMS reply resolves back through the one loop.

### Phase 5 — Cloud per-user hands + durability
- **User-scoped extension link:** extension sends the Supabase token; `/ws/extension` resolves the user → `registry.core_for(user)` → attaches to THAT core's `browser_link`. *(main.py:2037)*
- Decide **one tenancy model** (shared-process registry vs container-per-user) and align the Dockerfile.
- Add a **Railway persistent volume** at `ANTICIPY_DATA_DIR` (ideally Postgres RLS) so data survives redeploy.
- **Exit gate (integrated):** two signed-in users each drive their **own** Chrome; data survives a redeploy.

### Phase 6 — Safety breadth + the integrated multi-day owner test (= §4 done)
- Patch the `is_vent` directed-threat hole; add an **amount-aware** money tier; extend the **never-fake judge to the voice/API arm**; lock each with corpus lines.
- Then the real bar: **multiple real days, ~50% of the workload, zero vent-actions, every money/irreversible confirmed, never a faked "done," human voice throughout — as one seamless product.**
- **Exit gate:** §4 met. That's finished.

---

## WHAT ONLY YOU CAN UNBLOCK (one batch, so I never stall on it)
1. **Be signed into your target services in the paired Chrome** (Gmail/Amazon/your CRM) — so Phase 1/2/3 live-verification acts in real accounts. I never type your credentials; you just stay logged in.
2. **Voice go-live (Phase 4):** OK to expose the engine via a tunnel/deploy, and confirm the Twilio number + set its Voice webhook.
3. **Cloud (Phase 5):** the tenancy decision (shared-process vs container-per-user) + provisioning a Railway persistent volume.

Everything else in every phase is pure code, verifiable locally against the live engine + suite — I drive it.

---

## HOW EVERY PHASE IS JUDGED (so it can't go back to zero)
- The exit gate is the **integrated loop run live**, not a unit demo — per §4, a piece built in isolation counts for nothing until it's wired cleanly into the whole.
- **Verified by running it** (a curl / a glassbox trail / a replay), never by claim.
- **Committed** the moment it's green, on `factory/build`, one engine + one extension — no copy chaos.
