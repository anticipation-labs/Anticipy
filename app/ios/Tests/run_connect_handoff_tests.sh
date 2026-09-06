#!/bin/sh
# THE CONNECT HANDOFF AND THE CONNECT SESSION — the twenty seconds where this
# feature is compliant or broken.
#
#   sh app/ios/Tests/run_connect_handoff_tests.sh
#
# Spec: "Connections: how Anticipy asks, learns, and never says Composio",
# 2026-09-05. Server contract: spike/two-hands/src/connections/contract.ts.
#
# TWO FILES, AND THE SPLIT IS THE POINT. `ConnectHandoff` DECIDES — may this
# open, for whom, and how — and is pure Foundation, so every one of its rules
# runs here under swiftc with no simulator, no signing and no network.
# `ConnectSession` PERFORMS: it is the only code in the app that turns that
# decision into an opened browser, and the only holder of a `DisclosureGate`.
#
# The source legs below are here rather than in the suite because each is about
# the EXISTENCE or ABSENCE of something in a file, which no runtime assertion
# can see. The one leg that must never be softened — that no embedded web view
# is named in ANY file that can open a URL — lives in the suite instead, where
# it is checked against fixtures first so it cannot pass by matching nothing,
# and where it reads `ConnectHandoff.swift`, `ConnectSession.swift`,
# `AnticipyApp.swift` and every file under `Views/`. Until 2026-09-05 it read
# exactly one file: the one file in the app that never opens a URL.
#
# Exit code is the result. Non-zero means a connect could open somewhere Google
# refuses to sign anyone in, or a deep link could mark an app connected for a
# person who never tapped anything.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
repo=$(cd "$here/../../.." && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Backend/ConnectHandoff.swift"
presenter="$app/Backend/ConnectSession.swift"
root="$app/AnticipyApp.swift"
suite="$here/ConnectHandoffTests.swift"
for f in "$policy" "$presenter" "$root" "$suite"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

code() { grep -vE '^[[:space:]]*(//|///)' "$1"; }

# ------------------------------------------------------------ the policy is pure
# The whole point of a policy layer is that "what will the app open, and for
# whom" is answerable with no phone, no browser and no account. Foundation is
# the only import this file may have: AuthenticationServices, UIKit or SwiftUI
# in here means the decision has been folded back into the thing it exists to
# be testable without — and it is also how a class name that must never appear
# arrives.
imports=$(grep -E '^[[:space:]]*import[[:space:]]' "$policy" \
    | sed -E 's/^[[:space:]]*import[[:space:]]+//' | sort -u | tr '\n' ' ')
if [ "$imports" != "Foundation " ]; then
    echo "ConnectHandoff imports more than Foundation: ${imports:-nothing}"
    echo "The handoff decides what opens; it does not open it. A UI or web"
    echo "framework in here is a decision that can no longer be run on a laptop"
    echo "at the instant that matters."
    exit 2
fi

# ------------------------------------------- the presenter's imports, allowlisted
# The presenter DOES open things, so it gets the two frameworks that open a real
# browser and nothing else. This is an allowlist, not a blocklist: the two
# embedded-browser frameworks are what Google refuses a sign-in inside, and a
# blocklist is one new spelling away from being wrong. SwiftUI is out too — the
# decisions above it stay runnable on a laptop.
allowed="AuthenticationServices Combine Foundation UIKit"
extra=""
for name in $(grep -E '^[[:space:]]*import[[:space:]]' "$presenter" \
    | sed -E 's/^[[:space:]]*import[[:space:]]+//' | sort -u); do
    case " $allowed " in
        *" $name "*) ;;
        *) extra="$extra $name" ;;
    esac
done
if [ -n "$extra" ]; then
    echo "ConnectSession imports something outside the allowlist:$extra"
    echo "  allowed: $allowed"
    echo ""
    echo "Two openings and no third. A sign-in inside an embedded browser is"
    echo "answered with disallowed_useragent and the connect fails outright."
    exit 2
fi

# ------------------------------------------------------------------ LAW 1
# Nothing in either file may decide what a human's words mean. WHICH app the
# owner meant is a model's question, answered against the catalog by
# ToolkitJudge in the server contract; these files are handed a slug they never
# chose. A regex over text would be that decision moving back into a pattern.
for f in "$policy" "$presenter"; do
    if code "$f" | grep -qE 'NSRegularExpression|options:[[:space:]]*\.regularExpression'; then
        echo "$(basename "$f") matches a pattern against text."
        echo "HARNESS-LAWS Law 1: the only strings these files may read are an"
        echo "identifier's shape, a URL's scheme and host, and the machine tokens"
        echo "of our own done page. None of those is prose."
        exit 2
    fi
done

