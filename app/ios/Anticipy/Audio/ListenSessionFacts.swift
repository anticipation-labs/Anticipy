import Foundation

/// What the audio session actually BECAME, as a VALUE rather than as a sentence.
///
/// Three `try?` calls configure the audio session in `PhoneListener` and each
/// one swallows its error, so the app can report "Listening" over a session it
/// never got. Reading the session back and journalling what it says is the
/// cheapest way to see that. Low power mode rides along because it changes what
/// iOS will let a background app do, and a day that died on a throttled phone
/// otherwise looks like a bug.
///
/// WHY A TYPE AND NOT A `var facts = "…"`. That sentence used to be built up in
/// a mutable local inside a 1,100-line file, and the whole privacy argument for
/// it rested on `run_journal_tests.sh` being able to read every line that gave
/// that local a value. A reviewer wrote two working leaks past that reading in
/// one sitting:
///
///     self.facts += self.partial                      the scan could not see a
///                                                     write through `self.`
///     (facts, lastSessionFacts) = (self.partial, "")  an assignment shape it
///                                                     did not recognise, and
///                                                     therefore read as a
///                                                     harmless mention
///
/// Neither of them COMPILES any more, which is the point of this file.
///
/// WHY THE TWO NAMES ARE ENUMS AND NOT `String`s, which is the 2026-08-25
/// half of the same argument. Storing them as `String` left the privacy claim
/// resting on a SCAN again: `run_journal_tests.sh` read the one construction
/// site argument by argument and compared it against an allowlisted spelling.
/// A fifth-pass review broke that allowlist twice in one sitting — once by
/// exploiting `glue()`, which strips `+` and so reduced `f + acts.sentence` to
/// the allowlisted `facts.sentence`, and once by flipping the type of an
/// allowlisted Int to String — and the honest conclusion was that a scan over
/// an unbounded surface is a race the surface wins.
///
/// So the surface is bounded instead. `category` and `mode` are CLOSED SETS.
/// The initializer still accepts the raw names, because the only caller has an
/// `AVAudioSession.Category` and this file must stay AVFoundation-free — but a
/// name that is not one of Apple's collapses to `.unrecognised` on the way in.
/// `ListenSessionFacts(category: transcript, …)` compiles and records the word
/// "unrecognised": the transcript does not survive construction, so there is no
/// state left for a scan to have to detect.
///
/// `ListenEvent` makes the same argument with the same instrument: after
/// 2026-08-25 it declares no free `String` payload at all.
///
/// Pure Foundation on purpose, like `ListenJournal` and `TranscriptFlushPolicy`:
/// no AVFoundation, no Speech, no UI, so `swiftc` alone can exercise it.
struct ListenSessionFacts: Equatable {

    /// `AVAudioSession.Category`, as the closed set Apple actually declares.
    ///
    /// The raw values are Apple's constant strings rather than Swift case
    /// names, so a journal line written today still reads the same after a
    /// Swift-side rename — the rule `LineSource.wireName` was written for, and
    /// the reason `unrecognised` is spelled out rather than left to
    /// `String(describing:)`.
    enum Category: String, Equatable, CaseIterable {
        case ambient = "AVAudioSessionCategoryAmbient"
        case soloAmbient = "AVAudioSessionCategorySoloAmbient"
        case playback = "AVAudioSessionCategoryPlayback"
        case record = "AVAudioSessionCategoryRecord"
        case playAndRecord = "AVAudioSessionCategoryPlayAndRecord"
        case multiRoute = "AVAudioSessionCategoryMultiRoute"
        /// Apple shipped a category this build has never heard of — or
        /// somebody handed this initializer something that is not a category
        /// at all. Both read the same on disk, and neither can be a sentence
        /// anybody spoke.
        case unrecognised
    }

    /// `AVAudioSession.Mode`, same rule.
    enum Mode: String, Equatable, CaseIterable {
        case `default` = "AVAudioSessionModeDefault"
        case voiceChat = "AVAudioSessionModeVoiceChat"
        case gameChat = "AVAudioSessionModeGameChat"
        case videoRecording = "AVAudioSessionModeVideoRecording"
        case measurement = "AVAudioSessionModeMeasurement"
        case moviePlayback = "AVAudioSessionModeMoviePlayback"
        case videoChat = "AVAudioSessionModeVideoChat"
        case spokenAudio = "AVAudioSessionModeSpokenAudio"
        case voicePrompt = "AVAudioSessionModeVoicePrompt"
        case unrecognised
    }

    let category: Category
    let mode: Mode
    /// `ProcessInfo.isLowPowerModeEnabled` at the moment the session was read.
    let lowPower: Bool

    /// THE ONLY WAY IN, and it is a filter rather than a memberwise copy.
    ///
    /// It takes the raw names because the caller holds an
    /// `AVAudioSession.Category` and this file may not import AVFoundation.
    /// What it stores is a case of a closed enum, so whatever arrives, what is
    /// kept is one of seven words this file wrote itself.
    init(category: String, mode: String, lowPower: Bool) {
        self.category = Category(rawValue: category) ?? .unrecognised
        self.mode = Mode(rawValue: mode) ?? .unrecognised
        self.lowPower = lowPower
    }

    /// The one line this value is written to the journal as.
    ///
    /// ONE EXPRESSION, no mutable local, because `run_journal_tests.sh` reads
    /// this body and requires everything it names to be one of the stored
    /// properties above. A `+ speech` or a `\(partial)` fails that check — and
    /// could not say anything anyway, since the three properties it is allowed
    /// to name are two closed enums and a Bool.
    var sentence: String {
        "session category: \(category.rawValue) mode: \(mode.rawValue)"
            + (lowPower ? " · low power mode on" : "")
    }

    /// The reader for that line, deliberately in the same file as the writer.
    ///
    /// `ListenJournal.parse` rebuilds a day's events off disk, and a shape it
    /// cannot read is an event silently dropped from the tally — the exact
    /// failure `ListenEvent.everyCase` exists to make impossible. Keeping both
    /// halves here means a reworded `sentence` breaks the round trip in the
    /// test rather than in six months on somebody's phone.
    ///
    /// FAILABLE, AND STRICT. An unknown category is `nil` here rather than
    /// `.unrecognised`: on the way IN from AVFoundation an unknown name is a
    /// fact worth keeping, but on the way BACK a word this build never wrote is
    /// evidence the line did not come from `describe`, and reading it as though
    /// it had is how a writer and a reader drift apart in silence.
    init?(sentence: String) {
        var rest = sentence
        let lowSuffix = " · low power mode on"
        let low = rest.hasSuffix(lowSuffix)
        if low { rest = String(rest.dropLast(lowSuffix.count)) }
        let head = "session category: "
        guard rest.hasPrefix(head) else { return nil }
        let fields = rest.dropFirst(head.count).components(separatedBy: " mode: ")
        guard fields.count == 2,
              let category = Category(rawValue: fields[0]),
              let mode = Mode(rawValue: fields[1]) else { return nil }
        self.category = category
        self.mode = mode
        self.lowPower = low
    }
}
