#!/usr/bin/env python3
"""ARE THE JOURNAL'S PAYLOADS CLOSED? — the leg that replaced the scan.

WHY THIS EXISTS, and why it is not the thing it replaced.

`run_journal_tests.sh` used to prove the journal free of speech by SCANNING:
it derived the free-form `String` channels `ListenEvent` declared, found every
expression that flowed into one, and judged each against an allowlist. Five
hardening passes did that. Each closed its findings and leaked at a new layer —
two, then four, then two, then EIGHT (`.superpowers/sdd/privacy-gate-fifth.md`).
Thirteen attacks aimed at a RULE bounced. What kept giving way was the finder,
the derivation and the allowlist: whatever decided WHAT THE RULES RAN ON.

The one thing that held under every attack was a TYPE. So `ListenEvent` no
longer declares a `String` payload at all, and this file checks that property
instead of policing expressions. A value that cannot be constructed does not
need to be detected.

THE QUESTION IT ASKS: is every payload type of every `ListenEvent` case CLOSED?

    CLOSED  a scalar (Int, Bool, Double, ...)
    CLOSED  an enum declared in these files whose cases carry no associated
            values — its words are case names and raw values written here
    CLOSED  an enum whose every associated value is itself closed
    CLOSED  a struct whose every stored property is itself closed
    CLOSED  T?, T!, [T] where T is closed
    OPEN    everything else — String, Substring, Swift.String, a type these
            files do not declare, a payload this parser cannot read

THE POLARITY IS THE POINT. `channels.awk`, which this replaces, tested
`== "String"` literally and SKIPPED what it did not recognise: `String?`,
`String!`, `Swift.String`, `Substring`, `_ text: String`, a struct payload, an
enum-with-payload, and a case declared across two lines all passed by being
unreadable. Two of those are plain Strings. That is the same inversion the
same commit had just fixed one layer down in `namelines.awk` — FAILING TO
UNDERSTAND A LINE WAS A PASS — reintroduced one layer up.

So here, anything unreadable is OPEN, and OPEN is red.

AND IT MUST STILL GO RED WHEN IT CANNOT SEE. The version of this leg that
shipped before the types landed said, when its derivation came back empty:

    This gate can no longer find a single String payload on ListenEvent.
    It was about to allowlist nothing and call the journal clean.

That refusal is the most valuable line in the suite and it is kept, aimed at
the new question: no `ListenEvent`, no cases, no payloads, or a case this
parser cannot read to its end are each a red leg with a sentence attached,
never an empty search reported as a clean one.
"""

import re
import sys

SCALARS = {
    "Int", "Bool", "Double", "Float", "UInt",
    "Int8", "Int16", "Int32", "Int64",
    "UInt8", "UInt16", "UInt32", "UInt64",
}

# Members of `ListenJournal` that may be visible outside it, each because
# something outside it genuinely needs them. ANYTHING ELSE IS A NEW WAY IN.
#
# This list is the answer to leak C2/C3 of the fifth pass: a convenience
# `func log(_ text: String)` appending straight to the ring and the file built
# no `ListenEvent`, matched no anchor the finder knew, and put the owner's
# transcript on disk at exit 0; and a stored `var lastTail`, set from a call
# site nothing looked at, was rendered into a line by `describe`. Neither is a
# journal write in any sense the old scan could recognise. Both are a member of
# this class that is not on this list.
JOURNAL_SURFACE = {
    "shared":          "the singleton every call site records through",
    "init":            "the tests build their own journals with a limit and a file",
    "record":          "THE ONLY WAY IN. Everything else here is a way OUT.",
    "entries":         "the diagnostics screen reads the ring",
    "persistedLines":  "the diagnostics screen reads the file",
    "persistedEvents": "ListenTally folds the day off disk",
    "parse":           "one line back to an event; the reader half of describe",
    "clear":           "the person emptying their journal from Settings",
    "fileURL":         "Settings hands this file to a ShareLink",
}

