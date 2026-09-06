#!/bin/sh
# THE SETUP STEP AS FIRST RUN ACTUALLY WALKS IT — "which apps do you live in?"
#
#   sh app/ios/Tests/run_connect_onboarding_step_tests.sh
#
# run_connect_onboarding_tests.sh next door runs the DECISION and the SCREEN.
# It passed 154 checks on 2026-09-05 over a screen with ZERO CALL SITES:
# `OnboardingConnectStep.swift` was written, compiled into the target and
# constructed by nothing, and `FirstRunBeat` was welcome/tour/name/computer/
# pendant/mic with no room for it. So the spec's STEP 2 (page 45) existed in the
# repository and did not exist for one single person, with a green gate over it.
#
# This runner is the leg that could not go green over that, and it has two
# halves:
#
#   THE SOURCE. Claims about the FLOW that no amount of passing behaviour can
#   make true — the step is constructed, exactly once, on the beat between the
#   pendant and the microphone; the list the body draws is the list `nextPage`
#   walks; Skip goes through the policy and never through `recordDecline`; the
#   handoff goes through the one object allowed to open a connect link; and no
#   app is named and no sentence is written where the register gate cannot read
#   it.
#
#   THE SUITE. ConnectOnboardingPolicyTests.swift, compiled against the real
#   ConnectOnboardingPolicy AND the real FirstRunRoute. They cannot import each
#   other — the route is compiled on its own by run_first_run_route_tests.sh —
#   so a suite that holds both at once is the only thing stopping the flow's
#   snooze and the policy's meaning of a snooze from drifting apart.
#
# Exit code is the result.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Backend/ConnectOnboardingPolicy.swift"
handoff="$app/Backend/ConnectHandoff.swift"
route="$app/FirstRunRoute.swift"
onboard="$app/Views/OnboardingView.swift"
view="$app/Views/OnboardingConnectStep.swift"
suite="$here/ConnectOnboardingPolicyTests.swift"
for f in "$policy" "$handoff" "$route" "$onboard" "$view" "$suite"; do
    [ -f "$f" ] || { echo "missing $f — these checks would read nothing"; exit 2; }
done

# Whole-line comments dropped before every source scan. These files explain at
# length the defects they closed, and an explanation must never be what
# satisfies a grep — that is a suite that goes green on prose.
code() { grep -vE '^[[:space:]]*//' "$1"; }
code "$onboard" > "$out/onboard.code.swift"

# The text of one Swift declaration, by counting braces. Same shape as
# run_first_run_route_tests.sh, and for the same reason: several checks below
# are about WHERE a line is, not whether it appears anywhere in a 1,500-line
# view.
span() {
    awk -v sig="$2" '
        !inside && $0 ~ sig { inside = 1 }
        inside {
            print
            opens = gsub(/{/, "{"); depth += opens
            closes = gsub(/}/, "}"); depth -= closes
            if (started && depth <= 0) exit
            if (depth > 0) started = 1
        }
    ' "$1"
}

# ------------------------------------------------------ 1. IT IS CONSTRUCTED
#
# THE WHOLE DEFECT, IN ONE GREP. A view nothing constructs is a view no person
# has. Counted across every shipped source rather than looked for in one, and
# required to be EXACTLY ONE: a second call site is a second copy of this step
# with its own idea of what Skip does, and a screen somebody meets twice.
sites=$(grep -rho 'OnboardingConnectStep(' "$app" | wc -l | tr -d ' ')
if [ "$sites" != "1" ]; then
    echo "OnboardingConnectStep is constructed $sites times in the app."
    echo ""
    echo "Zero is the defect this runner exists for: the file was written on"
    echo "2026-09-05, compiled into the target, tested with 154 checks, and"
    echo "called by nothing — so the Connections spec's step 2 existed in the"
    echo "repository and did not exist for any person."
    echo ""
    echo "More than one is the other failure: two call sites are two cards with"
    echo "two ideas of what a skip costs, and a beat somebody meets twice."
    exit 2
