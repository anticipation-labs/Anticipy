#!/bin/sh
# Where first run is up to, now that the sign-in door stands in the middle of it.
#
#   sh app/ios/Tests/run_first_run_route_tests.sh
#
# The two beats that ask for nothing — the introduction and how she works —
# moved in FRONT of the door, because a stranger used to type an email, a
# password AND a phone number before the product had produced one single thing
# of its own. Splitting a four-page TabView across an auth boundary makes three
# states real that nobody can reach by tapping: force-quitting between the
# second beat and the door, signing out and handing the phone to somebody else,
# and reinstalling onto an account that already exists.
#
# FirstRunRoute is pure Foundation, so the real production source is compiled
# straight in rather than copied, exactly as run_first_run_tests.sh does with
# FirstRunOwnership. FirstRunTrack is LIFTED out of OnboardingView.swift for
# the same reason: a copy is honest right up until somebody edits one side.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/FirstRunRoute.swift"
owner="$app/FirstRunOwnership.swift"
root="$app/AnticipyApp.swift"
onboard="$app/Views/OnboardingView.swift"
auth="$app/Views/AuthView.swift"
settings="$app/Views/SettingsView.swift"
for f in "$policy" "$owner" "$root" "$onboard" "$auth" "$settings"; do
    [ -f "$f" ] || { echo "missing $f — these checks would read nothing"; exit 2; }
done

# Whole-line comments dropped before every source scan. These files EXPLAIN the
# defects they fixed at length, and an explanation must never be what satisfies
# a grep — that is a suite that goes green on prose.
code() { grep -vE '^[[:space:]]*//' "$1"; }

# The text of one Swift declaration, by counting braces — the same thing
# run_first_run_tests.sh does, and for the same reason: the entire question in
# the clear checks below is WHERE the line is, not whether it appears.
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

# ------------------------------------------------------- A DECISION IS ASKED
#
# A policy nothing consults is a comment. This is the failure run_first_run
# _tests.sh records in its own header: FirstRunOwnership shipped complete,
# correct, in the pbxproj and with ZERO call sites while the gate leg stayed red.
if ! code "$root" | grep -q 'FirstRunRoute.decide('; then
    echo "AnticipyApp does not ask FirstRunRoute which screen to open on."
    echo "Whatever decides that instead is what these checks should follow —"
    echo "as written they are reading a type nothing calls."
    exit 2
fi
for arm in 'case .intro:' 'case .door:' 'case .home:' 'case .tour(let segment):'; do
    if ! code "$root" | grep -qF "$arm"; then
        echo "AnticipyApp's routing has no \`$arm\` arm."
        echo "All four are reachable states of a real phone; a missing one is a"
        echo "screen somebody launches into and cannot get out of."
        exit 2
    fi
done

# ------------------------------------------------------- AND THE HARD LINE
#
# THE PRE-AUTH ARM MAY NOT WRITE THE TOUR FLAG. It has no account to write it
# for. `hasOnboarded = true` reached from in front of the door would route the
# stranger straight to Home with the microphone never asked for and their
# number never taken — the exact bug FirstRunOwnership exists to close, arriving
# from the other direction.
intro_arm=$(code "$root" | awk '/case \.intro:/ { grab = 1 } /case \.door:/ { grab = 0 } grab')
[ -n "$intro_arm" ] || { echo "Could not read AnticipyApp's pre-auth routing arm."; exit 2; }
if printf '%s\n' "$intro_arm" | grep -q 'hasOnboarded'; then
    echo "The pre-auth routing arm writes the tour flag."
    echo "There is no account in front of the door to own it. A hasOnboarded"
    echo "written there sends a stranger to Home having never been asked for"
    echo "the microphone — FirstRunOwnership's bug, from the other direction."
    exit 2
fi
if ! printf '%s\n' "$intro_arm" | grep -q 'segment: .intro'; then
    echo "The pre-auth routing arm no longer passes the .intro segment."
    echo "Any other segment carries the microphone primer, and heard() pushes"
    echo "live before it queues: that is a stranger's room on the server."
    exit 2
fi

# And the view can only render the pages its segment carries. This is the one
# structural guarantee behind the sentence above — a TabView listing all four
# pages unconditionally renders the primer whatever the segment says.
if ! code "$onboard" | grep -q 'ForEach(segment.pages'; then
    echo "OnboardingView no longer builds its pages from segment.pages."
    echo "A TabView that lists all four beats renders the microphone primer in"
    echo "front of the door whatever the routing decided."
    exit 2
fi

# ------------------------------------------------------- THE DEAD END
#
# advance() ended `if step < Step.count - 1`. Step.count - 1 is 3, how-it-works
# is 1, so in the pre-auth segment Continue stepped to a page tagged 2 that the
# segment does not carry: a blank screen, in front of the door, with no way
# forward. It is what "routing only, ~10 lines" produces.
if ! code "$onboard" | grep -q 'step < segment.lastStep'; then
    echo "advance() no longer ends the walkthrough at its own segment's last page."
    echo "Against Step.count - 1 the pre-auth segment walks past how-it-works"
    echo "onto a page it does not carry: a blank screen with no way forward,"
    echo "before the person has an account or a way to ask for help."
    exit 2
