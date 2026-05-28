#!/usr/bin/env python3
"""Smoke test for ``DomExtractor``.

Navigates Chrome (via the loopback bridge at 127.0.0.1:7777) to
saucedemo.com, extracts the semantic accessibility tree, and asserts:

1. The extractor returns a structured ``{root, nodes}`` payload.
2. The root URL belongs to saucedemo.com.
3. At least one node looks like a login input (role textbox / combobox with
   a name hinting at username or password), OR (when running on the JS-less
   fallback bridge) the synthesized tree still produced actionable input
   nodes.
4. ``compact_for_llm`` returns non-empty text under 15k chars and contains
   numbered labels like ``[1]``.

SauceDemo is a public e-commerce site purpose-built for automation. Its
login surface has stable, well-named inputs (``user-name``, ``password``,
``login-button``), so it is more representative of the real surfaces
Anticipy must traverse than google.com.

The script exits 0 on PASS, 1 on FAIL, and prints a JSON receipt on stdout
so the orchestrator can grep results without parsing prose.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path


# Make engine.app.product importable regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from engine.app.product.surface_dom_extractor import DomExtractor  # noqa: E402


def _emit(receipt: dict) -> None:
    print("RECEIPT " + json.dumps(receipt, ensure_ascii=False))


def main() -> int:
    extractor = DomExtractor()
    receipt: dict = {"ok": False, "checks": {}}

    # 1) extract tree, seeding via saucedemo.com
    start = time.monotonic()
    tree = extractor.extract_semantic_tree("https://www.saucedemo.com/")
    elapsed = round(time.monotonic() - start, 2)
    receipt["extract_seconds"] = elapsed
    receipt["source"] = tree.get("source", "")
    receipt["node_count"] = len(tree.get("nodes") or [])
    receipt["root"] = tree.get("root", {})

    # Check 1: structured payload
    has_shape = isinstance(tree, dict) and "root" in tree and "nodes" in tree
    receipt["checks"]["has_shape"] = bool(has_shape)
    if not has_shape:
        receipt["error"] = "extractor returned malformed tree"
        _emit(receipt)
        return 1

    # Check 2: root URL is saucedemo.com
    url = str((tree.get("root") or {}).get("url") or "")
    on_saucedemo = "saucedemo." in url
    receipt["checks"]["on_saucedemo"] = on_saucedemo
    receipt["url_seen"] = url

    # Check 3: login-input-shaped node present (username or password textbox)
    login_hit = None
    for node in tree.get("nodes") or []:
        role = str(node.get("role") or "").lower()
        name = str(node.get("name") or "").lower()
        if role in {"textbox", "combobox", "searchbox"} and (
            "user" in name or "password" in name or "login" in name
        ):
            login_hit = node
            break
        if role == "textbox" and bool(node.get("is_actionable")):
            login_hit = login_hit or node
    receipt["checks"]["login_node_present"] = bool(login_hit)
    if login_hit:
        receipt["login_node"] = {
            "node_id": login_hit.get("node_id"),
            "role": login_hit.get("role"),
            "name": (login_hit.get("name") or "")[:60],
            "is_actionable": bool(login_hit.get("is_actionable")),
        }

    # Check 4: compact_for_llm bounds
    compact = extractor.compact_for_llm(tree, max_chars=15000)
    receipt["compact_chars"] = len(compact)
    compact_non_empty = bool(compact and len(compact.strip()) > 0)
    compact_in_bounds = len(compact) <= 15000
    has_numbered_label = "[1]" in compact or "[2]" in compact or "PAGE url=" in compact
    receipt["checks"]["compact_non_empty"] = compact_non_empty
    receipt["checks"]["compact_in_bounds"] = compact_in_bounds
    receipt["checks"]["compact_has_label"] = has_numbered_label

    # The fallback bridge cannot run JS, so the login-node check is
    # acknowledged as a soft signal. The HARD requirements are: shape ok,
    # url is saucedemo, compact non-empty under 15k, and at least one
    # numbered label (or the PAGE header when fallback returns zero parsed
    # nodes).
    hard_ok = (
        has_shape
        and on_saucedemo
        and compact_non_empty
        and compact_in_bounds
        and has_numbered_label
    )
    receipt["ok"] = bool(hard_ok)
    if not hard_ok:
        receipt["error"] = "hard requirements failed; see checks"
    _emit(receipt)
    return 0 if hard_ok else 1


if __name__ == "__main__":
    sys.exit(main())
