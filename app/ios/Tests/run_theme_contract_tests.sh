#!/bin/sh
# The iOS half of the theme contract: no view may decide a colour, and no view
# may hand-roll a scheme-dependent effect.
#
#   sh app/ios/Tests/run_theme_contract_tests.sh
#
# WHY THIS EXISTS. `extension/tests/test_theme_contract.mjs` proves the four WEB
# surfaces share one palette — and it reads only .html and .css. So when light
# mode landed, two Swift views kept their own hand-rolled grain with
# `.blendMode(.plusLighter)` and the dark opacity baked in. One of them was
# AuthView, the first screen a new person ever sees: a white haze over a white
# page, eating the contrast of everything under it. Both passed every existing
# test, because nothing looked at Swift.
#
# This is a source scan, not a unit test, and that is deliberate: the defect is
# the EXISTENCE of a colour decision outside the token layer, which no runtime
# assertion can see.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
theme="$app/Theme.swift"
[ -f "$theme" ] || { echo "missing $theme"; exit 2; }
fail=0

# Everything except the token layer itself.
views=$(find "$app" -name '*.swift' ! -name 'Theme.swift' ! -name 'AppTheme.swift')
all_swift=$(find "$app" -name '*.swift')

# PROSE IS NOT CODE. These files EXPLAIN the defects they fixed — AuthView says
# in as many words that it used to hard-code `.blendMode(.plusLighter)` — and an
# explanation is the opposite of a regression. Whole-line comments are dropped
# before every scan below, exactly as the web contract test drops them.
code_only() {
    # shellcheck disable=SC2086
    grep -n "$1" $2 2>/dev/null | grep -v ':[0-9]*: *//' || true
}

# 1. Scheme-dependent blend modes belong to GrainLayer alone. `plusLighter`
#    adds light (right on ink, a haze on white); `multiply` removes it (right on
#    white, invisible on ink). A view choosing one has hard-coded a theme.
hits=$(code_only 'blendMode(\.plusLighter)\|blendMode(\.multiply)' "$views")
if [ -n "$hits" ]; then
    echo "A view hard-codes a scheme-dependent blend mode. Use GrainLayer():"
    echo "$hits"
    fail=1
fi

# 2. Raw colour literals. Every colour is a role on Theme.
hits=$(code_only 'Color(hex:\|Color(red:\|UIColor(hex:\|systemRed\|Color\.gray\|Color\.orange' "$views")
if [ -n "$hits" ]; then
    echo "A view names a colour instead of reading a Theme role:"
    echo "$hits"
    fail=1
fi

# 3. Exactly one place pins the colour scheme, and it reads the stored choice.
pins=$(code_only 'preferredColorScheme(' "$all_swift")
count=$(printf '%s' "$pins" | grep -c . || true)
if [ "$count" != "1" ]; then
    echo "Expected exactly ONE preferredColorScheme pin, found $count:"
    echo "$pins"
    fail=1
fi
if ! printf '%s' "$pins" | grep -q 'AppTheme(rawValue: themeChoice).colorScheme'; then
    echo "The scheme pin no longer reads the stored choice — light-by-default is gone."
    fail=1
fi

# 4. The system setting must stay ignored. A nil/unspecified pin would hand the
#    first impression to a switch in iOS Settings nobody chose for this product.
if [ -n "$(code_only 'preferredColorScheme(nil)\|UIUserInterfaceStyle' "$all_swift")" ] \
   || grep -q 'UIUserInterfaceStyle' "$here/../project.yml" 2>/dev/null; then
    echo "Something follows the system appearance. Light is the default for everyone."
    fail=1
fi

# 5. Light really is the default, and dark really is black.
grep -q 'static let bg = themed(0xFFFFFF, 0x000000)' "$theme" || {
    echo "Theme.bg is no longer white-on-light / black-on-dark."; fail=1; }
grep -q 'AppTheme.light.rawValue' "$app/AnticipyApp.swift" || {
    echo "The root no longer defaults to light."; fail=1; }

[ "$fail" = "0" ] || exit 1
echo "iOS theme contract: no view decides a colour, one scheme pin, light is the default"
