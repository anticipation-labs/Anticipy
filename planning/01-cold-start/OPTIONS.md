# Cold-start: knowing everything about a new user in seconds

Owner thread: 01-cold-start. Drafted 2026-05-29. Working doc.

The premise. A new wearer just installed `Anticipy.app`, finished `/onboarding`, and paired the engine. Until it knows their people, software, templates, voice, and mandate, the agent is a generic assistant that can answer trivia but cannot draft a demand letter, route a lab order, or update a Procore schedule. Bar: "useful within 5 minutes of install, great within a week."

The warm-start floor exists. `engine/app/anticipy/onboarding.py` runs the seven-question interview and produces a `UserProfile` (`engine/app/anticipy/seams.py`) via one LLM extraction. `engine/app/coldstart/ramp.py` holds the autonomy threshold conservative on day 0 and earns it down as trajectory confidence accrues. `engine/app/product/dossier_active_loader.py` ships the profile into inference. `engine/app/product/scoped_memory.py` writes under `~/.anticipy/v7/dossiers/<account_id>/`. The seven strategies below fill the same shape from richer sources, no service APIs.

## A. Browser-tab inhale of already-logged-in surfaces

The wearer's Chrome on day 0 is the richest source we have. `extension_v4/manifest.json` already holds `<all_urls>` and talks to `engine/app/bridge_extension.py`; the CDP path against the LaunchAgent clone is `engine/app/action_engine/cdp_dispatcher.py`. We add a read-only "inhale" mode that, on one consent click, walks `Target.getTargets` and attaches `Page.enable + Runtime.evaluate` per surface family.

Per-surface mechanics. Gmail: scroll the inbox virtualized list, capture `[role=row]` items, open Settings > Accounts via URL hash for the signature block, send-as identities, vacation responder. Calendar: `?view=agenda`, scroll next 30 days, extract titles, attendees from `data-tooltip`, recurrence. Drive: walk Recent and Shared, for "template" or `[Client]` titled items inhale headings only, never bodies. LinkedIn `/in/me`: role, employer, tenure. Slack: walk the left nav DOM for workspaces, channels, top DMs. Salesforce, HubSpot, Procore, MyChart, Canvas: per-surface recipe in `engine/app/product/action_recipes.py`, almost always anchored on the "Recents" widget.

Inhales: identity (the signature block is the single most reliable role+title+employer signal), people graph (calendar + Gmail frequency), tool inventory, templates (Drive headings), authority hints (meeting cadence). Cannot inhale: native apps (Outlook desktop, Epic Hyperdrive, Acrobat), unopened tabs, anything behind unstarted MFA. Time to value: 90 seconds when Gmail + Calendar are open. Privacy: all local, encrypted at rest with the existing profile Fernet key; only outbound call is the `_extract` mapping, which sees de-PII'd summaries (names yes, bodies never). Failure modes: Chrome closed (prompt to open), Safari/Arc (Arc is Chromium, same recipes; Safari needs an AppleScript + AX adapter), and the killer, MDM-locked Chrome that refuses unsigned extensions and blocks CDP.

## B. Twilio voice interview, 90 seconds

Twilio is wired (`engine/app/anticipy/comms.py`, `engine/app/crm_log.py`). On install completion the engine places an outbound call to the number the wearer just entered. Streaming TTS runs `INTERVIEW_SCRIPT` from `engine/app/anticipy/onboarding.py` verbatim; ASR is the same parakeet-mlx the pendant uses; the existing `_extract` maps transcript to `UserProfile`.

Inhales: explicit anchors for "the boss" and "us," mandate, do-not-touch, comms prefs, quiet hours, time zone. Cannot inhale: templates the wearer forgot they wrote, contacts they never named to an assistant, quantitative facts. Time to value: 90 seconds. Privacy: audio transcribed locally where possible, transcript discarded after extraction. Failure modes: hang-up at Q2 (keep what we got, mark rest ASK-needed, let A backfill), phone on DND (fall back to in-app text intake using the same script).

## C. Filesystem scan for templates and conventions

