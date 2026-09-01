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


def block_after(marker, start=0):
    """The source inside the braces opened by the line holding `marker`."""
    at = view.find(marker, start)
    if at < 0:
        return None
    i = view.index("{", at)
    depth, j = 0, i
    while j < len(view):
        if view[j] == "{":
            depth += 1
        elif view[j] == "}":
            depth -= 1
            if depth == 0:
                return view[i + 1:j]
        j += 1
    return None


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
#
#    THE COMPARISON, NOT THE EQUALS SIGN. This read `== "literal"` only, and
#    `$0.status != "cancelled"` walked straight past it — which restores the
#    entire shipped bug (cancellations render nowhere) with the suite green.
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
    hand = re.findall(r'\$0\.\w+\s*(?:==|!=)\s*"[^"]*"', body)
    if hand:
        bad.append("`%s` compares a row's own field against a literal by hand: %s\n"
                   "      That is a second answer to a question the policy already\n"
                   "      answers, and the two drift silently. `!=` counts: excluding\n"
                   "      \"cancelled\" from `finished` is the shipped bug, restored."
                   % (prop, ", ".join(hand)))

#    AND THE WORD ITSELF LIVES IN THE POLICY. `cancelled` matching nothing is
#    the original bug, and what let it happen was the status being spelled out
#    in several closures at once. Any spelling of it outside `HomeFeedPolicy` —
#    the card's own `calledOff`, the cap's, a filter's — is a second answer
#    sitting there waiting to drift away from the first.
policy = block_after("enum HomeFeedPolicy {")
if policy is None:
    bad.append("`HomeFeedPolicy` is gone from this file, so there is no one\n"
               "      place answering which section a job lands in.")
elif '"cancelled"' in view.replace(policy, ""):
    bad.append("The literal \"cancelled\" is written outside `HomeFeedPolicy`.\n"
               "      That status matching nothing at all is the bug this whole\n"
               "      suite exists for, and it happened because the word was spelled\n"
               "      out in more than one place. Ask the policy.")

# 2. The called-off card leads with what the SERVER wrote about THIS job.
#
#    Asking for the string "HomeFeedPolicy.calledOffLead" alone was not a check:
#    `calledOffLead(result: nil)` contains it, compiles, and pins the card to the
#    fallback forever — the warning could then never reach the screen at all.
if "HomeFeedPolicy.calledOffLead(result: job.result)" not in view:
    bad.append("DoneCard no longer leads a called-off card with\n"
               "      `HomeFeedPolicy.calledOffLead(result: job.result)`. `result` is\n"
               "      the only surviving carrier of \"it may already have gone\n"
               "      through\" — the card either promotes THAT job's result or the\n"
               "      warning is unread.")

cancelled = block_after("} else if calledOff {")
if cancelled is None:
    bad.append("DoneCard has no `else if calledOff` branch. A job the owner\n"
               "      stopped is back to rendering as a success or a failure, and\n"
               "      neither is what happened.")
    cancelled = ""

# 3. The card SAYS WHAT IT IS, before the server's words.
#
#    `decline` never writes `result`, so on that path the lead is whatever the
#    engine last said — for a stuck job, an offer to try again, on a row that
#    will never be tried again. Without this line nothing on the card says the
#    owner stopped it.
kickers = view.count("HomeFeedPolicy.calledOffKicker")
if kickers != 1:
    bad.append("`HomeFeedPolicy.calledOffKicker` is rendered %d times; it belongs\n"
               "      to the CALLED-OFF branch and nowhere else. Over a failed job it\n"
               "      says the owner stopped something the site refused to do, which\n"
               "      is the same class of false claim it was written to end."
               % kickers)
if "HomeFeedPolicy.calledOffKicker" not in cancelled:
    bad.append("The called-off branch no longer renders\n"
               "      `HomeFeedPolicy.calledOffKicker`. `decline` leaves `result`\n"
               "      exactly as the engine left it, so without the kicker a\n"
               "      cancelled stuck job renders under \"Done\" still leading with\n"
               "      \"check the site before I try again\" and nothing anywhere on\n"
               "      the card saying you stopped it.")

