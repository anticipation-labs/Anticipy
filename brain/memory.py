"""Anticipy's memory: a temporal knowledge graph, not a transcript dump.

Every line the pendant hears becomes an *episode*. From each episode an
extractor pulls entities (people, places, things, topics) and typed, timestamped
edges between them (said_to, committed_to, about, at). Commitments are
first-class nodes with an open/done/cancelled lifecycle — they are the
orchestrator's to-do list.

Recall is graph-walk + time, not embedding soup: start at the entities named in
the query, walk their edges, and return a time-ordered chain of connected facts
(a "linear graph"). That answers "what did I tell Sarah last week?" with the
actual chain: episode -> commitment -> person, newest first, with provenance.

On top of the raw graph sits the PROFILE layer (roadmap §1): a consolidation
pass reads recent episodes and distills the stable facts worth knowing someone
by — "partner is Sarah", "prefers 7pm dinners" — each with importance (1-5),
confidence, and the episode ids it came from. Recall consults the profile
first, ranked importance x recency x relevance, so "my mom is in hospital"
outranks a grocery mumble instead of weighing the same. Raw episodes are never
deleted; the profile is a lens, not a replacement.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,          -- person | place | thing | topic | commitment
    name TEXT NOT NULL,
    attrs TEXT NOT NULL DEFAULT '{}',
    status TEXT,                 -- commitments: open | done | cancelled
    created_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL,
    UNIQUE(type, name)
);
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY,
    src INTEGER NOT NULL REFERENCES nodes(id),
    rel TEXT NOT NULL,           -- said_to | committed_to | about | at | involves
    dst INTEGER NOT NULL REFERENCES nodes(id),
    episode_id INTEGER REFERENCES episodes(id),
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
CREATE TABLE IF NOT EXISTS profile_facts (
    id INTEGER PRIMARY KEY,
    fact TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,   -- 1-5, model-judged at distillation
    confidence REAL NOT NULL DEFAULT 0.6,    -- grows each time the fact re-appears
    source TEXT NOT NULL DEFAULT 'consolidation',  -- consolidation | interview | import
    provenance TEXT NOT NULL DEFAULT '[]',   -- JSON list of episode ids
    first_seen_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS consolidation_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Full-text index so recall searches EVERY episode instead of the newest few.
# Kept separate because it is optional: if this SQLite build lacks FTS5, the
# search falls back to LIKE and nothing breaks.
FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    text, content='episodes', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
    INSERT INTO episodes_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
    INSERT INTO episodes_fts(episodes_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
"""


@dataclass
class Extraction:
    """What one episode contributes to the graph."""
    people: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    commitment: Optional[str] = None   # "send the pitch deck to Sarah"
    commitment_to: Optional[str] = None  # "Sarah"
    completed: Optional[str] = None    # "sent Priya the launch plan"


EXTRACT_SYSTEM = """You extract memory from one line someone said during their day.
Reply ONLY with compact JSON:
{"people":["..."],"places":["..."],"topics":["..."],
 "commitment":"<what the speaker promised to do, or null>",
 "commitment_to":"<who it was promised to, or null>",
 "completed":"<what the speaker says they ALREADY DID, or null>"}
People are proper names only. Topics are 1-3 word noun phrases. A commitment is
only something the SPEAKER promised to do. "completed" is for past-tense
reports of finishing something ("sent Priya the deck", "already paid it",
"that's done") — the thing that got done, not the whole sentence."""

CONSOLIDATE_SYSTEM = """You distill what someone's assistant should KNOW about them from
lines overheard during their day. Each input line is "[id] text".
Reply ONLY with compact JSON:
{"facts":[{"fact":"...","importance":N,"episode_ids":[id,...]}]}
A fact is something STABLE — true for weeks, worth knowing them by: who
matters to them ("partner is Sarah"), preferences ("prefers 7pm dinners"),
their work ("building Anticipy"), health, routines, ongoing situations
("mom is in hospital"). NOT one-off logistics, small talk, or anything that
is only a task. Write each fact as a short third-person note. importance is
1-5: 5 = core of their life (family, health, hard boundaries), 3 = a solid
preference or ongoing project, 1 = mildly useful color. episode_ids lists
the [id]s of the input lines the fact came from — only ids you were given.
Nothing worth keeping -> {"facts":[]}."""

