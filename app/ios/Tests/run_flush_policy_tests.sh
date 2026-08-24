#!/bin/sh
# Checks for TranscriptFlushPolicy — the layer that decides WHEN the phone
# sends what it heard, and WHICH hypothesis it takes the words from.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_flush_policy_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# The checks are worthless if the app has quietly stopped using the policy.
# Prove the wiring before proving the logic.
listener="$app/Audio/PhoneListener.swift"
if [ ! -f "$listener" ]; then
    echo "PhoneListener.swift is missing — there is nothing for the policy to serve."
    exit 2
fi
# `flushReason` subsumes `mustFlushNow`: it answers the same ceiling question
# and also names WHICH clock ran out. The check follows the caller's entry
# point rather than pinning a method name.
if ! grep -q 'flushPolicy.flushReason' "$listener"; then
    echo "PhoneListener.swift never asks whether waiting words must go out."
    echo "Without the ceiling, a person who does not pause is never transcribed."
    exit 2
fi
# And the answer is worthless if the caller cannot tell a cut from an ending.
# Passing nil for the last partial makes .ceiling unreachable for every input
# there is, silently, with no test anywhere going red to say so.
if ! grep -q 'lastPartialAt: lastPartialAt' "$listener"; then
    echo "PhoneListener asks why the flush fired but cannot answer 'a cut'."
    echo "With no last-partial time the ceiling is unreachable, every line is"
    echo "published as a finished thought, and mid-sentence cuts stay orphans."
    exit 2
fi
# And a cut that is never allowed to expire is its own defect. The mark has to
# be READ through the policy: holding it as a bare flag left it true through a
# silence and chained a brand-new thought onto a sentence from minutes before.
# `source` was written for weeks and read by nothing, and no test noticed.
if ! grep -q 'let continuesPrevious = flushPolicy.cutContinues' "$listener"; then
    echo "PhoneListener no longer asks whether a cut still runs on."
    echo "Nothing then stops the mark surviving a silence, and the next new"
    echo "thought goes out chained to a sentence nobody was still saying."
    exit 2
fi
# ...and it has to be judged on when the words APPEARED, not on when the flush
# got round to them. A continuous talker's next ceiling is a whole maxHold
# after the last one, so measuring from delivery time makes every link in a
# monologue expire before it is asked about: zero edges, no failure anywhere.
if ! grep -q 'let appeared = pendingSince ?? Date()' "$listener"; then
    echo "PhoneListener no longer knows when the words it is flushing appeared."
    echo "Judged from delivery time instead, a cut expires before the fragment"
    echo "that continues it arrives, and no mid-sentence cut is ever linked."
    exit 2
fi
# ...and a voice sample must not be a pause in a sentence. Enrollment is
# twelve seconds of "read this out loud", but a cancelled one is over in half a
# second, which is inside the gap — so the mark is closed by name here rather
# than left to the clock. The awk range pins it inside that function, in the
# same shape run_heard_tests.sh compares a declaration with.
if ! awk '/func startForEnrollment/,/^    }/' "$listener" | grep -q 'cutAt = nil'; then
    echo "Enrollment no longer closes an open mid-sentence cut."
    echo "The first real sentence after a voice sample can then go out chained"
    echo "to whatever the clock interrupted before the sample began."
    exit 2
fi
# ...and a session ending closes the mark whether or not a tail went out. The
# state a ceiling flush leaves behind is an EMPTY tail — it took every pending
# word — so a clear that lives inside the `if !tail.isEmpty` branch is exactly
# the one that never runs when it matters. The indent is part of the pattern:
# nested one level deeper is back inside that branch.
if ! awk '/func stop\(\)/,/^    }/' "$listener" | grep -q '^        cutAt = nil$'; then
    echo "stop() no longer closes an open mid-sentence cut on every path."
    echo "Toggle Listen off just after a ceiling flush and back on, and the new"
    echo "session's first line goes out naming the old session's last line."
    exit 2
fi
if ! grep -q 'cursor.observe' "$listener"; then
    echo "PhoneListener never shows the cursor every hypothesis."
    echo "Without observe(), a discarded decode window takes its words with it."
    exit 2
fi
if ! grep -q 'update.banked' "$listener"; then
    echo "PhoneListener ignores the words the cursor banked from a lost window."
    echo "Those are real speech; dropping them is how sentences disappeared."
    exit 2
fi
if grep -vE '^[[:space:]]*//' "$listener" | grep -q 'minNewWords'; then
    echo "PhoneListener still gates a flush on a new-word floor."
    echo "That marked one- and two-word lines as sent without sending them."
    exit 2
fi
if ! grep -q 'cursor.takePending' "$listener"; then
    echo "PhoneListener does not take pending words all-or-nothing."
    exit 2
fi
echo "PhoneListener observes every hypothesis, banks lost windows, and holds no word floor"

swiftc -O \
    "$app/Audio/TranscriptCursor.swift" \
    "$app/Audio/TranscriptFlushPolicy.swift" \
    "$here/TranscriptFlushPolicyTests.swift" \
    -o "$out/flushtests"
"$out/flushtests"
