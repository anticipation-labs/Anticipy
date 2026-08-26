#!/bin/sh
# Checks for HOME'S COUNTED SENTENCES — the browser ask, the interview ask, the
# microphone taken away, and the day-zero examples said out loud.
#
#   sh app/ios/Tests/run_home_copy_tests.sh
#
# WHAT WENT WRONG THAT THIS WATCHES. Four sentences on Home carried a number,
# and the numbers were not read from the phone:
#
#   * the browser card spent four clauses on what pairing COSTS and never named
#     what was waiting on the other side of it, with the queue sitting three
#     inches below the card;
#   * the interview card opened "Six questions" — the numeral typed into the
#     prose — so somebody who had already answered three was told there were
#     six, and nothing on the phone could tell it otherwise;
#   * "Mic interrupted, taking it back…" claimed an ongoing recovery in the
#     present tense and read the same at four seconds as at four hours, which is
#     the 30-hour-deaf shape `CLAUDE.md` records;
#   * the day-zero example pair was hidden from VoiceOver outright, so a
#     first-timer using it got the promise and no sample of the delivery.
#
# The wording lives in `HomeCopy`, inside ContentView.swift between its ANCHOR
# markers — which drags in SwiftUI, the session and the microphone, none of
# which it touches. So this lifts the REAL source out from between the markers
# and compiles it alone with `PlainDuration`, the way run_home_feed_tests.sh
# does with the feed's placement rule. A copy of these strings in the test file
# would be honest only until somebody edited one side.
#
# The legs above the compile are the WIRING, and they are not decoration: a
# sentence that counts correctly and is never asked for its count is a sentence
# nobody reads. run_first_run_tests.sh records the shape they exist to catch —
# a policy "complete, correct and tested by nothing, in the pbxproj, with ZERO
# call sites".
#
# Exit code is the result. Non-zero means a case came back wrong.
set -e
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

view="$app/Views/ContentView.swift"

if ! python3 - "$view" <<'PY_LEG'; then
import re, sys

view_path = sys.argv[1]


def code(path):
    """The file with its comment LINES blanked out, line numbers preserved.

    Every leg below asks what SHIPS. The prose arguing for a rule is not the
    rule, and a leg that fails on the comment explaining itself is a leg that
    will be deleted rather than fixed.
    """
    return ["" if line.lstrip().startswith("//") else line
            for line in open(path, encoding="utf-8").read().split("\n")]


lines = code(view_path)
view = "\n".join(lines)
bad = []


def block_after(marker, start=0):
    """The braces-balanced block that opens on the line holding `marker`."""
    for i in range(start, len(lines)):
        if marker in lines[i]:
            depth = 0
            chunk = []
            for line in lines[i:]:
                chunk.append(line)
                depth += line.count("{") - line.count("}")
                if depth <= 0 and len(chunk) > 1:
                    return "\n".join(chunk)
            return "\n".join(chunk)
    return None


anchored = block_after("enum HomeCopy {")
if anchored is None:
    bad.append("`HomeCopy` is gone from ContentView.swift, so Home's counted\n"
               "      sentences are back to being written inline in three view\n"
               "      bodies where nothing can call them.")
    anchored = ""
elsewhere = view.replace(anchored, "")

# 1. THE BROWSER ASK READS THE QUEUE IT IS STANDING OVER.
#
#    The count can never be zero — `browserOffer` requires `!handling.isEmpty`
#    and the card renders inside the same condition — so there is no defensive
#    branch to write. What there IS to get wrong is spelling the number instead
#    of counting it: "three" was the number in this fix's own proposal, and a
#    hardcoded one is invisible until the day somebody has two.
card = block_after("private var browserOfferCard: some View {")
if card is None:
    bad.append("`browserOfferCard` is gone; this suite is measuring nothing\n"
               "      about the browser ask.")
    card = ""
if "handling.count" not in card:
    bad.append("The browser card no longer reads `handling.count`. The queue it\n"
               "      is standing over is the only thing that makes this an answer\n"
               "      rather than a chore, and a typed number is wrong the first\n"
               "      day somebody has a different one.")