fi
if ! code "$onboard" | grep -q 'OnboardingConnectStep('; then
    echo "The one call site is not in OnboardingView.swift."
    echo "That is where the first-run beats are drawn; a step constructed"
    echo "anywhere else is not in the walkthrough, whatever else it is in."
    exit 2
fi

# --------------------------------------------------------- 2. ON WHICH BEAT
#
# The index, the page builder and the walk have to agree. `FirstRunBeat.connect`
# on its own is a number; `page(_:)` is what turns one into a screen and nothing
# else reads it.
if ! grep -q 'static let connect = ' "$route"; then
    echo "FirstRunBeat has no connect beat. The step cannot be a page without one."
    exit 2
fi
pagefn=$(span "$out/onboard.code.swift" 'func page[(]')
[ -n "$pagefn" ] || { echo "OnboardingView has no func page(_:) for this runner to read."; exit 2; }
if ! printf '%s\n' "$pagefn" | grep -qE 'case Step\.connect:[[:space:]]+connectStep$'; then
    echo "page(_:) does not draw connectStep on the connect beat."
    echo "The beat indices are what the walk carries; this switch is what turns"
    echo "one into a screen. A beat with no arm here is a blank page on"
    echo "somebody's first run, between the pendant and the microphone."
    exit 2
fi
arms=$(printf '%s\n' "$pagefn" | grep -c 'connectStep' || true)
if [ "$arms" != "1" ]; then
    echo "page(_:) mentions connectStep $arms times; it may appear on exactly one arm."
    exit 2
fi
# AND THE MICROPHONE STAYS LAST. `heard` pushes live before it queues, so the
# beat that asks iOS for the microphone may never be moved in front of anything.
# This step went in FRONT of it for the same reason the pendant beat did.
if ! grep -qE '^[[:space:]]*static let connect = 5$' "$route" \
    || ! grep -qE '^[[:space:]]*static let mic = 6$' "$route"; then
    echo "The setup step is no longer the beat directly in front of the microphone."
    echo "Read FirstRunRoute.swift's header: the mic beat is last because it is"
    echo "the one that asks iOS for the microphone, and a beat added after it"
    echo "would run a microphone while somebody was still being asked questions."
    exit 2
fi

# ------------------------------------------- 3. ONE LIST, DRAWN AND WALKED
#
# The beat is the one page of first run that is not always due, so there are two
# places that have to agree about which pages exist: the ForEach that DRAWS them
# and the `nextPage` that WALKS them. A `nextPage` reading the unfiltered list
# steps onto a page nothing renders — a blank screen, mid-setup, with no way
# forward, which is the dead end `segment.lastStep` was written for arriving
# from the other side.
lists=$(code "$onboard" | grep -c 'segment.pages(showingConnect:' || true)
if [ "$lists" -lt 2 ]; then
    echo "OnboardingView asks for the walked page list $lists time(s)."
    echo "Both the ForEach that draws the pages and nextPage() that walks them"
    echo "must ask the same question, or they disagree about which page follows"
    echo "the pendant and somebody lands on a page nothing renders."
    exit 2
fi
if ! code "$onboard" | grep -q 'ForEach(segment.pages(showingConnect:'; then
    echo "The body no longer draws the filtered page list."
    exit 2
fi
nextfn=$(span "$out/onboard.code.swift" 'var nextPage')
[ -n "$nextfn" ] || { echo "OnboardingView has no nextPage for this runner to read."; exit 2; }
if ! printf '%s\n' "$nextfn" | grep -q 'segment.pages(showingConnect:'; then
    echo "nextPage walks a different list from the one the body draws."
    exit 2
fi
# AND THE ANSWER IS FROZEN once the beat is reached. The connections list is
# read over the network; one adopted while somebody is standing on the page it
# removes is a blank screen under a thumb.
if ! code "$onboard" | grep -q 'ConnectBeat.mayAdoptAudience(standingOn:'; then
    echo "OnboardingView adopts a late connections answer without asking whether"
    echo "the person is already standing on the beat it would remove."
    exit 2
