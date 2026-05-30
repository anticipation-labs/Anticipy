"""Local SQLite trivia cache.

Path: ``~/.anticipy/trivia_cache.db``. On first import the seed facts
from ``seed_facts.SEED_FACTS`` are written into the ``facts`` table.
Each (topic, alias) row is indexed for fast fuzzy match lookup.

Lookup strategy is deliberately simple and fast:

1. Lowercase the question, strip punctuation, drop common stopwords.
2. Score every alias against the cleaned question via a token-overlap
   plus character-bigram Jaccard hybrid. Pure Python, ~1-5 ms per
   question against ~1,000 aliases (168 facts x ~6 aliases each).
3. Return the top match if its score >= ``MIN_SCORE`` (default 0.45);
   else return None and let the answer module fall through to the LLM
   lane.

The embeddings lane is out of scope for the demo. The simple lookup
is reliable enough to hit ``"when did the Roman Empire fall"`` in
under 5 ms and resilient to common paraphrases. Tighten later.

Thread-safe: a module-level lock guards writes. SQLite's own
read-locking handles concurrent reads. The DB is opened in WAL mode
so the writer (seed load) does not block reads.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from .seed_facts import SEED_FACTS


_DEFAULT_DB_PATH = Path.home() / ".anticipy" / "trivia_cache.db"

_LOCK = threading.Lock()
_SEEDED = False
_CONN_CACHE: dict[str, sqlite3.Connection] = {}

# B034: Score threshold raised from 0.45 to 0.62 so loose paraphrases
# ("when did England win the world cup" matching "World Cup most wins" at
# 0.494) no longer fire. Real exact-phrase hits sit comfortably above 0.7.
MIN_SCORE = float(os.environ.get("ANTICIPY_TRIVIA_MIN_SCORE", "0.62"))

# B035: Require at least this many content tokens (after stopword removal)
# before firing. ASR mid-stream cutoffs like "wait when did the Roman Empire"
# otherwise score 0.696 and fire on the fall-of-Rome row.
MIN_CONTENT_TOKENS = int(os.environ.get("ANTICIPY_TRIVIA_MIN_TOKENS", "4"))

# Words that add noise to the match. "when did" / "what is" appear in
# many questions; their presence should not bias the score.
#
# B032: Do NOT strip country / proper-noun cues. Previously "france",
# "england", etc. were dropped at clean time, so "wait who is the current
# president of france" matched "current US president" with 2/3 token
# overlap. Country and continent words now stay and feed the proper-noun
# mismatch penalty in _score().
_STOPWORDS = {
    "a", "an", "the", "is", "was", "were", "are", "be", "been", "being",
    "do", "does", "did", "done", "doing",
    "have", "has", "had", "having",
    "when", "where", "why", "how", "what", "who", "whom", "whose",
    "which", "in", "on", "at", "of", "to", "for", "from", "by", "with",
    "and", "or", "but", "if", "so", "as", "it", "its", "this", "that",
    "these", "those", "you", "your", "yours",
    "i", "we", "us", "our", "ours", "they", "them", "their",
    "wait", "actually", "really", "ever", "just", "really", "exactly",
    "remember", "tell", "me", "us", "ok", "okay", "huh", "hmm", "uh",
    "um", "yeah", "yes", "no", "well", "like", "kind", "sort", "thing",
    "stuff", "year",
}

# Proper-noun cues. If a token from this set appears in the question but
# not in the alias (or vice versa), score is heavily penalized: a question
# about "France" must not fire on a "United States" alias just because
# "current president" overlaps.
_PROPER_NOUN_TOKENS = {
    # Major countries
    "france", "england", "britain", "uk", "germany", "italy", "spain",
    "portugal", "russia", "ukraine", "china", "japan", "korea",
    "india", "pakistan", "iran", "iraq", "israel", "egypt", "turkey",
    "canada", "mexico", "brazil", "argentina", "chile", "australia",
    "america", "usa", "us",
    # Major empires / civilizations
    "roman", "rome", "greek", "greece", "egyptian", "byzantine", "ottoman",
    "british", "spanish", "french",
    # Continents
    "europe", "asia", "africa", "americas",
    # Common historical events that easily collide
    "independence", "declaration", "founded", "founding",
}

_WORD_RE = re.compile(r"[A-Za-z0-9']+")


def db_path() -> Path:
    """Return the cache file path. Honor ``ANTICIPY_TRIVIA_DB`` override
    so tests can pin to a tmp file."""
    raw = os.environ.get("ANTICIPY_TRIVIA_DB", "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_DB_PATH


def _connect() -> sqlite3.Connection:
    path = str(db_path())
    conn = _CONN_CACHE.get(path)
    if conn is not None:
        return conn
    db_file = Path(path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    new_conn = sqlite3.connect(path, check_same_thread=False, timeout=10.0)
    new_conn.row_factory = sqlite3.Row
    try:
        new_conn.execute("PRAGMA journal_mode=WAL")
        new_conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    _create_schema(new_conn)
    _CONN_CACHE[path] = new_conn
    return new_conn


def _create_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            answer TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fact_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            alias_clean TEXT NOT NULL,
            FOREIGN KEY (fact_id) REFERENCES facts(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS aliases_clean_idx ON aliases(alias_clean)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS aliases_fact_idx ON aliases(fact_id)"
    )
    conn.commit()


def _clean(text: str) -> str:
    """Lowercase, strip punctuation, drop stopwords, normalize spacing."""
    if not text:
        return ""
    raw = text.lower()
    tokens = _WORD_RE.findall(raw)
    keep = [t for t in tokens if t not in _STOPWORDS]
    return " ".join(keep)


def _tokens(cleaned: str) -> set[str]:
    if not cleaned:
        return set()
    return set(cleaned.split())


def _char_bigrams(text: str) -> Counter:
    """Character bigrams over the cleaned text. Used as a soft-match
    backup so "constantinople" still matches "constantinople" with a
    typo or contraction."""
    if not text:
        return Counter()
    s = "  " + text + "  "
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


def _jaccard_counter(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    inter = sum((a & b).values())
    union = sum((a | b).values())
    if union == 0:
        return 0.0
    return inter / union


def _score(question_clean: str, alias_clean: str) -> float:
    """Hybrid token-overlap + char-bigram Jaccard score.

    - Token overlap (precision-leaning): fraction of alias tokens that
      appear in the question. Penalizes nothing when the question has
      extra words like "wait when did".
    - Char-bigram Jaccard (recall-leaning): handles paraphrase and
      partial spellings.

    Weighted 0.65 / 0.35 toward token overlap, which is the better
    signal on short questions.

    B032 + B033: If the question contains a proper-noun token (country,
    empire, etc.) and the alias does not, OR the alias contains a
    different proper-noun token, the score is zeroed out. This stops
    "france" from firing the US-president row and "Roman Empire founded"
    from firing the Declaration of Independence row.
    """
    if not question_clean or not alias_clean:
        return 0.0
    q_tokens = _tokens(question_clean)
    a_tokens = _tokens(alias_clean)
    if not a_tokens:
        return 0.0
    q_proper = q_tokens & _PROPER_NOUN_TOKENS
    a_proper = a_tokens & _PROPER_NOUN_TOKENS
    if q_proper and a_proper and not (q_proper & a_proper):
        return 0.0
    if q_proper and not a_proper:
        return 0.0
    overlap = len(q_tokens & a_tokens) / len(a_tokens)
    bigrams = _jaccard_counter(
        _char_bigrams(question_clean), _char_bigrams(alias_clean)
    )
    return 0.65 * overlap + 0.35 * bigrams


def ensure_seeded() -> int:
    """Idempotent. Returns the number of facts inserted on this call.

    Re-running is a no-op once the DB already has all seed facts; we
    upsert by (topic, alias) so adding a new alias to seed_facts later
    still propagates.
    """
    global _SEEDED
    with _LOCK:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("SELECT topic, id FROM facts")
        existing_topics: dict[str, int] = {
            str(row["topic"]).lower(): int(row["id"]) for row in cur.fetchall()
        }
        cur.execute("SELECT alias_clean FROM aliases")
        existing_aliases: set[str] = {
            str(row["alias_clean"]) for row in cur.fetchall()
        }
        inserted_facts = 0
        inserted_aliases = 0
        for entry in SEED_FACTS:
            topic = str(entry.get("topic") or "").strip()
            answer = str(entry.get("answer") or "").strip()
            source = str(entry.get("source") or "").strip()
            aliases = list(entry.get("aliases") or [])
            if not topic or not answer:
                continue
            topic_key = topic.lower()
            fact_id = existing_topics.get(topic_key)
            if fact_id is None:
                cur.execute(
                    "INSERT INTO facts (topic, answer, source, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (topic, answer, source, time.time()),
                )
                fact_id = int(cur.lastrowid or 0)
                existing_topics[topic_key] = fact_id
                inserted_facts += 1
            # Always include the topic itself as an alias so a question
            # phrased exactly like the canonical topic still scores.
            for alias in [topic, *aliases]:
                alias_str = str(alias).strip()
                if not alias_str:
                    continue
                alias_clean = _clean(alias_str)
                if not alias_clean:
                    continue
                if alias_clean in existing_aliases:
                    continue
                cur.execute(
                    "INSERT INTO aliases (fact_id, alias, alias_clean) "
                    "VALUES (?, ?, ?)",
                    (fact_id, alias_str, alias_clean),
                )
                existing_aliases.add(alias_clean)
                inserted_aliases += 1
        conn.commit()
        _SEEDED = True
        return inserted_facts


def lookup(question: str, *, min_score: Optional[float] = None) -> Optional[dict]:
    """Return the best matching fact for ``question`` or None.

    On hit returns dict with keys: ``topic``, ``answer``, ``source``,
    ``score``, ``alias``, ``fact_id``, ``elapsed_ms``.
    """
    if not question or not question.strip():
        return None
    t0 = time.monotonic()
    if not _SEEDED:
        try:
            ensure_seeded()
        except Exception:
            return None
    threshold = float(min_score if min_score is not None else MIN_SCORE)
    cleaned_q = _clean(question)
    if not cleaned_q:
        return None
    # B035: refuse to fire on incomplete utterances. ASR mid-stream cuts
    # otherwise score 0.696 on stub questions like "wait when did the
    # Roman Empire" and surface a wrong fall-of-Rome answer.
    if len(_tokens(cleaned_q)) < MIN_CONTENT_TOKENS:
        return None
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT aliases.alias, aliases.alias_clean, aliases.fact_id, "
        "facts.topic, facts.answer, facts.source "
        "FROM aliases JOIN facts ON facts.id = aliases.fact_id"
    )
    rows = cur.fetchall()
    if not rows:
        return None
    best_score = 0.0
    best_row: Optional[sqlite3.Row] = None
    for row in rows:
        score = _score(cleaned_q, str(row["alias_clean"] or ""))
        if score > best_score:
            best_score = score
            best_row = row
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    if best_row is None or best_score < threshold:
        return None
    return {
        "topic": str(best_row["topic"]),
        "answer": str(best_row["answer"]),
        "source": str(best_row["source"]),
        "score": round(float(best_score), 4),
        "alias": str(best_row["alias"]),
        "fact_id": int(best_row["fact_id"]),
        "elapsed_ms": round(float(elapsed_ms), 2),
    }


def count() -> int:
    """Return number of facts currently cached."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM facts")
    row = cur.fetchone()
    return int((row[0] if row else 0) or 0)


def stats() -> dict:
    """Diagnostic: facts and aliases count plus DB path."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM facts")
    facts = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM aliases")
    aliases = int(cur.fetchone()[0] or 0)
    return {
        "facts": facts,
        "aliases": aliases,
        "db_path": str(db_path()),
        "seeded": bool(_SEEDED),
    }


__all__ = [
    "MIN_SCORE",
    "count",
    "db_path",
    "ensure_seeded",
    "lookup",
    "stats",
]
