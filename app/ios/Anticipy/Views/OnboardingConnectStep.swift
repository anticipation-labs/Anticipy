import SwiftUI

/// ONBOARDING STEP 2 — "Which apps do you live in?"
///
/// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
/// 2026-09-05, page 25. It comes after the number and the pendant, and it is
/// the first time this product asks the owner for anything belonging to another
/// company. Four things have to be true of it at once, and all four are
/// decisions rather than pixels, which is why none of them are made here:
///
///   * the apps we already have evidence for arrive PRE-SELECTED, from the
///     signals table and the catalog — `ConnectOnboardingPolicy.detected`;
///   * a search box finds anything else, and it JUDGES NOTHING — the typed
///     words cross `OnboardingCatalogSearch` unread and what comes back is
///     shown in the order it came back;
///   * ONE Connect button, live only when something is ticked;
///   * SKIP IS ALWAYS VISIBLE, and a skip is a seven-day soft snooze rather
///     than a refusal of the apps.
///
/// ── WHAT THIS FILE IS NOT ────────────────────────────────────────────────
///
/// It draws and it forwards taps. Every sentence on the screen comes from
/// `ConnectOnboardingPolicy.Copy`, every row from `Step.apps`, every search
/// state from `searchState`, and the runner
/// (`Tests/run_connect_onboarding_tests.sh`, legs 3 and 6) fails if a sentence
/// or an app name appears in this source at all. Copy is a decision: written
/// here, it would sit where the forbidden-word gate — the one that keeps the
/// owner from ever hearing "authorize", "permissions" or the provider's name —
/// cannot read it.
///
/// ── SKIP ─────────────────────────────────────────────────────────────────
///
/// It is a plain, unconditional control at the bottom of every state this
/// screen can be in, including the state where detection refused. A person in
/// setup has no account to go back to and nothing else on screen; a way out
/// behind an `if` is a trap one condition away from existing, so the runner
/// reads this source and fails on a branch in front of it.
///
/// ── THE WRONG PERSON ─────────────────────────────────────────────────────
///
/// `owner` is the signed-in owner's ROW id, resolved by the caller and passed
/// in as `ConnectOnboardingPolicy.OwnerID`, which cannot be constructed from a
/// name or an email. It is handed to the catalog on every search for the same
/// reason `ConnectedAppsStore` takes one: a call that does not carry an owner
/// is a call somebody can make while signed out, and there is no such call in
/// this feature. With no owner the search does not run at all.
struct OnboardingConnectStep: View {

    /// What the signals table and the catalog produced, already decided. A
    /// refusal is passed in as a refusal — the card renders it as a card with
    /// no rows, not as a spinner that never ends.
    let detection: ConnectOnboardingPolicy.Detection

    /// The signed-in owner's row id. `nil` means nobody is signed in, and the
    /// search box does not reach the catalog at all.
    let owner: ConnectOnboardingPolicy.OwnerID?

    /// The seam. The typed words go over it unread; see the Law-1 note on
    /// `ConnectOnboardingPolicy.searchState`.
    let catalog: any OnboardingCatalogSearch

    /// What the owner ticked, handed over on one tap of one button. Minting
    /// links, opening them and writing rows are the connect flow's job, not
    /// this screen's, so they are injected and this file cannot grow a second
    /// quieter way of doing them.
    let connectThese: ([ConnectOnboardingPolicy.AppKey]) -> Void

    /// A seven-day soft snooze, not a decline. What that means is
    /// `ConnectOnboardingPolicy.skipOutcome`'s decision, not this button's.
    let skipForNow: () -> Void

    @State private var typed: String = String()
    @State private var answer: ConnectOnboardingPolicy.CatalogAnswer?
    @State private var found: [ConnectOnboardingPolicy.CatalogEntry] = []
    @State private var chosen: Set<ConnectOnboardingPolicy.AppKey> = []
    /// The pre-selection is seeded ONCE. Re-seeding on every redraw would put
    /// back ticks the owner had just taken off, which reads as the screen
    /// arguing with them.
    @State private var seeded = false

