import Foundation

// A randomised DIFFERENTIAL fuzzer for TranscriptCursor, plus a REPLAY of the
// real shredded lines from Omar's feed.
//
// Written from scratch, and deliberately not the property tests in
// TranscriptCursorTests.swift again. Those assert the type's invariants
// against schedules this codebase invented, and they share an assumption with
// the type: case 15 says outright that "letting two windows share words would
// not make the test stricter". That assumption is false, and it is exactly
// where the type was broken — a decode window that resets onto a DIFFERENT
// sentence still opens on "so", "the", "we", "I", because English does not
// hand each sentence its own function words. A generator with perfectly
// disjoint vocabularies can never produce that callback, so no number of runs
// of it would have found the defect. This file does things differently:
//
//  1. A reset draws its CONTENT from a vocabulary no other window in the
//     session uses — that is what a decoder reset is — but every window also
//     draws from one SHARED function-word pool, and the first word of a fresh
//     window is biased toward it. That single coincidence is the whole test.
//
//  2. It is scored by LONGEST COMMON SUBSEQUENCE against what the recognizer
//     actually committed to, not by a greedy prefix walk. A greedy walk stops
//     at the first mismatch and calls everything after it lost, which flatters
//     whichever emitter repeats itself most — and the baseline here repeats
//     itself constantly. Words match with a tolerance of one edit so that
//     absorbing a respelling ("invoice" -> "invoices") is not scored as a
//     deletion; the tolerance is implemented here, not borrowed from the type
//     under test. Because an LCS is order-preserving, "every word exactly
//     once" and "in order" are one measurement: a word emitted out of order
//     cannot join the subsequence and is counted both lost and extra.
//
//  3. It judges against HEAD~1. `OldCursor` is the integer-cursor emission
//     layer from PhoneListener.swift at HEAD~1, with its timers replaced by
//     explicit calls. Every schedule runs through both, so the honesty wall —
//     never lose a word the old code kept — is a mechanical result rather than
//     a claim, and every disagreement prints its full callback trace.
//
//  4. It runs four populations, because one number cannot answer several
//     different questions honestly. See the MODES note below.
//
//   sh app/ios/Tests/run_cursor_fuzz.sh                # 100k sequences
//   sh app/ios/Tests/run_cursor_fuzz.sh 500000 1234    # more, another seed
//
// ---------------------------------------------------------------- THE MODES
//
// There are two classes of word no emitter of this shape can ever produce, and
// they have to be separated out or they drown the signal. BOTH are counted per
// run and printed; neither is a licence, because both are computed
// mechanically from the schedule and can only grow if the schedule generates
// more of them.
//
// (A) BURIED. When the recognizer inserts a word INTO a span it has already
//     shown — "meet at Cineplex" becoming "meet at the Cineplex" — and the
//     emitter has already SENT that span, the word cannot be delivered in
//     order. Sending it alone produces the one-word mid-sentence line that was
//     the reported bug ("Pill 491 kill 492"); sending the span again
//     duplicates a sentence. Cases 1 and 2 of the unit tests pin the choice
//     not to.
//
//     Burial is counted PER EMITTER, against what that emitter had actually
//     emitted at the moment of the edit — not against the last pause, which is
//     what an earlier version of this file used and which under-counted every
//     word buried by a bank instead of by a pause. Per-emitter is the fair
//     comparison and it cannot be gamed in the direction that matters: an
//     emitter that has sent nothing gets nothing excused, and an emitter that
//     sends eagerly to earn excuses pays for it in the duplication column.
//
// (B) SEAM-SHADOWED. Words that two consecutive decode windows OPEN ON in
//     common cannot be attributed to either of them, because the callback
//     stream is the same whichever it is. Both readings are behaviours this
//     same file generates on purpose elsewhere:
//
//       "at" | "at" | "at meeting" | ...
//           reading 1: a one-word window, then a new window opening on "at".
//           reading 2: one window, growing, that repeated itself once — the
//                      identical repeat of case 5, which the recognizer emits
//                      constantly while nobody is talking.
//
//       "that to trailer screening" | "that" | "that to" | ...
//           reading 1: a four-word window, then a new window opening "that to".
//           reading 2: one window that retracted and came partway back — the
//                      retract-and-restore of case 3, which the recognizer
//                      does on almost every sentence.
//
//     The count is the shared opening, measured against the new window both as
//     it GREW and as it ended up (an in-place edit is legal under both
//     readings, so the growth path counts too), capped at the length of either
//     window. It is printed on its own line so it can never grow quietly, and
//     it is the ONLY thing STRICT excuses.
//
//     This excuses the shape, not the choice. Which reading to take is a real
//     decision with a real cost, and it is pinned where a decision belongs —
//     case 16 of the unit tests, on the exact input, both directions.
//
//   STRICT      the recognizer only appends, takes words back and puts them
//               straight back, repeats itself, blanks its string, and resets
//               its window. Nothing already shown is ever edited in place, so
//               burial is structurally impossible and the gate is absolute:
//               ZERO lost beyond the shadowed seams, ZERO duplicated, no other
//               adjustment and no excuse.
//
//   INSERTION   adds mid-text insertion, so burial becomes possible. Gate:
//               losses beyond buried + shadowed are zero.
//
//   CHURN       adds respelling, outright substitution and retraction that
//               sticks. Same gate. Duplication is reported, not gated: a word
//               the recognizer retracts after it has already been emitted
//               cannot be unsaid by anybody.
//
// THE ONE THING STILL FAILING — "the edit-seam residual". Both populations
// that edit in place still delete a handful of words: at 33 333 sequences
// each, INSERTION 3 and CHURN 12, against roughly a million and a half
// committed words apiece. It is left FAILING rather than gated down to
// whatever number it currently produces, because a gate set to today's number
// is not a test, it is a bookmark.
//
// What is known about it: it needs an in-place edit. STRICT, which has none,
// is at a flat zero on the same run, so the rule that places the boundary is
// not what is wrong. Every instance found so far has the same shape — a tail
// is banked because the recognizer appeared to drop it, and the recognizer
// then rewrites the span that tail came from, so the rewritten words land
// under a line that has already gone out. Every one is printed with its full
// callback trace, so the next person starts from a repro, not a hunch.
//
//   REPLAY      not random at all. The real shredded fragment families from
//               Omar's feed, reconstructed into the partial-result sequences
//               that produce them, and run under EVERY single-pause schedule
//               and a set of multi-pause ones. Gate: the sentences come back
//               whole, once each, in order — on every schedule.
//
// Every raw number is printed next to the adjusted one, in both columns, so
// the adjustment is visible rather than assumed.
//
// NOTE ON THE REPLAY MATERIAL: Omar's actual sentences live in this file and
// nowhere else. Nothing in TranscriptCursor.swift knows a word of them, and a
// grep for any of them across the app source is the check that keeps it that
// way. A test may use real data; the thing under test may not.

