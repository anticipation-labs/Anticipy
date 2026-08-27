import Foundation

/// The decisions a settings-style sheet makes that have NOTHING to do with a
/// screen.
///
/// WHY THIS FILE IS SEPARATE FROM `SettingsKit.swift`, and why it imports
/// Foundation and nothing else. Four of the five details that make this design
/// read as copied-well rather than copied-badly are arithmetic and case
/// analysis, not drawing: which inset a hairline takes, whether a hairline
/// exists at all, whether the confirm button in the header is alive, and what
/// the trailing slot of a row shows. Every one of those can be wrong in a way
/// a screenshot hides and a compiler cannot see.
///
/// So they live here, where `app/ios/Tests/run_settings_kit_tests.sh` compiles
/// THIS FILE — the real production source, not a copy of it — against
/// Foundation alone and asks them directly. The import list is the leg: the
/// moment one of these decisions reaches for a `Color`, a `Font` or a `View`,
/// that suite stops building, which is the same rule `FieldCaption` is held to
/// in Theme.swift.
///
/// It carries no colour, no font, no token and no view. `dividerLeading` takes
/// its three measurements as ARGUMENTS rather than reading `Theme`, so the
/// arithmetic is testable without a palette and the palette stays the one place
/// a measurement is named.
enum SheetKit {

    // ------------------------------------------------------------ hairlines
    //
    // DETAIL 1, and the brief calls it "the single most characteristic detail":
    // a divider between two rows begins AT THE LABEL, not at the card edge, so
    // the icon column stays clear. A full-bleed divider is the clearest tell
    // that a design was copied badly.

    /// WHERE a hairline between two rows starts, measured from the card's own
    /// leading edge.
    enum DividerInset: Equatable {
        /// Card edge to card edge. For a row whose content owns the full width
        /// and has no label column to align to — never for an ordinary row.
        case edge
        /// At the LABEL: past the card's horizontal padding and no further.
        /// This is what a row with no leading glyph takes — the two-line toggle
        /// rows, the select rows, the editable value rows.
        case label
        /// Past the whole icon column, so the glyph column stays clear. This is
        /// what a row WITH a leading glyph takes.
        case afterGlyph
    }

    /// A row with a leading glyph insets past the glyph; a row without one
    /// insets to its label. That is the entire rule, and it is a rule rather
    /// than a constant precisely because both kinds of row sit in the same card.
    static func dividerInset(hasGlyph: Bool) -> DividerInset {
        hasGlyph ? .afterGlyph : .label
    }

    /// The inset in points, from the card's leading edge.
    ///
    /// The three measurements arrive as arguments because they belong to the
    /// row component, not to this decision — and because the glyph column
    /// GROWS with Dynamic Type, so there is no constant to hard-code. The view
    /// layer passes the same scaled column it drew the glyph in, which is what
    /// keeps the hairline under the label at every text size instead of only at
    /// the default one.
    static func dividerLeading(_ inset: DividerInset,
                               rowPadding: CGFloat,
                               glyphColumn: CGFloat,
                               glyphGap: CGFloat) -> CGFloat {
        switch inset {
        case .edge: return 0
        case .label: return rowPadding
        case .afterGlyph: return rowPadding + glyphColumn + glyphGap
        }
    }

    /// A hairline sits BETWEEN rows: after every row but the last, and never in
    /// a card holding one row.
    ///
    /// The destructive card is the case this exists for. It is its own card
    /// holding a single row, and a hairline under it would draw a line along
    /// the bottom of the card with nothing beneath it.
    static func showsDivider(after index: Int, of count: Int) -> Bool {
        index >= 0 && index < count - 1
    }

    // ------------------------------------------------------------- trailing
    //
    // The source design shows "Max plan >" on one row: a trailing grey value
    // and a chevron, TOGETHER. Written as two independent `if let`s that rule
    // is easy to lose to a refactor, so it is one decision with one answer.

    /// What the trailing slot of a row shows.
    enum Trailing: Equatable {
        case nothing
        case value(String)
        case chevron
        case valueAndChevron(String)
    }

    /// A value and a chevron COEXIST. Neither suppresses the other.
    static func trailing(value: String?, isNavigable: Bool) -> Trailing {
        switch (value, isNavigable) {
        case let (.some(v), true): return .valueAndChevron(v)
        case let (.some(v), false): return .value(v)
        case (.none, true): return .chevron
        case (.none, false): return .nothing
        }
    }

