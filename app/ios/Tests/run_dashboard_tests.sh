#!/bin/sh
# The conversation dashboard — the screen where somebody talks to Anticipy.
#
#   sh app/ios/Tests/run_dashboard_tests.sh
#
# DashboardPolicy is pure Foundation, so the production source is compiled
# straight in. The SwiftUI halves are held to source facts here, and the first
# of them is the one that matters most.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
app="$here/../Anticipy"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

policy="$app/DashboardPolicy.swift"
view="$app/Views/ConversationDashboard.swift"
kit="$app/Views/DashboardKit.swift"
home="$app/Views/ContentView.swift"
dash="$app/Views/ConversationDashboard.swift"
for f in "$policy" "$view" "$kit" "$home"; do
    [ -f "$f" ] || { echo "missing $f"; exit 2; }
done

# Source with the comments taken out. Every grep below asks about CODE, and a
# policy whose prose mentions a word it must never use is still a policy that
# never uses it.
code() { sed 's://.*$::' "$1"; }

# ---------------------------------------------------------------- LAW ONE
# The tempting version of this screen picks your to-dos out of what you say.
# That is a keyword matcher wearing an animation, and HARNESS-LAWS law 1
# forbids it: meaning belongs to a model with full context, and every row
# reaching this screen was already decided by one. So the policy may sort,
# group and label — and may not look inside the words.
if code "$policy" | grep -qE 'NSRegularExpression|range\(of:|contains\("|hasPrefix\("|hasSuffix\("|localizedCaseInsensitiveContains'; then
    echo "DashboardPolicy reads the WORDS of what somebody said."
    echo
    echo "Law 1: no regex, word list or threshold may decide what a sentence"
    echo "MEANS. Every row that reaches this screen already carries a verdict —"
    echo "a job has a status and a lane, an event has a decision — and this"
    echo "file arranges those verdicts in time. A dashboard that picks out"
    echo "commitments by looking for 'remind me' is the exact thing the law"
    echo "was written about, and it fails on the first person who says it"
    echo "differently."
    code "$policy" | grep -nE 'NSRegularExpression|range\(of:|contains\("|hasPrefix\("|hasSuffix\("|localizedCaseInsensitiveContains'
    exit 2
fi
if code "$view" | grep -qE 'NSRegularExpression|localizedCaseInsensitiveContains|\.lowercased\(\)\.contains'; then
    echo "ConversationDashboard reads the words too. Same law, same reason."
    exit 2
fi

# --------------------------------------------------------------- SEATBELT
# "Nothing sends without your OK" is a promise the screen keeps or breaks.
if ! grep -q 'pendingApproval' "$view"; then
    echo "The dashboard no longer asks DashboardPolicy for the waiting approval."
    echo "An approval that is only a turn somewhere in a scroll is an approval"
    echo "somebody scrolls past, and this product's one hard promise is that"
    echo "nothing is sent until they did not."
    exit 2
fi
if ! grep -q 'case .approval' "$view"; then
    echo "The dashboard draws no approval turn at all."
    exit 2
fi
# The bar must not be able to APPROVE. A one-tap yes on a banner is the
# accident the seatbelt exists to prevent.
bar=$(awk '/private func waitingBar/{g=1} g{print} g&&/^    }$/{exit}' "$view")
if printf '%s\n' "$bar" | grep -qE 'onApprove|approve\(|confirm\(|send\('; then
    echo "The waiting bar can approve something. It may only carry somebody to"
    echo "the card that asks properly; a yes on a banner is a yes nobody read."
    exit 2
fi
if ! grep -q 'ConfirmJobCard(' "$home"; then
    echo "Home no longer builds ConfirmJobCard. That card is the one place the"
    echo "consequence of an action is written down before it happens."
    exit 2
fi

