#!/bin/sh
# Checks for the end-of-errand decision — the rule that decides whether a typed
# answer cancels the job and files the owner's own words as the reason.
#
#   sh app/ios/Tests/run_end_errand_tests.sh
#
# The rule lives inside AnticipySession, which drags in SwiftUI, Combine, the
# network layer and the microphone — none of which this decision touches. So
# rather than duplicate it (a copy is only honest until someone edits one side),
# this lifts the REAL source out of AnticipyApp.swift between its ANCHOR
# markers and compiles it alone. `Self.` resolves to the wrapper here exactly as
# it resolves to AnticipySession there.
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

src="$app/AnticipyApp.swift"

# The checks are worthless if the app has quietly stopped consulting the rule
# before it approves an answer. Prove the wiring before proving the logic.
if ! grep -q 'Self.answerThatEndsTheErrand' "$src"; then
    echo "confirm() no longer asks whether the answer ended the errand."
    echo "Without it every non-empty answer requeues the run — which is how"
    echo "'skip it, I don't need the batteries' relaunched the errand and got"
    echo "those words Bing-searched into a CAPTCHA."
    exit 2
fi
if grep -vE '^[[:space:]]*//' "$src" | grep -q 'wordCount <= 8'; then
    echo "The rule is gating on answer LENGTH again."
    echo "Every regression it was added for is short: 'leave it with the"
    echo "concierge', 'stop it from auto-renewing'. Length was never the"
    echo "condition; position is."
    exit 2
fi

# --------------------------------------------------------------------------
# LAW 2, FROM THE iOS SIDE. This rule is REGISTERED TAPE, not a design.
#
# It decides what the owner's words MEAN — three phrase lists on the phone,
# with no model anywhere near them — and on a hit it writes the job cancelled
# and files the owner's own sentence as the evidence they called it off. That
# is Law 1's canonical shape, and research/2026-08-24-law1-audit.md item #55
# records it at severity H.
#
# It is still here because deleting it could not be shown SAFE from inside
# app/ios/: see the block comment on the rule itself in AnticipyApp.swift. So
# it ships the only way Law 2 permits — carrying a marker and a red leg. Those
# live in two other files, and the whole point of Law 2 is that all three books
# have to agree. This leg is the iOS book: if the rule is in the tree and its
# declaration is not, these checks fail HERE, where the person editing the rule
# is already looking, rather than only in a gate they may never run.
#
# When the rule is deleted, delete this leg with it — and the registry entry,
# and the ledger bullet, in the same diff.
# --------------------------------------------------------------------------
#
# THE NEEDLE IS ASSEMBLED, NOT WRITTEN. It must not appear in this file as a
# literal, and that is not style. overnight/tape_gate.py decides a piece of
# tape is GONE by searching the whole of app/ for the registered `find` text —
# and app/ios/Tests/*.sh is inside app/. Spelled out here, this file WOULD BE
# a second copy of the tape as far as the gate can tell: the day someone
# actually deletes the rule the entry would come back MOVED instead of GONE,
# leg 1 would go red pointing at a test script, and Law 2's expiry could never
# turn green. An expiry that cannot come true is the thing this whole gate
# exists to stop. Caught by mutation, 2026-08-25: the rule was renamed away
# and leg 2 still counted it.
#
# The same trap applies to the marker: `marker` below is spelled in pieces for
# the identical reason. A bare one written out here would be a marker in a
# shipped file that no registry entry claims, and leg 1 calls that orphaned
# tape.
rule_name='answerThatEndsTheErrand'
rule_find="static func $rule_name("
marker='TA''PE'
gate="$here/../../../overnight/tape_gate.py"
laws="$here/../../../HARNESS-LAWS.md"