# 4. `safetyLine` MUST NOT reach the cancelled branch, IN ANY SPELLING. A
#    cancellation writes `effect_uncertain: false`, so it answers "Nothing you
#    told me was lost." — the reassuring sentence, printed under the warning
#    that contradicts it.
#
#    Counting `job.safetyLine` was not enough: calling the policy directly,
#    `JobReceiptPolicy.safetyLine(effectUncertain: job.effect_uncertain)`, put
#    that exact sentence back on the cancelled card with the suite green.
if "safetyLine" in cancelled:
    bad.append("`safetyLine` is rendered on the CALLED-OFF branch. The field it\n"
               "      reads was just set false by cancellationFields, so it returns\n"
               "      \"Nothing you told me was lost.\" directly under \"it may already\n"
               "      have gone through\". ex 36: that is the sentence that buys a\n"
               "      duplicate booking nobody checks for.")
# Counted over the RENDERING code only: `extension AgentJob` is where the
# property is declared, and a declaration is not a second answer to anything.
declaration = block_after("extension AgentJob {")
rendering = view.replace(declaration, "") if declaration else view
uses = len(re.findall(r"\bsafetyLine\b", rendering))
if uses != 1:
    bad.append("`safetyLine` is rendered %d times in this file; it may be rendered\n"
               "      once, on the FAILED branch, where `effect_uncertain` still\n"
               "      means what it says. Any second caller is a second answer to\n"
               "      \"is my stuff safe\" on a card that cannot answer it." % uses)

# 5. THE HOIST, AND ITS ONLY CONDITION. The unreachable sentence must be said
#    outside the stuck-queue block — an account with no number is asked nothing
#    and never parks any work, so nesting it there meant it reached nobody.
#
#    Ordering alone was not enough: `if !needsOK.isEmpty, HomeFeedPolicy...`
#    re-buried it behind a different queue while still preceding the handling
#    block. So the whole `if` condition is read, and it must be the policy call
#    and nothing else.
ask = [i for i, l in enumerate(lines) if "HomeFeedPolicy.sayUnreachable" in l]
gate = [i for i, l in enumerate(lines) if "if !handling.isEmpty {" in l]
if len(ask) != 1:
    bad.append("Home asks `HomeFeedPolicy.sayUnreachable` %d times; it must ask\n"
               "      exactly once. AN UNREACHABLE CUSTOMER NEVER FINDS OUT THEY ARE\n"
               "      UNREACHABLE — this file's own words — and a second copy of the\n"
               "      sentence is how it came to be said twice in two voices."
               % len(ask))
else:
    at = ask[0]
    top = at
    while top >= 0 and not lines[top].lstrip().startswith("if "):
        top -= 1
    if top < 0:
        bad.append("`HomeFeedPolicy.sayUnreachable` is no longer the condition of\n"
                   "      an `if`. Whatever it now feeds, this leg cannot see what\n"
                   "      guards the sentence.")
    else:
        end = top
        while end < len(lines) and not lines[end].rstrip().endswith("{"):
            end += 1
        cond = " ".join(l.strip() for l in lines[top:end + 1])
        cond = cond[len("if "):].rstrip()[:-1].strip()
        if not (cond.startswith("HomeFeedPolicy.sayUnreachable(") and cond.endswith(")")):
            bad.append("The unreachable sentence has a SECOND condition on it:\n"
                       "        %s\n"
                       "      Every extra clause is another queue to be behind, and\n"
                       "      being behind a queue is the burial this fix undid."
                       % cond)
        body = block_after("HomeFeedPolicy.sayUnreachable")
        if body is None or "unreachableNotice" not in body:
            bad.append("The `if` that asks whether we can reach this person no\n"
                       "      longer renders `unreachableNotice`. The question is being\n"
                       "      asked and the answer is being dropped.")
    if gate and at > min(gate):
        bad.append("The unreachable sentence is back inside `if !handling.isEmpty`\n"
                   "      (line %d, the block opens at line %d). That is the burial this\n"
                   "      fix undid: it reaches only people who already have errands\n"
                   "      stuck." % (at + 1, min(gate) + 1))

