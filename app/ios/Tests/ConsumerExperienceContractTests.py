#!/usr/bin/env python3
"""Source contract for the shipping consumer/developer SwiftUI route graph.

The views under test depend on SwiftUI, LocalAuthentication, and app-only
environment objects. Rebuilding look-alike views in a test target would prove
the duplicate, so this gate walks the named declarations in shipping source.
Comments and string contents are masked for structural checks; visible labels
are checked separately against the raw declaration bodies.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


IOS = Path(sys.argv[1]).resolve()
VIEWS = IOS / "Anticipy" / "Views"
PATHS = {
    "content": VIEWS / "ContentView.swift",
    "home": VIEWS / "SettingsHomeView.swift",
    "advanced": VIEWS / "SettingsAdvancedView.swift",
    "personalization": VIEWS / "SettingsPersonalizationView.swift",
    "privacy": VIEWS / "SettingsPrivacyDataView.swift",
    "auth": VIEWS / "AuthView.swift",
    "developer": VIEWS / "DeveloperDiagnosticsView.swift",
    "preferences": IOS / "Anticipy" / "AppPreferences.swift",
    "backend": IOS / "Anticipy" / "Backend" / "AnticipyBackend.swift",
    "session": IOS / "Anticipy" / "AnticipyApp.swift",
    "notifier": IOS / "Anticipy" / "Notifier.swift",
}
FAILURES: list[str] = []

missing = [str(path) for path in PATHS.values() if not path.is_file()]
if missing:
    print("CONSUMER EXPERIENCE CONTRACT COULD NOT READ SHIPPING SOURCE.")
    for path in missing:
        print(f"  - missing: {path}")
    raise SystemExit(2)

SOURCE = {name: path.read_text() for name, path in PATHS.items()}
PROJECT_YML = (IOS / "project.yml").read_text()
INFO_PLIST = (IOS / "Anticipy" / "Info.plist").read_text()


def swift_code(text: str) -> str:
    """Mask comments and string contents while preserving length/newlines."""

    out = list(text)
    i = 0
    state = "code"
    block_depth = 0
    while i < len(text):
        if state == "code":
            if text.startswith("//", i):
                out[i:i + 2] = "  "
                i += 2
                state = "line_comment"
            elif text.startswith("/*", i):
                out[i:i + 2] = "  "
                i += 2
                block_depth = 1
                state = "block_comment"
            elif text.startswith('"""', i):
                out[i:i + 3] = "   "
                i += 3
                state = "triple_string"
            elif text[i] == '"':
                out[i] = " "
                i += 1
                state = "string"
            else:
                i += 1
            continue

        if state == "line_comment":
            if text[i] == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
            continue

        if state == "block_comment":
            if text.startswith("/*", i):
                out[i:i + 2] = "  "
                i += 2
                block_depth += 1
            elif text.startswith("*/", i):
                out[i:i + 2] = "  "
                i += 2
                block_depth -= 1
                if block_depth == 0:
                    state = "code"
            else:
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            continue

        if state == "string":
            if text[i] == "\\":
                out[i] = " "
                if i + 1 < len(text):
                    if text[i + 1] != "\n":
                        out[i + 1] = " "
                    i += 2
                else:
                    i += 1
            elif text[i] == '"':
                out[i] = " "
                i += 1
                state = "code"
            else:
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            continue

        if state == "triple_string":
            if text.startswith('"""', i):
                out[i:i + 3] = "   "
                i += 3
                state = "code"
            else:
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            continue

    return "".join(out)


def swift_without_comments(text: str) -> str:
    """Mask comments while preserving executable code and visible strings."""

    out = list(text)
    i = 0
    state = "code"
    block_depth = 0
    while i < len(text):
        if state == "code":
            if text.startswith("//", i):
                out[i:i + 2] = "  "
                i += 2
                state = "line_comment"
            elif text.startswith("/*", i):
                out[i:i + 2] = "  "
                i += 2
                block_depth = 1
                state = "block_comment"
            elif text.startswith('"""', i):
                i += 3
                state = "triple_string"
            elif text[i] == '"':
                i += 1
                state = "string"
            else:
                i += 1
            continue
        if state == "line_comment":
            if text[i] == "\n":
                state = "code"
            else:
                out[i] = " "
            i += 1
            continue
        if state == "block_comment":
            if text.startswith("/*", i):
                out[i:i + 2] = "  "
                i += 2
                block_depth += 1
            elif text.startswith("*/", i):
                out[i:i + 2] = "  "
                i += 2
                block_depth -= 1
                if block_depth == 0:
                    state = "code"
            else:
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        if state == "string":
            if text[i] == "\\":
                i += 2
            elif text[i] == '"':
                i += 1
                state = "code"
            else:
                i += 1
            continue
        if state == "triple_string":
            if text.startswith('"""', i):
                i += 3
                state = "code"
            else:
                i += 1
            continue
    return "".join(out)


def body(text: str, declaration: str, label: str) -> str:
    """Return one braced declaration's raw body using masked brace matching."""

    masked = swift_code(text)
    match = re.search(declaration, masked, re.MULTILINE)
    if not match:
        FAILURES.append(f"{label} is missing; the gate cannot inspect its shipping body.")
        return ""
    opening = masked.find("{", match.start(), match.end())
    if opening < 0:
        FAILURES.append(f"{label} has no traceable opening brace.")
        return ""
    depth = 0
    for index in range(opening, len(masked)):
        if masked[index] == "{":
            depth += 1
        elif masked[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1:index]
    FAILURES.append(f"{label} has no balanced closing brace.")
    return ""


def struct(text: str, name: str) -> str:
    return body(text, rf"\b(?:private\s+)?struct\s+{re.escape(name)}\b[^{{]*\{{", name)


def require(label: str, text: str, pattern: str, reason: str) -> None:
    if not re.search(pattern, swift_code(text), re.MULTILINE | re.DOTALL):
        FAILURES.append(f"{label}: {reason}")


def forbid(label: str, text: str, pattern: str, reason: str) -> None:
    if re.search(pattern, swift_code(text), re.MULTILINE | re.DOTALL):
        FAILURES.append(f"{label}: {reason}")


def visible(label: str, text: str, pattern: str, reason: str) -> None:
    if not re.search(pattern, swift_without_comments(text), re.MULTILINE | re.DOTALL):
        FAILURES.append(f"{label}: {reason}")


def count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, swift_code(text), re.MULTILINE | re.DOTALL))


