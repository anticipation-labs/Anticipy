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

**2. The deployed brain matches no commit in the repo.**
The running worker prints `brain=ac7aa58025b8`. The committed tip hashes to
`97fbc7e70868`, and `ac7aa58025b8` matches **none of the last 20 commits**. The
two newest fix commits — "finishing is not cancelling, one plan not two,
corrections redo the right thing" and "a resume returns to its parked tab" —
were written, tested, committed, and **never deployed**. Deploys here are a
manual command, and it was not run.

That is the whole mystery of "you said you fixed it and it's still broken." It
was fixed. It just was not shipped.

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
- **One lane sits at 80%, not 100%.** Not silence — it still misses sometimes.
- **A malformed model reply is silently treated as "ignore."** One bad JSON
  response and the line is dropped with no retry. I did not change it, but it
  is a real silence source worth closing.
- **Two cards for one dinner still happens** in that transcript.
- **Nothing above is live until it is deployed**, which is the very failure
  this document is about.

---

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
