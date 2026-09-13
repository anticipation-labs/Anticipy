"""Pin the real applier's argument boundary, including leading SQL comments.

The actual Wrangler leg additionally needs macOS sandbox-exec and installed
lockfile tooling. Enable ANTICIPY_WRANGLER_LOCAL_PROOF=1 without an outer
sandbox: each CLI child is confined here, and macOS forbids nested sandboxes.
Portable argv/refusal regressions run on every platform, including CI.
"""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from proof.audit import d1_additive as additive


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [ROOT / "migration/d1" / name for name in (
    "2026-09-11-connect-code-delivery.sql", "2026-09-11-oauth-recovery.sql")]


def capture_applier(monkeypatch, sql):
    calls = []
    required = additive.required_columns(sql)
    declared = additive.trigger_bodies(sql)
    monkeypatch.setattr(additive, "live_columns", lambda *_args, **_kwargs: {
        table: {column for wanted_table, column in required if wanted_table == table}
        if calls else set() for table in additive.tables_in(sql)})
    monkeypatch.setattr(additive, "live_triggers", lambda *_args, **_kwargs: declared if calls else {})
    def run(command, **kwargs):
        calls.append((list(command), kwargs))
        return SimpleNamespace(returncode=0, stdout="[]", stderr="")
    monkeypatch.setattr(additive.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda path: path.stem)
@pytest.mark.parametrize("local", [False, True])
def test_main_binds_each_full_commented_statement_to_one_command_argument(monkeypatch, tmp_path, migration, local):
    sql = migration.read_text()
    statements = additive.statements(sql)
    assert statements[0].startswith("--")
    calls = capture_applier(monkeypatch, sql)
    config = tmp_path / "configuration with spaces.jsonc"
    args = [str(migration), "--apply", "--database", "synthetic-database", "--config", str(config)]
    if local:
        args.append("--local")
    assert additive.main(args) == 0
    assert len(calls) == len(statements)
    for (command, kwargs), statement in zip(calls, statements):
        assert command[:5] == ["npx", "--no-install", "wrangler", "d1", "execute"]
        assert command[5] == "synthetic-database"
        assert [arg for arg in command if arg.startswith("--command=")] == ["--command=" + statement]
        assert "--command" not in command
        assert command[-2:] == ["--config", str(config)]
        assert ("--remote" in command) is not local
        assert "--preview" not in command
        assert kwargs.get("shell", False) is False
        assert kwargs["capture_output"] is True and kwargs["text"] is True


def test_main_preserves_quotes_unicode_dollars_backticks_and_newlines_without_shell(monkeypatch, tmp_path):
    sql = "-- comment --remote --config=value\nCREATE TABLE IF NOT EXISTS fixture(value TEXT DEFAULT '$NAME `whoami` \"q\" Ω=a=b');\n"
    migration = tmp_path / "literal.sql"
    migration.write_text(sql)
    calls = capture_applier(monkeypatch, sql)
    assert additive.main([str(migration), "--apply", "--local"]) == 0
    command, kwargs = calls[0]
    expected = additive.statements(sql)[0]
    assert [arg for arg in command if arg.startswith("--command=")] == ["--command=" + expected]
    assert kwargs.get("shell", False) is False
    assert "--remote" not in command


@pytest.mark.parametrize("migration", MIGRATIONS, ids=lambda path: path.stem)
def test_planning_only_never_invokes_a_write(monkeypatch, migration):
    calls = capture_applier(monkeypatch, migration.read_text())
    assert additive.main([str(migration), "--local"]) == 0
    assert calls == []


def test_unclassified_statement_refuses_before_any_write(monkeypatch, tmp_path):
    migration = tmp_path / "unsafe.sql"
    migration.write_text("DELETE FROM fixture;\n")
    calls = capture_applier(monkeypatch, migration.read_text())
    assert additive.main([str(migration), "--apply", "--local"]) == 2
    assert calls == []


def test_diverged_trigger_refuses_before_any_write(monkeypatch):
    migration = MIGRATIONS[1]
    calls = capture_applier(monkeypatch, migration.read_text())
    name = next(iter(additive.trigger_bodies(migration.read_text())))
    monkeypatch.setattr(additive, "live_triggers", lambda *_args, **_kwargs: {name: "SELECT 1"})
    assert additive.main([str(migration), "--apply", "--local"]) == 3
    assert calls == []


def test_execution_failure_stops_later_statements_and_postchecks(monkeypatch):
    migration = MIGRATIONS[1]
    queries = []
    writes = []
    def columns(*_args, **_kwargs):
        queries.append("columns")
        return {"connect_links": set()}
    def triggers(*_args, **_kwargs):
        queries.append("triggers")
        return {}
    def fail(command, **_kwargs):
        writes.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="synthetic CLI refusal")
    monkeypatch.setattr(additive, "live_columns", columns)
    monkeypatch.setattr(additive, "live_triggers", triggers)
    monkeypatch.setattr(additive.subprocess, "run", fail)
    with pytest.raises(SystemExit, match="synthetic CLI refusal"):
        additive.main([str(migration), "--apply", "--local"])
    assert len(writes) == 1
    assert queries == ["columns", "triggers"]


@pytest.mark.skipif(sys.platform != "darwin", reason=(
    "actual Wrangler proof requires macOS sandbox-exec for enforced outbound denial; "
    "portable argv/refusal regressions run on every platform"))
