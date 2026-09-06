import SwiftUI
import UIKit

// The first-run component kit. One grammar for every screen a stranger sees
// before Home: a warm cream ground, one question per screen, soft filled
// fields, a thin progress bar under the mark, black pills for the commit and a
// circular arrow for "next". Every control here springs on `Theme.spring`, so
// the whole flow moves as one object.
//
// Tokens live here rather than in Theme.swift because this ground is used by
// first run ONLY: the app itself stays on `Theme.bg`. Every literal below goes
// through `themed(_:_:)` so a dark phone gets a dark first run rather than a
// cream page glowing at midnight.

// MARK: - Tokens

// `OnboardTheme` — every colour first run may name — lives in Theme.swift
// beside the app's other roles, where run_theme_contract_tests.sh allows a
// literal. Nothing in this file names a hex value.

enum OnboardFont {
    /// The question. Scaled with Dynamic Type off `.title1`.
    static func question(_ size: CGFloat = 30) -> Font {
        .system(size: UIFontMetrics(forTextStyle: .title1).scaledValue(for: size),
                weight: .semibold)
    }
    static let body = Font.system(size: 17)
    static let helper = Font.system(size: 15)
    static let field = Font.system(size: 17, weight: .medium)
    static let label = Font.system(size: 13, weight: .medium)
    static let pill = Font.system(size: 17, weight: .semibold)
}

enum OnboardMetric {
    static let gutter: CGFloat = 16
    static let pill: CGFloat = 50
    static let fab: CGFloat = 56
    static let fieldRadius: CGFloat = 14
    static let cardRadius: CGFloat = 16
    static let heroRadius: CGFloat = 28
    /// Room the scrolling body leaves for the footer that floats over it.
    static let footerClearance: CGFloat = 150
}

// MARK: - The mark, in any colour

/// `LogoMark` draws in `Theme.text` and `Theme.accent`. First run needs the
/// same proportions in white on the welcome and finale grounds, so the shape
/// is repeated here with its colours as parameters — never a second geometry.
struct OnboardMark: View {
    var size: CGFloat
    var stroke: Color = OnboardTheme.ink
    var dot: Color = OnboardTheme.dot

    var body: some View {
        let pillW = size * (11.0 / 32.0)
        let pillH = size * (26.0 / 32.0)
        ZStack {
            RoundedRectangle(cornerRadius: pillW / 2, style: .continuous)
                .strokeBorder(stroke, lineWidth: size * 0.07)
                .frame(width: pillW, height: pillH)
            Circle()
                .fill(dot)
                .frame(width: size * (3.6 / 32.0), height: size * (3.6 / 32.0))
                .offset(y: size * (4.0 / 32.0))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

// MARK: - Buttons

/// The pill. Black is the commit, white sits on imagery, soft is an in-card
/// action that hugs its words.
struct OnboardPillStyle: ButtonStyle {
    enum Kind { case black, white, soft }
    var kind: Kind
    var height: CGFloat = OnboardMetric.pill
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(kind == .soft ? .system(size: 15, weight: .semibold) : OnboardFont.pill)
            .lineLimit(1)
            .minimumScaleFactor(0.85)
            .foregroundStyle(foreground)
            .padding(.horizontal, kind == .soft ? 16 : 20)
            .frame(maxWidth: kind == .soft ? nil : .infinity)
            .frame(height: kind == .soft ? 40 : height)
            .background(Capsule().fill(background))
            .opacity(isEnabled ? 1 : 0.55)
            .scaleEffect(configuration.isPressed ? 0.975 : 1)
            .animation(Theme.spring, value: configuration.isPressed)
            .animation(Theme.spring, value: isEnabled)
            .contentShape(Capsule())
    }

    private var foreground: Color {
        switch kind {
        case .black: return OnboardTheme.onInk
        case .white: return OnboardTheme.inkFixed
        case .soft: return OnboardTheme.ink
        }
    }

    private var background: Color {
        switch kind {
        case .black: return OnboardTheme.ink
        case .white: return .white
        case .soft: return OnboardTheme.track
        }
    }
}

extension ButtonStyle where Self == OnboardPillStyle {
    static var onboardBlack: OnboardPillStyle { OnboardPillStyle(kind: .black) }
    static var onboardWhite: OnboardPillStyle { OnboardPillStyle(kind: .white) }
    static var onboardSoft: OnboardPillStyle { OnboardPillStyle(kind: .soft) }
}

/// A press that only scales — for the circular arrow and the pager dots.
struct OnboardPressStyle: ButtonStyle {
    var scale: CGFloat = 0.94
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? scale : 1)
            .animation(Theme.spring, value: configuration.isPressed)
    }
}