# Every property that turns a typed payload into words, and the type it hangs
# off. `describe` is not alone any more: it delegates to these, and a renderer
# nobody checks is a renderer that can say anything.
RENDERERS = [
    ("ListenJournal", "describe"),
    ("ListenEvent.PostDetail", "text"),
    ("ListenEvent.PostFailure", "text"),
    ("ListenSessionFacts", "sentence"),
]


def strip_comment(line):
    """The line without its `//` tail, respecting string literals."""
    out, i, in_str = [], 0, False
    while i < len(line):
        c = line[i]
        if in_str:
            if c == "\\":
                out.append(line[i:i + 2])
                i += 2
                continue
            if c == '"':
                in_str = False
            out.append(c)
            i += 1
            continue
        if c == '"':
            in_str = True
            out.append(c)
            i += 1
            continue
        if c == "/" and line[i + 1:i + 2] == "/":
            break
        out.append(c)
        i += 1
    return "".join(out)


def depth_of(text):
    """Net paren/bracket depth of a fragment, ignoring string literals."""
    d, in_str, i = 0, False, 0
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "([":
            d += 1
        elif c in ")]":
            d -= 1
        i += 1
    return d


def split_top(text, sep=","):
    """Split on `sep` at paren depth 0, outside string literals."""
    parts, cur, d, in_str, i = [], [], 0, False, 0
    while i < len(text):
        c = text[i]
        if in_str:
            if c == "\\":
                cur.append(text[i:i + 2])
                i += 2
                continue
            if c == '"':
                in_str = False
            cur.append(c)
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c in "([<":
            d += 1
        elif c in ")]>":
            d -= 1
        elif c == sep and d == 0:
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


DECL = re.compile(
    r"^\s*(?:public\s+|internal\s+|private\s+|fileprivate\s+|final\s+|"
    r"indirect\s+)*(enum|struct|class|extension)\s+([A-Za-z_][\w.]*)"
)
MEMBER = re.compile(
    r"^\s*(?:@\w+\s+)*(?:public\s+|internal\s+|private\s+|fileprivate\s+|"
    r"static\s+|final\s+|lazy\s+|override\s+|convenience\s+)*"
    r"(func|var|let|init|subscript|case)\b\s*([A-Za-z_]\w*)?"
)


class Types(object):
    """What the two files declare, and where each declaration's body lives."""

    def __init__(self):
        self.kind = {}        # qualified name -> enum|struct|class|extension
        self.cases = {}       # qualified enum name -> [(case name, [arg text])]
        self.stored = {}      # qualified name -> [(prop name, type text)]
        self.members = {}     # qualified name -> [(name, is_private, is_stored)]
        self.bodies = {}      # (qualified name, member) -> [lines]
        self.unreadable = []  # sentences describing what could not be parsed


