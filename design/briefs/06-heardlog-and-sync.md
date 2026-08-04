# Brief 06 — Heard-log redesign + one synced conversation (roadmap §4 + §5)

## Mission (iOS, one build)
Omar: "I don't want a log of everything I said… the only thing that should
pop up is actionable."
- **Home** shows ONLY: her greeting, the listen control, actionable cards
  (things needing his OK; things she delivered to the desk), and the chat
  thread with her.
- The raw HEARD stream moves behind an "Everything I've heard" screen
  reachable from Settings — an audit log, not the living room. Checkmark
  micro-moments stay but decay (fade after seconds), never a wall of bullets.
- **One conversation**: the app chat renders the same thread SMS uses
  (`anticipy_text` / inbound SMS events are already in the events
  collection); sending from the app joins the same thread (post the message
  as the same kind the SMS inbound path produces, so the brain answers it
  identically). Whichever surface he looks at shows the same her.

## Context you must read first
- `app/ios/Anticipy/Views/ContentView.swift` — the current Home + heard log.
- `app/ios/Anticipy/Views/SettingsView.swift` — where the audit screen hangs.
- `app/ios/Anticipy/Backend/AnticipyBackend.swift` + `Brain/BrainClient.swift`
  — how events are fetched/posted today.
- `backend/pb_hooks/sms.pb.js` + `brain/worker.py` SMS-in handling — the
  event kinds that make up the SMS thread.
- `app/ios/Anticipy/Theme.swift` — the design language. This app is
  consumer-grade premium: dark room, one lit thing per screen, 17pt+, grain.
  NOTHING may feel developer-ish.

## Design constraints (non-negotiable)
- SwiftUI, iOS 16.0 target, builds with `app/ios/build_on_mac.sh` (or
  xcodegen + xcodebuild -scheme Anticipy). The build MUST compile clean.
- No backend schema changes; use existing events kinds. If the app must
  post an owner message, mirror the exact shape the worker already consumes
  for SMS (`sms_in`-equivalent) so ONE brain path answers both.
- Do not remove capabilities (mic, pairing, pendant); only move surfaces.
- Keep diffs surgical — this file is shared with other work; do not
  reformat untouched code.

## Definition of done
- `xcodebuild` compiles with zero errors (run it; paste the tail in your
  summary).
- A markdown walkthrough (design/heardlog-sync.md): each screen, what moved
  where, and how the app/SMS thread unification works, plus what the
  manager should verify by eye in the simulator.

## Rules
Work only in this repo copy. Do NOT touch production, do NOT push, do NOT
edit files outside app/ios/ + design/. Commit scoped work, print DONE + summary.
