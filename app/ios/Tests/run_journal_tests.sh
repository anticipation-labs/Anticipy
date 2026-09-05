#!/bin/sh
# Checks for ListenJournal — the on-device record of what a listening session
# did, and the instrument a manual voice test is read with.
# Pure Foundation on purpose: no simulator, no scheme, no signing, no network.
#
#   sh app/ios/Tests/run_journal_tests.sh
#
# Exit code is the result. Non-zero means a case came back wrong.
#
# The wiring assertions below arrived with the call sites. Until those existed
# a check here would have failed for a reason that was not a defect, and a
# check reporting a failure the code did not commit is worse than no check.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

# These checks are worthless if nothing writes to the journal: an unread
# diagnostic is how "the test didn't complete" became undiagnosable in the
# first place. Prove the wiring before proving the logic.
listener="$app/Audio/PhoneListener.swift"
session="$app/AnticipyApp.swift"
if ! grep -q 'ListenJournal.shared.record(.sessionStarted)' "$listener"; then
    echo "A listening session no longer records that it started."
    echo "With no start line, a journal cannot say whether the microphone ever"
    echo "came up, which is the first thing a failed voice test must rule out."
    exit 2
fi
if ! grep -q 'ListenJournal.shared.record(.sessionStopped' "$listener"; then
    echo "Listening stops without saying why."
    echo "'It stopped' is the useless half of the report: the owner stopping it"
    echo "and iOS taking the microphone away read identically."
    exit 2
fi
if ! grep -q 'ListenJournal.shared.record(.recognizerSwapped' "$listener"; then
    echo "A recognizer is replaced without recording what drove it."
    echo "An error, Apple's task limit, a route change and the 120s rotation"
    echo "are indistinguishable afterwards, and they need different fixes."
    exit 2
fi
# Anchored on the record call like its siblings, and comment-stripped: the
# call is wrapped across two lines because it does not fit, so the newlines are
# folded first. Matching the bare case name against the raw file would pass on
# a surviving doc comment with both record calls deleted.
if ! grep -vE '^[[:space:]]*//' "$listener" | tr '\n' ' ' \
    | grep -q 'ListenJournal.shared.record( *\.flushed(reason:'; then
    echo "A flush no longer records its reason and word count."
    echo "That pair is the only evidence of the shard rate this work exists to"
    echo "reduce, and the count is all the journal may hold: never the words."
    exit 2
fi
if ! grep -q 'ListenJournal.shared.record(.posted(' "$session"; then
    echo "An event POST no longer records its outcome."
    echo "A session that heard everything and delivered nothing looked exactly"
    echo "like a microphone that heard nothing at all."
    exit 2
fi
# And a line sent from the QUEUE names the ear that heard it. The buffered
# line kept its source on disk for the wire; until 2026-09-05 the journal
# dropped it here, so the per-ear count on the Listening screen was honest
# only on a day with no outage. Folded first because the call wraps.
if ! grep -vE '^[[:space:]]*//' "$session" | tr '\n' ' ' | tr -s ' ' \
    | grep -q '\.sentFromQueue(from: \.init(wireName: line\.source'; then
    echo "A queued line is sent without recording which ear heard it."
    echo "Every line delivered late then vanishes from its ear's count, and a"
    echo "day the pendant spent mostly offline reads as a day it barely spoke."
    exit 2
fi
# The battery, and the guard that keeps it from destroying the record it lives
# in. The thing that reads it is the 4-SECOND WATCHDOG, so an unguarded write
# there is fifteen lines a minute — measured on this codebase three commits ago
# as fully evicting the 400-line ring in twenty-seven minutes and both 256 KB
# files in about five hours of outage, which deletes the one
# `sessionStopped cause: interruption` line that explains the whole day.
#
# ANCHORED ON THE FUNCTION, AND GUARDED AGAINST ITS RENAME, for the reason the
# churn leg below it now is: an awk range that matches nothing produces an empty
# string, finds no journal write in it, and says so cheerfully. Emptiness is the
# finding.
if ! grep -q 'ListenJournal.shared.record(' "$listener" \
    || ! grep -vE '^[[:space:]]*//' "$listener" | tr '\n' ' ' \
        | grep -q '\.batteryRead(percent:'; then
    echo "Listening no longer records what it costs."
    echo "An always-on microphone, a speech recognizer and a 4-second timer are"
    echo "a real draw, and with no reading in the journal the tally folds zero"
    echo "and the Listening screen reports \"Not recorded\" forever — the whole"
    echo "instrument green end to end and measuring nothing."
    exit 2
