# Manual voice test — a walkthrough you can run at 1am

You, a phone, and about 40 minutes. No terminal needed. No code needed.

This exists because manual testing matters more here than automated testing,
and because every previous report of a failed test has ended at *"it didn't
work"* — which tells nobody anything. This script is built so that when it
fails, **it fails at a named step**, and that step tells you which part of the
product is broken.

---

## Read this first — three things that will save you an hour

**1. There are no magic words.** Nothing you say triggers anything by matching a
keyword. A model reads what you said, in context, and decides. So test it the
way you actually talk: half-sentences, thinking out loud, changing your mind
mid-way, talking to someone else in the room. **If you find yourself phrasing a
sentence "properly" so it will work, stop — that is the bug you would be hiding.**
A version that only works on clean commands is not the product.

**2. Silence is the normal answer.** Most of what you say should produce
nothing. That is deliberate — she is not supposed to leap on every sentence.
So "she said nothing" is only a failure at the steps below that say it is.
Everywhere else, silence is a pass.

**3. Do the whole chain in order.** Six things have to happen for one sentence
to become one text message. If step 3 is broken, steps 4, 5 and 6 cannot pass
and testing them tells you nothing. Each part below checks one link.

The six links:

| # | Link | Plain English |
|---|---|---|
| 1 | **Hear** | The microphone is open and audio is arriving |
| 2 | **Flush** | That audio became a written sentence |
| 3 | **Deliver** | That sentence left the phone and reached the server |
| 4 | **Judge** | A model read it and decided what, if anything, it means |
| 5 | **Hold** | It became a task, waiting for you to say yes |
| 6 | **Reply** | A text message arrived on your phone |

---

## Your one instrument

Almost every check below is read from one screen. Learn where it is now, in the
quiet, so you are not hunting for it later:

> **Settings → Listening → "Find out what listening actually did"**

(Settings is the **three-slider icon in the top right** of the home screen.)

That screen shows, in plain sentences:

| Row | What it means |
|---|---|
| **Listening right now** | Yes / No — and if No, *why*. "You stopped it" and "A call or another app took the microphone" are different problems. |
| **Nothing heard for** | How long since the last sentence was captured. |
| **Times listening started** | How many separate listening sessions today. |
| **Longest stretch hearing nothing** | The big one. A long stretch here is a session that died and never came back. |
| **Words sent** | **How many words became sentences.** This is your link-2 counter. |
| **Lines that did not reach the server** | Your link-3 counter. It only appears if the number is above zero. |
| **Why it stopped or restarted** | The causes, counted. Read this twice. |
| **What the phone reported** | What the audio system actually gave back, as opposed to what was asked for. |
| **The log** | The raw record, newest at the bottom. There is a **"Send me the whole log"** button under it — use it at the end. |

Two habits that make everything else readable:

- **Write down the wall-clock time before you tap anything.** Every number on
  that screen is a duration. Without a start time you cannot anchor any of them.
- **Say a different sentence every time, and put a number in it** — "test line
  one", "test line two". Then a gap in the record is visible instead of being
  guessed at.

---

# PART 0 — Before you say a single word

Seven checks. Five minutes. Skipping these is how people spend an hour
diagnosing a phone that was simply paused.

### 0.1 — Which build is on this phone?

**Look:** Settings → scroll to the very bottom. There is a line reading
`Anticipy v1.1.0 (build NN)`.

**Write the number down.** It goes at the top of whatever you report.

**If there is no "Find out what listening actually did" row** in the Listening
section at the top of Settings, this phone is on **build 76 or earlier** and
does not have the diagnostics screen at all. Stop. Almost every check below
becomes unreadable. Install a current build first — otherwise you are about to
repeat a test that has already failed to produce an answer twice.

### 0.2 — Is she actually listening?

**Look:** Settings → Listening → the sentence at the very top.

- *"I can't hear anything right now."* → iPhone has microphone access switched
  off. There is an **Open iPhone Settings** button right there. It will not ask
  you again on its own; only you can turn it back on.
- Anything mentioning a **pause** → she is paused, possibly from yesterday.
  A pause deliberately survives the app being closed. Tap **"Start listening
  now"**.
- Otherwise, tap the big control on the home screen to start listening.

### 0.3 — Are you signed in?

