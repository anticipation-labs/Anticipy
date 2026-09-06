#!/usr/bin/env python3
"""CAN A PERSON ACTUALLY CONNECT AN APP? Six legs, measured against LIVE.

Everything about the Connections feature is repo-green. The pure core in
`migration/workers/src/routes/connect.ts` is ported from a spike with 1006
tests, `src/connections/store.ts` refuses a cross-owner write by name, the
provider turns `manage_connections` off and checks the answer, the iOS screen
is drawn — and on 2026-09-06 a person could not connect anything, because none
of it is joined up and none of it is deployed. HARNESS-LAWS law 3 is the whole
reason this file exists: repo-green is not done, and a green suite over a
feature nobody has wired reads exactly like a working product.

WHAT EACH LEG ANSWERS, in the order the chain breaks:

  1. THE WORKER SERVES /c/ AT ALL. `GET api.anticipy.ai/c/<43 characters>` with
     no credentials at all. connect.ts answers a signed-out caller with its own
     HTML — the 401 sign-in page, or its own 404 — and every page it draws
     carries the CSP it mints them with. The router's generic `notFound()`
     (src/pb/wire.ts) is JSON, and that JSON is what a MISSING ROUTE looks
     like. The two are not the same failure and this leg refuses to conflate
     them: one is a page that refused you, the other is a Worker with no
     connect page in it.

  2. THE WIRING IS INSTALLED. An unwired Worker answers 503 carrying the
     sentence connect.ts wrote for exactly this case. That is a RED leg and not
     an unproven one, and the distinction is the point of the whole file: we
     can SEE an unwired Worker. It told us. `installConnectWiring` had zero
     callers when this gate was written, so the honest reading of a 503 here is
     "the store, the catalog and the sentence writer are unset", never "we
     could not tell".

  3. THE FOUR TABLES EXIST ON LIVE D1. `app_usage_signals`, `connections`,
     `connect_nudges`, `connect_links` — asked of `sqlite_master` on the
     production database, not on a local one and not on schema.sql. A table
     that is absent is red and is NAMED, because "connections is broken" sends
     a reader to the code and "connect_links does not exist" sends them to one
     wrangler command.

  4. A LINK CAN BE MINTED AND ITS ROW LANDS. The one leg that writes. It
     inserts the exact seven columns `store.ts put()` writes, reads the row
     back, compares every column, deletes it, and confirms it is gone. This
     catches the failure the store is built around and that a table-name check
     cannot see: on 2026-09-05 the live `events` table was missing two columns
     schema.sql declared and EVERY write became a D1 1101. A table that exists
     with the wrong columns is a feature that fails on its first real link.

     WHY THE PROBE ROW IS SAFE, since this writes to production. Its
     `token_handle` is 32 random bytes in hex and NO TOKEN IS EVER GENERATED —
     the handle is sha256(token) and this one has no preimage anybody holds, so
     there is no string on earth that redeems it. Its `expires_at` is in the
     PAST, so `locate()` calls it dead on arrival, and its `used_at` is NULL,
     so the callback deadline is negative infinity and `/done` calls it dead
     too. Its `user_id` is a synthetic 15-character id that is not an owner and
     its toolkit is not an app. It is then deleted, and the deletion is
     verified rather than assumed. `--read-only` skips it, and skipping it
     makes this leg UNPROVEN rather than green — a leg that was not run does
     not pass.

  5. THE VENDOR KEY ANSWERS. One session create against Composio, exactly the
     call `provider.ts #sessionId` makes, expecting 201 with a `session_id`. A
     key nobody has checked is the cheapest thing in this chain to be wrong and
     the most expensive to discover from a person's tap.

  6. SOMEBODY HAS ACTUALLY CONNECTED AN APP. Distinct owners with a
     `status='connected'` row on live D1. ZERO IS UNPROVEN, NOT RED, and that
     is deliberate: nobody having connected yet is not the same as the feature
     being broken, and a gate that cried failure on the day before launch would
     teach its reader to ignore it — which is how the ears went deaf for thirty
     hours next to a green scoreboard.

THE THIRD STATE IS MANDATORY HERE, and it is copied from firmware_gate.py: exit
2 UNPROVEN is neither pass nor fail, and it belongs to anything that was
GENUINELY NOT MEASURED — the network refused, wrangler has no credentials, no
vendor key was given, a downstream leg could not be attempted because the leg
above it is red. What it must never mean is "measured and disappointing".

    0   every measurable leg passed
    1   RED — something we can SEE is broken
    2   UNPROVEN — a leg could not be measured. It does not pass.

THIS FILE NEVER PRINTS A NUMBER IT DID NOT MEASURE. Every count on the screen
came back from the live database or the live vendor in this run; a leg that
could not be asked prints the reason instead of a zero, because a zero reads as
evidence and an unasked question is not evidence.

HARNESS-LAWS LAW 1. Nothing here decides what anybody MEANT. It compares HTTP
status codes, the CSP header our own Worker mints, four table names, seven
column values it wrote itself, and one vendor status code. Law 1 permits
deterministic gates by name ("Measuring is not programming"), and there is no
prose anywhere in this file's inputs to misread — it never reads a message, a
transcript or a person's words.

    python3 overnight/is_connect_live.py
    python3 overnight/is_connect_live.py --read-only     # leg 4 not attempted
    python3 overnight/is_connect_live.py --self-test     # offline, no network

Read-only apart from leg 4, whose one row is described above.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

# The credentials sit next to the gates and nothing loaded them until _env
# existed. Same three lines every gate in this directory uses.
import os as _os  # noqa: E402
import sys as _sys  # noqa: E402

_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _env  # noqa: E402  sibling module; gates are run as scripts

ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_ENV_LOADED = _env.load_and_announce(ROOT)

# ---------------------------------------------------------------------------
# WHAT IS BEING MEASURED
# ---------------------------------------------------------------------------

RED, UNPROVEN, GREEN = 1, 2, 0
OK, BAD, INFO = "PASS", "FAIL", "...."

#: The Worker that serves the product. `CONNECT_URL_BASE` in connect.ts is
#: `https://api.anticipy.ai/c` and the comment above it says why it is not the
#: apex: this Worker's only route is the custom domain, and the apex answers a
#: redirect that never reaches the code. So this gate asks the host the links
#: are actually minted for, not the one the spec would prefer.
WORKER = (os.environ.get("ANTICIPY_PB")
          or os.environ.get("ANTICIPY_BACKEND_URL")
          or "https://api.anticipy.ai").rstrip("/")

#: The production D1 database, as `wrangler d1 execute` addresses it
#: (migration/d1/schema.sql section 5, store.ts, and the runbooks all name it).
D1_DATABASE = os.environ.get("ANTICIPY_D1", "anticipy-backend")

#: The four tables of migration/d1/schema.sql section 5. Sorted, because they
#: are printed when they are missing and a stable order makes two runs
#: comparable.
TABLES = ("app_usage_signals", "connect_links", "connect_nudges", "connections")

#: The vendor, pinned exactly as provider.ts pins it — a floating version is a
#: silent rename away from a leg that measures nothing.
COMPOSIO_BASE = os.environ.get("COMPOSIO_BASE_URL", "https://backend.composio.dev/api/v3.1")
SESSION_PATH = "/tool_router/session"

#: The vendor meta-tool that lets the MODEL start a connection on its own,
#: which in practice means pasting a raw `connect.composio.dev/...` link into a
#: text. `provider.ts MANAGE_CONNECTIONS_TOOL`, spelled the same way. An exact
#: identifier match against a vendor tool id — not a search for words inside a
#: description, and not a list of app names.
MANAGE_CONNECTIONS_TOOL = "COMPOSIO_MANAGE_CONNECTIONS"

#: `TOKEN_CHARS = 43` in connect.ts: 32 bytes of base64url, unpadded. The
#: probe token is well-formed ON PURPOSE — a malformed one would be refused by
#: `parseConnectPath` before the route ever ran, and this leg would then be
#: measuring the path parser instead of the deployment.
TOKEN_CHARS = 43

#: What connect.ts puts on every page it draws (`page()`), and what the router's
#: JSON 404 cannot have. This is the structural discriminator between "a connect
#: page refused you" and "there is no connect page here".
CSP_MARK = "form-action 'self'"

#: The sentence connect.ts wrote for an unwired Worker (`unwired()`). Unique in
#: the tree, and the ONLY way from outside to tell a Worker that has the route
#: and no wiring from one that has both.
UNWIRED_MARK = "Connecting isn't switched on here"

# ---------------------------------------------------------------------------
# THE PROBE ROW (leg 4)
# ---------------------------------------------------------------------------
# Every one of these values is chosen so that a row left behind by a crash
# between the INSERT and the DELETE is inert rather than dangerous.

#: 15 lowercase alphanumerics, which is the owner-row-id shape the CHECK
#: constraint enforces — and deliberately not an owner. No `owners` row has
#: this id, so a link bound to it can never be redeemed by a signed-in person:
#: `locate()` compares the session's owner id against the row's.
PROBE_OWNER = "gateprobe000000"

#: NOT AN APP NAME. The catalog decides what apps exist at run time and no app
#: is hardcoded anywhere in this feature; a gate that wrote "gmail" here would
#: be the first file to break that rule.
PROBE_TOOLKIT = "gate-probe"

#: How far in the past the probe link expires. Any positive number does; an
#: hour is chosen so a clock skew of minutes between this machine and D1
#: cannot accidentally produce a LIVE link.
PROBE_EXPIRY_BACKDATE_MS = 60 * 60 * 1000


class D1Unavailable(RuntimeError):
    """wrangler could not be run, or could not reach the database. This is an
    UNPROVEN cause, never a red one: a gate that reports missing tables because
    nobody was logged in would send its reader to write DDL that already
    exists."""


class VendorUnavailable(RuntimeError):
    """The vendor could not be ASKED. Distinct from the vendor refusing."""


# ===========================================================================
# LEG 1 + LEG 2 — the deployed route, and whether anything is wired to it
# ===========================================================================

def probe_token() -> str:
    """A well-formed token that is not a link.

    Random, so it matches nothing in the store; and it never reaches the store
    anyway, because `locate()` settles the session first and this request
    carries no credentials. It cannot burn anybody's link — burning happens in
    POST /go and this gate never posts.
    """
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "".join(secrets.choice(alphabet) for _ in range(TOKEN_CHARS))


def classify_c_response(status: int, headers: dict, body: str) -> tuple[str, str]:
    """What did the live Worker just answer, structurally?

    Returns (kind, detail). Four kinds, and the reason there are four rather
    than two is that "no route" and "no wiring" are different repairs done by
    different people:

      connect-page   connect.ts drew this. It carries the CSP that `page()`
                     mints on every response it makes.
      unwired        connect.ts drew this AND said the wiring is missing.
      route-missing  the router's own JSON 404. There is no /c/ on this Worker.
      unreadable     something else answered — a proxy, an edge error, an
                     origin that is not this Worker. Measured nothing.
    """
    lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    csp = lowered.get("content-security-policy", "")
    ctype = lowered.get("content-type", "")
    body = body or ""

    if status == 503 and UNWIRED_MARK in body:
        return "unwired", (f"{status} — connect.ts answered with its own "
                           f"\"{UNWIRED_MARK}\" page")
    if CSP_MARK in csp:
        return "connect-page", (f"{status} text/html with connect.ts's own CSP "
                                f"({CSP_MARK})")
    if "application/json" in ctype and '"code":404' in body.replace(" ", ""):
        return "route-missing", (f"{status} application/json — the router's generic "
                                 "notFound(), which is what an unrouted path answers")
    return "unreadable", (f"{status} {ctype or 'no content-type'} — neither a connect.ts "
                          "page nor the router's 404")


def leg_route(kind: str, detail: str, url: str) -> tuple[int, str, str]:
    """LEG 1. Does the deployed Worker serve /c/ at all?"""
    if kind in ("connect-page", "unwired"):
        return GREEN, OK, f"{url} -> {detail}"
    if kind == "route-missing":
        return RED, BAD, (f"{url} -> {detail}. routes/connect.ts is not on the "
                          "deployed Worker: every link in a text 404s")
    return UNPROVEN, INFO, (f"{url} -> {detail}; nothing about the route was "
                            "established")


def leg_wiring(kind: str, detail: str) -> tuple[int, str, str]:
    """LEG 2. Is anything wired to it?

    A 503 is RED and not unproven. We are not guessing at the wiring — the
    Worker told us, in a sentence written for this case.
    """
    if kind == "unwired":
        return RED, BAD, ("the Worker says so itself: no store, no catalog and no "
                          "sentence writer. installConnectWiring() has not been "
                          "called on the deployed build")
    if kind == "connect-page":
        return GREEN, OK, (f"a connect.ts page was drawn ({detail}), which only "
                           "happens after WIRING(env) returned deps")
    return UNPROVEN, INFO, ("not measurable while leg 1 is red — the route that would "
                            "answer 503 is not deployed, so the Worker cannot be "
                            "asked whether anything is wired to it")


# ===========================================================================
# LEG 3 — the four tables, on the live database
# ===========================================================================

def d1_query(sql: str, *, database: str = D1_DATABASE, root: str = ROOT,
             timeout: int = 180, remote: bool = True,
             config: str | None = None, persist_to: str | None = None) -> list[dict]:
    """One statement against the LIVE D1 database, through wrangler.

    `--json` because the human-readable output is a table nobody should parse,
    and `CI=1` so wrangler never opens a prompt in an overnight run. Anything
    that goes wrong here raises `D1Unavailable`, which the legs report as
    UNPROVEN: a missing credential must never be printed as a missing table.

    `remote=False` EXISTS FOR ONE REASON and it is not convenience: leg 4 is the
    only leg that writes, and its statements had never been run anywhere when
    this file was written, because the four tables do not exist on production.
    tests/test_is_connect_live.py stands the tables up in a LOCAL D1 and drives
    the real mint probe through them, so the INSERT, the read-back comparison,
    the DELETE and this JSON parsing are exercised end to end before they are
    ever pointed at production.

    THERE IS DELIBERATELY NO COMMAND-LINE FLAG FOR IT. A gate that can be
    pointed at a local database is a gate that will be, and law 3 exists
    because repo-green has twice been mistaken for done.
    """
    cmd = ["npx", "--no-install", "wrangler", "d1", "execute", database,
           "--remote" if remote else "--local", "--json", "--command", sql]
    if config:
        cmd += ["--config", config]
    # A scratch directory for the local proof, so the test never writes into the
    # repo's own dev database. Production runs pass neither this nor `config`.
    if persist_to:
        cmd += ["--persist-to", persist_to]
    env = dict(os.environ, CI="1")
    try:
        done = subprocess.run(cmd, cwd=root, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except FileNotFoundError:
        raise D1Unavailable("npx is not on PATH, so wrangler could not be run")
    except subprocess.TimeoutExpired:
        raise D1Unavailable(f"wrangler did not answer within {timeout}s")
    if done.returncode != 0:
        raise D1Unavailable(_why_wrangler_failed(done.returncode, done.stderr, done.stdout))
    return _first_result_set(done.stdout)


def _why_wrangler_failed(returncode: int, stderr: str, stdout: str) -> str:
    """A readable reason, not the last line of a JSON dump.

    Measured while writing this file: one transient wrangler failure reported
    itself to the gate as `live D1 could not be read (})` — the closing brace of
    an error object, which tells the reader nothing about whether the problem
    was a credential, a network or a database. The last THREE non-empty lines
    that are not bare punctuation carry the message; the return code is kept
    because it is the one thing that is always meaningful.
    """
    lines = [ln.strip() for ln in (stderr or "").splitlines() + (stdout or "").splitlines()]
    useful = [ln for ln in lines if len(ln.strip("{}[],\"' ")) > 3]
    if not useful:
        return f"wrangler exited {returncode} with nothing readable on either stream"
    return f"wrangler exited {returncode}: " + " | ".join(useful[-3:])[:240]


def _first_result_set(stdout: str) -> list[dict]:
    """Pull the rows out of `wrangler --json`.

    Wrangler prints a JSON array of result sets and, depending on version and
    terminal, some commentary before it. `raw_decode` from the first bracket is
    the whole trick; a regex over the payload would be one D1 message away from
    silently matching nothing.
    """
    start = stdout.find("[")
    if start < 0:
        raise D1Unavailable("wrangler printed no JSON to parse")
    try:
        payload, _ = json.JSONDecoder().raw_decode(stdout[start:])
    except ValueError as exc:
        raise D1Unavailable(f"wrangler's JSON could not be read: {exc}")
    if not isinstance(payload, list) or not payload:
        raise D1Unavailable("wrangler returned no result sets")
    first = payload[0]
    if not isinstance(first, dict):
        raise D1Unavailable("wrangler's first result set is not an object")
    if first.get("success") is False:
        raise D1Unavailable("D1 reported the statement failed")
    rows = first.get("results")
    return rows if isinstance(rows, list) else []


def leg_tables(found: set, database: str) -> tuple[int, str, str]:
    """LEG 3. All four, or say which are missing."""
    missing = [t for t in TABLES if t not in found]
    if not missing:
        return GREEN, OK, (f"all four present on {database}: " + ", ".join(TABLES))
    return RED, BAD, (
        f"{len(TABLES) - len(missing)} of {len(TABLES)} present on {database}; "
        f"MISSING: {', '.join(missing)} — the store refuses every write to a "
        "table that is not there (ConnectionsSchemaMissing)")


# ===========================================================================
# LEG 4 — mint a link and watch the row land
# ===========================================================================

def _probe_row(now_ms: int) -> dict:
    """The seven columns `store.ts put()` writes, with the safety argument for
    each value in the module docstring. Built here so the test can assert on
    the shape without a network."""
    return {
        "token_handle": secrets.token_hex(32),   # 64 hex, no preimage exists
        "user_id": PROBE_OWNER,
        "toolkit": PROBE_TOOLKIT,
        "alias": "",                             # schema.sql's spelling of null
        "expires_at": float(now_ms - PROBE_EXPIRY_BACKDATE_MS),
        "used_at": None,
        "completed_at": None,
    }


def probe_row_is_inert(row: dict, now_ms: int) -> tuple[bool, str]:
    """REFUSE TO WRITE A LIVE LINK. Checked rather than trusted, because the
    values above are one careless edit from being a real connect link bound to
    a real person.

    Four properties, each of which alone makes the row unredeemable:
      * the handle is 64 hex with no token behind it,
      * the owner is the synthetic probe id and not an owner,
      * it expired before it was written,
      * it was never claimed, so the callback window is closed too.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("token_handle", ""))):
        return False, "the token handle is not 64 hex characters"
    if row.get("user_id") != PROBE_OWNER:
        return False, (f"the probe owner is not {PROBE_OWNER!r} — a probe link bound "
                       "to a real owner is a real connect link")
    if not re.fullmatch(r"[a-z0-9]{15}", PROBE_OWNER):
        return False, "the probe owner id is not the 15-character owner-row shape"
    if not isinstance(row.get("expires_at"), (int, float)) or row["expires_at"] >= now_ms:
        return False, "the probe link would be LIVE — expires_at is not in the past"
    if row.get("used_at") is not None or row.get("completed_at") is not None:
        return False, "a probe row must be neither claimed nor completed"
    if not str(row.get("toolkit", "")):
        return False, "the probe toolkit is empty, which the CHECK constraint refuses"
    return True, "unredeemable: no token exists, expired before insert, never claimed"