fi

# ------------------------------------------------------------ 4. WHAT SKIP IS
#
# A SEVEN-DAY SOFT SNOOZE, NOT A DECLINE — page 41. The two implementations of
# this same event disagree by design of nobody: `ConnectionsPolicy.recordDecline`
# stamps `declined` at level 1, and level 1 raises the server's own threshold to
# 0.8 against a strict comparison, which silences every trigger that carries
# evidence for good. The flow must reach the one that snoozes.
if ! code "$onboard" | grep -q 'ConnectOnboardingPolicy.skipOutcome('; then
    echo "OnboardingView's Skip does not go through ConnectOnboardingPolicy."
    echo "Whatever it does instead is a second answer to \"what does walking past"
    echo "this card cost\", written where the suite cannot run it. Page 41 says"
    echo "it is a seven-day soft snooze; skipOutcome is where that lives."
    exit 2
fi
if code "$onboard" | grep -q 'recordDecline'; then
    echo "OnboardingView records a DECLINE for a skipped setup card."
    echo "A form refused is not an app refused. recordDecline advances the"
    echo "ladder to level 1, which raises the server's threshold to 0.8 against"
    echo "a strict comparison and silences repeated_use, onboarding and in_task"
    echo "outright — a life sentence with a seven-day label."
    exit 2
fi
skipfn=$(span "$out/onboard.code.swift" 'func recordConnectSkip[(]')
[ -n "$skipfn" ] || { echo "OnboardingView has no recordConnectSkip() to read."; exit 2; }
if printf '%s\n' "$skipfn" | grep -qE '\b7\b|\* 7|days: 7'; then
    echo "The snooze length is written into OnboardingView."
    echo "It is the contract's ONBOARDING_SKIP_SNOOZE_DAYS, and it arrives in"
    echo "skipOutcome's answer. A number typed here is a second book, and the"
    echo "two books disagree the week somebody edits one."
    exit 2
fi
if ! printf '%s\n' "$skipfn" | grep -q 'outcome.snoozeDays'; then
    echo "recordConnectSkip does not store the number of days the policy returned."
    exit 2
fi
# AND SKIP IS UNCONDITIONAL FROM THE FLOW'S SIDE TOO. The card renders it
# without a branch (run_connect_onboarding_tests.sh leg 6 reads that); this is
# the other half — the closure behind it must not be the thing that is
# conditional, or the button is visible and inert.
skipstep=$(span "$out/onboard.code.swift" 'func skipConnectStep[(]')
[ -n "$skipstep" ] || { echo "OnboardingView has no skipConnectStep() to read."; exit 2; }
if ! printf '%s\n' "$skipstep" | grep -q 'await advance()'; then
    echo "Skip on the setup card does not move first run forward."
    echo "A person in setup has no account to go back to and nothing else on"
    echo "screen. A way out that records a snooze and leaves them standing there"
    echo "is worse than no way out, because it looks like one."
    exit 2
fi
if printf '%s\n' "$skipstep" | grep -qE '^[[:space:]]*(if|guard|switch) '; then
    echo "skipConnectStep branches before it moves on."
    echo "Page 41: Skip is always visible, and it is always a way out. A"
    echo "condition here is a state where the only control on the screen does"
    echo "nothing at all."
    exit 2
fi

# A CONNECT THAT ASKED FOR NOTHING MAY NOT READ AS ONE THAT WORKED. If the
# catalog can name none of the ticked apps, nothing has been asked for, and
# walking on to the microphone beat tells the person it went through.
startfn=$(span "$out/onboard.code.swift" 'func startConnecting[(]')
[ -n "$startfn" ] || { echo "OnboardingView has no startConnecting() to read."; exit 2; }
if ! printf '%s\n' "$startfn" | grep -q 'guard !queue.isEmpty'; then
    echo "Connect advances first run without checking that anything was queued."
    echo "A tap that asked for nothing and moved on reads as a tap that worked."
    exit 2
