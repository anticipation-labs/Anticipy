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
root=$(cd "$here/../../.." && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/Backend/ConnectOnboardingPolicy.swift"
handoff="$app/Backend/ConnectHandoff.swift"
route="$app/FirstRunRoute.swift"
onboard="$app/Views/OnboardingView.swift"
view="$app/Views/OnboardingConnectStep.swift"
suite="$here/ConnectOnboardingPolicyTests.swift"
# The wire. The card's evidence and the phone's Skip both leave the handset
# through this one client, so the suite below drives the REAL one over a fake
# transport rather than a second copy of it — the same shape
# run_connected_apps_client_tests.sh uses, for the same reason: a client that
# is only ever exercised by its own mock is a contract nobody keeps.
client="$app/Backend/ConnectedAppsClient.swift"
connections="$app/Backend/ConnectionsPolicy.swift"
model="$app/Backend/ConnectedAppsModel.swift"
duration="$app/Audio/PlainDuration.swift"
for f in "$policy" "$handoff" "$route" "$onboard" "$view" "$suite" \
         "$client" "$connections" "$model" "$duration"; do
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

# ------------------------------------------------- 4B. THE CARD IS ACTUALLY FED
#
# GAP A, and it is the one that made page 45's first sentence a decoration.
# `OnboardingConnectStep` was constructed with LITERAL EMPTY ARRAYS — `detected(
# from: [], catalog: [], …)` — so "detected apps pre-selected" pre-selected
# nothing, for everybody, forever, while `ConnectOnboardingPolicy.detected`
# passed 154 checks proving it would have ranked them beautifully if anything
# had ever handed it a row.
#
# THE THREE EMPTY ANSWERS ARE THREE DIFFERENT FACTS and the flow may not fold
# them together. "We looked and you use none of these" is a claim about the
# person; "we could not look" and "the catalog could name none of it" are
# claims about us, and a person told the first when the truth is one of the
# other two is being told their app does not exist by a product whose request
# failed. The policy carries all three; this leg is that the FLOW reaches them.
detectfn=$(span "$out/onboard.code.swift" 'var connectDetection')
[ -n "$detectfn" ] || { echo "OnboardingView has no connectDetection for this runner to read."; exit 2; }
if printf '%s\n' "$detectfn" | grep -qE 'from: \[\]|catalog: \[\]'; then
    echo "OnboardingView still builds the setup card out of literal empty arrays:"
    printf '%s\n' "$detectfn" | grep -nE 'from: \[\]|catalog: \[\]'
    echo ""
    echo "That is not a ranking over no evidence, it is a promise never kept."
    echo "Page 45: \"Detected apps pre-selected from the email domain signal.\""
    echo "The rows come off the wire, through the one client, and the policy"
    echo "ranks them. A literal here pre-selects nothing for every person alive."
    exit 2
fi
if ! printf '%s\n' "$detectfn" | grep -q 'ConnectOnboardingPolicy.detected('; then
    echo "connectDetection no longer asks the policy which apps arrive ticked."
    exit 2
fi
# AND THE EMPTY ANSWERS ARE NOT INVENTED HERE. `SignalsAnswer` is the seam: the
# view holds what the route said, the policy turns it into a card. A view that
# built `.apps([])` or `.refused(…)` itself would be a second decision about
# what an empty answer means, in the one place no suite compiles.
if printf '%s\n' "$detectfn" | grep -qE '\.apps\(|\.refused\('; then
    echo "connectDetection decides for itself what an empty answer means."
    echo "Three empty answers are three different sentences, and which one a"
    echo "person is told is ConnectOnboardingPolicy's decision — it is the only"
    echo "half of this a laptop can run."
    exit 2
fi
# THE READ IS FROZEN, exactly as the audience read is and for the same reason:
# the card seeds its tick-boxes ONCE, so an answer adopted while somebody is
# standing on the step is a row that appears with no tick and a ranking nobody
# will ever see.
signalsfn=$(span "$out/onboard.code.swift" 'func readConnectSignals[(]')
[ -n "$signalsfn" ] || { echo "OnboardingView has no readConnectSignals() — nothing fetches the evidence."; exit 2; }
if ! printf '%s\n' "$signalsfn" | grep -q 'ConnectBeat.mayAdoptAudience(standingOn:'; then
    echo "The evidence read is adopted without asking whether the person is"
    echo "already standing on the card it would rearrange. The step seeds its"
    echo "ticks once; a late answer is rows nobody ticked."
    exit 2
fi
# AND IT ASKS THE ONE CLIENT. Every call that leaves this phone about
# connections goes through `ConnectedAppsClient`, which is where the owner is
# compared, the token is put in a header and the route census lives. A second
# way out of the app is a second one of all three.
if ! printf '%s\n' "$signalsfn" | grep -q 'connectedAppsClient().signals(owner:'; then
    echo "readConnectSignals does not ask ConnectedAppsClient for the evidence."
    echo "That client is the only thing in this app allowed to make this call:"
    echo "it compares the owner before a request exists, keeps the token off"
    echo "the URL, and declares every route it can reach in one enum."
    exit 2
fi
# ALL FOUR STATES ARE TRANSLATED, AND THE TRANSLATION IS TOTAL. The route
# declares four (SIGNALS_ANSWER) and three of them come back EMPTY. A view that
# handled three and let the fourth fall into a default would be choosing, in
# the one file no suite compiles, which person gets told they use nothing.
# The check is on the ASSIGNMENT and not on the word appearing somewhere in the
# function: `.catalogUnreadable` is also the name of the refusal being caught,
# so a grep for the bare word stays green while the arm that reads it hands
# back a different answer. Measured — that mutation passed until this line.
for state in 'nothingYet' 'ranked(' 'catalogUnreadable' 'unreachable'; do
    if ! printf '%s\n' "$signalsfn" | grep -qF "answer = .$state"; then
        echo "readConnectSignals never answers .$state."
        echo "me/connections/signals has four answers and three of them are"
        echo "empty. \"You use none of these\" is a claim about the PERSON;"
        echo "\"I could not look\" and \"I cannot name them\" are claims about us."
        exit 2
    fi
done
# THE ANSWER IS NOT ADOPTED FOR THE WRONG PERSON. The rows on this route carry
# no owner — the one list in this app that cannot be scoped twice — so the
# phone's half of that check is a comparison against the id the call was made
# for. Without it a slow answer pre-ticks one person's apps on another person's
# setup card, which is the failure this whole feature is built around.
if ! printf '%s\n' "$signalsfn" | grep -q 'guard session.accountID =='; then
    echo "readConnectSignals adopts an answer without checking it is still the"
    echo "same person's. The signals route puts no owner on any row, so this"
    echo "comparison is the only owner check the phone has left on it."
    exit 2
fi
# AND THE TRANSLATION IS THE ONE THE SUITE RUNS. OnboardingView cannot be
# compiled on a laptop, so the suite holds a copy of these lines and drives the
# real client through them. Two copies drift; this is what says when.
for half in "$out/onboard.code.swift" "$suite"; do
    if ! grep -q 'ConnectOnboardingPolicy.RankedApp(toolkit:' "$half"; then
        echo "$(basename "$half") does not build a RankedApp from the wire's own"
        echo "fields. The view's mapping and the suite's have to be one shape,"
        echo "or the checked half is not the shipped half."
        exit 2
    fi
done

# ------------------------------------------------- 4C. AND SKIP REACHES A SERVER
#
# GAP C. Onboarding's Skip wrote `connectStepSnoozeUntil` into THIS HANDSET'S
# UserDefaults and nothing else, so a reinstall forgot it and the ask engine —
# which is the thing that actually decides whether somebody is asked again —
# never heard it at all. The local write is the OFFLINE FALLBACK. The record is
# the server's.
#
# The wire has to exist before it can be used, so the client's own route census
# is read here rather than taken on trust.
if ! grep -q 'static let skip = "me/connections/skip"' "$client"; then
    echo "ConnectedAppsClient has no skip route, so a person's no has nowhere to go."
    exit 2
fi
if ! grep -q 'static let signals = "me/connections/signals"' "$client"; then
    echo "ConnectedAppsClient has no signals route, so the card has no evidence"
    echo "to rank and pre-selects nothing whatever the policy can do."
    exit 2
fi
sendfn=$(span "$out/onboard.code.swift" 'func sendConnectSkip[(]')
[ -n "$sendfn" ] || { echo "OnboardingView has no sendConnectSkip() — the skip never leaves the phone."; exit 2; }
# AND SOMETHING CALLS IT. This runner exists because a whole screen was written,
# compiled and tested with zero call sites; a send that nothing invokes is the
# same defect one function down. It is called from the Skip handler, beside the
# local write, so the two halves of one decision cannot come apart.
skipfn=$(span "$out/onboard.code.swift" 'func skipConnectStep[(]')
[ -n "$skipfn" ] || { echo "OnboardingView has no skipConnectStep() for this runner to read."; exit 2; }
for half in 'recordConnectSkip()' 'sendConnectSkip()'; do
    if ! printf '%s\n' "$skipfn" | grep -qF "$half"; then
        echo "Skip does not call $half"
        echo "A skip is two writes: this handset's fallback, and the server's"
        echo "record. Either one alone is a person who gets asked again — by a"
        echo "reinstall, or by an ask engine that never heard them."
        exit 2
    fi
done
if ! printf '%s\n' "$sendfn" | grep -q 'ConnectOnboardingPolicy.serverRecordsTheSoftSnooze'; then
    echo "sendConnectSkip does not consult the one fact that decides whether"
    echo "sending is safe. Read ConnectOnboardingPolicy.serverRecordsTheSoftSnooze."
    exit 2
fi
if ! printf '%s\n' "$sendfn" | grep -qE '\.skip\(toolkit:'; then
    echo "sendConnectSkip does not call the client's skip route."
    exit 2
fi

# THE EXPIRY, AND IT RETIRES ITSELF. REWRITTEN 2026-09-06, HALF SPENT.
#
# WHAT IT USED TO SAY. `POST /me/connections/skip` reached `recordSkip` ->
# `recordDecline`, which stamped `state: "declined"` and `level: nudge.level + 1`
# on the very event the setup card calls a shrug. Level 1 raises that same file's
# own threshold from 0.5 to 0.8 against a STRICT comparison, so repeated_use
# (0.6), onboarding (0.7) and in_task (0.8) were silenced for good — the two
# triggers that can name a task which already cost this person real time. So the
# phone did not send, and this leg read the server's source and demanded the
# Swift constant match it.
#
# WHAT CHANGED. The ladder was fixed: `recordDecline` now has a soft branch that
# writes `declined_soft` at LEVEL 0 with a seven-day snooze, and the Worker
# carrying it is deployed. `spike/two-hands/src/connections/contract.ts`,
# `ConnectionsPolicy.NudgeState` and live `/me/connections/skip` all know the
# state.
#
# WHY THE PHONE STILL DOES NOT SEND, and why that is not this leg going stale.
# Live D1's `connect_nudges` carries a CHECK constraint listing five states, and
# SQLite cannot widen a CHECK — the table has to be REBUILT. Until somebody runs
# `migration/d1/2026-09-06-connect-nudges-declined-soft.sql`, the row the fixed
# code writes is refused by the database and the route answers 503. A phone
# sending into that would fail every onboarding skip at the most fragile minute
# this product has.
#
# SO THE PREDICATE IS NOW THREE-STATE, and the third state is the one this file
# was missing:
#
#   the ladder still climbs          -> the constant MUST be false (the original
#                                       expiry, unchanged, still armed)
#   the ladder is soft AND the phone sends -> fine, the feature is done
#   the ladder is soft AND the phone does not
#                                    -> ALLOWED, but only while a RED LIVE LEG is
#                                       tracking the reason. That is law 2's
#                                       shape: a hold-back with an expiry
#                                       somebody can run, not a comment.
#
# The live leg is `overnight/is_connect_live.py` leg 13. This checks that it
# exists, that it names the state and the migration, and that the migration file
# is actually in the tree — so "we are waiting on the database" cannot be a
# sentence somebody typed.
nudge="$root/migration/workers/src/connections/nudge.ts"
if [ -f "$nudge" ]; then
    decline=$(sed -n '/export function recordDecline/,/^}/p' "$nudge")
    [ -n "$decline" ] || { echo "cannot read recordDecline out of the Worker's nudge module"; exit 2; }
    # THE SOFT BRANCH, not the absence of the hard one. `nudge.level + 1` is
    # still in this function and always will be — it is the ORDINARY ladder,
    # which a setup-card skip is now the exception to. A leg that reads the old
    # literal reports "the ladder still climbs" forever and passes by accident,
    # which is exactly what it did for the first hour after the fix landed.
    if printf '%s\n' "$decline" | grep -q 'state: "declined_soft"' \
        && printf '%s\n' "$decline" | grep -q 'level: 0'; then
        server_soft=true
    else
        server_soft=false
    fi
    swift_soft=$(grep -E '^[[:space:]]*static let serverRecordsTheSoftSnooze' "$policy" \
        | head -1 | sed -E 's/.*=[[:space:]]*//' | tr -d ' ')
    [ -n "$swift_soft" ] \
        || { echo "ConnectOnboardingPolicy has no serverRecordsTheSoftSnooze constant."; exit 2; }

    if [ "$server_soft" = false ] && [ "$swift_soft" = true ]; then
        echo ""
        echo "The constant claims the server honours a soft snooze. It does not:"
        echo "recordDecline stamps declined and advances the level, which raises"
        echo "the ask threshold to 0.8 against a strict comparison and silences"
        echo "in_task and repeated_use permanently. Do not send that."
        exit 2
    fi

    if [ "$server_soft" = true ] && [ "$swift_soft" = false ]; then
        # HOLDING BACK IS ALLOWED, WITH A RED LEG AND NOT WITH A PARAGRAPH.
        live="$root/overnight/is_connect_live.py"
        migration="$root/migration/d1/2026-09-06-connect-nudges-declined-soft.sql"
        ok=yes
        [ -f "$live" ] || ok=no
        [ -f "$migration" ] || ok=no
        if [ "$ok" = yes ]; then
            grep -q 'declined_soft' "$live" || ok=no
            grep -q '2026-09-06-connect-nudges-declined-soft.sql' "$live" || ok=no
        fi
        if [ "$ok" = no ]; then
            echo ""
            echo "The server records the soft snooze and the phone still does not send it,"
            echo "and nothing live is tracking why. That is tape without an expiry."
            echo ""
            echo "Either flip ConnectOnboardingPolicy.serverRecordsTheSoftSnooze to true,"
            echo "or keep overnight/is_connect_live.py leg 13 — which must name"
            echo "'declined_soft' and the migration file that repairs it — RED until the"
            echo "live connect_nudges CHECK can hold the state."
            exit 2
        fi
        echo "NOTE: the ladder is soft and the phone is deliberately not sending yet."
        echo "      Live D1's connect_nudges CHECK cannot hold 'declined_soft', so the"
        echo "      write would 503. overnight/is_connect_live.py leg 13 is RED until"
        echo "      migration/d1/2026-09-06-connect-nudges-declined-soft.sql is run;"
        echo "      flip the constant in the same change."
    fi
else
    echo "NOTE: the Worker's nudge module is absent, so what the server records"
    echo "      for a skip is UNPROVEN from here. The constant is pinned in the"
    echo "      suite; it is not pinned against the thing it is about."
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
            'func recordConnectSkip[(]' 'func sendConnectSkip[(]' \
            'func startConnecting[(]' 'var connectTroubleSheet' \
            'var connectDetection' 'func readConnectSignals[(]'; do
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
#
# AND THE CLIENT IS IN THE BINARY TOO, from 2026-09-06. The card's evidence and
# the phone's Skip both leave through `ConnectedAppsClient`, and the two things
# that can go wrong there cannot be seen from a source scan: a route that puts
# an owner on the wire, and an answer this build reads as a fact when it is a
# refusal. The real client is driven over a fake transport, so the request that
# would have been sent is inspected rather than imagined.
cp "$suite" "$out/main.swift"
swiftc -O "$policy" "$handoff" "$route" "$connections" "$model" "$client" \
    "$duration" "$out/main.swift" \
    -o "$out/connectonboardingsteptests"
"$out/connectonboardingsteptests"
