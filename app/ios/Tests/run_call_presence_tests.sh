#!/bin/sh
# Checks for CallPresencePolicy — what the telephony stack is doing, what the
# listener should do about it, and which conversation boundaries that produced.
#
#   sh app/ios/Tests/run_call_presence_tests.sh
#
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network,
# and no device that has to receive a real phone call.
#
# Exit code is the result. Non-zero means a case came back wrong, or one of the
# four source rules below no longer holds.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
policy="$app/Audio/CallPresencePolicy.swift"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

[ -f "$policy" ] || { echo "missing $policy"; exit 2; }

# PROSE IS NOT CODE. The file explains, at length, the FaceTime question it
# cannot answer and the duration threshold it must not grow — so a scan that
# read comments would flag the explanation of the very rule it is enforcing.
# Whole-line comments come out first, exactly as run_interruption_contract_tests.sh
# and the theme contract do it.
code=$(mktemp); trap 'rm -rf "$out"; rm -f "$code"' EXIT
grep -v '^[[:space:]]*//' "$policy" > "$code"

# A STRIPPED FILE THAT CAME BACK EMPTY IS FOUR RULES THAT CANNOT FAIL. Every
# check below asks whether something is ABSENT from this text, and an empty text
# is absent of everything — which is how a renamed anchor turned a green gate
# into a gate about nothing twice in this tree already.
if [ ! -s "$code" ]; then
    echo "CallPresencePolicy.swift stripped of comments is empty."
    echo "Every rule below asks whether something is absent from that text, so"
    echo "an empty one passes all four while saying nothing about the code."
    exit 2
fi

# 1. LAW 1 — NO THRESHOLD MAY DECIDE WHAT A CALL WAS WORTH.
#    "A call longer than N minutes deserves a message" is a threshold deciding
#    meaning wearing a sense's clothes, and it is the single most likely way
#    this file stops being a sense. The boundary carries how long the call was
#    held; something with full context decides what that is worth. A stored
#    duration, or any comparison against one, is the shape that has to stay out.
if grep -qE '(let|var)[[:space:]]+[A-Za-z_]+[[:space:]]*:[[:space:]]*TimeInterval[[:space:]]*=' "$code" \
   || grep -qE '[A-Za-z_](Seconds|Minutes|Hours)[[:space:]]*[:=]' "$code" \
   || grep -E '(TimeInterval|Seconds|heldFor|timeIntervalSince)' "$code" | grep -qE '[<>]'; then
    echo "CallPresencePolicy has grown a duration threshold."
    echo ""
    echo "HARNESS-LAWS.md law 1: no threshold may decide what things MEAN, and"
    echo "'a call longer than N minutes is worth speaking about' is exactly that"
    echo "decision with a sense's alibi on it. This file reports how long a call"
    echo "was held and stops there; a model with full context decides the rest."
    exit 2
fi

# 2. LOCAL-FIRST RULE 3 — THE SENSE HAS NO IDENTITY AND MUST NOT INVENT ONE.
#    `CXCall` carries UUID, isOutgoing, isOnHold, hasConnected and hasEnded, and
#    that is the entire surface: no number, no name, no handle. The thinness is
#    the feature — a sense that has no identity cannot leak one — so a field
#    named for one is either dead weight or data that came from somewhere it
#    should not have.
if grep -qEi '(handle|phoneNumber|callerName|remoteParty|contactID)' "$code"; then
    echo "CallPresencePolicy names an identity for the person on the call."
    echo ""
    echo "CXCall does not carry one — no number, no name, no handle — so this"
    echo "field is either dead weight or a value that arrived from somewhere it"
    echo "should not have. design/LOCAL-FIRST.md rule 3: what travels is the"
    echo "smallest conclusion that works, and this sense gets that for free by"
    echo "having nothing else to give."
    exit 2
fi

