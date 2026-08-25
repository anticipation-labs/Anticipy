#!/bin/sh
# The number the only channel this product has will text.
#
#   sh app/ios/Tests/run_phone_number_tests.sh
#
# `AnticipySession.e164` prepended "+1" to any bare ten-digit number, so a
# stranger outside North America finished sign-up with a US number on their
# account and received nothing all week, with no error on any screen. The fix is
# that e164 refuses to invent a country — and a refusal is only a fix if the
# field the stranger meets already carries theirs, which is DiallingCode.
#
# e164 is LIFTED OUT OF AnticipyApp.swift and compiled, never copied. The suite
# next door (ReachableNumberTests) keeps its own copy of looksReachable, and a
# copy is honest only until somebody edits one side of it.
#
# Exit code is the result. Non-zero means a stranger's number is wrong again.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

src="$app/AnticipyApp.swift"
auth="$app/Views/AuthView.swift"
onboard="$app/Views/OnboardingView.swift"
dial="$app/DiallingCode.swift"

for f in "$src" "$auth" "$onboard" "$dial"; do
    [ -f "$f" ] || { echo "missing $f — these checks would compile nothing"; exit 2; }
done

# ------------------------------------------------------------- the wiring
# The logic below is worthless if the door has stopped consulting it. `canGo`
# used to read looksReachable alone, which accepts a bare ten-digit number that
# e164 now refuses: the Start button would create the account with NO number on
# it, silently, because signUp passes e164(phone) straight through.
if ! grep -q 'session.e164(phone) != nil' "$auth"; then
    echo "AuthView no longer gates sign-up on e164."
    echo "looksReachable accepts a bare ten-digit number and e164 refuses one,"
    echo "so the Start button would light up over a number that normalises to"
    echo "nil — and signUp writes that nil straight onto the new account. An"
    echo "account with no number can never be texted, and this product has no"
    echo "notifications at all."
    exit 2
fi
if ! grep -q 'DiallingCode.forThisPhone()' "$auth" \
    || ! grep -q 'DiallingCode.forThisPhone()' "$onboard"; then
    echo "The number field no longer arrives with this phone's dialling code."
    echo "e164 refuses to guess a country. Without the prefill, a stranger"
    echo "outside North America meets an empty field, types the number they"
    echo "have typed their whole life, and is refused with nothing on screen"
    echo "explaining what is missing. That is the same dead end one screen"
    echo "later, not a fix."
    exit 2
fi

# ------------------------------------------------------------ the real e164
# Brace-matched from the declaration, so no marker comment can rot away from
# the function it claims to bracket. `nonisolated` is dropped: it means nothing
# at file scope and the body touches no `self`.
awk '
    /^[ \t]*(nonisolated[ \t]+)?func e164\(/ { grab = 1 }
    grab {
        line = $0
        sub(/nonisolated[ \t]+func e164\(/, "func e164(", line)
        print line
        n = gsub(/\{/, "{"); m = gsub(/\}/, "}")
        depth += n - m
        if (depth <= 0 && seen) { exit }
        if (n > 0) seen = 1
    }
' "$src" > "$out/e164.swift"

if ! grep -q 'func e164(' "$out/e164.swift"; then
    echo "Found no \`func e164\` in AnticipyApp.swift."
    echo "Either normalisation moved or this extraction broke; either way these"
    echo "checks are compiling nothing, which is worse than having none."
    exit 2
fi
# A brace-match that stopped early compiles a fragment; one that ran away
# swallows the rest of the file. Both are caught by the closing brace count.
opens=$(tr -cd '{' < "$out/e164.swift" | wc -c | tr -d ' ')
closes=$(tr -cd '}' < "$out/e164.swift" | wc -c | tr -d ' ')
if [ "$opens" != "$closes" ] || [ "$opens" = "0" ]; then
    echo "The extracted e164 has $opens '{' and $closes '}' — the extraction is"
    echo "not bracketing the function. These checks would test a fragment."
    exit 2
fi
echo "lifted e164 from AnticipyApp.swift: $(wc -l < "$out/e164.swift" | tr -d ' ') lines"

{
    echo "import Foundation"
    cat "$out/e164.swift"
} > "$out/E164.swift"

# COMPILED AS `main.swift`, and the name is the whole reason this works.
#
# These checks are written as top-level code, like ReachableNumberTests next
# door. That file is run with `swift <file>` — the interpreter, which allows
# top-level statements in a file of any name. This suite cannot be: it has to
# compile THREE files together (the lifted e164, DiallingCode, and the checks),
# and `swiftc` allows top-level code in `main.swift` and nowhere else. Passing
# `PhoneNumberTests.swift` to swiftc produced "expressions are not allowed at
# the top level" once per check — sixty-odd errors — and with `-O` in front of
# them the compile did not come back at all, so the suite read as a HANG rather
# than as a file that cannot build. Copying it under the one name the compiler
# accepts is the whole fix.
#
# AND WITHOUT `-O`, which is the other half of the same hang. Every other suite
# here optimises, but none of them links DiallingCode: its table is ~250 entries
# parsed out of one multi-line literal in a global initializer, and the
# optimiser sits on that indefinitely — measured here at over five minutes with
# no output and no end, against under three seconds without it. These are
# correctness checks on a pure function; there is nothing for `-O` to buy them,
# and a suite that never returns is a suite nobody runs.
cp "$here/PhoneNumberTests.swift" "$out/main.swift"
swiftc \
    "$out/E164.swift" \
    "$dial" \
    "$out/main.swift" \
    -o "$out/phonenumbertests"
"$out/phonenumbertests"
