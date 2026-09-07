#!/bin/sh
# The SwiftUI shell, proven as far as a Mac without Xcode can prove it.
#
#   sh app/macos/Tests/run_app_shell_tests.sh
#
# 1. The WHOLE app type-checks: every window, every view, the recorder and
#    both policy layers, against the macOS 26 SDK. This is what catches an
#    API that does not exist before CI's xcodebuild does, on any Mac with the
#    Command Line Tools.
# 2. The theme contract: no Mac view names a colour. Every colour is a role
#    on MacTheme, which is what lets one switch in Settings repaint the app
#    and what stops a view from shipping a champagne letter on white.
# 3. The guide in the app and the guide in docs/ have the same sections in
#    the same order. Two copies of a document drift; this is the belt.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
mac="$here/.."
repo="$mac/../.."
fail=0

echo "typecheck: every Mac source against the macOS 26 SDK"
xcrun swiftc -typecheck -parse-as-library -target arm64-apple-macos26.0 \
    "$mac"/AnticipyMac/*.swift \
    "$mac"/Anticipy/Capture/*.swift \
    "$mac"/Anticipy/Library/*.swift
echo "PASS: the app type-checks"

# Whole-line comments are dropped before every scan: prose that EXPLAINS a
# colour rule is the opposite of a regression.
code_only() {
    grep -n "$1" $2 2>/dev/null | grep -v ':[0-9]*: *//' || true
}
views=$(find "$mac/AnticipyMac" -name '*.swift' ! -name 'MacTheme.swift')

hits=$(code_only 'Color(hex:\|Color(red:\|NSColor(hex:\|\.orange\b\|\.red\b\|Color\.gray\|Color\.blue\|\.systemRed\|\.systemBlue' "$views")
if [ -n "$hits" ]; then
    echo "FAIL: a Mac view names a colour instead of reading a MacTheme role:"
    echo "$hits"
    fail=1
else
    echo "PASS: no Mac view names a colour"
fi

# The product's own copy carries no em dash (the phone's rule, kept here):
# a sentence that needs one is a sentence that wants a full stop.
hits=$(grep -n 'Text("[^"]*—' $views 2>/dev/null || true)
if [ -n "$hits" ]; then
    echo "FAIL: an em dash in a Mac view's copy:"
    echo "$hits"
    fail=1
else
    echo "PASS: no em dash in the Mac app's copy"
fi

# Guide sections: MacGuide's titles, in order, are the doc's h2 headings.
guide_doc="$repo/docs/MAC-APP-GUIDE.md"
[ -f "$guide_doc" ] || { echo "FAIL: missing $guide_doc"; exit 1; }
app_titles=$(grep -o 'Section(title: "[^"]*"' "$mac/AnticipyMac/GuideView.swift" | sed 's/Section(title: "//; s/"$//')
doc_titles=$(grep '^## ' "$guide_doc" | sed 's/^## //')
if [ "$app_titles" = "$doc_titles" ]; then
    echo "PASS: the in-app guide and docs/MAC-APP-GUIDE.md have the same sections"
else
    echo "FAIL: guide sections differ between GuideView.swift and docs/MAC-APP-GUIDE.md"
    echo "--- app"; echo "$app_titles"; echo "--- doc"; echo "$doc_titles"
    fail=1
fi

# The window app has a Dock icon: LSUIElement must be gone, and the icon
# set must carry the full macOS ladder.
if grep -q 'LSUIElement' "$mac/AnticipyMac/Info.plist"; then
    echo "FAIL: Info.plist still hides the app from the Dock (LSUIElement)"
    fail=1
else
    echo "PASS: the app shows in the Dock"
fi
icons=$(ls "$mac/AnticipyMac/Assets.xcassets/AppIcon.appiconset"/*.png 2>/dev/null | wc -l | tr -d ' ')
if [ "$icons" = "10" ]; then
    echo "PASS: the app icon carries all ten macOS sizes"
else
    echo "FAIL: expected 10 app icon PNGs, found $icons"
    fail=1
fi

[ "$fail" = 0 ] && echo "all app-shell checks passed"
exit $fail
