"""Actual worker ingestion must not print imported/deleted personal content.

Synthetic boundary doubles keep this a zero-network diagnostic regression, not
a claim about end-to-end consent, memory grounding or the entire logging system.
"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from brain import worker


PRIVATE = "SYNTHETIC_PRIVATE_CONTEXT_9381: Casey has a confidential appointment"
OWNER = "synthetic-owner"


@pytest.fixture
def ingestion(monkeypatch):
    event = {"id": "event-one", "text": PRIVATE, "source": "import",
             "importance": 4, "goal": "synthetic-job"}
    state = SimpleNamespace(kind="profile", event=event)
    memory = Mock()
    memory.remember_fact.return_value = 1
    memory.forget_fact.return_value = 1
    memory.read_facts_admitted.return_value = 0
    state.memory = memory
    state.mark = Mock()

    def fetch(*, kind, owner_ref):
        assert owner_ref == OWNER
        return [state.event] if kind == state.kind else []

    monkeypatch.setattr(worker, "fetch_unprocessed", fetch)
    monkeypatch.setattr(worker, "mark_processed", state.mark)
    return state


def assert_private_logs(capsys, expected):
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == expected + "\n"
    assert "SYNTHETIC_PRIVATE_CONTEXT_9381" not in captured.out


@pytest.mark.parametrize("source,expected_source", [
    ("import", "import"), ("interview", "interview"),
    (PRIVATE, "import"),
])
def test_profile_success_logs_only_fixed_source_and_numeric_importance(
        ingestion, capsys, source, expected_source):
    ingestion.event["source"] = source
    assert worker.ingest_profile_events(ingestion.memory, OWNER) == 1
    ingestion.memory.remember_fact.assert_called_once_with(
        PRIVATE, importance=4, source=expected_source)
    ingestion.mark.assert_called_once_with("event-one", "ignore")
    assert_private_logs(capsys, f"profile fact processed via {expected_source} (importance 4)")


def test_supervised_success_preserves_memory_but_not_log_content(ingestion, capsys):
    ingestion.kind = "read_fact"
    ingestion.event["source"] = "supervised_mail"
    assert worker.ingest_read_facts(ingestion.memory, OWNER) == 1
    ingestion.memory.remember_fact.assert_called_once_with(
        PRIVATE, importance=4, source="supervised_mail")
    ingestion.memory.note_read_fact_admitted.assert_called_once_with("synthetic-job")
    ingestion.mark.assert_called_once_with("event-one", "ignore")
    assert_private_logs(capsys, "read fact processed via supervised_mail (importance 4)")


def test_ceiling_refusal_logs_neither_content_nor_source_controlled_job(ingestion, capsys):
    ingestion.kind = "read_fact"
    ingestion.event["goal"] = PRIVATE
    ingestion.memory.read_facts_admitted.return_value = worker.READ_FACTS_PER_JOB
    assert worker.ingest_read_facts(ingestion.memory, OWNER) == 0
    ingestion.memory.remember_fact.assert_not_called()
    ingestion.memory.note_read_fact_admitted.assert_not_called()
    ingestion.mark.assert_called_once_with("event-one", "refused_read_fact_ceiling")
    assert_private_logs(capsys, f"read fact REFUSED: per-job ceiling of {worker.READ_FACTS_PER_JOB} facts reached")


def test_veto_preserves_deletion_without_reprinting_the_deleted_fact(ingestion, capsys):
    ingestion.kind = "read_veto"
    assert worker.ingest_read_vetoes(ingestion.memory, OWNER) == 1
    ingestion.memory.forget_fact.assert_called_once_with(PRIVATE, source="import")
    ingestion.mark.assert_called_once_with("event-one", "ignore")
    assert_private_logs(capsys, "read fact veto applied (1 row(s) deleted)")


@pytest.mark.parametrize("kind,method,message", [
    ("profile", "remember_fact", "profile import interrupted; outcome unconfirmed"),
    ("read_fact", "remember_fact", "supervised read ingest interrupted; outcome unconfirmed"),
    ("read_veto", "forget_fact", "veto interrupted; outcome unconfirmed"),
])
@pytest.mark.parametrize("failure_at", ["memory", "fetch", "mark"])
def test_import_error_messages_cannot_disclose_private_payloads(
        ingestion, monkeypatch, capsys, kind, method, message, failure_at):
    ingestion.kind = kind
    if failure_at == "memory":
        getattr(ingestion.memory, method).side_effect = RuntimeError(PRIVATE)
    elif failure_at == "fetch":
        monkeypatch.setattr(worker, "fetch_unprocessed", Mock(side_effect=RuntimeError(PRIVATE)))
        if kind == "read_fact":
            # Isolate this function's fetch failure from the preceding veto pass.
            monkeypatch.setattr(worker, "ingest_read_vetoes", lambda *a, **k: 0)
    else:
        ingestion.mark.side_effect = RuntimeError(PRIVATE)
    fn = {"profile": worker.ingest_profile_events,
          "read_fact": worker.ingest_read_facts,
          "read_veto": worker.ingest_read_vetoes}[kind]
    assert fn(ingestion.memory, OWNER) == 0
    assert_private_logs(capsys, message)


def test_identity_seed_error_does_not_echo_name_email_or_exception(monkeypatch, capsys):
    monkeypatch.setattr(worker, "_latest_profile", lambda owner: {
        "first_name": PRIVATE, "email": "synthetic-private@audit.invalid"})
    memory = Mock()
    memory.remember_fact.side_effect = RuntimeError(PRIVATE)
    seen = {}
    worker.seed_profile_identity(memory, seen, OWNER)
    assert seen == {}
    assert_private_logs(capsys, "profile identity seed failed; will retry")