# 3. NOTHING HERE MAY CLAIM FaceTime, OR CLAIM TELEPHONY.
#    The card this came from names FaceTime explicitly. Apple's CallKit
#    documentation does not mention FaceTime, and neither does any public header
#    in the iPhoneOS 26.2 SDK — `grep -ri facetime` over every framework header
#    in that SDK returns nothing at all. So there is no source saying FaceTime
#    calls appear in this stream and no source saying they do not, and only a
#    device settles it. Until one does, every name in this file says `call`,
#    meaning "whatever the telephony provider told us about", and a consumer
#    that renders "phone call" or "FaceTime" from it is putting a claim in the
#    owner's face that nobody has checked.
if grep -qEi 'facetime' "$code" || grep -qE 'phoneCall|PhoneCall' "$code"; then
    echo "CallPresencePolicy claims to know what KIND of call it is watching."
    echo ""
    echo "Nothing has established that. Apple's CallKit documentation never"
    echo "names FaceTime, and no public header in the iOS SDK mentions it"
    echo "anywhere, so whether FaceTime appears in this stream is unverified and"
    echo "only a device can settle it. Say 'call' and let a device promote it."
    exit 2
fi

# 4. IT STAYS PURE FOUNDATION, AND THAT IS LOAD-BEARING RATHER THAN TIDY.
#    The moment this file imports CallKit there is no macOS binary that can run
#    it, and every check below becomes a check nobody can execute without a
#    phone that has to receive a real call. The CallKit types belong in the
#    adapter that feeds this, not in the decision.
imports=$(grep -E '^[[:space:]]*(@testable[[:space:]]+)?import[[:space:]]' "$code" \
    | sed 's/^[[:space:]]*//' | sort -u)
if [ "$imports" != "import Foundation" ]; then
    echo "CallPresencePolicy imports something other than Foundation:"
    printf '  %s\n' "$imports"
    echo ""
    echo "There is then no macOS binary that can run these checks, and the one"
    echo "decision in this app about phone calls goes back to being a decision"
    echo "nothing can prove wrong without a device that receives a real call."
    exit 2
fi

# 5. NOBODY RE-IMPLEMENTS THE FOLD.
#    Deriving "a call started" from one `callChanged` at a time is how a missed
#    or coalesced callback becomes a state the sense never leaves. If a second
#    file starts reading `hasConnected` off a CXCall, there are two answers to
#    where a conversation begins and they will disagree on the day it matters.
#
#    AND THIS LEG REPORTS WHAT IT FOUND rather than passing by matching nothing.
#    The policy has no call site yet — the CallKit adapter that would feed it is
#    not built — and a rule about call sites that quietly passes over zero of
#    them is the same shape as a gate whose anchor was renamed.
sites=$(grep -rl 'CallPresencePolicy' "$app" 2>/dev/null | grep -v 'CallPresencePolicy.swift' || true)
if [ -n "$sites" ]; then
    for f in $sites; do
        if ! grep -q 'CallPresencePolicy\.decide(' "$f"; then
            echo "$f names CallPresencePolicy without asking it to decide."
            echo "A second answer to 'where does a conversation begin' is a second"
            echo "answer that will disagree with this one on the day it matters."
            exit 2
        fi
    done
fi
folders=$(grep -rl 'hasConnected' "$app" 2>/dev/null \
    | grep -v 'CallPresencePolicy.swift' || true)
if [ -n "$folders" ]; then
    echo "Something outside CallPresencePolicy is reading a call's hasConnected:"
    printf '  %s\n' $folders
    echo ""
    echo "CXCallObserverDelegate has one method and no start or end callback, so"
    echo "every transition has to be derived. Derive it in two places and the two"
    echo "will disagree about when a call began."
    exit 2
fi

swiftc -O \
    "$policy" \
    "$here/CallPresencePolicyTests.swift" \
    -o "$out/callpresencetests"
"$out/callpresencetests"

if [ -z "$sites" ]; then
    echo ""
    echo "NOTE: CallPresencePolicy has no call site. The CXCallObserver adapter"
    echo "that would feed it is not built, so nothing in the running app knows a"
    echo "call is happening yet. See research/2026-08-25-call-detection.md for"
    echo "what is owed and in what order."
fi
