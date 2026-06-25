# ANTICIPY — LEDGER (the ratchet record)

> The un-fakeable memory. A gate is **GREEN** only when it is built + adversarially verified + the
> suite is green + committed. This is what the next (or compacted) session trusts to be instantly
> current — read it with `THE_FORGE.md` (the system), `PLAN_TO_DONE.md` (the path), and
> `ANTICIPY_SOURCE_OF_TRUTH.md` (the bar = §4). Newest dated wins. Updated 2026-06-24.

**Ratchet:** `bash scripts/run_suite.sh` → **107 passed / 0 failed** (held across every Phase-0 commit).
**Trunk:** `factory/build`, one engine (`~/Anticipy/engine` on :8787), one extension (`~/Desktop/Anticipy-Extension`).

---

## ✅ GREEN — built + verified (held under adversarial attack or audit-grounded)

| Gate | Proof | Status |
|---|---|---|
| Safety floor (money hard-stop + vent floor + never-fake judge, BOTH browser arms; zero-breach corpus) | audit + suite `safety_mega_eval` | HELD |
| Brain classification (act/ask/silent; vents ignored; money blocked w/ warm copy) | live `/owner/ingest` probes | HELD |
| Memory (4 drawers, hybrid recall, honest scrape→memory) | audit + live `/memory/drawers` | HELD |
| Per-user cloud (Supabase auth + data isolation, A≠B on disk) | `test_user_isolation` + audit | HELD |
| **Phase 0.2** — judge revived (correct→true, wrong→false; not always-true) | live judge probes; **adversary HOLDS** | GREEN |
| **Phase 0.4** — memory write-idempotent (3 ingests→1 loop) + inject dedup/vent-gate | live; **adversary HOLDS** | GREEN |
| **Phase 0.1** — Board never fakes success (real ask id + celebrate only on terminal/running state) | refuted 3×, fixed 3×; **final adversary HOLDS, no hole** — it reproduced a live `{approved:true,state:"failed"}` and confirmed `resolvedOk` springs it back; no genuine success left un-celebratable | ✅ **GREEN — SEALED** |
| **Phase 0.3 (DROP side)** — bundled DISTINCT tasks split; no task vanishes | live: vent+"call dentist AND send Priya"→2 cards | GREEN |
| **Phase 1 (THE SPINE) — code** — YES→act drives the CONNECTED real Chrome (WebVoyagerAgent on browser_link), throwaway only as fallback; one judge + card-landing for both | mock routing test (8 assertions) + adversary HELD (25 more: judge-forced, agent-raising, missing keys, safety-stop, paused, fallback regression); suite 108/0 | ✅ GREEN (code) — **live act = BLOCKED-ON-OMAR** |
| **Phase 6.1 safety — is_vent directed-threat hole** — first-person violence at a person now suppressed as a vent (was surfaced as a HIGH-conf task) | adversary-driven (13 holes closed, 0 false-pos); safety_mega_eval BREACHES:0 / 172 lines; suite 108/0 | ✅ GREEN (improved) — bounded regex residual (bare proper-name / gerund), NO end-to-end breach |

## 🖐️ STEP 1 — THE HANDS OPERATE (the spine, the #1 gap) — ✅ LIVE-GREEN 2026-06-25

The hands were DEAD (every "browser" gate was a proxy): the extension threw `No current window` on
every action. **Fixed** (`createTab` → last-focused/any normal window, else open one; `020d94c`).
Live-proven via `/agent/run` (the SAME agent the owner act-path drives), each judged TRUE:
- **R1** open+read a real site — Wikipedia/Coffee → title + first sentence.
- **R2** *operate* — searched, navigated Main_Page→Espresso (2 steps), extracted the first sentence.
- **R3** *novel site* — Hacker News top story "Half-Life 2 in a Browser" → **horizontal, not hardcoded**.
Honesty held: an empty answer was refused as `needs_human`, never faked.

