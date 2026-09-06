import AVFoundation
import SwiftUI

/// The screen that finally runs the experiment.
///
/// `proof/engine_or_audio.py` has been ready since 2026-08-24 and has produced
/// nothing, because no build could write the microphone tap to a file. This is
/// the operator's side of `proof/RECORDING-PROTOCOL.md`: three recordings of
/// one page, twenty minutes, one room.
///
/// SHIPS IN RELEASE, for the same reason `ListeningDiagnosticsView` does — the
/// recordings have to be made on a real handset in a real room, and TestFlight
/// is a release build. It is inert until somebody presses record.
///
/// The protocol is ON THE SCREEN rather than in a document the operator is
/// meant to have open beside the phone. The two failures this experiment cannot
/// survive are a mislabelled arm and a toggle that never took, and both are
/// things a person does while reading instructions from somewhere else.
///
/// EVERY SECTION IS ITS OWN PROPERTY, and every sentence is a named constant.
/// Not style: the first draft of this file put all five sections and their
/// prose inline and the Swift compiler refused it — "unable to type-check this
/// expression in reasonable time". A SwiftUI body is one expression, and string
/// concatenation inside it multiplies the work.
struct ScratchRecorderView: View {
    @State private var arm: ScratchRecorder.Arm = .a
    @State private var recording = false
    @State private var trouble: String?
    @State private var lastTake: ScratchRecorder.Take?
    @State private var decodeNote: String?
    @State private var busy = false
    @State private var takes: [URL] = []
    @State private var voiceProcessing = ScratchRecorder.voiceProcessingWanted

    /// The one listener the app owns (`AnticipyApp.swift:763`). Taken as the
    /// session, the way `SettingsListeningView` takes it, rather than as an
    /// environment object nothing installs.
    @ObservedObject var session: AnticipySession
    private var listener: PhoneListener { session.listener }

    private static let why = "Read the same page aloud three times. The Mac scores the recordings and answers one question: are words lost because the recognizer is weak, or because the microphone is set up to hear badly?"
    private static let stakes = "Roughly a third of spoken words reach the server today. Nobody has ever measured which half of that is true."
    private static let tape = "Arms A and B must be from the same spot, to within a few centimetres. Put tape on the table."
    private static let armBOnly = "Arm B is the only arm that wants this on. Arms A and C are today's settings."
    private static let reading = "Recording. Read the whole script, out loud, at your normal pace."
    private static let clean = "Clean. Now decode it, twice."
    private static let copyOff = "Copy the whole scratch folder to the Mac with the Files app, then run the harness there."
    private static let noTakes = "No recordings yet."
    private static let notListening = "Listening is off, so there is no microphone tap to record. Turn listening on first."
    private static let noFormat = "The capture engine is not running yet. Wait a moment and try again."
    private static let nothing = "Nothing was recorded."

