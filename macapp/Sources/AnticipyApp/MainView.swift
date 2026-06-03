import SwiftUI

/// Screen 3 — Main (proactive-first). The centerpiece is the live "what I'm
/// doing / things to approve" area (empty). Record controls present but inert.
/// A small, clearly-secondary text box is the side door. Inert.
struct MainView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: DS.s3) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Today").font(DS.display()).foregroundColor(DS.textPrimary)
                    Text("What I'm doing · things to approve")
                        .font(DS.secondary()).foregroundColor(DS.textSecondary)
                }
                Spacer()
                RecordControls()
            }

            // Centerpiece: proactive area (empty state)
            Card(elevated: true) {
                VStack(spacing: DS.s2) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 26)).foregroundColor(DS.accent)
                    Text("Nothing needs you right now.")
                        .font(DS.title()).foregroundColor(DS.textPrimary)
                    Text("Anticipy is listening for what it can take off your plate.\nWhen something comes up, it shows up here.")
                        .font(DS.body()).foregroundColor(DS.textSecondary)
                        .multilineTextAlignment(.center).lineSpacing(4)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(DS.s4)
            }
            .frame(maxHeight: .infinity)

            // Side door: small, secondary text box
            SideDoor()
        }
        .padding(DS.s4)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.bg)
    }
}

private struct RecordControls: View {
    var body: some View {
        HStack(spacing: DS.s1) {
            ForEach(["MP3", "Transcript"], id: \.self) { label in
                Text(label)
                    .font(DS.secondary(.medium)).foregroundColor(DS.textSecondary)
                    .padding(.horizontal, DS.s2).padding(.vertical, 6)
                    .overlay(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous).stroke(DS.hairline))
            }
            HStack(spacing: 6) {
                Circle().fill(DS.accent).frame(width: 8, height: 8)
                Text("Record").font(DS.secondary(.medium)).foregroundColor(DS.textPrimary)
            }
            .padding(.horizontal, DS.s2).padding(.vertical, 6)
            .background(DS.elevated)
            .clipShape(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous))
        }
    }
}

private struct SideDoor: View {
    var body: some View {
        HStack(spacing: DS.s1) {
            Image(systemName: "text.cursor").font(.system(size: 12)).foregroundColor(DS.textSecondary)
            Text("Tell Anticipy something…")
                .font(DS.secondary()).foregroundColor(DS.textSecondary.opacity(0.7))
            Spacer()
        }
        .padding(.horizontal, DS.s2).padding(.vertical, DS.s1)
        .frame(maxWidth: 360)
        .background(DS.surface)
        .overlay(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous).stroke(DS.hairline))
    }
}