**RUNG A — integrated owner-flow → hand (§4.1) — ✅ LIVE-GREEN 2026-06-25 (`9412f68`):**
`/owner/ingest "Find the height of the Eiffel Tower in metres"` → brain → browser_action card →
auto-run (earned browser trust) → card PERSISTED → connected hand runs on the real web → judge
success=True → card `state=done`, answer "330 meters". Honesty held: a Guggenheim lookup answered from
Google (not the official site) → judge → `state=failed`, never faked. Fix: the auto-run + ask branches
`append+continue`'d BEFORE `_persist_card`, so results had no record to land on — now persist first.
**RUNG B — brain copy/flow — ✅ LIVE-GREEN 2026-06-25:**
- **B.1 routing determinism (`e93afa3`):** web-answerable QUESTIONS ("what time does X close", "check the
  status of flight Y", "how much is Z") were dropped/clarified; added scoped `_WEB_LOOKUP` (after the
  money/send pre-gates) so they route to the hand. LIVE: 6/6 lookups → hand; the dropped Costco
  question → card state=done "$65/yr". Money still blocked, vents ignored.
- **B.3 email draft-then-ask (`4e6c4f6`):** `_person_hint` was case-sensitive → "Email Priya"/"Send Sam"
  missed the name → generic confirm. Scoped `(?i:)` to the verb. LIVE: → `ask/draft_or_confirm_message`
  (drafts first, never auto-sends).
