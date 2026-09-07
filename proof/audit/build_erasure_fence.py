"""Generate the explicit D1 erasure migration; no production access."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = [
    ("jobs", "owner_ref", "owner"), ("segments", "owner_ref", "owner"),
    ("agents", "owner_ref", "owner"), ("owner_profile", "owner_ref", "owner_id"),
    ("pendants", "owner_ref", "owner"), ("agent_llm_audit", "owner_ref", None),
    ("agent_audit_sessions", "owner_ref", None), ("evidence", "owner_ref", None),
    ("events", "owner_ref", None), ("password_resets", "owner", None),
    ("connect_codes", "user_id", None), ("connect_links", "user_id", None),
    ("connect_nudges", "user_id", None), ("app_usage_signals", "user_id", None),
    ("connections", "user_id", None), ("owners", "id", None),
]


def render():
    sql = ["""-- Erasure fence: a purge request is permanent identity state.
-- Apply before deploying the corresponding account deletion handler.
-- The handler refuses cleanup if these triggers are absent. No rows are
-- erased by this migration. Existing purge rows block subsequent writes.
-- Owner presence keeps the brain's memory purge consumer waiting while the
-- API retries provider/picture cleanup. DELETE remains available for cleanup.
CREATE INDEX IF NOT EXISTS idx_purges_owner_ref ON purges(owner_ref);
"""]
    for table, column, legacy in TABLES:
        for operation in ("INSERT", "UPDATE"):
            matches = []
            for version in (("NEW",) if operation == "INSERT" else ("NEW", "OLD")):
                matches.append(f'p.owner_ref = {version}."{column}"')
                if legacy:
                    matches.append(f'({version}.owner_ref = \'\' AND p.owner_ref = {version}."{legacy}")')
            sql.append(f'''CREATE TRIGGER IF NOT EXISTS erasure_fence_{table}_{operation.lower()}
BEFORE {operation} ON "{table}"
WHEN EXISTS (SELECT 1 FROM purges p WHERE {" OR ".join(matches)})
BEGIN
  SELECT RAISE(ABORT, 'ACCOUNT_ERASURE_IN_PROGRESS');
END;
''')
    return "\n".join(sql)


if __name__ == "__main__":
    migration = ROOT / "migration/d1/2026-09-07-account-erasure-fence.sql"
    migration.write_text(render())
    schema = ROOT / "migration/d1/schema.sql"
    marker = "-- BEGIN ACCOUNT ERASURE FENCE\n"
    source = schema.read_text()
    if marker in source:
        source = source.split(marker)[0]
    schema.write_text(source.rstrip() + "\n\n" + marker + render())
