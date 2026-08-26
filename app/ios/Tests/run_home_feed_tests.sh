#!/bin/sh
# Checks for HOME'S FEED PLACEMENT — which section a job lands in, what a
# called-off card leads with, and whether Home may say there is no way to reach
# somebody.
#
#   sh app/ios/Tests/run_home_feed_tests.sh
#
# The decision lives inside ContentView.swift, which drags in SwiftUI, the
# session, the network layer and the microphone — none of which it touches. So
# rather than duplicate it (a copy is honest only until somebody edits one
# side), this lifts the REAL source out from between its ANCHOR markers and
# compiles it alone, the way run_end_errand_tests.sh does with the
# end-of-errand rule.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

view="$app/Views/ContentView.swift"
session="$app/AnticipyApp.swift"

# --------------------------------------------------------------------------
# THE WIRING, BEFORE THE LOGIC.
#
# Every check below the line is worthless if Home has quietly gone back to
# naming statuses by hand in three separate closures — which is the exact shape
# that let `cancelled` match none of them and vanish. A pure policy nobody
# consults is a pure policy that measures nothing.
# --------------------------------------------------------------------------
if ! python3 - "$view" "$session" <<'PY_LEG'; then
import re, sys

view_path, session_path = sys.argv[1], sys.argv[2]


def code(path):
    """The file with its comment LINES blanked out, line numbers preserved.

    Not decoration. The first version of this counted `job.safetyLine` over the
    raw file and went red on the comment in DoneCard that explains why
    safetyLine must never be rendered on a cancellation — a leg failing on the
    prose arguing for the very thing it checks. Prose about a rule is not the
    rule, and every leg below reads what ships.
    """
    out = []
    for line in open(path, encoding="utf-8").read().split("\n"):
        out.append("" if line.lstrip().startswith("//") else line)
    return out


view_lines = code(view_path)
view = "\n".join(view_lines)
session = "\n".join(code(session_path))
lines = view_lines
bad = []


def body_of(prop):
    """The source of one computed property, braces balanced."""
    m = re.search(r"private var %s: \[AgentJob\] \{" % prop, view)
    if m is None:
        return None
    i, depth = m.end() - 1, 0
    while i < len(view):
        if view[i] == "{":
            depth += 1
        elif view[i] == "}":
            depth -= 1
            if depth == 0:
                return view[m.end():i]
        i += 1
    return None


# 1. All three feed sections ask ONE question, in one place.
for prop in ("needsOK", "handling", "finished"):
    body = body_of(prop)
    if body is None:
        bad.append("`%s` is gone, or no longer returns [AgentJob]. This suite "
                   "cannot see the feed's placement rule any more, so it is "
                   "measuring nothing." % prop)
        continue
    if "HomeFeedPolicy.placement" not in body:
        bad.append("`%s` decides placement without HomeFeedPolicy.placement.\n"
                   "      Three closures naming statuses by hand is how `cancelled`\n"
                   "      came to match none of them and render nowhere at all."
                   % prop)
    hand = re.findall(r'\$0\.status\s*==\s*"[a-z_]+"', body)
    if hand:
        bad.append("`%s` matches a status literal by hand: %s\n"
                   "      That is a second answer to a question the policy already\n"
                   "      answers, and the two drift silently." % (prop, ", ".join(hand)))

# 2. The called-off card leads with what the server wrote.
if "HomeFeedPolicy.calledOffLead" not in view:
    bad.append("DoneCard no longer asks HomeFeedPolicy what a called-off card\n"
               "      leads with. `result` is the only surviving carrier of \"it may\n"
               "      already have gone through\" — the card either promotes it or\n"
               "      the warning is unread.")

# 3. `safetyLine` MUST NOT reach the cancelled branch. A cancellation writes
#    `effect_uncertain: false`, so it answers "Nothing you told me was lost."
#    — the reassuring sentence, printed under the warning that contradicts it.
#    Pinned by count: it belongs to the failed branch and nowhere else.
uses = view.count("job.safetyLine")
if uses != 1:
    bad.append("`job.safetyLine` is rendered %d times in this file; it may be\n"
               "      rendered once, on the FAILED branch. On a cancellation the\n"
               "      field was just set false by cancellationFields, so it returns\n"
               "      \"Nothing you told me was lost.\" directly under \"it may already\n"
               "      have gone through\". ex 36: that is the sentence that buys a\n"
               "      duplicate booking nobody checks for." % uses)