# ------------------------------------------------------- WHAT IT INHERITS
# The onboarding coach mark points at the listen control. Home has always
# published that anchor; the redesign must not have dropped it.
if ! grep -q 'ListenControlAnchorKey' "$view"; then
    echo "The listen control no longer publishes ListenControlAnchorKey."
    echo "The coach mark at the end of first run points at a frame Home"
    echo "reports, and with no anchor it has nothing to point at."
    exit 2
fi
if ! grep -q 'accessibilityLabel("Settings")' "$home"; then
    echo "Settings lost its accessibility label. The walk finds that control"
    echo "by name, and so does anybody using VoiceOver."
    exit 2
fi

# ------------------------------------------------------------ THE COLOURS
if code "$kit" | grep -q 'Color(hex:' || code "$view" | grep -q 'Color(hex:'; then
    echo "The dashboard names a colour instead of reading a Theme role."
    exit 2
fi

# -------------------------------------------------------------- the walk
# main.swift, because swiftc allows top-level code under that name only.
# ================== EVERY CONTROL THAT CAN BE TAPPED WHILE LISTENING STOPS IT
# 2026-09-06: Home had exactly ONE control bound to stopListening — the tick on
# the capture face — and the X beside it fired no listening callback at all. It
# only flipped `mode` back to .thread, so the microphone kept running and the
# face carrying the tick became UNREACHABLE, because `mode = .capture` happens
# only on a false->true edge of `listening` and listening never went false.
# From that tap onward Home could not stop capture at all.
if ! code "$dash" | grep -q 'if listening { onStopListening() }'; then
    echo "The capture face's dismiss button does not end the capture."
    echo
    echo "It is the universal 'close this' affordance. Wired to view state"
    echo "alone it strands a running microphone with no stop anywhere on Home —"
    echo "and the face that HAS a stop cannot be re-entered, because it is"
    echo "gated on a false->true edge of \`listening\` that never comes."
    exit 2
fi

# ...and the foot control must be DERIVED, never hardwired to start.
if code "$dash" | grep -q 'Haptics.engage()$' && \
   code "$dash" | grep -A 1 'Haptics.engage()$' | grep -q '^\s*onStartListening()'; then
    echo "The foot control is hardwired to onStartListening()."
    echo
    echo "A button that always says 'Listen with phone' says it over a LIVE"
    echo "microphone, and PhoneListener.begin() guards on !isListening, so the"
    echo "tap is a silent no-op. Derive it from ListenControlPolicy.face, which"
    echo "exists for exactly this and was unwired when Home became the thread."
    exit 2
fi
if ! code "$dash" | grep -q 'ListenControlPolicy.face('; then
    echo "The dashboard no longer asks ListenControlPolicy what the control is."
    exit 2
fi

# ============================== THE TASK LEADS, AND THE VERDICT SURVIVES
# The dashboard could only ever draw a transcript because the mapping into
# HeardRow kept id/text/at and dropped the brain's `decision` and `goal`. The
# policy layer then had nothing to tell a task from a sentence.
if ! code "$policy" | grep -q 'var goal: String?'; then
    echo "HeardRow no longer carries the goal the brain stamped."
    echo
    echo "Without it the policy cannot tell a line the brain recognised as"
    echo "something to do from a line it called noise, and every line renders"
    echo "as the same grey bubble — the whole transcript, no tasks."
    exit 2
fi
if ! code "$home" | grep -q 'goal: \$0.goal'; then
    echo "ContentView drops the verdict again when it builds HeardRow."
    exit 2
fi
# But every line must still APPEAR. Filtering to judged lines only was tried
# and reverted: somebody talking to a phone that had judged nothing watched an
# empty screen and concluded she was dead.
if code "$policy" | grep -qE 'for row in heard where.*goal|heard\.filter'; then
    echo "The thread filters heard lines by whether they were judged."
    echo "Leading with the task is a change of FACE, never of membership."
    exit 2
fi

cp "$here/DashboardTests.swift" "$out/main.swift"
swiftc "$policy" "$out/main.swift" -o "$out/dashboardtests"
"$out/dashboardtests"