# --------------------------------------------------------------------------
# THIS SCRIPT CHECKS ITSELF FIRST, BECAUSE IT ALREADY GOT THIS WRONG ONCE.
#
# The paragraph above says the marker must never appear here as a literal, and
# then on 2026-08-25 the rewrite of this file put one in anyway — not as a
# marker, as ordinary English inside a failure message: the words `REGISTERED
# <marker> (HARNESS-LAWS.md Law 2, audit item #55).`. Nobody wrote a
# declaration; a sentence happened to end in a parenthetical and a full stop,
# and tape_gate's MARKER_RE is `<marker>`, an OPTIONAL `(...)`, then a colon
# OR A FULL STOP. Leg 1 went `FAIL ... 1 marker(s) that overnight/tape_gate.py
# has never heard of`, exit 2, pointing at this test script — and the suite
# below still printed all green, because nothing here was looking.
#
# A rule written in a comment is a rule nobody runs. So the two files this
# suite owns are now scanned with the gate's own regex, and they may contain
# no marker at all. Note which way this points: an ORPHAN is tape that claims
# an expiry nothing tracks, so the honest state for a test file is zero
# markers, and that is a floor — it refuses rather than waves through.
# --------------------------------------------------------------------------
if ! python3 - "$gate" "$marker" "$here/run_end_errand_tests.sh" "$here/EndTheErrandTests.swift" <<'SELF_LEG'; then
import importlib.util, os, sys

gate_path, marker = sys.argv[1], sys.argv[2]
if not os.path.exists(gate_path):
    print("Cannot read %s, so this leg cannot ask the gate's question and is" % gate_path)
    print("not allowed to guess at it. No verdict beats an invented one.")
    raise SystemExit(1)
spec = importlib.util.spec_from_file_location("tape_gate", gate_path)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

orphans = []
for path in sys.argv[3:]:
    text = open(path).read()
    for m in gate.MARKER_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        orphans.append((path, line, text.split("\n")[line - 1].strip()))

if orphans:
    print("A '%s' marker has appeared in this suite's own files:" % marker)
    print("")
    for path, line, text in orphans:
        print("  %s:%d" % (path, line))
        print("      %s" % text[:72])
    print("")
    print("overnight/tape_gate.py scans app/ for markers and claims each one")
    print("against a registry entry. These belong to no entry, so leg 1 calls")
    print("them tape nobody declared and exits 2 — the gate red because of a")
    print("test file. The pattern is the word, then an OPTIONAL parenthetical,")
    print("then a colon OR A FULL STOP: `X, not a design` is safe, `X (Law 2).`")
    print("is not. Reword it, or assemble the word from pieces the way the")
    print("`marker` variable above is assembled.")
    raise SystemExit(1)

print("this suite's own files carry no '%s' marker of their own (%d scanned "
      "with the gate's regex)" % (marker, len(sys.argv) - 3))
SELF_LEG
    exit 2
fi

if grep -qF "$rule_find" "$src"; then
    # THE MARKER CHECK IS THE GATE'S OWN, IMPORTED — NOT A SECOND COPY OF IT.
    #
    # This used to be `grep -q "$marker[:.]" "$src"`: a whole-file grep over
    # 4,000 lines, which certifies "there is a marker somewhere in
    # AnticipyApp.swift" and says nothing about whether it is anywhere near
    # the rule. tape_gate leg 1 asks a different question — is the marker
    # inside `_window_span(source, find, before=400)`, a 400-character window
    # ending at the rule. Two predicates, one of them lax, and they diverged
    # for real: on 2026-08-25 a single ordinary comment line inserted between
    # the declaration and `static func` (gap 360 -> 437) took tape_gate to
    # `FAIL EVERY MARKER IS REGISTERED`, exit 2, while this script printed
    # "the rule is declared tape" and exited 0. Two books, opposite answers,
    # no explanation of which to believe.
    #
    # So the window and the regex are now IMPORTED from tape_gate.py rather
    # than re-expressed here. There is no second predicate left to drift: if
    # the gate changes its window, this moves with it in the same commit,
    # because it is the same object. Adjacency is checked on top — the marker
    # must be the LAST line above `static func` — which is stricter than the
    # gate and can only fail EARLIER, never later. That direction is the safe
    # one: this leg can be red while the gate is green, never the reverse.
    if ! python3 - "$src" "$rule_find" "$marker" "$gate" <<'MARKER_LEG'; then
import os, re, sys, importlib.util

src_path, find, marker, gate_path = sys.argv[1:5]
src = open(src_path).read()

