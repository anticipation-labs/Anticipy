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
#
# Matched without the closing paren on purpose. These two call sites now also
# carry when the words were spoken and whether the clock cut them out of the
# middle of a sentence, and pinning the whole argument list made a legitimate
# addition read as the wiring being torn out. What this check is about is the
# SOURCE label; tests/test_pendant_transcription_wiring.py already learned the
# same lesson about its own line.
if ! code | grep -q 'heard(line, from: .phoneMic'; then
    echo "The phone-mic callback does not name itself as the phone mic."
    exit 2
fi
if ! code | grep -q 'heard(line, speaker: tag, from: .phoneMic'; then
    echo "The voice-tagged phone-mic callback does not name its source."
    exit 2
fi
# And both must carry what the phone knows about the line, because both
# arguments DEFAULT. Delete `at: at` and heard() stamps Date() at push time
# instead: a line buffered offline and flushed hours later reports the moment
# the signal came back, which is the reordering the capture stamp exists to
# end, and nothing else here would have gone red. The closing paren these two
# checks used to carry was the only thing pinning the argument list, so what it
# protected is spelled out instead of dropped.
if ! code | grep -q 'heard(line, from: .phoneMic, at: '; then
    echo "The phone-mic callback no longer carries when the words were spoken."
    echo "heard() defaults that instant to now, so every line silently reverts"
    echo "to being stamped when the network took it, not when it was said."
    exit 2
fi
if ! code | grep -q 'heard(line, speaker: tag, from: .phoneMic, at: '; then
    echo "The voice-tagged phone-mic callback dropped the spoken instant."
    echo "heard() defaults it to now, so the stamp silently becomes push time."
    exit 2
fi
if [ "$(code | grep -c 'continuesPrevious: continues)')" -lt 2 ]; then
    echo "A phone-mic line no longer says whether the clock cut it in half."
    echo "That flag is the only thing that makes a mid-sentence fragment a"
    echo "linked part of a thought instead of an orphan line of its own, and"
    echo "it defaults to false, so losing it is silent."
    exit 2
fi
if ! code | grep -q 'heard(line, from: .pendant)'; then
    echo "The pendant transcript callback does not name itself as the pendant."
    echo "This is the one that buzzed all day: the phone mic is off, so the old"
    echo "test read 'not listening' and treated ambient speech as typed."
    exit 2
fi
echo "line ack: decided by source, and all three capture paths declare theirs"
