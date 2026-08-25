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
if printf '%s\n' "$dog" | grep -q 'batteryRead'; then
    guard=$(printf '%s\n' "$dog" | grep -n 'shouldRecord' | head -1 | cut -d: -f1)
    write=$(printf '%s\n' "$dog" | grep -n 'batteryRead' | head -1 | cut -d: -f1)
    if [ -z "$guard" ] || [ "$guard" -gt "$write" ]; then
        echo "The watchdog records a battery reading without first asking whether"
        echo "it has already said this."
        echo "That tick runs every four seconds for as long as listening is on, so"
        echo "an unguarded write is fifteen identical lines a minute and the whole"
        echo "ring gone in twenty-seven — including the line that says a call took"
        echo "the microphone. Go through BatteryReadingPolicy.shouldRecord."
        exit 2
    fi
fi
echo "the battery is recorded when it changes, not once per watchdog tick"

# ---------------------------------------------------------------- privacy
# THE JOURNAL IS EXPORTABLE FROM SETTINGS, so anything written into it leaves
# the phone on a person's tap, and `ListeningDiagnosticsView` ships in RELEASE
# so it leaves a STRANGER's phone. design/LOCAL-FIRST.md governs this, and it is
# the load-bearing claim behind that screen shipping at all.
#
# This used to grep one file for one keyword: `detail:` in AnticipyApp.swift.
# `.noted(String)` takes free-form prose, lives in PhoneListener.swift, and was
# protected by a comment. An auditor traced all seventeen record call sites and
# confirmed no speech reaches the journal today — every `.noted` producer is a
# system constant or an integer. That is not the point. The point is that
# `.noted(self.partial)`, added tomorrow to chase a recognizer bug, would have
# shipped green.
#
# So: EVERY record call site, in EVERY file, checked two ways.
cat > "$out/journalwrites.awk" <<'AWK'
function stripped(l,  t) { t = l; sub(/^[ \t]*/, "", t); return t }
{
  s = $0
  if (stripped(s) ~ /^\/\//) next
  if (!inCall) {
    p = index(s, "ListenJournal.shared.record(")
    if (p == 0) next
    inCall = 1; depth = 0; buf = ""
    s = substr(s, p + length("ListenJournal.shared.record"))
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
calls=$(find "$app" -name '*.swift' -print0 | xargs -0 -n1 awk -f "$out/journalwrites.awk")
if [ -z "$calls" ]; then
    echo "No ListenJournal.shared.record call sites found at all."
    echo "Either the journal has stopped being written or this scan has broken."
    echo "Both are the same failure: an unread diagnostic, vouched for by a"
    echo "green gate."
    exit 2
fi
if printf '%s\n' "$calls" | grep -q 'UNTERMINATED'; then
    echo "A ListenJournal.shared.record call could not be read to its end."
    echo "The privacy scan below cannot see what that call writes, so it cannot"
    echo "say the journal is free of speech. Unbalanced parentheses inside a"
    echo "string literal are the usual cause."
    exit 2
fi
# 1. NAMED DANGERS, anywhere in the call. `.noted(self.partial)` and
#    `detail: error.localizedDescription` carry no interpolation at all, so the
#    allowlist below would never see them. `line.split(...).count` is a word
#    COUNT and deliberately not matched: counting speech is the whole design.
if printf '%s\n' "$calls" | grep -nE 'partial|transcript|bestTranscription|formattedString|pendingTail|cursor\.pending|localizedDescription|serverMessage|\.message|\\\(error|error\.[A-Za-z]'; then
    echo ""
    echo "A journal write carries the owner's speech, or a server sentence built"
    echo "from it. The journal is exportable from Settings and the diagnostics"
    echo "screen ships in RELEASE, so this leaves a stranger's phone on a tap."
    echo "Record a COUNT, a status, or an error shape. Never the words."
    exit 2
fi
# 2. EVERY VALUE THAT REACHES A JOURNAL STRING, allowlisted. A denylist can only
#    catch the dangers somebody already thought of, and a mutation proved that:
#    `detail: lines.joined()` — the whole log, joined — carries no named danger
#    and no interpolation at all, and sailed through the denylist above.
#
#    So the rule is inverted. A `.noted(...)` argument and a `detail:` value must
#    be string literals, whose interpolations are on the list below, or else be
#    named here as a safe expression. Anything else fails, including the shapes
#    nobody has thought of yet. Adding to either list is a deliberate edit with a
#    reason attached, which is exactly the review moment this gate is for.
cat > "$out/journalstrings.awk" <<'AWK'
# Interpolations are checked on their own below, so blanking them first makes
# what is left an ordinary string literal with no parentheses in it — which is
# what lets the quote/paren scanner underneath be exact rather than nearly.
function blanked(t,   out, i, n, depth, c) {
  out = ""; i = 1; n = length(t)
  while (i <= n) {
    if (substr(t, i, 2) == "\\(") {
      out = out "\"\""; depth = 0; i++
      while (i <= n) {
        c = substr(t, i, 1)
        if (c == "(") depth++
        else if (c == ")") { depth--; if (depth == 0) { i++; break } }
        i++
      }
    } else { out = out substr(t, i, 1); i++ }
  }
  return out
}
# What is left of an expression once every string literal is taken out of it.
# Empty means the value is literal text and nothing else. `+` and spaces survive
# because joining two literals is safe; an identifier surviving is the finding.
function glue(e,   out, i, n, c, inStr) {
  n = length(e); inStr = 0; out = ""
  for (i = 1; i <= n; i++) {
    c = substr(e, i, 1)
    if (c == "\"") { inStr = !inStr; continue }
    if (!inStr) out = out c
  }
  gsub(/[ \t+]/, "", out)
  return out
}
# THE FILE AND THE EXPRESSION TOGETHER, never the expression alone. A bare name
# on the allowlist is a pass handed to every file at once, and `facts` is an
# ordinary enough English word that five other bindings here already carry it:
# the context facts in `sendContextFacts`, the supervised reader's list and the
# interview workflow's dictionary in AnticipyApp.swift, and two more in
# SupervisedReadView.swift. None of those is a String today, which is the only
# reason none of them can be journalled — a type accident, standing in for a
# rule. A reviewer added a method to AnticipyApp.swift whose body was `let facts
# = words` and `ListenJournal.shared.record(.noted(facts))`, and this gate
# exited 0. The pair is what was reasoned about, so the pair is what is written.
function report(file, kind, expr,   g) {
  g = glue(expr)
  if (g == "") return
  if ((file "#" g) ~ ENVIRON["SAFE_EXPRESSIONS"]) return
  print file "\t" kind "\t" expr
}
{
  tab = index($0, "\t")
  file = substr($0, 1, tab - 1)
  t = blanked(substr($0, tab + 1))
  n = length(t)
  # `.noted(` — the argument, to its matching close paren.
  for (i = 1; i <= n; i++) {
    if (substr(t, i, 7) != ".noted(") continue
    depth = 1; expr = ""; inStr = 0
    for (j = i + 7; j <= n; j++) {
      c = substr(t, j, 1)
      if (c == "\"") inStr = !inStr
      else if (!inStr) {
        if (c == "(") depth++
        else if (c == ")") { depth--; if (depth == 0) break }
      }
      expr = expr c
    }
    report(file, ".noted", expr)
  }
  # `detail:` — the value, to the top-level comma or close paren that ends it.
  for (i = 1; i <= n; i++) {
    if (substr(t, i, 7) != "detail:") continue
    depth = 0; expr = ""; inStr = 0
    for (j = i + 7; j <= n; j++) {
      c = substr(t, j, 1)
      if (c == "\"") inStr = !inStr
      else if (!inStr) {
        if (c == "(") depth++
        else if (c == ")") { if (depth == 0) break; depth-- }
        else if (c == "," && depth == 0) break
      }
      expr = expr c
    }
    report(file, "detail:", expr)
  }
}
AWK
# TWO PAIRS, and each one names the file it was reasoned about in.
#
# `AnticipyApp.swift#source.wireName` — the wire name of an event source,
# "voice" or "photo", chosen from a fixed set on the device.
#
# `PhoneListener.swift#facts` — the session-facts sentence, held in a variable
# because it is compared with the last one recorded before being written. That
# one is a promise, not a fact, and rule 3b below is what pays for it.
safe_values='/AnticipyApp\.swift#source\.wireName$|/Audio/PhoneListener\.swift#facts$'
rogue=$(printf '%s\n' "$calls" | SAFE_EXPRESSIONS="$safe_values" \
    awk -f "$out/journalstrings.awk" | sort -u)
if [ -n "$rogue" ]; then
    echo "A journal write hands over a value this gate has not been told is safe:"
    printf '%s\n' "$rogue"
    echo ""
    echo "What goes in the journal leaves the phone when the log is shared, and"
    echo "the diagnostics screen ships in RELEASE. Write a literal sentence with"
    echo "a count or a status interpolated into it, or name the FILE AND the"
    echo "expression in this file and say why it can never carry what the owner"
    echo "said. A name on its own is a pass for every file that has a variable"
    echo "by that name, which is how \`facts\` in AnticipyApp.swift got one."
    exit 2
fi
# 3. AND EVERY INTERPOLATION INSIDE THOSE LITERALS. Paired with a file for the
#    same reason rule 2 is: `dropped` is a bare name, and `TranscriptCursor`
#    has a `dropped` of its own that counts WORDS cut from a transcript. This
#    list may not hand that one a pass on the strength of an argument made
#    about a buffer counter in another file.
allowed='/Audio/PhoneListener\.swift#(dropped|session\.category\.rawValue|session\.mode\.rawValue)$|/AnticipyApp\.swift#Self\.postFailureShape\(error\)$'
cat > "$out/interpolations.awk" <<'AWK'
{
  tab = index($0, "\t")
  file = substr($0, 1, tab - 1)
  text = substr($0, tab + 1)
  for (i = 1; i < length(text); i++) {
    if (substr(text, i, 2) != "\\(") continue
    depth = 0; expr = ""
    for (j = i + 1; j <= length(text); j++) {
      c = substr(text, j, 1)
      if (c == "(") { depth++; if (depth == 1) continue }
      else if (c == ")") { depth--; if (depth == 0) break }
      expr = expr c
    }
    print file "\t" expr
  }
}
AWK
# Through ENVIRON rather than -v: awk expands escape sequences in a -v value,
# so the backslashes this regex is made of never survive the assignment.
rogue=$(printf '%s\n' "$calls" | awk -f "$out/interpolations.awk" | sort -u \
    | ALLOWED="$allowed" awk -F'\t' '($1 "#" $2) !~ ENVIRON["ALLOWED"]')
if [ -n "$rogue" ]; then
    echo "A journal write interpolates something this gate has not been told is safe:"
    printf '%s\n' "$rogue"
    echo ""
    echo "Every value interpolated into a journal line leaves the phone when the"
    echo "log is shared. If it is a count, a status or a system constant, add it"
    echo "to the allowlist in this file and say why. If it is derived from what"
    echo "the owner said, it does not belong in the journal at all."
    exit 2
fi
# 3b. AND EVERY NAME ON EITHER LIST EARNS ITS PLACE, LINE BY LINE.
#
#     Two of the entries above are variables — `facts` and `dropped` — so the
#     only thing standing between them and an exportable log is whatever gave
#     them their value. THE VERSION OF THIS RULE THAT SHIPPED DID NOT CHECK
#     THAT. It grepped one file for `facts (=|+=)` and ran the matches through
#     the INTERPOLATION check alone. A reviewer walked past it twice and both
#     leaks exited 0:
#
#       facts += self.partial          no `\(`, so the interpolation pass had
#                                      nothing to look at, and `glue()` — the
#                                      machinery invented at rule 2 for exactly
#                                      a value carrying "no named danger and no
#                                      interpolation at all" — was never run on
#                                      a build line at all.
#       facts.append(self.partial)     the grep did not even match it.
#
#     A third, `let facts = words` in any other file, was never this rule's to
#     catch — the grep only ever opened PhoneListener.swift — and is closed by
#     the (file, name) pairing at rule 2 instead. This rule is what makes the
#     PhoneListener half of that pair mean anything:
#
#       - every non-comment line of that file naming the identifier must be a
#         shape this scan can read — a value given to it, a plain read of it, or
#         a journal write spending it. A method called ON it is none of those;
#       - every value given to it goes through BOTH passes a journal literal
#         gets, `journalstrings.awk` and `interpolations.awk`, by being handed
#         to those exact two scripts. "Checked as if it had been written out at
#         the call" is now a property of the code below, not a claim in a
#         comment;
#       - a value continued on the next line is READ TO ITS END and checked
#         whole. `var facts = "…" ⏎ + self.partial` was the one hole the old
#         rule's own comment admitted it had, and admitting it is not closing
#         it. What still cannot be read to an end fails;
#       - finding nothing fails. An exception whose subject has been renamed
#         away is a check reporting on an empty search, and the twin of this
#         file's churn leg — anchored on `configureAndStartEngine`, and proved
#         by a reviewer to say nothing useful once that name moved.
cat > "$out/namelines.awk" <<'AWK'
function stripped(l,  t) { t = l; sub(/^[ \t]*/, "", t); return t }
# The whole file first, because a value may be continued on the lines after the
# one that starts it and a scan reading one line at a time cannot follow that.
{ src[NR] = $0 }
END {
  name = ENVIRON["NAME"]
  bare = "(^|[^A-Za-z0-9_.])" name "([^A-Za-z0-9_]|$)"
  touch = "(^|[^A-Za-z0-9_.])" name "[ \t]*[.[]"
  inout = "&" name "([^A-Za-z0-9_]|$)"
  for (i = 1; i <= NR; i++) {
    s = src[i]
    if (stripped(s) ~ /^\/\//) continue
    if (s !~ bare) continue
    seen++
    # A VALUE GIVEN TO IT, asked first so that a write and a journal call
    # sharing one line cannot hide behind the call.
    v = ""
    if (match(s, "(^|[^A-Za-z0-9_.])" name "[ \t]*\\+?=")) {
      v = substr(s, RSTART + RLENGTH)
      if (substr(v, 1, 1) == "=") v = ""   # a comparison, not a write
    }
    if (v != "") {
      assigns++
      # Swift continues an expression on the next line when that line opens
      # with an operator, so `+ self.partial` under a literal is part of this
      # value and is read in here rather than left unexamined.
      for (j = i + 1; j <= NR; j++) {
        t = stripped(src[j])
        if (t ~ /^\/\//) continue
        if (t !~ /^[+.?:,)]/) break
        v = v " " t
      }
      # `if <cond> { facts += "…" }` is how the low power clause is written, so
      # the block's closing brace arrives with the value and is not part of it.
      sub(/[ \t]*}[ \t]*$/, "", v)
      sub(/^[ \t]+/, "", v); sub(/[ \t]+$/, "", v)
      tmp = v; quotes = gsub(/"/, "", tmp)
      if (v == "" || quotes % 2 == 1 || v ~ /[+(,][ \t]*$/)
        print "BAD\t" FILENAME ":" i ": " s "\tthe value cannot be read to an end"
      else
        print "VALUE\t" v
      continue
    }
    # SPENT ON THE JOURNAL. Rules 1-3 above read those calls in full, across
    # the continuations this classification does not try to follow.
    if (s ~ /ListenJournal\.shared\.record\(|\.noted\(|detail:/) { spent++; continue }
    # READ AND NOTHING ELSE is all that is left. A method called on it or an
    # inout pass is a write whose inside this scan cannot see.
    if (s ~ touch || s ~ inout)
      print "BAD\t" FILENAME ":" i ": " s "\tsomething is done to it that this scan cannot follow"
  }
  if (seen == 0) print "BAD\t" FILENAME "\tno line in this file names it at all"
  else if (assigns == 0) print "BAD\t" FILENAME "\tnothing in this file gives it a value"
  else if (spent == 0) print "BAD\t" FILENAME "\tit never reaches a journal write from here"
}
AWK
# What may GIVE one of those names a value. A literal needs no entry — `glue()`
# reduces it to nothing — so this list only ever holds the non-literal sources,
# and it is short on purpose. `orphanDropped` is the audio thread's count of
# buffers it could not hand to a request: an Int, incremented in the tap closure
# and zeroed by the watchdog that drains it, and nothing else touches it.
safe_builds='/Audio/PhoneListener\.swift#self\.orphanDropped$'
earn_name() {
    _file=$1; _name=$2
    _lines=$(NAME="$_name" awk -f "$out/namelines.awk" "$_file")
    _bad=$(printf '%s\n' "$_lines" \
        | awk -F'\t' '$1 == "BAD" { print substr($0, index($0, "\t") + 1) }')
    if [ -n "$_bad" ]; then
        echo "\`$_name\` reaches the journal as a value, and this gate accepts it"
        echo "only on the strength of what gives it that value. A line naming it"
        echo "is not a shape this scan can read:"
        printf '%s\n' "$_bad"
        echo ""
        echo "What the scan cannot read, it cannot call free of speech. Give the"
        echo "value on one line, or write the sentence out at the journal call and"
        echo "let the literal rules above judge it there."
        exit 2
    fi
    _values=$(printf '%s\n' "$_lines" | awk -v f="$_file" -F'\t' \
        '$1 == "VALUE" { print f "\t.noted(" substr($0, index($0, "\t") + 1) ")" }')
    _rogue=$(printf '%s\n' "$_values" | SAFE_EXPRESSIONS="$safe_builds" \
        awk -f "$out/journalstrings.awk" | sort -u)
    if [ -n "$_rogue" ]; then
        echo "\`$_name\` is given a value this gate has not been told is safe:"
        printf '%s\n' "$_rogue"
        echo ""
        echo "It reaches the journal under that name, so this is the check the"
        echo "value would have got had it been written out at the call site."
        echo "\`facts += self.partial\` is what walks through when it is missing:"
        echo "no named danger, no interpolation, the owner's own words in a log"
        echo "the Settings screen will mail to anybody on one tap."
        exit 2
    fi
    _rogue=$(printf '%s\n' "$_values" | awk -f "$out/interpolations.awk" | sort -u \
        | ALLOWED="$allowed" awk -F'\t' '($1 "#" $2) !~ ENVIRON["ALLOWED"]')
    if [ -n "$_rogue" ]; then
        echo "\`$_name\` is given a value interpolating something this gate has not"
        echo "been told is safe:"
        printf '%s\n' "$_rogue"
        echo ""
        echo "The same rule as a journal literal, because that is what this value"
        echo "becomes the moment it is recorded."
        exit 2
    fi
}
earn_name "$listener" facts
earn_name "$listener" dropped
echo "every journal write is a count, a status or an allowlisted system fact"

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
    "$here/ListenJournalTests.swift" \
    -o "$out/journaltests"
"$out/journaltests"
