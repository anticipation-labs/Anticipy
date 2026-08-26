#!/bin/sh
# What a field says about itself, and the silence it used to keep.
#
#   sh app/ios/Tests/run_field_caption_tests.sh
#
# Settings' number field had two captions where it needed four. `e164` returns
# nil without a country code, `saveOwnerPhone` opens with
# `guard let e = e164(raw) else { return false }`, and the screen's only state
# was one `phoneSaved` bool — so typing "+44" and pressing Save set false over
# false and the caption went on showing its neutral default. The failure was
# invisible on the one field a text is sent to, and a text is the only channel
# this product has outside the app.
#
# Exit code is the result. Non-zero means a field is lying about itself again.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

theme="$app/Theme.swift"
settings="$app/Views/SettingsView.swift"
onboard="$app/Views/OnboardingView.swift"
for f in "$theme" "$settings" "$onboard"; do
    [ -f "$f" ] || { echo "missing $f — these checks would compile nothing"; exit 2; }
done

# Whole-line comments dropped before every source scan, exactly as the theme
# contract test does it: these files EXPLAIN the defects they fixed, and an
# explanation is the opposite of a regression.
code() { grep -vE '^[[:space:]]*//' "$1"; }

# ---------------------------------------------------------------- the wiring
#
# The logic below is worthless if the screen has stopped consulting it.

# 1. THE PREDICATE. `.disabled(phoneField.isEmpty)` never matched
#    `saveOwnerPhone`, which refuses anything `e164` refuses — so "+44" lit the
#    button, the save returned false, and nothing was reported. And once the
#    field is prefilled it is never empty, so that test stopped meaning anything
#    at all. This is the same expression the first-run beat gates its own button
#    on.
if ! code "$settings" | grep -q 'disabled(session\.e164(phoneField) == nil'; then
    echo "Settings' Save button no longer gates on e164."
    echo "saveOwnerPhone begins 'guard let e = e164(raw) else { return false }'."
    echo "A button that is live over text e164 refuses is a button whose only"
    echo "outcome is a silent false, which is the bug this suite exists for."
    exit 2
fi
if code "$settings" | grep -q 'disabled(phoneField\.isEmpty'; then
    echo "Settings' Save button is gated on emptiness again."
    echo "The field arrives holding this phone's dialling code, so it is never"
    echo "empty and that test can never be true."
    exit 2
fi

# 2. THE PREFILL. e164 refuses to invent a country; the refusal is only a fix
#    if the country is in front of the person rather than missing behind them.
if ! code "$settings" | grep -q 'DiallingCode\.forThisPhone()'; then
    echo "Settings' number field no longer arrives with this phone's dialling code."
    echo "e164 refuses to guess a country. Without the prefill somebody meets an"
    echo "empty field, types the number they have typed their whole life, and is"
    echo "refused. That is the same dead end wearing a different hat."
    exit 2
fi

# 3. THE CAPTION, ON THE NUMBER FIELD SPECIFICALLY. Naming the component alone
#    was not enough: a first draft of this leg passed while the number field's
#    caption had been replaced, because the details field four sections up still
#    named it. So the check is the WIRING — the caption must be driven by the
#    same predicate the button is gated on, and by the outcome the save came
#    back with. A caption reading anything else is a caption that can disagree
#    with the button beside it, which is the whole defect.
if ! code "$settings" | grep -q 'complete: session\.e164(phoneField) != nil'; then
    echo "Settings' number caption no longer reads e164."
    echo "The caption and the Save button have to answer to one predicate, or"
    echo "the screen can refuse a number in one place and accept it in the other."
    exit 2
fi
if ! code "$settings" | grep -q 'attempt: phoneAttempt'; then
    echo "Settings' number caption no longer reads what the save came back with."
    echo "That is the state the old `phoneSaved` bool had no room for: a save"
    echo "that never reached the server, reported as nothing at all."
    exit 2
fi
if ! code "$settings" | grep -q 'FieldCaptionLine('; then
    echo "Settings no longer renders its captions through FieldCaptionLine."
    echo "Every hand-rolled caption is a fourth set of states waiting to happen."
    exit 2
fi
if code "$settings" | grep -q 'phoneSaved ?'; then
    echo "The two-state caption ternary is back on the number field."
    exit 2
fi