for fn in ("browserHeadline", "browserBody", "browserButton"):
    if "HomeCopy.%s(" % fn not in card:
        bad.append("The browser card does not ask `HomeCopy.%s`. Its three\n"
                   "      sentences branch on ONE count; written in two places they\n"
                   "      drift, and the card then disagrees with itself." % fn)


def one_argument(block, pattern, what, why):
    """Every call matching `pattern` passes the same expression, character for
    character.

    ASKING WHETHER THE THREE NAMES APPEAR PROVES ONLY THAT THEY WERE CALLED.
    Changing one call site to `HomeCopy.browserBody(waiting: waiting + 1)` left
    the card reading "These need your Chrome" over "the 4 things below" with
    "Set it up — 3 waiting" on the button, and every leg in this file stayed
    green. One count means one expression, and this is the leg that says so.
    """
    found = re.findall(pattern, block)
    seen = sorted({" ".join(a.split()) for a in found})
    if len(seen) > 1:
        bad.append("%s is passed %d different expressions (%s). %s"
                   % (what, len(seen), "; ".join(seen), why))
    return found


one_argument(
    card,
    r"HomeCopy\.browser(?:Headline|Body|Button)\(waiting:\s*([^)]+)\)",
    "The browser card's count",
    "Its three sentences are one\n"
    "      answer about one queue: a headline that says these need your Chrome,\n"
    "      a body that says how many, and a button that prices the tap. Fed from\n"
    "      two expressions the card disagrees with itself in front of the person\n"
    "      it is asking for a permission.")
if re.search(r'Text\("Set it up"\)', card):
    bad.append("The browser button is back to a bare \"Set it up\". The count on\n"
               "      the button is what prices the tap while the thumb is still\n"
               "      over the card.")

# 2. THE INTERVIEW ASK COUNTS WHAT SHE ALREADY HOLDS.
#
#    `showInterviewOffer` gates on `!isComplete` alone, which is right — it asks
#    whether anything is LEFT. The card then has to say how much, and it used to
#    describe the whole script to somebody halfway through it.
offer = block_after("private var interviewOfferCard: some View {")
if offer is None:
    bad.append("`interviewOfferCard` is gone; this suite is measuring nothing\n"
               "      about the interview ask.")
    offer = ""
if "InterviewProgress().answeredCount" not in offer:
    bad.append("The interview card does not read `InterviewProgress().answeredCount`.\n"
               "      Someone with three answers behind them is being told there are\n"
               "      six questions again — the work counting for nothing on the one\n"
               "      screen that asks for more of it.")
if "InterviewQuestion.script.count" not in offer:
    bad.append("The interview card does not read `InterviewQuestion.script.count`.\n"
               "      The total has to come from the script, or the day a seventh\n"
               "      question ships this card goes on saying six.")
for fn in ("interviewTitle", "interviewBody", "interviewButton"):
    if "HomeCopy.%s(" % fn not in offer:
        bad.append("The interview card does not ask `HomeCopy.%s`." % fn)
one_argument(
    offer,
    r"HomeCopy\.interview(?:Title|Body|Button)\(answered:\s*([^,)]+)[,)]",
    "The interview card's answered count",
    "Three sentences about how much of\n"
    "      the script is behind you, and two of them disagreeing is the same\n"
    "      failure as the typed \"Six questions\" this card was fixed for.")
one_argument(
    offer,
    r"HomeCopy\.interview(?:Body|Button)\(answered:[^,]+,\s*total:\s*([^)]+)\)",
    "The interview card's total",
    "The body and the button count out of\n"
    "      the same script or they name two different scripts.")

