"""One promise/one workflow is storage identity, never keyword similarity."""
import hashlib
import ast
import inspect
import json
import sqlite3
import textwrap
from pathlib import Path

import requests

from brain import backend
from brain.anticipy_core import Anticipy


ROOT = Path(__file__).resolve().parents[1]


def test_commitment_key_has_only_tenant_and_integer_promise_as_inputs():
    key = Anticipy._commitment_key_for("owner-a", 90)
    assert key == hashlib.sha256(
        b"anticipy:commitment:v1:owner-a:90").hexdigest()
    assert len(key) == 64
    assert key != Anticipy._commitment_key_for("owner-b", 90)
    assert key != Anticipy._commitment_key_for("owner-a", 91)
    assert Anticipy._commitment_key_for("", 90) == ""
    assert Anticipy._commitment_key_for("owner-a", "not-an-id") == ""


def test_commitment_identity_cannot_consult_language_or_similarity():
    """A future repair cannot quietly turn identity back into word matching."""
    function = Anticipy._commitment_key_for
    assert tuple(inspect.signature(function).parameters) == \
        ("owner_ref", "commitment_id")
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    referenced = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    assert referenced.isdisjoint({
        "goal", "source", "text", "words", "keywords", "regex", "re",
        "similarity", "embedding", "model", "llm",
    })


def test_database_has_a_supported_unique_barrier_and_terminal_release():
    """The barrier is the D1 schema's partial unique index; the release is the
    Worker's writer clearing the key on every terminal status. Both halves are
    read from the code that runs (migration/d1, migration/workers), never from
    the PocketBase migration and hook they were ported from."""
    schema = (ROOT / "migration/d1/schema.sql").read_text()
    assert 'CREATE UNIQUE INDEX IF NOT EXISTS "idx_jobs_active_commitment"' in schema
    predicate = schema.split('"idx_jobs_active_commitment"', 1)[1].split(";", 1)[0]
    assert '"commitment_key" != \'\'' in predicate
    assert " IN " not in predicate
    for status in ("done", "failed", "cancelled"):
        assert status not in predicate
    records = (ROOT / "migration/workers/src/api/records.ts").read_text()
    release = records.split("export function releasesCommitment", 1)[1].split("}", 1)[0]
    assert 'def.name !== "jobs"' in release
    assert "TERMINAL_STATUSES.includes" in release
    terminal = records.split("TERMINAL_STATUSES = ", 1)[1].split("]", 1)[0]
    for status in ("done", "failed", "cancelled"):
        assert f'"{status}"' in terminal
    assert 'body.commitment_key = ""' in records


def test_storage_rejects_two_live_rows_but_allows_history_then_retry():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE jobs (commitment_key TEXT, status TEXT)")
    db.execute(
        "CREATE UNIQUE INDEX idx_jobs_active_commitment "
        "ON jobs(commitment_key) WHERE commitment_key != ''")
    db.execute("INSERT INTO jobs VALUES ('same-promise', 'queued')")
    try:
        db.execute("INSERT INTO jobs VALUES ('same-promise', 'needs_user')")
        raise AssertionError("storage admitted two active workflows")
    except sqlite3.IntegrityError:
        pass
    # The PocketBase model hook clears the auxiliary identity in the same
    # write that makes the row terminal.
    db.execute("UPDATE jobs SET status='done', commitment_key='' ")
    db.execute("INSERT INTO jobs VALUES ('same-promise', 'queued')")
    assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 2
    assert db.execute(
        "SELECT COUNT(*) FROM jobs WHERE commitment_key='same-promise'"
    ).fetchone()[0] == 1


def test_a_create_race_absorbs_by_commitment_key_not_words(monkeypatch):
    """Both workers saw an empty queue; storage let exactly one create."""
    existing = {
        "id": "winner",
        "goal": "prepare an unrelatedly worded outcome",
        "status": "awaiting_confirm",
        "commitment_key": "",
        "params": json.dumps({
            "source": "clock initiative", "commitment_id": 90,
        }),
    }
    state = {"collided": False, "posted": None}

    def get(_url, params=None, timeout=10, **_kwargs):
        filt = str((params or {}).get("filter") or "")
        items = []
        if state["collided"] and "commitment_key=" in filt:
            items = [existing]
        return _Response({"items": items})

    def post(_url, json=None, timeout=10, **_kwargs):
        state["posted"] = dict(json or {})
        existing["commitment_key"] = state["posted"]["commitment_key"]
        state["collided"] = True
        response = requests.Response()
        response.status_code = 400
        response._content = b'{"message":"unique constraint"}'
        raise requests.HTTPError(response=response)

    monkeypatch.setattr(backend, "get", get)
    monkeypatch.setattr(backend, "post", post)
    monkeypatch.setattr(
        backend, "patch",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("a clock paraphrase must not rewrite the winner")))

    brain = Anticipy(owner_id="owner-a")
    got = brain._queue_job(
        "completely different words from the winning workflow",
        {"source": "clock initiative", "commitment_id": 90},
        hold=True,
    )

    assert got == "winner"
    assert state["posted"]["commitment_key"] == \
        Anticipy._commitment_key_for("owner-a", 90)
    assert "different" not in state["posted"]["commitment_key"]


class _Response:
    def __init__(self, payload):
        self.payload = payload
        self.ok = True

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None
