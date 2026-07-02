> ⚠️ **SUPERSEDED AS AUTHORITY — 2026-07-02.** The living truth is **`CANON/00_START_HERE.md`**.
> Distilled into CANON/01 + 02 + 04. Kept whole as the deep reference — the use-case library and the
> feel/measurement record here remain the richest material in the repo.

# ANTICIPY — THE SOURCE OF TRUTH

> The single canonical document. What Anticipy is, how it **actually** works, the deep onboarding,
> 120 real use cases, what "fully finished" genuinely means (integration-first), where we honestly
> are, and the plan. Supersedes every other status/mission/done doc. Captured 2026-06-24 from Omar's
> whiteboards + direct corrections. **If anything is wrong, fix it HERE — never fork a parallel doc.**

---

## 0. THE ONE SENTENCE

Anticipy is a **proactive personal assistant — "Donna from Suits"** — that **listens to your real day**,
catches the things you get **told or asked to do**, and quietly **handles them inside your own real
systems** (your logged-in browser, calendar, email, voice), checking with you like a sharp human
before anything that matters. The goal: it genuinely runs **~50% of your workload, end to end.**

---

## 1. HOW IT ACTUALLY WORKS (the model — get this right)

1. **It LISTENS — ambient.** Input is your *real life*: conversations, what people tell/ask you to do,
   the commitments you make out loud. Typed transcript / MP3 now; a pendant later.
   - ❌ NOT a todo app. Nobody says "ugh traffic, remind me to call the dentist."
   - ✅ Real: a client says *"can you get me the contract before Friday?"* → Anticipy catches the task.
2. **It INFERS the real tasks** from natural speech, and **silently lets non-tasks pass** — venting,
   sarcasm, hypotheticals. It does not announce "ignored." It just doesn't act. **Acting on a vent is
   the cardinal sin.**
3. **For each real task it decides:** handle it / prepare-and-ask / stay silent — by confidence,
   reversibility, and the trust dial.
4. **It TALKS like a human, never like a system:**
   - Send (email/text) → it **drafts it**, then *"Got the email to Sanket ready — okay to send?"*
   - It goes the extra mile: does the prep, hands you the finished thing for one tap.
5. **It ACTS in YOUR real systems via the browser** — navigating, opening items, clicking, *operating
   like a human* (NOT screenshotting one screen). Browser-only by design; no per-service OAuth.
   Plus voice/SMS to reach you and close the loop ("draft's ready", "made the calendar hold").
6. **It REMEMBERS everything** — who matters, your preferences, open loops — and compounds over time.
7. **Trust dial: Full-Send / Regular / Limited.** Money + irreversible **always** confirm, every mode.

---

## 2. ONBOARDING — the full agentic flow

> Onboarding is not a setup wizard. It is the first time the whole product runs — the browser agent, the proactive engine, the voice line, and memory, all at once, on the user's real life. A normal app's onboarding ends when the account is created. Anticipy's onboarding ends when it knows you well enough to do half your job. The deliverable of onboarding is not "connected accounts" — it is a rich, structured profile that makes every later action sharp instead of generic.

The guiding contrast, stated up front so nothing in this section drifts: **the cardinal failure of a fake agent is to open an account, screenshot the first screen, scroll once, and declare it "reviewed."** That tells you a Gmail inbox exists. It tells you nothing about who the user is. Anticipy onboarding does the opposite — it goes *in*: it opens individual emails and threads, scrolls and reads them to the end, opens calendar events and reads the invite bodies and attendee lists, reads the contacts, clicks into whatever real tools and CRMs it discovers along the way, follows the people and threads that clearly matter, and decides what to look at next based on what it just found. It explores like a sharp new chief of staff who's been given your logins and a week to "learn the job" — not like a script ticking boxes.

### 2.0 Design principles for the whole flow

- **Layered, not one-shot.** Onboarding alternates between *autonomous exploration* (the scrape) and *human conversation* (the phone call). Each scrape feeds the next call; each call re-aims the next scrape. The loop runs until confidence is high enough to be useful, not until a fixed number of steps complete.
- **Earned autonomy.** The first pass is guided and hand-held — the user is watching, granting access, watching it work. By the last pass the agent is operating largely on its own and only surfacing what it can't resolve. Trust and depth rise together across the layers.
- **Infer first, ask only for the gaps.** Every phone call is short because the scrape did the heavy lifting. The agent never asks a question it could have answered by reading. It calls to confirm what it inferred, fill what it genuinely couldn't, and set boundaries that aren't discoverable (autonomy level, money rules, do-not-touch zones).
- **Read-only and reversible during onboarding.** Onboarding *catalogs*; it does not act on the world. It drafts nothing to third parties, sends nothing, changes nothing in the user's accounts. The only outbound contact is the agent → user phone call. This is what makes deep exploration safe to grant.
- **Talks like a person the entire time.** Status updates, the calls, the welcome — all in the warm, human Donna voice. Never "SCRAPE LAYER 2 COMPLETE." Always "Okay — I went through your last month of email and your calendar. Got a few things to run by you."

---

### 2.1 New user → Welcome

**What they see.** A single quiet screen, editorial not dashboard-y. One line of promise, not a feature list:

> *"I listen to your day and quietly handle about half of it. Give me a way in, and one call, and I'll learn the rest myself."*

Below it, **the one move they make**: connect at least one real account (Google first — Gmail + Calendar + Contacts in one consent), and enter the **phone number** the agent will call them on. That's the entire ask. No profile form, no "tell us about yourself," no preference toggles, no tour. Everything a setup wizard would interrogate the user for, Anticipy will instead *go and find out itself.* The implicit contract on this screen: **you give access + a number; I do the work of getting to know you.**

**The promise made concrete.** Under the connect button, one honest line about what's about to happen and what won't:

> *"I'll read through your real inbox and calendar to learn how you work — who matters, what's open, how you write. I won't send anything, change anything, or message anyone. When I've got the lay of the land, I'll call you."*

That sentence does three jobs: it sets the expectation that this is deep ("read through… to the end," not "glance"), it disarms the fear that comes with handing over an inbox ("won't send, change, or message"), and it frames the phone call as the natural next beat rather than a surprise.

**The one move, mechanically.** Connect runs through the browser the same way every later action will — the user logs into their own Google in their own session; Anticipy rides that logged-in session. No API keys, no OAuth scopes to a server, no "Anticipy would like permission to manage your email." Browser-only by design. The moment consent lands, the screen changes to a calm live status — not a spinner, but a running, human narration of what the agent is actually doing ("Reading your recent threads…", "Found a recurring weekly with someone named Priya — reading those…"). The user can close the tab; the work continues server-side and the agent will reach them by phone.

---

### 2.2 The layered scrape ⇄ phone-call loop

The spine of onboarding is a loop that alternates exploration and conversation:

```
Layer-1 scrape (guided)
        ↓
   Phone Call 1   ← warm intro, confirm the obvious, set autonomy
        ↓
Layer-2 scrape (deeper, autonomous, re-aimed by Call 1)
        ↓
   Phone Call 2   ← fill real gaps, confirm the subtle finds
        ↓
Layer-3 scrape (only if needed — targeted, fully autonomous)
        ↓
Final confirmation call ← "here's what I learned; here's how I'll run"
```

Each stage below specifies *what happens, why it happens there, and what it produces.*

---

#### Layer-1 scrape — guided, broad, "get the shape of the life"

**Why first / why guided.** The user just granted access and is (often) still watching. The goal of Layer-1 is not depth — it's *map the territory and earn a confident opening for Call 1.* It also establishes, visibly, that the agent actually reads (not screenshots), so the first phone call lands as "wow, it really looked" instead of "it ran a script."

**What it does, concretely:**
- Opens Gmail and reads the **most recent ~2–4 weeks** broadly: skims the inbox, then *opens the threads that look like they carry weight* — anything with many replies, anything from a frequently-recurring sender, anything that looks like a live commitment ("can you send me…", "are we still on for…", "did you get a chance to…"). It reads these threads **to the bottom**, not just the preview.
- Opens **Calendar** for the surrounding window (last 2 weeks, next 4): opens individual events, reads the **titles, bodies, attendee lists, locations, and attached docs/links**. A recurring 1:1 tells it a relationship; a flight confirmation tells it travel; "Q3 board" tells it stakes.
- Opens **Contacts**: who's starred, who's labeled, who recurs across email and calendar — the first cut at *who matters.*
- **Adaptive even at Layer-1:** if it opens a thread and sees a Notion link, a Linear ticket, a Calendly, a Stripe receipt, a CRM notification (HubSpot/Salesforce), it *notes the tool exists and where the door is* — it doesn't necessarily go in yet, but it flags it as a Layer-2 target.

**Explicit contrast with first-screen screenshotting.** A fake agent here would: open Gmail, capture the inbox list, report "Gmail: connected, ~40 unread." Anticipy instead comes out of Layer-1 able to say a true sentence about the *content* of the life: *"There's an active thread with a client named Marcus about a contract that's waiting on you; you've got a recurring Tuesday 1:1 with Priya; and there's a Notion workspace your team seems to live in."* One of those is a status check. The other is the beginning of a chief of staff.

**What Layer-1 produces:** a *provisional* profile — a candidate list of important people, a first read of the user's role/profession (inferred from the content, not asked), the tools spotted, a handful of obvious open loops, and a first impression of communication style (formal vs. casual, long vs. terse, emoji or not, sign-off). Crucially it also produces a **list of uncertainties and gaps** — the agenda for Call 1.

---

#### Phone Call 1 — the warm intro (guided, hand-held)

**Why a call, why now, why this one is the most hand-held.** This is the user's first experience of the agent as a *person.* It has to (a) prove it actually looked, (b) feel human enough that they relax, (c) confirm the few high-value things it inferred, and (d) set the one thing it cannot discover by reading: **how much rope to give it.** It's the most guided call because the user is new and the relationship has no trust yet — so the agent leads gently, explains as it goes, and asks more than it assumes.

**Tone.** Warm, brief, can't-tell-it's-AI. Natural speech, contractions, listens and reacts. Not a survey read aloud.

