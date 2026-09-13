"""Refuse a Worker deploy the deployed database cannot carry.

    python3 -m proof.audit.d1_connector_readiness              # the live D1
    python3 -m proof.audit.d1_connector_readiness --local

WHY THIS IS A SEPARATE STEP AND NOT A COMMENT IN THE RUNBOOK. Two of this
release's code paths write columns that a database without the 2026-09-11
migrations does not have, and BOTH failures are invisible from the outside:

  * `connect_auth.reserve()` writes `connect_codes.delivery_state`. D1 answers
    "no column named delivery_state", `handleSend` swallows it, and the browser
    is handed the ordinary "enter the code we texted you" page. Every phone code
    fails and looks exactly like a slow text.
  * `connectPageGo` calls `recovery.ready()` before it redeems the link. Without
    the recovery columns AND the four cancellation triggers it throws, and every
    Connect tap returns provider-unavailable.

So the deploy asks the database first, and stops if the answer is no. This reads
schema metadata only: no owner row, no code, no credential, nothing to print.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from proof.audit.d1_additive import normalize_sql, trigger_bodies

ROOT = Path(__file__).resolve().parents[2]
#: Where the four triggers' bodies are declared. The deploy applies this file,
#: so it — not schema.sql — is what the deployed database is held to;
#: migration/workers/test/schema-migration-parity.test.ts holds schema.sql to it.
RECOVERY_MIGRATION = ROOT / "migration/d1/2026-09-11-oauth-recovery.sql"

#: What the code about to be deployed needs. Table -> columns.
REQUIRED_COLUMNS = {
    "connect_codes": ["delivery_state"],
    "connect_links": ["recovery_account_id", "recovery_deadline", "recovery_next_check",
                      "recovery_attempts", "recovery_lease"],
}
#: The half a columns-only check cannot see. A database with the columns and
#: none of these reports ready and runs OAuth recovery with no cancellation
#: fence at all, which is worse than an unapplied migration: an unapplied one
#: fails closed.
REQUIRED_TRIGGERS = [
    "cancel_oauth_recovery_deleted_connection",
    "cancel_oauth_recovery_disconnected_connection",
    "cancel_oauth_recovery_decline_insert",
    "cancel_oauth_recovery_decline_update",
]


def expected_triggers() -> dict[str, str]:
    """Trigger name -> the normalised CREATE the migration declares."""
    declared = trigger_bodies(RECOVERY_MIGRATION.read_text())
    absent = [name for name in REQUIRED_TRIGGERS if name not in declared]
    if absent:
        raise SystemExit(f"{RECOVERY_MIGRATION.name} no longer declares: {', '.join(absent)}")
    return {name: declared[name] for name in REQUIRED_TRIGGERS}


def verify(columns: dict[str, set[str]], triggers: dict[str, str],
           expected: dict[str, str] | None = None) -> list[str]:
    """Everything the deploy would break on, named. Empty means go.

    `triggers` is name -> the CREATE the database holds (sqlite_master.sql).
    A required trigger that is PRESENT BY NAME WITH ANOTHER BODY is refused
    like a missing one: the name is what `recovery.ready()` checks, so that is
    exactly the shape that passes readiness and cancels nothing — a decline
    trigger with a narrowed WHEN, say, left behind by a hand edit or an older
    migration that `CREATE TRIGGER IF NOT EXISTS` will never replace.
    """
    wanted_bodies = expected_triggers() if expected is None else expected
    # SQLite compares trigger names case-insensitively and stores them as
    # written, so a hand-recreated `CANCEL_...` is the engine's `cancel_...`.
    held = {str(name).lower(): body for name, body in triggers.items()}
    missing: list[str] = []
    for table, wanted in REQUIRED_COLUMNS.items():
        present = {c.lower() for c in columns.get(table, set())}
        if not present:
            missing.append(f"{table}: the table itself is absent or unreadable")
            continue
        missing += [f"{table}.{column}" for column in wanted if column not in present]
    for name in REQUIRED_TRIGGERS:
        if name not in held:
            missing.append(f"trigger {name}")
        elif normalize_sql(held[name]) != wanted_bodies[name]:
            missing.append(f"trigger {name}: present, but its body differs from "
                           f"{RECOVERY_MIGRATION.relative_to(ROOT)} — it would not cancel what "
                           "the code expects")
    return missing


def _wrangler(command: str, *, database: str, remote: bool, config: Path) -> list[dict]:
    args = ["npx", "--no-install", "wrangler", "d1", "execute", database,
            "--json", "--command", command, "--config", str(config)]
    if remote:
        args.append("--remote")
    done = subprocess.run(args, cwd=ROOT / "migration/workers", capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"wrangler refused: {done.stderr.strip()[-2000:]}")
    start = done.stdout.find("[")
    payload = json.loads(done.stdout[start:]) if start >= 0 else []
    rows: list[dict] = []
    for block in payload if isinstance(payload, list) else [payload]:
        rows.extend(block.get("results", []) if isinstance(block, dict) else [])
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", default="anticipy-backend")
    parser.add_argument("--config", type=Path, default=ROOT / "migration/workers/wrangler.jsonc")
    parser.add_argument("--local", action="store_true")
    args = parser.parse_args(argv)

    columns = {table: {str(row.get("name", "")) for row in
                       _wrangler(f"PRAGMA table_info({table})", database=args.database,
                                 remote=not args.local, config=args.config)}
               for table in REQUIRED_COLUMNS}
    triggers = {str(row.get("name", "")): str(row.get("sql") or "") for row in _wrangler(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger'",
        database=args.database, remote=not args.local, config=args.config) if row.get("name")}

    expected = expected_triggers()
    missing = verify(columns, triggers, expected)
    for table, wanted in REQUIRED_COLUMNS.items():
        print(f"{table}: {len(columns.get(table, set()))} columns, "
              f"{len([c for c in wanted if c in {x.lower() for x in columns.get(table, set())}])}"
              f"/{len(wanted)} required present")
    held = {name.lower(): body for name, body in triggers.items()}
    print(f"cancellation triggers: {len([t for t in REQUIRED_TRIGGERS if t in held])}"
          f"/{len(REQUIRED_TRIGGERS)} present, "
          f"{len([t for t in REQUIRED_TRIGGERS if t in held and normalize_sql(held[t]) == expected[t]])}"
          f"/{len(REQUIRED_TRIGGERS)} with the declared body")
    if missing:
        print("REFUSING THE DEPLOY. The database is missing:")
        for name in missing:
            print(f"  - {name}")
        print("Apply the 2026-09-11 migrations with proof/audit/d1_additive.py first.")
        return 1
    print("the deployed database can carry this release")
    return 0


if __name__ == "__main__":
    sys.exit(main())
