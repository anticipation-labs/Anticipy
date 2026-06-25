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

## 🟡 PARTIAL — honest non-binary residual (NOT faked green)

| Item | What's done | The residual |
|---|---|---|
| **Phase 0.3 (OVER-SPLIT side)** | the deterministic splitter is conservative + correct on reminder-shaped lines | plain **imperative** lines still get over-split by the model. A post-extract `src_idx` merge was **ATTEMPTED and REVERTED 2026-06-24** — the ratchet caught that it could merge away a *money* line in a multi-line transcript (`src_idx` from whole-transcript extraction does NOT reliably mean "same sentence", so it grouped unrelated obligations). Bounded residual (an extra card, never a lost task). **Safer fix needed: group by sentence-span, not `src_idx`** — and any such merge must NEVER touch a money/blocked line. |

## 🔴 RED / NEXT — the path to §4 (from PLAN_TO_DONE)

1. **Phase 1 — THE SPINE (next):** route the YES→act path (`_run_browser_and_confirm`, control_core.py:1209) to drive `WebVoyagerAgent(self.browser_link, self.gateway, …)` when `browser_link.connected`, else fall back to the throwaway `browse_act`; normalize the agent's dict result (answer/final_url/needs_human/final_shot) into the existing judge + `_land_browser_result_on_card` path; pass the card's structured args. **Verification note:** the new branch only activates with an extension connected, so the stub suite can't reach it — verify the routing+adapter with a MOCK-based unit test (unattended, ratchet-able), and the live "act in real Gmail" with Omar logged into the paired Chrome (do NOT drive his Chrome unattended). *(code = mine; live proof = BLOCKED-ON-OMAR)*
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
