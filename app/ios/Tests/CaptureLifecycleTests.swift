import Foundation

// Only OS/model/audio edges are doubles. The runner extracts the shipping
// start, stop, watchdog, engine start, analyzer callbacks and swap bodies.
// The real watchdog policy and cursor execute. No microphone is opened.
final class ListenJournal {
    static let shared = ListenJournal()
    var events: [ListenEvent] = []
    func record(_ event: ListenEvent) { events.append(event) }
}
enum SFSpeechRecognizerAuthorizationStatus { case authorized, denied, restricted }
final class SFSpeechAudioBufferRecognitionRequest {
    var buffers: [Int] = []
    var shouldReportPartialResults = false
    var contextualStrings: [String] = []
    enum Hint { case dictation }
    var taskHint = Hint.dictation
    var addsPunctuation = false
    var requiresOnDeviceRecognition = false
    func append(_ buffer: Int) { buffers.append(buffer) }
}
final class SFSpeechRecognitionTask {
    var cancelled = false
    var finished = false
    func cancel() { cancelled = true }
    func finish() { finished = true }
}
struct RecognitionResult {
    struct Transcription { let formattedString: String }
    let bestTranscription: Transcription
    let isFinal: Bool
}
final class SFSpeechRecognizer {
    static var authorizations: [(SFSpeechRecognizerAuthorizationStatus) -> Void] = []
    static func requestAuthorization(_ callback: @escaping (SFSpeechRecognizerAuthorizationStatus) -> Void) {
        authorizations.append(callback)
    }
    var supportsOnDeviceRecognition = true
    var callbacks: [(RecognitionResult?, Error?) -> Void] = []
    func recognitionTask(with request: SFSpeechAudioBufferRecognitionRequest,
                         resultHandler: @escaping (RecognitionResult?, Error?) -> Void) -> SFSpeechRecognitionTask {
        callbacks.append(resultHandler)
        return SFSpeechRecognitionTask()
    }
}
final class AVAudioSession {
    static let singleton = AVAudioSession()
    static func sharedInstance() -> AVAudioSession { singleton }
    var permissions: [(Bool) -> Void] = []
    enum Options { case notifyOthersOnDeactivation }
    func requestRecordPermission(_ callback: @escaping (Bool) -> Void) { permissions.append(callback) }
    func setActive(_ active: Bool, options: Options) throws {}
}
enum ListenEnginePolicy { static var usesAnalyzerNow = true }
enum AnticipyVocabulary { static func current() -> [String] { [] } }
final class UIDevice {
    static let current = UIDevice()
    var isBatteryMonitoringEnabled = false
}
final class LifecycleSpeaker {
    func tagForLatestUtterance(completion: @escaping (String?) -> Void) { completion(nil) }
}
final class SpeechAnalyzerRequestEngine {
    static var created: [SpeechAnalyzerRequestEngine] = []
    static func make(locale: Locale) -> SpeechAnalyzerRequestEngine {
        let value = SpeechAnalyzerRequestEngine()
        created.append(value)
        return value
    }
    var onResult: ((String, Bool) -> Void)?
    var onError: (() -> Void)?
    var began = false
    var finished = false
    var buffers: [Int] = []
    func append(_ buffer: Int) { buffers.append(buffer) }
    func begin() { began = true }
    func finish() { finished = true }
}
final class CaptureEngine {
    var isRunning = true
    final class Input { func removeTap(onBus: Int) {} }
    let inputNode = Input()
    func stop() { isRunning = false }
}