# 6. AND IT IS AN EXPLICIT CANONICAL STATE, not a cached-string inference.
#    Unknown, none, malformed, and valid are four different product promises.
#    Home delegates the read to the session, whose account-bound canonical
#    owner refresh also rehydrates Settings. The short retry is bounded and a
#    foreground transition re-arms it; none of this may join the 3-second poll.
if "accountSaysNoNumber" in view:
    bad.append("Home still carries the old Bool? reachability inference. It cannot\n"
               "      distinguish a malformed number from a valid one and duplicates\n"
               "      the canonical state now owned by AnticipySession.")
read = block_after("private func refreshCanonicalOwnerForReachability() async")
if read is None:
    bad.append("`refreshCanonicalOwnerForReachability` is gone, so Home has no\n"
               "      bounded recovery after an owner read starts offline.")
else:
    if "session.refreshCanonicalOwner()" not in read:
        bad.append("Home no longer delegates reachability to the shared canonical\n"
                   "      owner/profile read.")
    if "0..<3" not in read or "Task.sleep" not in read:
        bad.append("The unknown canonical phone state has no bounded retry. It can\n"
                   "      remain `checking` for the whole foreground session.")
if 'session.accountID)' not in view or ".task(id:" not in view:
    bad.append("The canonical owner refresh is not keyed across account changes.")
if view.count("refreshCanonicalOwnerForReachability()") < 3:
    bad.append("Canonical reachability is not refreshed from both the task and\n"
               "      foreground paths (plus its declaration). A launch failure can\n"
               "      otherwise become a permanent session lie.")

route = block_after("private var notificationRoute: NotificationRoute")
if route is None:
    bad.append("ConfirmJobCard's notification route is gone.")
else:
    if "canonicalPhoneState" not in route or "session.ownerPhone" in route:
        bad.append("ConfirmJobCard still infers a delivery promise from the cached\n"
                   "      ownerPhone string instead of canonical phone state.")
    for state in (".unknown", ".none", ".invalid", ".valid"):
        if state not in route:
            bad.append("ConfirmJobCard does not handle canonical phone state %s."
                       % state)

# 7. THE SECOND COPY MUST NOT COME BACK. The same fact used to be said again,
#    ungated, in Theme.accent, inside the stuck-queue block.
if "no number for you" in view:
    bad.append("The accent-coloured \"I have no number for you\" sentence is back\n"
               "      inside the stuck-queue block. It asked the device-local mirror\n"
               "      with no guard at all, and it says the same thing\n"
               "      `unreachableNotice` already says a screen further up.")

# 8. AND THE CAP MAY NOT BE THE THING THAT SWALLOWS IT. "Done" is drawn by
#    terminal update time (with creation time only as a legacy fallback) and is
#    capped. A plain `prefix` would still swallow a warning-bearing terminal
#    card once enough ordinary receipts arrived. That is the same silence leg 1
#    undid, arriving through the display instead of the filter.
if re.search(r"\bfinished\.prefix\(", view):
    bad.append("Done is drawn with `finished.prefix(...)` again. That counts a\n"
               "      warning-bearing cancellation like an ordinary receipt and can\n"
               "      put \"it may already have gone through\" back out of sight —\n"
               "      the filter bug, one step later.")
shelf = body_of("finishedShown")
if shelf is None:
    bad.append("`finishedShown` is gone, so nothing decides which Done cards the\n"
               "      cap is allowed to swallow and the section is back to cutting\n"
               "      every terminal row by creation order alone.")
elif "HomeFeedPolicy.shelved(" not in shelf:
    bad.append("`finishedShown` no longer asks `HomeFeedPolicy.shelved` which\n"
               "      cards the shelf may swallow. A cancellation and a receipt are\n"
               "      the same thing to a plain counter, and only one of them is\n"
               "      still asking the reader to go and check something. The WALK\n"
               "      belongs to the policy, not to this property: a hand-written\n"
               "      one that stops at the shelf's edge instead of stepping past it\n"
               "      drops the exact card the rule keeps, and every predicate in\n"
               "      the file still answers correctly while it does.")