fi
dog=$(awk '/private func startWatchdog/,/RunLoop.main.add/' "$listener" \
    | sed '/^[[:space:]]*\/\//d')
if [ -z "$dog" ]; then
    echo "This gate can no longer find startWatchdog's body."
    echo "The rule below then reads an empty string and passes on nothing. If the"
    echo "method was renamed, rename it here too; what is being protected is the"
    echo "4s tick that would otherwise write fifteen battery lines a minute."
    exit 2
fi
# THE TICK GOES THROUGH ONE READER, WITH THE CHURN RULE ON. Since 2026-09-05
# the watchdog and the session boundaries share `recordBatteryReading`; the
# tick must pass `boundary: false` (the churn rule) and never `true`, and the
# reader itself must ask `shouldRecord` before it writes. Three legs, each red
# on emptiness rather than on absence.
if ! printf '%s\n' "$dog" | grep -q 'recordBatteryReading(boundary: false)'; then
    echo "The watchdog no longer reads the battery through recordBatteryReading"
    echo "with the churn rule on."
    echo "That tick runs every four seconds for as long as listening is on, so"
    echo "an unguarded write is fifteen identical lines a minute and the whole"
    echo "ring gone in twenty-seven — including the line that says a call took"
    echo "the microphone."
    exit 2
fi
if printf '%s\n' "$dog" | grep -q 'recordBatteryReading(boundary: true)'; then
    echo "The watchdog passes boundary: true, which switches the churn rule off"
    echo "on a 4-second tick. That is fifteen identical lines a minute."
    exit 2
fi
reader=$(awk '/private func recordBatteryReading\(boundary: Bool\)/,/^    }$/' "$listener" \
    | sed '/^[[:space:]]*\/\//d')
if [ -z "$reader" ]; then
    echo "This gate can no longer find recordBatteryReading's body."
    echo "If it was renamed, rename it here too; what is protected is that the"
    echo "one reader asks shouldRecord before it writes."
    exit 2
fi
guard=$(printf '%s\n' "$reader" | grep -n 'shouldRecord' | head -1 | cut -d: -f1)
write=$(printf '%s\n' "$reader" | grep -n '\.batteryRead(' | head -1 | cut -d: -f1)
if [ -z "$guard" ] || [ -z "$write" ] || [ "$guard" -gt "$write" ]; then
    echo "recordBatteryReading writes a reading without first asking whether"
    echo "it has already said this. Go through BatteryReadingPolicy.shouldRecord."
    exit 2
fi
echo "the battery is recorded when it changes, not once per watchdog tick"

# AND AT THE BOUNDARIES, where the churn rule is off on purpose: the reading
# stamped with a start opens the window the tally measures drain over, and
# the one stamped with a stop closes it. Without the stop reading the stretch
# after the last CHANGE is never measured and a five-minute test folds to
# "Nothing to compare yet". The start line is followed by one, and the owner's
# stop is preceded by one, in that order.
started=$(printf '%s\n' "$(awk '/private func begin\(\)/,/^    }$/' "$listener" | sed '/^[[:space:]]*\/\//d')")
if [ -z "$started" ]; then
    echo "This gate can no longer find begin()."; exit 2
fi
s_line=$(printf '%s\n' "$started" | grep -n 'record(.sessionStarted)' | head -1 | cut -d: -f1)
s_read=$(printf '%s\n' "$started" | grep -n 'recordBatteryReading(boundary: true)' | head -1 | cut -d: -f1)
if [ -z "$s_line" ] || [ -z "$s_read" ] || [ "$s_read" -lt "$s_line" ]; then
    echo "Listening starts without a battery reading stamped with the start."
    echo "The window the tally measures drain over then opens at the first"
    echo "CHANGE, not at the start, and a short session brackets nothing."
    exit 2
