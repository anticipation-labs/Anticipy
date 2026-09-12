"""Applying an additive D1 migration twice must be a no-op, not a red deploy.

The API deploy job applies its migrations by name on every run, so "rerunnable"
is not a nicety here: the second deploy is the one that finds out. These run the
REAL migration files against a real SQLite database built from the REAL
schema.sql, wound back to its pre-migration shape, so what is measured is the
engine's answer rather than a reading of the SQL.

They do not prove anything about the deployed database, D1's network semantics,
or that a migration has been applied to production.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from proof.audit import d1_additive as additive
from d1_schema_fixture import schema_for_column_rewind

ROOT = Path(__file__).resolve().parents[1]
D1 = ROOT / "migration/d1"
MIGRATIONS = sorted(p for p in D1.iterdir()
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}-.+\.sql", p.name))
ADDITIVE = [p for p in MIGRATIONS if additive.required_columns(p.read_text())]

#: ONE-SHOT MIGRATIONS, NAMED. SQLite cannot widen a CHECK in place, so this one
#: renames the table, recreates it, copies the rows and drops the original. Run
#: it twice and the second run renames the NEW table away and copies nothing
#: back. It was applied once, by hand, and it must never be wired into a step
#: that repeats. The applier refusing it is the guard, and the test below is
#: what keeps the guard honest.
ONE_SHOT = {"2026-09-06-connect-nudges-declined-soft.sql"}
REPEATABLE = [p for p in MIGRATIONS if p.name not in ONE_SHOT]


def columns_of(db: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]).lower() for row in db.execute(f"PRAGMA table_info({table})")}


def existing_for(db: sqlite3.Connection, sql: str) -> dict[str, set[str]]:
    return {table: columns_of(db, table) for table in additive.tables_in(sql)}


def objects_created(sql: str) -> list[tuple[str, str]]:
    made = []
    for statement in additive.statements(sql):
        flat = re.sub(r"\s+", " ", re.sub(r"--[^\n]*", " ", statement)).strip()
        found = re.match(r"^create\s+(?:unique\s+)?(index|trigger)\s+(?:if\s+not\s+exists\s+)?(\w+)",
                         flat, re.I)
        if found:
            made.append((found.group(1).lower(), found.group(2)))
    return made


@pytest.fixture
def fresh() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript(schema_for_column_rewind((D1 / "schema.sql").read_text()))
    yield db
    db.close()


def wind_back(db: sqlite3.Connection, sql: str) -> None:
    """Return the database to the shape it had before this migration ran.

    The index and triggers go first: SQLite refuses to drop a column anything
    still names, which is exactly the dependency the migration created.
    """
    for kind, name in objects_created(sql):
        db.execute(f"DROP {kind.upper()} IF EXISTS {name}")
    for table, column in additive.required_columns(sql):
        db.execute(f'ALTER TABLE {table} DROP COLUMN "{column}"')
    db.commit()


def apply_plan(db: sqlite3.Connection, sql: str) -> tuple[int, int]:
    to_run, skipped = additive.plan(sql, existing_for(db, sql))
    for statement in to_run:
        db.executescript(statement)
    db.commit()
    return len(to_run), len(skipped)


@pytest.mark.parametrize("comment", ["-- The comment has, a comma.", "/* A block comment has, one too. */"])
def test_fixture_comments_do_not_break_a_last_column_rewind(comment):
    """SQLite before the 2025-12-02 fix mistakes the comment's comma for SQL.

    This is the minimal shape behind connect_links.recovery_lease in Linux CI;
    it must work without suppressing ALTER errors or skipping older engines.
    """
    with sqlite3.connect(":memory:") as db:
        db.executescript(schema_for_column_rewind(f"""
            CREATE TABLE example(a INTEGER, b TEXT DEFAULT 'keep',
                {comment}
                c TEXT);
            INSERT INTO example(a) VALUES (7);
        """))
        db.execute("ALTER TABLE example DROP COLUMN c")
        assert columns_of(db, "example") == {"a", "b"}
        assert db.execute("SELECT a, b FROM example").fetchall() == [(7, "keep")]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_fixture_comment_removal_preserves_literals_identifiers_and_constraints():
    sql = """
        -- Real comment, removed only outside quoted SQL tokens.
        PRAGMA foreign_keys=ON;
        CREATE TABLE parent(id INTEGER PRIMARY KEY);
        CREATE TABLE "quoted""--table" (
            id INTEGER PRIMARY KEY,
            parent_id INTEGER REFERENCES parent(id),
            value TEXT NOT NULL DEFAULT '--literal, /*not a comment*/ ''quoted'''
                CHECK(length(value)>0),
            `tick``--name` TEXT,
            [bracket/*name*/] TEXT
        );
        /* Actual multiline, comment
           with ' " ` [ quote markers inside it. */
        CREATE TABLE audit(value TEXT);
        CREATE TRIGGER record_value AFTER INSERT ON "quoted""--table"
        BEGIN
            INSERT INTO audit VALUES (NEW.value || ' /*literal*/ --literal');
        END;
    """
    prepared = schema_for_column_rewind(sql)
    for literal in ("'--literal, /*not a comment*/ ''quoted'''", '"quoted""--table"',
                    '`tick``--name`', '[bracket/*name*/]', "' /*literal*/ --literal'"):
        assert literal in prepared
    assert "Real comment" not in prepared and "Actual multiline" not in prepared
    snapshots = []
    for declaration in (sql, prepared):
        with sqlite3.connect(":memory:") as db:
            db.executescript(declaration)
            db.execute("INSERT INTO parent VALUES (1)")
            db.execute('INSERT INTO "quoted""--table" (id,parent_id) VALUES (1,1)')
            snapshots.append((
                db.execute('PRAGMA table_info("quoted""--table")').fetchall(),
                db.execute('PRAGMA foreign_key_list("quoted""--table")').fetchall(),
                db.execute('SELECT * FROM "quoted""--table"').fetchall(),
                db.execute("SELECT * FROM audit").fetchall(),
            ))
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
                db.execute('INSERT INTO "quoted""--table" (id,value) VALUES (2,\'\')')
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                db.execute('INSERT INTO "quoted""--table" (id,parent_id) VALUES (3,99)')
    assert snapshots[0] == snapshots[1]


def schema_signature(db: sqlite3.Connection):
    """Ask SQLite about the real schema, including indexes and trigger bodies."""
    signature = []
    for kind, name, sql in db.execute(
            "SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall():
        quoted = '"' + name.replace('"', '""') + '"'
        if kind == "table":
            details = tuple(db.execute(f"PRAGMA {pragma}({quoted})").fetchall()
                            for pragma in ("table_info", "foreign_key_list", "index_list"))
        elif kind == "index":
            details = db.execute(f"PRAGMA index_xinfo({quoted})").fetchall()
        else:
            details = additive.normalize_sql(sql or "")
        signature.append((kind, name, details))
    return signature


def test_prepared_fixture_matches_the_entire_real_schema(fresh):
    with sqlite3.connect(":memory:") as original:
        original.executescript((D1 / "schema.sql").read_text())
        assert schema_signature(fresh) == schema_signature(original)
        assert fresh.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_recovery_reapply_preserves_real_schema_and_column_constraints(fresh):
    before = schema_signature(fresh)
    sql = (D1 / "2026-09-11-oauth-recovery.sql").read_text()
    wind_back(fresh, sql)
    apply_plan(fresh, sql)
    assert schema_signature(fresh) == before
    insert = """INSERT INTO connect_links
        (token_handle,user_id,toolkit,expires_at,recovery_attempts) VALUES (?,?,?,?,?)"""
    for attempts in (-1, 17):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            fresh.execute(insert, ("a" * 64, "fixtureowner001", "fixture_notes", 1, attempts))
    fresh.execute("""INSERT INTO connect_links (token_handle,user_id,toolkit,expires_at)
        VALUES (?,?,?,?)""", ("a" * 64, "fixtureowner001", "fixture_notes", 1))
    assert fresh.execute("""SELECT recovery_account_id,recovery_deadline,recovery_next_check,
        recovery_attempts,recovery_lease FROM connect_links""").fetchone() == (None, None, None, 0, None)
    assert fresh.execute("PRAGMA integrity_check").fetchone() == ("ok",)


@pytest.mark.parametrize("path", REPEATABLE, ids=lambda p: p.name)
def test_every_repeatable_migration_is_classifiable(path):
    """Nothing is skipped because the applier could not read it."""
    additive.plan(path.read_text(), {})


@pytest.mark.parametrize("name", sorted(ONE_SHOT))
def test_a_one_shot_table_rebuild_is_refused_not_quietly_repeated(name):
    """A deploy step that repeats must not be able to pick this file up."""
    with pytest.raises(additive.Unclassified):
        additive.plan((D1 / name).read_text(), {})


@pytest.mark.parametrize("path", ADDITIVE, ids=lambda p: p.name)
def test_applying_twice_adds_the_columns_once_and_then_does_nothing(fresh, path):
    sql = path.read_text()
    wanted = additive.required_columns(sql)
    wind_back(fresh, sql)
    for table, column in wanted:
        assert column not in columns_of(fresh, table), "the wind-back did not remove it"

    ran, skipped = apply_plan(fresh, sql)
    assert ran and skipped == 0, "a pre-migration database must run every statement"
    for table, column in wanted:
        assert column in columns_of(fresh, table)
    for kind, name in objects_created(sql):
        assert fresh.execute(
            "SELECT 1 FROM sqlite_master WHERE type=? AND name=?", (kind, name)).fetchone()

    # The second deploy. Nothing may raise, and no column may be added twice.
    ran_again, skipped_again = apply_plan(fresh, sql)
    assert skipped_again == len(wanted), "the ADD COLUMNs must be recognised as done"
    assert ran_again == ran - len(wanted), "everything else is rerunnable and reruns"
    for table, column in wanted:
        assert column in columns_of(fresh, table)


@pytest.mark.parametrize("path", ADDITIVE, ids=lambda p: p.name)
def test_the_raw_file_really_is_not_rerunnable(fresh, path):
    """The reason the applier exists, stated as a failing fact rather than a claim."""
    sql = path.read_text()
    wind_back(fresh, sql)
    fresh.executescript(sql)
    with pytest.raises(sqlite3.OperationalError, match="duplicate column"):
        fresh.executescript(sql)


def test_an_unguarded_create_is_refused_rather_than_rerun():
    with pytest.raises(additive.Unclassified):
        additive.plan("CREATE INDEX idx_thing ON connect_links(user_id);", {})


def test_an_unrecognised_statement_is_refused_rather_than_skipped():
    with pytest.raises(additive.Unclassified):
        additive.plan("UPDATE connect_links SET recovery_deadline = 0;", {})


def test_a_guarded_statement_survives_the_plan_even_when_columns_are_present():
    sql = (D1 / "2026-09-11-oauth-recovery.sql").read_text()
    present = {"connect_links": {c for _, c in additive.required_columns(sql)}}
    to_run, skipped = additive.plan(sql, present)
    assert len(skipped) == 5
    assert to_run and all("CREATE" in statement.upper() for statement in to_run)


# ---------------------------------------------------------------------------
# A TRIGGER WITH THIS MIGRATION'S NAME AND ANOTHER BODY (2026-09-12, OMNI-8).
# `CREATE TRIGGER IF NOT EXISTS` is a no-op over an existing name whatever the
# body says, so the applier used to rerun it, report success, and leave a
# narrowed or hand-edited trigger in place on every deploy. It now reads the
# body the database holds and refuses the divergence instead of guessing.
# ---------------------------------------------------------------------------
RECOVERY = D1 / "2026-09-11-oauth-recovery.sql"
NARROWED = "cancel_oauth_recovery_decline_insert"


def triggers_of(db: sqlite3.Connection) -> dict[str, str]:
    return {str(n).lower(): str(sql or "") for n, sql in
            db.execute("SELECT name, sql FROM sqlite_master WHERE type='trigger'")}


def narrow(db: sqlite3.Connection, name: str = NARROWED) -> None:
    db.execute(f"DROP TRIGGER {name}")
    db.execute(f"CREATE TRIGGER {name} AFTER INSERT ON connect_nudges WHEN 0 BEGIN SELECT 1; END")
    db.commit()


def test_a_same_name_trigger_with_another_body_is_refused_not_rerun(fresh):
    sql = RECOVERY.read_text()
    narrow(fresh)
    with pytest.raises(additive.Diverged, match=NARROWED):
        additive.plan(sql, existing_for(fresh, sql), triggers_of(fresh))


def test_the_refusal_comes_before_anything_is_planned(fresh):
    """Nothing is half-applied: the divergence is found on the trigger
    statement, but the plan as a whole is refused, ADD COLUMNs included."""
    sql = RECOVERY.read_text()
    wind_back(fresh, sql)
    fresh.executescript(sql)           # the first, clean apply
    narrow(fresh)
    fresh.execute('ALTER TABLE connect_links DROP COLUMN "recovery_lease"')
    fresh.commit()
    with pytest.raises(additive.Diverged):
        additive.plan(sql, existing_for(fresh, sql), triggers_of(fresh))
    assert "recovery_lease" not in columns_of(fresh, "connect_links"), "the plan ran anyway"


def test_a_same_name_trigger_with_the_same_body_reruns_as_the_no_op_it_is(fresh):
    sql = RECOVERY.read_text()
    to_run, skipped = additive.plan(sql, existing_for(fresh, sql), triggers_of(fresh))
    assert len(skipped) == len(additive.required_columns(sql))
    assert [n for n in additive.trigger_bodies(sql)] == [
        additive.CREATE_TRIGGER.match(additive._bare(st)).group("name").lower()
        for st in to_run if additive.CREATE_TRIGGER.match(additive._bare(st))]


def test_a_missing_trigger_is_planned_to_run(fresh):
    sql = RECOVERY.read_text()
    fresh.execute(f"DROP TRIGGER {NARROWED}")
    fresh.commit()
    to_run, _ = additive.plan(sql, existing_for(fresh, sql), triggers_of(fresh))
    assert any(NARROWED in st for st in to_run)


def test_not_looking_at_the_database_compares_nothing(fresh):
    """`triggers=None` is the planning-only call and must stay one."""
    sql = RECOVERY.read_text()
    narrow(fresh)
    additive.plan(sql, existing_for(fresh, sql))


def test_the_normaliser_cancels_what_the_engine_rewrites(fresh):
    """SQLite drops IF NOT EXISTS and the trailing semicolon and keeps the
    comments; the declaration has all three. They must compare equal, and a
    real change must not."""
    sql = RECOVERY.read_text()
    declared = additive.trigger_bodies(sql)
    stored = triggers_of(fresh)
    for name, body in declared.items():
        assert additive.normalize_sql(stored[name]) == body, name
    assert additive.normalize_sql("CREATE TRIGGER \"t\" -- c\n AFTER INSERT ON x BEGIN SELECT 1 ; END;") \
        == additive.normalize_sql("create trigger if not exists t after insert on x begin select 1;end")
    assert additive.normalize_sql("CREATE TRIGGER t AFTER INSERT ON x WHEN NEW.a=1 BEGIN SELECT 1; END") \
        != additive.normalize_sql("CREATE TRIGGER t AFTER INSERT ON x WHEN NEW.a=2 BEGIN SELECT 1; END")