# -------------------------------------------------- nobody's tokens but yours
# contract.ts: "A constant here would mean one person's tokens serving
# everybody, which is the worst failure this system can have." During the spike
# one operator's own mailbox was connected by hand; it was revoked and deleted.
# An owner row id is fifteen lowercase alphanumerics, so a literal of that shape
# in either file is that failure written down.
for f in "$policy" "$presenter"; do
    if code "$f" | grep -oE '"[a-z0-9]{15}"' | grep -q '[0-9]'; then
        echo "$(basename "$f") carries a literal shaped like an owner row id:"
        code "$f" | grep -oE '"[a-z0-9]{15}"' | grep '[0-9]'
        echo "Every connection belongs to the owner signed into THIS phone. The"
        echo "owner is an argument, resolved per request, never a constant."
        exit 2
    fi
done

# ------------------------------------------- the link allowlist, in the source
# The spec's first rule is that we own the ask: every link is anticipy.ai/c/,
# never the provider's own and never Google's. That is an ALLOWLIST — a
# blocklist is one new hostname from being wrong — and widening it has to be a
# visible diff rather than a value somebody adds in passing. Spelled as "sort
# the hosts out of the literal and compare the names" so re-wrapping stays
# green; a set that stopped being a literal at all extracts as nothing and is
# red here, which is the same hole with better manners.
hosts=$(tr '\n' ' ' < "$policy" \
    | sed -n 's/.*connectLinkHosts:[[:space:]]*Set<String>[[:space:]]*=[[:space:]]*\[\([^]]*\)\].*/\1/p' \
    | tr -d ' "' | tr ',' '\n' | grep -v '^$' | sort | tr '\n' ' ')
if [ "$hosts" != "anticipy.ai " ]; then
    echo "The connect-link allowlist is not the one host the spec names."
    echo "  the source declares : ${hosts:-nothing this leg can read}"
    echo "  the spec names      : anticipy.ai"
    echo ""
    echo "Every ask is ours: single-use token, ten minutes, bound to the owner."
    echo "Adding a host here is how a raw provider link reaches a person, which"
    echo "is what happened on 2026-09-05 and why the rule exists."
    exit 2
fi

# ------------------------------------------------- the enums are closed, in the source
# A fourth way to open a connect link is a SCHEMA CHANGE and has to be defended
# in a diff. The one that matters is an embedded web view, which is not a
# fallback or a compatibility mode: Google answers a sign-in inside one with
# `disallowed_useragent` and the connect fails outright. The suite reads these
# files for the class names; this reads the DECLARATION, which is the half a
# name-scan cannot see — a case called `.inApp` names nothing forbidden.
cases_of() {
    awk -v want="$2" '
        $0 ~ ("^enum " want "[ :{]") { inside = 1; next }
        inside && /^\}/ { exit }
        inside && /^[[:space:]]*case [a-z]/ {
            line = $0
            sub(/^[[:space:]]*case /, "", line)
            sub(/[ (=:].*$/, "", line)
            print line
        }
    ' "$1" | sort | tr '\n' ' '
}

presentations=$(cases_of "$policy" ConnectPresentation)
if [ "$presentations" != "authSession refused systemBrowser " ]; then
    echo "ConnectPresentation is no longer the two openings and the refusal."
    echo "  the source declares : ${presentations:-nothing this leg can read}"
    echo "  expected            : authSession refused systemBrowser"
    echo ""
    echo "Both openings are a real browser the person can see the address bar"
    echo "of. A third opening is how the connect stops working."
    exit 2
fi

openings=$(cases_of "$presenter" ConnectOpening)
if [ "$openings" != "openedInSignInSession openedInSystemBrowser refused " ]; then
    echo "ConnectOpening is no longer the two openings and the refusal."
    echo "  the source declares : ${openings:-nothing this leg can read}"
    echo "  expected            : openedInSignInSession openedInSystemBrowser refused"
    echo ""
    echo "What a tap DID has to stay the same shape as what the handoff"
    echo "decided, or the presenter has grown a way to open something the"
    echo "policy never authorised."
    exit 2
fi

dones=$(cases_of "$policy" ConnectDone)
if [ "$dones" != "cancelled connected failed unreadable " ]; then
    echo "ConnectDone is no longer four states."
    echo "  the source declares : ${dones:-nothing this leg can read}"
    echo "  expected            : cancelled connected failed unreadable"
    echo ""
    echo "\"it connected\", \"they backed out\", \"it went wrong\" and \"we cannot"
    echo "read this\" are four different things, and a smaller answer cannot"
    echo "keep them apart — the deep link is reachable by anyone, so the"
    echo "fourth state is the one that stops a stranger's URL being read as"
    echo "one of the other three."
    exit 2
fi