// ------------------------------------------------------ the HEAD~1 baseline

/// The emission layer as it stood at HEAD~1 (commit ee84c3a), before
/// TranscriptCursor existed. Transcribed from
/// `git show HEAD~1:app/ios/Anticipy/Audio/PhoneListener.swift`: an `Int` index
/// into the word array of `bestTranscription.formattedString`, a shrink
/// detector comparing CHARACTER counts with a strictly-greater +10 threshold,
/// and the `minNewWords: 3` guard on the final path. `DispatchQueue`/`Timer`
/// are replaced by explicit `pause()` / `final(_:)` so a schedule can drive it.
///
/// It is the code that produced "Pill 491 kill 492". It is here to be the
/// floor, not the target: the wall says never worse than this, on any input.
///
/// Note the driver fires the pause timer at scheduled points for BOTH
/// emitters. At HEAD~1 `scheduleSilenceFlush()` re-armed on every callback, so
/// in production that timer usually never reached its deadline. Giving the old
/// cursor pauses it would not really have had makes it emit MORE, which can
/// only make the wall harder to clear. That is the direction to be generous in.
final class OldCursor: Emitter {
    private var partial = ""
    private var emittedWords = 0
    private(set) var lines: [String] = []
    private(set) var emittedWordCount = 0

    private var currentWords: [String] {
        partial.split(whereSeparator: { $0 == " " || $0 == "\n" }).map(String.init)
    }

    private func send(_ line: String) {
        lines.append(line)
        emittedWordCount += line.split(whereSeparator: { $0 == " " }).count
    }

    private func flushTail(minNewWords: Int = 1) {
        let words = currentWords
        guard words.count > emittedWords else {
            emittedWords = max(emittedWords, words.count)
            return
        }
        let fresh = Array(words[emittedWords...])
        emittedWords = words.count
        guard fresh.count >= minNewWords else { return }
        let line = fresh.joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !line.isEmpty else { return }
        send(line)
    }

    func observe(_ text: String) {
        if partial.count > text.count + 10 {
            flushTail()
            emittedWords = 0
        }
        partial = text
    }

    func pause() { flushTail() }

    func final(_ text: String) {
        observe(text)
        flushTail(minNewWords: 3)
        partial = ""
        emittedWords = 0
    }

    var joined: String { lines.joined(separator: " ") }
}

/// What the driver needs from either emitter. `emittedWordCount` is what makes
/// burial a per-emitter measurement instead of a guess.
protocol Emitter: AnyObject {
    var lines: [String] { get }
    var emittedWordCount: Int { get }
    var joined: String { get }
    func observe(_ text: String)
    func pause()
    func final(_ text: String)
}

/// The type under test, driven through exactly the calls PhoneListener makes.
final class NewCursor: Emitter {
    private var cursor = TranscriptCursor()
    private(set) var lines: [String] = []
    private(set) var emittedWordCount = 0

    private func send(_ line: String) {
        lines.append(line)
        emittedWordCount += line.split(whereSeparator: { $0 == " " }).count
    }

    func observe(_ text: String) {
        if let banked = cursor.observe(text).banked { send(banked) }
    }
    func pause() { if let line = cursor.takePending() { send(line) } }
    func final(_ text: String) {
        if let banked = cursor.observe(text).banked { send(banked) }
        if let line = cursor.takePending() { send(line) }
        cursor.reset()
    }
    var joined: String { lines.joined(separator: " ") }
}

// ------------------------------------------------------------------- words

