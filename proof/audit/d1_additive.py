"""Apply an additive D1 migration so that applying it twice is a no-op.

    python3 -m proof.audit.d1_additive migration/d1/2026-09-11-oauth-recovery.sql
    python3 -m proof.audit.d1_additive <file> --apply --database anticipy-backend

WHY THIS EXISTS. The API deploy job applies its migrations by name on EVERY
run (.github/workflows/brain-deploy.yml), so a migration that is not rerunnable
turns the second deploy red. `CREATE ... IF NOT EXISTS` is rerunnable and the
two 2026-09-07 migrations are built entirely out of it. `ALTER TABLE ... ADD
COLUMN` is NOT: the second run fails with "duplicate column name", and
`CREATE TABLE IF NOT EXISTS` does not add a column to a table that already
exists, so the column cannot be smuggled in that way either.

WHAT THIS DOES. It reads the columns the database actually has, drops only the
`ADD COLUMN` statements whose column is already there, and runs everything else
verbatim. The planning half is pure and is what the tests exercise; the wrangler
half only moves bytes.

WHAT IT REFUSES. Any statement it cannot classify as rerunnable-by-construction
or as a recognised additive shape. A migration applier that skips what it does
not understand is how half a migration ships and nothing goes red.

NO CREDENTIALS ARE READ OR PRINTED HERE. Authentication is wrangler's own, from
the environment the deploy job already provides.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: A statement is safe to rerun when the engine itself makes it so. Spelled as
#: shapes rather than "starts with CREATE" because `CREATE INDEX` without the
#: guard is a second-run failure and must be caught here, not in production.
RERUNNABLE = (
    re.compile(r"^create\s+(unique\s+)?index\s+if\s+not\s+exists\b", re.I),
    re.compile(r"^create\s+trigger\s+if\s+not\s+exists\b", re.I),
    re.compile(r"^create\s+table\s+if\s+not\s+exists\b", re.I),
    re.compile(r"^create\s+view\s+if\s+not\s+exists\b", re.I),
    re.compile(r"^drop\s+(index|trigger|view|table)\s+if\s+exists\b", re.I),
    re.compile(r"^insert\s+or\s+ignore\b", re.I),
)

ADD_COLUMN = re.compile(
    r"^alter\s+table\s+[\"']?(?P<table>\w+)[\"']?\s+add\s+column\s+[\"']?(?P<column>\w+)[\"']?\b",
    re.I)


CREATE_TRIGGER = re.compile(
    r"^create\s+trigger\s+(?:if\s+not\s+exists\s+)?[\"']?(?P<name>\w+)[\"']?\b", re.I)


class Unclassified(Exception):
    """A statement this applier will not guess about."""


class Diverged(Exception):
    """A live object that has this migration's NAME and somebody else's BODY.

    `CREATE TRIGGER IF NOT EXISTS` is rerunnable only in the sense that the
    engine does not complain: when a trigger by that name already exists the
    statement is a no-op, whatever its body says. So a trigger edited in place
    in a later migration — or by hand on the deployed database — is never
    replaced by this applier, and every run reports success over a fence the
    code was not written against. This applier refuses that shape rather than
    guessing which body is the right one; a human drops the old trigger, or
    ships a migration that does, and says which.
    """


def normalize_sql(sql: str) -> str:
    """One trigger, as the engine would compare it.

    This is migration/workers/test/schema-migration-parity.test.ts's
    `normalize`, in Python, and must stay that: comments out, double quotes off,
    `IF NOT EXISTS` off (SQLite drops it from sqlite_master, so keeping it would
    compare a migration against a database that can never carry it), whitespace
    collapsed, punctuation unpadded, lowercased, and the trailing semicolon off
    (sqlite_master never stores one).
    """
    flat = re.sub(r"--[^\n]*", " ", sql)
    flat = flat.replace('"', "")
    flat = re.sub(r"\bIF\s+NOT\s+EXISTS\b", " ", flat, flags=re.I)
    flat = re.sub(r"\s+", " ", flat)
    flat = re.sub(r"\s*([(),;=])\s*", r"\1", flat)
    return flat.strip().lower().rstrip(";")


def trigger_bodies(sql: str) -> dict[str, str]:
    """Lower-cased trigger name -> its normalised CREATE, for every trigger this
    migration declares. Names are lower-cased because SQLite compares them
    case-insensitively: `Foo` and `foo` are the same trigger to the engine."""
    out: dict[str, str] = {}
    for statement in statements(sql):
        made = CREATE_TRIGGER.match(_bare(statement))
        if made:
            out[made.group("name").lower()] = normalize_sql(statement)
    return out


def statements(sql: str) -> list[str]:
    """Split on semicolons, keeping a trigger's BEGIN…END body in one piece."""
    out: list[str] = []
    buffer, depth = "", 0
    for line in sql.splitlines():
        bare = re.sub(r"--[^\n]*", "", line)
        buffer += line + "\n"
        if re.search(r"\bBEGIN\b", bare, re.I):
            depth += 1
        if re.search(r"\bEND\s*;", bare, re.I) and depth:
            depth -= 1
        if not depth and bare.rstrip().endswith(";"):
            if re.sub(r"--[^\n]*", "", buffer).strip():
                out.append(buffer.strip())
            buffer = ""
    if re.sub(r"--[^\n]*", "", buffer).strip():
        out.append(buffer.strip())
    return out


