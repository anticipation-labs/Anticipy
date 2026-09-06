"""The connect gate must be able to tell seven different kinds of nothing apart.

On 2026-09-06 every claim about Connections was repo-green: the pure core has
1006 tests behind it in the spike, the store refuses cross-owner writes by name,
the provider turns the connection meta-tool off and checks the answer, the iOS
screen is drawn. And a person could not connect anything, because:

    GET https://api.anticipy.ai/c/<43 chars>   ->  404 application/json,
                                                   the router's generic notFound
    SELECT name FROM sqlite_master ...          ->  zero of the four tables
    installConnectWiring()                      ->  zero callers

HARNESS-LAWS law 3 is the whole reason overnight/is_connect_live.py exists, and
these tests exist because a gate is only worth its discriminations. Seven
outcomes look identical to a careless instrument and want seven different
people:

    the six routes are not deployed    -> deploy the Worker
    the /c/ route is not deployed      -> deploy the Worker
    the route is there and unwired     -> call installConnectWiring
    the tables are not on live D1      -> one wrangler command
    the catalog search port is unfilled-> write a search adapter
    the page renders and goes nowhere  -> put a control on the sign-in page
    nobody has connected anything yet  -> nothing. This is not a failure.

Every test below fails if the gate collapses one of those into another, or if it
turns something it did not measure into a number on the screen.

The legs were renumbered on 2026-09-06 when legs 1, 3 and 7 were added, so that
the printed order is the order a person walks the chain in. Section headers
below carry the NEW numbers; the gate's own docstring carries the map.
"""
import json
import os
import re
import shutil
import sys
import time
import urllib.parse

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from overnight import is_connect_live as M  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(REPO, "migration", "d1", "schema.sql")
WRANGLER_CONFIG = os.path.join(REPO, "migration", "workers", "wrangler.jsonc")


# ---------------------------------------------------------------------------
# The answers the live Worker can give, as bodies and headers. Every one of
# these was copied off production with curl on 2026-09-06 unless it is marked
# as a shape the deployment can take but has not yet.
# ---------------------------------------------------------------------------

CSP = ("default-src 'none'; img-src https:; style-src 'unsafe-inline'; "
       "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

HTML_H = {"content-type": "text/html; charset=utf-8", "content-security-policy": CSP}
JSON_H = {"content-type": "application/json; charset=utf-8"}

#: Measured against production on 2026-09-06 04:08, when /c/ was not deployed.
#: Also what `/me/connectionsX` — leg 1's control — answers today.
LIVE_404 = (404, {"content-type": "application/json"},
            '{"code":404,"message":"The requested resource wasn\'t found.","data":{}}')
#: What all six /me/connections routes answer without a credential
#: (connections_api.ts SIGN_IN_FIRST). Measured 2026-09-06 06:17.
REFUSED = (401, JSON_H, '{"ok":false,"message":"Sign in first."}')
#: connections_api.ts NOT_A_ROUTE: the prefix is routed, this path is not a leg.
NOT_A_LEG = (404, JSON_H, '{"ok":false,"message":"There\'s nothing at this address."}')
#: `refuse(503, CATALOG_UNREACHABLE)` — what `?q=` answers when the search port
#: is unfilled on the deployed build, and also when the catalog refuses. Measured
#: 2026-09-06 06:17: no filler existed at all. A `provider.search` was written
#: into `connectionsApiDeps()` later the same day; whether the deployed build
#: carries it is what leg 3 is for, and it is UNPROVEN until somebody exports a
#: credential.
CATALOG_503 = (503, JSON_H,
               '{"ok":false,"message":"I couldn\'t look that up just now. '
               'Nothing has changed."}')
#: routes/connect.ts unwired().
UNWIRED = (503, HTML_H, f"<h1>{M.UNWIRED_MARK}</h1><p>Anticipy can't set this up "
                        "right now.</p>")


def sign_in_page(token, way_in=False):
    """`refusalPage("sign-in-required")`, as production draws it.

    MEASURED 2026-09-06 06:17 UTC and reproduced here in the part that matters:
    a heading, a sentence, and — unless `way_in` — NOTHING that a finger can
    touch. `plainPage`'s optional `back` link was not passed on this state, so
    the page had no anchor and no form at all.

    IT WAS FIXED AT 07:20 THE SAME DAY, and this fixture keeps the broken shape
    on purpose: leg 7's whole job is to say RED to it, and a fixture that quietly
    followed the repair would leave the leg untested against the only page it has
    ever had to catch.
    """
    body = ("<body>\n<h1>Sign in to finish</h1>\n<p>Sign in to Anticipy in this "
            "browser, then open this link again. It works for ten minutes.</p>\n")
    if way_in:
        body += f'<p><a href="/c/{token}/code">Text me a code</a></p>\n'
    return (401, HTML_H, body + "</body>")


def code_page(token):
    """`/c/{token}/code`, as connect_auth.ts draws it and as production served
    it on 2026-09-06 06:17. Leg 7's CONTROL: a page that is KNOWN to carry the
    control the scan looks for, because its own form posts back to itself."""
    return (200, HTML_H,
            f"<body>\n<h1>{M.CODE_PAGE_MARK}</h1>\n"
            f'<form method="post" action="/c/{token}/code">\n'
            '  <button type="submit">Text me a code</button>\n</form>\n'
            '<a class="later" href="https://anticipy.ai/">Skip for now</a>\n</body>')


#: Kept as a name because several leg 5/6 tests read it directly. It is the
#: measured dead end, so it must NOT carry a way in.
SIGN_IN = sign_in_page("A" * M.TOKEN_CHARS)


@pytest.fixture(autouse=True)
def _no_ambient_credentials(monkeypatch):
    """The gate loads `.env.local` at import, which on the owner's machine holds
    a real COMPOSIO_API_KEY and a real TWO_HANDS_OWNER. Tests that silently
    depended on those would pass here and fail in CI — and, worse, a test of
    "what happens when there is no key" would be measuring the machine rather
    than the gate. Every test below gets the same fixed values.

    The two credential variables are CLEARED, not set: leg 3's default state on
    this machine must be the honest "nobody gave me an owner token", and a test
    that silently picked one up would be measuring the operator's shell."""
    monkeypatch.setenv("COMPOSIO_API_KEY", "test-key-not-a-real-one")
    monkeypatch.setenv("ANTICIPY_CONNECT_PROBE_OWNER", "sxkotd1h02qb6gw")
    for name in M.CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)


class FakeWorker:
    """The live Worker, answered by PATH and VERB, recording every request.

    A fake that answered the same thing to every URL — which is what this file
    had before leg 1 existed — cannot catch a gate that asks the wrong path, or
    the right path with the wrong verb, or that sends a credential where it must
    not. All three are failures this gate has to be incapable of, so the fake
    knows the difference and `seen` keeps the receipts.
    """

    def __init__(self, page=None, code=None, routes=REFUSED, control=LIVE_404,
                 listing=None, catalog=CATALOG_503, way_in=False, only=None,
                 webhook=None, webhook_control=None):
        self.page = page              # (status, headers, body) or None -> sign-in
        self.code = code              # the /code control page, or None -> real one
        self.routes = routes          # the answer for all six /me/connections legs
        self.control = control        # the answer for /me/connectionsX
        self.listing = listing or (200, JSON_H, '{"items":[]}')
        self.catalog = catalog
        self.way_in = way_in
        self.only = only or {}        # path -> answer, overriding everything
        # LEG 10. `webhook` is a callable (headers) -> answer, so a test can
        # answer differently for a signed and an unsigned request without the
        # fake having to know how to verify a signature -- it looks at whether
        # one was PRESENTED, which is the only thing a fake honestly can.
        self.webhook = webhook
        self.webhook_control = webhook_control or (404, {}, "not found")
        self.seen = []
        self.token = None

    def __call__(self, url, method="GET", headers=None, body=None):
        path = urllib.parse.urlsplit(url).path
        query = urllib.parse.urlsplit(url).query
        self.seen.append({"method": method, "path": path, "query": query,
                          "headers": dict(headers or {}), "body": body})
        if path in self.only:
            return self.only[path]

        if path == M.WEBHOOK_CONTROL_PATH:
            return self.webhook_control
        if path == M.WEBHOOK_PATH:
            if self.webhook is None:
                raise AssertionError(
                    "the gate asked for the webhook and this fake serves none; "
                    "use a_deployed_worker() or pass webhook=")
            return self.webhook(dict(headers or {}))

        m = re.fullmatch(r"/c/([A-Za-z0-9_-]{43})(/code)?", path)
        if m:
            self.token = m.group(1)
            if m.group(2):
                return self.code or code_page(self.token)
            return self.page or sign_in_page(self.token, self.way_in)

        if path == M.CONNECTIONS_CONTROL_PATH:
            return self.control
        if path == "/me/connections" and (headers or {}).get("Authorization"):
            return self.listing
        if path == "/me/connections/catalog" and (headers or {}).get("Authorization"):
            return self.catalog
        if any(path == p for _n, _m, p in M.CONNECTIONS_ROUTES):
            return self.routes
        raise AssertionError(f"the gate asked for {path!r}, which the fake does not serve")

    def asked(self, path, method=None):
        return [r for r in self.seen
                if r["path"] == path and (method is None or r["method"] == method)]


def a_verifying_webhook(*, now_ms=None, stale_ok=False,
                        signed=(200, JSON_H,
                                '{"ok":true,"ignored":"no such connection"}')):
    """The shape production had on 2026-09-06, an hour after the secret landed.

    It cannot check a signature and does not pretend to: it answers on whether
    one was PRESENTED and whether the timestamp is inside the window. That is
    exactly the distinction leg 10 draws its verdict from, and no more.
    """
    def answer(headers):
        sig = headers.get("webhook-signature")
        stamp = headers.get("webhook-timestamp")
        if not sig or not stamp:
            return (403, JSON_H, '{"ok":false,"error":"forbidden"}')
        # THE SAME CLOCK THE GATE USED. A fake that read the wall clock while
        # the gate signed against an injected `now_ms` calls every fresh
        # signature stale, and the leg then reports a webhook keyed with the
        # wrong secret -- a false RED produced entirely by the test rig.
        now = int(now_ms / 1000) if now_ms else int(time.time())
        skew = abs(now - int(stamp))
        if skew > 300 and not stale_ok:
            return (403, JSON_H, '{"ok":false,"error":"forbidden"}')
        return signed
    return answer


