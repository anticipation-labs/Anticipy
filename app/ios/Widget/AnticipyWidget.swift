import SwiftUI
import WidgetKit

// THE ONE-TAP EAR. A home-screen or Lock Screen tile whose entire job is to
// put "Anticipy starts listening" one tap from anywhere. The tap opens the
// app with anticioy://listen — no AppIntent, no shared container, no App
// Group: a widget that needs provisioning ceremonies is a widget that does
// not ship, and a button this small has to work on the first morning.
//
// The app owns what happens next (AnticipyApp's onOpenURL -> startListening):
// permission prompts, the account gate, the feed. The widget only rings the
// doorbell.

struct ListenEntry: TimelineEntry {
    let date: Date
}

struct ListenProvider: TimelineProvider {
    func placeholder(in context: Context) -> ListenEntry { ListenEntry(date: .now) }
    func getSnapshot(in context: Context, completion: @escaping (ListenEntry) -> Void) {
        completion(ListenEntry(date: .now))
    }
    func getTimeline(in context: Context, completion: @escaping (Timeline<ListenEntry>) -> Void) {
        // A static doorbell has nothing to refresh: one entry, no reloads,
        // zero widget budget spent.
        completion(Timeline(entries: [ListenEntry(date: .now)], policy: .never))
    }
}

private let listenURL = URL(string: "anticipy://listen")!

struct ListenWidgetView: View {
    let entry: ListenEntry

    @Environment(\.widgetFamily) private var family

    var body: some View {
        // iOS 17 makes an explicit container background mandatory; older
        // builds pad their own. Both keep the tile tappable edge to edge.
        if #available(iOSApplicationExtension 17.0, *) {
            content
                .containerBackground(for: .widget) {
                    Color(.systemBackground).opacity(0.001)
                }
        } else {
            content.padding(6)
        }
    }

    @ViewBuilder
    private var content: some View {
        switch family {
        case .accessoryCircular:
            ZStack {
                AccessoryWidgetBackground()
                Image(systemName: "waveform")
                    .font(.system(size: 22, weight: .semibold))
            }
            .widgetURL(listenURL)
        case .accessoryRectangular:
            VStack(alignment: .leading, spacing: 2) {
                Image(systemName: "waveform")
                    .font(.system(size: 14, weight: .semibold))
                Text("Anticipy")
                    .font(.headline)
                Text("Tap to listen")
                    .font(.caption2)
            }
            .widgetURL(listenURL)
        default:
            VStack(alignment: .leading, spacing: 6) {
                Image(systemName: "waveform")
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(.green)
                Text("Anticipy")
                    .font(.headline)
                Text("Tap to listen")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
            .widgetURL(listenURL)
        }
    }
}

struct AnticipyListenWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "AnticipyListen", provider: ListenProvider()) { entry in
            ListenWidgetView(entry: entry)
        }
        .configurationDisplayName(Text("Anticipy"))
        .supportedFamilies([.systemSmall, .accessoryCircular, .accessoryRectangular])
    }
}

@main
struct AnticipyWidgetBundle: WidgetBundle {
    var body: some Widget {
        AnticipyListenWidget()
    }
}