fi

# ---------------------------------------------------- 5. THE HANDOFF IS SHARED
#
# There is exactly one object in this app allowed to open a connect link, and it
# holds the allowlist. A second opener in onboarding is a second allowlist, and
# four provider links were sent for real during the spike.
for call in 'connect.begin(' 'connect.adopt(link:' 'connect.ownerTapped('; do
    if ! code "$onboard" | grep -qF "$call"; then
        echo "OnboardingView's connect handoff does not call $call"
        echo "ConnectSession is the only thing that may open one of these links."
        exit 2
    fi
done
if code "$onboard" | grep -qE 'UIApplication.shared.open|openURL\('; then
    echo "OnboardingView opens a URL itself."
    echo "Every connect link goes through ConnectSession, which owns the"
    echo "allowlist — https, our host, our path — and spends the consent as the"
    echo "browser opens."
    exit 2
fi

# ------------------------------------------ 6. NO APP NAMED, NO SENTENCE WRITTEN
#
# The two rules a screen quietly breaks. Names and logos come from the catalog
# at run time, and copy lives where the forbidden-word leg can read all of it at
# once — a sentence written in a view is a sentence nothing checks.
if grep -nEi '\b(gmail|googlecalendar|google|notion|slack|outlook|microsoft|dropbox|github|asana|jira|trello|hubspot|salesforce|zoom|linkedin|airtable|shopify|composio)\b' "$onboard"; then
    echo ""
    echo "A vendor or app name appears in OnboardingView."
    echo "A new app in the catalog is a new app in Anticipy with zero code, and"
    echo "that is only true while this file cannot name one. A name in a comment"
    echo "counts: it is where the next agent's branch on that name starts."
    exit 2
fi
# The step's own block, which is where a sentence would go if one were written.
# SF Symbol names are addresses rather than sentences and are the only literals
# permitted, exactly as run_connect_onboarding_tests.sh permits them on the view.
for decl in 'var connectStep' 'func connectSheet[(]' 'func skipConnectStep[(]' \
            'func recordConnectSkip[(]' 'func startConnecting[(]' \
            'var connectTroubleSheet'; do
    block=$(span "$out/onboard.code.swift" "$decl")
    [ -n "$block" ] || { echo "OnboardingView has no $decl for this runner to read."; exit 2; }
    stray=$(printf '%s\n' "$block" | grep -oE '"[^"]*"' | grep -vE '^"[a-z0-9.]+"$' || true)
    if [ -n "$stray" ]; then
        echo ""
        echo "A sentence is written in OnboardingView's $decl:"
        printf '%s\n' "$stray"
        echo "Every word this step shows comes from ConnectOnboardingPolicy.Copy"
        echo "or from ConnectedAppsModel.Copy, where the forbidden-word leg reads"
        echo "all of it at once. The owner never hears the provider's name."
        exit 2
    fi
done

echo "the step is constructed once, on the beat in front of the microphone;"
echo "one page list is drawn and walked; Skip snoozes through the policy and"
echo "never declines; the handoff is the shared one; no app is named"

# --------------------------------------------------------------- 7. THE SUITE
#
# swiftc only permits top-level code in a file literally named main.swift.
#
# TWO REAL SOURCES, ONE BINARY, AND THAT IS THE MEASUREMENT. FirstRunRoute is
# compiled on its own by run_first_run_route_tests.sh and cannot see the policy;
# the policy cannot see it either. Compiling them together is what turns "the
# flow's snooze means what the policy says a snooze means" from a paragraph into
# a check that fails when it stops being true.
cp "$suite" "$out/main.swift"
swiftc -O "$policy" "$handoff" "$route" "$out/main.swift" \
    -o "$out/connectonboardingsteptests"
"$out/connectonboardingsteptests"
