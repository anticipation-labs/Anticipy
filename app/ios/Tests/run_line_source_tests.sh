#!/bin/sh
# Checks who gets a buzz for a finished line.
#
#   sh app/ios/Tests/run_line_source_tests.sh
#
# heard() cannot be lifted out and run: it lives on a @MainActor session that
# drags in SwiftUI, Combine, the network layer, the microphone and the pendant.
# So this proves the WIRING instead — which is where the bug was. The rule
# itself is one comparison; what was wrong was that the comparison asked the
# phone mic's state instead of asking where the line came from.
#
# Exit code is the result. Non-zero means the ack can misfire again.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
src="$app/AnticipyApp.swift"

code() { grep -vE '^[[:space:]]*//' "$src"; }

if code | grep -q 'if !listener.isListening { Haptics.tap() }'; then
    echo "The ack is decided by the PHONE MIC's state again."
    echo "That is not the same question as 'did a person type this'. With a"
    echo "pendant connected and the phone mic off, every ambient sentence all"
    echo "day buzzes the phone; and a line typed while the mic is running gets"
    echo "no ack at all."
    exit 2
fi
if ! code | grep -q 'if source == .typed { Haptics.tap() }'; then
    echo "heard() no longer acks on the line's SOURCE."
    exit 2
fi

# Every capture path must say where it came from, because the default is
# .typed — an unlabelled capture call site is a buzzing phone.
if ! code | grep -q 'heard(line, from: .phoneMic)'; then
    echo "The phone-mic callback does not name itself as the phone mic."
    exit 2
fi
if ! code | grep -q 'heard(line, speaker: tag, from: .phoneMic)'; then
    echo "The voice-tagged phone-mic callback does not name its source."
    exit 2
fi
if ! code | grep -q 'heard(line, from: .pendant)'; then
    echo "The pendant transcript callback does not name itself as the pendant."
    echo "This is the one that buzzed all day: the phone mic is off, so the old"
    echo "test read 'not listening' and treated ambient speech as typed."
    exit 2
fi
echo "line ack: decided by source, and all three capture paths declare theirs"
