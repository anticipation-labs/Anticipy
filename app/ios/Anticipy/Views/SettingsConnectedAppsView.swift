import SwiftUI

/// SETTINGS → CONNECTED APPS. The apps this owner has connected, what each one
/// is allowed to do, and a way to connect anything else in the catalog.
///
/// NOT `SettingsConnectorsView`, which is next door and is about this DEVICE —
/// the calendar, contacts, mail, the browser, the Mac, the pendant. This screen
/// is about the owner's own accounts elsewhere.
///
/// The view draws and does nothing else. Every decision — whose rows these are,
/// what the switch does when a write fails, what a disconnect is allowed to
/// claim, every sentence on the screen — lives in `ConnectedAppsModel`, where
/// `Tests/run_connected_apps_tests.sh` can run it without a simulator. Two
/// rules the runner enforces on this file, because they are the ones a screen
/// quietly breaks:
///
///   NO APP IS NAMED HERE. Names and logos come from the catalog at run time.
///   NO SENTENCE IS WRITTEN HERE. Copy lives in `ConnectedAppsModel.Copy`,
///   which is where the forbidden-word suite can read all of it at once.
///
/// WHOSE APPS THESE ARE. The owner is derived, once, from the signed-in
/// account's row id (`session.accountID`) — never from `session.ownerID`, which
/// is this app's legacy pre-accounts device UUID and is not an owner row id at
/// all. If the id on this phone is not an owner id, `OwnerId` refuses it and
/// the screen asks for a sign-in rather than showing anybody anything.
struct SettingsConnectedAppsView: View {
    @ObservedObject var session: AnticipySession
    @StateObject private var model: ConnectedAppsModel
    @Environment(\.dismiss) private var dismiss

    /// Starting a connection is the connect-link flow's job, not this screen's:
    /// our own single-use link, opened in Safari or `ASWebAuthenticationSession`
    /// and generated at the moment of the tap. It is injected so this screen
    /// cannot grow a second, quieter way of doing it.
    private let startConnect: (ToolkitMeta) -> Void

    @State private var addingAnApp = false
    /// The alert's own copy of the question.
    ///
    /// NOT `model.pendingDisconnect` directly, and that is a bug fix rather
    /// than a preference: an `isPresented` bound to the model's state clears it
    /// on dismissal, and iOS dismisses an alert as its button fires. The
    /// confirm action then found no pending question and disconnected nothing,
    /// so the destructive button did nothing at all. The model's question is
    /// cleared by the button that answers it, never by the sheet closing.
    @State private var confirming: ConnectedAppsModel.PendingDisconnect?

    init(session: AnticipySession,
         store: ConnectedAppsStore,
         startConnect: @escaping (ToolkitMeta) -> Void) {
        _session = ObservedObject(wrappedValue: session)
        _model = StateObject(wrappedValue: ConnectedAppsModel(store: store))
        self.startConnect = startConnect
    }

    private var owner: OwnerId? { OwnerId(session.accountID) }

