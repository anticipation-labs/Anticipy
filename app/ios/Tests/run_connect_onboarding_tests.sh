#!/bin/sh
# ONBOARDING STEP 2 — "Which apps do you live in?" — and the text/app lockstep.
#
#   sh app/ios/Tests/run_connect_onboarding_tests.sh
#
# Spec: "Connections: how Anticipy asks, learns, and never says Composio",
# 2026-09-05, page 25. ConnectOnboardingPolicy is pure Foundation, so the real
# production source is compiled straight in — no simulator, no scheme, no
# signing, no network.
#
# Five legs live in this file rather than in the suite, because each of them is
# a claim about the SOURCE that no amount of passing behaviour can make true:
#
#   1. PURITY        the decision answers with no SwiftUI, no UIKit and no
#                    device, or it is not a decision anybody can test
#   2. NO APP IS     not a domain, not a vendor name, in code OR in a comment —
#      HARDCODED     a name in a comment is where the next agent's branch on
#                    that name starts (the rule src/connections/signals.ts keeps)
#   3. THE REGISTER  no string this file can show a person contains the vendor's
#                    name, "authorize", "grant access", "permissions",
#                    "integration", "API" or "OAuth"
#   4. THE CONTRACT  every constant, every enum member and the owner-id shape are
#                    read back out of spike/two-hands/src/connections/*.ts and
#                    compared. Two implementations of "how long is the snooze"
#                    is how an owner gets re-asked on day 7 by one half of the
#                    product while the other believes it is day 14.
#   5. THE SUITE     ConnectOnboardingTests.swift, compiled against the real
#                    source and run. Exit code is the result.
#
# Non-zero means a case came back wrong, or the phone has drifted from the
# server contract it renders.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
root=$(cd "$here/../../.." && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Backend/ConnectOnboardingPolicy.swift"
suite="$here/ConnectOnboardingTests.swift"
contract="$root/spike/two-hands/src/connections/contract.ts"
signals="$root/spike/two-hands/src/connections/signals.ts"
nudgepolicy="$root/spike/two-hands/src/connections/policy.ts"

[ -f "$policy" ] || { echo "missing $policy"; exit 2; }
[ -f "$suite" ] || { echo "missing $suite"; exit 2; }

# Comment-stripped source, for the legs that are about executable code.
code() { grep -vE '^[[:space:]]*(//|///)' "$1"; }

# ------------------------------------------------------------------ 1. PURITY
# The whole point of a policy layer is that "which apps arrive pre-selected, and
# what does Skip do" is answerable with no phone, no network and no screen. A
# SwiftUI import here means the decision has been folded back into the thing it
# exists to be testable without.
if grep -qE '^[[:space:]]*import[[:space:]]+(SwiftUI|UIKit)' "$policy"; then
    echo "ConnectOnboardingPolicy imports a UI framework."
    echo "The decision has to sit IN FRONT of the screen so it can be run on a"
    echo "laptop. A policy that needs a view to answer is a policy nobody can"
    echo "run at the instant that matters."
    exit 2
fi
imports=$(grep -E '^[[:space:]]*import ' "$policy" | tr -d ' ' | sort -u | tr '\n' ' ')
if [ "$imports" != "importFoundation " ]; then
    echo "ConnectOnboardingPolicy imports more than Foundation: $imports"
    exit 2
fi

# --------------------------------------------------- 2. NO APP IS HARDCODED
# The spec's promise is that a new app in the catalog is a new app in Anticipy
# with zero code. The promise is only true if this file cannot NAME an app. Both
# checks run over the whole source — comments included — and over the suite,
# which invents its own catalog for the same reason.
for f in "$policy" "$suite"; do
    if grep -nEi '\b[a-z0-9][a-z0-9-]*\.(com|net|org|io|co|ai|dev|app|me|edu|gov|us|uk|xyz|so|sh)\b' "$f"; then
        echo ""
        echo "A domain literal appears in $(basename "$f")."
        echo "Which apps a person lives in is decided from injected signal rows"
        echo "and catalog metadata. A domain in the source is the hardcoding the"
        echo "spec forbids, and the day the catalog gains an app this file has"
        echo "never heard of, the table is silently wrong about them."
        exit 2
    fi
    if grep -nEi '\b(gmail|googlecalendar|google|notion|slack|outlook|microsoft|dropbox|github|asana|jira|trello|hubspot|salesforce|zoom|linkedin|airtable|shopify)\b' "$f"; then
        echo ""
        echo "A vendor or app name appears in $(basename "$f")."
        echo "Names, logos and permission words come from the catalog at run"
        echo "time. A name in a COMMENT is where the next agent's branch on that"
        echo "name starts — which is why signals.ts bans it in prose too."
        exit 2
    fi
done

# The provider's name may appear ONCE more in this repo than in the product: in
# a citation of the spec whose own title contains it. It may never appear in the
# policy's executable code — a branch on the vendor is a branch on a seam the
# user is not supposed to know exists. (The suite is exempt: it has to be able
# to NAME the words it forbids, which is leg 3's whole point.)
if code "$policy" | grep -qi 'composio'; then
    echo ""
    echo "The provider's name appears in ConnectOnboardingPolicy's code."
    echo "The user never hears it and the code never names it: what an app is"
    echo "called, and who hosts the connection, both come from the catalog at"
    echo "run time."
    exit 2
fi

# ------------------------------------------------------------- 3. THE REGISTER
# The owner never hears the vendor, and never hears the words the spec strikes
# out. This reads every string literal the executable code can produce.
literals=$(code "$policy" | grep -oE '"[^"]*"' || true)
# The vendor words the spec strikes out, AND the app names — as substrings this
# time, with no word boundary, because a boundary is exactly what an identifier
# like `my_vendor_token` hides behind.
for word in composio oauth authoriz 'grant access' integration permission \
            gmail google notion slack outlook microsoft dropbox github; do
    if printf '%s\n' "$literals" | grep -qi -- "$word"; then
        echo "A string in ConnectOnboardingPolicy contains \"$word\"."
        echo "The spec's register is fixed: it is \"connect your <name the"
        echo "catalog gave us>\", never a vendor, a permission or an API."
        printf '%s\n' "$literals" | grep -i -- "$word"
        exit 2
    fi
done
if printf '%s\n' "$literals" | grep -qiE '\bapi\b'; then
    echo "A string in ConnectOnboardingPolicy says \"API\"."
    exit 2
fi
# Skip is always visible, so it is a non-optional field of the card. A card that
# can hide it is a card that will.
if ! code "$policy" | tr '\n' ' ' | grep -qE 'let skipLabel: String'; then
    echo "The step's skip label is no longer a plain, non-optional field."
    echo "Page 25: Skip is ALWAYS VISIBLE and never buried. An optional or a"
    echo "computed label is one condition away from a card with no way out."
    exit 2
fi

# ------------------------------------------------------------ 4. THE CONTRACT
# contract.ts is the fixed, committed contract. These legs are hard.
[ -f "$contract" ] || { echo "missing $contract — the contract this phone renders"; exit 2; }

fail_drift() {
    echo ""
    echo "The phone has drifted from the server contract."
    echo "  $1"
    echo "  contract.ts says : $2"
    echo "  the Swift says   : $3"
    echo ""
    echo "These are one product. Two spellings of the same constant is how an"
    echo "owner gets re-asked on day 7 by one half of it while the other half"
    echo "believes it is day 14."
    exit 2
}

ts_const() {
    grep -E "^export const $1 = " "$contract" | head -1 \
        | sed -E "s/^export const $1 = //; s/;.*$//" | tr -d ' '
}
swift_const() {
    grep -E "^[[:space:]]*static let $1[ :=]" "$policy" | head -1 \
        | sed -E 's/^[^=]*=[[:space:]]*//' | tr -d ' '
}

set -- "ONBOARDING_SKIP_SNOOZE_DAYS onboardingSkipSnoozeDays" \
       "GLOBAL_ASK_INTERVAL_DAYS globalAskIntervalDays" \
       "SILENCE_IS_A_SOFT_NO_HOURS silenceIsASoftNoHours" \
       "LINK_TTL_MS linkTTLMilliseconds"
for pair in "$@"; do
    tsname=${pair%% *}
    swname=${pair##* }
    tsval=$(ts_const "$tsname")
    swval=$(swift_const "$swname")
    [ -n "$tsval" ] || { echo "cannot read $tsname out of contract.ts"; exit 2; }
    [ -n "$swval" ] || { echo "cannot read $swname out of the policy"; exit 2; }
    [ "$tsval" = "$swval" ] || fail_drift "$tsname vs $swname" "$tsval" "$swval"
done

# The owner-id shape. A name or an email binding a connection is THE failure
# this whole feature is shaped around (research/2026-09-05-composio-connections.md
# item 2), and the phone must refuse exactly what the server refuses.
ts_owner=$(grep -oE '\^\[a-z0-9\]\{[0-9]+\}\$' "$contract" | head -1)
sw_owner=$(grep -E 'ownerIdPattern = ' "$policy" | head -1 | sed -E 's/.*= "//; s/".*//')
[ -n "$ts_owner" ] || { echo "cannot read the owner-id shape out of contract.ts"; exit 2; }
[ "$ts_owner" = "$sw_owner" ] || fail_drift "the owner id's shape" "$ts_owner" "$sw_owner"

# The closed enums, member by member. A state, a trigger or a source the server
# writes and the phone cannot read is a card that silently shows nothing.
ts_union() { sed -n "/^export type $1 =/,/;/p" "$contract" | grep -oE '"[a-z_]+"' | tr -d '"' | sort | tr '\n' ' '; }
ts_inline() { grep -E "^  $1: " "$contract" | head -1 | grep -oE '"[a-z_]+"' | tr -d '"' | sort | tr '\n' ' '; }
swift_cases() {
    sed -n "/enum $1: String/,/^    }/p" "$policy" \
        | grep -oE 'case [a-zA-Z]+ = "[a-z_]+"' | sed -E 's/.*= "//; s/"//' | sort | tr '\n' ' '
}

for pair in "NudgeState NudgeState" "NudgeTrigger Trigger"; do
    tsname=${pair%% *}
    swname=${pair##* }
    tsval=$(ts_union "$tsname")
    swval=$(swift_cases "$swname")
    [ -n "$tsval" ] || { echo "cannot read the $tsname union out of contract.ts"; exit 2; }
    [ "$tsval" = "$swval" ] || fail_drift "$tsname's members" "$tsval" "$swval"
done

ts_alias=$(grep -E '^export type AccountAlias = ' "$contract" | grep -oE '"[a-z]+"' | tr -d '"' | sort | tr '\n' ' ')
[ "$ts_alias" = "$(swift_cases AccountAlias)" ] \
    || fail_drift "AccountAlias's members" "$ts_alias" "$(swift_cases AccountAlias)"

ts_source=$(ts_inline source)
[ "$ts_source" = "$(swift_cases SignalSource)" ] \
    || fail_drift "AppUsageSignal.source's members" "$ts_source" "$(swift_cases SignalSource)"

ts_channel=$(ts_inline channel)
[ "$ts_channel" = "$(swift_cases Channel)" ] \
    || fail_drift "ConnectNudge.channel's members" "$ts_channel" "$(swift_cases Channel)"

echo "the phone agrees with contract.ts: 4 constants, 5 enums, and the owner-id shape"

# signals.ts is this week's work and may not be on a given checkout. Its legs
# are hard WHEN IT IS THERE and loud when it is not — a silent skip would teach
# the next reader that the weights agree when nobody looked.
if [ -f "$signals" ]; then
    ts_weights=$(sed -n '/export const SOURCE_WEIGHT/,/});/p' "$signals" \
        | grep -oE '^  [a-z]+: [0-9.]+' | tr -d ' ' | sort | tr '\n' ' ')
    sw_weights=$(sed -n '/static let sourceWeight/,/^        \]/p' "$policy" \
        | grep -oE '\.[a-z]+: [0-9.]+' | sed -E 's/^\.//' | tr -d ' ' | sort | tr '\n' ' ')
    [ -n "$ts_weights" ] || { echo "cannot read SOURCE_WEIGHT out of signals.ts"; exit 2; }
    [ "$ts_weights" = "$sw_weights" ] || fail_drift "SOURCE_WEIGHT" "$ts_weights" "$sw_weights"

    ts_decays=$(sed -n '/export const SOURCE_DECAYS/,/});/p' "$signals" \
        | grep -oE '^  [a-z]+: (true|false)' | tr -d ' ' | sort | tr '\n' ' ')
    sw_decays=$(sed -n '/static let sourceDecays/,/^        \]/p' "$policy" \
        | grep -oE '\.[a-z]+: (true|false)' | sed -E 's/^\.//' | tr -d ' ' | sort | tr '\n' ' ')
    [ "$ts_decays" = "$sw_decays" ] || fail_drift "SOURCE_DECAYS" "$ts_decays" "$sw_decays"

    ts_half=$(grep -E '^export const DEFAULT_HALF_LIFE_MS = ' "$signals" | head -1 \
        | sed -E 's/^export const DEFAULT_HALF_LIFE_MS = //; s/;.*$//' | tr -d ' ')
    sw_half=$(swift_const defaultHalfLifeMilliseconds)
    [ "$ts_half" = "$sw_half" ] || fail_drift "DEFAULT_HALF_LIFE_MS" "$ts_half" "$sw_half"
    echo "the phone agrees with signals.ts: both weight tables and the half-life"
else
    echo "NOTE: $signals is absent, so the ranking weights are UNPROVEN against"
    echo "      the server's own table. They are pinned as values in the suite."
fi

# A STANDING DISAGREEMENT, PRINTED RATHER THAN HIDDEN. `recordDecline` in
# policy.ts treats an onboarding skip as decline LEVEL 1 with a seven-day
# snooze; this policy treats it as a seven-day snooze with the level UNCHANGED,
# because level 1 raises the server's own threshold from 0.5 to 0.8 and
# strictly-above then silences repeated_use (0.6), onboarding (0.7) and in_task
# (0.8) — a shrug at the setup card would end the conversation for good. One of
# the two has to move. Until it does, a reader deserves to see it every run.
if [ -f "$nudgepolicy" ] && grep -q 'ONBOARDING_SKIP_SNOOZE_DAYS' "$nudgepolicy"; then
    if sed -n '/export function recordDecline/,/^}/p' "$nudgepolicy" | grep -q 'nudge.level + 1'; then
        echo "NOTE: policy.ts recordDecline() advances the decline level on an"
        echo "      onboarding skip; this policy does not. See the comment on"
        echo "      skipOutcome() — the divergence is deliberate and owed a"
        echo "      decision on the server side."
    fi
fi

# --------------------------------------------------------------- 5. THE SUITE
# swiftc only permits top-level code in a file literally named main.swift, so
# the suite is copied under that name — the same reason run_battery_tests.sh
# does it.
cp "$suite" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/connectonboardingtests"
"$out/connectonboardingtests"