**Look:** Settings → your account details are filled in, not blank.

**Why this one matters more than it looks:** a signed-out phone still hears you,
still writes every sentence on screen, and **silently throws all of it away** —
no error, no warning, no "waiting to send" message. It is the single most
convincing way for the product to look healthy while doing nothing. Part 3
below catches it, but check now and save yourself the trip.

### 0.4 — Is your phone number saved?

**Look:** Settings → the section headed **"Your number"** → the field showing
something like `+1 604 555 0123`.

**If it is empty, Part 6 cannot pass** and nothing will tell you why. Without a
number she composes the text, sends it nowhere, and the record looks the same
as a successful send. Fill it in.

### 0.5 — Is your computer paired?

**Look:** Settings → **"Your computer"** section → the **Status** row.

| It says | Meaning |
|---|---|
| **Live · seen 12s ago** | Paired and Chrome is running the extension right now. Good. |
| **Away · seen 400s ago** | Paired, but Chrome is closed or asleep. Open Chrome. |
| **Paired** | Paired, but the extension has never checked in. Open Chrome and make sure the Anticipy extension is enabled. |
| **Not paired** | Not paired. There is a **"Set up your browser, step-by-step guide"** link right below it, and a box to type the 6-digit code from the extension popup. |

**You only need this for Part 5 and beyond.** Parts 1–4 and Part 7 work fine
with no computer at all. If you are testing at 1am and the laptop is shut,
run Parts 1–4 and 7 and stop there — that is still a complete, useful result.

### 0.6 — Optional but worth five minutes once: teach her your voice

**Look:** Settings → scroll past Listening and Pendant → a section called
**"Your voice"** → button **"Teach me your voice"**.

Nothing in the product ever suggests this, which is why it has never been done
on any test account — and why every line ever recorded has an empty speaker
field. Without it she cannot tell your promises from someone else's, so anything
you say near another person is judged with that information missing.

Do it once. It takes a couple of minutes and it never leaves the phone.

### 0.7 — What time is it, and how fast do you plan to talk?

Two things will make her go quiet no matter how well everything works:

- **Between 22:00 and 08:00 your local time, she will not start a conversation.**
  Tasks are still created; no text will come. If you want Part 6 to pass, test in
  daylight.
- **Ten sentences inside three minutes makes her think you are in a meeting.**
  She then holds everything for a summary later and cancels any question she was
  about to ask. It takes six to ten minutes of quiet to undo. **Leave at least
  30 seconds between test sentences, and pause for two full minutes before you
  expect a question.** The harder you hammer it, the more certain her silence —
  which is the opposite of what testing should feel like, so watch for it.

---

# PART 1 — Does the phone hear you?

### Step 1.1

**Note the time.** Start listening.

**Say, out loud, in a normal voice:**

> "Okay, test line one, this is me checking whether you can hear anything at all."

**What should happen:** Within about 8 seconds, a new row appears in the small
list of your sentences underneath the waveform on the home screen.

**Where to look:** The home screen, **the list of rows — not the waveform.** The
waveform only means the microphone is open. It keeps moving happily while the
recognizer is stone deaf. It is the least informative thing on the screen and
the easiest to stare at.

**If nothing appears within 15 seconds:**

Go to the diagnostics screen and read **Words sent**.

| Words sent | What it means |
|---|---|
| Still 0 | She never turned audio into a sentence. Continue to Step 1.2. |
| Rising | She heard you; the *screen* is what is stale. That is a display problem, and everything downstream may still be fine — carry on to Part 3. |

### Step 1.2 — Only if Step 1.1 produced nothing

**Do this:** Turn Listen **off**, then **on** again. Say a *different* sentence:

> "Test line two, trying again after restarting."

**If the row appears immediately now:** you have found the failure. **The
recognizer had gone deaf while the phone still claimed to be listening**, and
nothing but your finger could bring it back. Write down the wall-clock time and
how long the session had been running. This is the failure mode that produces
half-day gaps in the record and has been reported twice as "the test didn't
complete".

**If it still produces nothing:** read **"Listening right now"** at the top of
the diagnostics screen. It will name the cause:

