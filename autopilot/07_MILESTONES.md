# 07 MILESTONES — the ordered backlog

Each milestone's "done" is a real-world check by the judge (`05_JUDGE.md`), never a green unit test. Do them roughly in order. Always: one vertical slice per lap, the whole system on a real day every lap, never shrink the goal, money is the only stop.

The current state is in `CODEX_BRIEF.md`. Short version: the decision spine, memory, and a stranded multi-step browser agent are real; the product around them (front door, input, onboarding, the mesh beyond two apps, the proactive scheduler, distribution) is mostly absent. You are building that perimeter and wiring the real engine into a usable product.

## M0 — the ugly floor (do this first)
Make the whole house limp through ONE real day, end to end, on this Mac: ingest a day (a transcript is fine to start), infer one real need, do it through one real app, and have the judge open that app and confirm the real artifact.
Done when: the judge verifies one real task really happened, from one real day, through the live system. Record the ugly first score. This is the floor you climb from.

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
Make MP3, transcript, and live Bluetooth ingestion all work (the three buttons). The system transcribes MP3 days itself; the human does not sort them.
Done when: a real MP3 of a whole day flows end to end and the judge verifies the real tasks it produced.

## M8 — the full body (deferred, listed for completeness)
The iPhone app, the pendant firmware, and a one-click way to flash the pendant and pair it to a Mac. Sequence this after the software prototype is real. Flashing the physical pendant is a human gate.

Whenever a milestone's done-criterion is met and the judge confirms it on a fresh day, advance. If you find a faster real path than this order, take it, but never skip the judge and never lower a done-criterion to a green test.
