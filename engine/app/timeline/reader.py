"""Unified timeline reader.

Tiny streaming reader for ``~/.anticipy/v7/timeline.jsonl``. Pairs with
``writer.append``. The popover and the verifier both call into these
helpers; neither needs to know the file format.

Implementation notes:
    - We never hold the writer's lock for reads. Reads operate on an
      open file handle and tolerate the writer appending mid-read; new
      bytes simply aren't visible until the file is reopened.
    - ``tail`` reads from the end backward in chunks to avoid loading
      the entire file when the user only wants the last 50 rows. Old
      rotated ``.bak`` files are NOT searched; the popover only ever
      shows the live feed.
    - Malformed lines are skipped (they shouldn't exist; ``append``
      validates before writing).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

from .writer import _resolve_path

# How many bytes to seek back per pass when walking the tail. Sized for
# typical JSONL rows (~200-600 bytes) so 50 entries land in 1-2 passes.
_TAIL_CHUNK_BYTES = 32 * 1024


def _iter_lines(path: os.PathLike[str] | str) -> Iterator[str]:
    """Yield every non-empty line from the timeline file.

    Opens in text mode with UTF-8 and ``errors="replace"`` so a partial
    byte sequence at EOF (writer was mid-flush) doesn't kill the reader.
    Returns nothing when the file is missing.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if line:
                    yield line
    except FileNotFoundError:
        return


def _parse(line: str) -> dict[str, Any] | None:
    """Decode one JSONL line. ``None`` on parse failure."""
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def tail(n: int = 50) -> list[dict[str, Any]]:
    """Return the last ``n`` timeline rows, oldest first.

    Reads from the end of the file backward to avoid scanning the whole
    log for small ``n``. When the file is shorter than the requested
    window, returns whatever exists. Malformed lines are silently
    skipped so a transient half-written row never breaks the popover.
    """
    if n <= 0:
        return []
    path = _resolve_path()
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return []
    if size == 0:
        return []
    buf = b""
    offset = size
    lines: list[str] = []
    try:
        with open(path, "rb") as fh:
            # Walk backward in chunks until we collected n+1 newlines
            # (the +1 protects against losing a partial first line when
            # the chunk boundary lands mid-row).
            while offset > 0 and buf.count(b"\n") <= n:
                read_size = min(_TAIL_CHUNK_BYTES, offset)
                offset -= read_size
                fh.seek(offset)
                buf = fh.read(read_size) + buf
            # Decode and split. We don't trim the leading partial line
            # because the slice [-n:] handles that: when the partial
            # produces a malformed row, ``_parse`` returns None and we
            # drop it.
            text = buf.decode("utf-8", errors="replace")
            lines = [seg for seg in text.split("\n") if seg.strip()]
    except FileNotFoundError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-n:]:
        parsed = _parse(line)
        if parsed is not None:
            rows.append(parsed)
    return rows


def filter_by(
    *,
    kind: str | None = None,
    status: str | None = None,
    goal_id: str | None = None,
    since_ts: float | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield rows matching the given filters, in file order.

    All filters are optional and combined with logical AND. ``None``
    means "no constraint on this field". ``since_ts`` is inclusive:
    rows with ``ts >= since_ts`` are returned.

    Returns an iterator so the popover can stream into a virtualized
    list without materializing the full log. Callers that want a list
    can wrap with ``list(...)``.
    """
    path = _resolve_path()
    for line in _iter_lines(path):
        row = _parse(line)
        if row is None:
            continue
        if kind is not None and row.get("kind") != kind:
            continue
        if status is not None and row.get("status") != status:
            continue
        if goal_id is not None and row.get("goal_id") != goal_id:
            continue
        if since_ts is not None:
            row_ts = row.get("ts")
            if not isinstance(row_ts, (int, float)) or row_ts < since_ts:
                continue
        yield row
