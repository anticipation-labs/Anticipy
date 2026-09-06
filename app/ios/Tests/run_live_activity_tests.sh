#!/bin/sh
# The lock screen — the most privileged surface this product has.
#
#   sh app/ios/Tests/run_live_activity_tests.sh
#
# A Live Activity sits on a LOCKED phone, in front of whoever picks it up,
# without the owner choosing to look. Two rules follow from that, they are
# written at the top of LiveActivityPolicy.swift, and the greps below are what
# stops them from being only written down:
#
#   1. it never quotes anybody
#   2. it never approves
#
# LiveActivityPolicy is pure Foundation, so the production source compiles
# straight in and the walk in LiveActivityTests.swift is against the real thing.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
widget="$here/../Widget"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/LiveActivityPolicy.swift"
shape="$app/ListeningActivity.swift"
control="$app/LiveActivityController.swift"
view="$widget/AnticipyLiveActivity.swift"
bundle="$widget/AnticipyWidget.swift"
plist="$app/Info.plist"
proj="$here/../project.yml"
for f in "$policy" "$shape" "$control" "$view" "$bundle" "$plist" "$proj"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

code() { sed 's://.*$::' "$1" | sed 's:///.*$::'; }

# ============================================== ONE: IT NEVER QUOTES ANYBODY
#
# The strongest form of this rule is structural: the state that crosses to the
# widget process has no field that can carry a sentence. Adding one is the
# single change that would turn this feature into the worst thing this product
# could do, so it is the first thing checked.
state=$(awk '/public struct ContentState/{g=1} g{print} g&&/^    \}$/{exit}' "$shape")
if [ -z "$state" ]; then
    echo "ListeningActivityAttributes.ContentState is gone or was renamed."
    echo "That struct IS the rule: it is what crosses to the lock screen."
    exit 2
fi
# `reason` is the one sanctioned string, and it is a closed set of wire words
# spelled out in ActivityReason. Any OTHER String field is the failure.
strays=$(printf '%s\n' "$state" | sed 's:///.*$::' \
    | grep -E '^[[:space:]]*(var|let)[[:space:]]+[A-Za-z_]+[[:space:]]*:[[:space:]]*String' \
    | grep -v '[[:space:]]reason[[:space:]]*:' || true)
if [ -n "$strays" ]; then
    echo "The lock-screen state now carries a String."
    echo
    echo "Everything on that surface is a COUNT, a FLAG or a DATE, and the"
    echo "absence of a text field is the enforceable half of 'it never quotes"
    echo "anybody'. A lock screen is readable over a shoulder on a train; an"
    echo "always-on microphone that prints what it heard onto one is the worst"
    echo "thing this product could do."
    echo
    echo "The one exception is \`reason\`, a closed set of wire words. If you"
    echo "need another field, make it an Int or a Bool, or extend that closed"
    echo "set in ActivityReason — never free text."
    echo
    printf '%s\n' "$strays"
    exit 2
fi

# The other half: nothing the app SAYS may reach the capsule either. The
# controller is the only thing that builds a ContentState, and the only field
# it derives from what was said is a count.
if code "$control" | grep -qE '\.goal|\.text|transcript|partial|\.result|sessionLines\[|anticipySays'; then
    echo "The Live Activity controller touches what somebody actually said."
    echo
    echo "It may read a COUNT of lines and nothing else. \`goal\`, \`result\`,"
    echo "transcript text and partials are somebody's words, and the lock screen"
    echo "does not get them."
    code "$control" | grep -nE '\.goal|\.text|transcript|partial|\.result|sessionLines\[|anticipySays'
    exit 2
fi

# And the view: every string it draws comes from the policy or is a fixed word
# in that file. It must not interpolate anything it was handed.
if code "$view" | grep -qE 'Text\(.*state\.(reason|heard)[^)]*\)\s*$' \
   && ! code "$view" | grep -q 'things heard'; then
    echo "The lock-screen view prints a state field directly."
    exit 2