# Consumer Home: the one transcript renderer is a fixed day-zero fixture. The
# account transcript may feed only brain-stamped goal recaps, never raw cards.
home = struct(SOURCE["content"], "HomeView")
for pattern, name in (
    (r"\bsession\s*\.\s*listener\s*\.\s*partial\b", "live recognizer partial"),
    (r"\bsession\s*\.\s*sessionLines\b", "finalized launch lines"),
    (r"\bheardSection\b", "old Heard section"),
    (r"\bheardGroups\b", "old Heard shelf"),
    (r"\bConversationCard\s*\(", "raw conversation cards"),
):
    forbid("Consumer Home speech boundary", home, pattern,
           f"Home references the {name}; raw speech belongs in Settings.")

empty = body(home, r"\bprivate\s+var\s+emptyState\s*:\s*some\s+View\s*\{",
             "HomeView.emptyState")
if count(home, r"\bTranscriptRow\s*\(") != 1 or count(empty, r"\bTranscriptRow\s*\(") != 1:
    FAILURES.append(
        "Consumer Home speech boundary: TranscriptRow must occur exactly once in HomeView, "
        "inside the static day-zero example; a live TranscriptRow restores the word log."
    )
require("Day-zero example", empty,
        r"\btext\s*:\s*HomeCopy\s*\.\s*exampleHeard\b",
        "the sole TranscriptRow is not pinned to the static example fixture.")
forbid("Day-zero example", empty, r"\bsession\s*\.\s*transcript\b",
       "the empty-state fixture reads the account transcript.")

insights = body(home,
                r"\bprivate\s+var\s+recentConversationInsights\s*:\s*\[HomeConversationInsight\]\s*\{",
                "HomeView.recentConversationInsights")
insight_refs = count(insights, r"\bsession\s*\.\s*transcript\b")
if insight_refs != 1:
    FAILURES.append(
        "Consumer Home speech boundary: recentConversationInsights must have exactly one "
        f"transcript input; found {insight_refs}."
    )
# Home may observe the newest line to decide whether a contextual permission
# question is due. That is not a transcript renderer. What may never return is
# a collection/text builder drawing the archive itself.
for pattern, name in (
    (r"ForEach\s*\([^)]*session\s*\.\s*transcript", "a transcript loop"),
    (r"Text\s*\([^)]*session\s*\.\s*transcript", "direct transcript text"),
    (r"ConversationCard\s*\([^)]*session\s*\.\s*transcript", "transcript cards"),
):
    forbid("Consumer Home speech boundary", home, pattern,
           f"Home renders {name} instead of keeping it in Settings.")
require("Consumer recap grounding", insights,
        r"\bguard\s+let\s+title\s*=\s*group\s*\.\s*latestGoalTitle\b",
        "recaps do not require the newest brain-stamped goal correction.")
visible("Consumer recap grounding", insights, r'state:\s*"Recent conversation"',
        "the recap assigns an unproven action state instead of a neutral conversation label.")
for accessor in ("front", "lines", "rows", "text"):
    forbid("Consumer recap grounding", insights, rf"\bgroup\s*\.\s*{accessor}\b",
           f"group.{accessor} can put raw speech back on Home.")

# A worker completion is persisted twice for two different consumers: the job
# drives the receipt card and its linked anticipy_says event drives recaps when
# that job is not on screen. While the terminal job is in the visible deck,
# Home must not turn those two records into two apparent outcomes.
found_for_you = body(
    home,
    r"\bprivate\s+var\s+foundForYou\s*:\s*\[BrainEvent\]\s*\{",
    "HomeView.foundForYou",
)
require("One completed-job representation", found_for_you,
        r"Set\s*\(\s*finishedShown\s*\.\s*map\s*\(\s*\\\.id\s*\)\s*\)",
        "the recap filter does not derive the terminal job ids actually visible in Done.")
require("One completed-job representation", found_for_you,
        r"HomeFeedPolicy\s*\.\s*showsDoneEvent\s*\(\s*"
        r"externalEventID\s*:\s*ev\s*\.\s*external_event_id\s*,\s*"
        r"visibleTerminalJobIDs\s*:\s*visibleTerminalJobIDs\s*\)",
        "a linked worker result can render beside its own terminal job card.")
fresh_line = body(
    home,
    r"\bprivate\s+var\s+freshAnticipyLine\s*:\s*String\?\s*\{",
    "HomeView.freshAnticipyLine",
)
require("One completed-job representation", fresh_line,
        r"HomeFeedPolicy\s*\.\s*showsDoneEvent\s*\(\s*"
        r"externalEventID\s*:\s*event\s*\.\s*external_event_id\s*,[\s\S]*?"
        r"Set\s*\(\s*finishedShown\s*\.\s*map\s*\(\s*\\\.id\s*\)\s*\)",
        "the briefing can repeat a job-result event already visible in Done.")
briefing_card = body(
    home,
    r"\bprivate\s+var\s+anticipyCardView\s*:\s*some\s+View\s*\{",
    "HomeView.anticipyCardView",
)
require("One completed-job representation", briefing_card,
        r"if\s+let\s+says\s*=\s*freshAnticipyLine",
        "the briefing bypasses the linked-result filter.")
forbid("One completed-job representation", briefing_card,
       r"session\s*\.\s*freshAnticipyEvent",
       "the briefing reads the raw newest event instead of the filtered Home line.")
brain_event = struct(SOURCE["backend"], "BrainEvent")
require("One completed-job representation", brain_event,
        r"let\s+external_event_id\s*:\s*String\?",
        "BrainEvent does not decode the worker's job-result link.")

# A transport error is not a server refusal. The request can be accepted and
# claimed before its response is lost, so action cards may retry only after an
# exact read proves the original state remains.
write_action = body(
    SOURCE["session"],
    r"\bprivate\s+func\s+write\s*\(\s*id\s*:\s*String\s*,"
    r"[\s\S]*?\)\s+async\s*->\s*Bool\s*\{",
    "AnticipySession.write",
)
require("Uncertain action reconciliation", write_action,
        r"ActionWritePolicy\s*\.\s*isVerifiedRefusal",
        "all transport errors are still treated as proven refusals.")
require("Uncertain action reconciliation", write_action,
        r"reconcilePendingJob\s*\(\s*id\s*:\s*id\s*,\s*pending\s*:\s*pending\s*\)",
        "a response-lost action is not reconciled against its exact job.")
fetch_job = body(
    SOURCE["backend"],
    r"\bfunc\s+fetchJob\s*\(\s*id\s*:\s*String\s*\)\s+async\s+throws\s*->\s*AgentJob\s*\{",
    "AnticipyBackend.fetchJob",
)
require("Uncertain action reconciliation", fetch_job,
        r"appendingPathComponent\s*\(\s*id\s*\)[\s\S]*?"
        r"JSONDecoder\s*\(\s*\)\s*\.\s*decode\s*\(\s*AgentJob\s*\.\s*self",
        "reconciliation does not read and decode the exact canonical job row.")
confirm_card = struct(SOURCE["content"], "ConfirmJobCard")
visible("Uncertain action copy", confirm_card, r'"Check outcome"',
        "an unverified action still presents an immediate retry.")