# 4. TWO SENTENCES, ONE WORDING. The constants must still be what the first-run
#    beat ships, or the port has drifted and the component bought nothing.
refusal=$(grep -o 'That doesn'"'"'t look like a full number yet — country code and all\.' "$theme" | head -1)
[ -n "$refusal" ] || { echo "Theme lost the refusal sentence."; exit 2; }
grep -qF "$refusal" "$onboard" || {
    echo "The refusal sentence no longer matches the one OnboardingView ships."
    echo "Two wordings for one event is exactly what FieldCaption exists to stop."
    exit 2; }

failure=$(grep -o 'I couldn'"'"'t save that just now\. I need a connection to keep it\.' "$theme" | head -1)
[ -n "$failure" ] || { echo "Theme lost the connection sentence."; exit 2; }
grep -qF "$failure" "$onboard" || {
    echo "The connection sentence no longer matches the one OnboardingView ships."
    exit 2; }

# 5. THE DUPLICATE STOP. "Until I turn it back on" called the identical
#    stopNow() as the "Stop listening" button four lines above it and was
#    visible at the same moment — a menu offering a choice already on screen.
if code "$settings" | grep -q 'Until I turn it back on'; then
    echo "The pause menu carries a duplicate of the Stop button again."
    exit 2
fi

# 6. NO COLOUR DECIDED HERE. The theme contract's rule 2 says every colour is a
#    role on Theme; it greps for Color(hex:) and friends and cannot see a bare
#    `.red` on foregroundStyle, which is how six of them lived in this file. The
#    pendant row's own comment argues the case: iOS's red "appears nowhere else
#    in the brand". Scoped to this file, which is the one these checks own.
if code "$settings" | grep -qE 'foregroundStyle\(\.(red|orange|green|yellow|blue|gray)\)'; then
    echo "SettingsView names a system colour instead of reading a Theme role:"
    code "$settings" | grep -nE 'foregroundStyle\(\.(red|orange|green|yellow|blue|gray)\)'
    exit 2
fi

# ------------------------------------------------------------- the real type
#
# LIFTED from Theme.swift and compiled, never copied — the same rule
# run_phone_number_tests.sh applies to e164, for the same reason: a copy is
# honest exactly until somebody edits one side of it.
#
# The lift is also a law leg in its own right. It is compiled against Foundation
# ALONE, so the moment the state machine reaches for a Color, a Font or a View
# this suite stops building. The decision about which of four things a field is
# saying has to be answerable without a screen, or it cannot be tested without
# one.
awk '
    /^enum FieldCaption \{/ { grab = 1 }
    grab {
        print
        n = gsub(/\{/, "{"); m = gsub(/\}/, "}")
        depth += n - m
        if (depth <= 0 && seen) { exit }
        if (n > 0) seen = 1
    }
' "$theme" > "$out/lifted.swift"

if ! grep -q '^enum FieldCaption {' "$out/lifted.swift"; then
    echo "Found no \`enum FieldCaption\` in Theme.swift."
    echo "Either the component moved or this extraction broke; either way these"
    echo "checks are compiling nothing, which is worse than having none."
    exit 2
fi
# A brace-match that stopped early compiles a fragment; one that ran away
# swallows the rest of the file. Both are caught by the closing brace count.
opens=$(tr -cd '{' < "$out/lifted.swift" | wc -c | tr -d ' ')
closes=$(tr -cd '}' < "$out/lifted.swift" | wc -c | tr -d ' ')
if [ "$opens" != "$closes" ] || [ "$opens" = "0" ]; then
    echo "The extracted FieldCaption has $opens '{' and $closes '}' — the"
    echo "extraction is not bracketing the enum. These checks would test a"
    echo "fragment."
    exit 2
fi
# Five states and three attempts, or the lift has caught only the head of it.
for name in 'case neutral' 'case valid' 'case notYetValid' 'case saveFailed' \
            'case saved' 'case untried' 'case failed' 'static func state' \
            'static func rendered' 'static func sentence' 'struct Words'; do
    grep -q "$name" "$out/lifted.swift" || {
        echo "The extracted FieldCaption is missing \`$name\` — the lift is short."
        exit 2; }
done
echo "lifted FieldCaption from Theme.swift: $(wc -l < "$out/lifted.swift" | tr -d ' ') lines"

{
    echo "import Foundation"
    cat "$out/lifted.swift"
} > "$out/FieldCaption.swift"

# COMPILED AS `main.swift`: swiftc allows top-level code in a file of that name
# and nowhere else, and these checks are written as top-level statements like
# every other suite here. See run_phone_number_tests.sh for the whole argument.
cp "$here/FieldCaptionTests.swift" "$out/main.swift"
swiftc -O "$out/FieldCaption.swift" "$out/main.swift" -o "$out/fieldcaptiontests"
"$out/fieldcaptiontests"
