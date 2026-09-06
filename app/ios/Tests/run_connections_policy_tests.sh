#!/bin/sh
# CONNECTIONS — the pure policy the whole feature stands on.
#
#   sh app/ios/Tests/run_connections_policy_tests.sh
#
# The load-bearing question is whose account this is. During the week-1 spike
# one operator's own Gmail and Calendar were connected by hand under the
# `user_id` "omar" — a display name, which is one person's tokens serving
# everybody. It was revoked and deleted
# (research/2026-09-05-composio-connections.md, item 2). The contract's answer
# is that the user id is the owner ROW id, always, and never a name, and the
# Swift half of that rule is what the suite below spends its first section on.
#
# The legs in THIS file are the ones a Swift suite cannot ask:
#   * the policy is pure (no SwiftUI, no UIKit) so it runs on a laptop;
#   * no app is hardcoded, checked by reading the source rather than promised;
#   * the register list and the contract's closed sets are the SAME ones the
#     server uses, read out of the TypeScript at run time.
#
# That last group matters more than it looks. The app and the text thread are
# two skins on one record, and the twin claim is only true while both skins
# agree about what the states ARE. A member added to `NudgeState` on the server
# and not here does not fail to compile — it decodes as nil and the card
# silently disappears for whoever is in that state.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
repo=$(cd "$here/../../.." && pwd)
policy="$app/Backend/ConnectionsPolicy.swift"
suite="$here/ConnectionsPolicyTests.swift"
contract="$repo/spike/two-hands/src/connections/contract.ts"
words="$repo/spike/two-hands/src/connections/words.ts"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

[ -f "$policy" ] || { echo "missing $policy"; exit 2; }
[ -f "$suite" ] || { echo "missing $suite"; exit 2; }

# The contract is not optional reading. If it moved, this file has to be
# re-pointed at it in the same diff — a skipped leg is a leg somebody learns to
# skip by moving a file.
for f in "$contract" "$words"; do
    [ -f "$f" ] || {
        echo "missing $f"
        echo ""
        echo "This suite reads the SERVER's contract at run time so the app and"
        echo "the text thread cannot drift about what a nudge state is or which"
        echo "words the product may not say. If the contract moved, re-point"
        echo "this runner at it in the same diff rather than deleting the leg."
        exit 2
    }
done

# Comments stripped once, up front. Every source leg below reads `body`, because
# a leg that greps the whole file is a leg a comment can turn green — the
# failure stranger_gate.py's own header records five times over.
body=$(sed 's|//.*||' "$policy")

# ------------------------------------------------------- the policy stays pure
# The point of a policy layer is that "what will this show, and what will it let
# us do" is answerable with no phone, no server and no account. A SwiftUI import
# here means the decision has been folded back into the thing it exists to be
# testable without.
if printf '%s\n' "$body" | grep -qE '^[[:space:]]*import[[:space:]]+(SwiftUI|UIKit)'; then
    echo "ConnectionsPolicy imports SwiftUI or UIKit."
    echo "This decides who owns a connection and whether we may change anything"
    echo "inside somebody's account. It has to be answerable on a laptop."
    exit 2
fi

# ------------------------------------------------------------- LAW 1: no regex
# Nothing in this policy reads a human's words. WHICH APP a person meant is a
# meaning question and belongs to a model against the catalog (`ToolkitJudge`);
# a pattern here would be that question answered by a word list.
if printf '%s\n' "$body" | grep -qE 'NSRegularExpression|options:[[:space:]]*\.regularExpression'; then
    echo "ConnectionsPolicy matches a pattern against text."
    echo "HARNESS-LAWS law 1: no regex may decide what a human's words mean."
    echo "Which app somebody meant — \"my Outlook\", \"office mail\", \"my work"
    echo "email\" — is a model's question, asked against the catalog."
    exit 2
fi

# ------------------------------------------------------ NO APP IS HARDCODED
# The product claim is that a new app in the catalog is a new app in Anticipy
# with zero code. Names, logos and permission words come from `ToolkitMeta` at
# run time. A slug in executable code is the claim being false, and it is false
# quietly: everything keeps working for the apps somebody thought of.
#
# This list is a GATE, which is where HARNESS-LAWS law 1 permits a word list —
# it measures the source, it never reads a person.
names='gmail|googlecalendar|google_calendar|notion|slack|outlook|dropbox|github|linear|asana|salesforce|hubspot|jira|trello|zoom'
if printf '%s\n' "$body" | grep -qiE "(^|[^a-z0-9])($names)([^a-z0-9]|$)"; then
    echo "ConnectionsPolicy names an app in executable code:"
    printf '%s\n' "$body" | grep -inE "(^|[^a-z0-9])($names)([^a-z0-9]|$)" | head -5
    echo ""
    echo "NO APP IS HARDCODED. Names, logos and permission words come from the"
    echo "catalog at run time, so a new app in the catalog is a new app in"
    echo "Anticipy with zero code. A slug here makes that claim false for every"
    echo "app nobody thought of, and it fails quietly — the ones on the list"
    echo "keep working."
    exit 2
