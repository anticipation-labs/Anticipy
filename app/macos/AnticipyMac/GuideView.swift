import SwiftUI

/// The guide, in the app. The same sections, in the same order, as
/// docs/MAC-APP-GUIDE.md; run_guide_tests.sh refuses a heading that exists in
/// one and not the other, so the two cannot drift apart quietly.
enum MacGuide {
    struct Section: Identifiable {
        let title: String
        let body: [String]
        var id: String { title }
    }

    static let sections: [Section] = [
        Section(title: "What Anticipy for Mac does", body: [
            "It records a meeting from both sides: your microphone, and whatever your Mac is playing, which is everyone else on the call. The two are kept as separate tracks so nobody's words are mixed into anybody else's.",
            "On this Mac, the audio becomes text. The text reaches the same Anticipy your phone talks to, so what you agreed to in a meeting can become work. The audio never leaves this Mac.",
        ]),
        Section(title: "Starting a recording", body: [
            "Press Start recording in the window, press Command-R, or click the microphone in the menu bar. Press Stop, or Command-period, when the meeting ends.",
            "When a call starts in Zoom, Teams, FaceTime, a browser or any other app, Anticipy notices and offers: a notification, and a banner at the top of the window. The click is yours. In Settings you can ask it to start on its own instead.",
        ]),
        Section(title: "During a meeting", body: [
            "The window shows the clock, one sentence about the state of both wires, and the transcript as it settles. Lines from your microphone are marked You; lines from the call are marked Others. A line in grey italics is a phrase the transcriber may still revise.",
            "Type notes on the right at any time. They are saved as you type, into the same folder as the recording, and are there when the meeting becomes a record.",
        ]),
        Section(title: "After a meeting", body: [
            "Every recording appears in the sidebar under the day it happened, with its length. Click one to read the transcript and your notes. Click the title to rename it.",
            "Copy as Markdown puts the whole meeting, notes first, on the clipboard. Show in Finder opens its folder. Move to Trash sends the folder to the Trash; nothing is ever deleted outright.",
        ]),
        Section(title: "Permissions", body: [
            "macOS asks for the Microphone and for Speech Recognition during first run. The first recording also asks for System Audio Recording, which is how the other side of a call is heard; there is no way to ask for that one sooner.",
            "If a switch is off, the app says so in as many words and can only send you to System Settings, under Privacy & Security. It cannot ask again on its own.",
        ]),
        Section(title: "Privacy", body: [
            "Audio is written to Application Support, under Anticipy, under Meetings, and stays there. Transcript text is sent to api.anticipy.ai when you are signed in, over the same wire the phone app uses, with the same account.",
            "If a line cannot be sent, it waits on this Mac and is sent when a connection returns. The sidebar says how many are waiting. Nothing is dropped, and nothing is sent about a meeting while you are signed out.",
        ]),
        Section(title: "Where things are", body: [
            "Settings, under the Anticipy menu or Command-comma: the account, whether recording starts on its own, light or dark, and the meetings folder.",
            "The menu bar microphone: start, stop, open the window, quit. The window can be closed and reopened from the Dock or the menu bar without losing anything.",
        ]),
    ]
}

struct GuideView: View {
    @AppStorage(MacAppearance.key) private var appearanceRaw = MacAppearance.light.rawValue

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: MacTheme.Space.section) {
                HStack(spacing: MacTheme.Space.snug) {
                    BrandMark(size: 36)
                    Text("Anticipy for Mac")
                        .font(MacTheme.display(30, weight: .medium))
                        .foregroundStyle(MacTheme.text)
                }
                ForEach(MacGuide.sections) { section in
                    VStack(alignment: .leading, spacing: MacTheme.Space.snug) {
                        Text(section.title)
                            .font(MacTheme.display(20, weight: .medium))
                            .foregroundStyle(MacTheme.text)
                        ForEach(section.body, id: \.self) { paragraph in
                            Text(paragraph)
                                .font(MacTheme.voice)
                                .foregroundStyle(MacTheme.text2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .padding(MacTheme.Space.wide)
            .frame(maxWidth: 640, alignment: .leading)
        }
        .frame(minWidth: 560, minHeight: 480)
        .background(MacTheme.bg)
        .preferredColorScheme(MacAppearance(rawValue: appearanceRaw).colorScheme)
    }
}
