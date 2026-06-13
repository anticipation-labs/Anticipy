# ANTICIPY — GROUNDED BUILD PLAN (2026-06-13)
**Docket:** ANTICIPY-BUILDPLAN-2026-06-13-01 · companion to HANDOUT_2026-06-13.md
**Source:** deep research workflow `wzgkz5ifl` — 13 agents, 111 real web searches, every code claim
verified against this repo (then re-verified by foreman: orchestrator.py:558 + api_hand.py:160 confirmed).
**Read after the handout.** This is the *how*, grounded and adversarially critiqued.

## 0. The honest frame (this changes the promise)
"~75% of your work, fully autonomous" is **beyond 2026 SOTA** (best general agent ~65% GAIA; pass^8
turns a 90%/step agent into ~57%; deployed agents avg ~56%; live-write browser tasks ~33% Claude /
~6.5% GPT on ClawBench). The **achievable, honest product**: *~75% of the **toil**, with the human in
the loop at the money / ambiguity / irreversible edges.* You get there by **narrowing scope per task**
(Devin 34%→67% from scoping, not a smarter model), NOT by chasing full autonomy. Promising silent
autonomous binding-action from ambient audio = the exact 40–60%-then-dies wall.

## 1. THE TRAP THE CRITIQUES CAUGHT (verified true, foreman-checked)
- `orchestrator._verify` (orchestrator.py:556-558) = `result.proof is not None and bool(result.proof)`.
  It only checks a proof OBJECT EXISTS. **Self-attestation.** A buggy/mock executor that writes
  `proof={"ok":true}` passes.
- `api_hand.py:160` — the API "proof" id comes from the **write call's own response** (`resp.output.value`),
  never a second independent read. The actor grades its own homework.
- Consequence: stub/mock scoreboard shows `owner_success 1.0` saturated while real e2e sits ~0.65 and the
  HONEST baseline (dev_v2 owner-ingest real instrument) is **e2e 0.3778** (logs/STATE.md). The gate is
  blind to the gap. **This is the demo trap; it is the foundation everything else stands on.**
- Read-back is an **HONESTY** mechanism, NOT a reliability lever: behind a perfect read-back gate a
  33%-success browser write becomes a 33% completion + 67% honest-handoff. It fixes *lying*, not *failing*.

## 2. BUILD ORDER (the sequence that does not die at 50%) — depth-first, each DONE-by-real-receipt
**Slice 0 (FIRST, foundational) — independent read-back completion gate.** Net-new code, NOT a port of
proof.py (which is browser-only/async; _verify is sync). Add real READ intents to api_hand INTENT_MAP
(Calendar.GetEvent/ListEvents, Gmail.ListDrafts/GetDraft — they do NOT exist today). Build a per-tool
read-back: after create_event → GetEvent(id) and match summary/start; after WriteDraftEmail → ListDrafts
match. Make `_verify` FAIL on self-reported proof and PASS only on a proof carrying `readback:true` set by a
SECOND execute() call. **Acceptance:** a test mocking create_event=success but GetEvent=404 must make
_verify return False; the second network read must be visible in glassbox audit with a distinct request id.
**Forbid counting it done on stub/mock** — pass^k must run live (real second HTTP call). Anchor targets on
the 0.3778 honest floor, not the 0.69 stub number.

**Slice 1 — one real day, one door, end-to-end, live (the assembled-whole PoC).** Paste-transcript →
live brain → live Arcade Calendar event + Gmail DRAFT (never sent) → real SMS confirm to confirmed
OWNER_PHONE → **real receipts Omar can open**. Needs ZERO new capabilities (all pieces REAL per inventory).
This directly attacks the 40–60% pattern: it is the first time the whole thing runs as a product. Gate on
the catch of an UNSPOKEN/reported commitment ("I told Sam I'd send the deck" — currently a SILENT miss)
AND zero vent false-actions.

**Slice 2 — voice loop close (P3).** Replace static `<Say>` in channels/call.py with Twilio
**ConversationRelay** (Twilio runs STT+TTS+barge-in; we write the brain over a `/cr` WebSocket, reusing the
SAME decider — never fork the brain). NOTE: the existing gate_P3.sh only tests one-shot <Say>; the WS
conversation needs its OWN gate (transcript read-back asserting the slot was confirmed). Don't claim the old
gate proves the new code.

**Slice 3 — per-user API mesh (real, not the stub story).** Route-keyed dispatch ALREADY EXISTS
(control_core.py:906-940 on the `route` field). The REAL unbuilt work: (a) Arcade custom-OAuth verifier so
consent is **Anticipy-branded not Arcade-branded** (the default-app demo trap); (b) per-user encrypted token
vault replacing the single shared `ARCADE_API_KEY` (api_hand.py:75); tokens never enter a prompt/log/context.