def scan(paths):
    t = Types()
    for path in paths:
        with open(path) as fh:
            raw = fh.readlines()
        stack = []           # [(qualified name, depth at which its body opened)]
        depth = 0
        pending = None       # a `case`/`let` still gathering continuation lines
        for lineno, original in enumerate(raw, 1):
            line = strip_comment(original.rstrip("\n"))
            if not line.strip():
                depth += depth_of(line)
                continue

            here = ".".join(n for n, _ in stack)

            if pending is not None:
                pending["text"] += " " + line.strip()
                if depth_of(pending["text"]) == 0:
                    record_case(t, pending["owner"], pending["text"],
                                path, pending["line"])
                    pending = None
                depth += line.count("{") - line.count("}")
                continue

            m = DECL.match(line)
            if m:
                kind, name = m.group(1), m.group(2)
                if kind == "extension":
                    qualified = resolve_name(t, name, stack) or name
                else:
                    qualified = (here + "." + name) if here else name
                    t.kind.setdefault(qualified, kind)
                    if kind == "enum":
                        t.cases.setdefault(qualified, [])
                    t.stored.setdefault(qualified, [])
                    t.members.setdefault(qualified, [])
                t.members.setdefault(qualified, [])
                t.stored.setdefault(qualified, [])
                depth += line.count("{") - line.count("}")
                if "{" in line:
                    stack.append((name if kind != "extension" else qualified,
                                  depth - 1))
                continue

            # A member of the innermost type, at its own brace level.
            if stack and depth == stack[-1][1] + 1:
                owner = ".".join(n for n, _ in stack)
                mm = MEMBER.match(line)
                if mm:
                    what, name = mm.group(1), mm.group(2)
                    is_private = bool(re.match(
                        r"^\s*(?:@\w+\s+)*(?:private|fileprivate)\b", line))
                    if what == "case" and t.kind.get(owner) == "enum":
                        if depth_of(line) != 0:
                            pending = {"owner": owner, "text": line.strip(),
                                       "line": lineno}
                            depth += line.count("{") - line.count("}")
                            continue
                        record_case(t, owner, line.strip(), path, lineno)
                    elif what in ("var", "let"):
                        # Computed if the declaration opens a block; a stored
                        # property never does.
                        stored = not line.rstrip().endswith("{")
                        type_text = ""
                        if ":" in line:
                            type_text = split_top(
                                line.split(":", 1)[1], "=")[0].strip()
                            type_text = type_text.rstrip("{").strip()
                        if stored and name:
                            t.stored[owner].append((name, type_text))
                        if name:
                            t.members[owner].append((name, is_private, stored))
                    elif what in ("func", "init", "subscript"):
                        label = name or what
                        t.members[owner].append((label, is_private, False))
                        t.bodies[(owner, label)] = capture_body(raw, lineno - 1)
                    if what == "var" and name and not line.rstrip().endswith("{") \
                            and lineno < len(raw) and raw[lineno].strip() == "{":
                        t.bodies[(owner, name)] = capture_body(raw, lineno)
                    elif what == "var" and name and line.rstrip().endswith("{"):
                        t.bodies[(owner, name)] = capture_body(raw, lineno - 1)

            depth += line.count("{") - line.count("}")
            while stack and depth <= stack[-1][1]:
                stack.pop()
    return t


def capture_body(raw, start_index):
    """Lines from the declaration to the brace that closes it."""
    body, d, started = [], 0, False
    for line in raw[start_index:]:
        text = strip_comment(line)
        body.append(line.rstrip("\n"))
        d += text.count("{") - text.count("}")
        if "{" in text:
            started = True
        if started and d <= 0:
            break
    return body


def record_case(t, owner, text, path, lineno):
    body = text.strip()
    body = re.sub(r"^case\s+", "", body)
    if "(" not in body:
        for name in split_top(body):
            t.cases[owner].append((re.split(r"[\s=]", name)[0], []))
        return
    name = body[:body.index("(")].strip()
    inner = body[body.index("(") + 1:]
    close = inner.rfind(")")
    if close < 0:
        t.unreadable.append(
            "%s:%d: a `case` whose payload never closes: %s" % (path, lineno, body))
        return
    args = split_top(inner[:close])
    t.cases[owner].append((name, args))


def resolve_name(t, name, stack):
    names = [n for n, _ in stack]
    for k in range(len(names), -1, -1):
        candidate = ".".join(names[:k] + [name]) if k else name
        if candidate in t.kind:
            return candidate
    for known in t.kind:
        if known == name or known.endswith("." + name):
            return known
    return None


def arg_type(arg):
    """The TYPE of one payload argument.

    After the last top-level `:` if there is one, which is what makes
    `_ text: String` read as `String` rather than being skipped — one of the
    four spellings `channels.awk` silently passed.
    """
    parts = split_top(arg, ":")
    return (parts[-1] if len(parts) > 1 else arg).strip()