/// The circular arrow: ink when it can be tapped, the track colour when it
/// cannot. The back arrow sits on the field colour so the eye reads it as
/// secondary.
struct OnboardFAB: View {
    enum Direction { case forward, back }
    var direction: Direction = .forward
    var enabled: Bool = true
    var label: String
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: direction == .forward ? "arrow.right" : "arrow.left")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(glyph)
                .frame(width: OnboardMetric.fab, height: OnboardMetric.fab)
                .background(Circle().fill(fill))
                .shadow(color: shadow, radius: 12, y: 6)
                .contentShape(Circle())
        }
        .buttonStyle(OnboardPressStyle())
        .disabled(!enabled)
        .accessibilityLabel(label)
        .animation(Theme.spring, value: enabled)
    }

    private var fill: Color {
        switch direction {
        case .forward: return enabled ? OnboardTheme.ink : OnboardTheme.track
        case .back: return OnboardTheme.field
        }
    }
    private var glyph: Color {
        switch direction {
        case .forward: return enabled ? OnboardTheme.onInk : OnboardTheme.muted
        case .back: return OnboardTheme.ink
        }
    }
    private var shadow: Color {
        direction == .forward && enabled ? OnboardTheme.inkFixed.opacity(0.18) : .clear
    }
}

/// Reserves the FAB's footprint so a footer without a back arrow keeps its
/// arrow in the same place as one with it.
struct OnboardFABSpacer: View {
    var body: some View { Color.clear.frame(width: OnboardMetric.fab, height: OnboardMetric.fab) }
}

// MARK: - Stepper chrome

/// The mark, centred, over a thin progress bar. `progress` nil keeps the bar's
/// space and hides it — the sign-in screens share the header without counting.
struct StepperHeader: View {
    var progress: Double?
    var spokenLabel: String = ""

    var body: some View {
        VStack(spacing: 26) {
            OnboardMark(size: 40)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(OnboardTheme.track)
                    Capsule()
                        .fill(OnboardTheme.champagne)
                        .frame(width: max(0, geo.size.width * CGFloat(progress ?? 0)))
                }
            }
            .frame(height: 4)
            .opacity(progress == nil ? 0 : 1)
            .animation(Theme.springSlow, value: progress)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(spokenLabel)
            .accessibilityHidden(progress == nil)
        }
        .padding(.horizontal, OnboardMetric.gutter)
        .padding(.top, 6)
    }
}

/// The floating footer: a soft fade up from the ground so scrolled content
/// never reads through the controls. Callers lay out their own row inside.
struct OnboardFooter<Content: View>: View {
    @ViewBuilder var content: Content

    var body: some View {
        content
            .padding(.horizontal, OnboardMetric.gutter)
            .padding(.top, 28)
            .padding(.bottom, 18)
            .frame(maxWidth: .infinity)
            .background(
                LinearGradient(colors: [OnboardTheme.ground.opacity(0), OnboardTheme.ground],
                               startPoint: .top, endPoint: UnitPoint(x: 0.5, y: 0.38))
                    .allowsHitTesting(false)
            )
    }
}

// MARK: - Fields

/// One soft filled box: a small label that appears once there is something in
/// it, the value in medium weight, a champagne border while it has focus. The
/// label's row is reserved so the box never jumps on the first keystroke.
struct QuestionField<Tag: Hashable>: View {
    enum Kind { case email, password, newPassword, phone, givenName, plain }

    let label: String
    @Binding var text: String
    var placeholder: String
    var kind: Kind = .plain
    var focus: FocusState<Tag?>.Binding
    let tag: Tag
    var submit: SubmitLabel = .next
    var onSubmit: () -> Void = {}