    private var step: ConnectOnboardingPolicy.Step {
        ConnectOnboardingPolicy.step(for: detection, found: found, chosen: chosen)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                heading
                appRows
                searchArea
            }
            .padding(20)
        }
        .safeAreaInset(edge: .bottom) { footer }
        .task { seedSelection() }
        .task(id: typed) { await askTheCatalog() }
    }

    // MARK: - The card

    private var heading: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(step.title)
                .font(.title2.weight(.semibold))
            Text(step.subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            // Detection refused. The person is told the true and useful half;
            // the diagnostic half (`Refusal.sentence`) belongs in the journal,
            // where somebody can act on it.
            if step.refusal != nil {
                Text(ConnectOnboardingPolicy.Copy.detectionTrouble)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var appRows: some View {
        VStack(spacing: 0) {
            ForEach(step.apps, id: \.key) { app in
                Button {
                    toggle(app.key)
                } label: {
                    row(app, ticked: chosen.contains(app.key))
                }
                .buttonStyle(.plain)
                Divider()
            }
        }
    }

    private func row(_ app: ConnectOnboardingPolicy.DetectedApp, ticked: Bool) -> some View {
        HStack(spacing: 12) {
            logo(app.logo)
            // The ONLY place a name comes from is the catalog entry the policy
            // put on the row. A slug is never shown raw: the vendor's internal
            // spelling is not a name.
            Text(app.name)
                .font(.body)
            Spacer(minLength: 8)
            Image(systemName: ticked ? "checkmark.circle.fill" : "circle")
                .font(.title3)
                .foregroundStyle(ticked ? Color.accentColor : Color.secondary)
        }
        .contentShape(Rectangle())
        .padding(.vertical, 12)
    }

    private func logo(_ address: String?) -> some View {
        Group {
            if let address, let url = URL(string: address) {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    Color.clear
                }
            } else {
                // No logo in the catalog entry. A neutral placeholder, never a
                // guessed one: an icon chosen by us for somebody else's product
                // is a name in disguise.
                Image(systemName: "square.dashed")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 28, height: 28)
    }

    // MARK: - The search box

    private var searchArea: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.secondary)
                TextField(step.searchPlaceholder, text: $typed)
                    .textFieldStyle(.plain)
                    .autocorrectionDisabled()
            }
            .padding(12)
            .background(Color.secondary.opacity(0.12))
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            searchAnswer
        }
    }

    @ViewBuilder
    private var searchAnswer: some View {
        // WHAT IS SHOWN IS WHAT THE CATALOG ANSWERED. Nothing on this side
        // matches, ranks or corrects it, and the five states are five different
        // things to say: a person told "nothing matched" when the truth is that
        // a request failed gives up on a product that works.
        switch ConnectOnboardingPolicy.searchState(
            typed: typed,
            answer: answer,
            excluding: ConnectOnboardingPolicy.slugsOnCard(step.apps)) {
        case .searching(let said):
            HStack(spacing: 8) {
                ProgressView()
                Text(said)
            }
            .font(.footnote)
            .foregroundStyle(.secondary)
        case .idle(let said), .nothingFound(let said), .trouble(let said):
            Text(said)
                .font(.footnote)
                .foregroundStyle(.secondary)
        case .results(let rows):
            VStack(spacing: 0) {
                ForEach(rows, id: \.slug) { entry in
                    Button {
                        add(entry)
                    } label: {
                        HStack(spacing: 12) {
                            logo(entry.logo)
                            Text(entry.name)
                            Spacer(minLength: 8)
                            Image(systemName: "plus.circle")
                                .foregroundStyle(Color.accentColor)
                        }
                        .contentShape(Rectangle())
                        .padding(.vertical, 12)
                    }
                    .buttonStyle(.plain)
                    Divider()
                }
            }
        }
    }

    // MARK: - The two controls

    private var footer: some View {
        VStack(spacing: 12) {
            Button {
                connectThese(chosen.sorted { left, right in
                    left.toolkit == right.toolkit
                        ? (left.alias?.rawValue ?? String()) < (right.alias?.rawValue ?? String())
                        : left.toolkit < right.toolkit
                })
            } label: {
                Text(step.connectLabel)
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .disabled(!step.connectEnabled)

            Text(step.footnote)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button(step.skipLabel, action: skipForNow)
                .font(.body.weight(.medium))
        }
        .padding(20)
        .background(.bar)
    }

    // MARK: - Plumbing

    private func toggle(_ key: ConnectOnboardingPolicy.AppKey) {
        if chosen.contains(key) {
            chosen.remove(key)
        } else {
            chosen.insert(key)
        }
    }

    private func seedSelection() {
        guard !seeded else { return }
        seeded = true
        chosen = ConnectOnboardingPolicy.initialSelection(detection)
    }

    private func add(_ entry: ConnectOnboardingPolicy.CatalogEntry) {
        if !found.contains(where: { $0.slug == entry.slug }) {
            found.append(entry)
        }
        chosen.insert(ConnectOnboardingPolicy.chosenFromSearch(entry).key)
        // The box empties because the app they asked for is now a row above it.
        // Leaving the words in place would show the same hit twice: once as a
        // tick-box and once as a thing still to be added.
        typed.removeAll()
        answer = nil
    }

    @MainActor
    private func askTheCatalog() async {
        answer = nil
        guard let query = ConnectOnboardingPolicy.searchQuery(typed), let owner else { return }
        // A quarter of a second of quiet before asking. A request per keystroke
        // is the far end's problem and the owner's battery, and it also makes
        // the results flicker between four half-typed answers.
        try? await Task.sleep(nanoseconds: 250_000_000)
        if Task.isCancelled { return }
        do {
            let hits = try await catalog.catalog(matching: query, owner: owner)
            if Task.isCancelled { return }
            answer = .hits(hits)
        } catch {
            // NOT "nothing matched". The difference is the whole reason
            // `CatalogAnswer` has two cases.
            if Task.isCancelled { return }
            answer = .unreachable
        }
    }
}
