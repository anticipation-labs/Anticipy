"""THE STRANGER GATE. The cold stranger's week, as prerequisites a machine checks.

`overnight/done_gate.py` leg 6 is the finish line: a real person who is not Omar,
on their own accounts, carried through a real day. It cannot be faked and it
should not be — it needs a human week.

But a human week is expensive, and on 2026-08-24 an audit walked that week
through the code first and found nine dead ends before anybody spent one
(`research/2026-08-24-cold-stranger-walkthrough.md`). Six of the nine were not
logic bugs at all: they were drift between what is deployed and what is in the
tree, and between what the documentation says and what the screens are called.

The problem with an audit is that it is true on the day it was written. This
file is the half of that audit a machine can re-check every time it is run, so
the next person does not rediscover it by burning a stranger's week.

Rules, the same as done_gate.py, tejas_gate.py and tape_gate.py:

  * A leg that CANNOT be tested FAILS. No model key, no network, no `swift` on
    PATH, a symbol renamed out from under a leg — all of those are red, and the
    message says so rather than passing by default.
  * A leg that cannot FAIL is worse than no leg. Four gate rules in this repo
    were caught on 2026-08-24 passing by matching nothing, including one
    satisfied by a guard three lines above the sentence it meant to read. Every
    leg here was watched going red against the real tree and green against a
    mutated copy — `tests/test_stranger_gate.py` is that record.
  * A leg SEARCHES FOR BEHAVIOUR, NEVER FOR A TOKEN. The first version of this
    file was driven green five times over by comments, a rename and a
    neighbouring sentence — a `# TODO: honour CLOCK_QUIET…` retired the
    quiet-hours leg, a `# NOTE: MediaUrl is not wired yet` retired the MediaUrl
    leg — because a note documenting the absence contains the token the leg was
    hunting. The same defect fired the other way and blocked a correct repair.
    So Python is read as a syntax tree and followed through its calls, Swift
    and JavaScript have their comments stripped and their constants resolved,
    calls are parsed rather than windowed, and leg 3 outright compiles and runs
    the shipped code. See "READING CODE, NOT PROSE" below.
  * Legs run in order and the FIRST failure sets the verdict; later legs still
    run, so the whole picture is visible in one screen.
  * LIVE where LIVE is what bites (HARNESS-LAWS.md Law 3). Repo-green is not
    done: prod has served stale code twice. Legs 1 and 9 read production. Every
    other leg reads the tree and says so.

--------------------------------------------------------------------------
WHAT THIS GATE CANNOT SEE — stated out loud, so green is never read as safe
--------------------------------------------------------------------------
Everything the walkthrough could only settle with a device and a person:
whether the cable install succeeds on the stranger's phone at all, whether the
provisioning profile outlives the week, whether the Twilio account is trial
(on a trial account every unverified number fails silently), whether the
speaker engine actually judges correctly once enrolled, and whether the worker
running in production is this worker.

And, in the seven legs that read the tree: WHAT PRODUCTION IS ACTUALLY
RUNNING. Only legs 1 and 9 read a deployed artifact. Everything else is green
against this checkout, and this checkout has twice not been what was serving —
the extension at 0.8.4 against an app demanding 0.11.0, and the setup page.
The READY message says so out loud rather than leaving it in this docstring.

One thing inside a leg that it cannot see, named rather than implied: leg 6
establishes that quiet hours CAN stop the welcome, not that the guard points
the right way. A condition written backwards reads identically in a syntax
tree; telling them apart needs the clock moved, which is a running worker.

And four of the nine dead ends are deliberately NOT pinned here, because a leg
built on a name nobody has agreed to yet fires wrongly at 3am. They are listed
in `research/2026-08-24-stranger-gate.md` with the reason for each: the missing
consent artifact (STOP / 10DLC live outside the repo), MockTransport reporting
mock sends as delivered (the honest fix is a visible signal, not a return
value this gate could pin), the browser being offered only after an errand is
already stuck (a documented design decision, not drift), and UNDO plus the
clean-day counter (WIRE IT ALL names them, no code does — there is no symbol,
no column and no external API to anchor a leg to, so a leg here would only be
pinning a name this gate invented).

Run:  python3 overnight/stranger_gate.py
      python3 overnight/stranger_gate.py --verbose
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

BASE = os.environ.get("ANTICIPY_BACKEND_URL",
                      "https://backend-production-61e0a.up.railway.app")

# The one URL the setup page hands a stranger. Three names are served from the
# same bytes (`extension/build-zip.sh` copies the zip to all three); this is the
# one `backend/pb_public/setup.html` actually links.
ZIP_NAME = "anticipy-claude-version-extension.zip"

APP = "app/ios/Anticipy/AnticipyApp.swift"
BACKEND_SWIFT = "app/ios/Anticipy/Backend/AnticipyBackend.swift"
CONTENT = "app/ios/Anticipy/Views/ContentView.swift"
ONBOARDING = "app/ios/Anticipy/Views/OnboardingView.swift"
FINALE = "app/ios/Anticipy/Views/OnboardingFinale.swift"
SETTINGS = "app/ios/Anticipy/Views/SettingsView.swift"
ENROLL = "app/ios/Anticipy/Views/VoiceEnrollView.swift"
SPEAKER_MODEL = "app/ios/Anticipy/Resources/speaker-embedding.onnx"
WORKER = "brain/worker.py"
VOICE_ARM = "brain/voice_arm.py"
GUARD = "backend/pb_hooks/workflow_guard.pb.js"
SETUP_PAGE = "backend/pb_public/setup.html"
EXT_ONBOARDING = "extension/onboarding.html"
MANIFEST = "extension/manifest.json"
REPO_ZIP = "backend/pb_public/" + ZIP_NAME

WALKTHROUGH = "research/2026-08-24-cold-stranger-walkthrough.md"


class LegFailed(Exception):
    """The message is what the owner reads. Name the consequence, not the rule."""


def note(msg: str) -> None:
    if VERBOSE:
        print(f"      {msg}")


# --------------------------------------------------------------------------
# Reading the tree. Everything takes an explicit root so the mutation tests in
# tests/test_stranger_gate.py can point a leg at a synthetic copy — a gate leg
# nobody has watched fail is not a gate leg.
# --------------------------------------------------------------------------
def read(root: str, rel: str) -> str:
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        raise LegFailed(
            f"{rel} is not in this tree, so this leg cannot be tested — which "
            "counts as failing. If the file moved, move the leg with it; do "
            "not delete the leg, the check rots silently without it.")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def read_bytes(root: str, rel: str) -> bytes:
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        raise LegFailed(
            f"{rel} is not in this tree, so this leg cannot be tested.")
    with open(path, "rb") as f:
        return f.read()


def http_get(url: str, timeout: int = 30) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def swift_span(source: str, signature_re: str) -> str:
    """The full text of a Swift declaration, from its signature to the `}` that
    closes it, by counting braces. Used to lift a real shipped function out and
    RUN it, rather than believing a comment about what it does."""
    m = re.search(signature_re, source, re.M)
    if not m:
        return ""
    open_at = source.find("{", m.start())
    if open_at < 0:
        return ""
    depth = 0
    for i in range(open_at, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[m.start():i + 1]
    return ""


# --------------------------------------------------------------------------
# READING CODE, NOT PROSE.
#
# On 2026-08-24 a review drove five of this gate's legs green without fixing
# one thing. A `# TODO: honour CLOCK_QUIET_START/END here` comment retired the
# quiet-hours leg. A `# NOTE: MediaUrl is not wired yet` retired the MediaUrl
# leg. Moving a key into `OnboardingKeys.hasOnboarded` retired the leg that
# says the key is device-global. A sentence 200 characters past a call
# satisfied the leg reading that call. A comment naming a file satisfied the
# leg asking whether first run puts that file on screen.
#
# One defect, five times: THE LEG SEARCHED FOR A TOKEN INSTEAD OF ESTABLISHING
# THE BEHAVIOUR — and a note documenting the absence contains the token, so
# writing down that the bug is still there retires the leg that tracks it.
#
# The same defect fires the other way too, and that half is worse: leg 6 went
# RED on a real, working quiet-hours guard written behind a helper name, which
# is a gate blocking a correct repair and teaching people to route around it.
#
# So, everywhere below: Python is read as a syntax tree, where comments do not
# exist at all, and followed through the calls it makes; Swift and JavaScript
# have their comments removed before anything is matched; a constant is
# resolved to the literal behind it; a call's arguments are found by balancing
# its parentheses rather than by taking the next 400 characters. Leg 3 remains
# the standard — it compiles and runs the shipped function — and each of these
# is the closest the other legs can get to it.
# --------------------------------------------------------------------------
def strip_comments(source: str) -> str:
    """`source` with every `//` line comment and `/* */` block comment replaced
    by spaces. String literals are left alone (a URL keeps its `//`), newlines
    are kept, and the result is the same length as the input, so offsets and
    line numbers still line up with the file on disk.

    Swift and JavaScript only. Python needs none of this — `ast` has already
    thrown the comments away by the time a leg sees the tree."""
    out = list(source)
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if c == '"' and source.startswith('"""', i):     # Swift multi-line
            j = source.find('"""', i + 3)
            i = n if j < 0 else j + 3
            continue
        if c in "\"'":
            j = i + 1
            while j < n and source[j] != c and source[j] != "\n":
                j += 2 if source[j] == "\\" else 1
            i = j + 1
            continue
        if c == "/" and i + 1 < n and source[i + 1] in "/*":
            if source[i + 1] == "/":
                j = source.find("\n", i)
                j = n if j < 0 else j
            else:
                j = source.find("*/", i + 2)
                j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


