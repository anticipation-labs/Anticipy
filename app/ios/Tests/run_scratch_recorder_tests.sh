#!/bin/sh
# The scratch recorder — the input side of the word-error harness.
#
#   sh app/ios/Tests/run_scratch_recorder_tests.sh
#
# WHY THIS SUITE EXISTS. `proof/engine_or_audio.py` scores what this file
# records. Every defect the recorder can carry produces a plausible NUMBER
# rather than a visible failure: a mislabelled arm reverses the verdict, a
# dropped buffer reads as a starved microphone, a short read reads as a weak
# decoder. There is no downstream check that can catch any of them, because by
# then the only evidence left is the WAV.
#
# It COMPILES THE SHIPPING FILE, it does not restate it. `ScratchRecorder.swift`
# imports Foundation, AVFoundation and CryptoKit, all three of which exist on
# macOS, so swiftc takes the real source and the checks run against the real
# types. Nothing here can drift from the rule it polices.
#
# Exit 2 means this gate can no longer READ the source. Exit 1 means the
# recorder is wrong.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
APP="$HERE/../Anticipy"
SRC="$APP/Audio/ScratchRecorder.swift"
TESTS="$HERE/ScratchRecorderTests.swift"

for f in "$SRC" "$TESTS"; do
  if [ ! -f "$f" ]; then
    echo "scratch recorder: cannot read $f" >&2
    exit 2
  fi
done

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Swift allows top-level statements only in a file called main.swift, and the
# checks below ARE top-level statements. The suite keeps its real name in the
# repo and is copied under the name the compiler insists on.
cp "$TESTS" "$WORK/main.swift"

if ! swiftc -O -swift-version 5 -o "$WORK/scratch" "$SRC" "$WORK/main.swift" 2> "$WORK/build.log"; then
  echo "scratch recorder: the shipping source no longer compiles here" >&2
  sed -n '1,20p' "$WORK/build.log" >&2
  exit 2
fi

# The recorder writes into Documents/scratch. Under the test binary that is the
# runner's own working directory, not a phone, so the takes land in $WORK and
# leave with it.
cd "$WORK"
"$WORK/scratch"

# ---------------------------------------------------------------------------
# THE THREE FACTS THAT LIVE IN PhoneListener, NOT IN THE RECORDER.
#
# Compiling the recorder cannot see any of these, and each one silently voids
# the experiment rather than breaking it.
# ---------------------------------------------------------------------------
LISTENER="$APP/Audio/PhoneListener.swift"
[ -f "$LISTENER" ] || { echo "scratch recorder: cannot read PhoneListener.swift" >&2; exit 2; }

# Strip comments before every grep. Four legs written on 2026-09-06 were green
# over the exact code they forbade because they matched their own explanatory
# prose — see ios-test-harness, "INERT LEGS".
CODE="$WORK/listener.code"
sed -e 's://.*::' "$LISTENER" > "$CODE"

fail=0

# 1. The recorder must be fed. A tap with no `accept` call records silence, and
#    the screen would report a clean take of nothing.
if ! grep -q 'ScratchRecorder.shared.accept(' "$CODE"; then
  echo "  FAIL  the microphone tap never hands audio to the scratch recorder"
  fail=1
else
  echo "  ok    the microphone tap feeds the scratch recorder"
fi

# 2. Position. It must sit BELOW the deafen gate and ABOVE the recognizer, or
#    the WAV and the transcript scored against it describe different audio.
DEAF=$(grep -n 'deafUntil >' "$CODE" | head -1 | cut -d: -f1)
ACC=$(grep -n 'ScratchRecorder.shared.accept(' "$CODE" | head -1 | cut -d: -f1)
REQ=$(grep -n 'req.append(buffer)\|analyzerEngine?.append(buffer)' "$CODE" | head -1 | cut -d: -f1)
if [ -z "$DEAF" ] || [ -z "$ACC" ] || [ -z "$REQ" ]; then
  echo "scratch recorder: cannot locate the tap's sinks any more" >&2
  exit 2
fi
if [ "$DEAF" -lt "$ACC" ] && [ "$ACC" -lt "$REQ" ]; then
  echo "  ok    it records the same audio the recognizer received"
else
  echo "  FAIL  the recorder is not between the deafen gate and the recognizer"
  echo "        (deafen $DEAF, recorder $ACC, recognizer $REQ)"
  fail=1
fi

# 3. Arm B, and the ORDER of its two lines. Voice processing changes the input
#    node's format, so it must be set BEFORE the format is read — and the
#    read-back must happen, or an arm B that never took looks like proof the
#    setting does nothing.
SET=$(grep -n 'setVoiceProcessingEnabled(' "$CODE" | head -1 | cut -d: -f1)
ACT=$(grep -n 'voiceProcessingActual = ' "$CODE" | head -1 | cut -d: -f1)
FMT=$(grep -n 'outputFormat(forBus: 0)' "$CODE" | head -1 | cut -d: -f1)
if [ -z "$SET" ] || [ -z "$ACT" ] || [ -z "$FMT" ]; then
  echo "  FAIL  arm B is not wired: voice processing is never set, or never read back"
  fail=1
elif [ "$SET" -lt "$FMT" ] && [ "$ACT" -lt "$FMT" ]; then
  echo "  ok    arm B is applied and read back before the tap format is taken"
else
  echo "  FAIL  voice processing is set after the format is read (set $SET, read-back $ACT, format $FMT)"
  fail=1
fi

# 4. The recorder needs the tap's OWN format, or AVAudioFile converts silently.
if grep -q 'captureFormat = format' "$CODE"; then
  echo "  ok    the tap publishes the format it was actually installed with"
else
  echo "  FAIL  captureFormat is never set from the installed tap format"
  fail=1
fi

# ---------------------------------------------------------------------------
# THE DECODER'S TWO REFUSALS. Both are copied from the scorer's own hard-won
# rules (proof/engine_or_audio.py:169-191), and both are invisible downstream.
# ---------------------------------------------------------------------------
DEC="$APP/Audio/ScratchDecoder.swift"
[ -f "$DEC" ] || { echo "scratch recorder: cannot read ScratchDecoder.swift" >&2; exit 2; }
DCODE="$WORK/decoder.code"
sed -e 's://.*::' "$DEC" > "$DCODE"

if grep -q 'supportsOnDeviceRecognition' "$DCODE" && grep -q 'requiresOnDeviceRecognition = true' "$DCODE"; then
  echo "  ok    a cell that would decode in Apple's cloud is refused"
else
  echo "  FAIL  the decoder does not insist on the on-device engine under test"
  fail=1
fi

if grep -q 'words.count < 2' "$DCODE"; then
  echo "  ok    a one-word transcript is refused, not written as a decode"
else
  echo "  FAIL  an empty or one-word decode can be written as if it were a result"
  fail=1
fi

# The two cells differ by EXACTLY the vocabulary. If both carry it, R4 compares
# a thing with itself and prints VOCABULARY INERT for free.
if grep -q 'usesVocabulary ? AnticipyVocabulary.current() : \[\]' "$DCODE"; then
  echo "  ok    sf_ctx and sf_noctx differ by exactly the vocabulary"
else
  echo "  FAIL  the two on-device cells do not differ by the vocabulary alone"
  fail=1
fi

if [ "$fail" -ne 0 ]; then exit 1; fi
echo "scratch recorder: the phone can record for the harness"