@pytest.mark.skipif(os.environ.get("ANTICIPY_WRANGLER_LOCAL_PROOF") != "1", reason=(
    "separate actual Wrangler proof: set ANTICIPY_WRANGLER_LOCAL_PROOF=1 without an outer sandbox; "
    "the test confines each CLI child and macOS prohibits nested sandboxes"))
def test_installed_wrangler_roundtrips_both_migrations_in_isolated_local_d1(monkeypatch, tmp_path):
    """Real CLI/parser + local D1, no account/config/state from production."""
    installed = ROOT / "migration/workers/node_modules"
    if not (installed / "wrangler/bin/wrangler.js").is_file() or not shutil.which("npx"):
        pytest.skip("requires the repository's lockfile-installed Wrangler and Node tooling")
    assert Path("/usr/bin/sandbox-exec").is_file()
    from d1_schema_fixture import schema_for_column_rewind
    from tests.test_d1_additive import wind_back

    temporary = tmp_path.resolve()
    project = temporary / "project"
    working = project / "migration/workers"
    working.mkdir(parents=True)
    (working / "node_modules").symlink_to(installed.resolve(), target_is_directory=True)
    config = project / "wrangler.json"
    config.write_text(json.dumps({"name": "migration-transport-proof", "compatibility_date": "2026-09-03",
        "d1_databases": [{"binding": "DB", "database_name": "transport-fixture",
                          "database_id": "00000000-0000-4000-8000-000000000001"}]}))
    scratch = temporary / "scratch"
    scratch.mkdir()
    persistence = temporary / "local-d1"
    # Derive the dependency tables from the real schema and rewind only these
    # two migrations. This proof measures CLI transport; full-schema behavior
    # is independently covered by test_d1_additive.py.
    tables = ("owners", "connect_codes", "connect_links", "connections", "connect_nudges", "purges")
    with sqlite3.connect(":memory:") as source:
        source.executescript(schema_for_column_rewind((ROOT / "migration/d1/schema.sql").read_text()))
        for migration in MIGRATIONS:
            wind_back(source, migration.read_text())
        declarations = [source.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                                       (table,)).fetchone()[0] + ";" for table in tables]
    bootstrap = temporary / "bootstrap.sql"
    bootstrap.write_text("\n".join(declarations))

    environment = {key: os.environ[key] for key in ("PATH", "HOME", "LANG") if key in os.environ}
    environment.update(TMPDIR=str(scratch), PYTHON_DOTENV_DISABLED="1",
        CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV="false", WRANGLER_SEND_METRICS="false",
        WRANGLER_WRITE_LOGS="false", npm_config_offline="true",
        npm_config_userconfig="/dev/null", npm_config_cache=str(temporary / "npm-cache"), NO_COLOR="1")
    private_envs = [ROOT.parent / ".env", ROOT / ".env", ROOT / ".env.local",
                    ROOT.parent / "anticipy/.env", ROOT.parent / "anticipy/.env.local"]
    profile = ('(version 1)(allow default)(deny network-outbound)'
               '(allow network-outbound (remote ip "localhost:*"))'
               '(deny file-write*)'
               f'(allow file-write* (subpath {json.dumps(str(temporary))}))'
               '(allow file-write* (literal "/dev/null"))'
               + "".join(f'(deny file-read* (literal {json.dumps(str(path))}))' for path in private_envs))
    actual_run = additive.subprocess.run
    calls = []
    def run_local(command, **kwargs):
        assert command[:5] == ["npx", "--no-install", "wrangler", "d1", "execute"]
        assert command[5] == "transport-fixture" and "--remote" not in command and "--preview" not in command
        assert command[-2:] == ["--config", str(config)]
        calls.append(list(command))
        return actual_run(["/usr/bin/sandbox-exec", "-p", profile, *command,
                           "--local", "--persist-to", str(persistence)],
                          **kwargs, env=environment, timeout=45)
    monkeypatch.setattr(additive, "ROOT", project)
    monkeypatch.setattr(additive.subprocess, "run", run_local)
    additive._wrangler(["transport-fixture", "--file", str(bootstrap)], config=config)

    for migration in MIGRATIONS:
        sql = migration.read_text()
        before = len(calls)
        args = [str(migration), "--local", "--database", "transport-fixture", "--config", str(config)]
        assert additive.main(args) == 0
        assert all("--json" in command for command in calls[before:])
        before = len(calls)
        assert additive.main([*args, "--apply"]) == 0
        writes = [command for command in calls[before:] if "--json" not in command]
        assert [next(arg.removeprefix("--command=") for arg in command if arg.startswith("--command="))
                for command in writes] == additive.statements(sql)
        before = len(calls)
        assert additive.main([*args, "--apply"]) == 0
        # Replay may issue IF NOT EXISTS indexes/triggers, never another ALTER.
        assert not any(arg.startswith("--command=") and additive.ADD_COLUMN.match(additive._bare(arg[10:]))
                       for command in calls[before:] for arg in command)

    checks = additive._rows(additive._wrangler(["transport-fixture", "--json", "--command",
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name='connect_codes'"], config=config))
    assert len(checks) == 1
    assert "delivery_state" in checks[0]["sql"] and "DEFAULT 'accepted'" in checks[0]["sql"]
    assert "'pending', 'accepted', 'failed'" in checks[0]["sql"]
    recovery = additive._rows(additive._wrangler(["transport-fixture", "--json", "--command",
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name='connect_links'"], config=config))
    assert len(recovery) == 1
    assert "recovery_attempts INTEGER NOT NULL DEFAULT 0" in recovery[0]["sql"]
    assert "CHECK(recovery_attempts BETWEEN 0 AND 16)" in recovery[0]["sql"]
