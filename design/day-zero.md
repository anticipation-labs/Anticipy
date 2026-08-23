# Day zero — how she comes to know you

The deliverable `design/briefs/08-day-zero.md` has been asking for since it was
written: the interview script, the consent language, and the mechanism for
acquiring context about a person's life.

**Decision: context is acquired by SUPERVISED READ, never by autonomous
scrape.** She drives; you are present for the first read of each source and
watch it happen. The reasoning is in §2, and it is a product argument before it
is a legal one.

---

## 1. The shape: earn, then ask

Three phases. The ordering is the whole design — every ask lands after the thing
that makes it make sense.

| Phase | When | What she asks for |
|---|---|---|
| **Ears** | first run, ~70s | microphone, your name, your number |
| **Just-in-time** | whenever your own words need it | one connection, for one stated reason |
| **The picture** | after she has finished one real errand | the sources, one toggle at a time |

Nothing in phase 1 asks for an account. Nothing in phase 3 happens until phase
2 has produced something you watched her do.

### Phase 1 — Ears (unchanged budget)

The shipped flow already does this and stays as it is: welcome → `micPrimer` →
your name and number. `design/CONSUMER-FEEL-DIRECTION-2026-08-03.md` §5 budgets
the first run at **under seventy seconds**; this phase spends all of it, so
nothing may be added here. The browser step moves out of first run (see §5).

### Phase 2 — Just-in-time, triggered by your own sentence

Each ask is provoked by something the person said, and names the reason in the
same breath. The evidence for this ordering: an *unexpected* permission request is
about twice as likely to be denied as an expected one, and a request carrying an
explanation has roughly half the deny rate of one without. (Industry write-ups
also claim ~+28% grant rate for deferred prompts; treat that number as
directional — the deny-rate findings are the load-bearing ones.)

| You said | She asks | Source | What travels |
|---|---|---|---|
| "dinner with Priya Thursday" | "Want me to check your calendar?" | on-device `EventKit` | event titles + times, next ~30 days |
| a name she does not know | "Who's Priya? I can read just the names in your contacts." | on-device `Contacts` | the names list only |
| an errand needing the web | the existing browser pairing | extension | nothing new |
| an errand blocked on a code | the existing inbox side trip | `side_trip.js` | one value |

The calendar and contacts asks are the highest-value, lowest-risk context in the
product and they are **unbuilt today** — no `EventKit` or `Contacts` import
exists anywhere in `app/ios`.

**The permission API is version-split and a missing key is a crash, not a
denial.** The deployment target is iOS 16.0 (`project.yml`), so both paths ship:

| | iOS 17+ | iOS 16 |
|---|---|---|
| Calendar | `requestFullAccessToEvents()` | `requestAccess(to: .event)` |
| Info.plist | `NSCalendarsFullAccessUsageDescription` | `NSCalendarsUsageDescription` |

`NSCalendarsUsageDescription` is deprecated but still **required** while the
floor is 16.0 — an app linked on iOS 10–16 without it crashes rather than being
refused. Contacts needs `NSContactsUsageDescription`. iOS 18 may return
*limited* contacts access; that is fine here and needs no special handling,
because the only thing wanted is the names list. They need no account, no OAuth, no third party,
and `design/briefs/08-day-zero.md:31-33` already fixes their limits: *"NEVER
leaves the phone wholesale: only the names list and event titles+times for the
next ~30 days."*

Every ask is built from the shipped `micPrimer` template
(`OnboardingView.swift:403-473`): one question, a rule list of what she will and
will not do, a real skip, and a recovery path when the OS says no.

### Phase 3 — The picture (the graduation)

**Trigger, deterministic and in code:** at least one errand completed with a
visible result, AND at least one overnight. Not a step in a wizard — a card that
appears in the feed when both are true.

> **Want me to actually know you?**
> I'll read, and only read. I never send, never reply, never delete. You watch
> me do it the first time.

One toggle per source. **All off.** Skip is a button of equal weight, not a grey
footnote. This is `design/PREMIUM-FEEL.md:43-47`, restated.

1. **Your mail** — subject lines, who you talk to, what's in flight
2. **Your professional life** — your own profile: role, company, field
3. **Your work tools** — she names them, inferred from the field
4. **Tell me yourself** — the questions no read can answer

