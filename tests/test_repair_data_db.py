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
import re
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
    """Can every row of `table` still be read out of `db`'s OWN PAGES?

    `NOT INDEXED` is the whole point. `owners` is `id TEXT PRIMARY KEY`, so it
    carries `sqlite_autoindex_owners_1`, and a bare `SELECT count(*)` is
    answered by counting that index -- which stays perfectly readable while the
    table's own b-tree is full of holes. The first version of this helper did
    exactly that, pronounced `owners` intact, and let the fixture punch its
    pages. `.recover` reads TABLE pages, so it then dropped the table, the
    repair swapped the result in, and CI reported `no such table: owners`.
    `repair_data_db.sh` step 5 already says `NOT INDEXED` for this reason.

    A fresh connection every time on purpose: SQLite caches pages, and a
    connection opened before the bytes changed will happily serve the old ones
    and report a file that is no longer there.
    """
    conn = sqlite3.connect(db)
    try:
        n = conn.execute(f'SELECT count(*) FROM "{table}" NOT INDEXED').fetchone()[0]
        return n == rows
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
    for page in _candidate_pages(db, root, pages):
        before = db.read_bytes()
        with open(db, "r+b") as f:
            f.seek((page - 1) * 4096 + 8)
            f.write(os.urandom(256))
        damaged = subprocess.run(["sqlite3", str(db), "PRAGMA integrity_check;"],
                                 capture_output=True, text=True).stdout.strip() != "ok"
        collateral = not (_reads_whole(db, "owners", 50) and _reads_whole(db, "events", 2000))
        if collateral or not damaged or not _still_recoverable(db):
            db.write_bytes(before)          # this page was not agents-only; undo it
            continue
        if _count_holes(db, original) >= HOLES_WANTED:
            return
    raise AssertionError(
        f"could not damage {HOLES_WANTED} page(s) of `agents` while leaving "
        f"`owners` and `events` both readable AND still visible to `.recover`, "
        f"having tried {len(_candidate_pages(db, root, pages))} page(s) "
        f"(dbstat named {len(_agents_pages(db))} of them) with sqlite3 "
        f"{sqlite3.sqlite_version}. The fixture has not built the file this "
        f"test is about, so nothing below would be measuring the repair -- and "
        f"that is a fixture problem, NOT a verdict on repair_data_db.sh."
    )


def _agents_pages(db: pathlib.Path) -> list:
    """The pages SQLite says belong to `agents`, when it will say.

    `dbstat` is a virtual table compiled in by default on Debian/Ubuntu and on
    macOS, and it answers exactly the question the old fixture was guessing at.
    Its `path` is '/' for the root page, so anything else is a page whose loss
    damages the tree without taking the table's entry with it.

    Returns [] rather than raising when dbstat is not compiled in -- the caller
    falls back to trying every page, which is slower and still correct.
    """
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT pageno FROM dbstat WHERE name='agents' AND path<>'/' "
            "ORDER BY pageno"
        ).fetchall()
        return [r[0] for r in rows]
    except sqlite3.DatabaseError:
        return []
    finally:
        conn.close()


def _candidate_pages(db: pathlib.Path, root: int, pages: int) -> list:
    """Pages to try, best first.

    `agents`'s own non-root pages come first and are usually the whole answer;
    everything after the root follows as a fallback for a SQLite built without
    dbstat. Every page still has to pass the three checks in the caller, so
    this ordering only decides how fast the fixture gets there -- it is not
    trusted to be right.
    """
    known = _agents_pages(db)
    rest = [n for n in range(root + 1, pages + 1) if n not in set(known)]
    return known + rest


def _still_recoverable(db: pathlib.Path) -> bool:
    """Can `.recover` still SEE `owners` and `events` in this file?

    The fixture's job is "a file whose damage is confined to `agents`", and
    reading the two other tables is not enough to establish that. A hole can
    leave `owners` perfectly readable through its own root page while wrecking
    something `.recover` walks to find the schema -- and `.recover` then emits
    its scaffolding and nothing else. On GitHub's runner that is exactly what
    happened: 172 bytes of SQL, no tables at all, and a recovered file that
    passes `PRAGMA integrity_check` as "ok" because an empty database is a
    valid one. The repair script's step-5 gate caught it and refused the swap,
    which is the gate working -- but the fixture had stopped building the
    scenario this test is about.

    So the precondition is checked rather than hoped for. A page that costs
    `.recover` the whole schema is not agents-only damage, whatever a
    `SELECT count(*)` says.
    """
    out = subprocess.run(["sqlite3", str(db), ".recover"],
                         capture_output=True, text=True).stdout
    # `.recover` writes the schema unquoted and the rows single-quoted:
    #     CREATE TABLE owners(id TEXT PRIMARY KEY, name TEXT);
    #     INSERT OR IGNORE INTO 'owners'(_rowid_, 'id', 'name') VALUES (...);
    # The first draft of this looked for '"owners"' and so matched NOTHING, on
    # any file, healthy or not -- the same silently-unmatched-anchor mistake
    # that has produced three false "it is tested" readings this week. Both
    # halves are required: the CREATE alone would pass on a file whose rows
    # were all lost.
    return all(f"CREATE TABLE {t}" in out and f"INTO '{t}'" in out
               for t in ("owners", "events"))


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
    # WHAT THE DAMAGED TABLE DID, said out loud. Not "listed, not vanished" --
    # that was the old claim here and a measured run disproves it: `agents`
    # came back 497 of 600 with `lost_and_found` holding ZERO, because cells
    # `.recover` cannot parse as cells do not become lost_and_found entries.
    # They are gone. The guarantee is that the shortfall is NAMED and the
    # original is still on disk, so a person can decide about it.
    assert "lost_and_found" in out
    recovered = int(re.search(r"rows agents: original=600 recovered=(\d+)", out).group(1))
    assert recovered < 600, (
        "the fixture no longer damages `agents` at all, so this test is "
        "measuring a healthy-file repair:\n" + out
    )
    assert f"agents is short by {600 - recovered} row(s)" in out, (
        "the repair lost rows out of `agents` and did not say so:\n" + out
    )
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


