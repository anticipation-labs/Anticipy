#!/bin/sh
# The other half of a grant: what she says back, and what the button said
# before it. Both are consent copy, and both were the same string for three
# different things.
#
#   sh app/ios/Tests/run_context_receipt_tests.sh
#
# ContextGrant and LifeContext are compiled straight in, so the assertions are
# about the production sentences and the production caps.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

grant="$app/ContextGrant.swift"
life="$app/LifeContext.swift"
sheet="$app/Views/ContextAskSheet.swift"
for f in "$grant" "$life" "$sheet"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

# WIRING FIRST. Copy that exists and is rendered nowhere is the exact failure
# the sibling suite was written for: written for weeks, read by nothing.
if ! grep -q 'source.yesButton' "$sheet"; then
    echo "The per-source yes label is written and never rendered."
    exit 2
fi
# A literal yes anywhere in the rendered tree is the generic label coming
# back, whatever it now says. The prose in a comment is not a label, so the
# pattern is the render form rather than the words.
if grep -q 'Text("Yes' "$sheet"; then
    echo "A yes label is hardcoded on the button instead of coming from the source."
    exit 2
fi
if ! grep -q 'ContextReceipt.lines' "$sheet"; then
    echo "Nothing computes the receipt, so a grant still closes on silence."
    exit 2
fi
if ! grep -q 'ContextReceipt.heading' "$sheet"; then
    echo "The receipt has no heading, so the lines stand with nothing said about them."
    exit 2
fi
# The whole fix is that a yes does NOT close the sheet on an on-device source.
# `dismiss()` must be reachable only from the two buttons and the off-device
# early return, never straight off the grant.
if grep -q 'if ok { dismiss() }' "$sheet"; then
    echo "A granted on-device source still dismisses immediately: she takes and the sheet vanishes."
    exit 2
fi
echo "the button names its source, and a grant is answered on screen"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/ContextReceiptTests.swift" "$out/main.swift"
swiftc -O "$grant" "$life" "$out/main.swift" -o "$out/contextreceipttests"
"$out/contextreceipttests"