    private var isFocused: Bool { focus.wrappedValue == tag }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(OnboardFont.label)
                .foregroundStyle(OnboardTheme.muted)
                .frame(height: 17)
                .opacity(text.isEmpty ? 0 : 1)
            Group {
                if kind == .password || kind == .newPassword {
                    SecureField("", text: $text,
                                prompt: Text(placeholder).foregroundColor(OnboardTheme.muted))
                        .textContentType(kind == .newPassword ? .newPassword : .password)
                } else {
                    TextField("", text: $text,
                              prompt: Text(placeholder).foregroundColor(OnboardTheme.muted))
                        .textContentType(contentType)
                        .keyboardType(keyboard)
                        .textInputAutocapitalization(kind == .givenName ? .words : .never)
                        .autocorrectionDisabled()
                }
            }
            .font(OnboardFont.field)
            .foregroundStyle(OnboardTheme.ink)
            .focused(focus, equals: tag)
            .submitLabel(submit)
            .onSubmit(onSubmit)
            .frame(height: 24)
            .accessibilityLabel(label)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
        .frame(maxWidth: .infinity, minHeight: 62, alignment: .leading)
        // The tap lives on the background, not over the field, so the text
        // field keeps its own caret placement and selection gestures.
        .background(
            RoundedRectangle(cornerRadius: OnboardMetric.fieldRadius, style: .continuous)
                .fill(isFocused ? OnboardTheme.card : OnboardTheme.field)
                .contentShape(Rectangle())
                .onTapGesture { focus.wrappedValue = tag }
        )
        .overlay(
            RoundedRectangle(cornerRadius: OnboardMetric.fieldRadius, style: .continuous)
                .strokeBorder(isFocused ? OnboardTheme.champagne : .clear, lineWidth: 1.5)
                .allowsHitTesting(false)
        )
        .animation(Theme.spring, value: isFocused)
        .animation(Theme.spring, value: text.isEmpty)
    }

    private var contentType: UITextContentType? {
        switch kind {
        case .email: return .emailAddress
        case .phone: return .telephoneNumber
        case .givenName: return .givenName
        default: return nil
        }
    }

    private var keyboard: UIKeyboardType {
        switch kind {
        case .email: return .emailAddress
        case .phone: return .phonePad
        default: return .default
        }
    }
}

/// The grey line under a field. Turns champagne when what it asks for is
/// satisfied, with a light tap in the hand — the reward the old rule list gave,
/// without the ring and tick.
struct OnboardHelper: View {
    var text: String
    var satisfied: Bool = false
    var lock: Bool = false

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            if lock {
                Image(systemName: "lock")
                    .font(.system(size: 13, weight: .medium))
                    .padding(.top, 2)
                    .accessibilityHidden(true)
            }
            Text(text)
                .font(OnboardFont.helper)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(satisfied ? OnboardTheme.champagneInk : OnboardTheme.muted)
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(Theme.spring, value: satisfied)
        .onChange(of: satisfied) { ok in
            if ok { Haptics.tap() }
        }
    }
}

/// A failure, said plainly in the alarm colour under the field it is about.
struct OnboardProblem: View {
    var text: String
    var body: some View {
        Text(text)
            .font(OnboardFont.helper)
            .lineSpacing(3)
            .foregroundStyle(Theme.alarm)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .transition(.opacity.combined(with: .move(edge: .top)))
    }
}

/// A busy line: a small spinner and the words the button would say.
struct OnboardStatus: View {
    var text: String
    var body: some View {
        HStack(spacing: 8) {
            ProgressView()
                .progressViewStyle(.circular)
                .tint(OnboardTheme.champagne)
                .scaleEffect(0.8)
            Text(text)
                .font(OnboardFont.helper.weight(.medium))
                .foregroundStyle(OnboardTheme.champagneInk)
        }
        .transition(.opacity)
    }
}

/// A keyboard that has no return key — the phone pad — gets its commit on a
/// bar above it instead, so nobody has to reach past the keyboard to finish.
struct PhonePadDoneBar: ToolbarContent {
    var label: String
    var enabled: Bool
    var action: () -> Void

    var body: some ToolbarContent {
        ToolbarItemGroup(placement: .keyboard) {
            Spacer()
            Button(label, action: action)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(OnboardTheme.ink)
                .disabled(!enabled)
        }
    }
}

/// The dialling code, chosen from a menu: flag, code, chevron. The country is
/// in front of the person rather than assumed behind them — `e164` refuses a
/// bare ten digits, and a guessed country wrote a US number onto a London
/// stranger's account once. Every code `DiallingCode` knows is reachable; the
/// commonest sit first.
struct CountryCodeBox: View {
    @Binding var code: String

    private static let common = ["US", "CA", "GB", "MX", "AU", "DE", "FR", "ES", "IN", "BR"]