- **B.4 money:** already `blocked` + warm reason ("Because it's about money, you want to check it over
  first") — acceptable warm ask, not a cold status.
- **B.5 multi-line:** LIVE: "…call the dentist…and send Priya the deck" → 2 cards (no drop), vent ignored.
- Residuals (tracked, not blocking): role-recipient sends ("text my landlord") need a proper name to
  draft; stale-card dedup can still return a prior card on near-identical re-ingest.
**STEP 3 — onboarding deep-read via the LIVE hand — ✅ LIVE-GREEN 2026-06-25 (`0d62a11`):**
`POST /onboard/deep-read-hand {targets}` → `onboard_deep_read_via_hand` drives the connected Chrome to
OPEN each target + READ real content (observe: page text + visible items) → dossier synthesizer →
memory. Extended `_render` to carry generic notes/text (horizontal, any surface). Reliable (observe,
not the agent's flaky multi-fact synthesis). LIVE: Espresso article → surface ok, 1901 chars,
memory_written {profile:1,derived:1}, real facts synthesized. Old screenshot-first scrape superseded.
**Real-accounts (Gmail/calendar) reuse this read-only path → needs Omar logged in (login wall →
needs_login) = PENDING.** Depth follow-on (open sub-items within a page) tracked.
**RELIABILITY (§4.6) — ✅ LIVE-GREEN 2026-06-25 (`0cb5df9`):** the hand returned EMPTY on multi-fact
reads (AGENT_MAX_TOKENS=96 truncated the answer JSON → unparseable → blank). Raised cap to 512 + an
empty-answer re-ask guard. LIVE: "list 5 key facts" → 3/3 real answers (was 0/3); single-fact still
works. Follow-on: judge calibration wavers on deliberately-fuzzy asks (errs to handback, never fake-done).
**Next: Step 4 cloud per-user routing** (locally testable: 2 simulated users → isolated cores; cloud
deploy = Omar) → Step 5 voice (tunnel+Twilio = Omar) → Step 6 integrated owner test (§4 = finish).

## 🟡 PARTIAL — honest non-binary residual (NOT faked green)

| Item | What's done | The residual |
|---|---|---|
| **Phase 0.3 (OVER-SPLIT side)** | the deterministic splitter is conservative + correct on reminder-shaped lines | plain **imperative** lines still get over-split by the model. A post-extract `src_idx` merge was **ATTEMPTED and REVERTED 2026-06-24** — the ratchet caught that it could merge away a *money* line in a multi-line transcript (`src_idx` from whole-transcript extraction does NOT reliably mean "same sentence", so it grouped unrelated obligations). Bounded residual (an extra card, never a lost task). **Safer fix needed: group by sentence-span, not `src_idx`** — and any such merge must NEVER touch a money/blocked line. |

## 🔴 RED / NEXT — the path to §4 (from PLAN_TO_DONE)

1. **Phase 1 — THE SPINE:** ✅ **routing/adapter DONE + adversary-held (`c7e1106`)** — YES→act drives the connected real Chrome (`WebVoyagerAgent` on `browser_link`), throwaway only as fallback, one judge + card-landing. **REMAINING:** (a) live "act in real Gmail" proof — **BLOCKED-ON-OMAR** (won't drive his Chrome unattended); (b) thread the card's structured args into the act (today `_run_browser_and_confirm` still takes a task string + re-derived url); (c) "open email→read body" recipe + a general post-action read-back proof for non-commerce tasks.
2. **Phase 2 —** real Gmail drafts + "okay to send?" loop. *(code mine; live proof needs Omar)*
3. **Phase 3 —** full agentic onboarding (go-in scrape + scrape↔call loop + autonomy/money/do-not-touch capture). *(needs Omar login + Twilio)*
4. **Phase 4 —** voice on + reachable (tunnel + live env + inbound `/voice` webhook). *(needs Omar: tunnel + Twilio)*
5. **Phase 5 —** cloud per-user hands (extension carries the Supabase identity; `/ws/extension`→`registry.core_for(user)`) + durable Railway volume. *(needs Omar: tenancy decision + volume)*
6. **Phase 6 —** safety breadth (`is_vent` directed-threat hole, amount-aware money tier, judge on voice/API arm) + the **integrated multi-day owner test = §4 done.**

## 🙋 WHAT NEEDS OMAR (batched — everything else I drive)
- **Stay logged into your accounts in the paired Chrome** → unblocks Phase 1/2/3 live proof.
- **Voice go-live** → OK to expose via tunnel/deploy + confirm the Twilio number's webhook (Phase 4).
- **Cloud** → the tenancy decision (shared-process vs container-per-user) + a Railway persistent volume (Phase 5).

## Commits / cycle log
- `90b1089` THE_FORGE + Phase 0 (all 4 gates first pass)
- `ca91d93` close adversarial refutations of 0.1 + 0.3 (round 1)
- `5d9ab19` close the deeper 0.1 refutation (terminal-state)
- `5caea25` LEDGER v1
- **Cycle 2 (2026-06-24):** 0.1 final adversary HOLDS → **0.1 SEALED**. Over-split merge attempted →
  **reverted** (ratchet caught a money-line merge risk) → residual stays tracked, suite back to 107/0.
  Phase 1 mapped + verification approach defined; live act = BLOCKED-ON-OMAR.
- `c7e1106` **Cycle 3 (2026-06-24):** **Phase 1 spine code DONE** — YES→act repointed to the connected
  real Chrome (throwaway = fallback); mock routing test (8) + adversary HELD (25 more); suite **108/0**.
  Live act in real Gmail = BLOCKED-ON-OMAR.
- `6e5a7a2` **Cycle 4 (2026-06-24):** **Phase 6.1 directed-threat hole closed** (adversary-driven, 13
  holes, 0 false-pos, BREACHES:0, suite 108/0). DECLINED Phase 6.2 amount-tier (auto-spend-under-$X
  would weaken the money hard-stop — kept all-or-nothing park). **→ LOOP STOPPED:** every remaining
  gate is BLOCKED-ON-OMAR (see below). No further autonomous cycle scheduled — waiting on Omar.

---

## ⏸️ AUTONOMOUS LOOP STOPPED (2026-06-24) — waiting on Omar

Every gate that could be built + verified **without** Omar is done, ratcheted, and committed (suite
108/0). Everything left genuinely needs him — so per THE_FORGE ("don't grind, don't fake"), the loop
is **stopped**, not spinning. The batch to unblock the rest is in **`PENDING_FOR_OMAR.md`**.
