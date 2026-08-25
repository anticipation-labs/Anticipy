"""HANDS 1 — an address is a value, not a spelling.

tests/test_research_shape_parity.py proves the server and the extension agree.
These prove the thing they agree ON, without node, so the property survives a
machine where the parity test skips itself.

The defect these were written for: `is_researchable` refused
`http://127.0.0.1:8090/admin` and allowed `http://2130706433:8090/admin` — the
same machine, the same PocketBase admin port that extension/agent_loop.js names
by hand as the threat. The refusal was a set of regexes over whatever string
`urlsplit` returned, and `urlsplit` returns the spelling. The browser's URL
parser normalises first, so learn.js's identical regexes never saw one.

So the class is NOT "three encoded URLs". It is "a private address written in a
way the refusal did not recognise", and the only way to close a class like that
is to stop the refusal reading spellings at all. Every case below is generated
from ONE address by re-spelling it, which is why a fix that special-cases the
decimal form fails here rather than looking finished.
"""
import pytest

import brain.research as research

# 127.0.0.1 and 169.254.169.254 (the metadata endpoint every cloud host answers
# on, and the one address on this list that the SERVER can reach and the
# owner's laptop cannot), each written every way a URL parser accepts.
LOOPBACK_SPELLINGS = [
    "http://127.0.0.1/",
    "http://127.0.0.1:8090/admin",
    "http://2130706433/",
    "http://2130706433:8090/admin",
    "http://0x7f000001/",
    "http://0x7F000001/",
    "http://0177.0.0.1/",
    "http://127.1/",
    "http://127.0.1/",
    "http://0x7f.1/",
    "http://0x7f.0.0.1/",
    "http://127.000.000.001/",
    "http://2130706433./",
    # Percent-encoding is a spelling too — the browser decodes the host
    # before anything else looks at it.
    "http://%31%32%37.0.0.1/",
    "http://%32%31%33%30%37%30%36%34%33%33/",
]

METADATA_SPELLINGS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://2852039166/latest/meta-data/",
    "http://0xa9fea9fe/latest/meta-data/",
    "http://169.254.43518/latest/meta-data/",
    "http://0251.0376.0251.0376/latest/meta-data/",
]


@pytest.mark.parametrize("url", LOOPBACK_SPELLINGS + METADATA_SPELLINGS)
def test_no_spelling_of_a_refused_address_is_researchable(url):
    assert research.is_researchable(url) is False


@pytest.mark.parametrize("url", LOOPBACK_SPELLINGS + METADATA_SPELLINGS)
def test_every_spelling_parses_to_the_same_value(url):
    """The refusal above would also pass if the parser threw on all of them.
    It does not: each of these is a VALID URL that resolves, which is exactly
    why refusing it has to be deliberate."""
    parsed = research.parse_host(url)
    assert parsed is not None and parsed.ip is not None
    assert str(parsed.ip) in ("127.0.0.1", "169.254.169.254")


def test_a_public_address_that_merely_looks_encoded_is_still_researchable():
    """`010.0.0.1` is octal for 8.0.0.1 — public. A fix that refused anything
    with a leading zero, an `0x`, or no dots would pass every test above and
    quietly stop the arm reading real pages. Security that only ever says no is
    not distinguishable from a broken parser."""
    assert research.is_researchable("http://010.0.0.1/") is True
    assert str(research.parse_host("http://010.0.0.1/").ip) == "8.0.0.1"
    assert research.is_researchable("http://1.1.1.1/") is True
    assert research.is_researchable("http://2130706433.example.com/") is True
    assert research.is_researchable("http://1.2.3.4.example/") is True


@pytest.mark.parametrize("url", [
    "http://999.999.999.999/",
    "http://a:b:c/",
    "http://example.com:99999/",
    "http://%2570.example.com/",
    "http://example.com.5/",
    "http://1.1.1.1.1/",
    "http://256.0.0.1/",
    "http://0x100000000/",
])
def test_a_host_ending_in_a_number_that_cannot_finish_is_not_a_domain(url):
    """The browser THROWS on these. The old port fell back to treating them as
    domain names, which is the same mistake as the encoded case wearing the
    other face: a string the browser would never have accepted became a host
    the server was willing to fetch."""
    assert research.parse_host(url) is None
    assert research.is_researchable(url) is False


def test_the_attack_that_survived_the_write_no_longer_does():
    """The reviewer's own repro. `_clean_procedure` is the ONE door a procedure
    enters by — distilled here from web pages, or uplinked from the extension —
    and a `startUrl` is a place a browser is later pointed at. Before this fix
    the dotted-quad form was refused and the decimal form was written straight
    through, so the guard held against the sentence nobody would write and
    opened for the one an attacker would."""
    hostile = {
        "startUrl": "http://2130706433:8090/admin",
        "steps": ["open the portal", "click Users"],
        "learnedAt": research._now_ms(),
    }
    record = research._clean_procedure(hostile)
    assert record is not None, "the steps are not what is being refused"
    assert record["startUrl"] is None, (
        f"a page talked the arm into pointing a browser at {record['startUrl']}")


def test_the_metadata_endpoint_cannot_arrive_as_a_source_either():
    """`sources` and `startUrl` are different fields with the same problem, and
    rank_sources is what decides which pages the arm actually FETCHES —
    server-side, on a host that answers on 169.254.169.254."""
    ranked = research.rank_sources([
        "http://2852039166/latest/meta-data/",
        "https://support.anker.com/returns",
        "http://0x7f000001/admin",
    ])
    assert ranked == ["https://support.anker.com/returns"]


def test_one_page_per_host_cannot_be_defeated_by_respelling_the_host():
    """rank_sources keeps one page per host so a single help centre cannot
    crowd out the second opinion. It de-duplicates on `host_of`, so while that
    returned the spelling, three spellings of one address were three sources."""
    ranked = research.rank_sources([
        "http://1.1.1.1/a",
        "http://16843009/b",
        "http://0x01010101/c",
    ])
    assert ranked == ["http://1.1.1.1/a"]


def test_an_international_hostname_still_survives_both_branches():
    """IDNA runs BEFORE the address branch, which is the order the URL parser
    uses. Getting it backwards refuses réserver.fr."""
    assert research.is_researchable("https://réserver.fr/x") is True
    assert research.host_of("https://réserver.fr/x") == "xn--rserver-bya.fr"


def test_a_bracketed_ipv6_loopback_is_refused_and_a_public_one_is_not():
    assert research.is_researchable("http://[::1]/") is False
    assert research.is_researchable("https://[2606:4700::1111]/") is True
