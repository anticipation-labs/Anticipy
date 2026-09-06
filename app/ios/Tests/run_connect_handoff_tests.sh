#!/bin/sh
# THE CONNECT HANDOFF — the twenty seconds where this feature is compliant or
# broken.
#
#   sh app/ios/Tests/run_connect_handoff_tests.sh
#
# Spec: "Connections: how Anticipy asks, learns, and never says Composio",
# 2026-09-05. Server contract: spike/two-hands/src/connections/contract.ts.
#
# ConnectHandoff is pure Foundation, so the real production source is compiled
# straight in — no simulator, no scheme, no signing, no network. The source
# legs below are here rather than in the suite because each is about the
# EXISTENCE or ABSENCE of something in the file, which no runtime assertion can
# see; the one leg that must never be softened — that no embedded web view is
# named anywhere in the handoff — lives in the suite instead, where it is
# checked against fixtures first so it cannot pass by matching nothing.
#
# Exit code is the result. Non-zero means a connect could open somewhere Google
# refuses to sign anyone in, or a deep link could mark an app connected for a
# person who never tapped anything.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
repo=$(cd "$here/../../.." && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Backend/ConnectHandoff.swift"
suite="$here/ConnectHandoffTests.swift"
[ -f "$policy" ] || { echo "missing $policy"; exit 2; }
[ -f "$suite" ] || { echo "missing $suite"; exit 2; }

code() { grep -vE '^[[:space:]]*(//|///)' "$1"; }

# ------------------------------------------------------------ the policy is pure
# The whole point of a policy layer is that "what will the app open, and for
# whom" is answerable with no phone, no browser and no account. Foundation is
# the only import this file may have: AuthenticationServices, UIKit or SwiftUI
# in here means the decision has been folded back into the thing it exists to
# be testable without — and it is also how a class name that must never appear
# arrives.
imports=$(grep -E '^[[:space:]]*import[[:space:]]' "$policy" \
    | sed -E 's/^[[:space:]]*import[[:space:]]+//' | sort -u | tr '\n' ' ')
if [ "$imports" != "Foundation " ]; then
    echo "ConnectHandoff imports more than Foundation: ${imports:-nothing}"
    echo "The handoff decides what opens; it does not open it. A UI or web"
    echo "framework in here is a decision that can no longer be run on a laptop"
    echo "at the instant that matters."
    exit 2
fi

# ------------------------------------------------------------------ LAW 1
# Nothing here may decide what a human's words mean. WHICH app the owner meant
# is a model's question, answered against the catalog by ToolkitJudge in the
# server contract; this file is handed a slug it never chose. A regex over text
# would be that decision moving back into a pattern.
if code "$policy" | grep -qE 'NSRegularExpression|options:[[:space:]]*\.regularExpression'; then
    echo "ConnectHandoff matches a pattern against text."
    echo "HARNESS-LAWS Law 1: the only strings it may read are an identifier's"
    echo "shape, a URL's scheme and host, and the machine tokens of our own"
    echo "done page. None of those is prose."
    exit 2
fi

# -------------------------------------------------- nobody's tokens but yours
# contract.ts: "A constant here would mean one person's tokens serving
# everybody, which is the worst failure this system can have." During the spike
# one operator's own mailbox was connected by hand; it was revoked and deleted.
# An owner row id is fifteen lowercase alphanumerics, so a literal of that shape
# in this file is that failure written down.
if code "$policy" | grep -oE '"[a-z0-9]{15}"' | grep -q '[0-9]'; then
    echo "ConnectHandoff carries a literal shaped like an owner row id:"
    code "$policy" | grep -oE '"[a-z0-9]{15}"' | grep '[0-9]'
    echo "Every connection belongs to the owner signed into THIS phone. The"
    echo "owner is an argument, resolved per request, never a constant."
    exit 2
fi

# ------------------------------------------- the link allowlist, in the source
# The spec's first rule is that we own the ask: every link is anticipy.ai/c/,
# never the provider's own and never Google's. That is an ALLOWLIST — a
# blocklist is one new hostname from being wrong — and widening it has to be a
# visible diff rather than a value somebody adds in passing. Spelled as "sort
# the hosts out of the literal and compare the names" so re-wrapping stays
# green; a set that stopped being a literal at all extracts as nothing and is
# red here, which is the same hole with better manners.
hosts=$(tr '\n' ' ' < "$policy" \
    | sed -n 's/.*connectLinkHosts:[[:space:]]*Set<String>[[:space:]]*=[[:space:]]*\[\([^]]*\)\].*/\1/p' \
    | tr -d ' "' | tr ',' '\n' | grep -v '^$' | sort | tr '\n' ' ')
if [ "$hosts" != "anticipy.ai " ]; then
    echo "The connect-link allowlist is not the one host the spec names."
    echo "  the source declares : ${hosts:-nothing this leg can read}"
    echo "  the spec names      : anticipy.ai"
    echo ""
    echo "Every ask is ours: single-use token, ten minutes, bound to the owner."
    echo "Adding a host here is how a raw provider link reaches a person, which"
    echo "is what happened on 2026-09-05 and why the rule exists."
    exit 2
fi

# ------------------------------------------------- the enums are closed, in the source
# A fourth way to open a connect link is a SCHEMA CHANGE and has to be defended
# in a diff. The one that matters is an embedded web view, which is not a
# fallback or a compatibility mode: Google answers a sign-in inside one with
# `disallowed_useragent` and the connect fails outright. The suite reads this
# file for the class names; this reads the DECLARATION, which is the half a
# name-scan cannot see — a case called `.inApp` names nothing forbidden.
cases_of() {
    awk -v want="$2" '
        $0 ~ ("^enum " want "[ :{]") { inside = 1; next }
        inside && /^\}/ { exit }
        inside && /^[[:space:]]*case [a-z]/ {
            line = $0
            sub(/^[[:space:]]*case /, "", line)
            sub(/[ (=:].*$/, "", line)
            print line
        }
    ' "$1" | sort | tr '\n' ' '
}

presentations=$(cases_of "$policy" ConnectPresentation)
if [ "$presentations" != "authSession refused systemBrowser " ]; then
    echo "ConnectPresentation is no longer the two openings and the refusal."
    echo "  the source declares : ${presentations:-nothing this leg can read}"
    echo "  expected            : authSession refused systemBrowser"
    echo ""
    echo "Both openings are a real browser the person can see the address bar"
    echo "of. A third opening is how the connect stops working."
    exit 2
fi

dones=$(cases_of "$policy" ConnectDone)
if [ "$dones" != "cancelled connected failed unreadable " ]; then
    echo "ConnectDone is no longer four states."
    echo "  the source declares : ${dones:-nothing this leg can read}"
    echo "  expected            : cancelled connected failed unreadable"
    echo ""
    echo "\"it connected\", \"they backed out\", \"it went wrong\" and \"we cannot"
    echo "read this\" are four different things, and a smaller answer cannot"
    echo "keep them apart — the deep link is reachable by anyone, so the"
    echo "fourth state is the one that stops a stranger's URL being read as"
    echo "one of the other three."
    exit 2
fi

# ---------------------------------- every refusal cause is actually counted
# ConnectRefusal carries no associated values on purpose, so its census is the
# compiler's (`allCases`) rather than a list somebody types — the failure mode
# CalendarHandPolicy hit, where three causes were missing from a hand-written
# census and two of them could silently share one code. What still needs a
# human is the literal the suite asserts, so it is compared here.
declared=$(awk '/^enum ConnectRefusal/{e=1} e && /^[[:space:]]*case [a-z]/{n++}
                e && /^\}/{exit} END{print n+0}' "$policy")
asserted=$(grep -E '^let REFUSAL_CODES = [0-9]+' "$suite" | grep -oE '[0-9]+' | head -1)
if [ -z "$asserted" ] || [ "$declared" -ne "$asserted" ]; then
    echo "The refusal census does not match the enum."
    echo "  ConnectRefusal declares : ${declared} causes"
    echo "  the suite asserts       : ${asserted:-none}"
    echo "Add the case, then update REFUSAL_CODES in ConnectHandoffTests.swift."
    exit 2
fi

# ------------------------------------------- the callback scheme is registered
# A deep link the app is not registered for never arrives, and the failure is
# silent: the connect finishes at the other end, the browser hands the URL to
# nobody, and the phone sits on a spinner. The scheme is shared with the
# widget's doorbell, and Info.plist is REGENERATED from project.yml, so both
# have to name it or the next `xcodegen generate` takes it away.
scheme=$(sed -n 's/.*static let callbackScheme = "\([^"]*\)".*/\1/p' "$policy" | head -1)
if [ -z "$scheme" ]; then
    echo "This gate can no longer read the callback scheme out of the handoff."
    exit 2
fi
plist="$app/Info.plist"
if [ -f "$plist" ] && ! grep -q "<string>$scheme</string>" "$plist"; then
    echo "The callback scheme \"$scheme\" is not registered in $plist."
    echo "The done page redirects to $scheme://connected/{toolkit}. If the app"
    echo "does not own the scheme, that URL reaches nobody: the connect"
    echo "finishes at the other end and the phone sits on a spinner with no"
    echo "error anywhere. (The bundle id contains the word too, so this leg"
    echo "reads the URL-scheme entry itself and not the file.)"
    exit 2
fi
yml="$here/../project.yml"
if [ -f "$yml" ] && ! grep -qE "^[[:space:]]*-[[:space:]]*$scheme[[:space:]]*$" "$yml"; then
    echo "The callback scheme \"$scheme\" is not in project.yml's URL schemes."
    echo "Info.plist is REGENERATED from project.yml, so a scheme that lives"
    echo "only in the plist is a scheme the next \`xcodegen generate\` deletes."
    exit 2
fi

# ----------------------------------------- the clock agrees with the server
# LINK_TTL_MS in the server contract is what actually kills the link. If this
# app believes an attempt can still be alive after the server has expired it,
# it will accept a callback the server would not have produced. A missing
# contract is a NOTE, not a failure: a gate that goes red over a file in
# another tree is a gate somebody turns off.
contract="$repo/spike/two-hands/src/connections/contract.ts"
if [ -f "$contract" ]; then
    # Both sides are multiplied out rather than string-compared, so `600` and
    # `10 * 60` agree and nobody has to spell a constant a particular way to
    # keep a gate green — a leg that goes red on somebody's arithmetic is a leg
    # people learn to edit.
    product() {
        awk -v s="$1" 'BEGIN {
            p = 1; n = 0
            sub(/^[^=]*=/, "", s)
            while (match(s, /[0-9]+/)) {
                p *= substr(s, RSTART, RLENGTH); n++
                s = substr(s, RSTART + RLENGTH)
            }
            print (n ? p : "")
        }'
    }
    ttl_ms=$(product "$(grep 'LINK_TTL_MS' "$contract" | head -1)")
    ours_s=$(product "$(grep 'attemptLifetime: TimeInterval' "$policy" | head -1)")
    if [ -n "$ttl_ms" ] && [ -n "$ours_s" ] && [ "$ttl_ms" -ne $((ours_s * 1000)) ]; then
        echo "The attempt's lifetime disagrees with the server's link TTL."
        echo "  contract.ts LINK_TTL_MS : ${ttl_ms}ms"
        echo "  ConnectHandoff believes : $((ours_s * 1000))ms"
        echo ""
        echo "A phone that thinks an attempt is still alive after the server has"
        echo "expired the link will accept a callback the server could not have"
        echo "produced. The contract owns this number; this app agrees with it."
        exit 2
    fi
