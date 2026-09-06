#!/usr/bin/env python3
"""CAN A PERSON ACTUALLY CONNECT AN APP, AND DOES ANYTHING EVER OFFER?
Eleven legs, measured against LIVE.

Everything about the Connections feature is repo-green. The pure core in
`migration/workers/src/routes/connect.ts` is ported from a spike with 1006
tests, `src/connections/store.ts` refuses a cross-owner write by name, the
provider turns `manage_connections` off and checks the answer, the iOS screen
is drawn — and on 2026-09-06 a person could not connect anything, because none
of it was joined up and none of it was deployed. HARNESS-LAWS law 3 is the whole
reason this file exists: repo-green is not done, and a green suite over a
feature nobody has wired reads exactly like a working product.

THE LEGS ARE THE CHAIN A PERSON WALKS, in that order, because the gate's own
instruction to its reader is "work the first red leg" and that instruction is
only true if the order is the order things happen in:

    Settings -> Connected Apps        legs 1-2   the phone's API routes, the tables
    "Add an app", and a search        leg 3      the catalog
    a link is minted and texted       leg 4      connect_links
    the person taps it                legs 5-7   the page, the wiring, the way in
    the vendor's screen               leg 8      the key that opens a session
    a connection exists               leg 9      a row on live D1
    the vendor says it expired        leg 10     the webhook verifies

AND THEN THE OTHER HALF OF THE SPEC, which legs 1-10 say nothing about. All ten
measure whether somebody who WANTS to connect an app can. Nobody in this product
ever ASKED. The machinery to accept a yes shipped on 2026-09-06 with nothing
anywhere producing one:

    anything ever OFFERS              leg 11     an `asked` row on live D1

Legs 1, 3 and 7 were added on 2026-09-06 and THE SIX LEGS WERE RENUMBERED into
that order — a note quoting "leg 5" from before that day means the vendor key,
which is leg 8 now. The old order stopped at the /c/ page and had no instrument
at all for the server half: every route the phone actually calls could have
been absent from the deployed Worker and every leg here would still have been
green.

WHAT EACH LEG ANSWERS:

  1. THE /me/connections ROUTES EXIST. Every path in
     `CONNECTIONS_API_ROUTES`, asked with its own verb and NO credential. A
     deployed route answers 401 carrying connections_api.ts's own
     `{"ok":false,"message":"Sign in first."}`; an absent one falls through to
     the router's generic `notFound()` (src/pb/wire.ts), which is JSON with
     `"code":404` in it. Telling those apart is the whole leg — one is a route
     that refused you, the other is a Worker with no such route in it.

     AND THE CONTROL, because a 401 proves nothing on a Worker that answers 401
     to everything: `/me/connectionsX` is deliberately NOT a route (index.ts
     hands over `/me/connections` and the `/me/connections/` prefix, and nothing
     else), so it must come back as the router's generic 404. If the control
     does not, the discriminator is uncalibrated and this leg is UNPROVEN rather
     than green — the 401s would then be evidence about the edge, not about
     the routes.

  2. THE FOUR TABLES EXIST ON LIVE D1. `app_usage_signals`, `connections`,
     `connect_nudges`, `connect_links` — asked of `sqlite_master` on the
     production database, not on a local one and not on schema.sql. A table
     that is absent is red and is NAMED, because "connections is broken" sends
     a reader to the code and "connect_links does not exist" sends them to one
     wrangler command.

  3. THE CATALOG ANSWERS "ADD AN APP". `GET /me/connections/catalog?q=…` with a
     REAL owner credential, which is the only way to see this route at all:
     `connectionsApiRoute` settles the credential before it builds a single
     dependency, so an anonymous caller gets 401 and learns nothing about
     whether the search port behind it is filled.

     A 503 HERE IS RED AND THE MESSAGE IS QUOTED. `searchCatalog` answers
     `refuse(503, CATALOG_UNREACHABLE)` for two different reasons — the
     `ConnectionsApiDeps.search` port is unfilled on the deployed build, or the
     catalog itself did not answer — and this leg does not guess between them,
     because the body does not say. What it will not do is soften it: a person
     who cannot search the catalog cannot connect an app nobody has already
     asked them about, so that is a broken feature and not an unmeasured one.
     (Measured 2026-09-06 06:17 the port had no filler at all; a
     `provider.search` was written into `connectionsApiDeps()` the same day, and
     whether the deployed build carries it is exactly what this leg is for.)

     ITS CONTROL is `GET /me/connections` with the same credential. If the list
     route accepts it and the catalog refuses, the catalog is what is wrong; if
     the list route refuses it too, the CREDENTIAL is what is wrong and this leg
     is UNPROVEN — a stale token reported as a broken catalog sends the reader
     to write a search adapter that was never the problem.

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

  5. THE WORKER SERVES /c/ AT ALL. `GET api.anticipy.ai/c/<43 characters>` with
     no credentials at all. connect.ts answers a signed-out caller with its own
     HTML — the 401 sign-in page, or its own 404 — and every page it draws
     carries the CSP it mints them with. The router's generic `notFound()` is
     JSON, and that JSON is what a MISSING ROUTE looks like. The two are not the
     same failure and this leg refuses to conflate them: one is a page that
     refused you, the other is a Worker with no connect page in it.

  6. THE WIRING IS INSTALLED. An unwired Worker answers 503 carrying the
     sentence connect.ts wrote for exactly this case. That is a RED leg and not
     an unproven one, and the distinction is the point of the whole file: we
     can SEE an unwired Worker. It told us. `installConnectWiring` had zero
     callers when this gate was written, so the honest reading of a 503 here is
     "the store, the catalog and the sentence writer are unset", never "we
     could not tell".

  7. THE PAGE OFFERS A WAY IN. A page that renders is not a page that works.
     The signed-out `/c/{token}` is `refusalPage("sign-in-required")`, and at
     06:17 UTC on 2026-09-06 it was one heading, one sentence and NOTHING ELSE:
     no link, no button, no form. `/c/{token}/code` was live one path segment
     away, serving "Get a code by text" and the entire reason
     routes/connect_auth.ts exists — and the page that needed it did not mention
     it. Every person who tapped a texted link that morning hit a wall.

     So this leg looks for a control on the page whose target RESOLVES to that
     token's own code path — an `href` or an `action`, on one of our own hosts —
     and is RED when there is none, because a dead end is a feature nobody can
     use and a gate that passed on "the page rendered" would be certifying it.
     It went red on the 06:17 page, and green at 07:20 the same day when a
     control pointing at `/c/{token}/code` was deployed. Both readings are
     pinned in the self-test, because a leg is only worth what it has been seen
     to say on both sides of a real repair.

     ITS CONTROL is the same scan run over `/c/{token}/code`, a page that is
     KNOWN to carry exactly such a control (its own form posts back to itself).
     If the scan finds nothing there either, then the scan is what failed and
     this leg is UNPROVEN, not red. A pattern that silently stopped matching is
     the specific way an instrument lies, and it has produced false readings in
     this repo before.

  8. THE VENDOR KEY ANSWERS. One session create against Composio, exactly the
     call `provider.ts #sessionId` makes, expecting 201 with a `session_id`. A
     key nobody has checked is the cheapest thing in this chain to be wrong and
     the most expensive to discover from a person's tap.

  9. SOMEBODY HAS ACTUALLY CONNECTED AN APP. Distinct owners with a
     `status='connected'` row on live D1. ZERO IS UNPROVEN, NOT RED, and that
     is deliberate: nobody having connected yet is not the same as the feature
     being broken, and a gate that cried failure on the day before launch would
     teach its reader to ignore it — which is how the ears went deaf for thirty
     hours next to a green scoreboard.

 11. SOMEBODY IS ACTUALLY BEING ASKED. The other half of the product, and the
     half that had no instrument at all until 2026-09-06: `connect_nudges` rows
     in state `asked` on live D1. It separates FOUR states that look identical
     from outside — no text arrived — and are four different repairs:
     the five-minute Cron Trigger is not registered (RED, nothing can ever be
     asked); nothing calls `installNudgeWiring` (RED, the sweep asks nobody);
     nobody is due (UNPROVEN, exactly leg 9's rule — a quiet night and a
     feature whose senses were never wired read the same, so it is not a pass);
     and asks are going out (GREEN).

     ONLY A ROW TURNS IT GREEN. The schedule and the wiring are read out of
     this checkout, which is a claim about a checkout and not about
     api.anticipy.ai — law 3, in the file that exists for law 3 — so they are
     used ONLY to explain a zero. A deployed Worker running older code reads
     identically from here; the rows are what tell the difference, because a
     row was written by the Worker that is actually running on a tick that
     actually fired.

THE THIRD STATE IS MANDATORY HERE, and it is copied from firmware_gate.py: exit
2 UNPROVEN is neither pass nor fail, and it belongs to anything that was
GENUINELY NOT MEASURED — the network refused, wrangler has no credentials, no
vendor key or owner credential was given, a downstream leg could not be
attempted because the leg above it is red. What it must never mean is "measured
and disappointing".

    0   every measurable leg passed
    1   RED — something we can SEE is broken
    2   UNPROVEN — a leg could not be measured. It does not pass.

THIS FILE NEVER PRINTS A NUMBER IT DID NOT MEASURE. Every count on the screen
came back from the live database, the live Worker or the live vendor in this
run; a leg that could not be asked prints the reason instead of a zero, because
a zero reads as evidence and an unasked question is not evidence.

HARNESS-LAWS LAW 1. Nothing here decides what anybody MEANT. It compares HTTP
status codes and verbs, the CSP header our own Worker mints, two sentences our
own Worker writes for two named cases, four table names, seven column values it
wrote itself, the target of an HTML attribute resolved as a URL, the length of a
JSON array, and one vendor status code. Law 1 permits deterministic gates by
name ("Measuring is not programming"), and there is no prose anywhere in this
file's inputs to misread — it never reads a message, a transcript or a person's
words. The one string it sends into the product, the catalog probe query, is not
an app name and is not matched against anything here: what it means is the
catalog's business, and all this file reads is whether an answer came back.

    python3 overnight/is_connect_live.py
    python3 overnight/is_connect_live.py --read-only     # leg 4 not attempted
    python3 overnight/is_connect_live.py --self-test     # offline, no network

Read-only apart from leg 4, whose one row is described above.

CREDENTIALS COME FROM THE ENVIRONMENT, NEVER FROM ARGV. `ANTICIPY_CONNECT_PROBE_
CREDENTIAL` (or `ANTICIPY_OWNER_TOKEN`) is the owner auth token leg 3 asks with;
a secret on a command line is a secret in `ps`, in a shell history and in every
CI log that echoes its own command.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import base64
import hashlib
import hmac
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
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

#: The vendor's v3 root. The webhook subscription lives at
#: /api/v3/webhook_subscriptions — UNDERSCORE, not the hyphen the vendor's own
#: docs print, which 404s. Measured 2026-09-06.
COMPOSIO_BASE_V3 = "https://backend.composio.dev/api/v3"
SESSION_PATH = "/tool_router/session"

#: The vendor meta-tool that lets the MODEL start a connection on its own,
#: which in practice means pasting a raw `connect.composio.dev/...` link into a
#: text. `provider.ts MANAGE_CONNECTIONS_TOOL`, spelled the same way. An exact
#: identifier match against a vendor tool id — not a search for words inside a
#: description, and not a list of app names.
MANAGE_CONNECTIONS_TOOL = "COMPOSIO_MANAGE_CONNECTIONS"

#: `TOKEN_CHARS = 43` in connect.ts: 32 bytes of base64url, unpadded. The
#: probe token is well-formed ON PURPOSE — a malformed one would be refused by
#: `parseConnectPath` before the route ever ran, and leg 5 would then be
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

#: The router's own 404 body (src/pb/wire.ts `notFound`), compared with spaces
#: removed so a reformatted serialiser does not silently stop matching. This is
#: what an UNROUTED path answers, and every leg that asks "is this route on the
#: deployed Worker" is really asking whether it got this instead.
ROUTER_404_MARK = '"code":404'

# ---------------------------------------------------------------------------
# LEG 1 — the routes the phone calls
# ---------------------------------------------------------------------------

#: Every route in `CONNECTIONS_API_ROUTES`, with the verb each one takes, read
#: off that table and `METHOD` in routes/connections_api.ts — which are
#: themselves read off the `Route` enum in ConnectedAppsClient.swift. Three
#: books, and this is the one that asks production whether the middle book is
#: deployed.
#:
#: THE VERB MATTERS. `connectionsApiRoute` checks the method BEFORE it checks
#: the credential, so a GET on `/link` is a 405 with an `Allow` header and never
#: reaches the 401 this leg reads. Asking with the wrong verb would report four
#: deployed routes as unreadable.
#:
#: `skip` JOINED ON 2026-09-06 and is the reason this list is no longer called
#: "the six". Onboarding's Skip used to write a flag into UserDefaults ON THE
#: DEVICE, so a person's "no" never reached the ladder and the same person was
#: asked again from a second phone. A route that carries a refusal is exactly
#: the kind this leg must watch: it is invisible from the outside when it is
#: missing, because the failure it produces is another ask.
CONNECTIONS_ROUTES = (
    ("list", "GET", "/me/connections"),
    ("catalog", "GET", "/me/connections/catalog"),
    ("writes", "POST", "/me/connections/writes"),
    ("disconnect", "POST", "/me/connections/disconnect"),
    ("sentences", "POST", "/me/connections/sentences"),
    ("link", "POST", "/me/connections/link"),
    ("skip", "POST", "/me/connections/skip"),
)

#: THE CONTROL for leg 1. Not a route: index.ts hands `connectionsApiRoute` the
#: exact path `/me/connections` and the `/me/connections/` prefix, and this is
#: neither, so it must fall through to the router's generic 404. If it does not,
#: then a 401 is not evidence that anything is deployed and the leg says so.
CONNECTIONS_CONTROL_PATH = "/me/connectionsX"

#: `SIGN_IN_FIRST` in connections_api.ts, byte for byte. Paired with the
#: `{"ok":false}` envelope that file puts on every refusal, because the sentence
#: alone could in principle appear anywhere and the envelope alone is every
#: refusal it makes.
SIGN_IN_FIRST_MARK = "Sign in first."
REFUSAL_ENVELOPE_MARK = '"ok":false'

#: `NOT_A_ROUTE` in connections_api.ts — the answer for a path UNDER the prefix
#: that is not one of them. It means the file is deployed and its route table
#: disagrees with ours, which is a different repair from "the file is absent".
NOT_A_LEG_MARK = "There's nothing at this address."

# ---------------------------------------------------------------------------
# LEG 3 — the catalog
# ---------------------------------------------------------------------------

#: What leg 3 types into the search box.
#:
#: DELIBERATELY NOT AN APP NAME, and deliberately not a category either. The
#: product rule is that no app is hardcoded anywhere in this feature — names,
#: logos and search results come from the catalog at run time — and a gate that
#: probed with "gmail" would be the first file to break it, as well as being
#: wrong the day the catalog changes. One letter is the shortest thing a
#: substring search can be asked about and means nothing on its own.
#:
#: It only ever decides GREEN versus UNPROVEN: an answer of zero items is
#: reported as zero items with the query named, never as a broken catalog,
#: because what a catalog holds is not this file's to know. `--catalog-query`
#: overrides it for a reader who wants to ask for something in particular.
CATALOG_QUERY = "a"

#: `QUERY_SEARCH` in connections_api.ts. The catalog's other query name,
#: `slugs`, is not probed: it takes keys we already hold, and a person who has
#: connected nothing has none.
CATALOG_QUERY_NAME = "q"

#: The two environment names leg 3 will take an owner credential from. Nothing
#: else is read: the service token is not an owner credential, and a gate that
#: fell back to it would be measuring a door the phone never uses.
CREDENTIAL_ENV = ("ANTICIPY_CONNECT_PROBE_CREDENTIAL", "ANTICIPY_OWNER_TOKEN")

#: WHERE THAT CREDENTIAL MAY BE SENT, AND NOWHERE ELSE.
#:
#: Leg 3 is the only leg in this file that sends a secret anywhere, and `WORKER`
#: comes from an environment variable — `ANTICIPY_PB`, which pointed at a
#: different backend as recently as last week. A gate that posted an owner's auth
#: token to whatever host a variable happened to name would be a credential leak
#: with a scoreboard on it. Our zone, or the credential is not sent and the leg
#: says so; "not sent" is UNPROVEN, which is the honest reading.
CREDENTIAL_ZONE = "anticipy.ai"


def credential_may_be_sent(worker: str) -> bool:
    """Is this host ours? Exact zone or a subdomain of it, port ignored.

    A suffix test on the bare string would accept `evil-anticipy.ai`; the leading
    dot is what makes it a subdomain check rather than a substring one.
    """
    host = urllib.parse.urlsplit(worker).netloc.split("@")[-1].split(":")[0].lower()
    return host == CREDENTIAL_ZONE or host.endswith("." + CREDENTIAL_ZONE)

# ---------------------------------------------------------------------------
# LEG 7 — the way in
# ---------------------------------------------------------------------------

#: Every host a link of ours may point at. "Every link is ours": a control on
#: the connect page whose target is somebody else's host is not a way in, it is
#: a way out, and it fails this leg rather than passing it.
OUR_HOSTS = frozenset({
    urllib.parse.urlsplit(WORKER).netloc,
    "api.anticipy.ai", "anticipy.ai", "www.anticipy.ai",
})

#: The heading `/c/{token}/code` draws (`ASK_HEADING` in connect_auth.ts). Read
#: only to say what the control page WAS when the scan came back empty, so the
#: reader knows whether they are looking at the right page.
CODE_PAGE_MARK = "Get a code by text"

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
# LEG 1 — the API routes, and the control that says a 401 means anything
# ===========================================================================

def classify_connections_response(status: int, headers: dict, body: str) -> tuple[str, str]:
    """What did the live Worker just answer for a /me/connections path?

    Returns (kind, detail). Six kinds, because six different people fix them:

      refused        connections_api.ts answered. 401, its own `{ok:false}`
                     envelope, its own "Sign in first." This is the route being
                     THERE — the only thing an anonymous caller can prove.
      route-missing  the router's generic notFound(). The file is not on this
                     Worker, or index.ts does not hand it this prefix.
      not-a-leg      the prefix IS routed and this path is not one of them:
                     connections_api.ts's own "There's nothing at this address."
                     The file is deployed and its route table disagrees with
                     ours.
      wrong-method   405. The verb tables disagree; the route exists.
      answered       2xx WITHOUT a credential. Nothing anonymous may reach these
                     routes, so this is the loudest failure in the file.
      unreadable     something else answered — a proxy, an edge error, an origin
                     that is not this Worker. Measured nothing.
    """
    lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    ctype = lowered.get("content-type", "")
    body = body or ""
    compact = body.replace(" ", "")

    if status == 401 and SIGN_IN_FIRST_MARK in body and REFUSAL_ENVELOPE_MARK in compact:
        return "refused", f"401 — connections_api.ts's own \"{SIGN_IN_FIRST_MARK}\""
    if 200 <= status < 300:
        return "answered", (f"{status} — an anonymous caller got an ANSWER, not a "
                            "refusal")
    if status == 404 and "application/json" in ctype and ROUTER_404_MARK in compact:
        return "route-missing", (f"{status} application/json — the router's generic "
                                 "notFound(), which is what an unrouted path answers")
    if status == 404 and NOT_A_LEG_MARK in body:
        return "not-a-leg", (f"{status} — connections_api.ts is deployed and says this is "
                             f"not one of its routes (\"{NOT_A_LEG_MARK}\")")
    if status == 405:
        return "wrong-method", (f"{status} — the route is there and refused the verb this "
                                f"gate asked with (allow: {lowered.get('allow', 'unset')})")
    return "unreadable", (f"{status} {ctype or 'no content-type'} — neither a "
                          "connections_api.ts refusal nor the router's 404")


def leg_routes(results: list, control: tuple[str, str]) -> tuple[int, str, str]:
    """LEG 1. Is every route in `CONNECTIONS_ROUTES` on the deployed Worker?

    `results` is a list of (name, method, path, kind, detail); `control` is the
    (kind, detail) for `CONNECTIONS_CONTROL_PATH`.

    THE CONTROL IS CHECKED FIRST and it can only ever withhold green. A Worker
    that answered 401 to every path on earth would light all six of these up,
    and every one of them would be measuring the edge.
    """
    control_kind, control_detail = control
    names = {name: kind for name, _m, _p, kind, _d in results}

    answered = [n for n, k in names.items() if k == "answered"]
    if answered:
        return RED, BAD, (
            f"{', '.join(sorted(answered))} answered an ANONYMOUS caller with a 2xx. "
            "whoIsAsking() is not being consulted, or is not the first thing consulted: "
            "one person's connected accounts are readable by anybody with the URL")

    if control_kind != "route-missing":
        return UNPROVEN, INFO, (
            f"the control {CONNECTIONS_CONTROL_PATH} answered {control_detail}, and it is "
            "not a route on this Worker — so it should have been the router's generic 404. "
            "Until it is, a 401 on them proves nothing about whether they are deployed")

    broken = [f"{n} ({k})" for n, _m, _p, k, _d in results
              if k in ("route-missing", "not-a-leg", "wrong-method")]
    if broken:
        return RED, BAD, (
            f"{len(results) - len(broken)} of {len(results)} answer 401; BROKEN: "
            + ", ".join(broken)
            + ". The phone's Connected Apps screen calls every one of these and shows "
              "\"I couldn't read your connected apps\" for each that is not there")

    unreadable = [n for n, _m, _p, k, _d in results if k in ("unreadable", "unreachable")]
    if unreadable:
        return UNPROVEN, INFO, (
            f"{', '.join(sorted(unreadable))} answered something that is neither a "
            "connections_api.ts refusal nor the router's 404, so nothing is claimed about "
            "them either way")

    return GREEN, OK, (
        f"all {len(results)} answer 401 with connections_api.ts's own "
        f"\"{SIGN_IN_FIRST_MARK}\", and the control {CONNECTIONS_CONTROL_PATH} answers the "
        "router's generic 404 — so those 401s are these routes and not a blanket refusal")


# ===========================================================================
# LEG 3 — the catalog, which is how "Add an app" works
# ===========================================================================

def classify_api_json(status: int, headers: dict, body: str) -> dict:
    """One connections_api.ts answer, read structurally.

    `items` is the LENGTH of the `items` array or None if there is no array to
    count — never 0 as a stand-in for "could not tell", which is the exact shape
    this whole file exists to refuse. `message` is the sentence the Worker wrote
    for its own failure, carried through verbatim so a red leg can quote it
    rather than paraphrase it.
    """
    lowered = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    body = body or ""
    root = None
    if "application/json" in lowered.get("content-type", ""):
        try:
            root = json.loads(body)
        except ValueError:
            root = None
    items = None
    message = None
    if isinstance(root, dict):
        if isinstance(root.get("items"), list):
            items = len(root["items"])
        raw = root.get("message")
        if isinstance(raw, str) and raw:
            message = raw
    return {"status": status, "items": items, "message": message,
            "json": isinstance(root, dict)}


def leg_catalog(routes_code: int, credential: bool, control: dict | None,
                answer: dict | None, query: str) -> tuple[int, str, str]:
    """LEG 3. Does `?q=` come back with apps a person could pick from?

    `control` is the answer `GET /me/connections` gave to the SAME credential.
    Its only job is to decide whose fault a refusal is.
    """
    where = f"GET {CONNECTIONS_ROUTES[1][2]}?{CATALOG_QUERY_NAME}={query}"

    if routes_code != GREEN:
        return UNPROVEN, INFO, (
            "not attempted: leg 1 did not establish that these routes are deployed, and a "
            "catalog answer read over an undeployed route measures the router")
    if not credential:
        return UNPROVEN, INFO, (
            f"no owner credential in the environment ({' or '.join(CREDENTIAL_ENV)}), so "
            "the catalog was not asked. It CANNOT be asked without one: the route settles "
            "the credential before it builds a single dependency, so an anonymous caller "
            "sees 401 and never sees whether the search port behind it is filled")
    if control is None or answer is None:
        return UNPROVEN, INFO, (
            "the catalog could not be reached with that credential — a network, not a "
            "verdict about the catalog")
    if control["status"] == 401:
        return UNPROVEN, INFO, (
            f"the CONTROL {CONNECTIONS_ROUTES[0][2]} refused this environment's credential "
            "(401), so it is the credential that is stale, not the catalog. Nothing is "
            "claimed here; mint a fresh owner token and run this again")
    if control["status"] != 200 or control["items"] is None:
        return UNPROVEN, INFO, (
            f"the CONTROL {CONNECTIONS_ROUTES[0][2]} answered {control['status']}"
            + (f" \"{control['message']}\"" if control["message"] else "")
            + " instead of a list, so a catalog answer measured beside it would be "
              "measuring the same unknown twice")

    if answer["status"] == 200 and answer["items"] is not None:
        if answer["items"] > 0:
            return GREEN, OK, (
                f"{where} -> 200 with {answer['items']} item(s). The search box on Add an "
                "app has something to show, and the rows came from the catalog at run time")
        return UNPROVEN, INFO, (
            f"{where} -> 200 with 0 items. The search port answers, and nothing came back "
            f"for {query!r} — whether the catalog is empty or this probe word simply "
            "matches nothing there is not decidable from here. Ask for something in "
            "particular with --catalog-query")
    if answer["status"] == 200:
        return RED, BAD, (
            f"{where} -> 200 with no items array. ConnectedAppsClient reads row[\"items\"] "
            "and throws on anything else, so the screen shows a failure for a 200")
    if answer["json"] and answer["message"]:
        return RED, BAD, (
            f"{where} -> {answer['status']} \"{answer['message']}\". Add an app does not "
            "work: this is the route reporting its own failure. A 503 is either the "
            "ConnectionsApiDeps.search port unfilled on the deployed build or the catalog "
            "refusing to answer, and the body does not say which — `wrangler tail` does, "
            "in the log line searchCatalog writes for the unfilled case")
    return UNPROVEN, INFO, (
        f"{where} -> {answer['status']} with nothing readable in it, so nothing is claimed "
        "about the catalog")


# ===========================================================================
# LEG 5 + LEG 6 — the deployed page, and whether anything is wired to it
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
    if "application/json" in ctype and ROUTER_404_MARK in body.replace(" ", ""):
        return "route-missing", (f"{status} application/json — the router's generic "
                                 "notFound(), which is what an unrouted path answers")
    return "unreadable", (f"{status} {ctype or 'no content-type'} — neither a connect.ts "
                          "page nor the router's 404")


def leg_route(kind: str, detail: str, url: str) -> tuple[int, str, str]:
    """LEG 5. Does the deployed Worker serve /c/ at all?"""
    if kind in ("connect-page", "unwired"):
        return GREEN, OK, f"{url} -> {detail}"
    if kind == "route-missing":
        return RED, BAD, (f"{url} -> {detail}. routes/connect.ts is not on the "
                          "deployed Worker: every link in a text 404s")
    return UNPROVEN, INFO, (f"{url} -> {detail}; nothing about the route was "
                            "established")


def leg_wiring(kind: str, detail: str) -> tuple[int, str, str]:
    """LEG 6. Is anything wired to it?

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
    return UNPROVEN, INFO, ("not measurable while leg 5 is red — the route that would "
                            "answer 503 is not deployed, so the Worker cannot be "
                            "asked whether anything is wired to it")