    var body: some View {
        List {
            experiment
            whichArm
            processing
            control
            result
            onDisk
        }
        .navigationTitle("Recording for the harness")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            takes = ScratchRecorder.takesOnDisk()
            ScratchDecoder.authorize { _ in }
        }
    }

    private var experiment: some View {
        Section("The experiment") {
            Text(Self.why).font(.footnote)
            Text(Self.stakes).font(.footnote).foregroundStyle(.secondary)
        }
    }

    private var whichArm: some View {
        Section("Which recording") {
            Picker("Arm", selection: $arm) {
                ForEach(ScratchRecorder.Arm.allCases, id: \.self) { a in
                    Text("Arm \(a.rawValue)").tag(a)
                }
            }
            .pickerStyle(.segmented)
            .disabled(recording)
            Text(arm.instruction).font(.footnote)
            if arm != .c {
                Text(Self.tape).font(.footnote).foregroundStyle(.secondary)
            }
        }
    }

    private var processing: some View {
        Section("Voice processing") {
            Toggle("Voice processing on", isOn: $voiceProcessing)
                .disabled(recording)
            // NEVER what was asked for — what the node actually became.
            Text(processingState).font(.footnote)
            if let refusal = ScratchRecorder.voiceProcessingRefusal {
                Text("The last attempt was refused: \(refusal)")
                    .font(.footnote).foregroundStyle(.red)
            }
            Text(Self.armBOnly).font(.footnote).foregroundStyle(.secondary)
        }
        .onChange(of: voiceProcessing) { want in
            ScratchRecorder.voiceProcessingWanted = want
            // The engine must be rebuilt for the setting to reach the input
            // node, and only then does the read-back mean anything.
            listener.retakeMicrophone()
        }
    }

    private var processingState: String {
        ScratchRecorder.voiceProcessingActual
            ? "The microphone reports voice processing ON."
            : "The microphone reports voice processing OFF."
    }

    private var control: some View {
        Section {
            Button(recording ? "Stop" : "Record arm \(arm.rawValue)") {
                if recording { stop() } else { start() }
            }
            .disabled(busy)
            if recording {
                Text(Self.reading).font(.footnote)
            }
            if let trouble {
                Text(trouble).font(.footnote).foregroundStyle(.red)
            }
        }
    }

    @ViewBuilder
    private var result: some View {
        if let take = lastTake {
            Section("Last recording") {
                row("Arm", take.arm.rawValue)
                row("Length", "\(Int(take.seconds))s")
                row("Rate", "\(Int(take.sampleRate)) Hz")
                row("Dropped buffers", "\(take.droppedBuffers)")
                if let bad = take.trouble {
                    Text(bad).font(.footnote).foregroundStyle(.red)
                } else {
                    Text(Self.clean).font(.footnote).foregroundStyle(.secondary)
                }
                ForEach(ScratchDecoder.Decoder.allCases, id: \.self) { d in
                    Button("Decode: \(d.label)") { decode(take, with: d) }
                        .disabled(busy)
                }
                if let decodeNote {
                    Text(decodeNote).font(.footnote)
                }
            }
        }
    }

    private var onDisk: some View {
        Section("On this phone") {
            if takes.isEmpty {
                Text(Self.noTakes).font(.footnote).foregroundStyle(.secondary)
            }
            ForEach(takes, id: \.self) { url in
                Text(url.lastPathComponent).font(.footnote.monospaced())
            }
            Text(Self.copyOff).font(.footnote).foregroundStyle(.secondary)
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label)
            Spacer()
            Text(value).foregroundStyle(.secondary)
        }
        .font(.footnote)
    }

    private func start() {
        trouble = nil
        decodeNote = nil
        // The arm and the engine must agree BEFORE a byte is written. A wanted
        // toggle that the node refused would otherwise produce a second arm A
        // filed under B — the one failure that reverses the experiment's answer.
        if let mismatch = ScratchRecorder.armMatchesEngine(arm) {
            trouble = mismatch
            return
        }
        guard listener.isListening else {
            trouble = Self.notListening
            return
        }
        guard let format = listener.captureFormat else {
            trouble = Self.noFormat
            return
        }
        if let why = ScratchRecorder.shared.start(arm: arm, format: format) {
            trouble = why
            return
        }
        recording = true
    }

    private func stop() {
        recording = false
        guard let take = ScratchRecorder.shared.stop() else {
            trouble = Self.nothing
            return
        }
        lastTake = take
        trouble = take.trouble
        takes = ScratchRecorder.takesOnDisk()
    }

    private func decode(_ take: ScratchRecorder.Take, with decoder: ScratchDecoder.Decoder) {
        busy = true
        decodeNote = "Decoding \(decoder.rawValue)…"
        ScratchDecoder.decode(wav: take.url, using: decoder) { result in
            busy = false
            switch result {
            case .failure(let why):
                decodeNote = why.errorDescription
            case .success(let text):
                let words = text.split(whereSeparator: { $0 == " " || $0 == "\n" }).count
                let written = ScratchDecoder.write(text, for: take, decoder: decoder)
                if written != nil {
                    decodeNote = "\(decoder.rawValue): \(words) words written."
                    takes = ScratchRecorder.takesOnDisk()
                } else {
                    decodeNote = "\(decoder.rawValue) decoded \(words) words but the file could not be written."
                }
            }
        }
    }
}
