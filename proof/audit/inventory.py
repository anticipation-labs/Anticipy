#!/usr/bin/env python3
"""Inventory source and documentation without mistaking discovery for review.

This is a static audit instrument, not runtime interpretation of human words.
Its syntax searches produce candidates, including dynamic routes that require
manual tracing. They do not certify completeness of dispatch or API behavior.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/audit-2026-09-06/inventory"
DOC_EXT = {".md", ".html", ".pdf", ".rst", ".txt"}
CODE_EXT = {".ts", ".js", ".mjs", ".py", ".swift", ".yml", ".yaml", ".jsonc"}
PATH_CHECK = re.compile(r"\b(path|pathname)\b.*(?:===|startsWith|match|test)|(?:===|startsWith|match|test).*\b(path|pathname)\b")
CALL = re.compile(r"\b(fetch|requests\.(?:get|post|put|patch|delete)|pb\.(?:get|post|patch)|URLRequest|dataTask|URLSession|apiCall|apiFetch)\s*\(")
MD_LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")


def write(name: str, rows) -> None:
    (OUT / name).write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    files, docs, routes, calls, broken_links = [], [], [], [], []
    for relative in sorted(filter(None, paths)):
        path = ROOT / relative
        if not path.is_file():
            files.append({"path": relative, "status": "missing_from_checkout"})
            continue
        raw = path.read_bytes()
        info = {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        files.append(info)
        if path.suffix.lower() in DOC_EXT:
            docs.append({**info, "review_status": "not_reviewed", "notes": []})
        if path.suffix.lower() not in DOC_EXT | CODE_EXT or path.suffix.lower() == ".pdf":
            continue
        text = raw.decode(errors="replace")
        if path.suffix.lower() in CODE_EXT:
            for line, content in enumerate(text.splitlines(), 1):
                stripped = content.strip()
                if stripped.startswith(("//", "#", "*")):
                    continue
                if relative.startswith("migration/workers/src/") and PATH_CHECK.search(content):
                    routes.append({"path": relative, "line": line, "condition": stripped,
                                   "review_status": "dispatch_candidate", "evidence": []})
                if CALL.search(content):
                    calls.append({"path": relative, "line": line, "code": stripped,
                                  "review_status": "call_candidate", "evidence": []})
        if path.suffix.lower() == ".md":
            # Check concrete relative Markdown links. Code-span citations,
            # reference-style links, anchors and HTML links require other review.
            for match in MD_LINK.finditer(text):
                target = match[1].strip().split(' "', 1)[0].strip("<>")
                parsed = urlsplit(target)
                if parsed.scheme or target.startswith(("#", "/", "mailto:")):
                    continue
                target_path = unquote(parsed.path)
                if target_path and not (path.parent / target_path).exists():
                    broken_links.append({"path": relative, "line": text[:match.start()].count("\n") + 1,
                                         "target": target, "review_status": "candidate_missing_target"})

    db = sqlite3.connect(":memory:")
    db.executescript((ROOT / "migration/d1/schema.sql").read_text())
    tables = []
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        columns = [row[1] for row in db.execute(f'PRAGMA table_info("{name}")')]
        tables.append({"table": name, "columns": columns,
                       "identity_columns": [c for c in columns if c in {"owner_ref", "owner_id", "owner", "user_id", "person"}],
                       "foreign_keys": db.execute(f'PRAGMA foreign_key_list("{name}")').fetchall(),
                       "review_status": "schema_inventoried"})
    write("files.json", files)
    write("documents.json", docs)
    write("dispatch-candidates.json", routes)
    write("call-candidates.json", calls)
    write("relative-link-candidates.json", broken_links)
    write("tables.json", tables)
    print(json.dumps({"files": len(files), "documents": len(docs), "dispatch_candidates": len(routes),
                      "call_candidates": len(calls), "missing_relative_link_candidates": len(broken_links),
                      "tables": len(tables)}))


if __name__ == "__main__":
    main()
