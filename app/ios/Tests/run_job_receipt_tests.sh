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
echo "the receipt arrives from the server, reaches the card, and is drawn"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/JobReceiptTests.swift" "$out/main.swift"
swiftc -O "$receipt" "$policy" "$out/main.swift" -o "$out/jobreceipttests"
"$out/jobreceipttests"