def balanced_args(source: str, at: int) -> str:
    """The argument list of the call whose name starts at `at`: from its `(` to
    the `)` that closes it, string literals skipped.

    Leg 7 used to take the 400 characters after the call and ask whether the
    word `receipt` was in them, so a comment two lines below saying the receipt
    is NOT rendered turned the leg green. A call has an exact extent; this
    reads it."""
    open_at = source.find("(", at)
    if open_at < 0:
        return ""
    depth, i, n = 0, open_at, len(source)
    while i < n:
        c = source[i]
        if c in "\"'":
            j = i + 1
            while j < n and source[j] != c and source[j] != "\n":
                j += 2 if source[j] == "\\" else 1
            i = j + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return source[open_at + 1:i]
        i += 1
    return ""


def split_args(args: str) -> list:
    """An argument list split on its top-level commas, so `result: job.result`
    and `receipt: job.receipt` are two things and not one blob of text."""
    out, depth, start, i, n = [], 0, 0, 0, len(args)
    while i < n:
        c = args[i]
        if c in "\"'":
            j = i + 1
            while j < n and args[j] != c and args[j] != "\n":
                j += 2 if args[j] == "\\" else 1
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            out.append(args[start:i])
            start = i + 1
        i += 1
    out.append(args[start:])
    return [piece for piece in (p.strip() for p in out) if piece]


def blank_span(source: str, start: int, end: int) -> str:
    keep = "".join(c if c == "\n" else " " for c in source[start:end])
    return source[:start] + keep + source[end:]


def strip_previews(source: str) -> str:
    """Xcode previews blanked. A `PreviewProvider` builds every view in the
    app and ships to nobody, so a preview constructing VoiceEnrollView would
    tell leg 5 that first run offers enrollment. Same reasoning as comments:
    it is not the running product."""
    out = source
    while True:
        m = re.search(r"^[ \t]*(?:@\w+\s+)*(?:public\s+|private\s+|internal\s+|"
                      r"fileprivate\s+|final\s+)*struct\s+\w+\s*:[^\n{]*"
                      r"\bPreviewProvider\b", out, re.M)
        if not m:
            break
        span = swift_span(out, re.escape(out[m.start():m.end()]))
        if not span:
            break
        out = blank_span(out, m.start(), m.start() + len(span))
    while True:
        m = re.search(r"#Preview\b[^\n{]*\{", out)
        if not m:
            break
        depth, i = 0, m.end() - 1
        while i < len(out):
            if out[i] == "{":
                depth += 1
            elif out[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out = blank_span(out, m.start(), min(i + 1, len(out)))
    return out


def swift_sources(root: str) -> dict:
    """Every .swift file under the app, comments and previews stripped, keyed
    by repo-relative path. Build products are skipped: a stale copy of a view
    inside a .xcarchive is not what ships."""
    base = os.path.join(root, "app", "ios", "Anticipy")
    found = {}
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in ("build", "DerivedData")
                       and not d.endswith(".xcarchive")]
        for fn in sorted(filenames):
            if not fn.endswith(".swift"):
                continue
            full = os.path.join(dirpath, fn)
            with open(full, encoding="utf-8", errors="replace") as f:
                found[os.path.relpath(full, root)] = strip_previews(
                    strip_comments(f.read()))
    return found


_SWIFT_TYPE = (r"^[ \t]*(?:@\w+\s+)*(?:public\s+|private\s+|internal\s+|"
               r"fileprivate\s+|final\s+|open\s+)*(?:struct|class|enum|"
               r"extension)\s+{}\b")


def swift_string_behind(expr: str, sources: dict, depth: int = 0) -> tuple:
    """Resolve a Swift key expression to the constant string it actually is.

    Returns `("literal", value)` when the expression is — after following any
    constants and folding any interpolation whose pieces are themselves
    constants — one fixed string for every install; `("varies", detail)` when
    something in it is computed at run time; `("unknown", why)` when it cannot
    be followed, which a leg must treat as failing rather than passing.

    Leg 4 used to accept ANY key that was not a bare literal, so moving
    `"hasOnboarded"` into `OnboardingKeys.hasOnboarded` turned it green while
    the value stayed one string for the whole phone. `AppTheme.key` in this
    same file shows the team writes keys that way, so the rename is the
    likely accident, not a contrived one."""
    expr = expr.strip()
    if depth > 4:
        return ("unknown", f"{expr} resolves through more than four constants")
    if re.fullmatch(r'"[^"\\]*"', expr):
        return ("literal", expr[1:-1])
    if expr.startswith('"') and expr.endswith('"') and len(expr) > 1:
        # An interpolated key. It is only per-account if what it interpolates
        # actually varies — `"onboarded-\(Build.version)"` is still one value
        # for the whole phone, and a leg that stopped at "it interpolates" would
        # pass it.
        pieces, rest, folded = [], expr[1:-1], []
        while True:
            k = rest.find("\\(")
            if k < 0:
                folded.append(rest)
                break
            folded.append(rest[:k])
            depth_p, j = 0, k + 1
            while j < len(rest):
                if rest[j] == "(":
                    depth_p += 1
                elif rest[j] == ")":
                    depth_p -= 1
                    if depth_p == 0:
                        break
                j += 1
            inner = rest[k + 2:j]
            pieces.append(inner)
            kind, val = swift_string_behind(inner, sources, depth + 1)
            if kind != "literal":
                return ("varies", f"{expr} — it interpolates `{inner}`")
            folded.append(val)
            rest = rest[j + 1:]
        return ("literal", "".join(folded))
    if not re.fullmatch(r"[A-Za-z_][\w.]*", expr):
        return ("unknown", f"{expr} is not a literal, a constant or a path")

    parts = expr.split(".")
    member, container = parts[-1], (parts[-2] if len(parts) > 1 else "")
    values, mutable = set(), False
    for _rel, text in sources.items():
        spans = [text]
        if container:
            span = swift_span(text, _SWIFT_TYPE.format(re.escape(container)))
            spans = [span] if span else []
        for span in spans:
            for m in re.finditer(
                    rf"(?:static\s+)?let\s+{re.escape(member)}\s*"
                    r"(?::\s*[^=\n]+?)?=\s*([^\n]+)", span):
                values.add(m.group(1).strip().rstrip(","))
            # A `var` is not a constant, and its initializer is a DEFAULT, not
            # a value: `@AppStorage("accountID") var accountID = ""` folded to
            # the empty string would report an account-scoped key as one fixed
            # string for the phone — red on the very fix the leg asks for.
            if re.search(rf"\bvar\s+{re.escape(member)}\b", span):
                mutable = True
    if not values and mutable:
        return ("varies", f"`{expr}` is a var, so it is decided at run time")
    if not values:
        return ("unknown", f"nothing in the app declares `{expr}` as a `let`")
    if len(values) > 1:
        return ("unknown",
                f"`{expr}` has more than one declaration in the app: "
                + "; ".join(sorted(values)[:3]))
    return swift_string_behind(values.pop(), sources, depth + 1)


# --------------------------------------------------------------------------
# Python read as a tree. A comment is not a syntax node, so none of the legs
# below can be satisfied by one; and a call is followed into the function it
# names, so a guard written behind a helper is seen for what it is.
# --------------------------------------------------------------------------
def py_tree(source: str, rel: str) -> ast.Module:
    try:
        return ast.parse(source)
    except SyntaxError as e:  # noqa: BLE001
        raise LegFailed(
            f"{rel} does not parse as Python ({e}), so this leg cannot read "
            "what it does — which counts as failing.")


def py_functions(tree: ast.AST) -> dict:
    """Every function in the module by name, top-level ones winning over
    nested ones of the same name."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault(node.name, node)
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found[node.name] = node
    return found


def py_callee(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def py_code_nodes(node):
    """Every node under `node` EXCEPT bare string expressions and what is
    inside them. A docstring is prose, not code, and a leg reading prose is
    the whole defect this section exists to remove: a helper whose docstring
    says `MediaUrl is not wired yet` must not answer for the payload."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        for child in ast.iter_child_nodes(cur):
            if isinstance(child, ast.Expr) \
                    and isinstance(child.value, ast.Constant) \
                    and isinstance(child.value.value, str):
                continue
            stack.append(child)


def py_parents(tree: ast.AST) -> dict:
    parents = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def swift_appstorage_key(source: str, flag: str) -> str:
    """The key expression an @AppStorage-backed property is stored under, with
    its parentheses balanced.

    `[^)]*` is the obvious way to write this and it is wrong in exactly the case
    that matters: an account-scoped key is `"hasOnboarded-\\(accountID)"`, whose
    first `)` closes the interpolation. A leg using the lazy pattern reports
    "cannot find the declaration" against the very fix it is asking for, which
    is a red at 3am for work somebody already did."""
    for m in re.finditer(r"@AppStorage\(", source):
        depth = 0
        for j in range(m.end() - 1, len(source)):
            if source[j] == "(":
                depth += 1
            elif source[j] == ")":
                depth -= 1
                if depth == 0:
                    tail = source[j + 1:j + 96]
                    if re.match(rf"\s*(?:private\s+)?var\s+{re.escape(flag)}\b",
                                tail):
                        return source[m.end():j].strip()
                    break
    return ""


def have(prog: str) -> bool:
    from shutil import which
    return which(prog) is not None


