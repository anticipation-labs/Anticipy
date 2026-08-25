"""HANDS 1 — the server and the extension must key the cache IDENTICALLY.

`learn.js` exports `taskShape`, and `recipes.js` IMPORTS it rather than copying
it, on purpose, so the two browser caches can never key differently
(recipes.js:53-57). The server-side procedure store is a third reader of that
key and cannot import a JS module, so it holds a port — and a port is a second
copy of a predicate, which is exactly what that import was avoiding.

So the copy is only honest if drift is caught. These tests run the REAL
`extension/learn.js` under node over a shared corpus and compare it to the
Python port character by character. A word added to one list and not the other,
a changed slice, a different sort — any of it fails here rather than showing up
as a cache that silently forks and pays for research twice.

The same treatment for `isResearchable`, which is not a cache key but a
security predicate: research runs BEFORE the loop's loopback guard exists, so
a private address that gets past it is the owner's own machine opened on a
sentence a web page wrote.

Skipped, loudly, when node is missing — a skipped parity test is a copy nobody
is checking, and that is worth seeing in the output.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import brain.research as research

REPO = Path(__file__).resolve().parents[1]
LEARN_JS = REPO / "extension" / "learn.js"

GOALS = [
    "dispute the March bill from BC Hydro",
    "dispute the April bill from BC Hydro",
    "cancel Tuesday's Telus appointment",
    "cancel Thursday's Telus appointment",
    "cancel my Adobe subscription",
    "my Adobe subscription, cancel it",
    "dispute invoice 88231 for $412.90 from Telus",
    "dispute invoice 90114 for $9.99 from Telus",
    "claim the warranty on my Anker charger",
    "Find me a dentist that's open Saturdays near work",
    "book a table for 4 at Cactus Club tomorrow at 7pm",
    "renew my BC driver's licence online",
    "file a T1 adjustment with the CRA for last year",
    "  ",
    "",
    "the and for with from that this was are please",
    "a bc de fgh",
    "RENEW MY PASSPORT",
    "renew   my    passport",
    "email support@example.com about order #4471",
    "réserver une table chez Café Médina",
    "cancel the 3 subscriptions I have with Rogers",
    "what's the status of my claim",
    "whats the status of my claim",
    "next month's hydro bill dispute",
    "return the shoes I bought on Tuesday morning",
    "x" * 400,
    "dispute-bill-hydro " * 30,
]

URLS = [
    "https://support.anker.com/returns",
    "http://example.com/a",
    "https://EXAMPLE.COM/A",
    "https://www.chase.com/login",
    "https://chase.com",
    "https://notchase.com/",
    "https://paypal.com/disputes",
    "https://mybank.wellsfargo.com/x",
    "http://localhost:8090/admin",
    "http://LOCALHOST/admin",
    "http://app.localhost/",
    "http://printer.local/",
    "http://svc.internal/",
    "http://127.0.0.1:8090/admin",
    "http://127.9.9.9/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://169.254.169.254/latest/meta-data/",
    "http://172.16.0.1/",
    "http://172.20.0.1/",
    "http://172.31.255.255/",
    "http://172.32.0.1/",
    "http://172.15.0.1/",
    "http://0.0.0.0/",
    "http://[::1]/",
    "https://[2606:4700::1111]/",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/html,<b>hi</b>",
    "not a url at all",
    "//example.com/x",
    "https://",
    "",
    "https://gc.ca/forms",
    "https://réserver.fr/x",
    "https://xn--rserver-bva.fr/x",
    "ftp://example.com/x",
]


def _node_says():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed — the parity of the two copies of "
                    "taskShape/isResearchable is NOT being checked in this run")
    driver = (
        f'import {{ taskShape, isResearchable }} from {json.dumps(LEARN_JS.as_uri())};\n'
        'let input = "";\n'
        'process.stdin.on("data", (c) => { input += c; });\n'
        'process.stdin.on("end", () => {\n'
        '  const cases = JSON.parse(input);\n'
        '  console.log(JSON.stringify({\n'
        '    shapes: cases.goals.map((g) => taskShape(g)),\n'
        '    researchable: cases.urls.map((u) => isResearchable(u)),\n'
        '  }));\n'
        '});\n'
    )
    proc = subprocess.run(
        [node, "--input-type=module", "-e", driver],
        input=json.dumps({"goals": GOALS, "urls": URLS}),
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"node failed: {proc.stderr[-2000:]}"
    return json.loads(proc.stdout)


@pytest.fixture(scope="module")
def js():
    return _node_says()


def test_the_shape_key_is_identical_in_both_languages(js):
    mine = [research.task_shape(g) for g in GOALS]
    mismatches = [(g, a, b) for g, a, b in zip(GOALS, js["shapes"], mine) if a != b]
    assert not mismatches, "\n".join(
        f"{g[:60]!r}: learn.js -> {a!r}, research.py -> {b!r}"
        for g, a, b in mismatches)


def test_a_shape_that_is_not_a_string_is_survivable_in_both(js):
    """learn.js coerces with String(goal || "") and never throws. A crash here
    would be an errand lost to a null goal column."""
    for junk in (None, 5, [], {}, True):
        assert isinstance(research.task_shape(junk), str)


def test_the_researchable_host_rule_is_identical_in_both_languages(js):
    mine = [research.is_researchable(u) for u in URLS]
    mismatches = [(u, a, b) for u, a, b in zip(URLS, js["researchable"], mine)
                  if a != b]
    assert not mismatches, "\n".join(
        f"{u!r}: learn.js -> {a}, research.py -> {b}" for u, a, b in mismatches)


def test_the_corpus_actually_exercises_both_answers(js):
    """A parity test over a corpus that is all-True or all-False would pass
    against a function that returns a constant."""
    assert any(js["researchable"]) and not all(js["researchable"])
    assert len({s for s in js["shapes"]}) > 5


def test_the_shape_is_bounded(js):
    assert all(len(s) <= 120 for s in js["shapes"])
    assert all(len(research.task_shape(g)) <= 120 for g in GOALS)


def test_the_word_lists_themselves_have_not_drifted():
    """The corpus catches behaviour; this catches a list edited on one side
    that the corpus happens not to reach. Read straight out of the JS source,
    so adding a stop word in one language and not the other fails here."""
    src = LEARN_JS.read_text()
    for name, mine in (("STOP", research._STOP),
                       ("INSTANCE_WORDS", research._INSTANCE_WORDS)):
        block = src.split(f"const {name} = new Set([", 1)[1].split("]);", 1)[0]
        theirs = {w.strip().strip('",').strip("'")
                  for w in block.replace("\n", " ").split(",")}
        theirs = {w for w in theirs if w and not w.startswith("//")}
        assert theirs == mine, (
            f"{name} has drifted: only in learn.js {sorted(theirs - mine)}, "
            f"only in research.py {sorted(mine - theirs)}")
