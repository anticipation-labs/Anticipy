#!/bin/sh
# THE PHONE AS A HAND — calendar write and undo, decided before any device.
#
#   sh app/ios/Tests/run_calendar_hand_tests.sh
#
# research/2026-08-26-hands2-better-answer.md §4 rung 0. The app already holds
# full calendar access and already polls the job channel; what this adds is a
# DECISION, and the decision is what has to be legal.
#
# The binding constraint is docs/superpowers/specs/2026-08-24-shelf-2-redesign.md
# §4: "An act is admissible only when undoing it requires nothing the act
# produced." EKEvent.eventIdentifier is assigned BY EVENTKIT ON SAVE, so an undo
# that looks it up is the exact shape §6.1 excludes by name. The suite pins the
# alternative — an id WE mint, resolvable before the act, stamped onto the
# event, and searched for afterwards.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
policy="$app/Backend/CalendarHandPolicy.swift"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

[ -f "$policy" ] || { echo "missing $policy"; exit 2; }

# --------------------------------------------------- the policy stays pure
# The whole point of a policy layer is that "what will the hand do" is
# answerable with no device, no calendar and no store. An EventKit import here
# means the decision has been folded back into the thing it exists to be
# testable without.
if grep -qE '^[[:space:]]*import[[:space:]]+EventKit' "$policy"; then
    echo "CalendarHandPolicy imports EventKit."
    echo "The decision is supposed to sit IN FRONT of the store, so it can be"
    echo "run on a laptop. A policy that needs a calendar to answer is a policy"
    echo "nobody can test at the instant that matters."
    exit 2
fi

# ---------------------------------------------- the promise about the notes
# NSCalendarsFullAccessUsageDescription, which the owner has already read at an
# iOS prompt: "She never reads the notes or the invitees." An undo that searches
# the notes field reads the notes of every event in its window. The id rides on
# `url` for that reason, and this leg is what keeps it there.
if grep -vE '^[[:space:]]*(//|///)' "$policy" | grep -qi 'notes'; then
    echo "CalendarHandPolicy names the notes field in executable code."
    echo "The shipped permission string promises 'She never reads the notes or"
    echo "the invitees'. An undo that searches notes reads the notes of every"
    echo "event in its window and breaks a promise the owner already read."
    exit 2
fi
plist="$app/Info.plist"
if [ -f "$plist" ] && ! grep -q 'never reads the notes' "$plist"; then
    echo "The permission string no longer promises the notes are unread."
    echo "That promise is why the minted id rides on \`url\`. If the promise"
    echo "changed, the decision above has to be re-argued, not silently kept."
    exit 2
fi

# ----------------------------------------------------- LAW 1: no prose dates
# "Thursday 7pm" is the MODEL's to resolve, and it arrives already resolved on
# the plan. A weekday word or a regex in here would be a pattern deciding what
# a human's words meant — the violation the audit counted 61 times.
body=$(grep -vE '^[[:space:]]*(//|///)' "$policy")
if printf '%s' "$body" | grep -qiE '(mon|tues|wednes|thurs|fri|satur|sun)day|tomorrow|tonight|next week'; then
    echo "CalendarHandPolicy contains weekday or relative-day words in code."
    echo "HARNESS-LAWS Law 1: no word list may decide what a human's words"
    echo "mean. The plan's facts already carry the instant the model resolved."
    exit 2
fi
if printf '%s' "$body" | grep -qE 'NSRegularExpression|options:[[:space:]]*\.regularExpression'; then
    echo "CalendarHandPolicy matches a pattern against text."
    echo "The only text it reads is an ISO instant and a title it copies"
    echo "verbatim. A regex here is meaning being decided by a pattern."
    exit 2
fi

# ------------------------------------------- the shelf is shut, in the source
# brain/workflow.py ADMITTED_ACT_TYPES has one member and it is not this one.
# §10.1's six conditions are unmet for a calendar write — condition 6 in
# particular, which §10.4 says fires for "the first act type whose effect leaves
# our store": extension/agent_loop.js terminalReceiptEvidence is unrepaired.
#
# So the device admits NOTHING for act-and-tell, and that is a constant a reader
# can check in one diff rather than a value a row can carry.
if ! printf '%s' "$body" \
    | tr '\n' ' ' \
    | grep -qE 'admittedForActAndTell:[[:space:]]*Set<String>[[:space:]]*=[[:space:]]*\[\]'; then
    echo "The device's act-and-tell admitted set is no longer empty."
    echo ""
    echo "Widening it needs ALL SIX of spec §10.1 — ten live undos across ten"
    echo "distinct days, a silent-failure probe, a durable announcement, and"
    echo "condition 6: §2.1's receipt defect repaired FIRST, because a calendar"
    echo "write is the first act type whose effect leaves our store (§10.4)."
    echo "extension/agent_loop.js terminalReceiptEvidence is still unrepaired."
    exit 2
fi

# ----------------------------------------- the undo never reads a name or step
# §5.2: "The checker resolves every reference and refuses on any that does not
# resolve. It never inspects a field name and never parses prose." A checker
# that read `name` would be a word list wearing a different coat, defeated by a
# model that calls a field `owner_supplied_reference` and fills it from the
# counterparty's response — which is a case in the suite below.
if printf '%s' "$body" | grep -qE '\["name"\]'; then
    echo "CalendarHandPolicy reads an undo input's \`name\`."
    echo "Spec §5.2: the checker resolves references and never inspects a field"
    echo "name. A name check is defeated by a model that calls its field"
    echo "owner_supplied_reference and fills it from the response."
    exit 2
fi
if printf '%s' "$body" | grep -qE 'undo\["steps"\][^!]*\bas\?[[:space:]]*\[String\]'; then
    echo "CalendarHandPolicy decodes the undo's steps as text."
    echo "The steps are model-authored prose stored so a human can read them"
    echo "and a test can replay them. They are never parsed for meaning; the"
    echo "only question asked of them is whether there are any."
    exit 2
fi

echo "the policy is pure, prose-free, and the shelf is shut in the source"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/CalendarHandPolicyTests.swift" "$out/main.swift"
swiftc -O "$policy" "$out/main.swift" -o "$out/calendarhandtests"
"$out/calendarhandtests"
