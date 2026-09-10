import Foundation

// Production source-boundary probes. These do not use real audio or
// Apple's model and do not certify device capture. See the runner for exactly
// which production method bodies are compiled and which edges are doubled.
struct AVAudioPCMBuffer { let sequence: Int }
struct AVAudioFormat {
    init() {}
    init?(standardFormatWithSampleRate: Double, channels: Int) {}
}
struct AnalyzerInput {}
struct ProbeResult { let text: AttributedString; let isFinal: Bool }
enum ProbeFailure: Error { case finalizer, results }

final class SpeechTranscriber {
    static var isAvailable = true
    static var holdLocale = false
    static var pendingLocale: CheckedContinuation<Locale?, Never>?
    static var localeRequests = 0
    static func supportedLocale(equivalentTo locale: Locale) async -> Locale? {
        localeRequests += 1
        if !holdLocale { return locale }
        return await withCheckedContinuation { pendingLocale = $0 }
    }
    enum Preset { case transcription }
    let results: AsyncThrowingStream<ProbeResult, Error>
    private var continuation: AsyncThrowingStream<ProbeResult, Error>.Continuation!
    init(locale: Locale = Locale(identifier: "en_US"), preset: Preset = .transcription) {
        var builder: AsyncThrowingStream<ProbeResult, Error>.Continuation!
        results = AsyncThrowingStream { builder = $0 }
        continuation = builder
    }
    func emit(_ text: String) { continuation.yield(ProbeResult(text: AttributedString(text), isFinal: true)) }
    func complete() { continuation.finish() }
    func fail(cancelled: Bool = false) {
        continuation.finish(throwing: cancelled ? CancellationError() : ProbeFailure.results)
    }
}

enum AssetInventory {
    static var throwsCancellation = false
    struct Installation { func downloadAndInstall() async throws {} }
    static func assetInstallationRequest(supporting: [SpeechTranscriber]) async throws -> Installation? {
        if throwsCancellation { throw CancellationError() }
        return nil
    }
}

final class SpeechAnalyzer {
    private let lock = NSLock()
    private var starts = 0
    private var finalizations = 0
    var module: SpeechTranscriber?
    var finalWords: [String] = []
    var holdResultsCompletion = false
    var finalizationFails = false
    var finalizationCancels = false
    var startCancels = false
    init(modules: [SpeechTranscriber] = []) { module = modules.first }
    static func bestAvailableAudioFormat(compatibleWith: [SpeechTranscriber]) async -> AVAudioFormat? { AVAudioFormat() }
    var startCount: Int { lock.lock(); defer { lock.unlock() }; return starts }
    var finishCount: Int { lock.lock(); defer { lock.unlock() }; return finalizations }
    private func noteStart() { lock.lock(); starts += 1; lock.unlock() }
    private func noteFinish() { lock.lock(); finalizations += 1; lock.unlock() }
    func start(inputSequence: AsyncStream<AnalyzerInput>) async throws {
        noteStart()
        if startCancels { throw CancellationError() }
        // Apple's autonomous start returns immediately, not when audio ends.
    }
    func finalizeAndFinishThroughEndOfInput() async throws {
        if finalizationFails {
            module?.complete()
            noteFinish()
            if finalizationCancels { throw CancellationError() }
            throw ProbeFailure.finalizer
        }
        for text in finalWords { module?.emit(text) }
        noteFinish()
        if !holdResultsCompletion { module?.complete() }
    }
    func cancelAndFinishNow() async { module?.complete() }
}