def closed(t, type_text, scope, seen=None):
    """(is_closed, why_not). Anything unreadable is OPEN."""
    seen = seen or set()
    name = type_text.strip()
    while name.endswith("?") or name.endswith("!"):
        name = name[:-1].strip()
    if name.startswith("[") and name.endswith("]"):
        inner = name[1:-1]
        if ":" in inner:
            return False, "a dictionary payload (%s)" % type_text
        return closed(t, inner, scope, seen)
    if not name:
        return False, "an empty payload type"
    if "<" in name:
        return False, "a generic payload (%s)" % type_text
    if name in SCALARS:
        return True, ""
    if name in ("String", "Substring", "Character", "StaticString",
                "Swift.String", "NSString"):
        return False, "%s — a free-form text payload" % name
    resolved = resolve_name(t, name, [(s, 0) for s in scope])
    if resolved is None:
        return False, ("%s, which these files do not declare, so nothing here "
                       "can say what it may hold" % name)
    if resolved in seen:
        return True, ""
    seen = seen | {resolved}
    kind = t.kind.get(resolved)
    inner_scope = resolved.split(".")
    if kind == "enum":
        cases = t.cases.get(resolved, [])
        if not cases:
            return False, "%s — an enum with no cases this parser could read" % resolved
        for case_name, args in cases:
            for arg in args:
                ok, why = closed(t, arg_type(arg), inner_scope, seen)
                if not ok:
                    return False, "%s.%s carries %s" % (resolved, case_name, why)
        return True, ""
    if kind == "struct":
        props = t.stored.get(resolved, [])
        if not props:
            return False, ("%s — a struct with no stored properties this parser "
                           "could read" % resolved)
        for prop, ptype in props:
            ok, why = closed(t, ptype, inner_scope, seen)
            if not ok:
                return False, "%s.%s is %s" % (resolved, prop, why)
        return True, ""
    return False, "%s is a %s, which cannot be judged closed" % (resolved, kind)


def fail(*lines):
    for line in lines:
        print(line)
    sys.exit(2)


IDENT = re.compile(r"(?<![\w.])([A-Za-z_]\w*)")


def interpolations(text):
    """Every `\\( … )` in a line, read to its matching paren."""
    found, i = [], 0
    while i < len(text) - 1:
        if text[i:i + 2] != "\\(":
            i += 1
            continue
        d, j, expr = 0, i + 1, []
        while j < len(text):
            c = text[j]
            if c == "(":
                d += 1
                if d == 1:
                    j += 1
                    continue
            elif c == ")":
                d -= 1
                if d == 0:
                    break
            expr.append(c)
            j += 1
        found.append("".join(expr))
        i = j + 1
    return found


def outside_strings(text):
    """Only the CODE of a line: string literals removed, interpolations kept.

    A Swift string re-enters code at every `\\(`, and nests: the literals
    "yes" and "no" inside `\\(onPower ? "yes" : "no")` are string context sitting
    inside code context sitting inside string context. A scanner that merely
    toggles on every quote welds those two literals into a phantom identifier
    `yesno` — which is a false RED here, but the same blindness pointed the
    other way is how an expression hides in plain sight.
    """
    out = []
    i, n = 0, len(text)
    in_string = False
    interp = []          # paren depth inside each open interpolation
    while i < n:
        c = text[i]
        if in_string:
            if c == "\\":
                if text[i + 1:i + 2] == "(":
                    interp.append(0)
                    in_string = False
                    out.append(" ")
                    i += 2
                    continue
                i += 2
                continue
            if c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if interp:
            if c == "(":
                interp[-1] += 1
            elif c == ")":
                if interp[-1] == 0:
                    interp.pop()
                    in_string = True
                    out.append(" ")
                    i += 1
                    continue
                interp[-1] -= 1
        out.append(c)
        i += 1
    return "".join(out)