SAME_FACT_SYSTEM = """Two short notes about the same person. Decide whether they state the
SAME underlying fact (one restates or updates the other) or genuinely
different facts. "partner is Sarah" / "his partner's name is Sarah" -> same.
"prefers 7pm dinners" / "prefers Italian food" -> different.
Reply ONLY with compact JSON: {"same":true} or {"same":false}."""

# Rule fallback so completion still works with no model available.
_DONE_RE = re.compile(
    r"\b(already|just)\s+(sent|paid|booked|called|emailed|texted|finished|did|"
    r"done|handled|submitted|filed|ordered)\b"
    r"|\b(sent|paid|booked|called|emailed|texted|finished|handled|submitted|"
    r"filed|ordered)\s+(it|that|them|him|her)\b"
    r"|\b(that'?s|it'?s|all)\s+(done|sorted|handled|taken care of)\b"
    r"|\bi\s+(sent|paid|booked|called|emailed|texted|finished|did|handled)\b",
    re.IGNORECASE)


class Memory:
    def __init__(self, path: str | Path = ":memory:", llm=None):
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)
        try:
            self.db.executescript(FTS_SCHEMA)
            # Backfill an existing database once, so memory recorded before
            # the index existed is searchable too.
            missing = self.db.execute(
                "SELECT COUNT(*) FROM episodes WHERE id NOT IN "
                "(SELECT rowid FROM episodes_fts)").fetchone()[0]
            if missing:
                self.db.execute(
                    "INSERT INTO episodes_fts(rowid, text) "
                    "SELECT id, text FROM episodes WHERE id NOT IN "
                    "(SELECT rowid FROM episodes_fts)")
                self.db.commit()
        except sqlite3.Error:
            pass  # no FTS5 in this build; _search_episodes falls back to LIKE
        self.llm = llm  # optional LLM extractor; falls back to rules

    # ------------------------------------------------------------- ingest

    def ingest(self, text: str, ts: Optional[float] = None) -> dict:
        ts = ts or time.time()
        cur = self.db.execute("INSERT INTO episodes(ts, text) VALUES (?, ?)", (ts, text))
        episode_id = cur.lastrowid
        ex = self._extract(text)

        node_ids = {}
        for name in ex.people:
            node_ids[name] = self._upsert_node("person", name, ts)
        for name in ex.places:
            node_ids[name] = self._upsert_node("place", name, ts)
        for name in ex.topics:
            node_ids[name] = self._upsert_node("topic", name, ts)

        commitment_id = None
        if ex.commitment:
            # The episode this promise came out of, kept ON the commitment.
            # Before this, provenance existed only as edges to people/places —
            # so a commitment mentioning nobody had no traceable source at all,
            # and nothing could answer "why do I believe this?". Loops with no
            # source are exactly the ones she invented; open_loops() surfaces
            # the quote so the clock can refuse to raise anything unevidenced.
            commitment_id = self._upsert_node(
                "commitment", ex.commitment, ts, status="open",
                attrs={"source_episode": episode_id})
            if ex.commitment_to and ex.commitment_to in node_ids:
                self._add_edge(commitment_id, "committed_to",
                               node_ids[ex.commitment_to], episode_id, ts)
            for name, nid in node_ids.items():
                if name != ex.commitment_to:
                    self._add_edge(commitment_id, "involves", nid, episode_id, ts)

        # Saying you DID something closes the promise. Without this, an open
        # loop lived forever and the clock would nag about finished work —
        # the fastest way to make her look stupid.
        closed = self.close_from_speech(text, ex.completed)

        # Everything mentioned together in one breath is related.
        ids = list(node_ids.values())
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                self._add_edge(a, "about", b, episode_id, ts)

        self.db.commit()
        return {
            "episode_id": episode_id,
            "entities": list(node_ids),
            "commitment": ex.commitment,
            "commitment_id": commitment_id,
            "closed": closed,
        }

    def close_matching(self, about: str, status: str = "done") -> list[str]:
        """A plan finished or died OUTSIDE speech — its job was cancelled,
        its card declined — and the promise it grew from must close with it.
        Live, 2026-08-10: a toothbrush order was cancelled on the 4th, but
        the commitment behind it stayed "open", so six days later the clock
        texted "did you manage to get the toothbrush?" about a dead plan."""
        return self.close_from_speech(about, completed=about, status=status)

    def close_from_speech(self, text: str, completed: Optional[str] = None,
                          status: str = "done") -> list[str]:
        """The owner said they finished something — find which open promise
        that was and mark it done. Matches on word overlap, and only when the
        overlap is real, so 'I sent it' never closes an unrelated promise."""
        if not completed and not _DONE_RE.search(text or ""):
            return []
        claim = completed or text
        claim_words = {w for w in re.findall(r"[a-z0-9']+", claim.lower())
                       if len(w) > 2 and w not in self._STOP}
        if not claim_words:
            return []
        best, best_score, best_id = None, 0.0, None
        for loop in self.open_loops():
            words = {w for w in re.findall(r"[a-z0-9']+", loop["what"].lower())
                     if len(w) > 2 and w not in self._STOP}
            if not words:
                continue
            score = len(words & claim_words) / len(words)
            if score > best_score:
                best, best_score, best_id = loop["what"], score, loop["id"]
        # Half the promise's meaningful words must reappear. A bare "that's
        # done" with one open loop still closes it; with several it does not
        # guess, because closing the wrong promise is worse than closing none.
        if best_id is not None and best_score >= 0.5:
            self.resolve(best_id, status)
            return [best]
        return []

    # ------------------------------------------------------------- recall

    _STOP = {
        "the", "and", "was", "were", "are", "you", "your", "our", "for",
        "with", "that", "this", "what", "when", "where", "who", "whose",
        "which", "did", "does", "have", "has", "had", "want", "wants",
        "see", "get", "got", "how", "why", "can", "will", "would", "they",
        "them", "his", "her", "she", "him", "out", "not", "but", "about",
        "again", "still", "just", "there", "here", "into", "onto", "from",
    }

    def recall(self, query: str, limit: int = 8) -> list[dict]:
        """Relevance-then-time ordered chain of facts connected to the
        entities in `query`. Stopwords never seed matches — otherwise "the"
        matches every episode and recent noise buries the real answer."""
        words = {w.strip(".,!?").lower() for w in query.split()
                 if len(w) > 2 and w.strip(".,!?").lower() not in self._STOP}
        # What she KNOWS about him answers before what she happened to
        # overhear: the distilled profile is consulted first, ranked
        # importance x recency x relevance, and the raw graph/episode search
        # fills whatever window is left (roadmap §1).
        profile = self._profile_recall(words, limit)
        rows = self.db.execute("SELECT id, type, name, status FROM nodes").fetchall()

        def seeds_match(name: str) -> bool:
            # Token matching, NOT bidirectional substring: "Ann" used to seed
            # off "cannot" and "Sam" off "same", dragging unrelated people
            # into recall (and thence into triage context).
            tokens = {t.strip(".,!?") for t in name.lower().split()}
            for w in words:
                if w in tokens:
                    return True
                if len(w) >= 4 and any(t.startswith(w) or w.startswith(t)
                                       for t in tokens if len(t) >= 4):
                    return True
            return False

        seeds = [r for r in rows if seeds_match(r[2])]

        # Episodes whose raw text matches the query are facts in their own
        # right — a line can matter even when extraction pulled no entities.
        # SEARCHED, not scanned: the old code looked at only the newest 200
        # episodes, so a fact stated this morning became unrecallable by
        # afternoon ("the gate code is 4417" was provably lost after 240
        # later lines). A day of ambient listening blows past 200 in an hour.
        facts = []
        for eid, ts, text in self._search_episodes(words):
            hits = sum(1 for w in words if w in text.lower())
            if hits >= 2 or (hits == 1 and len(words) == 1):
                facts.append({"fact": f'heard: "{text}"',
                              "src_type": "episode", "dst_type": "episode",
                              "ts": ts, "quote": text})
        if not seeds and not facts:
            return profile

        seen = set()
        frontier = [r[0] for r in seeds]
        for _hop in range(2):  # 2-hop walk keeps recall on-topic
            next_frontier = []
            for nid in frontier:
                if nid in seen:
                    continue
                seen.add(nid)
                for src, rel, dst, ep, ts in self.db.execute(
                    "SELECT src, rel, dst, episode_id, ts FROM edges "
                    "WHERE src=? OR dst=?", (nid, nid)
                ):
                    other = dst if src == nid else src
                    next_frontier.append(other)
                    facts.append(self._fact(src, rel, dst, ep, ts))
            frontier = next_frontier

        # Dedupe on the FACT itself, keeping the newest occurrence: every
        # co-mention inserted a fresh identical edge, so one repeated
        # relationship filled the whole recall window with copies of itself.
        uniq: dict[str, dict] = {}
        for f in sorted(facts, key=lambda f: f["ts"]):
            uniq[f["fact"]] = f

        def relevance(f):
            blob = (f["fact"] + " " + (f.get("quote") or "")).lower()
            return sum(1 for w in words if w in blob)
        graph = sorted(uniq.values(), key=lambda f: (-relevance(f), -f["ts"]))
        return (profile + graph)[:limit]

    def _search_episodes(self, words: set[str], limit: int = 300):
        """Every episode ever heard is searchable — no recency cliff. Uses
        the FTS index when it exists, and a LIKE query otherwise, so an old
        database keeps working without a rebuild."""
        if not words:
            return []
        terms = sorted(words)[:8]
        try:
            q = " OR ".join(f'"{t}"' for t in terms)
            rows = self.db.execute(
                "SELECT e.id, e.ts, e.text FROM episodes_fts f "
                "JOIN episodes e ON e.id = f.rowid "
                "WHERE episodes_fts MATCH ? ORDER BY e.ts DESC LIMIT ?",
                (q, limit),
            ).fetchall()
            if rows:
                return rows
        except sqlite3.Error:
            pass
        clause = " OR ".join("LOWER(text) LIKE ?" for _ in terms)
        args = [f"%{t}%" for t in terms] + [limit]
        return self.db.execute(
            f"SELECT id, ts, text FROM episodes WHERE {clause} "
            f"ORDER BY ts DESC LIMIT ?", args,
        ).fetchall()

    def open_loops(self) -> list[dict]:
        """Open commitments, oldest first — the orchestrator's to-do list.

        Each carries `source`: the exact thing he said that created it, or None
        when the promise predates provenance or was never grounded in speech.
        Callers that are about to INTERRUPT him should require a source."""
        rows = self.db.execute(
            "SELECT id, name, created_ts, attrs FROM nodes "
            "WHERE type='commitment' AND status='open' ORDER BY created_ts"
        ).fetchall()
        out = []
        for r in rows:
            try:
                eid = (json.loads(r[3] or "{}") or {}).get("source_episode")
            except Exception:
                eid = None
            src = None
            if eid:
                ep = self.db.execute(
                    "SELECT text FROM episodes WHERE id=?", (eid,)).fetchone()
                src = ep[0] if ep else None
            out.append({"id": r[0], "what": r[1], "ts": r[2], "source": src})
        return out

    def resolve(self, commitment_id: int, status: str = "done"):
        self.db.execute("UPDATE nodes SET status=? WHERE id=?", (status, commitment_id))
        self.db.commit()

    def briefing_facts(self, since_ts: float) -> dict:
        """Raw material for the assistant's 'I overheard…' briefing.

        The profile leads: what she KNOWS about him (distilled, ranked by
        importance x recency) comes before the raw lines she happened to
        hear, so a briefing is grounded in who he is, not just today's
        noise. `heard` and `open_loops` keep their exact old shape."""
        heard = self.db.execute(
            "SELECT text FROM episodes WHERE ts>=? ORDER BY ts", (since_ts,)
        ).fetchall()
        profile = [{"fact": f["fact"], "importance": f["importance"]}
                   for f in self.profile_facts(limit=10)]
        return {"profile": profile,
                "heard": [h[0] for h in heard],
                "open_loops": self.open_loops()}

    # ------------------------------------------------- profile / consolidation

    def remember_fact(self, text: str, importance: int = 4,
                      source: str = "interview", confidence: float = 0.9,
                      ts: Optional[float] = None) -> int:
        """Seed the profile directly — the day-zero interview (roadmap §8)
        writes what he tells her here, so she is not amnesiac on install.
        Merges into an existing row when it already states the same fact
        (re-posting an interview answer must not dupe). Returns the row id."""
        text = (text or "").strip()
        if not text:
            raise ValueError("remember_fact needs actual text")
        ts = ts or time.time()
        importance = max(1, min(5, int(importance)))
        match = self._find_same_fact(text)
        if match is not None:
            self._merge_fact(match, importance, ts, [])
            self.db.commit()
            return match
        fid = self._insert_fact(text, importance, confidence, source, ts, [])
        self.db.commit()
        return fid

    def profile_facts(self, limit: Optional[int] = None) -> list[dict]:
        """The distilled profile, most important-and-fresh first. Salience
        here is importance x recency (half-life 30 days on last_seen), so a
        core fact stays near the top for months and stale color sinks."""
        now = time.time()
        out = []
        for r in self.db.execute(
            "SELECT id, fact, importance, confidence, source, provenance, "
            "first_seen_ts, last_seen_ts FROM profile_facts"
        ):
            try:
                prov = json.loads(r[5] or "[]")
            except Exception:
                prov = []
            age_days = max(0.0, (now - r[7]) / 86400.0)
            out.append({
                "id": r[0], "fact": r[1], "importance": r[2],
                "confidence": r[3], "source": r[4], "provenance": prov,
                "first_seen_ts": r[6], "last_seen_ts": r[7],
                "salience": r[2] * (0.5 ** (age_days / 30.0)),
            })
        out.sort(key=lambda f: -f["salience"])
        return out[:limit] if limit else out

    def consolidate(self, now: Optional[float] = None, batch: int = 200) -> dict:
        """One incremental consolidation pass: read episodes newer than the
        last consolidated id, have the model distill stable facts, merge or
        insert them, then advance the cursor — all in ONE transaction, so a
        crash mid-pass loses nothing and the same episodes are simply read
        again next time. With llm=None the pass is skipped entirely: the
        profile just stays empty, nothing crashes.

        Returns counters: {"ran", "episodes", "new", "merged", "remaining"}.
        ran=False means nothing was written OR advanced (no model, or the
        model's output was unusable)."""
        if not self.llm:
            return {"ran": False, "reason": "no llm", "episodes": 0,
                    "new": 0, "merged": 0, "remaining": 0}
        now = now or time.time()
        last = int(self._state_get("last_episode_id", "0") or 0)
        rows = self.db.execute(
            "SELECT id, ts, text FROM episodes WHERE id>? ORDER BY id LIMIT ?",
            (last, batch)).fetchall()
        if not rows:
            self._state_set("last_run_ts", str(now))
            self.db.commit()
            return {"ran": True, "episodes": 0, "new": 0, "merged": 0,
                    "remaining": 0}
        try:
            listing = "\n".join(f"[{r[0]}] {r[2]}" for r in rows)
            res = self.llm.chat(CONSOLIDATE_SYSTEM, listing)
            cands = json.loads(_extract_json(res.text)).get("facts")
            if not isinstance(cands, list):
                raise ValueError("no facts list in model output")
        except Exception as e:
            # Nothing advanced: these episodes stay unconsolidated and the
            # next pass re-reads them. A flaky model must not eat a day.
            return {"ran": False, "reason": f"model output unusable: {e}",
                    "episodes": 0, "new": 0, "merged": 0,
                    "remaining": self._episodes_after(last)}
        valid = {r[0]: r[1] for r in rows}  # id -> ts
        new = merged = 0
        try:
            for c in cands:
                if not isinstance(c, dict):
                    continue
                text = c.get("fact")
                if not isinstance(text, str) or not text.strip():
                    continue
                text = text.strip()
                try:
                    imp = max(1, min(5, int(c.get("importance", 3))))
                except Exception:
                    imp = 3
                eps = c.get("episode_ids")
                # The model writes ids as ints or as digit strings ("[1]" in
                # the prompt invites both); either way they must resolve to
                # episodes it was actually shown.
                clean: list[int] = []
                for e in eps if isinstance(eps, list) else []:
                    if isinstance(e, bool):
                        continue
                    if isinstance(e, str) and e.strip().isdigit():
                        e = int(e.strip())
                    if isinstance(e, int) and e in valid:
                        clean.append(e)
                eps = list(dict.fromkeys(clean))
                # A fact with no traceable source does not get written — same
                # doctrine as commitments: nothing unevidenced in the graph.
                if not eps:
                    continue
                fact_ts = max(valid[e] for e in eps)
                match = self._find_same_fact(text)
                if match is not None:
                    self._merge_fact(match, imp, fact_ts, eps)
                    merged += 1
                else:
                    self._insert_fact(text, imp, 0.6, "consolidation",
                                      fact_ts, eps)
                    new += 1
            self._state_set("last_episode_id", str(rows[-1][0]))
            self._state_set("last_run_ts", str(now))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"ran": True, "episodes": len(rows), "new": new,
                "merged": merged, "remaining": self._episodes_after(rows[-1][0])}

    def last_consolidation_ts(self) -> float:
        try:
            return float(self._state_get("last_run_ts", "0") or 0)
        except ValueError:
            return 0.0

    def _episodes_after(self, episode_id: int) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM episodes WHERE id>?", (episode_id,)
        ).fetchone()[0]

    def _profile_recall(self, words: set[str], limit: int) -> list[dict]:
        """Profile facts matching the query, ranked by importance x recency
        x relevance — so "mom is in hospital" beats a grocery mumble even
        when the mumble is newer and matches more words."""
        if not words:
            return []
        out = []
        for f in self.profile_facts():
            blob = f["fact"].lower()
            rel = sum(1 for w in words if w in blob)
            if not rel:
                continue
            out.append({
                "fact": f'known: {f["fact"]}',
                "src_type": "profile", "dst_type": "profile",
                "ts": f["last_seen_ts"], "quote": None,
                "importance": f["importance"],
                "salience": f["salience"] * rel,
            })
        out.sort(key=lambda f: -f["salience"])
        if len(out) < limit:
            # Wording is the model's, not the owner's — "go-to restaurant"
            # answers "usual dinner spot" yet shares no word with it. The
            # most important known facts ride along so a paraphrased
            # question still reaches what she actually knows.
            have = {f["fact"] for f in out}
            rest = sorted((f for f in self.profile_facts()
                           if f"known: {f['fact']}" not in have),
                          key=lambda f: -f["importance"])
            for f in rest[:limit - len(out)]:
                out.append({
                    "fact": f'known: {f["fact"]}',
                    "src_type": "profile", "dst_type": "profile",
                    "ts": f["last_seen_ts"], "quote": None,
                    "importance": f["importance"],
                    "salience": 0.0,
                })
        return out[:limit]

    def _find_same_fact(self, text: str) -> Optional[int]:
        """The existing profile row that states the same fact, or None.
        Identical-after-normalization needs no model; near matches are
        LLM-judged same-fact; with no model only the deterministic paths
        run, so near-identical wording still merges offline."""
        norm = " ".join(_fact_tokens(text))
        cand_words = {w for w in _fact_tokens(text)
                      if len(w) > 2 and w not in self._STOP}
        near = []
        for rid, fact in self.db.execute(
                "SELECT id, fact FROM profile_facts").fetchall():
            fnorm = " ".join(_fact_tokens(fact))
            if fnorm == norm:
                return rid
            fwords = {w for w in _fact_tokens(fact)
                      if len(w) > 2 and w not in self._STOP}
            if not cand_words or not fwords:
                continue
            overlap = len(cand_words & fwords) / len(cand_words | fwords)
            if overlap >= 0.8:
                return rid          # near-identical wording; no model needed
            if overlap >= 0.4:
                near.append((overlap, rid, fact))
        if self.llm and near:
            for _overlap, rid, fact in sorted(near, reverse=True)[:3]:
                try:
                    res = self.llm.chat(SAME_FACT_SYSTEM,
                                        json.dumps({"a": fact, "b": text}))
                    if json.loads(_extract_json(res.text)).get("same") is True:
                        return rid
                except Exception:
                    continue
        return None

    def _insert_fact(self, text: str, importance: int, confidence: float,
                     source: str, ts: float, episode_ids: list[int]) -> int:
        cur = self.db.execute(
            "INSERT INTO profile_facts(fact, importance, confidence, source, "
            "provenance, first_seen_ts, last_seen_ts) VALUES (?,?,?,?,?,?,?)",
            (text, importance, confidence, source,
             json.dumps(episode_ids or []), ts, ts))
        return cur.lastrowid

    def _merge_fact(self, fact_id: int, importance: int, ts: float,
                    episode_ids: list[int]) -> None:
        """A restatement is evidence, not a new row: bump confidence, keep
        the higher importance, extend provenance, refresh last_seen. The
        original wording stays — churning the text on every restatement
        would make the profile impossible to audit."""
        row = self.db.execute(
            "SELECT importance, confidence, provenance, last_seen_ts "
            "FROM profile_facts WHERE id=?", (fact_id,)).fetchone()
        if not row:
            return
        try:
            prov = json.loads(row[2] or "[]")
        except Exception:
            prov = []
        for e in episode_ids or []:
            if e not in prov:
                prov.append(e)
        prov = prov[-40:]  # bound growth; the newest evidence matters most
        self.db.execute(
            "UPDATE profile_facts SET importance=?, confidence=?, "
            "provenance=?, last_seen_ts=? WHERE id=?",
            (max(row[0], importance), min(0.99, row[1] + 0.15),
             json.dumps(prov), max(row[3], ts), fact_id))

    def _state_get(self, key: str, default: str = "") -> str:
        row = self.db.execute(
            "SELECT value FROM consolidation_state WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else default

    def _state_set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO consolidation_state(key, value) "
            "VALUES (?, ?)", (key, value))

    # ----------------------------------------------------------- internals

    def _fact(self, src, rel, dst, episode_id, ts) -> dict:
        name = lambda i: self.db.execute(
            "SELECT type, name FROM nodes WHERE id=?", (i,)).fetchone()
        s, d = name(src), name(dst)
        quote = None
        if episode_id:
            row = self.db.execute(
                "SELECT text FROM episodes WHERE id=?", (episode_id,)).fetchone()
            quote = row[0] if row else None
        return {
            "fact": f"{s[1]} —{rel}→ {d[1]}",
            "src_type": s[0], "dst_type": d[0],
            "ts": ts, "quote": quote,
        }

    def _upsert_node(self, type_: str, name: str, ts: float,
                     status: Optional[str] = None,
                     attrs: Optional[dict] = None) -> int:
        row = self.db.execute(
            "SELECT id FROM nodes WHERE type=? AND name=?", (type_, name)).fetchone()
        if row:
            self.db.execute("UPDATE nodes SET last_seen_ts=? WHERE id=?", (ts, row[0]))
            return row[0]
        cur = self.db.execute(
            "INSERT INTO nodes(type, name, status, created_ts, last_seen_ts, attrs) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (type_, name, status, ts, ts, json.dumps(attrs or {})))
        return cur.lastrowid

    def _add_edge(self, src: int, rel: str, dst: int, episode_id: int, ts: float):
        self.db.execute(
            "INSERT INTO edges(src, rel, dst, episode_id, ts) VALUES (?, ?, ?, ?, ?)",
            (src, rel, dst, episode_id, ts))

    # --------------------------------------------------------- extraction

    def _extract(self, text: str) -> Extraction:
        if self.llm:
            try:
                res = self.llm.chat(EXTRACT_SYSTEM, text)
                raw = json.loads(_extract_json(res.text))

                def names(key: str) -> list[str]:
                    # A bare string where a list was promised iterates per
                    # CHARACTER: "Sarah" became nodes S, a, r, a, h in the
                    # permanent graph, which then matched everything.
                    val = raw.get(key)
                    if isinstance(val, str):
                        val = [val]
                    if not isinstance(val, list):
                        return []
                    return [v.strip() for v in val
                            if isinstance(v, str) and len(v.strip()) > 1]

                def one(key: str):
                    val = raw.get(key)
                    return val.strip() if isinstance(val, str) and val.strip() else None

                return Extraction(
                    people=names("people"),
                    places=names("places"),
                    topics=names("topics"),
                    commitment=one("commitment"),
                    commitment_to=one("commitment_to"),
                )
            except Exception:
                pass
        return _rule_extract(text)


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start >= 0 <= end else "{}"


def _fact_tokens(text: str) -> list[str]:
    """Lowercase word tokens with possessives folded — "partner's" and
    "partner" must count as the same word or restatements never match."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [w[:-2] if w.endswith("'s") else w for w in words]


_COMMIT_RE = re.compile(
    r"\bI(?:'ll| will| can| should)\s+(.+?)(?:\.|$)", re.IGNORECASE)
_NAME_RE = re.compile(r"\b(?<![.!?]\s)([A-Z][a-z]{2,})\b")
_NOT_NAMES = {"The", "This", "That", "Monday", "Tuesday", "Wednesday", "Thursday",
              "Friday", "Saturday", "Sunday", "Tomorrow", "Today", "Italian"}


def _rule_extract(text: str) -> Extraction:
    """Deterministic fallback used offline and in tests."""
    people = [n for n in _NAME_RE.findall(text) if n not in _NOT_NAMES]
    m = _COMMIT_RE.search(text)
    commitment = m.group(1).strip() if m else None
    commitment_to = None
    if commitment:
        for p in people:
            if re.search(rf"\b{p}\b", commitment):
                commitment_to = p
                break
        if commitment_to is None and people:
            commitment_to = people[0]
    topics = []
    for kw in ("deck", "pitch deck", "invoice", "report", "dinner", "reservation",
               "meeting", "flight", "email", "document"):
        if kw in text.lower():
            topics.append(kw)
    return Extraction(people=people, places=[], topics=topics,
                      commitment=commitment, commitment_to=commitment_to)
