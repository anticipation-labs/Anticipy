"""final/tests/embed_gemini_proof.py — PROOF: real Gemini embeddings give paraphrase-robust recall.

The claim: with the stub (hashed bag-of-tokens) embedder, a query that shares NO content
words with a stored memory cannot be recalled — worse, a keyword-trap distractor that shares
a stopword steals the top rank. With real Gemini embeddings the SAME query recalls the SAME
memory by MEANING.

Concretely: store "schedule a trim" alongside keyword traps ("book a table", ...), then query
"book a haircut" (zero content-word overlap with the trim memory; shares "book"/"a" with the
trap). We assert:
  - GEMINI ranks "schedule a trim" #1 with high cosine, and
  - STUB is fooled — it ranks the "book a table" trap above "schedule a trim".

Runs entirely local against the Memory store (fresh temp dirs; never touches real data). Needs
GOOGLE_API_KEY/GEMINI_API_KEY (auto-loaded from .env.local) for the gemini leg.

Run:  engine/.venv/bin/python final/tests/embed_gemini_proof.py
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

# load .env.local so GOOGLE_API_KEY is available (same loader the engine uses)
try:
    from anticipy_engine.core.env import load_local_env
    load_local_env()
except Exception:
    pass

from anticipy_engine.memory import embed as embed_mod
from anticipy_engine.memory.store import Memory

TARGET = "schedule a trim"
TRAP = "book a table"
DISTRACTORS = [TRAP, "buy a car", "call a plumber", "pay the electricity bill"]
QUERY = "book a haircut"  # paraphrase of TARGET; zero content-word overlap; shares "book"/"a" with TRAP


def ranked(provider: str):
    """Store TARGET + distractors and rank them against QUERY, under the given provider."""
    prev = os.environ.get("ANTICIPY_EMBED_PROVIDER", "")
    os.environ["ANTICIPY_EMBED_PROVIDER"] = provider
    try:
        d = tempfile.mkdtemp(prefix=f"embedproof_{provider or 'stub'}_")
        mem = Memory(data_dir=Path(d))
        for text in [TARGET, *DISTRACTORS]:
            mem.history.write_text(text)
        qv = embed_mod.embed(QUERY)
        scored = []
        for item in mem.history.all():
            row = mem.db.get(item.id)  # embedding is on the row
            import json as _json
            emb = _json.loads(mem.db.conn.execute(
                "SELECT embedding FROM items WHERE id=?", (item.id,)).fetchone()["embedding"])
            scored.append((item.text, embed_mod.cosine(qv, emb)))
        scored.sort(key=lambda x: -x[1])
        return scored
    finally:
        if prev:
            os.environ["ANTICIPY_EMBED_PROVIDER"] = prev
        else:
            os.environ.pop("ANTICIPY_EMBED_PROVIDER", None)


def show(label, rows):
    print(f"\n=== {label} — ranking for query {QUERY!r} ===")
    for text, sc in rows:
        mark = "  <- TARGET" if text == TARGET else ("  <- keyword trap" if text == TRAP else "")
        print(f"  {sc:.4f}  {text}{mark}")


def main():
    if not (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        print("SKIP: no GOOGLE_API_KEY/GEMINI_API_KEY in env (.env.local).")
        return 2

    stub_rows = ranked("")            # on-device default == stub (ANTICIPY_MEMORY_MODE unset)
    gem_rows = ranked("gemini")

    show("STUB (hashed bag-of-tokens)", stub_rows)
    show("GEMINI (gemini-embedding-001)", gem_rows)

    stub_rank = [t for t, _ in stub_rows]
    gem_rank = [t for t, _ in gem_rows]
    stub_target = dict(stub_rows)[TARGET]
    gem_target = dict(gem_rows)[TARGET]

    print("\n--- verdict ---")
    print(f"stub: cos(query, TARGET)   = {stub_target:.4f}   top-1 = {stub_rank[0]!r}")
    print(f"gemini: cos(query, TARGET) = {gem_target:.4f}   top-1 = {gem_rank[0]!r}")

    failures = []
    # 1) gemini recalls the paraphrase as #1
    if gem_rank[0] != TARGET:
        failures.append(f"gemini top-1 should be TARGET, got {gem_rank[0]!r}")
    # 2) gemini cosine to the paraphrase is high
    if gem_target < 0.60:
        failures.append(f"gemini cos(query,TARGET)={gem_target:.4f} not high (>=0.60)")
    # 3) stub is fooled: the keyword trap outranks the true paraphrase
    if stub_rank.index(TRAP) >= stub_rank.index(TARGET):
        failures.append("stub was expected to rank the keyword TRAP above TARGET, but didn't")
    # 4) gemini beats the trap for the true meaning
    if dict(gem_rows)[TARGET] <= dict(gem_rows)[TRAP]:
        failures.append("gemini should score TARGET above the keyword TRAP")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nPASS: Gemini recalls the paraphrase (semantic) where the stub follows keywords into the trap.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
