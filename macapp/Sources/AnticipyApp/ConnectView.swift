import SwiftUI

/// Screen 2 — Connect (after onboarding). A generous grid of app tiles to
/// connect. No mention of the word "API" anywhere a user sees. Inert.
struct ConnectView: View {
    private struct App: Identifiable {
        let id = UUID(); let name: String; let glyph: String
    }
    private let apps: [App] = [
        .init(name: "Google", glyph: "g.circle.fill"),
        .init(name: "Gmail", glyph: "envelope.fill"),
        .init(name: "Calendar", glyph: "calendar"),
        .init(name: "Microsoft", glyph: "m.square.fill"),
        .init(name: "Slack", glyph: "number.square.fill"),
        .init(name: "Notion", glyph: "note.text"),
        .init(name: "Drive", glyph: "externaldrive.fill"),
        .init(name: "Messages", glyph: "message.fill"),
    ]
    private let cols = [GridItem(.adaptive(minimum: 150), spacing: DS.s2)]

    var body: some View {
        VStack(alignment: .leading, spacing: DS.s3) {
            VStack(alignment: .leading, spacing: DS.s1) {
                Text("Connect what you use.")
                    .font(DS.display())
                    .foregroundColor(DS.textPrimary)
                Text("Anticipy works best when it can see your day. Add what matters — you can change this anytime.")
                    .font(DS.body())
                    .foregroundColor(DS.textSecondary)
            }

            LazyVGrid(columns: cols, spacing: DS.s2) {
                ForEach(apps) { app in
                    Card {
                        VStack(alignment: .leading, spacing: DS.s2) {
                            Image(systemName: app.glyph)
                                .font(.system(size: 22))
                                .foregroundColor(DS.titanium)
                            Text(app.name)
                                .font(DS.body(.medium))
                                .foregroundColor(DS.textPrimary)
                            Text("Connect")
                                .font(DS.secondary())
                                .foregroundColor(DS.accent)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(DS.s2)
                    }
                }
            }
            Spacer()
        }
        .padding(DS.s4)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.bg)
    }
}
