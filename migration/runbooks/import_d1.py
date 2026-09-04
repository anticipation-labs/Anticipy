#!/usr/bin/env python3
"""Load a verified PocketBase export into Cloudflare D1, and prove it landed.

Reads the directory produced by ``export_pocketbase.sh`` and

  1. verifies the export against its own manifest (SHA-256 per file) before
     touching anything -- an unverified export is not an export;
  2. derives a landing schema from the collection definitions the SERVER
     reported, so the nine fellowship collections that exist in production but
     in no migration in this repo (``fellows``, ``fellow_applications``,
     ``fellow_submissions``, ``fellow_payouts``, ``fellow_conversions``,
     ``fellow_codes``, ``fellow_clicks``, ``fellow_progress``,
     ``fellow_meter`` -- migration/d1/FELLOWSHIP-PRECEDENT.md and
     migration/d1/GAPS.md) get tables too;
  3. emits D1-ready SQL in size-bounded chunks;
  4. optionally executes it with ``wrangler d1 execute``;
  5. reconciles source row counts against destination row counts and EXITS
     NON-ZERO on any mismatch.

THE VAULT INTERLOCK
-------------------
``internal_passwords.secret_enc`` is ciphertext produced by PocketBase's Go
``$security.encrypt`` under ``ANTICIPY_VAULT_KEY``
(backend/pb_hooks/internal_hq.pb.js:3079, read back at :3140).  Carrying those
bytes into D1 produces a vault that looks intact and cannot be opened, because
the only process that could ever decrypt it is the one being switched off.
This script therefore REFUSES to import non-empty ``secret_enc`` values unless
``<export>/vault/vault_rewrapped.json`` is present -- the receipt written by the
procedure in ``reencrypt_vault.md``.  Override with
``--allow-unreadable-vault`` only if you have decided, deliberately, to lose
the company's tool logins.

Python 3.9 compatible.  Standard library only.

Exit codes: 0 ok | 2 usage/preflight | 3 reconciliation failure | 4 wrangler failure
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------

# PocketBase attaches these to every record it serialises.  They describe the
# response, not the row, and a table that stores them stores the same two
# strings a few hundred thousand times.
PB_META_KEYS = ("collectionId", "collectionName", "expand")

# Characters that may appear inside a bare '...' SQL literal.  Anything else --
# a quote, a semicolon, a backslash, a newline, any non-ASCII byte -- is
# emitted as CAST(x'<hex>' AS TEXT) instead, so that no statement splitter
# anywhere in the toolchain can be confused by row content.  `fellows` rows
# with an apostrophe in a surname are exactly the case this exists for.
SAFE_LITERAL = re.compile(r"^[A-Za-z0-9 _\-.,:/@+=?#%&()\[\]{}*^$!~|<>\"]*$")

# PocketBase field type -> SQLite/D1 column type.
TYPE_MAP = {
    "text": "TEXT",
    "editor": "TEXT",
    "email": "TEXT",
    "url": "TEXT",
    "password": "TEXT",
    "date": "TEXT",
    "autodate": "TEXT",
    "json": "TEXT",
    "select": "TEXT",
    "relation": "TEXT",
    "file": "TEXT",
    "geoPoint": "TEXT",
    "number": "NUMERIC",
    "bool": "INTEGER",
}

VAULT_COLLECTION = "internal_passwords"
VAULT_CIPHERTEXT_FIELD = "secret_enc"
VAULT_REWRAPPED_FIELD = "secret_gcm"
VAULT_RECEIPT = Path("vault") / "vault_rewrapped.json"


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def die(msg: str, code: int = 2) -> "NoReturn":  # type: ignore[valid-type]
    sys.stderr.write("FATAL: %s\n" % msg)
    raise SystemExit(code)


def warn(msg: str) -> None:
    sys.stderr.write("WARN:  %s\n" % msg)


def info(msg: str) -> None:
    sys.stderr.write("       %s\n" % msg)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_literal(value: Any) -> str:
    """Render one JSON value as a SQL literal that no splitter can misread."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            # JSON cannot carry these, but a hand-edited export could.
            return "NULL"
        return repr(value)
    if isinstance(value, (dict, list)):
        value = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    text = str(value)
    if SAFE_LITERAL.match(text):
        return "'" + text + "'"
    return "CAST(x'" + text.encode("utf-8").hex() + "' AS TEXT)"


