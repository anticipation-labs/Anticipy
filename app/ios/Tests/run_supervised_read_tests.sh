#!/bin/sh
# The supervised read: the watch lease is the mechanism, and it must stay one.
#
#   sh app/ios/Tests/run_supervised_read_tests.sh
#
# WHY THIS IS A SOURCE SCAN AND NOT A UNIT TEST. The property being defended is
# that NOTHING can keep a read alive once the person stops watching. That is a
# property of the SHAPE of the code — a `.task(id:)` keyed on the scene phase,
# and the ABSENCE of any timer, background task or detached loop that could
# outlive it. No runtime assertion can see the absence of a Timer. A reviewer
# six months from now, "fixing" a heartbeat that "stops working when you
# background the app", absolutely can and will add one. This file is the thing
# that says no.
#
# The other half is the precedent `run_context_grant_tests.sh` sets in as many
# words: prove the WIRING first, because the exact failure `events.source`
# already suffered once was being written for weeks and read by nothing, with no
# test noticing. Every session call this screen depends on is asserted to be
# both declared and called.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
view="$app/Views/SupervisedReadView.swift"
home="$app/Views/ContentView.swift"
session="$app/AnticipyApp.swift"
for f in "$view" "$home" "$session"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done
fail=0

# PROSE IS NOT CODE. The view EXPLAINS at length that a Timer or a
# BGTaskScheduler job would destroy the safety property, and an explanation is
# the opposite of a regression. Whole-line comments are dropped before every
# scan, exactly as `run_theme_contract_tests.sh` does — but these greps run over
# ONE file, so `grep -n` emits `line:text` and the filter anchors at `^`, not
# after a filename.
code() { grep -n "$1" "$2" 2>/dev/null | grep -v '^[0-9]*: *//' || true; }
has() { [ -n "$(code "$1" "$2")" ]; }
bad() { echo "FAIL: $1"; fail=1; }
# One `private func`/`private var` body, comments and all.
member() { sed -n "/$1/,/^    }\$/p" "$2"; }

# ---------------------------------------------------------------- the mechanism

# 1. The heartbeat and the narration are both SwiftUI tasks on the same key.
#    SwiftUI cancels a `.task(id:)` on id change AND on the view leaving the
#    hierarchy; that cancellation IS the stop. Nothing else stops it.
beats=$(code 'task(id: driveKey)' "$view" | grep -c . || true)
[ "$beats" = "2" ] \
    || bad "expected the lease heartbeat AND the narration poll as .task(id: driveKey); found $beats"

# 2. The key folds in the scene phase. Drop that and the heartbeat survives
#    backgrounding, which is the whole safety property gone: the read would
#    carry on with nobody watching it — "I went through your mail while you
#    weren't looking" (design/day-zero.md §2).
member 'private var driveKey' "$view" | grep -q 'scenePhase == .active' \
    || bad "driveKey no longer reads scenePhase, so backgrounding the app would not end the read"

# 3. And the heartbeat itself refuses off the foreground, because `.task(id:)`
#    RESTARTS with the new key rather than merely stopping.
member 'private func holdTheLease' "$view" | grep -q 'scenePhase == .active' \
    || bad "holdTheLease no longer guards on scenePhase == .active"

# 4. NOTHING may outlive the view. Every one of these is a way to keep beating
#    after the person stopped watching, and every one is the defect the comment
#    above `.task(id: driveKey)` exists to forbid.
for escape in 'Timer' 'BGTaskScheduler' 'beginBackgroundTask' 'asyncAfter' 'Task.detached' 'DispatchSourceTimer' 'backgroundTask('; do
    if has "$escape" "$view"; then
        bad "SupervisedReadView uses $escape — the watch lease must die with the view and the foreground:"
        code "$escape" "$view"
    fi
done

# 5. Cadences. Ten seconds against a thirty-second lease leaves room for two
#    lost writes before a read somebody IS watching gets cut off. And the
#    narration follows the app's own three-second poll rather than inventing a
#    second timer discipline.
has '10_000_000_000' "$view" || bad "the lease heartbeat is no longer on a ten-second cadence"
has '3_000_000_000' "$view"  || bad "the narration poll is no longer on the app's three-second cadence"
has '3_000_000_000' "$session" \
    || bad "AnticipyApp's own poll cadence changed; the read screen now disagrees with the app it lives in"

