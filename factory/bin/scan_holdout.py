#!/usr/bin/env python
"""Precise holdout-access scan over a claude stream-json session log.

FAILS only on actual ACCESS to holdout contents: a tool_use whose input reaches INTO
factory/personas/holdout/<something> or realdays/holdout/<something> (Read file_path,
Bash command, Grep path, etc.). Mere MENTIONS of the directory name (CLAUDE.md, STATE.md,
.gitignore all reference it) are allowed — lap 20260610T045550Z was falsely reverted by
the old grep-for-the-string scan.

Usage: scan_holdout.py <build.stream.jsonl>   exit 0 clean / 1 violation / 0 if no file
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# a path that goes INTO a holdout dir (a real child segment after holdout/)
ACCESS_RE = re.compile(r"(factory/personas/holdout|realdays/holdout)/[A-Za-z0-9_\-]")

# only OPERATIONAL fields of file/exec tools count as access. Free-text fields
# (Agent/Workflow/Task prompts and scripts) MENTION paths legitimately — e.g. the
# prohibition itself — and tripped a false revert on lap 20260610T052102Z (ledger C12).
FIELD_MAP = {
    "Read": ["file_path"], "Write": ["file_path"], "Edit": ["file_path"],
    "NotebookEdit": ["notebook_path"],
    "Glob": ["path", "pattern"], "Grep": ["path", "pattern", "glob"],
    "Bash": ["command"], "BashOutput": [], "LSP": ["file_path"],
}


def tool_use_inputs(obj) -> list:
    out = []
    msg = obj.get("message") if isinstance(obj, dict) else None
    content = (msg or {}).get("content") if isinstance(msg, dict) else None
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {}) or {}
                fields = FIELD_MAP.get(name)
                if fields is None:
                    continue  # free-text tools (Agent, Workflow, Task...): mentions allowed
                for f in fields:
                    v = inp.get(f)
                    if isinstance(v, str):
                        out.append(v)
    return out


def main() -> int:
    if len(sys.argv) < 2 or not Path(sys.argv[1]).exists():
        print("SKIPPED_NO_STREAM")
        return 0
    hits = []
    with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            for inp in tool_use_inputs(obj):
                m = ACCESS_RE.search(inp)
                if m:
                    hits.append(m.group(0) + "...")
    if hits:
        print(f"FAIL: tool access into holdout: {sorted(set(hits))[:3]}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