def a_deployed_worker(*, now_ms=None, **kw):
    """Every HTTP leg green: six routes refusing, the control 404ing, a connect
    page with a way in on it, a catalog with rows, and a verifying webhook.

    Pass the same `now_ms` the gate is run with, or the webhook signs against
    one clock and is checked against another.
    """
    kw.setdefault("way_in", True)
    kw.setdefault("catalog", (200, JSON_H, '{"items":[{"slug":"x"},{"slug":"y"}]}'))
    kw.setdefault("webhook", a_verifying_webhook(now_ms=now_ms))
    return FakeWorker(**kw)


def a_webhook_secret(secret="plainprobesecret"):
    """The `webhook` transport run() takes: (api_key) -> (secret, subscription)."""
    return lambda _api_key: (secret, {"id": "ws_fake", "webhook_url": "x",
                                      "enabled_events": ["composio.connected_account.expired"]})


def http_answering(*answer):
    """A Worker whose /c/ page is `answer` and whose server half is healthy.

    Kept so the leg 5/6 tests read the way they always did: they are about what
    ONE page proves, and the rest of the chain is scenery for them.
    """
    return FakeWorker(page=answer)


class FakeD1:
    """A D1 addressed the way the gate addresses it: by statement text.

    Records every statement, so a test can assert on the QUESTION as well as on
    the answer — the gate deleting the row it wrote is a claim about what it
    SAID to the database, not about what the database said back.
    """

    def __init__(self, tables=(), connections=None, rows=None, fail_on=None,
                 asked=None, due=0):
        self.tables = list(tables)
        self.connections = connections or {"rows_n": 0, "owners_n": 0}
        self.statements = []
        self.stored = dict(rows) if rows else {}
        self.fail_on = fail_on or ()
        self.deleted = []
        # LEG 11. `asked` is the connect_nudges answer: None means the table
        # answered nothing at all (which the gate must read as UNPROVEN, not as
        # zero), and a dict is `{"asked_n": n, "newest": ms}`.
        self.asked = asked
        self.due = due

    def __call__(self, sql):
        self.statements.append(sql)
        for needle in self.fail_on:
            if needle in sql:
                raise M.D1Unavailable(f"refused: {needle}")
        if "sqlite_master" in sql:
            return [{"name": t} for t in self.tables]
        if sql.startswith("INSERT INTO \"connect_links\""):
            # Parsed out of the statement rather than handed over: a fake that
            # echoed the gate's intentions could not catch a gate that writes
            # one thing and compares another.
            self.stored["current"] = _row_from_insert(sql)
            self.stored["row"] = True
            return []
        if sql.startswith("SELECT \"token_handle\""):
            return [dict(self.stored["current"])] if self.stored.get("row") else []
        if sql.startswith("DELETE FROM \"connect_links\""):
            self.deleted.append(sql)
            self.stored["row"] = False
            return []
        if "count(*) AS n FROM \"connect_links\"" in sql:
            return [{"n": 1 if self.stored.get("row") else 0}]
        if "asked_n" in sql:
            return [] if self.asked is None else [dict(self.asked)]
        if "due_n" in sql:
            return [{"due_n": self.due}]
        if "FROM \"connections\"" in sql:
            return [dict(self.connections)]
        return []


def d1_with_a_working_connect_links(now_ms=None):
    """A FakeD1 whose four tables exist, whose connect_links behaves, and which
    has actually asked somebody — leg 11's green needs a row, not a config."""
    return FakeD1(tables=M.TABLES, connections={"rows_n": 2, "owners_n": 1},
                  asked={"asked_n": 3, "newest": float((now_ms or 0) - 3_600_000)})


def _row_from_insert(sql):
    """Read back the seven values the gate put in its own INSERT."""
    cols = re.search(r'INSERT INTO "connect_links" \((.*?)\) VALUES \((.*)\)$', sql, re.S)
    names = [c.strip().strip('"') for c in cols.group(1).split(",")]
    raw = [v.strip() for v in cols.group(2).split(",")]
    out = {}
    for name, value in zip(names, raw):
        if value == "NULL":
            out[name] = None
        elif value.startswith("'"):
            out[name] = value.strip("'")
        else:
            out[name] = float(value)
    return out


def vendor_answering(**overrides):
    base = {"status": 201, "session_id_len": 16, "manage_connections": False,
            "connection_tool_present": False}
    base.update(overrides)
    return lambda key, owner: base


def details(rows):
    return " || ".join(r[2] for r in rows)


def marks(rows):
    return [r[0] for r in rows]


# ===========================================================================
# LEG 1 — the six routes the phone calls, and the control under them
# ===========================================================================
# Until this leg existed the gate stopped at the /c/ page: every one of the six
# routes Settings -> Connected Apps calls could have been absent from the
# deployed Worker and the board would still have read 5 PASS. Law 3 had no
# instrument for the entire server half.

API_TS = os.path.join(REPO, "migration", "workers", "src", "routes", "connections_api.ts")


def _declared_routes():
    """`CONNECTIONS_API_ROUTES` and `METHOD` read out of connections_api.ts.

    THE ANCHOR IS ASSERTED TO BE UNIQUE before anything is parsed out of it. A
    regex that silently stopped matching would leave this test passing over an
    empty comparison, which is the exact way an instrument lies — three false
    "it is tested" readings came from that shape in one day.
    """
    text = open(API_TS, encoding="utf-8").read()
    assert text.count("export const CONNECTIONS_API_ROUTES = {") == 1, API_TS
    assert text.count('const METHOD: Record<ConnectionsApiLeg, "GET" | "POST"> = {') == 1
    paths = re.search(r"export const CONNECTIONS_API_ROUTES = \{(.*?)\} as const;",
                      text, re.S).group(1)
    verbs = re.search(r'const METHOD: Record<ConnectionsApiLeg, "GET" \| "POST"> = \{(.*?)\};',
                      text, re.S).group(1)
    declared = dict(re.findall(r'(\w+):\s*"(/[^"]+)"', paths))
    methods = dict(re.findall(r'(\w+):\s*"(GET|POST)"', verbs))
    # NOT A MAGIC NUMBER ANY MORE. It read `== 6` until 2026-09-06, when a
    # SEVENTH route (`/me/connections/skip`, the one that carries a person's
    # "no" off the glass and onto the ladder) was added to the Worker and this
    # assertion failed with a count instead of a name. The count that means
    # something is the gate's own list: a route the Worker declares and the gate
    # does not ask about is a route no leg measures, and that is what the next
    # two assertions compare.
    assert len(declared) == len(methods) >= len(M.CONNECTIONS_ROUTES), (declared, methods)
    return declared, methods


def test_the_gate_asks_for_every_route_the_worker_declares():
    """THREE BOOKS, ONE TRUTH. connections_api.ts declares the paths and the
    verbs, ConnectedAppsClient.swift reads the same ones, and this gate asks
    production about them. A route added to the Worker without this list is a
    route no leg measures — which happened on 2026-09-06 with `/skip` — and a
    path typed wrong here is a leg that measures the router's 404 forever."""
    declared, methods = _declared_routes()
    assert {p for _n, _m, p in M.CONNECTIONS_ROUTES} == set(declared.values())
    for name, method, path in M.CONNECTIONS_ROUTES:
        assert declared[name] == path, name
        assert methods[name] == method, f"{name} is a {methods[name]} in the Worker"


def test_the_control_path_is_deliberately_not_a_route():
    """The control only calibrates the discriminator if it is genuinely not a
    route. index.ts hands over the exact path and the trailing-slash prefix, so
    a control that started with `/me/connections/` would be answered by the file
    itself and would prove the opposite of what it is for."""
    assert M.CONNECTIONS_CONTROL_PATH.startswith("/me/connections")
    assert not M.CONNECTIONS_CONTROL_PATH.startswith("/me/connections/")
    assert M.CONNECTIONS_CONTROL_PATH not in {p for _n, _m, p in M.CONNECTIONS_ROUTES}


def test_a_deployed_route_and_a_missing_one_are_not_the_same_answer():
    """Both are JSON, both are a refusal to a stranger, and they want two
    different people: one is a route that asked for a credential, the other is a
    Worker that has never heard of the path."""
    assert M.classify_connections_response(*REFUSED)[0] == "refused"
    assert M.classify_connections_response(*LIVE_404)[0] == "route-missing"
    assert M.classify_connections_response(*NOT_A_LEG)[0] == "not-a-leg"


def test_every_route_is_asked_with_its_own_verb_and_no_credential():
    """`connectionsApiRoute` checks the METHOD before the credential, so a GET
    on /link is a 405 that never reaches the 401 this leg reads — asking with
    the wrong verb would report four deployed routes as unreadable. And no
    probe may carry a credential: an authenticated probe would reach
    the store, the vendor and the model, and would be measuring a signed-in path
    rather than the deployment."""
    worker = a_deployed_worker()
    M.run(http=worker, sql=FakeD1(tables=M.TABLES), vendor=vendor_answering(),
          owner="sxkotd1h02qb6gw", credential="an-owner-token", read_only=True)
    for name, method, path in M.CONNECTIONS_ROUTES:
        probes = [r for r in worker.asked(path) if not r["headers"].get("Authorization")]
        assert probes, f"{name} was never asked anonymously"
        assert probes[0]["method"] == method, name
    assert worker.asked(M.CONNECTIONS_CONTROL_PATH), "the control was never asked"


