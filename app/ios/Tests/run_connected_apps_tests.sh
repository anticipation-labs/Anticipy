#!/bin/sh
# SETTINGS → CONNECTED APPS: whose apps these are, what the switch means, and
# what the screen is allowed to say.
#
#   sh app/ios/Tests/run_connected_apps_tests.sh
#
# Spec: "Connections: how Anticipy asks, learns, and never says Composio",
# 2026-09-05, page 26. Contract: spike/two-hands/src/connections/contract.ts,
# mirrored in Swift by ConnectionsPolicy.swift — which is where the owner id,
# the statuses, the disconnect sentence and the forbidden register live. This
# screen consumes that; it does not restate it.
#
# Two instruments, because this screen can fail in two different ways.
#
#   The swiftc suite proves the DECISIONS — owner scoping across a sign-in and
#   a response that lands after one, the optimistic switch that reverts, the
#   disconnect that reports what actually happened, the search that judges
#   nothing. It compiles the real production sources, so there is no copy of
#   either to drift.
#
#   The scans prove the SHAPE — that no app is named in the shipped source,
#   that no sentence lives in the view where nothing can test it, that the
#   owner comes from the account row id and never from the legacy device UUID,
#   that the contract's vocabulary is used rather than re-declared, and that no
#   sentence uses a word the register list forbids.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
model="$app/Backend/ConnectedAppsModel.swift"
view="$app/Views/SettingsConnectedAppsView.swift"
home="$app/Views/SettingsHomeView.swift"
policy="$app/Backend/ConnectionsPolicy.swift"
duration="$app/Audio/PlainDuration.swift"
suite="$here/ConnectedAppsModelTests.swift"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

for f in "$model" "$view" "$home" "$policy" "$duration" "$suite"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

# PROSE IS NOT CODE. Both files explain at length the things they refuse, so
# whole-line comments come out before every scan — the same way the duration,
# control-policy and theme-contract runners do it.
strip() { grep -vE '^[[:space:]]*(//|///)' "$1"; }

# --------------------------------------------------------- the model is pure
# The whole point of the model is that "what will this screen do" is answerable
# with no phone, no account and no network. A SwiftUI or UIKit import means the
# decisions have been folded back into the thing they exist to be testable
# without.
if strip "$model" | grep -qE '^[[:space:]]*import[[:space:]]+(SwiftUI|UIKit)'; then
    echo "ConnectedAppsModel imports SwiftUI or UIKit."
    echo "The decisions are supposed to sit IN FRONT of the view so they can be"
    echo "run on a laptop. A model that needs a screen to answer is a model"
    echo "nobody can test at the instant that matters."
    exit 2
fi

# ------------------------------------------- ONE VOCABULARY, NOT TWO
# ConnectionsPolicy is the Swift mirror of contract.ts, and its own runner
# reads the TypeScript to prove it still matches. A second OwnerId, a second
# Connection or a second disconnect sentence declared HERE would not fail to
# compile and would not fail that runner: it would simply drift, and the two
# halves of the same feature would disagree about who somebody is.
for type in 'struct OwnerId' 'struct Connection' 'struct ToolkitMeta' \
            'struct DisconnectResult' 'enum ConnectionStatus' 'enum AccountAlias' \
            'enum NudgeState'; do
    if strip "$model" | grep -q "$type"; then
        echo "ConnectedAppsModel re-declares the contract's own type: $type"
        echo "It belongs to ConnectionsPolicy, whose runner compares it against"
        echo "spike/two-hands/src/connections/contract.ts at run time. A copy"
        echo "here is a second book that nothing keeps in step."
        exit 2
    fi
done
for call in 'ConnectionsPolicy.settingsCards' 'ConnectionsPolicy.writesTransition' \
            'ConnectionsPolicy.disconnectConfirmation' 'ConnectionsPolicy.statusLine' \
            'ConnectionsPolicy.connectedRows' 'OwnerScoped.rows' \
            'ConnectionsPolicy.writesEnabled'; do
    if ! strip "$model" | grep -q "$call"; then
        echo "ConnectedAppsModel no longer goes through the contract: missing $call"
        echo "Every one of these is a decision the contract already owns — the"
        echo "cards, the per-app toggle, the sentence that decides whether"
        echo "\"revoked\" is true, the status wording, and the owner filter."
        exit 2
    fi
done