# --------------------------------------------------------------------------
# Comparing an extension zip against the source it claims to be. Shared by the
# LIVE leg and the deployable-artifact leg, because the two failures are the
# same failure a deploy apart.
# --------------------------------------------------------------------------
IMPORT_RE = re.compile(
    r"""(?:^|\n)\s*(?:import[^"']*|export[^"']*from\s*)["']\./([^"']+)["']""")
SCRIPT_SRC_RE = re.compile(r"""<script[^>]+src=["']([^"']+)["']""")
INJECTED_RE = re.compile(r"""files:\s*\[([^\]]*)\]""")
GET_URL_RE = re.compile(r"""getURL\(\s*["']([^"']+)["']""")
QUOTED_RE = re.compile(r"""["']([^"']+)["']""")


def source_closure(root: str) -> set:
    """Every file the extension needs in order to run, derived from the source
    the way CHROME reaches it — and the way `extension/build-zip.sh` derives
    what it packages, so the two cannot disagree.

    WHAT COMPLETENESS MEANS FOR A ZIP, and why it is not "the files it happens
    to contain match". Legs 1 and 2 used to compare only files PRESENT in the
    package, so a zip containing nothing but manifest.json reported "byte for
    byte the source the app pins, 1 files" — a byte-perfect subset passing as
    the source. That is 2026-08-13, when workflow_state.js was left out and
    every fresh install sat forever with no pair code, except with the import
    edge removed so the import belt could not see it either.

    A package is the source when every file in it IS the source AND it contains
    everything the source declares it needs. The manifest is the authority for
    the second half because it is what Chrome loads: name a service worker or a
    popup that is not there and the extension is dead at install. From those
    entry points this follows <script src> in the pages, every relative import,
    every file pushed in with executeScript({files:[…]}), and every asset named
    by a literal chrome.runtime.getURL — to a fixed point. Nothing here is a
    remembered list; a new module joins the moment something reaches it."""
    ext = os.path.join(root, "extension")
    manifest_path = os.path.join(ext, "manifest.json")
    if not os.path.exists(manifest_path):
        raise LegFailed(
            f"{MANIFEST} is not in this tree, so there is no way to work out "
            "what a complete package would contain and this leg cannot be "
            "tested.")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as e:  # noqa: BLE001
        raise LegFailed(f"{MANIFEST} is not readable JSON: {e}")

    need = {"manifest.json"}
    queue = []
    worker = (manifest.get("background") or {}).get("service_worker")
    if worker:
        queue.append(worker)
    popup = (manifest.get("action") or {}).get("default_popup")
    if popup:
        queue.append(popup)
    for path in (manifest.get("icons") or {}).values():
        queue.append(path)
    for entry in (manifest.get("content_scripts") or []):
        queue.extend(entry.get("js") or [])
        queue.extend(entry.get("css") or [])
    for entry in (manifest.get("web_accessible_resources") or []):
        queue.extend(entry.get("resources") or [])
    if manifest.get("options_page"):
        queue.append(manifest["options_page"])
    if not queue:
        raise LegFailed(
            f"{MANIFEST} names no service worker, popup, icon or content "
            "script, so there is nothing to follow and this leg cannot tell a "
            "complete package from an empty one. Re-point it.")

    seen = set()
    while queue:
        name = queue.pop(0).lstrip("./")
        if name in seen:
            continue
        seen.add(name)
        path = os.path.join(ext, name)
        if not os.path.isfile(path):
            raise LegFailed(
                f"extension/{name} is reached from {MANIFEST} but is not on "
                "disk, so the source itself could not be packaged. "
                "`sh extension/build-zip.sh` refuses this too.")
        need.add(name)
        if name.endswith((".png", ".jpg", ".svg", ".woff", ".woff2", ".ico")):
            continue
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if name.endswith(".html"):
            queue.extend(h.group(1) for h in SCRIPT_SRC_RE.finditer(text))
        queue.extend(h.group(1) for h in IMPORT_RE.finditer(text))
        for hit in INJECTED_RE.finditer(text):
            queue.extend(QUOTED_RE.findall(hit.group(1)))
        queue.extend(h.group(1) for h in GET_URL_RE.finditer(text))
    return need


def zip_against_source(root: str, blob: bytes) -> dict:
    """What is in this zip that is not the source, what it needs that it does
    not contain, and what it imports that it does not contain. Returns a dict
    of lists, all empty when the artifact IS the source."""
    try:
        z = zipfile.ZipFile(io.BytesIO(blob))
    except Exception as e:  # noqa: BLE001
        raise LegFailed(f"the downloaded artifact is not a readable zip: {e}")
    entries = {}
    for info in z.infolist():
        if info.is_dir():
            continue
        name = info.filename.lstrip("./")
        entries[name] = z.read(info)

    differing, orphaned = [], []
    for name, packed in sorted(entries.items()):
        src = os.path.join(root, "extension", name)
        if not os.path.exists(src):
            orphaned.append(name)
            continue
        with open(src, "rb") as f:
            if f.read() != packed:
                differing.append(name)

    # A package can match its version and still be missing a limb — that is
    # 2026-08-13, when workflow_state.js was left out and every fresh install
    # sat forever with no pair code and no error anywhere. Same belt as
    # extension/build-zip.sh: resolve every relative import inside the package.
    broken = []
    for name, packed in sorted(entries.items()):
        if not name.endswith(".js"):
            continue
        text = packed.decode("utf-8", "replace")
        for hit in IMPORT_RE.finditer(text):
            target = hit.group(1)
            if target not in entries:
                broken.append(f"{name} imports ./{target}, which is not packaged")

    # A byte-perfect SUBSET is not the source. Everything the source says it
    # needs must be in the package — see source_closure().
    missing = sorted(source_closure(root) - set(entries))

    version = ""
    if "manifest.json" in entries:
        try:
            version = json.loads(entries["manifest.json"])["version"]
        except Exception:  # noqa: BLE001
            version = ""
    return {"entries": sorted(entries), "differing": differing,
            "orphaned": orphaned, "broken": broken, "missing": missing,
            "version": version}


def app_pin(root: str) -> str:
    src = read(root, APP)
    m = re.search(r'static let expectedExtensionVersion = "([^"]+)"', src)
    if not m:
        raise LegFailed(
            f"{APP} no longer declares `expectedExtensionVersion`, so there is "
            "no number the stale-extension banner compares against and this "
            "leg cannot be tested. If the constant was renamed, re-point this "
            "leg and tests/test_extension_version_pin.py at the new name.")
    return m.group(1)


def source_version(root: str) -> str:
    try:
        return json.loads(read(root, MANIFEST))["version"]
    except Exception as e:  # noqa: BLE001
        raise LegFailed(f"{MANIFEST} has no usable version string: {e}")


# --------------------------------------------------------------------------
# LEG 1 — THE HANDS ARE DOWNLOADABLE, AND THEY ARE THE ONES THE APP DEMANDS
#         *** LIVE — this leg reads production, not the tree ***
#
# The extension is the only executor in the product. A stranger installs
# whatever the one download URL serves; the app then compares what Chrome
# reports against `expectedExtensionVersion` and, when Chrome is behind, tells
# them: "Open chrome://extensions and press Reload to get 0.11.0."
#
# On 2026-08-24 that URL served 0.8.4 while the app demanded 0.11.0. Reload
# re-reads the folder already on disk — it cannot fetch a version nobody is
# serving — so the instruction was guaranteed not to work, with no next step
# anywhere. That ends day one.
#
# Version equality is not enough on its own and never was: 0.8.2 was once
# served with none of that day's code in it, which no version check could
# catch. So this compares the BYTES of every packaged file against the source,
# which is also the only honest way to see that the live package is missing
# supervised_read.js, config.js, side_trip.js and four more — the reason the
# supervised mail read can never complete in production no matter what the app
# does.
# --------------------------------------------------------------------------
def leg_1_hands_downloadable(root: str = ROOT, fetch=None, base: str = "") -> str:
    fetch = fetch or http_get
    base = (base or BASE).rstrip("/")
    pin = app_pin(root)
    src_version = source_version(root)
    url = f"{base}/{ZIP_NAME}"
    try:
        blob = fetch(url)
    except Exception as e:  # noqa: BLE001
        raise LegFailed(
            f"cannot verify: {url} did not answer ({str(e)[:90]}). This leg is "
            "the one that reads LIVE, so with production unreachable there is "
            "nothing to check and it fails rather than passing. Re-run when "
            "the backend is up, or point ANTICIPY_BACKEND_URL at it.")

    found = zip_against_source(root, blob)
    served = found["version"]
    note(f"served {served}, pinned {pin}, source {src_version}, "
         f"{len(found['entries'])} packaged file(s)")

    if not served:
        raise LegFailed(
            f"{url} answered, but the package has no readable manifest "
            "version. A stranger would install it and the app could not tell "
            "how old it is.")
    if served != pin:
        raise LegFailed(
            f"the app tells the stranger to press Reload to get {pin}; the "
            f"only download in the product serves {served}. Reload re-reads "
            "the folder already on their disk — it cannot fetch a version "
            "nobody is serving, so the banner is a permanent warning with no "
            "exit. Rebuild it (`sh extension/build-zip.sh`), commit, deploy the "
            "backend, and re-run THIS gate rather than the tests — "
            "HARNESS-LAWS Law 3: repo-green is not done.")
    if pin != src_version:
        raise LegFailed(
            f"{MANIFEST} ships {src_version} but {APP} pins {pin}. The banner "
            "can only fire for someone BEHIND the pin, so a pin left in the "
            "past produces no banner at all, for everyone, forever — which is "
            "indistinguishable from a fleet that is up to date. That is how "
            "0.8.3-vs-0.11.0 went unnoticed for three minor versions.")
    if found["orphaned"]:
        raise LegFailed(
            "the served package carries files that are not in extension/ at "
            "all: " + ", ".join(found["orphaned"][:8])
            + ". Either the deploy is older than this tree or somebody edited "
              "the artifact by hand. Rebuild it from source.")
    if found["missing"]:
        raise LegFailed(
            f"the served package is a SUBSET of the extension: "
            f"{len(found['missing'])} file(s) the source needs are not in it — "
            + ", ".join(found["missing"][:8])
            + ". Every byte it does carry may match; that is not the same as "
              "being the extension. Chrome loads what manifest.json names, so "
              "a package without those files installs and does nothing, which "
              "is 2026-08-13 (workflow_state.js left out, every fresh install "
              "sat forever with no pair code and no error anywhere). Rebuild "
              "it (`sh extension/build-zip.sh`), commit, deploy.")
    if found["differing"]:
        raise LegFailed(
            f"the served package says {served} and is NOT that source. "
            f"{len(found['differing'])} file(s) differ byte for byte: "
            + ", ".join(found["differing"][:8])
            + ". A version that matches while the code does not is the exact "
              "failure this comparison exists for — 0.8.2 shipped that way. "
              "The stranger installs instructions nobody wrote.")
    if found["broken"]:
        raise LegFailed(
            "the served package is missing modules its own code imports: "
            + "; ".join(found["broken"][:6])
            + ". Chrome's service worker dies at load, so a fresh install sits "
              "forever with no pair code and no error anywhere.")
    return (f"{url} serves {served}, byte for byte the source the app pins, "
            f"all {len(found['entries'])} files Chrome reaches from "
            "manifest.json")


