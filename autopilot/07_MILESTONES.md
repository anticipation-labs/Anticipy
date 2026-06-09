# 07 MILESTONES — the ordered backlog

Each milestone's "done" is a real-world check by the judge (`05_JUDGE.md`), never a green unit test. A milestone is done only when the reality judge confirms it on the required real surface. For broad reality milestones, require at least 5 different held-out real days spanning different situations, not 5 variations of one. Score by the worst case, never the average. One pass means nothing.

Do them roughly in order unless a later amendment narrows focus. Always: one vertical slice per lap, the whole system on a real day every lap, never shrink the goal, money is the only stop. Until real diverse users exist, label generalization as UNPROVEN in every scorecard and never claim the product works for everyone.

## Current focus amendment: M3 only
Stop widening the perimeter. The only milestone the builder may work now is M3: the browser hand actually completing a real task end to end. No more UI/status/observability/onboarding-polish laps. The product is: hear a task, do it, prove it happened.

M3 work must wire the real WebVoyager/browser agent into the live task loop so a typed task such as `add the cheapest stainless water bottle on <real site> to the cart` actually drives the browser and changes the cart. This means the real planner, real browser hand, and real artifact path, not a self-test, not a mocked flow, and not another status surface.

Mocked browser checks never count as M3 progress. They may only prove generic wiring did not regress. M3 advances only when a real artifact appears in the real world and the separate judge verifies it. Until the judge is available, the builder may build the real action path, but every scorecard and state update must label it UNPROVEN.

If the real action path needs the separate judge to confirm it and the judge is quota-blocked, the builder is BLOCKED on M3 for proof. Write that plainly in `PENDING_FOR_OMAR.md` and stop inventing easy side-work.

Hard target rule: `example.com`, localhost, fixture pages, and contrived no-stakes pages are banned as M3 task targets and banned as M3 evidence. They are diagnostics only, never progress.

The browser hand must not complete M3 by typing the task text into a search bar or address bar. A run that turns the user's instruction into search text is a failed run. The agent must plan and act on a real site or real account.

The real M3 shape is:
1. The task is vague natural language that does not name the site or exact item, for example `grab that thing I was looking at earlier for the kitchen`.
2. The system uses memory to resolve what the phrase means, choose the real site, and identify the real item.
3. The browser hand acts on that real site and creates a real reversible artifact, such as the item actually being in the real cart.
4. Proof exists only when the separate judge opens the real site/account and sees the real change. No mocks, no example pages, no localhost pages, and no screenshot-only proof.

If the full chain is not working yet, build the missing piece and label every run `UNPROVEN-PENDING-JUDGE`. Judge quota being blocked does not justify easy side-work. If building the chain itself is blocked, record the exact blocker in `PENDING_FOR_OMAR.md`.

The current state is in `CODEX_BRIEF.md`. Short version: the decision spine, memory, and a stranded multi-step browser agent are real; the product around them (front door, input, onboarding, the mesh beyond two apps, the proactive scheduler, distribution) is mostly absent. You are building that perimeter and wiring the real engine into a usable product.

"Done" is defined by a stranger, not the owner: a person who is not the human, on a clean machine, downloads at `anticipy.ai/app`, onboards, connects their apps, and gets a real task done. Until that is true, the product is not done no matter how good audio inference is.

The owner audio tests only the ears-to-brain slice. It is not the priority over the front door, real input box, wired browser hands, and self-onboarding. You may not spend more than 3 consecutive laps on inference or brain without advancing a perimeter milestone: M1, M2, M3, or M5. Every few laps, verify the whole house still runs end to end for the stranger path, not just the owner's audio. Raw audio inference is the last hard layer and a final exam, not the daily gate.

Breadth attack: you may generate synthetic diverse days for personas unlike the human (founder, parent, lawyer, doctor) only to try to break generalization. Hard asymmetry: a synthetic day can only lower confidence by exposing a failure. It can never raise confidence and never count as a pass. A break is a real finding that halts progress. Real confidence comes only from real diverse users, which do not exist yet.

## M0 — the clean floor (do this first)
Make the whole house complete ONE real task from a typed, fully time-grounded instruction on this Mac. Example shape: `create calendar event "[Anticipy test] Dentist" 2026-06-12 15:00-16:00`. The instruction must be unambiguous, safe, reversible, and sent through the live system, not a direct connector call.
Done when: the judge verifies one real, correct artifact in the real app from a typed clean instruction, with connector read-back where one exists, screenshot proof, and cleanup of test artifacts after verification. A guard that abstains or prevents a fake does not advance M0. M0 requires positive capability: real task, done correctly, proven in the real app.

## M1 — a real front door
Build, sign, and publish a real Mac app download at the project's Cloudflare R2 link, replacing the static placeholder.
Done when: from a clean profile, the link downloads a `.app` that launches and shows the live surface. Judge confirms by downloading and opening it.

## M2 — real input in the app
Make the app's typed task box a real input and the record control real (today the box is static text and record is inert per the brief).
Done when: a user types a task in the app and it runs through the engine; judge confirms the resulting real action.

## M3 — wire the real hands
Connect the existing multi-step browser agent (it exists but is stranded behind a side endpoint) into the actual task loop, so the hands can click, type, and fill on real sites, not just navigate and read.
Done when: a task with no API back door completes on a real site and the judge verifies the real artifact (item really in cart, form really submitted).

## M4 — turn anticipation on
Schedule the proactive time trigger so the system acts later when an open loop comes due (today the trigger never runs in production per the brief).
Done when: a due open loop fires on a fresh day and acts, judge verifies the real result, and no vented item was acted on.

## M5 — self-onboarding and the per-person mesh
Build onboarding on the user's real machine: read inboxes, call them with custom questions over the Twilio line, and build their personal mesh. For each service: API or connector if one exists; else take over the signed-in browser to get in or grab a token; else reset and store a password. Money is the only stop.
Done when: on a fresh account, onboarding ends with a working personal mesh and a real first profile; judge verifies the live connections by opening the apps.

## M6 — grow the mesh
Extend beyond the two working connectors (Calendar and Gmail-send today) using the general get-access routine: drafts, and the other services a real person's life runs on.
Done when: for each newly connected app, the judge verifies a real task completed through it.

## M7 — the three inputs live
Make MP3, transcript, and live Bluetooth ingestion all work (the three buttons). The system transcribes each MP3 once into a sidecar transcript and then uses cached text in the inner loop; the human does not sort them.
Done when: a real MP3 of a whole day flows end to end from cached transcript text, the harness passes wall-clock and transcript timing into the engine, and the judge verifies the real tasks it produced. This is a final exam after the typed-input perimeter works, not the daily development gate.

## M8 — the full body (deferred, listed for completeness)
The iPhone app, the pendant firmware, and a one-click way to flash the pendant and pair it to a Mac. Sequence this after the software prototype is real. Flashing the physical pendant is a human gate.

Whenever a milestone's done-criterion is met and the judge confirms it on a fresh day, advance. If you find a faster real path than this order, take it, but never skip the judge and never lower a done-criterion to a green test.
