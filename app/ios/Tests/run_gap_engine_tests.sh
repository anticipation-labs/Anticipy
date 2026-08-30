#!/bin/sh
# Checks for the gap law and the engine seam — the two decisions that decide
# whether a hole in the audio is SPOKEN ABOUT or spoken THROUGH.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_gap_engine_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
#
# THE DEFECT THIS SUITE GUARDS, stated once: a recognizer handed silent audio
# across a BLE gap will INVENT a sentence to fill it, and a transcript that
# carries an invention is worse than one that carries a hole. The law: a gap
# is measured (OpusFrameAssembler counts the packets that never arrived), the
# app marks it (GapMarker.text), and no engine is ever fed the silence.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

assembler="$app/BLE/OpusFrameAssembler.swift"
policy="$app/Audio/TranscriptionEnginePolicy.swift"
analyzer="$app/Audio/SpeechAnalyzerEngine.swift"
listener="$app/Audio/PhoneListener.swift"
manager="$app/BLE/PendantManager.swift"
session="$app/AnticipyApp.swift"
settings="$app/Views/SettingsView.swift"
for f in "$assembler" "$policy" "$analyzer" "$listener" "$manager" "$session" "$settings"; do
    if [ ! -f "$f" ]; then
        echo "$f is missing — there is nothing for the gap law to live in."
        exit 2
    fi
done

# ---------------------------------------------------------------- the wiring
# 1. THE ENGINE SEAM IS REAL. Both request sites must go through the policy,
#    or iOS 26's recognizer is whatever one file remembered to check.
if ! grep -q 'ListenEnginePolicy.usesAnalyzerNow' "$listener"; then
    echo "PhoneListener does not ask the policy which engine listens."
    exit 2
fi
if ! grep -q 'runAnalyzerRequest(SpeechAnalyzerRequestEngine.make' "$listener"; then
    echo "PhoneListener has an analyzer branch that never runs the analyzer."
    exit 2
fi

# 2. THE TAP FEEDS BOTH ENGINES. A tap that appends only to the legacy
#    request silences the new engine the first time the app actually runs it.
if ! grep -q 'self.analyzerEngine?.append(buffer)' "$listener"; then
    echo "The mic tap does not feed the analyzer engine."
    exit 2
fi

# 3. THE TAIL IS DELIVERED. SpeechTranscriber's documented trap: the tail of
#    a transcript never emits unless finalizeAndFinishThroughEndOfInput()
#    runs. finish() is the only place that can, so swap and stop must call it.
if ! grep -q 'finalizeAndFinishThroughEndOfInput' "$analyzer"; then
    echo "The analyzer engine does not finalize through end of input."
    echo "Without it the last words of every request die in the model."
    exit 2
fi
if ! grep -q 'analyzerEngine?.finish()' "$listener"; then
    echo "PhoneListener never finishes the engine — swaps would drop tails."
    exit 2
fi

# 4. THREE STRIKES. An engine that cannot provision its model must not spin
#    swap-forever against a phone that will never have the asset.
if ! grep -q 'analyzerDisabledForSession = true' "$listener"; then
    echo "The analyzer failure path has no session fallback."
    exit 2
fi

# 5. GAPS TRAVEL: assembler -> manager -> session, and NEVER as a transcript.
if ! grep -q 'takeGapSeconds' "$manager"; then
    echo "PendantManager never drains the assembler's gap accounting."
    exit 2
fi
if ! grep -q 'var onGap' "$manager"; then
    echo "PendantManager has no gap callback for the session to hear."
    exit 2
fi
if ! grep -q 'GapMarker.text(seconds)' "$session"; then
    echo "The session does not format gaps through GapMarker."
    echo "Freehand strings in three places is three wordings of one fact."
    exit 2
fi
#    The push path is for speech. A gap marker that rides it becomes a row
#    the brain triages, and "the radio lost 30 seconds" becomes an errand.
if grep -A8 'func recordPendantGap' "$session" | grep -q 'pushEvent'; then
    echo "Gap markers are pushed as transcript events — the brain would"
    echo "triage dead air into an errand. Gaps are marks, not speech."
    exit 2
fi

# 6. THE ESCAPE HATCH IS THE POLICY'S KEY, NOT A SECOND STRING. Two sources
#    of truth for the flag is how the hatch stops matching the toggle.
if ! grep -q 'ListenEnginePolicy.legacyFlagKey' "$settings"; then
    echo "The settings toggle does not bind to the policy's key."
    exit 2
fi

# ------------------------------------------------------------- the compiled
# swiftc only permits top-level code in a file literally named main.swift,
# so the checks copy in under that name (run_battery_tests.sh's move).
cp "$here/GapEngineTests.swift" "$out/main.swift"
swiftc -O \
    "$assembler" \
    "$policy" \
    "$out/main.swift" \
    -o "$out/gaptests"
"$out/gaptests"
