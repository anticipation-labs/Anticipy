"""backend/repair_data_db.sh, proven on a file that is actually broken.

2026-09-05: production's `agents` table went "database disk image is
malformed (11)" and the only tool that can put it right is SQLite's own
`.recover`. A repair that touches the one copy of every owner's data has to be
proven before it is switched on, so this builds a real SQLite file, breaks the
pages under one table on purpose, and runs the very script start.sh runs.

What it pins, each on a mutation that has been tried:
  - the original is kept byte for byte, so the repair is reversible by `mv`
  - the recovered file is what SQLite calls ok, and the untouched tables keep
    every row
  - the tag is one-shot: a second boot with the same tag does nothing
  - a healthy file is left alone — no copy, no marker, no swap
"""
import hashlib
import os
import pathlib
import shutil
import sqlite3
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "backend" / "repair_data_db.sh"

pytestmark = pytest.mark.skipif(shutil.which("sqlite3") is None, reason="needs the sqlite3 CLI")


def build(dirpath: pathlib.Path, *, corrupt: bool) -> pathlib.Path:
    db = dirpath / "data.db"
    c = sqlite3.connect(db)
    c.execute("PRAGMA page_size=4096")
    c.execute("CREATE TABLE owners(id TEXT PRIMARY KEY, name TEXT)")
    c.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, body TEXT)")
    c.executemany("INSERT INTO owners VALUES(?,?)", [(f"o{i}", f"owner {i}") for i in range(50)])
    c.executemany("INSERT INTO events VALUES(?,?)", [(i, "e" * 900) for i in range(2000)])
    c.commit()
    # agents last, so its leaf pages are allocated after every root page and
    # a hole punched just past its root lands in ITS tree and nobody else's.
    c.execute("CREATE TABLE agents(id TEXT PRIMARY KEY, agent_id TEXT, token TEXT)")
    c.execute("CREATE UNIQUE INDEX idx_agent ON agents(agent_id)")
    c.executemany("INSERT INTO agents VALUES(?,?,?)",
                  [(f"a{i}", f"agent-{i:04d}-" + "x" * 30, "t" * 64) for i in range(600)])
    c.commit()
    root = c.execute("SELECT rootpage FROM sqlite_master WHERE name='agents'").fetchone()[0]
    pages = c.execute("PRAGMA page_count").fetchone()[0]
    c.close()
    if corrupt:
        _punch_holes_in_agents_only(db, root, pages)
    return db


#: How many damaged pages the fixture is looking for. Three was the original
#: number and it is enough to orphan rows into lost_and_found.
HOLES_WANTED = 3


def _reads_whole(db: pathlib.Path, table: str, rows: int) -> bool:
    """Can every row of `table` still be read out of `db`?

    A fresh connection every time on purpose: SQLite caches pages, and a
    connection opened before the bytes changed will happily serve the old ones
    and report a file that is no longer there.
    """
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == rows
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()


def _punch_holes_in_agents_only(db: pathlib.Path, root: int, pages: int) -> None:
    """Damage the `agents` tree and NOTHING else, by checking rather than guessing.

    The fixture used to assume the layout: "agents last, so its leaf pages are
    allocated after every root page and a hole punched just past its root lands
    in ITS tree and nobody else's" -- and then punched `root+3 .. root+6`
    unconditionally. That assumption is a property of one SQLite version's
    allocator, not of SQLite. On this machine it held; on the CI runner it did
    not, and `root+3` landed in `owners`. `.recover` then dropped that table,
    the test asked it for a row count, and the failure surfaced as
    `sqlite3.OperationalError: no such table: owners` -- which reads like the
    repair script losing data, and is really the fixture aiming at the wrong
    page. It sat red across five pushes.

    So: try a page, keep the hole only if `owners` and `events` still read out
    whole and the file is now damaged, and put the bytes back otherwise. No
    page arithmetic to be right or wrong about, and nothing version-specific.
    """
    original = db.read_bytes()
    for page in range(root + 1, pages + 1):
        before = db.read_bytes()
        with open(db, "r+b") as f:
            f.seek((page - 1) * 4096 + 8)
            f.write(os.urandom(256))
        damaged = subprocess.run(["sqlite3", str(db), "PRAGMA integrity_check;"],
                                 capture_output=True, text=True).stdout.strip() != "ok"
        collateral = not (_reads_whole(db, "owners", 50) and _reads_whole(db, "events", 2000))
        if collateral or not damaged:
            db.write_bytes(before)          # this page was not agents-only; undo it
            continue
        if _count_holes(db, original) >= HOLES_WANTED:
            return
    raise AssertionError(
        f"could not damage {HOLES_WANTED} page(s) of `agents` without also "
        f"damaging `owners` or `events`, having tried pages {root + 1}..{pages}. "
        f"The fixture has not broken the file, so nothing below would be "
        f"measuring the repair."
    )