fi
stopped=$(printf '%s\n' "$(awk '/^    func stop\(\)/,/watchdog\?\.invalidate\(\)/' "$listener" | sed '/^[[:space:]]*\/\//d')")
if [ -z "$stopped" ]; then
    echo "This gate can no longer find stop()."; exit 2
fi
e_line=$(printf '%s\n' "$stopped" | grep -n 'sessionStopped(cause: .owner)' | head -1 | cut -d: -f1)
e_read=$(printf '%s\n' "$stopped" | grep -n 'recordBatteryReading(boundary: true)' | head -1 | cut -d: -f1)
if [ -z "$e_line" ] || [ -z "$e_read" ] || [ "$e_read" -gt "$e_line" ]; then
    echo "Listening stops without a battery reading stamped with the stop, before it."
    echo "The last stretch of every session — from the last change to the stop —"
    echo "is then never measured, in the direction that makes listening look"
    echo "costly. A reading stamped with a stop sorts before it in the fold."
    exit 2
fi
echo "the battery is read at the start and the stop, so the window is closed"

# ---------------------------------------------------------------- privacy
# THE JOURNAL IS EXPORTABLE FROM SETTINGS, so anything written into it leaves
# the phone on a person's tap, and `ListeningDiagnosticsView` ships in RELEASE
# so it leaves a STRANGER's phone. design/LOCAL-FIRST.md governs this, and it is
# the load-bearing claim behind that screen shipping at all.
#
# -- WHAT THIS SECTION USED TO BE, AND WHY IT IS NOT THAT ANY MORE ----------
#
# It was a SCAN. `ListenEvent` declared three free-form `String` payloads, so
# this file derived them, found every expression flowing into one, and judged
# each against an allowlist. Five hardening passes did that. Every one closed
# its findings and leaked at a new layer — two leaks, then four, then two, then
# EIGHT (`.superpowers/sdd/privacy-gate-fifth.md`).
#
# The pattern in those sixteen leaks is worth stating, because it is the reason
# for the rewrite. THIRTEEN ATTACKS AIMED AT A RULE BOUNCED. Not one rule was
# wrong. What gave way every single time was the layer underneath — the finder
# that decided which calls a rule ran on, the derivation that decided which
# channels existed, the allowlist that decided which expressions were vouched
# for. `glue()` stripped `+`, so `f + acts.sentence` reduced to an allowlisted
# name. `channels.awk` tested `== "String"` literally, so `String?`, `String!`,
# `Swift.String`, `Substring` and `_ text: String` were skipped in silence —
# FAILING TO UNDERSTAND A LINE WAS A PASS, the exact inversion the same commit
# had just fixed one layer down. An Int on the allowlist was flipped to String
# and carried the whole transcript through a vouched-for chain.
#
# The one thing that held under every attack was a TYPE. `ListenSessionFacts`
# was attacked five ways and three of the mutations did not compile.
#
# So the surface was made small enough to stop scanning. `ListenEvent` declares
# NO `String` payload at all: every case carries an Int, a Bool or a closed enum
# declared beside it, and the words on disk are chosen by `describe` from those.
# There is no channel left to put a sentence into.
#
# What is checked below is that THIS PROPERTY HOLDS — four questions, each of
# which goes red when it cannot be answered rather than when it happens to find
# something:
#
#   1. every ListenEvent payload is a CLOSED type, recursively;
#   2. `record` is the only way into the journal, and its state is private;
#   3. every renderer says only what its own case arm handed it;
#   4. the journal's source names still match the ones stamped on the wire.
#
# THE FAILURE THAT PROVED THIS WORTH DOING. The version of this section that
# shipped before the types landed derived its channel list and, finding none,
# printed "This gate can no longer find a single String payload on ListenEvent
# … it was about to allowlist nothing and call the journal clean" and exited 2.
# It was right to. Had it been written the obvious way — no channels, therefore
# nothing to check, therefore clean — the typed refactor would have silently
# disarmed the privacy gate and every run afterwards would have reported green
# over an unchecked journal. That refusal is preserved below, aimed at the new
# question: a missing enum, an unreadable case, an unfindable renderer and an
# empty member list are each a red leg with a sentence attached.
journal="$app/Audio/ListenJournal.swift"
[ -f "$journal" ] || { echo "ListenJournal.swift is gone; there is nothing to check."; exit 2; }
factsfile="$app/Audio/ListenSessionFacts.swift"
if [ ! -f "$factsfile" ]; then
    echo "ListenSessionFacts.swift is gone."
    echo "It is the payload of `.sessionFacts` and the only thing saying the"
    echo "session line cannot carry speech."
    exit 2