    private static let everyRegion: [(id: String, name: String)] = DiallingCode.regions
        .map { ($0, Locale.current.localizedString(forRegionCode: $0) ?? $0) }
        .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }

    @State private var region: String = Locale.current.region?.identifier ?? "US"

    var body: some View {
        Menu {
            Section {
                ForEach(Self.common, id: \.self) { id in entry(id) }
            }
            Section("Every country") {
                ForEach(Self.everyRegion, id: \.id) { r in entry(r.id) }
            }
        } label: {
            HStack(spacing: 6) {
                Text(Self.flag(region)).font(.system(size: 20))
                Text(code.isEmpty ? "+" : code)
                    .font(.system(size: 17, weight: .semibold))
                Image(systemName: "chevron.down")
                    .font(.system(size: 12, weight: .bold))
            }
            .foregroundStyle(OnboardTheme.ink)
            .frame(width: 96, height: 62)
            .background(
                RoundedRectangle(cornerRadius: OnboardMetric.fieldRadius, style: .continuous)
                    .fill(OnboardTheme.field)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel("Country code, \(code)")
        .onAppear {
            // Seed the flag from the code already in the box when it came from
            // the phone's own region rather than from this menu.
            if let match = Self.everyRegion.first(where: { Self.code(for: $0.id) == code }) {
                region = match.id
            }
        }
    }

    private func entry(_ id: String) -> some View {
        Button {
            region = id
            code = Self.code(for: id)
            Haptics.tap()
        } label: {
            Text("\(Self.flag(id))  \(Locale.current.localizedString(forRegionCode: id) ?? id)  \(Self.code(for: id))")
        }
    }

    private static func code(for region: String) -> String {
        (DiallingCode.forRegion(region) ?? "+").trimmingCharacters(in: .whitespaces)
    }

    static func flag(_ region: String) -> String {
        region.uppercased().unicodeScalars
            .compactMap { UnicodeScalar(127397 + $0.value) }
            .map { String($0) }
            .joined()
    }
}

/// Six boxes for a code that arrives by text. One real text field takes the
/// typing — and iOS's own "from Messages" autofill — while the boxes draw what
/// it holds. Tapping anywhere on the row puts the cursor in it.
struct OTPBoxes: View {
    @Binding var code: String
    @FocusState private var focused: Bool

    var body: some View {
        ZStack {
            TextField("", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .focused($focused)
                .frame(width: 1, height: 1)
                .opacity(0.02)
                .accessibilityLabel("6-digit code")
            HStack(spacing: 10) {
                ForEach(0 ..< 6, id: \.self) { i in
                    box(i)
                }
            }
        }
        .contentShape(Rectangle())
        .onTapGesture { focused = true }
        .onChange(of: code) { value in
            let digits = String(value.filter(\.isNumber).prefix(6))
            if digits != value { code = digits }
        }
        .onAppear { focused = true }
    }

    private func box(_ i: Int) -> some View {
        let chars = Array(code)
        let live = focused && i == min(chars.count, 5)
        return Text(i < chars.count ? String(chars[i]) : "")
            .font(.system(size: 22, weight: .semibold).monospacedDigit())
            .foregroundStyle(OnboardTheme.ink)
            .frame(maxWidth: .infinity)
            .frame(height: 57)
            .background(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .fill(OnboardTheme.card)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 13, style: .continuous)
                    .strokeBorder(live ? OnboardTheme.ink : .clear, lineWidth: 1.5)
            )
            .animation(Theme.spring, value: live)
            .accessibilityHidden(true)
    }
}

// MARK: - Cards

/// The white card one step off the ground: permissions, computer setup.
struct OnboardCard<Content: View>: View {
    var fill: Color = OnboardTheme.card
    @ViewBuilder var content: Content
    var body: some View {
        content
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: OnboardMetric.cardRadius, style: .continuous)
                    .fill(fill)
            )
    }
}

/// Icon, title, her sentence — and whatever sits at the trailing edge: a
/// switch, a status word, or nothing. The sentence arrives as a `Text` so a
/// phrase inside it can carry weight ("let them know").
struct PermissionCard<Accessory: View>: View {
    var icon: String
    var title: String
    var text: Text
    @ViewBuilder var accessory: Accessory

    var body: some View {
        OnboardCard {
            HStack(alignment: .center, spacing: 14) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 10) {
                        Image(systemName: icon)
                            .font(.system(size: 19, weight: .medium))
                            .foregroundStyle(OnboardTheme.ink)
                            .frame(width: 24)
                            .accessibilityHidden(true)
                        Text(title)
                            .font(.system(size: 19, weight: .semibold))
                            .foregroundStyle(OnboardTheme.ink)
                    }
                    text
                        .font(.system(size: 15.5))
                        .lineSpacing(3)
                        .foregroundStyle(OnboardTheme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                accessory
            }
        }
    }
}

/// The switch on a permission card: the design's own 51×31 capsule, track
/// colour off and ink on, a white knob that slides on the app's spring. A
/// `ToggleStyle`, so the native control's accessibility stays intact.
struct OnboardToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            Haptics.tap()
            configuration.isOn.toggle()
        } label: {
            ZStack(alignment: configuration.isOn ? .trailing : .leading) {
                Capsule()
                    .fill(configuration.isOn ? OnboardTheme.ink : OnboardTheme.track)
                Circle()
                    .fill(.white)
                    .frame(width: 27, height: 27)
                    .shadow(color: .black.opacity(0.15), radius: 3, y: 2)
                    .padding(2)
            }
            .frame(width: 51, height: 31)
            .animation(Theme.spring, value: configuration.isOn)
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityValue(configuration.isOn ? "On" : "Off")
    }
}

