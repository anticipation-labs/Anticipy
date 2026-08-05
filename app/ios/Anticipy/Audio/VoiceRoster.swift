import Foundation

/// Who is in his life — learned on this phone, kept on this phone.
///
/// The Swift mirror of `proof/voice_roster.py`. That file is the reference
/// implementation and the two MUST stay in step: same thresholds, same
/// margin rule, same drift, same "unknown means no verdict" fallback.
///
/// Local-first is not a nice-to-have here, it is the whole design. A
/// voiceprint is as personal as a fingerprint, so it is computed on this
/// device, written to this device's app-support directory, and never
/// synced, backed up to a server, or sent anywhere. What leaves the phone
/// is one short word — "owner", "other:v2", "other:Sarah" — and nothing
/// else, ever.
final class VoiceRoster {

    /// A genuine same-person score sits well above this. Measured
    /// 2026-08-05 across three voices and five cross-session comparisons:
    /// same person 0.897–0.911, different people 0.181–0.667.
    ///
    /// The 0.667 is why this is not 0.60 (an earlier, unsafe value): a
    /// third voice scored that against the owner, and 0.60 would have
    /// called a stranger Omar — putting someone else's promises in his
    /// mouth. That is the worst failure this system can have, so the gate
    /// is deliberately asymmetric: a missed match costs nothing (she just
    /// gets no hint), a false match corrupts whose life this is.
    static let match: Float = 0.78
    /// …and the winner must clearly beat whoever came second.
    static let margin: Float = 0.05

    struct Person: Codable {
        var vec: [Float]
        var name: String?
        var heard: Int
    }

    struct Verdict {
        /// What travels to the brain. Everything else here stays home.
        let tag: String          // "owner" | "other:<id>" | "unknown"
        let id: String?
        let name: String?
        let score: Float
        let confident: Bool
    }

    private struct Stored: Codable {
        var owner: [Float]?
        var people: [String: Person]
    }

    private var owner: [Float]?
    private(set) var people: [String: Person] = [:]
    private let url: URL
    private let queue = DispatchQueue(label: "ai.anticipy.voiceroster")

    var hasOwnerProfile: Bool { owner != nil }
    /// Voices she keeps hearing but cannot put a name to yet.
    var unnamedPeople: [(id: String, heard: Int)] {
        people.filter { $0.value.name == nil }
            .map { ($0.key, $0.value.heard) }
            .sorted { $0.heard > $1.heard }
    }

    init(filename: String = "voice-roster.json") {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory,
                                           in: .userDomainMask)[0]
        try? FileManager.default.createDirectory(at: dir,
                                                 withIntermediateDirectories: true)
        url = dir.appendingPathComponent(filename)
        load()
    }

    // MARK: - storage (this device only)

    private func load() {
        guard let data = try? Data(contentsOf: url),
              let stored = try? JSONDecoder().decode(Stored.self, from: data)
        else { return }
        owner = stored.owner
        people = stored.people
    }

    private func save() {
        let stored = Stored(owner: owner, people: people)
        guard let data = try? JSONEncoder().encode(stored) else { return }
        // Excluded from iCloud/iTunes backup: a voiceprint should not
        // travel even in a backup blob.
        try? data.write(to: url, options: .completeFileProtection)
        var res = URLResourceValues()
        res.isExcludedFromBackup = true
        var u = url
        try? u.setResourceValues(res)
    }

    // MARK: - enrollment

    func enrollOwner(_ vec: [Float]) {
        queue.sync {
            owner = vec
            save()
        }
    }

    /// "That was Sarah" — a name attaches to a voice already known, so the
    /// voice never has to be learned twice.
    func name(_ id: String, _ name: String) {
        queue.sync {
            guard people[id] != nil else { return }
            people[id]?.name = name
            save()
        }
    }

    func forgetEverything() {
        queue.sync {
            owner = nil
            people = [:]
            save()
        }
    }

    // MARK: - the decision

    static func cosine(_ a: [Float], _ b: [Float]) -> Float {
        guard a.count == b.count, !a.isEmpty else { return 0 }
        var dot: Float = 0, na: Float = 0, nb: Float = 0
        for i in 0..<a.count {
            dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]
        }
        let d = (na.squareRoot() * nb.squareRoot())
        return d > 0 ? dot / d : 0
    }

    /// Who spoke? `learn: false` for enrollment previews and tests.
    func identify(_ vec: [Float], learn: Bool = true) -> Verdict {
        queue.sync {
            var scores: [(Float, String)] = []
            if let owner { scores.append((Self.cosine(owner, vec), "owner")) }
            for (id, p) in people { scores.append((Self.cosine(p.vec, vec), id)) }
            scores.sort { $0.0 > $1.0 }

            let best = scores.first ?? (0, "")
            let runner = scores.count > 1 ? scores[1].0 : 0
            let confident = !scores.isEmpty && best.0 >= Self.match
                && (best.0 - runner) >= Self.margin

            if confident && best.1 == "owner" {
                return Verdict(tag: "owner", id: "owner", name: nil,
                               score: best.0, confident: true)
            }
            if confident, var p = people[best.1] {
                p.heard += 1
                // Drift with them: a voice changes with mood, phone, room.
                // Without this a cold turns a friend into a stranger.
                for i in 0..<p.vec.count {
                    p.vec[i] = 0.85 * p.vec[i] + 0.15 * vec[i]
                }
                people[best.1] = p
                if learn { save() }
                let label = p.name ?? best.1
                return Verdict(tag: "other:\(label)", id: best.1, name: p.name,
                               score: best.0, confident: true)
            }

            // Nobody known. A voice clearly NOT his becomes a new person so
            // it can be recognised tomorrow; genuinely ambiguous audio stays
            // unknown and teaches the roster nothing — one bad row poisons
            // every future match.
            let ownerScore = scores.first { $0.1 == "owner" }?.0 ?? 0
            let ambiguous = ownerScore >= (Self.match - 0.15)
            if learn && !ambiguous && best.0 < Self.match {
                let id = "v\(people.count + 1)"
                people[id] = Person(vec: vec, name: nil, heard: 1)
                save()
                return Verdict(tag: "other:\(id)", id: id, name: nil,
                               score: best.0, confident: false)
            }
            return Verdict(tag: "unknown", id: nil, name: nil,
                           score: best.0, confident: false)
        }
    }
}