# --------------------------------------------------------------------------
# LEG 2 — THE ARTIFACT A DEPLOY WOULD SHIP IS THE SOURCE
#         (tree only — this is the leg that makes leg 1 fixable)
#
# Leg 1's answer is "redeploy". This leg asks what a redeploy would actually
# put in a stranger's hands. On 2026-08-24 the committed zip was itself four
# files stale against its own source — agent_loop.js, config.js, side_trip.js
# and supervised_read.js — while its manifest.json was byte-identical, so both
# reported 0.11.0. `staleExtension()` only speaks when Chrome is BEHIND a
# literal, so it could never notice.
#
# Deploying that zip would turn leg 1 green while shipping code nobody wrote.
# --------------------------------------------------------------------------
def leg_2_deployable_is_source(root: str = ROOT) -> str:
    src_version = source_version(root)
    found = zip_against_source(root, read_bytes(root, REPO_ZIP))
    note(f"{REPO_ZIP}: {found['version']}, {len(found['entries'])} file(s)")
    if found["version"] != src_version:
        raise LegFailed(
            f"{REPO_ZIP} packs {found['version'] or 'no version'} while "
            f"{MANIFEST} says {src_version}. Run `sh extension/build-zip.sh` — "
            "it refuses to emit a zip whose manifest disagrees with source, "
            "which is the one failure it exists to make impossible.")
    if found["orphaned"]:
        raise LegFailed(
            f"{REPO_ZIP} contains files that no longer exist in extension/: "
            + ", ".join(found["orphaned"][:8])
            + ". Rebuild it rather than editing it.")
    if found["missing"]:
        raise LegFailed(
            f"{REPO_ZIP} is a SUBSET of extension/: {len(found['missing'])} "
            "file(s) the source needs are not packaged — "
            + ", ".join(found["missing"][:8])
            + ". Deploying it would hand the stranger an extension Chrome "
              "cannot run, while leg 1 reported it byte for byte the source. "
              "`sh extension/build-zip.sh` derives what to package from the "
              "same entry points; run it and commit the result.")
    if found["differing"]:
        raise LegFailed(
            f"{REPO_ZIP} reports {found['version']} and does not CONTAIN "
            f"{found['version']}. {len(found['differing'])} file(s) differ from "
            "extension/: " + ", ".join(found["differing"][:8])
            + ".\n        manifest.json is byte-identical, so the zip and the "
              "source agree on the number and disagree on the code — and "
              "staleExtension() compares numbers, so nothing in the product "
              "can see it. Deploying this would turn leg 1 green while handing "
              "the stranger code nobody wrote. `sh extension/build-zip.sh`, "
              "commit the result, then deploy.")
    if found["broken"]:
        raise LegFailed(
            f"{REPO_ZIP} is missing modules its own code imports: "
            + "; ".join(found["broken"][:6])
            + ". This is 2026-08-13 exactly: the MV3 service worker dies at "
              "load and every fresh install sits with no pair code.")
    return (f"{REPO_ZIP} is extension/ at {src_version}, "
            f"{len(found['entries'])} files, nothing Chrome reaches is "
            "missing, imports complete")


# --------------------------------------------------------------------------
# LEG 3 — A NUMBER FROM OUTSIDE NORTH AMERICA SURVIVES SIGN-UP
#         (tree — but it RUNS the shipped Swift, it does not read it)
#
# SMS is the only channel the product has outside the app. `AnticipySession
# .e164` normalises what a person typed, and it prepends "+1" to any bare
# 10-digit number. A stranger in London or Bangalore types their own number,
# sign-up succeeds, and a US number is written to their account. Nothing
# validates it, nothing tests deliverability, and no error appears anywhere —
# they simply never receive a single text for the rest of the week.
#
# This leg lifts the real function out of the real file and EXECUTES it, so it
# tests what ships rather than what a comment claims. A leg that grepped for
# `"+1"` would go green the day somebody moved the literal into a constant.
# --------------------------------------------------------------------------
LONDON_LOCAL = "2079460958"          # a real London landline, typed bare
LONDON_FULL = "+442079460958"        # the same number, fully qualified
DELHI_LOCAL = "07700900123"          # 11 digits, leading 0, not NANP


SWIFT_MODIFIERS = (r"(?:private|fileprivate|internal|public|open|final|static|"
                   r"class|nonisolated|override|@objc)")
E164_SIG = rf"^[ \t]*(?:{SWIFT_MODIFIERS}\s+)*func e164\("


def _run_e164(root: str, cases: list[str]) -> dict:
    src = read(root, APP)
    # Every modifier, not just `nonisolated`: a repair that fixes the "+1"
    # guess AND marks the function `private` would otherwise leave this leg red
    # on a product that is fixed. The modifiers are stripped before compiling,
    # since `static func` at file scope is not Swift.
    fn = swift_span(src, E164_SIG)
    if not fn:
        raise LegFailed(
            f"could not find `func e164` in {APP}, so the leg that proves a "
            "foreign number survives sign-up cannot be tested — which counts "
            "as failing. If normalisation moved, move this leg with it.")
    if not have("swift"):
        raise LegFailed(
            "cannot verify: `swift` is not on PATH, so the shipped "
            "normalisation cannot be executed. This leg refuses to fall back "
            "to reading the source for a `+1` literal — that check goes green "
            "the day the literal moves into a constant, while the stranger's "
            "number is still being rewritten. A leg that cannot be tested "
            "does not pass.")
    body = re.sub(rf"^[ \t]*(?:{SWIFT_MODIFIERS}\s+)*func e164\(",
                  "func e164(", fn)
    program = body + "\nfor a in CommandLine.arguments.dropFirst() " \
                     "{ print(e164(a) ?? \"nil\") }\n"
    tmp = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".swift",
                                         delete=False) as f:
            f.write(program)
            tmp = f.name
        r = subprocess.run(["swift", tmp, *cases], capture_output=True,
                           text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise LegFailed("running the shipped e164() timed out after 5 minutes")
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    if r.returncode != 0:
        tail = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-4:]
        raise LegFailed(
            "the shipped e164() would not compile on its own: "
            + " / ".join(t.strip() for t in tail)
            + ". If it now depends on the session around it, this leg needs "
              "re-pointing — it must keep EXECUTING the real thing.")
    out = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    if len(out) != len(cases):
        raise LegFailed(
            f"expected {len(cases)} answers from e164() and got {len(out)}")
    return dict(zip(cases, out))


def leg_3_foreign_number(root: str = ROOT) -> str:
    got = _run_e164(root, [LONDON_LOCAL, LONDON_FULL, DELHI_LOCAL])
    note("  ".join(f"{k} -> {v}" for k, v in got.items()))

    london = got[LONDON_LOCAL]
    if london.startswith("+1"):
        raise LegFailed(
            f"e164({LONDON_LOCAL!r}) returns {london!r}. A stranger outside "
            "North America types their own ten-digit number, sign-up succeeds, "
            "and a US number is written to their account. SMS is the only "
            "channel the product has outside the app, so they receive nothing "
            "for the whole week and no error appears anywhere.\n"
            "        Returning nil for a bare local number is a legitimate fix "
            "— refusing to guess is honest. Guessing the United States is not.")

    delhi = got[DELHI_LOCAL]
    if delhi.startswith("+0"):
        raise LegFailed(
            f"e164({DELHI_LOCAL!r}) returns {delhi!r}. No country code in "
            "E.164 begins with 0, so this number cannot be dialled by anyone; "
            "Twilio rejects it and the failure reaches a print() on worker "
            "stdout and nowhere else. Same stranger, same silent week.")

    if got[LONDON_FULL] != LONDON_FULL:
        raise LegFailed(
            f"e164({LONDON_FULL!r}) returns {got[LONDON_FULL]!r} — a number "
            "the person typed IN FULL, with its country code, no longer "
            "survives normalisation. Refusing every foreign number is not a "
            "fix for guessing at them.")
    return (f"{LONDON_LOCAL} -> {london}, {DELHI_LOCAL} -> {delhi}, "
            f"and a fully-typed +44 survives")