struct OnboardToggle: View {
    var label: String
    @Binding var isOn: Bool
    var body: some View {
        Toggle(label, isOn: $isOn)
            .toggleStyle(OnboardToggleStyle())
            .labelsHidden()
            .accessibilityLabel(label)
    }
}

// MARK: - Pager dots

/// Dots under a set of pages. The tour's active dot stretches into a pill; the
/// tips' active dot grows into a larger circle.
struct PagerDots: View {
    var count: Int
    var index: Int
    var stretches: Bool = true
    var onSelect: ((Int) -> Void)? = nil

    var body: some View {
        HStack(spacing: stretches ? 6 : 7) {
            ForEach(0 ..< count, id: \.self) { i in
                Button {
                    onSelect?(i)
                } label: {
                    Capsule()
                        .fill(i == index ? OnboardTheme.champagne : OnboardTheme.dotIdle)
                        .frame(width: width(i), height: i == index && !stretches ? 8 : 6)
                }
                .buttonStyle(OnboardPressStyle(scale: 0.9))
                .disabled(onSelect == nil)
                .accessibilityLabel("Page \(i + 1) of \(count)")
                .accessibilityAddTraits(i == index ? .isSelected : [])
            }
        }
        .animation(Theme.spring, value: index)
    }

    private func width(_ i: Int) -> CGFloat {
        guard i == index else { return 6 }
        return stretches ? 19 : 8
    }
}

// MARK: - Coach mark

/// A rounded ink bubble with a pointer under it, over the control it names.
struct CoachMark: View {
    var text: String
    var body: some View {
        Text(text)
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(.white)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .frame(maxWidth: .infinity)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(OnboardTheme.phoneShell)
            )
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(OnboardTheme.phoneShell)
                    .frame(width: 14, height: 14)
                    .rotationEffect(.degrees(45))
                    .offset(y: 7)
                    .accessibilityHidden(true)
            }
    }
}

// MARK: - The welcome ground

/// Warm evening light for the welcome: a dusk gradient, three slow pools of
/// light, the app's own grain, and a veil at the foot so the pills read. Only
/// the pools sit inside the clock; everything static is drawn once. Time
/// drives the drift rather than a repeat-forever transaction — see `WaveBars`
/// for why a forever animation may never touch layout in this app.
struct WelcomeAtmosphere: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @AppStorage(AppPreferences.ambientMotionKey) private var ambientMotion = true

    var body: some View {
        ZStack {
            LinearGradient(colors: OnboardTheme.Welcome.sky,
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(colors: [OnboardTheme.Welcome.glowWarm.opacity(0.62), .clear],
                           center: UnitPoint(x: 0.28, y: 0.18), startRadius: 0, endRadius: 280)
            RadialGradient(colors: [OnboardTheme.Welcome.glowEmber.opacity(0.50), .clear],
                           center: UnitPoint(x: 0.78, y: 0.62), startRadius: 0, endRadius: 260)
            RadialGradient(colors: [OnboardTheme.Welcome.glowPale.opacity(0.30), .clear],
                           center: UnitPoint(x: 0.58, y: 0.38), startRadius: 0, endRadius: 200)
            RadialGradient(colors: [OnboardTheme.Welcome.glowDeep.opacity(0.55), .clear],
                           center: UnitPoint(x: 0.20, y: 0.85), startRadius: 0, endRadius: 280)
            TimelineView(.animation(minimumInterval: 1.0 / 20.0,
                                    paused: reduceMotion || !ambientMotion)) { tick in
                let t = tick.date.timeIntervalSinceReferenceDate
                ZStack {
                    pool(OnboardTheme.Welcome.poolAmber.opacity(0.55), size: 180,
                         x: -150 + 18 * drift(t, 0), y: -230 - 22 * drift(t, 0))
                    pool(OnboardTheme.Welcome.poolCream.opacity(0.50), size: 120,
                         x: 150 + 14 * drift(t, 4), y: -110 - 16 * drift(t, 4))
                    pool(OnboardTheme.Welcome.poolEmber.opacity(0.45), size: 220,
                         x: 40 + 18 * drift(t, 8), y: 200 - 22 * drift(t, 8))
                }
            }
            GrainLayer()
            LinearGradient(colors: [Color.black.opacity(0.10), .clear, .clear, OnboardTheme.Welcome.veil.opacity(0.72)],
                           startPoint: .top, endPoint: .bottom)
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }

    /// A soft pool of light drawn as a radial falloff — the look of a blur
    /// without filtering three moving layers twenty times a second.
    private func pool(_ color: Color, size: CGFloat, x: CGFloat, y: CGFloat) -> some View {
        Circle()
            .fill(RadialGradient(colors: [color, color.opacity(0)],
                                 center: .center, startRadius: 0, endRadius: size * 0.65))
            .frame(width: size * 1.3, height: size * 1.3)
            .offset(x: x, y: y)
    }

    /// A slow breath in and out over fourteen seconds, phase-shifted per pool.
    private func drift(_ t: TimeInterval, _ shift: Double) -> CGFloat {
        CGFloat((sin(((t + shift) / 14.0) * 2 * .pi) + 1) / 2)
    }
}

// MARK: - Tour heroes

/// A white capsule that floats over a hero card's edge: an icon in champagne
/// and two words.
struct FloatingChip: View {
    var icon: String
    var text: String
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(OnboardTheme.champagneInk)
            Text(text)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(OnboardTheme.inkFixed)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .background(Capsule().fill(Color.white.opacity(0.94)))
        .shadow(color: OnboardTheme.inkFixed.opacity(0.14), radius: 12, y: 8)
        .accessibilityElement(children: .combine)
    }
}