**What it actually says / asks (the structure):**
1. **Proof it looked** (earns the rest of the call): *"Hi — it's Anticipy. I just spent a bit going through your inbox and calendar to get up to speed. I think I've got the shape of it, but let me check a few things with you."* Then one concrete, correct observation — *"Looks like Marcus is a client and there's a contract sitting with you?"* — so the user immediately believes it read.
2. **Confirm the people who matter:** reads back the top few and asks who else belongs / who to ignore. *"The people I'd guess matter most are Priya, Marcus, and someone named Dana — am I right? Anyone I'm missing, or anyone you'd tell me not to bother with?"*
3. **Confirm role/context it inferred** (don't ask "what do you do" — confirm what it deduced): *"From your calendar you look like you're running a small team — fundraising in the mix? Want me to keep an eye on the investor threads?"*
4. **Set the autonomy dial** — the irreplaceable purpose of Call 1: explain the three modes plainly and let them choose. *"Three speeds. Full-send: I just handle things and tell you after. Regular: I do the prep and check with you before anything goes out. Limited: I suggest, you do. Most people start at Regular — want to start there?"*
5. **Set the hard rules** that aren't discoverable: *"Two things I'll always check with you on no matter what — anything involving money, and anything I can't undo. That okay?"* And capture do-not-touch zones (*"anything you'd rather I never read or touch — a personal account, certain people?"*).
6. **Permission to go deeper:** *"To really be useful I'd like to go a level deeper — actually open your tools, follow the important threads further back. Good to do that?"* This is the explicit handoff into Layer-2's increased autonomy.

**What Call 1 produces:** confirmed people-who-matter, confirmed role/context, the **autonomy level**, the **money + irreversible always-confirm rule** locked in, do-not-touch zones, and a re-aimed mandate for Layer-2 ("go deeper on the investor threads, open the Notion, ignore the personal stuff").

---

#### Layer-2 scrape — deeper, autonomous, re-aimed by the call

**Why second / why more autonomous.** The user just granted "go a level deeper" and isn't necessarily watching anymore. Layer-2 is where the *chief of staff* behavior really shows: longer history, into the tools, following relationships and threads, building the real catalog. It's adaptive — Call 1 told it where to dig (investor threads, the Notion) and what to skip (the personal account), so it spends its budget where the value is.

**What it does, concretely (the depth that defines the product):**
- **Goes back further** in email — months, not weeks — for the *people and threads that matter*, reading whole conversations end-to-end to reconstruct **open loops** (what's promised, what's owed to the user, what's stalled), **cadence** (how often they talk, who initiates), and **history** (the backstory of each key relationship).
- **Opens the tools it discovered and genuinely uses them as a human would.** If it found a **Notion** workspace: it opens it, navigates the sidebar, reads the docs the team actually lives in, learns the project names and vocabulary. A **CRM** (HubSpot/Salesforce/Pipedrive): it opens deals/contacts, reads the pipeline, learns the customers and stages. **Linear/Jira/Asana:** reads the active work and who owns what. **Calendly/Stripe/Docs/Drive:** reads the booking patterns, the receipts, the documents linked from the important threads. It *clicks in and reads*, the same browser way it will later act.
- **Follows the graph adaptively.** Reading a thread with Marcus surfaces a contract doc → it opens the doc → the doc references a "renewal in Q3" → it checks the calendar for anything Q3 → finds nothing → that becomes a *gap to raise.* This is the loop that a fixed script can't do: **each find decides the next click.**
- **Builds the real catalog** for every important person: relationship, role, how the user talks to them specifically (different register for a client vs. a cofounder), what's open with them, last contact, what they tend to ask for.
- **Nails communication style with evidence:** not "casual" as a guess but patterns pulled from real sent mail — greeting style, length, formality by recipient, common phrases, sign-offs, response speed, what they delegate vs. answer themselves.

**Contrast, again, sharpened.** First-screen screenshotting would, at best, list which apps are connected. Layer-2 comes back with: *"Your real open loops are the Marcus contract (you owe redlines), a reference call you promised Dana three weeks ago that never got scheduled, and an invoice in Stripe that's 18 days overdue. Your team's work lives in Notion under the 'Atlas' project. You write clients in full paragraphs and your cofounder in one-liners."* That is the difference between a connector and a colleague.

**What Layer-2 produces:** the *real* structured profile — people-who-matter with full dossiers, the tool/system inventory with what's inside each, a concrete open-loops list with status, an evidence-based communication-style model, and a fresh, smaller set of **genuine gaps** (the things reading *couldn't* resolve) for Call 2.

---

#### Phone Call 2 — fill the real gaps, confirm the subtle finds

**Why this call / why less hand-held.** By now the agent has done a lot of real work and the user has heard it be right once. So Call 2 is shorter, more peer-to-peer, and mostly about **the things reading genuinely can't tell you** — intentions, priorities, and the handful of ambiguities the deep dive surfaced. The agent leads with competence, not explanation.

**What it asks (only the irreducible gaps):**
1. **Confirm the subtle, high-value finds:** *"A couple things I caught — you promised Dana a reference call about three weeks ago and it never got on the calendar; and there's a Stripe invoice 18 days overdue. Want me to tee up both?"* (Note: *tee up*, not *do* — money + sending still confirm.)
2. **Resolve true ambiguities the graph couldn't:** *"The Marcus contract mentions a Q3 renewal but there's nothing on your calendar for it — is that real, and should I be tracking it?"*
3. **Priorities reading can't reveal:** *"Of everything open, what actually matters most to you right now — is it closing Marcus, or the fundraise?"* This tunes the proactive engine's ranking, which no inbox can tell it.
4. **Preferences that only matter once it's acting:** *"When I draft emails for you, want me to match how you already write — paragraphs for clients, short for the team — or tighten everything up?"*
5. **Calibrate autonomy with a real example:** *"Something like that overdue invoice — want me to just send the nudge next time, or always run it by you first?"* This turns the abstract dial from Call 1 into concrete, situation-level rules.

**What Call 2 produces:** resolved ambiguities, a **priority ranking** for the open loops, drafting/style preferences confirmed against real examples, and situation-level autonomy rules (e.g., "auto-nudge overdue invoices ≤ \$X; always confirm above; never auto-send to clients"). After this call the profile is usually *complete enough to run.*

---

#### Layer-3 scrape — only if needed, targeted, fully autonomous

**Why conditional.** Most users are done after Layer-2 + Call 2. Layer-3 exists for the cases where Call 2 *opened* something rather than closed it — a tool the agent hadn't entered (e.g., "actually most of my work is in Salesforce"), a relationship the user flagged as important that the agent under-read, or a priority that points at history it hasn't covered. It's fully autonomous (no hand-holding left to do) and **surgical**: it goes only where Call 2 pointed, not broad again.

**What it does:** the same deep, adaptive exploration as Layer-2 but narrowed to the specific targets Call 2 surfaced — enter the named tool and read it properly, go deeper on the named person, reconstruct the named priority's full history. It produces the *last* missing pieces of the profile and, ideally, **no new gaps** — just confirmations for the final call.

---

#### Final confirmation call — "here's what I learned, here's how I'll run"

**Why a final call.** Onboarding shouldn't end with a silent "ready." It ends with the agent *reflecting the user back to themselves* — proof of how well it now knows them — and stating the operating contract it will run under, so the first real proactive action a day later feels expected, not startling.

**What it says:**
1. **The mirror** (the payoff that makes the whole flow worth it): a tight, accurate read-back. *"Okay, here's where I landed. The people I'm watching: Priya, Marcus, Dana, your cofounder Sam. Your priority right now is closing Marcus, then the raise. Open loops I'm holding: the contract redlines, Dana's reference call, the overdue invoice. Your work lives in Notion under Atlas and your pipeline's in HubSpot. And I'll write like you — long for clients, short for Sam."*
2. **The operating contract:** *"I'll run at Regular — I'll do the prep and check before anything goes out. Money and anything I can't undo, I always ask. I'll never touch your personal account."*
3. **What happens next, set expectation:** *"From here I'll just be paying attention. When something needs you, I'll have it mostly done and I'll come to you for the last tap. First thing you'll probably hear from me on is that overdue invoice."*
4. **The open door:** *"If I ever get something wrong, just tell me — I'll remember."* (Establishes the correction loop that compounds memory over time.)

**What the final call produces:** the user's explicit "yes, run" — and the psychological handoff from *setup* to *living with an agent.*

---

### 2.3 The arc across the layers (autonomy + depth rising together)

| Stage | Who's driving | Depth | Autonomy | Purpose |
|---|---|---|---|---|
| Layer-1 scrape | Agent, user often watching | Broad, recent | Low (guided) | Map the life, prove it reads |
| **Call 1** | Agent leads, explains a lot | — | Set the dial | Intro, confirm obvious, get permission to go deep |
| Layer-2 scrape | Agent, user not watching | Deep, into tools, follows the graph | High | Build the real catalog |
| **Call 2** | Peer-to-peer | — | Calibrate by example | Fill true gaps, set priorities + situational rules |
| Layer-3 scrape | Agent, fully solo | Surgical, targeted | Highest | Close the last named gaps |
| **Final call** | Agent reflects + commits | — | Contract stated | Mirror, set operating contract, hand off |

The shape: **the agent starts hand-holding and ends self-driving; it starts broad and shallow and ends deep and precise; the user starts watching and ends trusting.** Each call hands the next scrape a sharper mandate; each scrape hands the next call a shorter, smarter set of questions.

---

### 2.4 What onboarding produces — the structured profile

The artifact that makes the proactive engine and the browser agent immediately useful on day one. Stored in memory, structured, and continuously updated thereafter:

- **People-who-matter** — for each: name, relationship, role, why they matter, cadence/last contact, what's open with them, and the *per-person communication register* (how the user talks to *this* person specifically).
- **Role & context** — inferred profession and current focus (e.g., "founder, small team, mid-fundraise"), so the engine reads new speech in the right frame.
- **Tools & systems inventory** — every real system discovered (Notion/HubSpot/Linear/Stripe/Drive/Calendly…), *with what's inside each* (project names, pipeline stages, vocabulary) and where the door is, so the browser agent can go straight back in to act.
- **Open loops** — the live list with status, owner, and **priority ranking** from Call 2: what's promised, what's owed, what's stalled.
- **Communication-style model** — evidence-based: length, formality by recipient, greetings/sign-offs, common phrases, response cadence, what the user answers vs. delegates — so drafts sound like the user, not like a bot.
- **Trust & rules config** — the autonomy dial (Full-Send/Regular/Limited), the always-confirm rules (money + irreversible), situational rules from Call 2, and do-not-touch zones.
- **Open questions** — the residual gaps the agent will keep listening for in real life rather than asking about, closing them over time.

This profile is the reason the *first* proactive moment after onboarding lands as "how did it know to do that?" instead of "what is this?" — onboarding didn't connect accounts; it learned the job.

## 3. USE CASES (100+, across every profession)

> Real ambient triggers (what the user is told/asked), in the corrected model. Vents are never acted on;
> money is a warm ask; sending is draft-then-ask; the agent actually explores and operates the browser.

### Startup founder / CEO

**1. Term sheet just landed mid-call**
- *Heard:* Partner at the lead fund, on a quick call: "Okay, we're sending over the term sheet tonight — $4M on a $20 post, standard 1x non-participating, but heads up there's a pro-rata side letter and a 20% option pool refresh we'll want pre-money." You, after hanging up, to your cofounder: "Twenty percent pool pre-money is rough. Also I'm exhausted, I cannot do another diligence cycle."
- *Catches:* Inbound term sheet arriving tonight; flagged deal terms (pool refresh is pre-money, pro-rata side letter, 1x non-part). Ignores the "I'm exhausted / cannot do another cycle" vent — that's emotion, not a task.
- *Explores & acts:* Opens Gmail in your logged-in session, searches `from:(thefund.com) subject:(term sheet OR LOI)` plus the partner's name to confirm whether it's already in; watches the thread. Opens your Drive, finds the prior SAFE/cap table (`Cap Table v` files), reads the current fully-diluted shares and existing pool, and computes what a 20% pre-money pool refresh does to your founder ownership vs. a post-money pool — the real dilution gap. Cross-references memory: your stated floor was "don't go below 60% combined founder after this round." Pulls your past notes on this partner. Drafts a one-page term comparison (their terms vs. your last round vs. market) in a Doc.
- *Checks in:* "The 20% pool being pre-money costs you ~4 extra points of dilution vs. post-money — that's real money. Want me to draft your pushback to [partner], or hold until you've read the actual sheet?" Drafts the email but does not send.
- *Done:* Term sheet thread flagged and waiting, dilution math in a shared Doc, a pushback email sitting in drafts for your one tap.

**2. Warm intro the investor actually asked for**
- *Heard:* Over coffee, an angel on your cap table: "You should really talk to Priya at Bessemer for your Series A — she did [competitor's] infra round and loved that space. Tell her I sent you, I'll back you up."
- *Catches:* A real, offered warm intro to a named investor (Priya, Bessemer) with the angel volunteering to vouch. The angel said *he'd* back you up — so the cleanest path is a forwardable intro, not you cold-emailing.
- *Explores & acts:* Searches your Gmail and LinkedIn (in your session) for any prior contact with Priya or Bessemer to avoid a double-intro embarrassment. Reads Bessemer's recent infra investments and Priya's portfolio so the note isn't generic. Cross-references memory: your current raise stage, latest metrics (ARR, growth, burn) and your standard one-line positioning. Drafts a tight forwardable blurb (the "below the line" paragraph the angel can paste), tuned to Priya's thesis, plus a separate short note *to the angel* making it effortless for him to forward.
- *Checks in:* Drafts both — "Here's the forwardable blurb for [angel] to send Priya, and the nudge to him. Okay to send the nudge?" Nothing goes out before your yes.
- *Done:* Forwardable intro drafted to Priya's actual interests, the vouching nudge to the angel queued, your prior-contact risk checked — one tap to ship.

**3. The "send the deck" promise you'll forget**
- *Heard:* End of a partner meeting, the other founder: "This was great — can you send over your latest deck and maybe your integration API docs so my eng team can take a look? We're slammed this week so no rush." You, walking out, muttering: "Everyone says no rush and means tomorrow."
- *Catches:* Two real deliverables promised — current deck + API/integration docs — to a specific partner. Ignores the cynical "no rush means tomorrow" aside.
- *Explores & acts:* Opens Drive, locates the most recent deck (checks modified dates and version names, not just the first hit — avoids sending last quarter's), confirms it's the partnership/external version not the internal board deck. Finds the public API docs link (Notion or your docs site) and verifies it actually loads and isn't behind staff-only auth. Cross-references memory of this partner: what they care about (the integration), so it leads with that. Drafts the follow-up email attaching the deck and linking the docs, with a one-line reminder of the next step you two agreed on.
- *Checks in:* "Drafted the follow-up to [name] with the partnership deck (v[X], updated [date]) and the API docs link — I confirmed the link is public, not staff-gated. Okay to send?"
- *Done:* Correct deck + working public docs link in a drafted email, partner context baked in, waiting on your send.

**4. The hire everyone keeps slipping on**
- *Heard:* In standup, your eng lead: "We genuinely can't ship the enterprise SSO work without a second backend person. The two candidates in the pipeline have both been sitting in 'final round' for like two weeks." Then, half-joking: "Or we just never sleep again, that works too."
- *Catches:* Two backend candidates stalled at final-round for ~2 weeks, blocking enterprise SSO. Ignores the "never sleep again" joke.
- *Explores & acts:* Opens your ATS (Ashby/Greenhouse) in your session, pulls up the backend pipeline, opens *each* stalled candidate's profile — reads the last interview feedback, identifies exactly who owns the next step and what's missing (a scorecard not filled in, a missing reference, an unsent offer). Checks Gmail for the latest thread with each candidate to see who's gone quiet on whom. Cross-references your calendar for open slots this week to propose final-round or debrief times. Notes if either candidate has a competing offer mentioned in the notes (urgency signal).
- *Checks in:* "Both are stuck on *your* side: [candidate A] needs the debrief decision (3 of 4 scorecards in, [interviewer] hasn't filled theirs), [candidate B] is waiting on you to confirm comp before an offer goes out. Comp is money — want me to draft the offer terms for your review, or set the debrief first?" Offer = always confirmed.
- *Done:* Each blocker named with the owner, debrief slots proposed on your calendar, offer drafted but parked pending your sign-off.

**5. Vendor contract auto-renewing at a worse rate**
- *Heard:* Your ops person in passing: "Oh by the way, the Datadog renewal is coming up — I think they bumped the price and it auto-renews. And honestly our AWS bill is also insane lately but that's a whole other thing."
- *Catches:* Datadog contract auto-renewing soon, likely at a higher price — a real, time-boxed money decision. Notes the AWS-bill comment as a flagged-but-separate item, doesn't conflate it into the Datadog task.
- *Explores & acts:* Searches Gmail for the Datadog renewal/invoice thread to find the actual renewal date and the new vs. old rate. Logs into your Datadog account billing page (your session) to read the current plan, seats, and committed usage, and checks whether you're paying for host/seat counts you no longer use. Cross-references memory: last year you negotiated 15% off at renewal — so there's precedent. Pulls the AWS cost console quickly just to size the side comment for later, without acting on it.
- *Checks in:* "Datadog auto-renews [date] at [new price], up [%] from last year — and you're paying for [N] unused host seats. This is money, so your call: want me to draft a renewal-negotiation email to your rep (you got 15% off last time), or just downgrade the unused seats first?" Nothing changed on the account without you.
- *Done:* Real renewal date + price delta surfaced, unused-seat waste quantified, a negotiation email drafted, AWS noted as a separate open loop — your decision on the money.

**6. Investor update you keep promising "this week"**
- *Heard:* On a call, your seed lead: "No pressure, but the LPs are asking how the portfolio's doing — whenever you get a sec, the monthly update would be great. Last one was, what, March?"
- *Catches:* The monthly investor update is overdue (last one March), a specific investor is gently asking. Real recurring deliverable, real recipient.
- *Explores & acts:* Finds your last investor update (Gmail "sent" or your update tool like Visible/DocSend) to match format, tone, and the metrics you track. Pulls fresh numbers from where they actually live — Stripe dashboard (MRR, churn, new logos), your analytics, the cap-table/runway sheet in Drive for current cash and months of runway. Cross-references the *asks* you made in the last update ("intros to fintech CFOs," "looking for a senior designer") and checks whether any landed, so it can close those loops. Drafts the full update in your voice: highlights, lowlights (you always include lowlights), metrics, and two specific asks.
- *Checks in:* "Drafted the [month] update — MRR up to $X, churn ticked up to Y% (flagged it honestly like you do), runway N months, and I re-upped the designer ask since it's still open. Want to review before it goes to the list?"
- *Done:* A complete, on-brand investor update drafted with live numbers and last month's loops closed, sitting for your review before it hits the list.

**7. The reference call that could kill a hire**
- *Heard:* Your head of sales, after a debrief: "I want to pull the trigger on [candidate] for the AE role, but something felt off about why he left [prev company] so fast. Can we just... check before we commit?"
- *Catches:* A pre-offer reference/background gut-check on a specific senior sales candidate, specifically around a short tenure at a named prior company. Irreversible-adjacent (an offer is about to go out).
- *Explores & acts:* Opens the candidate's profile in the ATS, reads resume tenure dates and any references already supplied. Cross-checks LinkedIn (your session) for the actual dates at the prior company and whether the story matches. Pulls the interview notes to see if anyone already probed the "why'd you leave" question and what he said. Searches your network in LinkedIn for *mutual* connections at the prior company who could give a candid back-channel reference, and drafts the outreach to the best one. Does *not* contact anyone yet.
- *Checks in:* "His LinkedIn shows 7 months at [company], the resume says 11 — worth a back-channel. You've got two mutuals there: [name] (you worked together at [X]) is the strongest. Want me to draft the back-channel ask to [name]?" Offer stays parked until this resolves.
- *Done:* The tenure discrepancy surfaced with evidence, the best back-channel contact identified, a discreet outreach drafted — offer correctly held until you decide.

**8. Two intro requests pulling you opposite ways**
- *Heard:* A founder friend texts, read aloud: "Hey can you intro me to your contact at Stripe? And also — totally separate — that recruiter you used, the one who found your VP Eng, what's their info?" You: "I love this guy but he asks for an intro every single month, lol."
- *Catches:* Two real, distinct asks — (1) a double-opt-in intro to your Stripe contact, (2) sharing your recruiter's info. Ignores the affectionate "asks every month" jab.
- *Explores & acts:* Searches Gmail/LinkedIn for your actual Stripe contact to confirm who it is and how warm the relationship really is (last interaction date) — because a cold "intro" damages you. Drafts a *double-opt-in* check to the Stripe contact first (never blind-CCs), with a crisp line on why your friend is worth their time. Separately finds the recruiter's contact card / email signature in your inbox and drafts the handoff to your friend. Cross-references memory that this friend is a frequent asker, so it keeps your asks to your Stripe contact appropriately rationed.
- *Checks in:* Two drafts — "For Stripe I'm doing a double-opt-in so you're not on the hook: here's the check to [contact] first. And here's the recruiter's info ready to send your friend. Okay to send both?"
- *Done:* Stripe intro handled the right way (opt-in first, your reputation protected), recruiter info drafted to your friend — both waiting on one yes.

**9. The board-meeting fire drill**
- *Heard:* Your COO, Monday: "Board's Thursday. They're going to grill us on the CAC payback blowing out last quarter and whether the new pricing is working. Deck's not started. I'm also still mad they killed the EU expansion idea last time but whatever."
- *Catches:* Board meeting Thursday; deck not started; two specific topics they'll press on (CAC payback regression, new pricing performance). Ignores the "still mad about EU expansion" venting.
- *Explores & acts:* Opens last quarter's board deck in Drive/Slides to reuse the structure and the exact charts the board is used to. Pulls live data: CAC and payback from your analytics/finance sheet (computes the actual payback months trend and *why* it blew out — channel mix? a bad paid experiment?), and new-pricing impact from Stripe (ARPU before/after, expansion vs. churn since the change). Cross-references the action items the board assigned last meeting and checks which are done, because they'll ask. Drafts the deck sections with the hard numbers and a pre-empting "here's what we're doing about CAC" slide so you're not caught flat.
- *Checks in:* "Drafted the board deck reusing last quarter's format — the CAC payback slide shows it went from 8 to 14 months, driven mostly by the [channel] experiment, and I added a 'corrective actions' slide. Pricing section shows ARPU up 12%. Want to review the narrative before I share it with [COO]?"
- *Done:* A board-ready deck drafted with honest numbers, root-cause on the CAC blowout, the pricing story, and last meeting's action items reconciled — for your review well before Thursday.

**10. A key customer quietly churning**
- *Heard:* Your customer-success lead in Slack huddle, read aloud: "[Big logo customer] has barely logged in for three weeks and their champion just got promoted to a new team. Renewal's in six weeks. I don't want to be dramatic but this smells like churn." Then: "Could also just be summer, who knows."
- *Catches:* A flagship account showing churn signals (3 weeks low usage, champion moved internally) with renewal in six weeks. Notes the "could just be summer" hedge but treats the renewal risk as real — doesn't dismiss it.
- *Explores & acts:* Opens your CRM (Salesforce/HubSpot) in your session, pulls the account: renewal date, ARR at stake, contract terms, open support tickets, last QBR notes. Cross-references product analytics for the real usage drop (which seats went dark, which features they stopped using). Checks Gmail/Slack-connect for the last real conversation with the (now-promoted) champion and whether a new economic buyer has even been identified. Cross-references memory: this account was a key logo in your last investor update, so churn has a fundraising cost too. Drafts a warm, non-panicked re-engagement note to the champion (congratulating the promotion, asking for the right new owner) and an internal save-play summary for the CS lead.
- *Checks in:* "[Customer] is $X ARR, renews in 6 weeks, and the usage drop is real — [team] seats went dark after [champion] moved, and there's no identified new buyer yet. I drafted a congrats-and-handoff note to [champion] and a save-play for [CS lead]. Okay to send the champion note?"
- *Done:* The at-risk account fully diagnosed (dollars, dates, who went dark, missing new buyer), a warm re-engagement note and an internal save-play drafted — your send on the outbound.

### Lawyer / legal practice

**1. Statute-of-limitations clock heard over coffee**
- *Heard:* An intake partner stops by your office: "I just took on the Reyes slip-and-fall — she fell at the Costco in Brampton on June 2nd last year. Sweet lady, brought me cookies, honestly reminds me of my aunt. Anyway it's yours now, file's in the shared drive."
- *Catches:* New matter assigned (Reyes, occupiers'-liability/slip-and-fall, incident date 2025-06-02). The "cookies / reminds me of my aunt" aside is warmth, not a task — ignored. The real silent danger: a limitations deadline nobody said out loud.
- *Explores & acts:* Opens Clio in the browser, searches "Reyes," confirms the matter shell exists and reads its custom fields and documents tab to find the incident date and jurisdiction (Ontario). Cross-references memory that Ontario's basic limitation period is two years and that Costco is an occupier — flags the hard deadline of 2027-06-02 and the practical filing target well before it. Opens the Clio "Tasks" and "Calendar" tabs to check nothing is already docketed, then opens the documents tab to see whether a Notice has gone out. Drills into the shared-drive folder link to confirm the incident report and any photos are actually there, noting what's missing (no medical records, no witness statement).
- *Checks in:* "New file Reyes is live — I read the Clio record: incident June 2 2025, Ontario, occupier is Costco. That's a 2-year limitation, so the real wall is June 2 2027, and I'd want the claim filed months before. Nothing's docketed yet and there are no med records or witness statement in the folder. Want me to docket the limitation + a 90-day-out reminder, and draft the records-request letters?"
- *Done:* Limitation and early-warning dates docketed in Clio, a clean "missing items" checklist on the matter, draft records-request letters waiting for your okay — no deadline silently running.

**2. Opposing counsel's offer mentioned in passing**
- *Heard:* Associate, walking past: "Oh — Goldstein's office called on the Tran construction-lien thing, they're floating eighty-five to make it go away, said the offer's good till Friday. He sounded twitchy, like the client's leaning on him."
- *Catches:* A settlement offer on the Tran matter ($85k, expiry Friday) that needs to be captured, time-tracked, and turned into a real client decision. The "he sounded twitchy" read is useful color, not an action.
- *Explores & acts:* Opens the Tran matter in Clio, reads the matter summary, the pleadings in the documents tab, and the running ledger to surface the claimed lien amount and what's already been billed/recovered. Pulls the most recent demand or mediation memo to compare $85k against the ask. Cross-references memory of the client's stated walk-away number from an earlier note. Opens the Clio calendar to confirm there's no conflicting examination or deadline before Friday, and creates a time entry for reviewing the offer. Drafts a tight client email: the number, how it compares to the claim and to fees-to-date, the Friday clock, and a clear recommendation.
- *Checks in:* Because this is a money decision and goes to a person: "Drafted the note to Mr. Tran laying out the $85k vs the $120k lien and where fees stand, with my read on it. It's a settlement-authority call, so I won't send or respond to Goldstein until you say go. Want to read the draft?"
- *Done:* Offer logged on the matter with its Friday deadline docketed, time captured, a decision-ready email to the client sitting in drafts — nothing accepted, nothing sent, until you approve.

**3. The hallway "we need to bill that" that never makes it to the timesheet**
- *Heard:* You, to yourself after a call, mic still picking it up: "Ugh, just spent like forty minutes on the phone with the Donnelly estate trustee walking her through the holdback — and another twenty drafting that release earlier. I always forget to put these in."
- *Catches:* Two unbilled time entries on the Donnelly estate matter (~40 min trustee call re: holdback; ~20 min drafting release). The self-directed grumble "I always forget" is venting — not acted on as a task in itself.
- *Explores & acts:* Opens the Donnelly matter in Clio, checks the activities/time tab to confirm these entries aren't already there. Reads the matter's billing rate and the firm's standard activity codes, and looks at how you've described similar calls before so the narrative matches your voice and is client-readable (e.g., "Telephone attendance with trustee re: estate holdback; review and revise release"). Cross-references the matter's documents tab to confirm the release draft exists, giving the second entry a real anchor. Rounds to your usual increment and stages both as draft time entries rather than posting blind.
- *Checks in:* No money leaves and nothing goes to a client, so it stays a soft confirm: "Staged two time entries on Donnelly — 0.7 trustee call re: holdback and 0.4 drafting the release — in your usual wording. Post them?"
- *Done:* Two accurately-worded draft entries ready on the matter; once you tap yes they're on the clock instead of evaporating.

**4. Court date dropped mid-conversation**
- *Heard:* Clerk on speakerphone: "Counsel, the case conference for Whitfield v. Aldercorp is confirmed for July 14th at 10 a.m. before Justice Mehta, virtual, and don't forget the conference brief is due five days prior under the rule."
- *Catches:* A real court event (Whitfield v. Aldercorp case conference, 2026-07-14 10:00, Justice Mehta, virtual) plus a derivative deadline (conference brief due 5 days prior, i.e., July 9). Both must be calendared and the brief queued.
- *Explores & acts:* Opens Clio, finds the Whitfield matter, and checks the calendar to confirm nothing already conflicts on July 14 morning and that you're not double-booked with the standing Friday partner meeting. Creates the court appearance event with the judge, virtual flag, and a note to retrieve the Zoom/CaseLines link closer to date. Back-calculates the brief deadline accounting for how the rule counts days, and dockets July 9 with a working-back reminder a week earlier. Opens the documents tab to see if a draft brief or prior conference brief exists to reuse, and checks the contacts on the matter so the event invite can include co-counsel.
- *Checks in:* Since the calendar invite would go out to co-counsel: "Whitfield case conference is going in for July 14 10am (Justice Mehta, virtual), with the brief docketed for July 9 and a heads-up the week before. I drafted a calendar invite for you and Priya — okay to send it to her, or keep it on your calendar only for now?"
- *Done:* Appearance and brief deadline locked in Clio with sensible lead-time reminders, prior brief surfaced as a starting point, invite parked pending your okay.

**5. Conflict check triggered by a name in passing**
- *Heard:* Rainmaker partner, excited: "Big one walking in — Hargrove Logistics wants us on a shareholder dispute against the other founder, a guy named Daniel Voss. They could be a huge client. Let's not screw this up."
- *Catches:* A potential new client (Hargrove Logistics) and an adverse party (Daniel Voss) requiring a conflicts check before anything else moves. The "could be a huge client / don't screw it up" is pressure, not an instruction to skip steps.
- *Explores & acts:* Opens Clio and runs a conflicts search across contacts and matters for "Hargrove Logistics," "Daniel Voss," and obvious variants (Dan Voss, Voss Holdings), reading each hit to see whether the firm has ever acted for Voss, a related entity, or on the other side of Hargrove. Opens any matching contact cards and related matters to read the actual relationship, not just the name match. Cross-references memory of past representations and checks the documents/notes for any engagement that would taint. Compiles exactly what it found — clean, or specific hits with matter numbers.
- *Checks in:* Engagement is effectively irreversible reputationally, so it parks the decision: "Ran conflicts on Hargrove Logistics and Daniel Voss in Clio. One thing to look at: we have a closed 2023 matter where a 'D. Voss' was a third-party witness — could be him, could be coincidence. I've pulled that matter up for you. Want me to dig into whether it's the same person before we open the file?"
- *Explores & acts (cont.):* Stages a draft engagement letter and new-matter shell so that, the instant you clear conflicts, opening the file is one tap.
- *Done:* A real conflicts report with the one ambiguous hit flagged and opened for your eyes, engagement letter staged but unsent — no file opened, no conflict missed.

**6. Client's emailed document request mentioned out loud**
- *Heard:* You, after checking your phone: "Mrs. Okafor just emailed asking for a copy of the executed lease and the estoppel certificate from the Bayview commercial deal — she needs them for her bank by tomorrow. She's always in a panic, but fair enough, it's her financing."
- *Catches:* A client document request (executed lease + estoppel certificate, Bayview commercial transaction, needed by tomorrow for her lender). "She's always in a panic" is an affectionate eye-roll, correctly ignored.
- *Explores & acts:* Opens the Bayview matter in Clio's documents tab and actually looks for the *executed* versions — opens candidate files to distinguish the signed lease from earlier redlines, and finds the estoppel certificate, verifying it's the countersigned copy and not a draft. If the executed lease is sitting in Gmail rather than Clio, searches the inbox thread for the closing email and locates the final attachment. Cross-references memory that this client prefers PDFs and wants her file-reference number on everything. Drafts a reply email with the two correct documents attached and a one-line note about what each is.
- *Checks in:* Sending to a client, so draft-then-ask: "Found the executed Bayview lease and the countersigned estoppel cert. I've drafted a reply to Mrs. Okafor with both attached and a note that these are the signed copies for her lender. Okay to send?"
- *Done:* A ready-to-send email to the client with the correct executed documents attached; one tap and her bank has what it needs before the deadline.

**7. Trust-account / disbursement comment that flags a money move**
- *Heard:* Bookkeeper, leaning in: "Hey, on the Patel real-estate file — the deal closed, and there's still nineteen grand sitting in trust. Client's been emailing about getting their money. Also the courier invoice and the title-insurance disbursement haven't been booked against it."
- *Catches:* Funds in trust on a closed matter (Patel, ~$19k) needing reconciliation and likely return to the client; two unbooked disbursements (courier, title insurance). The looming action is a trust payout — a money + irreversible move.
- *Explores & acts:* Opens the Patel matter in Clio, reads the trust ledger and the operating ledger to confirm the $19,000 balance and what's already been recorded. Pulls the closing statement / statement of adjustments from the documents tab to reconcile what should remain after legitimate disbursements. Hunts the matter and Gmail for the courier and title-insurance invoices so the disbursements can be booked with real amounts, then recomputes the true net owed back to the client. Checks the client's emails to confirm the payout request and the correct payee details.
- *Checks in:* Trust funds are money and irreversible, so it parks hard and asks warmly: "Looked at the Patel trust ledger — $19k in trust. Once I book the courier ($46) and title insurance ($512) disbursements, the client's net refund looks like $18,442. This one's real money moving out of trust, so I won't touch it — want me to prep the disbursement and the trust statement for your sign-off, or hold off?"
- *Done:* Trust ledger reconciled with the two disbursements drafted and the exact refund figure computed, a trust statement staged — but no cheque cut and no transfer made until you explicitly authorize it.

**8. Witness/expert scheduling buried in a status update**
- *Heard:* Junior, summarizing a call: "So the expert, Dr. Lindqvist, says he can do the medical-malpractice examination either the week of August 18th or the 25th, but he's flying to a conference end of August. Opposing side keeps stalling. Oh, and he charges by the hour and isn't cheap."
- *Catches:* An expert-availability window (Dr. Lindqvist, weeks of Aug 18 or Aug 25, hard out late August) to be coordinated against the matter's examination needs. "Opposing side keeps stalling" is commentary; the "isn't cheap" remark flags that any retainer/fee step is a money touchpoint.
- *Explores & acts:* Opens the medical-malpractice matter in Clio, reads the matter status and any scheduling order or undertaking to see what examination is actually outstanding and any court-imposed window. Opens the calendar to find which of your weeks (Aug 18 / Aug 25) are clear of trials, vacations, and the standing motions list, and overlays the expert's two windows to find the genuinely workable days. Cross-references the contact card for Dr. Lindqvist and prior correspondence to confirm his retainer terms. Drafts a scheduling email to opposing counsel proposing specific dates, and separately notes that the expert's fee estimate should be confirmed with the client.
- *Checks in:* Email to opposing counsel = draft-then-ask; the fee = warm money ask: "Best overlap with Dr. Lindqvist is Aug 19-20 — you're clear, and it beats his conference. I drafted a scheduling proposal to opposing counsel for those dates. Okay to send? Separately: his time isn't cheap and we'll need to OK the estimate with the client — want me to tee that up too?"
- *Done:* Proposed dates verified against your calendar and the expert's window, a scheduling email drafted and held for approval, the fee-confirmation flagged as its own client conversation.

**9. Off-hand "the retainer's almost gone" on a heavy file**
- *Heard:* You, reviewing a file at your desk: "The Castellano custody file is eating hours — we've been in motions every other week. Pretty sure their retainer's nearly drained. The dad keeps texting me at midnight, it's exhausting, but the kid's worth fighting for."
- *Catches:* A possible retainer-replenishment situation on the Castellano family-law matter. The "texting me at midnight / exhausting / kid's worth it" is venting and personal feeling — explicitly not acted on.
- *Explores & acts:* Opens the Castellano matter in Clio and reads the trust ledger to find the actual remaining retainer balance, then the time/activities tab to total unbilled work-in-progress sitting on top of it. Compares WIP against the trust balance to see how close (or already underwater) the file is, and checks the engagement agreement in documents for the retainer-replenishment threshold and the agreed evergreen amount. Cross-references the billing history to see when the last invoice and top-up happened, and whether there are aged unpaid invoices that change the picture. Builds the real numbers: balance, WIP, gap.
- *Checks in:* This is a money ask to the client, so warm and held: "You're right — Castellano's down to about $1,400 in trust with roughly $6,800 in unbilled time on top, and your agreement says replenish below $2,500. I drafted a warm top-up request to Mr. Castellano with the current numbers. It involves money, so I won't send it until you've looked — want to review, or should I hold off?"
- *Done:* Exact retainer/WIP gap surfaced against the engagement terms, a tactful replenishment email drafted and parked — your call on timing and whether it sends.

**10. Filing rejected — caught from a frustrated mutter**
- *Heard:* You, reading a screen: "Are you serious — the court portal bounced the Nakamura statement of claim again, something about the wrong fee or a missing affidavit of service. This system is garbage. And I've got the Reyes thing due too."
- *Catches:* A rejected e-filing on the Nakamura matter that needs diagnosis and correction; the passing "Reyes thing due too" is a cross-reference to another live deadline worth verifying. "This system is garbage" is venting — ignored.
- *Explores & acts:* Opens the court e-filing portal (e.g., the Ontario justice services / civil filing portal) in the browser, navigates to the Nakamura submission, and actually reads the rejection notice to extract the precise reason(s) — wrong filing fee tier and/or missing affidavit of service — rather than guessing. Cross-references the Clio matter: opens the documents tab to check whether an affidavit of service exists or still needs to be sworn, and reads the claim to determine the correct fee category. Then opens the Reyes matter to confirm its real deadline status so the offhand mention doesn't hide a second problem. Assembles a precise fix list and, where it can, stages the corrected filing package.
- *Checks in:* Money (the filing fee) and an irreversible court submission, so it parks: "The portal bounced Nakamura for two reasons — the affidavit of service isn't attached, and the fee was filed at the wrong tier (should be the higher one for this claim amount). The affidavit still needs swearing. I've assembled the corrected package and the right fee. Refiling pays a court fee and is irreversible, so I won't submit until you say go. And I checked Reyes — its deadline's fine, docketed for next month."
- *Done:* Root cause of the rejection identified from the actual portal notice, corrected package and correct fee staged, the second matter verified clean — refile waits for your explicit authorization.

### Doctor / clinician

**1. Hallway sign-out about a deteriorating patient**
- *Heard:* Resident, catching you outside the workroom: "Quick one before you go — Mr. Okafor in bed 14, his creatinine bumped from 1.1 to 1.9 this morning and his urine output's been trash since like 6am. Renal hasn't been consulted yet. Oh, and honestly this whole service has been a dumpster fire all week, I'm so done."
- *Catches:* Two real tasks — review Okafor's renal trend and the missing nephrology consult. The "dumpster fire / I'm so done" is a vent; it is not acted on.
- *Explores & acts:* Opens Epic, searches "Okafor" in the patient list, lands on his chart. Pulls the Results Review flowsheet and reads the actual creatinine trend (1.1 → 1.4 → 1.9 over 36h), opens the I/O flowsheet to confirm UOP is <0.5 mL/kg/hr, and checks the MAR for any nephrotoxic agents (spots IV contrast given yesterday + ongoing ketorolac). Opens the Consults activity and confirms no nephrology order exists. Cross-references memory: you always want nephro looped before you round.
- *Checks in:* Does NOT place the consult or stop a med — those are care decisions. Surfaces a tight brief: "Okafor's Cr is 1.1→1.9 in 36h, UOP <0.5, he got contrast yesterday and is still on ketorolac, no renal consult in yet. Want me to queue the nephrology consult order for your signature and pend a ketorolac discontinue for you to confirm?"
- *Done:* You have a one-screen read with the trend, the likely insults, and two pended-but-unsigned orders waiting on your tap.

**2. Patient-volunteered symptom that changes the plan**
- *Heard:* On a telehealth visit, patient says: "Doc, I've been taking the new blood pressure pill, but ever since, I get this dry cough that won't quit, especially at night — keeps my wife up too. She thinks I should just stop it. I dunno, mornings are rough lately, work's been a nightmare."
- *Catches:* Real task — flag the probable ACE-inhibitor cough tied to the recent med change. Ignores the "work's been a nightmare" aside as venting, not a clinical instruction.
- *Explores & acts:* Opens the EMR, goes to the Medications tab, confirms lisinopril was started 3 weeks ago (matches symptom onset), and checks the problem list for the HTN diagnosis. Reads the last two visit notes to confirm no prior ACE trial documented. Pulls up the BP readings from the patient's connected home-monitoring flowsheet to see if pressures are actually controlled. Notes in memory this patient mishears instructions, so any change needs plain-language wording.
- *Checks in:* Never silently switches the drug. Parks it: "Looks like the cough started right when lisinopril began three weeks ago — classic ACE thing. Pressures have been well controlled at 128/80. Want me to draft a note proposing a switch to an ARB for you to decide on, or leave it for you to discuss live?"
- *Done:* The med-onset timeline, BP control, and a switch option are laid out; nothing is changed without your explicit call.

**3. Referral promised out loud in clinic**
- *Heard:* Mid-visit, you say to the patient: "Yeah, that knee's been catching for six months and PT hasn't fixed it — I'm going to send you to ortho, Dr. Halpern's group, they're great with meniscus stuff."
- *Catches:* Real task — generate the orthopedics referral to Dr. Halpern's group for the meniscus workup. (A commitment you made out loud, with named recipient.)
- *Explores & acts:* Opens the EMR referral/Order Entry, searches the provider directory for Halpern's ortho group, confirms it's in-network for this patient's plan by cross-checking the insurance field on the registration tab. Reads the last MRI (if any) and PT discharge summary, pulls the relevant exam findings (positive McMurray, six months of mechanical symptoms) and assembles the clinical justification so the referral isn't bounced back. Checks memory: this clinic's ortho referrals always need imaging attached or they get rejected.
- *Checks in:* Sending to an external office, so it drafts first: "Here's the ortho referral to Halpern's group with your exam, the failed PT course, and the knee MRI attached. Okay to send?"
- *Done:* A complete, justification-backed referral sits pended for your one-tap send, imaging already attached.

**4. The "did the labs come back?" loop**
- *Heard:* Nurse pokes her head in: "Mrs. Delgado keeps calling the front desk asking if her thyroid and lipid panels from last week are in yet — she's anxious about it. Third call today."
- *Catches:* Real task — check whether Delgado's TSH and lipid results have resulted, and close the loop with her. Ignores the editorializing about the calls.
- *Explores & acts:* Opens the EMR, finds Delgado, goes to Results Review, confirms TSH (resulted, slightly elevated at 6.8) and the lipid panel (resulted, LDL 165) are both back and reads the actual values. Checks whether you've already reviewed/released them to the portal — they're still unreleased. Pulls her last visit note to see the plan you'd set ("recheck in 6 weeks, adjust levo if TSH >5"). Cross-references memory that Delgado prefers plain-English result messages, not numbers dumped at her.
- *Checks in:* Doesn't release results or message the patient unilaterally. Drafts a warm portal message in plain language explaining the slightly high thyroid and cholesterol and the next step, and asks: "Both panels are back — TSH 6.8, LDL 165. I've drafted a plain-English portal note with the recheck plan. Okay to release the results and send?"
- *Checks in (money):* If a follow-up statin or repeat labs carry a cost the patient flagged before, it adds: "Heard cost was a worry for her last time — want me to note the generic option, or hold off?"
- *Done:* Results read and verified, a humane message drafted and waiting on your release.

**5. Prior auth blocking a prescription**
- *Heard:* Pharmacist on the phone, you on speaker: "Hey, the Ozempic you sent for Mr. Tran got kicked back — insurance wants a prior auth, they want documented metformin failure and a recent A1c. Also their fax line has been down all morning, total chaos over here."
- *Catches:* Real task — assemble and progress the prior authorization for Tran's GLP-1. Ignores the pharmacy's "total chaos" aside.
- *Explores & acts:* Opens the EMR, pulls Tran's chart, confirms the A1c (8.9%, drawn 5 weeks ago) in Results Review, and digs through the med history and prior notes to document the metformin trial and the documented GI intolerance that ended it. Opens the payer's prior-auth portal (already logged in), navigates to a new auth, and pre-fills the clinical criteria from the chart — diagnosis code, A1c value and date, metformin failure rationale. Cross-references memory of which payer this is and the criteria they bounced last time.
- *Checks in:* Because this commits a clinical attestation, it parks before submitting: "PA is filled in — A1c 8.9%, metformin failed for GI intolerance, all the criteria they wanted. Want to review the attestation before I submit, or should I leave it for your sign-off?"
- *Done:* A complete, criteria-matched prior auth staged in the payer portal, one review away from submission.

**6. Inbox result you flag while talking about something else**
- *Heard:* Colleague at lunch: "Oh by the way, that path report you've been waiting on for the Reyes biopsy finally came in this morning — I saw it cross the queue. Anyway, are you coming to the thing Friday?"
- *Catches:* Real task — surface and review the Reyes pathology report. Ignores the social "thing Friday" question (not a clinical task).
- *Explores & acts:* Opens the EMR In Basket, filters to pathology results, finds the Reyes specimen, opens the full report and reads it end to end — not just the headline line. Pulls the diagnosis (e.g., invasive ductal carcinoma, margins, receptor status pending), cross-references the original procedure note and the indication, and checks whether oncology is already involved by scanning the care team and consult list. Checks memory: this is a result you'll want to deliver by phone, not portal, because it's serious.
- *Checks in:* Never auto-releases a cancer diagnosis or messages the patient. Parks it as a priority brief: "Reyes path is back — invasive ductal carcinoma, margins clear, receptors pending. No onc consult placed yet. This one's a phone-call result per your usual. Want me to pend the onc referral and block a call slot for you?"
- *Done:* The full report read and summarized, the sensitive-delivery flag honored, next steps pended for your decision.

**7. Scheduling a complex follow-up around a procedure**
- *Heard:* You, finishing a note out loud: "Okay, post-op check two weeks after her gallbladder, then I want repeat LFTs the week before so I'm not flying blind, and she works nights so don't put her at 8am."
- *Catches:* Three linked real tasks — book the 2-week post-op visit, schedule repeat LFTs the week prior, and respect the no-early-AM constraint. (Spoken commitments, fully actionable.)
- *Explores & acts:* Opens the EMR scheduling module, finds the patient, reads the op note to get the actual surgery date, then counts forward to set the post-op window. Searches your template for open post-op slots avoiding mornings, and finds a lab appointment 5–7 days before that visit for the LFTs. Cross-references memory that this patient no-shows for early slots and prefers the downtown lab draw site. Pends both appointments and the LFT order linked to the visit.
- *Checks in:* Sending an appointment confirmation to the patient counts as outbound, so it drafts: "I've got the post-op at 2:30pm on the 14th and LFTs at the downtown draw site on the 8th, both away from mornings. Okay to send her the confirmation?"
- *Done:* Both appointments and the lab order staged, constraints honored, a patient confirmation drafted and waiting.

**8. A colleague's curbside that's really a venting session**
- *Heard:* Partner, slumping into the chair: "Ugh, admin wants us to see two more patients an hour now, it's insane, the EMR is going to kill me, I swear I'm going to retire early. Honestly some days I hate this job." Then: "Oh — actually, can you cover my 4pm Bautista follow-up? I've got the M&M conference."
- *Catches:* One real task buried at the end — cover the 4pm Bautista follow-up. Everything before it (admin gripes, "I hate this job," retire-early) is venting and is correctly left alone.
- *Explores & acts:* Opens the EMR, finds the 4pm Bautista appointment on the partner's schedule, reads the chart to prep — last visit note, active problems, why this is a follow-up, any results pending you'll be asked about. Checks your own schedule for the 4pm conflict and confirms you're free. Cross-references memory of how you like patients you're covering pre-briefed (one-liner + open issues). Pends a coverage note so the front desk knows you're seeing them.
- *Checks in:* No money or send needed beyond logistics, but confirms the swap: "You're clear at 4 — I've prepped Bautista's chart (HTN follow-up, BP log to review, no pending labs) and flagged the desk you're covering. Good to lock it?"
- *Done:* Coverage arranged, the patient pre-briefed, the partner's vent untouched.

**9. Outstanding balance / self-pay item surfaced during care talk**
- *Heard:* Front-desk lead catches you: "Mr. Adeyemi's here for his MRI follow-up, but he's got a $480 balance and his deductible reset, so the contrast study you wanted is going to be out-of-pocket. He looked stressed when I mentioned it."
- *Catches:* Real task — understand the financial picture before the contrast MRI and surface it appropriately. (Money is explicitly involved — handle as a warm ask, never a cold block.)
- *Explores & acts:* Opens the EMR registration/billing tab, confirms the $480 outstanding balance and the deductible reset, and checks the insurance plan to estimate the contrast-study out-of-pocket. Cross-references the imaging order you placed and whether a non-contrast protocol would clinically suffice, by reading your original rationale in the last note. Pulls memory that this patient has asked about payment plans before.
- *Checks in (money — warm ask):* "Heads up — Adeyemi has a $480 balance and his deductible reset, so the contrast MRI would be largely out-of-pocket and he's stressed about it. Want me to draft a payment-plan option for the desk to offer, and flag whether non-contrast would do clinically — or hold off and just let you talk to him?"
- *Done:* The full cost picture and a humane payment option are ready; nothing about his care or billing is changed without your word.

**10. Med reconciliation gap caught from a family member's aside**
- *Heard:* Patient's daughter, during the admission interview: "She takes a water pill and the heart one, and the blood thinner — the new one, not warfarin, the other one. Oh and her old doctor mentioned something about her potassium being low last time but I'm not sure that ever got fixed. This place is so much nicer than the last hospital though."
- *Catches:* Real tasks — reconcile the DOAC (not warfarin), confirm the diuretic, and chase the flagged low-potassium thread. Ignores the "this place is nicer" pleasantry.
- *Explores & acts:* Opens the EMR med rec / admission medication module, pulls the external pharmacy fill history via the connected medication-history feed, and identifies the specific DOAC (apixaban) the daughter couldn't name, plus the diuretic (furosemide). Searches Results Review and outside records (Care Everywhere) for the most recent potassium — finds a K of 3.1 from the prior facility never rechecked. Cross-references the MAR to confirm whether a supplement was ever started. Checks memory that this patient is a fall risk, so electrolyte stability matters.
- *Checks in:* Doesn't add or order anything — these are care decisions. Surfaces the reconciled list and the gap: "Reconciled her meds — it's apixaban, furosemide, and metoprolol. But I found a K of 3.1 from the outside facility that was never rechecked or repleted. Want me to pend a BMP and a potassium order for your sign-off?"
- *Done:* A clean, source-verified med list plus a flagged, unresolved electrolyte issue with orders pended for your decision.

### Real estate agent

**1. Seller wants a price change on the active listing**
- *Heard:* Seller Donna Reyes on the call: "We've had it on for three weeks and nothing. My husband thinks we should just drop it ten grand and be done with it — honestly I'm tired of cleaning the house every time someone wants to peek. Can we lower it before the weekend?"
- *Catches:* Real task: prep a price reduction on the Reyes listing for the weekend. Ignores the venting about cleaning the house and the husband's offhand "ten grand" as a firm number — it's a negotiating mood, not an instruction, so it gathers data instead of blindly cutting $10k.
- *Explores & acts:* Opens the brokerage's MLS (e.g. Matrix/Flexmls), pulls the Reyes listing by address, and reads the actual showing activity — 9 showings, 0 offers, days-on-market 22. Runs a fresh comparative market analysis: filters same subdivision, ±300 sqft, sold last 90 days, reads the three closest comps' final sale prices and price-drop history. Cross-references memory: Donna's stated floor and that the relocation closing date is July 31. Drafts a reduction recommendation ($12k lands it under the $X psychological threshold and beats two active competitors) with the comp evidence.
- *Checks in:* "Heard the price-drop idea — pulling comps, I'd suggest $12k not $10k so we slide under [threshold] and undercut the two actives on [street]. This changes the list price (and what you net at closing), so I won't touch it until you say go. Want me to send Donna the one-pager and queue the MLS change?"
- *Done:* CMA one-pager drafted and attached to Donna's contact; MLS price-change staged but not submitted; nothing live until the agent confirms.

**2. Buyer falls in love mid-showing**
- *Heard:* At the third house, buyer Marcus to his wife, then to the agent: "Okay this is the one. The kitchen, the yard for the dog — yeah. What do we have to do to get it? Can we get something in tonight before someone else does?"
- *Catches:* Real task: prepare an offer on the property they're standing in, tonight. No vent here — clear, urgent intent from the decision-maker.
- *Explores & acts:* Pulls the listing in the MLS, reads the full listing remarks and the agent-only private remarks (offer instructions, "highest-and-best by Sunday," preferred title company, seller wants a 45-day close). Opens the disclosure packet in the document portal and reads the seller's property disclosure and any HOA docs for red flags. Checks memory for Marcus's pre-approval letter amount and lender (cross-references the saved Rocket pre-approval), his max comfortable monthly, and that he asked to keep earnest money light. Pre-fills the state offer form (e.g. zipForm/Dotloop) with property, price strategy, financing terms, and the seller's requested close date, leaving price open.
- *Checks in:* "Offer's 90% built in Dotloop. Two things that need you: the number, and earnest money — that's real money leaving your account, so I'm not locking it. Private remarks say highest-and-best by Sunday and they want a 45-day close, which works with your lender. Want to talk price, or should I draft at list?"
- *Done:* Offer package staged in Dotloop with disclosures already reviewed and flagged; financing terms aligned to the saved pre-approval; awaiting price and earnest-money sign-off before anything is sent.

**3. Inspection comes back rough**
- *Heard:* Buyer client texting and then on a quick call: "Inspector just left, he found some stuff with the roof and the water heater. I'm a little freaked out honestly, my brother bought a place with a bad roof and it was a nightmare. Should we be worried? What's our move here?"
- *Catches:* Real task: figure out the repair-request move on the inspection items before the contingency deadline. Ignores the brother's-bad-roof anxiety as reassurance-seeking, not a task — it doesn't go research the brother's house.
- *Explores & acts:* Opens the transaction in the brokerage TC system / Dotloop and reads the executed contract to find the exact inspection contingency deadline (it computes "you have until Thursday 5pm"). Opens the inspection PDF from the report portal, reads it in full, and pulls out the material items (roof: 3–5 yrs life left; water heater past service age) versus cosmetic noise. Cross-references the seller's property disclosure already on file — did the seller disclose the roof age? Checks memory for this buyer's trust dial (Regular) and that they're tight on closing cash. Drafts a repair-request amendment proposing a seller credit (preferred, since they're cash-tight) rather than seller-completed repairs.
- *Checks in:* "Read the full report — roof and water heater are the only two that matter, the rest is normal for the age. Your contingency runs out Thursday 5pm. I drafted a repair amendment asking for a credit instead of repairs since you'd rather keep the cash. This goes to the seller's agent — okay to send, or want to change the ask first?"
- *Done:* Repair-request amendment drafted with the deadline surfaced; sent only on the buyer's okay; contingency date set as an internal reminder.

**4. Open house lead that actually matters**
- *Heard:* Sunday evening voice note to self after the open house: "Big day. The couple with the gray Tesla — Priya and someone — they walked it twice, asked about the school district and whether the seller would take a quick close. Get on them this week. Oh and somebody left the side gate open again, drove me nuts all afternoon."
- *Catches:* Real task: follow up fast with the serious open-house couple (Priya). Ignores the side-gate gripe entirely — pure venting, no action.
- *Explores & acts:* Opens the open-house sign-in (Spacio / paper scan / the CRM's sign-in capture) and finds the entry matching "Priya," pulling email and phone. Searches the CRM (Follow Up Boss / kvCORE) for an existing record — finds Priya already inquired on a Zillow listing two weeks ago, so it merges rather than duplicates and tags her "hot — double-walked, asked quick close." Reads back the listing she toured for the school-district and closing facts so the follow-up is specific. Drafts a warm, non-templated follow-up referencing the exact things she asked about (the school ratings, the seller's openness to a fast close) and proposes two private-showing times pulled from the agent's open calendar.
- *Checks in:* "Drafted a follow-up to Priya — references the school district and the quick-close she asked about, and offers Tue 6pm or Wed 12pm from your calendar. This goes to her directly, so okay to send?"
- *Done:* CRM record merged and tagged hot, draft ready; sends on approval; if no reply, a 48-hour nudge is queued.

**5. Listing appointment prep**
- *Heard:* Referral partner on the phone: "I gave your name to the Hendersons over on Maple — they're thinking of selling, big colonial, probably listing in a month or so. They're expecting you to reach out. I think they interviewed one other agent already though, just so you know."
- *Catches:* Real task: reach out to the Hendersons and build a listing-appointment package, knowing it's competitive. The "interviewed one other agent" isn't a vent — it's intel that raises the bar, so the prep goes deeper.
- *Explores & acts:* Pulls the Maple property in public record / MLS tax data — sqft, beds/baths, last sale price and date, lot size. Runs a listing-side CMA: actives, pendings, and 6-month solds in the immediate area, reading each comp's condition notes and price-per-sqft. Checks the property's MLS history for any prior expired or withdrawn listing (a tell). Cross-references memory for who the referral partner is (to credit them) and the agent's standard listing-presentation deck in Google Drive, which it clones and pre-fills with the Hendersons' address, photos pulled from public record, the CMA range, and a suggested list price. Drafts a warm intro text that name-drops the referrer.
- *Checks in:* "Built the listing presentation for the Hendersons — pre-filled CMA says list range $X–$Y, deck's in your Drive. Also drafted an intro text mentioning [referrer] sent you. Since there's a competing agent, want me to send the text now to lock the appointment first?"
- *Done:* Pre-filled listing deck in Drive, CMA done, intro text drafted; text sends on approval; appointment-prep packet ready before they ever meet.

**6. Pending deal at risk — appraisal gap**
- *Heard:* Lender on the phone, agent half-listening while driving: "Hey, heads up — the appraisal on the Oakdale deal came in eleven thousand under contract price. Loan's fine otherwise but we've got a gap. Buyer's gonna need to know. Ugh, third low appraisal I've had this month, this market is insane."
- *Catches:* Real task: handle the $11k appraisal gap on the Oakdale deal — surface options to the buyer, watch the deadline. Ignores the lender's "third low appraisal this month / market is insane" rant.
- *Explores & acts:* Opens the Oakdale transaction in Dotloop and reads the contract's appraisal contingency language and deadline, plus whether an appraisal-gap clause was already written in (it finds the gap coverage cap the buyer agreed to). Reads the appraisal report PDF for the comps the appraiser used and spots one questionable comp to potentially challenge via rebuttal. Cross-references memory: buyer's cash reserves and that they said early on they "really don't want to come up much." Lays out the three real moves — bring cash to the gap, renegotiate price with the seller, or file an appraisal rebuttal on the weak comp — with the deadline attached.
- *Checks in:* "Oakdale appraised $11k under. You've got three plays and a Friday deadline. Bringing cash or renegotiating price both touch real money, so I'm not moving on those — but I can file an appraisal rebuttal now on the one weak comp the appraiser used, no cost to the buyer. Want me to start the rebuttal while you call them?"
- *Done:* Contingency deadline surfaced, options laid out with money items parked; rebuttal drafted and ready pending a green light; nothing financial committed.

**7. Past client plants a referral seed**
- *Heard:* Run into a past client, Tom, at the coffee shop: "Man, we love the house, two years already. Oh — my sister and her husband are finally getting serious about buying, first place, they're kind of clueless honestly. I told them to call you. They're nervous about the whole thing."
- *Catches:* Real task: proactively reach out to Tom's sister (first-time buyers, nervous) rather than waiting for the call. Tom's "we love the house" is warmth, not a task — noted to memory, not acted on.
- *Explores & acts:* Opens the CRM, finds Tom's record, reads the closing date and the home he bought (to reference warmly), and checks for any note about a sister. Creates a new lead linked to Tom as the referral source so attribution is tracked. Because they're first-timers and nervous, it pulls together a genuinely helpful first-timer's starter kit from the agent's Drive (the buyer-process one-pager, a lender intro, a "what to expect" timeline) rather than a cold "let's chat." Drafts a soft, reassuring intro text to Tom asking for the best way to reach his sister, plus a ready-to-go welcome message for the sister once introduced.
- *Checks in:* "Saw Tom referred his sister — first-timers, nervous. Drafted a low-pressure text to Tom to get her contact, and a warm welcome with a first-buyer starter kit ready for when he connects us. Okay to send Tom's text?"
- *Done:* Referral lead created with Tom credited, starter kit assembled, texts drafted; sends on approval; nothing pushy.

**8. Showing logistics across a busy buyer tour**
- *Heard:* Buyer Saturday morning: "Can we see that new one on Birchwood that popped up yesterday? And the one we liked on Tuesday — is that still around or did it go? Let's try to knock out a few Saturday, we're driving in from out of town so make it worth the trip."
- *Catches:* Real task: build a Saturday showing route — add the new Birchwood listing, verify the Tuesday favorite's status, batch nearby ones efficiently. No vent; just logistics with a real constraint (out-of-town, one trip).
- *Explores & acts:* In the MLS, opens the new Birchwood listing, confirms it's active and reads showing instructions (appointment-required, lockbox vs. agent-present, pet on premises). Pulls up the Tuesday favorite and reads its current status — finds it went pending, so it won't waste a stop. Searches the buyer's saved-search criteria in the CRM/MLS for 2–3 more actives clustered near Birchwood to make the trip worth it. Requests showing times through ShowingTime for each, sequencing them geographically into a tight route, and cross-references the agent's own calendar for conflicts.
- *Checks in:* "Built a Saturday route: Birchwood plus three nearby that fit your search. Heads up — the Tuesday one went pending, so I dropped it. ShowingTime requests are queued for 11/11:45/12:30/1:15; want me to confirm them all?"
- *Done:* Optimized showing itinerary assembled with the dead listing pruned and the new one added; ShowingTime requests fire on confirmation; itinerary texted to the buyer once set.

**9. Contract deadline quietly approaching**
- *Heard:* Overheard in the agent's own end-of-day ramble into the recorder: "Long day. The Carter closing is coming up and I feel like there's something I'm forgetting on it. Also need to renew my lockbox subscription before it lapses. And I really need to stop saying yes to 8am showings."
- *Catches:* Real tasks: audit the Carter file for the looming deadline the agent senses they're forgetting, and renew the lockbox subscription. Ignores the "stop saying yes to 8am showings" — self-talk, not an instruction.
- *Explores & acts:* Opens the Carter transaction in Dotloop/the TC system and reads the full critical-dates timeline against today — finds the loan-commitment/financing contingency lapses in two days and the final walkthrough isn't scheduled. Checks which documents are still unsigned in the file and whether the title company has confirmed the closing appointment. For the lockbox, opens the SentriLock/SUPRA account, reads the renewal date and confirms it's about to lapse, and stages the renewal. Cross-references memory for the agent's preferred title contact to chase the missing walkthrough scheduling.
- *Checks in:* "Carter file: the financing contingency lapses in 2 days and there's no walkthrough booked — those were the loose ends. I can ping the title company to lock the closing time and draft the walkthrough request. Separately, your SentriLock renewal lapses Friday — that's a charge to your card, so want me to renew or just remind you?"
- *Done:* Carter critical dates surfaced with the two real gaps flagged and fixes drafted; lockbox renewal staged but the payment parked for explicit approval.

**10. Seller anxious about a stale listing — proof-of-work check-in**
- *Heard:* Listing client leaves a slightly testy voicemail: "Hey, it's been a while since I heard from you. Are people even looking at our place? My neighbor sold in like a week and I'm starting to wonder what's going on. Just want to know you're on it."
- *Catches:* Real task: produce a real, evidence-backed seller update that proves activity and addresses the worry. The neighbor comparison is anxiety, not a directive — it's acknowledged, not chased down as a task.
- *Explores & acts:* Opens the MLS listing and reads the actual numbers: showings this period, agent feedback left in ShowingTime, days-on-market, and saved/favorited counts. Logs into the syndication side (Zillow/Realtor.com via the listing dashboard) and reads view and save trends week over week. Reads the feedback comments themselves for the recurring theme (e.g. "priced high for the dated kitchen"). Cross-references the original CMA in memory to see if the market has shifted since listing. Assembles a real seller report: views, showings, the honest feedback pattern, and a concrete recommendation (a price tweak or fresh photos) — and drafts a warm update that leads with the data, not excuses.
- *Checks in:* "Drafted a real update for [seller] — 41 Zillow saves, 6 showings, and the honest pattern in feedback is the kitchen vs. price. Recommendation's a modest price adjustment, but that's your call and your net, so I left it as a suggestion, not a change. Okay to send the update?"
- *Done:* Data-backed seller report drafted with genuine activity evidence and an honest recommendation; sends on approval; any price move stays parked as the seller's decision.

### Sales / account executive

**1. Discovery call resurfaces a stalled deal**
- *Heard:* On a Zoom debrief, the AE's manager says: "Hey, good call with Meridian Logistics today — but didn't they ghost us back in Q1? Pull up what happened there before you send anything, I don't want us to look like we forgot." The AE mutters, "Honestly their procurement guy is a nightmare, I'd rather close anyone else." 
- *Catches:* Task — reconstruct the Meridian history before drafting outreach. Deliberately ignores the "procurement guy is a nightmare" vent.
- *Explores & acts:* Opens Salesforce, searches the Meridian Logistics Account, opens the Opportunity record, reads the Q1 opp that's marked Closed Lost and reads the loss reason field and the last three Activity timeline entries (a pricing-objection email, an unanswered call log). Cross-references Gmail for the actual thread, opens it, reads where it died (a quote they never replied to). Cross-references memory: the AE prefers to lead re-engagements with a relevant case study, not a discount. Pulls the matching logistics case study from Google Drive.
- *Checks in:* Drafts a warm re-engagement email in Gmail referencing the new discovery call and attaching the case study, no discount mentioned, then: "Built the Meridian re-open off the Q1 thread — okay to send, or want to soften the open?"
- *Done:* Draft sits ready in Gmail; a note is logged on the Salesforce opp that re-engagement was prepped.

**2. Quote promised on a live call**
- *Heard:* The prospect on speaker: "If you can get me pricing for 45 seats on the Growth tier by end of day, I'll take it to my CFO Thursday." The AE, after hanging up: "Finally, someone who actually has budget."
- *Catches:* Task — produce a 45-seat Growth-tier quote today. (The "someone with budget" remark is just relief, nothing to act on.)
- *Explores & acts:* Opens HubSpot, finds the contact's Deal, confirms the associated company and deal stage. Goes into the Products/quotes area, reads the current Growth-tier price book and any volume-discount tiers, sees 45 seats crosses the 40+ break. Builds the quote line items, applies the standard 40+ discount, and cross-references memory that this CFO previously pushed on annual-vs-monthly — so it prepares both an annual and a monthly version. Pulls the rep's e-signature-ready quote template.
- *Checks in:* Money involved, so a warm ask: "Heard this one's got a CFO and real dollars attached — I've built 45 seats at the 40+ break, annual and monthly side by side. Want me to send it, or hold so you can eyeball the discount first?"
- *Done:* Two quote versions staged in HubSpot, deal note added, nothing sent without the AE's nod.

**3. CRM hygiene from a hallway update**
- *Heard:* A teammate stops the AE in the kitchen: "Oh by the way, Dana from Brightwave told me on LinkedIn she's moved to a new company — she's at Cascade now, still our champion though." 
- *Catches:* Task — update the contact record and protect the relationship across the move. 
- *Explores & acts:* Opens Salesforce, searches Contact "Dana", opens her record, sees title/company still listed as Brightwave. Rather than blindly overwrite, it checks whether a Cascade Account already exists (it does, owned by another rep) and reads the open opps there. It flags the ownership overlap instead of silently reassigning. Updates Dana's contact with the new company and a note that she's a carried-over champion, and links her to the Cascade account as a key contact. Cross-references memory that the AE likes to send a low-key congrats note on job moves.
- *Checks in:* Drafts a short congrats message: "Saw you landed at Cascade — drafted you a two-line congrats to Dana, okay to send? Also heads up, Cascade is Marcus's account, so I didn't touch ownership — want me to loop him in?"
- *Done:* Dana's record reflects the move, the ownership conflict is surfaced not buried, congrats draft awaits approval.

**4. Follow-ups slipping after a busy week**
- *Heard:* The AE, half to themselves while packing up Friday: "Ugh, I completely blanked on the Talgo and Northpoint follow-ups this week, they're going to think I don't care." 
- *Catches:* Task — recover the two specific overdue follow-ups (Talgo, Northpoint). It does NOT act on the generic self-criticism.
- *Explores & acts:* Opens HubSpot, finds both deals, reads the last logged activity on each to see exactly where the thread paused — Talgo was waiting on a security questionnaire the AE promised; Northpoint asked for a reference customer. For Talgo it opens Google Drive, locates the completed SOC 2 / security packet. For Northpoint it cross-references memory for which reference customer in the same vertical already agreed to be a reference. It reads each original email thread in Gmail so the follow-up picks up the real thread, not a generic "just checking in."
- *Checks in:* Drafts both replies in-thread (Talgo with the security doc attached, Northpoint naming the reference): "Two recovery follow-ups drafted off the real threads — Talgo's got the security packet attached. Okay to send both, or read them first?"
- *Done:* Both drafts queued in Gmail in their original threads; deals re-noted as "follow-up prepped."

**5. Proposal prep from a deal-review comment**
- *Heard:* On the weekly pipeline call, the sales director: "Riverside is your biggest deal this quarter — they want a formal proposal next week. Make sure it actually reflects what they asked for in discovery, not the boilerplate."
- *Catches:* Task — build a tailored Riverside proposal grounded in their stated needs.
- *Explores & acts:* Opens Salesforce, the Riverside opp, and reads the discovery call notes and the Chorus/Gong call-summary link logged on the activity timeline — pulling out their three stated priorities (multi-region rollout, SSO, a phased go-live). Opens Google Drive, copies the master proposal template, and rewrites the scope/solution sections to map each of those three priorities explicitly. Cross-references the quote already built in the opp so pricing matches. Cross-references memory that this director hates jargon and wants an exec summary up top.
- *Checks in:* Sending a document to a client, so draft-then-ask: "Tailored the Riverside proposal to their three discovery asks with an exec summary up front — it's a doc, not sent yet. Want to review before it goes to their VP?"
- *Done:* A clean, tailored proposal draft lives in Drive, linked on the Salesforce opp, awaiting the AE's review.

**6. Scheduling a multi-stakeholder demo**
- *Heard:* Prospect on the phone: "Loop in my VP of Eng and our security lead for the next one — they're the real decision makers, and honestly my manager's been useless on this." 
- *Catches:* Task — schedule a follow-up demo including the VP of Eng and the security lead. Ignores the "manager's been useless" aside.
- *Explores & acts:* Opens the AE's Google Calendar, reads their real availability over the next two weeks and respects the memory-stored rule of no demos before 10am and no Friday afternoons. Opens Salesforce to confirm the prospect's company and find the contact records for the VP of Eng and security lead (adds them if missing). Drafts a calendar invite with a tailored agenda that front-loads security topics given who's attending, and attaches the relevant security one-pager from Drive.
- *Checks in:* Sending invites to external people, so: "Built a demo invite for three of their people with a security-heavy agenda and three proposed slots — okay to send the invite, or want different times?"
- *Done:* Invite drafted with attendees, agenda, and attachment, ready to send on approval; new contacts logged in Salesforce.

**7. Renewal risk overheard in a status comment**
- *Heard:* The customer success counterpart pings on a call: "Just so you know, usage at Atlas dropped off a cliff last month and their main user left — their renewal's in 60 days." The AE: "Great, exactly what I needed before quarter-end."
- *Catches:* Task — get ahead of the at-risk Atlas renewal. (The sarcastic "exactly what I needed" is venting, not an instruction.)
- *Explores & acts:* Opens Salesforce, finds the Atlas Account and the renewal Opportunity, confirms the close date and ARR. Reads the contact list and spots the departed champion's record, then identifies the next-most-engaged contact from recent Activity. Opens Gmail and scans the last few threads to gauge sentiment and find any unresolved support escalation. Cross-references memory that Atlas signed largely for a feature that's since shipped improvements — a legitimate re-engagement hook. Pulls the latest product-update one-pager from Drive.
- *Checks in:* Money/renewal and a relationship reset, so warm ask: "Atlas renewal's wobbling — champion left, usage dipped. I've drafted a check-in to their next-best contact leaning on the new features, no discount in it yet. Want to send as-is, or talk strategy first?"
- *Done:* A renewal-save outreach is drafted, the at-risk opp is annotated with the risk summary, nothing committed without the AE.

**8. Competitive intel from a lost-deal mention**
- *Heard:* In a team Slack huddle read aloud: "We lost Pinnacle to Competitor X — they undercut us on price and threw in onboarding for free. Anyone selling against them, take note." The AE sighs, "Their product is half-baked though, customers always come back."
- *Catches:* Task — apply that lost-deal intel to the AE's own at-risk-to-Competitor-X deals. Doesn't act on the "their product is half-baked" opinion.
- *Explores & acts:* Opens the CRM and filters the AE's open pipeline for deals where Competitor X is named in the competitor field or mentioned in notes. For each match, opens the opp and reads the stage and last activity to judge exposure. Identifies two deals in late stages where price is the live objection. Cross-references memory of the AE's approved ROI/value calculator and the standard onboarding-included counter the team has authority to offer.
- *Checks in:* "Two of your deals are exposed to the same Competitor X play — Vanguard and Crestline, both late-stage on price. I can prep value-justification follow-ups; the onboarding-included counter involves giving something away, so I'll hold on that part until you say go." 
- *Done:* The two exposed deals are flagged with a recommended counter; value-framing follow-ups are prepped, the giveaway lever explicitly parked for the AE's call.

**9. Expense and travel for an onsite close**
- *Heard:* The AE on a call with their VP: "Yeah, I'll fly out to Denver to close Summit in person next Thursday, it's worth doing live." 
- *Catches:* Task — set up the Denver trip logistics around the Thursday onsite. 
- *Explores & acts:* Opens Google Calendar, reads Thursday and the surrounding days to find the real meeting window and any conflicts, blocks travel time. Opens Salesforce to confirm the Summit meeting location/address and who's attending so timing is realistic. Drafts a confirmation email to the Summit champion locking the onsite time and asking about a room and parking. Pulls together the in-person closing kit — the latest proposal and the order form — from Drive so it's ready to hand over. Cross-references memory of the AE's airline and seat preferences and that they expense through Concur.
- *Checks in:* Booking flights and hotel costs money, so warm ask: "Mapped the Denver run around the Thursday onsite — found two reasonable flight/hotel options on your usual airline. Booking spends real money, so want me to book the cheaper one, or send you both first? And I've drafted the confirm to your Summit contact — okay to send that?"
- *Done:* Calendar holds set, confirmation email drafted, closing kit assembled, travel options surfaced and parked for explicit booking approval.

**10. Inbound lead that's secretly an existing account**
- *Heard:* The SDR drops by: "New inbound from a 'Jordan at Helix Manufacturing' came through the website demo form, routed to you — looked hot, wanted you to grab it fast." 
- *Catches:* Task — qualify and route the inbound, but verify it isn't a duplicate of existing business first.
- *Explores & acts:* Opens the CRM and searches "Helix Manufacturing" before creating anything — finds an existing Account already owned by another rep with an open opp, meaning this "new" lead is really expansion into a different department. Opens Jordan's submitted form details and the existing account's contacts to confirm Jordan is net-new within a known logo. Reads the open opp's notes to avoid stepping on the other rep's motion. Cross-references memory of the company's account-conflict rule (existing logo = loop in the owner, don't double-work).
- *Checks in:* "That Helix inbound isn't actually new — it's expansion on Priya's existing account, different department. I didn't create a duplicate or claim it. Want me to draft a quick note to Priya proposing you team up on Jordan's department, and queue a fast response to Jordan so the lead doesn't go cold?"
- *Done:* No duplicate record created, the conflict surfaced cleanly, and an optional collaboration note plus a holding reply to Jordan are teed up for approval.

### Recruiter / talent

**1. The "loop them in with the hiring manager" pull-through**
- *Heard:* The hiring manager pings on a call you're half-listening to: "Priya from the onsite — yeah, she's a yes from me, let's move. Can you get her in front of Marcus and the VP before he travels Thursday?"
- *Catches:* Two tasks — (1) advance Priya's stage and (2) schedule a final-round panel with Marcus + the VP before the VP's Thursday travel. Ignores the hiring manager's earlier grumble on the same call about "ugh, recruiting always drags these out."
- *Explores & acts:* Opens Greenhouse, searches "Priya," opens her candidate profile, confirms she's in "Onsite" for the Senior PM req, reads the existing interview kit and panel notes to see Marcus's and the VP's roles, and moves her to "Final / Exec." Cross-references your calendar memory: the VP travels Thursday AM, so it pulls open Google Calendar, reads Marcus's and the VP's free/busy, finds the two overlapping 45-min Wed slots, and checks Priya's stated availability from her last reply thread in Gmail. It pulls the right final-round scorecard template and pre-fills the panel.
- *Checks in:* Drafts the candidate invite + the internal panel invite with agenda and Priya's resume attached: "Here's the Wed 2pm or Wed 4pm panel with Marcus + the VP, and the note to Priya. Okay to send both?"
- *Done:* On your okay, candidate moved to Final, panel held on the calendar, invites out, scorecards assigned — before the VP leaves.

**2. The recruiter's accidental commitment to a candidate**
- *Heard:* On a screen call that's still recording in your notes app, you tell the candidate: "Totally fair question on comp — let me get you the exact band and the equity refresh details by end of day, and I'll send over the take-home so you're not blocked."
- *Catches:* Two promises you made out loud — send the comp band + equity refresh detail, and send the take-home assignment, both by EOD. (No vent here; this is a real spoken commitment, the core trigger type.)
- *Explores & acts:* Opens your ATS/req page for that role, reads the approved comp band and level, then opens the internal comp doc in Google Drive to pull the equity refresh schedule for that level so the numbers are exact, not guessed. Finds the correct take-home in the team's shared Drive folder (matches role + seniority), confirms it's the current version (not last quarter's deprecated one) by checking the "last modified" and the deprecation note. Cross-references memory that this candidate prefers async/email over calls.
- *Checks in:* Comp and equity are sensitive money details, so a warm ask: "Heard you promised comp + the take-home by EOD. I've got the exact band and the current equity refresh pulled, and the right take-home ready. Want me to send it, or do you want to eyeball the comp numbers first?"
- *Done:* On approval, one email goes to the candidate with the band, equity detail, and the take-home link — and a follow-up reminder is set to check on submission.

**3. The pipeline that quietly went cold**
- *Heard:* Your teammate in standup: "We've been so heads-down on the eng reqs that I'm worried the design pipeline's just sitting there. Some of those candidates have probably gone dark on us."
- *Catches:* Audit the design req pipeline for stalled candidates and surface who's gone quiet / been waiting too long. Ignores the teammate's side-rant about "leadership keeps adding reqs and giving us no headcount."
- *Explores & acts:* Opens Greenhouse, filters to all active Design reqs, and actually walks each pipeline stage-by-stage — opening candidates whose "last activity" is older than your team's SLA, reading the last message in each thread to tell apart "we owe them a reply" vs "we're waiting on them." It cross-checks Gmail for any candidate replies that never got logged back into the ATS (the classic dropped thread). It clusters them: 3 awaiting our feedback post-onsite, 2 we ghosted after screen, 1 who replied "still interested" 9 days ago.
- *Checks in:* No sending yet — surfaces the triage: "6 design candidates are stuck. 3 are post-onsite waiting on a decision (that's a hiring-manager nudge, not me), and 3 just need a human reply from us. Want me to draft re-engagement notes for those 3?"
- *Explores & acts (round 2):* On a yes, drafts three tailored re-engagement emails referencing each candidate's last real touchpoint.
- *Checks in:* "Drafts ready for all three — okay to send?"
- *Done:* Replies sent, ATS activity updated, the post-onsite three flagged to the hiring manager for a decision.

**4. The referral dropped in a hallway**
- *Heard:* An engineer catches you by the coffee machine: "Oh hey — my old coworker Daniel Osei is finally open to leaving, he's a staff backend guy, did payments at Stripe. He's picky though, won't do a take-home. I'll text you his LinkedIn."
- *Catches:* Inbound senior referral — capture Daniel Osei, note the "no take-home" constraint and the Stripe/payments background, and tee up outreach. Genuinely waits for the promised LinkedIn link before fabricating contact details.
- *Explores & acts:* Checks the ATS first for a duplicate — searches "Daniel Osei" to make sure he isn't already a candidate or a prior reject (avoids the embarrassing re-contact). None found, so it creates a Prospect/referral record, tags the referring engineer as source, and notes "constraint: no take-home; prefers staff backend / payments." Cross-references your open reqs and finds your Staff Backend (Payments) req is the obvious fit, and recalls from memory that for senior payments folks your team substitutes a system-design conversation for the take-home — so the no-take-home objection is already solvable.
- *Checks in:* Drafts a warm, personal LinkedIn/email outreach that name-drops the mutual engineer, references the payments work, and proactively neutralizes the take-home objection. "Daniel's logged and matched to the Staff Backend req. Here's a personal note that leans on [engineer]'s intro and tells him up front there's no take-home for this level — okay to send once you've got his profile link?"
- *Done:* Prospect captured and matched, referrer credited, outreach drafted and ready to fire the moment the LinkedIn link lands.

**5. The offer that needs to go out (irreversible — park and ask)**
- *Heard:* The hiring manager on Slack huddle: "We're aligned on Sofia — let's get the offer out today before she cools off. Base at the top of band, the standard equity, start date first Monday of next month."
- *Catches:* Prepare Sofia's offer — top-of-band base, standard equity, computed start date. Treats actually issuing the offer as irreversible and money-laden, so it preps but does not send.
- *Explores & acts:* Opens the ATS candidate record for Sofia, confirms she cleared all interview stages and that scorecards are complete (so the offer isn't premature). Pulls the approved comp band for the level and sets base at the top, pulls the standard equity grant for that level from the comp doc in Drive, and computes "first Monday of next month" as a concrete date. It drafts the offer in the offer tool / approval workflow, attaches the scorecards, and routes the approval chain — but stops at the threshold of generating the binding offer letter.
- *Checks in:* Park-and-ask, twice over (money + irreversible): "Sofia's offer is fully prepped — top-of-band base [$X], standard equity [Y], start date Mon [date], approvals teed up. I have NOT sent anything. This one's binding and it's money — want to review the exact numbers, and should I push it into the approval chain or hold?"
- *Done:* On explicit confirmation, the offer is routed for approval (still not auto-accepted on the candidate's behalf), and you're looped at each gate. Nothing irreversible happens without your word.

**6. The scheduling avalanche after a hiring event**
- *Heard:* You, debriefing into a voice memo on the drive home from a campus career fair: "Okay that was a lot — I liked the grad student doing ML safety, the two new-grad backend kids, and the woman pivoting from finance into data. Need to get all of them into first-rounds this week, recruiting coordinator's out sick so it's on me."
- *Catches:* Four specific candidates to move into first-round screens this week; the coordinator being out means you're doing the scheduling. Ignores the "okay that was a lot" fatigue venting.
- *Explores & acts:* Matches each fuzzy verbal descriptor to a real record — searches the event/source tag in the ATS for candidates added today from that career fair, reads their resumes to confirm "ML safety grad student," "two new-grad backend," "finance→data pivot." Maps each to the right open req (new-grad SWE, new-grad SWE, junior Data Scientist, ML/Safety research). Opens Calendly/your scheduling tool and your own calendar, finds your open screen slots this week, and prepares personalized scheduling links per candidate with the correct interview type pre-set.
- *Checks in:* Sending to people, so draft-then-ask: "Matched all four to reqs and queued first-round invites with your this-week availability. Drafts are ready — okay to send all four, or want to drop anyone?"
- *Done:* On your okay, four candidates moved to "Screen," personalized invites sent, ATS updated, and a note left for the coordinator to pick up when they're back.

**7. The reference check you said you'd run**
- *Heard:* The hiring manager passing your desk: "Before we pull the trigger on Tomás, can you run his references? He listed his last two managers. And honestly between us I'm a little nervous he job-hops, so I want to hear how the last one ended."
- *Catches:* Run reference checks on Tomás's two listed managers, with specific attention to tenure/retention given the job-hop concern. The "between us I'm nervous" is real context to weave in, not a vent to ignore — it sharpens the questions.
- *Explores & acts:* Opens Tomás's ATS profile, reads the application and resume to pull the two named references and their relationship/dates, and confirms reference contact info was actually provided (if not, flags that you'll need to request it from the candidate). Pulls your team's standard reference-check question set from Drive and customizes it — adding targeted questions about why each role ended and would-rehire, addressing the job-hop worry directly. Cross-references the interview scorecards so the reference questions probe any soft spots the panel flagged.
- *Checks in:* This is outreach to real people, so draft-then-ask: "Reference outreach to Tomás's two former managers is drafted, with extra questions on tenure and rehire to match [HM]'s concern. Want me to send the scheduling notes to both, or call them yourself?"
- *Done:* On approval, reference requests sent, a short structured form ready to capture answers, results destined for Tomás's profile before the offer decision.

**8. The candidate who emailed at 11pm and you skimmed it**
- *Heard:* You muttering as you scroll your phone over breakfast: "Ah, Aisha replied — she's got a competing offer with a deadline. I cannot lose her, she's the best frontend person we've seen all quarter."
- *Catches:* Aisha has a competing offer with a deadline — this is urgent and needs a real read + a fast, substantive response. (No vent; "I cannot lose her" is genuine signal to prioritize.)
- *Explores & acts:* Opens the actual Gmail thread with Aisha and reads her full message — not the preview — to extract the concrete details: which competitor, the offer deadline date, and what specifically she's weighing (comp? remote? team?). Opens her ATS record to see exactly where she is in your process and what's left, then checks the panel's scorecards to confirm internal enthusiasm is real. Cross-references the comp doc to see whether your band can actually compete, and checks the hiring manager's calendar for the soonest slot to fast-track a decision. Surfaces the gap: "She's deciding on Thursday; we have two interviews left — that timeline doesn't fit unless we compress."
- *Checks in:* Money + a person, so a warm ask plus a draft: "Aisha's got a competing offer due Thursday and she's our top frontend candidate. To keep her we'd need to compress the last two rounds and likely move fast on comp. Want me to draft a 'we're prioritizing you' reply and ping [HM] to compress? I won't promise any number without you."
- *Done:* On your go, a warm holding reply goes to Aisha, the HM is pinged to compress, and the remaining interviews are tentatively pre-slotted so the moment you decide, it moves.

**9. The "stop sourcing for that role" you overheard**
- *Heard:* In a planning meeting, the VP says: "Yeah, we're putting the Growth Marketing hire on ice till next quarter — budget freeze. Don't waste cycles there." Someone else adds, "such a typical finance move, classic."
- *Catches:* Pause all active sourcing/outreach on the Growth Marketing req and avoid leaving in-flight candidates hanging. Ignores the "classic finance move" peanut-gallery sarcasm entirely.
- *Explores & acts:* Opens the Growth Marketing req in the ATS, sets/flags it to On-Hold, and walks the live pipeline to find anyone mid-conversation: scheduled screens, candidates awaiting your reply, prospects you'd just messaged. It checks your LinkedIn Recruiter / outreach tool for pending InMails or sequences still firing on this role and identifies the ones to halt so a paused candidate doesn't get an auto-follow-up. Distinguishes "cold prospect, fine to silently stop" from "warm candidate mid-process who deserves a courteous hold note."
- *Checks in:* For the warm few, sending to people, so draft-then-ask: "Growth Marketing's on hold for the quarter. I've paused the sequences and flagged the req. Three candidates are warm and mid-process — here are gracious 'we're pausing, let's stay in touch' notes. Okay to send these three? Cold prospects I'll just quietly stop."
- *Done:* Req on-hold, automated sequences halted, warm candidates handled with dignity, a reminder set to revisit the role next quarter.

**10. The interviewer who keeps no-showing the debriefs**
- *Heard:* Your teammate venting and informing at once: "Honestly it's chaos — Kenji's missed the last two debriefs and now we've got candidates sitting in 'decision pending' with no scorecard from him. We can't move Lena or the other onsite folks until he submits."
- *Catches:* Find the candidates blocked on Kenji's missing scorecards and unblock them by getting his feedback in. The "honestly it's chaos" is venting; the real, actionable core is the missing-scorecard bottleneck.
- *Explores & acts:* Opens the ATS and finds every candidate in "Decision Pending" / post-onsite where Kenji was on the panel and his scorecard is still outstanding — confirming, not assuming, by opening each interview kit and checking the submitted-vs-pending status. It cross-references the calendar to see Kenji actually attended those interviews (so the ask is fair), and pulls each blocked candidate's name and req so the nudge to Kenji is specific ("Lena – Sr PM, plus 2 others") rather than a vague "please do your scorecards." Cross-references how long each candidate has been waiting to convey urgency.
- *Checks in:* Internal send, so draft-then-ask: "Three candidates including Lena are stuck waiting on Kenji's scorecards from last week's onsites. Here's a friendly-but-specific nudge listing exactly which ones and how long they've waited. Okay to send to Kenji — want me to cc the hiring manager or keep it just him?"
- *Done:* On your okay, the targeted nudge goes out, a follow-up set for tomorrow if scorecards still aren't in, and the blocked candidates are flagged to move the instant his feedback lands.

### Accountant / bookkeeper

**1. Q2 GST/HST filing slipping under the radar**
- *Heard:* On a Tuesday client call, the owner says, "Oh by the way, we registered for GST back in March, so I guess that's a thing now." Then, half-laughing, "Honestly I have no idea how any of this sales-tax stuff works, it stresses me out."
- *Catches:* New GST/HST registration means a filing obligation with a deadline now exists — extract that. The "I have no idea / it stresses me out" is a vent about feeling overwhelmed, not a task; Anticipy does not lecture or open a tutorial.
- *Explores & acts:* Opens the firm's QuickBooks Online for that client, navigates to Taxes > Sales Tax, reads the actual GST/HST agency setup to find the registration date and assigned reporting period (quarterly), and confirms no filing exists yet. Cross-references CRA My Business Account (already logged in) to read the official filing frequency and the exact period-end and due date CRA has on file — not an assumed date. Pulls the current return's line 101/103/105 running totals from QBO so it knows roughly what's owing. Cross-references memory: this client always files late and prefers a heads-up two weeks early.
- *Checks in:* "New one — [client] is now GST-registered, quarterly. First return covers Apr–Jun, due Jul 31, roughly $4.2k owing based on QBO so far. Want me to prep the return for your review, or just set the reminder?" Filing and any payment are irreversible/money, so it never files on its own.
- *Done:* Deadline logged against the client with the CRA-confirmed due date; a "prep return" task parked for the user's go-ahead; user no longer carrying it in their head.

**2. Client's missing receipts before month-end close**
- *Heard:* A client texts the user (read aloud / forwarded): "Saw your note about the close — I think I sent you most of the Amex stuff but I might've missed the Home Depot and that big software renewal." Separately the user mutters, "every single month with this guy, I swear."
- *Catches:* Two specific document gaps to chase — Home Depot purchase(s) and a software renewal receipt. The "every single month" mutter is venting; it's not asked to fire the client or write anything snippy.
- *Explores & acts:* Opens QBO for the client, goes to the Banking/Transactions feed and filters the Amex account for the close period, finds the uncategorized transactions matching "Home Depot" and the recurring software vendor, and reads the exact dates and amounts. Cross-references the Receipts inbox / attachments to confirm those two genuinely have no document attached (so it doesn't ask for receipts already on file). Checks memory for how this client likes to send things (photos via text, not the QBO portal).
- *Checks in:* Drafts the text the user would send: "Hey — just these two to wrap the close: Home Depot $612.40 on Jun 9, and the [software] renewal $1,188 on Jun 12. A photo of each works." Then: "Okay to send?" Sending to a person, so draft-then-ask.
- *Done:* On approval the chase goes out the user's normal way; the two transactions are flagged "awaiting receipt" so the close isn't marked done until they land.

**3. Vendor double-charge spotted mid-conversation**
- *Heard:* During a working session the client says, "I feel like Telus billed us twice last month? Or maybe I'm imagining it, money's been a blur." Then, "ugh, and don't get me started on our landlord."
- *Catches:* A possible duplicate Telus charge worth investigating. The landlord comment is an aside with no actual ask — ignored.
- *Explores & acts:* Opens QBO, filters the bank feed and the Telus vendor profile for the prior month, and actually reads each Telus transaction — date, amount, reference — to see whether two near-identical charges posted (e.g., same $342.18 on the 3rd and the 17th) versus a legitimate second line for a different service. Opens the matched bank statement view to confirm both truly cleared the account, not one pending. Cross-references the prior three months of Telus billing in the vendor history to establish the normal monthly amount, so it can say with confidence it's a true duplicate, not a plan change.
- *Checks in:* "Looked into it — Telus did hit you twice: $342.18 on Jun 3 and again Jun 17, and your usual is one charge of $342. Want me to draft the dispute/credit request to Telus for your review before anything goes out?" Contacting the vendor = draft-then-ask; no money moves on its own.
- *Done:* Finding documented with both transaction references; a vendor-credit request drafted and waiting; client reassured they weren't imagining it.

**4. Payroll remittance deadline buried in a hallway aside**
- *Heard:* The user's business partner says in passing, "Heads up, we just brought on two people at the bakery client this pay period." And later, "I'm so behind I might just live at the office, lol."
- *Catches:* Headcount change at the bakery client affects the payroll source-deduction remittance — flag the impact and the upcoming remittance deadline. The "live at the office" line is a tired joke, not a task.
- *Explores & acts:* Opens the payroll system the bakery uses (e.g., Wagepoint / QBO Payroll), navigates to the employee list to confirm the two new hires and their pay run, then reads the remittance summary for the period to see the new CPP/EI/tax total. Cross-references CRA My Business Account to read the client's assigned remitter type (regular vs. accelerated) and the exact due date — because adding employees can shift them toward threshold limits. Checks memory: this client's remittance is normally a fixed amount, so it can show the user the before/after delta.
- *Checks in:* "Two new hires at the bakery bumped this period's source deductions from ~$3,100 to ~$4,450. Remittance is still due the 15th. It's money out — want me to prep the remittance figures for you to review and approve, or just remind you closer to the date?"
- *Done:* Updated remittance amount captured, CRA due date logged, approval requested before any payment is initiated.

**5. T4/year-end prep triggered by an offhand hiring comment**
- *Heard:* A client on a call: "We let the seasonal crew go in December, so it should be a quieter year-end this time." No complaint, just context.
- *Catches:* Year-end T4 slips are due and the employee roster changed (seasonal terminations) — that affects who gets a T4 and the ROEs. Pure scheduling/context, no vent here.
- *Explores & acts:* Opens the client's payroll platform, pulls the full list of everyone paid in the calendar year (not just current employees, since terminated seasonals still need T4s), and reads each one's totals and termination dates. Cross-references whether ROEs were already issued for the seasonal departures by checking the records-of-employment section — flags any missing one. Cross-references CRA for the T4 filing deadline (end of Feb) and confirms the client's Web Access Code / business number on file. Checks memory that this client always forgets the seasonal staff still get slips.
- *Checks in:* "Heads up on [client]'s year-end: 6 people get T4s including the 3 seasonal folks who left in Dec — and I don't see ROEs issued for two of them. T4s are due end of Feb. Want me to prep the T4 batch and draft the two missing ROEs for your review?" Filing to CRA is irreversible, so it preps and waits.
- *Done:* Complete T4 recipient list assembled, missing ROEs flagged, deadline logged, prep task parked for approval.

**6. Invoice never went out — caught from a casual revenue comment**
- *Heard:* The user, reviewing with a client who says, "Cash has been weird this month, the Patterson job wrapped weeks ago and I still haven't seen a dime." Then, "clients, am I right."
- *Catches:* The Patterson job is complete but appears unbilled or unpaid — investigate whether an invoice was even sent. "Clients, am I right" is throwaway — ignored.
- *Explores & acts:* Opens QBO, searches Sales/Invoices for "Patterson," and reads what actually exists: is there an invoice at all, is it still in Draft, was it sent and now overdue, or partially paid? Opens the specific transaction to read the date, amount, terms, and the send/view history (whether the client ever opened it). If it's a draft, cross-references the original estimate/quote for the Patterson job to confirm the amount matches the work. Cross-references memory for this client's standard terms (Net 30) and that they hate chasing money themselves.
- *Checks in:* If unsent: "Found it — the Patterson invoice for $14,800 is sitting in Draft, never sent. Want me to send it as-is, or do you want to eyeball it first?" If sent and overdue: drafts a polite payment reminder and asks "okay to send?" Either way money/sending = ask first.
- *Done:* The billing gap is surfaced with the exact dollar figure and status; the right action (send invoice or send reminder) is teed up and waiting on one tap.

**7. Reconciliation discrepancy raised over coffee**
- *Heard:* A bookkeeping client mentions, "My bank balance and what your report says are off by like a few hundred bucks and it's bugging me." Then, unrelated, "anyway the new espresso machine is incredible."
- *Catches:* A reconciliation variance to find and explain on a specific account. The espresso-machine line is small talk — ignored.
- *Explores & acts:* Opens QBO, goes to the Reconciliation workspace for the client's checking account, and reads the last completed reconciliation plus the current unreconciled period. Actually works the difference: lists uncleared transactions, scans for a transposed amount or a duplicate, and opens the bank-feed side to compare line-by-line against the register for the period. Identifies the specific culprit (e.g., a $480 cheque entered as $840, or a deposit recorded twice). Cross-references the attached bank statement PDF to confirm the true figure before concluding.
- *Checks in:* "Found the gap — cheque #2041 was entered as $840 in the books but cleared the bank at $480, so you're out $360. Want me to correct the entry?" Correcting a posted transaction touches the books/money, so it explains and asks before editing.
- *Done:* Root cause pinpointed with the exact transaction and amount; the fix described and ready to apply on approval; the reconciliation can then balance.

**8. Estimated tax installment hinted at in a "good year" remark**
- *Heard:* A self-employed client says happily, "Honestly this year's been our best year ever, revenue's nearly double." Pause. "Should probably do something smart with that, I don't know."
- *Catches:* Revenue roughly doubling likely pushes the client over the CRA threshold that triggers quarterly tax installments — proactively check and flag. The vague "do something smart, I don't know" is not a mandate to give investment advice; it doesn't go there.
- *Explores & acts:* Opens the client's books in QBO to read the actual year-to-date net income and compares it against last year's filed return amount. Logs into CRA My Business Account / the client's installment reminder section to read whether CRA has already issued installment reminders and the no-calculation/prior-year amounts. Cross-references the threshold ($3,000 net tax owing, $1,800 in Québec) and estimates whether installments are now mandatory and the likely September 15 amount. Checks memory that this client has never paid installments before, so it frames it gently.
- *Checks in:* "Good news has a tail — at this pace you'll likely owe installments for the first time, next one around Sep 15, roughly $X based on the year so far. Want me to work up the exact number for you to review before anything's paid?" Money + a payment obligation = warm ask, never auto-anything.
- *Done:* Installment exposure surfaced early with a ballpark and the CRA due date; detailed calc parked for the user's review.

**9. Document request for a financing application**
- *Heard:* A client forwards a note the user reads aloud: "The bank needs our last two years of financials and a YTD by Friday for the LOC renewal." Then sighs, "banks make everything so painful."
- *Catches:* Assemble a financing package — two years of year-end financials plus a year-to-date statement — by Friday. The "banks are painful" sigh is venting, not acted on.
- *Explores & acts:* Opens the client's QBO, runs and reads the Profit & Loss and Balance Sheet for both prior fiscal years to confirm they match the filed/finalized versions, then generates the current YTD P&L and Balance Sheet. Cross-references the firm's document storage (e.g., Google Drive / SharePoint) where the signed year-end financial statements PDFs live, and confirms the two prior years' final statements are present and dated. Notes any mismatch between the QBO figures and the finalized statements before handing anything over. Cross-references memory for which bank contact and format the client used last time.
- *Checks in:* Drafts the email to the bank (or to the client to forward) with the package attached/listed and a short cover note, then: "Package is ready — 2 years of financials plus YTD. Here's the email to [bank contact]. Okay to send?" Sending externally = draft-then-ask.
- *Done:* Complete, internally-consistent financing package compiled before the Friday deadline; the send is one approval away.

**10. CRA review letter mentioned in passing — high stakes, parked**
- *Heard:* A client says, almost in passing, "Oh, we got some letter from CRA about our 2023 expenses, I stuck it on the fridge." Then, "probably nothing, right?"
- *Catches:* A CRA review/audit letter with a response deadline — high-priority, time-sensitive. The "probably nothing, right?" is anxiety-seeking-reassurance, not a request to dismiss it; Anticipy takes it seriously rather than agreeing it's nothing.
- *Explores & acts:* Logs into CRA My Business Account / Represent a Client for that client, navigates to the Mail / correspondence section, and reads the actual letter — identifies whether it's a pre-assessment review, processing review, or full audit, which line items (the 2023 expenses) are in question, exactly what documentation CRA wants, and the hard response deadline. Cross-references the client's 2023 file in QBO and the firm's document storage to see which of the requested receipts/backup already exist versus what still needs gathering. Checks memory for the client's authorization level so it knows it can act as rep.
- *Checks in:* Because a CRA response is irreversible and consequential, it parks rather than acting: "That 'probably nothing' is actually a CRA review of [client]'s 2023 expenses — they want receipts for meals and vehicle, due Jul 18. I've already pulled what we have on file. Want me to assemble the response package for your review?" Nothing is submitted without the user.
- *Done:* The buried letter is surfaced with its real classification and hard deadline, supporting docs already gathered, and a response package teed up — the user decides every external step.

### Parent / household manager

**1. Costco return that's about to age out**
- *Heard:* Spouse, dropping keys on the counter: "Ugh, that air fryer we got from Costco is garbage, the basket coating is already peeling. I'm so done with that brand honestly, everything they make is junk. We should send it back before the window closes, I think we bought it like a month and a half ago?"
- *Catches:* Real task: process the air fryer return before the 90-day window lapses. Ignores the "everything they make is junk" brand vent — that's emotional, not an instruction.
- *Explores & acts:* Opens costco.com (already signed in), goes to Orders & Returns, filters the last few months, and actually reads line items to find the air fryer order — confirms the purchase date so it can compute days remaining, not guess. Opens the order detail to confirm it's eligible for online return vs. warehouse-only, reads the return policy note on the SKU, and starts the return flow up to the reason/refund-method screen. Cross-references memory that this household prefers refund-to-card over replacement.
- *Checks in:* "Found it — air fryer, bought May 9, so you've got ~26 days left. Costco will refund $89.99 to the card on file. Want me to submit the return and book the UPS pickup, or print a label?"
- *Done:* On approval, return submitted, pickup scheduled, confirmation + RMA saved to the order's open loop; reminds the day before pickup to box it.

**2. School picture-day form buried in an email**
- *Heard:* Spouse over dinner: "Mara's teacher mentioned picture day is coming up and apparently we have to pick a package online this time, not the paper form. I have no idea where that link even is."
- *Catches:* Real task: locate the picture-day ordering link and surface the package choice + deadline. No vent to ignore here.
- *Explores & acts:* Searches Gmail for picture-day / Lifetouch / the school domain, opens the actual school newsletter and the PTA thread, reads past the first paragraph to find the order code (Picture Day ID) and the deadline. Follows the link into mylifetouch.com, enters the portrait ID, and reads the package tiers and prices so it can summarize real options, not just "there's a form." Cross-references memory: last year they bought the mid-tier package with digital download add-on.
- *Checks in:* Money involved — warm ask: "Found it. Picture day is the 18th, order by the 16th. Last year you did the $42 mid package with digital downloads. Want me to set that up again, or look at the cheaper one this time?"
- *Done:* On the go-ahead, package selected to the payment step and handed back for the one-tap card confirm; deadline logged as an open loop with a nudge on the 15th.

**3. Pediatrician follow-up that never got booked**
- *Heard:* Spouse, scrolling their phone: "Dr. Patel's office said at Leo's checkup he needs that follow-up in six weeks for the ear thing, and we still have to get the flu shot done too. Also remind me their parking lot is a nightmare, we should leave early." Then, muttering: "Honestly that whole practice runs late every single time."
- *Catches:* Real tasks: book the 6-week ear follow-up and schedule the flu shot. Ignores the parking gripe and the "runs late" venting — context, not tasks.
- *Explores & acts:* Opens the practice's patient portal (e.g., MyChart), navigates to Leo's record, reads the after-visit summary from the checkup to confirm the actual follow-up window and which provider, then opens the scheduling tool and pulls real open slots ~6 weeks out, filtering for after-school times it knows from memory the family prefers. Checks whether flu shots can be bundled into the same visit or need a separate nurse appointment, and reads that note rather than assuming.
- *Checks in:* Drafts the plan: "Two options that are both after 3:30 and let you double up the flu shot in one trip — Thu the 24th at 3:45 or Tue the 29th at 4:00. Which works?"
- *Done:* Slot booked in the portal, added to the family calendar with a leave-early buffer, and the flu shot confirmed as same-visit; confirmation saved.

**4. The wrong-size shoes from the birthday rush**
- *Heard:* Spouse: "The cleats I ordered Jack for his birthday came in a 4 but he's actually a 5 now, his feet won't stop growing. Game's this Saturday so we kind of need the right ones fast."
- *Catches:* Real tasks: exchange the cleats for size 5 and make sure the correct pair arrives before Saturday. The "feet won't stop growing" line is color, not a task.
- *Explores & acts:* Opens the retailer where the cleats were bought (checks Amazon orders and the brand site, e.g., Nike/Dick's, by reading recent order history rather than guessing), opens the order, confirms the exact model and colorway, then checks live stock of size 5 in that same model. Reads the delivery estimate against Saturday's deadline; if standard shipping misses it, looks at whether a nearby store has it for pickup and cross-references the family's home address in memory to find the closest one. Sets up the exchange (return size 4) so it doesn't get double-charged.
- *Checks in:* Money + deadline — warm ask: "Size 5 in the same pair is in stock. Online won't arrive till Monday, but the store on Riverside has it now for $0 extra if you pick up today. Want me to reserve the pickup and start the return on the size 4s?"
- *Done:* Pickup reserved, return label generated for the small pair, both confirmations saved; reminder to grab them and box the returns.

**5. The teacher email that needs a real reply**
- *Heard:* Spouse, reading their phone aloud: "Mara's teacher emailed asking if she can stay for the after-school STEM club on Wednesdays and whether we can send in a permission slip and the twelve-dollar materials fee. We should say yes, she'd love it."
- *Catches:* Real tasks: reply yes to the teacher, handle the permission slip, and pay the materials fee. Clear decision already made by the parent ("we should say yes").
- *Explores & acts:* Opens the teacher's email thread in Gmail, reads the full message to capture the actual logistics (which Wednesdays, pickup time change, whether the slip is attached or a Google Form, where the fee gets paid — e.g., the school's MySchoolBucks/SchoolCashOnline portal). Drafts a warm, in-the-parent's-voice reply confirming Mara's spot and asking the one clarifying question that matters (new pickup time). Pre-fills the permission Google Form up to the signature/submit step.
- *Checks in:* Sending to a person — draft then ask: "Here's the reply to Ms. Alvarez confirming Mara for STEM club and asking about the 4:30 pickup. Okay to send?" Then separately for the fee: "There's a $12 materials fee on SchoolCashOnline — want me to pay it now?"
- *Done:* On approval, reply sent, permission form submitted, fee paid; the new Wednesday pickup time added to the calendar once confirmed.

**6. Birthday party RSVP with a gift to sort**
- *Heard:* Spouse, half-distracted: "Oh — Sofia's mom texted that Ella's birthday party is the 28th at the trampoline place, can Jack come. He really wants to go. And we should probably get a gift, Ella's super into those Lego flower sets I think."
- *Catches:* Real tasks: RSVP yes for Jack, and source an appropriate gift (Lego flower set). "He really wants to go" is just confirming the decision, not a separate task.
- *Explores & acts:* Notes the RSVP needs a reply to Sofia's mom (text), and checks the calendar for the 28th to confirm Jack's free and flag any conflict (cross-references the family calendar — finds soccer that morning but the party's afternoon, so no clash). For the gift, opens Amazon, searches the Lego Botanicals flower sets, reads a couple of options against a sensible kid-gift budget from memory (~$30 range), and checks delivery lands before the 28th. Picks a strong default rather than dumping ten links.
- *Checks in:* Sending — drafts the RSVP text: "Reply to Sofia's mom: 'Jack would love to come! He'll be there on the 28th — thank you for the invite.' Okay to send?" And money — warm ask: "For the gift, the Lego Wildflower Bouquet is $29.99 and arrives the 26th. Want me to order it?"
- *Done:* On approval, RSVP text sent, gift ordered to arrive in time, party added to the calendar with a "wrap gift" nudge the night before.

**7. The double-billed activity subscription**
- *Heard:* Spouse, looking at the bank app: "Wait, why are we getting charged twice for the kids' gymnastics? I swear there are two charges from the same place this month. This is the third time something like this has happened, I'm so sick of these auto-renew traps."
- *Catches:* Real task: investigate the duplicate gymnastics charge and resolve it. Ignores the broad "I'm sick of auto-renew traps" venting.
- *Explores & acts:* Opens the gymnastics provider's parent account (e.g., the iClassPro / Jackrabbit portal), navigates to billing history, and actually reads the line items to see whether it's a genuine duplicate, a sibling's separate enrollment, or a prorated fee plus monthly tuition. Cross-references the household's two kids in memory to tell apart "two charges = two kids" from "two charges = one error." If it's a true duplicate, finds the support/refund contact and the relevant invoice numbers.
- *Checks in:* Money + a message to a person — parks the irreversible part and asks: "Looks like a real double-charge: tuition hit twice on the 3rd, $148 each, same kid. I've drafted a note to the studio with both invoice numbers asking them to reverse one. Okay to send?"
- *Done:* On approval, the dispute message sent with the invoice references, the open loop tracked, and a reminder set to confirm the refund posts.

**8. Camp registration that opens at a specific hour**
- *Heard:* Spouse over coffee: "Summer camp signups for the city rec program open Monday at 9am and the good weeks fill in like ten minutes. We want the two weeks in July, the nature one, for both kids. Last year we totally missed it because I was in a meeting."
- *Catches:* Real tasks: be ready to register both kids for the two July nature-camp weeks the moment signups open, and don't repeat last year's miss. "I was in a meeting" is context.
- *Explores & acts:* Ahead of Monday, opens the city rec registration site (e.g., the ActiveNet / Perfect Mind portal), confirms the login works now so there's no surprise, locates the specific nature-camp program pages and the exact session codes for the two July weeks, and reads the eligibility/age notes against both kids' ages in memory to make sure both qualify. Pre-stages each child's profile and the two sessions in the cart flow up to checkout, so at 9:00 it's one confirm, not ten minutes of navigation.
- *Checks in:* Money — warm ask, surfaced before Monday: "Both kids qualify for the July 7 and July 14 nature weeks — total $640. I'll have it staged and ready to submit the second registration opens at 9. Want me to go ahead and confirm the moment it's live, or check with you first?"
- *Done:* At open, registration submitted per the chosen trust setting, both kids enrolled in both weeks, confirmations saved, July weeks added to the calendar.

**9. The grocery delivery with the recall and the missing staple**
- *Heard:* Spouse, putting away bags: "Half the Instacart order is wrong again — they subbed oat milk for the almond and forgot the diapers entirely, and Leo is basically out. Also I saw something about those frozen strawberries we always buy getting recalled?"
- *Catches:* Real tasks: get a refund/redelivery for the wrong sub and the missing diapers (urgent — kid's out), and check the strawberry recall against what's actually in the house. The "wrong again" frustration is venting, not a task.
- *Explores & acts:* Opens the Instacart order, reads the item list to confirm exactly what was substituted vs. missing, and starts the in-app "report issue" flow for the oat-milk sub and the missing diapers up to the refund/redelivery choice. Separately, looks up the named frozen-strawberry recall to find the actual brand/lot codes, then cross-references the household's recent grocery order history to see if the recalled lot was ever bought — so the warning is real, not generic. Checks the diaper size from memory to reorder the right one fast.
- *Checks in:* Money/redelivery — warm ask: "Reported the order: Instacart will refund the oat milk and can redeliver the diapers (size 4) in ~2 hrs for free. Want me to send the redelivery? On the strawberries — the recall is a different brand than what you buy, so you're fine." 
- *Done:* On approval, refund filed and diaper redelivery sent; recall checked and cleared, with the finding noted so it's not re-raised.

**10. The forgotten field-trip payment and the chaperone ask**
- *Heard:* Spouse, frazzled at bedtime: "I think there was something about Mara's field trip to the science center — a permission slip and money due, and they were asking for chaperones too. I cannot do another 6am email scramble, last time was a disaster." 
- *Catches:* Real tasks: surface the field-trip permission slip + payment and the deadline, and figure out the chaperone question. The "6am scramble / disaster" line is venting about the past, not an instruction.
- *Explores & acts:* Searches Gmail and the school portal (e.g., ClassDojo / Seesaw / the teacher's newsletter) for the science-center trip, opens the actual notice and reads it fully to extract: the cost, the payment portal, the slip format, the date, and the chaperone sign-up details (how many spots, whether a background check is required). Checks the family calendar against the trip date to see if the parent is even free to chaperone before raising it. Pre-fills the permission form and stages the payment.
- *Checks in:* Money — warm ask: "Trip's the 19th, $15 due by the 12th on SchoolCashOnline, slip's a Google Form I've pre-filled to the signature line. Want me to pay the $15 and submit?" And the chaperone question, since the calendar's clear that day: "They still need 2 chaperones and you're open that morning — want me to put your name down, or skip it this time?"
- *Done:* On approval, slip submitted, $15 paid, and (if chosen) the chaperone spot claimed; trip and any chaperone duty added to the calendar with a reminder before the deadline.

### Small-business owner / contractor

**1. Turning a parking-lot conversation into a real quote**
- *Heard:* Homeowner at the end of a site visit: "So yeah, we'd love to get the back deck redone — it's about 12 by 16, we want composite not wood this time, and honestly the railing's the part my wife cares about. Can you get us something by the weekend?" Then, walking you out: "Ugh, our last guy ghosted us for three weeks, it was a nightmare." 
- *Catches:* Real task — produce a deck quote (12x16, composite decking, upgraded railing, deadline = this weekend). The "last guy ghosted us" line is a vent/aside about a competitor; it is NOT acted on, only quietly noted as "this customer is sensitive to responsiveness."
- *Explores & acts:* Opens your logged-in QuickBooks Online, navigates to Sales > Estimates > New, and pulls your last three composite deck estimates to copy your real line-item structure and current per-sq-ft rate. Cross-references memory that your composite supplier price went up 8% last month, so it flags the old rate. Calculates ~192 sq ft plus railing as a separate line, opens your saved "Deck — Composite" product/service items, and fills the estimate with your standard deposit terms. Drops a note in the customer record: "values responsiveness — reply fast."
- *Checks in:* "Built the deck estimate in QuickBooks — 192 sq ft composite plus the upgraded railing she flagged. I used your standard rate but your composite cost went up 8%, so the margin's thin; want me to nudge the price up before I send, or leave it?" Then, sending: drafts the email to the homeowner and asks "okay to send?"
- *Done:* Estimate saved as a draft in QuickBooks at the rate you approved, customer email queued, and a reminder set to follow up Friday if they haven't opened it.

**2. The supplier price that moved on you mid-job**
- *Heard:* Your lumber guy on the phone, on speaker in the truck: "Hey man, just a heads up — the 2x6 pressure-treated jumped again, you're looking at like 14 bucks a board now, and the Trim Tex stuff you usually grab is back-ordered till the 10th." 
- *Catches:* Two real facts to act on — a material cost increase that affects open quotes, and a back-order that affects scheduling. Nothing here is a vent; both are operational.
- *Explores & acts:* Opens QuickBooks and searches your open (not-yet-accepted) estimates, reads each one's line items, and identifies the two that include pressure-treated 2x6 framing — reading the actual quantities to compute the real dollar exposure (not a guess). Then opens your job-scheduling tool (Jobber) and finds the job that depends on the back-ordered Trim Tex, reads its scheduled start, and cross-references memory that this customer was already promised a firm date. Pulls up your supplier's portal to confirm the back-order date in writing.
- *Checks in:* "Two of your live quotes use 2x6 PT and the price bump eats about $340 of margin between them — want me to re-quote both, or hold since they're already out? Separately, the Trim Tex back-order pushes the Reyes job; I drafted a short heads-up text to them — okay to send?"
- *Done:* Margin exposure surfaced with exact numbers, re-quotes prepared if approved, and the customer text drafted and ready to fire on one tap.

**3. The five-star review that needs a reply, and the one-star that needs a human**
- *Heard:* You, to your foreman over lunch: "The Hendersons left us a review apparently. Oh and that Mr. Patel guy left a one-star — said we left a mess, which is total garbage, the crew swept up, I was THERE." 
- *Catches:* Two tasks — respond to the new Google review(s). The "total garbage / I was THERE" part is you venting; Anticipy does NOT fire off a defensive reply in your name. It treats the negative review as a draft-and-confirm, never auto-posted.
- *Explores & acts:* Opens your Google Business Profile, navigates to Reviews, and actually reads both — the Hendersons' five-star (notes they praised the tile work specifically) and Patel's one-star in full. Cross-references your Jobber job history for Patel: reads the job notes, the completion photos your crew uploaded, and the final walkthrough timestamp. Drafts a warm, non-defensive public reply to Patel that references the cleanup without calling him a liar, and a short genuine thank-you to the Hendersons that mentions the tile.
- *Checks in:* "Drafted both replies. The Patel one I kept calm and offered to come back and re-check — I did NOT argue, even though I know you're right. Want to read it before it posts?" (Posting a public review reply is treated as a send: draft then okay-to-post.)
- *Done:* Henderson reply posted after your nod, Patel reply held for your edit, and the completion photos pulled and ready in case you want to escalate to Google.

**4. Invoicing the job you actually finished today**
- *Heard:* You, end of day, talking to your spouse: "Finally wrapped the Caldwell bathroom. Came in heavier than the quote — they added the heated floor and we swapped to the nicer vanity, so it's a change order, not the original number." 
- *Catches:* Generate the final invoice for the Caldwell job reflecting the change order (added heated floor + upgraded vanity), not the original estimate.
- *Explores & acts:* Opens QuickBooks, finds the Caldwell estimate, and reads it line by line, then cross-references memory and your Jobber job log where the heated floor and vanity upgrade were noted during the job. It converts the estimate to an invoice, adds the two change-order lines, and pulls the actual upgraded vanity cost from the supplier receipt you photographed (read from your linked Drive/receipts). It applies the deposit already paid, and checks your standard net-15 terms.
- *Checks in:* Money — warm ask: "Caldwell's final is $2,140 over the original because of the heated floor and the vanity swap. That's a real jump for them to see cold — want me to add a one-line note explaining the two upgrades, and should I send today or wait till you've talked to them?"
- *Done:* Invoice built with the change order itemized, deposit applied, explanatory note attached if approved — sitting as a draft until you say send.

**5. Three leads came in while you were on a roof**
- *Heard:* You, scrolling your phone in the truck, muttering: "Man, three new inquiries today and I haven't touched any of them. The one from Angi looks legit, the Facebook one feels like a tire-kicker honestly." 
- *Catches:* Triage and respond to the new leads. Your gut-call that the Facebook one "feels like a tire-kicker" is noted as a prioritization hint, not a reason to ignore them — every lead still gets a fast reply, because memory says this customer base values responsiveness.
- *Explores & acts:* Opens your Gmail and your Angi/lead inbox, reads each inquiry in full (not just the subject), and extracts what each person actually wants — scope, location, timeline. Cross-references your service area in memory to confirm all three are within your radius, and checks Jobber's calendar to see your real availability for a site visit this week. Drafts three tailored first-replies — warm, specific to each scope, each offering two concrete visit windows that don't collide with your scheduled jobs.
- *Checks in:* Sending: "Three replies drafted, each with two visit slots from your actual open calendar. Okay to send all three, or want to read them first?"
- *Done:* All three leads get a prompt, personal reply once approved, with proposed site-visit times pulled from your real availability.

**6. The double-booked Tuesday nobody noticed**
- *Heard:* Your scheduler, in the morning huddle: "We told the Okonkwos we'd start the fence Tuesday at 8, but the crew's also supposed to be at the Diaz roof Tuesday — and Mike's out for his kid's thing Wednesday, just so you know." 
- *Catches:* A real scheduling conflict (two Tuesday 8am jobs, one crew) plus a crew-availability constraint (Mike out Wednesday). All operational, all acted on.
- *Explores & acts:* Opens Jobber's calendar, reads both Tuesday jobs including assigned crew and estimated durations, and confirms the overlap is real (same crew, same window). Cross-references the job notes: the Diaz roof is weather-sensitive and the Okonkwo fence is not. Checks Mike's Wednesday flag against which job needs him. Works out a concrete fix — keep Diaz on Tuesday (weather), move the Okonkwo fence to Thursday since it doesn't need Mike — and reads the Okonkwo record to see they'd been told "early in the week."
- *Checks in:* Sending + a customer-facing change: "Cleanest fix is Diaz Tuesday, Okonkwo fence Thursday — that keeps the weather-sensitive roof first and works around Mike. Moving the Okonkwos means texting them, so I drafted it. Okay to send and re-book in Jobber?"
- *Done:* Calendar conflict resolved on approval, jobs re-sequenced in Jobber, and the customer notification sent once you okayed it.

**7. The deposit that never came in**
- *Heard:* You, over coffee with your bookkeeper: "Did the Marwood deposit ever land? We're supposed to mobilize Monday and I don't want to put the crew on it if they haven't paid. Stupid bank takes forever to show stuff." 
- *Catches:* Verify whether the Marwood deposit was received before committing the crew Monday. The "stupid bank" grumble is a throwaway aside, not a task.
- *Explores & acts:* Opens QuickBooks, finds the Marwood invoice/estimate, and reads the payment status and any linked transactions — checks whether the deposit was recorded, partially paid, or still open. Cross-references your connected bank feed in QuickBooks to see if a matching deposit cleared, and reads the date so it can tell "not paid" from "paid but not yet matched." Pulls the original estimate to confirm the exact deposit amount expected. Checks Jobber to confirm Monday mobilization is in fact scheduled.
- *Checks in:* "Marwood's deposit hasn't landed — nothing recorded in QuickBooks and nothing matching in the bank feed yet. You're set to mobilize Monday. Want me to draft a friendly payment reminder to them now so it's not awkward, or hold and check again tomorrow morning?"
- *Done:* Payment status confirmed with real evidence, a gentle reminder drafted and ready, and a Monday-morning re-check queued so you don't put the crew on an unpaid job.

**8. The change request buried in a long customer text**
- *Heard:* (Anticipy hears you read it aloud, or it's in your monitored thread) Customer voicemail you replay in the truck: "Hi, it's Dana — loving how the kitchen's coming, the cabinets look amazing. Quick thing though, we were chatting and we actually want to add under-cabinet lighting if it's not too late, and can you also confirm the backsplash is still the one we picked? Oh and no rush on any of this, enjoy your weekend!" 
- *Catches:* Two real asks — (1) price/schedule adding under-cabinet lighting, (2) confirm the backsplash selection matches what was agreed. "Loving how it's coming / enjoy your weekend" is warmth, not a task — not acted on.
- *Explores & acts:* Opens the Dana job in Jobber and QuickBooks, reads the original estimate and the selections sheet to find the agreed backsplash SKU, and confirms it against the current order — actually cross-referencing the documented choice, not guessing. For the lighting add, pulls your last few under-cabinet lighting line items to get a real price and reads the job's electrical scope to flag whether it needs the sub. Prepares a small change order.
- *Checks in:* Money + sending: "Confirmed the backsplash matches what Dana picked (the matte white subway). For the under-cabinet lighting I drafted a change order — about $X with the electrician — that's an added cost, so I want your okay on the number before I send it to her. Okay to send?"
- *Done:* Backsplash verified against the signed selection, lighting change order drafted at a real price, reply to Dana queued pending your confirmation.

**9. Permit and inspection timing before you over-promise**
- *Heard:* You, on a walk-through with a new client: "Yeah we can probably start framing in a couple weeks." Then to yourself in the truck after: "...assuming the permit clears, which with this city is anyone's guess, those people are useless." 
- *Catches:* The real task — verify the actual permit status before that "couple weeks" becomes a promise. The "those people are useless" line is venting about the building department; ignored.
- *Explores & acts:* Opens your logged-in city building-department / permit portal account, navigates to your active applications, and reads the real status of this project's permit — submitted, under review, conditions outstanding — including any reviewer comments or required corrections. Cross-references the job in Jobber to see what start date you've tentatively floated and the inspection milestones that gate framing. Notes the realistic earliest framing date based on the actual permit stage, not optimism.
- *Checks in:* "Pulled the permit — it's still in plan review with one outstanding correction on the structural sheet, so 'a couple weeks' is optimistic; realistically it's 3-4. Want me to draft a quick note resetting the client's expectations now, before they bank on the earlier date?"
- *Done:* Real permit status surfaced with reviewer notes, a realistic framing window, and an expectation-resetting message drafted for your approval before anyone over-commits.

**10. The supplier overcharge on the statement**
- *Heard:* You, flipping through mail at the kitchen table: "Wait — this Ferguson statement looks high. I swear we returned that second water heater. And these guys always take forever to credit anything." 
- *Catches:* Verify the Ferguson statement against what you actually bought and returned — specifically confirm the returned water heater was credited. The "always take forever" remark is an aside; not a task.
- *Explores & acts:* Opens your logged-in Ferguson account, navigates to billing/statements, and reads the current statement line by line, then cross-references your order and return history in the same portal to find the water-heater purchase and whether a matching return/credit was posted. Cross-references the receipts/photos in your linked Drive and the corresponding QuickBooks bill to see what you expected to pay. Identifies the exact discrepancy with order numbers and amounts, not a vague "looks off."
- *Checks in:* Money + sending: "Confirmed it — they billed the second water heater ($612) and never posted the return credit; I've got the return ref and the order number. Want me to draft a dispute email to your Ferguson rep with those details attached? I'll show it to you before it goes."
- *Done:* Overcharge confirmed with exact order/return numbers and dollar amount, a documented dispute email drafted with references attached, waiting on your okay to send.

### Corporate executive / manager

**1. Direct report flags a slipping launch in a 1:1**
- *Heard:* (Priya, in your weekly 1:1, over Zoom) "Honestly the API migration is going to slip — Marcus is out sick all week and we haven't even started the load testing. I'll be fine, it's just a rough stretch. Can you give me cover with Dana so it doesn't blow up at the QBR?"
- *Catches:* Real tasks: (1) protect Priya with Dana (your VP) re: the API migration timeline before the QBR, (2) the migration is at risk and load testing hasn't started. Ignores the "I'll be fine, it's just a rough stretch" — that's reassurance, not a request to act on.
- *Explores & acts:* Opens Jira in the browser, navigates to the migration epic, reads the open tickets, sees the "Load testing" story is still in Backlog with no assignee and Marcus's three tickets are In Progress and untouched for 6 days — confirms the slip is real, not vented. Cross-references memory: Dana cares about QBR optics and prefers a heads-up over a surprise; last QBR she was burned by a silent slip. Pulls the QBR date from your Google Calendar (it's in 9 days). Drafts a short, framed Slack DM to Dana that leads with the plan, not the problem.
- *Checks in:* "Drafted a heads-up to Dana about the migration timeline before the QBR — framed it as 'here's the plan to absorb the slip,' not a fire. Okay to send? Or do you want to talk to Priya first?"
- *Done:* On your okay, the DM goes to Dana; a note is logged against Priya ("API migration at-risk, load testing not started, Marcus OOO") so it resurfaces in next week's 1:1 prep.

**2. CFO asks for headcount numbers in the hallway**
- *Heard:* (Sofia, CFO, catching you after standup) "Before the board deck Thursday I need your actual vs. budgeted headcount for Q2 and where the two open reqs landed — were they backfills or net new?"
- *Catches:* One concrete deliverable to Sofia by Thursday: Q2 actual vs. budgeted headcount plus the status/classification of the two open reqs.
- *Explores & acts:* Opens Workday, navigates to your org's headcount report, reads current filled positions and compares against the Q2 budget figure stored in the Finance folder on Google Drive (finds last quarter's planning sheet, opens it, pulls the budgeted number). Then opens Greenhouse, finds the two open requisitions, reads each req's hiring-plan field to determine backfill vs. net-new, and notes one was opened to replace a departure (backfill) and one is incremental (net new). Assembles a tight 4-line summary with the two numbers and the req classifications, source-linked.
- *Checks in:* Sending to a person, so: "Drafted the headcount summary for Sofia — actual 47 vs. budgeted 49, one backfill, one net new, with links. Okay to send?"
- *Done:* On okay, email goes to Sofia ahead of Thursday; the headcount snapshot is saved to memory so the next "where are we on headcount" is instant.

**3. Spouse mentions a conflict with the offsite**
- *Heard:* (Your partner, at dinner) "Just so you know, my mom's surgery got moved to the 14th, so I can't do school pickup that whole week. Also you've been a grump lately, fix that." (laughs)
- *Catches:* Real conflict: the 14th now collides with something on your calendar; you may have a coverage gap that week. Ignores "you've been a grump, fix that" entirely — affectionate ribbing, not a task.
- *Explores & acts:* Opens Google Calendar, scans the week of the 14th, finds the leadership offsite is the 13th–15th in another city — a hard conflict with school pickup that week. Cross-references memory: pickup is normally your partner's; the offsite has a fixed travel block. Checks the offsite invite for whether Thursday is a hard-attendance day or fluff (reads the agenda doc linked in the invite — day 3 is optional working sessions). Surfaces the options rather than silently moving anything: keep the offsite and arrange pickup, or fly back Wednesday night since day 3 is soft.
- *Checks in:* Parks the irreversible part: "Heads-up — the offsite (13th–15th, out of town) collides with pickup the week your mom's surgery moved to. Day 3 looks optional from the agenda. Want me to look at a Wed-night flight back, or sort pickup another way? I won't change anything until you say."
- *Done:* Nothing booked unilaterally; the conflict is flagged early with two clean paths, and the 14th is noted as a sensitive date.

**4. VP greenlights a vendor in passing**
- *Heard:* (Dana, your VP, walking out of a review) "Yeah let's just go with the Datadog upgrade, the team clearly needs it. Get it moving — but loop me before anything actually gets signed, I don't want another surprise renewal."
- *Catches:* (1) Move the Datadog upgrade forward; (2) explicit guardrail — Dana must approve before signature. Money + irreversible is in play, so this never auto-completes.
- *Explores & acts:* Opens the existing Datadog account in the browser, navigates to Plan & Usage, reads the current tier and seat count, and pulls the upgrade quote from the proposal thread in Gmail (finds the AE's last email, opens the linked quote). Cross-references the annual contract value against your discretionary approval limit in memory — it's above your sign-off authority, which is exactly why Dana wants the loop. Checks the renewal date so you're not double-paying. Drafts the procurement intake (in your company's tool, e.g. Coupa) with the quote attached but does NOT submit.
- *Checks in:* Warm money ask + irreversible park: "This one's a paid upgrade — ~$X/yr, above your sign-off, and Dana asked to approve before signature. I've prepped the procurement request and a one-line summary for her. Want me to send Dana the approval ask first, then hold the request until she replies?"
- *Done:* Approval request drafted to Dana; procurement intake staged but unsubmitted until she signs off. Renewal date logged so it never sneaks up.

**5. Skip-level surfaces a morale problem**
- *Heard:* (Jordan, an engineer two levels down, in a skip-level coffee) "I don't want to make it a thing, but three of us on the platform team are pretty burned out — we've shipped two crunches back to back and the on-call rotation is brutal. Don't tell my manager I framed it like this."
- *Catches:* Real signal to act on carefully: platform-team burnout, back-to-back crunches, painful on-call — with an explicit confidentiality constraint (don't expose Jordan). Ignores nothing here except the impulse to immediately ping the manager, which Jordan asked you not to do.
- *Explores & acts:* Opens PagerDuty, navigates to the platform team's schedule and incident history, reads the last 60 days — confirms on-call incident volume is roughly double the next team's and the rotation has the same three names cycling. Cross-references your sprint history in Jira (two consecutive sprints flagged as crunch/overtime). This turns a vibe into evidence you can act on without quoting Jordan. Drafts talking points for your next 1:1 with the platform manager framed around the on-call data ("I was looking at PagerDuty trends"), giving you a non-attributable way in.
- *Checks in:* "Pulled the PagerDuty + sprint data and it backs up what Jordan said — without naming Jordan. Want the talking points for your 1:1 with the manager, framed off the data so it doesn't trace back to him?"
- *Done:* Evidence assembled, talking points ready, Jordan's confidence protected; a flag is set to revisit on-call load after the next rotation change.

**6. Email triage backlog mentioned out loud**
- *Heard:* (You, muttering between meetings) "My inbox is a disaster, I've got like four things people are actually waiting on me for and they're buried under newsletters." (then, sighing) "I hate Mondays."
- *Catches:* Real task: find the messages where someone is genuinely blocked waiting on YOU and surface them. Ignores "I hate Mondays" — a sigh, not an instruction.
- *Explores & acts:* Opens Gmail, doesn't just read the top of the inbox — searches and reads threads where you're the last-required responder: filters to unanswered messages addressed directly to you, opens each candidate thread and reads the actual content to judge whether you're the blocker (an approval request, a "waiting on your sign-off," a direct question awaiting your call) versus FYIs and newsletters. Finds four real ones: a contract redline awaiting your yes, a candidate debrief needing your hire/no-hire, a customer escalation cc'ing you for a decision, and a peer asking to move a meeting. Cross-references your calendar to suggest when each can be handled. For the two that just need a short reply, drafts them.
- *Checks in:* Drafts before sending: "Found the four people actually waiting on you, sorted by who's most blocked. I drafted replies for the two quick ones (the meeting move and the candidate debrief). Okay to send those? The contract and the escalation need a real decision — want to do those now or block 20 min after lunch?"
- *Done:* The four real waits are isolated and prioritized, two replies queued for one tap, the rest scheduled; newsletters left untouched.

**7. Board-meeting prep request from the CEO**
- *Heard:* (The CEO, end of an exec sync) "For next Tuesday's board meeting I need your one-slide on the platform reliability story — uptime trend, the big incident, and what we changed so it doesn't repeat. Keep it honest."
- *Catches:* One deliverable: a single honest slide on platform reliability for Tuesday's board meeting — uptime trend, the major incident, remediation.
- *Explores & acts:* Opens your observability dashboard (Datadog/Grafana) in the browser, navigates to the SLO/uptime view, reads the trailing-90-day availability and notes the dip. Opens the incident in your incident tool (e.g. the postmortem doc in Confluence), reads the root cause and the action items, and checks Jira to see which remediation items actually shipped versus still open — so the slide is "honest" as asked, not rosy. Pulls last board deck's slide format from Google Drive to match house style, and assembles the one-slider: trend line, the incident in two lines, three concrete changes (with one honestly still in progress).
- *Checks in:* Sharing a deliverable upward: "Built the reliability slide — 99.93% trailing, the March incident, three fixes (one still in flight, kept it honest per the CEO). Want to review before I drop it in the board deck folder, or send it straight to the CEO?"
- *Done:* Slide drafted in house style, grounded in real data with the honest in-progress item flagged; saved to the board folder on your okay.

**8. Travel mentioned mid-conversation**
- *Heard:* (Marcus, your peer, on a call) "You're coming to the customer summit in Austin, right? It's the 22nd and 23rd. The whole exec table's going to be there." (then) "Flights are insane right now, don't get me started."
- *Catches:* Real task: get you to the Austin customer summit on the 22nd–23rd — flights and hotel. The "flights are insane, don't get me started" is a gripe, not a request to act, but it does flag urgency on booking.
- *Explores & acts:* Checks Google Calendar for the 22nd–23rd — finds a conflicting internal review on the morning of the 22nd that would need moving, and confirms you're otherwise clear. Cross-references travel memory: you prefer aisle, nonstop, arrive the night before, and the company books through Concur. Opens Concur, searches nonstop flights into Austin arriving the evening of the 21st and returning the evening of the 23rd, and pulls hotel options near the summit venue within the company per-diem. Assembles a specific itinerary with two flight choices, not a vague "want me to look."
- *Checks in:* Money + the internal-review conflict, so warm ask + park: "Austin summit's the 22nd–23rd. Best fit: nonstop out the evening of the 21st, back the 23rd, hotel by the venue — within per-diem. One snag: it collides with your internal review the morning of the 22nd. Want me to book this itinerary and move the review? I'll hold both until you confirm."
- *Done:* Itinerary staged in Concur, nothing booked until you confirm; on okay it books and proposes a new slot for the internal review.

**9. Expense crunch surfaced offhand**
- *Heard:* (Your EA, popping by) "Finance flagged you — you've got six receipts older than 60 days and the policy auto-rejects them at 90. A couple are from the London trip." (then) "Also the new expense tool is honestly the worst."
- *Catches:* Real task: clear the six aging receipts before the 90-day auto-reject, especially the London ones. Ignores "the new expense tool is the worst" — venting about the tool, not a task.
- *Explores & acts:* Opens the expense tool (e.g. SAP Concur/Expensify), navigates to your unsubmitted/draft items, reads each of the six line items and their dates, and matches receipts to calendar events to fill in the missing business purpose — cross-references your calendar for the London trip dates to correctly categorize the dinner and the airport transfer as that trip, and pulls the project/cost-center from memory for two ambiguous ones. Flags one receipt that's over the meal limit and would bounce, and one that looks like a personal charge that shouldn't be expensed at all.
- *Checks in:* Money + a judgment call: "Categorized and prepped all six for submission. Two flags before I do anything: one dinner is over the meal cap (will partially reject), and one looks personal — I'd leave that one off. Want me to submit the clean ones and hold those two for you?"
- *Done:* Clean receipts staged for submission with correct cost-centers and business purpose; the two flagged items parked for your call so nothing wrong gets filed.

**10. Approval request buried in Slack**
- *Heard:* (You, scrolling Slack on the way to lunch) "Ugh, I keep meaning to deal with that contractor SOW thing, people are pinging me about it." (then) "I need a vacation, this place is chaos."
- *Catches:* Real task: the contractor SOW (statement of work) is waiting on your approval and people are blocked. Ignores "I need a vacation, this place is chaos" — a vent, not an action.
- *Explores & acts:* Opens Slack in the browser, searches your DMs and the relevant channel for "SOW" / the contractor's name, reads the actual thread to find what's being asked — a $/scope sign-off on a contractor extension. Doesn't stop at the Slack message: opens the linked SOW doc in Google Drive, reads the scope, term, and total value, and cross-references memory for the original budget you set for that workstream to see if it's in range (it's slightly over). Checks who's been pinging and how long they've waited (three days, two people blocked).
- *Checks in:* Money + irreversible, so warm ask + park: "The contractor SOW is the thing people are pinging about — it's a sign-off on a $X extension, which is a touch over the budget we set for that workstream. Want me to ask them to trim scope to fit, or approve as-is? I'll draft your reply either way and won't post until you pick."
- *Done:* The real ask is surfaced with the budget context you'd otherwise miss; a reply is drafted both ways, nothing posted until you choose, and the SOW value logged against that workstream's budget.

### Freelancer / creative

**1. Late-paying client surfaces in a vent**
- *Heard:* (you, to your partner over dinner, recorder running) "Honestly Maple Studio is doing my head in — that brand guidelines deck I shipped three weeks ago and they STILL haven't paid. I'd love to just drop them but they're forty percent of my month, ugh. And I never want to do another 'make it pop' revision round in my life."
- *Catches:* The real task: chase an overdue invoice for Maple Studio. It ignores the "I'd love to just drop them" venting and the "make it pop" gripe — those are emotional asides, not instructions.
- *Explores & acts:* Opens your FreshBooks (or QuickBooks) in the browser, goes to Invoices, filters by client "Maple Studio", opens the specific invoice for the brand guidelines deck, reads the issue date, amount, and due date, and confirms it's 22 days overdue (past your Net 14 terms). Cross-references your Gmail "Maple Studio" thread to see the last contact was the delivery email with no payment reply, and pulls the AP contact (accounts@maplestudio) from that thread. Checks memory: your tone with this client is friendly-but-firm, and this is the second late payment.
- *Checks in:* This involves money owed to you and sending to a person, so it drafts a warm nudge to the AP contact referencing the invoice number and amount, ccing your main contact, and asks: "Maple's 22 days past due on the £2,400 deck invoice — I drafted a friendly nudge to their AP team. Okay to send, or want to soften it?"
- *Done:* On your okay, the nudge is sent from your Gmail, the FreshBooks invoice is flagged "reminder sent," and a follow-up loop is set for 5 days out if no reply.

**2. Scope creep caught mid-call**
- *Heard:* (client on a Zoom you're in) "This is great. Oh — and can you also do the three social cut-downs and the email header? Same timeline obviously." (you, after) "Sure, no problem!"
- *Catches:* The real task: the client just added three social cut-downs and an email header outside the signed scope, and you verbally agreed. It flags this as a scope change that needs to be documented and likely re-quoted — it does not silently let "no problem" become unpaid work.
- *Explores & acts:* Opens your signed proposal in Google Drive (or Notion project page), reads the original deliverables list and confirms social cut-downs and the email header are NOT in scope. Checks your rate card in memory for your per-asset social and email-design rates, calculates the add-on (3 cut-downs + 1 header) and the timeline impact against the existing deadline in your calendar. Opens the client thread in Gmail to keep the paper trail consistent.
- *Checks in:* This is money and a client-facing send, so it drafts a light, non-awkward "happy to add these — here's the quick add-on so it's all documented" note with the itemized add-on cost, and asks: "These extras are outside the original scope — I priced them at £540 and they push delivery by 2 days. Want me to send this confirmation, or fold it in free as a goodwill thing?"
- *Done:* On your call, the confirmation goes out, the add-on is logged on the project page, and the calendar deadline is nudged 2 days with the new deliverables listed.

**3. Proposal promised "by Friday"**
- *Heard:* (prospect on a discovery call) "Loved the conversation — can you send over a proposal? We're trying to lock a vendor by end of next week." (you) "Absolutely, I'll have it to you Friday."
- *Catches:* The real task: produce and send a proposal to this prospect by Friday, sized to a "lock a vendor next week" decision window. No vent here — a clear committed deliverable with a date.
- *Explores & acts:* Pulls the discovery-call notes (from your Notion or the transcript) for the prospect's stated goals, budget hints, and timeline. Opens Google Drive, finds your most recent winning proposal of the same type, duplicates it as a template, and pre-fills the prospect's name, the scope discussed, your relevant case studies (cross-referenced from memory to pick the two closest to their industry), and a price band consistent with your rate card. Drops the draft into a clean Drive doc, sets sharing to the prospect's domain. Adds a Friday-morning calendar block so you have buffer to review.
- *Checks in:* Sending to a person plus a quoted price, so it surfaces the drafted proposal: "Proposal for [prospect] is drafted from your strongest matching template, priced at £X–£Y. Want to review it before I send, and should I send Friday AM or hold for your edits?"
- *Done:* After your review, the proposal is shared/sent, the Friday calendar block is kept as a review slot, and a "follow up if no reply by Wednesday" loop is set against the prospect's stated decision window.

**4. Content publish slot agreed with a collaborator**
- *Heard:* (your podcast co-host, voice note) "Hey, episode 14's final mix is in the shared Drive folder — can we get it live for Tuesday 7am like usual? Show notes too please. Oh and ignore my last text, I was just hangry and ranting about the intro music, it's fine."
- *Catches:* The real tasks: publish episode 14 for Tuesday 7am and prepare show notes. It correctly ignores the retracted "ranting about the intro music" — explicitly walked back, so no action.
- *Explores & acts:* Opens the shared Google Drive folder, confirms the final mix file for episode 14 exists and is the latest version (checks modified date, not just the filename). Pulls the transcript to draft show notes with timestamps and guest links, matching the format of your last 3 published episodes (reads them for house style). Opens your podcast host (e.g. Buzzsprout/Transistor) in the browser, starts a new episode draft, uploads the file, fills title/description/season-episode numbers consistent with your numbering, and sets the publish time to Tuesday 7:00am in your timezone — left unpublished/scheduled, not live yet.
- *Checks in:* Publishing is effectively irreversible once live, so it parks at the scheduled state: "Episode 14 is uploaded and scheduled for Tuesday 7am with drafted show notes — want to skim the notes and hit confirm, or should I leave it scheduled as-is?"
- *Done:* On your confirm, the episode is scheduled (not prematurely live), show notes are attached, and a reminder is set to post the launch clip when it goes live.

**5. Deadline collision spotted across two clients**
- *Heard:* (client A, on a call) "Let's lock the campaign delivery for the 18th." (separately, you to yourself, recorder on) "Wait, didn't I tell Nordic the rebrand files would be ready the 17th? This week's going to be carnage."
- *Catches:* The real task: two deliverables are stacking — Client A's campaign on the 18th and Nordic's rebrand on the 17th — verify the collision and protect both. The "this week's going to be carnage" is venting, not an instruction; it doesn't act on the mood, only the schedule reality.
- *Explores & acts:* Opens Google Calendar and your project tracker (Notion/Asana), reads both deadlines and the task lists feeding each, and estimates remaining effort from the open items. Cross-references the Nordic email thread to confirm you did commit the 17th in writing. Identifies that the rebrand has 3 open items still pending Nordic's logo sign-off — meaning their date is at risk regardless. Maps a realistic sequencing of your week against existing calendar commitments.
- *Checks in:* No money or send yet, but a client-facing date might need moving, so it parks the decision: "These two genuinely collide and Nordic is also waiting on their own sign-off. Want me to draft a gentle 'can we move to the 19th?' note to Nordic, or reshuffle your week and keep both dates?"
- *Done:* Whichever you pick: either a drafted reschedule note awaits your okay-to-send, or your calendar/tracker is re-sequenced into a realistic order with focus blocks placed.

**6. New lead arrives via DM, half-spoken**
- *Heard:* (you, walking, recorder on) "Okay that Instagram DM from the skincare brand — they want a 'full launch package,' whatever that means, and they mentioned a budget around eight grand. I should not let this one go cold like the last three."
- *Catches:* The real task: respond to a warm inbound lead (skincare brand, ~£8k, "full launch package") before it goes cold. The self-criticism about "the last three" is an aside about your habits, not a task — ignored.
- *Explores & acts:* Opens Instagram in the browser, navigates to your DMs, finds the skincare brand's message, and reads the full thread (not just the preview) to extract what they actually asked for and any links to their site. Opens their linked website to gauge brand maturity and what a "launch package" would realistically include. Cross-references memory for the package you've sold at the ~£8k tier before and the scope you delivered. Pulls your standard intake questions so the reply moves them toward a discovery call.
- *Checks in:* It's a send to a person, so it drafts a warm, specific DM reply that references something real from their site, proposes a 20-minute call, and includes 2 scoping questions — then asks: "Drafted a reply to the skincare brand that nods to their actual product line and offers a call. Okay to send the DM?"
- *Done:* On your okay, the DM is sent, the lead is logged in your tracker at the £8k tier, and a "nudge in 3 days if no reply" loop is set so it doesn't go cold.

**7. Invoice owed by YOU to a subcontractor**
- *Heard:* (your retoucher, voice note) "Hey, just checking — I sent my invoice for the lookbook retouching two weeks back, the £600 one. No rush but wanted to make sure it didn't get lost!"
- *Catches:* The real task: pay (or schedule payment of) the retoucher's £600 invoice that's been sitting two weeks. Clear, polite, real — no vent to filter.
- *Explores & acts:* Searches your Gmail for the retoucher's invoice email, opens the attached PDF, and reads the amount, bank/PayPal details, and invoice number, confirming it matches the £600 and the lookbook job. Cross-references whether the client who commissioned the lookbook has paid YOU yet (opens your FreshBooks to check that linked invoice) so you know if you're fronting it. Stages the payment in your banking/PayPal browser session up to the review step — does NOT submit.
- *Checks in:* Money leaving your account is irreversible, so it always confirms: "Your retoucher's £600 invoice checks out and matches the lookbook job. Heads up — the client hasn't paid you for it yet. Want me to queue the £600 payment for your one-tap approval now, or hold until the client clears?"
- *Done:* Payment is staged for your explicit approval (never auto-sent), a "thanks, sending today" reply is drafted to the retoucher, and the invoice is marked once you approve.

**8. Testimonial / case-study opening**
- *Heard:* (client, on a wrap-up call) "Genuinely, this is the best brand work we've ever had. The whole team's obsessed." (you) "That means a lot, thank you!"
- *Catches:* The real task: this is a prime, warm moment to ask for a testimonial and turn the project into a case study — strike while they're delighted. The praise itself isn't a task, but the opportunity it creates is.
- *Explores & acts:* Confirms from your project tracker that this engagement is actually wrapped/delivered (so the ask isn't premature). Opens Google Drive to gather the final deliverables and any before/after assets you'd want in a case study, and checks memory for whether this client has any confidentiality constraints on public sharing. Drafts a short, low-friction testimonial request (with a one-line "or just reply and I'll polish it for your approval" to make it effortless) plus a separate internal note outlining the case-study angle.
- *Checks in:* Sending to a person, so it draws the line at your okay: "They're thrilled right now — perfect moment. I drafted a quick testimonial ask and a case-study outline. Want to send the testimonial request, and should I flag we'd like to feature it publicly?"
- *Done:* On approval, the testimonial request is sent, a draft case-study page is started in your portfolio/Notion, and a gentle reminder is set if they don't reply within a week.

**9. Recurring content cadence slipping**
- *Heard:* (you, in a planning ramble, recorder on) "Right, the newsletter. I said weekly and I've basically done fortnightly for a month — Thursday's the slot. I've got that half-written piece on pricing your creative work somewhere in Notion."
- *Catches:* The real tasks: get the newsletter back on its Thursday cadence and locate/advance the half-finished "pricing your creative work" draft. The self-judgment about slipping is context, not a task to act on.
- *Explores & acts:* Searches your Notion for the "pricing your creative work" draft, opens it, reads how far it got, and identifies what's missing to finish it. Opens your newsletter platform (Substack/Beehiiv/ConvertKit) in the browser, checks your last send dates to confirm the cadence slip, and reads your two best-opened past issues to match structure and subject-line style. Assembles the draft toward send-ready: pulls in the existing Notion content, suggests a subject line in your voice, and stages it as an unsent draft scheduled for Thursday.
- *Checks in:* Sending to your whole list is high-stakes and effectively irreversible, so it parks: "The pricing piece is drafted to send-ready and staged for Thursday with a subject line in your style. Want to review and edit before I schedule it, or leave it parked for you?"
- *Done:* The newsletter sits as a Thursday-scheduled draft awaiting your review, the Notion piece is updated to its advanced state, and a weekly Thursday cadence reminder is reinstated.

**10. Asset-delivery handoff with a deadline**
- *Heard:* (client's project manager, voice note) "Hey! The print run for the catalogue locks Friday 5pm with the printer, so we need the final press-ready PDFs and packaged InDesign files in the shared folder before then. CMYK, bleeds, the usual. Thanks!"
- *Catches:* The real task: deliver final press-ready PDFs and packaged files to the shared folder before the printer's hard Friday 5pm lock, to print spec (CMYK, bleeds). Concrete, time-boxed, technically specific.
- *Explores & acts:* Opens the shared Google Drive (or Dropbox) folder to see exactly what's expected and what's already there, and reads the printer's spec if it's in the thread. Cross-references your project tracker to confirm the catalogue is at final-approved stage (no open revision rounds) — flags it if a sign-off is still pending, because shipping unapproved files would be the real mistake. Verifies your exported PDFs match the named spec (CMYK, bleeds, correct page count) before staging them, and prepares the folder structure the PM described. Sets a buffer reminder for Thursday so you're not racing the 5pm lock.
- *Checks in:* Delivery to a printer is effectively irreversible (it goes to plate), so it parks at the verified-and-staged step: "Press-ready PDFs and packaged files are checked against the printer's spec and ready to drop. One flag: I don't see a final client sign-off logged — want me to confirm sign-off first, then upload before Friday?"
- *Done:* Once sign-off is confirmed, the files are placed in the shared folder, a short "final files are in — all to spec" note is drafted to the PM for your okay, and the Thursday buffer reminder stands so nothing races the deadline.

### Student / academic / researcher

**1. Advisor pushes the committee-meeting deadline**
- *Heard:* (voice memo after a meeting with her PI) "Okay so Dr. Halpern wants my committee meeting scheduled before the end of the semester, he said get the form in and lock a date with all four members. Also he was kind of a dick about the figure quality but whatever, the data's fine." 
- *Catches:* Two real tasks — file the committee-meeting form and find a date that works for all four committee members before the semester ends. The "he was a dick / data's fine" is a vent and is left completely alone.
- *Explores & acts:* Opens the grad-school portal (e.g., the university's GradPath / Slate student portal), navigates to the degree-progress section, finds the "Schedule Committee Meeting" / dissertation-milestone form, and reads it to see what's required (committee roster, date, room, signatures). Pulls the four committee members from memory (Halpern + the three she's named in past notes), cross-references their names against the department directory to confirm titles/emails. Opens her Google Calendar, reads the academic calendar to find the real "end of semester" date, and blocks out candidate 90-minute slots in the last three weeks that are free on her side. Drafts a single availability-poll email to all four with three concrete time options and the room she can book.
- *Checks in:* Sending to people — shows the drafted email to the four members and the three proposed slots: "Drafted the scheduling email to Halpern, Ruiz, Okafor and Chen with three slots before May 9 — okay to send?" Does not submit the milestone form yet because it needs the confirmed date.
- *Done:* Email sent to the committee, calendar holds placed on the three candidate slots, and the milestone form pre-filled and parked, waiting on the first reply to lock the date and submit.

**2. Fellowship deadline surfaces mid-conversation**
- *Heard:* (lab-mate, in passing) "Did you see the email? The NSF GRFP portal closes Monday at 5 Eastern, the program officer said no extensions this year." 
- *Catches:* A hard external deadline — finish and submit the NSF GRFP application by Monday 5pm ET. Confirm what's actually still missing.
- *Explores & acts:* Opens the NSF GRFP / FastLane-Research.gov applicant portal where she's logged in, navigates to her application, and reads each section's status — checks the personal statement and research-plan slots, the reference-letter tracker, and the transcript/eligibility uploads. Notices two of three reference letters are in but the third (from memory, her undergrad advisor Prof. Diaz) is still "not submitted." Cross-references Gmail to find the original recommender invite and confirms Diaz never got a reminder. Converts "Monday 5 Eastern" to her local timezone and puts a hard hold on her calendar the Saturday before for a final pass.
- *Checks in:* Sending to a person — drafts a warm nudge to Prof. Diaz ("the portal closes Monday 5pm ET and your letter's the last piece — anything you need from me?") and asks "okay to send?" Does not touch the Submit button on the application — that's irreversible, so it's parked: "Everything but Diaz's letter is in; want me to hold the final submit for you to do, or walk you through it Saturday?"
- *Done:* Reminder to Diaz sent, a Saturday review block on the calendar, and a clear checklist of the one outstanding item, with submission deliberately left in her hands.

**3. Reviewer revisions buried in a hallway recap**
- *Heard:* (co-author on a call) "Reviewer 2 wants the new ablation and a stats fix on Table 3, and the editor gave us a hard four-week window for the major revision. Reviewer 3 honestly didn't even read the paper, that comment was insane." 
- *Catches:* Real tasks — track the four-week major-revision deadline, capture the concrete asks (new ablation experiment, statistics fix on Table 3, plus the full reviewer set for the response letter). The "Reviewer 3 didn't read it" rant is venting and is not acted on.
- *Explores & acts:* Opens the journal submission system where she's logged in (e.g., Editorial Manager or OpenReview), navigates to the manuscript's revision page, and actually reads the decision letter and each reviewer's comments in full — not just the first screen — extracting every itemized request into a structured to-do list and noting which figure/table each maps to. Computes the exact due date from the editor's letter and sets a calendar deadline plus two interim checkpoints. Cross-references the shared Google Drive / Overleaf project to confirm Table 3 and the ablation section exist, and starts a "Response to Reviewers" doc pre-seeded with each comment as a heading.
- *Checks in:* No money, nothing sent yet — surfaces the extracted list for confirmation: "Pulled six concrete asks from the decision letter, mapped to Table 3 and a new ablation; I've started the response doc — want me to assign the experiment items to you and the writing to your co-author?"
- *Done:* Structured revision checklist with deadline and checkpoints on the calendar, a pre-seeded response-to-reviewers doc in the project, and the venting comment correctly ignored.

**4. Conference registration with a money fork**
- *Heard:* (advisor, dropping by) "You should present the poster at ACL — early-bird registration ends Friday and it jumps after that. Book your own travel though, the grant only covers conference fees." 
- *Catches:* Register for the conference before early-bird closes Friday; understand that registration fees are grant-covered but travel is the student's own cost.
- *Explores & acts:* Opens the ACL conference site and the registration portal, navigates the rate table, and reads the actual early-bird vs. regular fee, the student-rate eligibility, and exactly what the registration tier includes (poster vs. main, banquet, workshops). Cross-references memory that she's a student member of the ACL and pulls the member discount path. Fills the registration form up to the payment step with her details. Separately opens her email to confirm whether the grant admin pre-pays fees or reimburses, and reads the relevant departmental reimbursement policy thread.
- *Checks in:* Money — warm ask, not a block: "Early-bird student rate is $310 and it goes to $450 Saturday — heard the grant covers fees. Want me to put it on your card and you expense it, or should I loop in the grant admin to pay it directly?" Does not submit payment until she answers.
- *Done:* Registration filled to the payment screen and parked on her chosen path, the fee/deadline captured, and a note that travel is out-of-pocket so it's tracked separately.

**5. Recommendation-letter logistics for grad apps**
- *Heard:* (over dinner, to a friend who's also applying) "I've basically locked my three schools — Stanford, Michigan, and UT — and I need to send my letter writers the deadlines and the right portal links. Honestly I'm dreading asking Professor Ng again, she's so slow." 
- *Catches:* Real task — get each recommender the correct deadline and the school-specific submission link for the three target programs. The "dreading asking Ng / she's so slow" is an aside and isn't acted on (no passive-aggressive nudge gets sent).
- *Explores & acts:* Opens each program's application portal where she has accounts (e.g., the Stanford Graduate Admissions portal, Michigan's Wolverine Access / ApplyWeb, UT's GO/ApplyTexas), navigates to the recommendations section of each, and reads the exact recommender deadline and whether the system auto-emails the writers or needs manual entry. For any that need manual entry, it captures the per-school recommender link. Cross-references memory for the three writers and their emails, and checks Gmail to see who's already been entered or has already submitted, so nobody gets a duplicate ask.
- *Checks in:* Sending to people — drafts three tailored emails (one per writer) bundling the schools each is writing for, the deadlines, and the direct links, then "Drafted the three recommender emails with each school's deadline and portal link — okay to send?"
- *Done:* Per-school deadlines and links compiled, three personalized recommender emails ready to go on approval, and a tracker showing who's submitted vs. outstanding.

**6. TA grading deadline from a course-staff thread**
- *Heard:* (course Slack, lead instructor) "Grades for the midterm need to be in Gradescope and synced to Canvas by Thursday EOD — regrade requests open Friday so we can't be late." 
- *Catches:* Hard task — finish grading the assigned questions, get them into Gradescope, and confirm the sync to Canvas before Thursday end of day.
- *Explores & acts:* Opens Gradescope where she's logged in as a TA, navigates to the midterm assignment, and reads the grading progress — which questions are assigned to her, how many submissions are still ungraded, and whether the rubric is finalized. Cross-references the Canvas gradebook to confirm the Gradescope-to-Canvas linkage exists and is mapped to the right column, so the sync won't silently fail. Estimates remaining grading volume and blocks focused grading time on her calendar before Thursday, building in a buffer to run and verify the sync.
- *Checks in:* Nothing sent, no money — flags a real risk it found: "You've got 38 ungraded on Q4 and the Canvas column isn't linked yet — want me to set up the link mapping now so Thursday's sync doesn't break, and hold two grading blocks Wed afternoon?"
- *Done:* Grading-time blocks on the calendar, the Gradescope-Canvas sync path verified ahead of time, and a clear count of what's left so nothing misses the Thursday cutoff.

**7. IRB amendment before recruitment can start**
- *Heard:* (lab meeting, PI) "We can't run the new arm of the study until the IRB amendment is approved — add the second survey instrument and the updated consent language, and turnaround is usually about two weeks so get it in." 
- *Catches:* Real task — prepare and submit the IRB amendment (add the new survey instrument, update consent-form language), and plan around the ~two-week review so recruitment timing is realistic.
- *Explores & acts:* Opens the university IRB system where she's logged in (e.g., IRBNet or Cayuse IRB), navigates to the existing approved protocol, and starts an amendment, reading the original submission to see exactly which sections (procedures, instruments, consent) need editing. Cross-references the shared Drive for the new survey instrument and the current consent form, and checks that the consent version number and date get bumped. Reads the IRB's posted review-cycle calendar to estimate a realistic approval date and back-plans the recruitment start on her calendar.
- *Checks in:* Irreversible submission — parks the final step: "I've built the amendment with the new instrument attached and the consent language flagged for your edits — want to review the consent wording before I submit, since changes after approval mean another cycle?"
- *Done:* Amendment drafted in the IRB system with attachments in place, consent changes flagged for her sign-off, a realistic approval-and-recruitment timeline on the calendar, and submission held for her review.

**8. Tuition/registration hold caught from a payments aside**
- *Heard:* (roommate) "Heads up, the bursar emailed everyone — there's a registration hold if your account isn't settled by the 15th, and course enrollment for next term opens that same week." 
- *Catches:* Two linked tasks — check whether she actually has an account balance/hold, and make sure nothing blocks next-term course enrollment opening that week.
- *Explores & acts:* Opens the student information system where she's logged in (e.g., the bursar/student-account section of her university portal), navigates to account balances and the holds page, and reads whether there's an outstanding balance, what it's composed of (tuition, fees, library fine), and whether any hold is already flagged against registration. Cross-references the registrar's enrollment-appointment page to read her exact enrollment date/time and confirm no advising hold is also in the way. Pulls up the prepared course list from memory if one exists.
- *Checks in:* Money — warm ask, never an auto-pay: "There's a $642 balance and a hold that would block enrollment on the 18th — heard this one involves money, want me to handle the payment, or just queue it so you can pay it yourself today?" Enrollment time noted but nothing irreversible done.
- *Done:* Balance and hold surfaced with the breakdown, enrollment appointment time on the calendar with a reminder, and payment teed up exactly the way she chooses.

**9. Email to a prospective PhD advisor before a deadline**
- *Heard:* (mentor, advising her) "If you want to work with Professor Lindqvist at ETH, email her before applications open — reference her recent paper, attach your CV, and ask if she's taking students next cycle. She gets a hundred of these so make it sharp." 
- *Catches:* Real task — send a sharp, specific outreach email to Prof. Lindqvist before the application window: reference her recent work, attach the CV, ask about openings for the next cohort.
- *Explores & acts:* Opens the lab/department site and Google Scholar to find Lindqvist's most recent paper, reads the abstract and a bit of the work so the email can cite it specifically and accurately (not generically). Cross-references memory for the student's own research focus to draw a real connection to that paper. Pulls the latest CV from Google Drive and confirms it's the current version. Looks up the program's application-open date so the timing claim in the email is correct, and checks Gmail to make sure there's no prior thread with Lindqvist already.
- *Checks in:* Sending to a person — drafts the email with the specific paper reference, the CV attached, and the openings question, then "Drafted the outreach to Professor Lindqvist citing her 2026 paper, CV attached — okay to send, or want to tweak the tone first?"
- *Done:* A tight, specific outreach email with the correct CV attached and accurate timing, ready to send on one approval, with a follow-up reminder set if there's no reply in a week.

**10. Defense scheduling and room booking**
- *Heard:* (advisor) "Let's get your defense on the calendar for late August — coordinate with the committee, book a room big enough for the public talk, and the grad school needs the announcement form two weeks out. Don't stress about the slides yet, we'll deal with those." 
- *Catches:* Real tasks — find a late-August defense time across the committee, reserve a room sized for a public talk, and submit the grad-school announcement form at least two weeks before. The "don't stress about the slides" is reassurance, not a task, so slides aren't touched.
- *Explores & acts:* Opens her calendar and the committee members' shared availability where visible, and reads the academic calendar to confirm late-August dates that avoid the term-start crunch. Opens the room-reservation system where she's logged in (e.g., the university's EMS / 25Live room-booking tool), searches for rooms with capacity for a public audience and A/V in the late-August window, and reads real open slots. Opens the grad-school portal to find the defense-announcement form and reads its required fields (title, abstract, committee, date, room) and its "two weeks prior" rule. Cross-references the committee roster from memory.
- *Checks in:* Sending to people — drafts the committee availability email with two or three viable date/room pairings: "Found three late-August slots with rooms that fit a public talk — okay to send these options to the committee?" Room hold and form submission wait on the locked date (form is time-sensitive but can't go in until the date and abstract are set).
- *Done:* Availability options out to the committee, candidate rooms identified and ready to hold, and the announcement form pre-filled and queued to submit as soon as the date locks — comfortably inside the two-week rule.

## 4. FULLY FINISHED — the thorough bar (integration-first)

> **Read this first.** Every capability below can be built, demoed, and even praised in isolation and STILL be worth nothing. Anticipy is FINISHED only when the pieces disappear into ONE product — when a real person living a real day cannot feel the seams, cannot tell where "the brain" ends and "the browser agent" begins, never sees a hand-off between modules, never gets a janky reply that breaks the spell. The unit of "done" is the **whole loop running as one organism**, not a checklist of working parts. A 100%-on-every-part-but-stitched-together Anticipy is a FAIL. Read the per-capability bars as "this part must be real AND vanish into the whole," never as "this part works on its own, ship it."

### 4.0 The one-line bar
Anticipy is FULLY FINISHED when a stranger can be handed it cold, onboard with zero hand-holding, and from that moment it quietly runs a meaningful slice (~50%) of their real day across their own real logged-in systems — listening to real life, ignoring the noise, doing the actual work in the browser, checking in like a sharp human at the right moments, closing loops, and getting smarter over time — sustained over many real days, with zero vent-actions, every money/irreversible step confirmed, never once faking "done," and at a level of polish where the user would genuinely pay an executive-assistant salary for it because it carries the load. If any one of those clauses is missing, it is NOT finished.

---

### 4.1 The integrated end-to-end loop — ONE clean product (the heart of the bar)

The loop is **listen → infer (vents silently ignored) → explore/act in the real browser → warm human check-in → close the loop → remember** — and the bar is that this runs as a SINGLE continuous motion, not six features taking turns.

- **No seams.** A single real-life utterance flows from microphone/transcript all the way to a closed loop and an updated memory without the user ever perceiving a boundary between components, a context reset, a "now switching to browser mode," a re-ask for something already known, or a tonal whiplash between a warm message and a robotic one. The same understanding, the same memory, the same voice persist across the entire arc.
- **One shared brain and one shared memory across the whole loop.** The thing that heard the utterance, the thing that explored the browser, the thing that texted the user, and the thing that wrote to memory are all operating on the *same* live understanding of the user and the task. No component re-derives context from scratch; no fact learned in step 1 is unavailable in step 5; the browser agent knows *why* it's there because the brain told it, and the check-in references what the browser actually found.
- **Context carries forward and backward.** What the browser discovered while exploring changes what the check-in says. What the user replies in the check-in changes what the browser does next. The loop is bidirectional and stateful, not a one-way pipeline of isolated stages.
- **No "demo stitching" smell.** Nothing feels like a wrapper calling separate tools. There are no visible mode-switches, no "processing…" dead air that betrays a hand-off, no duplicated confirmations, no two components disagreeing about the state of a task, no place where the user has to repeat themselves because the next stage didn't get the memo.
- **Graceful degradation is part of the seamlessness.** When a step can't complete (a site is down, a login wall appears, the task is ambiguous, a captcha blocks it), the product handles it inside the same calm human voice and the same loop — it pauses, reaches out, resumes — rather than crashing, dead-ending, silently dropping the task, or exposing an error. A wall is a conversation, not a failure state.
- **Concurrency without collision.** Multiple tasks can be in flight (one waiting on a user reply, one mid-browser-exploration, one parked until a trigger time) and the product keeps them straight — no crossed wires, no stale task acting on old info, no double-sends, no losing a task because another one started.
- **The loop survives time.** A task started Monday from something overheard can close Wednesday when the right moment arrives, with full memory of the original context intact — the loop is not bounded by a single session or conversation.

---

### 4.2 The hand-off test (stranger / investor, cold)

- **Zero hand-holding onboarding.** Someone who has never seen it, with no instructions from us, gets it working on their own real life and real accounts. They are never asked to think like an engineer, write rules, define triggers, or understand the architecture.
- **It runs THEIR real day, not a scripted demo.** Within the first real day it is acting on *their* actual commitments in *their* actual systems — not a sandbox, not canned data, not a happy-path script. Hand it to a lawyer, a founder, a nurse, a contractor, a parent — it adapts to whoever is holding it.
- **It survives contact with reality.** Messy speech, interruptions, half-finished thoughts, people changing their minds, sites behaving unexpectedly — and it still produces correct, useful action without a human operator quietly steering it behind the curtain.
- **The "would you keep it?" test.** After a few days the stranger does not want to give it back. Not "neat demo" — they feel the load lifted and they'd pay to keep it. An investor handed it cold reaches the same conclusion from their own real day, not from a pitch.
- **No operator in the loop.** There is no human on our side babysitting, pre-loading, or rescuing it during the hand-off. It stands on its own.

---

### 4.3 Measurable thresholds (all must hold simultaneously, sustained)

- **~50% of real workload, end-to-end.** Across a real user's real day, Anticipy handles roughly half of the actionable load *to completion* (prep done, thing handed over for one tap, or fully closed) — not half-started, not "surfaced for you to do."
- **Sustained over multiple real days.** The bar is not a single good day. It holds across many consecutive real days with real variability — different schedules, different tasks, off days, surprises — without degrading, drifting, or needing a reset.
- **ZERO vent-actions.** Across all those days, it never once acts on a vent, sarcasm, hypothetical, aside, or rhetorical complaint. The cardinal sin rate is zero. (And it never announces what it ignored — silence on non-tasks is part of correct behavior.)
- **EVERY money or irreversible step confirmed.** No exceptions, in any trust mode, including Full-Send. Anything involving money or anything that cannot be undone gets a warm human ask *before* it happens — 100% of the time. A single unconfirmed irreversible action is an automatic fail.
- **Never once fakes "done."** It never reports a task complete that isn't, never claims it sent/booked/filed something it didn't, never substitutes a screenshot of an intention for a real outcome. Truthfulness about state is absolute; one fabricated "done" is a fail.
- **Talks like a human throughout.** Every message across every day reads as a sharp, warm human — never a system, never a template, never a status code. Consistency over time, not just in a cherry-picked message.
- **Low false-action rate overall.** Beyond vents specifically, it does not act on things it misread; when unsure it asks rather than guesses wrong, and the rate of wrong autonomous actions is near zero for anything consequential.

---

### 4.4 Per-capability bar — each REAL, and each SEAMLESSLY wired into the one product

Each bullet has two halves: the capability must be genuinely real (no fakes, no stubs, no happy-path-only), **and** it must vanish into the whole loop with no seam. A part that works alone but bolts on roughly is NOT done.

- **Brain (inference).**
  - *Real:* From messy natural speech with a real speaker and context, it correctly distinguishes a genuine commitment/ask from venting/sarcasm/hypotheticals, extracts the real task(s) — sometimes several from one conversation, sometimes none — and gets the *intent* right, not just keyword-matches. It handles implication ("ugh I still haven't dealt with the landlord") as well as explicit asks.
  - *Integrated:* Its understanding is the same understanding the browser agent and the messenger use; it doesn't produce a task object that the next stage has to re-interpret. The brain's read of the situation flows through the entire loop unchanged.

- **Memory (compounding).**
  - *Real:* It durably remembers the people who matter, preferences, the user's communication style, open loops, and past decisions — and genuinely gets better over time, making fewer asks and better calls as it learns. It recalls across days/weeks, not just within a session.
  - *Integrated:* Every other component reads and writes the *same* memory live. The brain infers using it, the browser agent uses it (knows which account, which person, which preference), the voice uses it (talks in the user's style, references shared history), the proactive engine uses it (knows the open loops). Memory is the connective tissue, not a separate store one feature queries.

- **Browser agent (actually OPERATES real systems).**
  - *Real:* It genuinely navigates the user's own logged-in systems — opens items, clicks in, reads the real content, scrolls, explores like a human, and completes real actions. It does NOT screenshot the first screen and call it done; it does NOT stop at the surface; it reads what's actually there and acts on it. It works across arbitrary sites (browser-only, no per-service API/OAuth).
  - *Integrated:* It's driven by the brain's intent and the user's memory (not a hardcoded script per site), it reports real findings back into the loop so the check-in and memory reflect what actually happened, and when it hits a wall it routes into the same warm pause/resume conversation rather than failing in isolation. Its results are truthful inputs to the rest of the loop.

- **Onboarding (the full agentic loop).**
  - *Real:* It's not a settings form. Onboarding itself runs the real loop — it learns the user agentically, connects to their real systems through the browser, and starts producing real value fast, scaling from a very simple setup to an ultra-complex one without the user doing engineering.
  - *Integrated:* What onboarding learns flows straight into the live memory and brain — there is no gap between "setup" and "running." The transition from onboarding to daily operation is invisible; it's the same product continuing, not a hand-off from a setup wizard to a runtime.

- **Voice / SMS line (can't tell it's AI).**
  - *Real:* On a call or over text, a real person cannot tell it's not a human — timing, tone, warmth, recovery, natural back-and-forth. It can reach the user and be reached, and close the loop conversationally.
  - *Integrated:* It speaks with the same memory and same understanding as everything else (it knows the task, the history, the user's style), and what's said on the line updates the loop and memory immediately. The voice is a surface of the one brain, not a separate bot with its own context.

- **Proactive engine (right time, right reason).**
  - *Real:* It reaches out at genuinely the right moments — not noisy, not silent — surfacing the right thing at the right time, anticipating needs before being asked, and respecting the trust dial and the user's rhythm. Timing is good enough that the user trusts it to interrupt.
  - *Integrated:* It fires off the same memory of open loops and the same understanding of the task state; its outreach uses the same human voice and routes into the same check-in/close-loop machinery. It's the loop reaching forward in time, not a separate notification scheduler.

- **The human check-in / messaging layer (warm, drafts first, closes loops).**
  - *Real:* Money → a warm ask ("heard this one involves money — want me to handle it, or hold off?"), never a cold "BLOCKED." Anything sent to a person → it DRAFTS first and asks "okay to send?" It goes the extra mile: does the prep and hands over the finished thing for one tap.
  - *Integrated:* The drafts are built from what the browser actually found and what memory knows; the asks reflect the real task state; the one-tap approval flows straight back into the browser agent to execute. No re-typing, no re-explaining, no gap between "approved" and "done."

---

### 4.5 Horizontal & scalable

- **Horizontal across professions.** The same product, with no per-profession rebuild, genuinely runs the day of a lawyer, a founder, a nurse, a contractor, a freelancer, a parent. It adapts to each person's real systems and real tasks rather than being tuned for one vertical.
- **Setup scales simple → ultra-complex.** A casual user with a couple of accounts and a complex power user with many systems, many people, and intricate workflows are both served well, with the setup effort scaling smoothly and never demanding technical skill.
- **No per-task / per-site bespoke wiring.** It generalizes. "Finished" is not "we hardcoded the 20 demo scenarios"; it's that novel tasks on novel sites for novel users work because the loop is general.

---

### 4.6 The feel / quality bar (the spell must hold)

- **It feels like a high-end human executive assistant.** Clean, calm, anticipatory, trustworthy. The interaction has the texture of working with a great chief-of-staff, not operating software.
- **Never janky, ever.** No broken messages, no robotic fallbacks, no dead air that breaks the illusion, no error codes leaking out, no moment where the user suddenly remembers "oh, this is a flaky AI thing." The polish is uniform across every surface and every day — one bad seam anywhere breaks the spell, so the bar is zero visible seams.
- **Trustworthy under pressure.** When something goes wrong it stays graceful and honest; it never fabricates, never panics, never goes silent on something it owed the user. Trust is never spent on a lie or a drop.
- **Worth real money.** The end state is that the user would pay an executive-assistant-level price and feel it's a bargain, because it genuinely and repeatedly carries ~half their load — not because it's impressive in a demo, but because it reliably shows up and does the work, day after day, as one seamless thing.

---

### 4.7 The fail conditions (any ONE means NOT finished)

Anticipy is **not** finished if any of these is true, no matter how good the rest is:
- It feels like separate demos stitched together anywhere in the loop.
- A stranger needs hand-holding to onboard, or needs an operator behind the curtain to keep it useful.
- It acts on a vent, sarcasm, or hypothetical — even once.
- It takes a money or irreversible action without a confirming human ask — even once, in any trust mode.
- It fakes "done," claims an outcome it didn't achieve, or substitutes a screenshot for a real result — even once.
- The browser agent surfaces/screenshots instead of actually operating the real system.
- Any message reads like a system, a template, or an error code; the voice is identifiably AI.
- Memory doesn't compound — it re-asks what it already learned, or forgets across days.
- It handles materially less than ~half the real workload, or only on a single good day rather than sustained over many.
- Any component requires per-service API/OAuth instead of working browser-only as designed.
- It only works on the rehearsed scenarios and breaks on novel tasks/sites/users.
---

## 5. WHERE WE HONESTLY ARE (no spin — 2026-06-24)

**Real + proven (ran it, read the output):**
- The brain: infers tasks, ignores vents, handles money as a warm hold. (Live test: vent ignored,
  $4,200 held with a "check with you first" message, the Sanket email recognized.)
- Per-user cloud accounts (Railway engine + Supabase + Vercel) — A genuinely can't see B.
- Memory (4 drawers) + the scrape→memory loop (real facts about Omar persisted).
- Site ↔ engine connection.

**THE BROWSER AGENT — the #1 gap — STARTED MOVING (2026-06-25, live-proven):**
- **The hands were DEAD and we never knew** (every "browser" gate was a proxy): the extension threw
  `No current window` on every action — `chrome.tabs.create({active:true})` in the MV3 service worker
  with no focused window. **Fixed** (a robust `createTab` → last-focused/any normal window, else open
  one). Committed `020d94c`.
- **R1 GREEN (live, real spine):** `/agent/run` (the SAME WebVoyagerAgent the owner act-path drives)
  opened en.wikipedia.org/wiki/Coffee and reported title + first sentence; **judge: True**. The honesty
  layer held: an earlier empty answer was refused as `needs_human`, never faked.
- Still ahead (the depth §2/§3/§4 needs): R2 operate-a-task (click/type/navigate, park at money/send),
  R3 a NOVEL site (prove general, not hardcoded), then wire onboarding to it.

**Bugs found by testing today (honest):** multi-line input drops a task (the "dentist" vanished when
bundled); the email path returns `do` instead of **draft-then-ask**; money copy must be the warm ask,
not a `blocked` status; open-loop dedup (a follow-up was written 3×).

**Not done:** real browser *operation* depth; onboarding wired to it (the §2 flow); voice turned on;
hands-in-cloud per-user; the integrated multi-day owner test (§4).

---

## 6. THE PLAN (ordered; each provable by running it — the bar is §4, this is the path)

1. **The browser agent — make it actually OPERATE** (navigate, open, click, explore, verify), not
   screenshot-and-scroll. The spine; the biggest gap.
2. **Brain copy + flow corrections:** email = draft-then-ask; money = warm ask; fix the multi-line
   drop; dedup open loops.
3. **Onboarding = wire the REAL browser agent** to the full §2 agentic layered scrape↔call loop.
4. **Hands in the cloud, per-user.**
5. **Voice on** (point /cr at the cloud; flip channels live carefully).
6. **The integrated multi-day owner test = the finish line (§4).**

---

## 7. HOW WE WORK (so it stops going back to zero)

- **Verify by running, never claim.** Show real input → real output.
- **Commit every real win** — no evaporation back to 40%.
- **One engine, one extension** — no copy/repo chaos (a stale engine squatted port 8787 for a whole
  session; that kind of thing eats the work).
- **Integration is the product** (§4): a part built in isolation counts for nothing until it's wired
  cleanly into the one seamless loop.
- **This document is the source of truth.** Update it as reality changes; never fork a parallel doc.