/// Words are interned to Ints and "close enough to be the same word respelled"
/// is precomputed pairwise. The scorer runs an LCS per sequence over hundreds
/// of thousands of sequences; doing edit distance inside that loop is what
/// makes a fuzzer too slow to run at the size that finds anything.
final class Vocab {
    private var ids: [String: Int] = [:]
    private(set) var words: [String] = []
    private var alikeTable: [Bool] = []
    private var sealed = 0

    func id(_ w: String) -> Int {
        if let k = ids[w] { return k }
        let k = words.count
        ids[w] = k
        words.append(w)
        return k
    }

    /// Call once, after every word that can appear has been interned.
    func seal() {
        sealed = words.count
        alikeTable = [Bool](repeating: false, count: sealed * sealed)
        for i in 0..<sealed {
            for j in 0..<sealed {
                alikeTable[i * sealed + j] = Vocab.closeEnough(words[i], words[j])
            }
        }
    }

    /// Anything an emitter invents that was not interned before sealing falls
    /// through to the slow path rather than indexing past the table. It should
    /// be rare; correctness must not depend on it being rare.
    func alike(_ a: Int, _ b: Int) -> Bool {
        if a == b { return true }
        if a < sealed && b < sealed { return alikeTable[a * sealed + b] }
        return Vocab.closeEnough(words[a], words[b])
    }

    /// Independent of the type under test on purpose: exact match, or one edit
    /// between words of four letters or more. The recognizer changing its mind
    /// about spelling is not the emitter deleting a word, and scoring it as one
    /// would bury real losses in noise.
    static func closeEnough(_ a: String, _ b: String) -> Bool {
        if a == b { return true }
        let x = Array(a), y = Array(b)
        guard x.count >= 4, y.count >= 4, abs(x.count - y.count) <= 1 else { return false }
        var prev = Array(0...y.count)
        var cur = [Int](repeating: 0, count: y.count + 1)
        for i in 1...x.count {
            cur[0] = i
            for j in 1...y.count {
                cur[j] = min(prev[j - 1] + (x[i - 1] == y[j - 1] ? 0 : 1),
                             prev[j] + 1, cur[j - 1] + 1)
            }
            swap(&prev, &cur)
        }
        return prev[y.count] <= 1
    }
}

let vocab = Vocab()

/// The comparison form of an emitted line: lower-cased, punctuation dropped.
func normalise(_ s: String) -> [Int] {
    s.split(whereSeparator: { $0 == " " || $0 == "\n" })
        .map { String($0).lowercased().filter { !$0.isPunctuation && !$0.isSymbol } }
        .filter { !$0.isEmpty }
        .map { vocab.id($0) }
}

// ----------------------------------------------------------------- scoring

struct Score {
    /// Committed words that never came out.
    var lost: Int
    /// Emitted words over and above the committed text: repeats and leftovers.
    var extra: Int
}

/// LCS with the one-edit tolerance. `expected` is what the recognizer
/// committed to; `got` is what the emitter actually sent. Order is enforced by
/// construction — a subsequence cannot reorder.
func score(_ expected: [Int], _ got: [Int]) -> Score {
    let m = expected.count, n = got.count
    if m == 0 { return Score(lost: 0, extra: n) }
    if n == 0 { return Score(lost: m, extra: 0) }
    var prev = [Int](repeating: 0, count: n + 1)
    var cur = [Int](repeating: 0, count: n + 1)
    for i in 1...m {
        cur[0] = 0
        let a = expected[i - 1]
        for j in 1...n {
            cur[j] = vocab.alike(a, got[j - 1])
                ? prev[j - 1] + 1
                : max(prev[j], cur[j - 1])
        }
        swap(&prev, &cur)
    }
    let common = prev[n]
    return Score(lost: m - common, extra: n - common)
}

// ------------------------------------------------------------------ random

/// xorshift64. Deterministic: a failure must reproduce from its seed alone.
struct Rng {
    private var s: UInt64
    init(_ seed: UInt64) { s = seed == 0 ? 0x9E37_79B9_7F4A_7C15 : seed }
    mutating func next() -> UInt64 {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17
        return s
    }
    mutating func below(_ n: Int) -> Int { n <= 1 ? 0 : Int(next() % UInt64(n)) }
    mutating func oneIn(_ n: Int) -> Bool { below(n) == 0 }
    mutating func pick(_ xs: [String]) -> String { xs[below(xs.count)] }
}

// ------------------------------------------------------------ vocabularies

/// CONTENT words, one pool per decode window and never reused in a session. A
/// reset means the decoder discarded its hypothesis and started on different
/// audio; the words that come back are different words.
let contentPools: [[String]] = [
    ["Nicholson", "Baylor", "quarter", "closes", "account", "deal", "Eric", "pick"],
    ["clinic", "referral", "Thursday", "review", "Priya", "appointment", "week"],
    ["parking", "ticket", "Friday", "doubles", "remind", "garage", "meter"],
    ["invoice", "Sam", "Monday", "late", "sorry", "meeting", "yesterday"],
    ["flight", "Denver", "Tuesday", "noon", "gate", "boarding", "land"],
    ["Cineplex", "eight", "tickets", "popcorn", "screening", "trailer"],
    ["dentist", "filling", "insurance", "claim", "reschedule", "August"],
]