    var body: some View {
        SheetChrome(title: ConnectedAppsModel.Copy.title, leading: .back) {
            dismiss()
        } content: {
            if let notice = model.notice {
                GroupedCard {
                    InfoRow(notice, systemImage: "info.circle")
                    ActionRow(ConnectedAppsModel.Copy.dismissNotice) {
                        Haptics.engage()
                        model.dismissNotice()
                    }
                }
            }

            switch model.screen(for: owner) {
            case .signedOut(let said), .loading(let said):
                GroupedCard { InfoRow(said, systemImage: "person.crop.circle") }
            case .trouble(let said):
                GroupedCard { InfoRow(said, systemImage: "exclamationmark.circle") }
                GroupedCard {
                    ActionRow(ConnectedAppsModel.Copy.tryAgain,
                              systemImage: "arrow.clockwise") {
                        Haptics.engage()
                        Task { await model.load() }
                    }
                }
                addAnApp
            case .invitation(let said):
                GroupedCard { InfoRow(said, systemImage: "square.on.square") }
                addAnApp
            case .apps(let rows):
                SectionHeader(ConnectedAppsModel.Copy.sectionHeader)
                ForEach(rows) { row in
                    card(for: row)
                }
                addAnApp
                FootnoteText(ConnectedAppsModel.Copy.optional)
            }
        }
        .task(id: session.accountID) {
            if let owner {
                model.signIn(owner)
                await model.load()
            } else {
                model.signOut()
            }
        }
        .navigationDestination(isPresented: $addingAnApp) {
            AddAnAppView(model: model, owner: owner, startConnect: startConnect)
        }
        .alert(confirming?.question ?? "",
               isPresented: Binding(
                get: { confirming != nil },
                set: { if !$0 { confirming = nil } }
               ),
               presenting: confirming) { pending in
            Button(pending.confirmWords, role: .destructive) {
                Haptics.engage()
                guard let owner else { return }
                Task { await model.confirmDisconnect(owner: owner) }
            }
            Button(pending.cancelWords, role: .cancel) {
                model.cancelDisconnect()
            }
        } message: { pending in
            Text(pending.detail)
        }
    }

    private var addAnApp: some View {
        GroupedCard {
            NavRow(ConnectedAppsModel.Copy.addAnApp, systemImage: "plus") {
                Haptics.engage()
                addingAnApp = true
            }
        }
    }

    /// One app: what it is, then what it may do, then how to end it. The switch
    /// sits above the disconnect on purpose — the everyday control first, the
    /// irreversible one last.
    private func card(for row: ConnectedAppsModel.Row) -> some View {
        GroupedCard {
            CardRowBox.custom {
                AppHeaderRow(row: row)
            }
            ToggleRow(row.writesTitle, subtitle: row.writesDetail,
                      isOn: writes(for: row))
            DestructiveRow(row.disconnectWords, systemImage: "minus.circle") {
                Haptics.engage()
                guard let owner else { return }
                model.askToDisconnect(row.card.toolkit, owner: owner)
                // The model refuses to pose a question about somebody else's
                // app, so a nil here is an answer and the alert stays shut.
                confirming = model.pendingDisconnect
            }
        }
    }

    /// Optimistic in the model, not here: this hands the flip over and redraws
    /// from whatever the model says next — which is the old value again, plus a
    /// sentence, when the write does not land.
    private func writes(for row: ConnectedAppsModel.Row) -> Binding<Bool> {
        Binding(
            get: { row.writesEnabled },
            set: { on in
                Haptics.engage()
                guard let owner else { return }
                Task {
                    await model.setWrites(on, toolkit: row.card.toolkit, owner: owner)
                }
            }
        )
    }
}

// ------------------------------------------------------------- the app's row

/// Logo, name, and the three facts underneath: which account it is, whether it
/// is working, and when it was last used. Every one of them is a value from the
/// model; none of them is written here.
private struct AppHeaderRow: View {
    let row: ConnectedAppsModel.Row

    /// The account label, the status, the read/write position and when it was
    /// last used — four values, every one of them from the model. An app with
    /// no named account simply has three.
    private var facts: String {
        [row.accountLabel, row.statusWords, row.writesWords, row.lastUsedWords]
            .filter { !$0.isEmpty }
            .joined(separator: " · ")
    }