# 3. THE NUMERALS AND THE SENTENCES LIVE IN ONE PLACE.
#
#    Each of these was a literal in a view body, and each is now built from a
#    count. One left behind is one that goes stale silently.
for literal, why in (
    ('"Six questions', "the script's length, typed into prose"),
    ('"Want me to actually know you?"', "the interview title"),
    ('"I work inside your own Chrome', "the browser body"),
    ('"Mic interrupted', "the interruption line"),
    ('"I\'ll get that invoice over to you tonight"', "the example heard line"),
    ('"Draft the invoice email to Devon"', "the example job"),
):
    if literal in elsewhere:
        bad.append("%s is written into a view body again (%s).\n"
                   "      It belongs in `HomeCopy`, where a test can call it and where\n"
                   "      the count it depends on is an argument rather than a guess."
                   % (literal, why))

# 4. THE INTERRUPTION GAP IS NEVER READ ON THE POLL.
#
#    THIS IS THE ONE THAT COSTS SOMETHING IF IT GOES. `persistedEvents` is a
#    synchronous `queue.sync` over two files plus a parse of every line in them,
#    and Home redraws every three seconds. The same read reached from a view
#    body is disk I/O on the main thread twenty times a minute, for a number
#    that moves by three seconds.
reader = block_after("private func readInterruptionGap() async {")
if reader is None:
    bad.append("`readInterruptionGap` is gone. The interruption line can only\n"
               "      carry a duration if something reads the journal off the main\n"
               "      thread, and nothing else on this screen may.")
    reader = ""
#    THESE LEGS WERE TOKEN COUNTS AND TOKEN COUNTS PROVED NOTHING. They asked
#    whether `Task.detached` and a journal read both appeared SOMEWHERE in this
#    function. A mutation that left
#
#        _ = Task.detached(priority: .utility) { }
#        let tally = ListenTally.of(ListenJournal.shared.persistedEvents, now: Date())
#
#    behind — the entire disk read and parse back on the main actor of an
#    @MainActor func, precisely the regression the paragraph above claims to
#    catch — went green through them. So the read is located structurally now:
#    it has to sit INSIDE the closure's braces, not merely in the same file as
#    one.
#
#    And it sweeps every accessor, not one. `persistedEvents` is one door onto
#    that `queue.sync`; `ListenJournal.persistedLines` (`ListenJournal.swift:353`)
#    is another onto the same files, and a leg naming only the first is blind to
#    the second from the day somebody reaches for it in a view body.
reads = re.findall(r"ListenJournal\.shared\.persisted\w*", view)
if len(reads) != 1:
    bad.append("The journal is read %d times in this file (%s); it belongs in\n"
               "      `readInterruptionGap` and nowhere else. A second read is a\n"
               "      synchronous `queue.sync` over two files plus a parse of every\n"
               "      line in them, on the main thread, on a screen that redraws\n"
               "      twenty times a minute."
               % (len(reads), ", ".join(sorted(set(reads))) or "none"))


def detached_body(block):
    """The inside of the first `Task.detached` closure in `block`, braces-balanced."""
    at = block.find("Task.detached")
    if at < 0:
        return None
    brace = block.find("{", at)
    if brace < 0:
        return None
    depth = 0
    for i in range(brace, len(block)):
        if block[i] == "{":
            depth += 1
        elif block[i] == "}":
            depth -= 1
            if depth == 0:
                return block[brace + 1:i]
    return None


detached = detached_body(reader)
if detached is None:
    bad.append("`readInterruptionGap` no longer detaches. The fold is file I/O\n"
               "      plus a parse of every line the journal holds, and its caller is\n"
               "      a view.")
    detached = ""
in_reader = len(re.findall(r"ListenJournal\.shared\.persisted\w*", reader))
in_closure = len(re.findall(r"ListenJournal\.shared\.persisted\w*", detached))
if in_reader == 0:
    bad.append("The journal read has moved out of `readInterruptionGap`, which\n"
               "      is the only place on this screen that is off the main thread\n"
               "      and off the three-second poll.")
elif in_closure != in_reader:
    bad.append("`readInterruptionGap` reads the journal OUTSIDE its\n"
               "      `Task.detached` closure (%d of %d reads are outside). A\n"
               "      detached task standing next to a main-actor disk read is not a\n"
               "      detached disk read; this function is `@MainActor`, so the read\n"
               "      and the fold both have to be inside the braces."
               % (in_reader - in_closure, in_reader))
