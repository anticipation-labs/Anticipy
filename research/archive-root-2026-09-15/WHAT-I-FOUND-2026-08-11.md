# What I found when I actually ran it

Omar, you asked me to stop quoting test suites, load the extension in a real
browser, pair it, feed it real conversations, watch where it breaks, and tell
you the truth. I did that. Here it is, shortest true version first.

---

## The one-sentence answer

**The browser agent is not fundamentally broken — it passed every failure you
reported, on the real model, in a real browser. What was broken is that your
fixes were never reaching the thing you were running.**

---

## What I actually did

I loaded `extension/` (0.3.9) unpacked into a real Chromium, paired it to a
backend I control, and gave it jobs on pages I built to reproduce the exact
failures you watched — not paraphrases of them. Every scenario asserts on
**what the website recorded**, never on what the agent claimed. An agent that
says "done" proves nothing; a site that says "reservation confirmed for Tue Aug
11 at 1:30 PM for 3" proves something.

Harness: `proof/hands_battery.py`. Traces of every click:
`proof/hands_battery_traces.json`.

## The result: 8 of 8

| what you watched fail | what happened when I ran it |
|---|---|
| Date field kept snapping back (readonly picker) | Booked Tue Aug 11, 1:30 PM, 3 people |
| Stopped to ask about the site's own 6:30 default | Set its own values: Wed Aug 12, 12:00, 4 |
| Invented "Anticipation Labs" as your last name | Stopped: "I need your first name and last name" — booked nothing |
| Toured Winnipeg for an Earls you never named | Stopped and listed the locations to choose from |
| Retyped into autocomplete forever | Typed, then picked the suggestion |
| Verification code stalled the run forever | Parked, asked for the code, resumed **in the same tab**, site confirmed |
| A readonly native date input | Took the picker route, booked the right date |
| "It's all reservation-shaped" | Filed a support ticket: dropdown, order number, written message |

That last row matters most to you: it is not a restaurant, and the same
machinery did it in 26 seconds with no special handling.

---

## So why does it keep failing for you?

Because you were not running these fixes. Two independent gaps, both measured:

**1. The extension production hands out is six versions old.**
The source is `0.3.9`. The file `setup.html` gives every user —
`/anticipy-extension.zip` — was **`0.3.3`**. I unzipped the live URL and
searched it:

| fix | in production 0.3.3 | in source 0.3.9 |
|---|---|---|
| sees inside iframes (`allFrames`) | **0** | 2 |
| resumes in the parked tab (`resumeTabId`) | **0** | 3 |
| knows what a field already contains | **0** | 1 |
| readonly-picker label | **0** | 1 |

Every time the browser arm misbehaved you were told to re-download that zip and
reload. **That instruction downgraded you** and silently put back every bug you
had just been told was fixed.

Your own Chrome is fine — it is on 0.3.9, synced directly from the repo. The
drift is in the artifact everyone else gets, including you if you ever follow
your own setup page.

**2. The brain running in production did not match the code on this Mac.**
The running worker printed `brain=ac7aa58025b8`; the local tip hashed to
`97fbc7e70868`. Two fix commits that existed here — "finishing is not
cancelling, one plan not two, corrections redo the right thing" and "a resume
returns to its parked tab" — were not what production was running.

