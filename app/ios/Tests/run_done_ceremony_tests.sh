#!/bin/sh
# The done ceremony — how an errand coming back is allowed to arrive.
#
#   sh app/ios/Tests/run_done_ceremony_tests.sh
#
# This is the most valuable moment the product produces, and until 2026-09-06 it
# was one line: Haptics.success(). The ceremony added around it is around the
# EVIDENCE, never around applause — run_insights_tests.sh fails the build if
# anything congratulates, and that rule stays exactly as written.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/DoneCeremonyPolicy.swift"
home="$app/Views/ContentView.swift"
session="$app/AnticipyApp.swift"
for f in "$policy" "$home" "$session"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

code() { sed 's://.*$::' "$1" | sed 's:///.*$::'; }

# ===================================== THE CEREMONY NEVER SPEAKS
# The compatibility proof with run_insights_tests.sh. This policy emits TIMINGS.
# The moment it starts producing a sentence, it is producing a sentence about
# somebody's success, and this product's voice states what happened — it does
# not applaud.
if code "$policy" | grep -qiE 'congratulat|well done|keep it up|nice work|great job|nailed it|"Success'; then
    echo "The done ceremony has started congratulating somebody."
    echo
    echo "run_insights_tests.sh holds the same rule for the insights screen and"
    echo "the reason is the same here: the thing worth being ceremonial about is"
    echo "the PROOF, and proof does not need applause on top of it."
    exit 2
fi
if code "$policy" | grep -qE 'confetti|Confetti|sparkle|Sparkle|fireworks'; then
    echo "Confetti reached the done ceremony."
    echo "Robinhood paid \$7.5m for celebratory imagery attached to an action"
    echo "with consequences. Anticipy's results have consequences."
    exit 2
fi

# ================================================ THE FACT OUTRANKS THE THEATRE
if ! code "$policy" | grep -q 'maximumDelay'; then
    echo "The ceremony no longer has a delay budget."
    echo "Without one, a receipt with nine rows makes somebody wait on"
    echo "choreography to learn something about their own life."
    exit 2
fi
# The plan must COMPRESS to fit rather than grow. If `min(` disappears from the
# stagger calculation the budget stops being enforced and only the walk notices.
if ! code "$policy" | grep -q 'min(preferredStagger'; then
    echo "The stagger is no longer clamped against the budget."
    exit 2
fi

# ============================================ IT REACHES ONE ARM OF THE CARD
# DoneCard has three mutually exclusive branches and only `succeeded` is a
# completion. A failed errand arriving with a reveal sequence would be the
# product performing delight over bad news.
if ! code "$policy" | grep -q 'case notACompletion'; then
    echo "The ceremony no longer distinguishes a success from a failure."
    exit 2
fi
if ! code "$home" | grep -q 'outcome: outcome'; then
    echo "DoneCard no longer tells the policy which of its three arms this is."
    exit 2
fi

# ================================ THE FOUR LINES THAT MUST NEVER BE DELAYED
# The survey of ContentView named them: the unproven sentence, the called-off
# lead, the safety line on a failure, and the surface label. NONE of them may
# sit behind the reveal. Only the proof block is staggered.
# Order-independent: `revealed == nil` can sit on either side of the thing it
# is gating, and an ordered grep was green over exactly that mutation.
if code "$home" | grep -E 'unproven|safetyLine|calledOffLead|executionSurfaceLabel' \
   | grep -q 'revealed\|landed('; then
    echo "The ceremony reaches a line that must never be delayed."
    echo
    echo "card.unproven, the called-off lead, job.safetyLine and the surface"
    echo "label are the four things a person may need IMMEDIATELY — 'it may"
    echo "already have gone out' is the most time-critical sentence in the app."
    code "$home" | grep -nE 'unproven|safetyLine|calledOffLead|executionSurfaceLabel' \
        | grep 'revealed\|landed('
    exit 2
fi
if ! code "$home" | grep -q 'ReceiptProof(proof: proof, revealed: revealed)'; then
    echo "The proof block is no longer the thing being revealed."
    echo "It is the only part of the card made of the receipt's own evidence,"
    echo "and evidence is the only thing worth arriving one piece at a time."
    exit 2
fi

# ================================================= OPACITY, NEVER LAYOUT
# A card that grows under somebody's thumb while they read it is a card whose
# buttons move. Every revealed row keeps its space from the first frame.
if code "$home" | grep -qE 'landed\([0-9]\) \? .* : .*(EmptyView|nil)' ; then
    echo "A revealed row is being removed from layout rather than faded."
    exit 2
fi

# ======================================================= ONCE PER JOB, EVER
if ! code "$session" | grep -q 'func spendCeremony'; then
    echo "Nothing spends a job's ceremony, so it can replay."
    exit 2
fi
if ! code "$session" | grep -q 'ceremonySpentRaw'; then
    echo "The spent set is no longer durable."
    echo "A moment that replays on every cold launch is not a moment, it is a"
    echo "jingle."
    exit 2
fi
if ! code "$home" | grep -q 'task(id: job.id)'; then
    echo "The ceremony no longer runs from .task(id:)."
    echo "onAppear replays it every time the card scrolls back into view, and"
    echo "does not cancel the sequence when the card leaves."
    exit 2
fi

# ==================================== REDUCE MOTION, AND THE OWNER'S OWN SWITCH
# The app honours the pair everywhere else and this is not an exception.
if ! code "$home" | grep -q 'accessibilityReduceMotion'; then
    echo "DoneCard does not read Reduce Motion."
    exit 2
fi
if ! code "$home" | grep -q 'AppPreferences.ambientMotionKey'; then
    echo "DoneCard ignores the owner's own ambient-motion switch."
    exit 2
fi

# ===================================== THE PULSE IS NOT A repeatForever
# Banned here on evidence, not taste: a repeatForever transaction wrapping a
# whole bar once interpolated the bar's LAYOUT POSITION when the parent
# ScrollView settled, and three bars wandered across the screen.
if code "$home" | grep -q 'DoneCeremonyPolicy.breathOmega' && \
   ! code "$home" | grep -q 'TimelineView(.animation(paused: !breathes))'; then
    echo "The anticipation pulse is not driven by a paused TimelineView."
    exit 2
fi

# ================================================== ONE RATE, NOT TWO LITERALS
if code "$home" | grep -qE 'sin\(t \* 2\.1\)'; then
    echo "The card's breath rate is written as a literal instead of read from"
    echo "the policy. Four ambient rates already coexist in this app because"
    echo "the same number kept being retyped."
    exit 2
fi

# ---------------------------------------------------------------- the walk
cp "$here/DoneCeremonyTests.swift" "$out/main.swift"
swiftc "$policy" "$out/main.swift" -o "$out/ceremonytests"
"$out/ceremonytests"
