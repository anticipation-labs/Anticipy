#!/bin/sh
# The verified receipt is what the person reads.
#
#   sh app/ios/Tests/run_job_receipt_tests.sh
#
# JobReceipt and JobReceiptPolicy are pure Foundation, so the real production
# sources are compiled straight in rather than copied.
#
# stranger_gate.py leg 7: the backend refuses to mark ANY job done without a
# receipt whose `verified` is true and whose `evidence` is non-empty, and the
# done card rendered `result` — free text the extension composed about its own
# success. The evidence the server actually checked sat unread in the same row.
set -eu
# Parse before installing EXIT cleanup: macOS sh can mask a later syntax error
# with a successful trap. Syntax errors are failures, never a green test run.
sh -n "$0"
case "${1:-}" in ''|--check-mutations) ;; *) echo 'unknown option'; exit 2;; esac
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

receipt="$app/Backend/JobReceipt.swift"
policy="$app/Backend/JobReceiptPolicy.swift"
[ -f "$receipt" ] || { echo "missing $receipt"; exit 2; }
[ -f "$policy" ] || { echo "missing $policy"; exit 2; }

# The logic below is worthless if the column never arrives from the server, or
# arrives and reaches nothing. Prove the WIRING first — this is the exact life
# `events.source` already had once: written for weeks, read by nothing, and no
# test noticed because nothing asserted the read.
backend="$app/Backend/AnticipyBackend.swift"
if ! grep -q 'let receipt: String?' "$backend"; then
    echo "AgentJob no longer decodes the receipt column."
    echo "The server enforces a verified receipt on every completion and the"
    echo "app goes back to showing whatever sentence the browser composed."
    exit 2
fi

row="$app/Views/ContentView.swift"
if ! grep -q 'JobReceiptPolicy.doneCard(' "$row"; then
    echo "The done card no longer asks JobReceiptPolicy what to lead with."
    exit 2
fi
# FED, not merely decoded. A column nothing renders changes nothing a stranger
# can see, which is the state stranger_gate leg 7 was opened on.
if ! grep -q 'receipt: job.receipt' "$row"; then
    echo "The done card is no longer fed job.receipt."
    echo "Decoding a column and then rendering only \`result\` is the defect"
    echo "leg 7 exists for: the stranger cannot tell a receipt from a sentence."
    exit 2
fi
if ! grep -q 'effectKey: job.effect_key' "$row"; then
    echo "The done card no longer tells the policy which effect this row is."
    echo "The backend binds a receipt to an exact effect_key; without it a"
    echo "receipt for one action could vouch for a different one."
    exit 2
fi
# AND RENDERED. Mutation-tested by deleting the proof block from DoneCard: the
# checks above all stayed green with the card showing the browser's sentence
# and nothing else, and this leg is what caught it.
#
# THE HONEST LIMIT OF THIS CHECK, measured rather than assumed: it catches
# DELETION, not disabling. Rewriting the block as `if false, let proof =
# card.proof` was tried, and this grep still matched — the reference is there
# and the view is dead. The same limit the CaptureSourcePolicy legs carry, and
# it is written down for the same reason: a check whose reach is implied gets
# read as a check that proves more than it does. Only a simulator can see a
# pixel.
if ! grep -q 'card.proof' "$row"; then
    echo "DoneCard no longer renders the proof block."
    echo "The receipt reaches the card and dies there — the person still sees"
    echo "only the sentence the extension wrote. Moment 31: done without proof"
    echo "doesn't exist."
    exit 2
fi
if ! grep -q 'card.unproven' "$row"; then
    echo "DoneCard no longer says when a done row has NOTHING behind it."
    echo "A claim with no receipt then wears a receipt's clothes, silently."
    exit 2
fi
echo "receipt column and rendering call sites are wired (not a pixel/render proof)"

# Lift actual computed methods instead of restating the view's row arithmetic.
# Fail closed if a method disappears or its braces no longer balance. Swift
# compilation below validates the extracted bodies; these methods have no
# braces inside string literals. This does not typecheck the SwiftUI hierarchy.
extract() {
    awk -v signature="$1" -v target="$2" '
        BEGIN { print "extension " target " {" }
        !inside && index($0, signature) { inside = 1; found = 1 }
        inside {
            sub(/private /, "")
            print
            depth += gsub(/{/, "{"); depth -= gsub(/}/, "}")
            if (depth == 0) { closed = 1; exit }
        }
        END { print "}"; if (!found || !closed) exit 2 }
    ' "$row"
}
extract 'private var proofRows: Int {' DoneCardFixture > "$out/CardRows.swift"
extract 'private func landed(_ index: Int) -> Bool {' ReceiptRevealFixture > "$out/Reveal.swift"

# Scoped call-site guards: deletion/rewiring regressions, not proof that a view
# is reachable or rendered. A simulator/device must still verify actual pixels.
awk '/^private struct ReceiptProof: View/{inside=1} inside{print} inside && /^}/{exit}' "$row" > "$out/ReceiptProof.txt"
for binding in 'Text(proof.checked ??' 'Array(proof.notes.enumerated())' 'proof.notesStartIndex + index' 'proof.disclosureRowIndex' 'Array(proof.items.enumerated())'; do
    if ! grep -Fq "$binding" "$out/ReceiptProof.txt"; then
        echo "ReceiptProof no longer wires $binding"; exit 2
    fi
done
if [ "$(grep -Fc 'id: \.offset' "$out/ReceiptProof.txt")" -ne 2 ]; then
    echo 'Receipt references must retain distinct row identities, including duplicates'; exit 2
fi

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/JobReceiptTests.swift" "$out/main.swift"
compile() {
    swiftc -O "$1" "$2" "$app/DoneCeremonyPolicy.swift" \
        "$out/CardRows.swift" "$out/Reveal.swift" "$out/main.swift" -o "$out/jobreceipttests"
}
compile "$receipt" "$policy"
"$out/jobreceipttests"

if [ "${1:-}" = --check-mutations ]; then
    # Copies only: the user's working sources are never mutated for a probe.
    sed 's/CFGetTypeID($0) == CFBooleanGetTypeID()/true/' "$receipt" > "$out/NumericVerified.swift"
    compile "$out/NumericVerified.swift" "$policy"
    if "$out/jobreceipttests" > "$out/numeric.log" 2>&1; then
        echo 'SURVIVED: numeric JSON verification'; exit 1
    fi
    echo 'KILLED: numeric JSON verification'
    sed 's/notesStartIndex + notes.count/notesStartIndex/' "$policy" > "$out/MissingNoteRows.swift"
    compile "$receipt" "$out/MissingNoteRows.swift"
    if "$out/jobreceipttests" > "$out/rows.log" 2>&1; then
        echo 'SURVIVED: missing arrival note rows'; exit 1
    fi
    echo 'KILLED: missing arrival note rows'
    sed 's/verified && hasValidEvidence/verified/' "$receipt" > "$out/PartialEvidence.swift"
    compile "$out/PartialEvidence.swift" "$policy"
    if "$out/jobreceipttests" > "$out/evidence.log" 2>&1; then
        echo 'SURVIVED: partially malformed evidence'; exit 1
    fi
    echo 'KILLED: partially malformed evidence'
fi