# --------------------------------------- the disclosure has exactly one holder
# Google's Workspace policy wants a real affirmative action immediately before
# each connect flow. `DisclosureGate` is satisfied by `disclosureShown` followed
# by `acknowledge`, and a view that could make both calls in one function body
# would be back to the version of this feature that had no disclosure in it at
# all — which is what shipped until 2026-09-05, when the gate had ZERO CALLERS.
# So the gate has exactly one holder, it is private inside it, and no other
# production file may construct one or call either method.
strays=$(grep -rl --include='*.swift' -e 'DisclosureGate(' -e '\.acknowledge(' \
    -e '\.disclosureShown(' "$app" 2>/dev/null \
    | grep -v '/Backend/ConnectSession.swift$' \
    | grep -v '/Backend/ConnectHandoff.swift$' || true)
if [ -n "$strays" ]; then
    echo "A production file other than ConnectSession touches the disclosure gate:"
    echo "$strays"
    echo ""
    echo "The gate is private inside ConnectSession so the two calls that"
    echo "satisfy it cannot be made in one function body by something that drew"
    echo "nothing. A second holder is that hole, reopened."
    exit 2
fi
if ! grep -q 'private var gate = DisclosureGate()' "$presenter"; then
    echo "ConnectSession no longer holds its DisclosureGate privately."
    echo "A gate a view can reach is a gate a view can satisfy without drawing"
    echo "anything, which is the failure this whole section is about."
    exit 2
fi

# ------------------------------------------- the callback scheme is registered
# A deep link the app is not registered for never arrives, and the failure is
# silent: the connect finishes at the other end, the browser hands the URL to
# nobody, and the phone sits on a spinner. The scheme is shared with the
# widget's doorbell, and Info.plist is REGENERATED from project.yml, so both
# have to name it or the next `xcodegen generate` takes it away.
scheme=$(sed -n 's/.*static let callbackScheme = "\([^"]*\)".*/\1/p' "$policy" | head -1)
host=$(sed -n 's/.*static let callbackHost = "\([^"]*\)".*/\1/p' "$policy" | head -1)
if [ -z "$scheme" ] || [ -z "$host" ]; then
    echo "This gate can no longer read the callback scheme or host out of the handoff."
    exit 2
fi
plist="$app/Info.plist"
if [ -f "$plist" ] && ! grep -q "<string>$scheme</string>" "$plist"; then
    echo "The callback scheme \"$scheme\" is not registered in $plist."
    echo "The done page redirects to $scheme://$host/{toolkit}. If the app"
    echo "does not own the scheme, that URL reaches nobody: the connect"
    echo "finishes at the other end and the phone sits on a spinner with no"
    echo "error anywhere. (The bundle id contains the word too, so this leg"
    echo "reads the URL-scheme entry itself and not the file.)"
    exit 2
fi
yml="$here/../project.yml"
if [ -f "$yml" ] && ! grep -qE "^[[:space:]]*-[[:space:]]*$scheme[[:space:]]*$" "$yml"; then
    echo "The callback scheme \"$scheme\" is not in project.yml's URL schemes."
    echo "Info.plist is REGENERATED from project.yml, so a scheme that lives"
    echo "only in the plist is a scheme the next \`xcodegen generate\` deletes."
    exit 2
fi

# ------------------------------------------ and something has to ROUTE the host
# Registering the scheme is half of it. `AnticipyApp.onOpenURL` used to answer
# the widget's doorbell and IGNORE every other host, so a connect finishing in
# the system browser reached nobody: the phone sat on a spinner and no error was
# raised anywhere. This ran as a printed NOTE for one day, on the grounds that
# the wiring belonged to another part; it is a hard leg now that the wiring
# exists, because a note nobody reads is how that spinner ships.
if ! grep -q 'ConnectHandoff.callbackHost' "$root"; then
    echo "AnticipyApp does not route ConnectHandoff.callbackHost."
    echo "Nothing hands $scheme://$host/{toolkit} to the handoff, so a connect"
    echo "that finishes in the system browser is dropped: the far end succeeds,"
    echo "the browser hands the URL to the app, and the app throws it away."
    exit 2
fi
if ! grep -q 'handleCallback' "$root"; then
    echo "AnticipyApp names the callback host but hands it to nothing."
    exit 2
fi
# The owner it hands over must be the ACCOUNT row id. `ownerID` is this
# device's pre-accounts UUID; binding a connection to it would bind one phone's
# connections to no account at all, which is the wrong-person failure by
# another road.
if grep -n 'handleCallback' "$root" | grep -q 'ownerID'; then
    echo "AnticipyApp hands the device UUID to the connect callback."
    echo "contract.ts: the user id is the owner ROW id, always, and never a"
    echo "name — and never this device's legacy identity either."
    exit 2
fi