spec = importlib.util.spec_from_file_location("tape_gate", gate_path)
if spec is None or not os.path.exists(gate_path):
    print("Cannot import %s, so this leg cannot ask the gate's question and" % gate_path)
    print("is not allowed to guess at it. No verdict beats a made-up one.")
    raise SystemExit(1)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

lo, hi = gate._window_span(src, find)          # the gate's window, not a copy
m = gate.MARKER_RE.search(src, lo, hi)         # the gate's regex, not a copy
found = src.find(find)
lines = src[:found].count("\n") + 1

if m is None:
    anywhere = list(gate.MARKER_RE.finditer(src))
    print("The end-of-errand rule is in AnticipyApp.swift with no '%s:'" % marker)
    print("marker in the window overnight/tape_gate.py searches — the 400")
    print("characters ending at `%s`, line %d." % (find, lines))
    if anywhere:
        print("")
        print("A marker DOES exist at line %d, %d characters away. That is the"
              % (src[:anywhere[0].start()].count("\n") + 1,
                 found - anywhere[0].start()))
        print("failure exactly: the declaration is written and the gate cannot")
        print("see it, so leg 1 reports this rule as tape nobody declared and")
        print("exits 2 while the comment sits right there. Do NOT answer that")
        print("by adding a duplicate entry to KNOWN_TAPE. Move the marker back")
        print("down so it is the last line above `static func`.")
    else:
        print("")
        print("Undeclared tape is a rejected diff (Law 2). Either delete the")
        print("rule and route every answer to the brain, or declare it.")
    raise SystemExit(1)

# Stricter than the gate, on purpose: distance is a budget that erodes without
# anyone deciding to spend it. Position does not.
above = src[:found].rsplit("\n", 2)[-2] if src[:found].count("\n") >= 2 else ""
if not gate.MARKER_RE.search(above):
    print("The '%s:' marker is inside the gate's window, but it is not the" % marker)
    print("last line above `%s`." % find)
    print("The line that IS immediately above it reads:")
    print("    %s" % above.strip()[:70])
    print("")
    print("That gap is a budget of 400 characters and it erodes one innocent")
    print("comment at a time until leg 1 goes red for a declaration that was")
    print("never removed. Put your prose ABOVE the declaration paragraph.")
    raise SystemExit(1)

print("the marker is %d of %d characters from the rule (the gate's own window "
      "and regex, imported), and is the line immediately above it"
      % (found - m.start(), 400))
MARKER_LEG
        exit 2
    fi
    if ! grep -qF "$rule_find" "$gate"; then
        echo "The rule carries a marker but overnight/tape_gate.py has no entry"
        echo "whose find= is:  $rule_find"
        echo "A marker pointing at a leg that does not track it reads as"
        echo "compliant and enforces nothing — that is audit item #21 exactly."
        exit 2
    fi
    if ! grep -q 'tape:answer_ends_errand' "$laws"; then
        echo "Neither book a human reads mentions this tape. HARNESS-LAWS.md's"
        echo "'Known standing tape' section needs its [tape:answer_ends_errand]"
        echo "bullet, or the next agent reads the ledger and believes the list"
        echo "is complete."
        exit 2
    fi
    echo "the rule is declared tape: marker in the source, entry in the gate, bullet in the law"
fi

# The END rule comes first: the closing marker contains the opening marker as a
# substring, so testing for the opening one first re-armed it and swallowed the
# rest of the file.
awk '/END ANCHOR: end-of-errand decision/{f=0;next} /ANCHOR: end-of-errand decision/{f=1;next} f' \
    "$src" > "$out/rule.swift"
if [ ! -s "$out/rule.swift" ]; then
    echo "Found no code between the ANCHOR markers in AnticipyApp.swift."
    echo "Either the markers moved or the rule did; these checks are compiling"
    echo "nothing, which is worse than not having them."
    exit 2
fi
if ! grep -q 'func answerThatEndsTheErrand' "$out/rule.swift"; then
    echo "The anchored region no longer contains answerThatEndsTheErrand."
    exit 2
fi
echo "confirm() consults the rule, and the anchored region is $(wc -l < "$out/rule.swift" | tr -d ' ') lines"