def read_ndjson(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError as exc:
                die("%s:%d is not valid JSON: %s" % (path, lineno, exc))
            if not isinstance(obj, dict):
                die("%s:%d is not a JSON object" % (path, lineno))
            yield obj


# --------------------------------------------------------------------------
# the export
# --------------------------------------------------------------------------

class Export(object):
    def __init__(self, root: Path):
        self.root = root
        mpath = root / "manifest.json"
        cpath = root / "collections.json"
        if not mpath.is_file():
            die("no manifest.json in %s -- run export_pocketbase.sh first" % root)
        if not cpath.is_file():
            die("no collections.json in %s" % root)
        self.manifest = json.loads(mpath.read_text(encoding="utf-8"))
        self.collections = json.loads(cpath.read_text(encoding="utf-8"))
        if self.manifest.get("format") != "anticipy-pb-export-1":
            die("unrecognised export format: %r" % self.manifest.get("format"))
        self.by_name = dict((c["name"], c) for c in self.collections)
        self.entry_by_name = dict((e["name"], e) for e in self.manifest.get("collections", []))

    # -- verification -------------------------------------------------------
    def verify(self, check_blobs: bool = True) -> None:
        """Refuse to proceed on an export that does not match its own manifest."""
        problems = []  # type: List[str]

        if not self.manifest.get("reconciled", False):
            problems.append(
                "the export itself did not reconcile (manifest.reconciled is false); "
                "re-run export_pocketbase.sh with writes frozen")

        for entry in self.manifest.get("collections", []):
            nd = entry.get("ndjson") or {}
            path = self.root / nd.get("path", "")
            if not path.is_file():
                problems.append("%s: %s is missing" % (entry["name"], nd.get("path")))
                continue
            actual = sha256_file(path)
            if actual != nd.get("sha256"):
                problems.append("%s: %s sha256 %s != manifest %s"
                                % (entry["name"], nd.get("path"), actual, nd.get("sha256")))
            lines = sum(1 for _ in read_ndjson(path))
            if lines != entry.get("rows_exported"):
                problems.append("%s: %d lines on disk, manifest says %s rows"
                                % (entry["name"], lines, entry.get("rows_exported")))
            if not entry.get("reconciles", False):
                problems.append("%s: exported %s rows, server reported %s"
                                % (entry["name"], entry.get("rows_exported"),
                                   entry.get("total_items_reported")))

        if check_blobs:
            for f in self.manifest.get("files", []):
                path = self.root / f["path"]
                if not path.is_file():
                    problems.append("blob missing: %s" % f["path"])
                    continue
                if sha256_file(path) != f["sha256"]:
                    problems.append("blob sha256 mismatch: %s" % f["path"])

        backup = self.manifest.get("backup")
        if not backup:
            warn("this export has NO native PocketBase archive. Password hashes "
                 "(owners.password), tokenKeys and agents.agent_token are NOT in it. "
                 "They exist only inside /pb_data/data.db.")
        else:
            bpath = self.root / backup["path"]
            if not bpath.is_file():
                problems.append("native archive missing: %s" % backup["path"])
            elif sha256_file(bpath) != backup["sha256"]:
                problems.append("native archive sha256 mismatch: %s" % backup["path"])

        for gap in self.manifest.get("gaps", []):
            warn("recorded gap -- %s.%s: %s" % (gap.get("collection"), gap.get("field"), gap.get("reason")))

        if problems:
            for p in problems:
                sys.stderr.write("  ! %s\n" % p)
            die("the export does not verify; %d problem(s) above. Nothing was written."
                % len(problems), 3)
        info("export verified against its manifest")

    # -- vault interlock ----------------------------------------------------
    def vault_receipt(self) -> Optional[Dict[str, Any]]:
        path = self.root / VAULT_RECEIPT
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != "anticipy-vault-gcm-1":
            die("%s has format %r, expected 'anticipy-vault-gcm-1'"
                % (path, data.get("format")))
        return data


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------

def field_columns(coll: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
    """(column name, sqlite type, field def) in declared order."""
    out = []
    for field in coll.get("fields") or []:
        name = field.get("name")
        if not name:
            continue
        ftype = TYPE_MAP.get(field.get("type"), "TEXT")
        out.append((name, ftype, field))
    return out


def create_table_sql(coll: Dict[str, Any], extra_columns: List[str],
                     absent: List[str]) -> str:
    name = coll["name"]
    cols = field_columns(coll)
    declared = set(c[0] for c in cols)
    lines = []
    have_id = False
    for cname, ctype, field in cols:
        if cname == "id":
            have_id = True
            lines.append("  %s TEXT PRIMARY KEY NOT NULL" % quote_ident(cname))
            continue
        # Every non-id column is nullable on purpose.  This is a LANDING
        # schema whose one job is that no byte is lost; the application-facing
        # constraints belong in migration/d1/ where the Worker's own contract
        # is written.  A NOT NULL here would reject exactly the rows whose
        # value PocketBase declined to serialise (the hidden fields listed in
        # manifest.gaps), which is the opposite of what an import is for.
        note = ""
        if cname in absent:
            note = "   -- NEVER POPULATED: PocketBase did not serialise this field"
        lines.append("  %s %s%s" % (quote_ident(cname), ctype, note))
    for cname in extra_columns:
        if cname in declared:
            continue
        lines.append("  %s TEXT   -- present in exported rows, not in the collection definition"
                     % quote_ident(cname))
    if not have_id:
        lines.insert(0, '  "id" TEXT PRIMARY KEY NOT NULL')
    return "CREATE TABLE IF NOT EXISTS %s (\n%s\n);" % (quote_ident(name), ",\n".join(lines))


_INDEX_HEAD = re.compile(r"(?i)^\s*CREATE\s+(UNIQUE\s+)?INDEX\s+(IF\s+NOT\s+EXISTS\s+)?")
_INDEX_NAME = re.compile(r"(?i)^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?([A-Za-z0-9_]+)")
_INDEX_COLS = re.compile(r"\(([^()]*)\)")


def index_statements(coll: Dict[str, Any], known_columns: Iterable[str],
                     used_names: Dict[str, str]) -> Tuple[List[str], List[str]]:
    """Translate PocketBase's stored index DDL.  Returns (statements, skipped)."""
    known = set(known_columns)
    stmts = []  # type: List[str]
    skipped = []  # type: List[str]
    for raw in coll.get("indexes") or []:
        sql = str(raw).strip().rstrip(";")
        if not sql:
            continue
        m = _INDEX_NAME.match(sql)
        idx_name = m.group(1) if m else None
        # SQLite index names are database-global.  PocketBase's are only
        # collection-scoped, so a collision between two collections is possible
        # and would abort the whole schema file.
        if idx_name and idx_name in used_names and used_names[idx_name] != coll["name"]:
            new_name = "%s__%s" % (idx_name, coll["name"])
            sql = sql.replace(idx_name, new_name, 1)
            skipped.append("renamed duplicate index %s -> %s (also on %s)"
                           % (idx_name, new_name, used_names[idx_name]))
            idx_name = new_name
        if idx_name:
            used_names[idx_name] = coll["name"]
        # An index over a column that PocketBase never serialised cannot be
        # built, because the column is empty -- but it CAN be built and simply
        # index nothing, which is harmless and keeps the shape.  What must not
        # happen is an index over a column that does not exist at all.
        cols_group = _INDEX_COLS.search(sql)
        if cols_group:
            referenced = re.findall(r"[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)[`\"\]]?", cols_group.group(1))
            unknown = [c for c in referenced
                       if c not in known and c.upper() not in
                       ("ASC", "DESC", "COLLATE", "NOCASE", "BINARY", "RTRIM", "LOWER", "UPPER")]
            if unknown:
                skipped.append("skipped index %s: references unknown column(s) %s"
                               % (idx_name or "?", ", ".join(sorted(set(unknown)))))
                continue
        if not re.search(r"(?i)IF\s+NOT\s+EXISTS", sql):
            sql = _INDEX_HEAD.sub(
                lambda m: "CREATE %sINDEX IF NOT EXISTS " % (m.group(1) or ""), sql, count=1)
        stmts.append(sql + ";")
    return stmts, skipped


# --------------------------------------------------------------------------
# data emission
# --------------------------------------------------------------------------

class ChunkWriter(object):
    """Writes SQL into size-bounded files so no single wrangler invocation
    carries an unbounded statement set."""

    def __init__(self, out_dir: Path, stem: str, max_bytes: int):
        self.out_dir = out_dir
        self.stem = stem
        self.max_bytes = max_bytes
        self.index = 0
        self.handle = None  # type: Optional[Any]
        self.size = 0
        self.paths = []  # type: List[Path]

    def _open(self) -> None:
        self.index += 1
        path = self.out_dir / ("%s.%03d.sql" % (self.stem, self.index))
        self.handle = path.open("w", encoding="utf-8")
        self.handle.write("-- %s chunk %d\n" % (self.stem, self.index))
        self.size = 0
        self.paths.append(path)

    def write(self, statement: str) -> None:
        blob = statement if statement.endswith("\n") else statement + "\n"
        if self.handle is None or (self.size + len(blob.encode("utf-8")) > self.max_bytes and self.size > 0):
            self.close()
            self._open()
        assert self.handle is not None
        self.handle.write(blob)
        self.size += len(blob.encode("utf-8"))

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
            self.handle = None


def row_columns(row: Dict[str, Any], keep_meta: bool) -> Dict[str, Any]:
    if keep_meta:
        return row
    return dict((k, v) for k, v in row.items() if k not in PB_META_KEYS)


# --------------------------------------------------------------------------
# wrangler
# --------------------------------------------------------------------------

class Wrangler(object):
    def __init__(self, binary: str, database: str, extra: List[str],
                 config: Optional[str], dry_run: bool):
        self.binary = binary
        self.database = database
        self.extra = extra
        self.config = config
        self.dry_run = dry_run

    def _base(self) -> List[str]:
        cmd = [self.binary, "d1", "execute", self.database]
        if self.config:
            cmd += ["--config", self.config]
        cmd += self.extra
        return cmd

    def execute_file(self, path: Path) -> None:
        cmd = self._base() + ["--file", str(path)]
        if self.dry_run:
            info("dry-run: " + " ".join(cmd))
            return
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode != 0:
            sys.stderr.write(proc.stdout.decode("utf-8", "replace"))
            die("wrangler failed on %s" % path, 4)

    def query(self, sql: str) -> List[Dict[str, Any]]:
        cmd = self._base() + ["--json", "--command", sql]
        if self.dry_run:
            info("dry-run: " + " ".join(cmd))
            return []
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
            die("wrangler query failed: %s" % sql, 4)
        return self._parse(proc.stdout.decode("utf-8", "replace"))

    @staticmethod
    def _parse(text: str) -> List[Dict[str, Any]]:
        """wrangler prints banners around its JSON; find the payload."""
        start = None
        for i, ch in enumerate(text):
            if ch in "[{":
                start = i
                break
        if start is None:
            die("wrangler --json produced no JSON:\n%s" % text[:2000], 4)
        decoder = json.JSONDecoder()
        try:
            payload, _ = decoder.raw_decode(text[start:])
        except ValueError as exc:
            die("could not parse wrangler --json output (%s):\n%s" % (exc, text[:2000]), 4)
        if isinstance(payload, dict):
            payload = [payload]
        rows = []  # type: List[Dict[str, Any]]
        for item in payload:
            if isinstance(item, dict) and isinstance(item.get("results"), list):
                rows.extend(r for r in item["results"] if isinstance(r, dict))
        return rows


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="import_d1.py",
        description="Load a verified PocketBase export into Cloudflare D1 and reconcile it.")
    p.add_argument("export_dir", help="directory written by export_pocketbase.sh")
    p.add_argument("--out", default=None,
                   help="where to write the generated SQL (default: <export_dir>/d1)")
    p.add_argument("--database", default=None,
                   help="D1 database name or uuid for `wrangler d1 execute`")
    p.add_argument("--wrangler", default="wrangler", help="wrangler binary (default: wrangler)")
    p.add_argument("--wrangler-config", default=None, help="path to wrangler.jsonc")
    p.add_argument("--wrangler-arg", action="append", default=None,
                   help="replace the default wrangler flags (default: --remote); repeatable")
    p.add_argument("--yes", action="store_true", help="append -y to every wrangler call")
    p.add_argument("--emit-only", action="store_true",
                   help="write SQL and stop; do not call wrangler")
    p.add_argument("--dry-run", action="store_true",
                   help="print the wrangler commands instead of running them")
    p.add_argument("--schema-file", default=None,
                   help="use this SQL file as the schema instead of generating one "
                        "(e.g. migration/d1/schema.sql)")
    p.add_argument("--no-schema", action="store_true", help="do not create tables at all")
    p.add_argument("--only", action="append", default=None, help="import only these collections")
    p.add_argument("--skip", action="append", default=None, help="skip these collections")
    p.add_argument("--include-system", action="store_true",
                   help="also import PocketBase's own _-prefixed collections")
    p.add_argument("--include-views", action="store_true",
                   help="also import view collections (they are derived; off by default)")
    p.add_argument("--keep-pb-meta", action="store_true",
                   help="keep collectionId/collectionName/expand columns")
    p.add_argument("--rows-per-insert", type=int, default=50)
    p.add_argument("--max-file-bytes", type=int, default=400000,
                   help="ceiling per generated .sql chunk (default 400000)")
    p.add_argument("--max-row-bytes", type=int, default=900000,
                   help="a rendered row larger than this is handled per --oversize "
                        "(agent_llm_audit fields are capped at 1,000,000 characters by "
                        "backend/pb_migrations/1700000032_agent_audit_large_payloads.js:11)")
    p.add_argument("--oversize", choices=("isolate", "truncate", "skip"), default="isolate",
                   help="isolate: emit alone in its own statement (default); "
                        "truncate: store a marker plus the original sha256; "
                        "skip: quarantine the row and exclude it from the expected count")
    p.add_argument("--allow-unreadable-vault", action="store_true",
                   help="import internal_passwords.secret_enc even though nothing on "
                        "Cloudflare can decrypt it. See reencrypt_vault.md.")
    p.add_argument("--skip-blob-verify", action="store_true",
                   help="do not re-hash exported file blobs during verification")
    p.add_argument("--deep-reconcile", action="store_true",
                   help="page every id back out of D1 and diff the id sets")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    export_root = Path(args.export_dir).expanduser().resolve()
    export = Export(export_root)

    out_dir = Path(args.out).expanduser().resolve() if args.out else export_root / "d1"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "data").mkdir(parents=True)
    os.chmod(str(out_dir), 0o700)

    info("export : %s" % export_root)
    info("output : %s" % out_dir)

    # ---- 1. verify before anything else ----------------------------------
    export.verify(check_blobs=not args.skip_blob_verify)

    # ---- 2. decide the collection set ------------------------------------
    only = set(args.only or [])
    skip = set(args.skip or [])
    selected = []   # type: List[Dict[str, Any]]
    excluded = []   # type: List[Dict[str, str]]
    for coll in export.collections:
        name = coll["name"]
        if only and name not in only:
            excluded.append({"name": name, "reason": "not in --only"})
            continue
        if name in skip:
            excluded.append({"name": name, "reason": "--skip"})
            continue
        if coll.get("system") and not args.include_system:
            excluded.append({"name": name,
                             "reason": "PocketBase system collection; pass --include-system to import"})
            continue
        if coll.get("type") == "view" and not args.include_views:
            excluded.append({"name": name,
                             "reason": "view collection (derived, no rows of its own); pass --include-views"})
            continue
        selected.append(coll)

    if not selected:
        die("no collections selected")
    info("importing %d collection(s); %d excluded" % (len(selected), len(excluded)))
    for ex in excluded:
        info("  excluded %-28s %s" % (ex["name"], ex["reason"]))

    # ---- 3. the vault interlock ------------------------------------------
    rewrap = export.vault_receipt()
    rewrap_by_id = {}  # type: Dict[str, str]
    vault_selected = any(c["name"] == VAULT_COLLECTION for c in selected)
    if vault_selected:
        nd = export_root / "records" / ("%s.ndjson" % VAULT_COLLECTION)
        encrypted_ids = []
        if nd.is_file():
            for row in read_ndjson(nd):
                if str(row.get(VAULT_CIPHERTEXT_FIELD) or "").strip():
                    encrypted_ids.append(str(row.get("id")))
        if encrypted_ids:
            if rewrap is None:
                sys.stderr.write(
                    "\n"
                    "  ############################################################\n"
                    "  #  THE VAULT CANNOT BE CARRIED ACROSS AS-IS                #\n"
                    "  ############################################################\n"
                    "  %d row(s) in %s hold a non-empty %s.\n"
                    "  Those bytes were produced by PocketBase's Go $security.encrypt\n"
                    "  under ANTICIPY_VAULT_KEY (internal_hq.pb.js:3079) and are read\n"
                    "  back only by $security.decrypt (internal_hq.pb.js:3140) --\n"
                    "  code that stops existing when the instance is decommissioned.\n"
                    "  Re-wrap the vault FIRST: migration/runbooks/reencrypt_vault.md\n"
                    "  Expected receipt: %s\n\n"
                    % (len(encrypted_ids), VAULT_COLLECTION, VAULT_CIPHERTEXT_FIELD,
                       export_root / VAULT_RECEIPT))
                if not args.allow_unreadable_vault:
                    return 3
                warn("--allow-unreadable-vault given: importing ciphertext nothing can open")
            else:
                rewrap_by_id = dict((str(i["id"]), str(i[VAULT_REWRAPPED_FIELD]))
                                    for i in rewrap.get("items", []))
                missing = [i for i in encrypted_ids if i not in rewrap_by_id]
                if missing and not args.allow_unreadable_vault:
                    die("the vault receipt covers %d of %d encrypted rows; missing: %s"
                        % (len(rewrap_by_id), len(encrypted_ids), ", ".join(missing[:10])), 3)
                info("vault receipt found: %d row(s) re-wrapped under %s"
                     % (len(rewrap_by_id), rewrap.get("key_env", "?")))

    # ---- 4. schema --------------------------------------------------------
    schema_path = out_dir / "schema.sql"
    schema_notes = []  # type: List[str]
    if args.no_schema:
        info("schema: skipped (--no-schema)")
        schema_path = None  # type: ignore[assignment]
    elif args.schema_file:
        src = Path(args.schema_file).expanduser().resolve()
        if not src.is_file():
            die("--schema-file %s does not exist" % src)
        shutil.copyfile(str(src), str(schema_path))
        info("schema: copied from %s" % src)
    else:
        used_index_names = {}  # type: Dict[str, str]
        parts = ["-- Landing schema generated by import_d1.py from the collection",
                 "-- definitions the PocketBase server reported at export time.",
                 "-- Every non-id column is nullable on purpose; application constraints",
                 "-- belong in migration/d1/, not in the vessel that carries the bytes.",
                 ""]
        for coll in selected:
            entry = export.entry_by_name.get(coll["name"], {})
            absent = list(entry.get("fields_absent_from_output") or [])
            nd = export_root / "records" / ("%s.ndjson" % coll["name"])
            extra = set()  # type: set
            if nd.is_file():
                for n, row in enumerate(read_ndjson(nd)):
                    if n >= 500:
                        break
                    for k in row_columns(row, args.keep_pb_meta):
                        extra.add(k)
            declared = set(c[0] for c in field_columns(coll))
            extra_cols = sorted(x for x in extra if x not in declared)
            if coll["name"] == VAULT_COLLECTION and rewrap_by_id:
                extra_cols.append(VAULT_REWRAPPED_FIELD)
            parts.append(create_table_sql(coll, extra_cols, absent))
            known = declared | set(extra_cols) | {"id"}
            stmts, notes = index_statements(coll, known, used_index_names)
            parts.extend(stmts)
            for n in notes:
                schema_notes.append("%s: %s" % (coll["name"], n))
                warn("%s: %s" % (coll["name"], n))
            parts.append("")
        schema_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
        info("schema: %s" % schema_path)

    # ---- 5. data ----------------------------------------------------------
    plan = {
        "format": "anticipy-d1-import-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "export": str(export_root),
        "schema": str(schema_path) if schema_path else None,
        "schema_notes": schema_notes,
        "excluded": excluded,
        "collections": [],
        "files": [],
    }  # type: Dict[str, Any]

    oversized_log = out_dir / "oversized.ndjson"
    oversized_count = 0
    with oversized_log.open("w", encoding="utf-8") as oversized_fh:
        for coll in selected:
            name = coll["name"]
            nd = export_root / "records" / ("%s.ndjson" % name)
            writer = ChunkWriter(out_dir / "data", name, args.max_file_bytes)
            declared = [c[0] for c in field_columns(coll)]
            columns = list(declared)
            seen = set(columns)
            if name == VAULT_COLLECTION and rewrap_by_id and VAULT_REWRAPPED_FIELD not in seen:
                columns.append(VAULT_REWRAPPED_FIELD)
                seen.add(VAULT_REWRAPPED_FIELD)
            # any key the rows carry that the definition did not declare
            if nd.is_file():
                for n, row in enumerate(read_ndjson(nd)):
                    if n >= 500:
                        break
                    for k in row_columns(row, args.keep_pb_meta):
                        if k not in seen:
                            seen.add(k)
                            columns.append(k)
            if "id" not in seen:
                columns.insert(0, "id")

            col_sql = ", ".join(quote_ident(c) for c in columns)
            prefix = "INSERT INTO %s (%s) VALUES\n" % (quote_ident(name), col_sql)

            expected = 0
            skipped_rows = 0
            batch = []  # type: List[str]

            def flush(batch_ref):
                if batch_ref:
                    writer.write(prefix + ",\n".join(batch_ref) + ";")
                    del batch_ref[:]

            if nd.is_file():
                for row in read_ndjson(nd):
                    row = row_columns(row, args.keep_pb_meta)
                    if name == VAULT_COLLECTION:
                        rid = str(row.get("id") or "")
                        if rid in rewrap_by_id:
                            row = dict(row)
                            row[VAULT_REWRAPPED_FIELD] = rewrap_by_id[rid]
                            # the unreadable ciphertext is deliberately not carried
                            row[VAULT_CIPHERTEXT_FIELD] = ""
                    values = [sql_literal(row.get(c)) for c in columns]
                    tup = "(" + ", ".join(values) + ")"
                    tup_bytes = len(tup.encode("utf-8"))
                    if tup_bytes > args.max_row_bytes:
                        oversized_count += 1
                        oversized_fh.write(json.dumps(
                            {"collection": name, "id": row.get("id"),
                             "bytes": tup_bytes, "action": args.oversize}) + "\n")
                        if args.oversize == "skip":
                            skipped_rows += 1
                            warn("%s/%s: %d bytes -- quarantined (--oversize=skip)"
                                 % (name, row.get("id"), tup_bytes))
                            continue
                        if args.oversize == "truncate":
                            row = dict(row)
                            for c in columns:
                                v = row.get(c)
                                if isinstance(v, str) and len(v.encode("utf-8")) > 65536:
                                    digest = hashlib.sha256(v.encode("utf-8")).hexdigest()
                                    row[c] = ("[[truncated by import_d1.py: %d bytes, sha256=%s]]"
                                              % (len(v.encode("utf-8")), digest))
                            values = [sql_literal(row.get(c)) for c in columns]
                            tup = "(" + ", ".join(values) + ")"
                        else:  # isolate
                            flush(batch)
                            writer.write(prefix + tup + ";")
                            expected += 1
                            continue
                    batch.append(tup)
                    expected += 1
                    if len(batch) >= args.rows_per_insert:
                        flush(batch)
                flush(batch)
            writer.close()

            plan["collections"].append({
                "name": name,
                "type": coll.get("type"),
                "source_rows": export.entry_by_name.get(name, {}).get("rows_exported"),
                "expected_rows": expected,
                "quarantined_rows": skipped_rows,
                "columns": columns,
                "chunks": [str(p) for p in writer.paths],
            })
            info("%-28s %6d row(s) -> %d chunk(s)" % (name, expected, len(writer.paths)))

    if oversized_count:
        warn("%d oversized row(s); see %s" % (oversized_count, oversized_log))

    ordered_files = ([str(schema_path)] if schema_path else []) + \
        [c for entry in plan["collections"] for c in entry["chunks"]]
    plan["files"] = ordered_files
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    info("plan: %s (%d SQL file(s))" % (out_dir / "plan.json", len(ordered_files)))

    if args.emit_only:
        info("--emit-only: stopping before wrangler")
        return 0

    if not args.database:
        die("--database is required unless --emit-only is given")

    extra = list(args.wrangler_arg) if args.wrangler_arg else ["--remote"]
    if args.yes:
        extra = extra + ["-y"]
    if not args.dry_run and shutil.which(args.wrangler) is None:
        die("wrangler not found on PATH as %r; install it or pass --wrangler" % args.wrangler)
    wr = Wrangler(args.wrangler, args.database, extra, args.wrangler_config, args.dry_run)

    # ---- 6. execute -------------------------------------------------------
    for path in ordered_files:
        info("executing %s" % path)
        wr.execute_file(Path(path))

    # ---- 7. reconcile -----------------------------------------------------
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "database": args.database,
        "collections": [],
        "excluded": excluded,
        "ok": True,
    }  # type: Dict[str, Any]

    for entry in plan["collections"]:
        name = entry["name"]
        src_rows = entry["expected_rows"]
        nd = export_root / "records" / ("%s.ndjson" % name)
        src_ids = []  # type: List[str]
        if nd.is_file():
            src_ids = [str(r.get("id")) for r in read_ndjson(nd)]
        src_min = min(src_ids) if src_ids else None
        src_max = max(src_ids) if src_ids else None
        src_idlen = sum(len(i) for i in src_ids)

        rows = wr.query(
            'SELECT COUNT(*) AS n, MIN("id") AS lo, MAX("id") AS hi, '
            'SUM(LENGTH("id")) AS idlen FROM %s;' % quote_ident(name))
        if args.dry_run:
            continue
        got = rows[0] if rows else {}
        dst_rows = int(got.get("n") or 0)
        dst_min = got.get("lo")
        dst_max = got.get("hi")
        dst_idlen = int(got.get("idlen") or 0)

        problems = []
        if dst_rows != src_rows:
            problems.append("row count %d != %d" % (dst_rows, src_rows))
        if src_rows and dst_min != src_min:
            problems.append("min id %r != %r" % (dst_min, src_min))
        if src_rows and dst_max != src_max:
            problems.append("max id %r != %r" % (dst_max, src_max))
        if src_rows and dst_idlen != src_idlen:
            problems.append("sum(length(id)) %d != %d" % (dst_idlen, src_idlen))

        missing_ids = []  # type: List[str]
        extra_ids = []    # type: List[str]
        if args.deep_reconcile and src_rows:
            seen = set()
            offset = 0
            while True:
                page = wr.query('SELECT "id" FROM %s ORDER BY "id" LIMIT 1000 OFFSET %d;'
                                % (quote_ident(name), offset))
                if not page:
                    break
                for r in page:
                    seen.add(str(r.get("id")))
                if len(page) < 1000:
                    break
                offset += 1000
            src_set = set(src_ids)
            missing_ids = sorted(src_set - seen)[:50]
            extra_ids = sorted(seen - src_set)[:50]
            if missing_ids:
                problems.append("%d id(s) present in the export and absent from D1" % len(src_set - seen))
            if extra_ids:
                problems.append("%d id(s) present in D1 and absent from the export" % len(seen - src_set))

        ok = not problems
        report["collections"].append({
            "name": name,
            "source_rows": src_rows,
            "destination_rows": dst_rows,
            "quarantined_rows": entry["quarantined_rows"],
            "source_id_bounds": [src_min, src_max],
            "destination_id_bounds": [dst_min, dst_max],
            "missing_ids_sample": missing_ids,
            "unexpected_ids_sample": extra_ids,
            "problems": problems,
            "ok": ok,
        })
        if not ok:
            report["ok"] = False
        sys.stderr.write("  %-4s %-28s src=%-8d dst=%-8d %s\n"
                         % ("ok" if ok else "FAIL", name, src_rows, dst_rows,
                            "; ".join(problems)))

    report_path = out_dir / "reconcile.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    info("reconciliation report: %s" % report_path)

    if args.dry_run:
        info("--dry-run: nothing was executed, nothing was reconciled")
        return 0

    if not report["ok"]:
        die("RECONCILIATION FAILED. The destination does not match the export. "
            "Do not decommission anything. See %s" % report_path, 3)

    total_src = sum(c["source_rows"] for c in report["collections"])
    total_dst = sum(c["destination_rows"] for c in report["collections"])
    info("reconciled: %d rows in, %d rows out, across %d collection(s)"
         % (total_src, total_dst, len(report["collections"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
