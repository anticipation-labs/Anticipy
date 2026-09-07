#!/bin/sh
# Settings — fourteen screens that had no suite at all.
#
#   sh app/ios/Tests/run_settings_tests.sh
#
# The audit of 2026-09-06 found this the flattest surface in the product: ~3,700
# lines across fourteen screens with ONE animation and ZERO transitions between
# them, and no gate anywhere. It is also where sign-out, "forget me on this
# iPhone" and "delete my account" live — the screens where being unsure costs
# the most, and where polish IS the trust signal.
#
# There is no pure policy behind most of Settings, so this suite is source facts
# rather than a walk. Each one is a rule about what an irreversible row may look
# like, and each is written because getting it wrong is unrecoverable.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
views="$here/../Anticipy/Views"
kit="$views/SettingsKit.swift"
[ -f "$kit" ] || { echo "missing $kit"; exit 2; }
code() { sed 's://.*$::' "$1" | sed 's:///.*$::'; }
screens=$(ls "$views" | grep '^Settings.*View\.swift$')
count=$(printf '%s\n' "$screens" | wc -l | tr -d ' ')
[ "$count" -ge 11 ] || { echo "only $count Settings screens found; the glob is wrong"; exit 2; }

# ============================== AN IRREVERSIBLE ROW SAYS WHAT IT COSTS
# Consequence before verb. "Delete my account and server data" followed by the
# sentence naming transcripts, memory, work and receipts — never a bare verb
# that a person discovers the meaning of afterwards.
for f in $screens; do
    path="$views/$f"
    grep -q 'DestructiveRow' "$path" || continue
    if ! grep -q 'FootnoteText' "$path"; then
        echo "$f has a destructive row and no sentence saying what it removes."
        echo
        echo "Consequence before verb. A person tapping something irreversible"
        echo "must have been told what it takes with it BEFORE they tap, not in"
        echo "the alert that follows and certainly not afterwards."
        exit 2
    fi
    # ...and it must ASK, never act on the tap itself — unless the row is
    # genuinely reversible AND says so with the marker, which turns the
    # exception into an argument somebody made rather than one they forgot.
    if ! grep -qE 'confirmation|\.alert|showsConfirm' "$path" \
       && ! grep -q 'REVERSIBLE:' "$path"; then
        echo "$f performs a destructive action without confirming it."
        echo
        echo "Either confirm it, or — if the action genuinely takes nothing"
        echo "away — mark the row 'REVERSIBLE:' and say why. An unguarded"
        echo "irreversible row is the one mistake in this app nobody can undo."
        exit 2
    fi
done

# ================= A DESTRUCTIVE ROW NEVER SHARES A CARD WITH A SAFE ONE
# A GroupedCard reads as one object. "Appearance" one row above "Delete my
# account" is a mis-tap that cannot be undone, and thumbs miss.
for f in $screens; do
    path="$views/$f"
    grep -q 'DestructiveRow' "$path" || continue
    mixed=$(awk '
        /GroupedCard \{/ { depth = 1; card = ""; destructive = 0; safe = 0; next }
        depth > 0 {
            card = card $0 "\n"
            if ($0 ~ /DestructiveRow/) destructive = 1
            if ($0 ~ /(NavRow|ActionRow|StateRow|ToggleRow)\(/) safe = 1
            # An if/else inside one card is ONE row position wearing two faces,
            # not two rows a thumb can miss between — "Stop listening" and
            # "Start listening" are the same control in opposite states.
            if ($0 ~ /\} else \{/) exclusive = 1
            if ($0 ~ /^            \}/) {
                if (destructive && safe && !exclusive) print "MIXED"
                depth = 0; exclusive = 0
            }
        }' "$path")
    if [ -n "$mixed" ]; then
        echo "$f puts a destructive row in the same card as an ordinary one."
        echo
        echo "A GroupedCard reads as one object and thumbs miss. Anything"
        echo "irreversible gets a card of its own."
        exit 2
    fi
done

# ==================================== EVERY SCREEN WEARS THE SAME CHROME
# Consistency is what lets somebody navigate without thinking. A Settings page
# that dismisses differently from its neighbours is a page people get lost on.
# The ROOT is a Form with a navigation title — the platform's own container,
# and correct: it is pushed by the app rather than presented as a sheet, so it
# gets a back button from the navigation stack. Every page BELOW it is a sheet
# and must wear SheetChrome, or it dismisses differently from its neighbours.
for f in $screens; do
    case "$f" in SettingsView.swift) continue ;; esac
    grep -q 'SheetChrome' "$views/$f" || {
        echo "$f is a Settings sub-page that does not use SheetChrome, so it"
        echo "dismisses differently from every other page at its level."
        echo
        echo "Consistency is what lets somebody navigate without thinking. The"
        echo "root (SettingsView) is exempt: it is pushed, not presented."
        exit 2
    }
done
grep -q 'navigationTitle("Settings")' "$views/SettingsView.swift" || {
    echo "The Settings root lost its navigation title, so the page it is"
    echo "pushed onto has nothing to label the back button with."
    exit 2
}

# ================================== NO SCREEN NAMES A COLOUR
# The same rule the rest of the app lives under: colours are ROLES on Theme.
for f in $screens SettingsKit.swift; do
    if code "$views/$f" | grep -qE 'Color\(hex:|Color\(red:|UIColor\(|\.systemRed|Color\.gray|Color\.orange|Color\.red'; then
        echo "$f names a colour instead of reading a Theme role."
        code "$views/$f" | grep -nE 'Color\(hex:|Color\(red:|UIColor\(|\.systemRed|Color\.gray|Color\.orange|Color\.red'
        exit 2
    fi
done

# ============================= A ROW ANSWERS THE THUMB, AND HONOURS THE SWITCH
# One style is worn by every row on all fourteen screens, which is why it is
# the only place this had to change. It must also be the only place that can
# forget Reduce Motion.
if ! code "$kit" | grep -q 'struct CardRowButtonStyle'; then
    echo "The shared row press style is gone."
    exit 2
fi
style=$(code "$kit" | awk '/struct CardRowButtonStyle/{g=1} g{print} g&&/^\}$/{exit}')
if ! printf '%s\n' "$style" | grep -q 'isPressed\|pressed'; then
    echo "Settings rows no longer react to being pressed."
    exit 2
fi
if ! printf '%s\n' "$style" | grep -q 'accessibilityReduceMotion'; then
    echo "The row press style ignores Reduce Motion."
    echo
    echo "It is worn by every row on fourteen screens, so forgetting it here"
    echo "forgets it everywhere at once. Under Reduce Motion the row must still"
    echo "CHANGE — the tint is the feedback — it just stops moving."
    exit 2
fi
if ! printf '%s\n' "$style" | grep -q 'spring('; then
    echo "The press is no longer a spring."
    echo "A row is a physical thing being pushed and released, and a linear"
    echo "fade is not how objects behave."
    exit 2
fi

echo "all settings checks passed ($count screens)"
