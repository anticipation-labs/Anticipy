# Anticipy — One Direction

**Files:** `/Users/omarebrahim/Anticipy-pendant/app/ios/Anticipy/Theme.swift`, `Views/AuthView.swift`, `Views/OnboardingView.swift`, `Views/ContentView.swift`, `Views/SettingsView.swift`, `AnticipyApp.swift`
**Target:** iOS 16.0 (`Anticipy.xcodeproj/project.pbxproj:280, 365`). Everything below compiles on 16.0. No backend, no new data, no pendant.

---

## 1. The one-line direction

> **She is a person speaking in a dark room, not a document about a product — so exactly one thing on every screen is lit, she says it at 17pt or larger, and the room has grain in it.**

Three tests any change must pass. If a change fails one, don't make it.

1. **Is this a sentence she is saying?** Then it is 17pt or bigger, in ivory, with real leading. `Theme.gray` never carries a sentence again — it is for counts, timestamps and error codes.
2. **Is exactly one object on this screen lit?** One bloom, one elevated card, one bright control. If two things are competing, one of them is wrong.
3. **Does this arrive from somewhere?** Nothing fades in from nowhere; nothing pops. Insertions move, removals collapse, and one curve — `springJoy` — is rationed to four moments in the entire app.

---

## 2. The system first — `Theme.swift`

This file is currently 8 colors, one broken font function and two springs. Every other change in this document compiles against what's added here. Do this first; it lifts all five screens before you touch a single view.

### 2.1 The serif does not render. Fix this before anything else.

`Theme.swift:24-27` calls `.custom("New York", …)`. New York is a font **design**, not a lookup-by-name family — `UIFont(name: "New York", size: 24)` returns `nil`, and `Font.custom` falls back to SF Pro **silently**. All 13 `Theme.display()` call sites are currently SF Pro at arbitrary point sizes. That is the entire brand voice, absent on device.

Verify in 30 seconds: drop `Text(String(describing: UIFont(name: "New York", size: 24)))` into any view. It prints `nil`.

```swift
/// New York, reached the way iOS actually exposes it — as a font *design*,
/// not a lookup-by-name. Font.custom("New York") resolves to nil and falls
/// back to SF Pro silently, which is what shipped. Manual UIFontMetrics
/// keeps the Dynamic Type behaviour that relativeTo: used to give us.
static func display(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
    let scaled = UIFontMetrics(forTextStyle: .largeTitle).scaledValue(for: size)
    return .system(size: scaled, weight: weight, design: .serif)
}
```

The default `weight:` argument keeps all 13 existing call sites compiling untouched.

### 2.2 Three serif sizes. Not eight.

Eight sizes are in use today (18, 21, 24, 26, 28, 32, 34, 44) with no ratio between them. Collapse to three on a ~1.35 ratio, each with tracking. Use `.tracking()`, never `.kerning()` — tracking leaves no trailing whitespace.

| Token | Tracking | Every place it is allowed |
|---|---|---|
| `display(40)` | `-1.0` | Onboarding wordmark; Home empty-state headline. **Two uses in the app.** |
| `display(30)` | `-0.5` | Every screen headline: AuthView title, all four onboarding page titles, the four connection-state headlines, the completion line, the Settings listening state, the forget-me sheet |
| `display(22)` | `-0.2` | Nav titles, "Needs your OK", Settings section headers, the listen control's label |

Delete 18, 21, 24, 26, 28, 32, 34, 44 as usable sizes.

### 2.3 Three body registers. Not five.

