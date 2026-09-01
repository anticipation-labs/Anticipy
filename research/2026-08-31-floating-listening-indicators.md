# Floating listening indicators — 2026-08-31

## Report and visual evidence

The founder supplied `IMG_4340.PNG`, `IMG_4341.PNG`, and `IMG_4342.PNG` from
the listening Home screen. Across consecutive screenshots, exactly four brown
marks changed page position: one circle and three narrow rounded bars. That
count and geometry map exactly to the shared `BreathingDot` and `WaveBars`
views in `app/ios/Anticipy/Theme.swift`.

The orange point inside the Dynamic Island is different: it is iOS's system
microphone privacy indicator and is expected while listening. The brown point
inside Anticipy's pill logo is also intentional. The defect was the duplicate
brown circle and three bars travelling outside their owning components.

## Root cause

Both shared views put a broad SwiftUI `.animation(...repeatForever..., value:)`
modifier around the rendered shape. That modifier creates an animation
transaction for the view, not a guarantee that only one property participates.
When Home's `ScrollView` settled or recomputed layout, the repeating transaction
also interpolated the shapes' positions. The three delayed bar transactions
made them escape independently, which is why the screenshot showed three
separate dashes plus one circle.

This is the same accidental-animation mechanism discussed in Apple's
[Explore SwiftUI animation](https://developer.apple.com/videos/play/wwdc2023/10156/)
session and its documentation for
[`Transaction`](https://developer.apple.com/documentation/SwiftUI/Transaction)
and
[`animation(_:value:)`](https://developer.apple.com/documentation/swiftui/view/animation%28_%3Avalue%3A%29).

## Repair

Commit `a8a3c128` removes the `@State` toggles and every `repeatForever`
transaction from `BreathingDot` and `WaveBars`. A `TimelineView` now derives
only scale and opacity from time. Their position is constant structural layout,
so there is no animation transaction capable of carrying either component
across the screen. Reduce Motion and Anticipy's Ambient Motion setting still
pause the effect.

`tests/test_ambient_motion_scope.py` holds the regression by proving that the
reported one circle and three bars use the time-derived path and contain no
repeating animation transaction.

## Verification and release

- The focused Python regression suite passed.
- The unsigned iOS Simulator build passed.
- Every suite in `app/ios/Tests/run_all.sh` passed.
- `git diff --check` passed.
- The fix was pushed to `origin/jose_anticipy_system` in `a8a3c128`.
- GitHub Actions run `33472845126` archived and uploaded build 115 successfully.
- App Store Connect reports `1.1.0 (115)` as `VALID`, unexpired, and
  `IN_BETA_TESTING`; automatic tester notification is enabled.

The release initially exposed a separate CI hygiene failure: ephemeral GitHub
runners had left eleven unusable `DEVELOPMENT / Created via API` certificate
records behind. Run `33472845126` removed those eleven orphan records before
signing. No named development, distribution, or Developer ID certificate was
eligible or touched. The workflow is now serialized, chooses its build number
from App Store Connect's live history, and performs this narrowly scoped cleanup
before future releases. Apple documents development-certificate ownership and
limits in its
[Certificates overview](https://developer.apple.com/help/account/create-certificates/certificates-overview).

## Phone proof

Refresh Anticipy in TestFlight and install build 115. While listening, the logo
dot and the waveform may breathe in place, but no brown mark should travel
through the page. The orange Dynamic Island microphone indicator remains while
the microphone is active because it is rendered by iOS, not Anticipy.
