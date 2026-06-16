I have everything I need — the four research streams are rich and well-cited. This is a synthesis task, not a research task. Let me write the deliverable.

# Anticipy: What "Done" Looks Like, How To Build That Feel, and The Path There

---

# PART 1 — WHAT DONE LOOKS AND FEELS LIKE

## The first 60 seconds

You don't fill out a form. You answer one question.

The screen is near-black (`#0C0C0C`), a single line of cream serif text centered in a field of empty space: *"Before I start listening — who am I helping?"* You connect your Google account. Anticipy spends the next forty seconds reading you, not interrogating you: it pulls your last two weeks of calendar and the people you email most, and instead of a progress bar that says "Transcribing 71%," one word breathes in the center — *Reading your week.* Then the inference you didn't ask for, rendered as a quiet recap you can correct: *"You talk to Dana most. Tuesdays are packed. You have two kids — pickup matters."* You tap to confirm or fix one thing. That's onboarding.

This is the deliberate inversion of the graveyard's deepest wound. Limitless's own reviewer named it: the AI "doesn't know who the user is beyond what they've recently said, nor does it understand relationships, goals, or personal context" ([jock.pl](https://thoughts.jock.pl/p/voice-ai-hardware-limitless-pendant-real-world-review-automation-experiments)). The first 60 seconds exist to prove Anticipy already knows you — that it's an assistant who read the file before the meeting, not a recorder you have to train. And the consent is active and continuous, not a buried checkbox ([Aircall](https://aircall.io/blog/support/ai-voice-agent-privacy/)): a visible listening indicator, a one-tap pause that you can *see* is off.

## A real day living with it

**9:14am — the catch you didn't expect.** You're on the phone with your sister, half-complaining about logistics: *"...and I still have to get Mom's prescription before the pharmacy closes Friday."* You weren't talking to Anticipy. You forgot it was there — which is the entire point ("You put it on. You forget it's there." — anticipy.ai). You never open the app. But that evening, in the day's single digest, a line waits: *"Caught: pick up Mom's prescription before Fri 6pm. Want me to set a Thursday reminder?"* It heard the obligation buried three clauses deep in speech aimed at someone else. That is the product — "the inference… the task it caught that you didn't say."

**1:30pm — the quiet when you vented.** Bad meeting. You mutter to a coworker: *"Honestly I should just quit and move to the woods."* Nothing happens. No draft resignation, no job-search tab, no "I noticed you mentioned quitting — want me to…" The silence is *engineered*, and it is the most important feature in the product. The graveyard is littered with devices that acted with false confidence — Humane "bad at almost everything… confidently wrong" ([MKBHD/Dexerto](https://www.dexerto.com/tech/marques-brownlee-slams-humane-ai-pin-as-the-worst-product-hes-ever-reviewed-2646829/)); Apple pulled an entire proactive feature rather than ship a fabricated headline ([Axios](https://www.axios.com/2025/01/17/apple-ai-news-alerts-fake-headlines)). Anticipy's restraint here isn't an absence — it's the thing you'd feel viscerally if it failed. Acting on that vent would be "the cardinal sin" (`HANDOUT_2026-06-13.md:42`).

**2:45pm — "done; I'll call you at 2:45."** This morning your wife said, in passing, *"can you grab the kids at 3?"* You got one tight line at the time — *"Got it. I'll call you at 2:45 so you're not late."* No celebration, no "Task completed ✓." Now your phone rings. A warm, human voice — not a robot — reminds you. The loop closed where it mattered, on schedule, regardless of breakpoints ([Fischer et al.](https://dl.acm.org/doi/10.1145/2037373.2037402)). This is the canonical scene Omar returns to in every doc, and the bar is literal: "the 2:45 reminder call actually rings his phone" (`HANDOUT:45-48`).

**6:30pm — the calm report.** Not 12 pings across the day. One digest: *"Here's what I handled and what's waiting on you."* Three things done silently (calendar held, a draft to Dana prepared, a fact remembered), one thing waiting for your yes (the prescription reminder), nothing screaming. Twelve silent acts cost you one glance, not twelve interruptions ([Knock](https://knock.app/blog/building-a-batched-notification-engine); [Tian Pan](https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy)).

## The exact emotional payoff — named precisely

Not "delight." Not "magic." Three specific feelings, in this order:

1. **Unburdened.** The weight of remembering left your body without you noticing — "does this transfer cognitive load" is the literal prioritization test (`anticipy-product-vision.md:21-22`). You stopped carrying the prescription, the pickup, the draft.
2. **Caught.** Someone competent was paying attention to *your* life when you weren't — the relief of "it was already handled before I asked" ("Twenty minutes later, Anticipy had already filed the dispute" — anticipy.ai).
3. **Safe enough to forget it's there.** You trust it *because* it stayed silent on the vent. The silence is what earns the autonomy. This is the difference between Donna and Friend — Friend spent >$1M positioning AI as better than your humans and the public revolted ([SF Standard](https://sfstandard.com/2025/11/16/avi-schiffmann-friend-ai-pendant-loneliness-profile/)). Anticipy makes you show up *better* for your people.

The composite feeling has a name Omar already gave it: **a competent assistant you'd be upset to lose** (`HANDOUT:48`).

## The design language that produces that feel

- **Visual:** Charcoal `#0C0C0C`, cream `#F5F0EB`, warm-gray `#6B635B`, DM Serif Display headers; one centered pulsing circle, one word of state — *Listening / Thinking / Acting / Resting* (`ANTICIPY_PRD.md:33,56-60`). Whitespace is the premium tell — "brands confident enough to leave space empty signal they don't need to fill every pixel" ([Zamora](https://zamora.design/10-things-that-make-your-design-look-premium/)). One moment per screen, never the dense dev console it is today.
- **Motion:** Physics, never linear — "linear motion is the enemy of premium-feeling animation… it looks robotic and cheap" ([TryDemotion](https://trydemotion.com/blog/apple-style-animation-guide)). Task cards *settle* in with ease-out, never blink. The thinking latency becomes a choreographed reveal — tasks surfacing one at a time like an assistant reading your day back — not a dead spinner.
- **Voice/copy:** Human sentences, never machinery. "Calendar event made," never `done`. "I lost the thread for a moment. Try again," never a stack trace (`ANTICIPY_PRD.md:62-64`). Banned visible text: port numbers, JSON, model names, "Ingest," "Press Go." The 2:45 call is warm, never robot-voiced (task ground-truth).
- **Surfaces:** Pendant later ("brushed titanium, 8 grams, lighter than a house key" — anticipy.ai) → the Mac app + phone now. The app must *inherit* the marketing site's restraint, not introduce a second busier visual language. Premium = invisible until the receipt, exactly how Granola beat Otter by removing the bot from the room ([Granola](https://www.granola.ai/blog/meeting-note-tool-pricing-granola-vs-fireflies-fathom-otter)).

## The one-line litmus

**You know it's done when you vent about quitting your job and nothing happens — and twenty minutes later it quietly reminds you about your mom's prescription that you mentioned to someone else.** Silence on the vent, the catch on the buried real task: both in the same hour. That contrast *is* the product.

---

# PART 2 — HOW TO ACHIEVE THAT LOOK AND FEEL

## The act/ask/silent boundary — a scored gate, not a vibe

Score every candidate on two axes: **expected utility** = P(user acts) × value-if-acted, and **attention cost** = disruption given current context ([Tian Pan](https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy)). Then route:

| Route | Trigger | Rule |
|---|---|---|
| **SILENT-act** | Reversible AND touches no other person AND no money (reminder set, calendar held, draft prepared, fact remembered, cart loaded-not-bought). High confidence. | **This is the default.** Do it, write an in-app receipt, spend zero interrupt budget. |
| **SILENT-nothing** | Vent, sarcasm, joke, low-confidence weak signal. | The cardinal-sin guard. One-way bias toward silence. |
| **ASK** | Touches another human, hard to reverse, OR medium confidence on a real obligation. | Costs interrupt budget. Preview-before-execute. |
| **BLOCKED → one-tap handoff** | Money / captcha / 2FA / login wall. | The only hard stop. Hand back the smallest next step (`OWNER_ACTION_ENGINE.md:38`). |

**The reconciliation of the homepage vs. the constitution — prepare-then-park.** The site sells "already handled" (it filed the dispute); the law forbids auto-acting on a vent or auto-spending. The resolution Omar already wrote: *do everything up to the irreversible edge, then park it.* "DO it — as long as it doesn't 'press go'… a prepped item that turns out to be a vent just sits PARKED… the cardinal sin is structurally impossible for parked work" (`CONSTITUTION.md:59-67`). The feel reads "it's handled"; the truth underneath is "it's prepared and one yes away." **Any build that makes the homepage literally true — auto-canceling on an overheard gripe — violates the constitution.** Build to parked, market the feel.

## Cadence rules — the exact numbers so it never spams

- **Attention is a hard budget: 3 interrupts/day default, 5 ceiling**, visible to the decider as state. When depleted, a new candidate must *displace* a queued one (forces honest priority comparison), never stack ([Tian Pan](https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy)). Silent acts and the daily digest don't draw from this. This is the budget that the cold-boot bug — "once fired 6 real SMS in 36s" before InterruptGuard (`HANDOUT:125`) — proves is load-bearing.
- **The ASK bar must clear high P(act).** A dismissed interrupt is *net-negative* (spent budget + eroded trust); opened-no-action breaks even; acted-on is positive. If P(act) is low, it's a silent card or a digest line, not an interrupt.
- **Two clocks: urgency deadline (hard) + breakpoint opportunity (soft).** Hold non-urgent asks; release at the next *coarse* breakpoint — end of a call, end of a conversation, a speech pause beyond N seconds ([Fischer et al.](https://dl.acm.org/doi/10.1145/2037373.2037402); [arXiv 1711.10171](https://arxiv.org/pdf/1711.10171)). An always-listening device can *hear* its breakpoints — this is a gift no notification system normally has. The 2:45 call ignores breakpoints (hard deadline wins).
- **Two delivery lanes:** real-time (budgeted, time-critical only) and one daily digest (free, everything else). Throttle real-time per rolling hour.
- **Track dismiss-rate as a first-class health metric.** Fatigue lags engagement by ~3 weeks and hides inside "clicks" — a rising dismiss-rate is the early churn alarm that the act/ask boundary has drifted too aggressive ([Tian Pan](https://tianpan.co/blog/2026-05-13-background-agents-notification-budget-attention-economy)).

## Confirmation / close-the-loop pattern — confirm by tier, not by reflex

- **Silent acts → in-app receipt only, no push.** Surface the *real artifact* (the actual calendar entry, the actual draft) — read-back is the proof, not the prose (CLAUDE.md non-negotiable; `OWNER_ACTION_ENGINE.md:36`).
- **Deadlined promises → one tight line at the moment it matters.** "Done — I'll call you at 2:45." Sets expectation, closes loop.
- **Cross-person / money → a careful, human-toned ask,** never an auto-fired form letter.

The premium feel = *under*-confirm the routine, confirm the consequential with care. The opposite of a robot pinging "Done!" after every micro-action.

## Voice/copy spec

Assistant register, always. "Here's what I caught today," never "2 tasks ingested." Show the *why*: "I set a 2:45 reminder *because school moved pickup to 3*" — exposing reasoning is what prevents both over- and under-trust ([DoubleAgents](https://arxiv.org/pdf/2509.12626)). Forbidden visible text: jargon, JSON, status codes, model/vendor names, stack traces (`ANTICIPY_PRD.md:62`). Loading speaks human ("Listening to your week"), errors speak human ("I lost the thread for a moment").

## Onboarding that "scrapes you" without being creepy

The scrape (calendar + top contacts + recent threads) is fine *if* it's transparent and in service of you, immediately: show the inferred picture and let the user correct it in the first 60 seconds. The line between helpful and creepy is **surprise** — "trust collapses when systems act in ways users do not anticipate" ([Tsaaro](https://tsaaro.com/blogs/ai-ears-everywhere-privacy-risks-in-always-listening-voice-technologies/)). So: visible listening indicator, one-tap pause that visibly *is* off, short retention/auto-delete by default, and one user-facing, user-deletable ledger that is *both* the proof-of-action log and the privacy log. Anti-spam and anti-creep are the same system run on outputs vs. inputs. Bee inverted this ("red = muted," default-on invisible recording) and became the cautionary tale ([TechCrunch](https://techcrunch.com/2025/07/22/amazon-acquires-bee-the-ai-wearable-that-records-everything-you-say/)).

## The premium surface (off localhost)

The "dev server" smell is a *confidence* problem, not a deploy problem. The fix is restraint: one focused moment per screen with generous margins; one typeface + real type scale; human sentences instead of raw state; physics-based motion; the marketing site's exact palette inherited, not re-invented. Get off `localhost:3000` onto a real domain with the pendant page's visual DNA — but the URL is the last 5%; the 95% is killing the density, the monospace, and the verb-from-the-codebase copy ("Ingest," "Resolve," "Press Go").

## Trust guardrails (the structural ones)

- **Vent = cardinal sin (must be ZERO).** The vent-guard may only *downgrade* (ACT→ASK→SILENT), never enable an action (`CONSTITUTION.md:32`).
- **Money = the only hard stop.** Never auto-executed; always bounced to Omar (`CONSTITUTION.md:35`).
- **Browser arm = hostile territory.** It runs inside Omar's real logged-in Chrome — it sits squarely on the "lethal trifecta" (real credentials + untrusted web tokens + email/SMS exfil), and prompt injection is structurally unsolved and *rising 32%* ([Wiz](https://www.wiz.io/blog/agentic-browser-security-2025-year-end-review)). Mandate: untrusted page text can never escalate to an action; never let a webpage's content become a command. The money-stop + harm-line + owner-gated confirm must hold even when the page is adversarial.
- **Failure degrades to silence, never retry-and-ping** ([Case](https://www.caseorganic.com/post/principles-of-calm-technology)). The 6-SMS cold-boot event was a failure that failed *loud* — the cardinal anti-pattern.

---

# PART 3 — THE PATH TO TAKE US THERE

## Brutally honest: where we are vs. done

**What works:** the engine catches real tasks on *clean* input and errs safe — one-way-toward-SILENT, InterruptGuard cap, harm-line veto, money hard-stop, read-back receipts, ~0.875 memory recall (`HANDOUT` A/C). The safety floor is real and gated (mega-eval found 10 breaches *after* a "converged" claim — never trust convergence without running it).

**The rough edges between here and done:**
1. **It's a dev console, not a product.** "REAL, mock-mode… Owner login + paste/upload transcript + task cards" (`HANDOUT:97-100`) — functionally localhost. Fails the premium bar on sight.
2. **No real front door / onboarding.** There is no "scrape-you" first-60-seconds; the identity moat the whole product depends on isn't surfaced to the user.
3. **Over-asking / annoyance.** "It won't catastrophically act on a vent, but it's noisy" (`STATUS.md:104`). The 3–5/day budget, displacement, breakpoint timing, and the single digest lane are *not yet* first-class.
4. **Ambient-mic reality.** The engine works on typed/clean transcript; real-world mic noise, overlapping speakers, and partial utterances are unproven — the catch-rate on messy ambient audio is the unvalidated frontier.
5. **Catch-rate misses on indirect tasks** — the buried-three-clauses-deep obligation aimed at someone else is exactly the hardest and most valuable case.
6. **The brain is starved** (free-tier 429s, 60s+/call) — per the memory index, the real blocker is funding the model, the one thing only Omar can do.

## Ordered roadmap — highest leverage first

**1. The premium shell + onboarding front door** *(real-build; partly a demo move)*. Reskin the app to the PRD design language (one moment/screen, the palette, human copy, physics motion) and build the 60-second scrape-you onboarding. **Unlocks:** the product stops reading as a science project; the investor demo has a front door; the identity moat becomes *visible*. Highest leverage because it converts existing real capability into felt product with no new engine risk. *Demo-tonight slice:* the onboarding recap screen + one choreographed thinking-reveal over a canned transcript.

**2. Cadence as first-class state** *(real-build)*. Make the 3/day budget (ceiling 5) visible decider state with displacement, add breakpoint-timed release, and ship the single daily digest lane + dismiss-rate metric. **Unlocks:** "interrupts rarely," kills the noise defect (`STATUS.md:104`), and the calm-report feel of Part 1's 6:30pm moment.

**3. The closed-loop receipt + the 2:45 call, end-to-end on a real day** *(real-build)*. The deadlined-promise tier: one tight confirmation at capture, the real voice call at the deadline, the in-app artifact read-back. **Unlocks:** the canonical scene becomes literally true — the non-negotiable core of the Owner Test.

**4. Ambient-mic + indirect-catch hardening** *(real-build, the deepest)*. Validate catch-rate on noisy overlapping real audio and on indirect/memory-dependent tasks. **Unlocks:** the 9:14am "catch you didn't expect" moment survives a real day, not a clean transcript. This is the true gate to the 5-day Owner Test.

**5. Browser-arm injection defense before P4 broadens** *(real-build, safety)*. Untrusted-page-text-can-never-command, enforced. **Unlocks:** safe expansion of the acting surface without sitting naked on the lethal trifecta.

**Cross-cutting unblock (only Omar can do):** fund the model. A starved brain caps every other slice.

## The single highest-leverage thing to do next

**Build the 60-second scrape-you onboarding + premium shell over the engine that already works.** It is the one move that simultaneously (a) kills the "localhost dev server" disqualifier, (b) surfaces the identity moat that is Anticipy's actual differentiator versus the whole recorder graveyard, and (c) gives the imminent investor demo a real front door — all by *converting existing real capability into felt product*, not by taking on new engine risk. Everything downstream (cadence, the 2:45 loop, ambient hardening) is felt *through* that shell; without it, even a perfect engine demos as a science project.