require("Uncertain action control", confirm_card,
        r"if\s+unverified\s*\{[\s\S]*?session\s*\.\s*reconcileWrite\s*\(\s*job\s*\)"
        r"[\s\S]*?\}\s*else\s*\{[\s\S]*?session\s*\.\s*confirm",
        "the unverified action button can resend instead of only checking.")
for phrase in (r"Nothing was sent", r"She hasn't heard it"):
    visible_code = swift_without_comments(SOURCE["content"])
    if re.search(phrase, visible_code, re.IGNORECASE):
        FAILURES.append(
            "Uncertain action copy: response loss still makes the unverified claim "
            f"`{phrase}`."
        )


# Listening History: Settings -> Privacy & Data -> archive, with the server's
# page boundary retained and prior pages accumulated by stable event id.
settings = struct(SOURCE["home"], "SettingsHomeView")
visible("Settings index", settings, r'NavRow\("Privacy & Data"',
        "Privacy & Data is not visible on the Settings index.")
require("Settings index", settings, r"route\s*=\s*\.privacyData\b",
        "the privacy row does not select its route.")
require("Settings index", settings,
        r"case\s+\.privacyData\s*:\s*SettingsPrivacyDataView\s*\(\s*session\s*:\s*session\s*\)",
        "privacyData does not open SettingsPrivacyDataView.")

privacy = struct(SOURCE["privacy"], "SettingsPrivacyDataView")
visible("Privacy & Data", privacy, r'DisclosureRow\("Listening history"',
        "Listening history is not visible under Privacy & Data.")
require("Privacy & Data", privacy, r"showHistory\s*=\s*true",
        "the history row cannot select its destination.")
require("Privacy & Data", privacy,
        r"navigationDestination\s*\(\s*isPresented\s*:\s*\$showHistory\s*\)"
        r"[\s\S]*?ListeningHistoryView\s*\(\s*session\s*:\s*session\s*\)",
        "showHistory does not open ListeningHistoryView.")

# Two-account pending-speech regression. Every consumer of the disk-backed
# queue asks the same ownership helper: display, count, delete, and flush. This
# is structural on purpose—the private BufferedLine cannot be rebuilt in a test
# without testing a duplicate type, and these are the exact four drift seams.
pending_section = body(
    privacy,
    r"\bif\s+session\s*\.\s*pendingCount\s*>\s*0\s*\{",
    "SettingsPrivacyDataView pending section",
)
require("Pending speech viewer", pending_section,
        r"showPendingSpeech\s*=\s*true",
        "the current account's unsent words have a delete count but no inspectable route.")
require("Pending speech viewer", privacy,
        r"navigationDestination\s*\(\s*isPresented\s*:\s*\$showPendingSpeech\s*\)"
        r"[\s\S]*?PendingSpeechView\s*\(\s*session\s*:\s*session\s*\)",
        "the pending-speech route does not open its scoped viewer.")
pending_view = struct(SOURCE["privacy"], "PendingSpeechView")
require("Pending speech viewer", pending_view,
        r"ForEach\s*\([^\n]*session\s*\.\s*pendingSpeechLines",
        "the viewer does not enumerate the session's account-scoped speech lines.")

session_source = SOURCE["session"]
unsent_property = body(
    session_source,
    r"\bprivate\s+var\s+unsent\s*:\s*\[BufferedLine\]\s*\{",
    "AnticipySession.unsent",
)
# The queue is BOUNDED before it is stored, so the rows that exist after a
# write are `kept`, not `newValue` — those differ by exactly the rows that
# just overflowed. Counting `newValue` would report speech the phone had
# already thrown away as still pending, which is the failure this trio is
# aimed at from the other side. The three requires below are deliberately
# tighter than the single one they replaced: it is not enough that the count
# goes through the ownership helper, it must go through it over THE SAME
# VALUE THAT WAS PERSISTED, and the overflow must reach the journal. Counting
# one array and storing another would satisfy any one of these alone.
require("Pending count ownership", unsent_property,
        r"pendingCount\s*=\s*pendingLinesOwnedByCurrentAccount\s*\(\s*in\s*:\s*kept\s*\)\s*\.\s*count",
        "queue writes count every account's rows instead of the signed-in account's rows.")
require("Pending count ownership", unsent_property,
        r"encode\s*\(\s*kept\s*\)",
        "the queue stores a different array than the one it counted.")
require("Pending queue is bounded", unsent_property,
        r"PendingSpeechRetention\s*\.\s*bounded\s*\(\s*newValue\s*\)",
        "the unsent queue is written without a bound; a long outage grows it without limit.")
require("Pending queue is bounded", unsent_property,
        r"if\s+dropped\s*>\s*0\s*\{[\s\S]*?ListenJournal\s*\.\s*shared\s*\.\s*record\s*\("
        r"\s*\.\s*speechDropped\s*\(\s*count\s*:\s*dropped\s*\)",
        "the queue discards heard speech without recording that it did.")
owned_lines = body(
    session_source,
    r"\bprivate\s+func\s+pendingLinesOwnedByCurrentAccount\s*\("
    r"[\s\S]*?in\s+queue\s*:\s*\[BufferedLine\][\s\S]*?\)\s*->\s*\[BufferedLine\]\s*\{",
    "AnticipySession.pendingLinesOwnedByCurrentAccount",
)
require("Pending queue ownership helper", owned_lines,
        r"guard\s+!accountID\s*\.\s*isEmpty\s+else\s*\{\s*return\s*\[\s*\]\s*\}",
        "signed-out state can expose unattributed queue rows.")
require("Pending queue ownership helper", owned_lines,
        r"queue\s*\.\s*filter\s*\{\s*\$0\s*\.\s*account\s*==\s*accountID\s*\}",
        "the helper does not select only rows stamped with the current account id.")
refresh_pending = body(
    session_source,
    r"\bprivate\s+func\s+refreshPendingCount\s*\(\s*\)\s*\{",
    "AnticipySession.refreshPendingCount",
)
require("Pending count ownership", refresh_pending,
        r"pendingCount\s*=\s*pendingLinesOwnedByCurrentAccount\s*\(\s*in\s*:\s*unsent\s*\)\s*\.\s*count",
        "account changes do not recompute the scoped count through the ownership helper.")
for function_name, declaration in (
    ("signIn", r"\bfunc\s+signIn\s*\([^)]*\)\s+async\s*->\s*String\?\s*\{"),
    ("resumeSignedInAccount", r"\bfunc\s+resumeSignedInAccount\s*\(\s*\)\s+async\s*\{"),
):
    account_entry = body(session_source, declaration, f"AnticipySession.{function_name}")
    require("Two-account pending count", account_entry,
            r"refreshPendingCount\s*\(\s*\)",
            f"{function_name} can show the previous account's pending count.")
