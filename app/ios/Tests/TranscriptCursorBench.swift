import Foundation

// What one recognizer callback costs. TranscriptCursor runs on the MAIN THREAD
// inside `SFSpeechRecognitionTask`'s handler, several times a second, for as
// long as somebody is talking. A cost that grows with the length of the request
// would be invisible in a one-sentence test and would make the app stutter in a
// two-minute conversation, so the number that matters is not the average — it
// is whether the average moves as the request gets longer.
//
//   sh app/ios/Tests/run_cursor_bench.sh
//
// This asserts nothing. It prints, and it prints the shape of the curve as well
// as the numbers, because a number in a comment cannot be run and a number
// without its curve cannot be trusted. (The header of TranscriptCursor.swift
// once quoted timings from a bench script that had never been committed. This
// is that script, written for real.)

let bounded = "so I told Eric that the Nicholson deal is dead and we should call "
    + "Baylor before the quarter closes because nobody else will pick up that "
    + "account and I said I would let him know before Friday if the numbers "
    + "move at all which they might given what the clinic said about the "
    + "referral and the review that Priya has to run before anyone signs "
    + "anything on Thursday morning in the office with Sam and the invoice "
    + "that went out late on Monday which is the part he actually cares about"

/// A callback stream shaped like a real request: a word at a time, with the
/// recognizer repeating itself, taking two words back and putting them straight
/// back, pushing a filler into text it has already shown, and blanking its
/// string — the four behaviours that decide which path inside the cursor runs.
func stream(words target: [String]) -> [String] {
    var steps: [String] = []
    var shown: [String] = []
    for (k, w) in target.enumerated() {
        shown.append(w)
        steps.append(shown.joined(separator: " "))
        if k % 5 == 3 { steps.append(shown.joined(separator: " ")) }
        if k % 7 == 6, shown.count > 2 {
            steps.append(shown[0..<(shown.count - 2)].joined(separator: " "))
            steps.append(shown.joined(separator: " "))
        }
        // The expensive path: an edit inside text already sent, which is the
        // only thing that reaches the alignment at all.
        if k % 9 == 8, shown.count > 3 {
            shown.insert("just", at: shown.count / 2)
            steps.append(shown.joined(separator: " "))
        }
        if k % 23 == 21 { steps.append("") }
    }
    return steps
}

/// Grow the corpus to `n` words by repeating it. Repetition is the HARD case
/// for a text cursor, not the easy one: every word the record holds appears
/// again later, so every coincidence the alignment could fall for is present.
func corpus(_ n: Int) -> [String] {
    let base = bounded.split(separator: " ").map(String.init)
    var out: [String] = []
    while out.count < n { out.append(contentsOf: base) }
    return Array(out.prefix(n))
}

struct Result {
    var words: Int
    var callbacks: Int
    var totalMs: Double
    var worstMs: Double
    var lines: Int
}

func measure(words n: Int, pauseEvery: Int) -> Result {
    let steps = stream(words: corpus(n))
    var cursor = TranscriptCursor()
    var lines = 0
    var total = 0.0
    var worst = 0.0
    for (k, text) in steps.enumerated() {
        let t0 = DispatchTime.now().uptimeNanoseconds
        if cursor.observe(text).banked != nil { lines += 1 }
        if k % pauseEvery == pauseEvery - 1, cursor.takePending() != nil { lines += 1 }
        let dt = Double(DispatchTime.now().uptimeNanoseconds - t0) / 1_000_000
        total += dt
        worst = max(worst, dt)
    }
    if cursor.takePending() != nil { lines += 1 }
    return Result(words: n, callbacks: steps.count, totalMs: total, worstMs: worst, lines: lines)
}

@main
struct TranscriptCursorBench {
    static func main() {
        // 2.6s of silence cuts a line, so a talker at ~150 wpm flushes every
        // 30-odd words; the sweep also runs a request that never pauses, which
        // is the worst case for the record and the one the app hits when
        // somebody talks straight through.
        let sizes = [50, 100, 200, 400, 800]
        print("TranscriptCursor cost per recognizer callback")
        print("  main thread, one callback = one observe() plus any takePending()")
        print("  the corpus repeats, so every word in the record appears again later")
        print("")
        for (label, pauseEvery) in [("flushes every ~30 words", 30), ("never pauses", 1 << 30)] {
            print("  \(label)")
            print("    words  callbacks     mean ms     worst ms   lines")
            var previousMean = 0.0
            for n in sizes {
                let r = measure(words: n, pauseEvery: pauseEvery)
                let mean = r.totalMs / Double(r.callbacks)
                let drift = previousMean == 0 ? "" :
                    String(format: "   (x%.2f on the previous size)", mean / previousMean)
                previousMean = mean
                print(String(format: "    %5d  %9d  %10.4f  %11.4f  %6d%@",
                             r.words, r.callbacks, mean, r.worstMs, r.lines,
                             drift as NSString))
            }
            print("")
        }
        print("  What to look at: the x-factor column. Doubling the request should")
        print("  not double the mean. If it does, the windowing in placeBoundary")
        print("  has stopped working and a long conversation will stutter.")
    }
}
