#!/bin/sh
# SETTINGS → CONNECTED APPS, ON THE WIRE — and the connect that starts from it.
#
#   sh app/ios/Tests/run_connected_apps_client_tests.sh
#
# Spec: "Connections: how Anticipy asks, learns, and never says Composio",
# 2026-09-05, page 26. Contract: spike/two-hands/src/connections/contract.ts,
# mirrored in Swift by ConnectionsPolicy.swift.
#
# WHAT THIS IS FOR. Until 2026-09-05 the Connected apps screen was built with
# `UnreachableConnectedAppsStore`, whose every method threw, and the Connect
# button on a catalog result was an `assertionFailure`. The screen, its model
# and its whole suite were green over a dead end: nothing in the app could read
# an owner's connections, and nothing in the app could start a connection.
# `ConnectedAppsClient` is the half that reaches the server; this gate is what
# says it is WIRED rather than merely written.
#
# Two instruments, as next door.
#
#   The swiftc suite proves the DECISIONS — whose call it is, what goes on the
#   wire, what a refusal means, which sentences may be shown, which links may
#   be opened, and the whole screen driven through the real client. It compiles
#   the shipping sources, so there is no copy of anything to drift.
#
#   The scans prove the SHAPE — that the client names no app and no host, that
#   no route carries an owner, that the screen is built with the real client
#   rather than the refusing one, that the connect button is no longer an
#   assertion, and that the one producer of the callback `state` has a caller.
#
# Exit code is the result. Non-zero means the screen is a dead end again, or a
# call could reach the server on the wrong person's behalf.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
client="$app/Backend/ConnectedAppsClient.swift"
model="$app/Backend/ConnectedAppsModel.swift"
policy="$app/Backend/ConnectionsPolicy.swift"
handoff="$app/Backend/ConnectHandoff.swift"
duration="$app/Audio/PlainDuration.swift"
home="$app/Views/SettingsHomeView.swift"
suite="$here/ConnectedAppsClientTests.swift"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

for f in "$client" "$model" "$policy" "$handoff" "$duration" "$home" "$suite"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

# PROSE IS NOT CODE. The files explain at length the things they refuse, so
# whole-line comments come out before every scan.
strip() { grep -vE '^[[:space:]]*(//|///)' "$1"; }

# ---------------------------------------------------------- the client is pure
# Everything the client decides — whose call this is, what shape an answer must
# have, which link may be opened — has to be answerable on a laptop. Foundation
# is the only import it may have: the one piece that touches the world is behind
# `ConnectedAppsTransport`, and a UI framework in here is a decision that can no
# longer be run at the instant that matters.
imports=$(grep -E '^[[:space:]]*import[[:space:]]' "$client" \
    | sed -E 's/^[[:space:]]*import[[:space:]]+//' | sort -u | tr '\n' ' ')
if [ "$imports" != "Foundation " ]; then
    echo "ConnectedAppsClient imports more than Foundation: ${imports:-nothing}"
    echo "The network is behind ConnectedAppsTransport for exactly this reason."
    exit 2
fi

# ------------------------------------------------------- NO APP IS HARDCODED
# The product rule, verbatim from the spec: "A new app in the catalog is a new
# app in Anticipy with zero code." The same smoke-alarm list the model's runner
# uses — names no honest sentence in this file needs.
names='gmail|googlecalendar|google|notion|slack|outlook|dropbox|github|gitlab|jira|asana|trello|hubspot|salesforce|zoom|spotify|airtable|calendly|shopify|stripe|whatsapp|discord|figma|zendesk|intercom|mailchimp|quickbooks|todoist|evernote|onedrive|sharepoint|telegram|instagram|linkedin|youtube|wordpress|webflow|clickup|confluence|bitbucket|sendgrid|twilio|zapier|docusign'
hit=$(grep -inE "(^|[^a-zA-Z])($names)([^a-zA-Z]|$)" "$client" || true)
if [ -n "$hit" ]; then
    echo "An app is named in ConnectedAppsClient.swift:"
    echo "$hit"
    echo ""
    echo "Names, logos and descriptions arrive from the catalog at run time."
    exit 2
