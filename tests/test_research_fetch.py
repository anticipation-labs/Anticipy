"""HANDS 1 — where the fetch LANDS, not where the string said it would go.

`is_researchable` reads a URL. It is a port of learn.js and it is now faithful
to it (tests/test_research_host.py), but faithful is the ceiling of what a URL
string can tell you, and this half of the product is not a browser:

  * `requests` FOLLOWS REDIRECTS by default. `https://a-real-help-page.example`
    passes every string check there is and can answer 302
    Location: http://169.254.169.254/latest/meta-data/. Every refusal in this
    module is applied to the first URL and none of them are applied to the one
    actually read.
  * A hostname is not an address. `localtest.me` and any domain an attacker
    controls resolve to 127.0.0.1 whenever its owner wants them to.
  * `run_research` fetched every URL its search backend returned WITHOUT
    calling `is_researchable` at all — `learn_procedure` filters through
    `rank_sources`, and the answer lane never did.

The laptop is not exposed to this: the extension has a browser, an origin, and
a user. The worker is a cloud host that answers on 169.254.169.254 with
credentials. So the fetch itself is guarded, on the ADDRESS it is about to
connect to, at every hop — which is the only place the question can honestly be
asked, and needs no pattern over anything.

The resolver is injected so none of this touches the network.
"""
import types

import pytest

import brain.research as research


class Resolver:
    """Stands in for socket.getaddrinfo: host -> the addresses it answers."""

    def __init__(self, table, boom=False):
        self.table = table
        self.boom = boom
        self.asked = []

    def __call__(self, host, port, *a, **kw):
        self.asked.append(host)
        if self.boom:
            raise OSError("no such host")
        addrs = self.table.get(host)
        if addrs is None:
            raise OSError("no such host")
        return [(2, 1, 6, "", (addr, port or 80)) for addr in addrs]


class FakeResponse:
    def __init__(self, status=200, body="<p>hello</p>", location=None,
                 content_type="text/html"):
        self.status_code = status
        self.text = body
        self.headers = {"content-type": content_type}
        if location:
            self.headers["location"] = location
        self.ok = 200 <= status < 400

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308) \
            and "location" in self.headers


class FakeRequests:
    def __init__(self, pages):
        self.pages = pages
        self.got = []
        self.kwargs = []

    def get(self, url, **kw):
        self.got.append(url)
        self.kwargs.append(kw)
        page = self.pages.get(url)
        if page is None:
            raise AssertionError(f"unexpected fetch: {url}")
        return page


PUBLIC = Resolver({"help.example.com": ["93.184.216.34"],
                   "evil.example.com": ["127.0.0.1"],
                   "cdn.example.com": ["93.184.216.34"],
                   "mapped.example.com": ["::ffff:127.0.0.1"],
                   "split.example.com": ["93.184.216.34", "10.0.0.5"]})


@pytest.fixture
def fake(monkeypatch):
    def install(pages):
        stub = FakeRequests(pages)
        monkeypatch.setattr(research, "requests", stub)
        return stub
    return install


# --------------------------------------------------------------------------
# A name is not an address
# --------------------------------------------------------------------------

def test_a_public_name_that_resolves_to_loopback_is_never_fetched(fake):
    stub = fake({})
    assert research.fetch_page("https://evil.example.com/x", resolver=PUBLIC) == ""
    assert stub.got == [], "the address was checked before the connection"


def test_a_public_name_that_resolves_to_an_ipv4_mapped_loopback_is_refused(fake):
    """`http://[::ffff:127.0.0.1]/` is loopback wearing an IPv6 hat, and BOTH
    string predicates — learn.js's and this module's port of it — return true
    for it. That divergence is not fixable in the port without breaking parity
    with the extension, and it does not need to be: the address check unwraps
    the mapping and the connection never happens."""
    stub = fake({})
    assert research.is_researchable("http://[::ffff:127.0.0.1]/") is True, (
        "if this ever becomes False the parity port has drifted from learn.js")
    assert research.fetch_page("http://[::ffff:127.0.0.1]/", resolver=PUBLIC) == ""
    assert research.fetch_page("https://mapped.example.com/x", resolver=PUBLIC) == ""
    assert stub.got == []


def test_one_bad_address_among_good_ones_refuses_the_whole_host(fake):
    """`requests` picks whichever address it likes. A host that answers with
    both a public and a private address is a host that sometimes connects to
    the private one, and "sometimes" is not a security property."""
    stub = fake({})
    assert research.fetch_page("https://split.example.com/x", resolver=PUBLIC) == ""
    assert stub.got == []