final class AnalyzerBoundaryEngine {
    let desiredLocale = Locale(identifier: "en_US")
    var onResult: ((String, Bool) -> Void)?
    var onError: (() -> Void)?
    var onFinished: (() -> Void)?
    var transcriber: SpeechTranscriber?
    var analyzer: SpeechAnalyzer?
    var builder: AsyncStream<AnalyzerInput>.Continuation?
    var targetFormat: AVAudioFormat?
    var held: [AVAudioPCMBuffer] = []
    var finished = false
    var cancelled = false
    var failureReported = false
    var provisioningTask: Task<Void, Never>?
    var startTask: Task<Void, Never>?
    var resultsTask: Task<Void, Never>?
    var finalizationTask: Task<Void, Never>?
    var cancellationTask: Task<Void, Never>?
    let queue = DispatchQueue(label: "test.anticipy.analyzer-boundary")
    var converted: [Int] = []
    // Conversion is intentionally a double: we measure lifecycle ownership,
    // not sample fidelity. Neither AVFoundation nor Speech is imported.
    func convertAndYield(_ buffer: AVAudioPCMBuffer) {
        converted.append(buffer.sequence)
        builder?.yield(AnalyzerInput())
    }
    func drainAudioQueue() { queue.sync {} }
}

final class SpeakerFIFOProbe {
    var deliveryGeneration = 0
    let embeddingQueue = DispatchQueue(label: "test.anticipy.speaker-fifo")
}

@MainActor final class CompletionProbe { var done = false }

