# Consumer UX audit — 2026-08-30

## Verdict

Anticipy has a distinctive, premium visual language and unusually honest
privacy copy. It does not yet feel consumer-finished because the primary value
is buried under explanation and sample content, onboarding asks for too much
before value, and Settings openly exposes an unfinished migration plus a large
developer/diagnostic surface.

The audit used a real local account and a deterministic XCUITest route. It
produced 25 screenshots and failed if a page boundary was not actually reached.
It covered every primary first-run and top-level Settings page, listening
diagnostics, one permission detail, the complete legacy settings form, and
light/dark appearance. It did not exercise real microphone permission, hardware
pairing, voice enrollment, destructive confirmation or server deletion.

## Fixed during the audit

1. Profile no longer displays the phone component's country-code error under
   unchanged name/email/birthday fields.
2. An inert `StateRow` no longer collapses its visual value; Listening now shows
   `Right now — Off` as its accessibility value already promised.
3. The screenshot walker now uses assertions and accessibility navigation; a
   false-green run that remains on onboarding is no longer possible.

Final walk: pass, zero failures, 134.495 seconds, iPhone 17 Pro simulator on
iOS 26.5.

## Priority findings

### P0 — blocks “consumer-finished”

1. **Settings tells the user the app is unfinished.** The root says “Pendant,
   voice, browser and the rest” and “These haven't moved to the new layout
   yet.” The next screen is a long legacy form. Remove the migration scar from
   the product and finish the information architecture.
2. **Legacy Settings exposes implementation and repair surfaces.** It contains
   speech-engine fallback, pendant status, backend URL, extension code, haptics
   troubleshooting, raw engine state and disabled/unavailable actions alongside
   normal account controls. Consumer controls, diagnostics and developer
   plumbing need separate destinations and release gates.
3. **Home delays proof of value.** The actual listening and typed-input controls
   are clear, but the rest of the first screen is a large explainer plus demo
   cards that resemble real data. Put current state, the last thing caught and
   the next useful action above examples; label examples explicitly.

### P1 — major conversion and trust cost

4. **First run is too long before value.** Welcome → explanation → account form
   → microphone essay → account confirmation repeats the pitch and asks for
   phone/profile data before the product has helped. Ask only for what the next
   action needs and postpone the rest.
5. **The custom microphone pre-alert is long and ambiguous.** It has four
   promise paragraphs and two equal exits before the system prompt. Apple says
   custom pre-alerts should be contextual, make clear the next action opens the
   system alert, and ideally use one button. Shorten this to the immediate
   reason and preserve a clear, non-manipulative way to continue without
   listening.
6. **Authentication is password-only.** Sign-in is visually clean, but a modern
   consumer iOS app should evaluate Sign in with Apple or passkeys. Signup also
   asks for a phone number up front.
7. **Listening uses a navigation affordance for an immediate action.** “Start
   listening” ends in a chevron but performs the action in place. Use a direct
   action style. Pause durations should be disabled or explained while the
   current state is Off.

### P2 — polish and consolidation

8. Appearance copy (“The way she looks by default”, “Remembered, once you pick
   it”) explains implementation rather than helping a person choose.
9. Listening diagnostics are transparent and valuable, but their visual system
   is separate from the new Settings kit and the “send log” row reads as a
   technical escape hatch. Preserve transparency while tightening the layer.
10. Access and About are the strongest settings pages: short, state-forward,
    specific about consent, and easy to reverse. Use them as the internal model.
11. Dark mode is coherent and readable in the tested primary surfaces.

## Benchmarks

- [Apple onboarding guidance](https://developer.apple.com/design/human-interface-guidelines/onboarding)
  emphasizes fast, optional onboarding, learning by doing, contextual help and
  postponing nonessential setup.
- [Apple privacy guidance](https://developer.apple.com/design/human-interface-guidelines/privacy)
  emphasizes contextual permission asks, clear custom pre-alerts, data
  minimization and passwordless/system authentication where appropriate.
- [Granola on iPhone](https://docs.granola.ai/help-center/ios/getting-started)
  gets quickly to a concrete object: an upcoming or ad-hoc note, with direct
  creation and a notes list. Its App Store listing also foregrounds one-tap
  widget capture, calendar context, summaries, actions and sharing.
- [Oura](https://apps.apple.com/us/app/oura/id1043837948) compresses a complex
  sensor product into three daily scores, immediate guidance, trends and tags.
  Anticipy needs an equivalent compact “what happened / what matters / what can
  I do” hierarchy rather than a transcript-shaped home.
- [Day One](https://apps.apple.com/us/app/day-one-daily-journal-diary/id1044867788)
  pairs fast capture with strong privacy, Face ID, export, backup and audio
  transcription without making setup the main experience.
- [Limitless](https://apps.apple.com/us/app/limitless-ai-voice-recorder/id6737710033)
  is a useful anti-benchmark: its promise is close to Anticipy's, while reviews
  call out transcript segmentation and organization. Raw capture cannot be the
  information architecture.

## Recommended execution order

1. Finish Settings architecture and remove every migration/developer sentence
   from the consumer route.
2. Prototype a one-screen value-first Home with real/demo separation.
3. Compress onboarding and defer profile/phone.
4. Correct action affordances and align diagnostics with the Settings kit.
5. Run the same asserted walk at small-screen width, dark mode and accessibility
   text sizes, then add controlled fixtures for conditional pages.