if "ListenTally.of(" not in detached:
    bad.append("The fold has left the detached closure. Reading the lines off\n"
               "      the main thread and then parsing every one of them back on it\n"
               "      moves the cost rather than paying it somewhere else.")
if not re.search(r"=\s*await\s+Task\.detached", reader):
    bad.append("`readInterruptionGap` does not await the detached task into a\n"
               "      value. A fire-and-forget `Task.detached` whose result nothing\n"
               "      reads is a task that satisfies a grep and answers no question.")
if "now: Date()" not in detached:
    bad.append("The tally is folded without `now:`. A fold that can only measure\n"
               "      to the journal's own last line answers \"58 min\" for a phone\n"
               "      that has been deaf since breakfast, because on that day the\n"
               "      last line IS the failure.")
if not re.search(r'guard session\.listener\.suspended else', reader):
    bad.append("`readInterruptionGap` no longer returns early while the\n"
               "      microphone is fine. That guard is what keeps this off the disk\n"
               "      on every ordinary day.")
if not re.search(r'case \.stoppedByOther', reader):
    bad.append("`readInterruptionGap` no longer requires `.stoppedByOther`. An\n"
               "      `.unknown` record has no session line in it at all, and a\n"
               "      duration invented for it is a number about nothing.")
gap_calls = view.count("HomeCopy.micInterrupted(")
if gap_calls != 1:
    bad.append("`HomeCopy.micInterrupted` is rendered %d times. It belongs on\n"
               "      the listening card's suspended branch and nowhere else."
               % gap_calls)
briefing = block_after("private var briefingText: String {")
if briefing and ("interruptedGap" in briefing or "heardNothingSince" in briefing):
    bad.append("The briefing carries the interruption gap. `briefingText` is\n"
               "      captured ONCE into `briefingShown` and never recomputed, so a\n"
               "      duration put there freezes at whatever it was when the\n"
               "      typewriter ran and then goes on being stated as now.")

# 4b. WHAT IS STORED IS THE INSTANT, WHICH IS WHY THE NUMBER CANNOT FREEZE.
#
#     Same defect, one layer down, and it survived the first pass of this fix.
#     `.task(id:)` restarts only when the id VALUE changes, and the key on the
#     interruption read is `"\(suspended)|\(scenePhase)"` — both halves constant
#     for the whole of an outage. So it runs once at the transition and never
#     again, and a stored COUNT OF SECONDS is then drawn unchanged for as long
#     as the screen stays up: somebody on speakerphone with Anticipy open read
#     the same "4 min" at minute forty.
#
#     The fix may NOT be to re-read on the poll — the leg above is the reason,
#     and it is the expensive one. Storing the instant and subtracting at the
#     draw costs one subtraction per redraw and no disk at all.
if not re.search(r"@State private var heardNothingSince: Date\?", view):
    bad.append("`heardNothingSince` is not a `Date?` on this view. The stored\n"
               "      value has to be WHEN, not HOW LONG: a stored duration is read\n"
               "      once at the interruption and then goes on being stated as now\n"
               "      for as long as the screen is up, which is the defect this whole\n"
               "      line was rewritten to end.")
if re.search(r"@State private var interruptedGap", view):
    bad.append("`interruptedGap` is `@State` again. Held rather than derived it\n"
               "      is a duration that freezes; it belongs computed off\n"
               "      `heardNothingSince` where the label is drawn.")
derived = block_after("private var interruptedGap: Int? {")
if derived is None or "Date().timeIntervalSince" not in derived:
    bad.append("`interruptedGap` no longer subtracts `heardNothingSince` from\n"
               "      `Date()` at the draw. That subtraction is the only thing making\n"
               "      the number on the card move while the microphone stays gone.")