def _count_holes(db: pathlib.Path, original: bytes) -> int:
    """How many 4096-byte pages now differ from the file as first written."""
    now = db.read_bytes()
    return sum(1 for i in range(0, min(len(now), len(original)), 4096)
               if now[i:i + 4096] != original[i:i + 4096])


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(dirpath: pathlib.Path, tag: str) -> str:
    done = subprocess.run(["sh", str(SCRIPT), str(dirpath), tag], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def integrity(db: pathlib.Path) -> str:
    return subprocess.run(["sqlite3", str(db), "PRAGMA integrity_check;"],
                          capture_output=True, text=True).stdout.strip()


def count(db: pathlib.Path, table: str) -> int:
    return sqlite3.connect(db).execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def test_a_broken_file_is_rebuilt_and_the_original_kept(tmp_path):
    db = build(tmp_path, corrupt=True)
    before = sha(db)
    out = run(tmp_path, "t1")
    assert "done: data.db is the recovered file" in out, out
    assert integrity(db) == "ok"
    kept = [p for p in tmp_path.iterdir() if p.name.startswith("data.db.malformed-t1-")
            and not p.name.endswith((".final", "-wal", "-shm"))]
    assert len(kept) == 1, sorted(p.name for p in tmp_path.iterdir())
    assert sha(kept[0]) == before, "the original must survive byte for byte"
    # every row of the tables the damage never touched
    assert count(db, "owners") == 50
    assert count(db, "events") == 2000
    # and what the damage orphaned is listed, not vanished
    assert "lost_and_found" in out
    assert (tmp_path / "repair-t1.done").exists()
    # the recovered file must not sit beside a WAL that belonged to the old one
    assert not (tmp_path / "data.db-wal").exists()


def test_the_tag_is_one_shot(tmp_path):
    build(tmp_path, corrupt=True)
    run(tmp_path, "t2")
    db = tmp_path / "data.db"
    after_first = sha(db)
    out = run(tmp_path, "t2")
    assert "already ran" in out, out
    assert sha(db) == after_first
    assert len([p for p in tmp_path.iterdir() if p.name.startswith("data.db.malformed-")]) == 1


def test_a_healthy_file_is_left_alone(tmp_path):
    db = build(tmp_path, corrupt=False)
    before = sha(db)
    names = sorted(p.name for p in tmp_path.iterdir())
    out = run(tmp_path, "t3")
    assert "nothing to repair" in out, out
    assert sha(db) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == names, "no copy, no marker, no sql"


def test_start_sh_only_repairs_when_told(tmp_path):
    start = (ROOT / "backend" / "start.sh").read_text()
    assert 'if [ -n "${ANTICIPY_REPAIR_DATA_DB:-}" ]' in start
    assert "repair_data_db.sh /pb_data" in start
    docker = (ROOT / "backend" / "Dockerfile").read_text()
    assert "COPY repair_data_db.sh /app/repair_data_db.sh" in docker
    assert " sqlite " in docker or " sqlite\\" in docker or "wget sqlite" in docker


def test_a_dirty_recovery_is_never_swapped_in(tmp_path):
    """The one guard the fixture cannot reach on its own: `.recover` always
    yields a clean file here, so a shim makes sqlite3 report the RECOVERED
    file as broken and the script must leave the original in place."""
    real = shutil.which("sqlite3")
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "sqlite3"
    shim.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *data.db.recovered-*integrity_check*) echo '*** in database main ***'; echo 'Tree 4 page 5: shim'; exit 0;;\n"
        "esac\n"
        f"exec {real} \"$@\"\n"
    )
    shim.chmod(0o755)
    db = build(tmp_path, corrupt=True)
    before = sha(db)
    env = dict(os.environ, PATH=f"{shim_dir}:{os.environ['PATH']}")
    done = subprocess.run(["sh", str(SCRIPT), str(tmp_path), "t5"],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "NOT clean" in done.stdout, done.stdout
    assert sha(db) == before, "the original must still be data.db"
    assert not (tmp_path / "repair-t5.done").exists(), "a refused repair consumes no tag"
    assert any(p.name.startswith("data.db.recovered-t5-") for p in tmp_path.iterdir()), \
        "the refused file is left for a person to inspect"
