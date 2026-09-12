"""The deploy preflight must refuse a database this release would break on.

It is checked against a real SQLite database built from the real schema.sql and
wound back to its pre-migration shape, so what it reads is the engine's answer.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from proof.audit import d1_additive as additive
from proof.audit import d1_connector_readiness as readiness
from d1_schema_fixture import schema_for_column_rewind

ROOT = Path(__file__).resolve().parents[1]
D1 = ROOT / "migration/d1"
MIGRATIONS = ["2026-09-11-connect-code-delivery.sql", "2026-09-11-oauth-recovery.sql"]


def observe(db: sqlite3.Connection):
    columns = {table: {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}
               for table in readiness.REQUIRED_COLUMNS}
    triggers = {str(row[0]): str(row[1] or "") for row in
                db.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")}
    return columns, triggers


@pytest.fixture
def fresh():
    db = sqlite3.connect(":memory:")
    db.executescript(schema_for_column_rewind((D1 / "schema.sql").read_text()))
    yield db
    db.close()


def wind_back(db: sqlite3.Connection):
    for name in MIGRATIONS:
        sql = (D1 / name).read_text()
        for kind, made in [("TRIGGER", readiness.REQUIRED_TRIGGERS)]:
            for obj in made:
                db.execute(f"DROP {kind} IF EXISTS {obj}")
        db.execute("DROP INDEX IF EXISTS idx_connect_links_recovery")
        for table, column in additive.required_columns(sql):
            db.execute(f'ALTER TABLE {table} DROP COLUMN "{column}"')
    db.commit()


def test_the_current_schema_is_accepted(fresh):
    assert readiness.verify(*observe(fresh)) == []


def test_a_pre_migration_database_is_refused_by_name(fresh):
    wind_back(fresh)
    missing = readiness.verify(*observe(fresh))
    assert "connect_codes.delivery_state" in missing, "the phone-code column is not named"
    assert "connect_links.recovery_account_id" in missing
    assert "trigger cancel_oauth_recovery_deleted_connection" in missing


def test_columns_without_triggers_is_still_refused(fresh):
    """The half-applied migration: the worst state available, because the code
    would run with no cancellation fence at all."""
    for name in readiness.REQUIRED_TRIGGERS:
        fresh.execute(f"DROP TRIGGER {name}")
    missing = readiness.verify(*observe(fresh))
    assert missing == [f"trigger {name}" for name in readiness.REQUIRED_TRIGGERS]


def test_applying_the_migrations_turns_a_refusal_into_a_pass(fresh):
    wind_back(fresh)
    assert readiness.verify(*observe(fresh))
    for name in MIGRATIONS:
        sql = (D1 / name).read_text()
        existing = {t: {str(r[1]).lower() for r in fresh.execute(f"PRAGMA table_info({t})")}
                    for t in additive.tables_in(sql)}
        for statement in additive.plan(sql, existing)[0]:
            fresh.executescript(statement)
    fresh.commit()
    assert readiness.verify(*observe(fresh)) == []


def test_a_missing_table_is_reported_rather_than_passing_empty():
    missing = readiness.verify({}, {})
    assert any("the table itself is absent" in line for line in missing)
    assert len(missing) == len(readiness.REQUIRED_COLUMNS) + len(readiness.REQUIRED_TRIGGERS)


# ---------------------------------------------------------------------------
# THE TRIGGER THAT IS THERE BY NAME AND ABSENT IN FACT (2026-09-12, OMNI-8).
# `recovery.ready()` checks the four names, and so did this preflight — so a
# trigger left behind by a hand edit or an older migration, with the right name
# and a narrowed body, passed readiness and cancelled nothing. `CREATE TRIGGER
# IF NOT EXISTS` never replaces it. The preflight now reads the body the
# engine stored and holds it to the body the migration declares.
# ---------------------------------------------------------------------------
NARROWED = "cancel_oauth_recovery_decline_insert"


def narrow(db: sqlite3.Connection, name: str = NARROWED) -> None:
    """Same name, a WHEN that never fires: the fence is gone and the name is not."""
    db.execute(f"DROP TRIGGER {name}")
    db.execute(f"""CREATE TRIGGER {name} AFTER INSERT ON connect_nudges
        WHEN 0 BEGIN SELECT 1; END""")
    db.commit()


def test_a_trigger_present_by_name_with_another_body_is_refused(fresh):
    narrow(fresh)
    missing = readiness.verify(*observe(fresh))
    assert len(missing) == 1, missing
    assert missing[0].startswith(f"trigger {NARROWED}: present, but its body differs")
    assert "2026-09-11-oauth-recovery.sql" in missing[0]


def test_the_engine_itself_would_not_have_noticed(fresh):
    """Why the name check was not enough, as the engine's own answer: the
    migration's guarded CREATE leaves the narrowed trigger exactly as it was."""
    narrow(fresh)
    before = fresh.execute("SELECT sql FROM sqlite_master WHERE name=?", (NARROWED,)).fetchone()[0]
    sql = (D1 / "2026-09-11-oauth-recovery.sql").read_text()
    for statement in additive.statements(sql):
        if additive.CREATE_TRIGGER.match(additive._bare(statement)) and NARROWED in statement:
            fresh.executescript(statement)
    after = fresh.execute("SELECT sql FROM sqlite_master WHERE name=?", (NARROWED,)).fetchone()[0]
    assert after == before, "IF NOT EXISTS replaced the trigger after all; the guard is moot"
    assert NARROWED in {n for n, in fresh.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}


def test_the_declared_body_is_what_a_fresh_install_carries(fresh):
    """The comparison is exact against the engine's stored text, not a reading
    of the file: every required trigger on a schema.sql database normalises to
    the migration's declaration. (schema-migration-parity.test.ts proves the two
    files agree; this proves the Python normaliser reads what SQLite stores.)"""
    _, triggers = observe(fresh)
    expected = readiness.expected_triggers()
    for name in readiness.REQUIRED_TRIGGERS:
        assert additive.normalize_sql(triggers[name]) == expected[name], name


def test_a_whitespace_comment_or_name_case_change_is_not_a_body_change(fresh):
    """The stored text is compared as SQL, not as bytes: reflowed, commented,
    the keyword and the NAME recased (SQLite compares names case-insensitively
    and stores them as written, so the recased name must still be found)."""
    name = readiness.REQUIRED_TRIGGERS[0]
    stored = fresh.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0]
    fresh.execute(f"DROP TRIGGER {name}")
    reflowed = ("  -- restated by hand\n"
                + stored.replace("CREATE TRIGGER " + name, "create   trigger " + name.upper(), 1)
                        .replace("\n", "  -- reflowed\n   ") + "\n")
    fresh.execute(reflowed)
    fresh.commit()
    assert name.upper() in {n for n, in fresh.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert readiness.verify(*observe(fresh)) == []


def test_the_migration_must_still_declare_every_required_trigger(monkeypatch, tmp_path):
    """A required trigger the migration no longer declares is a preflight that
    cannot answer, not one that passes."""
    stripped = tmp_path / "2026-09-11-oauth-recovery.sql"
    stripped.write_text("CREATE INDEX IF NOT EXISTS idx_nothing ON connect_links(user_id);\n")
    monkeypatch.setattr(readiness, "RECOVERY_MIGRATION", stripped)
    with pytest.raises(SystemExit, match="no longer declares"):
        readiness.expected_triggers()