fi
if code "$onboard" | grep -q 'step < Step.count - 1'; then
    echo "The old terminal predicate is back in advance()."
    exit 2
fi
# And clearing the last PRE-AUTH page is not the end of first run: a voice
# enrolment offer must not be raised over somebody with no account to attach a
# voice to. On today's build EnrollmentOfferPolicy returns false anyway because
# sherpa-onnx is unlinked — which is accidental safety, and accidental safety
# is the class of thing this change is about.
if ! code "$onboard" | grep -q 'guard segment.endsTheTour else'; then
    echo "finish() no longer asks whether this segment ends the tour."
    echo "In front of the door it does not: the door is next. Without the guard"
    echo "the enrolment invite is raised over a person with no account."
    exit 2
fi

# ------------------------------------------------------- WHAT THE TRACK SAYS
#
# No honest number exists in front of the door: the true ordinal there is 1,
# and the track's rule is that it never opens at 1; the absolute ordinal counts
# an account nobody has made. Both permitted numbers are forbidden.
if ! code "$onboard" | grep -q 'if segment.showsTrack'; then
    echo "The progress track is no longer withheld in front of the door."
    echo "Every number available there is false: \"1 of 5\" opens the track at"
    echo "1, which its own rule forbids, and \"3 of 5\" counts an account"
    echo "nobody has made yet."
    exit 2
fi
# The OTHER mechanism, which this one does not replace. In `.whole` the welcome
# beat is a real page and must still not be counted; both halves are needed.
if ! code "$onboard" | grep -q 'step == Step.welcome ? 0 : 1'; then
    echo "The track stopped hiding itself on the welcome beat."
    echo "That is a separate mechanism from segment.showsTrack: this one is"
    echo "about the whole-tour segment, where welcome IS a page."
    exit 2
fi
# THE INVARIANT. `pageCount` is what the track counts over, never how many
# pages the current segment happens to carry. Handing it segment.pages.count is
# the obvious-looking tidy-up that renames every beat — the compiled checks
# show the microphone beat wearing "Where to reach you" under it.
if code "$onboard" | grep -q 'pageCount: segment'; then
    echo "The track is being told a segment's page count."
    echo "That renames every beat: in the post-door segment the microphone"
    echo "primer wears the name and number of the beat after it."
    exit 2
fi
if ! code "$onboard" | grep -q 'pageCount: Step.count'; then
    echo "The track is no longer counted over the absolute beat count."
    exit 2
fi

# ------------------------------------------------------- THE FLAG'S LIFECYCLE
#
# ONE STRING, IN ONE PLACE — the accident stranger_gate.py's swift_string_behind
# was written for. A second copy of "hasSeenIntro" is a clear that clears
# nothing, and this flag has three clear sites rather than one.
if grep -rq '@AppStorage("hasSeenIntro")' "$app"; then
    echo "Something binds the raw string \"hasSeenIntro\"."
    echo "It is declared once as FirstRunOwnership.introKey; a second copy is"
    echo "how a rename leaves behind a clear that silently clears nothing."
    exit 2
fi
if ! grep -q 'static let introKey = "hasSeenIntro"' "$owner"; then
    echo "FirstRunOwnership no longer declares introKey."
    echo "It lives beside flagKey and ownerKey because it is cleared on the"
    echo "same decision as the tour flag, on the same lines."
    exit 2
fi