/// Reveals its content a beat after the page lands: a short rise, on the
/// app's spring, once. A page swiped away mid-reveal cancels the reveal
/// rather than popping in later.
struct RiseIn<Content: View>: View {
    var delay: Double = 0
    var on: Bool
    @ViewBuilder var content: Content
    @State private var shown = false
    @State private var pending: Task<Void, Never>?

    var body: some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown ? 0 : 14)
            .onChange(of: on) { live in
                if live { reveal() } else { pending?.cancel() }
            }
            .onAppear { if on { reveal() } }
            .onDisappear { pending?.cancel() }
    }

    private func reveal() {
        pending?.cancel()
        pending = Task { @MainActor in
            shown = false
            try? await Task.sleep(nanoseconds: UInt64(max(0, delay) * 1_000_000_000))
            guard !Task.isCancelled else { return }
            withAnimation(Theme.spring) { shown = true }
        }
    }
}

/// The frame every tour scene sits in: 314×370, a large radius, a soft lift.
struct HeroFrame<Scene: View>: View {
    @ViewBuilder var scene: Scene
    var body: some View {
        scene
            .frame(width: 314, height: 370)
            .clipShape(RoundedRectangle(cornerRadius: OnboardMetric.heroRadius, style: .continuous))
            .shadow(color: OnboardTheme.inkFixed.opacity(0.12), radius: 20, y: 20)
    }
}

/// Bars breathing on the app's harmonic, in whatever colour the scene asks
/// for. Time-driven, like `WaveBars`.
struct HeroWave: View {
    var color: Color
    var barWidth: CGFloat = 4
    var height: CGFloat = 30
    var bars: Int = 7
    var gap: CGFloat? = nil
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: reduceMotion)) { tick in
            let t = tick.date.timeIntervalSinceReferenceDate
            HStack(spacing: gap ?? barWidth + 1) {
                ForEach(0 ..< bars, id: \.self) { i in
                    Capsule()
                        .fill(color)
                        .frame(width: barWidth,
                               height: reduceMotion ? height * 0.5
                                   : 8 + (height - 8) * CGFloat((sin((t * 5.7) + Double(i) * 0.9) + 1) / 2))
                }
            }
            .frame(height: height)
        }
        .accessibilityHidden(true)
    }
}

