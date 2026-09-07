import SwiftUI

struct ReplyTextDeliveryBadge: View {
    let state: ReplyTextDeliveryPolicy.State

    var body: some View {
        if let caption = state.caption {
            Label(caption, systemImage: state.symbol)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel(caption)
        }
    }
}