elif "shelf: Self.doneShelf" not in shelf:
    bad.append("`finishedShown` no longer hands `HomeFeedPolicy.shelved` the\n"
               "      section's own shelf depth. A second number here is a second\n"
               "      answer to how much of Done is a shelf.")
else:
    #    AND WHAT IT ASKS IS WHAT IT HANDS BACK. Asking for the call to appear
    #    somewhere in the body was not a check: leaving the call in place and
    #    returning `rows.prefix(8)` underneath it kept this leg green and put
    #    the plain cut straight back. So the answer is traced to the return.
    got = re.search(r"\blet\s+(\w+)\s*=\s*HomeFeedPolicy\.shelved\(", shelf)
    rets = [l.strip() for l in shelf.split("\n") if l.strip().startswith("return ")]
    if not rets:
        bad.append("`finishedShown` has no `return`, so this leg cannot see what it\n"
                   "      hands the section. Whatever it now does, the cap rule is no\n"
                   "      longer traceable from the property that is supposed to apply it.")
    else:
        carried = [r for r in rets
                   if "HomeFeedPolicy.shelved(" in r or (got and got.group(1) in r)]
        if len(carried) != len(rets):
            bad.append("`finishedShown` asks `HomeFeedPolicy.shelved` and then hands\n"
                       "      back something else: %s\n"
                       "      The call being present is not the rule being applied —\n"
                       "      that is the shape of check that let a plain cut sit\n"
                       "      underneath it with this suite green."
                       % "; ".join(r for r in rets if r not in carried))
    if ".prefix(" in shelf:
        bad.append("`finishedShown` cuts the section itself with `.prefix(`. The\n"
                   "      shelf is the policy's to spend: a slice here counts the card\n"
                   "      that must not be swallowed against the cap it is exempt from.")
done_consumers = (
    "ForEach(Array(finishedShown.enumerated())",
    "DoneDeck(jobs: finishedShown)",
)
if not any(consumer in view for consumer in done_consumers):
    bad.append("The Done section no longer draws `finishedShown`. The cap rule is\n"
               "      declared and nothing consults it, which is indistinguishable\n"
               "      from not having written it.")

# 9. The decline button is a cancellation and says so; the two ESCAPE HATCHES
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

# 10. THE PREMISE, in the file that writes it. If the stop no longer puts the
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
               "      this card and leg 4 above is arguing about nothing. Re-read\n"
               "      both before deleting either.")

if bad:
    print("HOME'S FEED PLACEMENT IS NOT WIRED THE WAY THESE CHECKS ASSUME.")
    print("")
    for b in bad:
        print("  - %s" % b)
    raise SystemExit(1)

print("the three feed sections ask one policy, the called-off card names itself "
      "and then leads with this job's result, safetyLine stays off it in every "
      "spelling, and the unreachable sentence is said once, outside every queue, "
      "on the account's own answer")
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

# HomeFeedPolicy's reachability input is the exact production enum declared by
# OwnerMirror. Lift that type too so these cases compile the shipping four-state
# model rather than a test-only copy that can drift.
awk '/^enum OwnerMirror \{/,/^\}/' "$session" > "$out/OwnerMirror.swift"
if ! grep -q 'enum PhoneState' "$out/OwnerMirror.swift"; then
    echo "OwnerMirror.PhoneState is missing from AnticipyApp.swift."
    exit 2
fi

{
    echo "import Foundation"
    cat "$out/OwnerMirror.swift"
    cat "$out/policy.swift"
} > "$out/HomeFeedPolicy.swift"

swiftc -O \
    "$out/HomeFeedPolicy.swift" \
    "$here/HomeFeedTests.swift" \
    -o "$out/homefeedtests"
"$out/homefeedtests"
