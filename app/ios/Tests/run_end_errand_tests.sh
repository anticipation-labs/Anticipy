#!/bin/sh
# Checks for the end-of-errand decision — the rule that decides whether a typed
# answer cancels the job and files the owner's own words as the reason.
#
#   sh app/ios/Tests/run_end_errand_tests.sh
#
# The rule lives inside AnticipySession, which drags in SwiftUI, Combine, the
# network layer and the microphone — none of which this decision touches. So
# rather than duplicate it (a copy is only honest until someone edits one side),
# this lifts the REAL source out of AnticipyApp.swift between its ANCHOR
# markers and compiles it alone. `Self.` resolves to the wrapper here exactly as
# it resolves to AnticipySession there.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

src="$app/AnticipyApp.swift"

# The checks are worthless if the app has quietly stopped consulting the rule
# before it approves an answer. Prove the wiring before proving the logic.
if ! grep -q 'Self.answerThatEndsTheErrand' "$src"; then
    echo "confirm() no longer asks whether the answer ended the errand."
    echo "Without it every non-empty answer requeues the run — which is how"
    echo "'skip it, I don't need the batteries' relaunched the errand and got"
    echo "those words Bing-searched into a CAPTCHA."
    exit 2
fi
if grep -vE '^[[:space:]]*//' "$src" | grep -q 'wordCount <= 8'; then
    echo "The rule is gating on answer LENGTH again."
    echo "Every regression it was added for is short: 'leave it with the"
    echo "concierge', 'stop it from auto-renewing'. Length was never the"
    echo "condition; position is."
    exit 2
fi

# --------------------------------------------------------------------------
# LAW 2, FROM THE iOS SIDE. This rule is REGISTERED TAPE, not a design.
#
# It decides what the owner's words MEAN — three phrase lists on the phone,
# with no model anywhere near them — and on a hit it writes the job cancelled
# and files the owner's own sentence as the evidence they called it off. That
# is Law 1's canonical shape, and research/2026-08-24-law1-audit.md item #55
# records it at severity H.
#
# It is still here because deleting it could not be shown SAFE from inside
# app/ios/: see the block comment on the rule itself in AnticipyApp.swift. So
# it ships the only way Law 2 permits — carrying a marker and a red leg. Those
# live in two other files, and the whole point of Law 2 is that all three books
# have to agree. This leg is the iOS book: if the rule is in the tree and its
# declaration is not, these checks fail HERE, where the person editing the rule
# is already looking, rather than only in a gate they may never run.
#
# When the rule is deleted, delete this leg with it — and the registry entry,
# and the ledger bullet, in the same diff.
# --------------------------------------------------------------------------
#
# THE NEEDLE IS ASSEMBLED, NOT WRITTEN. It must not appear in this file as a
# literal, and that is not style. overnight/tape_gate.py decides a piece of
# tape is GONE by searching the whole of app/ for the registered `find` text —
# and app/ios/Tests/*.sh is inside app/. Spelled out here, this file WOULD BE
# a second copy of the tape as far as the gate can tell: the day someone
# actually deletes the rule the entry would come back MOVED instead of GONE,
# leg 1 would go red pointing at a test script, and Law 2's expiry could never
# turn green. An expiry that cannot come true is the thing this whole gate
# exists to stop. Caught by mutation, 2026-08-25: the rule was renamed away
# and leg 2 still counted it.
rule_name='answerThatEndsTheErrand'
rule_find="static func $rule_name("
marker='TAPE'
gate="$here/../../../overnight/tape_gate.py"
laws="$here/../../../HARNESS-LAWS.md"
if grep -qF "$rule_find" "$src"; then
    if ! grep -q "$marker[:.]" "$src"; then
        echo "The end-of-errand rule is in AnticipyApp.swift with no '$marker:'"
        echo "comment. Undeclared tape is a rejected diff (Law 2). Either delete"
        echo "the rule and route every answer to the brain, or declare it."
        exit 2
    fi
    if ! grep -qF "$rule_find" "$gate"; then
        echo "The rule carries a marker but overnight/tape_gate.py has no entry"
        echo "whose find= is:  $rule_find"
        echo "A marker pointing at a leg that does not track it reads as"
        echo "compliant and enforces nothing — that is audit item #21 exactly."
        exit 2
    fi
    if ! grep -q 'tape:answer_ends_errand' "$laws"; then
        echo "Neither book a human reads mentions this tape. HARNESS-LAWS.md's"
        echo "'Known standing tape' section needs its [tape:answer_ends_errand]"
        echo "bullet, or the next agent reads the ledger and believes the list"
        echo "is complete."
        exit 2
    fi
    echo "the rule is declared tape: marker in the source, entry in the gate, bullet in the law"
fi

# The END rule comes first: the closing marker contains the opening marker as a
# substring, so testing for the opening one first re-armed it and swallowed the
# rest of the file.
awk '/END ANCHOR: end-of-errand decision/{f=0;next} /ANCHOR: end-of-errand decision/{f=1;next} f' \
    "$src" > "$out/rule.swift"
if [ ! -s "$out/rule.swift" ]; then
    echo "Found no code between the ANCHOR markers in AnticipyApp.swift."
    echo "Either the markers moved or the rule did; these checks are compiling"
    echo "nothing, which is worse than not having them."
    exit 2
fi
if ! grep -q 'func answerThatEndsTheErrand' "$out/rule.swift"; then
    echo "The anchored region no longer contains answerThatEndsTheErrand."
    exit 2
fi
echo "confirm() consults the rule, and the anchored region is $(wc -l < "$out/rule.swift" | tr -d ' ') lines"

{
    echo "import Foundation"
    echo "enum EndOfErrand {"
    cat "$out/rule.swift"
    echo "}"
} > "$out/EndOfErrand.swift"

swiftc -O \
    "$out/EndOfErrand.swift" \
    "$here/EndTheErrandTests.swift" \
    -o "$out/enderrandtests"
"$out/enderrandtests"