/// Scene one: a dark room, two lines heard, one caught.
struct TourTranscriptHero: View {
    var on: Bool
    var body: some View {
        ZStack {
            HeroFrame {
                ZStack(alignment: .top) {
                    LinearGradient(colors: OnboardTheme.Hero.transcriptSky,
                                   startPoint: .topLeading, endPoint: .bottomTrailing)
                    VStack(spacing: 10) {
                        HeroWave(color: OnboardTheme.Hero.wave.opacity(0.9))
                            .padding(.top, 44)
                            .padding(.bottom, 20)
                        heardLine("\u{201C}\u{2026}and I'll get you the deck by Friday.\u{201D}", dim: false)
                        heardLine("\u{201C}Can you book Thursday with Marcus?\u{201D}", dim: true)
                    }
                    .padding(.horizontal, 22)
                }
                .overlay(alignment: .bottom) {
                    RiseIn(delay: 0.15, on: on) {
                        VStack(spacing: 2) {
                            Text("Heard just now")
                                .font(.system(size: 15, weight: .medium))
                                .foregroundStyle(OnboardTheme.muted)
                            Text("\u{201C}the deck by Friday\u{201D}")
                                .font(.system(size: 19, weight: .semibold))
                                .foregroundStyle(OnboardTheme.inkFixed)
                        }
                        .padding(.vertical, 15)
                        .frame(maxWidth: .infinity)
                        .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(.white))
                        .shadow(color: OnboardTheme.inkFixed.opacity(0.18), radius: 14, y: 12)
                        .padding(.horizontal, 34)
                        .padding(.bottom, 24)
                    }
                }
            }
            RiseIn(delay: 0.1, on: on) {
                FloatingChip(icon: "mic", text: "Listening")
            }
            .offset(x: -157 + 62, y: -185 + 44)
            RiseIn(delay: 0.3, on: on) {
                FloatingChip(icon: "iphone", text: "On your phone")
            }
            .offset(x: 157 - 74, y: -185 + 234)
        }
        .frame(width: 314, height: 370)
    }

    private func heardLine(_ text: String, dim: Bool) -> some View {
        Text(text)
            .font(.system(size: 14))
            .lineSpacing(2)
            .foregroundStyle(OnboardTheme.Hero.chipText.opacity(dim ? 0.65 : 0.92))
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Color.white.opacity(0.10)))
    }
}

/// Scene two: four things she is keeping, on warm paper.
struct TourCommitmentsHero: View {
    var on: Bool

    private let rows: [(icon: String, title: String, when: String)] = [
        ("doc.text", "Send the deck", "Friday"),
        ("phone", "Call Priya back", "Today"),
        ("calendar", "Thursday \u{00B7} Marcus", "2:00 pm"),
        ("questionmark.circle", "Budget", "still open"),
    ]

    var body: some View {
        ZStack {
            HeroFrame {
                ZStack(alignment: .top) {
                    LinearGradient(colors: OnboardTheme.Hero.commitmentsSky,
                                   startPoint: .topLeading, endPoint: .bottomTrailing)
                    RadialGradient(colors: [Color.white.opacity(0.55), .clear],
                                   center: UnitPoint(x: 0.5, y: 0.45), startRadius: 0, endRadius: 170)
                    VStack(spacing: 10) {
                        ForEach(rows.indices, id: \.self) { i in
                            RiseIn(delay: 0.05 + Double(i) * 0.1, on: on) {
                                HStack(spacing: 10) {
                                    Image(systemName: rows[i].icon)
                                        .font(.system(size: 17, weight: .medium))
                                        .foregroundStyle(OnboardTheme.champagneInk)
                                        .frame(width: 22)
                                    Text(rows[i].title)
                                        .font(.system(size: 15, weight: .semibold))
                                        .foregroundStyle(OnboardTheme.inkFixed)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.85)
                                    Spacer(minLength: 8)
                                    Text(rows[i].when)
                                        .font(.system(size: 13, weight: .medium))
                                        .foregroundStyle(OnboardTheme.muted)
                                }
                                .padding(.horizontal, 14)
                                .padding(.vertical, 12)
                                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(.white))
                                .shadow(color: OnboardTheme.Hero.commitmentsShadow.opacity(0.12), radius: 8, y: 6)
                            }
                        }
                    }
                    .padding(.horizontal, 22)
                    .padding(.top, 54)
                }
            }
            RiseIn(delay: 0.2, on: on) {
                FloatingChip(icon: "checkmark", text: "4 commitments")
            }
            .offset(x: -157 + 66, y: 185 - 86)
            RiseIn(delay: 0.4, on: on) {
                FloatingChip(icon: "clock", text: "From today's calls")
            }
            .offset(x: 157 - 92, y: 185 - 42)
        }
        .frame(width: 314, height: 370)
    }
}

/// Scene three: a lock screen rising into the frame, and her one notification
/// over it. The phone fades out through the foot of the card so it reads as a
/// device, not a picture of one.
struct TourNotificationHero: View {
    var on: Bool