**Slice 4 — always-listening capture (lean).** Deepgram Nova-3 streaming behind Silero VAD (pay only for
speech, ~$3.68/day) → emit FINAL transcripts into the existing loop. VAD + `no_speech_prob` filter is
load-bearing SAFETY (un-VAD'd Whisper hallucinates ~1% — a hallucinated "pick up the kids at 3" firing an
action is the cardinal sin). Keep batch transcribe.py as-is.

**Slice 5 — onboarding-scraper (NEXT plan; defer).** API-first collectors (Gmail/Calendar/People/MS Graph)
+ read-only browser for no-API sites + **user-paste for LinkedIn** (autonomous logged-in crawl can BAN the
user's own account — hiQ precedent). Low-confidence relationships route to the clarifying call, never asserted.

**Slice 6 — general browser arm (build LAST; highest variance).** Live-write SOTA ~33%, so design as
**prepare-then-handoff** (agent fills the final screen; human does the last binding click). Evolve site_hints
into replayable deterministic recipes (the 30%→80% lever, per-site-family only). Gating metric = **% of
failures converted into deterministic recipes**, measured on the LIVE site distribution, not the cart demo.
The 75%-of-toil promise is carried by API-arm writes + browser READS; browser writes are opportunistic, never
load-bearing.

**Deferred deliberately:** multi-agent action orchestration (keep ONE linear owner per goal; reads may fan
out, WRITES never), cloud browser (kills the "user's own Chrome" anti-bot advantage), pendant, horizontal
breadth (vertical wedge beats horizontal 3–5× on retention; stay on just-Omar until P5 passes), multi-tenancy
(engine is single-tenant: one global ControlCore, no user_id — fine to defer for 5-Omar-days, but NAMED not
silently assumed).

## 3. NON-NEGOTIABLE safety before real accounts/money (prompt-injection is UNSOLVED — contain blast radius)
- Every byte the agent reads = DATA never instructions; commit the plan BEFORE reading untrusted content.
- Dual-LLM/CaMeL split: privileged planner never sees raw page/email; quarantined reader has NO tools.
- Harm-line as a non-LLM chokepoint on EVERY action incl. browser clicks; money stays the only hard stop;
  generalize PURCHASE_GUARD to a code-level click-blocklist (pay/place-order/transfer/delete/change-password).
- Bridge-level nav allowlist + high-value blocklist. VERIFIED GAP: native_bridge_link.py has none and even
  passes `--remote-allow-origins=http://localhost:*` (line 820). Prompt-level allowlists are decorative.
- Egress controls (strip auto-render md images/links, sanitize zero-width/unicode-tag, block base64-in-URL
  to non-allowlisted hosts). Per-user credential vault. Tamper-evident audit (extend glassbox.py).
- Privacy floor at onboarding: scoped consent per source; persist distilled facts+embeddings, drop raw bodies.
- Gate P5 on AgentDojo-style red-team: ~0% attack success, zero credential leak, zero unconfirmed money/send.

## 4. CHEAPEST EXPERIMENTS — run BEFORE building (de-risk the whole)
- **PoC-A (latency/cost spike, cheapest, run first):** the un-researched KILLER. "Listen to EVERYTHING" =
  thousands of lines/day; the full chain is too slow (handout: 5-line probe >150s). Prove the two-stage
  filter: the deterministic triage gate must drop 95%+ of noise for ~free, and only a few lines/day reach the
  decider(~1s)/orchestrator. Measure $ + wall-clock for ONE real ~1000-line day. If every line hits the
  decider, always-listening is economically impossible on this architecture — discover it now, not at 50%.
- **PoC-B = Slice 1** (one real day end-to-end live). The assembled-whole test; zero new capabilities.
- **PoC-C (onboarding feasibility):** attempt logged-in crawl on 2–3 real sites, observe if the account gets
  flagged/challenged. Cheap; tells us if "scrape you" is even account-safe before architecting it.

## 5. THE 2–3 THINGS ONLY OMAR DECIDES
1. **OWNER_PHONE** — already confirmed +1 604 724 5161 (factory/config/owner_phone.confirmed exists). ✅
2. **The expectation contract:** "~75% of the toil with you in the loop at the edges" (honest, shippable) vs
   "75% fully autonomous" (beyond SOTA). Governs how hard the harm-line gates (over-gate=nag, under-gate=sin).
3. **The wedge:** which ONE persona's ONE workflow ships first (founder / lawyer-Cosmolex-no-API / doctor) —
   each implies a different first connector + legal surface. Research says stay just-Omar until P5 passes.
Secondary: Cosmolex has NO public API → it's browser-arm-only (the "per-person API for each" promise is
partly false for the exact example); Google restricted-scope CASA audit is weeks of calendar-time, not code.

## FIRST MOVE (locked): PoC-A (latency/cost) → Slice 0 (real read-back gate) → Slice 1 (one real day live).
Each ends with a receipt Omar can open. A skeptic agent attacks each "done" before it counts.