**And here I got it wrong, in the exact way this project keeps getting burned.**
I first concluded "production matches no commit at all", because I had only
walked the history on this Mac. It matched perfectly well — a commit that was
on GitHub and had never been pulled down here. Two more people's fixes
("corrections, invented OTPs, prompt-leak plans, evaporating clarifications,
deflected status") were sitting on the remote, live in production, and absent
from the working tree I was reasoning about.

I then deployed my local branch over it, which removed those fixes from
production for about twenty minutes. I caught it when the push was rejected,
rebased my work on top of theirs so both survive, re-ran everything (412 tests
green), and redeployed the merged tree.

I am telling you this because it is the same disease as everything else in this
document, and it bit the person writing the document: **three different places
each believed they were the truth — this Mac, GitHub, and the running
container — and nothing forced them to agree.** That is the actual root cause
behind "fix two, break three". It is not carelessness; it is a missing
check that takes ten seconds.

---

## What I measured in the brain

`proof/silence_rate.py`, production model, sequential runs.

- **Total silences: 0.** The old "one conversation in four vanishes" — a plan
  she understood, deleted by a coin-flip about who you were talking to — is
  genuinely gone.
- But one lane sat at **2 of 5**, and not from silence. I ran it and read the
  transcript. She understood the venue perfectly — "Book dinner for 2 at
  **Cactus Club Park location** tomorrow at 7 PM" is her own wording, twice —
  and the held card still said "Confirm dinner reservation for 2 people
  tomorrow at 7 PM", with no venue. Then she texted you:

  > "Tomorrow at 7 PM for dinner, what restaurant and how many people?"

  Asking for a restaurant you had just named, and a party size you had just
  given. That is your "it asks me what I already told it" — and a card with no
  venue is exactly what sends the browser looking for a restaurant nobody
  named.

**The cause.** When a later sentence re-mentions a plan, the code decided
whether to update the card by measuring only what the new wording **erases**.
Naming the venue drops three near-synonyms ("confirm", "reservation",
"people") — 3 of 7, over the one-third limit — so the better sentence was
refused. It never asked what the new wording **adds**.

**The fix.** Weigh both sides: a re-mention that brings more than it takes is
an enrichment and lands. Verified on the real strings that this accepts the
venue, still refuses the bleaching that once sent the agent to Gmail, and still
accepts a "7 not 8" correction. That lane went **2/5 → 5/5**.

---

## What I changed (all small, all with a test)

1. **A held FYI is no longer destroyed.** Overheard findings respect quiet
   hours (22:00–08:00) — but "held for morning" and "sent" were the same silent
   value, so the caller recorded it as delivered and **the morning never came**.
   Ten hours a day, any overheard lookup that finished was thrown away. That is
   a real source of "I'll text you what I find" → nothing.
2. **The venue reaches the card** (the merge fix above).
3. **The map stops giving wrong advice on readonly date fields** — it used to
   tell the model to write into a field only a picker can set.
4. **`extension/build-zip.sh`** — rebuilds the downloadable zip from source and
   **refuses** to produce one whose version disagrees. This drift cannot
   silently happen again. The zip is now 0.3.9.

Tests: 399 pass (2 new regression guards). All 5 extension suites pass.

---

## The Winnipeg failure is real, and it is worse than anyone thought

One run of the battery showed the merged agent booking at "Vancouver Robson"
for a task that named no location. My first read was "the merge broke it", and
I nearly withheld the release on that.

I measured it instead — both versions alternating in the same minutes
(`proof/ab_unnamed_branch.py`) — and it said the opposite:

```
  merged (0.4.0) refused: 3/3      <- correct
  before (0.3.9) refused: 1/3      <- BOOKED THE WRONG BRANCH, TWICE
```

There was no regression. **The build production had been serving all along was
the one picking restaurants nobody chose, two runs in three.** That is your
Winnipeg failure, reproduced on demand, and it was still shipping today. 0.4.0
is now deployed.

The deeper problem is what this rule is made of. **"Never pick a branch they
did not name" exists only as a sentence in the prompt** (`agent_loop.js:34`).
Nothing in code stops it. Compare the confirm gate, which lives in the job
queue where no model can talk its way past it, or the new OTP guard, which
mechanically refuses a code the owner never gave. A rule written in prose is
obeyed on a *distribution* — 1 time in 3 here — and a rule that spends your
money must not be a matter of the model's mood. **Enforcing this in code is the
single highest-value thing left on the browser side**, and it is the one I would
do next.

## The bug I would fix next (it is your complaint, exactly)

Measuring the deployed brain, one lane fails mostly one way. Here is a real
failing run — one dinner:

```
  her desk:
    [awaiting_confirm]  Plan dinner at Earls in Brooklyn this weekend
    [queued]            Find out which Earl's location for this weekend
    [awaiting_confirm]  Book Earls Brooklyn for 4 people on Saturday at 1 PM

  texts sent (2):
    "i'm ready to book a table at Earls for this weekend; which location and how many people?"
    "for saturday at 1pm at earls in brooklyn, how many people should i say?"
```

Three cards and **two texts about one dinner** — and the second asks how many
people while the card beside it already says *for 4 people*. That is "it asks
me what I already told it" and "why is it texting me twice", from the same root.

**Why.** A recent fix (a good one) stopped a sealed plan going quiet just
because the model happened to word it "plan X" instead of "book X" — it now
judges the substance. The side effect is that the early, vague line becomes a
held card too, and the later precise line does not merge into it: "Plan dinner
at Earls in Brooklyn this weekend" and "Book Earls Brooklyn for 4 people on
Saturday at 1 PM" share almost no words, so the same-plan check does not fire.
Two cards, each with its own idea of what is still unknown, each entitled to
ask you a question.

**This is not something I introduced** — the change that causes it was already
running in production before I started (it is an ancestor of the commit that
was live). But measured side by side it is expensive:

| tree | Earls lane |
|---|---|
| without that change (my branch, earlier today) | 4/4 |
| with it (what is deployed) | **2 of 8** — every failure "got 2 cards", or 3 |

So a fix for a silence that happened *sometimes* introduced a double-card,
double-text that happens *most times* on that conversation. That trade is worth
re-opening, and the answer is not to revert it — the silence it fixes is real —
but to make the second plan MERGE into the first.

It is the biggest remaining quality bug, it is squarely what you keep shouting
about, and it is well-defined: **one plan must be one card.** The same-plan
test needs to match on what identifies a plan — the venue, the day, the person
— not on how many words two phrasings happen to share. A blunt version of the
invariant would already help: *never hold two unconfirmed cards that name the
same place.*

I did not attempt it tonight. It is the most delicate code in the system, it
would need the same interleaved A/B the other two fixes got, and starting that
at the end of a long session — then going quiet — is exactly the pattern that
has burned you. It is the first thing I would pick up.

## What is still wrong — the honest list

- **Real hostile sites are still unproven.** My pages reproduce the failure
  *shapes* faithfully, but they are small and well-behaved. Cloudflare, a
  200-element navigation, cross-origin widgets and React inputs that fight back
  are not in this battery. This is the biggest remaining unknown, and it is the
  gap between "the logic is right" and "it works on earls.ca".
- **The model does not always obey the map.** After I fixed the readonly label,
  the model *still* tried to write into the field first and learned from the
  refusal. The map telling the truth is necessary but not sufficient; the
  executor's refusal is what actually saves the run.
- **Neither lane is at 100%.** It still misses sometimes — just not by going
  silent any more.
- **Two cards for one dinner still happens** in that transcript: one "Plan
  dinner for tomorrow" and one "Confirm dinner reservation…", for a single
  plan. I saw it and did not fix it.
- **I did not touch the iPhone app at all.** Nothing here says anything about
  what you see on your phone.
- **The pendant is untouched** — this was all phone/brain/browser.
- **What I fixed, I fixed on the shapes I could reproduce.** Where the real
  world is nastier than my pages, these fixes will be necessary but not
  sufficient.

---

## What is live now

Verified, not assumed:

- **The brain running in production is the code in the repo.** The worker
  prints `brain=fd8a4d8fd029`; the merged tree hashes to the same. That
  sentence has not been true for a while.
- **The zip production hands out is built from the source** (was 0.3.3).
- **This Mac, GitHub and production are the same commit** — 0 ahead, 0 behind.
- The database is still sealed to strangers (403), backend healthy.

## The ten-second check that would have prevented all of it

`proof/is_it_live.py`. It asks the three places whether they agree and names
what to do when they do not:

```
  git      : 0 ahead, 0 behind github/pendant-system
  brain    : local fd8a4d8fd029   live fd8a4d8fd029
  extension: source 0.4.0   served 0.3.9
```

It found a real drift within a minute of existing — the merge had bumped the
extension to 0.4.0 while production still served 0.3.9. Run it before you
believe anything is shipped, and run it before you deploy, because "behind"
means someone else's fixes are live and you are about to deploy over them.

## The pattern worth fixing forever

The recurring problem was never that the work was wrong. It is that **"fixed"
and "shipped" were allowed to be different things, and nobody could tell them
apart from the outside.** A commit was treated as a delivery. The worker prints
a fingerprint precisely so this is checkable — and it was not being checked.

Two cheap habits close it permanently:

- After any brain change: deploy, then compare the worker's printed
  `brain=<hash>` against the same hash computed on the commit you believe you
  shipped. Different means it is not live, no matter what the deploy said.
- After any extension change: run `sh extension/build-zip.sh` and commit the
  zip. The script now fails loudly rather than shipping a stale one.