fi
if code "$view" | grep -qE 'goal|transcript|partial|result|\.words|sentence'; then
    echo "The lock-screen view names something that carries words."
    code "$view" | grep -nE 'goal|transcript|partial|result|\.words|sentence'
    exit 2
fi

# ============================================== TWO: IT NEVER APPROVES
#
# "Nothing sends without your OK" means an OK given with the consequence in
# front of you. A lock-screen button is a one-tap yes on a surface too small to
# carry the consequence, given by whoever is holding the phone.
if code "$policy" | grep -qiE 'case (approve|confirm|send|pay|accept)'; then
    echo "LiveActivityPolicy.Action grew a case that COMMITS something."
    echo
    echo "The lock screen may SAY something is waiting and may OPEN the app at"
    echo "it. It may not approve, send, confirm or pay. Whoever is holding this"
    echo "phone is not necessarily its owner, and a one-tap yes on a locked"
    echo "screen is a yes given without the consequence in front of you."
    exit 2
fi
for f in "$shape" "$view"; do
    if code "$f" | grep -qE 'struct \w*(Approve|Confirm|Send|Pay)\w*Intent'; then
        echo "$(basename "$f") declares an intent that commits something."
        echo "See the rule above: there is exactly one intent here and it stops"
        echo "the microphone."
        exit 2
    fi
done
intents=$(code "$shape" | grep -cE ': (LiveActivityIntent|AppIntent)' || true)
if [ "$intents" != "1" ]; then
    echo "Expected exactly one lock-screen intent, found $intents."
    echo "The one is StopListeningIntent. Adding a second is a decision about"
    echo "what a locked phone may do, and it belongs in this file's header"
    echo "before it belongs in code."
    exit 2
fi

# ============================================================== EXACTLY ONE
#
# A Live Activity OUTLIVES THE PROCESS — iOS keeps it on the lock screen after a
# force-quit, and it is still there when the app comes back. The controller's
# handle is not: it is an instance property and returns nil. Asking "is my
# handle nil?" before requesting therefore stacked a second capsule on every
# relaunch, a third on the next, with nothing in the app able to see them.
#
# The question has to be put to iOS, not to a local variable.
if ! grep -q 'Activity<ListeningActivityAttributes>.activities' "$control"; then
    echo "The controller no longer asks iOS what it is already showing."
    echo
    echo "Then it cannot know about the capsule a previous run of this app left"
    echo "on the lock screen, and it will request another one beside it. That"
    echo "is how an app ends up with a stack of its own notifications that"
    echo "nothing on the phone can clear but a reinstall."
    exit 2
fi
if ! grep -q 'adoptExistingActivity()' "$control"; then
    echo "Nothing adopts the activity this app already has on screen."
    exit 2
fi
requests=$(code "$control" | grep -c 'Activity.request(' || true)
if [ "$requests" != "1" ]; then
    echo "Expected exactly one Activity.request call site, found $requests."
    echo "One capsule means one place that can create one."
    exit 2
fi
# The adoption has to happen BEFORE the request, or it adopts nothing.
adopt_line=$(grep -n 'adoptExistingActivity()$' "$control" | head -1 | cut -d: -f1)
req_line=$(grep -n 'Activity.request(' "$control" | head -1 | cut -d: -f1)
if [ -z "$adopt_line" ] || [ -z "$req_line" ] || [ "$adopt_line" -ge "$req_line" ]; then
    echo "adoptExistingActivity() does not run before Activity.request()."
    echo "Adopting after requesting is adopting the one you just made."
    exit 2
fi

# ================================================ IT ENDS RATHER THAN LINGERS
# An app that will not leave somebody's lock screen is an app they delete.
if ! grep -q 'func finish()' "$control"; then
    echo "The controller can no longer end the activity."
    exit 2