def test_a_route_that_is_not_deployed_is_red_and_named():
    """'connections is broken' sends a reader to the code. 'link answers the
    router's 404' sends them to one deploy."""
    worker = a_deployed_worker(only={"/me/connections/link": LIVE_404})
    code, rows = M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
                       vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    assert rows[0][0] == M.BAD
    assert "link" in rows[0][2] and "route-missing" in rows[0][2]
    assert code == M.RED


def test_the_prefix_being_routed_with_the_wrong_paths_is_its_own_failure():
    """connections_api.ts deployed with a route table that disagrees with ours
    answers its OWN 404, not the router's. Different repair, different sentence,
    and a gate that collapsed them would send somebody to redeploy a Worker that
    is already there."""
    worker = a_deployed_worker(only={"/me/connections/sentences": NOT_A_LEG})
    _, rows = M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
                    vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    assert rows[0][0] == M.BAD
    assert "not-a-leg" in rows[0][2]


def test_a_worker_that_refuses_everything_proves_nothing():
    """THE CONTROL, and the reason this leg is not just six status codes. If the
    edge answered 401 to every path on earth, all six would light up green and
    every one of them would be measuring the edge. The control is a path that is
    NOT a route: it has to come back as the router's own 404, or the six 401s
    are not evidence."""
    worker = a_deployed_worker(control=REFUSED)
    code, rows = M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
                       vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    assert rows[0][0] == M.INFO, "an uncalibrated discriminator cannot pass"
    assert M.CONNECTIONS_CONTROL_PATH in rows[0][2]
    assert code != M.GREEN


def test_an_anonymous_caller_getting_an_answer_is_the_loudest_red():
    """The failure this whole feature is shaped around, seen from outside: one
    person's connected accounts readable by anybody with the URL. It outranks
    every other reading of leg 1, including a missing route."""
    worker = a_deployed_worker(only={"/me/connections": (200, JSON_H, '{"items":[]}')})
    code, rows = M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
                       vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    assert rows[0][0] == M.BAD
    assert "ANONYMOUS" in rows[0][2]
    assert "whoIsAsking" in rows[0][2]
    assert code == M.RED


def test_an_unreadable_route_withholds_green_without_crying_red():
    """An edge error is not evidence that a route is missing. It is not evidence
    of anything, and the third state is what says so."""
    worker = a_deployed_worker(
        only={"/me/connections/writes": (502, {"content-type": "text/html"}, "<html/>")})
    _, rows = M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
                    vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    assert rows[0][0] == M.INFO
    assert "writes" in rows[0][2]


# ===========================================================================
# LEG 5 and LEG 6 — the deployment, and the wiring, which are not the same thing
# ===========================================================================

def test_the_live_404_is_a_missing_route_and_says_so():
    """The measured production answer. A JSON 404 from the router is a Worker
    with no connect page in it — not a page that refused the caller."""
    kind, detail = M.classify_c_response(*LIVE_404)
    assert kind == "route-missing"
    code, mark, sentence = M.leg_route(kind, detail, "u")
    assert code == M.RED
    assert "connect.ts is not on the deployed Worker" in sentence


def test_an_unwired_worker_is_red_on_the_wiring_leg_and_never_unproven():
    """The distinction the whole file is built on: we can SEE an unwired
    Worker, because it tells us in a sentence written for the case. Reporting
    that as 'unproven' would file a fixable, visible break under 'we could not
    measure' and nobody would work it."""
    kind, detail = M.classify_c_response(*UNWIRED)
    assert kind == "unwired"
    assert M.leg_route(kind, detail, "u")[0] == M.GREEN, "the route IS deployed"
    code, _, sentence = M.leg_wiring(kind, detail)
    assert code == M.RED
    assert "installConnectWiring" in sentence


def test_a_refusal_page_still_proves_the_route_and_the_wiring():
    """THE CONTROL. A 401 is the correct answer to a signed-out probe, and it
    is drawn by connect.ts AFTER the wiring returned deps — so it proves both
    legs. A gate that read any non-200 as a failure would go red on a Worker
    that is working perfectly."""
    kind, detail = M.classify_c_response(*SIGN_IN)
    assert kind == "connect-page"
    assert M.leg_route(kind, detail, "u")[0] == M.GREEN
    assert M.leg_wiring(kind, detail)[0] == M.GREEN


def test_an_edge_error_measures_nothing():
    """A 502 from something that is not this Worker is not evidence about the
    route in either direction."""
    kind, detail = M.classify_c_response(502, {"content-type": "text/html"}, "<html>bad</html>")
    assert kind == "unreadable"
    assert M.leg_route(kind, detail, "u")[0] == M.UNPROVEN
    assert M.leg_wiring(kind, detail)[0] == M.UNPROVEN


def test_the_probe_token_is_one_connect_ts_would_route():
    """43 characters of the token alphabet (connect.ts TOKEN_CHARS and
    parseConnectPath). A malformed token is refused by the path parser before
    the route runs, and leg 1 would then be measuring the parser rather than
    the deployment — it would answer 404 on a perfectly deployed Worker."""
    for _ in range(20):
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", M.probe_token())


def test_the_probe_request_carries_no_credentials(monkeypatch):
    """A gate that sent the service token would be measuring a signed-in path
    and could reach the store. This one must be anonymous: connect.ts settles
    the session before it looks anything up, so an anonymous probe cannot read,
    spend or disturb anybody's link."""
    seen = {}

    class _Res:
        status = 401
        headers = {"content-type": "text/html"}

        def read(self):
            return b"<h1>Sign in to finish</h1>"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["headers"] = {k.lower(): v for k, v in req.headers.items()}
        seen["method"] = req.get_method()
        seen["data"] = req.data
        return _Res()

    monkeypatch.setattr(M.urllib.request, "urlopen", fake_urlopen)
    M._http("https://api.anticipy.ai/c/" + M.probe_token())
    assert seen["method"] == "GET", "a POST would spend a link"
    assert "authorization" not in seen["headers"]
    assert "cookie" not in seen["headers"]
    assert seen["data"] is None, "a GET must not carry a body"

    # The four POST routes carry an EMPTY body, so the request has a
    # Content-Length and the Worker reads it as a POST — and nothing else. The
    # credential is settled before any of them looks at a body, so an empty one
    # is refused without a row being written or a budget being spent.
    M._http("https://api.anticipy.ai/me/connections/link", method="POST")
    assert seen["method"] == "POST"
    assert seen["data"] == b""
    assert "authorization" not in seen["headers"]


# ===========================================================================
# LEG 2 — the four tables on the live database
# ===========================================================================

def test_missing_tables_are_named_one_by_one():
    """'connections is broken' sends a reader to the code; 'connect_links does
    not exist' sends them to one wrangler command."""
    code, _, sentence = M.leg_tables({"connections"}, "anticipy-backend")
    assert code == M.RED
    assert "connect_links" in sentence and "connect_nudges" in sentence
    assert "app_usage_signals" in sentence


def test_all_four_present_is_green():
    assert M.leg_tables(set(M.TABLES), "anticipy-backend")[0] == M.GREEN


def test_an_unreadable_database_is_unproven_and_claims_no_count():
    """THE CONTROL THAT MATTERS MOST HERE. wrangler with no credentials must
    never be reported as a missing schema: that would send somebody to write
    DDL that already exists, and — worse — a gate in the habit of turning 'I
    could not ask' into 'the answer is zero' is a gate that will one day print
    zero connections for a database it never reached."""
    code, rows = M.run(http=http_answering(*LIVE_404),
                       sql=FakeD1(fail_on=("sqlite_master", "connections")),
                       vendor=vendor_answering())
    text = details(rows)
    assert rows[1][0] == M.INFO
    assert "0 of 4" not in text
    assert "MISSING" not in text
    assert code == M.RED, "leg 1 is still red; an unreadable D1 does not soften that"


# ===========================================================================
# LEG 3 — the catalog, which is the whole of "Add an app"
# ===========================================================================
# The one leg here that needs a credential, and it needs one because the route
# settles the credential before it builds a single dependency: an anonymous
# caller sees 401 and never sees whether the search port behind it is filled.

def _catalog_run(worker, **kw):
    kw.setdefault("credential", "an-owner-token")
    return M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
                 vendor=vendor_answering(), owner="sxkotd1h02qb6gw", **kw)


def test_the_unfilled_search_port_is_red_and_its_sentence_is_quoted():
    """A 503 to `?q=` is a person tapping Add an app and getting nothing — a
    broken feature, not an unmeasured one — whether the cause is an unfilled
    `ConnectionsApiDeps.search` port on the deployed build or a catalog that did
    not answer. The leg quotes the Worker's own sentence so the reader can grep
    for it rather than take our word, and does not guess between the two causes,
    because the body does not say."""
    code, rows = _catalog_run(a_deployed_worker(catalog=CATALOG_503))
    assert rows[2][0] == M.BAD
    assert "I couldn't look that up just now" in rows[2][2]
    assert "search" in rows[2][2], "the reader is pointed at the port by name"
    assert code == M.RED


def test_the_catalog_is_asked_as_the_phone_asks_it():
    """With the credential in the header — never in the query string — and with
    `q`, which is the query name ConnectedAppsClient sends. `slugs` is never
    sent by this gate: that parameter takes catalog keys, and a gate that had
    keys to send would be a gate with app names hardcoded in it."""
    worker = a_deployed_worker()
    _catalog_run(worker)
    asks = worker.asked("/me/connections/catalog")
    assert len(asks) == 2, "once anonymously for leg 1, once with the credential"
    authed = [a for a in asks if a["headers"].get("Authorization")]
    assert len(authed) == 1
    assert authed[0]["method"] == "GET"
    assert urllib.parse.parse_qs(authed[0]["query"]) == {M.CATALOG_QUERY_NAME: [M.CATALOG_QUERY]}
    assert "slugs" not in authed[0]["query"]
    assert "an-owner-token" not in authed[0]["query"], "a credential in a URL is a "\
        "credential in browser history and in our own logs"