# ------------------------------------------------------- NO APP IS HARDCODED
# The product rule, verbatim from the spec: "A new app in the catalog is a new
# app in Anticipy with zero code. If you write a Swift enum or array of app
# names, you have built the wrong thing."
#
# This list is a SMOKE ALARM, not the rule — it is deliberately made of names
# no honest sentence in these two files needs, and it stays out of ambiguous
# ones ("box", "drive", "calendar") that the device connectors legitimately
# talk about next door. The rule itself is architectural: names arrive through
# ConnectedAppsStore at run time.
names='gmail|googlecalendar|google|notion|slack|outlook|dropbox|github|gitlab|jira|asana|trello|hubspot|salesforce|zoom|spotify|airtable|calendly|shopify|stripe|whatsapp|discord|figma|zendesk|intercom|mailchimp|quickbooks|todoist|evernote|onedrive|sharepoint|telegram|instagram|linkedin|youtube|wordpress|webflow|clickup|confluence|bitbucket|sendgrid|twilio|zapier|docusign'
for f in "$model" "$view"; do
    hit=$(grep -inE "(^|[^a-zA-Z])($names)([^a-zA-Z]|$)" "$f" || true)
    if [ -n "$hit" ]; then
        echo "An app is named in $(basename "$f"):"
        echo "$hit"
        echo ""
        echo "Names, logos and descriptions come from the catalog at run time."
        echo "A name in this source is a second book to keep in step with 1,400"
        echo "apps, and it is the difference between a product that gains an app"
        echo "when the catalog does and one that gains an app when somebody"
        echo "ships a build."
        exit 2
    fi
done

# ----------------------------------------------------------- THE COPY RULE
# The register the spec fixes: never "authorize", "grant access",
# "permissions", "integration", "API", "OAuth" — and never the vendor's name.
# It is "connect your things", in the words a person uses themselves.
#
# The list is READ OUT OF ConnectionsPolicy rather than typed again here, for
# the same reason the model consumes it: two lists is one list nobody updates.
# Scanned as STRING LITERALS rather than as source text, so both files can go
# on explaining in their comments exactly which words they refuse and why.
terms=$(awk '/static let forbiddenTerms: \[String\] = \[/,/^    \]$/' "$policy" \
    | grep -oE '"[^"]+"' | tr -d '"')
[ -n "$terms" ] || { echo "this gate can no longer read ConnectionsPolicy.forbiddenTerms"; exit 2; }
for f in "$model" "$view"; do
    literals=$(strip "$f" | grep -oE '"[^"]*"' || true)
    [ -n "$literals" ] || continue
    printf '%s\n' "$terms" | while IFS= read -r term; do
        [ -n "$term" ] || continue
        bad=$(printf '%s\n' "$literals" \
            | grep -inE "(^|[^a-z0-9])$term([^a-z0-9]|$)" || true)
        if [ -n "$bad" ]; then
            echo "A sentence in $(basename "$f") uses \"$term\", which the register forbids:"
            echo "$bad"
            echo ""
            echo "The person never hears the vendor's name and never reads the"
            echo "vocabulary of a consent screen. It is \"connect your things\"."
            exit 2
        fi
    done || exit 2
done

# ------------------------------------------- the view writes no sentences
# Copy is a DECISION, and decisions live where they can be tested. Every
# sentence on this screen comes from ConnectedAppsModel.Copy or from
# ConnectionsPolicy, both of which the suite reads in one census; a sentence
# typed into the view is a sentence the register leg above cannot see change.
#
# "Two words in one literal" is the test, because that is what a sentence is
# and it is not what an SF Symbol name or a separator is.
sentences=$(strip "$view" | grep -oE '"[^"]*"' \
    | grep -E '"[^"]*[A-Za-z]{2,}[^"]* [A-Za-z]{2,}' || true)
if [ -n "$sentences" ]; then
    echo "SettingsConnectedAppsView is writing its own copy:"
    echo "$sentences"
    echo ""
    echo "Every sentence belongs in ConnectedAppsModel.Copy, where the suite"
    echo "checks all of them at once against the words the register forbids."
    exit 2
fi
if ! grep -q 'ConnectedAppsModel.Copy' "$view"; then
    echo "The view no longer reads its copy from the model."
    exit 2
fi

