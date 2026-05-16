"""Static RLS coverage validator.

Proves, by parsing the actual production migration DDL, that EVERY
user data table has Row Level Security enabled AND an explicit per
user policy keyed on auth.uid() in the SAME migration that creates it.
A table without both is inaccessible by design intent and is a hard
build failure. This is the "every new table has RLS proven on" gate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
MIGRATION = ENGINE / "migrations" / "0001_anticipy_system_v1.sql"


def validate(path: Path = MIGRATION) -> tuple[bool, list]:
    sql = path.read_text(encoding="utf-8")
    low = sql.lower()
    tables = re.findall(r"create table\s+([a-z0-9_\.]+)\s*\(", low)
    log = []
    ok = True
    for t in tables:
        bare = t.split(".")[-1]
        has_rls = re.search(
            rf"alter table\s+{re.escape(t)}\s+enable row level security", low
        ) is not None
        # an explicit per user policy on this table keyed on auth.uid()
        pol = re.search(
            rf"create policy\s+\w+\s+on\s+{re.escape(t)}\b(.*?);", low, re.S
        )
        has_policy = pol is not None and "auth.uid()" in (pol.group(1) if pol else "")
        good = has_rls and has_policy
        ok &= good
        log.append(
            f"[{'ok' if good else 'FAIL'}] {bare}: rls_enabled={has_rls} "
            f"per_user_policy_auth_uid={has_policy}"
        )
    if not tables:
        ok = False
        log.append("[FAIL] no create table statements found in migration")
    # Vault: OAuth tokens must be referenced by opaque key, never stored
    # as plaintext columns named like a token/secret/password.
    bad_secret_cols = re.findall(r"\b(oauth_token|access_token|refresh_token|password)\s+text", low)
    if bad_secret_cols:
        ok = False
        log.append(f"[FAIL] plaintext secret columns present: {bad_secret_cols}")
    else:
        log.append("[ok] no plaintext OAuth/secret columns (opaque vault keys only)")
    return ok, log


def main() -> int:
    ok, log = validate()
    print(f"RLS coverage validator: {MIGRATION.relative_to(ENGINE)}")
    for line in log:
        print("  " + line)
    print("RLS_VALIDATOR_PASS" if ok else "RLS_VALIDATOR_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