| It says | Meaning |
|---|---|
| **No. A call or another app took the microphone** | Something else owns the microphone. Close other audio apps, end any call, try again. |
| **No. Permission was taken away** | iPhone revoked microphone access. Settings → Open iPhone Settings. |
| **No. It failed and could not recover** | The audio engine died. Force-quit the app and reopen. |
| **No. You stopped it** | Listening is simply off. Turn it on. |
| **Not recorded** | The journal cannot answer — usually a phone that restarted. Force-quit, reopen, start again, retest. |
| **Yes** | She believes she is listening and is producing nothing. That is the deaf-recognizer failure again; report it with the time. |

---

# PART 2 — Does it turn sound into sentences properly?

Link 1 says audio arrived. Link 2 is whether it became a *usable* sentence
rather than being chopped in half.

### Step 2.1 — A long sentence

**Say, in one breath, without pausing:**

> "So I've been thinking about the trip in September and I still need to sort out somewhere to stay for the two nights before the conference starts."

**What should happen:** One row, containing roughly the whole thing.

**Where to look:** The row list on the home screen, then the diagnostics screen's
**"Sentences cut off by the clock"** row.

**What it means if it didn't:** A sentence is closed either 2.6 seconds after you
stop talking, or after 8 seconds of continuous speech, whichever comes first. If
you get two or three short rows instead of one, the 8-second ceiling cut you off
mid-thought. Check **"Sentences cut off by the clock"** — it reads like
`3 of 11`. A high proportion there means long thoughts are arriving as fragments,
and a fragment is far more likely to be judged as nothing.

### Step 2.2 — Repeat yourself deliberately

**Say this exact sentence, wait 3 seconds, say it again, wait 15 seconds, say it
a third time:**

> "Test line three, I am saying this three times on purpose."

**What should happen:** **Three rows.**

**What it means if you get two:** The phone dropped a repeat with no trace
anywhere. Report it — a fix for this landed in the repo on 2026-08-24 and this
step is how you confirm it is on the phone in your hand. Two rows means it isn't.

### Step 2.3 — Messy, real speech

**Say, with the hesitations, exactly as written:**

> "Um, yeah, so — no, hang on. What I meant was, can we, you know, move the Thursday thing to the Friday instead?"

**What should happen:** A row appears. It may not be a tidy transcription; that
is fine. **You are checking that disfluent speech is not silently discarded.**

**Where to look:** The row list, and **Words sent** rising.

**What it means if it didn't:** Real speech is being dropped while clean speech
is not. That is worth reporting on its own, because every test anyone has run so
far has been in clean sentences.

---

# PART 3 — Does it reach the server?

This is the link that has been broken. Read this part carefully.

### Step 3.1 — The mark on the row

**Look at the rows** from Parts 1 and 2 on the home screen. Each carries a small
symbol on the left:

| Symbol | Meaning |
|---|---|
| **Dotted circle** | Still on its way to the server. |
| **Filled checkmark** | **The server has it.** This is your pass. |
| **Lightning bolt** | The server has it *and* decided to act on it. That is Part 5 arriving early — good. |

**What should happen:** Within about 5 seconds, dotted circles become filled
checkmarks.

**What it means if a row stays dotted for more than about 15 seconds:** it never
reached the server. Now find out which kind of failure it is.

### Step 3.2 — Which kind of delivery failure

**Look at two places, in this order.**

**First, the home screen**, just under the waveform. Is there a line reading
**"N things you said are waiting for a signal"**?

**Then the diagnostics screen**, for the row **"Lines that did not reach the
server"**.

| Waiting-for-a-signal banner | "Lines that did not reach the server" | What it means |
|---|---|---|
| Yes, N above 0 | Present, rising | **A network or server problem.** She captured everything, could not deliver it, and is holding it on disk to retry. Nothing is lost. Get a better signal and watch N fall to zero. |
| **No banner at all** | **Absent**, while **Words sent** is large | **The phone is signed out.** This is the nastiest failure in the product: every sentence is transcribed, drawn on screen twice, and thrown away without being queued, without an error, and without a single trace in the log. Sign in, and **redo Parts 1–3** — everything you said while signed out is gone for good. |
| No banner | Present | Posts are being refused. Report the number and the time. |

**If rows are checkmarked but the server has no record**, that is not something
the phone can tell you — someone with a terminal needs to check. The command is
in the appendix.

---

# PART 4 — Does the model judge it?