final class LifecycleListener {
    var isListening = false
    var enrolling = false
    var wasListeningBeforeEnrollment = false
    var authorized = true
    var suspended = false
    var listenStartGeneration = 0
    var beginCalls = 0
    var engine = CaptureEngine()
    var recognizer: SFSpeechRecognizer? = SFSpeechRecognizer()
    var task: SFSpeechRecognitionTask?
    var request: SFSpeechAudioBufferRecognitionRequest?
    var analyzerEngine: SpeechAnalyzerRequestEngine?
    var usingAnalyzer = false
    var analyzerFailures = 0
    var analyzerDisabledForSession = false
    var watchdog: Timer?
    var lastBufferAt = Date()
    var lastResultAt = Date()
    var lastPartialAt: Date?
    var requestBornAt = Date()
    var orphanLock = NSLock()
    var orphanDropped = 0
    var orphanBuffers: [Int] = []
    var acceptingAudio = false
    var cursor = TranscriptCursor()
    let flushPolicy = TranscriptFlushPolicy()
    let utteranceGap: TimeInterval = 2.6
    var lastDelivered: String?
    var speaker: LifecycleSpeaker?
    var onSpeaker: ((String, String?, Date, Date, Bool) -> Void)?
    var onLine: ((String, Date, Date, Bool) -> Void)?
    var pendingTail: String { cursor.pending }
    var pendingSince: Date?
    var partial = ""
    var lineageBrokeAt: Date?
    var cutAt: Date?
    var everEmittedThisTask = false
    var silenceFlush: DispatchWorkItem?
    var scheduledAudioRecovery: DispatchWorkItem?
    var scheduledAudioRecoveryCause: ListenEvent.SwapCause?
    var lastSessionFacts: ListenSessionFacts?
    var lastBatteryReading: Int?
    var tapInstalled = false
    var delivered: [String] = []
    var retryCalls = 0
    var recoveryCalls = 0

    init() {
        onLine = { [weak self] line, _, _, _ in self?.delivered.append(line) }
    }
    func installObserversOnce() {}
    func installCallSenseOnce() {}
    func configureAndStartEngine() { beginCalls += 1; engine.isRunning = true }
    func recordBatteryReading(boundary: Bool) {}
    func retryCapture(cause: ListenEvent.SwapCause) { retryCalls += 1 }
    func recoverAudio(cause: ListenEvent.SwapCause) { recoveryCalls += 1 }
}

