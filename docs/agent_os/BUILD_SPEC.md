# Anticipy — Build Spec & Handoff

The stable north star: WHAT Anticipy is and HOW to build it. No status, no percentages, no opinions —
those drift and rot. Live open work lives in `DONE_LEDGER.md`; this file is the unchanging target.
Build to this. (Architecture references are file pointers, not claims about state — verify in code.)

---

## 1. What Anticipy is

An always-on personal assistant you live with. It hears your messy real day (typed, MP3, or live
mic), works out what you actually need without you spelling it out, remembers everything and ties
vague references to the right thing, then handles it — through a browser in your own Chrome, your
calendar and email, and a voice/text line that talks back like a sharp human. The product is the
inference: turning ordinary speech (sarcasm, vents, half-thoughts, things other people ask of you)
into the right action, taken at the right level, with proof and follow-up.

It is "Donna from Suits": competent, brief, warm, ahead of you. The win condition is that after a
few days you forget it's software and would be upset to lose it.

---

## 2. The end-to-end journey it must deliver

OPEN (hosted site / downloadable app) → ONBOARD (who you are, who matters, how to reach them) →
CONNECT (Chrome, Google, phone) → build a per-person PROFILE / TOOL MESH → INPUT (transcript, MP3,
live listening — all into ONE brain) → MEMORY + INTENT (recall context, resolve "that desk thing")
→ AUTONOMY DECISION (pick the right level, below) → ACTION (browser / API / voice-text) → PROOF
(independent read-back: screenshot+DOM+URL, calendar/draft read-back, delivery SID) → FOLLOW-UP
(check back later and nudge) → FRONTEND RECEIPT (human-language result in the app).

Every input route is the same brain (`core.owner_ingest`). The decision logic never branches on which
mouth the words came from.

---

## 3. How it behaves (the autonomy levels — this is the whole personality)

It is NOT an approval machine. Default to acting. It chooses ONE level per thing it hears:

- **AUTO_DO** — low-risk, reversible. Just do it; show the proof. (calendar hold, look something up.)
- **AUTO_DO_WITH_OPT_OUT** — a reversible chore on an outside service (Amazon refund/return/support,
  contacting a company about an order). START it, text "I'm on it — tell me to stop," keep going
  unless stopped. This is the centerpiece; it must feel like a chief of staff, not a form.
- **PREPARE_THEN_STOP** — anything that moves money, sends to a real person, signs, or can't be
  undone: get it ready to the very last step, tell the owner in plain human words what's ready and
  that it's waiting on their go, take the final step only on their go. One tap, not a wall.
- **CLARIFY_FIRST** — only when genuinely missing context (which of two people, which item). One
  short question, never a guess.
- **REMEMBER_ONLY** — preferences and facts. Store, don't act.
- **IGNORE** — vents, jokes, sarcasm, fantasy, background noise. Do nothing, say nothing.

Worked example — Mom (heard in the room): "Omar, call Amazon and get me a refund for this, it's
expired." → AUTO_DO_WITH_OPT_OUT → opens Amazon in the owner's own Chrome, starts the refund, texts
"I'm on the Amazon refund — tell me to stop," lands proof on the card, schedules a 2-day follow-up.
"If I win the lottery I'm buying an island" → IGNORE. "Pay the $1,450 rent" → PREPARE_THEN_STOP:
ready, one tap from the owner.

Every message the agent sends (asks, "on it," results, the "this is ready / needs your go" heads-up)
is written per-situation by the model in this voice — never a canned template.

---

## 4. The arms (what each does)

- **Browser (own Chrome).** The real arm drives the owner's logged-in Chrome via the MV3 extension
  (`hands/browser_hand.py` → `/ws/extension`), so it's already signed in (no fresh-profile walls). A
  throwaway browser (`hands/browser_use_link.py` + the CFT binary) is the fallback. It prepares
  carts/forms/returns/support flows, captures screenshot + DOM + URL, and never completes a
  purchase on its own.
- **API (Arcade).** Calendar create/read-back, Gmail draft (compose, never auto-send). Proof is an
  INDEPENDENT read-back by id, never the write's own echo. (`hands/api_hand.py`, `INTENT_MAP`,
  `READ_BACK`.)
- **Voice / text (Twilio).** Outbound SMS + voice (the "calendar made; I'll call you at 2:45" line,
  `channels/call.py`, `channels/text.py`). Inbound is a POLLER (`channels/inbound.py`) — the owner's
  "YES" replies come back and resolve the exact pending ask; two-way live voice uses ConversationRelay
  over a public wss (`/cr`).

---

## 5. Architecture map (where to build)

- One brain: `core/control_core.py::owner_ingest` → `_owner_ingest_inner` (observe → moat
  `_expand_tasks_with_model` → intent `_intent_resolve` → dedup `_consolidate_obligations` → capture →
  card per line → autonomy label → follow-up → find-notification).
- The inference (the moat): `proactive/extract.py` (per-line task vs vent vs ambient). The
  deterministic shaper: `owner_mode.py::card_for_line`. The act/ask decision spine: `_spine_card` +
  `proactive/harm.py` + `proactive/decider.py`.
- Autonomy labels: `proactive/autonomy.py`. Intent/vague-ref: `proactive/intent_threads.py`. Dedup:
  `core/control_core.py::_same_obligation`. Follow-up: `proactive/follow_up.py`. Human messages:
  `proactive/agent_reply.py` (`agent_reply`, `notify_finds`).
- Web app: `app/` (Next.js — `page.js` the day surface, `welcome/` onboarding, `connect/` connect,
  `download/` + `api/download/...` the app), proxying to the engine via `app/api/_engine.js`.
- Engine: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`.
  Web: `npm run build && npm run start` (production server — stable; `next dev` corrupts `.next` under
  repeated restarts).
- Tests: `bash scripts/run_suite.sh`. Add a regression test for every fix.

---

## 6. The plan to finish (ordered; mark progress in DONE_LEDGER, not here)

1. **Software to zero.** Build a model-based semantic-dedup pass so one obligation split across
   clauses ("buy the seats" + "charge the card"; "pay the recruiter" + "send the 8 grand") becomes
   ONE card. Run a red-team pass over diverse real-life days; fix any real wrong-behavior at the root;
   lock each with a test; keep the suite green.
2. **Light up the live arms.** Gmail: enable the Gmail toolkit for the Arcade project, then create +
   read-back a real draft. Inbound: close the reply→act loop (poller + a real "YES"). Two-way voice:
   public wss (a tunnel works without a full deploy). Browser: drive a real task in the owner's own
   logged-in Chrome via the extension.
3. **Distribution.** Deploy the app + engine to a real URL behind the owner token. Sign + notarize
   the downloadable Mac app (or ship the unsigned dev build for local).
4. **Live it.** Five real days of ordinary use. It hears the day, handles what it should, prepares
   the money/irreversible to the last tap, never acts on a vent. If after five days it's a competent
   assistant you'd be upset to lose — that's the finish line.

Phase 1 is buildable now. Phases 2–4 need the owner's accounts, a deploy, and lived time.

---

## 7. How you know it's working (objective behavior, not opinion)

A normal person, using only the app: onboards in under a minute; talks/uploads/lets it listen; sees
the right things caught and the throwaway lines ignored; gets a human text when something needs their
go; taps once for the money/irreversible; gets proof of what was done; gets a follow-up later.
Across a real week: nothing it shouldn't have done, nothing real missed, no spam. That is the bar.
