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

# ---------------------------------------------------------------- the lineage
# The echo guard is armed by a fact only PhoneListener holds: the cursor lost
# its record of what it had already sent. TranscriptFlushPolicyTests compiles
# the policy and the cursor and CANNOT SEE this file, so unwiring any line
# below leaves all 48 checks green while duplicates go back on the feed. That
# is the shape of defect this suite was written blind to last time.
#
# Read from a copy with the comment lines stripped, because every sentence
# below is also written in the prose around the code it describes, and a leg
# satisfied by the comment explaining it enforces nothing.
code="$out/PhoneListener.nocomments.swift"
grep -vE '^[[:space:]]*//' "$listener" > "$code"

# The call is read with the spaces and newlines squeezed out, as one string.
# Read line by line, three of these legs passed while the thing they name was
# gone: `deliver` also asks `cutContinues(cutAt:wordsAppearedAt:)`, so a leg
# grepping the deliver body for `wordsAppearedAt: wordsAppearedAt` was answered
# by a DIFFERENT call four lines below the one it meant to read.
call=$(awk '/private func deliver/,/^    }/' "$code" | tr -d ' \n')
if ! printf '%s' "$call" | grep -q 'flushPolicy.isEchoOfPrevious(line,previous:last,'; then
    echo "PhoneListener no longer asks the policy whether a line is a duplicate."
    exit 2
fi
# ...and it asks with the lineage break, not with an elapsed time. Every line
# leaves here either on a partial or one utterance gap after the last one, so
# two timer-delivered lines are ALWAYS further apart than the gap — a machine
# re-render and a person saying it again alike. A window of any width holds
# both or neither, which is how the 2.6s window let the recorded 2026-08-17
# duplicate back onto the feed while still eating the tester's second attempt.
if ! printf '%s' "$call" | grep -q 'lineageBrokeAt:broke,'; then
    echo "PhoneListener judges duplicates without the lineage break."
    echo "Elapsed time cannot separate a re-decoded sentence from a person"
    echo "repeating themselves: the debounce gives both the same floor."
    exit 2
fi
# ...and on when the words APPEARED, which is what stops the mark reaching a
# sentence spoken a minute after the swap that armed it. Pinned ADJACENT to the
# lineage argument, so only this call can answer for it.
if ! printf '%s' "$call" | grep -q 'lineageBrokeAt:broke,wordsAppearedAt:wordsAppearedAt)'; then
    echo "PhoneListener no longer says when the words it is judging appeared."
    echo "Measured from delivery time the arming never expires, and the next"
    echo "repeat after any task rotation is deleted with no trace."
    exit 2
fi
# One break answers for one line. A mark with nothing to clear it is a mode:
# the swap that armed it would go on eating repeats until the next swap.
if ! awk '/private func deliver/,/^    }/' "$code" | grep -q '^        lineageBrokeAt = nil$'; then
    echo "PhoneListener never closes the lineage break it opened."
    exit 2
fi
# A retired recognition task takes the cursor's record with it and its held
# audio is replayed into the new one. That pairing IS the duplicate.
#
# The indent is load-bearing, and not for tidiness: `startRecognition` encloses
# the whole recognition callback, so an awk range over it also contains
# `self.lineageBrokeAt = Date()` from the in-task branch. A leg written without
# the anchors passed with this line deleted, answered by the one nested inside
# the closure below it.
if ! awk '/private func startRecognition/,/^    }/' "$code" \
     | grep -q '^        lineageBrokeAt = Date()$'; then
    echo "PhoneListener does not mark the lineage break at a task seam."
    echo "The recorded 2026-08-17 duplicate arrives that way and goes on the feed."
    exit 2
fi
# ...and so does a decode window replaced mid-task, which is the commoner half.
if ! grep -qE 'update\.didReset.*self\.lineageBrokeAt = Date\(\)' "$code"; then
    echo "PhoneListener ignores the cursor telling it the window was replaced."
    exit 2
fi
# ORDER, and it is load-bearing: banked words are words the cursor is handing
# over BECAUSE the window died under them. They were never sent. Arming in
# front of them suppresses the one delivery that exists to stop speech being
# lost — the 12-second sentence collapsing to "Of August".
banked_line=$(grep -n 'self.deliver(banked' "$code" | head -1 | cut -d: -f1)
arm_line=$(grep -nE 'update\.didReset.*self\.lineageBrokeAt = Date\(\)' "$code" \
           | head -1 | cut -d: -f1)
if [ -z "$banked_line" ] || [ -z "$arm_line" ] || [ "$arm_line" -lt "$banked_line" ]; then
    echo "PhoneListener arms the echo guard before it hands over banked words."
    echo "Those words were never sent; suppressing them deletes real speech."
    exit 2
fi
echo "PhoneListener observes every hypothesis, banks lost windows, holds no word floor,"
echo "and judges duplicates on the lineage break rather than on elapsed time"

swiftc -O \
    "$app/Audio/TranscriptCursor.swift" \
    "$app/Audio/TranscriptFlushPolicy.swift" \
    "$here/TranscriptFlushPolicyTests.swift" \
    -o "$out/flushtests"
"$out/flushtests"