# 6. The lease must EXIST before the extension can claim the job — it re-reads
#    watching_until before every action and refuses without one. So the first
#    beat is pushed the instant the job exists, not up to ten seconds later.
sed -n '/read.began(jobID: id)/,/^        }$/p' "$view" | grep -q 'reader.hold(id)' \
    || bad "the first watch-lease push no longer happens immediately after the job is created"

# 7. Coming back to the foreground must NOT resume a read that lapsed. Restarting
#    one silently is the same lie as never stopping it.
member 'private func narrate' "$view" | grep -q 'read.lapse()' \
    || bad "narrate no longer records a lapse, so returning to the app could silently resume a dead read"

# 7b. A STOP THAT WORKS MID-SENTENCE (one of the four load-bearing things on
#     this screen). Quitting the heartbeat alone means "stop within thirty
#     seconds", and anything she found in that window lands in the store having
#     never appeared on screen — which makes "I kept what you watched me find"
#     false in the one direction that matters. So Stop drops the lease into the
#     past, and so does the screen going away.
member 'func stop()' "$view" | grep -q 'release()' \
    || bad "Stop no longer drops the watch lease, so stopping means \"within thirty seconds\""
member 'func release()' "$view" | grep -q 'reader.drop(' \
    || bad "release() no longer ends the lease"
has 'onDisappear { read.release() }' "$view" \
    || bad "closing the screen mid-read no longer ends the lease immediately"
# And the drop must go BACKWARDS. Turn that into a positive interval and every
# sentence above becomes a lie while every test still passed.
sed -n '/func dropWatchLease/,/^    }$/p' "$session" | grep -q 'addingTimeInterval(-' \
    || bad "dropWatchLease no longer puts watching_until in the PAST, so Stop would extend the read instead of ending it"

# ------------------------------------------------------------------ the wiring

# 8. Every session call this screen depends on: declared on AnticipySession AND
#    actually called from here. Either half alone is decoration.
for call in 'startSupervisedRead' 'holdWatchLease' 'supervisedLines' 'forgetSupervisedFact' 'dropWatchLease'; do
    has "$call" "$view" || bad "SupervisedReadView never calls $call, so that half of the read does nothing"
    grep -q "func $call" "$session" \
        || bad "AnticipySession declares no $call — the read screen calls a method that does not exist"
done

# 9. The veto is SENT, not just hidden. design/day-zero.md §3: "A tap deletes it
#    and marks it never-re-derive" — draining a local array is half a promise.
member 'func forget(_ fact: Fact)' "$view" | grep -q 'reader.forget(' \
    || bad "forget(_:) no longer sends the veto, so a tapped fact would only be hidden"
# And the removal comes FIRST, so the tap feels instant and the write happens
# behind it — the shape AnticipySession.write already uses for job actions.
first=$(member 'func forget(_ fact: Fact)' "$view" \
        | grep -o 'facts.removeAll\|reader.forget(' | head -1)
[ "$first" = "facts.removeAll" ] \
    || bad "forget(_:) waits on the server before removing the fact, so the tap would stall"

# 10. NEVER A SPINNER THAT WAITS FOREVER. Every dead end reaches `failed` with a
#     sentence: no job created, nothing ever coming back from Chrome, and a job
#     that settled having read nothing.
dead=$(code 'read.failed(' "$view" | grep -c . || true)
[ "$dead" -ge 3 ] \
    || bad "only $dead dead ends say why; a read that cannot happen must say so, never breathe forever"

# 11. The screen never invents narration. Her lines come from `reader.poll` and
#     nowhere else; the only literal lines in the file live in the DEBUG
#     previews, which is where hand-written examples belong.
if sed '/^#if DEBUG/,$d' "$view" | grep -n 'say("\|found("' | grep -v ': *//' | grep -q .; then
    bad "shipping code puts words in her mouth; narration comes from reader.poll only:"
    sed '/^#if DEBUG/,$d' "$view" | grep -n 'say("\|found("' | grep -v ': *//'
fi

# 12. Only CONCLUSIONS travel (design/LOCAL-FIRST.md:9-11). The reader hands
#     back distilled lines and facts and nothing else, so there is no raw page
#     text channel for this screen to render or forward by accident.
grep -q 'let poll: (String) async -> (lines: \[String\], facts: \[String\])' "$view" \
    || bad "SupervisedReader.poll changed shape; anything beyond distilled lines and facts is the stream, not a conclusion"