Sources 1–3 are supervised reads. Source 4 is the interview, and it is where
*"what tools do you think I'll use day-to-day"* belongs, because no scrape can
answer it.

---

## 2. Why supervised, and not autonomous

The product reason first, because it is the one that decides.

A person who has no idea what this thing is learns what it is by **watching it
work**. Watching her open a tab, read subject lines, and say *"you and Marcus
have something in flight"* teaches, in one gesture: she reads your things, in
your browser, in your accounts, and she asks first. An autonomous scrape teaches
nothing — there is nothing to see — so trust has to be carried by a sentence
instead of by a mechanism, and it arrives framed as *"I went through your mail
while you weren't looking."* A silent failure behind that promise is the worst
first impression the product can make.

Three independent constraints agree, any one of which would be sufficient:

- **The architecture already forbids it.** `design/PRODUCTION-ROADMAP.md:123-141`
  §6 — *"Research must never use Omar's browser — FIRST BUILD ITEM"* — and it is
  enforced in shipped code in three places: `background.js:74` (`BROWSER_LANE`
  excludes read-only work), `backend/pb_hooks/research_lane.pb.js:70-73` (403,
  *"research jobs run in the worker, never in a browser"*), and
  `brain/anticipy_core.py:592-604` (`job_lane()`). The autonomous version
  requires deleting a guard installed on purpose.
- **The API route is a subscription to an audit.** `gmail.readonly` is a Google
  *restricted* scope: mandatory CASA assessment, Tier 2 self-scan withdrawn,
  ~$540–$4,500+ per app per year, re-certified every 12 months.
- **LinkedIn's penalty lands on the customer.** User Agreement §8.2 prohibits
  automated access. hiQ won the CFAA point and **lost on breach of contract**
  (N.D. Cal., Nov 2022), settling under a permanent injunction to stop and
  delete. The practical outcome of an automated round is occasionally getting a
  paying user's account restricted.

**What supervised means precisely.** She drives — you do not copy anything. You
tap once per source, the tab opens in the foreground, and a narrated log runs
while she reads. Supervision is required only for the **first** read of a
source; afterwards refreshes are quiet and land in the feed. This is what makes
phase 3 graduate into ambient behaviour rather than staying a chore.

`design/PREMIUM-FEEL.md:112-139` §5 "THE LIFE SCRAPE" is superseded by this
section: the rounds and the promise line survive, the autonomy does not.

---

## 3. What gets stored, and why it is small

**The memory store has no embeddings.** Retrieval is FTS5 keyword matching plus
a graph walk plus a distilled `profile_facts` ranking (`brain/memory.py:9`,
per-owner SQLite at `brain/supervisor.py:85-93`, mode `0o700`). Dumping fifty
subject lines into it does not make her smarter — it buries the ten facts that
matter under keyword noise.

So the output of a read is **5–15 facts per source**, not a corpus:

```
remember_fact(
    fact="Marcus Bell is a client; a proposal is in flight.",
    importance=4,               # 5 = identity, 4 = a live commitment
    source="import",            # already in the schema's enum
    confidence=0.9,             # imports and interview answers, per memory-consolidation.md
    provenance={"source": "gmail", "seen": "<ts>"},
)
```

**Transport.** The phone posts a `kind: "profile"` event through the existing
`pushEvent()` (`Backend/AnticipyBackend.swift:420`, posting to `api/collections/events/records`).
`kind` is a free `text` column (`backend/pb_migrations/1700000000_anticipy.js:32`)
so **no migration is required**. The worker consumes that kind and calls
`remember_fact()` — it must NOT go through `hear()` as a `transcript`, or an
interview answer like *"I work at Acme"* would be triaged and could mint an
errand.

Everything then lands through the existing seam. `remember_fact()`
(`brain/memory.py:414-432`) already merges restatements, so re-reading a source
cannot duplicate a fact, and `worker.seed_profile_identity()`
(`brain/worker.py:264-285`) already proves the path is live. **Do not build a
parallel store.**