# CLEARED WHERE THE PERSON CHANGES, and nowhere else. An introduction is said
# to a PERSON, not to a handset: a purely per-device flag re-opens the hole
# FirstRunOwnership closed, on the two beats this change just moved — the
# installer walks welcome and how-it-works, sets the flag, and the real owner
# who signs up next is never introduced to the product at all.
signin=$(span "$root" 'func signIn[(]')
[ -n "$signin" ] || { echo "AnticipyApp has no func signIn for this suite to read."; exit 2; }
resuming=$(span "$root" 'func resumeSignedInAccount[(]')
[ -n "$resuming" ] || { echo "AnticipyApp has no func resumeSignedInAccount."; exit 2; }
for pair in "signIn:$signin" "resumeSignedInAccount:$resuming"; do
    where=${pair%%:*}
    body=${pair#*:}
    if ! printf '%s\n' "$body" | grep -q 'introSurvivesReplay('; then
        echo "$where clears the introduction flag without asking whether the"
        echo "introduction on this phone could have been this person's."
        echo "arriving() answers .replay for a brand-new sign-up too — an empty"
        echo "owner id is not the id just minted — so an unconditional clear"
        echo "walks EVERY new customer through the welcome typewriter and the"
        echo "how-it-works cards a second time, forty seconds after the first."
        exit 2
    fi
    if ! printf '%s\n' "$body" | grep -q 'hasSeenIntro = false'; then
        echo "$where clears the tour flag and leaves the introduction flag set."
        echo "The two are cleared on the SAME .replay decision or they drift:"
        echo "a second person signing in on a handed-on phone would be dropped"
        echo "into the microphone primer having never been introduced to the"
        echo "product, which is the bug FirstRunOwnership exists for."
        exit 2
    fi
done
# NEVER in signOut. FirstRunOwnership argues this at length: sign-out is not
# where the account changes, sign-IN is. It is also not one of the five owner
# mirrors, so OwnerMirror.clear() must not reach it either.
signout=$(span "$root" 'func signOut[(]')
if [ -n "$signout" ] && printf '%s\n' "$signout" | grep -q 'hasSeenIntro'; then
    echo "signOut touches the introduction flag."
    echo "Sign-out is not where the person changes — sign-in is. Clearing it"
    echo "there replays the introduction to somebody who just signed out of"
    echo "their own account, and it is not one of the five owner mirrors."
    exit 2
fi

# AND THE BUTTON THAT PROMISES IT. Settings offers "Replay the welcome tour",
# and two of those screens are in front of the door now: clearing only the tour
# flag replays the microphone and the number and skips the welcome — the one
# screen the button and its alert both name.
replay=$(code "$settings" | grep -A4 'Button("Replay it")')
if ! printf '%s\n' "$replay" | grep -q 'hasSeenIntro = false'; then
    echo "Settings' \"Replay it\" no longer clears the introduction flag."
    echo "Its alert says \"It's the few screens you saw when you first opened"
    echo "me\", and two of those screens are in front of the door now. Without"
    echo "this it replays the microphone and the number and skips the welcome."
    exit 2
fi

# ------------------------------------------------------- THE DOOR'S OWN COPY
#
# The welcome beat opens "I'm Anticipy. I listen, I remember what matters..."
# and it now comes BEFORE this screen, so the door saying "I'm Anticipy." is no
# longer a repetition — it is a contradiction.
if code "$auth" | grep -q 'return "I.m Anticipy."'; then
    echo "The door introduces the product again."
    echo "The welcome beat says \"I'm Anticipy.\" one screen EARLIER now."
    exit 2
fi
if ! code "$auth" | grep -q "Let's make it yours."; then
    echo "The door lost the title that replaced the second introduction."
    exit 2
fi
if ! code "$auth" | grep -q 'An email, a password, and the number I text you on'; then
    echo "The door no longer names what it is asking for."
    echo "It is three fields before the product has produced anything, and"
    echo "saying which three is the least it can do."
    exit 2
fi

echo "the routing asks the policy, the microphone stays behind the door, the"
echo "track withholds the number it cannot honestly say, and all three clear"
echo "sites clear both flags"

# ------------------------------------------------------------- the real types
#
# LIFTED and compiled, never copied. Brace-matched from the declaration, the
# same way run_first_run_copy_tests.sh lifts FirstRunTrack — the declaration may
# carry a conformance clause, so the match ends at the first character that can
# legally follow the name.
lift() {
    awk -v decl="^enum $2[ :{]" '
        $0 ~ decl { grab = 1 }
        grab {
            print
            n = gsub(/\{/, "{"); m = gsub(/\}/, "}")
            depth += n - m
            if (depth <= 0 && seen) { exit }
            if (n > 0) seen = 1
        }
    ' "$1"
}

{
    echo "import Foundation"
    lift "$onboard" FirstRunTrack > "$out/FirstRunTrack.swift"
    if ! grep -qE '^enum FirstRunTrack[ :{]' "$out/FirstRunTrack.swift"; then
        echo "Found no \`enum FirstRunTrack\` in OnboardingView.swift." >&2
        echo "Either the type moved or this extraction broke; either way the" >&2
        echo "arithmetic below is testing nothing, which is worse than none." >&2
        exit 2
    fi
    opens=$(tr -cd '{' < "$out/FirstRunTrack.swift" | wc -c | tr -d ' ')
    closes=$(tr -cd '}' < "$out/FirstRunTrack.swift" | wc -c | tr -d ' ')
    if [ "$opens" != "$closes" ] || [ "$opens" = "0" ]; then
        echo "Extracted FirstRunTrack has $opens '{' and $closes '}' — the lift" >&2
        echo "is not bracketing the type. These checks would test a fragment." >&2
        exit 2
    fi
    cat "$out/FirstRunTrack.swift"
} > "$out/track.swift"

# swiftc only permits top-level code in a file literally named main.swift.
cp "$here/FirstRunRouteTests.swift" "$out/main.swift"
# BOTH policies, compiled together. The defect this suite caught did not
# live inside either one: FirstRunOwnership.arriving answers .replay for a
# brand-new sign-up as well as for a second person on a handed-on phone, so a
# rule phrased as "clear the intro flag wherever the tour flag is cleared"
# walks every new customer through the welcome typewriter twice. Only a walk
# that runs the two together can see it.
swiftc -O "$policy" "$owner" "$out/track.swift" "$out/main.swift" -o "$out/firstrunroutetests"
"$out/firstrunroutetests"