# ------------------------------------------------------ THE WRONG-PERSON LEG
# The failure this whole feature is shaped around: during the spike one
# operator's own mailbox was connected by hand, and it had to be revoked and
# deleted. Every connection belongs to the owner signed into THIS phone.
#
# `session.ownerID` is NOT that owner: it is a UUID this app mints for its
# pre-accounts identity (AnticipyApp.swift, `if ownerID.isEmpty { ownerID =
# UUID().uuidString }`). The account row id is `session.accountID`, and
# contract.ts's OwnerId is exactly that id. A screen reading the other one
# would bind a person's apps to a handset.
if strip "$view" | grep -q 'session\.ownerID'; then
    echo "The view reads session.ownerID."
    echo "That is the legacy pre-accounts device UUID, not the account row id."
    echo "Connections bind to the owner ROW id — contract.ts, OwnerId."
    exit 2
fi
if ! strip "$view" | grep -q 'OwnerId(session.accountID)'; then
    echo "The view no longer derives its owner from the signed-in account."
    exit 2
fi
mints=$(strip "$view" | grep -c 'OwnerId(' || true)
if [ "$mints" -ne 1 ]; then
    echo "The view mints an owner id in $mints places; there is exactly one."
    echo "A second one is a second answer to \"whose apps are these\", and the"
    echo "spike proved what happens when that question has two answers."
    exit 2
fi

# ------------------------------------------------ every sentence is censused
# `Copy.everySentence` is the only list of this screen's own wording there is,
# and a list somebody types goes stale in silence — the exact failure the
# calendar runner's refusal census was built for, where three added causes sat
# outside the list and nothing went red. So the census is checked HERE, against
# the declarations themselves: a sentence added to Copy and forgotten in
# everySentence is a sentence the register leg never reads.
copy=$(awk '/^    enum Copy \{/,/^    \}$/' "$model")
[ -n "$copy" ] || { echo "this gate can no longer find ConnectedAppsModel.Copy"; exit 2; }
census=$(printf '%s\n' "$copy" | sed -n '/static func everySentence/,$p')
[ -n "$census" ] || { echo "this gate can no longer find Copy.everySentence"; exit 2; }
missing=""
for name in $(printf '%s\n' "$copy" | grep -oE 'static (let|func) [A-Za-z]+' \
              | awk '{print $3}' | grep -v '^everySentence$'); do
    printf '%s\n' "$census" | grep -qw "$name" || missing="$missing $name"
done
if [ -n "$missing" ]; then
    echo "Copy.everySentence does not cover:$missing"
    echo ""
    echo "Every sentence the screen writes has to be in the census, or the"
    echo "suite's register leg is checking a subset and reporting it as the"
    echo "whole. Add it to everySentence in the same diff."
    exit 2
fi

# ------------------------------------------------ ONE PREDICATE FOR THE WRITE
# The screen's switch and the router's permission are the SAME question, and on
# 2026-09-05 they were two: `settingsCards` folds the opt-in over every row that
# is not `disconnected`, `mayUse(..., .write, ...)` folds it over `connected`
# rows only. They disagreed in BOTH directions, and the permissive one drew a
# switch reading ON — and the sentence "I can also send, create and change
# things in it" — over an app whose only account needed signing in again, where
# every write would have been refused.
#
# The suite compares the two answers across every shape two accounts can be in.
# This leg is the structural half: the row may not be built from the card's own
# field, which is the field that was wrong.
if strip "$model" | grep -qE 'writesEnabled:[[:space:]]*card\.writesEnabled'; then
    echo "The row's switch is built from ConnectionCard.writesEnabled again."
    echo "That field folds the opt-in over rows that are merely NOT disconnected;"
    echo "a write is licensed by ConnectionsPolicy.mayUse, which folds over"
    echo "CONNECTED rows only. Ask the question of the thing that answers it."
    exit 2
fi

# ------------------------------------- THE CATALOG'S OWN WORDS GO THROUGH TOO
# `ToolkitMeta.description` is written by a vendor, arrives at run time from
# 1,400 catalog rows nobody here has read, and was rendered verbatim as the
# subtitle of every "Add an app" result — which is also the VoiceOver hint on
# the button that starts a connect. It is not in `Copy.everySentence`, so the
# register leg above never read one: a blurb saying "integration" or "API", or
# naming the provider, went straight onto the screen. The model now withholds
# such a sentence (`shownDescription`); this leg is what stops the view from
# going around it again.
if strip "$view" | grep -qE 'meta\.description'; then
    echo "The view renders the catalog's own description directly:"
    strip "$view" | grep -nE 'meta\.description'
    echo ""
    echo "Every user-visible string goes through the register gate. The model"
    echo "hands back ConnectedAppsModel.Found.subtitle, which is that sentence"
    echo "only when it is one this product is allowed to say."
    exit 2
