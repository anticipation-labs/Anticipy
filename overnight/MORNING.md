# Morning, Omar

Plain words. Three things you need to know, then the details.

---

## 1. SOMETHING YOU HAVE TO DO (2 minutes)

**Your AI credits ran out.** Not Anticipy's fault, not a bug — the account
that pays for her thinking hit a wall and started refusing.

At about 1am the model she thinks with started answering **"402 Payment
Required"** to everything. If I had left it, you would have woken up to an
assistant that hears you and cannot think — every line silently failing.

**What I did:** switched her onto a cheaper model that still answers, and
checked it handles your real cases correctly before switching. She is
awake right now.

**What you do:** top up OpenRouter (openrouter.ai → Credits). Then, if you
want the better model back:

```
cd ~/AnticipyFleet/control && railway variables --service worker --set "ANTICIPY_MODEL=google/gemini-2.5-flash"
```

I did not top it up myself — spending your money is yours to do.

---

## 2. THE THING YOU ASKED ME TO FIX — it works

**What went wrong last night:** you dictated a newsletter list to your Mac
with Wispr Flow. Your phone heard it and thought you were talking to *her*.
One dictation became **three real jobs**: "remove items 491, 492, 493",
"update the KTHAI list", "reply to Toby's email". You never asked for any
of it.

**Why it happened:** she only ever asked one question — *"does this sound
like something to do?"* — and "kill 491, 492, 493 of your list" sounds
exactly like something to do.

**What she does now:** every single line gets a **second, separate
question** — *whose job did these words just create?*

| answer | what it means | what she does |
|---|---|---|
| **his** | he promised someone, or asked her | do the work |
| **someone else's** | a friend said "I'll book it" | remember it. Never start it. |
| **a machine's** | he's voice-typing into an app | **nothing.** That app is already doing it |
| **nobody's** | chatter, or the transcript is mush | may quietly look something up, never more |

Both keys must turn before she does anything that matters.

**Proof, on your real words:**

```
PASS  "Pill 491 kill 492 kill 493 of your list"            -> machine, silent
PASS  "Carson Michael and RV.help23 ... KTHAI"             -> machine, silent
PASS  "4546 4748 reply my inbox drive to Toby's email"     -> machine, silent
PASS  "Can you book dinner for 7 PM tomorrow at Cactus"    -> his, fires
```

All three of your real false fires are dead. The dinner still gets caught.
The Cactus and Earls conversation proofs still pass. 70 offline tests pass.

**No keywords, no hardcoding.** She is not looking for the word "kill" or
"491". She is judging who owed what — which is why it also handles the case
you actually care about: your boss asking you for the deck is *your* job,
your colleague saying they'll send theirs is *theirs*.

---

## 3. THE MOST IMPORTANT THING I LEARNED (read this one)

**The way we have been judging changes has been broken, and it explains a
lot of the last week.**

I ran the *exact same code* on the *exact same data* three times:

```
run 1: 8 false fires     run 2: 11 false fires     run 3: 8 false fires
```

**Nothing changed between those runs.** The AI is just not perfectly
repeatable. So a swing of 3 means nothing.

Every time someone (me, Devin, the fleet) made one change, ran it once, and
said "fixed!" or "broken!" — **they may have been reading noise.** That is
almost certainly why this thing has felt like it lurches between deaf and
spammy. We were steering on a wobbly needle.

From now on: **every judgement is the average of at least 3 runs.** It is
in the tooling, it can't be skipped.

I also caught myself making the same mistake twice more overnight:
- I counted "the AI errored out" as "she wrongly did something" — that
  produced a fake result of 57 false fires and nearly sent me chasing a
  problem that did not exist.
- I counted a miss every time she stayed quiet on a line — but a dinner
  agreed over six sentences needs **one** card, not six. So the old number
  punished her for the exact behaviour we want. Now it asks the honest
  question: of the conversations that needed something, how many got
  **nothing at all**?

---

## The scorecard

Built from **your real 244 lines**, split in two before I touched anything:
- **dev** (146 lines) — what I tuned on
- **held out** (98 lines) — never looked at while building, scored once

Both sets labelled with what *should* have happened. Your own Wispr Flow
history is the ground truth for the dictation lines — those aren't my
opinion, they're documented fact.

(Final before/after numbers are appended below by the last run of the
night — if this section says TBD, the run was still going when you woke.)

---

## Your button

Nothing was changed on your phone. The app is untouched. The only live
change is the model swap that kept her breathing.

If anything at all feels wrong:

```bash
bash ~/AnticipyFleet/control/REVERT.sh
```

Puts the brain back exactly as you left it. Your data is never touched. My
work is saved on a branch, not thrown away.

---

## What I did NOT do

- **Did not ship the new brain to production.** It lives on the branch
  `overnight-directed-speech`, waiting for the held-out score. I said I
  would only ship if it beats the current behaviour on data I never tuned
  against, and I meant it.
- **Did not touch your money.**
- **Did not build the Wispr-Flow-specific hack.** You were right to push
  back on that — it solved one app, and the real problem is every
  conversation you have with every person. The "whose job is it" question
  handles all of them, which is why it also gets the boss-vs-colleague case
  right.