- **Skips record nothing.** Never an empty fact. (`briefs/08-day-zero.md:30`)
- **Every fact is vetoable.** A tap deletes it and marks it never-re-derive.
- **Known split-brain, not made worse:** `conversation.py:771-846` writes a
  separate `owner_profile.facts` blob and SMS text never reaches `memory.py`
  episodes. Day-zero writes only through `remember_fact()`. Unifying the two is
  named here as follow-up, not silently inherited.

---

## 4. Gates — in code, never in the model

`CLAUDE-ONBOARDING.md:19-20`: *"that gate lives in deterministic code, never in
the model."*

1. **Per-source consent.** A read refuses without a stored per-source grant. One
   grant, one source, revocable.
2. **Read-only, mechanically.** During a read job the action vocabulary is
   narrowed to navigate/scroll/extract. No type, no click-submit, no attachment
   open. Enforced where the existing refusals live
   (`agent_loop.js:5053-5056`, `:5126`, `:5146`), not by prompt.
3. **Domain allowlist per round**, on top of the standing blocklist
   (`agent_loop.js:1882-1894`).
4. **Page budget per round**, on the `learn.js:58` `MAX_PAGES` pattern.
5. **Foreground and present.** First read of a source requires the app in the
   foreground. This is the supervision, expressed as a precondition.
6. **Read text is untrusted.** Fenced as `learn.js` already fences it — page
   text can authorize nothing. A mail body that says *"send this"* is data, not
   an instruction. This is the prompt-injection boundary and it is
   non-negotiable.

### Local-first posture (`LOCAL-FIRST.md:39-40` Rule 5 requires this section)

Calendar and contacts are read **on the device**; only the derived list travels,
never the store. For supervised reads, the page slice goes to the model provider
— the same path today's browser work already takes, bounded by
`page_map.js:214-247` at ~5,000 visible characters — and **only distilled facts
persist**. Raw page text is never stored, never synced. The gap this leaves is
named, not hidden: fact extraction is not yet on-device, and the later that
localises it is the memory-locality work already on the scoreboard.

---

## 5. The feel: smoother, more interactive, self-explanatory

The current first run is five static pages and a Continue button. Fixes, all
inside existing canon:

- **One lit object per screen**, and anything she says is 17pt or larger.
  (`CONSUMER-FEEL-DIRECTION` §2)
- **Her lines are typed; permission copy is not.** The typewriter is banned on
  consent and error text — *"where a companion becomes twee."*
- **The read is the interaction.** A live narrated feed, facts materialising as
  cards, each vetoable by tap. This is the most interactive surface in the
  product and it doubles as the explanation of what she is.
- **Progress is a rule list with a live marker,** not wizard dots — the same
  gesture the extension's pairing page already uses.