pending_lines = body(
    session_source,
    r"\bvar\s+pendingSpeechLines\s*:\s*\[String\]\s*\{",
    "AnticipySession.pendingSpeechLines",
)
require("Pending viewer ownership", pending_lines,
        r"pendingLinesOwnedByCurrentAccount\s*\(\s*in\s*:\s*unsent\s*\)\s*\.\s*map\s*\(\s*\\\.text\s*\)",
        "the Settings viewer bypasses the account ownership helper.")
clear_pending = body(
    session_source,
    r"\bfunc\s+clearPendingLines\s*\(\s*\)\s*\{",
    "AnticipySession.clearPendingLines",
)
require("Pending delete ownership", clear_pending,
        r"guard\s+!accountID\s*\.\s*isEmpty\s+else\s*\{\s*return\s*\}",
        "signed-out deletion can clear another account's sealed queue.")
require("Pending delete ownership", clear_pending,
        r"clearPendingLinesOwned\s*\(\s*by\s*:\s*accountID\s*\)",
        "deleting this account's pending speech bypasses the owner-scoped erasure helper.")
clear_pending_owned = body(
    session_source,
    r"\bprivate\s+func\s+clearPendingLinesOwned\s*\(\s*by\s+ownerAccount\s*:\s*String\s*\)\s*\{",
    "AnticipySession.clearPendingLinesOwned",
)
require("Pending delete ownership", clear_pending_owned,
        r"unsent\s*=\s*unsent\s*\.\s*filter\s*\{\s*\$0\s*\.\s*account\s*!=\s*ownerAccount\s*\}",
        "the owner-scoped helper does not preserve every other account's rows.")
flush_unsent = body(
    session_source,
    r"\bprivate\s+func\s+flushUnsent\s*\(\s*\)\s+async\s*\{",
    "AnticipySession.flushUnsent",
)
foreign = body(
    flush_unsent,
    r"\bguard\s+line\s*\.\s*account\s*==\s*accountID\s+else\s*\{",
    "AnticipySession.flushUnsent foreign-account branch",
)
require("Pending flush ownership", foreign,
        r"retained\s*\.\s*append\s*\(\s*line\s*\)",
        "another account reconnecting drops this account's sealed row.")
require("Pending flush ownership", flush_unsent,
        r"unsent\s*=\s*retained\s*\+\s*unsent",
        "foreign and failed rows are collected but not restored to the persisted queue.")

history = struct(SOURCE["privacy"], "ListeningHistoryView")
for state in ("events", "page", "totalPages", "totalItems", "loading"):
    require("Listening History pagination", history,
            rf"@State\s+private\s+var\s+{state}\b", f"{state} state is missing.")
forbid("Listening History pagination", history, r"\bsession\s*\.\s*transcript\b",
       "history reads Home's small live window instead of the server archive.")
forbid("Listening History pagination", history, r"\.(?:prefix|suffix)\s*\(",
       "a local cap prevents complete server history.")
require("Listening History first page", history,
        r"\.task\s*\(\s*id\s*:\s*session\s*\.\s*accountID\s*\)"
        r"[\s\S]*?await\s+loadPage\s*\(\s*1\s*\)",
        "history is not keyed to the authenticated account and reset to page 1.")
require("Listening History next page", history,
        r"if\s+page\s*<\s*totalPages\s*\{[\s\S]*?await\s+loadPage\s*\(\s*page\s*\+\s*1\s*\)",
        "Load older is not bounded by totalPages and advancing one page.")
visible("Listening History next page", history, r'"Load older history"',
        "the visible load-more control is missing.")

# The concrete offset mutation that makes "complete snapshot" untrue even
# with a created-time upper bound: deleting a page-one row shifts `b` into the
# already-consumed offset, so page two skips it.
initial_rows = ["d", "c", "b", "a"]
page_size = 2
first_page = initial_rows[:page_size]
after_deletion = [row for row in initial_rows if row != "d"]
second_page = after_deletion[page_size:page_size * 2]
if first_page != ["d", "c"] or second_page != ["a"] \
        or "b" in first_page + second_page:
    FAILURES.append(
        "Listening History mutation fixture no longer demonstrates an offset-page skip."
    )
visible("Listening History pagination truth", history,
        r'History can change while older pages load',
        "the UI does not disclose mutation-between-pages shifting.")
visible("Listening History pagination truth", history,
        r'not a frozen snapshot',
        "the loaded-pages footer still implies snapshot completeness.")
for claim in (r'Complete history snapshot', r'This is every transcript page'):
    if re.search(claim, swift_without_comments(history)):
        FAILURES.append(
            f"Listening History pagination truth: mutable offset pages still claim `{claim}`."
        )

load_page = body(history,
                 r"\bprivate\s+func\s+loadPage\s*\(\s*_\s+requestedPage\s*:\s*Int\s*\)\s+async\s*\{",
                 "ListeningHistoryView.loadPage")
require("Listening History request", load_page,
        r"session\s*\.\s*backend\s*\.\s*fetchTranscriptPage\s*\(\s*page\s*:\s*requestedPage\s*,"
        r"\s*createdAtOrBefore\s*:\s*\w*[Ss]napshot\w*\s*\)",
        "loadPage does not carry the page-one created upper bound.")
require("Listening History accumulation", load_page,
        r"Dictionary\s*\(\s*uniqueKeysWithValues\s*:\s*events\s*\.\s*map",
        "new pages replace prior pages instead of merging by event id.")
require("Listening History accumulation", load_page,
        r"for\s+event\s+in\s+result\s*\.\s*items\s*\{[\s\S]*?"
        r"byID\s*\[\s*event\s*\.\s*id\s*\]\s*=\s*event",
        "returned items are not accumulated by stable event id.")
for field in ("page", "totalPages", "totalItems"):
    require("Listening History server boundary", load_page,
            rf"\b{field}\s*=\s*result\s*\.\s*{field}\b",
            f"the UI guesses {field} instead of keeping the server answer.")
require("Listening History snapshot", history,
        r"@State\s+private\s+var\s+\w*[Ss]napshot\w*\s*:\s*String\?",
        "there is no persisted boundary reducing newer-row churn on later pages.")
require("Listening History snapshot", history,
        r"\.task\s*\(\s*id\s*:\s*session\s*\.\s*accountID\s*\)"
        r"[\s\S]*?\w*[Ss]napshot\w*\s*=\s*nil",
        "changing accounts does not clear the prior account's page boundary.")
require("Listening History snapshot", load_page,
    r"if\s+requestedPage\s*==\s*1\s*&&\s*\w*[Ss]napshot\w*\s*==\s*nil\s*\{"
        r"[\s\S]*?\w*[Ss]napshot\w*\s*="
        r"[\s\S]*?result\s*\.\s*items\s*\.\s*first\?\s*\.\s*created",
        "page 1 does not retain its created-time upper bound for later pages.")

