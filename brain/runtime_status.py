"""Read-only facts about the running image, process and durable snapshot."""
from functools import lru_cache
import hashlib
from pathlib import Path


@lru_cache(maxsize=1)
def source_hash() -> str:
    root = Path(__file__).parent
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".md")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def health(*, running: bool, snapshot_at: float | None, snapshot_error: bool,
           now: float, interval: int) -> dict:
    age = None if snapshot_at is None else max(0, now - snapshot_at)
    durable = age is not None and age <= max(180, interval * 3) and not snapshot_error
    return {"ok": running and durable, "child_running": running,
            "source_sha256": source_hash(), "snapshot_age_seconds": age,
            "snapshot_error": snapshot_error, "snapshot_current": durable}
