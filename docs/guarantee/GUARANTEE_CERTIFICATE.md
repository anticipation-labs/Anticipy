# Anticipy — SOFTWARE_CERTIFIED_READY_FOR_OWNER_5DAY

_Dated 2026-06-17. Method: GUI-first — the messy day driven through the real web UI; live arms via the
engine's real Arcade/Twilio/browser execution; deterministic + representative-sample testing._

## The product spine, proven through the actual app
A messy 9-line day (Mom→Amazon, "I'll handle it", coffee→woods vent, Boss→Sam deck, "remind me before
I send it", CRM retainer note, lottery joke, Jarvis desk "don't buy", "that desk thing") typed into the
real UI → **4 cards**, each correct:
- **Amazon "call Amazon about the plant"** → **AUTO_DO_WITH_OPT_OUT** / browser. UI lane *"On it — you
  can stop me: I'm on it … tell me to stop"* + **Stop** button. Not an approval queue.
- **CRM "retainer note in the CRM"** → **AUTO_DO** prepare-internal-note. UI *"Prepare internal note —
  CRM not connected, I've kept the note text ready"*. Not money-blocked.
- **Sam deck** → **ONE** card (the "remind before I send it" reminder folded into the deck thread).
- **"that desk thing"** → resolved to **the Jarvis standing desk**.
- **Both vents** (coffee→woods, lottery→island) → **silent**, 0 cards.
- Money/send still hard-stop; every card carries proof + an autonomy mode shown in the UI.

## Criteria (all met; two via the allowed "exact blocker remains")
| Criterion | Status |
|---|---|
| product opens | ✅ localhost UI ↔ engine |
| onboarding works | ✅ /welcome 4-step; profile (name/tz/people/prefs) written + used |
| profile / tool mesh | ✅ sourced profile; Calendar connected |
| transcript + MP3 + listening → one brain | ✅ Gate C (MP3 = full local-Whisper audio) |
| memory / intent through UI | ✅ vague-ref, dedup, vents |
| autonomy modes | ✅ all 6; AUTO_DO_WITH_OPT_OUT in UI |
| browser arm | ✅ **live** cart-prep, screenshot+DOM+URL, stop-before-buy |
| Calendar live | ✅ create→read-back→delete (real event ids) |
| Gmail draft live **or** exact auth blocker | ✅ **blocker recorded** (Arcade Gmail-toolkit config; consent granted 3×, binding is Arcade-side) |
| voice/text live **or** blocker | ✅ **live**: SMS delivered + call connected (owner-confirmed); inbound = exact blocker (public URL) |
| proof in UI | ✅ |
| follow-up | ✅ Gate I (fires, linked) |
| representative human-life testing | ✅ 1,200-run sample, 10 domains × 14 scenarios, **0 critical** |
| no P0/P1 | ✅ safety 0 breaches; suite **99/0** |
| proof bundle | ✅ docs/guarantee/proof + docs/e2e |

## What remains (owner-gated)
1. **Five real owner days** — lived use, the headline remaining proof.
2. **Gmail draft** — enable the Gmail toolkit/scope for the Arcade project in the Arcade dashboard
   (Google consent is already granted; the binding is Arcade-side config, not a tap).
3. **Inbound voice + two-way voice + hosted front door** — a public URL (deploy or a cloudflared
   tunnel) so the Twilio webhook / ConversationRelay reach the engine.
4. **Signed downloadable Mac app** — Apple Developer signing/notarization (today: unsigned dev/local open).

## Honest caveats
- `assert_done.py` (stricter internal gate) marks G + H FAIL because it demands FULL pass; under the
  Phase-5 "OR exact blocker remains" allowance they are met-with-recorded-blocker.
- Live **arm execution** was proven via the engine's real arms (Arcade/Twilio/browser-runner) — the same
  paths the UI buttons trigger; the act/ask/silent **spine** + onboarding were driven through the real UI.

DONE_CERTIFIED is withheld until the five owner days are lived.
