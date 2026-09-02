#!/bin/sh
# Regression gate for the retired phone-side "end the errand" classifier.
# A typed answer is an inbound turn. The phone may transport it, but must not
# interpret keywords and cancel the job before Conversation.on_reply sees it.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
session="$app/AnticipyApp.swift"
policy="$app/Backend/AnswerRoutePolicy.swift"

if grep -R -n 'answerThatEndsTheErrand\|endsTheErrand\|endTheErrand' \
    "$session" "$policy" "$here/AnswerRoutePolicyTests.swift"; then
    echo "The phone-side end-the-errand classifier returned."
    echo "Typed answers must reach Conversation.on_reply as app_reply events."
    exit 2
fi

if grep -q 'trigger: "their answer read as ending it"' "$session"; then
    echo "The phone can still cancel a job by interpreting an answer."
    exit 2
fi

if ! grep -q 'pushEvent(kind: "app_reply"' "$session"; then
    echo "Typed answers no longer reach the brain as app_reply events."
    exit 2
fi

echo "phone-side keyword cancellation is absent"
echo "typed answers reach the brain as app_reply events"