else
    echo "note: $contract is not in this tree, so the ten-minute link could not"
    echo "      be checked against the server contract."
fi

# --------------------------------------------- and the half this part does not own
# The deep link only arrives if something routes it. `AnticipyApp.onOpenURL`
# answers the widget's doorbell and IGNORES every other host, so a connect
# finishing in the system browser today reaches nobody. That wiring belongs to
# the view part, not this one, so it is said out loud rather than failed on: a
# gate that goes red over a file this change may not touch is a gate somebody
# turns off (the precedent is run_owner_mirror_tests.sh's two notes).
session="$app/AnticipyApp.swift"
if [ -f "$session" ] && ! grep -q 'ConnectHandoff' "$session"; then
    echo "note: AnticipyApp.swift does not mention ConnectHandoff, so nothing"
    echo "      routes $scheme://$(sed -n 's/.*static let callbackHost = "\([^"]*\)".*/\1/p' "$policy" | head -1)/{toolkit} into parseDone yet."
    echo "      A connect that finishes in the system browser is dropped until"
    echo "      onOpenURL hands that host to the handoff."
fi

echo "the handoff is pure, prose-free, owner-agnostic and closed at three enums"
echo "the link allowlist is one host and the callback scheme is registered"

# swiftc only permits top-level code in a file literally named main.swift, so
# the suite is copied under that name — the same reason run_calendar_hand_tests.sh
# does it. The suite is handed the production source path: its first leg reads
# that file and fails if either embedded-web-view class name appears in it.
cp "$suite" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/connecthandofftests"
"$out/connecthandofftests" "$policy"