# ===========================================================================
# LEG 7 — is there a way off the page a person actually lands on
# ===========================================================================

#: `href="…"` and `action="…"`, single or double quoted. HTML structure, not
#: prose: the value is then RESOLVED as a URL and compared to a path this file
#: built itself. Nothing here reads what a link SAYS.
_LINK_ATTR = re.compile(r"""(?:href|action)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)


def code_controls(page_url: str, html: str, token: str) -> list:
    """Every control on this page that starts the code flow for THIS token.

    Resolved against the page's own URL, so a relative `code`, an absolute
    `/c/{token}/code` and a fully qualified `https://api.anticipy.ai/c/{token}/
    code` all count as the same thing — which is what a browser would do with
    them.

    A TARGET ON SOMEBODY ELSE'S HOST IS NOT A WAY IN. "Every link is ours": a
    button pointing off our hosts is not a control this leg will accept, and
    filtering by `OUR_HOSTS` is what makes that a measurement rather than a
    hope.
    """
    want = f"/c/{token}/code"
    found = []
    for double, single in _LINK_ATTR.findall(html or ""):
        raw = (double or single).strip()
        if not raw:
            continue
        target = urllib.parse.urljoin(page_url, raw)
        parts = urllib.parse.urlsplit(target)
        if parts.path == want and parts.netloc in OUR_HOSTS:
            found.append(target)
    return found


def leg_way_in(kind: str, status: int, page_url: str, body: str, token: str,
               control_url: str | None, control_body: str | None) -> tuple[int, str, str]:
    """LEG 7. Can the person who tapped the link get any further?

    `control_*` is `/c/{token}/code`, a page KNOWN to carry the control this
    scan looks for. If the scan comes back empty there, the scan is what broke.
    """
    if kind != "connect-page":
        return UNPROVEN, INFO, (
            "not attempted: leg 5 did not get a connect.ts page back, so there is no page "
            "to look at")
    if status != 401:
        return UNPROVEN, INFO, (
            f"the page answered {status}, not the 401 sign-in page. This leg measures the "
            "one page a signed-out person actually lands on, and that is not what came "
            "back")
    if control_url is None or control_body is None:
        return UNPROVEN, INFO, (
            f"the control page /c/<{TOKEN_CHARS} chars>/code could not be fetched, so an "
            "empty scan of the sign-in page would not be evidence of anything")
    if not code_controls(control_url, control_body, token):
        drew = "and it is not the code page either" if CODE_PAGE_MARK not in control_body \
            else "though it IS the code page"
        return UNPROVEN, INFO, (
            f"the scan found no control on /c/<{TOKEN_CHARS} chars>/code, a page whose own "
            f"form posts to exactly that path ({drew}). The SCAN is what failed here, not "
            "the sign-in page, and a red leg from a broken instrument is worse than no leg")

    controls = code_controls(page_url, body, token)
    if controls:
        return GREEN, OK, (
            f"the signed-out page carries {len(controls)} control(s) whose target resolves "
            f"to /c/<{TOKEN_CHARS} chars>/code on our own host — a person who taps the "
            "texted link can start the code flow from the page they land on")
    return RED, BAD, (
        # `len(body)` is what THIS gate received, which is not always what the
        # Worker wrote: measured 2026-09-06, Cloudflare's analytics beacon is
        # injected into the HTML for some callers and not others (1003 bytes to
        # curl, 1370 here). The count is offered as a sign of "a real page came
        # back", never as a byte-for-byte claim about connect.ts's output.
        f"the signed-out page is a DEAD END: {len(body)} bytes of HTML came back "
        "with no href and no form action anywhere in it that reaches "
        f"/c/<{TOKEN_CHARS} chars>/code. routes/connect_auth.ts serves that page and it "
        "works; refusalPage(\"sign-in-required\") in routes/connect.ts never mentions it, "
        "so the person is told to sign in in a browser and given nothing to tap")


# ===========================================================================
# LEG 2 — the four tables, on the live database
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
    this file was written, because the four tables did not exist on production.
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
    """LEG 2. All four, or say which are missing."""
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
# LEG 8 — the vendor key
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
    """LEG 8. 201 with a session id the WORKER would accept.

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
# LEG 9 — has anybody connected anything
# ===========================================================================

def leg_connected(owners: int | None, rows: int | None) -> tuple[int, str, str]:
    """LEG 9. Owners with a connected row on live D1.

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
# LEG 11 — is anybody actually being ASKED
# ===========================================================================

#: The five-minute Cron Trigger the connect ask is dispatched on. src/cron.ts
#: switches on this LITERAL STRING, so the text here is the routing key and not
#: a description of one — a schedule spelled differently in wrangler.jsonc is a
#: leg dispatched by code production never invokes.
ASK_CRON = "*/5 * * * *"

#: The line in src/cron.ts that gives `connectNudgeSweep` a `NudgeDeps`. With
#: no caller the sweep logs "no wiring installed; nobody was asked anything" on
#: every tick — which is the exact shape `installConnectWiring` was in on
#: 2026-09-05, when every /c/ leg answered 503 to every token there had ever
#: been while five tested modules sat behind it.
WIRING_CALL = "installNudgeWiring(nudgeWiring)"

#: The two `app_usage_signals.source` values due.ts turns into a MOMENT
#: (`MOMENT_TRIGGER` in that file, and it is the whole of it). The other four —
#: mx, link, connected, asked — add weight and cannot name the moment an ask
#: opens with, so a table full of them is a table that produces no ask. Reading
#: this wrong is how a full table gets mistaken for a working feature.
MOMENT_SOURCES = ("observer", "said")

#: `GLOBAL_ASK_INTERVAL_DAYS` in src/connections/nudge.ts: one ask per owner per
#: seven days, across all apps. The candidate count below mirrors that cap, so
#: it counts owners the policy could actually be handed rather than rows.
GLOBAL_ASK_INTERVAL_DAYS = 7

# ---------------------------------------------------------------------------
# THE DUE COUNT — read out of due.ts, never mirrored
# ---------------------------------------------------------------------------
#
# WHAT USED TO BE HERE, AND WHY IT IS GONE. This constant was a hand-written
# copy of `candidateSql()` in src/connections/due.ts — "the same three NOT
# EXISTS clauses, the same `weight > 0`, the same one-row-per-owner rule". On
# 2026-09-06 due.ts deleted the weight predicate (it could never be false; the
# stored column only ever rises) and replaced `WHERE "pick" = 1` with a
# per-owner row budget. The copy here did not move. The one leg every fixer
# names as the law-3 proof was therefore counting owners against a shape the
# shipped code had stopped having.
#
# THE DRIFT CHECK THAT WAS SUPPOSED TO CATCH IT DID NOT, and that is the part
# worth writing down. tests/test_is_connect_live.py asserted each clause was in
# BOTH books — but it asked `clause in due_ts`, over the WHOLE FILE, and due.ts
# still carries the sentence "This file used to write `AND s.\"weight\" > 0`
# and call that the aliveness test". A substring check over a source file
# cannot tell code from prose, so the book that had changed read as agreeing,
# in the exact words of its own changelog.
#
# SO THE MIRROR IS GONE RATHER THAN RE-TIGHTENED, and the argument is not only
# that mirrors drift. A faithful mirror is now IMPOSSIBLE: due.ts's aliveness
# test is `decayedWeight(...) > ALIVE_WEIGHT_FLOOR`, an exponential, applied in
# TypeScript AFTER the statement returns, and due.ts's own header refuses to
# put a second copy of it in SQL because "SQLite has no exponential". Any SQL
# this gate writes is a query the code does not run. What the gate CAN do
# exactly is run due.ts's OWN statement, and that is what it does: the text
# below is lifted out of the file, its placeholders are bound BY NAME, and a
# rename or a failed read makes the leg UNPROVEN instead of wrong.
#
# WHAT THE NUMBER IS, STATED HONESTLY. It is not `due()`. It is the count of
# owners due.ts's statement HANDS to `dueCandidates`, and everything that
# function does afterwards — the owner-id check, the empty-toolkit drop, the
# source-names-no-moment drop, the decayed-weight floor, the one-per-owner
# dedupe, the cap — can only REMOVE owners. So it is an exact UPPER BOUND, and
# the direction matters:
#
#   zero here PROVES nobody is due. `due() <= 0` is `due() == 0`, so the quiet
#   night this leg reports today is now proven rather than asserted.
#   above zero does NOT prove somebody is due — every one of those owners could
#   be carrying evidence that has decayed under the floor. That is the one
#   thing this gate cannot see, and leg 11's red says so in its own sentence
#   rather than sending a reader to look for a break that is not there.

#: The one file the statement comes from, and the anchor it is found by. The
#: anchor is asserted UNIQUE before anything is cut out of it: a regex that
#: silently matched nothing would leave this gate reporting UNPROVEN forever
#: while production ran fine, and a broken instrument reads exactly like a
#: broken product.
DUE_TS_PATH = ("migration", "workers", "src", "connections", "due.ts")
DUE_SQL_ANCHOR = "function candidateSql(): string {"

#: `MOMENT_TRIGGER` in due.ts, found the same way. Read so the gate can REFUSE
#: when its own `MOMENT_SOURCES` disagrees with the file's, rather than binding
#: a short `IN (…)` list and quietly counting fewer owners than the code does.
MOMENT_TRIGGER_ANCHOR = 'export const MOMENT_TRIGGER: Readonly<Record<string, NudgeTrigger>>'

#: How many of one owner's rows the gate asks the statement for. ONE, where
#: due.ts binds `SIGNAL_ROWS_PER_OWNER`, and the difference changes nothing
#: this leg reads: the count below is over DISTINCT `user_id`, and an owner
#: with any candidate row at all has a `pick = 1` row. Asking for one row per
#: owner instead of five simply means the cap below bounds OWNERS rather than
#: rows, which is the number the leg prints.
DUE_ROWS_PER_OWNER = 1

#: The gate's own bound on one read against production, and it is the gate's,
#: not due.ts's. The leg's verdict is zero-versus-not-zero, which no cap can
#: change; the cap only bounds how large a number the sentence can print, and
#: it is stated so nobody reads "500 owners" as "exactly 500 owners".
DUE_COUNT_CAP = 500


def _read_or_none(path: str) -> str | None:
    """A file's text, or `None` when this checkout cannot produce it. `None`
    is a claim about the checkout and never about production, and every caller
    turns it into UNPROVEN rather than into a verdict."""
    try:
        return open(path, encoding="utf-8").read()
    except OSError:
        return None


def due_statement(source: str | None) -> str | None:
    """The SQL text `candidateSql()` returns, cut out of due.ts's source.

    NOT PARSED — LIFTED. Everything between the anchor's `return `` ` `` and the
    backtick that closes it, exactly as the file has it, placeholders and all.
    `None` means the shape this reader knows is not there any more, and every
    caller turns that into UNPROVEN.
    """
    if not source or source.count(DUE_SQL_ANCHOR) != 1:
        return None
    body = source.split(DUE_SQL_ANCHOR, 1)[1]
    opened = body.find("return `")
    if opened < 0:
        return None
    rest = body[opened + len("return `"):]
    closed = rest.find("`")
    if closed < 0:
        return None
    statement = rest[:closed]
    return statement if statement.strip() else None


def due_moment_sources(source: str | None) -> tuple[str, ...] | None:
    """The KEYS of due.ts's `MOMENT_TRIGGER`, in the order it declares them.

    The keys and not the values: the value is the `NudgeTrigger` an ask opens
    with, and this gate never renders one. The key is the `app_usage_signals`
    source the statement's `IN (…)` list is built from, which is the only half
    a count can be wrong about.
    """
    if not source or source.count(MOMENT_TRIGGER_ANCHOR) != 1:
        return None
    body = source.split(MOMENT_TRIGGER_ANCHOR, 1)[1]
    end = body.find("});")
    if end < 0:
        return None
    found = re.findall(r'(?m)^\s*(\w+)\s*:\s*"', body[:end])
    return tuple(found) if found else None


def bind_due_statement(statement: str | None, *, sources: tuple[str, ...],
                       now_ms: int, cutoff_ms: int,
                       rows_per_owner: int = DUE_ROWS_PER_OWNER,
                       cap: int = DUE_COUNT_CAP) -> str | None:
    """due.ts's statement with its own placeholders filled in, BY NAME.

    due.ts writes `?${pNow}`, `?${pCutoff}`, `?${pRows}`, `?${pCap}` and
    `${inList}`, and the names are what this binds against — never the ORDER of
    the `.bind(...)` call, because an order is a second thing to keep in step
    and this file has just finished paying for one of those. A name this
    function does not know, or a placeholder left behind, returns `None`: the
    leg would rather say "who is due could not be counted" than run a statement
    it does not fully understand against production.
    """
    if not statement:
        return None
    values = {
        "inList": ", ".join("'%s'" % s for s in sources),
        "pNow": str(int(now_ms)),
        "pCutoff": str(int(cutoff_ms)),
        "pRows": str(int(rows_per_owner)),
        "pCap": str(int(cap)),
    }
    unknown: list[str] = []

    def fill(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in values:
            unknown.append(name)
            return match.group(0)
        return values[name]

    bound = re.sub(r"\?\$\{(\w+)\}", fill, statement)
    bound = re.sub(r"\$\{(\w+)\}", fill, bound)
    if unknown or "${" in bound or re.search(r"\?\d", bound):
        return None
    return bound


def due_count_sql(now_ms: int, root: str = ROOT, source: str | None = None,
                  rows_per_owner: int = DUE_ROWS_PER_OWNER) -> str | None:
    """The whole statement leg 11 runs, or `None` if it cannot be built.

    THE COUNT IS OVER DISTINCT OWNERS, because that is what the 7-day global
    cap makes a candidate: `dueCandidates` keeps one per owner and the sweep
    could not send a second ask in the same week anyway.

    `rows_per_owner` IS A TEST SEAM AND NOT A TUNABLE. The answer must not
    depend on it — that is the whole claim `DUE_ROWS_PER_OWNER` rests on — so
    the local-D1 proof runs the same seed at 1 and at 5 and compares.

    THE THREE BOOKS ARE COMPARED HERE, not only in the self-test: if due.ts's
    `MOMENT_TRIGGER` no longer names exactly `MOMENT_SOURCES`, this refuses.
    Binding the gate's shorter list would count fewer owners than the code
    considers and print the difference as a quiet night.
    """
    if source is None:
        source = _read_or_none(_os.path.join(root, *DUE_TS_PATH))
    if due_moment_sources(source) != MOMENT_SOURCES:
        return None
    cutoff = int(now_ms) - GLOBAL_ASK_INTERVAL_DAYS * 86_400_000
    bound = bind_due_statement(due_statement(source), sources=MOMENT_SOURCES,
                               now_ms=int(now_ms), cutoff_ms=cutoff,
                               rows_per_owner=rows_per_owner)
    if bound is None:
        return None
    return ('SELECT count(*) AS due_n FROM (SELECT DISTINCT "user_id" FROM ('
            + bound + "))")

#: Every ask this backend has ever sent, and when the newest one went.
ASKED_SQL = ('SELECT count(*) AS asked_n, max("sent_at") AS newest '
             'FROM "connect_nudges" WHERE "state" = \'asked\' AND "sent_at" IS NOT NULL')


def ask_config(root: str = ROOT) -> tuple[bool | None, bool | None]:
    """(is the tick registered, is the wiring installed) — from the REPO.

    THESE ARE CONFIG FACTS AND THIS FUNCTION SAYS SO. `wrangler.jsonc` is what a
    deploy WOULD carry and `src/cron.ts` is what it would run; neither is
    evidence about `api.anticipy.ai`, and HARNESS-LAWS law 3 is explicit that
    repo-green means nothing. So they are used ONLY to explain a zero — the leg
    cannot go green on them, and the only thing that turns it green is rows the
    deployed Worker wrote.

    They are read rather than assumed because the two zeros they explain are
    completely different repairs: "add a line to a config file" and "wait for
    somebody to use an app".

    `None` from either is an unreadable file, which is a claim about this
    checkout and not about the product.
    """
    base = _os.path.join(root, "migration", "workers")
    try:
        wrangler = open(_os.path.join(base, "wrangler.jsonc"), encoding="utf-8").read()
    except OSError:
        wrangler = None
    try:
        cron = open(_os.path.join(base, "src", "cron.ts"), encoding="utf-8").read()
    except OSError:
        cron = None
    registered = None
    if wrangler is not None:
        found = re.search(r'"crons"\s*:\s*\[([^\]]*)\]', wrangler)
        registered = bool(found) and ('"%s"' % ASK_CRON) in found.group(1)
    wired = None if cron is None else (WIRING_CALL in cron)
    return registered, wired


#: THE STATES LEG 11 CAN BE IN, as names rather than as a shape a reader has to
#: derive from a wall of prose. They are exported in this literal form because
#: test/connections-endtoend.test.ts pins them: that suite proves the chain in
#: the repo and this leg proves it on production, and a leg that quietly lost a
#: state would leave the repo half claiming an instrument that no longer exists.
ASK_STATES = (
    "asking",              # GREEN     rows on live D1
    "cron-unregistered",   # RED       the tick is not registered
    "unwired",             # RED       installNudgeWiring has no caller
    "nobody-due",          # UNPROVEN  a quiet night, or senses nobody wired
    "due-but-silent",      # RED       owners are due and no ask ever went
    "due-unknown",         # UNPROVEN  the due query could not be run
    "unreadable",          # UNPROVEN  connect_nudges could not be counted
)


def ask_state(registered: bool | None, wired: bool | None,
              due: int | None, asked: int | None) -> str:
    """Which of `ASK_STATES` this deployment is in.

    SPLIT OUT FROM THE SENTENCE ON PURPOSE. The verdict and the paragraph that
    explains it are two different things, and a self-test that has to match a
    substring of the paragraph goes red the day somebody improves the wording —
    which teaches the next person to loosen the check rather than read it.

    THE ORDER IS THE VERDICT. `asked > 0` wins over everything, including a
    config file that says the schedule is missing: rows on live D1 were written
    by the Worker that is actually running, and a checkout that disagrees with
    them is the checkout being wrong. Config beats the due count for the
    opposite reason — a missing schedule makes every hop below it unreachable,
    so reporting "nobody is due" there would name the wrong repair.
    """
    if asked is None:
        return "unreadable"
    if asked > 0:
        return "asking"
    if registered is False:
        return "cron-unregistered"
    if wired is False:
        return "unwired"
    if due is None:
        return "due-unknown"
    if due == 0:
        return "nobody-due"
    return "due-but-silent"


def leg_ask(registered: bool | None, wired: bool | None, due: int | None,
            asked: int | None, newest_ms: float | None,
            now_ms: int) -> tuple[int, str, str]:
    """LEG 11. Is the connect ask reaching anybody, and if not, WHICH hop.

    FOUR STATES, AND THEY ARE FOUR DIFFERENT REPAIRS. Every one of them looks
    identical from outside — no text arrived — and telling them apart is the
    whole of this leg:

        the cron is not registered   a line in wrangler.jsonc. Nothing can
                                     EVER be asked; the sweep is dispatched by
                                     code production never invokes.  RED
        nothing is wired             `installNudgeWiring` has no caller, so the
                                     sweep runs and asks nobody.  RED
        nobody is due                due.ts's OWN statement, run against live
                                     D1, returns nobody. Everything the code
                                     does after that statement only removes
                                     candidates, so zero here is zero due —
                                     which is the correct state of a working
                                     feature on a quiet night, and also the
                                     state of a feature whose senses were never
                                     wired. Hence UNPROVEN and not green.
        asks are going out           `connect_nudges` holds `asked` rows on
                                     LIVE D1. Rows are the only proof that
                                     survives a stale deploy: they were written
                                     by the Worker that is actually running,
                                     on a tick that actually fired.  GREEN

    NOBODY-DUE IS UNPROVEN, THE SAME SHAPE AS LEG 9, and for the same reason:
    the day before the first person is asked, zero is the state of a working
    feature, and reporting it red trains the reader to skip the gate. A skipped
    gate is how the ears stayed deaf for thirty hours next to a green board.

    THE CONFIG HALF NEVER PRODUCES A GREEN. `registered` and `wired` come out
    of this checkout, not out of production, so they are read only to explain a
    zero. A deployed Worker running older code reads exactly the same from
    here, and the ask rows are what tell the difference.
    """
    state = ask_state(registered, wired, due, asked)
    if state == "unreadable":
        return UNPROVEN, INFO, ("connect_nudges could not be counted on live D1, so "
                                "nothing is claimed about whether anybody is being asked")
    if state == "asking":
        age = ""
        if newest_ms:
            days = (now_ms - float(newest_ms)) / 86_400_000.0
            age = (f", the newest {days:.1f} day(s) ago" if days >= 1
                   else f", the newest {max(0.0, days) * 24:.1f} hour(s) ago")
        return GREEN, OK, (f"asks are going out: {asked} `asked` row(s) on live D1{age}. "
                           "Those rows were written by the Worker that is actually "
                           "running, on a tick that actually fired — the whole chain from "
                           "a signal to a text is proven by their existence")

    # From here down the answer is "nobody has been asked", and the leg's job is
    # to say WHICH hop that is. Config first, because a missing schedule makes
    # every hop below it unreachable rather than merely quiet.
    if state == "cron-unregistered":
        return RED, BAD, (f"nobody has ever been asked, and wrangler.jsonc does not "
                          f"register {ASK_CRON!r} — the tick src/cron.ts dispatches the "
                          "connect ask on. Nothing can ever be asked: the sweep is code "
                          "production never invokes. Add the schedule and deploy")
    if state == "unwired":
        return RED, BAD, (f"nobody has ever been asked, and nothing calls {WIRING_CALL} — "
                          "so `connectNudgeSweep` logs that it asked nobody on every "
                          "tick. A tested part nothing calls is not a feature; this is "
                          "the shape `installConnectWiring` was in on 2026-09-05")
    if state == "due-unknown":
        return UNPROVEN, INFO, ("nobody has been asked, and who is DUE could not be "
                                "counted on live D1 — so it is not known whether that is "
                                "a quiet night or a broken chain")
    if state == "nobody-due":
        unknown_config = " (this checkout could not be read, so the schedule and the "\
                         "wiring were not checked either)" if registered is None else ""
        return UNPROVEN, INFO, (
            "nobody is due, so nobody has been asked. due.ts's own candidate statement, "
            "run against live D1, returns no owner at all — `app_usage_signals` holds no "
            f"{' or '.join(MOMENT_SOURCES)} row for anybody who has not already "
            "connected that app, been asked this week, or snoozed it. Everything the "
            "code does after that statement only DROPS candidates, so zero here is zero "
            "due. That is the correct state of a working feature on a quiet night AND "
            "the state of one whose senses were never wired, so it is not a pass. Of "
            "the six ingest doors in src/connections/signals.ts only the connected-apps "
            "sweep has a caller; the two that name a MOMENT — the browser hand's "
            "post-run host, and a model resolving the owner's own words — are what turn "
            "this green" + unknown_config)
    return RED, BAD, (f"at least {due} owner(s) are due to be asked and NOT ONE ask has ever "
                      f"been sent. The schedule is registered and the wiring has a caller, so "
                      "the break is below them: the moment could not be established (no "
                      "timezone on the profile), the writer's draft was refused, the link "
                      "could not be minted, or the send failed. `wrangler tail "
                      "anticipy-api` and read the `connect ask:` lines. THE ONE READING "
                      "THAT IS NOT A BREAK: that count is what due.ts's statement hands "
                      "`dueCandidates`, and the decayed-weight floor it applies afterwards "
                      "is an exponential no SQL this gate can write runs — so owners whose "
                      "evidence has all gone stale are counted here and dropped there")


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


def _http(url: str, method: str = "GET", headers: dict | None = None,
          timeout: int = 30, body: bytes | None = None) -> tuple[int, dict, str]:
    """One request, with exactly the headers the caller asked for.

    THE DEFAULT IS ANONYMOUS — no Authorization, no cookie — and every leg but
    the catalog uses that default. That is what makes legs 1, 5, 6 and 7 measure
    the DEPLOYMENT: a signed-out caller is answered before any store is touched,
    so those requests cannot read, spend or disturb anybody's link.

    `data=b""` on a POST so the request carries `Content-Length: 0` rather than
    no length at all; the four POST routes settle the credential before they
    read a body, so an empty one is refused without anything being written.
    """
    data = body if body is not None else (b"" if method == "POST" else None)
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, dict(res.headers), res.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), err.read().decode("utf-8", "replace")


def _credential() -> str:
    """The owner auth token leg 3 asks with, from the environment only.

    NEVER RETURNED TO THE SCREEN and never put on a command line. The gate
    prints whether one was found, not what it was.
    """
    for name in CREDENTIAL_ENV:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def run(*, read_only: bool = False, http=None, sql=None, vendor=None,
        owner: str | None = None, now_ms: int | None = None,
        credential: str | None = None, catalog_query: str | None = None,
        webhook=None) -> tuple[int, list]:
    """Every leg, in chain order. Returns (exit code, rows to print).

    The FOUR transports are injected so the whole gate is testable offline;
    `main()` supplies the real ones. `http` is called as
    `http(url, method=..., headers=..., body=...)`, and `webhook` as
    `webhook(api_key)` returning `(secret, subscription)` or None.
    """
    http = http or _http
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    query = catalog_query if catalog_query is not None else CATALOG_QUERY
    creds = _credential() if credential is None else credential
    rows: list[tuple[str, str, str]] = []
    codes: list[int] = []

    def ask(path: str, method: str = "GET", headers: dict | None = None,
            body: bytes | None = None):
        """One live request, or None if the request itself failed."""
        try:
            return http(f"{WORKER}{path}", method=method, headers=headers, body=body)
        except Exception:
            return None

    # -- leg 1: the API routes, plus the control -----------------------------
    route_results = []
    for name, method, path in CONNECTIONS_ROUTES:
        answer = ask(path, method)
        if answer is None:
            kind, detail = "unreachable", "the request failed"
        else:
            kind, detail = classify_connections_response(*answer)
        route_results.append((name, method, path, kind, detail))

    # THE CONTROL, asked last so a reader of a `wrangler tail` sees it next to
    # the routes it calibrates. It is a (kind, detail) pair like every other answer.
    got = ask(CONNECTIONS_CONTROL_PATH)
    control = ("unreachable", "the control request failed") if got is None \
        else classify_connections_response(*got)

    code, mark, sentence = leg_routes(route_results, control)
    routes_code = code
    codes.append(code)
    rows.append((mark, "1  THE /me/connections ROUTES EXIST", sentence))

    # -- leg 2: the four tables ----------------------------------------------
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
    rows.append((mark, "2  THE FOUR TABLES EXIST ON LIVE D1", sentence))

    # -- leg 3: the catalog ---------------------------------------------------
    control_answer = catalog_answer = None
    sendable = bool(creds) and credential_may_be_sent(WORKER)
    if routes_code == GREEN and sendable:
        auth = {"Authorization": creds}
        got = ask(CONNECTIONS_ROUTES[0][2], "GET", auth)
        control_answer = None if got is None else classify_api_json(*got)
        if control_answer is not None:
            asked = ask(
                CONNECTIONS_ROUTES[1][2] + "?"
                + urllib.parse.urlencode({CATALOG_QUERY_NAME: query}), "GET", auth)
            catalog_answer = None if asked is None else classify_api_json(*asked)
    if creds and not sendable:
        code, mark, sentence = UNPROVEN, INFO, (
            f"an owner credential is set and was NOT SENT: {WORKER} is not on "
            f"{CREDENTIAL_ZONE}. Point ANTICIPY_PB at our own zone and run this again; "
            "posting an owner's auth token to whatever host an environment variable "
            "happens to name is a credential leak, not a measurement")
    else:
        code, mark, sentence = leg_catalog(routes_code, sendable, control_answer,
                                           catalog_answer, query)
    codes.append(code)
    rows.append((mark, "3  THE CATALOG ANSWERS \"ADD AN APP\"", sentence))

    # -- leg 4: mint one link -------------------------------------------------
    if read_only:
        code, mark, sentence = UNPROVEN, INFO, (
            "--read-only: the one leg that writes was not attempted, so nothing is "
            "known about whether a minted row lands")
    elif not tables_known:
        code, mark, sentence = UNPROVEN, INFO, (
            "not attempted: live D1 could not be read at all (leg 2)")
    elif "connect_links" not in found:
        code, mark, sentence = UNPROVEN, INFO, (
            "not attempted: connect_links does not exist on live D1 (leg 2), so there is "
            "nothing to write a link into and nothing to measure")
    else:
        code, mark, sentence = mint_probe_link(sql, now_ms)
    codes.append(code)
    rows.append((mark, "4  A LINK CAN BE MINTED, AND ITS ROW LANDS", sentence))

    # -- legs 5, 6 and 7: one page, three questions ---------------------------
    token = probe_token()
    page_path = f"/c/{token}"
    page_url = f"{WORKER}{page_path}"
    shown = f"{WORKER}/c/<{TOKEN_CHARS} chars>"
    page = ask(page_path)
    if page is None:
        status, kind, detail, body = 0, "unreadable", "the request failed", ""
    else:
        status, headers, body = page
        kind, detail = classify_c_response(status, headers, body)

    code, mark, sentence = leg_route(kind, detail, shown)
    codes.append(code)
    rows.append((mark, "5  THE WORKER SERVES /c/", sentence))

    code, mark, sentence = leg_wiring(kind, detail)
    codes.append(code)
    rows.append((mark, "6  THE WIRING IS INSTALLED", sentence))

    control_url = control_body = None
    if kind == "connect-page":
        code_url = f"{page_url}/code"
        got = ask(f"{page_path}/code")
        if got is not None:
            control_url, control_body = code_url, got[2]
    code, mark, sentence = leg_way_in(kind, status, page_url, body, token,
                                      control_url, control_body)
    codes.append(code)
    rows.append((mark, "7  THE PAGE OFFERS A WAY IN", sentence))

    # -- leg 8: the vendor key ------------------------------------------------
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
    rows.append((mark, "8  THE VENDOR KEY ANSWERS", sentence))

    # -- leg 9: has anybody connected anything --------------------------------
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
    rows.append((mark, "9  SOMEBODY HAS ACTUALLY CONNECTED AN APP", sentence))

    # -- leg 10: the expiry webhook -------------------------------------------
    # Every request here is safe against production, repeatedly: the unsigned
    # and stale ones are refused before anything is read, and the signed one
    # names an account NO ROW HOLDS, so the handler's answer is a quiet 200 and
    # nothing is written. No owner is touched.
    unsigned_answer = ask(WEBHOOK_PATH, "POST",
                          {"content-type": "application/json"}, WEBHOOK_PROBE_BODY)
    unsigned_code = unsigned_answer[0] if unsigned_answer else None
    control_answer = ask(WEBHOOK_CONTROL_PATH, "POST",
                         {"content-type": "application/json"}, WEBHOOK_PROBE_BODY)
    control_code = control_answer[0] if control_answer else None

    signed_result = stale_code = None
    if unsigned_code == 403 and key:
        # NOT `found`. That name holds leg 2's set of live tables and every leg
        # below reads it; rebinding it here made leg 11's `"connect_nudges" in
        # found` a membership test against a webhook subscription, which throws
        # on the None case. Caught the day leg 11 was added, in 2026-09-06's own
        # test run — a shadow that had been harmless only because nothing had
        # yet read `found` after this point.
        try:
            subscription = (webhook or webhook_secret)(key)
        except VendorUnavailable:
            subscription = None
        if subscription:
            secret, _sub = subscription
            stamp = str(int((now_ms if now_ms else 0) / 1000) or int(time.time()))
            head = {"content-type": "application/json", "webhook-id": WEBHOOK_PROBE_ID,
                    "webhook-timestamp": stamp,
                    "webhook-signature": sign_webhook(secret, WEBHOOK_PROBE_ID, stamp,
                                                      WEBHOOK_PROBE_BODY)}
            got = ask(WEBHOOK_PATH, "POST", head, WEBHOOK_PROBE_BODY)
            if got:
                signed_result = (got[0], got[2])
            # The same body signed for a timestamp outside the window. If this
            # is accepted, a captured request can be replayed at leisure.
            old_stamp = str(int(stamp) - WEBHOOK_STALE_SECONDS)
            stale_head = {"content-type": "application/json",
                          "webhook-id": WEBHOOK_PROBE_ID, "webhook-timestamp": old_stamp,
                          "webhook-signature": sign_webhook(secret, WEBHOOK_PROBE_ID,
                                                            old_stamp, WEBHOOK_PROBE_BODY)}
            stale_answer = ask(WEBHOOK_PATH, "POST", stale_head, WEBHOOK_PROBE_BODY)
            stale_code = stale_answer[0] if stale_answer else None

    code, mark, sentence = leg_webhook(unsigned_code, control_code, signed_result, stale_code)
    codes.append(code)
    rows.append((mark, "10 THE EXPIRY WEBHOOK IS LIVE AND VERIFIES", sentence))

    # -- leg 11: is anybody actually being asked -------------------------------
    # THE ONE LEG THAT MEASURES THE OTHER HALF OF THE PRODUCT. Legs 1-10 all ask
    # whether somebody who WANTS to connect an app can. This asks whether
    # anything ever OFFERS — the half of the spec that was written, tested and
    # called by nothing.
    #
    # Two counts, both read-only, both bounded, both safe against production as
    # often as anybody likes: the owners `due()` would hand the policy, and the
    # asks this backend has ever sent.
    due_n = asked_n = newest = None
    if tables_known and "connect_nudges" in found:
        try:
            counted = sql(ASKED_SQL)
            if counted:
                asked_n = int(float(counted[0].get("asked_n", 0)))
                raw = counted[0].get("newest")
                newest = None if raw is None else float(raw)
        except (D1Unavailable, TypeError, ValueError, KeyError, IndexError):
            asked_n = newest = None
        if "app_usage_signals" in found and "connections" in found:
            # NOT A MIRROR — due.ts's own statement, read out of the file and
            # bound by name. A checkout this reader cannot make sense of leaves
            # `due_n` as None, which is `due-unknown`: the leg then says who is
            # due could not be counted instead of counting it wrong.
            statement = due_count_sql(now_ms)
            if statement is not None:
                try:
                    counted = sql(statement)
                    if counted:
                        due_n = int(float(counted[0].get("due_n", 0)))
                except (D1Unavailable, TypeError, ValueError, KeyError, IndexError):
                    due_n = None
    registered, wired = ask_config()
    code, mark, sentence = leg_ask(registered, wired, due_n, asked_n, newest, now_ms)
    codes.append(code)
    rows.append((mark, "11 SOMEBODY IS ACTUALLY BEING ASKED", sentence))

    return overall(codes), rows


# ===========================================================================
# SELF-TEST — the verdicts against shapes this system has actually had
# ===========================================================================

def _routes_all(kind: str) -> list:
    """Every route, all of them answering the same way."""
    return [(name, method, path, kind, kind) for name, method, path in CONNECTIONS_ROUTES]


#: The self-test's clock. Fixed, so a case that reads an AGE reads the same
#: sentence in June as it does in December.
NOW_FOR_SELF_TEST = 1_757_000_000_000


def _fake_due_ts(extra_predicate: str) -> str:
    """A due.ts-SHAPED source whose prose and whose statement disagree.

    This is the 2026-09-06 drift in miniature, and it is a fixture rather than a
    fixture file because the thing under test is a READER: the comment below
    quotes `AND s."weight" > 0` whatever `extra_predicate` is, so a check that
    greps the file agrees with itself while a check that reads the STATEMENT
    tells the truth. That difference is the whole finding.
    """
    return (
        ' * This file used to write `AND s."weight" > 0` and call that the aliveness\n'
        ' * test. IT WAS NEVER TRUE.\n'
        + MOMENT_TRIGGER_ANCHOR + " = Object.freeze({\n"
        + '  observer: "in_task",\n  said: "user_named_it",\n});\n'
        + DUE_SQL_ANCHOR + "\n"
        '  const inList = MOMENT_SOURCES.map((_, i) => `?${i + 1}`).join(", ");\n'
        "  return `\n"
        '    SELECT s."user_id" FROM "app_usage_signals" s\n'
        '     WHERE s."source" IN (${inList})\n'
        "       " + extra_predicate +
        '       AND s."last_seen_at" > ?${pCutoff}\n'
        "       AND ?${pNow} > 0`;\n"
        "}\n")


def self_test() -> int:
    """Offline. Pins each leg to a measured shape rather than to a guess."""
    cases = []

    # ---- LEG 1, from the live probe of 2026-09-06 --------------------------
    json_headers = {"content-type": "application/json; charset=utf-8"}
    live401 = (401, json_headers, '{"ok":false,"message":"Sign in first."}')
    live404 = (404, {"content-type": "application/json"},
               '{"code":404,"message":"The requested resource wasn\'t found.","data":{}}')
    live_not_a_leg = (404, json_headers,
                      '{"ok":false,"message":"There\'s nothing at this address."}')

    for answer, want, why in [
        (live401, "refused", "2026-09-06 LIVE: a deployed route refuses an anonymous caller"),
        (live404, "route-missing", "2026-09-06 LIVE: /me/connectionsX, the control"),
        (live_not_a_leg, "not-a-leg", "the prefix is routed and this path is not a leg"),
        ((405, {"allow": "POST"}, ""), "wrong-method", "the verb tables disagree"),
        ((200, json_headers, '{"items":[]}'), "answered",
         "an anonymous caller got an ANSWER"),
        ((502, {"content-type": "text/html"}, "<html>edge</html>"), "unreadable",
         "an edge error measures nothing"),
    ]:
        cases.append((f"leg1    {why}",
                      classify_connections_response(*answer)[0] == want))

    control_ok = ("route-missing", "the router's generic 404")
    cases.append(("leg1    2026-09-06 LIVE: 401s beside a generic-404 control is green",
                  leg_routes(_routes_all("refused"), control_ok)[0] == GREEN))
    cases.append(("leg1    one route missing is red and names it",
                  leg_routes([("list", "GET", "/me/connections", "route-missing", "")]
                             + _routes_all("refused")[1:], control_ok)[0] == RED))
    cases.append(("leg1    a missing route is NAMED, not counted",
                  "list" in leg_routes(
                      [("list", "GET", "/me/connections", "route-missing", "")]
                      + _routes_all("refused")[1:], control_ok)[2]))
    cases.append(("leg1    an anonymous 2xx is the loudest red there is",
                  leg_routes([("list", "GET", "/me/connections", "answered", "")]
                             + _routes_all("refused")[1:], control_ok)[0] == RED))
    cases.append(("leg1    THE CONTROL: a Worker that 401s everything proves nothing",
                  leg_routes(_routes_all("refused"), ("refused", "401"))[0] == UNPROVEN))
    cases.append(("leg1    an unreadable route withholds green without crying red",
                  leg_routes([("link", "POST", "/me/connections/link", "unreadable", "")]
                             + _routes_all("refused")[1:], control_ok)[0] == UNPROVEN))
    cases.append(("leg1    the paths are the ones connections_api.ts declares",
                  [p for _n, _m, p in CONNECTIONS_ROUTES] == [
                      "/me/connections", "/me/connections/catalog", "/me/connections/writes",
                      "/me/connections/disconnect", "/me/connections/sentences",
                      "/me/connections/link", "/me/connections/skip"]))

    # ---- LEG 3, the catalog ------------------------------------------------
    listed = {"status": 200, "items": 4, "message": None, "json": True}
    unfilled = {"status": 503, "items": None, "json": True,
                "message": "I couldn't look that up just now. Nothing has changed."}
    cases.append(("leg3    the unfilled search port is RED, not unproven",
                  leg_catalog(GREEN, True, listed, unfilled, "a")[0] == RED))
    cases.append(("leg3    and the 503's own sentence is QUOTED",
                  unfilled["message"] in leg_catalog(GREEN, True, listed, unfilled, "a")[2]))
    cases.append(("leg3    a filled port with rows is green",
                  leg_catalog(GREEN, True, listed,
                              {"status": 200, "items": 3, "message": None, "json": True},
                              "a")[0] == GREEN))
    cases.append(("leg3    a filled port with no rows claims nothing",
                  leg_catalog(GREEN, True, listed,
                              {"status": 200, "items": 0, "message": None, "json": True},
                              "a")[0] == UNPROVEN))
    cases.append(("leg3    no credential is UNPROVEN and names the variable",
                  leg_catalog(GREEN, False, None, None, "a")[0] == UNPROVEN
                  and CREDENTIAL_ENV[0] in leg_catalog(GREEN, False, None, None, "a")[2]))
    cases.append(("leg3    THE CONTROL: a refused credential is not a broken catalog",
                  leg_catalog(GREEN, True,
                              {"status": 401, "items": None, "json": True,
                               "message": "Sign in first."},
                              unfilled, "a")[0] == UNPROVEN))
    cases.append(("leg3    not attempted while leg 1 is not green",
                  leg_catalog(RED, True, listed, unfilled, "a")[0] == UNPROVEN))
    cases.append(("leg3    the items count is a LENGTH, never a stand-in for unknown",
                  classify_api_json(200, {"content-type": "application/json"},
                                    '{"items":[1,2,3]}')["items"] == 3
                  and classify_api_json(503, {"content-type": "application/json"},
                                        '{"ok":false,"message":"no"}')["items"] is None))
    cases.append(("leg3    the probe query is not an app name",
                  len(CATALOG_QUERY) <= 2))
    # The one secret this file ever sends. Our zone or nowhere, and a subdomain
    # check rather than a suffix one, because `evil-anticipy.ai` ends with the
    # zone and is not ours.
    for host, allowed in [("https://api.anticipy.ai", True),
                          ("https://anticipy.ai", True),
                          ("https://preview.workers.anticipy.ai:8443", True),
                          ("https://evil-anticipy.ai", False),
                          ("https://anticipy.ai.example.com", False),
                          ("http://localhost:8787", False),
                          ("https://anticipy-backend.up.railway.app", False)]:
        cases.append((f"leg3    the credential may {'' if allowed else 'NOT '}go to {host}",
                      credential_may_be_sent(host) is allowed))

    # ---- LEG 5 / LEG 6, and the two shapes the deployment can take ---------
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

    for status, (headers, body), want_kind, want5, want6, why in [
        (404, json404, "route-missing", RED, UNPROVEN,
         "2026-09-06 04:08: /c/ answered the router's JSON 404"),
        (401, page401, "connect-page", GREEN, GREEN,
         "2026-09-06 LIVE: the sign-in page a signed-out caller gets"),
        (503, page503, "unwired", GREEN, RED,
         "deployed, nothing wired: the Worker says so itself"),
        (502, ({"content-type": "text/html"}, "<html>edge error</html>"),
         "unreadable", UNPROVEN, UNPROVEN,
         "an edge error is not evidence about the route"),
    ]:
        kind, detail = classify_c_response(status, headers, body)
        cases.append((f"leg5/6  {why}", kind == want_kind
                      and leg_route(kind, detail, "u")[0] == want5
                      and leg_wiring(kind, detail)[0] == want6))

    # ---- LEG 7, the way in -------------------------------------------------
    tok = "A" * TOKEN_CHARS
    base = f"https://api.anticipy.ai/c/{tok}"
    # Measured 2026-09-06 06:17 UTC: the whole body of the signed-out page, minus
    # the stylesheet. There is no anchor and no form in it.
    dead_end = ("<body><h1>Sign in to finish</h1><p>Sign in to Anticipy in this browser, "
                "then open this link again. It works for ten minutes.</p></body>")
    # The control page, as connect_auth.ts draws it.
    code_page = (f"<body><h1>{CODE_PAGE_MARK}</h1>"
                 f"<form method=\"post\" action=\"/c/{tok}/code\">"
                 "<button type=\"submit\">Text me a code</button></form>"
                 "<a class=\"later\" href=\"https://anticipy.ai/\">Skip for now</a></body>")
    with_way_in = dead_end.replace("</body>", f"<a href=\"/c/{tok}/code\">Text me a code</a></body>")
    off_site = dead_end.replace("</body>", f"<a href=\"https://elsewhere.example/c/{tok}/code\">go</a></body>")

    cases.append(("leg7    2026-09-06 06:17: the dead-end page, measured, and it is RED",
                  leg_way_in("connect-page", 401, base, dead_end, tok,
                             f"{base}/code", code_page)[0] == RED))
    cases.append(("leg7    a page carrying the control is green",
                  leg_way_in("connect-page", 401, base, with_way_in, tok,
                             f"{base}/code", code_page)[0] == GREEN))
    cases.append(("leg7    a control pointing off our hosts is not a way in",
                  leg_way_in("connect-page", 401, base, off_site, tok,
                             f"{base}/code", code_page)[0] == RED))
    cases.append(("leg7    THE CONTROL: a scan that finds nothing on the code page is "
                  "UNPROVEN, not red",
                  leg_way_in("connect-page", 401, base, dead_end, tok,
                             f"{base}/code", "<body><h1>Get a code by text</h1></body>"
                             )[0] == UNPROVEN))
    cases.append(("leg7    not attempted when leg 5 got no page",
                  leg_way_in("route-missing", 404, base, "", tok, None, None)[0] == UNPROVEN))
    cases.append(("leg7    the relative form connect_auth.ts could use also counts",
                  code_controls(f"{base}/code", "<form action=\"code\"></form>", tok) != []))
    cases.append(("leg7    a link to the page itself is not a way in",
                  code_controls(base, f"<a href=\"/c/{tok}\">back</a>", tok) == []))

    # ---- LEG 2, from the live query of 2026-09-06 --------------------------
    cases.append(("leg2    2026-09-06 04:08: zero of four tables",
                  leg_tables(set(), "anticipy-backend")[0] == RED))
    cases.append(("leg2    all four present",
                  leg_tables(set(TABLES), "anticipy-backend")[0] == GREEN))
    cases.append(("leg2    one missing is named",
                  "connect_links" in leg_tables(set(TABLES) - {"connect_links"}, "d")[2]))

    # ---- LEG 4's refusal to write anything redeemable ----------------------
    now = 1_757_000_000_000
    good = _probe_row(now)
    cases.append(("leg4    the probe row is inert", probe_row_is_inert(good, now)[0]))
    cases.append(("leg4    a LIVE expiry is refused",
                  not probe_row_is_inert({**good, "expires_at": float(now + 600_000)}, now)[0]))
    cases.append(("leg4    a real owner id is refused",
                  not probe_row_is_inert({**good, "user_id": "sxkotd1h02qb6gw"}, now)[0]))
    cases.append(("leg4    a claimed row is refused",
                  not probe_row_is_inert({**good, "used_at": float(now)}, now)[0]))

    # ---- LEG 8, the first case being the vendor's own answer of 2026-09-06 --
    live201 = {"status": 201, "session_id_len": 16, "manage_connections": False,
               "connection_tool_present": False}
    cases.append(("leg8    2026-09-06 LIVE: 201, session id, connection tool off",
                  leg_vendor(live201)[0] == GREEN))
    cases.append(("leg8    201 with no session id is red",
                  leg_vendor({**live201, "session_id_len": 0})[0] == RED))
    cases.append(("leg8    401 is red",
                  leg_vendor({"status": 401, "session_id_len": 0,
                              "manage_connections": None,
                              "connection_tool_present": None})[0] == RED))
    cases.append(("leg8    the config saying manage_connections ON is red",
                  leg_vendor({**live201, "manage_connections": True})[0] == RED))
    cases.append(("leg8    the connection tool still in the list is red",
                  leg_vendor({**live201, "connection_tool_present": True})[0] == RED))
    cases.append(("leg8    an answer confirming NEITHER is red, not green",
                  leg_vendor({**live201, "manage_connections": None,
                              "connection_tool_present": None})[0] == RED))
    cases.append(("leg8    one half confirming is enough, as in provider.ts",
                  leg_vendor({**live201, "manage_connections": None})[0] == GREEN))
    # The parser reads the two fields where the vendor actually puts them —
    # `config.manage_connections`, not a top-level key. Pinned because reading
    # the wrong place answers None and the leg above turns that into a refusal.
    body = json.dumps({"session_id": "ts_abc123", "config": {
        "manage_connections": {"enabled": False}},
        "tool_router_tools": ["COMPOSIO_SEARCH_TOOLS"]})
    parsed = _vendor_answer(201, body)
    cases.append(("leg8    manage_connections is read from config, not the root",
                  parsed["manage_connections"] is False
                  and parsed["connection_tool_present"] is False
                  and parsed["session_id_len"] == 9))

    # ---- LEG 9 — the whole reason the third state exists -------------------
    cases.append(("leg9    zero connections is UNPROVEN, never red",
                  leg_connected(0, 0)[0] == UNPROVEN))
    cases.append(("leg9    one owner connected is green",
                  leg_connected(1, 2)[0] == GREEN))
    cases.append(("leg9    an uncountable table is UNPROVEN",
                  leg_connected(None, None)[0] == UNPROVEN))

    # ---- LEG 10 — every state the webhook has actually been in -------------
    # The first two are not hypotheses: both were MEASURED on 2026-09-06,
    # either side of `wrangler secret put`, in that order.
    ok200 = (200, '{"ok":true,"ignored":"no such connection"}')
    cases.append(("leg10   404 is red — the route is not deployed",
                  leg_webhook(404, 404, None, None)[0] == RED))
    cases.append(("leg10   503 is red — deployed, but no secret, so every expiry is dropped",
                  leg_webhook(503, 404, None, None)[0] == RED))
    cases.append(("leg10   403 with no signed probe is UNPROVEN, never green",
                  leg_webhook(403, 404, None, None)[0] == UNPROVEN))
    cases.append(("leg10   403 that the CONTROL also gives is UNPROVEN — that is the zone",
                  leg_webhook(403, 403, ok200, 403)[0] == UNPROVEN))
    cases.append(("leg10   an unsigned event ACCEPTED is red",
                  leg_webhook(200, 404, None, None)[0] == RED))
    cases.append(("leg10   a correctly signed event refused is red — wrong secret deployed",
                  leg_webhook(403, 404, (403, '{"ok":false}'), 403)[0] == RED))
    cases.append(("leg10   200 that does not say it ignored the account is red",
                  leg_webhook(403, 404, (200, '{"ok":true}'), 403)[0] == RED))
    cases.append(("leg10   a stale event ACCEPTED is red — a capture can be replayed",
                  leg_webhook(403, 404, ok200, 200)[0] == RED))
    cases.append(("leg10   unreachable is UNPROVEN, not a verdict",
                  leg_webhook(None, None, None, None)[0] == UNPROVEN))
    cases.append(("leg10   the live shape of 2026-09-06 is green",
                  leg_webhook(403, 404, ok200, 403)[0] == GREEN))
    # The signer must mirror webhookKeyBytes, not invent a rule. A whsec_
    # secret keys with its DECODED bytes; anything else with its own UTF-8.
    cases.append(("leg10   a whsec_ secret signs with decoded bytes",
                  sign_webhook("whsec_" + base64.b64encode(b"key").decode(), "i", "1", b"{}")
                  == "v1," + base64.b64encode(hmac.new(
                      b"key", b"i.1.{}", hashlib.sha256).digest()).decode()))
    cases.append(("leg10   a plain secret signs with its own bytes",
                  sign_webhook("plainsecret", "i", "1", b"{}")
                  == "v1," + base64.b64encode(hmac.new(
                      b"plainsecret", b"i.1.{}", hashlib.sha256).digest()).decode()))
    cases.append(("leg10   the probe names an account no owner could hold",
                  WEBHOOK_PROBE_ACCOUNT.startswith("ca_gate_probe")
                  and PROBE_OWNER in WEBHOOK_PROBE_BODY.decode()))

    # ---- LEG 11 — the four states, and the one that must not be green ------
    # A row on live D1 beats every config fact there is, because a row is what
    # the RUNNING Worker wrote. The rest is the diagnosis of a zero.
    cases.append(("leg11   an `asked` row on live D1 is green — the chain ran end to end",
                  leg_ask(True, True, 0, 1, float(NOW_FOR_SELF_TEST - 3600_000),
                          NOW_FOR_SELF_TEST)[0] == GREEN))
    cases.append(("leg11   and green says how long ago the newest ask went",
                  "hour(s) ago" in leg_ask(True, True, 0, 1,
                                           float(NOW_FOR_SELF_TEST - 3600_000),
                                           NOW_FOR_SELF_TEST)[2]))
    cases.append(("leg11   rows beat a checkout that says the schedule is missing",
                  leg_ask(False, False, 0, 1, None, NOW_FOR_SELF_TEST)[0] == GREEN))
    cases.append(("leg11   2026-09-06 MEASURED: zero signals, zero asks -> UNPROVEN",
                  leg_ask(True, True, 0, 0, None, NOW_FOR_SELF_TEST)[0] == UNPROVEN))
    cases.append(("leg11   nobody-due is UNPROVEN, never green — the leg 9 rule",
                  ask_state(True, True, 0, 0) == "nobody-due"
                  and leg_ask(True, True, 0, 0, None, NOW_FOR_SELF_TEST)[0] != GREEN))
    cases.append(("leg11   and nobody-due NAMES the two doors that would turn it green",
                  all(w in leg_ask(True, True, 0, 0, None, NOW_FOR_SELF_TEST)[2]
                      for w in ("observer", "said", "signals.ts"))))
    cases.append(("leg11   an unregistered cron is RED, and it is not the same as quiet",
                  leg_ask(False, True, 0, 0, None, NOW_FOR_SELF_TEST)[0] == RED
                  and ASK_CRON in leg_ask(False, True, 0, 0, None, NOW_FOR_SELF_TEST)[2]))
    cases.append(("leg11   nothing wired is RED, and it names the call that is missing",
                  leg_ask(True, False, 0, 0, None, NOW_FOR_SELF_TEST)[0] == RED
                  and WIRING_CALL in leg_ask(True, False, 0, 0, None, NOW_FOR_SELF_TEST)[2]))
    cases.append(("leg11   the schedule is diagnosed BEFORE the due count",
                  ask_state(False, True, 7, 0) == "cron-unregistered"))
    cases.append(("leg11   owners due and no ask ever sent is RED, and counts them",
                  leg_ask(True, True, 4, 0, None, NOW_FOR_SELF_TEST)[0] == RED
                  and "4 owner(s)" in leg_ask(True, True, 4, 0, None,
                                              NOW_FOR_SELF_TEST)[2]))
    cases.append(("leg11   an uncountable connect_nudges is UNPROVEN, not a verdict",
                  leg_ask(True, True, 5, None, None, NOW_FOR_SELF_TEST)[0] == UNPROVEN))
    cases.append(("leg11   and it is not the same UNPROVEN as a quiet night",
                  ask_state(True, True, 0, None) == "unreadable"
                  and "could not be counted"
                  in leg_ask(True, True, 0, None, None, NOW_FOR_SELF_TEST)[2]))
    cases.append(("leg11   an uncountable due query is UNPROVEN and says which half",
                  leg_ask(True, True, None, 0, None, NOW_FOR_SELF_TEST)[0] == UNPROVEN
                  and "who is DUE" in leg_ask(True, True, None, 0, None,
                                              NOW_FOR_SELF_TEST)[2]))
    cases.append(("leg11   an unreadable checkout is UNPROVEN and admits it read nothing",
                  leg_ask(None, None, 0, 0, None, NOW_FOR_SELF_TEST)[0] == UNPROVEN
                  and "could not be read" in leg_ask(None, None, 0, 0, None,
                                                     NOW_FOR_SELF_TEST)[2]))
    cases.append(("leg11   every state ask_state can return is one of ASK_STATES",
                  all(ask_state(*a) in ASK_STATES for a in [
                      (True, True, 0, 1), (True, True, 0, 0), (False, True, 0, 0),
                      (True, False, 0, 0), (True, True, 3, 0), (True, True, None, 0),
                      (True, True, 0, None), (None, None, None, None)])))
    # ---- LEG 11's DUE COUNT — the mirror that drifted, and its replacement --
    # On 2026-09-06 the hand-written copy of due.ts's candidate query still
    # carried `AND s."weight" > 0` and `WHERE "pick" = 1`, months after due.ts
    # deleted the first and replaced the second. The check that was supposed to
    # notice asked `clause in due_ts` over the WHOLE FILE, and due.ts still
    # carries the sentence that quotes the predicate it deleted — so the drift
    # read as agreement, in the words of its own changelog. There is no copy
    # any more: the gate runs due.ts's own text. These cases are what keep that
    # true, and every one of them fails if the two ever become two again.
    _due_src = _read_or_none(_os.path.join(ROOT, *DUE_TS_PATH))
    _nudge_src = _read_or_none(_os.path.join(
        ROOT, "migration", "workers", "src", "connections", "nudge.ts"))
    cases.append(("leg11   THE INSTRUMENT: due.ts's own statement is still readable",
                  due_statement(_due_src) is not None))
    cases.append(("leg11   THE INSTRUMENT: due.ts's MOMENT_TRIGGER still names ours",
                  due_moment_sources(_due_src) == MOMENT_SOURCES))
    cases.append(("leg11   THE INSTRUMENT: nudge.ts still caps asks at one per 7 days",
                  "export const GLOBAL_ASK_INTERVAL_DAYS = %d;" % GLOBAL_ASK_INTERVAL_DAYS
                  in (_nudge_src or "")))
    _live_due = due_count_sql(NOW_FOR_SELF_TEST)
    cases.append(("leg11   the statement it runs is fully bound and counts owners",
                  _live_due is not None and "${" not in _live_due
                  and not re.search(r"\?\d", _live_due)
                  and 'count(*) AS due_n' in _live_due
                  and 'SELECT DISTINCT "user_id"' in _live_due
                  and str(NOW_FOR_SELF_TEST) in _live_due))
    # THE CONTROL THAT MATTERS: the statement pointed at production is due.ts's
    # own text, character for character, with only its placeholders filled. A
    # scan of this file for the mirror's clauses would be defeated by the very
    # comment explaining them, so the check is on the SQL, not on the source.
    cases.append(("leg11   THE CONTROL: the statement run on production IS due.ts's text",
                  _live_due is not None and bind_due_statement(
                      due_statement(_due_src), sources=MOMENT_SOURCES,
                      now_ms=NOW_FOR_SELF_TEST,
                      cutoff_ms=NOW_FOR_SELF_TEST
                      - GLOBAL_ASK_INTERVAL_DAYS * 86_400_000) in _live_due))
    cases.append(("leg11   and the mirror constant is DELETED, not renamed",
                  "DUE_COUNT_SQL" not in globals()))
    cases.append(("leg11   THE CONTROL: change due.ts's SQL and the gate's SQL changes",
                  'AND s."weight" > 0'
                  in (due_statement(_fake_due_ts('AND s."weight" > 0\n')) or "")))
    cases.append(("leg11   THE CONTROL: a comment quoting a predicate is not the predicate",
                  "weight" not in (due_statement(_fake_due_ts("")) or "weight")))
    cases.append(("leg11   a due.ts whose moments are not ours refuses, never under-counts",
                  due_count_sql(NOW_FOR_SELF_TEST, source=_fake_due_ts("").replace(
                      '  observer: "in_task",\n', "")) is None))
    cases.append(("leg11   a placeholder this gate cannot name refuses the whole count",
                  due_count_sql(NOW_FOR_SELF_TEST,
                                source=_fake_due_ts('AND s."x" > ?${pMystery}\n')) is None))
    cases.append(("leg11   a due.ts this reader cannot find the statement in is UNPROVEN",
                  due_count_sql(NOW_FOR_SELF_TEST, source="// nothing here") is None
                  and ask_state(True, True, None, 0) == "due-unknown"))
    # THE THREE BOOKS AGREE. This leg reads two literals out of the repo, and a
    # literal that stopped matching would report "not registered" forever while
    # production ran it — a red leg from a broken instrument, which is worse
    # than no leg. So the strings are checked against the files they came from.
    _reg, _wired = ask_config()
    cases.append(("leg11   THE INSTRUMENT: the cron literal still matches wrangler.jsonc",
                  _reg is True))
    cases.append(("leg11   THE INSTRUMENT: the wiring literal still matches src/cron.ts",
                  _wired is True))

    # ---- The roll-up -------------------------------------------------------
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


# ===========================================================================
# LEG 10 — the expiry webhook
# ===========================================================================

#: The only webhook the vendor publishes. There is no "connected" event, which
#: is the whole reason connections/wait.ts exists.
WEBHOOK_PATH = "/connections/events"

#: A control path one character away, so a 403 from the leg above can be shown
#: to be THIS ROUTE answering rather than a blanket refusal on the zone.
WEBHOOK_CONTROL_PATH = "/connections/eventsX"

#: An account id no `connections` row holds, and shaped so it could not be
#: mistaken for one. A verified event naming it must be a quiet 200: the vendor
#: retries an error forever, and an account somebody already disconnected is
#: not a problem.
WEBHOOK_PROBE_ACCOUNT = "ca_gate_probe_nobody_holds_this"

#: The webhook-id on every probe. A fixed value on purpose: the handler treats
#: a repeat as the same event, so running this gate in a loop cannot pile up
#: state anywhere.
WEBHOOK_PROBE_ID = "msg_gate_probe"

#: One second past the handler's freshness window (300s), so the stale case is
#: unambiguous rather than sitting on the boundary.
WEBHOOK_STALE_SECONDS = 301

#: The event body, byte-exact, because the signature covers it. Compact
#: separators for the same reason: a re-serialisation with different spacing
#: signs something other than what is sent.
WEBHOOK_PROBE_BODY = json.dumps({
    "type": "composio.connected_account.expired",
    "data": {"id": WEBHOOK_PROBE_ACCOUNT,
             "connected_account_id": WEBHOOK_PROBE_ACCOUNT,
             "user_id": PROBE_OWNER},
}, separators=(",", ":")).encode()


def leg_webhook(unsigned: int | None, control: int | None,
                signed: tuple[int, str] | None, stale: int | None) -> tuple[int, str, str]:
    """LEG 10. Is the expiry webhook deployed, secret-bearing, and verifying?

    ONE STATUS CODE SEPARATES FOUR STATES, which is why this leg is cheap and
    safe to run against production as often as anybody likes:

        404  the route is not deployed at all
        503  deployed, but COMPOSIO_WEBHOOK_SECRET is unset — every expiry is
             dropped and no owner is ever asked to reconnect
        403  deployed, secret set, and the signature was refused
        200  deployed, secret set, and a correctly signed event was handled

    Both 503 and 403 were measured on 2026-09-06, in that order, either side of
    `wrangler secret put` — so the difference between them is not a reading of
    the source, it is a before and after.

    The signed case is the one that proves anything end to end: it exercises the
    HMAC, the freshness window and the store read, and it names an account
    NOBODY HOLDS, so it moves no row and touches no owner. Without it a 403 on
    every request is indistinguishable from a webhook wired to the wrong secret,
    which would refuse every real expiry forever with a green deploy.
    """
    where = f"POST {WORKER}{WEBHOOK_PATH}"

    if unsigned is None:
        return UNPROVEN, INFO, (f"{where} could not be reached, so nothing here is a "
                                "claim about the webhook either way")
    if unsigned == 404:
        return RED, BAD, (f"{where} -> 404. The route is not deployed. Every "
                          "connected_account.expired the vendor sends is dropped, and "
                          "nobody is ever asked to reconnect a dead credential")
    if unsigned == 503:
        return RED, BAD, (f"{where} -> 503, so the route is deployed and "
                          "COMPOSIO_WEBHOOK_SECRET is UNSET. Same outcome as a 404 for "
                          "the person: every expiry is dropped. `wrangler secret put "
                          "COMPOSIO_WEBHOOK_SECRET` with the value from the vendor's "
                          "webhook subscription")
    if unsigned != 403:
        return RED, BAD, (f"{where} -> {unsigned} for an UNSIGNED event. Anything but a "
                          "403 here means an unauthenticated caller can reach the "
                          "handler, and marking somebody's connection expired strips "
                          "the API hand off a working account and texts them about it")
    if control is not None and control == 403:
        return UNPROVEN, INFO, (f"{where} -> 403, but so does the control "
                                f"{WEBHOOK_CONTROL_PATH}, so that 403 is the zone "
                                "refusing everything and says nothing about this route")

    if signed is None:
        return UNPROVEN, INFO, (f"{where} -> 403 for an unsigned event and the control "
                                f"{WEBHOOK_CONTROL_PATH} -> {control}, which is this "
                                "route answering. But no CORRECTLY signed event was "
                                "sent, so a webhook keyed with the wrong secret — which "
                                "refuses every real expiry forever — reads identically "
                                "from here")
    code, body = signed
    if code != 200:
        return RED, BAD, (f"{where} refused a correctly signed event: {code} {body[:120]}. "
                          "The deployed secret does not match the vendor's webhook "
                          "subscription, so every real expiry will be refused")
    if "ignored" not in body:
        return RED, BAD, (f"{where} answered 200 to an event naming {WEBHOOK_PROBE_ACCOUNT}, "
                          f"which no row holds, and did NOT say it ignored it: {body[:160]}. "
                          "It may have written something")
    if stale is not None and stale != 403:
        return RED, BAD, (f"{where} accepted an event whose timestamp was 301s old "
                          f"({stale}), so a captured request can be replayed at leisure")

    freshness = " and a 301s-stale one was refused" if stale == 403 else ""
    return GREEN, OK, (f"{where}: unsigned -> 403 (control {WEBHOOK_CONTROL_PATH} -> "
                       f"{control}, so that is this route), correctly signed -> 200 "
                       f"{body[:60]}{freshness}. The HMAC, the freshness window and the "
                       "store read are all exercised, and no row moved: the event named "
                       "an account nobody holds")


def webhook_secret(api_key: str, *, base: str = COMPOSIO_BASE_V3,
                   timeout: int = 30) -> tuple[str, dict] | None:
    """The signing secret of our ONE webhook subscription, and the subscription.

    NEVER RETURNED TO THE SCREEN. The caller signs with it inside this process
    and prints only a status code; the secret is not put on a command line, not
    logged, and not written to a file.

    Exactly one subscription is expected. Two would mean two secrets, only one
    of which the Worker holds, and a leg that picked the first would be green
    or red by luck.
    """
    req = urllib.request.Request(f"{base.rstrip('/')}/webhook_subscriptions",
                                 headers={"x-api-key": api_key, "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            answer = json.loads(res.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as exc:
        raise VendorUnavailable(str(exc)) from exc
    items = answer.get("items") or []
    if len(items) != 1:
        return None
    secret = str(items[0].get("secret") or "")
    return (secret, items[0]) if secret else None


def sign_webhook(secret: str, msg_id: str, timestamp: str, body: bytes) -> str:
    """Standard Webhooks, the scheme connections_webhook.ts verifies.

    Signed input is `{id}.{timestamp}.{body}`, HMAC-SHA256, base64, presented as
    `v1,<sig>`. The key bytes rule mirrors `webhookKeyBytes` EXACTLY: a
    `whsec_` prefix means base64-decode the rest, anything else is the string's
    own UTF-8 bytes. Mirroring rather than re-deciding is the point — a signer
    that made its own choice here would go green against a Worker that verifies
    differently.
    """
    signed = msg_id.encode() + b"." + timestamp.encode() + b"." + body
    key = (base64.b64decode(secret[len("whsec_"):]) if secret.startswith("whsec_")
           else secret.encode())
    return "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


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
    ap.add_argument("--catalog-query", default=None,
                    help=f"what leg 3 types into the search box (default {CATALOG_QUERY!r}). "
                         "The owner credential itself is read from "
                         f"{' or '.join(CREDENTIAL_ENV)} and is never taken from argv")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    code, rows = run(read_only=args.read_only, owner=args.owner,
                     catalog_query=args.catalog_query)
    report(code, rows)
    return code


if __name__ == "__main__":
    sys.exit(main())