@main @MainActor struct AnalyzerLifecycleBoundaryTests {
    static var checks = 0
    static var failures = 0
    static func check(_ name: String, _ condition: Bool) {
        checks += 1
        if condition { print("PASS: \(name)") }
        else { failures += 1; print("FAIL: \(name)") }
    }
    static func drainMain() {
        var completed = false
        DispatchQueue.main.async { DispatchQueue.main.async { completed = true } }
        let deadline = Date().addingTimeInterval(1)
        while !completed, Date() < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.002))
        }
        if !completed { print("UNPROVEN: main queue did not drain"); exit(2) }
    }
    static func waitForStart(_ analyzer: SpeechAnalyzer) {
        let deadline = Date().addingTimeInterval(1)
        while analyzer.startCount == 0, Date() < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.002))
        }
    }
    static func waitUntil(_ condition: () -> Bool) {
        let deadline = Date().addingTimeInterval(1)
        while !condition(), Date() < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.002))
        }
    }

    static func main() {
        print("SOURCE-BODY REGRESSIONS: not a device or live-agent test")
        repeatedResumeStress()
        immediateStopTail()
        drainingBoundaries()
        stoppedWarmUp()
        warmUpOverflow()
        engineTaskOwnership()
        provisioningCancellation()
        readBeforeFinished()
        realSpeakerFIFO()
        failedEnginesCannotFinishSuccessfully()
        unexpectedCancellationReportsFailure()
        print("Analyzer boundaries: \(checks) checks, \(failures) failures")
        if failures > 0 { exit(1) }
    }

    static func repeatedResumeStress() {
        ListenEnginePolicy.usesAnalyzerNow = true
        let listener = LifecycleListener()
        for session in 0..<40 {
            let before = listener.delivered.count
            listener.begin()
            guard let engine = listener.analyzerEngine else {
                print("UNPROVEN: stress fixture did not start analyzer"); exit(2)
            }
            for _ in 0..<3 { engine.onResult?("same repeated phrase", true) }
            drainMain()
            listener.watchdog?.fire()
            let afterPhrases = listener.delivered.count
            check("three identical phrases survive session \(session)", afterPhrases - before == 3)
            check("watchdog retains healthy analyzer in session \(session)", listener.analyzerEngine === engine)
            listener.stop()
            engine.onResult?("obsolete callback", true)
            drainMain()
            check("Stop and stale callback preserve count in session \(session)", !listener.isListening && listener.delivered.count == afterPhrases)
        }
        print("MEASURED: \(listener.delivered.count) of 120 controlled final phrases delivered across 40 sessions")
    }

    static func immediateStopTail() {
        let listener = LifecycleListener()
        listener.begin()
        guard let engine = listener.analyzerEngine else {
            print("UNPROVEN: Stop fixture did not start analyzer"); exit(2)
        }
        listener.feedRecognitionAudio(7)
        check("tail fixture hands audio to the current analyzer before Stop", engine.buffers == [7])
        listener.stopAfterCurrentAudio { true }
        check("Stop requests finalization without restarting microphone", engine.finished && !listener.isListening)
        // Model-double result for audio accepted BEFORE Stop, arriving when
        // the real async finalize operation is allowed to return its tail.
        engine.onResult?("words captured before stop", true)
        drainMain()
        check("same-session asynchronous finalization preserves its captured tail", listener.delivered == ["words captured before stop"])
        // This expectation must never be implemented by removing the identity
        // guard: account exit/enrollment/new sessions need their own fencing.
        engine.onFinished?()
        drainMain()
        check("all read final results release the retiring identity", listener.finishingAnalyzers.isEmpty)
        engine.onResult?("after completed stream", true)
        drainMain()
        check("completed stream cannot append another late callback", listener.delivered.count == 1)
    }

    static func drainingBoundaries() {
        let listener = LifecycleListener()
        var frames: [(String, Date, Date)] = []
        listener.onLine = { line, start, end, _ in frames.append((line, start, end)) }
        listener.begin()
        let original = listener.analyzerEngine!
        listener.requestBornAt = Date().addingTimeInterval(-8)
        let originalStart = listener.requestBornAt
        original.onResult?("already queued before stop", true)
        // Do not drain main: exercise a result whose old callback was queued
        // before ownership moved into the finalization slot.
        listener.stopAfterCurrentAudio { true }
        let stoppedBy = Date()
        listener.begin()
        let newer = listener.analyzerEngine!
        newer.onResult?("new session partial", false)
        original.onResult?("late original tail", true)
        drainMain()
        check("pre-Stop queued callback transfers into the original drain", frames.contains { $0.0 == "already queued before stop" })
        check("late final survives rapid restart without changing active cursor", listener.analyzerEngine === newer && listener.pendingTail == "new session partial" && frames.contains { $0.0 == "late original tail" })
        check("late final retains original capture envelope, not delivery clock", frames.allSatisfy { $0.1 == originalStart && $0.2 <= stoppedBy })
        listener.stop()
        original.onResult?("private after account discard", true)
        drainMain()
        check("default Stop cancels retiring audio as an account boundary", original.cancelled && listener.finishingAnalyzers.isEmpty && !frames.contains { $0.0 == "private after account discard" })

        for change in ["account", "token", "enrollment", "forget"] {
            let value = LifecycleListener()
            var current = true
            value.begin()
            let old = value.analyzerEngine!
            value.stopAfterCurrentAudio { current }
            if change == "account" || change == "token" { current = false }
            else if change == "enrollment" { value.startForEnrollment() }
            else { value.discardCapturedAudio() }
            old.onResult?("private old words", true)
            drainMain()
            check("\(change) cannot adopt a delayed final", value.delivered.isEmpty)
            value.stop()
        }

        let queued = LifecycleListener()
        let speaker = LifecycleSpeaker()
        speaker.holdDeliveries = true
        queued.speaker = speaker
        var lease = true
        queued.begin()
        let delayed = queued.analyzerEngine!
        queued.stopAfterCurrentAudio { lease }
        delayed.onResult?("FIFO final", true)
        delayed.onFinished?()
        drainMain()
        check("finalizer retains identity while a FIFO delivery is pending", queued.delivered.isEmpty && queued.finishingAnalyzers.count == 1 && speaker.pending.count == 2)
        lease = false
        speaker.releaseDeliveries()
        check("delivery rechecks account lease after speaker FIFO barrier", queued.delivered.isEmpty && queued.finishingAnalyzers.isEmpty)

        let success = LifecycleListener()
        let heldSpeaker = LifecycleSpeaker()
        heldSpeaker.holdDeliveries = true
        success.speaker = heldSpeaker
        success.begin()
        let tail = success.analyzerEngine!
        success.stopAfterCurrentAudio { true }
        tail.onResult?("ordered one", true)
        tail.onResult?("ordered two", true)
        tail.onFinished?()
        drainMain()
        heldSpeaker.releaseDeliveries()
        check("all final phrases precede identity retirement in FIFO order", success.delivered == ["ordered one", "ordered two"] && success.finishingAnalyzers.isEmpty)

        let timed = LifecycleListener()
        timed.begin()
        let timeoutEngine = timed.analyzerEngine!
        timed.stopAfterCurrentAudio { true }
        timed.finishingAnalyzers.values.first!.timeout.perform()
        timeoutEngine.onResult?("too late", true)
        drainMain()
        check("deadline cancels work and exposes finalization failure", timeoutEngine.cancelled && timed.finalizationFailed && timed.delivered.isEmpty && timed.finishingAnalyzers.isEmpty)
        timed.discardCapturedAudio()
        check("privacy discard clears the prior account's finalization status", !timed.finalizationFailed)

        let bounded = LifecycleListener()
        var requests: [SpeechAnalyzerRequestEngine] = []
        for _ in 0..<5 {
            bounded.begin()
            requests.append(bounded.analyzerEngine!)
            bounded.stopAfterCurrentAudio { true }
        }
        check("rapid stops keep a bounded retirement set and report exhausted budget", bounded.finishingAnalyzers.count == 4 && requests.filter(\.cancelled).count == 1 && bounded.finalizationFailed)
        bounded.discardCapturedAudio()
        check("privacy discard cancels every pending finalizer", requests.allSatisfy(\.cancelled) && bounded.finishingAnalyzers.isEmpty)

        let discarded = LifecycleListener()
        discarded.begin()
        discarded.analyzerEngine!.onResult?("unsaved private partial", false)
        drainMain()
        discarded.discardCapturedAudio()
        check("forget/storage discard publishes no known or asynchronous tail", discarded.delivered.isEmpty && discarded.pendingTail.isEmpty)
        let refused = LifecycleListener()
        refused.begin()
        refused.analyzerEngine!.onResult?("not licensed for this owner", false)
        drainMain()
        refused.stopAfterCurrentAudio { false }
        check("an already-invalid Stop lease discards even a recognized tail", refused.delivered.isEmpty && refused.pendingTail.isEmpty && refused.finishingAnalyzers.isEmpty)
    }

    static func stoppedWarmUp() {
        let engine = AnalyzerBoundaryEngine()
        engine.finish()
        engine.drainAudioQueue()
        check("warm-up fixture is already finished", engine.finished)
        // Models begin() resuming after its locale/assets await. The method
        // invoked here is the exact real warmUp body, not a replay of its logic.
        let analyzer = SpeechAnalyzer()
        let stream = engine.makeStream()
        engine.warmUp(analyzer: analyzer, transcriber: SpeechTranscriber(),
                      stream: stream, format: AVAudioFormat())
        engine.drainAudioQueue()
        waitForStart(analyzer)
        check("finished engine refuses to install analyzer state", engine.analyzer == nil)
        check("finished engine cannot launch analyzer task after warm-up resumes", analyzer.startCount == 0)
        check("probe did not capture or convert new audio", engine.converted.isEmpty)
        // Close the controlled stream so this intentionally failing fixture
        // does not leave its fake task parked until process exit.
        engine.builder?.finish()
    }

    static func warmUpOverflow() {
        let engine = AnalyzerBoundaryEngine()
        var errors = 0
        engine.onError = { errors += 1 }
        for sequence in 0..<601 { engine.append(AVAudioPCMBuffer(sequence: sequence)) }
        engine.drainAudioQueue()
        // append queues the coalesced failure report onto the engine queue;
        // that nested block can be behind the first barrier. Await the actual
        // callback instead of assuming two main-queue turns join that work.
        waitUntil { errors > 0 }
        drainMain()
        check("warm-up fixture retains the first 600 buffers in order", engine.held.map(\.sequence) == Array(0..<600))
        check("warm-up overflow is retained or explicitly reported, never silently lost", engine.held.count == 601 || errors > 0)
        engine.finish()
        engine.drainAudioQueue()
    }

    static func engineTaskOwnership() {
        let value = AnalyzerBoundaryEngine()
        let analyzer = SpeechAnalyzer()
        value.warmUp(analyzer: analyzer, transcriber: SpeechTranscriber(),
                     stream: value.makeStream(), format: AVAudioFormat())
        value.drainAudioQueue()
        waitForStart(analyzer)
        check("warm-up installs ownership of start and results tasks atomically", value.startTask != nil && value.resultsTask != nil && analyzer.startCount == 1)
        value.finish()
        value.drainAudioQueue()
        check("finish owns its asynchronous finalizer", value.finalizationTask != nil)
        value.cancel()
        value.drainAudioQueue()
        check("privacy cancel fences and cancels every owned task", value.cancelled && value.startTask?.isCancelled == true && value.resultsTask?.isCancelled == true && value.finalizationTask?.isCancelled == true && value.analyzer == nil)
        value.append(AVAudioPCMBuffer(sequence: 999))
        value.drainAudioQueue()
        check("cancelled engine never adopts another audio buffer", !value.converted.contains(999) && value.held.isEmpty)
    }

    static func provisioningCancellation() {
        for privacyDiscard in [false, true] {
            SpeechTranscriber.holdLocale = true
            SpeechTranscriber.pendingLocale = nil
            let value = AnalyzerBoundaryEngine()
            value.begin()
            waitUntil { SpeechTranscriber.pendingLocale != nil }
            check("begin owns suspended provisioning task (discard: \(privacyDiscard))", value.provisioningTask != nil && SpeechTranscriber.pendingLocale != nil)
            if privacyDiscard { value.cancel() } else { value.finish() }
            value.drainAudioQueue()
            SpeechTranscriber.pendingLocale?.resume(returning: Locale(identifier: "en_US"))
            SpeechTranscriber.pendingLocale = nil
            drainMain()
            value.drainAudioQueue()
            check("completed provisioning cannot launch after stop (discard: \(privacyDiscard))", value.provisioningTask?.isCancelled == true && value.startTask == nil && value.resultsTask == nil && value.analyzer == nil)
            SpeechTranscriber.holdLocale = false
        }
        let stopped = AnalyzerBoundaryEngine()
        stopped.cancel()
        stopped.drainAudioQueue()
        let requests = SpeechTranscriber.localeRequests
        stopped.begin()
        stopped.drainAudioQueue()
        drainMain()
        check("begin after cancellation cannot even request assets or locale", stopped.provisioningTask == nil && SpeechTranscriber.localeRequests == requests)
    }

    static func readBeforeFinished() {
        let value = AnalyzerBoundaryEngine()
        let transcriber = SpeechTranscriber()
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        analyzer.finalWords = ["first finalized", "last finalized"]
        analyzer.holdResultsCompletion = true
        var observed: [String] = []
        value.onResult = { text, _ in observed.append(text) }
        value.onFinished = { observed.append("finished") }
        value.warmUp(analyzer: analyzer, transcriber: transcriber,
                     stream: value.makeStream(), format: AVAudioFormat())
        value.drainAudioQueue()
        waitForStart(analyzer)
        value.finish()
        waitUntil { analyzer.finishCount > 0 && observed.count == 2 }
        check("finalizer return alone cannot retire the unread result stream", observed == ["first finalized", "last finalized"])
        transcriber.complete()
        waitUntil { observed.count == 3 }
        check("onFinished follows every published result after reader completion", observed == ["first finalized", "last finalized", "finished"])
        value.cancel()
        value.drainAudioQueue()

        let failedWarmup = AnalyzerBoundaryEngine()
        var errors = 0
        var done = false
        failedWarmup.onError = { errors += 1 }
        failedWarmup.onFinished = { done = true }
        failedWarmup.append(AVAudioPCMBuffer(sequence: 1))
        failedWarmup.finish()
        failedWarmup.drainAudioQueue()
        drainMain()
        check("Stop during asset warm-up reports held audio loss instead of success", errors == 1 && done && failedWarmup.held.isEmpty)
    }

    static func realSpeakerFIFO() {
        let speaker = SpeakerFIFOProbe()
        var observed: [Int] = []
        speaker.afterPendingDeliveries { observed.append(1) }
        speaker.afterPendingDeliveries { observed.append(2) }
        speaker.embeddingQueue.sync {}
        drainMain()
        check("production speaker barrier delivers in queue order", observed == [1, 2])
        speaker.afterPendingDeliveries { observed.append(3) }
        speaker.embeddingQueue.sync {}
        speaker.deliveryGeneration += 1
        drainMain()
        check("production speaker barrier rejects a changed delivery generation", observed == [1, 2])
    }

    static func failedEnginesCannotFinishSuccessfully() {
        for stage in ["finalizer", "results", "finalizer-cancelled", "results-cancelled"] {
            let value = AnalyzerBoundaryEngine()
            let transcriber = SpeechTranscriber()
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            analyzer.finalizationFails = stage.hasPrefix("finalizer")
            analyzer.finalizationCancels = stage == "finalizer-cancelled"
            var errors = 0
            var finished = 0
            value.onError = { errors += 1 }
            value.onFinished = { finished += 1 }
            value.warmUp(analyzer: analyzer, transcriber: transcriber,
                         stream: value.makeStream(), format: AVAudioFormat())
            value.drainAudioQueue()
            waitForStart(analyzer)
            if stage.hasPrefix("results") {
                transcriber.fail(cancelled: stage == "results-cancelled")
                waitUntil { errors == 1 }
            }
            value.finish()
            waitUntil { errors > 0 }
            // Queue a completion sentinel only after the owned finalizer is
            // done; it makes a falsely-successful callback deterministic.
            let finalizerDone = CompletionProbe()
            value.drainAudioQueue()
            let task = value.finalizationTask
            Task { await task?.value; await MainActor.run { finalizerDone.done = true } }
            waitUntil { finalizerDone.done }
            drainMain()
            check("\(stage) failure cannot signal successful finalization", errors == 1 && finished == 0 && finalizerDone.done)
            value.cancel()
            value.drainAudioQueue()
        }
    }

    static func unexpectedCancellationReportsFailure() {
        let starting = AnalyzerBoundaryEngine()
        let transcriber = SpeechTranscriber()
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        analyzer.startCancels = true
        var startErrors = 0
        var startFinished = 0
        starting.onError = { startErrors += 1 }
        starting.onFinished = { startFinished += 1 }
        starting.warmUp(analyzer: analyzer, transcriber: transcriber,
                        stream: starting.makeStream(), format: AVAudioFormat())
        starting.drainAudioQueue()
        waitUntil { startErrors > 0 }
        starting.finish()
        starting.drainAudioQueue()
        let joined = CompletionProbe()
        let finalizer = starting.finalizationTask
        Task { await finalizer?.value; await MainActor.run { joined.done = true } }
        waitUntil { joined.done }
        drainMain()
        check("underlying start cancellation reports failure without successful finish", startErrors == 1 && startFinished == 0 && joined.done)
        starting.cancel()
        starting.drainAudioQueue()

        let provisioning = AnalyzerBoundaryEngine()
        var provisioningErrors = 0
        provisioning.onError = { provisioningErrors += 1 }
        AssetInventory.throwsCancellation = true
        provisioning.begin()
        waitUntil { provisioningErrors > 0 }
        provisioning.drainAudioQueue()
        check("underlying asset cancellation reports provisioning failure", provisioningErrors == 1 && provisioning.startTask == nil)
        AssetInventory.throwsCancellation = false
        provisioning.cancel()
        provisioning.drainAudioQueue()

        let privacy = AnalyzerBoundaryEngine()
        let privacyTranscriber = SpeechTranscriber()
        let privacyAnalyzer = SpeechAnalyzer(modules: [privacyTranscriber])
        var privacyErrors = 0
        var privacyFinished = 0
        privacy.onError = { privacyErrors += 1 }
        privacy.onFinished = { privacyFinished += 1 }
        privacy.warmUp(analyzer: privacyAnalyzer, transcriber: privacyTranscriber,
                       stream: privacy.makeStream(), format: AVAudioFormat())
        privacy.drainAudioQueue()
        waitForStart(privacyAnalyzer)
        privacy.cancel()
        privacy.drainAudioQueue()
        privacyTranscriber.fail(cancelled: true)
        drainMain()
        check("requested privacy cancellation stays silent and cannot finish successfully", privacyErrors == 0 && privacyFinished == 0 && privacy.resultsTask?.isCancelled == true)
    }
}