/// Function words. EVERY window draws these, because every English sentence
/// does. This is the overlap a disjoint-vocabulary generator cannot produce,
/// and the reason this fuzzer sees what the property tests cannot.
let functionPool = ["the", "so", "we", "and", "I", "to", "at", "on", "it", "that", "me"]

/// Words the recognizer decides belong INSIDE text it has already shown.
let fillerPool = ["just", "really", "then", "actually", "kind", "of"]

/// The recognizer changing its mind about spelling rather than about content.
func respelling(_ w: String, _ variant: Int) -> String {
    guard w.count >= 4 else { return w }
    var c = Array(w)
    switch variant {
    case 0:  c.append("s")
    case 1:  c[c.count - 1] = c[c.count - 1] == "e" ? "a" : "e"
    default: c.insert(c[c.count - 2], at: c.count - 1)
    }
    return String(c)
}

// -------------------------------------------------------------- a schedule

enum Mode: Int {
    /// Append, retract-and-restore, repeat, blank, reset. Nothing shown is
    /// ever edited in place, so every committed word is emittable.
    case strict
    /// ... plus a word inserted into text already shown.
    case insertion
    /// ... plus respelling, substitution, and retraction that sticks.
    case churn
    /// The real shredded lines from Omar's feed, under every pause schedule.
    case replay

    var name: String {
        switch self {
        case .strict:    return "STRICT     (append, retract-and-restore, repeat, blank, reset)"
        case .insertion: return "INSERTION  (+ a word pushed into text already shown)"
        case .churn:     return "CHURN      (+ respelling, substitution, sticky retraction)"
        case .replay:    return "REPLAY     (Omar's real shredded lines, every pause schedule)"
        }
    }
    var edits: Bool { self == .insertion || self == .churn }
    var short: String {
        switch self {
        case .strict: return "STRICT"
        case .insertion: return "INSERTION"
        case .churn: return "CHURN"
        case .replay: return "REPLAY"
        }
    }
}

/// One callback. `editedAt` is set when this text differs from the last by a
/// word appearing at, or replacing, that position INSIDE text already shown —
/// the only thing that can bury a word.
struct Step {
    var text: String
    var pause: Bool
    var editedAt: Int?
    /// True when `editedAt` made the text one word LONGER (a word appeared)
    /// rather than swapping a word for a word. Only an insertion shifts the
    /// positions after it.
    var editIsInsertion = false
    /// True on the FIRST callback of a decode window. Word positions are
    /// per-window, so the position bookkeeping has to start over here.
    var windowStart = false
    /// Set when the recognizer took words back AND KEPT THEM OFF, leaving the
    /// text this many words long. Everything an emitter had already sent past
    /// that point is now unreachable: the recognizer will refill those
    /// positions with different words, and no emitter can deliver them in
    /// order without re-sending a line it has already sent.
    var stickyKeep: Int?
}

/// One recognition request: the callbacks it produced, and what it committed
/// to. The commitment is the last text shown in each window — that is what the
/// recognizer stood behind, and none of it may go missing.
struct Schedule {
    var steps: [Step] = []
    var committed: [Int] = []
    var finalText = ""
    /// Words of a window that no emitter can tell apart from its neighbour
    /// growing into, or collapsing out of, the same text. See SEAM-SHADOWED.
    var shadowed = 0
    /// The seam that produced it, kept for the witness line.
    var shadowWitness: (String, String)?
}

/// How many leading words two texts agree on, with the scorer's own one-edit
/// tolerance — "that" and "thaat" are the same word to the scorer, so a seam
/// where one window ends on one and the next opens on the other is exactly as
/// undecidable as a seam where they are spelled identically.
func sharedOpening(_ a: [Int], _ b: [Int]) -> Int {
    var i = 0
    while i < a.count, i < b.count, vocab.alike(a[i], b[i]) { i += 1 }
    return i
}