backend = SOURCE["backend"]
require("Transcript archive endpoint", backend,
        r"\bstruct\s+BrainEventPage\b[\s\S]*?\blet\s+totalPages\s*:\s*Int\b"
        r"[\s\S]*?\blet\s+items\s*:\s*\[BrainEvent\]",
        "the page type does not carry both totalPages and items.")
fetch_transcript = body(
    backend,
    r"\bfunc\s+fetchTranscriptPage\s*\(\s*page\s*:\s*Int\s*,\s*perPage\s*:\s*Int\s*=\s*\d+\s*,"
    r"\s*createdAtOrBefore\s+snapshot\s*:\s*String\?\s*=\s*nil\s*\)"
    r"\s+async\s+throws\s*->\s*BrainEventPage\s*\{",
    "AnticipyBackend.fetchTranscriptPage",
)
require("Transcript archive endpoint", fetch_transcript,
        r"fetchEventPage\s*\(\s*page\s*:\s*page\s*,\s*perPage\s*:\s*perPage\s*,"
        r"\s*matching\s*:\s*clauses\s*\.\s*joined",
        "the wrapper does not preserve page/perPage and the upper-bound filter.")
visible("Transcript archive endpoint", fetch_transcript,
        r'"kind=\\"transcript\\""',
        "the archive request is not transcript-only.")
require("Transcript archive endpoint", fetch_transcript,
        r"if\s+let\s+snapshot\s*,\s*!snapshot\s*\.\s*isEmpty\s*\{"
        r"[\s\S]*?clauses\s*\.\s*append",
        "the optional snapshot is accepted but never added to the server filter.")


# Developer speech: a seven-tap hidden entry asks device-owner authentication;
# it is the only place that can persist developerMode=true, and the only route
# to the private raw stream starts inside Advanced's developerMode block.
about = struct(SOURCE["home"], "SettingsAboutView")
require("Hidden developer entry", about,
        r"@AppStorage\s*\(\s*AppPreferences\s*\.\s*developerModeKey\s*\)"
        r"\s+private\s+var\s+developerMode\s*=\s*false",
        "About does not default developer mode to locked.")
tap = body(about, r"\bprivate\s+func\s+registerBuildTap\s*\(\s*\)\s*\{",
           "SettingsAboutView.registerBuildTap")
require("Hidden developer entry", tap,
        r"if\s+buildTaps\s*>=\s*7\s*\{[\s\S]*?authenticateOwner\s*\(\s*\)",
        "the build gesture does not require seven taps before authentication.")
auth = body(about, r"\bprivate\s+func\s+authenticateOwner\s*\(\s*\)\s*\{",
            "SettingsAboutView.authenticateOwner")
for pattern, reason in (
    (r"canEvaluatePolicy\s*\(\s*\.deviceOwnerAuthentication", "device-owner authentication is not available-checked"),
    (r"evaluatePolicy\s*\(\s*\.deviceOwnerAuthentication", "the owner challenge is not performed"),
    (r"if\s+success\s*\{[\s\S]*?developerMode\s*=\s*true", "unlock is not confined to authentication success"),
):
    require("Authenticated developer entry", auth, pattern, reason + ".")

view_sources = {path: path.read_text() for path in VIEWS.glob("*.swift")}
true_sites = [path for path, text in view_sources.items()
              for _ in re.finditer(r"\bdeveloperMode\s*=\s*true\b", swift_code(text))]
if true_sites != [PATHS["home"]]:
    FAILURES.append(
        "Authenticated developer entry: developerMode may become true exactly once, in "
        "SettingsAboutView's authenticated callback; found "
        + (", ".join(path.name for path in true_sites) or "none") + "."
    )

advanced = struct(SOURCE["advanced"], "SettingsAdvancedView")
dev_block = body(advanced, r"\bif\s+developerMode\s*\{",
                 "SettingsAdvancedView developerMode block")
visible("Developer route gate", dev_block, r'DisclosureRow\("Developer diagnostics"',
        "the diagnostics disclosure is outside the developer-only block.")
require("Developer route gate", dev_block, r"showDeveloperDiagnostics\s*=\s*true",
        "the gated row cannot select diagnostics.")
require("Developer route gate", advanced,
        r"navigationDestination\s*\(\s*isPresented\s*:\s*\$showDeveloperDiagnostics\s*\)"
        r"[\s\S]*?DeveloperDiagnosticsView\s*\(\s*session\s*:\s*session\s*\)",
        "the gated state does not open DeveloperDiagnosticsView.")
constructors = [path for path, text in view_sources.items()
                for _ in re.finditer(r"\bDeveloperDiagnosticsView\s*\(\s*session\s*:", swift_code(text))]
if constructors != [PATHS["advanced"]]:
    FAILURES.append(
        "Developer route gate: DeveloperDiagnosticsView must be constructed once from "
        "Advanced only; found " + (", ".join(path.name for path in constructors) or "none") + "."
    )

diagnostics = struct(SOURCE["developer"], "DeveloperDiagnosticsView")
visible("Developer speech route", diagnostics, r'NavRow\("Developer speech stream"',
        "diagnostics has no deliberate speech-stream row.")
require("Developer speech route", diagnostics,
        r"case\s+\.speechStream\s*:\s*DeveloperSpeechStreamView\s*\(\s*session\s*:\s*session\s*\)",
        "speechStream does not open the raw speech view.")
if not re.search(r"\bprivate\s+struct\s+DeveloperSpeechStreamView\b", swift_code(SOURCE["developer"])):
    FAILURES.append("Developer speech route: DeveloperSpeechStreamView is not private.")
speech = struct(SOURCE["developer"], "DeveloperSpeechStreamView")
for pattern, name in (
    (r"\bsession\s*\.\s*listener\s*\.\s*partial\b", "live partial"),
    (r"\bsession\s*\.\s*sessionLines\b", "finalized launch lines"),
    (r"\bsession\s*\.\s*transcript\b", "server transcript metadata"),
):
    require("Developer speech stream", speech, pattern,
            f"the {name} is no longer inspectable after authenticated unlock.")
require("Developer preference", SOURCE["preferences"],
        r"\bstatic\s+let\s+developerModeKey\s*=",
        "there is no single persisted developer-mode key.")


# Done deck: exactly one card, selected by job id. Poll changes repair only a
# missing selection. Swipe, explicit buttons, counter, and adjustable action
# all drive the same move(by:) function.
done = struct(SOURCE["content"], "DoneDeck")
done_view = body(done, r"\bvar\s+body\s*:\s*some\s+View\s*\{", "DoneDeck.body")
if count(done_view, r"\bDoneCard\s*\(") != 1:
    FAILURES.append("Done deck: body must construct exactly one DoneCard.")