108 text runs across the views are 16pt or smaller; four are 17pt. `Theme.gray` (#8A8A8A) is the most-used colour in the app and carries most of the readable prose. `.lineSpacing` is called **zero times** in the entire codebase.

| Register | Spec | What goes in it |
|---|---|---|
| **Voice** | `.system(size: 17)` · `.lineSpacing(3)` · `Theme.ivory` | Anything she is saying. Her briefing, every card body, every error sentence, transcript text, every privacy promise, every consequence line |
| **Aside** | `.system(size: 15)` · `.lineSpacing(2)` · `Theme.sand` | Supporting explanation that sits under a control |
| **Meta** | `.system(size: 12, weight: .semibold)` · `.tracking(1.2)` · `.textCase(.uppercase)` · `Theme.gray` — or plain 12pt gray for values | Section chronology labels, timestamps, counts, "Error 503", the version string |

`.lineSpacing` in SwiftUI **adds** to leading — 17 + 3 lands at ≈25pt, which is the 1.45× you want. Apply it to every paragraph that already carries `.fixedSize(horizontal: false, vertical: true)` (there are 18).

Delete `.caption2` (11pt) and `.footnote` (13pt) from every consumer-visible surface. Keep `.caption2.monospaced()` for the DEBUG error dump in `SettingsView.swift:329` only.

### 2.4 Space, radius and the third elevation rung

23 distinct padding values and 4 corner radii exist today. Add the scales; use nothing else.

```swift
extension Theme {
    /// Level-2 elevation. The dark ladder is #0C0C0C → #1E1E1E → #262626;
    /// ink and card were rungs 0 and 1, this is the missing third.
    static let raised = Color(hex: 0x262626)

    /// Destructive, in the brand's register. systemRed appears nowhere else
    /// in this product and reads as borrowed from Apple. The ONLY new hue.
    static let alarm = Color(hex: 0xC96A5A)

    enum Space {
        static let hair: CGFloat = 4      // icon ↔ label
        static let tight: CGFloat = 8     // inside a row
        static let snug: CGFloat = 12     // between rows in a group
        static let base: CGFloat = 16     // screen margin
        static let card: CGFloat = 20     // card interior
        static let roomy: CGFloat = 24    // hero interior
        static let section: CGFloat = 32  // above a section header
        static let wide: CGFloat = 40     // between major blocks
        static let hero: CGFloat = 72     // top of a hero screen
    }
    enum Radius {
        static let small: CGFloat = 12    // fields, chips
        static let card: CGFloat = 20
        static let hero: CGFloat = 28
    }
}
```

**The ratio is the point:** space *between* groups must be ≈2.5–3× space *within* a group (32 vs 12). At today's 18-and-18 the eye cannot find the groups, and that single fact is most of why the app reads as a list rather than a layout.

### 2.5 The card, rebuilt — and given a second register

`Theme.stroke` #252525 on `Theme.card` #1E1E1E measures **1.09:1**. The border on all 11 cards is optically absent. There are zero shadows, zero materials and zero blurs in the app.

```swift
struct CardBackground: ViewModifier {
    var elevated = false
    private var r: CGFloat { elevated ? Theme.Radius.hero : Theme.Radius.card }

    func body(content: Content) -> some View {
        content
            .padding(elevated ? Theme.Space.roomy : Theme.Space.card)
            .background(
                RoundedRectangle(cornerRadius: r, style: .continuous)
                    .fill(elevated ? Theme.raised : Theme.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: r, style: .continuous)
                            // A 9%-white top edge fading to 2% at the bottom is a
                            // single light source above. The old flat #252525
                            // border was 1.09:1 against the fill — invisible.
                            .strokeBorder(
                                LinearGradient(colors: [.white.opacity(0.09), .white.opacity(0.02)],
                                               startPoint: .top, endPoint: .bottom),
                                lineWidth: 0.75)
                    )
            )
            // Two layers, not one: a heavy single shadow goes muddy on dark.
            .shadow(color: .black.opacity(elevated ? 0.55 : 0), radius: 2,  y: 1)
            .shadow(color: .black.opacity(elevated ? 0.35 : 0), radius: 18, y: 10)
    }
}

extension View {
    func anticipyCard(elevated: Bool = false) -> some View {
        modifier(CardBackground(elevated: elevated))
    }
}
```

**`elevated: true` gets used in exactly three places app-wide:** the Home briefing hero, the onboarding pairing-success scene, the Settings listening hero. Nowhere else, ever. It is the only mechanism the app has for saying "this matters more than that."

Every `RoundedRectangle` in every view file gets `style: .continuous`. Kill the stray radii: 10 (`OnboardingView.swift:485`) and 14 (`ContentView.swift:912`, `AuthView.swift:158/161`) all become `Theme.Radius.small` = 12.

### 2.6 Motion: three curves, and one of them is rationed

```swift
static let spring     = Animation.spring(response: 0.35, dampingFraction: 0.80) // state
static let springSlow = Animation.spring(response: 0.55, dampingFraction: 0.85) // page / hero
/// The only curve allowed to overshoot. Four call sites in the whole app.
static let springJoy  = Animation.spring(response: 0.30, dampingFraction: 0.62)
```

`springJoy` fires **only** at: onboarding pairing success, onboarding completion, a transcript line flipping to `"act"`, and the Settings "Saved" confirmation. Damping 0.62 on ordinary UI reads as a toy; on a rare peak it reads as joy. The difference is entirely how seldom it fires.

Kill the three strays: `OnboardingView.swift:59` `.easeInOut` → `Theme.springSlow`; `OnboardingView.swift:83` `.spring(duration: 0.3)` → `Theme.spring`; `ContentView.swift:840, 897` `.easeInOut(duration: 0.2)` → `Theme.spring`.

**Ambient motion runs on one harmonic.** Everything that loops forever is 1.6s or a clean multiple/division of it:

- `BreathingDot` — **1.6s** (`Theme.swift:250`, currently 1.5)
- `RadarRipple` — **3.2s** (`OnboardingView.swift:580-597`, currently 1.6)
- Waveform bars — **0.8s**, delays `0 / 0.13 / 0.27`
- The listen control's halo — **1.6s**, so halo and dot breathe as one organism

Also at `Theme.swift:247`: `.scaleEffect(1.25)` is a pulse, not a breath. Take it to **1.16** and widen the opacity swing at `:248` to `0.7 ↔ 1.0`.

### 2.7 `TypewriterText`: one speed, and it breathes at punctuation

She currently types at 36 cps in the welcome and 45 cps on Home — two tempos for one voice. And she runs straight through a full stop at mid-word speed, which is exactly what makes typed text read as *streaming* rather than *speaking*.

Replace the loop at `Theme.swift:220-224`:

```swift
for ch in text {
    guard typing else { return }
    shown.append(ch)
    let base = 1_000_000_000.0 / 40.0            // one speed, everywhere
    let mult: Double = ".?!".contains(ch)  ? 8
                     : ",;:—".contains(ch) ? 4 : 1
    try? await Task.sleep(nanoseconds: UInt64(base * mult))
}
```

Delete the `speed` parameter entirely and drop the `speed: 45` argument at `ContentView.swift:490`. Change the default `color` from `Theme.sand` to **`Theme.ivory`** and `font` to `.system(size: 17)` — this component *is* her, it should not default to the secondary voice. Split the cursor `▍` out of the composed `Text` (`:195`) and drive `.opacity(caret ? 1 : 0)` on `.easeInOut(duration: 0.53).repeatForever(autoreverses: true)`. Keep the `reduceMotion` bail, the tap-to-finish and the single `accessibilityLabel` — all three are correct.

**Where the typewriter is allowed:** her briefing, `freshAnticipySays`, the welcome line, the first line of each onboarding page, the mic-priming line, the pairing line, the completion line. **Never** on error copy, permission explanations, Settings, or `failureLine`. Watching "That code didn't match" get typed out is where a companion becomes twee.

### 2.8 `LogoMark` becomes her state machine, and draws itself

One glyph, four states, no face, no mascot. Default stays visually identical so all 13 existing call sites are unaffected.

```swift
enum MarkState { case idle, listening, working, needsYou }

struct LogoMark: View {
    var size: CGFloat = 64
    var state: MarkState = .idle
    var trim: CGFloat = 1                    // 0→1 draws the pill on
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var lineWidth: CGFloat { size * 0.07 }
    // idle      → dot static, full opacity, no bloom  (today's look)
    // listening → dot breathing 1.6s
    // working   → dot breathing 0.8s + champagne 0.10 bloom behind the mark
    // needsYou  → dot full + one springJoy 1.0→1.3→1.0 on arrival + 0.14 bloom
}
```

For the draw-on, `.strokeBorder` cannot be trimmed. Swap `Theme.swift:58-60` for:

```swift
RoundedRectangle(cornerRadius: (pillW - lineWidth) / 2, style: .continuous)
    .trim(from: 0, to: trim)
    .stroke(Theme.ivory, style: StrokeStyle(lineWidth: lineWidth, lineCap: .round))
    // .stroke straddles the path where .strokeBorder insets it — inset the
    // frame by lineWidth so the outer bounds are unchanged.
    .frame(width: pillW - lineWidth, height: pillH - lineWidth)
```

Gate every animating state behind `accessibilityReduceMotion`, exactly as `BreathingDot` already does at `Theme.swift:241`.

Then use the *same* component everywhere: 26pt in the Home toolbar (driven by real state, and drop `.accessibilityHidden(true)` from nothing — keep it, it says nothing a label doesn't), 22pt in the briefing hero, 40pt in the Settings listening hero, 96pt on the empty state.

### 2.9 Depth: one bloom per screen, always behind the mark

`AuthView.swift:32-34` already has the right instinct and the right comment ("the one piece of depth on the screen, so the eye lands in the right place"). Promote it to a token so it is something the app *has*, not something one screen did.

```swift
extension Theme {
    /// The eye-anchor. ONE per screen, always behind the mark. Two is wallpaper.
    static func bloom(_ opacity: Double = 0.12, radius: CGFloat = 300) -> some View {
        RadialGradient(colors: [Theme.champagne.opacity(opacity), .clear],
                       center: .center, startRadius: 8, endRadius: radius)
            .blur(radius: 30)
            .allowsHitTesting(false)
    }
}
```

Budget, one per screen: Auth `0.14 / 240` behind the mark (replacing the screen-wide wash — a tight bloom behind one object reads as light coming *off* the object; a full-screen wash reads as a gradient background). Onboarding welcome `0.12 / 300`. Mic page `0.14 / 260`. Pairing/completion `0.18 → 0.34` animated. Home: briefing hero `0.10 / 300` **or** empty state `0.14 / 260`, never both (they are mutually exclusive by the day-one rule in §3.2). Settings listening hero `0.10 / 260`.

### 2.10 Grain — the anti-synthetic texture

Flat #0C0C0C is the flattest surface a phone can render, and it reads as an absence of pixels rather than as a material.

```swift
import CoreImage

enum Grain {
    /// Generated at runtime, never bundled — a shipped PNG always ends up
    /// looking like a downloaded stock texture.
    static let image: Image = {
        let noise = CIFilter(name: "CIRandomGenerator")!.outputImage!
        let mono  = noise.applyingFilter("CIColorControls",
                     parameters: [kCIInputSaturationKey: 0, kCIInputContrastKey: 1.0])
        let tile  = mono.cropped(to: CGRect(x: 0, y: 0, width: 512, height: 512))
        let cg    = CIContext().createCGImage(tile, from: tile.extent)!
        return Image(uiImage: UIImage(cgImage: cg)).resizable(resizingMode: .tile)
    }()
}
```

Apply above `Theme.ink` in the root `ZStack` of `HomeView` (`ContentView.swift:84`), `OnboardingView` (`:48`), `AuthView` (`:29`) and `SettingsView` (`:351`):

```swift
Grain.image
    .opacity(0.035)
    .blendMode(.plusLighter)
    .ignoresSafeArea()
    .allowsHitTesting(false)
```

**Use `.plusLighter`, not `.overlay`.** Overlay blend multiplies toward black when the base is dark — on #0C0C0C (luminance 0.047) it collapses to nothing and you will conclude grain "doesn't work." `.plusLighter` adds. Tune between 0.025 and 0.045 on a real device in a dark room; above ~0.05 it reads as sensor noise.

### 2.11 Press response and the haptic vocabulary

`Pressable` (`Theme.swift:149`) — take the scale from `0.97` to **`0.96`** and add `.brightness(configuration.isPressed ? 0.04 : 0)`. A 3% scale on a 56pt capsule sits below the perception threshold; on a dark UI the brightness lift is what the eye actually registers.

Add the missing generator:

```swift
private static let selectionGen = UISelectionFeedbackGenerator()
/// A page turn is a selection, and iOS users expect the tick.
static func pageTurn() { selectionGen.selectionChanged(); selectionGen.prepare() }
```

Then wire the seven haptics that are missing or misfiring. `Haptics.taskDone()` — the crisp double-tap written at `Theme.swift:129` for exactly this — is currently called from **nowhere in the app**.

| Where | Change |
|---|---|
| `AnticipyApp.swift:252` | `Haptics.success()` → **`Haptics.taskDone()`**. The `seenDoneJobIDs` guard at `:251` is already correct. One word, and the signature haptic finally plays. |
| `ContentView.swift:105` | **Delete** `.onAppear { Haptics.engage() }`. It fires on a header re-appearing. |
| `ContentView.swift:374` | `SessionLine.received` false→true: `Haptics.herMessage()` + checkmark springs 1.0→1.3→1.0. A small promise kept, felt in the hand, several times a minute. |
| `ContentView.swift:382` | `line.decision` nil→`"act"`: `Haptics.taskDone()`, guarded by `@State private var celebrated = false` so the 3s poll can't re-fire it |
| `AuthView.swift:41` | `problem` nil→non-nil: `Haptics.warning()` (defined at `Theme.swift:116`, fired from no view today) |
| `OnboardingView.swift:66` | `Haptics.pageTurn()` on every `step` change |
| `SettingsView.swift` | `.pressable` on all 21 non-debug buttons; `engage()` in `stopNow()`, `pairing()` in `startNow()`, `success()` after both saves, `warning()` on `.noMatch`, `taskDone()` on `.paired` |

Not to add: no haptic on scroll, none per typed character, none on poll-driven feed updates.

---

## 3. Per screen, in build order

Each step is shippable on its own. Stop anywhere and the app is better, not half-done.

### Step 1 — The global sweep (all four view files, no restructuring)

Mechanical, safe, and it is most of the distance. Do it in one pass:

1. Every `.callout` / `.footnote` / `.caption2` carrying a sentence → **Voice** (17pt ivory, `lineSpacing(3)`) or **Aside** (15pt sand, `lineSpacing(2)`).
2. Every `Theme.gray` on a sentence → `Theme.sand` or `Theme.ivory`. Gray survives only on: `statusPill` details, `"Error \(status)"` (`ContentView.swift:633`), timestamps, the "doesn't look like a full number yet" line (`OnboardingView.swift:411`), the version string (`SettingsView.swift:346`).
3. Every serif call → 40 / 30 / 22 with tracking.
4. Every `RoundedRectangle` → `style: .continuous`; radii 10/14/18 → 12/12/20.
5. **Delete all six `ProgressView()`.** They are the most internal-tool pixel available. `ContentView.swift:342` (listening) becomes three champagne capsules, `RoundedRectangle(cornerRadius: 1.5).fill(Theme.champagne).frame(width: 3, height: 10)`, `.scaleEffect(y:)` animating `0.4 ↔ 1.0` on `.easeInOut(duration: 0.8).repeatForever(autoreverses: true)`, delays `0 / 0.13 / 0.27`. A listening app shows a waveform, never a spinner. `ContentView.swift:563, 749, 791, 863` and `AuthView.swift:175` become `BreathingDot(size: 6)` at the appropriate tint.
6. `ContentView.swift:161` → `.toolbarBackground(.ultraThinMaterial, for: .navigationBar)` + `.toolbarColorScheme(.dark, for: .navigationBar)`. One line, and it is the single clearest "this is a real, current iOS app" signal available.
7. `AnticipyApp.swift:12-22` — add `.animation(Theme.springSlow, value: session.isSignedIn)` and `.animation(Theme.springSlow, value: hasOnboarded)` on the `Group`, `.transition(.opacity)` on each branch. Today both boundaries are single-frame cuts.
8. Wire the seven haptics from §2.11.
9. Grain in all four roots.

Cheap AuthView fixes, in the same pass:

- `:180` — the disabled button is `Theme.stroke` #252525 on #0C0C0C ink, a 25-value delta: **there is no visible button on screen until the form validates.** Change the false branch to `Capsule().fill(Theme.surface).overlay(Capsule().strokeBorder(Theme.stroke, lineWidth: 1))` with a `Theme.sand` label. Present, obviously not-yet-ready, not missing.
- `:42-44` — the error is painted `Theme.champagne`, the colour of every checkmark, the breathing dot and every primary button. A failure in the success colour reads correct at a glance and wrong on reading. Use the shape already proven at `OnboardingView.swift:507-524`: `VStack(alignment: .leading, spacing: 10)` in `.anticipyCard()`, sentence at 17pt `Theme.sand`, no SF Symbol, retry inside the card.
- `:198` — `password.count >= 8` is a rule nobody can discover. Under the password field, a 15pt line "Eight characters or more" that flips to `Theme.champagne` with `checkmark.circle.fill` and `Haptics.tap()` the moment it's satisfied — the exact pattern already working at `OnboardingView.swift:403-408`. Same for the `@` check. Two small rewards before commitment instead of one silent refusal.
- `:174-178` — delete the `ProgressView`; keep only `Text(buttonLabel)` (the labels at `:189-193` are already excellent). Add a 2pt `Rectangle().fill(Theme.ivory.opacity(0.35))` pinned to the capsule's bottom inside edge, `.scaleEffect(x: busy ? 1 : 0, anchor: .leading)` on `.linear(duration: 1.2).repeatForever()`. Zero geometry change; a sweep reads as work, a spinner that shoves the label sideways reads as a stall.
- `:154` — `@FocusState` only drives a border colour. Add `.submitLabel(.next)` / `.go`, an `.onSubmit` chain, and `.task { try? await Task.sleep(nanoseconds: 400_000_000); focus = .email }` so the first field is live without racing the view transition.
- Open in `.signIn` with the email prefilled whenever `session.ownerEmail` is non-empty (`AnticipyApp.swift:92`).

**What the user feels:** the app stops whispering. Every sentence is readable at arm's length, cards look like panels lit from above instead of slightly different greys, the header blurs as content passes under it, and the phone buzzes correctly the first time she finishes something she promised.

---

### Step 2 — Home (`Views/ContentView.swift`)

The screen with the most hours on it. Today: seven identical #1E1E1E rectangles down a flat black page, everything separated by exactly 18pt.

**2a. Variable rhythm.** `:86` is `VStack(alignment: .leading, spacing: 18)` wrapping the *entire* feed — status strip, briefing, listen control, four section headers and every card, all at 18. Inside the cards the spacings are 3/5/6/8/10/12/14/16, so the gap *between* groups is barely wider than the gap *within* one. Set the outer stack to `spacing: 0` and drive rhythm explicitly. Section headers `.padding(.top, Theme.Space.section)` / `.padding(.bottom, Theme.Space.tight)`; sibling rows in a `VStack(spacing: Theme.Space.snug)`; hero blocks `.padding(.top, Theme.Space.wide)`. Replace the four hardcoded `.padding(.top, 70)` (`:566, 588, 618, 645`) with `Theme.Space.hero`.

**2b. Fix the opening statement.** Today a fresh install paints, in order: "No pendant", "Chrome not linked", then a card where she says *"I'm not listening yet"*, then a near-invisible capsule, then a second 72pt logo announcing *"Live your day."* — three LogoMarks on one screen and two headlines that flatly contradict each other. The status strip's own copy argues for the fix (`:251`: "You don't have a pendant set up — you don't need one").

```swift
VStack(alignment: .leading, spacing: 0) {
    if micNeedsHelp { micRecoveryCard.padding(.top, Theme.Space.tight) }
    // Day one is ONE composition: she speaks inside the hero, not above it.
    if verified && !feedIsEmpty { briefingHero.padding(.top, Theme.Space.snug) }
    listenHero.padding(.top, feedIsEmpty ? Theme.Space.tight : Theme.Space.roomy)
    if feedIsEmpty { /* the four states */ } else { /* the four sections */ }
    statusStrip.padding(.top, Theme.Space.wide)     // diagnostics belong at the foot
}
```

**2c. The listen control becomes the one lit object.** `:320-335` — the switch that turns the entire product on is a 16pt label in a ~34pt capsule, and when idle it is `Theme.surface` #161616 on `Theme.ink` #0C0C0C: a 10-value delta, functionally invisible. Two rows down, `ConfirmJobCard`'s "Send it" is full-width and filled solid champagne. The control that turns her on is smaller and darker than the button that approves one email.

```swift
HStack(spacing: Theme.Space.snug) {
    if session.listener.isListening { BreathingDot(size: 10) }
    else { Image(systemName: "mic").font(.system(size: 18, weight: .medium)) }
    Text(listenButtonLabel).font(Theme.display(22)).tracking(-0.2)
    Spacer()
    if session.listener.isListening { WaveBars() }
}
.padding(.horizontal, Theme.Space.card)
.frame(height: 60).frame(maxWidth: .infinity)
.background(
    RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
        .fill(session.listener.isListening ? Theme.champagne : Theme.card)
        .overlay(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
            .strokeBorder(session.listener.isListening ? .clear : Theme.champagne.opacity(0.45),
                          lineWidth: 1)))
.foregroundStyle(session.listener.isListening ? Theme.ink : Theme.ivory)
.shadow(color: Theme.champagne.opacity(session.listener.isListening ? 0.30 : 0), radius: halo)
```

`halo` animates `18 ↔ 30` on `.easeInOut(duration: 1.6).repeatForever(autoreverses: true)` — the same period as `BreathingDot`, so the halo and the dot breathe as one organism rather than two unrelated widgets.

**2d. The briefing becomes the hero.** `:448-472`. Drop the `LogoMark + "Anticipy"` label row (`:450-455`) — the nav bar two inches above already says Anticipy, and it is a wasted headline slot. Pull `greeting` out of the joined string at `:501` and make it the headline: `Text(greeting).font(Theme.display(30)).tracking(-0.5).foregroundStyle(Theme.champagne)`. The remainder becomes Voice. `freshAnticipySays` (`:463-467`) goes to Aside, separated by a `Theme.champagne.opacity(0.14)` 1px divider with 12pt above and below, not the current `.padding(.top, 2)`. Wrap the whole thing in `.anticipyCard(elevated: true)` with `Theme.bloom(0.10, radius: 300)` behind it. She now *opens* with "Evening." in serif; that alone is the difference between a designed card and a string join.

**2e. Four card registers instead of one.** Seven `.anticipyCard()` calls on this screen; with real data "Heard" alone renders up to 30 identical rounded rectangles in a row.

| Register | Who | Spec |
|---|---|---|
| **Hero** | briefing only | `.anticipyCard(elevated: true)` + bloom |
| **Card** | `ConfirmJobCard` only — the only thing that asks something of you | `.anticipyCard()`, radius 20, padding 20 |
| **Rule** | `TranscriptRow` (`:988`) | **No container.** `HStack(alignment: .top, spacing: 12)` with a 2pt `Capsule().fill(Theme.champagne.opacity(0.35))` at the leading edge; text 17pt ivory; 20pt between entries. Speech should look like speech. |
| **Row** | `DoneCard` (`:920`), `HandlingCard` (`:808`) | **No container.** Icon + text on the ink, `.padding(.vertical, 16)`, one `Rectangle().fill(Theme.stroke).frame(height: 0.5)` between siblings only. |

**2f. Two section-header registers.** `:550` serves four sections of wildly different importance identically, and `display(21)` next to 16pt body is a 1.3× jump — too small to register as a different level, so it reads as "slightly bigger text."

- **"Needs your OK"** — the only one that demands an action: `Theme.display(22).tracking(-0.2)`, ivory, plus a count badge: `Text("\(needsOK.count)").font(.system(size: 12, weight: .bold)).padding(.horizontal, 7).padding(.vertical, 3).background(Capsule().fill(Theme.champagne)).foregroundStyle(Theme.ink)`.
- **"Handling" / "Heard" / "Done"** — chronology, not commands: the **Meta** register (12pt semibold, tracking 1.2, uppercase, gray).

A tracked uppercase micro-label beside a large serif is an editorial move — it creates a visible second level and gives the serif something to be big *against*.

**2g. The empty state becomes the ghost of tomorrow.** `:642-659` is a poster with an apology button under it — and this branch is only reachable when `session.connection == .ready` (`:99`), i.e. the read *succeeded*, so "Check again" tells a first-timer something might be broken.

1. `LogoMark(size: 96).padding(.top, Theme.Space.hero)` over `Theme.bloom(0.14, radius: 260)`.
2. Greeting on its own line at `Theme.display(40).tracking(-1.0)` ivory; the rest at Voice, sized **by measure** — `.frame(maxWidth: 300)` (≈40 characters), not `.padding(.horizontal, 24)`. A margin fighting the layout is not a measure.
3. **A living manifest:** three rows of `BreathingDot(size: 6)` + 17pt sand — "things you say you'll do" / "names and dates you mention" / "anything that needs a reply" — dots staggered `.delay(0)`, `.delay(0.53)`, `.delay(1.07)` on the shared 1.6s curve so they pulse in sequence. Motion is the only thing that distinguishes *waiting* from *broken*.
4. A hairline, then a Meta label "When I catch something, it looks like this", then the **real** `TranscriptRow` and `ConfirmJobCard` fed fixtures at `.opacity(0.42).allowsHitTesting(false).blur(radius: 0.4)`. Both types have synthesized memberwise inits, no backend needed:
   ```swift
   AnticipySession.TranscriptLine(id: "demo-1",
       text: "I'll get that invoice over to you tonight", decision: "act")
   AgentJob(id: "demo-2", goal: "Draft the invoice email to Devon",
            params: "", status: "awaiting_confirm", result: nil, created: "")
   ```
   Using the actual components guarantees the promise matches the delivery. Content must be human — never "Example task 1."
5. **Delete `retryButton("Check again")` from this branch only** (`:656`). Keep it on loading / offline / refused. Pull-to-refresh is already wired at `:139`.

**2h. Rows arrive from somewhere.** `:136-137` animates the *container*, and there are **zero** `.transition(` calls in the file — so every insertion is a raw fade and any single change jellies the whole stack, which is exactly the "page reload" the comment at `:134` says it is trying to avoid. Move it onto the rows and index the delay:

```swift
ForEach(Array(needsOK.enumerated()), id: \.element.id) { i, job in
    ConfirmJobCard(job: job)
        .transition(.asymmetric(
            insertion: .move(edge: .top).combined(with: .opacity),
            removal:   .opacity.combined(with: .scale(scale: 0.96))))
        .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)), value: session.jobs)
}
```

50ms per row, **capped at 250ms** — the cap is what stops the tail of a 30-row transcript looking broken. Same pattern for `handling` (`:120`), `transcript` (`:124`) and `finished` (`:128`).

**2i. Live transcription is the demo; stop styling it as fine print.** `session.listener.partial` (`:396-401`) — your own voice becoming text — is 13pt, `Theme.gray`, italic, positioned *below* the lines it produces. Move it **above** `sessionLines` (before `:370`), set it `.font(.system(size: 20))`, `Theme.ivory.opacity(0.55)`, `.lineSpacing(3)`, and let settled lines animate down into the list on `Theme.spring` with `.transition(.asymmetric(insertion: .move(edge: .top).combined(with: .opacity), removal: .opacity))`.

**2j. The "act" verdict.** `:382-388` — the instant the product becomes real is a 12pt caption with a bolt glyph. On `line.decision` nil→`"act"`: `Haptics.taskDone()`, label in on `springJoy` from `.scale(0.8)` at `.font(.system(size: 15, weight: .semibold))`, and flash the leading champagne rule to full opacity for 600ms.

**What the user feels:** the screen has a subject. One breathing champagne bar says *press me*, one raised panel says *she is talking*, everything else is quiet. Work arrives from the top instead of appearing. Watching your own sentence form at 20pt and settle into the record is the thing people hand the phone to a friend for.

---

### Step 3 — The first run (`Views/OnboardingView.swift`)

Five near-identical pages of grey paragraphs in flat cards, one animated moment out of five, ending on a Bool flipping into a screen that lists what you don't have.

**3a. The composition holds still while she speaks.** `stepBody` centres its VStack (`:223`), and at `welcomeStage >= 3` the 44pt placeholder (`:251`) is replaced by a `TypewriterText` that grows from one line to three as it types — so the 120pt logo and the 44pt wordmark **creep upward for the entire two seconds of her first sentence.** That is the first motion anyone sees in the product and it is unintentional.

Replace the placeholder and the `minHeight: 44` with the real string, invisible, as the height reservation:

```swift
Text("I'm Anticipy. I listen, I remember what matters, and I quietly do the work.")
    .font(.system(size: 17)).lineSpacing(3).multilineTextAlignment(.center)
    .opacity(0)
    .overlay(alignment: .topLeading) { if welcomeStage >= 3 { TypewriterText(...) } }
```

Wordmark (`:238-239`) → `Theme.display(40)` with `.tracking(-1.0)`. Mark draws itself: `trim` 0→1 over 0.75s `.easeInOut`, champagne dot drops in at completion with `Haptics.pairing()`. Retime the stages: `450_000_000` → **`320_000_000`** (`:258`), `400_000_000` → **`260_000_000`** (`:260`) — both currently sit outside the 400ms Doherty window, so the intro reads as the app thinking.

**3b. Hide the progress dots on page one.** `:74-89` sits above the welcome, turning her introduction into step 1 of 5 of a wizard. `.opacity(step == Step.welcome ? 0 : 1)` with `.animation(Theme.springSlow, value: step)`. Let the product introduce itself before it starts counting.

**3c. Stabilise the footer.** `:133-146` renders the skip button on two of five steps and reserves nothing on the other three, so the champagne capsule **moves 44pt vertically** on every page turn — the one control that must be the same object on every page is the one thing that isn't. Add `else { Color.clear.frame(height: 44) }`. And `Text(primaryLabel)` (`:122`) swaps string with no transition: add `.id(primaryLabel).transition(.opacity)` with `.animation(Theme.spring, value: primaryLabel)`.

**3d. The consent screen — the most important page in the product currently looks like an FAQ.** `micPrimer` (`:311-370`) stacks four identical `stepCard()`s: SF Symbol in a 30pt column + title + grey paragraph, all in the same flat card. Four evenly spaced symbol-and-card rows is the single most recognisable AI-built layout there is, and this is where someone decides whether to hand an always-listening app their microphone. Nothing on the page moves — `BreathingDot` doesn't appear until *after* permission is granted.

Keep all four promises; delete all four cards. Render them as a rule list: no fill, no border, no icon column — a 2pt `Theme.champagne.opacity(0.35)` capsule at the leading edge, 14pt gutter, title 17pt semibold ivory, body Voice, 24pt between items. Speech-shaped, not form-shaped.

Above the list, put the thing the page is about: `LogoMark(size: 88, state: .listening)` over `Theme.bloom(0.14, radius: 260)`, with three champagne capsules below it running the 0.8s waveform. Before permission the whole object sits at `.opacity(0.35)`; the instant `session.listener.isListening` flips, it goes to 1.0 on `Theme.springJoy` with `Haptics.pairing()`.

Type the headline: `:315` becomes `TypewriterText(text: "May I listen?", font: Theme.display(30), color: Theme.ivory)`.

**Prime the OS alert.** `advance()` at `:158-161` calls `session.startListening()` immediately, so iOS throws two system dialogs with no beat in between and the 13pt warning at `:360` is not read by anyone. Hold 500ms and type one line first — **"Two taps from iOS. Both of them are me."** — then start. The app conducts the permission moment instead of being ambushed by the OS mid-sentence.

**3e. Don't ask for the phone number twice.** `AuthView.swift:110` collects it during sign-up; ninety seconds later `:23` declares `@State private var phone = ""` and asks again from empty, with different copy and a different visual language. That is the clearest possible evidence nobody walked the flow end to end.

Seed it from `session.ownerPhone` in a `.task`. If it already passes `session.e164`, the step becomes a **confirmation**: `Theme.display(30)` "I'll reach you at", the number at `.system(size: 22, design: .monospaced)` ivory, and a 15pt sand "Change it". One tap instead of retyping.

If it is empty: **delete the 54pt `Image(systemName: "message")` at `:374-376`** — a giant stock SF Symbol as a hero is the loudest AI-built tell on the screen. Let `LogoMark(size: 72)` + bloom carry it, or nothing at all. Move `.padding(.horizontal, 12)` (`:394`) *inside* the background — right now 12pt of dead, tappable-looking space flanks the field. Add `.overlay(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).strokeBorder(valid ? Theme.champagne : Theme.stroke, lineWidth: valid ? 1.5 : 1))` on `Theme.spring`, so the "That's you" moment at `:404` has a border to light up with. Add `@FocusState private var phoneFocused` focused 350ms after the step lands, a keyboard toolbar `Done` button (`.phonePad` has no return key and the footer can sit under the keyboard on a small phone), `.scrollDismissesKeyboard(.interactively)` on the `ScrollView` at `:216` (AuthView already does this), and format as you type in the existing `.onChange(of: phone)` at `:395` → `+1 604 555 0123`.

**3f. The six-digit code is a ceremony, not a form.** `:480-497` — one `TextField` at the only 10pt radius in the flow, no `.textContentType(.oneTimeCode)`, beside `Button("Pair").buttonStyle(.borderedProminent)` — the only stock-styled button in the entire app, in system chrome, two lines below hand-built champagne capsules.

Six 44×54 boxes at `Theme.Radius.small` filled `Theme.surface`; the active index gets a champagne 1.5pt border and `.scaleEffect(1.06)` on `Theme.spring`; digits at `.system(size: 24, weight: .medium, design: .monospaced)` ivory. One hidden `TextField` behind them holds the string with `@FocusState`, `.textContentType(.oneTimeCode)` and `.keyboardType(.numberPad)`. Each landed digit fires `Haptics.tap()` and springs its own box 1.15 → 1.0. **On the sixth character call `pair()` automatically and delete the "Pair" button entirely.** Keep the `.unreachable` recovery card at `:507-524` exactly as written — it is the best error copy in the flow.

**3g. Pairing takes over the step.** `:469-478` — two devices finding each other, the only genuinely magical thing in this flow, renders as a `BreathingDot(size: 8)` and 13pt text *smaller than the instructions above it*. Meanwhile `RadarRipple` (`:580-597`) is a finished, Reduce-Motion-aware scanning animation, 57 lines, **referenced by zero screens in the app.**

On `session.agentPaired` → true: `withAnimation(Theme.springJoy) { paired = true }`, the instruction stack goes to `.opacity(0)` and collapses out of the layout, and in its place `LogoMark(size: 104)` with two `RadarRipple()`s inverted to collapse **inward** (scaleEffect 1.45 → 1.0), plus `Theme.bloom(0.18, radius: 220)`. `Haptics.pairing()` on arrival, then her line typed: **"Your browser is mine now. In a good way."** Wrap the scene in `.anticipyCard(elevated: true)`. The footer already flips to "Start living your day" at `:101` — leave it.

**3h. The ending. This is the peak-end moment of the entire product and it is currently a Bool flipping.** `advance()`'s final branch (`:181-182`) is `Haptics.success(); hasOnboarded = true` — a generic notification buzz and an instantaneous view swap into a screen whose first words are two negatives.

Add a sixth beat, ~40 lines, before `hasOnboarded = true`:

```swift
@State private var finishing = false
// on the last tap:
withAnimation(Theme.springSlow) { finishing = true }
```

Overlay a full-bleed `Theme.ink` scene: `LogoMark(size: 132)`, two `RadarRipple()`s collapsing inward (1.45 → 1.0 on `.easeOut(duration: 1.6)`), a champagne bloom animating `opacity 0.10 → 0.34 → 0.22` over 1.2s. `Haptics.pairing()` at t=0, `Haptics.taskDone()` at t=+0.55s. Her line typed at `Theme.display(30)`: **"Give me a day. You'll see."** Hold 1.4s after the last character, then set `hasOnboarded = true` — and because Step 1 already put `.animation(Theme.springSlow, value: hasOnboarded)` on the `Group` in `AnticipyApp.swift`, the app dissolves into Home rather than cutting.

**3i. One page-entrance choreography.** `howItWorks` staggers three cards at `110_000_000` ns (`:297`) — 330ms of cascade, which reads as waiting. Take it to **`70_000_000`** (210ms total: still legible as a cascade, no longer a wait). Give every page the same four-beat entrance keyed on `step`, 80ms apart on `Theme.springSlow`: title (`offset y 10 → 0` + opacity) → subtitle → items (staggered 70ms) → footnote.

**What the user feels:** she introduces herself while the screen holds perfectly still, asks for the microphone with a mark that is visibly listening, hands the phone a laptop and gets a celebration for it, and the last four seconds — the ones they will describe to a friend — are a mark collapsing inward, two haptics, one typed sentence, and a dissolve.

---

### Step 4 — The door (`Views/AuthView.swift`)

The file's own doc comment says "It is deliberately not a form." It renders as the densest form in the product: three labelled fields plus a disclaimer paragraph before she has said one thing.

**4a. Delete the field labels.** `:132-136` — `Text(label.uppercased()).font(.caption2.weight(.semibold)).tracking(1.1).foregroundStyle(Theme.gray)` is 11pt uppercase grey: a Stripe-dashboard label, and it sits over an empty-placeholder box (`TextField("", text:)` at `:139`/`:142`), so an unfocused field is a blank grey rectangle with a tiny caps tag above it. Delete the row; the placeholder carries the label:

```swift
TextField("", text: text, prompt: Text("you@email.com").foregroundStyle(Theme.gray))
```

Prompts: `"Omar"` / `"you@email.com"` / `"At least 8 characters"` / `"+1 604 555 0123"` (that last string is already the right one at `OnboardingView.swift:386`).

**4b. Three beats, and she asks your name first.** The app never asks your name anywhere in the first run, which is why `ContentView.swift:521` greets everyone with a bare "Morning." forever. Every companion product that works asks one reciprocal question in the first sixty seconds and visibly uses the answer in the next sentence.

`@State private var beat = 0`, one mounted at a time:

- **beat 0** — first name. `.textContentType(.givenName)`, `.submitLabel(.next)`.
- **beat 1** — email **and** password together. Keep them paired so iOS AutoFill and the Keychain save prompt still fire.
- **beat 2** — number.

Titles change per beat at `Theme.display(30)` with `.id(title).transition(.opacity)`:

| Beat | Title | Subtitle |
|---|---|---|
| 0 | "I'm Anticipy." | "Before anything else — what should I call you?" |
| 1 | "Hello, Omar." | "An email and a secret, so this is yours on any phone you pick up." |
| 2 | "Last thing, Omar." | "When something needs your word I text you here. Nothing else ever uses it." |

Transition: `.asymmetric(insertion: .move(edge: .trailing).combined(with: .opacity), removal: .move(edge: .leading).combined(with: .opacity))` on `Theme.springSlow`, `Haptics.engage()` on advance.

Write the answer straight to `session.ownerFirstName` — it is `@AppStorage("ownerFirstName")` at `AnticipyApp.swift:90`, so **no backend call is needed**; `saveOwnerDetails` (`:301`) pushes it later. Then `ContentView.swift:521-528` returns `"Morning, \(session.ownerFirstName)."` when non-empty. Same four inputs, no extra taps, and the product can finally say your name back to you.

**4c. Land the two marks in the same place.** `AuthView.swift:73` is `LogoMark(size: 34)` pinned top-left; `OnboardingView.swift:234` is `LogoMark(size: 120)` scaling up from 0.6 in the centre — two hero logos, nearly four times apart in size, in different corners, with a hard cut between them, and the only screen with any depth is the one you just left. Take AuthView's mark to **72** and centre it above the serif title; start Onboarding's welcome mark at **72** (not `.scaleEffect(0.6)`) growing to 120 with the draw-in. The eye tracks one object across the boundary instead of losing one and finding another. Title drops from `display(34)` to `display(30)`.

**What the user feels:** a person asks their name, uses it in the very next sentence, and the mark they were looking at is still there when the next screen arrives.

---

### Step 5 — Settings (`Views/SettingsView.swift`)

This is where a frightened person goes looking for the off switch on an always-listening product. Trust is decided here, and the screen currently belongs to Apple.

**5a. Stop being the iOS Settings app.** Seven `Section("…")` string literals (`:43, 83, 114, 141, 162, 221, 285`) render as 13pt SF, UPPERCASED, in system grey. `:352` is `.navigationTitle("Settings")` with no display mode, so it renders as a large SF Pro bold title — literally Apple's own header. And the toolbar carrying `LogoMark` + the serif wordmark belongs to ContentView (`:141-150`), so it does not follow the push; neither does `.toolbarBackground` (`:161`), which means this screen's nav bar is a visibly different black from the `Theme.ink` behind it. There is a seam across the top.

```swift
Section { … } header: {
    Text("Listening")
        .font(Theme.display(22)).tracking(-0.2)
        .foregroundStyle(Theme.ivory)
        .textCase(nil)                       // ← without this iOS uppercases it anyway
        .padding(.top, Theme.Space.snug).padding(.bottom, Theme.Space.hair)
}
```

Plus `.listRowBackground(Theme.card)` and `.listRowSeparatorTint(Theme.stroke)` on each section, and replace `:352` with `.navigationBarTitleDisplayMode(.inline)` + a principal toolbar item (`LogoMark(size: 22)` + `Text("Settings").font(Theme.display(22))`) + `.toolbarBackground(.ultraThinMaterial, for: .navigationBar)` + `.toolbarColorScheme(.dark, for: .navigationBar)`.

**5b. The kill switch becomes an object.** `:44-46` is 16pt text; `:55` is `Button("Stop listening")` — a champagne word in a list row, visually identical to "Save details", "Pair a pendant" and "Open iPhone Settings". This file contains **zero** `LogoMark` and **zero** `BreathingDot`: nothing on it ever indicates she is live right now.

Hoist the section out of the `Form` into a hero above it: `LogoMark(size: 40, state: session.listener.isListening ? .listening : .idle)` + `BreathingDot(size: 10, active: session.listener.isListening)`, the state line at `Theme.display(30).tracking(-0.5)` in champagne-when-live, all in `.anticipyCard(elevated: true)` over `Theme.bloom(0.10, radius: 260)`. Under it, a full-width 56pt capsule with a `Theme.display(22)` label — filled champagne when off, `Theme.surface` when on — `.buttonStyle(.pressable)`. "Pause for a while" stays a `Menu` below at 15pt sand, because it is secondary.

Two-year-old-proof means a frightened person finds *stop* in under a second without reading.

**5c. The privacy promises stop looking like terms of service.** `:222-236` — five consecutive 16pt sand paragraphs, identical treatment, no separation, at default leading, inside Apple's inset-grouped rows with Apple's hairline separators between them. This includes the best sentence in the product ("Anyone near you is heard too, and they haven't agreed to any of this. Please tell them, or stop me while they're around.").

Lift it out of the `Form`. Headline at `Theme.display(22)`; each promise a 2pt `Theme.champagne.opacity(0.35)` capsule at the leading edge, 12pt gutter, text at **Voice in ivory** (17.3:1, not sand's 12.5:1), `.padding(.vertical, Theme.Space.tight)`. No fill, no border, no separators. Same rule-list shape as the mic primer in Step 3d — one gesture, used twice, in the two places she is asking to be trusted.

**5d. Birthday is a picker.** `:121` is `TextField("Birthday (YYYY-MM-DD)", text: $birthday)`. Nobody should ever type a wire format into a consumer app. `DatePicker("Birthday", selection: $birthdayDate, in: ...Date(), displayedComponents: .date).datePickerStyle(.compact).tint(Theme.champagne)`, converted with an ISO8601 formatter at save time. Add a `@FocusState` chain across first/last/email with `.submitLabel(.next)` and `.textInputAutocapitalization(.words)` on the names. On success, `Haptics.success()` and crossfade the button label to `Label("Saved", systemImage: "checkmark")` in champagne, entering on `Theme.springJoy` scale 1.0 → 1.12 → 1.0, reverting after 2s.

**5e. The exit is calm, and it is ours.** `role: .destructive` at `:106, 246, 254, 256` renders systemRed #FF453A — a colour that appears nowhere in the brand — and `.red`/`.orange` are hardcoded at `:194, 198, 303, 308, 315, 329`. Drop the role and set `.foregroundStyle(Theme.alarm)` explicitly. `:194` `.red` → `Theme.alarm`; `:198` `.orange` → `Theme.champagne` (that one says "my end, not your code" — a reassurance, not a failure). DEBUG block colours at `:303-329` can stay.

Then replace the stock `.alert` at `:255-260` — whose message is a single 62-word, five-clause paragraph at 13pt inside iOS's grey rectangle — with a `.sheet(isPresented: $confirmForget)` at `.presentationDetents([.medium])`: `Theme.display(30)` "Forget you on this phone?", the consequences broken into four separate Voice lines using the champagne leading rule from 5c, and two full-width 56pt capsules — "Forget me" filled `Theme.alarm`, "Keep me" filled `Theme.surface` — both `.pressable`. This is the moment someone decides whether they are allowed to leave; making it calm and legible is how you earn the right to be listened to at all.

**What the user feels:** the character does not vanish at the exact moment they went looking for the off switch, and the off switch is a 56pt object they can hit without reading.

---

## 4. What to cut

Removal is the cheapest quality there is. Every one of these is a deletion, not a redesign.

| # | Delete | Where | Why |
|---|---|---|---|
| 1 | All six `ProgressView()` | `ContentView.swift:342, 563, 749, 791, 863`; `AuthView.swift:175` | A stock UIActivityIndicator is the most internal-tool pixel available, and one of them is what "listening" currently looks like |
| 2 | The 54pt `Image(systemName: "message")` hero | `OnboardingView.swift:374-376` | A giant stock SF Symbol as a hero is the loudest AI-built tell in the flow |
| 3 | The four `stepCard()`s on the consent page | `OnboardingView.swift:322-331` | Four evenly spaced symbol-and-card rows is the most recognisable AI-built layout there is. Keep all four promises; delete the cards. |
| 4 | `Button("Pair").buttonStyle(.borderedProminent)` | `OnboardingView.swift:494-495` | The only stock-styled button in the app, sitting two lines below hand-built capsules. Auto-submit on the sixth digit replaces it. |
| 5 | The uppercase 11pt field labels | `AuthView.swift:132-136` | Prompts carry the label. This is the loudest enterprise-form cue in the product's first screen. |
| 6 | `retryButton("Check again")` from `emptyState` **only** | `ContentView.swift:656` | This branch is only reachable when the read *succeeded*. Offering a retry tells a first-timer something is broken. |
| 7 | The `LogoMark` + `Text("Anticipy")` row inside the briefing card | `ContentView.swift:450-455` | The nav bar two inches above already says it. Three LogoMarks on one screen. |
| 8 | `.onAppear { Haptics.engage() }` on the section header | `ContentView.swift:105` | The celebration gets spent on a header re-appearing |
| 9 | `.anticipyCard()` on `TranscriptRow`, `DoneCard`, `HandlingCard` | `ContentView.swift:988, 920, 808` | With real data this is 30 identical rectangles in a row |
| 10 | The briefing card on day one | `ContentView.swift:92` | She says "I'm not listening yet" directly above a hero that says "Live your day." Two headlines contradicting each other. |
| 11 | The `speed:` parameter on `TypewriterText` | `Theme.swift:187`, `ContentView.swift:490` | One voice, one tempo |
| 12 | Five serif sizes and four `.padding(.top, 70)` literals | throughout | A list is not a scale |
| 13 | `role: .destructive` and every `.red`/`.orange` outside DEBUG | `SettingsView.swift:106, 194, 198, 246, 254, 256` | systemRed appears nowhere else in this product |
| 14 | The second phone ask, when the first one worked | `OnboardingView.swift:23` | Being asked the same question twice is the clearest evidence nobody walked the flow |
| 15 | `.padding(.horizontal, 24)` used to narrow text | `ContentView.swift:576, 599, 631, 655` | A margin fighting the layout. `.frame(maxWidth: 300)` is a measure. |

---

## 5. The 60-second story

What a brand-new person sees, in order, and what must be true at each beat.

**0:00 — Launch.** A dark room with grain in it, not a black rectangle. One warm champagne bloom, top-centre, behind a 72pt ivory mark. Below it, in serif at 30pt: *"I'm Anticipy."* And one question: *"Before anything else — what should I call you?"* One field, live, cursor already in it. No password yet, no phone number, no paragraph.
→ **Must be true:** the serif actually renders (§2.1). One field on screen. The button is visible even before it is valid.

**0:08 — She uses your name.** The beat slides left, the next slides in from the right on `springSlow`. The title now reads *"Hello, Omar."* Email and password together. Under the password, a grey line: "Eight characters or more" — which turns champagne with a checkmark and a light tap the moment it's satisfied. Two small rewards before you've committed to anything.
→ **Must be true:** `session.ownerFirstName` is written. The rule is discoverable. Failures are never painted in the success colour.

**0:20 — The seam that isn't.** You tap "Start". The label doesn't move; a 2pt ivory sweep runs under it. Then the whole screen dissolves — not cuts — into the same room with the same mark in the same place, which now draws itself on, stroke by stroke, over 750ms, and the champagne dot drops in with two soft rising taps. The wordmark fades up at 40pt with real tracking. Then she types, and **nothing on the screen moves while she does it.**
→ **Must be true:** `.animation(Theme.springSlow, value: session.isSignedIn)` on the root `Group`. Height reserved with the real string. Marks land at the same size in the same place.

**0:30 — How it works.** Three items cascade in 70ms apart — 210ms total, a cascade, not a wait. Her sentences are 17pt ivory with real leading, not 13pt grey disclaimers.
→ **Must be true:** `Theme.gray` carries no sentence anywhere in this flow.

**0:38 — The ask.** *"May I listen?"* types itself in serif. Above it the mark sits over a bloom with three champagne bars moving to a rhythm at 35% opacity — a listening app showing what listening looks like. Four promises as a rule list with a champagne edge, not four cards. You tap *"Yes — start listening."* Nothing happens for half a second, and then one line types: **"Two taps from iOS. Both of them are me."** Only then does the OS alert appear.
→ **Must be true:** the app conducts the permission moment. The listening object jumps to full opacity on `springJoy` with `Haptics.pairing()` the instant permission lands.

**0:48 — Your number, already known.** She has it from the door. So the page says *"I'll reach you at"* and the number in monospace, with a quiet "Change it". One tap.
→ **Must be true:** `phone` seeded from `session.ownerPhone` in a `.task`; the step becomes a confirmation, not a second interrogation.

**0:52 — The browser, or not.** If they skip, the footer reads "I'll do this later" and they move on. If they pair, the instructions collapse out and the step is taken over by a 104pt mark with two radar rings collapsing *inward*, a champagne bloom, `Haptics.pairing()`, and one typed line: **"Your browser is mine now. In a good way."**
→ **Must be true:** `RadarRipple` — 57 finished lines currently referenced by zero screens — is used here. Elevated card. `springJoy`.

**0:56 — The end, which is the part they'll describe.** Last tap. The screen goes full-bleed ink. A 132pt mark, two rings collapsing inward over 1.6s, a champagne bloom rising 0.10 → 0.34 → 0.22. `Haptics.pairing()`, then `Haptics.taskDone()` 550ms later — the crisp double-tap that has never once played on a real phone. She types: **"Give me a day. You'll see."** A 1.4-second hold, and the whole thing dissolves into Home.
→ **Must be true:** `Haptics.taskDone()` is wired (`AnticipyApp.swift:252` and here). The `Group` dissolves rather than cuts.

**1:00 — Home, day one.** Not two grey pills about what they don't have. A 96pt mark over a bloom, *"Morning, Omar."* at 40pt serif, one 40-character sentence at 17pt, and three dots breathing in sequence beside "things you say you'll do" / "names and dates you mention" / "anything that needs a reply." Below a hairline, a Meta label — WHEN I CATCH SOMETHING, IT LOOKS LIKE THIS — and a real `TranscriptRow` and `ConfirmJobCard`, dimmed to 42%, showing *"I'll get that invoice over to you tonight"* → *"Draft the invoice email to Devon."* And above all of it, the one lit object on the screen: a 60pt champagne-outlined bar that says **Listen with phone.**
→ **Must be true:** the briefing card is suppressed when the feed is empty. The status strip is at the foot. There is no "Check again" button. Nothing else on this screen is as bright as that bar.

**1:06 — The delight.** They tap it. The bar fills champagne, a halo starts breathing at 1.6s in time with the dot, three bars move. They say *"I need to send Devon that invoice tonight"* — and their own sentence forms **above** the record at 20pt ivory, then settles down into the list with a checkmark that springs 1.0 → 1.3 → 1.0 and a barely-there tick in the hand. A moment later a bolt appears: **On it.** `springJoy`, `Haptics.taskDone()`, and the champagne rule beside the line flashes to full for 600ms.

That is the moment they hand the phone to someone else. Everything above exists to get them there in under seventy seconds, and to make sure that when they get there, it looks like it was made by a person.