func makeSchedule(_ r: inout Rng, mode: Mode) -> Schedule {
    var sch = Schedule()
    let windowCount = 1 + r.below(4)
    var usedPools: [Int] = []
    var lastShown = ""
    var previousWindowText: [Int]?

    for _ in 0..<windowCount {
        var p = r.below(contentPools.count)
        var tries = 0
        while usedPools.contains(p), tries < 24 { p = r.below(contentPools.count); tries += 1 }
        usedPools.append(p)
        let content = contentPools[p]

        var shown: [String] = []

        var opening = true
        func emitStep(_ text: String, _ pause: Bool, editedAt: Int? = nil,
                      inserted: Bool = false, stickyKeep: Int? = nil) {
            sch.steps.append(Step(text: text, pause: pause, editedAt: editedAt,
                                  editIsInsertion: inserted, windowStart: opening,
                                  stickyKeep: stickyKeep))
            opening = false
        }

        // Which of `shown` is still spelled the way it was first shown. The
        // scorer's tolerance is ONE edit, deliberately, so respelling the same
        // word twice would move it two edits from the form the emitter
        // absorbed and score a correct absorption as a deletion. Respell each
        // word at most once and the measurement means what it says.
        var pristine: [Bool] = []

        let n = 1 + r.below(20)
        var target: [String] = (0..<n).map { _ in
            r.below(10) < 4 ? r.pick(functionPool) : r.pick(content)
        }
        // Bias hard toward the shape that broke the type: a fresh window whose
        // FIRST word is a function word the previous window also used.
        if r.oneIn(2) { target[0] = r.pick(functionPool) }

        for w in target {
            shown.append(w)
            pristine.append(true)
            emitStep(shown.joined(separator: " "), r.oneIn(6))

            // The recognizer takes its own last words back.
            if shown.count >= 3, r.oneIn(6) {
                let keep = max(0, shown.count - (1 + r.below(3)))
                let sticks = mode == .churn && r.oneIn(5)
                emitStep(shown[0..<keep].joined(separator: " "), r.oneIn(10),
                         stickyKeep: sticks ? keep : nil)
                if sticks {
                    shown = Array(shown[0..<keep])          // the retraction sticks
                    pristine = Array(pristine[0..<keep])
                } else {
                    emitStep(shown.joined(separator: " "), r.oneIn(10))
                }
            }
            // A word appears INSIDE text already shown.
            if mode.edits, shown.count > 2, r.oneIn(8) {
                let at = r.below(shown.count - 1)
                shown.insert(r.pick(fillerPool), at: at)
                pristine.insert(true, at: at)
                emitStep(shown.joined(separator: " "), r.oneIn(10), editedAt: at,
                         inserted: true)
            }
            if mode == .churn {
                // Re-spelling a word it already showed. Not an edit for burial
                // purposes: the scorer treats one edit as the same word, so
                // absorbing it costs nothing and demands nothing.
                if !shown.isEmpty, r.oneIn(9) {
                    let k = r.below(shown.count)
                    if pristine[k] {
                        shown[k] = respelling(shown[k], r.below(3))
                        pristine[k] = false
                        emitStep(shown.joined(separator: " "), r.oneIn(10))
                    }
                }
                // Changing its mind about a word outright.
                if !shown.isEmpty, r.oneIn(12) {
                    let k = r.below(shown.count)
                    shown[k] = r.pick(content)
                    pristine[k] = true
                    emitStep(shown.joined(separator: " "), r.oneIn(10), editedAt: k)
                }
                // Punctuation and capitalisation churn.
                if r.oneIn(9) {
                    emitStep(shown.joined(separator: " ").uppercased() + ".", r.oneIn(10))
                }
            }
            // Identical repeats while nobody is talking.
            if r.oneIn(7) { emitStep(shown.joined(separator: " "), r.oneIn(8)) }
            // The recognizer clears its string. A pause here flushes whatever
            // is pending, exactly as the real one does.
            if r.oneIn(14) { emitStep("", r.oneIn(10)) }
        }

        lastShown = shown.joined(separator: " ")
        // How many words of this seam no emitter can place. See SEAM-SHADOWED:
        // words the two windows OPEN ON in common belong to either of them, and
        // the callback stream is the same whichever it is — the second window's
        // copy is an identical repeat, and the first window's tail is a
        // retraction. The undecidable amount is that shared opening, measured
        // against the window as it GREW (before any in-place edit, since an
        // edit is legal under both readings) and against where it ended up,
        // whichever agrees for longer, and never more than either window holds.
        if let previous = previousWindowText {
            let q = normalise(lastShown)
            let grew = normalise(target.joined(separator: " "))
            let share = max(sharedOpening(previous, grew), sharedOpening(previous, q))
            let undecidable = min(share, min(previous.count, q.count))
            if undecidable > 0 {
                sch.shadowed += undecidable
                if sch.shadowWitness == nil {
                    sch.shadowWitness = (previous.map { vocab.words[$0] }.joined(separator: " "),
                                         lastShown)
                }
            }
        }
        previousWindowText = normalise(lastShown)
        sch.committed.append(contentsOf: normalise(lastShown))
    }

    sch.finalText = lastShown
    return sch
}

// ------------------------------------------------------------------ driving

/// Run a schedule through one emitter and return how many words that emitter
/// had already sent when the recognizer edited in front of them. Checked
/// BEFORE the edited text is handed over, because that is the moment the
/// question is about.
@discardableResult
func drive(_ sch: Schedule, _ e: Emitter) -> Int {
    // How many LEADING WORDS OF THE CURRENT TEXT this emitter has committed to.
    // Not the same as the number of words it has emitted: a word buried below
    // the line pushes the line one further along the text, and a retraction
    // that sticks pulls it back. Getting this wrong in the compounding
    // direction — adding the running burial total back into the position and
    // then burying the difference again — inflated the excused count in CHURN
    // to 369k, which is not an accounting, it is an amnesty.
    var buriedInserts = 0, buriedSwaps = 0, retracted = 0
    // Positions are counted inside the CURRENT decode window. `emittedWordCount`
    // is cumulative over the whole session, so using it raw put the committed
    // line tens of words into a window that had just started, and every edit
    // anywhere in that window came out excused. Excusing by accident is worse
    // than not excusing at all, so the baseline restarts at every seam.
    var baseline = 0, windowInserts = 0, windowRetracted = 0
    func committedPosition() -> Int {
        max(0, e.emittedWordCount - baseline + windowInserts - windowRetracted)
    }
    for s in sch.steps {
        if let at = s.editedAt, at < committedPosition() {
            if s.editIsInsertion { buriedInserts += 1; windowInserts += 1 }
            else { buriedSwaps += 1 }
        }
        e.observe(s.text)
        // A retraction that sticks is measured AFTER the callback, because the
        // callback itself is what forces a never-lose emitter to bank: it is
        // the moment the words at risk stop being visible. Whatever that
        // emitter has now sent past the retraction point can never be
        // reoccupied in order. An emitter that banks nothing gets nothing
        // excused here — and loses nothing either, because its words are still
        // pending.
        if let keep = s.stickyKeep {
            let position = committedPosition()
            if position > keep {
                retracted += position - keep
                windowRetracted += position - keep
            }
        }
        // A fresh window: whatever the emitter had sent by the time it took
        // this callback in — including the previous window's tail, banked right
        // here — is behind it, and position zero starts again. Taken BEFORE the
        // pause on purpose: a bank belongs to the window that is ending, but a
        // pause cuts a line out of the window that is starting, and counting
        // that line into the baseline hid every edit in the first window.
        if s.windowStart {
            baseline = e.emittedWordCount
            windowInserts = 0
            windowRetracted = 0
        }
        if s.pause { e.pause() }
    }
    e.final(sch.finalText)
    return buriedInserts + buriedSwaps + retracted
}