From here on you are testing the brain, not the ears. **If Part 3 did not pass,
stop. Nothing below can produce a meaningful result** — the model cannot judge a
sentence that never arrived.

Leave **at least 30 seconds** between each of these. Say each one only once.

### Step 4.1 — An obligation, said sideways

Not a command. A person thinking out loud, which is how the product is meant to
be used.

**Say:**

> "Ah, I still haven't booked the dentist and it's been three weeks now."

**What should happen:** Within about 30 seconds, something appears on the home
screen — either a card saying she is on it, or a question, or a task waiting for
your OK.

**Where to look:** The home screen feed, and the notification banner if the app
is in the background.

**What it means if nothing happens:** Note it and continue — a single silence is
not conclusive. If **all** of Steps 4.1 to 4.3 produce nothing, see "When
everything is silent" at the end of this part.

### Step 4.2 — Mid-conversation, half a sentence

**Say, as if replying to someone in the room:**

> "Yeah, no, tell them Tuesday works but I need the address first."

**What should happen:** Most likely **nothing** — this is you talking to another
person, and she is supposed to stay out of it. **Silence here is a pass.**

**What it means if she acts on it:** That is a real bug and worth reporting.
She has taken someone else's conversation as your instruction.

### Step 4.3 — Something only worth remembering

**Say:**

> "Sarah's new number ends in 4471, I keep forgetting that."

**What should happen:** Probably nothing visible. That is correct — a fact is
remembered, not acted on.

**Note honestly:** whether she remembered it **cannot be checked from anywhere**.
Memory lives in a local database on the server and is not visible in the app, in
the log, or in any report. So this step can only fail loudly, never pass
visibly. If she creates a *task* out of it, that is the failure.

### When everything in Part 4 is silent

Silence is the default outcome and mostly by design. Before reporting it as a
bug, rule these out:

- **Did you say more than ten sentences in the last three minutes?** She thinks you are in a meeting and is holding everything back. Stay quiet for ten minutes and try one sentence.
- **Did you repeat something you already said today?** She will not raise the same thing twice in 24 hours. Use a genuinely new sentence.
- **Was it four words or fewer?** Short lines are dropped unless they clearly continue something. Say a full sentence.
- **Is it between 22:00 and 08:00?** Tasks are still created but she will not speak first.

If none of those apply and all three steps were silent, report it as **"link 4
silent"** with the three sentences and the times. Someone with a terminal can
tell within a minute whether the lines arrived and what she decided, and the
command is in the appendix.

---

# PART 5 — Does a job get created and held for your OK?

**Needs the computer paired** — check 0.5 again if you skipped it.

The rule this step verifies is the safety rule of the whole product: **she never
does anything in your browser until you have said yes.**

### Step 5.1 — Ask for something that touches the outside world

**Say:**

> "I need to send Alex the updated invoice before the end of the week, can you get that ready."

**What should happen:** Within about a minute a card appears on the home screen
headed **"Ready. Say the word"**, with:

- the task in plain words,
- **"Your exact words"** — your own sentence quoted underneath,
- two buttons: **"Send it"** and **"Not now"**.

**Where to look:** The home screen, in the section for things that need you.

**What it means if it didn't:**

| What you see | Meaning |
|---|---|
| Nothing at all | Either she judged it not actionable, or link 4 is broken. Re-read the "When everything is silent" list above. |
| A card, but no **"Your exact words"** | The task exists but cannot be traced to what you said. Report it — that quote is what makes the approval meaningful. |
| **"Stuck. I need you"** with a text box | She started and hit a wall — a login page, a CAPTCHA, a site that refused. That is a real answer, not a failure of this step. |
| The card appears and then **acts without you tapping anything** | **Stop testing and report this immediately.** It is the most serious possible failure in this product. |

### Step 5.2 — The one to be careful about

**Do not tap anything yet.** Instead, **say out loud:**

> "Actually, hold off on that until I've checked the numbers."

**What should happen:** The card should **stay**. You did not cancel it — you
asked her to wait.

**⚠️ What it probably does instead:** There is a **word list on the phone** that
reads spoken answers and decides whether you called the errand off. It looks for
things like *"cancel"*, *"forget it"*, *"drop it"*, *"leave it"*, *"never mind"*,
*"skip it"*, *"already done"*, *"handled it"*, *"took care of it"* at the start
of a clause. If it fires, the app marks the task **cancelled** and **quotes your
sentence back to you as proof that you called it off** — and the model never
sees the sentence at all.

