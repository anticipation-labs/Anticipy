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
function report(file, kind, expr,   g) {
  g = glue(expr)
  if (g == "") return
  if (g ~ ENVIRON["SAFE_EXPRESSIONS"]) return
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
# `source.wireName` is the wire name of an event source — "voice", "photo" — and
# is the one journal value that is neither a literal nor a count.
rogue=$(printf '%s\n' "$calls" | SAFE_EXPRESSIONS='^(source\.wireName)$' \
    awk -f "$out/journalstrings.awk" | sort -u)
if [ -n "$rogue" ]; then
    echo "A journal write hands over a value this gate has not been told is safe:"
    printf '%s\n' "$rogue"
    echo ""
    echo "What goes in the journal leaves the phone when the log is shared, and"
    echo "the diagnostics screen ships in RELEASE. Write a literal sentence with"
    echo "a count or a status interpolated into it, or name the expression in"
    echo "this file and say why it can never carry what the owner said."
    exit 2
fi
# 3. AND EVERY INTERPOLATION INSIDE THOSE LITERALS.
allowed='dropped|session\.category\.rawValue|session\.mode\.rawValue|Self\.postFailureShape\(error\)'
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
    | ALLOWED="$allowed" awk -F'\t' 'BEGIN { ok = "^(" ENVIRON["ALLOWED"] ")$" } $2 !~ ok')
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
echo "every journal write is a count, a status or an allowlisted system fact"

# And the safe reduction must still be the thing standing between them.
if ! grep -q 'postFailureShape(error)' "$session"; then
    echo "A post failure no longer goes through postFailureShape."
    echo "That function is the only thing turning a refusal into a status code"
    echo "instead of the server's sentence about the owner's own words."
    exit 2
fi

# ------------------------------------------------------------ the noted spam
# EVERY WRITE ABOVE THE 0 Hz GUARD OBEYS THE SAME DEDUPE THE GUARD ITSELF DOES.
# The two `.noted` calls in configureAndStartEngine sat three lines above a
# guard whose own comment reads "Recorded once per outage, not once per watchdog
# tick: the 4s watchdog retries this path for as long as the call lasts, and a
# journal that spends all 400 of its lines saying the same thing has evicted the
# session it was meant to explain." They did not obey it. Measured: 15 identical
# lines a minute, 30 in low power; the ring fully evicted in 27 minutes and both
# 256 KB files in about five hours, so the one interruption line that explains
# the day rotates away and the screen reports a blank, healthy day.
pre=$(awk '/private func configureAndStartEngine/,/guard format.sampleRate/' "$listener" \
    | grep -vE '^[[:space:]]*//')
if printf '%s\n' "$pre" | grep -q 'ListenJournal.shared.record'; then
    guarded=$(printf '%s\n' "$pre" | grep -n 'if !suspended' | head -1 | cut -d: -f1)
    firstwrite=$(printf '%s\n' "$pre" | grep -n 'ListenJournal.shared.record' | head -1 | cut -d: -f1)
    if [ -z "$guarded" ] || [ "$guarded" -gt "$firstwrite" ]; then
        echo "configureAndStartEngine writes to the journal before it knows the"
        echo "microphone is ours, and outside the 'if !suspended' dedupe."
        echo "The 4s watchdog calls this method on every tick of a phone call, so"
        echo "an unguarded write here is fifteen identical lines a minute and the"
        echo "whole ring gone in twenty-seven — including the one line that says"
        echo "a call took the microphone."
        exit 2
    fi
fi
echo "the session facts are recorded once per outage, not once per watchdog tick"

# THE TAP CLOSURE STAYS JOURNAL-FREE. It runs on the audio thread, and the
# journal now writes to a FILE. A record() call in there would park audio
# behind a disk write — the instrument built to explain dropped speech becoming
# a way to drop it. Dropped-buffer counting is a plain integer there, reported
# by the watchdog from the main queue instead. Asserted on source shape,
# the way run_flush_policy_tests.sh asserts its own.
tap=$(awk '/installTap\(onBus: 0/,/^        }$/' "$listener")
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
