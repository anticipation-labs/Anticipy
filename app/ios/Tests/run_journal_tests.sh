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
# So: EVERY record call site, in EVERY file, through EVERY String channel
# `ListenEvent` declares. The last version of this sentence said "checked two
# ways" and named the two anchors by hand; the enum had three String payloads
# and the third one — `flushed(reason:)`, printed verbatim to disk — was not one
# of them. A sentence claiming completeness is not completeness. The channels
# are derived from the enum below so the claim is produced by the code.
cat > "$out/journalwrites.awk" <<'AWK'
# WHICH CALL TO READ comes in through the environment as a REGEX ending in its
# open paren, so one scanner serves both the journal writes and the one value
# that reaches them under a name. Two copies of this loop would be two places
# for the paren counting to drift.
#
# A LITERAL `ListenJournal.shared.record(` IS WHAT THIS USED TO LOOK FOR, and
# two working leaks came of it. `ListenJournal` ⏎ `.shared` ⏎ `.record(.noted(
# line))` contains that text on no line at all, and `let sink = ListenJournal
# .shared` then `sink.record(.noted(line))` never contains it either. Both wrote
# the owner's transcript to the exportable log and this gate exited 0 — not
# because a rule was wrong, but because the scan never saw the call to apply any
# rule to. The anchor is the EVENT now, derived from the enum: whatever the sink
# is called and however it is reached, a journal write has to build a
# `ListenEvent` case, and that is what is looked for.
function stripped(l,  t) { t = l; sub(/^[ \t]*/, "", t); return t }
BEGIN { call = ENVIRON["CALL"]; skip = ENVIRON["SKIP"] }
FNR == 1 { skipping = (skip != "" && index(FILENAME, skip) > 0) }
skipping { next }
{
  s = $0
  if (stripped(s) ~ /^\/\//) next
  # `case .noted(let fact):` reads an event apart; it does not build one.
  if (!inCall && stripped(s) ~ /^case /) next
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
# 2. EVERY VALUE THAT REACHES A JOURNAL STRING, allowlisted — THROUGH EVERY
#    CHANNEL THE EVENT TYPE DECLARES, not through the ones somebody remembered.
#    A denylist can only catch the dangers already thought of, and a mutation
#    proved that: `detail: lines.joined()` — the whole log, joined — carries no
#    named danger and no interpolation at all, and sailed through rule 1.
#
#    THE CHANNEL LIST IS DERIVED FROM `ListenJournal.swift`. The version that
#    shipped named two anchors by hand, `.noted(` and `detail:`, under a comment
#    claiming "EVERY record call site, in EVERY file, checked two ways". It was
#    not true when it was written: `ListenEvent` had a THIRD free-form String,
#    `case flushed(reason: String, words: Int)`, rendered verbatim to disk by
#    `describe`. Changing one token at the flush call site — directly beneath a
#    comment reading "The word COUNT, never the words. The journal is exportable
#    from Settings" — put every flushed utterance of the day into that log and
#    this gate exited 0. A hand-kept list of channels IS the defect, so the enum
#    declaring a `String` associated value is now what puts that value under
#    this rule, and a fourth case arrives already covered.
#
#    So the rule is inverted. A positional `.case(...)` String argument and
#    every labelled `String` value must be string literals, whose interpolations
#    are on the list at rule 3, or else be named here as a safe expression.
#    Anything else fails, including the shapes nobody has thought of yet. Adding
#    to either list is a deliberate edit with a reason attached, which is
#    exactly the review moment this gate is for.
journal="$app/Audio/ListenJournal.swift"
[ -f "$journal" ] || { echo "ListenJournal.swift is gone; there is nothing to check."; exit 2; }
cat > "$out/channels.awk" <<'AWK'
# Every String-carrying payload of ListenEvent, and the anchor it has to be read
# with: `label:` for a labelled value, `.case(` for the one-argument case that
# takes its String positionally. A String this scan cannot anchor on is printed
# as unsupported rather than skipped — an unreadable channel is the whole class
# of defect this derivation exists to end.
function trim(t) { sub(/^[ \t]+/, "", t); sub(/[ \t]+$/, "", t); return t }
/^enum ListenEvent/ { inEnum = 1; next }
inEnum && /^}/ { inEnum = 0 }
!inEnum { next }
{
  s = $0
  sub(/^[ \t]*/, "", s)
  if (s ~ /^\/\//) next
  if (s !~ /^case [A-Za-z_]/) next
  sub(/^case[ \t]+/, "", s)
  p = index(s, "(")
  if (p == 0) next
  name = trim(substr(s, 1, p - 1))
  depth = 0; args = ""
  for (i = p; i <= length(s); i++) {
    c = substr(s, i, 1)
    if (c == "(") { depth++; if (depth == 1) continue }
    else if (c == ")") { depth--; if (depth == 0) break }
    args = args c
  }
  # A generic or an array in the payload would break the comma split below, so
  # it is reported rather than mis-split into something that looks harmless.
  if (args ~ /[<\[]/) { print "U\t" name; next }
  n = split(args, part, ",")
  for (k = 1; k <= n; k++) {
    a = trim(part[k])
    if (a ~ /^[A-Za-z_][A-Za-z0-9_]*[ \t]*:/) {
      lab = a; sub(/[ \t]*:.*$/, "", lab)
      if (trim(substr(a, index(a, ":") + 1)) == "String") print "L\t" lab "\t" name
    } else if (a == "String") {
      if (n == 1) print "P\t" name "\t" name
      else print "U\t" name "\t" name
    }
  }
}
AWK
channels=$(awk -f "$out/channels.awk" "$journal" | sort -u)
if [ -z "$channels" ]; then
    echo "This gate can no longer find a single String payload on ListenEvent."
    echo "It was about to allowlist nothing and call the journal clean. Either"
    echo "the enum was renamed or moved out of ListenJournal.swift, or this"
    echo "derivation has broken; both leave the free-form channels unread."
    exit 2
fi
if printf '%s\n' "$channels" | grep -q '^U	'; then
    echo "A ListenEvent case carries a String this scan cannot anchor on:"
    printf '%s\n' "$channels" | grep '^U	'
    echo ""
    echo "An unlabelled String beside other arguments, or a payload holding a"
    echo "generic or an array, has no anchor the extractor below can read it"
    echo "with — and an unread channel is exactly how flushed(reason:) carried"
    echo "speech past this rule. Give it a label, or teach the extractor."
    exit 2
fi

# EVERY PLACE A JOURNAL EVENT IS BUILT, anchored on the CASE NAMES the enum
# declares rather than on one spelling of the sink, so that neither
# `ListenJournal` ⏎ `.shared` ⏎ `.record(` nor a `let sink = ListenJournal.shared`
# can put a write where no rule reaches it. Both of those wrote a transcript to
# the exportable log past the literal anchor that used to be here, and both
# exited 0. `.record(` stays in the alternation beside the cases so that a call
# whose case name is written on the line BELOW it is still opened here and read
# to its end by the join.
#
# ListenJournal.swift itself is skipped: `parse` rebuilds these same cases from
# lines already on disk, and reading those back is not a write.
cases=$(printf '%s\n' "$channels" | awk -F'\t' '{ print $3 }' | sort -u | tr '\n' '|' | sed 's/|$//')
if [ -z "$cases" ]; then
    echo "No ListenEvent case carrying a String could be named, so this scan has"
    echo "nothing to look for and would read the whole app as clean."
    exit 2
fi
calls=$(read_calls "\\.(record|$cases)[ \t]*\\(" ListenJournal.swift)
if [ -z "$calls" ]; then
    echo "Nothing in the app builds a ListenEvent that carries a String."
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
# The argument of `.case(`, from the first character after the paren to the one
# that matches it. `\001` means it ran off the end unclosed.
function readParen(t, start,   j, c, depth, inStr, expr) {
  depth = 1; inStr = 0; expr = ""
  for (j = start; j <= length(t); j++) {
    c = substr(t, j, 1)
    if (c == "\"") inStr = !inStr
    else if (!inStr) {
      if (c == "(" || c == "[") depth++
      else if (c == ")" || c == "]") { depth--; if (depth == 0) return expr }
    }
    expr = expr c
  }
  return "\001"
}
# A labelled value, from the first character after the colon to the top-level
# comma or close paren that ends it. Brackets count as depth for the same reason
# parens do: `detail: names[0, 1]` must not be read as ending at that comma.
function readValue(t, start,   j, c, depth, inStr, expr) {
  depth = 0; inStr = 0; expr = ""
  for (j = start; j <= length(t); j++) {
    c = substr(t, j, 1)
    if (c == "\"") inStr = !inStr
    else if (!inStr) {
      if (c == "(" || c == "[") depth++
      else if (c == ")" || c == "]") { if (depth == 0) return expr; depth-- }
      else if (c == "," && depth == 0) return expr
    }
    expr = expr c
  }
  return "\001"
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
function report(file, anchor, expr,   g) {
  g = glue(expr)
  if (g == "") return
  if ((file "#" g) ~ ENVIRON["SAFE_EXPRESSIONS"]) return
  print "ROGUE\t" file "\t" anchor "\t" expr
}
# THE ANCHORS ARE TOLERANT OF WHITESPACE, because Swift is. The version that
# shipped compared seven characters at a fixed offset, so `.noted (x)` and
# `detail : x` — both valid, both verified compiling — matched neither anchor
# and the extractor returned nothing at all. Nothing extracted then read as
# "everything was allowlisted", which is why `SEEN` is printed for every
# occurrence and the caller insists each declared channel produced one.
BEGIN {
  n = split(ENVIRON["CHANNELS"], rows, "\n")
  for (i = 1; i <= n; i++) {
    if (rows[i] == "") continue
    split(rows[i], f, "\t")
    nch++
    kind[nch] = f[1]; who[nch] = f[2]
    if (f[1] == "L") re[nch] = "(^|[^A-Za-z0-9_])" f[2] "[ \t]*:"
    else re[nch] = "\\." f[2] "[ \t]*\\("
  }
}
{
  tab = index($0, "\t")
  file = substr($0, 1, tab - 1)
  t = blanked(substr($0, tab + 1))
  for (a = 1; a <= nch; a++) {
    pos = 1
    while (pos <= length(t) && match(substr(t, pos), re[a])) {
      after = pos + RSTART + RLENGTH - 1
      print "SEEN\t" who[a]
      if (kind[a] == "P") expr = readParen(t, after)
      else expr = readValue(t, after)
      if (expr == "\001" || expr == "")
        print "UNREAD\t" file "\t" who[a] "\t" substr(t, pos)
      else
        report(file, who[a], expr)
      pos = after
    }
  }
}
AWK
# FOUR PAIRS, and each one names the file it was reasoned about in.
#
# `AnticipyApp.swift#source.wireName` — the wire name of an event source,
# "voice" or "photo", chosen from a fixed set on the device.
#
# `PhoneListener.swift#facts.sentence` — the session-facts line. `facts` is a
# `ListenSessionFacts`, not a String: there is no `+=` and no `.append` that can
# put a transcript into it, and rules 3b and 3c below check both the one
# construction it has and the body of `sentence` itself.
#
# `PhoneListener.swift#reason?.rawValue??` and `#TranscriptFlushPolicy.Reason
# .final.rawValue` — why a flush fired. `Reason` is a `String` enum of exactly
# `gap`, `ceiling` and `final`, so its rawValue is one of three words chosen in
# TranscriptFlushPolicy and never a word anybody spoke. THIS CHANNEL HAD NO
# ENTRY AND NO CHECK until the derivation above found it: `reason:` was a third
# free-form String, and `reason: line` beside a word count of that same line
# exited 0.
safe_values='/AnticipyApp\.swift#source\.wireName$|/Audio/PhoneListener\.swift#(facts\.sentence|reason\?\.rawValue\?\?|TranscriptFlushPolicy\.Reason\.final\.rawValue)$'
scan=$(printf '%s\n' "$calls" | CHANNELS="$channels" SAFE_EXPRESSIONS="$safe_values" \
    awk -f "$out/journalstrings.awk")
unread=$(printf '%s\n' "$scan" | awk -F'\t' '$1 == "UNREAD" { print $2 ": " $4 }' | sort -u)
if [ -n "$unread" ]; then
    echo "A journal write has a value this gate could not read to its end:"
    printf '%s\n' "$unread"
    echo ""
    echo "An expression the scan cannot finish reading is an expression it"
    echo "cannot call free of speech. It used to be read as nothing to check."
    exit 2
fi
missing=$(printf '%s\n' "$channels" | while IFS='	' read -r _k _w _c; do
    [ -n "$_w" ] || continue
    printf '%s\n' "$scan" | grep -q "^SEEN	$_w\$" || echo "$_w"
done)
if [ -n "$missing" ]; then
    echo "ListenEvent declares a String channel that no journal write uses, or"
    echo "that this scan failed to find at a call site:"
    printf '%s\n' "$missing"
    echo ""
    echo "An anchor matching nothing is a rule reporting on an empty search, and"
    echo "an empty search is what let \`.noted (x)\` and \`detail : x\` — one"
    echo "space in each, both valid Swift — walk past this rule. Either the"
    echo "channel is unused and the case should go, or the extractor is broken."
    exit 2
fi
rogue=$(printf '%s\n' "$scan" | awk -F'\t' '$1 == "ROGUE" { print $2 "\t" $3 "\t" $4 }' | sort -u)
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
#    same reason rule 2 is: a bare name is a pass handed to every file at once,
#    and `dropped` is a name two files here carry.
#
#    A CORRECTION TO THE COMMIT THAT ADDED THE PAIRING. It called `dropped` "a
#    second bare name with no justification at all" and let that stand as a
#    third leak found. Half of it holds and half of it does not. The WIDENING
#    was real — the entry was `dropped` alone, so any file's `dropped` had a
#    pass, and pairing it with PhoneListener.swift was the right fix. The LEAK
#    was not: `TranscriptCursor.dropped` is `private var dropped = 0`, an Int
#    counting words cut off the front of the ring so an alignment index keeps
#    its origin, and rule 1's own comment says counting speech is the design.
#    There was never a shape in which it could carry a word. Two of the three
#    leaks that commit claimed were real; this one was an over-claim, and a
#    gate whose comments overstate what they caught is a gate nobody can
#    calibrate against.
#
#    `ListenSessionFacts.swift#(category|mode)` is the same pair for the value
#    type rule 3c checks: those two are `let` properties of a struct whose only
#    construction is read argument by argument below.
allowed='/Audio/PhoneListener\.swift#(dropped|session\.category\.rawValue|session\.mode\.rawValue)$|/AnticipyApp\.swift#Self\.postFailureShape\(error\)$|/Audio/ListenSessionFacts\.swift#(category|mode)$'
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
#     THE VERSION THAT REPLACED IT LEAKED TWICE MORE, and both are why the
#     classification below is written the way it is:
#
#       self.facts += self.partial     the scan's own name regex excluded a
#                                      preceding `.`, so a write through `self.`
#                                      matched nothing and the line was skipped
#                                      before it was ever classified. Three
#                                      characters made the sentence in
#                                      PhoneListener.swift that named the first
#                                      leak false.
#       (facts, lastSessionFacts)      an assignment shape the matcher did not
#         = (self.partial, "")         recognise. It fell through every arm and
#                                      landed on "a plain read", so FAILING TO
#                                      UNDERSTAND A LINE WAS A PASS — the exact
#                                      inversion of this rule's own principle.
#                                      It blanked the dedupe key too, so the
#                                      live transcript was journalled on every
#                                      watchdog tick for the length of a call.
#
#     A third, `let facts = words` in any other file, was never this rule's to
#     catch — the grep only ever opened PhoneListener.swift — and is closed by
#     the (file, name) pairing at rule 2 instead. This rule is what makes the
#     PhoneListener half of that pair mean anything:
#
#       - a preceding `.` no longer hides a line. `self.facts` and `other.facts`
#         are both seen, and the one this scan cannot attribute fails;
#       - every non-comment line naming the identifier must be a shape this scan
#         can read — a value given to it, a plain read of it, or a journal write
#         spending it. A method called ON it, an inout pass, and ANY line where
#         the name sits on the left of an assignment this scan did not parse are
#         none of those, and are reported rather than assumed harmless;
#       - a journal write only counts as spending it when the call OPENS BEFORE
#         the name. `facts.append(x); ListenJournal.shared.record(...)` used to
#         classify as a spend on the strength of the second statement;
#       - every value given to it goes through BOTH passes a journal literal
#         gets, `journalstrings.awk` and `interpolations.awk`, by being handed
#         to those exact two scripts. "Checked as if it had been written out at
#         the call" is now a property of the code below, not a claim in a
#         comment;
#       - a value continued on the next line is READ TO ITS END and checked
#         whole — by OPEN PARENTHESES as well as by a leading operator, so a
#         constructor call spread over three lines is one value rather than a
#         fragment ending in a comma. What still cannot be read to an end fails;
#       - finding nothing fails. An exception whose subject has been renamed
#         away is a check reporting on an empty search, and the twin of this
#         file's churn leg — anchored on `configureAndStartEngine`, and proved
#         by a reviewer to say nothing useful once that name moved.
cat > "$out/namelines.awk" <<'AWK'
function stripped(l,  t) { t = l; sub(/^[ \t]*/, "", t); return t }
# The position of the first ASSIGNMENT `=` outside a string literal, or 0.
# `==`, `!=`, `<=` and `>=` are comparisons; the `=` of `+=` is a write.
function assignAt(s,   i, n, c, p, q, inStr) {
  n = length(s); inStr = 0
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\") { i++; continue }
    if (c == "\"") { inStr = !inStr; continue }
    if (inStr) continue
    if (c != "=") continue
    q = substr(s, i + 1, 1)
    if (q == "=") { i++; continue }
    p = (i > 1) ? substr(s, i - 1, 1) : " "
    if (p == "=" || p == "!" || p == "<" || p == ">") continue
    return i
  }
  return 0
}
# What is being assigned TO, given where the `=` is. `if x > 0, let y = z` puts
# a condition in front of a binding, so the left-hand side starts after the last
# TOP-LEVEL comma — top-level being what keeps `(facts, other) = (a, b)` whole.
function lhsOf(s, a,   i, c, inStr, d, cut) {
  cut = 0; d = 0; inStr = 0
  for (i = 1; i < a; i++) {
    c = substr(s, i, 1)
    if (c == "\\") { i++; continue }
    if (c == "\"") { inStr = !inStr; continue }
    if (inStr) continue
    if (c == "(" || c == "[") d++
    else if (c == ")" || c == "]") d--
    else if (c == "," && d == 0) cut = i
  }
  return substr(s, cut + 1, a - cut - 1)
}
# How far out of balance a fragment's parentheses and brackets are, and whether
# it left a quote open. Either one means the rest of the value is on the lines
# below and this scan has not read it yet.
function depthOf(s,   i, n, c, inStr, d) {
  n = length(s); inStr = 0; d = 0
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\") { i++; continue }
    if (c == "\"") { inStr = !inStr; continue }
    if (inStr) continue
    if (c == "(" || c == "[") d++
    else if (c == ")" || c == "]") d--
  }
  return d
}
function openQuote(s,   i, n, c, inStr) {
  n = length(s); inStr = 0
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\") { i++; continue }
    if (c == "\"") inStr = !inStr
  }
  return inStr
}
# The whole file first, because a value may be continued on the lines after the
# one that starts it and a scan reading one line at a time cannot follow that.
{ src[NR] = $0 }
END {
  name = ENVIRON["NAME"]
  # `self.` and any other receiver are INSIDE these, not excluded from them.
  # Excluding a preceding `.` is what made `self.facts += self.partial`
  # invisible to every arm below.
  bare   = "(^|[^A-Za-z0-9_])(self\\.)?" name "([^A-Za-z0-9_]|$)"
  assign = "(^|[^A-Za-z0-9_])(self\\.)?" name "[ \t]*\\+?="
  touch  = "(^|[^A-Za-z0-9_])(self\\.)?" name "[ \t]*[.[]"
  inout  = "&(self\\.)?" name "([^A-Za-z0-9_]|$)"
  spend  = "ListenJournal|\\.noted[ \t]*\\(|(^|[^A-Za-z0-9_])detail[ \t]*:"
  for (i = 1; i <= NR; i++) {
    s = src[i]
    if (stripped(s) ~ /^\/\//) continue
    if (!match(s, bare)) continue
    at = RSTART
    seen++
    # A VALUE GIVEN TO IT, asked first so that a write and a journal call
    # sharing one line cannot hide behind the call.
    v = ""
    if (match(s, assign)) {
      v = substr(s, RSTART + RLENGTH)
      if (substr(v, 1, 1) == "=") v = ""   # a comparison, not a write
    }
    if (v != "") {
      assigns++
      # Swift continues an expression on the next line when that line opens
      # with an operator, and an argument list continues for as long as its
      # parentheses are open. Both are read in here rather than left
      # unexamined: a value this scan stops short of is a value it never saw.
      for (j = i + 1; j <= NR; j++) {
        t = stripped(src[j])
        if (t ~ /^\/\//) continue
        if (depthOf(v) <= 0 && !openQuote(v) && t !~ /^[+.?:,)]/) break
        v = v " " t
        if (j - i > 20) break
      }
      # `if <cond> { facts += "…" }` is how a folded clause is written, so the
      # block's closing brace arrives with the value and is not part of it.
      sub(/[ \t]*}[ \t]*$/, "", v)
      sub(/^[ \t]+/, "", v); sub(/[ \t]+$/, "", v)
      tmp = v; quotes = gsub(/"/, "", tmp)
      if (v == "" || quotes % 2 == 1 || depthOf(v) != 0 || v ~ /[+(,][ \t]*$/)
        print "BAD\t" FILENAME ":" i ": " s "\tthe value cannot be read to an end"
      else
        print "VALUE\t" v
      continue
    }
    # AN ASSIGNMENT THIS SCAN COULD NOT PARSE IS A FAILURE, NOT A READ. The
    # matcher above wants `=` immediately after the name; a tuple, a subscript
    # or a member on the left is a write it cannot follow, and the version that
    # shipped let every one of them fall through to "a plain read".
    a = assignAt(s)
    if (a > 0 && lhsOf(s, a) ~ bare) {
      print "BAD\t" FILENAME ":" i ": " s "\tit is written by an assignment shape this scan cannot read"
      continue
    }
    # SPENT ON THE JOURNAL. Rules 1-3 above read those calls in full, across
    # the continuations this classification does not try to follow. The call
    # must OPEN BEFORE the name: a second statement on the same line is not a
    # reason to stop reading the first one.
    if (match(s, spend) && RSTART < at) { spent++; continue }
    # READ AND NOTHING ELSE is all that is left. A method called on it or an
    # inout pass is a write whose inside this scan cannot see.
    if (s ~ touch || s ~ inout) {
      print "BAD\t" FILENAME ":" i ": " s "\tsomething is done to it that this scan cannot follow"
      continue
    }
  }
  if (seen == 0) print "BAD\t" FILENAME "\tno line in this file names it at all"
  else if (assigns == 0) print "BAD\t" FILENAME "\tnothing in this file gives it a value"
  else if (spent == 0) print "BAD\t" FILENAME "\tit never reaches a journal write from here"
}
AWK
# What may GIVE one of those names a value. A literal needs no entry — `glue()`
# reduces it to nothing — so this list only ever holds the non-literal sources,
# and it is short on purpose.
#
# `self.orphanDropped` is the audio thread's count of buffers it could not hand
# to a request: an Int, incremented in the tap closure and zeroed by the
# watchdog that drains it, and nothing else touches it.
#
# The `ListenSessionFacts(...)` construction is spelled out ARGUMENT BY
# ARGUMENT, so the entry only holds while all three arguments are exactly
# these. `category: self.partial` changes the reduced expression and fails
# here; there is no wildcard for a fourth argument to hide in.
safe_builds='/Audio/PhoneListener\.swift#(self\.orphanDropped|ListenSessionFacts\(category:session\.category\.rawValue,mode:session\.mode\.rawValue,lowPower:ProcessInfo\.processInfo\.isLowPowerModeEnabled\))$'
# The positional String channel, taken from the enum rather than typed here, so
# that renaming `.noted` renames the wrapper these values are checked inside
# instead of quietly emptying the check.
noted=$(printf '%s\n' "$channels" | awk -F'\t' '$1 == "P" { print $2; exit }')
if [ -z "$noted" ]; then
    echo "ListenEvent no longer has a case taking a bare String."
    echo "The rule below wraps each value in that case to check it the way the"
    echo "journal would, and with no such case it would wrap them in nothing and"
    echo "find nothing to complain about."
    exit 2
fi
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
    _values=$(printf '%s\n' "$_lines" | awk -v f="$_file" -v n="$noted" -F'\t' \
        '$1 == "VALUE" { print f "\t." n "(" substr($0, index($0, "\t") + 1) ")" }')
    _scan=$(printf '%s\n' "$_values" | CHANNELS="$channels" SAFE_EXPRESSIONS="$safe_builds" \
        awk -f "$out/journalstrings.awk")
    # THE WRAPPER MUST HAVE BEEN READ. Every value handed in produces exactly
    # one anchor sighting; fewer means the extractor walked past a build line
    # and this whole rule reported on an empty search.
    _want=$(printf '%s\n' "$_values" | grep -c '.' || true)
    _got=$(printf '%s\n' "$_scan" | grep -c '^SEEN' || true)
    if [ "$_got" -lt "$_want" ]; then
        echo "\`$_name\` has $_want value(s) given to it and only $_got were read by"
        echo "the check that judges them. A value the extractor walks past reads"
        echo "as a value nobody objected to."
        exit 2
    fi
    _rogue=$(printf '%s\n' "$_scan" \
        | awk -F'\t' '$1 == "ROGUE" || $1 == "UNREAD" { print $2 "\t" $3 "\t" $4 }' | sort -u)
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

# 3c. THE VALUE TYPE THAT CARRIES THE SESSION FACTS, BOTH ENDS OF IT.
#
#     The session facts used to be a `var facts = "…"` built up with `+=` inside
#     a 1,100-line file, and the whole privacy claim rested on rule 3b reading
#     every line that gave that local a value. Two working leaks went past that
#     reading in one sitting — a write through `self.`, and a tuple assignment
#     the matcher did not recognise and therefore read as harmless. Rule 3b is
#     fixed above; this is the other half. `facts` is a `ListenSessionFacts`
#     now, not a String, so `+=`, `.append` and `= self.partial` DO NOT COMPILE.
#     `ListenEvent.batteryRead` makes the same argument with the same
#     instrument: the privacy claim is the type.
#
#     A type is only worth what its two openings are worth, so both are read:
#     every construction of it anywhere in the app, argument by argument, and
#     the body of the one property that turns it into a line of the journal.
factsfile="$app/Audio/ListenSessionFacts.swift"
if [ ! -f "$factsfile" ]; then
    echo "ListenSessionFacts.swift is gone."
    echo "The session-facts line is what the journal mostly carries, and the"
    echo "two checks below are the only thing saying it cannot carry speech."
    exit 2
fi
factschannels=$(awk '
    /^struct ListenSessionFacts/ { inS = 1; next }
    inS && /^}/ { inS = 0 }
    !inS { next }
    {
      s = $0; sub(/^[ \t]*/, "", s)
      if (s ~ /^\/\//) next
      if (s !~ /^let [A-Za-z_][A-Za-z0-9_]*[ \t]*:/) next
      lab = s; sub(/^let[ \t]+/, "", lab); sub(/[ \t]*:.*$/, "", lab)
      print "L\t" lab
    }' "$factsfile")
if [ -z "$factschannels" ]; then
    echo "ListenSessionFacts declares no stored properties this scan can find."
    echo "The check below reads each one at the construction site; with none"
    echo "derived it would read nothing and pass. Either the struct was renamed"
    echo "or its properties are no longer plain \`let\`s."
    exit 2
fi
builds=$(read_calls 'ListenSessionFacts[ \t]*\(')
if [ -z "$builds" ]; then
    echo "Nothing in the app constructs a ListenSessionFacts."
    echo "Either the session facts stopped being recorded, or this scan has"
    echo "broken; both leave the rule below reporting on an empty search."
    exit 2
fi
if printf '%s\n' "$builds" | grep -q 'UNTERMINATED'; then
    echo "A ListenSessionFacts construction could not be read to its end."
    echo "The scan below cannot see what it is given, so it cannot say the line"
    echo "it renders as is free of speech."
    exit 2
fi
# What may be handed to that initializer. All three are read off the audio
# session and the process, never off a recognizer.
safe_args='/Audio/PhoneListener\.swift#(session\.category\.rawValue|session\.mode\.rawValue|ProcessInfo\.processInfo\.isLowPowerModeEnabled)$'
buildscan=$(printf '%s\n' "$builds" | CHANNELS="$factschannels" SAFE_EXPRESSIONS="$safe_args" \
    awk -f "$out/journalstrings.awk")
rogue=$(printf '%s\n' "$buildscan" \
    | awk -F'\t' '$1 == "ROGUE" || $1 == "UNREAD" { print $2 "\t" $3 "\t" $4 }' | sort -u)
if [ -n "$rogue" ]; then
    echo "A ListenSessionFacts is built from a value this gate has not been told"
    echo "is safe:"
    printf '%s\n' "$rogue"
    echo ""
    echo "Whatever goes in comes back out of \`sentence\` and into a journal the"
    echo "Settings screen mails on one tap. These three fields are what the audio"
    echo "session became and whether the phone is throttled; nothing a recognizer"
    echo "produced belongs among them."
    exit 2
fi
missing=$(printf '%s\n' "$factschannels" | while IFS='	' read -r _k _w; do
    [ -n "$_w" ] || continue
    printf '%s\n' "$buildscan" | grep -q "^SEEN	$_w\$" || echo "$_w"
done)
if [ -n "$missing" ]; then
    echo "A ListenSessionFacts property is never given a value at a construction"
    echo "site this scan can see:"
    printf '%s\n' "$missing"
    echo ""
    echo "An argument the extractor cannot find is an argument it cannot judge,"
    echo "and it reads exactly like an argument nobody objected to."
    exit 2
fi
# AND THE BODY THAT TURNS IT INTO A LINE, through the same two passes a journal
# literal gets. It is one expression on purpose: no mutable local, so there are
# no assignment shapes here for a scan to misread. What survives outside its
# quotes must be the allowlisted residue, and every interpolation must be on
# rule 3's list — `+ speech` fails the first, `\(partial)` fails the second.
sentence=$(awk '/^    var sentence: String \{$/,/^    \}$/' "$factsfile" \
    | sed '/^[[:space:]]*\/\//d')
body=$(printf '%s\n' "$sentence" | sed '1d;$d' | tr '\n' ' ')
if [ -z "$(printf '%s' "$body" | tr -d ' 	')" ]; then
    echo "This gate can no longer read the body of ListenSessionFacts.sentence."
    echo "That body is the one thing turning these three fields into a line on"
    echo "disk, and an empty body has no residue and no interpolations — it"
    echo "would pass by being unreadable. Point the anchor at the new name."
    exit 2
fi
sentencescan=$(printf '%s\t.%s(%s)\n' "$factsfile" "$noted" "$body" \
    | CHANNELS="$channels" SAFE_EXPRESSIONS='/Audio/ListenSessionFacts\.swift#\(lowPower\?:\)$' \
      awk -f "$out/journalstrings.awk")
rogue=$(printf '%s\n' "$sentencescan" \
    | awk -F'\t' '$1 == "ROGUE" || $1 == "UNREAD" { print $2 "\t" $3 "\t" $4 }' | sort -u)
if [ -n "$rogue" ]; then
    echo "ListenSessionFacts.sentence builds its line out of something this gate"
    echo "has not been told is safe:"
    printf '%s\n' "$rogue"
    echo ""
    echo "Everything outside the quotes of that expression is what this gate has"
    echo "to reason about. Keep it to the three fields the initializer is checked"
    echo "on, or say here why a new one can never carry a word anybody said."
    exit 2
fi
if ! printf '%s\n' "$sentencescan" | grep -q '^SEEN'; then
    echo "The check on ListenSessionFacts.sentence read nothing at all."
    echo "Its body was wrapped in the journal's own String case and handed to the"
    echo "same extractor, and the extractor found no anchor — so this rule was"
    echo "about to pass on an empty search."
    exit 2
fi
rogue=$(printf '%s\t%s\n' "$factsfile" "$body" | awk -f "$out/interpolations.awk" | sort -u \
    | ALLOWED="$allowed" awk -F'\t' '($1 "#" $2) !~ ENVIRON["ALLOWED"]')
if [ -n "$rogue" ]; then
    echo "ListenSessionFacts.sentence interpolates something this gate has not"
    echo "been told is safe:"
    printf '%s\n' "$rogue"
    echo ""
    echo "That line goes to disk verbatim. A count, a status or a system constant"
    echo "belongs; anything derived from what the owner said does not."
    exit 2
fi
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