**This step is testing the word list, not the harness.** Try these too, one at a
time, at least 30 seconds apart, and note what each one does:

| Say this | It should | Report if it |
|---|---|---|
| "Leave it with the concierge if he's not there." | Stay, or become a new instruction | Cancels the task |
| "Don't send it until it's not already booked — go ahead once you've checked." | Stay | Marks it as done-by-you |
| "Stop it from auto-renewing while you're in there." | Stay, or add to the task | Cancels the task |
| "Actually never mind." | Cancel it | Does anything else |

Only the last one is genuinely a cancellation. **Any of the first three
cancelling is a bug, and it is a bug of exactly the kind the product claims not
to have** — a list of words deciding what your sentence meant.

### Step 5.3 — Approve it

**Tap "Send it".**

**What should happen:** The button shows **"Sending…"**, then the card leaves the
"needs you" area, and Chrome on your computer starts doing the thing.

**What it means if it didn't:**

| What you see | Meaning |
|---|---|
| **"That didn't go through, I couldn't reach Anticipy. Nothing was sent."** | The phone could not reach the server. Nothing happened — it is safe to tap again once you have signal. |
| The button spins and never finishes | Report it with the time. |
| Chrome never moves | Go back to Settings → Your computer. If Status says **Away**, the extension is not running — open Chrome. If it says **Live**, the failure is on the computer side and needs someone with the laptop. |

---

# PART 6 — Does a text come back?

**Only meaningful between 08:00 and 22:00 your local time,** and only if
Step 0.4 found a phone number saved.

### Step 6.1

**Say something that needs a decision from you, then go quiet.**

> "I want to take the team out somewhere next Thursday evening, maybe eight of us."

**Then say nothing at all for two full minutes.** Put the phone down. This is
the hard part and it is genuinely required: a question is only sent after
**120 seconds of total silence**, and it expires unasked ten minutes after it
was formed. **A tester who keeps talking guarantees the question dies.**

**What should happen:** A text message arrives on your phone.

**Where to look:** Your normal Messages app. Also the home screen — a question
with no task behind it appears there with a box to answer in.

**What it means if no text arrives:**

| Check | Meaning |
|---|---|
| Did you speak at all inside those two minutes? | Then the question was never sent. Try again and stay quiet. |
| Is it after 22:00 or before 08:00 locally? | She will not start a conversation at night. Nothing is broken. |
| Is your number saved (Step 0.4)? | Without it she composes the message and sends it nowhere, and the record shows a success. This is the single most likely cause. |
| Did you say ten-plus sentences in the last three minutes? | The question was cancelled outright. Wait ten minutes and retry. |
| Does the question appear **on the home screen** but not as a text? | The brain is fine; the text channel is broken. Report exactly that — it is a much narrower bug than "no reply". |

---

# PART 7 — The things that should produce NOTHING

**This part matters as much as the rest.** A harness that acts on everything is
worse than one that acts on nothing, and the only way to see that is to feed it
things it must ignore.

Leave 30 seconds between each. Say each once.

### 7.1 — Someone else's errand

> "Marcus said he still needs to renew his passport before the trip."

**Should produce:** nothing. It is not your task.
**Report if:** she creates a task. She has taken someone else's obligation as yours.

### 7.2 — A hypothetical

> "Just as an example, if someone said 'book me a table at eight', that's the kind of thing I'd want you to catch."

**Should produce:** nothing. You explicitly said it was an example.
**⚠️ Note honestly:** this is currently decided by a **pattern looking for phrases
like "as an example", "hypothetical only", "for reference only", "do not act
on"** — not by the model. A pass here proves the pattern works; it proves
nothing at all about the harness. Test it the other way too:

> "Say I were the sort of person who books tables at eight. I'm not, and I don't want one."

**That** version has none of the marker phrases. If she books a table, you have
found a real failure — and it is the one the pattern exists to hide.

### 7.3 — Reading something out loud

> "Dear Alex, thanks for your note, I'll get the revised figures over to you by Friday, best, Omar."

**Should produce:** nothing. You were reading, not instructing.
**Report if:** she sends an email.

### 7.4 — Dictating at another machine