# ---------------------------------- every refusal cause is actually counted
# ConnectRefusal carries no associated values on purpose, so its census is the
# compiler's (`allCases`) rather than a list somebody types — the failure mode
# CalendarHandPolicy hit, where three causes were missing from a hand-written
# census and two of them could silently share one code. What still needs a
# human is the literal the suite asserts, so it is compared here.
declared=$(awk '/^enum ConnectRefusal/{e=1} e && /^[[:space:]]*case [a-z]/{n++}
                e && /^\}/{exit} END{print n+0}' "$policy")
asserted=$(grep -E '^[[:space:]]*let REFUSAL_CODES = [0-9]+' "$suite" \
    | grep -oE '[0-9]+' | head -1)
if [ -z "$asserted" ] || [ "$declared" -ne "$asserted" ]; then
    echo "The refusal census does not match the enum."
    echo "  ConnectRefusal declares : ${declared} causes"
    echo "  the suite asserts       : ${asserted:-none}"
    echo "Add the case, then update REFUSAL_CODES in ConnectHandoffTests.swift."
    exit 2
fi

# ----------------------------------------- the clock agrees with the server
# LINK_TTL_MS in the server contract is what actually kills the link. If this
# app believes an attempt can still be alive after the server has expired it,
# it will accept a callback the server would not have produced. A missing
# contract is a NOTE, not a failure: a gate that goes red over a file in
# another tree is a gate somebody turns off.
contract="$repo/spike/two-hands/src/connections/contract.ts"
if [ -f "$contract" ]; then
    # Both sides are multiplied out rather than string-compared, so `600` and
    # `10 * 60` agree and nobody has to spell a constant a particular way to
    # keep a gate green — a leg that goes red on somebody's arithmetic is a leg
    # people learn to edit.
    product() {
        awk -v s="$1" 'BEGIN {
            p = 1; n = 0
            sub(/^[^=]*=/, "", s)
            while (match(s, /[0-9]+/)) {
                p *= substr(s, RSTART, RLENGTH); n++
                s = substr(s, RSTART + RLENGTH)
            }
            print (n ? p : "")
        }'
    }
    ttl_ms=$(product "$(grep 'LINK_TTL_MS' "$contract" | head -1)")
    ours_s=$(product "$(grep 'attemptLifetime: TimeInterval' "$policy" | head -1)")
    if [ -n "$ttl_ms" ] && [ -n "$ours_s" ] && [ "$ttl_ms" -ne $((ours_s * 1000)) ]; then
        echo "The attempt's lifetime disagrees with the server's link TTL."
        echo "  contract.ts LINK_TTL_MS : ${ttl_ms}ms"
        echo "  ConnectHandoff believes : $((ours_s * 1000))ms"
        echo ""
        echo "A phone that thinks an attempt is still alive after the server has"
        echo "expired the link will accept a callback the server could not have"
        echo "produced. The contract owns this number; this app agrees with it."
        exit 2
    fi
else
    echo "note: $contract is not in this tree, so the ten-minute link could not"
    echo "      be checked against the server contract."
fi

echo "the handoff is pure, prose-free and owner-agnostic; the presenter imports"
echo "only what opens a real browser; the gate has one private holder; the link"
echo "allowlist is one host and the callback scheme is registered AND routed"

# ------------------------------------------------- the half a Mac cannot run
# The suite below compiles both files for THIS machine, where UIKit does not
# exist — so the block that actually presents `ASWebAuthenticationSession` and
# opens Safari is compiled by nothing. A platform block nothing compiles is a
# platform block nobody has read, and it is the compliance-critical half. This
# typechecks it against the real iOS SDK.
#
# A missing SDK is a NOTE and not a failure: this leg is about the code, and a
# gate that goes red because somebody has no Xcode is a gate they turn off.
sdk=$(xcrun --sdk iphoneos --show-sdk-path 2>/dev/null || true)
if [ -n "$sdk" ] && [ -d "$sdk" ]; then
    if ! swiftc -typecheck -target arm64-apple-ios16.0 -sdk "$sdk" \
        "$policy" "$presenter" 2>"$out/ios.log"; then
        echo "The iOS half of ConnectSession does not compile:"
        cat "$out/ios.log"
        exit 2
    fi
    echo "and the phone-only half typechecks against $(basename "$sdk")"
else
    echo "note: no iOS SDK on this machine, so the ASWebAuthenticationSession"
    echo "      and Safari half of ConnectSession was NOT compiled by anything."
fi

# The suite is async-shaped and @MainActor, so it is a @main entry compiled with
# -parse-as-library — the same shape run_connected_apps_tests.sh uses. It is
# handed the app's source ROOT: its first leg reads every file under it that can
# open a URL and fails if an embedded web view is named in any of them.
swiftc -O -parse-as-library "$policy" "$presenter" "$suite" -o "$out/connecthandofftests"
"$out/connecthandofftests" "$app"