// --------------------------------------------------------------------- run

struct Tally {
    var mode: Mode = .strict
    var sequences = 0
    var callbacks = 0
    var newBuried = 0, oldBuried = 0
    var shadowed = 0
    var lines = 0
    var newLostRaw = 0, oldLostRaw = 0
    var newLost = 0, oldLost = 0          // beyond what burial and shadow explain
    var newExtra = 0, oldExtra = 0
    var newLossSeq = 0, oldLossSeq = 0
    var newDupSeq = 0, oldDupSeq = 0
    var wallBreaks = 0
    var witness: (String, String)?
}

func trace(_ sch: Schedule) -> String {
    sch.steps.map { step -> String in
        "\"" + step.text + "\"" + (step.pause ? "|pause" : "")
            + (step.editedAt.map { "|edit@\($0)" } ?? "")
    }.joined(separator: " -> ")
}

func report(_ label: String, _ sch: Schedule, _ old: OldCursor, _ new: NewCursor,
            _ so: Score, _ sn: Score, _ nb: Int, _ ob: Int, _ index: Int) {
    print("\(label) at sequence \(index)")
    print("   committed : \(sch.committed.map { vocab.words[$0] }.joined(separator: " "))")
    print("   HEAD~1    : \(old.joined)")
    print("   HEAD      : \(new.joined)")
    print("   shadowed=\(sch.shadowed)"
          + "   HEAD~1 buried=\(ob) lost=\(so.lost) extra=\(so.extra)"
          + "   HEAD buried=\(nb) lost=\(sn.lost) extra=\(sn.extra)")
    print("   callbacks : " + trace(sch))
}

func run(_ count: Int, seed: UInt64, mode: Mode) -> Tally {
    var r = Rng(seed)
    var t = Tally()
    t.mode = mode
    t.sequences = count
    var shownWall = 0, shownDup = 0, shownLoss = 0

    for i in 0..<count {
        let sch = makeSchedule(&r, mode: mode)
        t.callbacks += sch.steps.count
        t.shadowed += sch.shadowed
        if t.witness == nil { t.witness = sch.shadowWitness }

        let old = OldCursor(); let ob = drive(sch, old)
        let new = NewCursor(); let nb = drive(sch, new)
        t.newBuried += nb; t.oldBuried += ob
        t.lines += new.lines.count

        let so = score(sch.committed, normalise(old.joined))
        let sn = score(sch.committed, normalise(new.joined))

        let newBeyond = max(0, sn.lost - nb - sch.shadowed)
        let oldBeyond = max(0, so.lost - ob - sch.shadowed)

        t.newLostRaw += sn.lost;  t.oldLostRaw += so.lost
        t.newLost += newBeyond;   t.oldLost += oldBeyond
        t.newExtra += sn.extra;   t.oldExtra += so.extra
        if newBeyond > 0 { t.newLossSeq += 1 }
        if oldBeyond > 0 { t.oldLossSeq += 1 }
        if sn.extra > 0 { t.newDupSeq += 1 }
        if so.extra > 0 { t.oldDupSeq += 1 }

        if newBeyond > 0, shownLoss < 3 {
            shownLoss += 1; report("WORD DELETED", sch, old, new, so, sn, nb, ob, i)
        }
        // THE HONESTY WALL. Losing a word the old cursor kept, where neither
        // burial nor an undecidable seam explains it, is the failure this
        // exercise exists to prevent.
        if newBeyond > oldBeyond {
            t.wallBreaks += 1
            if shownWall < 3 { shownWall += 1; report("HONESTY WALL BROKEN", sch, old, new, so, sn, nb, ob, i) }
        }
        // In STRICT there is nothing to excuse, so duplication is a failure
        // there and a measurement everywhere else.
        if mode == .strict, sn.extra > 0, shownDup < 3 {
            shownDup += 1; report("DUPLICATED A WORD", sch, old, new, so, sn, nb, ob, i)
        }
    }
    return t
}