# --------------------------------------------------------------------------
# THE WORD LISTS ARE PINNED EXACTLY, IN BOTH DIRECTIONS.
#
# The Swift cases below are BEHAVIOURS: they sample the rule. Sampling is not
# fencing, and the gap was measured on 2026-08-25 rather than argued about.
# Every one of the 50 phrases in `whole`/`declines`/`handled` was deleted in
# turn, the mutated rule compiled, and its verdicts diffed against the shipping
# one: 24 of those deletions CHANGE what the app does and leave the suite at
# 48/48, exit 0. Two worked examples, both one-word edits, both green:
#
#   NARROWING — delete "cancel" from `whole`, and a bare typed "cancel" at a
#   needs_user card stops returning a verdict. It routes .toTheBrain, where
#   _classify's offline fallback (brain/conversation.py) reads _pending(),
#   which is `awaiting_confirm` only — so with the model unreachable the owner
#   is told "Nothing's queued up on my end right now" and the errand runs on.
#   A stop that no longer stops anything, which is the exact case this rule is
#   still in the tree to prevent.
#
#   WIDENING — add one line, "yes", to `declines`, and "yes", "yes please" and
#   "ok yes thanks" all come back `You called it off: "yes". I did nothing
#   further.` The owner's approval, written into the ledger as their
#   cancellation. That is the shape brain/conversation.py already records a
#   bare \bno\b causing, one process over.
#
# This matters more here than it would for a design. The violation is
# REGISTERED rather than deleted, which means these lists ship — so the only
# thing standing between them and silent drift is a check that goes red when
# they change. Behaviour cases cannot be that check: there is no finite set of
# them that covers a 116-word vocabulary in both directions.
#
# So the vocabulary itself is the check. Every string literal in the anchored
# region — all five lists, the conditional words, the clause separators and
# both verdict sentences — is extracted from the SHIPPING source and compared
# to GOLDEN below. Add a word, drop a word, move one between lists, or edit
# what the owner is told: red, naming what changed.
#
# This is a gate, not a decision — Law 1 exempts it (`Gates and evals —
# deterministic tests of outcomes`). It reads the lists; it never consults
# them about anybody's meaning.
# --------------------------------------------------------------------------
if ! python3 - "$out/rule.swift" <<'VOCABULARY_LEG'; then
import re, sys

# ---- what the shipping rule is allowed to say, exactly -------------------
# Regenerate ONLY when you meant to change the tape, and say why in the diff.
GOLDEN = [
    ('rule body', [
        '’', "'",
    ]),
    ('whole', [
        'no', 'nope', 'stop', 'cancel', 'skip', 'skip it', 'never mind',
        'nevermind', 'forget it', 'drop it', 'leave it', "don't bother",
        'dont bother', 'call it off', 'not anymore',
    ]),
    ('declines', [
        'never mind', 'nevermind', 'forget it', "don't bother",
        'dont bother', 'no longer need', "don't need", 'dont need',
        'do not need', 'not needed', 'drop it', 'skip it', 'skip this',
        'call it off', "don't do it", 'dont do it', 'cancel it',
        'cancel that', 'cancel this', 'stop it', 'leave it',
    ]),
    ('handled', [
        'handled it', 'i handled', 'did it myself', 'took care of it',
        'already did', 'already done', 'already handled',
        'already booked', 'already sent', 'already ordered',
        'done it myself', 'did that myself', 'sorted it',
        'i did it already',
    ]),
    ('rule body', [
        ',;:!?\\n\\u{2014}\\u{2013}', "'", 'if', 'unless', 'otherwise',
        'whether',
    ]),
    ('openers', [
        'ok', 'okay', 'oh', 'well', 'so', 'and', 'but', 'then',
        'actually', 'just', 'please', 'sorry', 'yeah', 'yea', 'yep',
        'yes', 'sure', 'no', 'nah', 'i', 'we', 'it', "it's", 'its',
        'that', "that's", 'thats', 'hey', 'um', 'uh',
    ]),
    ('trailers', [
        'it', 'that', 'this', 'them', 'already', 'myself', 'please',
        'thanks', 'thank', 'you', 'now', 'for', 'anymore', 'any', 'more',
        'though', 'anyway', 'too', 'sorry', 'then', 'ok', 'okay',
    ]),
    ('rule body', [
        ' ', ' ', ' ', ' ',
        'You handled it yourself: \\u{201C}\\(answer)\\u{201D}. I did nothing further.',
        'You called it off: \\u{201C}\\(answer)\\u{201D}. I did nothing further.',
    ]),
]