def test_the_catalog_probe_names_no_app():
    """NO APP IS HARDCODED, anywhere in this feature. A gate that probed with a
    real app's name would be the first file to break that rule, and would be
    wrong the day the catalog changes."""
    assert re.fullmatch(r"[a-z]{1,2}", M.CATALOG_QUERY)


def test_the_credential_is_never_sent_off_our_own_zone(monkeypatch):
    """`WORKER` comes from ANTICIPY_PB, which pointed at a different backend as
    recently as last week. Leg 3 is the only leg in the file that sends a secret,
    and a gate that posted an owner's auth token to whatever host a variable
    happened to name would be a credential leak with a scoreboard on it."""
    monkeypatch.setattr(M, "WORKER", "https://anticipy-backend.up.railway.app")
    worker = a_deployed_worker()
    _, rows = _catalog_run(worker)
    assert rows[2][0] == M.INFO
    assert "NOT SENT" in rows[2][2]
    assert not [r for r in worker.seen if r["headers"].get("Authorization")]


@pytest.mark.parametrize("host,allowed", [
    ("https://api.anticipy.ai", True),
    ("https://anticipy.ai", True),
    ("https://preview.workers.anticipy.ai:8443", True),
    ("https://evil-anticipy.ai", False),          # ends with the zone, is not ours
    ("https://anticipy.ai.example.com", False),   # begins with it, is not ours
    ("http://localhost:8787", False),
])
def test_which_hosts_may_hold_an_owner_token(host, allowed):
    assert M.credential_may_be_sent(host) is allowed


def test_a_refused_credential_is_not_a_broken_catalog():
    """THE CONTROL. `GET /me/connections` with the same credential says whose
    fault a refusal is. A stale token reported as a broken catalog sends the
    reader to write a search adapter that was never the problem."""
    worker = a_deployed_worker(listing=REFUSED)
    code, rows = _catalog_run(worker)
    assert rows[2][0] == M.INFO
    assert "credential" in rows[2][2]
    assert "search port" not in rows[2][2], "no claim about the catalog may be made here"
    assert code != M.GREEN


def test_no_credential_means_the_catalog_is_never_even_asked():
    """UNPROVEN, and the route is not touched. A gate that guessed here would be
    reporting its own setup as the product's state."""
    worker = a_deployed_worker()
    _, rows = _catalog_run(worker, credential="")
    assert rows[2][0] == M.INFO
    assert M.CREDENTIAL_ENV[0] in rows[2][2]
    assert not [a for a in worker.seen if a["headers"].get("Authorization")]


def test_the_catalog_is_not_asked_over_an_undeployed_route():
    """Chain order is load-bearing: a 404 from the catalog path means the router,
    not the catalog, and reading it as a catalog verdict would send somebody to
    the wrong file."""
    worker = a_deployed_worker(routes=LIVE_404)
    _, rows = _catalog_run(worker)
    assert rows[2][0] == M.INFO
    assert "leg 1" in rows[2][2]
    assert not [a for a in worker.seen if a["headers"].get("Authorization")]


def test_an_answer_with_no_rows_claims_nothing_and_prints_what_it_counted():
    """A filled port that matched nothing is not a broken catalog and is not a
    working one either. The count on the screen is the count that came back."""
    worker = a_deployed_worker(catalog=(200, JSON_H, '{"items":[]}'))
    _, rows = _catalog_run(worker)
    assert rows[2][0] == M.INFO
    assert "0 items" in rows[2][2]


def test_rows_coming_back_is_the_only_green():
    worker = a_deployed_worker(catalog=(200, JSON_H, '{"items":[{"slug":"x"}]}'))
    _, rows = _catalog_run(worker)
    assert rows[2][0] == M.OK
    assert "1 item" in rows[2][2]


def test_a_200_that_is_not_a_list_is_red_because_the_screen_throws():
    """ConnectedAppsClient reads row["items"] and throws on anything else, so a
    200 the phone cannot read is a failure for the person, whatever it is for
    the server."""
    worker = a_deployed_worker(catalog=(200, JSON_H, '{"ok":true}'))
    _, rows = _catalog_run(worker)
    assert rows[2][0] == M.BAD


# ===========================================================================
# LEG 4 — the one leg that writes
# ===========================================================================

def test_the_probe_row_can_never_be_a_live_link():
    """Four independent reasons, each of which alone makes the row
    unredeemable. This is the test that lets a gate write to production."""
    now = 1_757_000_000_000
    row = M._probe_row(now)
    ok, why = M.probe_row_is_inert(row, now)
    assert ok, why
    assert re.fullmatch(r"[0-9a-f]{64}", row["token_handle"])
    assert row["expires_at"] < now, "born expired"
    assert row["used_at"] is None and row["completed_at"] is None
    assert re.fullmatch(r"[a-z0-9]{15}", row["user_id"])


@pytest.mark.parametrize("mutation, why", [
    ({"expires_at": 1_757_000_600_000.0}, "a link that is still live"),
    ({"user_id": "sxkotd1h02qb6gw"}, "a real owner's id"),
    ({"used_at": 1_757_000_000_000.0}, "a claimed row, which opens the callback window"),
    ({"token_handle": "short"}, "a handle that is not the sha256 shape"),
    ({"toolkit": ""}, "an empty toolkit, which the CHECK constraint refuses"),
])
def test_a_dangerous_probe_row_is_refused_before_it_is_written(mutation, why):
    now = 1_757_000_000_000
    row = {**M._probe_row(now), **mutation}
    ok, _ = M.probe_row_is_inert(row, now)
    assert not ok, f"the gate would have written {why}"


def test_the_probe_row_never_names_an_app():
    """NO APP IS HARDCODED is a product rule for this whole feature. A gate
    writing 'gmail' into connect_links would be the first file to break it."""
    assert M.PROBE_TOOLKIT not in ("gmail", "googlecalendar", "notion", "slack")


def test_the_mint_leg_writes_reads_deletes_and_confirms():
    now = 1_757_000_000_000
    fake = d1_with_a_working_connect_links(now)
    code, _, sentence = M.mint_probe_link(fake, now)
    assert code == M.GREEN, sentence
    kinds = [s.split(" ")[0] for s in fake.statements]
    assert kinds == ["INSERT", "SELECT", "DELETE", "SELECT"], fake.statements
    assert "nothing left behind" in sentence
    assert M.PROBE_OWNER in fake.deleted[0], "the DELETE must be owner-scoped"


def test_a_row_that_comes_back_wrong_is_red_and_names_the_column():
    """The 1101 detector. On 2026-09-05 the live `events` table was missing two
    columns schema.sql declared and EVERY write became a D1 1101; a table-name
    check cannot see that, and a person's first real link is a bad place to."""
    now = 1_757_000_000_000
    fake = d1_with_a_working_connect_links(now)
    original = fake.__call__

    def bent(sql):
        out = original(sql)
        if sql.startswith('SELECT "token_handle"') and out:
            out[0]["toolkit"] = "something-else"
        return out

    code, _, sentence = M.mint_probe_link(bent, now)
    assert code == M.RED
    assert "toolkit" in sentence
    assert "nothing left behind" in sentence, "a wrong row is still cleaned up"


def test_a_missing_column_is_reported_as_a_missing_column():
    now = 1_757_000_000_000
    fake = d1_with_a_working_connect_links(now)
    original = fake.__call__

    def bent(sql):
        out = original(sql)
        if sql.startswith('SELECT "token_handle"') and out:
            out[0].pop("completed_at")
        return out

    code, _, sentence = M.mint_probe_link(bent, now)
    assert code == M.RED
    assert "completed_at" in sentence and "1101" in sentence


def test_a_probe_row_left_behind_is_red_and_says_where_it_is():
    """A gate that leaves rows in production is a gate somebody turns off — and
    an undeleted connect_links row is one nobody can account for later."""
    now = 1_757_000_000_000
    fake = d1_with_a_working_connect_links(now)
    original = fake.__call__

    def stuck(sql):
        if sql.startswith("DELETE"):
            raise M.D1Unavailable("no write permission")
        return original(sql)

    code, _, sentence = M.mint_probe_link(stuck, now)
    assert code == M.RED
    assert "by hand" in sentence


def test_a_delete_that_quietly_deletes_nothing_is_caught():
    """The DELETE is not believed, it is CHECKED. A statement that reports
    success and removes nothing — a scoping typo, a replica, a CHECK — would
    otherwise leave a row in production under a green leg, which is the
    'measured and it was fine' shape that gates exist to stop."""
    now = 1_757_000_000_000
    fake = d1_with_a_working_connect_links()
    original = FakeD1.__call__

    def keeps_it(sql):
        if sql.startswith("DELETE"):
            return []          # reports success, removes nothing
        return original(fake, sql)

    code, _, sentence = M.mint_probe_link(keeps_it, now)
    assert code == M.RED
    assert "still there" in sentence and "by hand" in sentence


def test_an_insert_that_fails_is_red_not_unproven():
    """A refused INSERT is the exact failure a real link would hit. We measured
    it; it is red."""
    def refuses(sql):
        raise M.D1Unavailable("D1_ERROR: no such column: completed_at")

    code, _, sentence = M.mint_probe_link(refuses, 1_757_000_000_000)
    assert code == M.RED
    assert "did NOT land" in sentence


def test_read_only_leaves_the_write_leg_unproven_rather_than_green():
    code, rows = M.run(read_only=True, http=a_deployed_worker(),
                       sql=FakeD1(tables=M.TABLES, connections={"rows_n": 1, "owners_n": 1}),
                       vendor=vendor_answering(), credential="an-owner-token")
    assert rows[3][0] == M.INFO
    assert code == M.UNPROVEN, "a leg that was not run does not pass"


def test_the_write_leg_is_not_attempted_when_its_table_is_missing():
    fake = FakeD1(tables=["connections"])
    code, rows = M.run(http=http_answering(*LIVE_404), sql=fake, vendor=vendor_answering())
    assert rows[3][0] == M.INFO
    assert "connect_links does not exist" in rows[3][2]
    assert not any(s.startswith("INSERT") for s in fake.statements)