def test_a_recovery_that_lost_a_table_is_refused(tmp_path):
    """The swap must not happen when `.recover` dropped a table the original had.

    THIS IS A REAL FAILURE, not a hypothetical. On GitHub's runner, a file whose
    damage was confined to `agents` recovered without `owners` at all --
    `.recover` reads TABLE pages and those had holes in them, while the
    autoindex that answers a bare `count(*)` did not. The recovered file passed
    `PRAGMA integrity_check` as "ok", because an empty database is a perfectly
    valid one, so step 4 waved it through. The script printed "rows owners:
    original=50 recovered=missing" and then swapped it in and said "done".

    The original is kept, so it was recoverable by hand. Nothing in the output
    said anybody needed to.

    Reproducing the SQLite-version behaviour that caused it is not possible on
    every machine, so this drives the branch directly: a `sqlite3` shim on PATH
    that is the real thing for every call EXCEPT counting `owners` in the
    recovered file, where it fails the way the runner's did.
    """
    real = shutil.which("sqlite3")
    assert real, "needs the sqlite3 CLI"

    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "sqlite3"
    shim.write_text(
        "#!/bin/sh\n"
        "# Real sqlite3, except: counting `owners` in the RECOVERED file fails,\n"
        "# which is what the runner's .recover left behind.\n"
        'case "$*" in\n'
        '  *.recovered-*owners*) exit 1 ;;\n'
        "esac\n"
        f'exec {real} "$@"\n'
    )
    shim.chmod(0o755)

    db = build(tmp_path, corrupt=True)
    before = sha(db)

    env = dict(os.environ, PATH=f"{shim_dir}:{os.environ.get('PATH', '')}")
    done = subprocess.run(["sh", str(SCRIPT), str(tmp_path), "t9"],
                          capture_output=True, text=True, env=env)
    out = done.stdout + done.stderr

    assert done.returncode == 0, out
    assert "STOPPING: the recovered file has LOST a table" in out, out
    assert "owners(original=50 recovered=missing)" in out, out
    assert "done: data.db is the recovered file" not in out, (
        "the script announced a successful repair after losing a table:\n" + out
    )

    # THE CONTROL, and the point of keeping the original: nothing was swapped.
    assert sha(db) == before, "data.db was replaced by a file missing `owners`"
    assert not (tmp_path / "repair-t9.done").exists(), (
        "a refused repair left its one-shot marker behind, so a retry after the "
        "cause is fixed would be skipped:\n" + out
    )


def test_what_recover_complains_about_is_printed_not_counted(tmp_path):
    """`.recover`'s stderr is the diagnostic, and it used to be thrown away.

    The line read ".recover wrote 172 bytes of SQL (1 stderr lines)" on
    GitHub's runner. 172 bytes is `.recover`'s scaffolding and nothing else --
    no tables at all -- and the one stderr line was the reason why. It was
    counted and discarded, so the only visible symptom was a number nobody
    could act on, and the next line said the recovered file passed
    integrity_check as "ok", because an empty database does.

    Counting a diagnostic is not reading one.
    """
    real = shutil.which("sqlite3")
    assert real, "needs the sqlite3 CLI"

    complaint = "recovery scan aborted at page 999"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    shim = shim_dir / "sqlite3"
    shim.write_text(
        "#!/bin/sh\n"
        "# Real sqlite3, except the .recover CALL also complains on stderr.\n"
        "#\n"
        "# Matching `$2` and not `$*`: the recovered file is named\n"
        "# data.db.recovered-<tag>-<stamp>, so a glob of *.recover* fires on\n"
        "# every later call that mentions that PATH -- including the\n"
        "# integrity_check on it, which then read 'ok <complaint>' and failed\n"
        "# the clean-file check. The script invokes `sqlite3 <db> .recover`,\n"
        "# so the command is exactly $2.\n"
        'if [ "${2:-}" = ".recover" ]; then\n'
        f'  {real} "$@"; echo "{complaint}" >&2; exit 0\n'
        "fi\n"
        f'exec {real} "$@"\n'
    )
    shim.chmod(0o755)

    build(tmp_path, corrupt=True)
    env = dict(os.environ, PATH=f"{shim_dir}:{os.environ.get('PATH', '')}")
    done = subprocess.run(["sh", str(SCRIPT), str(tmp_path), "t8"],
                          capture_output=True, text=True, env=env)
    out = done.stdout + done.stderr

    assert complaint in out, (
        "the script did not print what .recover said on stderr:\n" + out
    )
    # THE CONTROL: a complaint is not by itself a reason to stop. .recover
    # found everything here, so the repair still finishes.
    assert "done: data.db is the recovered file" in out, out