# 4. THE HOIST. The unreachable sentence must be said OUTSIDE the stuck-queue
#    block, or it reaches only people who already have work parked — and an
#    account with no number is asked nothing and never parks any.
ask = [i for i, l in enumerate(lines) if "HomeFeedPolicy.sayUnreachable" in l]
gate = [i for i, l in enumerate(lines) if "if !handling.isEmpty {" in l]
if not ask:
    bad.append("Home never asks whether it can reach this person.\n"
               "      AN UNREACHABLE CUSTOMER NEVER FINDS OUT THEY ARE UNREACHABLE\n"
               "      — this file's own words, above the line that was nested.")
elif gate and min(ask) > min(gate):
    bad.append("The unreachable sentence is back inside `if !handling.isEmpty`\n"
               "      (line %d, the block opens at line %d). That is the burial this\n"
               "      fix undid: it reaches only people who already have errands\n"
               "      stuck." % (min(ask) + 1, min(gate) + 1))

# 5. The decline button is a cancellation and says so; the two ESCAPE HATCHES
#    on this screen are not, and keep their words. Every escape hatch in this
#    app is full-width, real size and unguilty — a relabelling pass that swept
#    them up with the cancel button would be the opposite of this fix.
if 'Text("Don\'t do it")' not in view:
    bad.append("The button under `session.decline` no longer says \"Don't do it\".\n"
               "      decline writes status=cancelled and nulls approval, lease and\n"
               "      receipt. \"Not now\" promises a later that does not exist.")
hatches = view.count('Text("Not now")')
if hatches != 2:
    bad.append("This screen has %d \"Not now\" labels; it should have exactly 2 —\n"
               "      the mail offer and the interview offer, both of which really do\n"
               "      defer. If you just relabelled one of those for consistency,\n"
               "      put it back: they are offers, not cancellations." % hatches)

# 6. THE PREMISE, in the file that writes it. If the stop no longer puts the
#    warning in `result`, or no longer clears `effect_uncertain`, then the
#    argument this whole suite rests on has changed and the person editing it
#    should hear so here.
if "may already have gone through" not in session:
    bad.append("AnticipyApp.swift no longer writes \"it may already have gone\n"
               "      through\" into a stopped job's result. That sentence was the\n"
               "      only surviving carrier of the warning and this suite's\n"
               "      fixtures quote it. If the wording moved, move them with it.")
if '"effect_uncertain": false' not in session:
    bad.append("cancellationFields no longer writes `effect_uncertain: false`.\n"
               "      If a cancellation now preserves it, `safetyLine` stops lying on\n"
               "      this card and leg 3 above is arguing about nothing. Re-read\n"
               "      both before deleting either.")

if bad:
    print("HOME'S FEED PLACEMENT IS NOT WIRED THE WAY THESE CHECKS ASSUME.")
    print("")
    for b in bad:
        print("  - %s" % b)
    raise SystemExit(1)

print("the three feed sections ask one policy, the called-off card leads with "
      "the result, safetyLine stays on the failed branch, and the unreachable "
      "sentence is said outside the stuck-queue block")
PY_LEG
    exit 2
fi

# The END rule comes first: the closing marker CONTAINS the opening one as a
# substring, so testing for the opening one first re-arms it and swallows the
# rest of the file.
awk '/END ANCHOR: home feed placement/{f=0;next} /ANCHOR: home feed placement/{f=1;next} f' \
    "$view" > "$out/policy.swift"
if [ ! -s "$out/policy.swift" ]; then
    echo "Found no code between the ANCHOR markers in ContentView.swift."
    echo "Either the markers moved or the policy did; these checks are compiling"
    echo "nothing, which is worse than not having them."
    exit 2
fi
if ! grep -q 'enum HomeFeedPolicy' "$out/policy.swift"; then
    echo "The anchored region no longer contains HomeFeedPolicy."
    exit 2
fi
echo "the anchored region is $(wc -l < "$out/policy.swift" | tr -d ' ') lines of the shipping source"

{
    echo "import Foundation"
    cat "$out/policy.swift"
} > "$out/HomeFeedPolicy.swift"

swiftc -O \
    "$out/HomeFeedPolicy.swift" \
    "$here/HomeFeedTests.swift" \
    -o "$out/homefeedtests"
"$out/homefeedtests"
