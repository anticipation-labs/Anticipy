#!/bin/sh
# RAW AUDIO NEVER LEAVES THIS PHONE — the iOS half, checked.
#
#   sh app/ios/Tests/run_local_ears_tests.sh
#
# design/LOCAL-FIRST.md rule 1, first in the list and naming the vendor itself:
# "RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone. If a
# capability needs better ears, find a better local model."
#
# That law was written and then, for months, the product streamed the pendant's
# raw Opus frames to a speech vendor's realtime websocket while LOCAL-FIRST.md's
# own scoreboard said "phone does ALL processing... law-abiding by design".
#
# `overnight/no_vendor_ears.py` greps the whole repo for the hostname and is the
# scoreboard. THIS suite checks the three things that gate cannot see, all of
# them specific to the phone:
#
#   1. nothing here can open a socket that could carry audio, whatever it is
#      named or wherever it is pointed;
#   2. nothing here asks the server for a vendor credential, so the permanent
#      410 has no client-side retry loop to spin against;
#   3. THE COPY DOES NOT PROMISE A LANE THAT IS CLOSED. This is the one that
#      matters. Those sentences were privacy promises rendered in the product,
#      and the moment the lane closed they became FALSE. A false privacy promise
#      is worse than the violation it described: it tells someone their audio
#      goes somewhere it does not, and nothing about where it went instead.
#      no_vendor_ears.py only sees sentences that NAME the vendor — it cannot
#      see "I'm opening its secure transcription stream", which was false in
#      exactly the same way and was the branch that actually rendered.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"

fail() { echo "$1"; exit 2; }

# EVERY LINE THAT IS NOT A WHOLE-LINE COMMENT, as "file:line: text".
#
# The same rule overnight/no_vendor_ears.py uses, and for the reason it gives:
# "this file's own explanation names Deepgram nine times, and a gate that could
# not survive being described would be unusable." Every phrase forbidden below
# is quoted in the comment that removed it, and a first draft of this suite went
# red on its own explanation.
#
# LINE-BASED rather than cutting from `//` to end of line: a vendor URL is
# "wss://host/...", and cutting at the first `//` would leave `"wss:` and HIDE
# the hostname from the check hunting it. A line that merely ENDS in a comment
# is still read whole.
codelines() {
    awk '{ t = $0; sub(/^[ \t]+/, "", t)
           if (t ~ /^\/\// || t ~ /^\*/ || t ~ /^\/\*/) next
           print FILENAME ":" FNR ": " $0 }' "$@"
}

swift=$(find "$app" -name '*.swift' | sort)
# shellcheck disable=SC2086
allcode=$(codelines $swift)

says() { echo "$allcode" | grep -F -q "$1"; }

# ------------------------------------------------- 1. no socket, no client
[ -f "$app/Audio/TranscriberClient.swift" ] && fail \
"TranscriberClient.swift is back.

It opened a websocket to a speech vendor and forwarded the pendant's raw Opus
frames undecoded. LOCAL-FIRST rule 1 forbids that lane. The replacement is an
ON-DEVICE transcriber (Audio/LocalTranscriber.swift), not a better-behaved
version of this one."

# Any websocket at all. The vendor gate greps hostnames; a reinstated stream
# pointed at a proxy, or at a host nobody added to that registry, would pass it
# and fail this. The app has never needed a websocket for anything else.
if says "URLSessionWebSocketTask" || says "webSocketTask("; then
    echo "$allcode" | grep -F "webSocketTask" || true
    fail "Something in the app opens a websocket again.

The only websocket this product ever had carried pendant audio off the phone."
fi
if says "connect(accessToken:"; then
    fail "The vendor transcriber client is back."
fi

# ------------------------------------------- 2. no credential, no retry loop
if says '"transcription/token"' || says "appendingPathComponent(\"transcription"; then
    fail \
"The app asks the server for a transcription token again.

That endpoint answers 410 GONE (backend/pb_hooks/transcription_token.pb.js) and
it is never coming back. The old catch block retried on ANY error, so a
permanent refusal spun a three-second reconnect loop forever against a
connected pendant - battery and radio spent on a decision that will not change.

If a remote lane is ever legitimate again the rule is written down and must not
be re-derived: a 410 is a DECISION and must stop; a 5xx or a dropped connection
is an OUTAGE and may be retried. Never widen one catch over both."
fi
if says "schedulePendantRetry"; then
    fail "The pendant reconnect loop is back with nothing for it to reconnect to."
fi
if says "send(opusFrame:"; then
    fail "Pendant audio is being forwarded somewhere again."
fi
# Dropped AT THE SOURCE. Audio that is never held cannot later be sent, which is
# a cheaper thing to keep true than a promise never to send what you are holding.
says "onOpusFrame = nil" || fail \
"Nothing clears the pendant's frame handler.

Frames must be dropped where they arrive, not queued for something downstream
to decide about."

# ------------------------------------------------------- 3. THE COPY IS TRUE
#
# Checked by ABSENCE of the false claims rather than presence of blessed wording:
# pinning exact sentences would make every copy edit a red gate, and what must
# not come back is a claim, not a phrasing.
for phrase in \
    "Deepgram" \
    "short-lived token" \
    "opening its secure transcription stream" \
    "starting transcription" \
    "transcription stream is not live yet" \
    "Pendant · listening"
do
    if says "$phrase"; then
        echo "$allcode" | grep -F "$phrase" || true
        fail \
"The app still tells the owner \"$phrase\".

That lane is closed, so the sentence is now FALSE. Say what is true: the pendant
cannot turn sound into words yet, nothing from it is recorded or sent anywhere,
and the phone's microphone is the ear that works."
    fi
done

# And it must not have gone SILENT instead. Deleting the promise and leaving a
# blank was explicitly not the fix: somebody who read the old sentence needs to
# find the new answer in the same place.
says "nothing I do with sound leaves this phone" || fail \
"Settings no longer says where pendant sound goes.

A stranger reading 'Between us' deserves the current answer, not a blank where
a privacy promise used to be."
says "can't turn its sound into words yet" || fail \
"The pendant status note no longer says why it is silent."

echo "no vendor socket, no vendor credential, no retry loop, and the copy is true"
