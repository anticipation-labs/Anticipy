"""
Chrome native-messaging wire codec.

Frame format (per Chrome docs):
  [ 4-byte little-endian uint32 length ][ UTF-8 JSON payload ]

The 4-byte prefix is *unsigned* little-endian.  Max payload per Chrome is
1,048,576 bytes (1 MiB) inbound from extension → host.  We enforce the
same cap on both directions because the API is symmetric.

This module is dependency-free so the codec can be unit-tested without
the rest of the daemon being importable.  Functions:

  pack(obj)             → bytes ready for stdout.write()
  unpack_message(bytes) → (obj, leftover)  if a full frame is available
  read_message(stream)  → blocking read of one full frame from a binary
                          stream  (sys.stdin.buffer)
  write_message(stream, obj) → blocking write of one frame to stdout.buffer

Errors raised:
  ProtocolError        — base
  FrameTooLarge        — payload exceeds MAX_PAYLOAD
  IncompleteFrame      — stream EOF in the middle of a frame
  MalformedJSON        — payload was not valid UTF-8 JSON
"""

from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO, Tuple

MAX_PAYLOAD = 1 << 20  # 1 MiB — matches Chrome's documented limit.


class ProtocolError(Exception):
    """Base class for native-messaging protocol errors."""


class FrameTooLarge(ProtocolError):
    """Frame size exceeded MAX_PAYLOAD."""


class IncompleteFrame(ProtocolError):
    """Stream closed mid-frame."""


class MalformedJSON(ProtocolError):
    """Payload bytes were not valid UTF-8 JSON."""


def pack(obj: Any) -> bytes:
    """Serialize ``obj`` into a length-prefixed frame.

    ``obj`` must be JSON-serializable (dict / list / primitive). Returns
    raw bytes ready for stdout.buffer.write().
    """
    data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_PAYLOAD:
        raise FrameTooLarge(f"payload {len(data)} > {MAX_PAYLOAD}")
    return struct.pack("<I", len(data)) + data


def unpack_message(buf: bytes) -> Tuple[Any | None, bytes]:
    """Try to peel one frame off the front of ``buf``.

    Returns ``(message, leftover_bytes)``.  When ``buf`` doesn't yet hold
    a complete frame, ``message is None`` and ``leftover_bytes`` is the
    original buffer unchanged — caller should append more bytes and
    retry.

    Useful for stream-style decoders / tests.
    """
    if len(buf) < 4:
        return None, buf
    (length,) = struct.unpack("<I", buf[:4])
    if length > MAX_PAYLOAD:
        raise FrameTooLarge(f"declared length {length} > {MAX_PAYLOAD}")
    if len(buf) < 4 + length:
        return None, buf
    payload = buf[4 : 4 + length]
    leftover = buf[4 + length :]
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedJSON(str(exc)) from exc
    return message, leftover


def read_message(stream: BinaryIO) -> Any:
    """Blocking read of one full frame from ``stream``.

    Returns the decoded JSON object, or raises ``IncompleteFrame`` on
    EOF.  Use with ``sys.stdin.buffer``.
    """
    header = _read_exact(stream, 4)
    (length,) = struct.unpack("<I", header)
    if length > MAX_PAYLOAD:
        raise FrameTooLarge(f"declared length {length} > {MAX_PAYLOAD}")
    payload = _read_exact(stream, length)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MalformedJSON(str(exc)) from exc


def write_message(stream: BinaryIO, obj: Any) -> None:
    """Blocking write of one frame to ``stream`` and flush."""
    stream.write(pack(obj))
    stream.flush()


def _read_exact(stream: BinaryIO, n: int) -> bytes:
    """Read exactly ``n`` bytes from ``stream`` or raise IncompleteFrame."""
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            raise IncompleteFrame(f"stream ended after {n - remaining}/{n} bytes")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


__all__ = [
    "MAX_PAYLOAD",
    "ProtocolError",
    "FrameTooLarge",
    "IncompleteFrame",
    "MalformedJSON",
    "pack",
    "unpack_message",
    "read_message",
    "write_message",
]