Years of context live in `~/Documents`, iCloud Drive locals, project folders. With Documents-folder TCC already requested, a `coldstart/fs_scan.py` (to add) leans on `mdfind` (Spotlight is pre-indexed, sub-second), extracts headings via `textract` for `.docx` and `pdftotext` for PDF, writes `(path, kind, headings, first_lines, mtime)` tuples to `~/.anticipy/v7/dossiers/<account_id>/templates.jsonl`. One LLM pass clusters reusable templates from one-offs; bodies stay on disk and load lazily when a relevant action fires.

Inhales: templates (the moat for lawyer / sales / PM verticals), naming conventions (`[Client] Subject - YYYY-MM-DD.docx`), project ontology (folder hierarchy IS structure), writing voice (sampled from prior outbound `.eml`). Cannot inhale: cloud-only apps with no local mirror, sandboxed app containers, iCloud "Optimize Storage" stubs. Time to value: 60-300 seconds scan + 30 clustering. Failure modes: encrypted disk images, stub-only iCloud, a brand-new Mac with nothing on it.

## D. Calendar-graph relationship inference

A specialization of A that earns its own line because the next 60 days of calendar is a near-complete relationship map. A small graph pass over attendee lists fills `UserProfile.people` with ranked relations: `boss` (recurring 1:1 where wearer is second attendee), `reports` (inverse), `clients` (external-domain + project keywords), `partner` (non-work-hours events with words like "dinner," "weekend," anniversary dates). Cannot infer: the freelancer emailed weekly but never met, authority order inside client teams, anything personal kept off the work calendar. Time to value: 5 seconds once A is running. Failure modes: Outlook / iCloud Calendar without parallel recipes, exec-style "Hold" blocks with no attendees.

## E. Role-template library matched on one question

