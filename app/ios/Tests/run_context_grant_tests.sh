#!/bin/sh
# Day-zero consent: the gate starts shut, one source at a time, skips are not
# permanent, and reads are bounded.
#
#   sh app/ios/Tests/run_context_grant_tests.sh
#
# ContextGrant and LifeContext are compiled straight in rather than copied, so
# the assertions are about the production source and cannot drift from it.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

grant="$app/ContextGrant.swift"
life="$app/LifeContext.swift"
for f in "$grant" "$life"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

# The logic checks below are worthless if nothing consults the gate. Prove the
# wiring first — this is the exact failure `events.source` already suffered
# once: written for weeks, read by nothing, and no test noticed because nothing
# asserted the read.
session="$app/AnticipyApp.swift"
if ! grep -q 'ContextGrants().grant(source)' "$session"; then
    echo "grantContext no longer records the grant, so the gate is decorative."
    exit 2
fi
if ! grep -q 'guard ContextGrants().granted(source) else { return }' "$session"; then
    echo "sendContextFacts no longer checks the gate before reading."
    echo "That is the whole safety property: no grant, no read."
    exit 2
fi
# The OS must be asked only AFTER our own screen has explained itself, and the
# grant must be recorded only after the OS agrees.
if ! grep -q 'guard osOK else { return false }' "$session"; then
    echo "grantContext records a grant even when iOS refused."
    exit 2
fi
# Facts must not travel as transcripts, or an imported diary entry gets triaged
# into an errand and she tries to book the dinner that is already booked.
if ! grep -q 'pushEvent(kind: "profile"' "$session"; then
    echo "Context facts are no longer posted as kind:profile."
    exit 2
fi
if grep -q 'pushEvent(kind: "transcript", text: fact' "$session"; then
    echo "Context facts are being posted as transcripts. They will be triaged."
    exit 2
fi
# And the server half has to actually consume that kind.
worker="$here/../../../brain/worker.py"
if [ -f "$worker" ]; then
    if ! grep -q 'fetch_unprocessed(kind="profile"' "$worker"; then
        echo "brain/worker.py no longer polls for profile events, so facts never land."
        exit 2
    fi
    if ! grep -q 'source="import"' "$worker"; then
        echo "Imported facts lost their provenance."
        exit 2
    fi
fi
echo "the gate is consulted, the OS is asked second, and facts land as profile events"

# Usage descriptions: a missing calendar key is a CRASH on the iOS 16 floor,
# not a denial, so both spellings must be present.
spec="$here/../project.yml"
for key in NSCalendarsFullAccessUsageDescription NSCalendarsUsageDescription NSContactsUsageDescription; do
    grep -q "$key" "$spec" || { echo "project.yml is missing $key"; exit 2; }
done
echo "both calendar usage keys and the contacts key are declared"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/ContextGrantTests.swift" "$out/main.swift"
swiftc -O "$grant" "$life" "$app/ContextTrigger.swift" "$out/main.swift" -o "$out/contextgranttests"
"$out/contextgranttests"