OPENS = re.compile(r"^\s*let\s+(\w+)\s*(?::\s*[^=]+)?=\s*\[\s*$")
BODY = 'rule body'


def vocabulary(text):
    """Every string literal in the rule, in source order, tagged with the list
    it belongs to. Comments are stripped as we go, because the prose around
    this rule quotes phrases ("leave it with the concierge") that are not part
    of it and must never be mistaken for part of it."""
    group, depth, tagged = BODY, 0, []
    for line in text.split("\n"):
        opening = OPENS.match(line)
        here = group
        if opening and depth == 0:
            group = here = opening.group(1)
            depth = 1
        i, n, cur = 0, len(line), None
        while i < n:
            c = line[i]
            if cur is None:
                if c == "/" and line[i + 1:i + 2] == "/":
                    break
                if c == '"':
                    cur = []
                    i += 1
                    continue
                if depth and not opening:
                    if c == "[":
                        depth += 1
                    elif c == "]":
                        depth -= 1
                        if depth == 0:
                            group = BODY
                i += 1
            elif c == "\\":
                cur.append(line[i:i + 2])
                i += 2
            elif c == '"':
                tagged.append((here, "".join(cur)))
                cur = None
                i += 1
            else:
                cur.append(c)
                i += 1
        if cur is not None:
            print("A string literal in the rule runs past the end of its line.")
            print("This extractor is line-based and cannot read that honestly,")
            print("so it reports nothing rather than a wrong answer:")
            print("    %s" % line.strip()[:70])
            raise SystemExit(1)
    return tagged


want = [(g, s) for g, items in GOLDEN for s in items]
have = vocabulary(open(sys.argv[1]).read())

if have == want:
    print("the rule's vocabulary is pinned: %d literals across %d lists, "
          "unchanged" % (len(want), len({g for g, _ in want if g != BODY})))
    raise SystemExit(0)

print("THE RULE'S WORD LISTS CHANGED AND NOTHING ELSE HERE WOULD SAY SO.")
print("")
groups = []
for g, _ in want + have:
    if g not in groups:
        groups.append(g)
changed = False
for g in groups:
    w = [s for gg, s in want if gg == g]
    h = [s for gg, s in have if gg == g]
    if w == h:
        continue
    changed = True
    pool = list(w)
    for s in h:
        if s in pool:
            pool.remove(s)
        else:
            print("  ADDED     %-10s %r" % (g, s))
    for s in pool:
        print("  REMOVED   %-10s %r" % (g, s))
    if sorted(w) == sorted(h):
        print("  REORDERED %-10s (same words, different order)" % g)
if not changed:
    print("  MOVED     the same words, in a different list or a different")
    print("            place in the rule")
print("")
print("This rule is registered tape, audit item #55, under HARNESS-LAWS.md Law 2.")
print("The behaviour cases in EndTheErrandTests.swift sample it; 24 of the 50")
print("phrases can be deleted with all of them still green, and one word added")
print("to `declines` files the owner's \"yes\" as their cancellation. So the")
print("lists are pinned exactly, and this is the check that noticed.")
print("")
print("If you MEANT to change them, you are widening or narrowing tape that is")
print("supposed to be on its way out. Say why in the commit, then update")
print("GOLDEN in this script to match.")
print("If you DELETED the rule: this whole leg goes with it, in the same diff")
print("as the registry entry and the ledger bullet.")
raise SystemExit(1)
VOCABULARY_LEG
    exit 2
fi

{
    echo "import Foundation"
    echo "enum EndOfErrand {"
    cat "$out/rule.swift"
    echo "}"
} > "$out/EndOfErrand.swift"

swiftc -O \
    "$out/EndOfErrand.swift" \
    "$here/EndTheErrandTests.swift" \
    -o "$out/enderrandtests"
"$out/enderrandtests"
