#!/bin/sh
# The opening — the four-second dot-to-mark intro — walked frame by frame.
#
#   sh app/ios/Tests/run_launch_intro_tests.sh
#
# LaunchIntro is pure Foundation, so the production source is compiled straight
# in, together with FirstRunRoute for `plays(route:)`. The SwiftUI half,
# IntroView, is held to three source facts here: it draws what LaunchIntro
# says, it shows the finished mark under Reduce Motion, and it puts NO TEXT on
# screen — the owner's rule for the piece (2026-09-05) was no text, no filler,
# nothing that was not drawn in front of them.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

intro="$app/LaunchIntro.swift"
route="$app/FirstRunRoute.swift"
view="$app/Views/IntroView.swift"
appfile="$app/AnticipyApp.swift"
for f in "$intro" "$route" "$view" "$appfile"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

# ------------------------------------------------------------ source facts
if grep -q 'Text(' "$view"; then
    echo "IntroView puts text on screen. The opening is ink on cream and"
    echo "nothing else; a caption, a wordmark or a skip label is filler."
    exit 2
fi
if ! grep -q 'LaunchIntro.frame(at:' "$view"; then
    echo "IntroView no longer draws LaunchIntro.frame(at:). Whatever it draws"
    echo "instead is not the timeline this suite walks."
    exit 2
fi
if ! grep -q 'reduceMotion' "$view" || ! grep -q 'LaunchIntro.finalFrame' "$view"; then
    echo "IntroView does not show the finished mark under Reduce Motion."
    exit 2
fi
if ! grep -q 'onTapGesture' "$view"; then
    echo "The opening cannot be tapped through. Four seconds a person cannot"
    echo "skip is a wait, not an opening."
    exit 2
fi
if ! grep -qE 'IntroView[ ({]' "$appfile" || ! grep -q 'LaunchIntro.plays(route:' "$appfile"; then
    echo "AnticipyApp does not put IntroView on screen behind LaunchIntro.plays(route:)."
    echo "Either the opening is unreachable or it plays over Home."
    exit 2
fi

# ------------------------------------------------------------ the timeline
# main.swift, because swiftc allows top-level code under that name only
# (run_phone_number_tests.sh learned this the long way). No -O: nothing here
# is worth an optimiser's time.
cp "$here/LaunchIntroTests.swift" "$out/main.swift"
swiftc "$intro" "$route" "$out/main.swift" -o "$out/launchintrotests"
"$out/launchintrotests"