# --------------------------------------------------------------------------
# LEG 4 — ONBOARDING BELONGS TO THE ACCOUNT, NOT TO THE PHONE
#
# `@AppStorage("hasOnboarded")` is device-global and nothing in the account
# lifecycle clears it. A cable install means the phone passed through somebody
# else's hands first — that is the ONLY way to install this app today — so the
# realistic case is: the installer opened it once to check it, and the
# stranger's sign-up lands them straight on the feed. They never see the mic
# primer, listening is never started, and she hears nothing all week. The four
# -step tour is then reachable only as "Replay the welcome tour", buried in
# Settings, which nobody knows to look for.
#
# Two shapes of fix both pass here: key the flag by account, or clear it when
# the account changes. Neither is guessed at — the leg reads which flag the App
# actually routes on and follows it to its declaration.
#
# It follows it THROUGH constants. The first version of this leg accepted any
# key that was not a bare string literal, so `@AppStorage(OnboardingKeys
# .hasOnboarded)` turned it green while the stored value stayed one string for
# the whole phone — the failure leg 3's own comment predicts, "the grep goes
# green the day the literal moves into a constant", reproduced inside the leg
# that was rewritten to fix it. An interpolated key is only per-account if what
# it interpolates actually varies, so that is folded too.
# --------------------------------------------------------------------------
def _clears(lifecycle: str, flag: str, key: str, literal: str) -> str:
    """The line in the account lifecycle that actually CLEARS the flag, or "".

    A mention is not a clear, and neither is a test: `if hasOnboarded == true`
    contains the flag and an `=`, and a leg looking for "the name and an equals
    sign on one line" would read it as a repair. So this wants an assignment TO
    the flag, or a removal/write of the key itself."""
    quoted = f'"{literal}"'
    patterns = (
        rf"\b{re.escape(flag)}\s*=(?!=)",
        r"removeObject\(\s*forKey:\s*(?:" + re.escape(key) + "|"
        + re.escape(quoted) + ")",
        r"\.set\([^)]*forKey:\s*(?:" + re.escape(key) + "|"
        + re.escape(quoted) + ")",
    )
    for row in lifecycle.splitlines():
        for pattern in patterns:
            if re.search(pattern, row):
                return row.strip()
    return ""


def leg_4_onboarding_is_per_account(root: str = ROOT) -> str:
    src = strip_previews(strip_comments(read(root, APP)))
    m = re.search(r"\}\s*else if (\w+)\s*\{\s*\n\s*HomeView\(\)", src)
    if not m:
        raise LegFailed(
            f"{APP} no longer routes to HomeView on a single onboarding flag, "
            "so this leg cannot find what to follow — which counts as failing. "
            "Re-point it at whatever now decides that a signed-in person skips "
            "the tour.")
    flag = m.group(1)
    key = swift_appstorage_key(src, flag)
    if not key:
        raise LegFailed(
            f"{APP} routes on `{flag}` but this leg cannot find its "
            "@AppStorage declaration, so it cannot tell whether the flag "
            "belongs to the account or to the phone. Re-point the leg.")

    sources = swift_sources(root)
    sources[APP] = src
    kind, resolved = swift_string_behind(key, sources)
    note(f"routes on `{flag}`, key {key} -> {kind}: {resolved}")
    if kind == "unknown":
        raise LegFailed(
            f"{APP} stores `{flag}` under {key}, and this leg cannot follow "
            f"that to the string it becomes ({resolved}), so it cannot tell "
            "whether the flag belongs to the account or to the phone — which "
            "counts as failing rather than passing. Re-point the leg at "
            "wherever the key is now defined.")
    if kind == "varies":
        return (f"the onboarding flag `{flag}` is stored under {key}, which is "
                f"not one string for the whole phone: {resolved}")

    literal = resolved
    lifecycle = ""
    for sig in (r"^[ \t]*func signOut\(", r"^[ \t]*func signIn\(",
                r"^[ \t]*func createAccount\("):
        lifecycle += swift_span(src, sig)
    if not lifecycle:
        raise LegFailed(
            f"{APP} has no signOut/signIn/createAccount for this leg to read, "
            "so it cannot tell whether a change of account clears the "
            "onboarding flag. Re-point the leg at the account lifecycle.")
    # The lifecycle already has its comments stripped, and a mention is not a
    # clear: `// we deliberately keep hasOnboarded across accounts` used to
    # satisfy this, and so would `if hasOnboarded == true`.
    row = _clears(lifecycle, flag, key, literal)
    if row:
        return (f"`{flag}` is stored under {key} (\"{literal}\") but the "
                f"account lifecycle clears it — {row} — so a new "
                "account still sees the tour")

    raise LegFailed(
        f"`{flag}` is stored under {key}, which is the one string "
        f"\"{literal}\" on every install — one value for the whole PHONE, and "
        "nothing in signOut, signIn or createAccount clears it. A stranger "
        "handed a phone anybody has opened this app on before signs up and "
        "lands straight on the feed: no microphone primer, so listening is "
        "never started and she hears nothing all week. The tour survives only "
        "as \"Replay the welcome tour\" in Settings, which nobody knows to "
        "look for.\n"
        "        Cable install is the only way onto a device today "
        f"({WALKTHROUGH} Step 0), so the phone having a previous owner is the "
        "normal case, not the edge one. Fix by keying the flag to the account "
        f"id, or by clearing {key} when the account changes.")


# --------------------------------------------------------------------------
# LEG 5 — ENROLLMENT IS OFFERED, NOT MERELY FINDABLE
#
# VoiceEnrollView is complete, its 26MB model ships in every build, and the
# whole app presents it from exactly one place: a sheet inside Settings, under
# "Your voice", below Listening / Pendant / You. Nothing ever suggests it.
#
# The consequence is measured, not speculated: `research/2026-08-24-engine-
# options.md:254` records `speaker` at 0% across 221 events, cause "enrollment
# unreachable", confidence "Certain." With no owner profile the tagger returns
# nil and every line anyone says is attributed to nobody — which is the named
# cause of four of the six bad acts on the only call ever scored.
#
# The planned fix is EnrollmentInvite.swift plus an onboarding page (Task 4 of
# docs/superpowers/plans/2026-08-24-voice-capture.md, still unlanded). This leg
# accepts either the invite or a direct presentation from first run.
# --------------------------------------------------------------------------
#
# "Offered" means PUT ON SCREEN, which in SwiftUI means constructed. The first
# version of this leg asked whether first run's source contained the WORD
# `SettingsView`, so a comment appended to OnboardingView.swift saying
# "enrollment still lives in SettingsView()" turned it green while enrollment
# stayed three scrolls deep in Settings. Comments are stripped and a bare
# mention is not a presentation.
# --------------------------------------------------------------------------
FIRST_RUN = (ONBOARDING, FINALE)
DECLARES_RE = (r"^[ \t]*(?:@\w+[^\n]*?\s+)?(?:public\s+|private\s+|internal\s+|"
               r"fileprivate\s+|final\s+|open\s+)*(?:struct|class|enum)\s+"
               r"(\w+)\s*[:{]")


def _constructs(text: str, type_name: str) -> bool:
    """Does this Swift source PUT `type_name` on screen — i.e. construct it —
    rather than merely name it in passing?"""
    return re.search(rf"\b{re.escape(type_name)}\s*\(", text) is not None


def leg_5_enrollment_offered(root: str = ROOT) -> str:
    read(root, ENROLL)                       # exists, or the leg is untestable
    if not os.path.exists(os.path.join(root, SPEAKER_MODEL)):
        raise LegFailed(
            f"{SPEAKER_MODEL} is not in this tree. Offering enrollment without "
            "the model behind it would give the stranger a twelve-second read "
            "that can never produce a profile.")

    sources = swift_sources(root)
    sites = {rel: text for rel, text in sources.items()
             if rel != ENROLL and _constructs(text, "VoiceEnrollView")}
    note(f"presentation sites: {sorted(sites) or 'none'}")
    if not sites:
        mentions = [rel for rel, text in sources.items()
                    if rel != ENROLL and "VoiceEnrollView" in text]
        raise LegFailed(
            f"{ENROLL} exists and NOTHING in the app presents it"
            + (f" — {', '.join(mentions[:4])} name it without constructing it"
               if mentions else "")
            + ". The model ships in every build and can never be reached.")

    first_run = "".join(sources.get(rel, "") for rel in FIRST_RUN)
    if not first_run.strip():
        raise LegFailed(
            "neither " + " nor ".join(FIRST_RUN) + " is in this tree, so this "
            "leg cannot tell what first run offers. Re-point it.")

    for rel in sorted(sites):
        if rel in FIRST_RUN:
            return f"first run presents enrollment directly ({rel})"
        if rel == SETTINGS:
            # Putting Settings on screen from first run is not offering
            # enrollment; Settings is where enrollment ALREADY is, three
            # scrolls down, which is the entire complaint. Without this, a
            # "Settings" button added to onboarding retires the leg.
            continue
        # One hop: an invite view that first run PUTS ON SCREEN. The types
        # eligible for that hop are the ones this file declares whose own body
        # constructs VoiceEnrollView — not the file's name, which is only a
        # guess at what it declares.
        text = sites[rel]
        carriers = [name for name in re.findall(DECLARES_RE, text, re.M)
                    if _constructs(swift_span(
                        text, DECLARES_RE.replace("(\\w+)",
                                                  re.escape(name))),
                        "VoiceEnrollView")]
        if not carriers:
            carriers = [os.path.basename(rel)[:-len(".swift")]]
        for name in carriers:
            if _constructs(first_run, name):
                return (f"first run offers enrollment through {name} "
                        f"({rel})")

    raise LegFailed(
        "enrollment has " + ("one presentation site" if len(sites) == 1
                             else f"{len(sites)} presentation sites")
        + " and first run is not among them: " + ", ".join(sorted(sites))
        + ".\n        To reach it a stranger must, with nobody suggesting it, "
          "tap the slider glyph in the Home toolbar and scroll past Listening, "
          "Pendant and You. Nobody does. That is why `speaker` is 0% across "
          "221 production events with the cause recorded as \"enrollment "
          "unreachable\" — mechanical, not mysterious, and the named cause of "
          "four of six bad acts on the only call ever scored.\n"
          "        Land the invite: EnrollmentInvite.swift plus an onboarding "
          "page (Task 4 of docs/superpowers/plans/2026-08-24-voice-capture.md). "
          "This leg passes when " + " or ".join(FIRST_RUN) + " presents "
          "VoiceEnrollView, directly or through a view it puts on screen.")