    var body: some View {
        ZStack(alignment: .top) {
            VStack(spacing: 0) {
                RoundedRectangle(cornerRadius: 32, style: .continuous)
                    .fill(LinearGradient(colors: OnboardTheme.Hero.notificationSky,
                                         startPoint: .top, endPoint: .bottom))
                    .overlay(alignment: .top) {
                        VStack(spacing: 6) {
                            Capsule().fill(OnboardTheme.Hero.phoneBlack).frame(width: 74, height: 20).padding(.top, 8)
                            Text("Monday, September 16")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(.white.opacity(0.95))
                                .padding(.top, 14)
                            Text("9:41")
                                .font(.system(size: 56, weight: .semibold))
                                .tracking(-1)
                                .foregroundStyle(.white)
                        }
                    }
                    .padding(9)
                    .background(
                        UnevenRoundedTop(radius: 40).fill(OnboardTheme.Hero.phoneBlack)
                    )
                    .frame(width: 257, height: 420)
                Spacer(minLength: 0)
            }
            // The mask belongs to the CARD's box, so the phone is gone by the
            // card's foot rather than fading on past it into the headline.
            .frame(width: 314, height: 370, alignment: .top)
            .clipped()
            .mask(
                LinearGradient(stops: [.init(color: .black, location: 0.0),
                                       .init(color: .black, location: 0.68),
                                       .init(color: .clear, location: 1.0)],
                               startPoint: .top, endPoint: .bottom)
            )
            RiseIn(delay: 0.2, on: on) {
                HStack(alignment: .top, spacing: 12) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 11, style: .continuous)
                            .fill(OnboardTheme.Hero.phoneScreen)
                            .frame(width: 40, height: 40)
                        OnboardMark(size: 28, stroke: OnboardTheme.inkFixed, dot: OnboardTheme.dot)
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text("The deck for Priya is ready")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(OnboardTheme.inkFixed)
                        Text("Anticipy asks before anything is sent. Want me to send it?")
                            .font(.system(size: 14))
                            .lineSpacing(2)
                            .foregroundStyle(OnboardTheme.Hero.phoneText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 4)
                    Text("now")
                        .font(.system(size: 12))
                        .foregroundStyle(OnboardTheme.muted)
                        .padding(.top, 2)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 14)
                .frame(width: 366)
                .background(RoundedRectangle(cornerRadius: 22, style: .continuous).fill(.white))
                .shadow(color: OnboardTheme.inkFixed.opacity(0.22), radius: 18, y: 14)
            }
            .padding(.top, 178)
        }
        .frame(width: 314, height: 370)
    }
}

/// A rectangle whose top corners are rounded and whose bottom runs off the
/// frame — the phone's bezel, which exits through the fade.
private struct UnevenRoundedTop: Shape {
    var radius: CGFloat
    func path(in rect: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: rect.minX, y: rect.maxY))
        p.addLine(to: CGPoint(x: rect.minX, y: rect.minY + radius))
        p.addQuadCurve(to: CGPoint(x: rect.minX + radius, y: rect.minY),
                       control: CGPoint(x: rect.minX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.maxX - radius, y: rect.minY))
        p.addQuadCurve(to: CGPoint(x: rect.maxX, y: rect.minY + radius),
                       control: CGPoint(x: rect.maxX, y: rect.minY))
        p.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY))
        p.closeSubpath()
        return p
    }
}

// MARK: - The mark as texture

/// Three of the mark, translucent and enormous, bleeding off every edge of the
/// finale. Positioned by their centres, off the middle of a 390×844 screen.
struct GiantMarks: View {
    var color: Color = .white.opacity(0.16)
    var body: some View {
        ZStack {
            OnboardMark(size: 560, stroke: color, dot: color)
                .rotationEffect(.degrees(-22))
                .offset(x: -125, y: -312)
            OnboardMark(size: 680, stroke: color, dot: color)
                .rotationEffect(.degrees(24))
                .offset(x: 185, y: 158)
            OnboardMark(size: 520, stroke: color, dot: color)
                .rotationEffect(.degrees(-32))
                .offset(x: -85, y: 392)
        }
        .frame(width: 0, height: 0)   // draws outside its own box, never sizes a parent
        .accessibilityHidden(true)
        .allowsHitTesting(false)
    }
}

/// The mark tiled faintly across a surface, slightly rotated — the texture
/// behind a tip card's scene. Fills whatever it is given and never sizes it.
struct MarkPattern: View {
    var color: Color = OnboardTheme.ink.opacity(0.07)
    var pitch: CGFloat = 60
    var body: some View {
        GeometryReader { geo in
            let cols = Int(geo.size.width / pitch) + 6
            let rows = Int(geo.size.height / pitch) + 6
            ZStack {
                ForEach(0 ..< rows, id: \.self) { r in
                    ForEach(0 ..< cols, id: \.self) { c in
                        OnboardMark(size: 32, stroke: color, dot: color)
                            .position(x: CGFloat(c) * pitch - 2 * pitch,
                                      y: CGFloat(r) * pitch - 2 * pitch)
                    }
                }
            }
            .rotationEffect(.degrees(-14))
            .scaleEffect(1.3)
        }
        .clipped()
        .accessibilityHidden(true)
        .allowsHitTesting(false)
    }
}