if derived is not None and re.search(r"ListenJournal|ListenTally\.of\(", derived):
    bad.append("`interruptedGap` reads the journal. It is evaluated on every\n"
               "      redraw of Home — three seconds apart, all day — which is the\n"
               "      one thing the leg above exists to keep off this screen.")

# 5. THE DAY-ZERO EXAMPLES ARE READ OUT, NOT HIDDEN — AND STILL READ AS EXAMPLES.
empty = block_after("private var emptyState: some View {")
if empty is None:
    bad.append("`emptyState` is gone; this suite is measuring nothing about the\n"
               "      day-zero screen.")
    empty = ""
if "accessibilityElement(children: .ignore)" not in empty:
    bad.append("The example pair is not `.accessibilityElement(children: .ignore)`.\n"
               "      Hidden, a first-timer using VoiceOver gets the promise and no\n"
               "      sample of the delivery at all.")
if "children: .contain" in empty:
    bad.append("The example pair uses `.contain`. That leaves the children\n"
               "      individually focusable, so VoiceOver walks into the fixture\n"
               "      card's inert \"Send it\" and \"Not now\" buttons — a decision to\n"
               "      make about an invoice that does not exist.")
if "HomeCopy.exampleCardsLabel" not in empty:
    bad.append("The example pair's label is not `HomeCopy.exampleCardsLabel`.\n"
               "      A hand-written copy of the two fixture sentences goes stale the\n"
               "      first time somebody edits the cards, and a VoiceOver user is\n"
               "      then read a screen that is not on the screen.")
if "allowsHitTesting(false)" not in empty:
    bad.append("The example pair is tappable again. It is a sample, and its\n"
               "      buttons do nothing.")
if "opacity(1.0)" in empty or "opacity(1)" in empty:
    bad.append("The example pair is at full strength. The caption plus a\n"
               "      visibly quieter pair is what says \"example\"; a first-timer\n"
               "      reading a fixture as a real job is a worse failure than the\n"
               "      one this fix was for.")

if bad:
    print("HOME'S COUNTED SENTENCES ARE NOT WIRED THE WAY THESE CHECKS ASSUME.")
    print("")
    for b in bad:
        print("  - %s" % b)
    raise SystemExit(1)

print("the browser ask counts the queue it stands over, the interview ask counts "
      "what she already holds, the interruption gap is read off the main thread "
      "and only where it can be seen, and the day-zero examples are read out as "
      "examples")
PY_LEG
    exit 2
fi

# The END rule comes first: the closing marker CONTAINS the opening one as a
# substring, so testing for the opening one first re-arms it and swallows the
# rest of the file.
awk '/END ANCHOR: home card copy/{f=0;next} /ANCHOR: home card copy/{f=1;next} f' \
    "$view" > "$out/copy.swift"
if [ ! -s "$out/copy.swift" ]; then
    echo "Found no code between the ANCHOR markers in ContentView.swift."
    echo "Either the markers moved or the copy did; these checks are compiling"
    echo "nothing, which is worse than not having them."
    exit 2
fi
if ! grep -q 'enum HomeCopy' "$out/copy.swift"; then
    echo "The anchored region no longer contains HomeCopy."
    exit 2
fi
# Wording is not a look. A copy type that can reach for a Color is one that will
# eventually return a red one over a queue that is merely long — which is the
# badge this whole set of fixes exists to refuse.
if grep -qE '^ *import +(SwiftUI|UIKit)' "$out/copy.swift"; then
    echo "The anchored region imports SwiftUI or UIKit. Home's sentences are"
    echo "words, not a look: no colour, no badge, no meter can be decided here."
    exit 2
fi
echo "the anchored region is $(wc -l < "$out/copy.swift" | tr -d ' ') lines of the shipping source"

{
    echo "import Foundation"
    cat "$out/copy.swift"
} > "$out/HomeCopy.swift"

swiftc -O \
    "$out/HomeCopy.swift" \
    "$app/Audio/PlainDuration.swift" \
    "$here/HomeCopyTests.swift" \
    -o "$out/homecopytests"
"$out/homecopytests"
