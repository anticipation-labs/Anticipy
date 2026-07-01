"""M5 gate — the privacy layer (gated like the money hard-stop).

Proves, with checks that can FAIL:
  1. NEVER-STORE secret VALUES (SSN, card/account numbers, passwords/PINs) are absent from the
     ENTIRE durable store — every drawer AND the inert remember-list — even when the line is
     force-kept. Only the value is masked; the fact that it was said survives.
  2. No raw secret value leaves the device: the assembled ContextPack (the ONE egress) is clean.
  3. SENSITIVE facts (health) are TAGGED and RETENTION-bounded — they auto-expire via the M3
     bi-temporal filter instead of living forever.
  4. RIGHT-TO-DELETE wipes ALL traces (drawers + remember-list), leaving nothing.

Deterministic, no model. Run:
  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memctx_privacy.py
"""
import datetime as dt
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.live_memory.privacy import RETENTION_DAYS
from anticipy_engine.memory import Memory


def _iso(d):
    return d.isoformat()


def _all_stored_text(lm):
    """Every string persisted anywhere in the db — drawer rows (text + serialized fields) AND
    the remember-list. This is exactly the surface a 'never leaves the device' claim must clear."""
    blobs = []
    conn = lm.memory.db.conn
    for r in conn.execute("SELECT text, fields FROM items").fetchall():
        blobs.append(r["text"] or "")
        blobs.append(r["fields"] or "")
    for r in conn.execute("SELECT text FROM remembered_lines").fetchall():
        blobs.append(r["text"] or "")
    return "\n".join(blobs)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-privacy-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))

    tz = dt.timezone.utc
    day1 = dt.datetime(2026, 6, 1, 9, 0, tzinfo=tz)
    meta = {"observed_at": _iso(day1), "timezone": "UTC"}

    # the raw secret VALUES that must NEVER persist or egress.
    SECRETS = ["123-45-6789", "4111 1111 1111 1111", "hunter2please", "021000021"]
    secret_lines = [
        "my social security number is 123-45-6789.",
        "the card on file is 4111 1111 1111 1111.",
        "my password is hunter2please for the portal.",
        "the routing number is 021000021 for the wire.",
    ]
    # force-keep so they are DURABLY written — masking-at-rest must hold even then.
    for line in secret_lines:
        lm.capturer.capture(line, source="mp3", force=True, meta=meta)

    # a SENSITIVE (health) fact — kept, but tagged + retention-bounded.
    lm.capturer.capture("I was diagnosed with high blood pressure and take 20 mg lisinopril.",
                        source="mp3", force=True, meta=meta)
    # a normal durable fact — untouched control.
    lm.capturer.capture("I work at NewCo.", source="mp3", force=True, meta=meta)

    # (1) NEVER-STORE values absent from the ENTIRE durable store.
    stored = _all_stored_text(lm)
    for s in SECRETS:
        assert s not in stored, (f"raw secret persisted in the durable store: {s!r}")
    # the redaction marker proves the line itself was kept (fact-of not lost), value gone.
    assert "[redacted:" in stored, "redaction never happened — masking is not wired"

    # (2) no raw secret leaves via the ONE egress (ContextPack), across all purposes.
    for purpose in ("decide", "act", "speak"):
        pack = lm.build_context(about="portal card password ssn wire", purpose=purpose,
                                as_of=day1.timestamp())
        blob = pack.text + "\n" + "\n".join(pack.open_loops + pack.profile + pack.history +
                                            pack.derived + list(pack.provenance))
        for s in SECRETS:
            assert s not in blob, (f"raw secret egressed in ContextPack[{purpose}]: {s!r}")

    # (3) the health fact is TAGGED sensitive and RETENTION-bounded (auto-expires, not forever).
    health = next((it for it in lm.memory.history.all()
                   if "blood pressure" in it.text), None)
    assert health is not None, "health fact was dropped entirely"
    assert "health" in (health.fields.get("sensitivity") or []), (health.fields)
    assert health.valid_to is not None, "sensitive fact got no retention window (lives forever)"
    after_retention = day1.timestamp() + (RETENTION_DAYS + 5) * 86400.0
    assert not health.is_valid_at(after_retention), "sensitive fact did not expire past retention"
    # ...and it is genuinely gone from egress after retention.
    pack_future = lm.build_context(about="blood pressure medication", purpose="decide",
                                   as_of=after_retention)
    assert all("blood pressure" not in h for h in pack_future.history), \
        "expired sensitive fact still surfaced after its retention window"

    # (4) RIGHT-TO-DELETE wipes ALL traces (drawers + remember-list).
    pre = _all_stored_text(lm)
    assert pre.strip(), "nothing was stored — test is vacuous"
    res = lm.forget_all()
    assert res["removed"] >= 1, res
    post = _all_stored_text(lm)
    assert post.strip() == "", (f"traces survived right-to-delete: {post!r}")
    for drawer in (lm.memory.profile, lm.memory.open_loops, lm.memory.history, lm.memory.derived):
        assert drawer.all() == [], f"{drawer.name} not wiped by right-to-delete"
    assert lm.capturer.remember.count() == 0, "remember-list survived right-to-delete"

    print(f"OK  M5 privacy: {len(SECRETS)} secrets masked-at-rest & never egressed, "
          f"health tagged+retention={int(RETENTION_DAYS)}d, right-to-delete removed {res['removed']} rows")


if __name__ == "__main__":
    main()