# ===========================================================================
# LEG 7 — the page renders, and it goes nowhere
# ===========================================================================
# A page that draws is not a page that works. This is the leg that was missing
# on 2026-09-06 when the board read 5 PASS over a link that leads to a dead end.

TOKEN = "A" * M.TOKEN_CHARS
PAGE_URL = f"https://api.anticipy.ai/c/{TOKEN}"


def test_the_measured_sign_in_page_carries_no_way_in():
    """THE ANCHOR, ASSERTED UNIQUE BEFORE IT IS USED. The code path appears
    exactly once in the control page and exactly zero times in the sign-in page
    production served on 2026-09-06 — so a scan that finds nothing on the second
    is finding nothing because there is nothing, and a scan that finds nothing on
    the first is broken. Without this assertion the two tests below could both be
    passing over a regex that stopped matching."""
    _, _, page = sign_in_page(TOKEN)
    _, _, control = code_page(TOKEN)
    assert control.count(f"/c/{TOKEN}/code") == 1
    assert page.count(f"/c/{TOKEN}/code") == 0
    assert "<a" not in page and "<form" not in page, "no anchor, no form: a dead end"


def test_a_dead_end_is_red_and_says_where_the_way_in_already_lives():
    """Measured against production on 2026-09-06 at 06:17 UTC. The person taps
    the link in the text, is told to sign in in a browser, and is given nothing
    to tap. /c/{token}/code exists one path segment away, serves "Get a code by
    text", and is the entire reason routes/connect_auth.ts was written."""
    _, _, page = sign_in_page(TOKEN)
    _, _, control = code_page(TOKEN)
    code, mark, sentence = M.leg_way_in("connect-page", 401, PAGE_URL, page, TOKEN,
                                        f"{PAGE_URL}/code", control)
    assert code == M.RED
    assert "DEAD END" in sentence
    assert "connect_auth.ts" in sentence


def test_a_control_on_the_page_is_the_only_green():
    _, _, page = sign_in_page(TOKEN, way_in=True)
    _, _, control = code_page(TOKEN)
    assert M.leg_way_in("connect-page", 401, PAGE_URL, page, TOKEN,
                        f"{PAGE_URL}/code", control)[0] == M.GREEN


def test_a_scan_that_finds_nothing_on_the_control_page_is_unproven():
    """THE CONTROL, and the reason this leg cannot cry wolf. If the scan comes
    back empty on a page whose own form posts to exactly the path being looked
    for, the SCAN is what failed. A red leg produced by a broken instrument is
    worse than no leg: it teaches its reader to stop believing the board."""
    _, _, page = sign_in_page(TOKEN)
    code, _, sentence = M.leg_way_in("connect-page", 401, PAGE_URL, page, TOKEN,
                                     f"{PAGE_URL}/code",
                                     "<body><h1>Get a code by text</h1></body>")
    assert code == M.UNPROVEN
    assert "SCAN is what failed" in sentence


@pytest.mark.parametrize("target,counts", [
    (f'href="/c/{TOKEN}/code"', True),                              # absolute path
    (f'href="https://api.anticipy.ai/c/{TOKEN}/code"', True),       # fully qualified
    (f'href="https://anticipy.ai/c/{TOKEN}/code"', True),           # the apex, also ours
    ('action="code"', True),                                        # relative, from the page
    (f'href="https://elsewhere.example/c/{TOKEN}/code"', False),    # NOT ours
    (f'href="/c/{"B" * M.TOKEN_CHARS}/code"', False),               # another link's token
    (f'href="/c/{TOKEN}"', False),                                  # the page itself
    (f'href="/c/{TOKEN}/go"', False),                               # the tap, not the way in
])
def test_what_counts_as_a_way_in(target, counts):
    """Resolved as a browser would resolve it, and then held to one rule the
    product states outright: EVERY LINK IS OURS. A button pointing off our own
    hosts is not a way in, it is a way out."""
    page = f"<body><h1>Sign in to finish</h1><a {target}>go</a></body>"
    found = M.code_controls(f"{PAGE_URL}/code" if "action=" in target else PAGE_URL,
                            page, TOKEN)
    assert bool(found) is counts, found


def test_a_page_that_is_not_the_sign_in_page_is_not_this_legs_business():
    """Leg 7 measures the ONE page a signed-out person lands on. An expired or
    already-used page is a different state with a different copy, and reading it
    as a dead end would be red on a Worker that is behaving correctly."""
    assert M.leg_way_in("connect-page", 410, PAGE_URL, "<body>gone</body>", TOKEN,
                        f"{PAGE_URL}/code", code_page(TOKEN)[2])[0] == M.UNPROVEN
    assert M.leg_way_in("route-missing", 404, PAGE_URL, "", TOKEN, None, None)[0] == M.UNPROVEN
    assert M.leg_way_in("unwired", 503, PAGE_URL, "", TOKEN, None, None)[0] == M.UNPROVEN


def test_the_control_page_is_only_ever_read_never_posted_to():
    """POST /c/{token}/code TEXTS A CODE TO A REAL PERSON'S PHONE. It is rate
    limited per link and per owner, so a gate that posted would burn somebody's
    budget and make their phone buzz on every overnight run. This one GETs, and
    nothing else."""
    worker = a_deployed_worker()
    M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
          vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    code_requests = [r for r in worker.seen if r["path"].endswith("/code")]
    assert code_requests, "the control page was never fetched"
    assert all(r["method"] == "GET" for r in code_requests)
    assert all(not r["headers"].get("Authorization") for r in code_requests)


def test_the_control_page_is_asked_for_the_same_token_as_the_page():
    """A control fetched for a different token would carry a control pointing at
    a different link, and the scan would calibrate on something the sign-in page
    could never have contained."""
    worker = a_deployed_worker()
    M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
          vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    tokens = {r["path"].split("/")[2] for r in worker.seen if r["path"].startswith("/c/")}
    assert len(tokens) == 1, tokens


def test_the_page_is_fetched_once_per_run_and_never_with_a_credential():
    """connect.ts settles the session before it looks anything up, so an
    anonymous probe cannot read, spend or disturb anybody's link. A probe with a
    credential would be measuring a signed-in path that no texted link ever
    takes."""
    worker = a_deployed_worker()
    M.run(http=worker, sql=FakeD1(tables=M.TABLES), read_only=True,
          vendor=vendor_answering(), owner="sxkotd1h02qb6gw",
          credential="an-owner-token")
    page_requests = [r for r in worker.seen
                     if r["path"].startswith("/c/") and not r["path"].endswith("/code")]
    assert len(page_requests) == 1
    assert page_requests[0]["method"] == "GET"
    assert not page_requests[0]["headers"].get("Authorization")


# ===========================================================================
# LEG 8 — the vendor key
# ===========================================================================

def test_the_live_vendor_answer_is_green():
    """Measured 2026-09-06: 201, a 16-character session id,
    config.manage_connections.enabled false, and five tools, none of them the
    connection tool."""
    code, _, sentence = M.leg_vendor({"status": 201, "session_id_len": 16,
                                      "manage_connections": False,
                                      "connection_tool_present": False})
    assert code == M.GREEN
    assert "201" in sentence


@pytest.mark.parametrize("answer, why", [
    ({"status": 401, "session_id_len": 0, "manage_connections": None,
      "connection_tool_present": None}, "the key does not authenticate"),
    ({"status": 201, "session_id_len": 0, "manage_connections": False,
      "connection_tool_present": False}, "201 with no session id"),
    ({"status": 201, "session_id_len": 16, "manage_connections": True,
      "connection_tool_present": False}, "the config says the connection tool is ON"),
    ({"status": 201, "session_id_len": 16, "manage_connections": False,
      "connection_tool_present": True}, "the connection tool is in the tool list"),
    ({"status": 201, "session_id_len": 16, "manage_connections": None,
      "connection_tool_present": None}, "nothing confirms the connection tool is off"),
])
def test_a_session_the_worker_would_refuse_is_red(answer, why):
    """provider.ts refuses each of these before caching the session, so no link
    can be minted with it. A gate that called them green would be green over a
    session production throws on."""
    assert M.leg_vendor(answer)[0] == M.RED, why


def test_the_vendor_answer_is_read_where_the_vendor_puts_it():
    """`config.manage_connections`, not a root key — the shape measured against
    the live vendor. Reading the wrong place answers None, and None with a None
    tool list is a refusal, so this parser being wrong turns a healthy key red."""
    body = json.dumps({
        "session_id": "ts_hkC1gYqE8Nsv",
        "config": {"user_id": "sxkotd1h02qb6gw",
                   "manage_connections": {"enabled": False,
                                          "enable_connection_removal": True}},
        "tool_router_tools": ["COMPOSIO_MULTI_EXECUTE_TOOL", "COMPOSIO_SEARCH_TOOLS"],
    })
    answer = M._vendor_answer(201, body)
    assert answer["manage_connections"] is False
    assert answer["connection_tool_present"] is False
    assert answer["session_id_len"] == len("ts_hkC1gYqE8Nsv")
    assert M.leg_vendor(answer)[0] == M.GREEN


def test_the_connection_tool_is_matched_by_identifier():
    body = json.dumps({"session_id": "x", "config": {},
                       "tool_router_tools": [M.MANAGE_CONNECTIONS_TOOL]})
    assert M._vendor_answer(201, body)["connection_tool_present"] is True