def check_renderer(t, owner, member):
    r"""Every value this renderer names must be one it was HANDED.

    Leak C3 of the fifth pass was a stored `var lastTail` on `ListenJournal`,
    set from a call site nothing looked at and rendered by `describe`'s
    `.sessionStarted` arm. It round-tripped through `parse` unchanged, so even
    the round-trip test stayed green. Nothing about it is a journal write, so
    no finder anchored on one could ever have seen it. The only thing that
    catches it is this: a renderer may speak its own arguments and its own
    `case` bindings, and nothing else.

    NOT JUST INTERPOLATIONS. `PostDetail.text` returns bare expressions and
    concatenates two of them, and an earlier draft of this rule looked only
    inside `\( … )` — so `+ stash` would have been invisible for exactly the
    reason `glue()` stripping `+` was (leak I1). Every identifier in the body
    is judged, however it is spelled.

    THE OWNER'S OWN STORED PROPERTIES ARE ALLOWED ONLY TO A COMPUTED PROPERTY
    OF A VALUE TYPE — `ListenSessionFacts.sentence` may name the three fields
    it renders, because those are what the type was checked closed on. A
    `static func` on the journal may not: that is the `lastTail` shape.
    """
    body = t.bodies.get((owner, member))
    if not body:
        fail("This gate can no longer find %s.%s." % (owner, member),
             "That member is where a typed payload becomes words on disk. With",
             "its body unread, everything it names is unjudged and this rule",
             "would pass on an empty search. Point it at the new name.")

    signature = strip_comment(body[0])
    is_func = bool(re.search(r"\bfunc\b", signature))
    params = set()
    if is_func and "(" in signature:
        inner = signature[signature.index("(") + 1:]
        inner = inner[:inner.rfind(")")] if ")" in inner else inner
        for arg in split_top(inner):
            words = re.findall(r"[A-Za-z_]\w*", arg.split(":")[0])
            if words:
                params.add(words[-1])
    base = params if is_func else {p for p, _ in t.stored.get(owner, [])}

    STRUCTURE = {
        "return", "switch", "case", "default", "if", "else", "guard", "let",
        "var", "for", "in", "where", "self", "true", "false", "nil", "break",
        "func", "static", "private", "String", "some", "throw", "try",
    }

    bound = set(base)
    grounded = False
    for line in body[1:]:
        text = strip_comment(line)
        stripped = text.strip()
        if stripped.startswith("case ") or stripped.startswith("default"):
            bound = set(base)
            bound |= set(re.findall(r"\blet\s+([A-Za-z_]\w*)", stripped))
            bound |= set(re.findall(r"\bvar\s+([A-Za-z_]\w*)", stripped))
        for ident in IDENT.findall(outside_strings(text)):
            if ident in STRUCTURE:
                continue
            if ident in bound:
                grounded = True
                continue
            fail("%s.%s names something it was not handed: `%s`"
                 % (owner, member, ident),
                 "  in: %s" % stripped,
                 "",
                 "This is where the journal chooses its words, and it may say what",
                 "its own arguments and `case` bindings gave it and nothing else.",
                 "A stored property, a static or a global reachable from here is a",
                 "channel no call-site scan looks at — which is exactly how a",
                 "`var lastTail`, set from outside and rendered from right here,",
                 "put a transcript on disk at exit 0.")
    if not grounded:
        fail("%s.%s never names its own payload at all." % (owner, member),
             "Either it stopped rendering what it was given, or this parser is",
             "reading the wrong body. Both leave the renderer unjudged, and an",
             "unjudged renderer reads exactly like a clean one.")