First question regardless of channel: "what do you do?" An LLM single-shot maps the free-text answer to one of N pre-built templates in `/Users/omarebrahim/Developer/Anticipy-V7/roles/` (the directory exists with `worker.md`, `planner.md`, `judge.md`): `Lawyer-Litigation`, `Lawyer-Transactional`, `Doctor-Primary-Care`, `Sales-AE-B2B`, `Construction-PM`, `Founder-Hardware`, `Student-Undergrad`, etc. Each carries a canonical software list, common templates, baseline do-not-touch rules (a doctor's template hard-codes "never modify a signed chart note"), typical mandate, quiet hours.

Inhales nothing real, everything prior. Time to value: 3 seconds. The point is to give every other strategy something to subtract from rather than build up. Provenance must be `role_template_prior` in `engine/app/product/memory_provenance.py` so any inhaled or wearer-confirmed entry overwrites cleanly. Failure modes: no template matches (we ship a `Knowledge-worker` generic), priors are wrong (later strategies correct as they confirm or refute).

## F. Federated import from CSV/JSON dumps

For the power-user who has exports ready: Google Takeout (Contacts + Calendar + Drive index), Notion workspace export, Apple Contacts `.vcf`, 1Password filtered to non-credential fields. The Tkinter file picker in `engine/app/desktop_app.py` handles drag-and-drop; ingest reuses the same `_extract` pipeline. Inhales deep history (3-year-old calendar, names long inactive but still load-bearing) in one shot. Time to value: 30-120 seconds. Failure modes: nobody on day 0 has these exports lying around. The 5% strategy.

## G. Passive listening for the first 72 hours

The pendant (today the Mac mic) captures ambient audio from minute one. `engine/app/proactive/` runs VAD + diarization + ASR + intent extraction + memory writes; in cold-start `engine/app/coldstart/ramp.py` holds ACT at COLD_START for 72 hours but lets LATENT writes happen at full speed. Names dropped in passing, project aliases, verbal tics, the wearer's spouse on a call, all land in `engine/app/anticipy/memory.py`'s ADD/UPDATE/DELETE/NOOP reconciliation.

Inhales the things you only learn by listening. Cannot inhale: pre-install, pendant-off periods, environments diarization cannot parse. Time to value: low hour 1, dominant by hour 72. Privacy: the strategy that lives or dies on the local-first promise. Transcripts never leave `~/.anticipy/`. Failure modes: wearer skips the pendant at home, back-to-back Zooms where the wearer rarely speaks, or wearer turns the pendant off because it's annoying (the real failure mode, owned by thread `04-quietness-ux`).

## Combination: the sequence of moves

T+0 to T+90 seconds. Vercel onboarding hands off to the local engine via the model broker handshake. Strategy E fires on whatever the wearer typed in the "what do you do" field; the `UserProfile` is populated with priors in 3 seconds and written to disk. In parallel, strategy A walks open Chrome tabs. By T+90 the Gmail signature, calendar agenda, and LinkedIn profile have collapsed the priors into something specific. The autonomy ramp stays at COLD_START.

T+90 seconds to T+5 minutes. Strategy B places the outbound Twilio call. Strategy C runs the filesystem scan in the background. The call lands the explicit anchors A could only guess at ("the boss," "us," mandate, do-not-touch). At T+5 the dossier is dense enough to resolve "draft a follow-up to Sarah about the Cooper deal" by mapping Sarah to a calendar attendee, recognizing Cooper as Project Atlas, picking the right template from C. First ACT is gated to draft-only by the COLD_START threshold.

T+5 minutes to T+1 hour. Strategy A continues opportunistically as the wearer visits new surfaces. Strategy G accumulates latent context. The first 1-3 wearer-confirmed actions feed `earn_trust` in `coldstart/ramp.py`, which starts lowering the ACT threshold along the frozen autonomy ramp. Corrections persist via the memory reconciliation primitive in `engine/app/anticipy/memory.py`.

T+1 hour to T+1 week. Strategy G dominates. Each ambient conversation refines `UserProfile.people`, adds aliases, surfaces missed templates. The ramp progresses COLD_START to ONBOARDED. By end of week the agent acts silently on low-risk, asks on medium, refuses or escalates on ultra-high. The `ASK_CAP_PER_DAY = 4` cap in `coldstart/ramp.py` prevents flooding.

Stack vs conflict. A and G both want CDP access; A wins on day 0 (short-lived), G owns steady state. B and C run parallel (no shared resources). E's priors must always carry lower provenance than anything observed, or they cement wrong defaults.

## The 5-minute MVP cold start

Stripped to the bone: strategy E (role template) plus strategy A's Gmail signature inhale plus strategy A's calendar inhale of the next 7 days, nothing else. That gives us name, employer, role (from signature), the week's meetings (from calendar attendees), and a generic role template. With that, on day 0 inside 5 minutes, the agent can do exactly one real thing: take "remind me to prep for the Sarah meeting tomorrow," resolve Sarah against the attendee list with confidence > 0.7, and write a calendar event or draft a prep doc to the wearer's desktop. The day 0 single thing must NOT be a send action. The COLD_START ramp keeps it at draft / propose / confirm. The wearer gets to see Anticipy do something useful and right, not autonomous and wrong, on their first day.

## Open problems

1. MDM-locked Chrome blocks both the extension and CDP. Vision + AppleScript fallback is 1000x slower and breaks on every Salesforce UI tick. No good answer.
2. Native EHRs (Epic Hyperdrive, Clio, Smokeball) are not browsers and not standard Mac apps. Inhale misses them entirely; G picks up verbal mentions but not structured data. Per-vertical AX recipes are possible but the AX APIs on these apps are nightmarishly inconsistent.
3. First-action regret. If day 0 action one is wrong, trust drops sharply and rarely recovers. Gating to draft-only is right but does not quite reach "delight." How do we make action one trivially correct?
4. Voice-anchor binding. Strategy G's diarization produces speaker IDs, not names. Cold-start has no clean way to bind speaker-3 to "Dana, the founder" without a labelling step the wearer will not do.
5. Cross-device dossier. Work laptop plus personal Mac under one `account_id`: do they merge, diverge, or pick a winner? `scoped_memory.py` suggests merge, but device-local templates and filesystem context cannot sync without a sync layer that risks the "no centralized transcripts" rule.
6. Privacy reset. A wearer leaves a job. The dossier has old-employer people, templates, software baked in. We need a "fresh start" purge of work context that keeps personal context. We do not have a clean ontology for which is which.