def test_the_session_call_is_the_one_provider_ts_makes(monkeypatch):
    """Same body, same header, same spelling. `{"enabled": false}` is a 400 at
    the vendor and a bare boolean is a 400; sending something else would make
    this leg evidence about a request the Worker never makes."""
    seen = {}

    class _Res:
        status = 201

        def read(self):
            return json.dumps({"session_id": "abc", "config": {
                "manage_connections": {"enabled": False}}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(req, timeout=None):
        seen["url"] = req.full_url
        seen["headers"] = {k.lower(): v for k, v in req.headers.items()}
        seen["body"] = json.loads(req.data.decode())
        return _Res()

    answer = M.vendor_session("secret-key-value", "sxkotd1h02qb6gw", opener=opener)
    assert seen["url"].endswith("/tool_router/session")
    assert seen["headers"]["x-api-key"] == "secret-key-value"
    assert seen["body"] == {"user_id": "sxkotd1h02qb6gw",
                            "manage_connections": {"enable": False}}
    # The key and the session id are the two things that must never reach a log.
    assert "secret-key-value" not in json.dumps(answer)
    assert "abc" not in json.dumps(answer)


def test_no_key_here_is_unproven_and_says_it_measured_this_environment(monkeypatch):
    """Two different sentences that must never be swapped: 'the key is dead'
    and 'this machine has no key'. And the leg says WHOSE key it measured —
    the one in this environment, which is not necessarily the secret bound to
    the deployed Worker. On 2026-09-06 those differed: the key here answers 201
    and `wrangler secret list` for anticipy-api carries no COMPOSIO_API_KEY at
    all, so a leg that read as 'production can reach the vendor' would be
    false."""
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    _, rows = M.run(http=http_answering(*LIVE_404), sql=FakeD1(),
                    vendor=vendor_answering())
    assert rows[7][0] == M.INFO
    assert "not asked" in rows[7][2]

    _, rows = M.run(http=http_answering(*LIVE_404), sql=FakeD1(),
                    vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    monkeypatch.setenv("COMPOSIO_API_KEY", "k")
    _, rows = M.run(http=http_answering(*LIVE_404), sql=FakeD1(),
                    vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    assert rows[7][0] == M.OK
    assert "this environment" in rows[7][2], "whose key was measured must be on the screen"


def test_a_vendor_that_cannot_be_reached_is_unproven_not_a_verdict():
    def dead(key, owner):
        raise M.VendorUnavailable("URLError")

    code, rows = M.run(http=http_answering(*LIVE_404), sql=FakeD1(), vendor=dead,
                       owner="sxkotd1h02qb6gw")
    assert rows[7][0] == M.INFO
    assert "network" in rows[7][2]


def test_a_name_or_a_uuid_is_refused_as_an_owner():
    """The failure this whole feature is shaped around: `user_id` was `omar`,
    a name, and one operator's mailbox served everybody. ANTICIPY_OWNER_ID in
    this tree is a UUID, not an owner row id, so a gate that fell back to it
    would ask the vendor about a person who does not exist and report the
    answer as a verdict about the key."""
    for bad in ("omar", "jose@anticipy.ai", "A12D860F-C4C9-4AA2-AB77-9EECB9098F76"):
        _, rows = M.run(http=http_answering(*LIVE_404), sql=FakeD1(),
                        vendor=vendor_answering(), owner=bad)
        assert rows[7][0] == M.INFO
        assert "owner ROW id" in rows[7][2]


# ===========================================================================
# LEG 9 — the one that must not cry wolf
# ===========================================================================

def test_nobody_connected_yet_is_unproven_and_never_red():
    """The day before the first person connects, zero is the correct state of a
    working feature. A red leg here would teach its reader to skip this gate,
    and a skipped gate is how the ears stayed deaf for thirty hours next to a
    green board."""
    code, _, sentence = M.leg_connected(0, 0)
    assert code == M.UNPROVEN
    assert "not a failure" in sentence


def test_one_connected_owner_turns_it_green():
    assert M.leg_connected(1, 2)[0] == M.GREEN


def test_an_uncountable_connections_table_claims_nothing():
    code, _, sentence = M.leg_connected(None, None)
    assert code == M.UNPROVEN
    assert "0" not in sentence


# ===========================================================================
# THE ROLL-UP
# ===========================================================================

def test_the_measured_state_of_2026_09_06_at_0408():
    """The whole chain as production stood the morning this gate was written:
    nothing deployed, no tables, a working vendor key, nothing connected."""
    code, rows = M.run(http=FakeWorker(page=LIVE_404, routes=LIVE_404,
                                       webhook=lambda _h: LIVE_404), sql=FakeD1(),
                       vendor=vendor_answering(), owner="sxkotd1h02qb6gw")
    assert marks(rows) == [
        M.BAD,    # 1 the six routes: the router's generic 404
        M.BAD,    # 2 zero of four tables
        M.INFO,   # 3 the catalog cannot be asked over an undeployed route
        M.INFO,   # 4 nothing to write a link into
        M.BAD,    # 5 /c/ answers the generic 404 too
        M.INFO,   # 6 no route to ask about the wiring
        M.INFO,   # 7 no page to look at
        M.OK,     # 8 the vendor key
        M.INFO,   # 9 the connections table could not be counted
        M.BAD,    # 10 the webhook route is not deployed either
        M.INFO,   # 11 connect_nudges could not be counted either
    ], details(rows)
    assert code == M.RED


def test_the_measured_state_of_2026_09_06_at_0617():
    """AND THE STATE TWELVE HOURS LATER, which is the one this gate was extended
    for. Everything is deployed, the tables are there, the vendor answers — and
    the page a person lands on has nothing on it to tap, so leg 7 is red while
    every leg the old six-leg gate had is green. This test is the whole reason
    leg 7 exists: without it the board reads 5 PASS / 1 UNPROVEN over a feature
    nobody can use.

    Production was repaired at 07:20 the same day and leg 7 went green against
    live. This test keeps measuring the 06:17 shape, because a leg that has only
    ever been seen to say PASS is a leg nobody has watched work."""
    now = 1_757_000_000_000
    code, rows = M.run(http=FakeWorker(), sql=d1_with_a_working_connect_links(now),
                       vendor=vendor_answering(), owner="sxkotd1h02qb6gw", now_ms=now)
    assert marks(rows)[:2] == [M.OK, M.OK]
    assert marks(rows)[2] == M.INFO, "no owner credential on this machine"
    assert marks(rows)[4:6] == [M.OK, M.OK], "the page is served and wired"
    assert marks(rows)[6] == M.BAD, "and it is a dead end"
    assert code == M.RED


def test_everything_working_is_the_only_way_to_exit_zero():
    now = 1_757_000_000_000
    code, rows = M.run(http=a_deployed_worker(now_ms=now),
                       sql=d1_with_a_working_connect_links(now),
                       vendor=vendor_answering(), owner="sxkotd1h02qb6gw",
                       credential="an-owner-token", now_ms=now,
                       webhook=a_webhook_secret())
    assert marks(rows) == [M.OK] * 11, details(rows)
    assert code == M.GREEN


def test_one_unmeasured_leg_is_enough_to_withhold_green():
    """A working system with nobody connected yet exits 2, not 0. The finish
    line is a person, and no amount of green plumbing is one."""
    now = 1_757_000_000_000
    fake = d1_with_a_working_connect_links(now)
    fake.connections = {"rows_n": 0, "owners_n": 0}
    code, rows = M.run(http=a_deployed_worker(), sql=fake, vendor=vendor_answering(),
                       owner="sxkotd1h02qb6gw", credential="an-owner-token", now_ms=now)
    assert code == M.UNPROVEN
    assert marks(rows)[8] == M.INFO


# ===========================================================================
# LEG 11 — is anybody actually being ASKED
# ===========================================================================
# Legs 1-10 all measure whether somebody who WANTS to connect an app can. This
# one measures the other half of the spec — the half that was written, tested
# and called by nothing: does anything ever OFFER?
#
# The four states below all look identical from outside (no text arrived) and
# every one of them is a different repair. That is the leg.


def _run_with(asked=None, due=0, **over):
    """One run against a working deployment, with leg 11's two counts set."""
    now = over.pop("now_ms", 1_757_000_000_000)
    fake = FakeD1(tables=M.TABLES, connections={"rows_n": 2, "owners_n": 1},
                  asked=asked, due=due)
    return M.run(http=a_deployed_worker(now_ms=now), sql=fake,
                 vendor=vendor_answering(), owner="sxkotd1h02qb6gw",
                 credential="an-owner-token", now_ms=now,
                 webhook=a_webhook_secret(), **over), fake


def test_an_ask_row_on_live_d1_is_the_only_thing_that_turns_leg_11_green():
    """A ROW IS THE ONLY PROOF THAT SURVIVES A STALE DEPLOY. Production has
    served old code at least twice (HARNESS-LAWS law 3), so a gate that read the
    repo's own wrangler.jsonc and called it green would report the checkout, not
    the deployment. `connect_nudges` rows were written by the Worker that is
    actually running, on a tick that actually fired."""
    now = 1_757_000_000_000
    (code, rows), _ = _run_with(asked={"asked_n": 2, "newest": float(now - 7_200_000)},
                                now_ms=now)
    assert marks(rows)[10] == M.OK, details(rows)
    assert "asks are going out" in rows[10][2]
    assert code == M.GREEN


def test_nobody_due_is_unproven_not_green_and_not_red():
    """THE SAME RULE AS LEG 9, and the reason is the same. The day before the
    first person is asked, zero is the correct state of a working feature; red
    would train the reader to skip the board, and green would let a feature
    whose senses were never wired read as done. It is neither."""
    (code, rows), _ = _run_with(asked={"asked_n": 0, "newest": None}, due=0)
    assert marks(rows)[10] == M.INFO, details(rows)
    assert code == M.UNPROVEN
    assert "nobody is due" in rows[10][2]


def test_nobody_due_names_the_two_doors_that_would_change_it():
    """A gate that says "nothing to report" teaches nothing. This one names the
    two ingest doors that produce a MOMENT, because those are the two pieces of
    work between here and an ask."""
    (_code, rows), _ = _run_with(asked={"asked_n": 0, "newest": None}, due=0)
    for word in ("observer", "said", "signals.ts"):
        assert word in rows[10][2], rows[10][2]


def test_owners_due_and_nothing_ever_sent_is_red_and_counts_them():
    """The state that must never read as quiet: the evidence is there, the
    schedule is there, the wiring is there, and not one text has gone."""
    (code, rows), _ = _run_with(asked={"asked_n": 0, "newest": None}, due=6)
    assert marks(rows)[10] == M.BAD, details(rows)
    assert "6 owner(s)" in rows[10][2]
    assert code == M.RED


def test_a_connect_nudges_table_that_cannot_be_counted_claims_nothing():
    """`asked is None` is "the database did not answer", which is NOT zero. The
    two are opposite facts and conflating them is how a missing migration reads
    as a quiet night."""
    (code, rows), _ = _run_with(asked=None)
    assert marks(rows)[10] == M.INFO, details(rows)
    assert code == M.UNPROVEN
    # AND THE SENTENCE HAS TO SAY WHICH. `nobody-due` is also UNPROVEN and also
    # INFO, so a mark alone cannot tell the two apart — and they are opposite
    # facts: one is a quiet night, the other is a database that did not answer.
    # This assertion exists because the mutation that collapses them survived a
    # check on the mark alone.
    assert M.ask_state(True, True, 0, None) == "unreadable"
    assert "could not be counted" in rows[10][2], rows[10][2]
    assert "nobody is due" not in rows[10][2], rows[10][2]


def test_leg_11_is_not_attempted_when_its_table_is_missing():
    """No connect_nudges on live D1 means leg 2 already said so. Leg 11 must not
    then report a count of zero as though it had asked."""
    fake = FakeD1(tables=[t for t in M.TABLES if t != "connect_nudges"])
    code, rows = M.run(http=a_deployed_worker(), sql=fake, vendor=vendor_answering(),
                       owner="sxkotd1h02qb6gw", read_only=True)
    assert marks(rows)[10] == M.INFO, details(rows)
    assert not any("asked_n" in st for st in fake.statements), \
        "the gate counted asks over a table leg 2 said was missing"


DUE_TS = os.path.join(REPO, "migration", "workers", "src", "connections", "due.ts")


def _due_source():
    return open(DUE_TS, encoding="utf-8").read()


def test_the_due_count_is_due_ts_own_statement_and_not_a_copy_of_it():
    """THE FINDING OF 2026-09-06, PINNED SO IT CANNOT RETURN.

    `DUE_COUNT_SQL` was a hand-written copy of `candidateSql()`. due.ts deleted
    `AND s."weight" > 0` (a predicate no code path could make false) and
    replaced `WHERE "pick" = 1` with a per-owner row budget; the copy did not
    move, so the one leg every fixer names as the law-3 proof was counting
    owners against a shape the shipped code no longer had.

    There is no copy now. The gate reads due.ts's own statement out of the file
    and binds its placeholders, so the two cannot disagree — the only failure
    left is a read that stops working, and that one is UNPROVEN by
    construction rather than a wrong number."""
    statement = M.due_statement(_due_source())
    assert statement, "due.ts's candidate statement could not be read at all"
    built = M.due_count_sql(M.NOW_FOR_SELF_TEST)
    assert built and statement.split("${")[0].strip()[:40] in built, built
    # And the mirror is DELETED rather than renamed: a module-level SQL constant
    # for this query is the thing that drifted, and its absence is the fix.
    assert not hasattr(M, "DUE_COUNT_SQL")


def test_a_comment_quoting_a_predicate_is_not_the_predicate():
    """WHY THE OLD DRIFT CHECK PASSED OVER THE DRIFT, which is the part worth
    keeping. It asserted `clause in due_ts` over the WHOLE FILE — and due.ts
    still carries the sentence "This file used to write `AND s."weight" > 0`
    and call that the aliveness test". A substring check over a source file
    cannot tell code from prose, so the book that had changed read as agreeing
    with the copy, in the words of its own changelog.

    This is that shape, driven: a due.ts whose comment quotes a predicate its
    statement does not carry."""
    prose_only = M._fake_due_ts("")
    assert 's."weight" > 0' in prose_only, "the fixture is not the shape being tested"
    assert "weight" not in (M.due_statement(prose_only) or "weight"), \
        "the reader picked a predicate out of a COMMENT, which is how the drift hid"
    # THE CONTROL, the other way round: put the predicate in the STATEMENT and
    # the gate's SQL carries it, unasked. That is what "not a mirror" means.
    in_the_sql = M._fake_due_ts('AND s."weight" > 0\n')
    assert 's."weight" > 0' in (M.due_statement(in_the_sql) or "")
    # And today's real statement carries no weight BOUND — it selects the column
    # and orders by it, which is not the same thing and is why this asks for a
    # comparator rather than for the word. due.ts's ALIVE section says why: the
    # one boundary is `ALIVE_WEIGHT_FLOOR` and it is stated once, in TypeScript.
    live = M.due_statement(_due_source()) or ""
    assert re.search(r'"weight"\s*(?:<=|>=|<>|=|<|>)', live) is None, \
        "due.ts's statement has grown a weight predicate again — read its ALIVE section"


def test_the_gate_binds_by_name_and_never_by_the_order_of_a_bind_call():
    """due.ts binds `?${pNow}`, `?${pCutoff}`, `?${pRows}`, `?${pCap}` and
    `${inList}` positionally, in ONE call, in an order this gate cannot see.
    Binding by name means a reordered `.bind(...)` in due.ts cannot silently
    hand this gate a cutoff where it expected a clock — which would open the
    7-day cap for the whole table and report it as owners being due."""
    now = M.NOW_FOR_SELF_TEST
    built = M.due_count_sql(now)
    cutoff = now - M.GLOBAL_ASK_INTERVAL_DAYS * 86_400_000
    assert str(now) in built and str(cutoff) in built
    assert "${" not in built and not re.search(r"\?\d", built), built
    assert "'observer', 'said'" in built
    # A placeholder this gate has no value for refuses the whole count rather
    # than running a statement it does not fully understand against production.
    assert M.due_count_sql(now, source=M._fake_due_ts('AND s."x" > ?${pMystery}\n')) is None


def test_a_due_ts_that_names_other_moments_refuses_rather_than_undercounting():
    """The `IN (…)` list is the gate's own, so a third moment source in due.ts
    would have the gate counting fewer owners than the code considers — and
    fewer owners is a quiet night, which is the one answer nobody investigates.
    It refuses instead, and `due-unknown` is UNPROVEN."""
    third = M._fake_due_ts("").replace(
        '  said: "user_named_it",\n', '  said: "user_named_it",\n  mx: "in_task",\n')
    assert M.due_moment_sources(third) == ("observer", "said", "mx")
    assert M.due_count_sql(M.NOW_FOR_SELF_TEST, source=third) is None
    assert M.ask_state(True, True, None, 0) == "due-unknown"
    # THE CONTROL: the real file's moments ARE the gate's, so the refusal above
    # is about disagreement and not about the reader being broken.
    assert M.due_moment_sources(_due_source()) == M.MOMENT_SOURCES == ("observer", "said")


def test_an_unreadable_checkout_costs_the_count_and_never_invents_one():
    """Every way the reader can fail lands on `None`, and `None` is
    `due-unknown` — never zero. Zero is "nobody is due", which is a claim about
    production; this is a claim about this checkout."""
    now = M.NOW_FOR_SELF_TEST
    assert M.due_count_sql(now, root=os.path.join(REPO, "overnight")) is None
    assert M.due_count_sql(now, source="// due.ts, but not as this reader knows it") is None
    assert M.due_statement(None) is None
    assert M.due_moment_sources(None) is None
    assert M.bind_due_statement(None, sources=("observer",), now_ms=now, cutoff_ms=0) is None


def test_the_count_is_over_owners_because_the_cap_is_per_owner():
    """`GLOBAL_ASK_INTERVAL_DAYS` is one ask per OWNER per seven days across all
    apps, so two candidate rows for one owner are one candidate. The statement
    hands back rows; the count this leg reads is over distinct `user_id`."""
    built = M.due_count_sql(M.NOW_FOR_SELF_TEST)
    assert 'SELECT DISTINCT "user_id"' in built and "count(*) AS due_n" in built
    # THREE BOOKS on the interval itself: the gate computes the cutoff from its
    # own constant, and nudge.ts is where the number actually lives.
    nudge = open(os.path.join(REPO, "migration", "workers", "src", "connections",
                              "nudge.ts"), encoding="utf-8").read()
    assert ("export const GLOBAL_ASK_INTERVAL_DAYS = %d;"
            % M.GLOBAL_ASK_INTERVAL_DAYS) in nudge, \
        "nudge.ts retuned the global ask cap and this gate's cutoff did not move"


def test_the_red_says_which_owners_it_counted_and_what_it_could_not_see():
    """The number is an UPPER BOUND on `due()`: everything `dueCandidates` does
    after the statement — the owner-id check, the empty-toolkit drop, the
    source-names-no-moment drop, the decayed-weight floor, the dedupe, the cap —
    can only remove owners. So zero PROVES a quiet night, and above zero does
    not prove a break. The red has to say so, or it sends a reader hunting a
    failure that is really six months of silence."""
    red = M.leg_ask(True, True, 4, 0, None, M.NOW_FOR_SELF_TEST)
    assert red[0] == M.RED and "4 owner(s)" in red[2]
    assert "decayed-weight floor" in red[2], red[2]
    quiet = M.leg_ask(True, True, 0, 0, None, M.NOW_FOR_SELF_TEST)
    assert quiet[0] == M.UNPROVEN
    assert "only DROPS candidates" in quiet[2], quiet[2]


def test_the_two_literals_leg_11_reads_out_of_the_repo_still_match():
    """A RED LEG FROM A BROKEN INSTRUMENT IS WORSE THAN NO LEG. Leg 11 explains
    a zero by reading two strings out of this checkout — the cron schedule and
    the wiring call — and either of them silently ceasing to match would have
    the gate reporting "not registered" forever while production ran it."""
    registered, wired = M.ask_config(REPO)
    assert registered is True, "wrangler.jsonc no longer registers " + M.ASK_CRON
    assert wired is True, "src/cron.ts no longer calls " + M.WIRING_CALL
    # THE CONTROL: the same reader over a directory with neither file must say
    # "unreadable" and not "missing" — those are different claims.
    assert M.ask_config(os.path.join(REPO, "overnight")) == (None, None)


def test_the_config_half_can_never_produce_a_green_on_its_own():
    """The repo agreeing with itself is not evidence about production. Whatever
    wrangler.jsonc and cron.ts say, leg 11 without a row is never a pass."""
    for registered in (True, False, None):
        for wired in (True, False, None):
            code, _mark, _s = M.leg_ask(registered, wired, 0, 0, None,
                                        M.NOW_FOR_SELF_TEST)
            assert code != M.GREEN, (registered, wired)


def test_rows_outrank_a_checkout_that_disagrees_with_them():
    """And the other direction: a working deployment plus a checkout that has
    since removed the schedule is still green, because the rows happened."""
    assert M.leg_ask(False, False, 0, 5, None, M.NOW_FOR_SELF_TEST)[0] == M.GREEN


def test_red_outranks_unproven():
    assert M.overall([M.GREEN, M.UNPROVEN, M.RED]) == M.RED
    assert M.overall([M.GREEN, M.UNPROVEN]) == M.UNPROVEN
    assert M.overall([M.GREEN, M.GREEN]) == M.GREEN


def test_the_self_test_covers_every_leg_offline():
    assert M.self_test() == 0


# ===========================================================================
# THE LOCAL PROOF — the write leg, run against a REAL D1
# ===========================================================================
# Leg 4's statements had never run anywhere when this gate was written, because
# the four tables do not exist on production. A write path that has only ever
# been exercised against a Python dict is a claim, and this file is a gate.
#
# So: stand the four tables up in a scratch LOCAL D1 from schema.sql's own
# section 5, and drive the real `mint_probe_link` through the real `d1_query`
# and the real wrangler JSON. It proves the SQL parses, the CHECK constraints
# accept the probe row, the read-back comparison holds against real column
# types, and the row is gone afterwards. It is NOT a law-3 proof and does not
# pretend to be one: production is measured by running the gate.

def _section5_ddl():
    """The four CREATE TABLE statements, taken from schema.sql rather than
    copied. A second copy of the DDL is a second book, and the two disagree the
    first time one is edited."""
    text = open(SCHEMA, encoding="utf-8").read()
    out = []
    for table in M.TABLES:
        m = re.search(r'CREATE TABLE IF NOT EXISTS "' + table + r'" \((.*?)\n\);',
                      text, re.S)
        assert m, f"schema.sql no longer declares {table}"
        # Comments are stripped because several of them contain semicolons, and
        # a statement runner that splits on ';' would cut one in half.
        body = "\n".join(
            line.split("--")[0].rstrip()
            for line in m.group(1).splitlines()
            if line.split("--")[0].strip())
        out.append(f'CREATE TABLE IF NOT EXISTS "{table}" (\n{body}\n)')
    return out


def test_schema_sql_still_declares_all_four_tables():
    ddl = _section5_ddl()
    assert len(ddl) == 4
    assert all("user_id" in d for d in ddl)


@pytest.mark.skipif(shutil.which("npx") is None, reason="no npx on this machine")
@pytest.mark.skipif(not os.path.exists(WRANGLER_CONFIG), reason="no wrangler config")
def test_the_mint_probe_lands_in_a_real_d1(tmp_path):
    scratch = str(tmp_path / "d1state")

    def local(sql):
        return M.d1_query(sql, remote=False, config=WRANGLER_CONFIG,
                          persist_to=scratch, timeout=180)

    try:
        local("; ".join(_section5_ddl()))
    except M.D1Unavailable as exc:
        pytest.skip(f"local D1 is unavailable here: {exc}")

    present = {r["name"] for r in local(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ("
        + ", ".join(f"'{t}'" for t in M.TABLES) + ")")}
    assert present == set(M.TABLES)
    assert M.leg_tables(present, "scratch")[0] == M.GREEN

    now = int(1_757_000_000_000)
    code, _, sentence = M.mint_probe_link(local, now)
    assert code == M.GREEN, sentence

    left = local('SELECT count(*) AS n FROM "connect_links"')
    assert int(float(left[0]["n"])) == 0, "the probe row was not cleaned up"


@pytest.mark.skipif(shutil.which("npx") is None, reason="no npx on this machine")
@pytest.mark.skipif(not os.path.exists(WRANGLER_CONFIG), reason="no wrangler config")
def test_the_due_count_statement_runs_on_a_real_d1(tmp_path):
    """THE STATEMENT LEG 11 POINTS AT PRODUCTION HAS NEVER BEEN RUN ANYWHERE.

    It is due.ts's own text — a `ROW_NUMBER() OVER (PARTITION BY …)` inside two
    nested subqueries — wrapped in a count this gate composes. That wrapper is
    the one thing in it nobody else executes, and "it should parse" is exactly
    the sentence this file exists to refuse. So the four tables are stood up in
    a scratch LOCAL D1 from schema.sql's own DDL, seeded with one row for each
    reason a candidate is excluded, and the real statement is run through the
    real `d1_query`.

    NOT A LAW-3 PROOF and it does not pretend to be one: production is measured
    by running the gate. This proves the instrument works before it is pointed
    at anybody."""
    scratch = str(tmp_path / "d1due")

    def local(sql):
        return M.d1_query(sql, remote=False, config=WRANGLER_CONFIG,
                          persist_to=scratch, timeout=180)

    try:
        local("; ".join(_section5_ddl()))
    except M.D1Unavailable as exc:
        pytest.skip(f"local D1 is unavailable here: {exc}")

    now = M.NOW_FOR_SELF_TEST
    day = 86_400_000
    # Fifteen characters each, because the table CHECKs it — the one failure
    # this whole feature is shaped around is a connection bound to a name.
    due, connected, laddered, asked_recently, no_moment, snoozed = (
        "duexownerxaaaa1", "connxownerxaaa1", "levelxownerxaa1",
        "recentxownerxa1", "signalxownerxa1", "snoozexownerxa1")
    rows = []
    # THE ONE OWNER WHO IS DUE, and two rows for them, so the count proves it
    # counts OWNERS and not evidence. Two apps, neither of which is an app.
    rows += [(due, "quorbex", "observer"), (due, "vantorel", "said")]
    rows += [(connected, "quorbex", "observer")]        # already connected
    rows += [(laddered, "quorbex", "said")]             # end of the decline ladder
    rows += [(asked_recently, "quorbex", "observer")]   # inside the 7-day global cap
    rows += [(no_moment, "quorbex", "mx")]              # weight, but names no moment
    rows += [(snoozed, "quorbex", "observer")]          # mid-snooze
    local("; ".join(
        'INSERT INTO "app_usage_signals" ("user_id","toolkit","source","alias",'
        '"weight","last_seen_at") VALUES (\'%s\',\'%s\',\'%s\',\'\',3,%d)'
        % (who, app, src, now - day) for who, app, src in rows))
    local("; ".join([
        'INSERT INTO "connections" ("connected_account_id","user_id","toolkit","alias",'
        '"status","writes_enabled","last_used_at") '
        'VALUES (\'ca_local_probe\',\'%s\',\'quorbex\',\'\',\'connected\',0,NULL)'
        % connected,
        'INSERT INTO "connect_nudges" ("user_id","toolkit","state","level","snooze_until",'
        '"trigger","sent_at","acted_at","channel") '
        'VALUES (\'%s\',\'quorbex\',\'declined\',3,NULL,NULL,NULL,NULL,NULL)' % laddered,
        'INSERT INTO "connect_nudges" ("user_id","toolkit","state","level","snooze_until",'
        '"trigger","sent_at","acted_at","channel") '
        'VALUES (\'%s\',\'anotherapp\',\'asked\',0,NULL,NULL,%d,NULL,NULL)'
        % (asked_recently, now - day),
        'INSERT INTO "connect_nudges" ("user_id","toolkit","state","level","snooze_until",'
        '"trigger","sent_at","acted_at","channel") '
        'VALUES (\'%s\',\'quorbex\',\'declined\',1,%d,NULL,NULL,NULL,NULL)'
        % (snoozed, now + 14 * day),
    ]))

    statement = M.due_count_sql(now)
    assert statement, "the gate could not build the statement at all"
    counted = local(statement)
    assert int(float(counted[0]["due_n"])) == 1, (
        "the statement did not count exactly the one owner who is due: "
        + str(counted))

    # AND THE ANSWER DOES NOT DEPEND ON THE ROW BUDGET. `DUE_ROWS_PER_OWNER` is
    # 1 where due.ts binds 5, and the whole justification for that is that a
    # count over DISTINCT `user_id` cannot see the difference — an owner with
    # any candidate row has a `pick = 1` row. The owner who is due here holds
    # TWO apps, so a count that had slipped back to counting rows answers 2 at a
    # budget of 5 and 1 at a budget of 1.
    wide = M.due_count_sql(now, rows_per_owner=5)
    assert int(float(local(wide)[0]["due_n"])) == 1, (
        "the due count changed with the row budget, so it is counting evidence "
        "rows and not owners — and the 7-day cap is per OWNER")

    # THE CONTROL, so the 1 above is the query discriminating and not the seed
    # being thin: give the connected owner a second app nobody has connected and
    # the count moves. A statement that answered 1 either way would be measuring
    # nothing.
    local('INSERT INTO "app_usage_signals" ("user_id","toolkit","source","alias",'
          '"weight","last_seen_at") '
          'VALUES (\'%s\',\'vantorel\',\'observer\',\'\',3,%d)'
          % (connected, now - day))
    counted = local(statement)
    assert int(float(counted[0]["due_n"])) == 2, (
        "an owner whose OTHER app is connected was still excluded, so the "
        "connections anti-join is joined on the owner and not on the pair: "
        + str(counted))
