> ⚠️ **SUPERSEDED — 2026-07-02.** Historical document. The living truth is **`CANON/00_START_HERE.md`**
> (+ `MISSION_LOCK.md` for live mission status). Do not follow this file's read-order, done-definition,
> or status claims. Indexed with context in `CANON/99_SUPERSEDED_INDEX.md`.

# WAKEUP — overnight run report (read me first)

Branch `overnight/real-progress`. I did real work or honestly-labeled work all night. Nothing below
is "green" unless a checker that reads reality confirmed it. Where it isn't proven, it says NOT
VERIFIED.

---

## 1. THE TRUTH IN FIVE LINES
1. **REAL & PROVEN — calendar:** I created **12 real Google Calendar events from 12 DIFFERENT fresh
   requests** (not one task ×12); a *separate, self-proved* judge confirmed each by reading your real
   calendar. 3 are still on your calendar as proof (labeled `[Anticipy test]`), 9 I cleaned up.
2. **REAL & PROVEN — judgment brain:** I built the ACT/ASK/SILENT decider and graded it on a 60-line
   key with a separate self-proved scorer. **Cardinal false-action (acting on a vent/wish) = 0** on
   train, held-out, and all. It stayed silent on **30/30** noise lines and caught **28/30** real
   commitments. (PROVISIONAL — see #2 below.)
3. **REAL BUG FOUND + FIXED:** every calendar create was *silently* failing — `ApiHand._proof_from`
   couldn't read the event id Arcade nests under `{event:{id}}`. Fixed generally; suite still 29/29.
4. **HANDED OFF (1 tap owed):** Gmail **drafts** need a scope you haven't granted (`gmail.compose`).
   I built the whole draft path and it **refuses to run until you tap** — it will not fake a draft.
5. **NOT DONE:** onboarding, web search, the typed-input box, multi-step browser, iOS — untouched
   tonight (I chose to *prove* the few real things rather than build inert versions of the rest).

---

## 2. THE 1–3 THINGS ONLY YOU CAN DO

**(a) Tap to connect Gmail drafts** (unlocks the built-and-waiting draft path — re-run
`overnight/track_c/draft_runner.py` after and it proves itself for real):
```
https://accounts.google.com/o/oauth2/v2/auth?access_type=offline&client_id=826965503-pci56f36oeot675h17vic7rsc370til4.apps.googleusercontent.com&include_granted_scopes=true&prompt=consent&redirect_uri=https%3A%2F%2Fcloud.arcade.dev%2Fapi%2Fv1%2Foauth%2Ff4c6b_aps_arcade-google%2Fcallback&response_type=code&scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.email+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fuserinfo.profile+https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.compose&state=f751df4b-5389-46e9-a775-df5ed08eacdc
```

**(b) Red-pen the answer key** (`overnight/track_b/answer_key.jsonl`). My numbers are only as honest
as your marks, and I wrote both the decider's rule and the key — so their agreement partly reflects
*my* consistency, not proven truth. Look hardest at these, where my decider disagreed with my own key
(both are safe-direction misses, not false-actions):
- `"Did the dispute ever get filed? I should chase it."` — I keyed ACT; decider said SILENT.
- `"I'll probably tidy up the garage this weekend."` — I keyed ACT; decider said SILENT.
- and the 8 rows tagged `nearline` (e.g. *"I really need to call my mom"*, *"I keep meaning to cancel
  that subscription"*) — genuinely ambiguous; your call decides them.

**(c) Nothing else is blocked on you.** Calendar is already connected. No Apple/device step came up.

---

## 3. WHAT I BUILT BUT COULD NOT VERIFY (and what each needs)
- **Gmail draft path** (`overnight/track_c/draft_worker.py` + `draft_judge.py` + `draft_runner.py`):
  BUILT, **NOT VERIFIED** — needs **your tap (2a)**. It mirrors the proven calendar path exactly
  (fresh ask → real draft, never sends, forced to your own address → separate judge confirms in the
  mailbox). Tonight it correctly *blocked itself*.
- **Draft connector in the engine** (`send_email_draft → Gmail.WriteDraftEmail` in `api_hand.py`):
  BUILT, **NOT VERIFIED** — real tool name + schema, but unexecuted until the scope is granted.

I deliberately did **not** build fake versions of onboarding / web search / the input box / iOS.
Per your law, a pretty-but-hollow version of those is the exact failure to avoid.

---

## 4. RANKED REAL FAILURES / GAPS STILL OPEN (real reason each)
1. **Gmail drafts unusable** — `gmail.compose` scope not granted. Reason: a human OAuth tap only you
   can do. (1 tap → fixed; path already built.)
2. **The shipped proactive engine OVER-ASKS on noise** — graded on the same key, the *existing*
   triage+harm-line is cardinal-SAFE (0 false-actions, good news) **but would interrupt you on 9/30
   vent/wish/joke lines** (e.g. *"If I won the lottery I'd buy an island"* → it asks). Reason: triage
   is tuned for high recall and the harm-line fail-safes to ASK. My Track B decider fixes this
   (0 over-asks, still 0 false-actions) but is **not wired into the engine** — that's a real change
   for a future, supervised session, not something I'll slip in unproven overnight.
3. **Track B recall has 2 holes** — the decider silences two soft commitments ("I should chase it",
   "I'll probably…"). Safe direction, but real. Pending your red pen (2b) before I'd tune anything.
4. **The whole product perimeter** (from last audit) — onboarding, web search, multi-step browser in
   the task loop, the connector mesh beyond Calendar/Gmail, real input — still absent. Not tonight's
   scope; named so it isn't mistaken for done.

---

## 5. ONE HONEST LINE
Real progress, not a mess: the one truly un-fakeable thing — a fresh request becoming a real calendar
artifact, confirmed by an independent self-proved judge — works **12/12**, and the judgment brain's
catastrophe count is **0**. Everything I couldn't prove, I left gated behind your tap or your red pen
instead of faking it.

---
### Where to look (all on branch `overnight/real-progress`)
- `STATUS.md` — full technical log + every real event id.
- `overnight/track_a/` — the proven calendar path (generator / worker / judge / run_laps + results).
- `overnight/track_b/` — decider, the 60-line key, the self-proved scorer, and the existing-engine grade.
- `overnight/track_c/` — the built-not-verified Gmail draft path.
- Commits this run: Track A (`cac129d`), Track B (`995ad3c`), Track C (this commit). Suite 29/29 throughout.