    var body: some View {
        HStack(alignment: .center, spacing: Theme.Space.base) {
            AppLogo(url: row.logoURL, name: row.name)
            VStack(alignment: .leading, spacing: Theme.Space.hair) {
                Text(row.name)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
                Text(facts)
                    .font(.footnote)
                    .foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        // The kit's row padding is private to it and is spelled in the app's
        // own spacing scale, so this row sits on the same rhythm without
        // copying a number that belongs to another file. No minimum height:
        // a 30pt tile inside this padding already clears the 44pt target.
        .padding(.horizontal, Theme.Space.base)
        .padding(.vertical, Theme.Space.snug)
        .accessibilityElement(children: .combine)
    }
}

/// The catalog's logo when there is one, and the app's own initial when there
/// is not. No per-app asset ships in this bundle: an app the catalog gained
/// this morning draws correctly this afternoon.
private struct AppLogo: View {
    /// This component's own geometry, for the reason `SheetMetric` gives for
    /// keeping the kit's numbers out of `Theme`: a 30pt tile with an 8pt corner
    /// describes one control and would mean nothing anywhere else.
    private enum Metric {
        static let side: CGFloat = 30
        static let corner: CGFloat = 8
    }

    /// Already parsed and scheme-checked by `ConnectionsPolicy.logoURL`, so a
    /// catalog row cannot hand this view a `file:` or `javascript:` "logo".
    let url: URL?
    let name: String

    private var initial: String {
        String(name.trimmingCharacters(in: .whitespacesAndNewlines).prefix(1)).uppercased()
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: Metric.corner, style: .continuous)
                .fill(Theme.edge)
            Text(initial)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(Theme.text2)
            if let url {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFit()
                } placeholder: {
                    Color.clear
                }
            }
        }
        .frame(width: Metric.side, height: Metric.side)
        .clipShape(RoundedRectangle(cornerRadius: Metric.corner, style: .continuous))
        .accessibilityHidden(true)
    }
}

// --------------------------------------------------------------- add an app

/// The whole catalog, searched by name — which is how somebody connects
/// something Anticipy never thought to ask about.
///
/// The field's letters go straight to the model, which hands them to the
/// catalog untouched. Nothing here filters, ranks or corrects: what comes back
/// is what is shown, in the order it came back.
private struct AddAnAppView: View {
    @ObservedObject var model: ConnectedAppsModel
    let owner: OwnerId?
    let startConnect: (ToolkitMeta) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    /// Typing is not a search per letter. The model already refuses a stale
    /// answer, so this is politeness to the catalog rather than correctness —
    /// but a request per keystroke is a request per keystroke.
    @State private var typing: Task<Void, Never>?

    var body: some View {
        SheetChrome(title: ConnectedAppsModel.Copy.addAnApp, leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                ValueRow(ConnectedAppsModel.Copy.searchLabel,
                         text: $query,
                         placeholder: ConnectedAppsModel.Copy.searchPlaceholder,
                         submit: .search) {
                    searchNow(query)
                }
            }

            switch model.searchState {
            case .idle(let said), .searching(let said),
                 .nothingFound(let said), .trouble(let said):
                GroupedCard { InfoRow(said, systemImage: "magnifyingglass") }
            case .results(let found):
                GroupedCard {
                    for hit in found {
                        row(for: hit)
                    }
                }
            }

            FootnoteText(ConnectedAppsModel.Copy.optional)
        }
        .onChange(of: query) { value in
            run(value)
        }
    }

    private func row(for hit: ConnectedAppsModel.Found) -> CardRowBox {
        CardRowBox.custom {
            if hit.alreadyConnected {
                StateRow(hit.meta.name, state: ConnectedAppsModel.Copy.alreadyConnected)
            } else {
                ActionRow(ConnectedAppsModel.Copy.connectAction(app: hit.meta.name),
                          subtitle: hit.meta.description,
                          systemImage: "plus.circle") {
                    Haptics.engage()
                    startConnect(hit.meta)
                }
            }
        }
    }

    /// One search per pause in the typing.
    private func run(_ text: String) {
        typing?.cancel()
        guard let owner else { return }
        typing = Task {
            try? await Task.sleep(nanoseconds: 300_000_000)
            guard !Task.isCancelled else { return }
            await model.search(text, owner: owner)
        }
    }

    /// Somebody who hit Search has stopped typing by definition.
    private func searchNow(_ text: String) {
        typing?.cancel()
        typing = nil
        guard let owner else { return }
        Task { await model.search(text, owner: owner) }
    }
}