def main():
    journal, facts, capture = sys.argv[1], sys.argv[2], sys.argv[3]
    t = scan([journal, facts])
    if t.unreadable:
        fail("A declaration in the journal's types could not be read to its end:",
             *t.unreadable)

    # ---- 1. THE ENUM IS THERE AND THIS PARSER CAN SEE IT -----------------
    if t.kind.get("ListenEvent") != "enum":
        fail("This gate can no longer find `enum ListenEvent` in %s." % journal,
             "It was about to judge no payloads at all and call the journal clean.",
             "Either the enum was renamed or moved, or this parser has broken;",
             "both leave every payload unread, which is the one thing this leg",
             "exists to refuse.")
    cases = t.cases.get("ListenEvent", [])
    if not cases:
        fail("`ListenEvent` declares no cases this parser could read.",
             "An empty search is not a clean journal.")
    with_payload = [c for c in cases if c[1]]
    if not with_payload:
        fail("No `ListenEvent` case carries a payload at all.",
             "Every line on disk would then be a bare case name, which is not what",
             "this journal does — so this parser is reading the cases wrong and",
             "would report an unchecked enum as closed.")

    # ---- 2. AND EVERY PAYLOAD IS CLOSED ---------------------------------
    open_ones = []
    for name, args in cases:
        for arg in args:
            ok, why = closed(t, arg_type(arg), ["ListenEvent"])
            if not ok:
                open_ones.append("  ListenEvent.%s(%s) -> %s" % (name, arg, why))
    if open_ones:
        fail("A ListenEvent payload is not a closed type:",
             *(open_ones + [
                 "",
                 "The journal is exportable from Settings and the diagnostics screen",
                 "ships in RELEASE, so what is written here leaves a stranger's phone",
                 "on a tap. A payload that can hold arbitrary text puts the privacy",
                 "claim back on a scan over every call site — and five passes of that",
                 "leaked sixteen times while the types held under every attack.",
                 "",
                 "Carry an Int, a Bool, or a closed enum this file declares, and let",
                 "`describe` choose the words."]))
    print("every ListenEvent payload is a closed type: %d cases, %d payloads"
          % (len(cases), sum(len(a) for _, a in cases)))

    # ---- 3. AND THERE IS NO OTHER WAY INTO THE JOURNAL -------------------
    members = t.members.get("ListenJournal")
    if not members:
        fail("This gate can no longer find the members of `ListenJournal`.",
             "It was about to check nothing and report no new ways in.")
    strangers = [(n, stored) for n, private, stored in members
                 if not private and n not in JOURNAL_SURFACE]
    if strangers:
        fail("`ListenJournal` has a member that is neither private nor known:",
             *(["  %s%s" % (n, " (a stored property)" if s else "")
                for n, s in strangers] + [
                 "",
                 "`record` is the only way in, and everything reaching it builds a",
                 "typed `ListenEvent`. A visible member beside it is a second door:",
                 "a `func log(_ text: String)` appending to the ring and the file",
                 "builds no event, matches no anchor any call-site scan knows, and",
                 "puts the owner's transcript on disk at exit 0. So did a stored",
                 "`var lastTail` rendered by `describe`.",
                 "",
                 "Make it private, or add it to JOURNAL_SURFACE in this file with a",
                 "reason — which is the review moment this leg exists for."]))
    # Visible STORED state is judged separately from visible behaviour, because
    # it is the shape that got past every call-site scan: nothing writes it
    # through `record`, so no finder anchored on a journal write can see it
    # being set. Both `shared` and `fileURL` are on the reviewed list above.
    leaky_state = [n for n, private, stored in members
                   if stored and not private and n not in JOURNAL_SURFACE]
    if leaky_state:
        fail("`ListenJournal` stores state anything outside it can reach:",
             *(["  " + n for n in leaky_state] + [
                 "",
                 "A stored property set from a call site is a payload that never",
                 "passed through `record`, so it reaches `describe` without any",
                 "journal write having happened. That is leak C3 exactly."]))
    print("`record` is the only way into the journal, and its state is private")

    # ---- 4. AND THE RENDERERS SPEAK ONLY WHAT THEY WERE HANDED ----------
    for owner, member in RENDERERS:
        check_renderer(t, owner, member)
    print("every renderer says only what its own case arm gave it")

    # ---- 5. AND THE WIRE NAMES STILL AGREE ------------------------------
    origins = {name for name, args in t.cases.get("ListenEvent.Origin", [])}
    if not origins:
        fail("This gate can no longer read `ListenEvent.Origin`'s cases.")
    raws = dict(re.findall(
        r'case\s+([A-Za-z_]\w*)\s*=\s*"([^"]*)"',
        "\n".join(open(journal).read().split("enum Origin")[1:2])))
    wire = {raws.get(o, o) for o in origins if o != "unrecognised"}
    with open(capture) as fh:
        policy = fh.read()
    stamped = set(re.findall(r'static let (?:phone|pendant|typed)\s*=\s*"([^"]*)"',
                             policy))
    if not stamped:
        fail("This gate can no longer read CaptureSourcePolicy's wire constants.")
    if wire != stamped:
        fail("The journal's `Origin` and the wire constants disagree:",
             "  journal: %s" % ", ".join(sorted(wire)),
             "  wire:    %s" % ", ".join(sorted(stamped)),
             "",
             "A rename on one side lands every journal line as `unrecognised` and",
             "the badge silently stops appearing — in silence, on both screens.")
    print("the journal's source names are the ones the phone stamps on the wire")


if __name__ == "__main__":
    main()