fi
if ! grep -q 'func tearDown()' "$control"; then
    echo "The controller can no longer tear the activity down at a sign-out."
    echo "The next person on this phone must not inherit a capsule that says"
    echo "somebody is being listened to."
    exit 2
fi
if ! grep -q 'LiveActivityController.shared.tearDown()' "$control"; then
    echo "Nothing calls tearDown(). A sign-out has to take the capsule with it."
    exit 2
fi

# ==================================================== IT DOES NOT PUSH A CLOCK
# A Live Activity updated once a second is one iOS throttles and then stops
# delivering, which is how these end up frozen on other people's phones. The
# widget runs its own timer off `startedAt`.
if ! grep -q 'style: .timer' "$view"; then
    echo "The lock screen no longer runs its own clock."
    echo
    echo "Text(started, style: .timer) is what keeps the app from waking once a"
    echo "second to push a number a timer can derive. iOS throttles frequent"
    echo "updates and then stops delivering them, and the capsule freezes."
    exit 2
fi
# ...and the view must put back the half the clock replaces. Without this the
# offline capsule reads "3 things heard · 2:12" on a phone with no signal.
if ! code "$view" | grep -q 'LiveActivityPolicy.qualifier('; then
    echo "The live line no longer carries the reason's qualifier."
    echo
    echo "While the microphone is on, the view draws its own clock instead of"
    echo "the policy's \`detail\` — so anything \`detail\` says BESIDE the count"
    echo "and the time is dropped on the floor. Today that is the one sentence"
    echo "telling somebody their words are staying on this phone."
    exit 2
fi
if code "$control" | grep -qE 'Timer\.(publish|scheduledTimer)|repeatForever'; then
    echo "The controller runs a timer. See above: it pushes when the FACE"
    echo "changes, and the clock is not part of the face."
    exit 2
fi
if ! code "$control" | grep -q 'pushType: nil'; then
    echo "The activity asked for a push token."
    echo "Nothing off this phone updates this capsule. A remote-updatable Live"
    echo "Activity is a server that can write to a locked screen."
    exit 2
fi

# ============================================== IT IS ACTUALLY BUILDABLE
if ! grep -q '<key>NSSupportsLiveActivities</key>' "$plist"; then
    echo "Info.plist lost NSSupportsLiveActivities. Without it ActivityKit"
    echo "refuses every request at runtime and the feature is silently dead."
    exit 2
fi
if ! grep -q 'AnticipyLiveActivity()' "$bundle"; then
    echo "The widget bundle no longer carries the Live Activity, so iOS has"
    echo "nothing to render when the app requests one."
    exit 2
fi
for f in ListeningActivity.swift LiveActivityPolicy.swift; do
    if ! awk '/^  AnticipyWidget:/{g=1} g&&/^  [A-Za-z]/&&!/^  AnticipyWidget:/{g=0} g' "$proj" \
        | grep -q -- "- path: Anticipy/$f"; then
        echo "project.yml no longer compiles $f into the widget target."
        echo "Both targets need it: the widget decodes the struct the app"
        echo "encoded, and both have to agree on what the capsule may say."
        exit 2
    fi
done
# The extension stays poor on purpose — an app group is what makes provisioning
# refuse on a fresh account, and LiveActivityIntent exists so it is not needed.
if awk '/^  AnticipyWidget:/{g=1} g&&/^  [A-Za-z]/&&!/^  AnticipyWidget:/{g=0} g' "$proj" \
    | grep -qi 'group.ai.anticipy\|APPLICATION_GROUP\|com.apple.security.application-groups'; then
    echo "The widget target grew an app group."
    echo "It has never had one, and the stop button works without one because"
    echo "LiveActivityIntent runs in the APP'S process. Read the note on the"
    echo "Anticipy target's dependency before adding one."
    exit 2
fi

# =============================================================== the walk
cp "$here/LiveActivityTests.swift" "$out/main.swift"
swiftc "$policy" "$out/main.swift" -o "$out/liveactivitytests"
"$out/liveactivitytests"