fi

# -------------------------------------------------------------- NO HOST HERE
# The base URL is INJECTED, from `session.backend`, which is this app's one
# place for "which server". A host written into this file is a host nobody can
# point at a preview or a local server, and — worse — a second answer to the
# question `ConnectHandoff.connectLinkHosts` already answers with an allowlist.
hosts=$(strip "$client" | grep -oE '"[^"]*"' | grep -E '://|\.(ai|com|dev|net|org)' || true)
if [ -n "$hosts" ]; then
    echo "ConnectedAppsClient carries a host or a URL literal:"
    echo "$hosts"
    echo ""
    echo "The base URL is injected. The one allowlist of hosts our links may"
    echo "live on is ConnectHandoff.connectLinkHosts, and a second one here is"
    echo "a second list to widen."
    exit 2
fi

# ------------------------------------------------- nobody's tokens but yours
# contract.ts: "A constant here would mean one person's tokens serving
# everybody, which is the worst failure this system can have." An owner row id
# is fifteen lowercase alphanumerics, so a literal of that shape is that failure
# written down.
if strip "$client" | grep -oE '"[a-z0-9]{15}"' | grep -q '[0-9]'; then
    echo "ConnectedAppsClient carries a literal shaped like an owner row id:"
    strip "$client" | grep -oE '"[a-z0-9]{15}"' | grep '[0-9]'
    echo "The owner is an argument, compared against the signed-in session,"
    echo "never a constant."
    exit 2
fi

