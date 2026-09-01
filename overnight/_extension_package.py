"""Byte-level comparisons shared by the live extension gate and its tests."""

from __future__ import annotations

import os
from collections.abc import Mapping


def anticipy_record_state(record: Mapping) -> str | None:
    """Classify a Chrome preference record without mistaking a tombstone.

    Chrome retains the path and extension ID after an unpacked extension is
    removed. Those records have no stored manifest and do not appear on
    chrome://extensions, but a path-only search used to call them "loaded".
    """
    manifest = record.get("manifest") or {}
    name = manifest.get("name") or ""
    if "anticipy" not in name.lower():
        return None
    return "disabled" if record.get("disable_reasons") else "enabled"


def compare_package_tree(
        package_files: Mapping[str, bytes], root: str) -> list[str]:
    """Return every packaged file that is missing or different under *root*.

    An empty/unreadable package must fail closed. Otherwise the Chrome leg
    could once again pass without comparing anything when the ZIP leg fails.
    """
    if not package_files:
        return ["package contains no readable files"]

    root = os.path.abspath(root)
    differences = []
    for name, expected in package_files.items():
        normalized = os.path.normpath(name)
        if (os.path.isabs(name) or normalized == ".." or
                normalized.startswith(".." + os.sep)):
            differences.append(f"unsafe package path {name}")
            continue

        candidate = os.path.abspath(os.path.join(root, normalized))
        if os.path.commonpath([root, candidate]) != root:
            differences.append(f"unsafe package path {name}")
        elif not os.path.isfile(candidate):
            differences.append(f"missing {name}")
        elif open(candidate, "rb").read() != expected:
            differences.append(name)
    return differences
