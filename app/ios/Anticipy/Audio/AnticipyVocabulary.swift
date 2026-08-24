import Foundation

/// The words the recognizer cannot be expected to know: the product's own
/// name and the people in his life. The shipped model heard "anticipy growth
/// ... dot com" as "anticipate growth there's something.com", and she offered
/// to buy the misspelling of her own product. `contextualStrings` on
/// SFSpeechRecognizer exists for exactly this — both request sites
/// (PhoneListener, LocalTranscriber) call `current()` when they build a
/// request, so a name learned today is in the lexicon tomorrow.
enum AnticipyVocabulary {

    /// Names no acoustic model ships with. "Anticipy" first: it is the word
    /// the recognizer mishears most, and the one that must survive the cap.
    static let starters = ["Anticipy", "Tejas", "OpenTrade", "pendant"]

    static func current() -> [String] {
        var words = starters
        // The owner's name, as onboarding wrote it (@AppStorage in
        // AnticipyApp.swift uses these exact keys).
        for key in ["ownerFirstName", "ownerLastName"] {
            if let v = UserDefaults.standard.string(forKey: key) {
                words.append(v)
            }
        }
        words += rosterNames()

        // Empties dropped, first spelling of a name wins, and the list is
        // capped at 60: Apple degrades recognition on oversized lists rather
        // than rejecting them, so an unbounded roster would quietly make
        // EVERY word worse.
        var seen = Set<String>()
        var out: [String] = []
        for raw in words {
            let word = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !word.isEmpty, seen.insert(word.lowercased()).inserted else { continue }
            out.append(word)
            if out.count == 60 { break }
        }
        return out
    }

    /// The people the voice roster can already name. VoiceRoster owns the
    /// file (Application Support, this device only); this only peeks at the
    /// name fields, defensively — a fresh install has no roster, and a
    /// decode failure must never cost the starter words.
    private static func rosterNames() -> [String] {
        struct Person: Decodable { var name: String? }
        struct Stored: Decodable { var people: [String: Person]? }
        let dir = FileManager.default.urls(for: .applicationSupportDirectory,
                                           in: .userDomainMask)[0]
        let url = dir.appendingPathComponent("voice-roster.json")
        guard let data = try? Data(contentsOf: url),
              let stored = try? JSONDecoder().decode(Stored.self, from: data)
        else { return [] }
        // Sorted so the list is stable across calls — the recognizer should
        // not see a reshuffled lexicon on every request swap.
        return (stored.people ?? [:]).compactMap(\.value.name).sorted()
    }
}