def _bare(statement: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"--[^\n]*", " ", statement)).strip()


def plan(sql: str, existing: dict[str, set[str]],
         triggers: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """Return (to_run, skipped). `existing` maps table -> lowercase columns.

    A table absent from `existing` is a table this applier has never been told
    about, and an ADD COLUMN against it runs — the engine's own error is a
    better answer than a guess about whether the table exists.

    `triggers` maps lower-cased trigger name -> the CREATE the database holds
    (sqlite_master.sql), for the triggers this migration declares. A declared
    trigger the database already has with the SAME body is rerunnable and
    reruns as the no-op it is; one it has with a DIFFERENT body raises
    `Diverged` before anything is planned (see the class). `None` means the
    caller did not look, and no trigger is compared — the planning-only tests
    and a migration that declares no trigger pass nothing.
    """
    to_run: list[str] = []
    skipped: list[str] = []
    for statement in statements(sql):
        flat = _bare(statement)
        if not flat:
            continue
        made = CREATE_TRIGGER.match(flat)
        if made and triggers is not None:
            name = made.group("name").lower()
            live = triggers.get(name)
            if live is not None and normalize_sql(live) != normalize_sql(statement):
                raise Diverged(
                    f"trigger {name}: the database already has a trigger by this name with a "
                    "different body, and CREATE TRIGGER IF NOT EXISTS would leave the live one in "
                    "place while reporting success")
        added = ADD_COLUMN.match(flat)
        if added:
            table = added.group("table").lower()
            column = added.group("column").lower()
            if column in existing.get(table, set()):
                skipped.append(f"{table}.{column} already present")
            else:
                to_run.append(statement)
            continue
        if any(shape.match(flat) for shape in RERUNNABLE):
            to_run.append(statement)
            continue
        raise Unclassified(flat[:200])
    return to_run, skipped


def tables_in(sql: str) -> list[str]:
    """Every table an ADD COLUMN in this migration touches."""
    seen: list[str] = []
    for statement in statements(sql):
        added = ADD_COLUMN.match(_bare(statement))
        if added:
            table = added.group("table").lower()
            if table not in seen:
                seen.append(table)
    return seen


def required_columns(sql: str) -> list[tuple[str, str]]:
    """(table, column) for every column this migration is responsible for."""
    out: list[tuple[str, str]] = []
    for statement in statements(sql):
        added = ADD_COLUMN.match(_bare(statement))
        if added:
            out.append((added.group("table").lower(), added.group("column").lower()))
    return out


# --------------------------------------------------------------- the wrangler half


def _wrangler(args: list[str], *, config: Path) -> str:
    command = ["npx", "--no-install", "wrangler", "d1", "execute", *args,
               "--config", str(config)]
    done = subprocess.run(command, cwd=ROOT / "migration/workers",
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"wrangler refused: {done.stderr.strip()[-2000:]}")
    return done.stdout


def live_columns(database: str, tables: list[str], *, remote: bool, config: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for table in tables:
        args = [database, "--json", "--command", f"PRAGMA table_info({table})"]
        if remote:
            args.append("--remote")
        found[table] = {str(row.get("name", "")).lower()
                        for row in _rows(_wrangler(args, config=config))}
    return found


def _rows(raw: str) -> list[dict]:
    start = raw.find("[")
    payload = json.loads(raw[start:]) if start >= 0 else []
    rows: list[dict] = []
    for block in payload if isinstance(payload, list) else [payload]:
        rows.extend(block.get("results", []) if isinstance(block, dict) else [])
    return rows


def live_triggers(database: str, *, remote: bool, config: Path) -> dict[str, str]:
    """Lower-cased trigger name -> the CREATE the database holds. Schema
    metadata only: sqlite_master carries no owner's row."""
    args = [database, "--json", "--command",
            "SELECT name, sql FROM sqlite_master WHERE type='trigger'"]
    if remote:
        args.append("--remote")
    return {str(row.get("name", "")).lower(): str(row.get("sql") or "")
            for row in _rows(_wrangler(args, config=config)) if row.get("name")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("migration", type=Path)
    parser.add_argument("--database", default="anticipy-backend")
    parser.add_argument("--config", type=Path,
                        default=ROOT / "migration/workers/wrangler.jsonc")
    parser.add_argument("--local", action="store_true",
                        help="plan against the local D1 rather than the deployed one")
    parser.add_argument("--apply", action="store_true",
                        help="execute the plan; without it nothing is written")
    args = parser.parse_args(argv)

    sql = args.migration.read_text()
    tables = tables_in(sql)
    existing = (live_columns(args.database, tables, remote=not args.local, config=args.config)
                if tables else {})
    for table in tables:
        print(f"{table}: {len(existing.get(table, set()))} columns already present")
    declared = trigger_bodies(sql)
    triggers = (live_triggers(args.database, remote=not args.local, config=args.config)
                if declared else None)
    if triggers is not None:
        print(f"triggers: {len([n for n in declared if n in triggers])}/{len(declared)} "
              "declared here already present")
    try:
        to_run, skipped = plan(sql, existing, triggers)
    except Unclassified as why:
        print(f"REFUSING: this applier cannot classify a statement: {why}")
        print("Add its shape to RERUNNABLE, or apply this migration by hand.")
        return 2
    except Diverged as why:
        print(f"REFUSING: {why}")
        print("Decide which body the database should carry, DROP the live trigger by hand "
              "(or ship a migration that does), then rerun.")
        return 3
    for note in skipped:
        print(f"skip: {note}")
    print(f"{len(to_run)} statement(s) to run, {len(skipped)} already applied")
    if not args.apply:
        print("(planning only — pass --apply to execute)")
        return 0

    for statement in to_run:
        run_args = [args.database, "--command", statement]
        if not args.local:
            run_args.append("--remote")
        _wrangler(run_args, config=args.config)

    after = live_columns(args.database, tables, remote=not args.local, config=args.config) if tables else {}
    missing = [f"{table}.{column}" for table, column in required_columns(sql)
               if column not in after.get(table, set())]
    if missing:
        print("REFUSING: the migration ran and these columns are still absent: "
              + ", ".join(missing))
        return 1
    if declared:
        after_triggers = live_triggers(args.database, remote=not args.local, config=args.config)
        wrong = [name for name, body in declared.items()
                 if normalize_sql(after_triggers.get(name, "")) != body]
        if wrong:
            print("REFUSING: the migration ran and these triggers are absent or carry another "
                  "body: " + ", ".join(wrong))
            return 1
    print("applied; every column and trigger this migration declares is present as declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
