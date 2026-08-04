# Brief 08 — Day zero: the interview + imports (roadmap §8)

## Mission
On install she knows nothing. Two parts:
1. **The interview** (iOS onboarding finale): she asks five human questions
   — who matters to you; what do you do; what should I never touch; how do
   you like to be reached; what's coming up this month. Conversational,
   skippable per-question, in her voice (typed-out text style already used
   in onboarding). Answers are posted to the backend as seed events the
   worker writes into memory as high-importance profile facts.
2. **Imports with permission**: contacts + calendar, read-only, each behind
   its own OS permission ask and its own explicit in-app consent. Names she
   hears then resolve to people she can spell; "tomorrow at 7" checks a real
   calendar. Skipping must be first-class and shame-free.

## Context you must read first
- `app/ios/Anticipy/Views/OnboardingView.swift` — the page flow, animations,
  and voice; the finale page this extends.
- `app/ios/Anticipy/Backend/AnticipyBackend.swift` — how the app posts events.
- `brain/worker.py` — the transcript/event intake; where seed events get
  consumed.
- `brain/memory.py` — if brief 05's `remember_fact` seed API exists in your
  copy, use its shape; otherwise write facts as episodes tagged
  source="interview" the consolidation layer will pick up.
- `design/PRODUCTION-ROADMAP.md` §8, §1.

## Design constraints (non-negotiable)
- Consumer-grade premium: one lit thing per screen, 17pt+, her voice — no
  form-feel, no developer-feel. Interview is a conversation, not a survey.
- Everything skippable; skips recorded as nothing (never as empty facts).
- Contacts/calendar data NEVER leaves the phone wholesale: only the names
  list (contacts) and event titles+times for the next ~30 days (calendar),
  posted as seed events, with clear in-app language saying exactly that.
- iOS 16.0, builds clean via app/ios/build_on_mac.sh / xcodebuild.
- Worker-side: seed events become memory facts (importance 4–5,
  provenance "interview"/"import"), idempotently (re-posting must not dupe).

## Definition of done
- xcodebuild compiles with zero errors (paste the tail in your summary).
- Offline tests for the worker-side seed intake (idempotent, tagged).
- A markdown walkthrough (design/day-zero.md): the interview script, the
  consent language, what data flows where.

## Rules
Work only in this repo copy. Do NOT touch production, do NOT push, do NOT
edit files outside app/ios/ + brain/ + tests/ + proof/ + design/. Commit
scoped work, print DONE + summary.