# ------------------------------------------------------------- the entry point

# 13. Reachable from Home with a live session, or it can never run at all.
has 'SupervisedReadView(session: session)' "$home" \
    || bad "ContentView no longer opens the read screen with a live session"

# 14. Gated. An offer whose only button cannot work is the "confidently asserts
#     things that are not true" failure CONSUMER-READINESS §1 names.
gate=$(member 'private var mailReadOffer' "$home")
for cond in 'session.agentPaired' 'session.agentOnline' 'ContextGrants().granted(.mail)' 'showInterviewOffer'; do
    printf '%s\n' "$gate" | grep -q -- "$cond" || bad "mailReadOffer no longer checks $cond"
done
# The provocation: she has been TOLD what you live in all day (interview
# question 3). A clock is not a reason to ask somebody for their mail.
printf '%s\n' "$gate" | grep -q 'InterviewProgress().isAnswered("tools")' \
    || bad "mailReadOffer no longer waits until she has been told what you live in"
# And value first, from a real errand: a finished READ must not be what
# qualifies you to be offered your first read.
printf '%s\n' "$gate" | grep -q 'isErrand($0) && $0.status == "done"' \
    || bad "mailReadOffer no longer requires a finished ERRAND (day-zero.md phase 3: value BEFORE the ask)"

# 15. The answer itself must never be copied onto the phone. Interview answers
#     live in the brain's per-owner SQLite; InterviewProgress stores which
#     questions were answered and never the answers, because a second local copy
#     is the split-brain design/day-zero.md §3 already names as a defect.
grep -q 'func isAnswered' "$app/Interview.swift" \
    || bad "InterviewProgress.isAnswered is gone; the mail offer's gate has no source"
if grep -q 'answers\[' "$app/Interview.swift" || grep -q 'func answer(for' "$app/Interview.swift"; then
    bad "Interview.swift now stores answers on the phone. That is the split-brain day-zero.md §3 warns about."
fi

# 16. Not a fourth rounded rectangle (CONSUMER-FEEL-DIRECTION §6, §4 cut #3) —
#     her voice against the page, like its two siblings. It had a 2px accent
#     rule down its left edge until every golden bar came out of the product;
#     NOTHING replaced the rule, on purpose. A border, a fill or a surface put
#     here to "hold it together" is precisely the identical card §6 forbids, so
#     what is left holding it together is the serif display line and space.
card=$(member 'private var mailReadCard' "$home")
printf '%s\n' "$card" | grep -q 'RoundedRectangle' \
    && bad "the mail offer became a rounded-rectangle card; it is a bespoke hero, not a fourth identical row"
printf '%s\n' "$card" | grep -qE 'cardSurface|\.border\(|Theme\.accentDim' \
    && bad "the mail offer grew a surface, a border or the old accent rule back; it holds together with type and space or not at all"
printf '%s\n' "$card" | grep -q 'Theme.display(24)' \
    || bad "the mail offer lost the serif display line it shares with interviewOfferCard and browserOfferCard"
# The consent wording has ONE home. Two of those promises were untrue once
# already; a second copy of the ask is a second chance at that.
printf '%s\n' "$card" | grep -q 'ContextSource.mail.ask()' \
    || bad "the mail offer retypes the ask instead of reading ContextSource.mail.ask()"
# "Not now" is the canonical decline, so Settings can reopen it.
printf '%s\n' "$card" | grep -q 'session.declineContext(.mail)' \
    || bad "\"Not now\" no longer writes the canonical decline, so Settings could not reopen the door"

# 17. A read is not an errand. Left in the feed, a read somebody is watching
#     renders under "Waiting for your browser" — with the pairing offer possibly
#     stacked over it, telling them to pair the Chrome she is working in.
grep -q 'job.lane != "supervised_read"' "$home" \
    || bad "supervised reads are no longer excluded from the errand feed"

# 18. The old "not built yet" claim must be gone now that a reader exists — and
#     must not have been replaced by a claim the code cannot keep.
grep -q "the part of me that does the reading isn't built" "$view" \
    && bad "the screen still says the reader is not built, but it now has one"

[ "$fail" = "0" ] || exit 1
echo "supervised read: the lease dies with the view and the foreground, the veto is sent, the offer is earned"