for pattern, reason in (
    (r"\bForEach\b", "loops over every result instead of showing one"),
):
    forbid("Done deck", done_view, pattern, reason + ".")
require("Done deck identity", done, r"@State\s+private\s+var\s+selectedID\s*:\s*String\?",
        "selection is not stored by optional job id.")
require("Done deck identity", done,
        r"jobs\s*\.\s*firstIndex\s*\(\s*where\s*:\s*\{\s*\$0\s*\.\s*id\s*==\s*selectedID\s*\}\s*\)",
        "the current index is not resolved from the selected id.")
require("Done deck identity", done_view, r"\.id\s*\(\s*job\s*\.\s*id\s*\)",
        "the visible card does not carry its job id.")
require("Done deck polling", done_view,
        r"\.onChange\s*\(\s*of\s*:\s*jobs\s*\.\s*map\s*\(\s*\\\.id\s*\)\s*\)"
        r"\s*\{[\s\S]*?repairSelection\s*\(\s*\)",
        "poll changes do not repair selection against stable ids.")
repair = body(done, r"\bprivate\s+func\s+repairSelection\s*\(\s*\)\s*\{",
              "DoneDeck.repairSelection")
require("Done deck polling", repair,
        r"selectedID\s*==\s*nil\s*\|\|\s*!jobs\s*\.\s*contains\s*\(\s*where\s*:\s*\{"
        r"\s*\$0\s*\.\s*id\s*==\s*selectedID\s*\}\s*\)",
        "a still-present selection is replaced, or a missing one is not repaired.")
require("Done deck polling", repair,
        r"selectedID\s*=\s*jobs\s*\[\s*0\s*\]\s*\.\s*id",
        "a missing selection does not fall back to the first current id.")
move = body(done, r"\bprivate\s+func\s+move\s*\(\s*by\s+amount\s*:\s*Int\s*\)\s*\{",
            "DoneDeck.move")
require("Done deck movement", move,
        r"selectedID\s*=\s*jobs\s*\[\s*destination\s*\]\s*\.\s*id",
        "movement stores an index instead of the destination id.")
for pattern, reason in (
    (r"DragGesture\s*\(", "no swipe gesture"),
    (r"translation\s*\.\s*width", "swipe ignores horizontal distance"),
    (r"translation\s*\.\s*height", "swipe cannot reject vertical scrolling"),
    (r"move\s*\(\s*by\s*:\s*value\s*\.\s*translation\s*\.\s*width\s*<\s*0\s*\?\s*1\s*:\s*-1\s*\)", "swipe direction does not move results"),
    (r"accessibilityAdjustableAction", "VoiceOver cannot adjust the deck"),
):
    require("Done deck interaction", done_view, pattern, reason + ".")
require("Done deck accessibility container", done_view,
        r"\.accessibilityElement\s*\(\s*children\s*:\s*\.contain\s*\)",
        "the adjustable action is attached to an implicit, potentially unfocusable container.")
visible("Done deck accessibility container", done_view,
        r'\.accessibilityLabel\("Done results"\)',
        "the adjustable deck has no explicit VoiceOver label.")
visible("Done deck accessibility container", done_view,
        re.escape('.accessibilityValue("Result \\(index + 1) of \\(jobs.count)")'),
        "the adjustable deck has no explicit Result X of N accessibility value.")
visible(
    "Done deck accessibility container",
    done_view,
    r"\.onChange\s*\(\s*of\s*:\s*jobs\s*\.\s*map\s*\(\s*\\\.id\s*\)\s*\)"
    r"[\s\S]*?\.accessibilityElement\s*\(\s*children\s*:\s*\.contain\s*\)"
    r"[\s\S]*?" + re.escape('.accessibilityLabel("Done results")')
    + r"[\s\S]*?" + re.escape('.accessibilityValue("Result \\(index + 1) of \\(jobs.count)")')
    + r"[\s\S]*?\.accessibilityAdjustableAction",
    "label, value, and adjustable action are not chained onto the outer polling-stable deck.",
)
for label in ("Previous", "Next"):
    visible("Done deck interaction", done_view, rf'Button\("{label}"\)',
            f"the {label} button is missing.")
visible("Done deck counter", done_view,
        re.escape('Text("\\(index + 1) of \\(jobs.count)")'),
        "the visible X of N counter is missing.")
visible("Done deck counter", done_view,
        re.escape('accessibilityLabel("Result \\(index + 1) of \\(jobs.count)")'),
        "the counter does not announce Result X of N.")
require("Home Done route", home, r"DoneDeck\s*\(\s*jobs\s*:\s*finishedShown\s*\)",
        "Home does not send terminal work through DoneDeck.")


# Settings migration: the new index, not the unreachable legacy page, must
# retain interview/reteach, voice enrollment, onboarding replay, unsent delete,
# local forget, and server delete.
visible("Settings personalization", settings, r'NavRow\("Personalization"',
        "Personalization is absent from the index.")
require("Settings personalization", settings,
        r"case\s+\.personalization\s*:\s*SettingsPersonalizationView\s*\(\s*session\s*:\s*session\s*\)",
        "the route does not open SettingsPersonalizationView.")

# Speech privacy copy follows the recognizer path rather than promising every
# iPhone has local recognition. On unsupported devices SFSpeech may use
# Apple's service; both permission prompts and About must disclose that path.
about = struct(SOURCE["home"], "SettingsAboutView")
require("Speech privacy truth", about,
        r"SFSpeechRecognizer\s*\([\s\S]*?supportsOnDeviceRecognition",
        "About does not inspect whether this iPhone can recognize on-device.")
visible("Speech privacy truth", about, r"Apple's speech service",
        "About hides the Apple speech-service fallback on unsupported iPhones.")
for label, disclosure in (("project.yml", PROJECT_YML), ("Info.plist", INFO_PLIST)):
    if "Apple's speech service" not in disclosure or "on-device" not in disclosure:
        FAILURES.append(
            f"Speech privacy truth: {label} does not disclose both the on-device "
            "path and Apple's speech-service fallback."
        )

personalization = struct(SOURCE["personalization"], "SettingsPersonalizationView")
for pattern, reason in (
    (r"InterviewProgress\s*\(\s*\)\s*\.\s*reopenAll\s*\(\s*\)", "completed answers cannot be reopened"),
    (r"navigationDestination\s*\(\s*isPresented\s*:\s*\$showInterview\s*\)"
     r"[\s\S]*?InterviewView\s*\(\s*\)", "the interview destination is not wired"),
    (r"if\s+session\s*\.\s*speakerTagger\s*\.\s*available\s*\{", "voice enrollment ignores capability availability"),
    (r"navigationDestination\s*\(\s*isPresented\s*:\s*\$showVoiceEnrollment\s*\)"
     r"[\s\S]*?VoiceEnrollView\s*\(\s*\)", "voice enrollment is not wired"),
    (r"hasOnboarded\s*=\s*false", "welcome replay does not reset onboarding"),
    (r"hasSeenIntro\s*=\s*false", "welcome replay does not reset the intro"),
):
    require("Personalization capability", personalization, pattern, reason + ".")