// ------------------------------------------------------------------ replay
//
// The real thing. These are Omar's own lines, as they came out of the feed in
// shredded slices, put back together into the sentences he actually spoke and
// then re-shredded into the callback stream that produces those slices.
//
//   "Feedback" / "Feedback be able to" / "some feedback from him as a startup
//   company ..."          -> one sentence, cut into three overlapping pieces.
//   "I'm pretty good" / "I'm pretty good speak to Joe Baxter" / "not able to
//   speak to Joe Baxter"  -> two sentences, the second re-sent inside the
//                            first and then again on its own.
//
// Both families are the same event: a decode window reset mid-utterance, the
// integer cursor's index dropped to zero, and it re-emitted growing prefixes
// of the new window while the old one's tail was never sent at all.
//
// A window here is one continuous decode window. The generator below turns a
// list of windows into the callbacks the recognizer would have produced —
// growth a word at a time, an identical repeat, a retract-and-restore, a
// blanked string — and then runs it under EVERY position a single pause could
// land in, plus several multi-pause patterns. On real material, an exhaustive
// sweep over pause placement is worth more than a million random schedules.

let replayFamilies: [[String]] = [
    // The Angie call: one sentence, one mid-utterance window reset.
    ["so she was asking whether I could give",
     "some feedback from him as a startup company before they raise"],
    // The same call, cut in a different place.
    ["Angie called from a startup about the feedback",
     "and there is nothing I need to do about it"],
    // Joe Baxter: two sentences, the second opening on words the first used.
    ["I'm pretty good",
     "I was not able to speak to Joe Baxter yesterday"],
    // The shape that produced "not able to speak to Joe Baxter" on its own.
    ["I said I'm pretty good thanks for asking",
     "I'm not able to speak to Joe Baxter until Thursday"],
    // A single window that never resets, as the control.
    ["let me know when the invoice goes out so I can tell him"],
]

/// Turn a list of decode windows into a callback stream. Deterministic.
func replaySteps(_ windows: [String]) -> (steps: [String], committed: [Int], finalText: String) {
    var steps: [String] = []
    var committed: [Int] = []
    var lastShown = ""
    for window in windows {
        let target = window.split(separator: " ").map(String.init)
        var shown: [String] = []
        for (k, w) in target.enumerated() {
            shown.append(w)
            steps.append(shown.joined(separator: " "))
            // The recognizer repeats itself while nobody is talking.
            if k % 5 == 3 { steps.append(shown.joined(separator: " ")) }
            // And takes its last two words back, then puts them straight back.
            if k % 7 == 6, shown.count > 2 {
                steps.append(shown[0..<(shown.count - 2)].joined(separator: " "))
                steps.append(shown.joined(separator: " "))
            }
            // And clears its string entirely.
            if k % 11 == 9 { steps.append("") }
        }
        lastShown = shown.joined(separator: " ")
        committed.append(contentsOf: normalise(lastShown))
    }
    return (steps, committed, lastShown)
}

struct ReplayResult { var runs = 0, failures = 0, lost = 0, extra = 0 }

func runReplay() -> ReplayResult {
    var res = ReplayResult()
    var shown = 0
    for windows in replayFamilies {
        let (steps, committed, finalText) = replaySteps(windows)
        // Every single-pause schedule, then a spread of multi-pause ones.
        var schedules: [[Int]] = (0..<steps.count).map { [$0] }
        schedules.append([])
        for stride in [2, 3, 5, 7] {
            schedules.append((0..<steps.count).filter { $0 % stride == 0 })
        }
        for pauses in schedules {
            let set = Set(pauses)
            let e = NewCursor()
            for (k, text) in steps.enumerated() {
                e.observe(text)
                if set.contains(k) { e.pause() }
            }
            e.final(finalText)
            let s = score(committed, normalise(e.joined))
            res.runs += 1
            res.lost += s.lost
            res.extra += s.extra
            if s.lost > 0 || s.extra > 0 {
                res.failures += 1
                if shown < 3 {
                    shown += 1
                    print("REPLAY FAILED  pauses at \(pauses.sorted())")
                    print("   spoken  : \(windows.joined(separator: " | "))")
                    print("   emitted : \(e.lines)")
                    print("   lost=\(s.lost) extra=\(s.extra)")
                }
            }
        }
    }
    return res
}

func pad(_ n: Int, _ w: Int = 14) -> String {
    let s = String(n)
    return s + String(repeating: " ", count: max(1, w - s.count))
}

func printTally(_ t: Tally) {
    print("")
    print("\(t.mode.name)")
    print("  \(t.sequences) sequences, \(t.callbacks) callbacks, \(t.lines) lines emitted")
    print("  \(t.shadowed) words in seams no emitter can decide"
          + (t.witness.map { "  (e.g. \"\($0.0)\" / \"\($0.1)\")" } ?? ""))
    print("                              HEAD~1        HEAD")
    print("    words buried by edits   : \(pad(t.oldBuried))\(pad(t.newBuried))")
    print("    words missing, raw      : \(pad(t.oldLostRaw))\(pad(t.newLostRaw))")
    print("    words missing, unexcused: \(pad(t.oldLost))\(pad(t.newLost))")
    print("    words emitted extra     : \(pad(t.oldExtra))\(pad(t.newExtra))")
    print("    sequences losing words  : \(pad(t.oldLossSeq))\(pad(t.newLossSeq))")
    print("    sequences duplicating   : \(pad(t.oldDupSeq))\(pad(t.newDupSeq))")
    print("    honesty wall broken     : \(t.wallBreaks)")
}