fi
if ! strip "$model" | grep -q 'ConnectionsPolicy.saysNothingForbidden'; then
    echo "The model no longer puts the catalog's own sentence through the gate."
    exit 2
fi

# ------------------------------------ A QUESTION BELONGS TO THE ACCOUNT ASKED
# The view keeps its OWN copy of the disconnect question, and it has to: iOS
# dismisses an alert as its button fires, so an `isPresented` bound to the
# model's state cleared the question before the confirm action ran and the
# destructive button disconnected nothing. A copy is also where a previous
# account's app name can survive a sign-out — "Disconnect <app>?" sitting on a
# phone that has just changed hands. So the copy goes back through the model,
# with whoever is signed in now, and it is dropped at the account boundary.
if ! strip "$view" | grep -q 'model.questionStillStands'; then
    echo "The held disconnect question is drawn without asking the model whose"
    echo "it is. Only the model knows the account signed in right now, and the"
    echo "question carries the owner it was posed for."
    exit 2
fi
if ! strip "$view" | grep -qE 'task\(id: session.accountID\)'; then
    echo "The screen no longer reacts to the account changing."
    exit 2
fi
if ! awk '/task\(id: session.accountID\)/,/^        \}$/' "$view" \
     | grep -q 'confirming = nil'; then
    echo "The account boundary does not drop the held question."
    echo "The model clears its own state on signIn/signOut; the view's copy of"
    echo "the question is not the model's to clear, so it is cleared here."
    exit 2
fi

# ------------------------------------------------------- THE SCREEN IS REACHED
# This screen, its model and its whole suite existed for a day with NOTHING in
# the app navigating to them — a finished feature no person could get to, which
# is worth exactly as much as an unfinished one. Settings' index is the door.
#
# And it is a SECOND door, not a rename of the first: "Connectors" next to it is
# this iPhone's own calendar, contacts and mail plus the browser, the Mac and
# the pendant. Merging them would put "turn on calendar access on this phone"
# beside "let Anticipy make changes in an account of yours". Both rows are
# required here so neither can quietly absorb the other.
if ! strip "$home" | grep -q 'SettingsConnectedAppsView('; then
    echo "Nothing in SettingsHomeView opens SettingsConnectedAppsView."
    echo "A screen nothing navigates to is not shipped, however green its suite."
    exit 2
fi
if ! awk '/private enum Route: Hashable \{/,/^    \}$/' "$home" | grep -q 'connectedApps'; then
    echo "SettingsHomeView's Route enum has no connectedApps case."
    echo "The index navigates by that enum; a destination it cannot name is"
    echo "unreachable however it is written."
    exit 2
fi
for wiring in 'route = .connectedApps' 'case .connectedApps:'; do
    if ! strip "$home" | grep -qF "$wiring"; then
        echo "The Connected apps row is not wired end to end: missing \"$wiring\""
        echo "A route with no row, or a row with no destination, is a chevron"
        echo "that goes nowhere."
        exit 2
    fi
done
if ! strip "$home" | grep -q 'ConnectedAppsModel.Copy.title'; then
    echo "The Settings row names the screen in its own words."
    echo "The title is written once, in ConnectedAppsModel.Copy, so the row and"
    echo "the page it opens cannot come to disagree about what this is called."
    exit 2
fi
if ! strip "$home" | grep -q 'NavRow("Connectors"'; then
    echo "The Connectors row is gone from Settings."
    echo "This device's own calendar, contacts, mail, browser, Mac and pendant"
    echo "are NOT the owner's connected accounts. Both rows belong."
    exit 2
fi

echo "the model is pure, uses the contract rather than restating it, names no"
echo "app, writes no sentence in the view, takes its owner from the account row"
echo "id, censuses every sentence it does write, puts the catalog's own sentence"
echo "through the same gate, hands the held question back to the model, and is"
echo "reached from the Settings index alongside Connectors rather than instead"
echo "of it"

# swiftc only permits top-level code in a file literally named main.swift, and
# this suite is async, so it is a @main entry compiled with -parse-as-library —
# the same shape run_refresh_account_race_tests.sh uses.
swiftc -O -parse-as-library "$policy" "$model" "$duration" "$suite" \
    -o "$out/connectedappstests"
"$out/connectedappstests"