# --------------------------------------------------------------------------
# LEG 6 — THE PRODUCT'S FIRST WORDS CANNOT ARRIVE AT 1AM
#
# `maybe_welcome_new_owner` is the very first text a stranger ever receives.
# It is called from a 60-second polling beat and consults no clock. Every other
# lane in worker.py honours CLOCK_QUIET_START/END — the night digest, the clock
# lane, the nudges — and this one, the only one that fires for somebody who has
# never heard from her before, does not.
#
# People set up new things late at night. The first thing this product would
# ever say to a stranger can be a phone buzz at 1am, which is exactly the
# "makes them say WHAT?" failure the definition of done forbids.
#
# THIS LEG READS A SYNTAX TREE, and it is the one that had to change most.
# Searching the welcome's source for "CLOCK_QUIET" was wrong twice over:
#
#   * it went GREEN on `# TODO: honour CLOCK_QUIET_START/END here before we
#     ever text a stranger` — a comment saying the bug is still there retired
#     the leg that tracks the bug; and
#   * it went RED on a real, working guard written as `if _in_quiet_hours(now):
#     return False`, which is how anyone would write it, since worker.py
#     consults these constants in eight places. A leg that blocks a correct
#     repair is worse than a missing leg: it teaches people to route around
#     the gate.
#
# So the question the leg asks is behavioural: CAN THE CLOCK STOP THIS SEND?
# A comment is not a node in a syntax tree, so it cannot answer yes; a helper
# is followed into, so it can. What is accepted:
#
#   * a branch inside the welcome (or inside anything it calls, transitively
#     through this module) whose condition depends on the quiet constants and
#     one of whose arms returns, raises, continues or breaks;
#   * a return whose value depends on them (`return not _quiet(now) and …`);
#   * a branch that lexically ENCLOSES a call to the welcome.
#
# What is still not seen, said out loud rather than implied: POLARITY. A guard
# written backwards — speaking only during quiet hours — reads identically to
# a correct one in a syntax tree. Establishing that needs the clock moved,
# which is a running worker, not a gate.
# --------------------------------------------------------------------------
QUIET_NAMES = ("CLOCK_QUIET_START", "CLOCK_QUIET_END")
STOPS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _quiet_dependent(expr, funcs: dict, local: set, seen: frozenset) -> bool:
    """Can evaluating this expression's value change with the quiet-hours
    constants — directly, through a local computed from them, or through a
    function in this module that is itself steered by them?"""
    for sub in ast.walk(expr):
        if isinstance(sub, ast.Name) and (sub.id in QUIET_NAMES
                                          or sub.id in local):
            return True
        if isinstance(sub, ast.Attribute) and sub.attr in QUIET_NAMES:
            return True
        if isinstance(sub, ast.Call):
            name = py_callee(sub)
            if name and name in funcs and name not in seen:
                if _steered_by_quiet(funcs[name], funcs, seen | {name}):
                    return True
    return False


def _quiet_locals(fn, funcs: dict, seen: frozenset) -> set:
    """Names inside `fn` that hold a value computed from the quiet constants,
    to a fixed point — `quiet = CLOCK_QUIET_START <= hour …` then `if quiet:`
    is a guard, and a leg that only looked at the `if` would miss it."""
    names, changed = set(), True
    while changed:
        changed = False
        for sub in ast.walk(fn):
            value = getattr(sub, "value", None)
            if not isinstance(sub, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) \
                    or value is None:
                continue
            if not _quiet_dependent(value, funcs, names, seen):
                continue
            targets = sub.targets if isinstance(sub, ast.Assign) else [sub.target]
            for target in targets:
                for nm in ast.walk(target):
                    if isinstance(nm, ast.Name) and nm.id not in names:
                        names.add(nm.id)
                        changed = True
    return names


def _steered_by_quiet(fn, funcs: dict, seen: frozenset) -> bool:
    """Can this function's outcome depend on quiet hours at all? Used when
    following a call — `if _in_quiet_hours(now): return False` needs
    `_in_quiet_hours` to answer yes."""
    local = _quiet_locals(fn, funcs, seen)
    for sub in ast.walk(fn):
        if isinstance(sub, (ast.If, ast.IfExp, ast.While)) \
                and _quiet_dependent(sub.test, funcs, local, seen):
            return True
        if isinstance(sub, ast.Return) and sub.value is not None \
                and _quiet_dependent(sub.value, funcs, local, seen):
            return True
    return False


def _quiet_can_stop(fn, funcs: dict) -> str:
    """The reason this function's send can be stopped by the clock, or ""."""
    local = _quiet_locals(fn, funcs, frozenset())
    for sub in ast.walk(fn):
        if isinstance(sub, (ast.If, ast.While)) \
                and _quiet_dependent(sub.test, funcs, local, frozenset()):
            arms = list(sub.body) + list(getattr(sub, "orelse", []))
            for stmt in arms:
                for inner in ast.walk(stmt):
                    if isinstance(inner, STOPS):
                        return (f"a quiet-hours branch at {WORKER}:"
                                f"{sub.lineno} that can stop the send")
        if isinstance(sub, ast.Return) and sub.value is not None \
                and _quiet_dependent(sub.value, funcs, local, frozenset()):
            return (f"what it returns depends on quiet hours "
                    f"({WORKER}:{sub.lineno})")
    return ""


def leg_6_welcome_respects_the_night(root: str = ROOT) -> str:
    src = read(root, WORKER)
    tree = py_tree(src, WORKER)
    declared = {t.id for node in ast.walk(tree)
                if isinstance(node, ast.Assign)
                for target in node.targets
                for t in ast.walk(target) if isinstance(t, ast.Name)}
    if not set(QUIET_NAMES) & declared:
        raise LegFailed(
            f"{WORKER} no longer declares CLOCK_QUIET_START, so this leg "
            "cannot tell what quiet hours are — which counts as failing. If "
            "the constants were renamed, re-point this leg.")
    funcs = py_functions(tree)
    welcome = funcs.get("maybe_welcome_new_owner")
    if welcome is None:
        raise LegFailed(
            f"{WORKER} has no top-level `maybe_welcome_new_owner`, so the "
            "first text a stranger receives cannot be found and this leg "
            "cannot be tested. Re-point it at whatever sends the welcome.")

    why = _quiet_can_stop(welcome, funcs)
    if why:
        return f"the welcome consults quiet hours before it speaks — {why}"

    # A guard at the CALL SITE is accepted, but only when it truly encloses the
    # call. This used to be read off the indentation of the three lines above,
    # which is a good approximation of enclosure and not the thing itself; the
    # syntax tree says it exactly.
    parents = py_parents(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) \
                or py_callee(node) != "maybe_welcome_new_owner":
            continue
        scope, enclosing = parents.get(node), None
        while scope is not None:
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                enclosing = scope
                break
            scope = parents.get(scope)
        local = (_quiet_locals(enclosing, funcs, frozenset())
                 if enclosing is not None else set())
        holder = parents.get(node)
        while holder is not None:
            if isinstance(holder, (ast.If, ast.IfExp, ast.While)) \
                    and not any(node is n for n in ast.walk(holder.test)) \
                    and _quiet_dependent(holder.test, funcs, local,
                                         frozenset()):
                # The call is in a branch of this test, not in the test itself
                # — a condition that CALLS the welcome in order to decide has
                # already sent it.
                return ("the call to the welcome sits inside a quiet-hours "
                        f"guard ({WORKER}:{holder.lineno})")
            holder = parents.get(holder)

    raise LegFailed(
        "the very first text a stranger ever receives consults no clock. "
        "`maybe_welcome_new_owner` runs off the 60-second profile beat, and "
        "worker.py honours CLOCK_QUIET_START/END in the night digest, the "
        "clock lane and the nudges — everywhere except the one message that "
        "goes to somebody who has never heard from her before.\n"
        "        A stranger who finishes onboarding at 1am, which is when "
        "people set up new things, gets the product's first ever words as a "
        "phone buzz in the middle of the night.\n"
        "        Put the guard INSIDE maybe_welcome_new_owner, next to its "
        "other two guardrails (young profile, one durable stamp per number), "
        "or immediately on the call. A helper is fine — this leg follows "
        "`if _in_quiet_hours(now): return False` into `_in_quiet_hours` — but "
        "the branch has to be able to STOP the send, so a line that only "
        "logs the hour will not do. A held welcome must still be sent in the "
        "morning: dropping it silently trades one bad first impression for "
        "no first impression at all.")