fi
if printf '%s\n' "$body" | grep -qE 'switch[[:space:]]+[a-zA-Z_.]*[Tt]oolkit|switch[[:space:]]+[a-zA-Z_.]*slug'; then
    echo "ConnectionsPolicy switches on a toolkit slug."
    echo "That is a per-app table with better manners. The only thing that may"
    echo "vary per app is what the catalog said about it."
    exit 2
fi

# --------------------------------------------- the register is ONE list, shared
# The app's copy is bound by the same rules as the SMS copy. Two lists is two
# rules, and the day they differ is the day a sentence the server would refuse
# ships on a card.
list_from() {
    # $1 file, $2 the line that opens the array literal. Comments stripped
    # first, then every double-quoted string up to the closing bracket.
    sed 's|//.*||' "$1" \
        | awk -v open="$2" '
            !on && $0 ~ open { on = 1 }
            on {
                s = $0
                while (match(s, /"[^"]*"/)) {
                    t = substr(s, RSTART + 1, RLENGTH - 2)
                    if (t != "") print t
                    s = substr(s, RSTART + RLENGTH)
                }
                if (index($0, "]") > 0 && on > 1) exit
                on = 2
            }
        ' | sort | tr '\n' ' '
}
swift_terms=$(list_from "$policy" 'static let forbiddenTerms:')
server_terms=$(list_from "$words" 'export const FORBIDDEN_TERMS')
if [ -z "$server_terms" ]; then
    echo "Could not read FORBIDDEN_TERMS out of $words."
    echo "Re-point this leg rather than removing it: it is the only thing"
    echo "keeping the app's register and the SMS register the same register."
    exit 2
fi
if [ "$swift_terms" != "$server_terms" ]; then
    echo "The app's forbidden register and the server's have drifted."
    echo "  ConnectionsPolicy : $swift_terms"
    echo "  words.ts          : $server_terms"
    echo ""
    echo "The person never hears the vendor's name and never hears the"
    echo "vocabulary of a consent screen. One rule, one list — a term the"
    echo "server refuses and the app allows ships on a card."
    exit 2
fi

# ------------------------------- the closed sets are the CONTRACT's closed sets
# The census in ConnectionsPolicyTests.swift is what the Swift enums are checked
# against; this compares that census with contract.ts. Swift enums with raw
# values cannot be enumerated from a shell script, so the two lists meet here.
#
# A state added on the server and not here does not fail to compile. It decodes
# as nil, and the card silently vanishes for whoever is in that state.
# BLOCK COMMENTS ARE STRIPPED TOO, and that is not tidiness. Both readers below
# lift every double-quoted string out of a declaration, and a JSDoc block sitting
# inside one is full of prose — contract.ts's own note on `declined_soft` quotes
# the spec twice, and on 2026-09-06 this leg reported the union as
# `never_asked asked " Page 25: " " not a real decline" declined_soft …`,
# failing over an English sentence rather than over a state. `sed 's|//.*||'`
# alone only ever handled the line-comment half; the second expression deletes
# any line whose first non-space character opens or continues a block comment,
# which is every line of a JSDoc and cannot be a line of a union.
strip_comments() {
    sed -e 's|//.*||' -e '/^[[:space:]]*[*\/]/d' "$1"
}
union_from() {
    # Every double-quoted string between the declaration and its ';'.
    strip_comments "$1" \
        | awk -v open="$2" '
            !on && $0 ~ open { on = 1 }
            on {
                s = $0
                while (match(s, /"[^"]*"/)) {
                    print substr(s, RSTART + 1, RLENGTH - 2)
                    s = substr(s, RSTART + RLENGTH)
                }
                if (index($0, ";") > 0) exit
            }
        ' | tr '\n' ' '
}
census_from() {
    # The `let NAME = [...]` literal in the suite, in declaration order.
    strip_comments "$suite" \
        | awk -v open="^let $1 " '
            !on && $0 ~ open { on = 1 }
            on {
                s = $0
                while (match(s, /"[^"]*"/)) {
                    print substr(s, RSTART + 1, RLENGTH - 2)
                    s = substr(s, RSTART + RLENGTH)
                }
                if (index($0, "]") > 0) exit
            }
        ' | tr '\n' ' '
}

compare() {
    if [ "$2" != "$3" ]; then
        echo "$1 disagrees with the server contract."
        echo "  contract.ts                   : ${2:-nothing this leg could read}"
        echo "  ConnectionsPolicyTests.swift  : ${3:-nothing this leg could read}"
        echo ""
        echo "The app and the text thread are two skins on ONE record. A member"
        echo "that exists on one side and not the other does not fail to"
        echo "compile — it decodes as nil and the surface silently disappears"
        echo "for whoever is in that state."
        exit 2
    fi
}

compare "NudgeState" \
    "$(union_from "$contract" '^export type NudgeState =')" \
    "$(census_from CONTRACT_NUDGE_STATES)"