// -------------------------------------------------------------------- main

@main
struct TranscriptCursorFuzz {
    static func main() {
        var args = CommandLine.arguments.dropFirst().makeIterator()
        let total = Int(args.next() ?? "") ?? 100_000
        let seed = UInt64(args.next() ?? "") ?? 0x5346_5245_5345_5401

        // Intern every word that can appear — in the form the scorer sees it,
        // which is lower-cased — plus all three respellings of each, before
        // sealing the alike-table.
        var base: [String] = functionPool + fillerPool
        for pool in contentPools { base.append(contentsOf: pool) }
        for windows in replayFamilies {
            for w in windows { base.append(contentsOf: w.split(separator: " ").map(String.init)) }
        }
        for w in base {
            let lower = w.lowercased().filter { !$0.isPunctuation && !$0.isSymbol }
            _ = vocab.id(lower)
            for v in 0..<3 {
                _ = vocab.id(respelling(lower, v))
                _ = vocab.id(respelling(w, v).lowercased())
            }
        }
        vocab.seal()

        print("TranscriptCursor differential fuzz")
        print("  sequences : \(total), split three ways, plus the replay sweep")
        print("  seed      : 0x\(String(seed, radix: 16, uppercase: true))")
        print("  baseline  : HEAD~1 integer cursor (PhoneListener.flushTail)")
        print("  resets    : every window draws content from a vocabulary no")
        print("              other window in the session uses, over one shared")
        print("              function-word pool; a fresh window opens on a")
        print("              shared word half the time")

        // The replay first: it is the fastest and it is the one with real
        // words in it, so a regression there should be the first thing seen.
        let rep = runReplay()
        print("")
        print("\(Mode.replay.name)")
        print("  \(rep.runs) pause schedules over \(replayFamilies.count) real fragment families")
        print("    words missing           : \(rep.lost)")
        print("    words emitted extra     : \(rep.extra)")
        print("    schedules failing       : \(rep.failures)")

        let per = total / 3
        let counts = [per, per, total - 2 * per]
        var tallies: [Tally] = []
        var s = seed
        for (k, mode) in [Mode.strict, .insertion, .churn].enumerated() {
            tallies.append(run(counts[k], seed: s, mode: mode))
            s = s &* 6_364_136_223_846_793_005 &+ 1
        }
        for t in tallies { printTally(t) }

        var failed = false
        print("")
        if rep.lost > 0 || rep.extra > 0 {
            print("FAILED — REPLAY lost \(rep.lost) and duplicated \(rep.extra) words"
                  + " of Omar's own sentences across \(rep.failures) pause schedules")
            failed = true
        }
        let strict = tallies[0]
        if strict.newLostRaw > strict.shadowed {
            print("FAILED — STRICT lost \(strict.newLostRaw) words,"
                  + " \(strict.shadowed) of which are undecidable seams")
            failed = true
        }
        if strict.newExtra > 0 {
            print("FAILED — STRICT emitted \(strict.newExtra) words twice")
            failed = true
        }
        for t in tallies {
            if t.wallBreaks > 0 {
                print("FAILED\(t.mode.edits ? " (KNOWN — the edit-seam residual)" : "")"
                      + " — honesty wall broken \(t.wallBreaks) times in \(t.mode.name)")
                failed = true
            }
            if t.newLost > 0 {
                if t.mode.edits {
                    print("FAILED (KNOWN, NOT FIXED — \"the edit-seam residual\")"
                          + " — \(t.newLost) words deleted in \(t.sequences)"
                          + " \(t.mode.short) sequences, beyond burial and"
                          + " undecidable seams.")
                    print("   This is the one thing left open. It needs an IN-PLACE EDIT:"
                          + " STRICT, which has none, is at a flat zero on the same run,")
                    print("   so the boundary rule is not what is wrong. What is wrong is"
                          + " the seam between banking a tail and the recognizer then")
                    print("   rewriting the span that tail came from. It is single digits"
                          + " to low tens of words per 33k sequences — order of one in a")
                    print("   hundred thousand — and every one is printed above with its"
                          + " full callback trace. Reproduce with the seed above.")
                } else {
                    print("FAILED — \(t.newLost) words deleted in \(t.mode.name),"
                          + " beyond burial and undecidable seams")
                }
                failed = true
            }
            if t.newExtra > t.oldExtra {
                print("FAILED — duplicated more than HEAD~1 in \(t.mode.name)")
                failed = true
            }
        }
        if failed { exit(1) }

        print("\(total)/\(total) sequences passed, and \(rep.runs) replay schedules.")
        print("  REPLAY     : Omar's own sentences come back whole, once each, in")
        print("               order, under every pause placement.")
        print("  STRICT     : nothing lost but the undecidable seams, nothing twice.")
        print("  INSERTION  : nothing lost beyond words buried by in-place edits.")
        print("  CHURN      : same, and every mode stayed at or under HEAD~1 on")
        print("               both losses and duplication.")
        print("TranscriptCursor fuzz: all green")
        exit(0)
    }
}
