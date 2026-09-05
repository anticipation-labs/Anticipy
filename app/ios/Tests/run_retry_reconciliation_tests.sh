#!/bin/sh
# After a crash, does the phone cite what was found, or a constant?
#
#   sh app/ios/Tests/run_retry_reconciliation_tests.sh
#
# Audit #90, correction (E). RetryReconciliationPolicy is pure Foundation, so
# the real production source is compiled straight in. No simulator, no scheme,
# no signing, no network. The wiring legs read AnticipyApp.swift and
# ContentView.swift comment-stripped, because the defect this closes was a
# literal in exactly those two places.
#
# Exit code is the result. Non-zero means a retry can once again be minted from
# a tap alone.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Backend/RetryReconciliationPolicy.swift"
[ -f "$policy" ] || { echo "missing $policy"; exit 2; }
session="$app/AnticipyApp.swift"
content="$app/Views/ContentView.swift"

code() { grep -vE '^[[:space:]]*//' "$1"; }

# ------------------------------------------------------------- the constants
# THE TWO LITERALS THAT SATISFIED THE GUARD. Either one back in the session
# file is the whole defect back: the guard's retry leg reads conclusion,
# evidence and owner_words, and these were all three of them.
for literal in 'owner explicitly checked the destination before retry' \
               'I checked the site; the action did not happen'; do
    if code "$session" | grep -q "$literal"; then
        echo "The phone is citing a constant again: \"$literal\""
        echo "That string is what backend/pb_hooks/workflow_guard.pb.js's retry"
        echo "leg accepts as proof it is safe to retry, and nothing checked"
        echo "anything. A crash plus a tap re-sends the submission."
        exit 2
    fi
done
if code "$session" | grep -q '"conclusion": "not_applied"'; then
    echo "approvalFields writes the conclusion as a literal again."
    echo "It has to be read off params._reconciliation — the verdict the"
    echo "extension recorded after looking at the page — or the guard is"
    echo "satisfied by a string the phone made up."
    exit 2
fi

# ---------------------------------------------------------------- the wiring
# The write goes through the policy's floor, and cites its evidence.
fields=$(awk '/private func approvalFields\(for job: AgentJob,/,/^    }$/' "$session" \
    | sed '/^[[:space:]]*\/\//d')
if [ -z "$fields" ]; then
    echo "This gate can no longer find approvalFields."
    echo "An empty block contains no constant and passes every rule above by"
    echo "containing nothing. If it was renamed, rename it here too."
    exit 2
fi
for needle in 'RetryReconciliationPolicy.read(params)' \
              'RetryReconciliationPolicy.mayRetry(' \
              'RetryReconciliationPolicy.retryEvidence(' \
              '"conclusion": row.verdict.rawValue'; do
    if ! printf '%s\n' "$fields" | tr '\n' ' ' | grep -q "$needle"; then
        echo "approvalFields no longer goes through the reconciliation floor: missing"
        echo "  $needle"
        exit 2
    fi
done
# ORDER: the floor is asked BEFORE the reconciliation is assembled, so an
# uncertain row that may not be retried throws rather than writes.
guardline=$(printf '%s\n' "$fields" | grep -n 'RetryReconciliationPolicy.mayRetry(' | head -1 | cut -d: -f1)
writeline=$(printf '%s\n' "$fields" | grep -n 'fields\["reconciliation"\] = ' | head -1 | cut -d: -f1)
if [ -z "$guardline" ] || [ -z "$writeline" ] || [ "$guardline" -gt "$writeline" ]; then
    echo "approvalFields assembles the reconciliation before asking whether"
    echo "the row may be retried at all."
    exit 2
fi

# And the card: the caption is the row's sentence, and the button obeys the
# same floor, so the owner is not offered a tap the write will refuse.
card=$(awk '/^struct ConfirmJobCard: View \{/,/^}$/' "$content" | sed '/^[[:space:]]*\/\//d')
if [ -z "$card" ]; then
    echo "This gate can no longer find ConfirmJobCard."
    exit 2
fi
for needle in 'RetryReconciliationPolicy.explanation(' \
              'RetryReconciliationPolicy.mayRetry(' \
              '!retryable'; do
    if ! printf '%s\n' "$card" | tr '\n' ' ' | grep -q -- "$needle"; then
        echo "ConfirmJobCard no longer reads the reconciliation row: missing"
        echo "  $needle"
        echo "The caption would go back to telling him to check, and the button"
        echo "would offer a retry the write refuses — or, worse, one it does not."
        exit 2
    fi
done
if printf '%s\n' "$card" | grep -q 'Only continue if the action did not happen'; then
    echo "The card is back to a standing instruction instead of what the row says."
    exit 2
fi
echo "the retry cites the row, and the card reads the same row"

# swiftc only permits top-level code in a file literally named main.swift, so
# the suite is copied under that name — the same reason run_battery_tests.sh
# does it.
cp "$here/RetryReconciliationPolicyTests.swift" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/retrytests"
"$out/retrytests"