visible("Personalization capability", personalization, r'"Replay the welcome tour"',
        "the replay control is missing.")
visible("Personalization capability", personalization, r'"Learn my voice"',
        "the voice-enrollment control is missing.")

require("Pending deletion", privacy,
        r"if\s+session\s*\.\s*pendingCount\s*>\s*0\s*\{[\s\S]*?confirmation\s*=\s*\.pending",
        "unsent deletion is unreachable when pending lines exist.")
require("Pending deletion", privacy,
        r"case\s+\.pending\s*:[\s\S]*?session\s*\.\s*clearPendingLines\s*\(\s*\)",
        "confirming deletion does not clear pending lines.")
visible("Local forget", privacy, r'"Forget me on this iPhone"',
        "the local-forget control is missing.")
require("Local forget", privacy,
        r"case\s+\.local\s*:[\s\S]*?action\s*:\s*forgetLocalUser",
        "the local confirmation does not invoke forgetLocalUser.")
forget = body(privacy, r"\bprivate\s+func\s+forgetLocalUser\s*\(\s*\)\s*\{",
              "SettingsPrivacyDataView.forgetLocalUser")
require("Local forget boundary", forget,
        r"await\s+session\s*\.\s*forgetThisPhone\s*\(\s*\)",
        "the view does not await the session-owned forget and verified browser disconnect.")
after_forget = forget.split("await session.forgetThisPhone()", 1)[-1]
if re.search(r"\blocalNote\s*=", swift_code(after_forget)):
    FAILURES.append(
        "Local forget navigation: the browser verdict is still written into "
        "Settings @State after sign-out removes that view."
    )

forget_phone = body(
    session_source,
    r"\bfunc\s+forgetThisPhone\s*\(\s*\)\s+async\s*->\s*Bool\s*\{",
    "AnticipySession.forgetThisPhone",
)
for pattern, reason in (
    (r"stopListening\s*\(\s*\)", "listening remains active"),
    (r"clearAllPendingLinesOnDevice\s*\(\s*\)",
     "sealed prior-account or unstamped legacy speech survives"),
    (r"let\s+browserDisconnected\s*=\s*await\s+requestedBackend\s*\.\s*unpairAgent"
     r"\s*\(\s*owner\s*:\s*oldIdentity\s*\)", "browser unpair is fire-and-forget"),
    (r"AccountWriteLeasePolicy\s*\.\s*begin", "the forget has no authenticated account lease"),
    (r"guard\s+stillCurrent\s*\|\|\s*expiredSameAccount\s+else\s*\{\s*return\s+false\s*\}",
     "a delayed forget can mutate a replacement account"),
    (r"signOut\s*\(\s*\)", "credentials and account memory are not cleared"),
    (r"ownerID\s*=\s*UUID\s*\(\s*\)\s*\.\s*uuidString", "device identity is not rotated"),
    (r"return\s+browserDisconnected", "the UI cannot report whether Chrome disconnected"),
):
    require("Session local-forget boundary", forget_phone, pattern, reason + ".")
device_queue_clear = body(
    session_source,
    r"\bprivate\s+func\s+clearAllPendingLinesOnDevice\s*\(\s*\)\s*\{",
    "AnticipySession.clearAllPendingLinesOnDevice",
)
require("Device-wide pending speech erasure", device_queue_clear,
        r"unsent\s*=\s*PendingSpeechRetention\s*\.\s*afterDeviceForget\s*\(\s*unsent\s*\)",
        "device Forget does not replace the entire queue; nil/prior/current rows can survive.")
require(
    "Local forget navigation",
    forget_phone,
    r"UserDefaults\s*\.\s*standard\s*\.\s*set\s*\(\s*notice\s*,\s*forKey\s*:\s*"
    r"AppPreferences\s*\.\s*postSignOutNoticeKey\s*\)[\s\S]*?signOut\s*\(",
    "the post-signout outcome is not persisted before navigation leaves Settings.",
)
auth = struct(SOURCE["auth"], "AuthView")
require(
    "Local forget navigation",
    auth,
    r"@AppStorage\s*\(\s*AppPreferences\s*\.\s*postSignOutNoticeKey\s*\)",
    "Auth does not read the persisted forget outcome.",
)
visible("Local forget navigation", auth, r'"Got it"',
        "the post-signout outcome has no acknowledgement control.")

sign_out = body(session_source, r"\bfunc\s+signOut\s*\(\s*\)\s*\{",
                "AnticipySession.signOut")
for pattern, reason in (
    (r"authToken\s*=\s*", "the credential survives"),
    (r"accountID\s*=\s*", "the account id survives"),
    (r"listener\s*\.\s*stop\s*\(\s*\)", "the microphone survives"),
    (r"clearSignedInSurface\s*\(\s*\)", "renderable account state survives"),
    (r"purgeLocalPersonState\s*\(\s*\)", "device-only person memory survives"),
):
    require("Sign-out boundary", sign_out, pattern, reason + ".")

clear_surface = body(
    session_source,
    r"\bprivate\s+func\s+clearSignedInSurface\s*\(\s*\)\s*\{",
    "AnticipySession.clearSignedInSurface",
)
for pattern, reason in (
    (r"OwnerMirror\s*\.\s*clear\s*\(\s*\)", "profile mirrors survive"),
    (r"transcript\s*=\s*\[\s*\]", "server transcript memory survives"),
    (r"sessionLines\s*=\s*\[\s*\]", "launch speech memory survives"),
    (r"jobs\s*=\s*\[\s*\]", "the prior account's jobs survive"),
    (r"removeObject\s*\(\s*forKey\s*:\s*AppPreferences\s*\.\s*developerModeKey\s*\)",
     "the next account inherits authenticated developer mode"),
    (r"refreshPendingCount\s*\(\s*\)", "pending count still describes the account that left"),
):
    require("Signed-in surface clearing", clear_surface, pattern, reason + ".")

purge_person = body(
    session_source,
    r"\bprivate\s+func\s+purgeLocalPersonState\s*\(\s*\)\s*\{",
    "AnticipySession.purgeLocalPersonState",
)
for pattern, reason in (
    (r"speakerTagger\s*\.\s*roster\s*\.\s*forgetEverything\s*\(\s*\)", "voice enrollment survives"),
    (r"InterviewProgress\s*\(\s*\)\s*\.\s*reopenAll\s*\(\s*\)", "interview progress survives"),
    (r"ContextGrants\s*\(\s*\)\s*\.\s*resetAll\s*\(\s*\)", "context grants survive"),
):
    require("Local person-memory clearing", purge_person, pattern, reason + ".")