# --------------------------------------------------------------------------
# LEG 7 — WHAT THE SERVER VERIFIED IS WHAT THE PERSON READS
#
# `workflow_guard.pb.js` refuses any transition to `done` unless the job
# carries a receipt with verified === true, a matching effect_key, and a
# non-empty evidence array. The column exists, the migration adds it, and the
# server enforces it on every single completion.
#
# The app never decodes it. `AgentJob` stops at `lane`, and the done card feeds
# `job.result` — free text the browser happened to write — into
# JobReceiptPolicy. So the structured, server-enforced evidence exists in the
# database and the stranger never sees a byte of it; what they see is whatever
# sentence the extension composed. That is the difference between a receipt and
# a claim, on the one card whose entire job is to be a receipt.
# --------------------------------------------------------------------------
#
# The done-card half used to read the 400 characters after the call and ask
# whether the word `receipt` was among them, so a comment two lines below
# saying "the receipt column is not rendered yet" turned it green. A call has
# an exact extent: this balances its parentheses and reads its arguments, with
# the file's comments already removed, and follows a bare argument back to the
# `let` that computed it so a rendered `receiptText` still counts.
# --------------------------------------------------------------------------
def leg_7_receipt_is_what_is_shown(root: str = ROOT) -> str:
    guard = strip_comments(read(root, GUARD))
    if "receipt.verified" not in guard.replace("!receipt.verified",
                                               "receipt.verified"):
        raise LegFailed(
            f"{GUARD} no longer demands a verified receipt before a job may go "
            "done, so the column this leg tracks may no longer be the record "
            "of truth. Re-point the leg — do not delete it. The alternative is "
            "the app rendering the browser's own prose as evidence again.")

    swift = strip_comments(read(root, BACKEND_SWIFT))
    struct = swift_span(swift, r"^struct AgentJob\b")
    if not struct:
        raise LegFailed(
            f"{BACKEND_SWIFT} has no `struct AgentJob`, so this leg cannot "
            "tell what the app decodes. Re-point it.")
    if not re.search(r"^\s*(?:let|var)\s+receipt\b", struct, re.M):
        raise LegFailed(
            "the backend refuses to mark ANY job done without a receipt whose "
            "`verified` is true and whose `evidence` is non-empty — and "
            "`AgentJob` never decodes the column. The app writes `\"receipt\": "
            "\"\"` on approve and cancel and never reads it back.\n"
            "        So the done card renders `result`, which is free text the "
            "extension composed, while the evidence the server actually "
            "checked sits unread in the row. The stranger cannot tell a "
            "receipt from a sentence, which is the whole promise of the card.\n"
            f"        Add `let receipt: String?` to AgentJob in {BACKEND_SWIFT} "
            "and render it.")

    content = strip_comments(read(root, CONTENT))
    i = content.find("JobReceiptPolicy.doneCard(")
    if i < 0:
        raise LegFailed(
            f"{CONTENT} no longer builds the done card through "
            "JobReceiptPolicy.doneCard, so this leg cannot see what it is fed. "
            "Re-point it at the new render site.")
    args = balanced_args(content, i)
    if not args.strip():
        raise LegFailed(
            f"{CONTENT} calls JobReceiptPolicy.doneCard and this leg cannot "
            "read its argument list — the parentheses do not close. Re-point "
            "it at the new render site.")
    carries = False
    for value in split_args(args):
        value = re.sub(r"^[A-Za-z_]\w*\s*:\s*", "", value).strip()
        # `label: "no receipt yet"` is prose handed to the card, not the
        # receipt reaching it, so string contents do not answer this either.
        value = re.sub(r'"[^"]*"', '""', value)
        if re.search(r"\breceipt\b", value):
            carries = True
            break
        # One hop back: `let receiptText = render(job.receipt)` passed in as
        # `evidence: receiptText` IS the receipt reaching the card, and a leg
        # that insisted on the word `receipt` in the argument list itself would
        # go red on it — the same wrong-fire leg 6 was caught making.
        if re.fullmatch(r"[A-Za-z_]\w*", value) and re.search(
                rf"\b(?:let|var)\s+{re.escape(value)}\b[^\n]*\.receipt\b",
                content):
            carries = True
            break
    if not carries:
        raise LegFailed(
            "AgentJob decodes `receipt` and the done card is still fed only "
            f"`result`: doneCard({args.strip()[:120]}). Decoding a column "
            "nothing renders changes nothing a stranger can see — the card "
            "still leads with whatever sentence the browser wrote.")
    return "the server-verified receipt is decoded and reaches the done card"


# --------------------------------------------------------------------------
# LEG 8 — THE DONE-TEXT CAN CARRY THE PHOTO IT PROMISES
#
# WIRE IT ALL's verify loop is act -> evidence -> done-text WITH PHOTO. There
# is no photo. `VoiceArm.text` posts From, To and Body; `MediaUrl` appears
# nowhere in any .py, .js or .swift in this repository.
#
# The anchor here is not a name this gate invented: MediaUrl is Twilio's own
# parameter, and it is the only way an image reaches a phone over the channel
# this product uses. Evidence exists browser-side and server-side as URLs in
# receipt.evidence; it reaches neither the text nor the app.
#
# This leg reads the POST's payload out of the syntax tree. Asking whether the
# text of `text()` contained "MediaUrl" turned it green on
# `# NOTE: MediaUrl is not wired yet; see WIRE IT ALL step 1` — a note
# documenting the absence retiring the leg that tracks it. A comment is not a
# node in a syntax tree, and a key that is not in what gets posted is not
# plumbed.
# --------------------------------------------------------------------------
MEDIA_KEY = "MediaUrl"


def _post_payload(fn, funcs: dict) -> tuple:
    """The expression handed to `data=` on the Messages.json post inside `fn`,
    and the function it was found in. Follows `data=self._payload(...)` into
    that payload builder, so plumbing the parameter through a helper is not
    read as not plumbing it."""
    for sub in py_code_nodes(fn):
        if not isinstance(sub, ast.Call):
            continue
        where = list(sub.args[:1]) + [kw.value for kw in sub.keywords
                                      if kw.arg == "url"]
        url = " ".join(n.value for arg in where for n in ast.walk(arg)
                       if isinstance(n, ast.Constant)
                       and isinstance(n.value, str))
        if "Messages.json" not in url:
            continue
        for kw in sub.keywords:
            if kw.arg in ("data", "json", "files"):
                return (kw.value, fn)
    return (None, fn)