fi
capture="$app/Audio/CaptureSourcePolicy.swift"
[ -f "$capture" ] || { echo "CaptureSourcePolicy.swift is gone; the wire names cannot be checked."; exit 2; }
# A leg that CANNOT be tested FAILS — the same rule the overnight gates run on.
# The alternative is this whole section vanishing on a machine without python3
# and the suite still printing its closing line.
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is not on PATH, so the payload derivation cannot run."
    echo "That derivation is the whole privacy claim for this journal now. A"
    echo "missing tool is a red leg, never a skipped one."
    exit 2
fi
python3 "$here/journal_payloads.py" "$journal" "$factsfile" "$capture" || exit 2

# ------------------------------------------------- and the call sites, still
# A BACKSTOP, NOT THE CLAIM. With no String payload left there is nothing for
# an expression to flow INTO, so this no longer has to be complete — which is
# the point, because completeness over an unbounded surface is what failed
# sixteen times. It stays because it is cheap and it reads the one thing the
# types cannot: whether somebody is computing a journal argument OUT of speech
# (`.buffersDropped(count: partial.count)` counts words, which is fine;
# `partial` appearing at all is worth a human look).
cat > "$out/journalwrites.awk" <<'AWK'
# WHICH CALL TO READ comes in through the environment as a REGEX ending in its
# open paren.
#
# A LITERAL `ListenJournal.shared.record(` IS WHAT THIS USED TO LOOK FOR, and
# two working leaks came of it. `ListenJournal` ⏎ `.shared` ⏎ `.record(.noted(
# line))` contains that text on no line at all, and `let sink = ListenJournal
# .shared` then `sink.record(...)` never contains it either. The anchor is the
# EVENT, derived from the enum: whatever the sink is called and however it is
# reached, a journal write has to build a `ListenEvent` case.
function stripped(l,  t) { t = l; sub(/^[ \t]*/, "", t); return t }
# A `switch` arm's PATTERN, and only the pattern.
#
# THIS USED TO DISCARD THE WHOLE LINE. `if (!inCall && stripped(s) ~ /^case /)
# next` was written for `case .noted(let fact):`, which reads an event apart
# rather than building one — but it threw away EVERY line beginning with
# `case `, so an ordinary Swift arm:
#
#     case .ceiling: ListenJournal.shared.record(.noted(line))
#
# was never shown to a single rule, and the suite exited 0 with all checks
# passing (leak C1 of the fifth pass). The pattern ends at the first colon
# OUTSIDE parentheses — which is what keeps `case .sessionStopped(cause: let c):`
# and `case .noted(let fact):` discarded while the arm's STATEMENTS are read.
function afterCasePattern(s,   i, c, d, inStr) {
  if (stripped(s) !~ /^(case|default)[ \t:]/) return s
  d = 0; inStr = 0
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == "\"") { inStr = !inStr; continue }
    if (inStr) continue
    if (c == "(" || c == "[") d++
    else if (c == ")" || c == "]") d--
    else if (c == ":" && d == 0) return substr(s, i + 1)
  }
  return ""
}
BEGIN { call = ENVIRON["CALL"]; skip = ENVIRON["SKIP"] }
# AN EXACT BASENAME, never a substring (leak M1). `index(FILENAME, skip) > 0`
# exempted `ListenJournal.swiftHelpers.swift` — and anything else somebody
# named with the skipped file as a prefix — from the entire scan.
FNR == 1 {
  base = FILENAME
  sub(/^.*\//, "", base)
  skipping = (skip != "" && base == skip)
}
skipping { next }
{
  s = $0
  if (stripped(s) ~ /^\/\//) next
  if (!inCall) s = afterCasePattern(s)
  if (!inCall) {
    if (!match(s, call)) next
    inCall = 1; depth = 0; buf = ""
    s = substr(s, RSTART)
  }
  sub(/^[ \t]+/, "", s)
  buf = buf (buf == "" ? "" : " ") s
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == "(") depth++
    else if (c == ")") {
      depth--
      if (depth == 0) { print FILENAME "\t" buf; inCall = 0; break }
    }
  }
}
END { if (inCall) print FILENAME "\tUNTERMINATED\t" buf }
AWK
read_calls() {
    find "$app" -name '*.swift' -print0 \
        | CALL="$1" SKIP="$2" xargs -0 -n1 awk -f "$out/journalwrites.awk"
}
# The case names come from the enum, never from a list typed here, so a renamed
# case renames the anchor instead of quietly emptying the search.
cases=$(awk '
    /^enum ListenEvent/ { inEnum = 1; next }
    inEnum && /^}/ { inEnum = 0 }
    !inEnum { next }
    { s = $0; sub(/^[ \t]*/, "", s)
      if (s ~ /^\/\//) next
      if (s !~ /^case [A-Za-z_]/) next
      sub(/^case[ \t]+/, "", s)
      sub(/[( \t].*$/, "", s)
      print s }' "$journal" | sort -u | tr '\n' '|' | sed 's/|$//')
if [ -z "$cases" ]; then
    echo "No ListenEvent case could be named, so the call-site scan has nothing"
    echo "to look for and would read the whole app as clean."
    exit 2
fi
calls=$(read_calls "\\.(record|$cases)[ \t]*\\(" ListenJournal.swift)
if [ -z "$calls" ]; then
    echo "Nothing in the app builds a ListenEvent."
    echo "Either the journal has stopped being written or this scan has broken."
    echo "Both are the same failure: an unread diagnostic, vouched for by a"
    echo "green gate."
    exit 2
fi
if printf '%s\n' "$calls" | grep -q 'UNTERMINATED'; then
    echo "A ListenJournal record call could not be read to its end."
    echo "Unbalanced parentheses inside a string literal are the usual cause."
    exit 2
fi
# NAMED DANGERS, anywhere in the call. `line.split(...).count` is a word COUNT
# and deliberately not matched: counting speech is the whole design.
if printf '%s\n' "$calls" | grep -nE 'partial|transcript|bestTranscription|formattedString|pendingTail|cursor\.pending|localizedDescription|serverMessage|\.message|\\\(error|error\.[A-Za-z]'; then
    echo ""
    echo "A journal write is computed from the owner's speech, or from a server"
    echo "sentence built out of it. The journal is exportable from Settings and"
    echo "the diagnostics screen ships in RELEASE, so this leaves a stranger's"
    echo "phone on a tap. Record a COUNT, a status, or an error shape."
    exit 2
fi
echo "every journal write is a count, a status or a closed system fact"

# And the safe reduction must still be the thing standing between them.
if ! grep -q 'postFailureShape(error)' "$session"; then
    echo "A post failure no longer goes through postFailureShape."
    echo "That function is the only thing turning a refusal into a status code"
    echo "instead of the server's sentence about the owner's own words."
    exit 2
fi

# ------------------------------------------------------------ the noted spam
# NO WRITE ABOVE THE 0 Hz GUARD MAY REPEAT ITSELF. The two `.noted` calls in
# configureAndStartEngine sat three lines above a guard whose own comment reads
# "Recorded once per outage, not once per watchdog tick: the 4s watchdog retries
# this path for as long as the call lasts, and a journal that spends all 400 of
# its lines saying the same thing has evicted the session it was meant to
# explain." They did not obey it. Measured: 15 identical lines a minute, 30 in
# low power; the ring fully evicted in 27 minutes and both 256 KB files in about
# five hours, so the one interruption line that explains the day rotates away
# and the screen reports a blank, healthy day.
#
# THIS LEG USED TO REQUIRE `if !suspended`, and that was the wrong instrument
# for the right rule. It bought silence for the whole outage, including the tick
# capture comes BACK — the one moment these facts are worth having, because that
# is when the session may have become something else (a call that began on
# Bluetooth ending on speaker). Comparing against the last line recorded kills
# the 210 repetitions and keeps every sentence that is new, so the rule below
# now asks for the comparison rather than for the flag.
#
# ANCHORED ON A FUNCTION NAME, AND THEREFORE GUARDED AGAINST ITS RENAME. A
# reviewer renamed `configureAndStartEngine` to `rebuildCaptureChain` and put
# the pre-fix churn back — an unguarded `.noted(facts)` on every watchdog tick.
# The awk range matched nothing, `pre` came back empty, and `set -e` killed this
# script on the empty pipeline: exit 1, no output, the regression that evicts
# the ring in 27 minutes reported as a shell accident. Emptiness is now the
# finding it always was, with a sentence attached.
pre=$(awk '/private func configureAndStartEngine/,/guard format.sampleRate/' "$listener" \
    | sed '/^[[:space:]]*\/\//d')
if [ -z "$pre" ]; then
    echo "This gate can no longer find configureAndStartEngine's opening lines."
    echo "The rule below then reads an empty string, finds no journal write in it"
    echo "and says so cheerfully. If the method was renamed, rename it here too;"
    echo "the thing being protected is the 4s watchdog path that writes fifteen"
    echo "identical lines a minute for the length of a phone call."
    exit 2
fi
if printf '%s\n' "$pre" | grep -q 'ListenJournal.shared.record'; then
    guarded=$(printf '%s\n' "$pre" | grep -n '!= lastSessionFacts' | head -1 | cut -d: -f1)
    firstwrite=$(printf '%s\n' "$pre" | grep -n 'ListenJournal.shared.record' | head -1 | cut -d: -f1)
    if [ -z "$guarded" ] || [ "$guarded" -gt "$firstwrite" ]; then
        echo "configureAndStartEngine writes to the journal without first asking"
        echo "whether it has already said this."
        echo "The 4s watchdog calls this method on every tick of a phone call, so"
        echo "an unguarded write here is fifteen identical lines a minute and the"
        echo "whole ring gone in twenty-seven — including the one line that says"
        echo "a call took the microphone."
        exit 2
    fi
fi
echo "the session facts are recorded when they change, not once per watchdog tick"

# THE TAP CLOSURE STAYS JOURNAL-FREE. It runs on the audio thread, and the
# journal now writes to a FILE. A record() call in there would park audio
# behind a disk write — the instrument built to explain dropped speech becoming
# a way to drop it. Dropped-buffer counting is a plain integer there, reported
# by the watchdog from the main queue instead. Asserted on source shape,
# the way run_flush_policy_tests.sh asserts its own.
tap=$(awk '/installTap\(onBus: 0/,/^        }$/' "$listener")
if [ -z "$tap" ]; then
    echo "This gate can no longer find the audio tap closure."
    echo "An empty block contains no ListenJournal call, so the rule below would"
    echo "pass without reading anything — the audio thread free to park behind a"
    echo "disk write again, vouched for by a green line of output."
    exit 2
fi
if printf '%s' "$tap" | grep -q 'ListenJournal'; then
    echo "The audio tap closure now writes to the journal."
    echo "That closure runs on the audio thread and the journal touches a file."
    echo "Count into an integer there and let the watchdog report it."
    exit 2
fi
echo "the journal is written on start, stop, swap, flush and post"
echo "the audio tap stays journal-free"

swiftc -O \
    "$app/Audio/ListenJournal.swift" \
    "$app/Audio/ListenSessionFacts.swift" \
    "$here/ListenJournalTests.swift" \
    -o "$out/journaltests"
"$out/journaltests"