unpair = body(backend,
              r"\bfunc\s+unpairAgent\s*\(\s*owner\s*:\s*String\s*\)\s+async\s*->\s*Bool\s*\{",
              "AnticipyBackend.unpairAgent")
for pattern, reason in (
    (r"let\s+savedData\s*=\s*try\?\s+await\s+send\s*\(\s*patch\s*\)",
     "the unpair patch response is not awaited and retained"),
    (r"let\s+saved\s*=\s*try\?\s+JSONSerialization\s*\.\s*jsonObject\s*\(\s*with\s*:\s*savedData\s*\)",
     "the backend's saved record response is not decoded"),
    (r"saved\s*\[\s*[^]]+\s*\]\s+as\?\s+Bool\s*\)\s*==\s*false", "the paired=false result is not verified"),
    (r"var\s+page\s*=\s*1[\s\S]*?var\s+totalPages\s*=\s*1",
     "the paged snapshot cursor is missing"),
    (r"AgentUnpairPolicy\s*\.\s*pages\s*\(\s*totalPages\s*:\s*totalPages\s*\)",
     "the server pagination boundary is ignored"),
    (r"remainingRows\s*:\s*remaining",
     "zero remaining affiliated browser rows is not verified"),
):
    require("Verified browser unpair", unpair, pattern, reason + ".")
visible("Verified browser unpair", unpair,
        r'"filter=\\\(filter\)&perPage=20&page=\\\(page\)"',
        "the paged request does not carry its page cursor.")
visible("Verified browser unpair", unpair,
        r'"filter=\\\(filter\)&perPage=1&page=1"',
        "the final verification does not query the affiliated set again.")
visible("Verified browser unpair", unpair,
        r'root\s*\[\s*"totalItems"\s*\]\s+as\?\s+Int',
        "the final verification does not read the server's remaining-row count.")

visible("Server deletion", privacy, r'DestructiveRow\("Delete my account and server data"',
        "the server deletion control is missing.")
require("Server deletion", privacy,
        r"case\s+\.server\s*:[\s\S]*?action\s*:\s*deleteServerData",
        "server confirmation does not invoke deleteServerData.")
delete = body(privacy, r"\bprivate\s+func\s+deleteServerData\s*\(\s*\)\s*\{",
              "SettingsPrivacyDataView.deleteServerData")
require("Server deletion boundary", delete,
        r"await\s+session\s*\.\s*deleteEverythingOnServer\s*\(\s*\)",
        "server deletion does not call the existing operation.")
forbid("Server deletion boundary", delete,
       r"session\s*\.\s*signOut\s*\(\s*\)|Task\s*\.\s*sleep",
       "the view schedules an unscoped delayed sign-out that can eject a replacement account.")
delete_session = body(
    session_source,
    r"\bfunc\s+deleteEverythingOnServer\s*\(\s*\)\s+async\s*->\s*"
    r"\(\s*ok\s*:\s*Bool\s*,\s*message\s*:\s*String\s*\)\s*\{",
    "AnticipySession.deleteEverythingOnServer",
)
require("Server deletion evidence", delete_session,
        r"AccountDeletionPolicy\s*\.\s*outcome\s*\(\s*status\s*:\s*status\s*,\s*body\s*:\s*body\s*\)",
        "the response body is discarded instead of surfacing message/deleted/failed evidence.")
require("Server deletion local erasure", delete_session,
        r"if\s+outcome\s*\.\s*ok\s*\{[\s\S]*?"
        r"clearAllPendingLinesOnDevice\s*\(\s*\)[\s\S]*?\}",
        "successful account deletion leaves device-wide queued speech behind before sign-out.")
require("Server deletion account lease", delete_session,
        r"AccountWriteLeasePolicy\s*\.\s*begin[\s\S]*?"
        r"requestedBackend\s*\.\s*deleteAccount\s*\(\s*\)[\s\S]*?"
        r"guard\s+stillCurrent\s*\|\|\s*expiredSameAccount[\s\S]*?"
        r"signOut\s*\(\s*\)",
        "the session does not own an account-leased post-delete sign-out.")
require("Server deletion uncertainty", delete_session,
        r"catch\s*\{[\s\S]*?AccountDeletionPolicy\s*\.\s*unverified",
        "a lost response does not use the explicit re-authenticate/recheck outcome.")
visible("Server deletion uncertainty", SOURCE["session"],
        r'couldn\'t verify how far deletion got[\s\S]*Sign in again[\s\S]*check what\'s left',
        "transport uncertainty does not tell the owner to re-authenticate and recheck.")
forbid("Server deletion honesty", delete_session,
       r"Nothing was (?:half-)?deleted",
       "incremental deletion is falsely described as having deleted nothing.")
visible("Server deletion honesty", SOURCE["session"],
        r'case\s+memoryPurge\s*=\s*"memory_purge"',
        "the app does not decode the worker-owned private-memory purge state.")
visible("Server deletion honesty", SOURCE["session"],
        r'final private-memory purge is scheduled',
        "a scheduled private-memory purge is not surfaced to the owner.")
forbid("Server deletion honesty", SOURCE["session"],
       r'Done\. It\'s gone',
       "the app calls an asynchronously scheduled memory purge already gone.")

# Local notifications are a real second reachability lane while the app keeps
# polling (including background listening). No-phone copy must describe the
# missing SMS backstop without erasing that lane or promising it when iOS has
# not granted notifications.
unreachable_notice = body(
    SOURCE["content"],
    r"\bprivate\s+var\s+unreachableNotice\s*:\s*some\s+View\s*\{",
    "ContentView.unreachableNotice",
)
visible("No-phone reachability truth", unreachable_notice,
        r'no SMS backstop', "the notice does not identify what is actually missing.")
visible("No-phone reachability truth", unreachable_notice,
        r'Local alerts can reach you[\s\S]*if notifications are allowed',
        "the notice hides or overpromises the local-notification lane.")
visible("No-phone reachability truth", unreachable_notice,
        r'Otherwise, open[\s\S]*the app',
        "the notice does not explain the fallback when local alerts cannot run.")
if "final class Notifier" in SOURCE["notifier"]:
    forbid("No-phone reachability truth", unreachable_notice,
           r'text is the only way',
           "copy claims SMS is the only reachability lane while Notifier ships.")


if FAILURES:
    print("CONSUMER EXPERIENCE CONTRACT IS BROKEN.")
    print()
    for failure in FAILURES:
        print(f"  - {failure}")
    raise SystemExit(1)

print(
    "consumer Home hides raw speech; Privacy & Data owns paged history; "
    "device-owner authentication gates developer speech; Done is one stable, "
    "swipeable, accessible card; and Settings retains personalization, voice, "
    "onboarding, pending/local forget, and server deletion"
)
