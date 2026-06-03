import SwiftUI

/// Screen 1 — Onboarding (first). Calm "let me get to know you". One primary
/// action, a quiet progress area. Inert.
struct OnboardingView: View {
    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            VStack(spacing: DS.s2) {
                Text("Let me get to know you.")
                    .font(DS.display())
                    .foregroundColor(DS.textPrimary)
                    .multilineTextAlignment(.center)

                Text("A few quiet minutes so Anticipy can anticipate —\nyour people, your week, the way you work.")
                    .font(DS.body())
                    .foregroundColor(DS.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineSpacing(4)

                Button("Begin") {}            // inert
                    .buttonStyle(PrimaryButtonStyle())
                    .padding(.top, DS.s1)

                ProgressDots(total: 5, done: 0)
                    .padding(.top, DS.s3)
                Text("This stays on your Mac.")
                    .font(DS.caption())
                    .foregroundColor(DS.textSecondary.opacity(0.8))
            }
            .frame(maxWidth: 520)
            .padding(DS.s4)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DS.bg)
    }
}

private struct ProgressDots: View {
    let total: Int
    let done: Int
    var body: some View {
        HStack(spacing: DS.s1) {
            ForEach(0..<total, id: \.self) { i in
                Capsule()
                    .fill(i < done ? DS.accent : DS.hairline)
                    .frame(width: i == done ? 22 : 8, height: 8)
            }
        }
    }
}