compare "AccountAlias" \
    "$(union_from "$contract" '^export type AccountAlias =')" \
    "$(census_from CONTRACT_ALIASES)"
compare "NudgeTrigger" \
    "$(union_from "$contract" '^export type NudgeTrigger =')" \
    "$(census_from CONTRACT_TRIGGERS)"
compare "Connection.status" \
    "$(union_from "$contract" 'status:[[:space:]]*"connected"')" \
    "$(census_from CONTRACT_STATUSES)"

# The snooze ladder, and the owner-id shape. Both are numbers this file would
# otherwise be free to retype wrong.
server_snooze=$(sed 's|//.*||' "$contract" \
    | sed -n 's/.*SNOOZE_DAYS[^=]*=[[:space:]]*{\([^}]*\)}.*/\1/p' \
    | tr -d ' ' | tr ',' '\n' | sed 's/^[0-9]*://' | grep -v '^$' | tr '\n' ' ')
suite_snooze=$(sed 's|//.*||' "$suite" \
    | sed -n 's/^let CONTRACT_SNOOZE_DAYS[^=]*=[[:space:]]*\[\([^]]*\)\].*/\1/p' \
    | tr -d ' ' | tr ',' '\n' | grep -v '^$' | tr '\n' ' ')
if [ "$server_snooze" != "$suite_snooze" ]; then
    echo "The snooze ladder disagrees with the contract."
    echo "  contract.ts : ${server_snooze:-unreadable}"
    echo "  the suite   : ${suite_snooze:-unreadable}"
    echo ""
    echo "Two implementations of \"how long is the snooze\" is how an owner gets"
    echo "re-asked on day 14 by one path while the other believes it is day 45."
    exit 2
fi

server_idlen=$(sed 's|//.*||' "$contract" \
    | sed -n 's|.*\[a-z0-9\]{\([0-9]*\)}\$/.*|\1|p' | head -1)
suite_idlen=$(sed 's|//.*||' "$suite" \
    | sed -n 's/^let CONTRACT_OWNER_ID_LENGTH[^=]*=[[:space:]]*\([0-9]*\).*/\1/p' | head -1)
if [ -z "$server_idlen" ] || [ "$server_idlen" != "$suite_idlen" ]; then
    echo "The owner-id shape disagrees with the contract."
    echo "  contract.ts : ${server_idlen:-unreadable}"
    echo "  the suite   : ${suite_idlen:-unreadable}"
    echo ""
    echo "\`ownerId()\` next door refuses anything that is not 15 lowercase"
    echo "alphanumerics, because a name or an email reaching there means a"
    echo "caller confused \"who is this\" with \"what do we call them\" — and the"
    echo "connection would bind to the wrong person. It already did once."
    exit 2
fi

# -------------------------------------- the owner filter is actually a filter
# `OwnerScoped.rows` is the whole rule. If it ever stopped filtering, every
# behavioural leg in the suite that passes a mixed list would still pass on a
# clean one — and the clean lists are what a hurried reader writes.
if ! printf '%s\n' "$body" | tr '\n' ' ' | grep -q 'static func rows<Row: OwnerStamped>'; then
    echo "OwnerScoped.rows is gone."
    echo "It is the executable form of the contract's OwnerId rule: a function"
    echo "that takes a list of rows FILTERS it rather than trusting the caller."
    exit 2
fi
# EVERY DOOR THAT READS ROWS TAKES THE SIGNED-IN OWNER. Flattened first,
# because these signatures wrap and a leg that goes red on somebody's line
# break is a leg people learn to edit. A door that lost its `for owner:` would
# still compile and every clean-list test in the suite would still pass — and a
# clean list is what a hurried reader writes.
flat=$(printf '%s\n' "$body" | tr '\n' ' ')
for door in settingsCards mayUse writesEnabled writesTransition connectedRows; do
    printf '%s' "$flat" | grep -q "func $door(" || continue
    if ! printf '%s' "$flat" | grep -qE "func $door\([^)]*for owner: OwnerId"; then
        echo "$door no longer takes an OwnerId."
        echo "Every door into this policy that reads rows takes the signed-in"
        echo "owner and filters. A screen built from an unscoped list is the"
        echo "spike's failure with a nicer layout."
        exit 2
    fi
done
for door in nudgeRender recordDecline recordTapped nudgeAfter; do
    printf '%s' "$flat" | grep -q "func $door(" || continue
    if ! printf '%s' "$flat" | grep -qE "func $door\([^)]*(for owner: OwnerId|NudgeCardInput)"; then
        echo "$door no longer knows whose nudge it is holding."
        echo "A nudge is read and written for ONE owner. Rendering or"
        echo "transitioning one without saying which owner is asking is how"
        echo "this phone shows its user what somebody else was asked about."
        exit 2
    fi
done

echo "the policy is pure, hardcodes no app, and shares the server's register and closed sets"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$suite" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/connectionspolicytests"
"$out/connectionspolicytests"
