#!/bin/sh
# The pendant's onboarding — the beat almost nobody walks past.
#
#   sh app/ios/Tests/run_pendant_onboarding_tests.sh
#
# Spec: research/2026-09-06-pendant-onboarding-design.md.
# PendantOnboardingPolicy is pure Foundation, so the production source compiles
# straight in. The SwiftUI half is held to source facts here, and the first two
# are the ones that matter.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/PendantOnboardingPolicy.swift"
view="$app/Views/PendantOnboarding.swift"
route="$app/FirstRunRoute.swift"
onboard="$app/Views/OnboardingView.swift"
for f in "$policy" "$view" "$route" "$onboard"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

code() { sed 's://.*$::' "$1"; }

# --------------------------------------------------- THE RADIO IS NOT TOUCHED
# Same rule as the microphone, and the same reason it exists: a permission
# prompt belongs where it has just been explained. `startScan()` raises iOS's
# Bluetooth dialog, so it may only be reachable once somebody has said they own
# a pendant AND has been told what the looking is for.
scans=$(code "$view" | grep -c 'pendant.startScan()' || true)
if [ "$scans" != "1" ]; then
    echo "PendantOnboarding calls startScan() $scans times."
    echo
    echo "It may be called from exactly one place — look() — and only once the"
    echo "looking beat is on screen. Bluetooth's permission dialog is raised by"
    echo "that call, and a dialog that appears before the sentence explaining it"
    echo "is a dialog somebody refuses."
    exit 2
fi
lookfn=$(awk '/private func look\(\)/{g=1} g{print} g&&/^    }$/{exit}' "$view")
if ! printf '%s\n' "$lookfn" | grep -q 'pendant.startScan()'; then
    echo "The one startScan() is not inside look()."
    exit 2
fi
if ! printf '%s\n' "$lookfn" | grep -q 'guard !asked'; then
    echo "look() is not gated. A second tap would start a second scan."
    exit 2
fi
# The offer screen may not reach the radio at all — that is the screen everybody
# sees, including people who own no hardware.
offer=$(awk '/private var offer: some View/{g=1} g{print} g&&/^    }$/{exit}' "$view")
if printf '%s\n' "$offer" | grep -qE 'startScan|pendant\.'; then
    echo "The offer screen touches the radio. Everybody sees that screen,"
    echo "including the great majority who own no pendant."
    exit 2
fi

# ------------------------------------------------ THE MICROPHONE IS STILL LAST
# The pendant beat went in FRONT of the microphone on purpose: `heard` pushes
# live before it queues, so the beat that asks iOS for the microphone may never
# be moved forward.
if ! grep -q 'static let pendant = 4' "$route" || ! grep -q 'static let mic = 5' "$route"; then
    echo "The pendant beat is no longer directly in front of the microphone."
    echo "Nothing may move the microphone beat forward — see the route header."
    exit 2
fi

# ----------------------------------------------------- THE BRANCH'S DIRECTION
# The primary control is the one WITHOUT hardware. If somebody swaps these, the
# product starts telling strangers they need to buy something to continue.
if ! grep -q 'kind: .black' "$view"; then
    echo "The offer's primary control is no longer the filled pill."
    exit 2
fi
primary_block=$(awk '/offerPrimary/{print; found=1} END{if(!found) exit 1}' "$view") || {
    echo "The offer screen no longer renders Copy.offerPrimary."; exit 2; }
# The filled pill must carry offerPrimary, and offerSecondary must NOT be a pill.
if code "$view" | grep -B 4 'OnboardPillStyle(kind: .black)' | grep -q 'offerSecondary'; then
    echo "The 'I have a pendant' line has become a filled pill."
    echo
    echo "That inverts the whole flow. There is no shipping pendant and the"
    echo "phone is the primary ear, so continuing without one is the ordinary"
    echo "road and must look like it."
    exit 2
fi

# ----------------------------------------------------------- NO INVENTED FACTS
if code "$policy" | grep -qiE '"[0-9]+%"|battery.*[0-9]{1,3}|firmware.*=.*"[0-9]'; then
    echo "The policy states a hardware fact nobody measured."
    echo "A battery percentage or firmware version invented here is a sentence"
    echo "that will be wrong in front of the first real device."
    exit 2
fi

# ------------------------------------------------------------------ THE COLOUR
if code "$view" | grep -q 'Color(hex:'; then
    echo "The pendant screens name a colour instead of reading a Theme role."
    exit 2
fi

# --------------------------------------------------------------- the walk
cp "$here/PendantOnboardingTests.swift" "$out/main.swift"
swiftc "$policy" "$out/main.swift" -o "$out/pendantonboardingtests"
"$out/pendantonboardingtests"