@main struct CaptureLifecycleTests {
    static var failures = 0
    static var checks = 0
    static func check(_ name: String, _ condition: Bool) {
        checks += 1
        if condition { print("PASS: \(name)") }
        else { failures += 1; print("FAIL: \(name)") }
    }
    // All production permission callbacks marshal to the main queue. Pump it
    // explicitly after delivering each controlled OS answer, never sleep in an
    // assertion (nor depend on optimized assert semantics).
    static func drain() {
        var completed = false
        DispatchQueue.main.async { DispatchQueue.main.async { completed = true } }
        let deadline = Date().addingTimeInterval(1)
        while !completed, Date() < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.002))
        }
        if !completed { print("FAIL: main callback queue failed to drain"); exit(2) }
    }
    static func resetPermissions() {
        SFSpeechRecognizer.authorizations = []
        AVAudioSession.singleton.permissions = []
    }
    static func grantSpeech(_ index: Int = 0, _ answer: SFSpeechRecognizerAuthorizationStatus = .authorized) {
        guard SFSpeechRecognizer.authorizations.indices.contains(index) else {
            print("FAIL: expected a pending speech permission"); failures += 1; return
        }
        SFSpeechRecognizer.authorizations[index](answer)
        drain()
    }
    static func grantMic(_ index: Int = 0, _ answer: Bool = true) {
        guard AVAudioSession.singleton.permissions.indices.contains(index) else {
            print("FAIL: expected a pending microphone permission"); failures += 1; return
        }
        AVAudioSession.singleton.permissions[index](answer)
        drain()
    }
    static func main() {
        permissionChecks()
        recognitionChecks()
        analyzerPhraseChecks()
        enrollmentChecks()
        print("Capture lifecycle: \(checks) checks, \(failures) failures")
        if failures > 0 { exit(1) }
    }
    static func permissionChecks() {
        resetPermissions()
        let first = LifecycleListener()
        first.start()
        first.stop()
        grantSpeech()
        if !AVAudioSession.singleton.permissions.isEmpty { grantMic() }
        check("Stop fences a delayed speech grant", !first.isListening && first.beginCalls == 0)
        check("obsolete speech grant does not ask for microphone", AVAudioSession.singleton.permissions.isEmpty)

        resetPermissions()
        let second = LifecycleListener()
        second.start()
        grantSpeech()
        second.stop() // Same listener boundary signOut/expireSession invoke.
        grantMic()
        check("Stop fences a delayed microphone grant", !second.isListening && second.beginCalls == 0)

        resetPermissions()
        let newer = LifecycleListener()
        newer.start()
        grantSpeech()
        newer.stop()
        newer.start()
        grantSpeech(1)
        grantMic(1)
        let begins = newer.beginCalls
        let journalCount = ListenJournal.shared.events.count
        grantMic(0, false)
        grantSpeech(0, .denied)
        check("stale denials do not poison a new granted session", newer.authorized && newer.isListening && newer.beginCalls == begins)
        check("stale denials produce no journal events", ListenJournal.shared.events.count == journalCount)
        newer.start()
        check("repeated Start on a live session asks no new permissions", SFSpeechRecognizer.authorizations.count == 2)
        newer.stop()

        resetPermissions()
        let denied = LifecycleListener()
        denied.start()
        grantSpeech(0, .denied)
        check("current speech denial is visible without beginning capture", !denied.authorized && denied.beginCalls == 0)
        denied.start()
        grantSpeech(1)
        grantMic(0, false)
        check("current microphone denial is visible without beginning capture", !denied.authorized && denied.beginCalls == 0)
        denied.start()
        grantSpeech(2)
        grantMic(1)
        check("a later real grant recovers authorization", denied.authorized && denied.isListening && denied.beginCalls == 1)
        denied.stop()

        resetPermissions()
        let enrollment = LifecycleListener()
        enrollment.startForEnrollment()
        enrollment.stopAfterEnrollment()
        grantSpeech()
        if !AVAudioSession.singleton.permissions.isEmpty { grantMic() }
        check("cancelled enrollment cannot reopen a delayed microphone", !enrollment.enrolling && !enrollment.isListening && enrollment.beginCalls == 0)

        resetPermissions()
        let ambientEnrollment = LifecycleListener()
        ambientEnrollment.isListening = true
        ambientEnrollment.startForEnrollment()
        ambientEnrollment.stopAfterEnrollment()
        check("enrollment preserves already-running ambient capture", ambientEnrollment.isListening && !ambientEnrollment.enrolling && SFSpeechRecognizer.authorizations.isEmpty)
        ambientEnrollment.stop()
    }
    static func recognitionChecks() {
        ListenEnginePolicy.usesAnalyzerNow = true
        let listener = LifecycleListener()
        listener.isListening = true
        listener.startRecognition()
        guard let first = listener.analyzerEngine else { print("FAIL: analyzer fixture did not begin"); exit(2) }
        first.onResult?("words not yet sent", false)
        drain()
        listener.startWatchdog()
        for _ in 0..<3 { listener.watchdog?.fire() }
        check("healthy analyzer survives repeated watchdog ticks", listener.analyzerEngine === first)
        check("watchdog retains unsent analyzer words", listener.pendingTail == "words not yet sent")
        check("healthy analyzer tick does not flush or restart", listener.delivered.isEmpty && !first.finished)

        listener.analyzerEngine = nil
        listener.watchdog?.fire()
        check("analyzer flag without an engine restarts recognition", listener.analyzerEngine != nil && listener.analyzerEngine !== first)
        guard let active = listener.analyzerEngine else { exit(2) }
        let heard = listener.pendingTail
        first.onResult?("stale result", false)
        first.onError?()
        drain()
        check("superseded analyzer callbacks cannot mutate current capture", listener.pendingTail == heard && listener.analyzerFailures == 0 && listener.analyzerEngine === active)

        active.onResult?("tail before retry", false)
        drain()
        active.onError?()
        drain()
        check("analyzer error flushes known words before swapping", listener.delivered.contains("tail before retry") && active.finished)
        let retryEngine = listener.analyzerEngine
        listener.begin()
        check("reentrant begin does not reset this session's failure count", listener.analyzerFailures == 1 && listener.analyzerEngine === retryEngine)
        listener.analyzerEngine?.onError?()
        drain()
        listener.analyzerEngine?.onError?()
        drain()
        check("third analyzer failure selects legacy fallback", listener.analyzerDisabledForSession && !listener.usingAnalyzer && listener.task != nil && listener.analyzerEngine == nil)
        let legacyTask = listener.task
        listener.watchdog?.fire()
        check("healthy legacy fallback survives watchdog tick", listener.task === legacyTask)
        listener.task = nil
        listener.watchdog?.fire()
        check("missing legacy request is restarted", listener.task != nil && listener.task !== legacyTask)
        let staleLegacyCallback = listener.recognizer!.callbacks.first!
        let currentRequest = listener.request
        let beforeLate = listener.pendingTail
        staleLegacyCallback(RecognitionResult(bestTranscription: .init(formattedString: "obsolete legacy"), isFinal: false), nil)
        drain()
        check("superseded legacy callback is rejected by request identity", listener.pendingTail == beforeLate && listener.request === currentRequest)
        listener.stop()

        listener.begin()
        check("a genuinely new session retries analyzer after prior fallback", listener.analyzerFailures == 0 && !listener.analyzerDisabledForSession && listener.usingAnalyzer && listener.analyzerEngine != nil)
        listener.stop()

        let stopping = LifecycleListener()
        stopping.isListening = true
        stopping.startRecognition()
        let stoppingEngine = stopping.analyzerEngine!
        stoppingEngine.onResult?("recognized final tail", false)
        drain()
        stopping.stop()
        check("normal Stop hands recognized tail to serial delivery once", stopping.delivered == ["recognized final tail"])
        check("normal Stop finishes engine and stops microphone intent", stoppingEngine.finished && !stopping.isListening && stopping.analyzerEngine == nil)
        stoppingEngine.onResult?("late retired result", true)
        stoppingEngine.onError?()
        drain()
        check("late callbacks after Stop cannot restart or duplicate delivery", stopping.delivered == ["recognized final tail"] && stopping.analyzerEngine == nil && !stopping.isListening)

        let progressive = LifecycleListener()
        progressive.begin()
        let progressiveEngine = progressive.analyzerEngine!
        progressiveEngine.onResult?("first settled phrase", true)
        drain()
        check("analyzer finalization does not retire its request", progressive.analyzerEngine === progressiveEngine && !progressiveEngine.finished)
        check("analyzer finalization flushes its phrase immediately", progressive.delivered == ["first settled phrase"] && progressive.pendingTail.isEmpty)
        progressive.stop()
        check("settled analyzer phrase still delivers on ordinary Stop", progressive.delivered == ["first settled phrase"])

        ListenEnginePolicy.usesAnalyzerNow = false
        let legacyFinal = LifecycleListener()
        legacyFinal.begin()
        let legacyBefore = legacyFinal.task
        legacyFinal.recognizer!.callbacks.last!(RecognitionResult(bestTranscription: .init(formattedString: "legacy task tail"), isFinal: true), nil)
        drain()
        check("legacy final still flushes and retires task", legacyFinal.delivered == ["legacy task tail"] && legacyFinal.task !== legacyBefore)
        legacyFinal.stop()
        ListenEnginePolicy.usesAnalyzerNow = true
    }

    static func analyzerPhraseChecks() {
        ListenEnginePolicy.usesAnalyzerNow = true
        let repeated = LifecycleListener()
        repeated.begin()
        let repeatingEngine = repeated.analyzerEngine!
        repeatingEngine.onResult?("yes please", true)
        drain()
        repeated.flushTail(reason: .gap)
        repeatingEngine.onResult?("yes please", true)
        drain()
        repeated.stop()
        check("two identical finalized phrases are both delivered", repeated.delivered == ["yes please", "yes please"])

        let different = LifecycleListener()
        different.begin()
        let differentEngine = different.analyzerEngine!
        differentEngine.onResult?("the first phrase", true)
        drain()
        differentEngine.onResult?("the second phrase", true)
        drain()
        check("distinct finalized phrases keep one analyzer and two full lines", different.analyzerEngine === differentEngine && different.delivered == ["the first phrase", "the second phrase"])
        different.stop()

        // The shipping .transcription preset is final-only. These two cases
        // constrain the adapter's ordinary in-order revision behavior without
        // claiming support for arbitrary overlapping volatile result ranges.
        let revision = LifecycleListener()
        revision.begin()
        let revisionEngine = revision.analyzerEngine!
        revisionEngine.onResult?("send the blue folder", false)
        drain()
        revisionEngine.onResult?("send the green folder", true)
        drain()
        check("a volatile-to-final revision delivers the settled phrase once", revision.delivered == ["send the green folder"] && revision.pendingTail.isEmpty && revision.analyzerEngine === revisionEngine)
        revision.stop()

        let gap = LifecycleListener()
        gap.begin()
        let gapEngine = gap.analyzerEngine!
        gapEngine.onResult?("already heard once", false)
        drain()
        gap.flushTail(reason: .gap)
        gapEngine.onResult?("already heard once", true)
        drain()
        check("finalizing an already gap-flushed phrase does not repeat it", gap.delivered == ["already heard once"])
        gapEngine.onResult?("already heard once", true)
        drain()
        check("the next identical phrase survives a previously gap-flushed final", gap.delivered == ["already heard once", "already heard once"])
        gap.stop()

        let old = LifecycleListener()
        old.begin()
        let oldEngine = old.analyzerEngine!
        let born = Date().addingTimeInterval(-180)
        old.requestBornAt = born
        old.analyzerFailures = 2
        oldEngine.onResult?("fresh words on an old request", true)
        drain()
        let received = old.lastPartialAt
        old.watchdog?.fire()
        check("fresh final speech keeps an aged analyzer alive", old.analyzerEngine === oldEngine && !oldEngine.finished)
        check("phrase reset retains real speech clock, request age and failure budget", received != nil && old.lastPartialAt == received && old.requestBornAt == born && old.analyzerFailures == 2)
        old.stop()
    }

    static func enrollmentChecks() {
        // The real deliver body is extracted: an enrolled sample must not
        // reach onLine even if the recognizer already placed it in the cursor.
        resetPermissions()
        let fresh = LifecycleListener()
        fresh.startForEnrollment()
        grantSpeech()
        grantMic()
        check("fresh enrollment opens only sample capture, not recognition", fresh.isListening && fresh.enrolling && fresh.task == nil && fresh.analyzerEngine == nil)
        fresh.feedRecognitionAudio(40)
        check("fresh sample audio is not held for a future transcript", fresh.orphanBuffers.isEmpty)
        _ = fresh.cursor.observe("private enrollment sample")
        fresh.stopAfterEnrollment()
        check("fresh enrollment never delivers its recognized sample", fresh.delivered.isEmpty)
        check("fresh enrollment closes and clears its transcript cursor", !fresh.isListening && !fresh.enrolling && fresh.pendingTail.isEmpty)

        for analyzer in [true, false] {
            ListenEnginePolicy.usesAnalyzerNow = analyzer
            let listener = LifecycleListener()
            listener.begin()
            let retiredAnalyzer = listener.analyzerEngine
            let retiredRequest = listener.request
            let retiredLegacy = listener.recognizer?.callbacks.last
            listener.absorbRecognized("ambient words before sample", isFinal: false)
            retiredAnalyzer?.onResult?("result already queued at enrollment entry", false)
            retiredLegacy?(RecognitionResult(bestTranscription: .init(formattedString: "result already queued at enrollment entry"), isFinal: false), nil)
            listener.startForEnrollment()
            drain()
            check("entry preserves already recognized ambient words (analyzer: \(analyzer))", listener.delivered == ["ambient words before sample"])
            check("enrollment retires the recognizer before sample (analyzer: \(analyzer))", listener.request == nil && listener.task == nil && listener.analyzerEngine == nil && listener.pendingTail.isEmpty)
            listener.feedRecognitionAudio(41)
            check("enrollment audio never enters orphan replay (analyzer: \(analyzer))", listener.orphanBuffers.isEmpty)
            check("enrollment audio never reaches retired recognizer (analyzer: \(analyzer))", retiredAnalyzer?.buffers.isEmpty != false && retiredRequest?.buffers.isEmpty != false)
            listener.watchdog?.fire()
            check("enrollment watchdog cannot restart transcription (analyzer: \(analyzer))", listener.task == nil && listener.analyzerEngine == nil)
            // Late callbacks queued before or during the sample retain the
            // retired request identity; neither side of exit may adopt them.
            retiredAnalyzer?.onResult?("queued enrollment words", false)
            retiredLegacy?(RecognitionResult(bestTranscription: .init(formattedString: "queued enrollment words"), isFinal: false), nil)
            drain()
            _ = listener.cursor.observe("sample that must be discarded")
            listener.stopAfterEnrollment()
            check("ambient enrollment resumes from an empty cursor (analyzer: \(analyzer))", listener.isListening && !listener.enrolling && listener.pendingTail.isEmpty)
            retiredAnalyzer?.onResult?("late enrollment final", true)
            retiredLegacy?(RecognitionResult(bestTranscription: .init(formattedString: "late enrollment final"), isFinal: true), nil)
            drain()
            listener.absorbRecognized("ordinary speech after sample", isFinal: false)
            listener.stop()
            check("sample and late callbacks never become ambient transcript (analyzer: \(analyzer))", listener.delivered == ["ambient words before sample", "ordinary speech after sample"])
        }
        ListenEnginePolicy.usesAnalyzerNow = true

        let cancelled = LifecycleListener()
        cancelled.begin()
        cancelled.startForEnrollment()
        cancelled.stop() // Sign-out/owner Stop during enrollment.
        cancelled.stopAfterEnrollment()
        check("enrollment completion cannot undo an intervening Stop", !cancelled.isListening && cancelled.analyzerEngine == nil && cancelled.task == nil)

        for ambient in [false, true] {
            resetPermissions()
            let restarted = LifecycleListener()
            if ambient { restarted.begin() }
            restarted.startForEnrollment()
            if !ambient { grantSpeech(); grantMic() }
            restarted.stop() // Same cancellation boundary used by sign-out.
            check("Stop closes enrollment state after protecting its tail (ambient: \(ambient))", !restarted.enrolling && !restarted.wasListeningBeforeEnrollment)
            resetPermissions()
            restarted.start()
            grantSpeech()
            grantMic()
            let newEngine = restarted.analyzerEngine
            check("new Start after cancelled enrollment starts real recognition (ambient: \(ambient))", restarted.isListening && !restarted.enrolling && newEngine != nil)
            restarted.stopAfterEnrollment() // Delayed old sheet cleanup.
            check("old enrollment cleanup cannot stop a new session (ambient: \(ambient))", restarted.isListening && !restarted.enrolling && restarted.analyzerEngine === newEngine && newEngine != nil)
            restarted.stop()
        }
    }
}