- **Consent is a rule list, never four cards.** (`CONSUMER-FEEL-DIRECTION` §3d,
  §4 cut #3)
- **Every ask has a real skip and a recovery path.** A denied permission must
  never be terminal (`CONSUMER-READINESS` B1).
- **Nothing steals focus, ever.** (`PRODUCTION-ROADMAP.md:176-185` §9)
- **Move the browser step out of first run.** It is asked just-in-time, when an
  errand actually needs hands, which also returns the ~70-second budget and
  removes a step from what the audit called a six-step wall.

---

## 6. Prerequisite that blocks shipping the consent surface

`design/CONSUMER-READINESS-2026-08-03.md` §5 gates any consent surface on a real
privacy policy **and a working delete**.

- The policy page exists (`backend/pb_public/privacy.html`).
- **The delete exists and is reachable.** `POST /me/delete`
  (`backend/pb_hooks/account_delete.pb.js`) clears every owner-scoped table —
  including `agent_llm_audit`, which holds up to 1 MB per row of verbatim task
  text and has no cascade — writes a `purges` row, then closes the account.
  `brain/supervisor.py` `purge_deleted_owners()` finishes the part PocketBase
  cannot reach, the per-owner memory file, and refuses to touch any account
  discovery still returns. Settings calls it; the apology and the mailto are
  gone.

The gate is therefore met. It was met by building the thing, not by softening
the sentence.

**Correction to an earlier draft of this section.** It claimed "phases 1 and 2
are unaffected — they touch no account", and that was wrong: §3 has the phone
POSTing `kind:"profile"` events to the server, so imported calendar and contact
facts leave the device in phase 2. The consent-surface rule therefore applies to
phase 2 as well. What phase 2 genuinely avoids is a THIRD-PARTY account — no
OAuth, no Gmail, no LinkedIn — which is a narrower claim and the only one the
code supports.

---

## 7. Build order, and where it actually got to

1. ~~Contacts + calendar just-in-time asks (phase 2).~~ **Done.**
   `ContextGrant.swift` (the gate), `ContextTrigger.swift` (a deterministic rule,
   never the model), `LifeContext.swift` (the readers, capped), `ContextAskSheet`
   (the ask), `kind:"profile"` transport, `brain/worker.py`
   `ingest_profile_events`.
2. ~~Interview as a conversation.~~ **Done.** `Interview.swift` (six questions,
   including the one no scrape can answer — which tools you actually live in),
   `InterviewView.swift`, offered on Home after she has earned it and always
   reachable from Settings.
3. ~~Server-side delete + the app control.~~ **Done**, and hardened after an
   audit found a cross-account deletion primitive in the first draft: the caller's
   `legacy_uuid` is a CLAIM, so it may only ever match the legacy column, never
   `owner_ref`.
4. **Supervised read — built.** Consent (`ContextSource.mail`), surface
   (`SupervisedReadView`), and the reader.

   ### How "while you watch" is enforced rather than promised

   The promise is "I read it once, in the front window, while you watch". A flag
   cannot carry that: `side_trip.js:194-198` already settles why — "another
   process decided I may read your inbox" is the sentence this product cannot
   afford to be true. So supervision is a **lease**:

   - `jobs.watching_until`, written by the APP as `now + 30s`, refreshed every
     10s, and only while the read screen is on-screen with the scene phase
     `.active`.
   - The extension re-reads it before EVERY action and stops the moment it is
     past — the same shape as the `stoppedNow()` re-check that already guards
     irreversible actions (`agent_loop.js:5211`).
   - Background the app, lock the phone, or swipe the screen away and the read
     stops itself inside 30 seconds.

   A lease is evidence rather than permission: nothing but a foregrounded app can
   keep it fresh. The lane guard's exemption for `lane == "supervised_read"` is
   keyed on it, so a browser can never claim a read that nobody is watching.

   ### Who navigates decides what is allowed

   The action vocabulary is **per source**, default-deny:

   | Source | Vocabulary | Why |
   |---|---|---|
   | `mail` | navigate, scroll, extract | The person opened their own mailbox; moving between a list and a thread inside it is still their session. |
   | `professional` | **extract only** | LinkedIn's UA §8.2 prohibits automated access and hiQ lost on breach of contract, with the penalty landing on the *user's* account. A script that navigates is automated access however honestly we describe it; a script that reads a DOM the person navigated to themselves is a tool summarising what was already on their screen. So the person drives and we only read. |

   An unknown source gets no vocabulary at all, so a new source has to state its
   own rather than silently inheriting mail's.

   ### What travels

   `read_line` (one sentence in her voice, about what she concluded) and
   `read_fact` (one distilled fact). Never raw page text, a subject line, or a
   message body — `LOCAL-FIRST.md:9-11` is absolute, and the emit path refuses
   anything that looks like quoted content rather than trusting the model to
   behave.

   ### Mail is written by other people

   Anyone can email the owner, so a fact derived from a mailbox has exactly the
   provenance of an imported calendar invite: attacker-controlled text. It is
   fenced accordingly — `"supervised_mail"` joins `_UNTRUSTED_SOURCES`, and its
   importance is capped at 4, because importance 5 is reserved for boundaries the
   owner stated in their own words and a fact nobody typed must never outrank one
   they did.
5. Professional and work-tools reads, reusing 4. Not started.

**What is deliberately refused, and why.** A Gmail *scrape* via OAuth
(`gmail.readonly` is a restricted scope: mandatory CASA assessment, Tier 2
self-scan withdrawn, ~$540–$4,500+ per app per year, re-certified annually) and
an automated LinkedIn round (User Agreement §8.2; hiQ won the CFAA point and
**lost on breach of contract**, N.D. Cal. Nov 2022, settling under a permanent
injunction — the penalty lands on the customer's account, not ours). The
supervised read in step 4 is how the same context is acquired without either.