def _carries_media(node, fn, funcs: dict, seen: frozenset) -> bool:
    """Can this payload carry Twilio's MediaUrl? A dict literal with the key, a
    local built up before the post, or a builder function that puts it in."""
    if node is None:
        return False
    for sub in py_code_nodes(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                and sub.value.startswith(MEDIA_KEY):
            return True
        if isinstance(sub, ast.Call):
            name = py_callee(sub)
            if name and name in funcs and name not in seen:
                if _carries_media(funcs[name], funcs[name], funcs,
                                  seen | {name}):
                    return True
    # `payload = {...}` then `payload["MediaUrl"] = url` before the post.
    names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    if names:
        for sub in py_code_nodes(fn):
            if not isinstance(sub, (ast.Assign, ast.AugAssign)):
                continue
            touched = {n.id for t in (sub.targets
                                      if isinstance(sub, ast.Assign)
                                      else [sub.target])
                       for n in ast.walk(t) if isinstance(n, ast.Name)}
            if not (touched & names):
                continue
            for inner in py_code_nodes(sub):
                if isinstance(inner, ast.Constant) \
                        and isinstance(inner.value, str) \
                        and inner.value.startswith(MEDIA_KEY):
                    return True
        for sub in py_code_nodes(fn):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr in ("update", "setdefault") \
                    and isinstance(sub.func.value, ast.Name) \
                    and sub.func.value.id in names:
                for inner in ast.walk(sub):
                    if isinstance(inner, ast.Constant) \
                            and isinstance(inner.value, str) \
                            and inner.value.startswith(MEDIA_KEY):
                        return True
    return False


def leg_8_done_text_can_carry_the_photo(root: str = ROOT) -> str:
    src = read(root, VOICE_ARM)
    tree = py_tree(src, VOICE_ARM)
    if "Messages.json" not in src:
        raise LegFailed(
            f"{VOICE_ARM} no longer posts to Twilio's Messages.json, so this "
            "leg cannot find the send it is about. Re-point it.")
    funcs = py_functions(tree)
    sender = funcs.get("text")
    payload, holder = _post_payload(sender, funcs) if sender else (None, None)
    if sender is None or payload is None:
        raise LegFailed(
            f"{VOICE_ARM} has no `text(` method that posts to Messages.json "
            "with a data payload this leg can read, so it cannot see what an "
            "outgoing text carries — which counts as failing. Re-point it at "
            "whatever sends an SMS now.")
    note(f"{VOICE_ARM} text() posts data={ast.dump(payload)[:80]}")
    if not _carries_media(payload, holder, funcs, frozenset()):
        raise LegFailed(
            "the outgoing text has no way to carry a picture. "
            f"{VOICE_ARM}'s text() posts From, To and Body and nothing else, "
            "and `MediaUrl` — Twilio's own parameter, the only way an image "
            "reaches a phone on this channel — appears in no .py, .js or "
            ".swift in the repository.\n"
            "        WIRE IT ALL step 1 describes the loop as act -> evidence "
            "-> done-text WITH PHOTO. Two of those three exist: the browser "
            "captures evidence and workflow_guard.pb.js refuses `done` without "
            "it, as URLs in receipt.evidence. Nothing carries them onward, so "
            "the stranger's confirmation is a sentence about a screenshot they "
            "will never see.\n"
            "        This leg asks only that the parameter be plumbed. Whether "
            "the picture is the right one is a human's judgement, not a gate's.")
    return "the outgoing text can carry the evidence picture"


# --------------------------------------------------------------------------
# LEG 9 — THE INSTALL GUIDE NAMES SCREENS THAT EXIST
#         *** the live half of this leg reads production ***
#
# `setup.html` is the only guide in the product, and a stranger reads it while
# doing the five-minute Chrome ceremony. Step 5 tells them: "Still setting the
# app up? You're already on the right screen — the one headed 'Your hands on
# the computer.'" That screen was DELETED when the browser left first run;
# onboarding is four beats and none of them is it. The same page then says to
# find "Browser agent" in Settings; the section is called "Your computer".
#
# A stranger following correct instructions concludes they have broken
# something. This is held the way tape_gate holds the audited five: BY NAME,
# because a leg that tried to detect dead pointers in prose by pattern would
# match nothing and pass in silence. Each name is cross-checked against the app
# on every run, so re-introducing the screen retires the item honestly.
# --------------------------------------------------------------------------
DEAD_POINTERS = (
    ("Your hands on the computer", ONBOARDING,
     "a first-run screen deleted when the browser left first run"),
    ("Browser agent", SETTINGS,
     'a Settings section since renamed to "Your computer"'),
)
GUIDE_FILES = (SETUP_PAGE, EXT_ONBOARDING)


def _app_names(root: str) -> tuple[set, str]:
    """Every name first run and Settings actually put on screen, read out of the
    app so this leg updates itself when the app is renamed."""
    # Comments stripped first: a commented-out `beatNames = ["Your hands on
    # the computer"]` would otherwise put a deleted screen back on the list of
    # screens the app has, and retire the dead pointer that names it.
    onb = strip_comments(read(root, ONBOARDING))
    m = re.search(r"beatNames\s*=\s*\[([^\]]*)\]", onb)
    if not m:
        raise LegFailed(
            f"{ONBOARDING} no longer declares `beatNames`, so this leg cannot "
            "read what first run's screens are called and cannot tell a dead "
            "pointer from a live one. Re-point it.")
    names = set(re.findall(r'"([^"]*)"', m.group(1)))
    settings = strip_comments(read(root, SETTINGS))
    sections = set(re.findall(r'Section\("([^"]*)"\)', settings))
    if not sections:
        raise LegFailed(
            f"{SETTINGS} no longer declares any `Section(\"...\")`, so this "
            "leg cannot read what Settings' sections are called. Re-point it.")
    return names | sections, ", ".join(sorted(names))


def leg_9_guide_names_real_screens(root: str = ROOT, fetch=None,
                                   base: str = "") -> str:
    fetch = fetch or http_get
    base = (base or BASE).rstrip("/")
    on_screen, beats = _app_names(root)

    bad = []
    for rel in GUIDE_FILES:
        # `read` raises when the file is gone. This used to `continue`, so
        # renaming setup.html made the tree half of this leg check nothing and
        # say nothing — the silent rot the gate's own rules forbid.
        text = read(root, rel)
        for phrase, home, what in DEAD_POINTERS:
            if phrase in text and phrase not in on_screen:
                bad.append(f"{rel} sends the stranger to “{phrase}” "
                           f"— {what}, and no longer anywhere in {home}")

    url = f"{base}/setup.html"
    try:
        live = fetch(url).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        raise LegFailed(
            f"cannot verify the deployed guide: {url} did not answer "
            f"({str(e)[:80]}). The page a stranger actually reads is the live "
            "one, so this leg fails rather than settling for the tree. "
            + ("The tree is wrong too: " + bad[0] if bad else
               "The copy in the tree is clean."))

    # WHAT CAME BACK HAS TO BE THE GUIDE. A 200 is not an answer: an empty body
    # and an unrelated error page both used to turn this leg GREEN, because
    # nothing dead can be found in a page that contains nothing. Leg 1 has no
    # such hole — it PARSES what it downloads, so an HTML error page is caught
    # by not being a zip. This is the same shape check: the setup page is the
    # page that hands a stranger the extension, so it must link the download.
    if ZIP_NAME not in live:
        raise LegFailed(
            f"what production serves at {url} is not the install guide: "
            f"{len(live)} bytes and no link to {ZIP_NAME}, the download this "
            "page exists to hand over. An empty 200 and an error page both "
            "contain no dead pointers, so a leg that only searched them for "
            "dead pointers would report the guide clean while a stranger "
            "reads whatever this is. Deploy pb_public and re-run.\n"
            "        " + (f"The tree is wrong too: {bad[0]}" if bad
                          else "The copy in the tree is clean."))
    for phrase, home, what in DEAD_POINTERS:
        if phrase in live and phrase not in on_screen:
            bad.append(f"the DEPLOYED {url} sends the stranger to "
                       f"“{phrase}” — {what}, and no longer anywhere "
                       f"in {home}")

    if bad:
        raise LegFailed(
            "the install guide points at things that are not in the app:\n"
            "        - " + "\n        - ".join(bad)
            + f"\n        First run is four beats: {beats}. A stranger "
              "mid-onboarding reads “you're already on the right "
              "screen”, looks at a screen asking for their phone number, "
              "and concludes they have done something wrong — while holding "
              "the six-digit code that pairs the only executor in the product."
              "\n        Fix the guide (or bring the screen back); then deploy "
              "pb_public, because the live half of this leg reads production.")
    return (f"the guide names only screens the app has; first run is: {beats}")


# --------------------------------------------------------------------------

LEGS = [
    (1, "THE HANDS ARE DOWNLOADABLE", "LIVE", leg_1_hands_downloadable),
    (2, "A DEPLOY WOULD SHIP THE SOURCE", "tree", leg_2_deployable_is_source),
    (3, "A FOREIGN NUMBER SURVIVES SIGN-UP", "runs", leg_3_foreign_number),
    (4, "ONBOARDING BELONGS TO THE ACCOUNT", "tree",
     leg_4_onboarding_is_per_account),
    (5, "ENROLLMENT IS OFFERED", "tree", leg_5_enrollment_offered),
    (6, "THE FIRST WORDS RESPECT THE NIGHT", "tree",
     leg_6_welcome_respects_the_night),
    (7, "THE VERIFIED RECEIPT IS WHAT IS SHOWN", "tree",
     leg_7_receipt_is_what_is_shown),
    (8, "THE DONE-TEXT CAN CARRY THE PHOTO", "tree",
     leg_8_done_text_can_carry_the_photo),
    (9, "THE GUIDE NAMES SCREENS THAT EXIST", "LIVE",
     leg_9_guide_names_real_screens),
]


def main() -> int:
    print()
    print(f"  STRANGER GATE   tree: {ROOT}")
    print(f"                  live: {BASE}")
    print(f"                  from: {WALKTHROUGH}")
    print("  " + "-" * 66)
    first = None
    for num, name, where, fn in LEGS:
        try:
            detail = fn()
            print(f"  [{num}] PASS  {name}  ({where})")
            print(f"        {detail}")
        except LegFailed as e:
            mark = "FAIL" if first is None else "fail"
            print(f"  [{num}] {mark}  {name}  ({where})")
            print(f"        {e}")
            if first is None:
                first = (num, name, str(e))
        except Exception as e:  # noqa: BLE001
            print(f"  [{num}] FAIL  {name}  ({where})")
            print(f"        gate itself errored: {e}")
            if first is None:
                first = (num, name, f"gate errored: {e}")
    print("  " + "-" * 66)
    if first is None:
        tree_legs = sorted(num for num, _, where, _ in LEGS if where != "LIVE")
        live_legs = sorted(num for num, _, where, _ in LEGS if where == "LIVE")
        print("  READY — every prerequisite a machine can check is standing.")
        print(f"  READ THAT NARROWLY: {len(tree_legs)} of these {len(LEGS)} "
              f"legs (legs {', '.join(str(n) for n in tree_legs)}) read THIS")
        print("  TREE, not production. They prove the repo. Only legs "
              f"{' and '.join(str(n) for n in live_legs)} survive a")
        print("  bad deploy, and production has served stale code twice — the")
        print("  extension at 0.8.4 against an app demanding 0.11.0, and the")
        print("  setup page. A green here is a green against code that may not")
        print("  be running (HARNESS-LAWS Law 3: repo-green is not done).")
        print("  Nor is it done. done_gate.py leg 6 still needs a real person")
        print("  on their own accounts, carried through a real day.")
    else:
        num, name, _ = first
        print(f"  NOT READY FOR A STRANGER — first failing leg: {num} ({name})")
        print("  Fix this before spending somebody's week discovering it.")
    print()
    print("  What this gate cannot see: everything that needs a device and a")
    print("  person — whether the cable install succeeds at all, whether the")
    print("  provisioning profile outlives the week, whether the Twilio account")
    print("  is trial (unverified numbers fail silently on one), and whether")
    print("  the worker in production is this worker. Four of the nine dead")
    print("  ends are deliberately unpinned; the reasons are in")
    print("  research/2026-08-24-stranger-gate.md.")
    print()
    print("  Also unseen: whether a quiet-hours guard points the right way")
    print("  (leg 6 proves the clock CAN stop the welcome, not which side of")
    print("  it speaks), and what production is running for every leg marked")
    print("  (tree) or (runs) — those prove this checkout, not the deploy.")
    print()
    return 1 if first else 0


if __name__ == "__main__":
    sys.exit(main())