# -------------------------------------------- NO OWNER TRAVELS ON THE WIRE
# Every route is under `me/`, so the server derives the owner from the session
# token exactly as `me/profile/upsert` and `me/phone/remove` already do. A route
# that took an owner would be a route somebody could point at another account,
# and the suite's transport-recorder legs would then be checking the wrong
# thing. The census is here because it is about the DECLARATION: a path typed at
# a call site is a path no list can find.
routes=$(awk '/^    enum Route \{/,/^    \}$/' "$client")
[ -n "$routes" ] || { echo "this gate can no longer find ConnectedAppsClient.Route"; exit 2; }
paths=$(printf '%s\n' "$routes" | grep -oE '"[^"]+"' | tr -d '"')
[ -n "$paths" ] || { echo "ConnectedAppsClient.Route declares no paths"; exit 2; }
for path in $paths; do
    case "$path" in
        me/*) ;;
        *)
            echo "A connections route is not under me/: $path"
            echo "The owner is derived from the session token, never named in a"
            echo "path, a query string or a body. contract.ts, OwnerId."
            exit 2
            ;;
    esac
done
census=$(printf '%s\n' "$routes" | sed -n '/static var every/,$p')
[ -n "$census" ] || { echo "this gate can no longer find Route.every"; exit 2; }
missing=""
for name in $(printf '%s\n' "$routes" | grep -oE 'static let [A-Za-z]+' | awk '{print $3}'); do
    printf '%s\n' "$census" | grep -qw "$name" || missing="$missing $name"
done
if [ -n "$missing" ]; then
    echo "Route.every does not cover:$missing"
    echo "The suite asserts every route is under me/ by reading that list. A"
    echo "route outside it is a route nothing checks."
    exit 2
fi

# Anything that looks like a call site building its own path.
strays=$(strip "$client" | grep -nE '"me/[^"]*"' | grep -v 'static let' || true)
if [ -n "$strays" ]; then
    echo "A route is written outside ConnectedAppsClient.Route:"
    echo "$strays"
    exit 2
fi

# ------------------------------------------------------------- THE COPY RULE
# The register the spec fixes: never "authorize", "grant access", "permissions",
# "integration", "API", "OAuth" — and never the vendor's name. The list is READ
# OUT OF ConnectionsPolicy rather than typed again, and it is scanned over
# STRING LITERALS so both files can go on explaining in prose exactly which
# words they refuse and why.
#
# SENTENCES ONLY, and the test for one is the same as the view leg's next door:
# two runs of letters with a space between them. This file is the one place in
# the feature that holds WIRE VOCABULARY as well as copy — an `Authorization`
# header, a `connected_account_id` column — and those are not words anybody
# reads. The authoritative check on this file's own copy is not this scan at
# all: the suite puts `ConnectStartCopy.everySentence` through the real
# `ConnectionsPolicy.firstForbidden` at run time, where nothing can be fooled by
# how a string is spelled.
terms=$(awk '/static let forbiddenTerms: \[String\] = \[/,/^    \]$/' "$policy" \
    | grep -oE '"[^"]+"' | tr -d '"')
[ -n "$terms" ] || { echo "this gate can no longer read ConnectionsPolicy.forbiddenTerms"; exit 2; }
for f in "$client" "$home"; do
    literals=$(strip "$f" | grep -oE '"[^"]*"' \
        | grep -E '"[^"]*[A-Za-z]{2,}[^"]* [A-Za-z]{2,}' || true)
    [ -n "$literals" ] || continue
    printf '%s\n' "$terms" | while IFS= read -r term; do
        [ -n "$term" ] || continue
        bad=$(printf '%s\n' "$literals" \
            | grep -inE "(^|[^a-z0-9])$term([^a-z0-9]|$)" || true)
        if [ -n "$bad" ]; then
            echo "A literal in $(basename "$f") uses \"$term\", which the register forbids:"
            echo "$bad"
            exit 2
        fi
    done || exit 2
done

# ------------------------------------------ the connect flow's copy is censused
# Two sentences, and they are the only ones this flow adds. `everySentence` is
# what the suite puts through the register gate, and a list somebody types goes
# stale in silence.
copy=$(awk '/^enum ConnectStartCopy \{/,/^\}$/' "$client")
[ -n "$copy" ] || { echo "this gate can no longer find ConnectStartCopy"; exit 2; }
saidcensus=$(printf '%s\n' "$copy" | sed -n '/static var everySentence/,$p')
[ -n "$saidcensus" ] || { echo "this gate can no longer find ConnectStartCopy.everySentence"; exit 2; }
missing=""
for name in $(printf '%s\n' "$copy" | grep -oE 'static (let|func) [A-Za-z]+' \
              | awk '{print $3}' | grep -v '^everySentence$'); do
    printf '%s\n' "$saidcensus" | grep -qw "$name" || missing="$missing $name"
done
if [ -n "$missing" ]; then
    echo "ConnectStartCopy.everySentence does not cover:$missing"
    exit 2
fi

# -------------------------------------------------- THE SCREEN IS REACHABLE
# The whole point. A screen built over a store that throws is a screen that can
# only ever say "I could not read your connected apps", and a Connect button
# that asserts is a button that does nothing at all.
if ! strip "$home" | grep -q 'ConnectedAppsClient('; then
    echo "SettingsHomeView does not build the Connected apps screen with the"
    echo "real client. Over UnreachableConnectedAppsStore the screen can only"
    echo "say it could not read anything, forever."
    exit 2
fi
if strip "$home" | grep -q 'UnreachableConnectedAppsStore('; then
    echo "SettingsHomeView still constructs UnreachableConnectedAppsStore."
    echo "That type exists for the model's suite, which pins it to the"
    echo "'.trouble' side of \"empty is not broken\". Nothing that ships is"
    echo "built with it."
    exit 2
fi
if strip "$home" | grep -q 'assertionFailure'; then
    echo "SettingsHomeView still asserts instead of starting a connect."
    echo "The Connect button on a catalog result is the beginning of the only"
    echo "flow where somebody hands over a key. It runs, or the feature does"
    echo "not exist."
    exit 2
fi
for wiring in 'connect.begin(' 'connect.adopt(' 'connect.ownerTapped(' \
              'ConnectedAppsCredential('; do
    if ! strip "$home" | grep -qF "$wiring"; then
        echo "The connect flow is not wired end to end: missing \"$wiring\""
        echo "begin puts the disclosure up, adopt binds our single-use link to"
        echo "the attempt, and ownerTapped is the only call in the app that"
        echo "opens one. A missing step is a sheet with a dead button."
        exit 2
    fi
done
# The owner it starts a connect for is the ACCOUNT row id. `session.ownerID` is
# this device's pre-accounts UUID; a connection bound to that is bound to a
# handset rather than to a person.
if strip "$home" | grep -q 'session\.ownerID'; then
    echo "SettingsHomeView reads session.ownerID."
    echo "Connections bind to the owner ROW id — contract.ts, OwnerId."
    exit 2
fi

# ------------------------------------- THE STATE HAS A PRODUCER AND A CALLER
# `ConnectHandoff.callbackURL(for:)` is the only code that produces the `state`
# the whole callback binding rests on, and until 2026-09-05 it had NO PRODUCTION
# CALLER: the value went out on nothing, so `parseDone`'s state check could only
# ever refuse. `stateToken` reads it back out of that callback — one producer —
# and `outboundLink` puts it on the link the attempt adopts.
if ! grep -q 'callbackURL(for: attempt)' "$handoff"; then
    echo "ConnectHandoff.stateToken no longer reads the state out of the"
    echo "callback it will accept. Two producers of one value is how the half"
    echo "we send and the half we demand come to disagree."
    exit 2
fi
if ! strip "$client" | grep -q 'ConnectHandoff.outboundLink'; then
    echo "The client hands back a link with no state on it."
    echo "anticipy://connected/{toolkit} is openable by any web page, any other"
    echo "app or a QR code on a poster, and every other check on it is"
    echo "satisfied for free by a stranger's URL while a connect is in flight."
    exit 2
fi

echo "the client is pure, names no app and no host, keeps every route under me/"
echo "and censused, passes the register gate, is what the screen is actually"
echo "built with, starts a real connect rather than asserting, and stamps the"
echo "one state the callback binding rests on"

# ------------------------------------------------- the half a Mac cannot run
# The suite below compiles the client, the model and the policy — the decisions.
# The WIRING is in `SettingsHomeView`, which is SwiftUI and is compiled by
# nothing on this machine: the scans above can see that `connect.begin(` appears
# in it and cannot see whether the file builds. A view that does not compile is
# a screen that does not exist, and the last two gates on this feature were both
# green over exactly that.
#
# So the whole app source is typechecked against the real iOS SDK, with DEBUG
# defined so the previews are read too. A missing SDK is a NOTE and not a
# failure: a gate that goes red because somebody has no Xcode is a gate they
# turn off.
sdk=$(xcrun --sdk iphoneos --show-sdk-path 2>/dev/null || true)
if [ -n "$sdk" ] && [ -d "$sdk" ]; then
    header="$app/Anticipy-Bridging-Header.h"
    if [ -f "$header" ]; then
        set -- -import-objc-header "$header"
    else
        set --
    fi
    # shellcheck disable=SC2046
    if ! swiftc -typecheck -D DEBUG -target arm64-apple-ios16.0 -sdk "$sdk" "$@" \
         $(find "$app" -name '*.swift') 2>"$out/ios.log"; then
        echo "The app does not typecheck against the iOS SDK:"
        grep -E 'error:' "$out/ios.log" | head -20
        exit 2
    fi
    echo "and the whole app typechecks against $(basename "$sdk"), previews included"
else
    echo "note: no iOS SDK on this machine, so SettingsHomeView — where the"
    echo "      connect flow is actually wired — was NOT compiled by anything."
fi

# swiftc only permits top-level code in a file literally named main.swift, and
# this suite is async, so it is a @main entry compiled with -parse-as-library —
# the same shape run_connected_apps_tests.sh uses.
swiftc -O -parse-as-library "$policy" "$handoff" "$model" "$client" "$duration" "$suite" \
    -o "$out/connectedappsclienttests"
"$out/connectedappsclienttests"