    // ------------------------------------------------------------ wrapping
    //
    // DETAIL 2. The subtitle wraps to as many lines as it needs and the row
    // grows with it. Nothing is clipped and nothing is truncated — except the
    // one deliberate single-line value row, which is the exception this type
    // names out loud so it cannot spread by accident.

    /// The text slots a row has.
    enum Slot: Equatable {
        case title
        case subtitle
        /// The grey state on the right of a row: "Allowed", "Read & write",
        /// "Never", "Max plan".
        case trailingValue
    }

    /// How many lines a slot may take. `nil` means "as many as it needs".
    ///
    /// The trailing value is the ONE slot allowed to truncate, because it sits
    /// on the same line as a label that has the stronger claim on the width. A
    /// title or a subtitle that truncates is a bug.
    static func lineLimit(for slot: Slot) -> Int? {
        switch slot {
        case .title, .subtitle: return nil
        case .trailingValue: return 1
        }
    }

    // ------------------------------------------------------------- the save
    //
    // THE SAVE AFFORDANCE, and it is a real interaction change: the confirm
    // control is a circular button in the header, greyed while there is
    // nothing to save, not a button at the bottom of a form.
    //
    // "Greyed while there is nothing to save" has two halves, and shipping only
    // the first is the defect `run_field_caption_tests.sh` was written for: a
    // live button whose only outcome is a silent false. So a change is not
    // enough — the change has to be one the thing storing it will accept.

    /// One field's draft against what is stored for it.
    struct Edit: Equatable {
        let draft: String
        let stored: String

        init(draft: String, stored: String) {
            self.draft = draft
            self.stored = stored
        }

        /// Compared verbatim. No trimming, no case folding, no normalising:
        /// a save button that decides two different strings are the same string
        /// is a save button deciding what somebody typed MEANT, and the person
        /// who typed a trailing space is the one who finds out.
        var isChanged: Bool { draft != stored }
    }

    /// Is there anything worth writing?
    static func hasChanges(_ edits: [Edit]) -> Bool {
        edits.contains { $0.isChanged }
    }

    /// Is the confirm button in the header alive?
    ///
    /// `acceptable` is the caller's own validity predicate — the SAME one the
    /// screen shows its caption from, never a second opinion about it. This
    /// type does not know what a valid anything looks like and must not learn.
    static func saveEnabled(edits: [Edit], acceptable: Bool) -> Bool {
        hasChanges(edits) && acceptable
    }

    // ----------------------------------------------------------- the header
    //
    // A circular button on the left: an X at the ROOT of the sheet, a back
    // chevron on a sub-screen.

    /// What the left-hand circular button is for.
    enum HeaderLeading: Equatable {
        /// The root of a sheet. This dismisses the whole thing.
        case close
        /// A screen pushed onto the sheet. This goes back one.
        case back
        /// No button, and the space it would have taken is still held — see
        /// the header layout in SettingsKit.swift. A header whose title jumps
        /// left when a button is absent is a header that moves.
        case none
    }

    /// The root closes; anything pushed onto it goes back. Depth is how many
    /// screens are stacked ON the root, so the root itself is zero.
    static func headerLeading(depth: Int) -> HeaderLeading {
        depth <= 0 ? .close : .back
    }

    /// The SF Symbol each role draws. Names, not pictures — which is why this
    /// decision is answerable here rather than on a screen.
    static func leadingGlyph(_ role: HeaderLeading) -> String? {
        switch role {
        case .close: return "xmark"
        case .back: return "chevron.left"
        case .none: return nil
        }
    }

    // ------------------------------------------------------- single-select
    //
    // A card of title+subtitle rows where the chosen one carries a CHECKMARK on
    // the right. A checkmark — not a radio, not a highlight, not a filled row.

    /// Is this the chosen one?
    static func isChosen<T: Equatable>(_ item: T, selection: T?) -> Bool {
        guard let selection else { return false }
        return item == selection
    }

    /// WHICH row carries the checkmark, or none.
    ///
    /// Returns the FIRST match and nothing else, so a list that somehow holds
    /// the same item twice still draws exactly one checkmark. Two ticks in one
    /// group is a group that has stopped meaning "pick one"; and a selection
    /// that matches nothing in the list draws no tick at all rather than
    /// defaulting to the first row, because "we lost your choice" and "your
    /// choice is the top one" are different sentences and only one of them is
    /// true.
    static func chosenIndex<T: Equatable>(in items: [T], selection: T?) -> Int? {
        guard let selection else { return nil }
        return items.firstIndex(of: selection)
    }
}