def _sql_literal(value) -> str:
    """Values this file generated itself, spelled for SQL.

    Nothing untrusted reaches here — the handle is hex this process made, the
    owner and toolkit are module constants checked against a fixed alphabet
    above, and the timestamp is a number. The escaping is belt on top of that,
    and anything that is not one of those three shapes is refused rather than
    quoted, because a gate is the wrong place to invent a serialiser.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        raise ValueError("no boolean column exists in connect_links")
    if isinstance(value, (int, float)):
        return repr(float(value))
    text = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_-]*", text):
        raise ValueError(f"refusing to put {text!r} in a statement")
    return "'" + text + "'"


def mint_probe_link(run_sql, now_ms: int, row: dict | None = None) -> tuple[int, str, str]:
    """LEG 4. Insert the row `store.ts` writes, read it back, delete it.

    `run_sql` is injected so the whole leg is testable without a database. Its
    contract is `d1_query`'s: rows out, `D1Unavailable` on anything else.
    """
    row = row or _probe_row(now_ms)
    inert, why = probe_row_is_inert(row, now_ms)
    if not inert:
        return RED, BAD, f"refused to write the probe row: {why}"

    handle = row["token_handle"]
    cols = ", ".join(f'"{c}"' for c in row)
    vals = ", ".join(_sql_literal(v) for v in row.values())
    try:
        run_sql(f'INSERT INTO "connect_links" ({cols}) VALUES ({vals})')
    except D1Unavailable as exc:
        return RED, BAD, (f"the row did NOT land: {exc}. A link minted for a real "
                          "person would fail exactly here, and connect.ts would have "
                          "nothing to redeem")

    # READ IT BACK BEFORE DELETING IT. An INSERT that reports success and a row
    # that cannot be read are the same outcome for a person tapping a link.
    back, mismatch = None, None
    try:
        rows = run_sql('SELECT "token_handle", "user_id", "toolkit", "alias", '
                       '"expires_at", "used_at", "completed_at" FROM "connect_links" '
                       f"WHERE \"token_handle\" = {_sql_literal(handle)}")
        back = rows[0] if rows else None
        mismatch = _column_mismatch(row, back)
    except D1Unavailable as exc:
        mismatch = f"the row could not be read back: {exc}"

    # THE DELETE RUNS WHATEVER HAPPENED ABOVE, and it is owner-scoped: a gate
    # that leaves rows in production is a gate somebody turns off.
    removed, remove_note = _remove_probe_link(run_sql, handle)

    if mismatch:
        return RED, BAD, f"the row landed and came back wrong: {mismatch}. {remove_note}"
    if back is None:
        return RED, BAD, f"the INSERT reported success and the row was not there. {remove_note}"
    if not removed:
        return RED, BAD, (f"the row landed and CAME BACK CORRECT, and the probe row is "
                          f"still in production: {remove_note}")
    return GREEN, OK, ("one row inserted with the seven columns store.ts writes, read "
                       f"back identical, deleted, and confirmed gone ({remove_note})")


def _column_mismatch(wrote: dict, back: dict | None) -> str | None:
    """Every column, compared. This is the 1101 detector: a live table missing
    `completed_at`, or carrying a column with a different type affinity, shows
    up here and nowhere else."""
    if back is None:
        return None
    for col, want in wrote.items():
        if col not in back:
            return (f"the live table has no {col!r} column — every write store.ts makes "
                    "would be a D1 1101")
        got = back[col]
        if want is None:
            if got is not None:
                return f"{col} came back {got!r}, and NULL was written"
            continue
        if isinstance(want, (int, float)):
            try:
                if float(got) != float(want):
                    return f"{col} came back {got!r}, {want!r} was written"
            except (TypeError, ValueError):
                return f"{col} came back {got!r}, which is not the number that was written"
            continue
        if str(got) != str(want):
            return f"{col} came back {got!r}, {want!r} was written"
    return None


def _remove_probe_link(run_sql, handle: str) -> tuple[bool, str]:
    """Delete the probe row and CONFIRM it is gone.

    Scoped by the probe owner as well as the handle, so a bug in this file can
    only ever delete a row it wrote itself.
    """
    try:
        run_sql(f'DELETE FROM "connect_links" WHERE "token_handle" = {_sql_literal(handle)} '
                f'AND "user_id" = {_sql_literal(PROBE_OWNER)}')
    except D1Unavailable as exc:
        return False, f"the DELETE failed ({exc}) — remove it by hand: token_handle {handle[:12]}…"
    try:
        left = run_sql('SELECT count(*) AS n FROM "connect_links" WHERE "token_handle" = '
                       f"{_sql_literal(handle)}")
        n = int(float(left[0].get("n", 0))) if left else 0
    except (D1Unavailable, TypeError, ValueError, KeyError, IndexError) as exc:
        return False, f"the delete could not be confirmed ({exc}) — check token_handle {handle[:12]}…"
    if n:
        return False, f"{n} row(s) still there — remove token_handle {handle[:12]}… by hand"
    return True, "nothing left behind"


# ===========================================================================
# LEG 5 — the vendor key
# ===========================================================================

def vendor_session(api_key: str, owner: str, *, base: str = COMPOSIO_BASE,
                   opener=None, timeout: int = 45) -> dict:
    """Exactly the call `provider.ts #sessionId` makes, and no other.

    `manage_connections: {enable: false}` is not decoration: measured on
    2026-09-05, `{"enabled": false}` is a 400 and a bare boolean is a 400, and
    a session created with the tool ON hands the model a way to paste a raw
    vendor link into a text — the one thing the spec forbids outright. Sending
    the same body the Worker sends is what makes this leg evidence about the
    Worker rather than about the key alone.

    THE KEY IS NEVER RETURNED, LOGGED OR PRINTED, and neither is the session id.
    """
    body = json.dumps({"user_id": owner, "manage_connections": {"enable": False}}).encode()
    req = urllib.request.Request(
        f"{base.rstrip('/')}{SESSION_PATH}", data=body, method="POST",
        headers={"x-api-key": api_key, "content-type": "application/json",
                 "accept": "application/json"})
    send = (opener or urllib.request.urlopen)
    try:
        with send(req, timeout=timeout) as res:
            return _vendor_answer(res.status, res.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as err:
        return _vendor_answer(err.code, err.read().decode("utf-8", "replace"))
    except Exception as exc:  # transport, DNS, TLS — the vendor was not ASKED
        raise VendorUnavailable(f"{type(exc).__name__}") from None


def _vendor_answer(status: int, text: str) -> dict:
    """What came back, WITHOUT the parts that must not be printed.

    The two fields read here are the two `provider.ts #assertManageConnectionsOff`
    reads, in the same places: `config.manage_connections` is what the vendor
    thinks we asked for, and `tool_router_tools` is what the model would
    actually be handed. They fail differently, which is why the Worker reads
    both and why this gate does too. Measured against the live vendor on
    2026-09-06: `config.manage_connections.enabled` is `false` and the tool list
    holds five tools, none of them the connection tool.
    """
    try:
        root = json.loads(text)
    except ValueError:
        root = None
    sid = None
    manage = None
    tool_present = None
    if isinstance(root, dict):
        raw = root.get("session_id")
        sid = raw if isinstance(raw, str) and raw else None
        config = root.get("config")
        mc = config.get("manage_connections") if isinstance(config, dict) else None
        if isinstance(mc, dict):
            for key in ("enabled", "enable"):
                if isinstance(mc.get(key), bool):
                    manage = mc[key]
                    break
        elif isinstance(mc, bool):
            manage = mc
        tools = root.get("tool_router_tools")
        if isinstance(tools, list):
            names = set()
            for entry in tools:
                if isinstance(entry, str):
                    names.add(entry)
                elif isinstance(entry, dict):
                    for key in ("name", "slug", "tool_slug", "id"):
                        if isinstance(entry.get(key), str):
                            names.add(entry[key])
                            break
            tool_present = MANAGE_CONNECTIONS_TOOL in names
    return {"status": status, "session_id_len": len(sid) if sid else 0,
            "manage_connections": manage, "connection_tool_present": tool_present}


def leg_vendor(answer: dict) -> tuple[int, str, str]:
    """LEG 5. 201 with a session id the WORKER would accept.

    Not merely "the key authenticates". A session whose answer does not confirm
    the connection meta-tool is off is refused by `provider.ts` before it is
    ever cached, so no link can be minted with it — and the reason that check is
    a FLOOR is written on it: waving through leaves the model holding a tool
    that texts people raw vendor links, which is the one thing the spec forbids
    outright. This leg reports the same verdict the deployed Worker would reach
    from the same answer; inventing a softer rule here would make the gate green
    over a session production refuses.
    """
    status = answer.get("status")
    length = answer.get("session_id_len") or 0
    manage = answer.get("manage_connections")
    tool = answer.get("connection_tool_present")
    where = f"POST {COMPOSIO_BASE}{SESSION_PATH}"

    if status != 201:
        return RED, BAD, (f"{where} -> {status}. The vendor key does not open a session, "
                          "so the tap that mints a link has nothing to mint it with")
    if not length:
        return RED, BAD, (f"{where} -> 201 with NO session_id in the body — provider.ts "
                          "raises ConnectionsResponseShape here and no link can be minted")
    if manage is True or tool is True:
        said = ("the config came back with manage_connections ENABLED" if manage is True
                else f"{MANAGE_CONNECTIONS_TOOL} is still in the session's tool list")
        return RED, BAD, (f"{where} -> 201, and {said}. provider.ts refuses this session "
                          "(ConnectionsManageConnectionsOn): the model could paste a raw "
                          "vendor link into a text")
    if manage is None and tool is None:
        return RED, BAD, (f"{where} -> 201, and NEITHER config.manage_connections nor "
                          "tool_router_tools could be read, so nothing confirms the "
                          "connection tool is off. provider.ts refuses this session too")
    confirmed = ", ".join(
        [w for w in ("config.manage_connections says off" if manage is False else "",
                     "the tool list does not carry it" if tool is False else "") if w])
    # WHOSE KEY. This is the key in THIS environment, which is not necessarily
    # the secret bound to the deployed Worker — measured 2026-09-06, they
    # differed: this one answers 201 and `wrangler secret list` for anticipy-api
    # carries no COMPOSIO_API_KEY at all. A leg that let itself be read as
    # "production can reach the vendor" would be the false half of a true
    # sentence, which is the shape every failure in this repo's history has had.
    return GREEN, OK, (f"{where} -> 201, a session id of {length} characters came back, "
                       f"and the connection tool is off ({confirmed}). Measured with the "
                       "key in this environment, NOT with the Worker's own secret — "
                       "`wrangler secret list` says whether the deployed Worker has one")


# ===========================================================================
# LEG 6 — has anybody connected anything
# ===========================================================================

def leg_connected(owners: int | None, rows: int | None) -> tuple[int, str, str]:
    """LEG 6. Owners with a connected row on live D1.

    ZERO IS UNPROVEN. The day before the first person connects, zero is the
    correct state of a working feature; reporting it red would train the reader
    to skip this gate, and a skipped gate is how a thirty-hour outage happens
    next to a green board.
    """
    if owners is None:
        return UNPROVEN, INFO, ("not measurable: the connections table could not be "
                                "counted, so nothing is claimed either way")
    if owners > 0:
        return GREEN, OK, (f"{owners} owner(s) hold {rows} connected row(s) on live D1 — "
                           "somebody has actually connected an app")
    return UNPROVEN, INFO, ("nobody has connected anything yet. That is not a failure — "
                            "it is the state of a feature nobody has been offered. This "
                            "leg turns green on the first real connection")


# ===========================================================================
# THE RUN
# ===========================================================================

def overall(codes: list) -> int:
    """RED beats UNPROVEN beats green. A single visible break is the headline,
    and an unmeasured leg never passes."""
    if RED in codes:
        return RED
    if UNPROVEN in codes:
        return UNPROVEN
    return GREEN


def _http_get(url: str, timeout: int = 30) -> tuple[int, dict, str]:
    """GET with NO credentials at all — no Authorization, no cookie.

    That is what makes leg 1 measure the deployment: a signed-out caller is
    answered by connect.ts before the store is ever touched, so this request
    cannot read, spend or disturb anybody's link.
    """
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, dict(res.headers), res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read().decode("utf-8", "replace")


def run(*, read_only: bool = False, http=None, sql=None, vendor=None,
        owner: str | None = None, now_ms: int | None = None) -> tuple[int, list]:
    """Every leg, in chain order. Returns (exit code, rows to print).

    The three transports are injected so the whole gate is testable offline;
    `main()` supplies the real ones.
    """
    http = http or _http_get
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    rows: list[tuple[str, str, str]] = []
    codes: list[int] = []

    # -- legs 1 and 2: one request, two questions -----------------------------
    url = f"{WORKER}/c/{probe_token()}"
    shown = f"{WORKER}/c/<{TOKEN_CHARS} chars>"
    try:
        status, headers, body = http(url)
        kind, detail = classify_c_response(status, headers, body)
    except Exception as exc:
        kind, detail = "unreachable", f"the request failed: {type(exc).__name__}"

    code, mark, sentence = leg_route(kind, detail, shown)
    codes.append(code)
    rows.append((mark, "1  THE WORKER SERVES /c/", sentence))

    code, mark, sentence = leg_wiring(kind, detail)
    codes.append(code)
    rows.append((mark, "2  THE WIRING IS INSTALLED", sentence))

    # -- leg 3: the four tables ----------------------------------------------
    found: set = set()
    tables_known = False
    if sql is None:
        sql = d1_query
    try:
        names = sql("SELECT name FROM sqlite_master WHERE type='table' AND name IN ("
                    + ", ".join(f"'{t}'" for t in TABLES) + ")")
        found = {str(r.get("name")) for r in names}
        tables_known = True
        code, mark, sentence = leg_tables(found, D1_DATABASE)
    except D1Unavailable as exc:
        code, mark, sentence = UNPROVEN, INFO, (
            f"live D1 could not be read ({exc}) — no claim is made about the tables. "
            "This is a credential or a network, not a schema")
    codes.append(code)
    rows.append((mark, "3  THE FOUR TABLES EXIST ON LIVE D1", sentence))

    # -- leg 4: mint one link -------------------------------------------------
    if read_only:
        code, mark, sentence = UNPROVEN, INFO, (
            "--read-only: the one leg that writes was not attempted, so nothing is "
            "known about whether a minted row lands")
    elif not tables_known:
        code, mark, sentence = UNPROVEN, INFO, (
            "not attempted: live D1 could not be read at all (leg 3)")
    elif "connect_links" not in found:
        code, mark, sentence = UNPROVEN, INFO, (
            "not attempted: connect_links does not exist on live D1 (leg 3), so there is "
            "nothing to write a link into and nothing to measure")
    else:
        code, mark, sentence = mint_probe_link(sql, now_ms)
    codes.append(code)
    rows.append((mark, "4  A LINK CAN BE MINTED, AND ITS ROW LANDS", sentence))

    # -- leg 5: the vendor key ------------------------------------------------
    key = (os.environ.get("COMPOSIO_API_KEY") or "").strip()
    owner = (owner or os.environ.get("ANTICIPY_CONNECT_PROBE_OWNER")
             or os.environ.get("TWO_HANDS_OWNER") or "").strip()
    if not key:
        code, mark, sentence = UNPROVEN, INFO, (
            "no COMPOSIO_API_KEY in the environment, so the vendor was not asked. "
            "A gate that reported this as a dead key would be reporting its own setup")
    elif not re.fullmatch(r"[a-z0-9]{15}", owner):
        code, mark, sentence = UNPROVEN, INFO, (
            "no owner ROW id to ask with (15 lowercase alphanumerics). Set "
            "ANTICIPY_CONNECT_PROBE_OWNER; a name, an email or a UUID is refused here "
            "for the same reason provider.ts refuses one")
    else:
        try:
            code, mark, sentence = leg_vendor(
                (vendor or vendor_session)(key, owner))
        except VendorUnavailable as exc:
            code, mark, sentence = UNPROVEN, INFO, (
                f"the vendor could not be reached ({exc}) — that is a network, not a "
                "verdict about the key")
    codes.append(code)
    rows.append((mark, "5  THE VENDOR KEY ANSWERS", sentence))

    # -- leg 6: has anybody connected anything --------------------------------
    owners_n = rows_n = None
    if tables_known and "connections" in found:
        try:
            counted = sql('SELECT count(*) AS rows_n, count(DISTINCT "user_id") AS owners_n '
                          'FROM "connections" WHERE "status" = \'connected\'')
            if counted:
                owners_n = int(float(counted[0].get("owners_n", 0)))
                rows_n = int(float(counted[0].get("rows_n", 0)))
        except (D1Unavailable, TypeError, ValueError, KeyError, IndexError):
            owners_n = rows_n = None
    code, mark, sentence = leg_connected(owners_n, rows_n)
    codes.append(code)
    rows.append((mark, "6  SOMEBODY HAS ACTUALLY CONNECTED AN APP", sentence))

    return overall(codes), rows


# ===========================================================================
# SELF-TEST — the verdicts against shapes this system has actually had
# ===========================================================================

def self_test() -> int:
    """Offline. Pins each leg to a measured shape rather than to a guess."""
    cases = []

    # Leg 1 / leg 2, from the live probe of 2026-09-06 and the two shapes the
    # deployment can take once connect.ts ships.
    json404 = ({"content-type": "application/json"},
               '{"code":404,"message":"The requested resource wasn\'t found.","data":{}}')
    page401 = ({"content-type": "text/html; charset=utf-8",
                "content-security-policy": "default-src 'none'; img-src https:; "
                "style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; "
                "frame-ancestors 'none'"},
               "<h1>Sign in to finish</h1>")
    page503 = ({"content-type": "text/html; charset=utf-8",
                "content-security-policy": "default-src 'none'; form-action 'self'"},
               f"<h1>{UNWIRED_MARK}</h1>")

    for status, (headers, body), want_kind, want1, want2, why in [
        (404, json404, "route-missing", RED, UNPROVEN,
         "2026-09-06 LIVE: /c/ answers the router's JSON 404"),
        (401, page401, "connect-page", GREEN, GREEN,
         "deployed and wired: the sign-in page a signed-out caller gets"),
        (503, page503, "unwired", GREEN, RED,
         "deployed, nothing wired: the Worker says so itself"),
        (502, ({"content-type": "text/html"}, "<html>edge error</html>"),
         "unreadable", UNPROVEN, UNPROVEN,
         "an edge error is not evidence about the route"),
    ]:
        kind, detail = classify_c_response(status, headers, body)
        cases.append((f"leg1/2  {why}", kind == want_kind
                      and leg_route(kind, detail, "u")[0] == want1
                      and leg_wiring(kind, detail)[0] == want2))

    # Leg 3, from the live query of 2026-09-06: none of the four exist.
    cases.append(("leg3    2026-09-06 LIVE: zero of four tables",
                  leg_tables(set(), "anticipy-backend")[0] == RED))
    cases.append(("leg3    all four present",
                  leg_tables(set(TABLES), "anticipy-backend")[0] == GREEN))
    cases.append(("leg3    one missing is named",
                  "connect_links" in leg_tables(set(TABLES) - {"connect_links"}, "d")[2]))

    # Leg 4's refusal to write anything redeemable.
    now = 1_757_000_000_000
    good = _probe_row(now)
    cases.append(("leg4    the probe row is inert", probe_row_is_inert(good, now)[0]))
    cases.append(("leg4    a LIVE expiry is refused",
                  not probe_row_is_inert({**good, "expires_at": float(now + 600_000)}, now)[0]))
    cases.append(("leg4    a real owner id is refused",
                  not probe_row_is_inert({**good, "user_id": "sxkotd1h02qb6gw"}, now)[0]))
    cases.append(("leg4    a claimed row is refused",
                  not probe_row_is_inert({**good, "used_at": float(now)}, now)[0]))

    # Leg 5, the first case being the vendor's own answer of 2026-09-06:
    # `config.manage_connections.enabled = false`, five tools, none of them the
    # connection tool, and a 16-character session id.
    live201 = {"status": 201, "session_id_len": 16, "manage_connections": False,
               "connection_tool_present": False}
    cases.append(("leg5    2026-09-06 LIVE: 201, session id, connection tool off",
                  leg_vendor(live201)[0] == GREEN))
    cases.append(("leg5    201 with no session id is red",
                  leg_vendor({**live201, "session_id_len": 0})[0] == RED))
    cases.append(("leg5    401 is red",
                  leg_vendor({"status": 401, "session_id_len": 0,
                              "manage_connections": None,
                              "connection_tool_present": None})[0] == RED))
    cases.append(("leg5    the config saying manage_connections ON is red",
                  leg_vendor({**live201, "manage_connections": True})[0] == RED))
    cases.append(("leg5    the connection tool still in the list is red",
                  leg_vendor({**live201, "connection_tool_present": True})[0] == RED))
    cases.append(("leg5    an answer confirming NEITHER is red, not green",
                  leg_vendor({**live201, "manage_connections": None,
                              "connection_tool_present": None})[0] == RED))
    cases.append(("leg5    one half confirming is enough, as in provider.ts",
                  leg_vendor({**live201, "manage_connections": None})[0] == GREEN))
    # The parser reads the two fields where the vendor actually puts them —
    # `config.manage_connections`, not a top-level key. Pinned because reading
    # the wrong place answers None and the leg above turns that into a refusal.
    body = json.dumps({"session_id": "ts_abc123", "config": {
        "manage_connections": {"enabled": False}},
        "tool_router_tools": ["COMPOSIO_SEARCH_TOOLS"]})
    parsed = _vendor_answer(201, body)
    cases.append(("leg5    manage_connections is read from config, not the root",
                  parsed["manage_connections"] is False
                  and parsed["connection_tool_present"] is False
                  and parsed["session_id_len"] == 9))

    # Leg 6 — the whole reason the third state exists.
    cases.append(("leg6    zero connections is UNPROVEN, never red",
                  leg_connected(0, 0)[0] == UNPROVEN))
    cases.append(("leg6    one owner connected is green",
                  leg_connected(1, 2)[0] == GREEN))
    cases.append(("leg6    an uncountable table is UNPROVEN",
                  leg_connected(None, None)[0] == UNPROVEN))

    # The roll-up.
    cases.append(("verdict red beats unproven", overall([GREEN, UNPROVEN, RED]) == RED))
    cases.append(("verdict unproven beats green", overall([GREEN, UNPROVEN]) == UNPROVEN))
    cases.append(("verdict all green is green", overall([GREEN, GREEN]) == GREEN))

    bad = sum(0 if ok else 1 for _, ok in cases)
    print("\n  SELF-TEST — every leg against a shape this system has had")
    print("  " + "-" * 74)
    for name, ok in cases:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("  " + "-" * 74)
    print(f"  {len(cases) - bad}/{len(cases)} correct\n")
    return 1 if bad else 0


def report(code: int, rows: list) -> None:
    width = max(len(r[1]) for r in rows) + 2
    print(f"\n  IS CONNECT LIVE?   {WORKER}   d1: {D1_DATABASE}")
    print("  " + "-" * (width + 30))
    for mark, name, detail in rows:
        print(f"  [{mark}] {name.ljust(width)} {detail}")
    print("  " + "-" * (width + 30))
    if code == RED:
        print("  NOBODY CAN CONNECT AN APP. Work the first red leg — the legs are in")
        print("  chain order and a lower one cannot be measured over a broken higher one.")
        print("  The commands and the order are in "
              "research/2026-09-06-composio-connections-live.md\n")
    elif code == UNPROVEN:
        print("  UNPROVEN — a leg that could not be measured does not pass. What was not")
        print("  measured is named above; none of it is a claim that the feature works.\n")
    else:
        print("  A PERSON CAN CONNECT AN APP, and somebody has.\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--read-only", action="store_true",
                    help="do not write the probe row; leg 4 becomes UNPROVEN")
    ap.add_argument("--self-test", action="store_true",
                    help="check every verdict offline and exit")
    ap.add_argument("--owner", default=None,
                    help="owner ROW id to open the vendor session for (15 lowercase "
                         "alphanumerics)")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    code, rows = run(read_only=args.read_only, owner=args.owner)
    report(code, rows)
    return code


if __name__ == "__main__":
    sys.exit(main())