def test_a_host_that_does_not_resolve_is_a_missing_source_not_a_crash(fake):
    fake({})
    assert research.fetch_page("https://nowhere.example.com/x",
                               resolver=Resolver({}, boom=True)) == ""


def test_an_ordinary_page_is_still_read(fake):
    """A guard that only ever refuses is indistinguishable from a broken
    fetcher, and the research arm would go quiet rather than wrong."""
    stub = fake({"https://help.example.com/x": FakeResponse(body="<p>Open 9-5</p>")})
    assert "Open 9-5" in research.fetch_page("https://help.example.com/x",
                                             resolver=PUBLIC)
    assert stub.got == ["https://help.example.com/x"]


# --------------------------------------------------------------------------
# Every hop, not just the first
# --------------------------------------------------------------------------

def test_redirects_are_not_followed_by_the_library(fake):
    """Structural, and the most important assertion in this file: if
    `requests` follows the chain itself, every check below runs on a URL that
    was never fetched and the one that was is unexamined."""
    stub = fake({"https://help.example.com/x": FakeResponse()})
    research.fetch_page("https://help.example.com/x", resolver=PUBLIC)
    assert stub.kwargs[0].get("allow_redirects") is False


def test_a_redirect_to_the_metadata_endpoint_is_not_followed(fake):
    """The whole reason the address check cannot live only on the input URL."""
    stub = fake({"https://help.example.com/x": FakeResponse(
        status=302, location="http://169.254.169.254/latest/meta-data/")})
    assert research.fetch_page("https://help.example.com/x", resolver=PUBLIC) == ""
    assert stub.got == ["https://help.example.com/x"]


def test_a_redirect_to_a_name_that_resolves_privately_is_not_followed(fake):
    stub = fake({"https://help.example.com/x": FakeResponse(
        status=302, location="https://evil.example.com/admin")})
    assert research.fetch_page("https://help.example.com/x", resolver=PUBLIC) == ""
    assert stub.got == ["https://help.example.com/x"]


def test_a_relative_redirect_is_resolved_before_it_is_judged(fake):
    """`Location: /docs` is legal and common. Judging the raw header instead of
    the resolved URL is how a check passes on a string that is not a URL."""
    stub = fake({
        "https://help.example.com/x": FakeResponse(status=301, location="/docs"),
        "https://help.example.com/docs": FakeResponse(body="<p>Open 9-5</p>"),
    })
    assert "Open 9-5" in research.fetch_page("https://help.example.com/x",
                                             resolver=PUBLIC)
    assert stub.got == ["https://help.example.com/x",
                        "https://help.example.com/docs"]


def test_an_ordinary_cross_host_redirect_still_works(fake):
    stub = fake({
        "https://help.example.com/x": FakeResponse(
            status=302, location="https://cdn.example.com/x"),
        "https://cdn.example.com/x": FakeResponse(body="<p>Open 9-5</p>"),
    })
    assert "Open 9-5" in research.fetch_page("https://help.example.com/x",
                                             resolver=PUBLIC)


def test_a_redirect_loop_terminates(fake):
    stub = fake({"https://help.example.com/x": FakeResponse(
        status=302, location="https://help.example.com/x")})
    assert research.fetch_page("https://help.example.com/x", resolver=PUBLIC) == ""
    assert len(stub.got) <= research.MAX_FETCH_HOPS


def test_a_redirect_to_a_scheme_that_is_not_the_web_is_refused(fake):
    stub = fake({"https://help.example.com/x": FakeResponse(
        status=302, location="file:///etc/passwd")})
    assert research.fetch_page("https://help.example.com/x", resolver=PUBLIC) == ""


# --------------------------------------------------------------------------
# The answer lane fetched whatever the search backend handed it
# --------------------------------------------------------------------------

def test_run_research_does_not_read_a_page_the_arm_may_not_read():
    """`learn_procedure` filters its candidates through `rank_sources`.
    `run_research` did not filter at all — it read every result the backend
    returned, in order, including one pointing at the owner's machine."""
    read = []

    def fetcher(url):
        read.append(url)
        return "page text"

    class Brave:
        def search(self, query, count=5):
            return [{"title": "t", "url": u, "description": "d"} for u in (
                "http://169.254.169.254/latest/meta-data/",
                "https://help.example.com/hours",
                "http://2130706433:8090/admin",
            )]

    out = research.run_research("opening hours", brave=Brave(), fetcher=fetcher)
    assert out["ok"] is True
    assert read == ["https://help.example.com/hours"]
    assert "169.254" not in out["result"] and "2130706433" not in out["result"]