Say forty or more words of clean instruction-prose, as if voice-typing at a
different assistant. For example:

> "Please go through the landing page and make sure the wording is consistent throughout, and you should update the pricing section so that it matches what we agreed, and change the heading to something shorter, and remove the testimonial at the bottom of the page entirely."

**Should produce:** nothing.
**⚠️ Note honestly:** this is decided by a rule that counts words (forty or more)
and looks for two or more instruction phrases like *"make sure"*, *"please"*,
*"you should"*, *"change the"*. **It also overrides the model's own judgement of
who you were talking to.** So a pass here is a pass for a word count and a
phrase list, not for the harness. The interesting version is a **short** one:

> "Make the heading shorter and drop the testimonial."

Under forty words, so the rule stands down and the model decides. Note what
happens — that result is the real data point.

### 7.5 — Television, or a podcast

Play something with speech in it near the phone for about a minute. Say nothing
yourself.

**Should produce:** nothing.
**Report if:** she creates a task out of it. If you enrolled your voice at Step
0.6, she should be able to tell it is not you — that is what enrollment buys.

---

# PART 8 — Finish properly

**Do this before you put the phone down**, while the evidence still exists. Rows
on the home screen are capped at the last four and are erased if the app
restarts. The log is the only durable record.

1. **Open Settings → Listening → "Find out what listening actually did".**
2. **Screenshot the whole screen**, scrolling if you need more than one shot.
3. Read these rows out loud to yourself and write them down:
   - Listening right now
   - Nothing heard for
   - Times listening started
   - Longest stretch hearing nothing
   - **Words sent**
   - Lines that did not reach the server
   - Everything under **"Why it stopped or restarted"**
4. **Tap "Send me the whole log"** at the bottom and send it to yourself.
5. Write down: your **start time**, your **end time**, and the **build number**
   from Step 0.1.

### What to report

Just this, in plain words:

> Build NN. Started 21:40, finished 22:25.
> **Link 1 (hear): passed / failed at step 1.2.**
> **Link 2 (flush): passed.**
> **Link 3 (deliver): failed — rows stayed dotted, no waiting-for-a-signal banner, Words sent 340.**
> Links 4–6 not testable, link 3 was down.
> Part 7: 7.2 short version created a task — bug.
> Log attached.

That is a complete result even though almost nothing worked. **A failure at a
named link is a finding. "It didn't work" is not.**

---

## Appendix A — Two failures that look identical and are not

**"She heard me and said nothing"** versus **"She never heard me."**

These produce an identical screen and want opposite reactions. The one row that
separates them is **Words sent** on the diagnostics screen.

- **Words sent is rising** → she heard you. Any silence after that is a brain question. Go to Part 4.
- **Words sent is flat** → she never heard you. Nothing about the brain is being tested. Go to Part 1.

Check that row before forming any theory. It costs four seconds and it has been
the missing fact in every previous report.

## Appendix B — For whoever has a terminal

From the repo, after `set -a; . ./.env.local; set +a`:

```
python3 proof/capture_day.py --hours 6 --owner <owner_ref>     # what ARRIVED
python3 proof/outcome_rate.py --hours 6 --owner <owner_ref>    # what came of it
```

Always pass `--owner`. The blended report mixes several accounts, and one
person's busy morning fills another's dead day — the script says so itself.

Read them together:

| capture_day | outcome_rate | Where the fault is |
|---|---|---|
| lines arriving | low rate | The brain. Links 1–3 are fine. |
| **no lines** | n/a | **The ears.** Links 4–6 are untestable; do not draw conclusions about them. |
| lines arriving | good rate | Working. Any complaint is about delivery or wording. |

## Appendix C — Known things that are not your fault

If you hit one of these, it is already on record. Do not spend the night on it.

- **A card with the heading "Quick question for you" and no question underneath.** She formed a question, could not find a quiet moment to ask it, and the header shipped anyway.
- **Nothing about *why* a sentence was ignored, anywhere.** The reason is computed and then discarded — it is never written down. Six different silences are indistinguishable from outside. This is the top item on the fix list.
- **Speaker is always empty** on every line ever recorded, unless you did Step 0.6.
- **The browser extension being served from the website is an old version.** If you set up a computer from that download, you get eight-day-old code. Someone should redeploy.
