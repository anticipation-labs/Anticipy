#!/usr/bin/env python3
"""THE WIRING GATE — the failable check behind "nothing is built until it is WIRED."

Omar's second most-cited defect is the plumbing disease: things get BUILT but never WIRED — the
deep scrape existed while the UI called the shallow path; the autonomy dropdown wrote a local JSON
store while the real engine gate sat unused. Every one of those shipped "done" because a test
somewhere exercised the code — just never through the product. This gate assumes every endpoint is
unwired and makes the code prove otherwise.

Three checks, all static, all deterministic (stdlib only, no network, no model calls):
  1. ENGINE → PRODUCT: every FastAPI route in engine/anticipy_engine/main.py must have at least one
     caller in a PRODUCT surface (app/api/*.js, extension/*.js, macapp/*.swift). engine/scripts/ is
     deliberately EXCLUDED — "tested but never surfaced" is exactly the disease, not a wire.
  2. NEXT ROUTE → UI: every app/api/**/route.js must be fetched by some UI code (app/ outside
     app/api/, or web/). A Next route nobody calls is a dead proxy.
  3. ORPHAN MODULES: every .py under engine/anticipy_engine/ must be imported by something.
     Imported only from engine/scripts/ = TEST-ONLY (built for the suite, never for the product).

Matching is CONSERVATIVE by construction: parameterized paths match on their static prefix,
dynamic template segments (`${...}`) match anything, ambiguous imports count as imported. A
failure here is a real severed wire, never a false positive worth arguing with.

Known-unwirable surfaces live in factory/wiring_allowlist.txt (KIND<TAB>NAME<TAB>JUSTIFICATION).
A justification starting with "TODO(FIX-" is acknowledged DEBT: it passes the default run so the
suite stays honest about NEW breakage, and fails --strict so the debt can never silently become
permanent.

Run:  factory/bin/check_wiring.py            (full report)
      factory/bin/check_wiring.py --quiet    (only failures + verdict)
      factory/bin/check_wiring.py --strict   (TODO debt fails too)
      factory/bin/check_wiring.py --list     (dump the enumeration, exit 0)
Exit: 0 = every surface wired or honestly allowlisted · 1 = at least one severed wire
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENGINE_MAIN = REPO / "engine" / "anticipy_engine" / "main.py"
ENGINE_PKG = REPO / "engine" / "anticipy_engine"
ENGINE_SCRIPTS = REPO / "engine" / "scripts"
APP = REPO / "app"
APP_API = REPO / "app" / "api"
EXTENSION = REPO / "extension"
MACAPP = REPO / "macapp"
WEB = REPO / "web"
ALLOWLIST = REPO / "factory" / "wiring_allowlist.txt"

# A char that can CONTINUE a URL path. A route match is only real when the char before and
# after the matched literal is NOT one of these (so "/health" never matches "/healthz" or
# "/api/health", but does match `"/health"`, `/health?`, `/health${qs}`, backtick-end, etc.).
_PATH_CHAR = re.compile(r"[A-Za-z0-9_\-./]")

ROUTE_DECORATOR = re.compile(r'@app\.(get|post|put|delete|websocket)\(\s*"([^"]+)"')


def _read(f: Path) -> str:
    try:
        return f.read_text(errors="replace")
    except Exception:
        return ""


# ---------------------------------------------------------------- allowlist

def load_allowlist() -> tuple[dict[tuple[str, str], str], int]:
    """Returns ({(kind, name): justification}, n_todo). Malformed file = the gate itself fails."""
    entries: dict[tuple[str, str], str] = {}
    todo = 0
    if not ALLOWLIST.exists():
        return entries, todo
    for i, raw in enumerate(_read(ALLOWLIST).splitlines(), 1):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            print(f"❌ ALLOWLIST factory/wiring_allowlist.txt:{i} — expected KIND<TAB>NAME<TAB>"
                  f"JUSTIFICATION (3 tab-separated fields), got {len(parts)}: {line!r}")
            sys.exit(1)
        kind, name, why = (p.strip() for p in parts)
        if kind not in ("endpoint", "route", "module"):
            print(f"❌ ALLOWLIST factory/wiring_allowlist.txt:{i} — KIND must be endpoint|route|"
                  f"module, got {kind!r}")
            sys.exit(1)
        if not name or not why:
            print(f"❌ ALLOWLIST factory/wiring_allowlist.txt:{i} — empty NAME or JUSTIFICATION "
                  f"(an allowlist entry without a reason is just the disease with paperwork)")
            sys.exit(1)
        entries[(kind, name)] = why
        if why.startswith("TODO(FIX-"):
            todo += 1
    return entries, todo


# ------------------------------------------------- CHECK 1: engine endpoints

def enumerate_endpoints() -> list[tuple[str, str]]:
    """[(method, path)] from main.py decorators — ALL engine routes live in main.py."""
    return [(m.group(1), m.group(2)) for m in ROUTE_DECORATOR.finditer(_read(ENGINE_MAIN))]


def caller_surfaces() -> list[tuple[Path, str]]:
    """Product surfaces that may legitimately dial the engine. engine/scripts/ is EXCLUDED."""
    files: list[Path] = []
    if APP_API.exists():
        files += sorted(APP_API.rglob("*.js"))
    if EXTENSION.exists():
        files += sorted(EXTENSION.rglob("*.js"))
    if MACAPP.exists():
        files += sorted(MACAPP.rglob("*.swift"))
    return [(f, _read(f)) for f in files]


def _literal_hit(text: str, path: str) -> bool:
    """True if `path` appears as a complete path literal (not a substring of a longer path)."""
    start = 0
    while True:
        i = text.find(path, start)
        if i < 0:
            return False
        before_ok = i == 0 or not _PATH_CHAR.match(text[i - 1])
        j = i + len(path)
        after_ok = j >= len(text) or not _PATH_CHAR.match(text[j])
        if before_ok and after_ok:
            return True
        start = i + 1


def check_endpoints(endpoints: list[tuple[str, str]], surfaces: list[tuple[Path, str]]) -> list:
    """UNWIRED-ENDPOINT for every engine route no product surface ever dials."""
    failures, seen = [], set()
    for _method, path in endpoints:
        if path in seen:
            continue  # GET+POST on the same path = one wire to prove
        seen.add(path)
        if "{" in path:
            prefix = path[: path.index("{")]  # '/goals/{goal_id}' -> '/goals/'
            wired = any(prefix in text for _f, text in surfaces)
        else:
            wired = any(_literal_hit(text, path) for _f, text in surfaces)
        if not wired:
            failures.append(("endpoint", path,
                             "no caller in app/api, extension/, or macapp/ (engine/scripts "
                             "deliberately doesn't count)"))
    return failures


# ---------------------------------------------------- CHECK 2: app/api routes

def enumerate_api_routes() -> list[str]:
    """/api/<dir> for every app/api/**/route.js; [param] dirs become wildcard segments."""
    routes = []
    if not APP_API.exists():
        return routes
    for f in sorted(APP_API.rglob("route.js")):
        rel = f.parent.relative_to(APP_API)
        segs = [] if str(rel) == "." else list(rel.parts)
        if any(s.startswith("_") for s in segs):
            continue  # _-prefixed dirs are private helpers, not routes
        routes.append("/api" + ("/" + "/".join(segs) if segs else ""))
    return routes


def ui_caller_texts() -> list[str]:
    """Everything that may fetch a Next route: app/ EXCLUDING app/api/, plus web/."""
    texts = []
    if APP.exists():
        for f in sorted(APP.rglob("*.js")):
            if APP_API in f.parents or f == APP_API:
                continue
            texts.append(_read(f))
    if WEB.exists():
        texts += [_read(f) for f in sorted(WEB.rglob("*.js"))]
    return texts

API_LITERAL = re.compile(r"(/api/[^\"'`\s?]*)")


def _segs_match(route: str, literal: str) -> bool:
    """Match a caller's /api/... literal against a route. [param] segments and ${...} caller
    segments are wildcards; a caller literal ending in '/' is a concat prefix (matches one
    more segment). Conservative: dynamic matches anything."""
    r = route.strip("/").split("/")
    lit = literal.split("?")[0]
    prefix_mode = lit.endswith("/")
    c = [s for s in lit.strip("/").split("/") if True]
    if prefix_mode:
        c = [s for s in c if s]  # drop the trailing empty seg
        if len(c) >= len(r):
            return False
        return all(_seg_ok(rs, cs) for rs, cs in zip(r, c))
    if len(c) != len(r):
        return False
    return all(_seg_ok(rs, cs) for rs, cs in zip(r, c))


def _seg_ok(route_seg: str, caller_seg: str) -> bool:
    if route_seg.startswith("[") and route_seg.endswith("]"):
        return bool(caller_seg)          # wildcard route segment
    if "${" in caller_seg:
        return True                      # dynamic caller segment — could be anything
    return route_seg == caller_seg


def check_api_routes(routes: list[str], ui_texts: list[str]) -> list:
    literals = set()
    for text in ui_texts:
        literals.update(API_LITERAL.findall(text))
    failures = []
    for route in routes:
        if not any(_segs_match(route, lit) for lit in literals):
            failures.append(("route", route,
                             "no UI caller in app/ (outside app/api) or web/"))
    return failures


# ------------------------------------------------- CHECK 3: orphan modules

def _import_statements(text: str) -> list[str]:
    """Every import statement in the file, with parenthesized continuations flattened."""
    stmts, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith(("from ", "import ")):
            stmt = re.sub(r"#.*", "", lines[i])  # comments (`# noqa`) are not names
            while (stmt.count("(") > stmt.count(")")) or stmt.rstrip().endswith("\\"):
                i += 1
                if i >= len(lines):
                    break
                stmt = stmt.rstrip().rstrip("\\") + " " + re.sub(r"#.*", "", lines[i])
            stmts.append(" ".join(stmt.split()))
        i += 1
    return stmts

FROM_RE = re.compile(r"^from\s+(\.*)([\w.]*)\s+import\s+(.+)$")
IMPORT_RE = re.compile(r"^import\s+(.+)$")


def _names(clause: str) -> list[str]:
    clause = clause.replace("(", "").replace(")", "")
    out = []
    for part in clause.split(","):
        part = part.strip()
        if " as " in part:
            part = part.split(" as ")[0].strip()
        if part:
            out.append(part)
    return out


def _is_module(dotted: str) -> bool:
    return bool(dotted) and (ENGINE_PKG / (dotted.replace(".", "/") + ".py")).is_file()


def _resolved_targets(stmt: str, importer_pkg: list[str]) -> list[str]:
    """Dotted targets (relative to anticipy_engine) this import statement touches.
    - `from pkg.mod import X`  -> pkg.mod (base is a module: importing from it imports it)
    - `from pkg import X`      -> pkg.X only (NOT bare pkg — pulling one name off a package
                                  is not evidence the package's OTHER re-exports are used)
    - `import anticipy_engine.pkg` / `from x import *` -> pkg / pkg.* (whole-namespace pulls,
                                  matched by the __init__ re-export chase)
    importer_pkg = the importer's dir parts under anticipy_engine ([] outside the package)."""
    targets = []
    m = FROM_RE.match(stmt)
    if m:
        dots, base, clause = m.group(1), m.group(2), m.group(3)
        if dots:  # relative — only resolvable when the importer lives inside the package
            up = len(dots) - 1
            if up > len(importer_pkg):
                return []
            root = importer_pkg[: len(importer_pkg) - up]
            base_parts = root + ([p for p in base.split(".") if p] if base else [])
        else:     # absolute — only anticipy_engine.* counts
            parts = base.split(".")
            if parts[0] != "anticipy_engine":
                return []
            base_parts = parts[1:]
        base_dotted = ".".join(base_parts)
        if _is_module(base_dotted):
            targets.append(base_dotted)  # `from pkg.mod import name` imports pkg.mod itself
        for name in _names(clause):
            if name == "*":
                targets.append((base_dotted + ".*") if base_dotted else "*")
            else:
                targets.append((base_dotted + "." if base_dotted else "") + name)
        return targets
    m = IMPORT_RE.match(stmt)
    if m:
        for name in _names(m.group(1)):
            parts = name.split(".")
            if parts[0] == "anticipy_engine":
                targets.append(".".join(parts[1:]))
        return targets
    return []


def enumerate_modules() -> list[Path]:
    mods = []
    for f in sorted(ENGINE_PKG.rglob("*.py")):
        if "__pycache__" in f.parts or f.name in ("__init__.py", "main.py"):
            continue
        mods.append(f)
    return mods


def check_modules(modules: list[Path]) -> list:
    """ORPHAN-MODULE / TEST-ONLY-MODULE with one level of __init__ re-export chasing.
    CONSERVATIVE: star imports and package-level touches count as importing (never cry wolf)."""
    py_files = [f for f in sorted((REPO / "engine").rglob("*.py"))
                if "__pycache__" not in f.parts and ".venv" not in f.parts]
    # Precompute: for every file, its resolved import targets.
    file_targets: dict[Path, set[str]] = {}
    for f in py_files:
        try:
            rel = f.relative_to(ENGINE_PKG)
            importer_pkg = list(rel.parts[:-1])
        except ValueError:
            importer_pkg = []  # engine/scripts etc.
        tset: set[str] = set()
        for stmt in _import_statements(_read(f)):
            tset.update(_resolved_targets(stmt, importer_pkg))
        file_targets[f] = tset

    def direct_importers(dotted: str) -> set[Path]:
        return {f for f, tset in file_targets.items() if dotted in tset}

    def chase_init(init_file: Path, dotted: str, dead: set[Path]) -> set[Path]:
        """One level of __init__ re-export chasing: the __init__ of package P imported this
        module — whoever pulls the re-exported names (or P's whole namespace: `import ...P`,
        `from P import *`) off P inherits the wire. If NOBODY does, the re-export is dead
        plumbing and vouches for nothing — a module alive only because Python happens to
        execute its package __init__ is exactly the disease this gate exists to catch."""
        init_pkg = ".".join(init_file.relative_to(ENGINE_PKG).parts[:-1])
        init_targets = file_targets[init_file]
        names = {t[len(dotted) + 1:] for t in init_targets
                 if t.startswith(dotted + ".") and "." not in t[len(dotted) + 1:]}
        if dotted in init_targets:                # `from . import mod` — re-exported as `mod`
            names.add(dotted.rsplit(".", 1)[-1])
        # A pure re-export shim vouches for nothing — but an __init__ that USES the imported
        # name in its own body (builds an instance, wires a registry) is a genuine consumer.
        body = re.sub(r'(?s)""".*?"""|\'\'\'.*?\'\'\'', "", _read(init_file))
        body = "\n".join(ln for ln in body.splitlines()
                         if not ln.lstrip().startswith(("from ", "import ", "#")))
        if any(re.search(r"\b" + re.escape(n) + r"\b", body) for n in names):
            return {init_file}
        wanted = {init_pkg, (init_pkg + ".*") if init_pkg else "*"}
        wanted |= {(init_pkg + "." if init_pkg else "") + n for n in names}
        return {f for f, tset in file_targets.items() if tset & wanted} - {init_file} - dead

    dead: set[Path] = set()  # modules already proven orphan can't vouch for anyone else
    verdicts: dict[Path, str] = {}
    while True:
        verdicts = {}
        for mod in modules:
            rel = mod.relative_to(ENGINE_PKG)
            dotted = ".".join(rel.with_suffix("").parts)
            importers = direct_importers(dotted) - {mod} - dead
            expanded: set[Path] = set()
            for f in importers:
                if f.name == "__init__.py" and ENGINE_PKG in f.parents:
                    expanded.update(chase_init(f, dotted, dead | {mod}))
                else:
                    expanded.add(f)
            expanded -= dead
            if not expanded:
                verdicts[mod] = "ORPHAN-MODULE: nothing imports it"
            elif all(ENGINE_SCRIPTS in f.parents for f in expanded):
                verdicts[mod] = "TEST-ONLY-MODULE: imported only from engine/scripts/"
        new_dead = {m for m, v in verdicts.items() if v.startswith("ORPHAN")}
        if new_dead == dead:
            break
        dead = new_dead

    return [("module", str(mod.relative_to(ENGINE_PKG)), why)
            for mod, why in sorted(verdicts.items())]


# ---------------------------------------------------------------------- main

def main() -> int:
    quiet = "--quiet" in sys.argv
    strict = "--strict" in sys.argv
    if "--list" in sys.argv:
        print("== engine endpoints (engine/anticipy_engine/main.py) ==")
        for method, path in enumerate_endpoints():
            print(f"  {method.upper():<9} {path}")
        print("== app/api routes ==")
        for route in enumerate_api_routes():
            print(f"  {route}")
        print("== engine modules ==")
        for mod in enumerate_modules():
            print(f"  {mod.relative_to(ENGINE_PKG)}")
        return 0

    allow, _ = load_allowlist()
    endpoints = enumerate_endpoints()
    routes = enumerate_api_routes()
    modules = enumerate_modules()
    raw_failures = (check_endpoints(endpoints, caller_surfaces())
                    + check_api_routes(routes, ui_caller_texts())
                    + check_modules(modules))

    failures, debt_shown, allowlisted, matched_todo = [], [], 0, 0
    for kind, name, why in raw_failures:
        just = allow.get((kind, name))
        if just is None:
            failures.append((kind, name, why))
        elif just.startswith("TODO(FIX-"):
            allowlisted += 1
            matched_todo += 1
            if strict:
                failures.append((kind, name, f"{why} — acknowledged debt: {just}"))
            else:
                debt_shown.append((kind, name, just))
        else:
            allowlisted += 1  # permanent, justified

    if not quiet:
        print("\n=== WIRING GATE (built-but-never-wired detector) ===")
        for kind, name, just in debt_shown:
            print(f"  ⚠  {kind.upper()} {name} — debt, passes non-strict: {just}")
    for kind, name, why in failures:
        print(f"❌ {kind.upper()} {name} — {why}")

    if failures:
        print(f"\nWIRING: {len(failures)} unwired — FAILS")
        return 1
    print(f"\nWIRING: CLEAN ({len(endpoints)} endpoints / {len(routes)} routes / "
          f"{len(modules)} modules checked, {allowlisted} allowlisted incl. {matched_todo} TODO-debt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
