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
first, ranked importance-then-confidence-then-age x relevance, so a core
fact outranks a grocery mumble instead of weighing the same. Raw episodes are
never deleted; the profile is a lens, not a replacement.
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
    text TEXT NOT NULL,
    -- WHOSE MOUTH THIS CAME OUT OF: 'owner', 'other', or NULL for no verdict.
    -- The phone computes it per line and hear() already had it; until this
    -- column existed it was dropped one call before memory saw the words, so
    -- a guest's "I'll send you the deck" became an open commitment of the
    -- owner's and the clock could mint a browser job off it.
    -- NULL is not 'owner'. See _speaker_verdict and _ADDED_COLUMNS.
    speaker TEXT
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
    source TEXT NOT NULL DEFAULT 'consolidation',  -- consolidation | interview | import | supervised_mail
    provenance TEXT NOT NULL DEFAULT '[]',   -- JSON list of episode ids
    -- HOW LONG THIS STAYS TRUE, which is a different question from how much
    -- it matters: 'stable' | 'situation' | NULL for no verdict. Named by the
    -- model at distillation and only ever compared here — deciding it from
    -- the words at recall time is the pattern-match on meaning HARNESS-LAW 1
    -- forbids. See _HALF_LIFE_DAYS for what the ranker does with it.
    kind TEXT,
    -- WHEN THIS STOPPED BEING TRUE, and which row took its place. NULL means
    -- it is still true. The row is NEVER deleted: "the old facts aren't
    -- deleted — they're retired" (Brief moment 35), and a chain that can be
    -- walked backwards is the only way to answer "why did she stop believing
    -- that?". Deleting is the VETO's job (forget_fact) and means something
    -- else entirely: stop deriving this at all.
    --
    -- Written only after a MODEL says the two facts cannot both be true any
    -- more (SAME_FACT_SYSTEM's "replaces"). Reading a retirement out of the
    -- words at recall time — "broke up" retires "partner" — is the
    -- pattern-match on meaning HARNESS-LAW 1 forbids.
    retired_ts REAL,
    retired_by INTEGER,
    first_seen_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS consolidation_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- THE VETO. design/day-zero.md §3: "Every fact is vetoable. A tap deletes it
-- and marks it never-re-derive." Deleting the row alone is not a veto — the
-- next supervised read reads the same inbox and helpfully puts the same fact
-- back, so the tap would look broken to the one person it exists for.
--
-- This is the smallest honest store: it lives in the SAME per-owner SQLite as
-- the facts it vetoes (brain/supervisor.py:85-93, mode 0o700), so a veto is
-- deleted by the same account delete that deletes the fact and can never
-- outlive it. `CREATE TABLE IF NOT EXISTS` in SCHEMA runs on every Memory()
-- open, so existing owner databases gain it with no migration.
--
-- `fact` is kept verbatim for audit ("why did she stop knowing this?"), `norm`
-- is the token-normalised form the re-derivation check compares against.
CREATE TABLE IF NOT EXISTS vetoed_facts (
    id INTEGER PRIMARY KEY,
    fact TEXT NOT NULL,
    norm TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vetoed_norm ON vetoed_facts(norm);
"""

# COLUMNS ADDED AFTER OWNERS ALREADY HAD A memory.db ON DISK.
#
# `CREATE TABLE IF NOT EXISTS` reaches an old database with a new TABLE — that
# is how `vetoed_facts` shipped — and it can NEVER reach one with a new COLUMN,
# because the table already exists and the whole statement is skipped. A column
# declared only in SCHEMA therefore exists for new owners and for nobody else,
# and this store is one SQLite file per owner (brain/supervisor.py:93), so
# "nobody else" is every owner the product already has.
#
# `ALTER TABLE ... ADD COLUMN` is the only mechanism SQLite offers, and there
# was none in this repo before this list. It is meant to be re-run: every
# Memory() open replays it, and the second one raises "duplicate column name",
# which is the steady state rather than a failure.
#
# Each column is written down TWICE — in SCHEMA so a fresh database is created
# correct in one statement, and here so an existing one catches up. Two
# declarations of one column can drift; the shape-parity leg in
# tests/test_memory_knows_who_spoke.py compares PRAGMA table_info of a fresh
# database against a retrofitted one and is what notices when they do.
_ADDED_COLUMNS = (
    ("episodes", "speaker", "TEXT"),
    ("profile_facts", "kind", "TEXT"),
    ("profile_facts", "retired_ts", "REAL"),
    ("profile_facts", "retired_by", "INTEGER"),
)

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
Those three keys are REQUIRED and are the whole of the shape. There is one
OPTIONAL extra key, "kind":"stable"|"situation", explained at the bottom —
omit the key entirely unless you are sure, because a guess there is worse
than no answer.
A fact is something STABLE — true for weeks, worth knowing them by: who
matters to them ("partner is Sarah"), preferences ("prefers 7pm dinners"),
their work ("building Anticipy"), health, routines, ongoing situations
("mom is in hospital"). NOT one-off logistics, small talk, or anything that
is only a task. Write each fact as a short third-person note. importance is
1-5: 5 = core of their life (family, health, hard boundaries), 3 = a solid
preference or ongoing project, 1 = mildly useful color.
episode_ids lists the [id]s of the input lines the fact came from — only ids
you were given.
Nothing worth keeping -> {"facts":[]}.
THE OPTIONAL KEY. "kind" is HOW LONG a fact stays true, which is a different
question from how much it matters: "stable" for something that holds for
months or years until something changes it (an allergy, who their partner is,
what they do for a living), "situation" for a live state of affairs that will
end on its own ("mom is in hospital", "the Devon deal closes Friday"). OMIT
THE KEY unless the fact is clearly one of those two. A wrong "stable" is not
a small error: it means the fact never fades at all, so "the Devon deal
closes Friday" outranks fresher facts forever after the deal has closed.
Leaving it out is the safe answer and costs nothing."""

SAME_FACT_SYSTEM = """Two short notes about the same person, each with how long ago it was
last heard. Decide the RELATION between them. Exactly one of three:

"same" — they state the SAME underlying fact; one restates or updates a
  detail of the other. "partner is Sarah" / "his partner's name is Sarah".
"replaces" — they cannot both be true any more, and the newer one has taken
  the older one's place: a new person in the same role, a move, a breakup, a
  job change, a place that closed, an explicit renunciation ("never again").
  "partner is Dana" / "broke up with Dana".
"different" — genuinely different facts that can both be true at once.
  "prefers 7pm dinners" / "prefers Italian food".

Say "replaces" only when going on believing the OLDER note would make the
assistant wrong about this person today. Two facts that merely sit oddly
together are "different" — a wrongly retired fact is a thing she stops
knowing about him.
Reply ONLY with compact JSON, one of:
{"relation":"same"} {"relation":"replaces"} {"relation":"different"}"""

# THE TWO LANES A RETIRED FACT MAY TRAVEL, and they are not symmetric.
#
# docs/DECISIONS-2026-08-24.md RULING 2 settles Brief moment 35 ("they never
# surface in her voice again") against the §7 broadband entry (where "the
# superseded fact is the load-bearing one" — she has to name the old address
# because the broadband company's records still show it):
#
#   RETIREMENT GATES ACTION ABSOLUTELY, AND GATES SPEECH CONDITIONALLY.
#   A retired fact may never be an INPUT to action, nor an unqualified
#   assertion. It may be QUOTED as history — only with its retirement stated
#   in the same sentence.
#
# So the lane is a parameter of the READ, named at the sink, and the default
# is the strict one. `fill_gaps_from_memory` turns a recalled fact into a value
# the browser agent types into a real form; a sink added next month that
# forgets to think about this gets the lane that cannot spend money.
#
# In RETIRED_QUOTED the retirement is written INTO the fact's own text (see
# _retired_note), not hung off a sibling key. A sibling key is how
# briefing_facts once laundered `source` — it projected the key away and
# handed imported text to the prompt as established fact. A prompt-builder
# cannot drop what is inside the sentence it is rendering.
RETIRED_EXCLUDED = "excluded"
RETIRED_QUOTED = "quoted"

# Rule fallback so completion still works with no model available.
_DONE_RE = re.compile(
    r"\b(already|just)\s+(sent|paid|booked|called|emailed|texted|finished|did|"
    r"done|handled|submitted|filed|ordered)\b"
    r"|\b(sent|paid|booked|called|emailed|texted|finished|handled|submitted|"
    r"filed|ordered)\s+(it|that|them|him|her)\b"
    r"|\b(that'?s|it'?s|all)\s+(done|sorted|handled|taken care of)\b"
    r"|\bi\s+(sent|paid|booked|called|emailed|texted|finished|did|handled)\b",
    re.IGNORECASE)


# HOW MUCH OF A BOUNDED PROFILE WINDOW MAY BE THINGS NOBODY TYPED: one slot in
# three, and the rest is RESERVED for what the owner told us.
#
# Ranking here (see profile_facts) carries no provenance term at all, so age
# alone inverts authority: a supervised read is always the freshest thing in
# the store, and a fresh importance-4 mail fact out-scores the owner's own
# importance-5 interview answer once that answer is about 30 days old. The
# importance gate does not save it — the gate bounds what CONFIDENCE may do,
# and this inversion is age. Measured on this store: 2 interview rows aged
# 45 days plus 15 fresh supervised_mail rows made `profile_facts(limit=10)`
# return 10/10 supervised_mail, which made `Anticipy.briefing`'s `told` list
# EMPTY and handed BRIEFING_SYSTEM a profile section that was wholly
# `quoted_from_other_people`. No attacker: the client's own sanctioned ceiling
# is 15 facts per source (`extension/supervised_read.js` FACT_CEILING) and the
# briefing takes 10, so one honest read filled the window.
#
# A count cap on ingest cannot fix that — 15 legitimate facts are 15 legitimate
# facts. The WINDOW is what has to be split.
#
# Three, not two: the untrusted share has to be small enough that the profile
# block still reads as what she KNOWS about him (limit=10 -> 7 owner-told slots
# are held) and big enough that a read visibly contributes (3 slots, which is
# also what the briefing's 400-char fenced block comfortably holds).
_UNTRUSTED_WINDOW_DIVISOR = 3


# HOW FAST A FACT LOSES PROMINENCE, BY WHAT THE MODEL SAID IT IS.
#
# One uniform 30-day half-life ran backwards from what anyone intends.
# `last_seen_ts` refreshes on every restatement, so a live situation gets
# mentioned constantly and never decayed at all, while a stable fact stated
# once decayed to nothing. Measured: a 90-day-old importance-5 "allergic to
# shellfish" scored 0.625 against 3.909 for a 1-day-old importance-4 "mom is
# in hospital" — a 6x inversion, on the ranker that feeds the briefing and
# memory_notes, against the one fact in EXEMPLARS-A-LIFE that could hurt him.
#
# `stable` does not decay. Prominence for a fact that holds for years is its
# importance and how sure she is of it; the clock has nothing to say about it.
# When it stops being TRUE somebody says so and it is retired or vetoed —
# decay cannot express "no longer true", only "less prominent", and treating
# the two as one is what produced the inversion.
#
# `situation` keeps the 30 days it has always had, and so does an unlabelled
# row. Making situations decay FASTER would be inventing a number nobody has
# measured, and it would not fix the case it looks like it fixes: a situation
# that has resolved is stale rather than faint, and staleness is a
# supersession problem. Both are listed rather than one defaulting silently,
# so the ranker is reading the model's answer and not stepping around it.
_HALF_LIFE_DAYS = {"stable": None, "situation": 30.0}
_DEFAULT_HALF_LIFE_DAYS = 30.0

# The kinds this store keeps. Anything else the model says — a value it
# invented, a value from a prompt revision nobody here has seen — is NO
# VERDICT, for the same reason an unrecognised voice tag is.
_FACT_KINDS = ("stable", "situation")

# HOW MUCH CONFIDENCE MAY MOVE A FACT: within its importance tier, never out
# of it. EXEMPLARS-A-LIFE:465 — "Importance gates, confidence orders.
# Confidence-first ranking buries the shellfish allergy under the coffee
# order." A plain `x confidence` violates that sentence exactly as much as
# ignoring confidence did: importance 4 x 0.99 = 3.96 beats importance 5 x
# 0.60 = 3.00, which IS the allergy under the coffee order.
#
# So confidence enters compressed into [_CONFIDENCE_FLOOR, 1]. The floor is
# above 4/5 because that is the tightest adjacent-tier ratio importance can
# produce (5 -> 4), so at equal age the weakest belief at one tier still
# outranks the strongest belief below it. Age is deliberately NOT bounded this
# way: the doctrine sentence is about confidence, and a fact genuinely does
# fade.
_CONFIDENCE_FLOOR = 0.85

# WHERE A BELIEF SETTLES. EXEMPLARS-A-LIFE:467 — "Confidence saturates. Past
# ~0.95 a re-sighting refreshes last_seen and nothing else, or the profile
# becomes whatever he says most, not what matters most."
_CONFIDENCE_SETTLED = 0.95
_CONFIDENCE_CEILING = 0.99
# The old step was a flat +0.15, which reached the ceiling from the 0.6
# consolidation seed in THREE restatements. That made confidence a "seen more
# than twice" flag rather than a graded belief, and a tie-breaker that is
# constant for most facts is not a tie-breaker. A proportional step keeps
# saying something for eight or nine sightings and approaches the ceiling
# instead of slamming into it.
_CONFIDENCE_STEP = 0.25


def _confidence_band(confidence) -> float:
    """Confidence as a multiplier that reorders inside an importance tier and
    can never reach the tier above. See _CONFIDENCE_FLOOR."""
    try:
        c = min(1.0, max(0.0, float(confidence)))
    except (TypeError, ValueError):
        c = 0.0
    return _CONFIDENCE_FLOOR + (1.0 - _CONFIDENCE_FLOOR) * c


def _fact_kind(kind) -> Optional[str]:
    return kind if kind in _FACT_KINDS else None


def _days_ago(ts: float, now: float) -> int:
    """Whole days between two epoch seconds, never negative. Days rather than
    dates because the store keeps no timezone and the model is being asked
    which of two facts is the later one, not what the calendar said."""
    try:
        return max(0, int((float(now) - float(ts)) // 86400))
    except (TypeError, ValueError):
        return 0


def _retired_note(fact: str, retired_ts: float, now: float) -> str:
    """A retired fact, rendered so its retirement travels with it.

    RULING 2 permits a retired fact to be quoted "only with its retirement
    stated in the same sentence". This is that sentence, built once here so
    every speech sink states it identically and none of them can render the
    bare wording by accident — the failure mode is her telling him his partner
    is Sarah four months after he said they broke up.

    Days, not a date: the store keeps epoch seconds and has no timezone, and
    "retired 4 months ago" is what makes the reader treat it as history."""
    days = max(0, int((now - float(retired_ts or 0)) // 86400))
    when = "today" if days < 1 else (
        "yesterday" if days == 1 else f"{days} days ago")
    return f"no longer true — retired {when}: {fact}"


def _decay(kind, age_days: float) -> float:
    half_life = _HALF_LIFE_DAYS.get(_fact_kind(kind), _DEFAULT_HALF_LIFE_DAYS)
    if half_life is None:
        return 1.0
    return 0.5 ** (age_days / half_life)


def _provenance_window(facts: list[dict], limit: int) -> list[dict]:
    """Take at most `limit` of `facts` without letting untrusted volume evict
    what the owner told us — and without wasting a slot when one side is empty.

    `facts` arrives already ranked (salience, or salience x relevance) and the
    result keeps that order: this only decides what is DROPPED, never what
    comes first, because every caller reads element 0 as "most salient".

    The reserve is not a floor on owner-told rows. Unused reserve is handed
    back to the untrusted side, so a read into an otherwise empty store still
    contributes every fact it can fit — the point of a read is that it adds
    something, and a floor would silently turn day zero off."""
    if limit <= 0:
        return []
    # MEMBERSHIP, NOT THE LITERAL "import" — anticipy_core._UNTRUSTED_SOURCES is
    # the one definition of the fence and every consumer asks it. Imported here
    # rather than at module scope because anticipy_core imports this module.
    from .anticipy_core import _UNTRUSTED_SOURCES
    told, fenced = [], []
    for i, f in enumerate(facts):
        (fenced if str(f.get("source") or "") in _UNTRUSTED_SOURCES
         else told).append(i)
    keep_fenced = fenced[:limit // _UNTRUSTED_WINDOW_DIVISOR]
    keep_told = told[:limit - len(keep_fenced)]
    # Give back what the owner-told side could not use. Only ever positive when
    # the store holds fewer owner-told rows than the reserve, which is the
    # thin-profile and read-only cases — a full profile never triggers it.
    spare = limit - len(keep_told) - len(keep_fenced)
    if spare > 0:
        keep_fenced = fenced[:len(keep_fenced) + spare]
    keep = set(keep_told) | set(keep_fenced)
    return [f for i, f in enumerate(facts) if i in keep]


class Memory:
    def __init__(self, path: str | Path = ":memory:", llm=None):
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)
        self._retrofit_columns()
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

    def _retrofit_columns(self) -> None:
        """Bring an existing owner's database up to _ADDED_COLUMNS.

        The except is narrow on purpose. "duplicate column name" means the
        column is already there and there is nothing to do — the ordinary case
        on every open after the first. A locked, read-only or damaged file
        raises the same exception class, and swallowing THAT would leave the
        store permanently one column short while every later read of it failed
        somewhere far from here with no clue why. So the column is checked for
        afterwards, and an open that could not produce it fails loudly."""
        for table, column, decl in _ADDED_COLUMNS:
            try:
                self.db.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            except sqlite3.OperationalError:
                cols = {r[1] for r in self.db.execute(
                    f"PRAGMA table_info({table})").fetchall()}
                if column not in cols:
                    raise
        self.db.commit()

    # ------------------------------------------------------------- ingest

    def ingest(self, text: str, ts: Optional[float] = None,
               speaker: Optional[str] = None) -> dict:
        """`speaker` is the phone's LOCAL voice verdict for this line, in the
        roster's vocabulary: "owner", "other", or nothing at all. It is stored,
        never inferred — attribution is a fact about where a line came FROM,
        and reading it back out of the words would be the pattern-match on
        meaning HARNESS-LAW 1 forbids.

        The default is no verdict, and no verdict is a distinct third state
        that changes nothing. Live coverage of the voice roster is 0%, so a
        store that read "unattributed" as "not his" would refuse to prepare
        work off every line the product has ever heard."""
        ts = ts or time.time()
        speaker = _speaker_verdict(speaker)
        cur = self.db.execute(
            "INSERT INTO episodes(ts, text, speaker) VALUES (?, ?, ?)",
            (ts, text, speaker))
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
            # `speaker` rides in the SAME attrs blob as source_episode, so
            # attribution needs no nodes-table migration at all. It is the
            # promise's own record of whose mouth it came out of, which is
            # what open_loops() reports and the clock refuses to act on.
            commitment_id = self._upsert_node(
                "commitment", ex.commitment, ts, status="open",
                attrs={"source_episode": episode_id, "speaker": speaker})
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

    def recall(self, query: str, limit: int = 8,
               retired: str = RETIRED_EXCLUDED) -> list[dict]:
        """Relevance-then-time ordered chain of facts connected to the
        entities in `query`. Stopwords never seed matches — otherwise "the"
        matches every episode and recent noise buries the real answer.

        `retired` is RULING 2's lane, defaulting to the action-safe one: a
        caller that has not thought about retired facts does not get them.
        A speech sink that has (`_answer_from_memory`, triage context) asks
        for RETIRED_QUOTED by name, and what comes back says out loud that it
        is no longer true.

        Only the PROFILE layer has retirement. Episodes are raw hearing and
        are never retired — "he said they broke up" is a true record of a
        thing that was said, whenever it is read."""
        words = {w.strip(".,!?").lower() for w in query.split()
                 if len(w) > 2 and w.strip(".,!?").lower() not in self._STOP}
        # What she KNOWS about him answers before what she happened to
        # overhear: the distilled profile is consulted first, ranked
        # importance-then-confidence-then-age x relevance, and the raw search
        # fills whatever window is left (roadmap §1).
        profile = self._profile_recall(words, limit, retired)
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
        Callers that are about to INTERRUPT him should require a source.

        Each also carries two independent attributions, and neither is derived
        from the words:

          `speaker` — the phone's voice verdict on the line this promise came
            out of. Precise when it exists; it exists for almost nothing.
          `owes` — triage's own verdict on whose obligation the sentence
            expressed, written back by hear() after _decide(). Produced by a
            model with the whole conversation in front of it, on every line
            that reaches triage, which is why it is the one that fires today.

        Both are None for every promise recorded before this existed, and None
        means NO VERDICT — never "the owner's". A caller that reads a missing
        key as "somebody else's" retires every loop in every existing owner's
        database at once."""
        rows = self.db.execute(
            "SELECT id, name, created_ts, attrs FROM nodes "
            "WHERE type='commitment' AND status='open' ORDER BY created_ts"
        ).fetchall()
        out = []
        for r in rows:
            try:
                attrs = json.loads(r[3] or "{}") or {}
            except Exception:
                attrs = {}
            eid = attrs.get("source_episode")
            src = None
            if eid:
                ep = self.db.execute(
                    "SELECT text FROM episodes WHERE id=?", (eid,)).fetchone()
                src = ep[0] if ep else None
            out.append({"id": r[0], "what": r[1], "ts": r[2], "source": src,
                        "speaker": _speaker_verdict(attrs.get("speaker")),
                        "owes": attrs.get("owes") or None})
        return out

    def attribute_commitment(self, commitment_id: Optional[int],
                             owes: Optional[str]) -> None:
        """Record triage's verdict on whose obligation a promise is.

        ingest() runs BEFORE _decide(), so the commitment node exists before
        anybody has judged whose it is; this is hear() coming back to say. Same
        bug family as the dropped voice verdict and as 8849df15 — the answer
        was computed and thrown away one call before the place that needed it.

        A NON-VERDICT WRITES NOTHING AND ERASES NOTHING. `owes=None` used to
        POP the key, and that is what turned this method into the weapon that
        destroyed the fence it exists to hold. _upsert_node returns the SAME
        commitment node whenever the same sentence is extracted again, so the
        second hearing of one guest sentence — the guest repeating himself, or
        the worker restarting before mark_processed and re-polling the event —
        arrived here with the no-verdict `owes` that _decide() falls back to on
        a triage timeout, and unmarked a promise an earlier, better-informed
        pass had judged correctly. The clock then minted the browser job the
        mark exists to stop.

        So absence is treated the way `_speaker_verdict` and `_fact_kind` treat
        it, and for the same reason: an answer nobody gave is not an answer.
        Reversal is not lost by this — owner_is_party() reverses triage's
        over-eager "somebody else took this on" (wrong six for six on a dinner
        the owner had plainly agreed to) BEFORE hear() ever writes the mark, so
        a withdrawn verdict never reaches the store to need erasing. There is
        deliberately no erase path at all: a correction that genuinely has to
        remove a stored verdict should arrive as its own named method with its
        own recorded reason, not as a falsy argument to this one."""
        if not commitment_id or not owes:
            return
        row = self.db.execute(
            "SELECT attrs FROM nodes WHERE id=? AND type='commitment'",
            (commitment_id,)).fetchone()
        if not row:
            return
        try:
            attrs = json.loads(row[0] or "{}") or {}
        except Exception:
            attrs = {}
        attrs["owes"] = str(owes)
        self.db.execute("UPDATE nodes SET attrs=? WHERE id=?",
                        (json.dumps(attrs), commitment_id))
        self.db.commit()

    def resolve(self, commitment_id: int, status: str = "done"):
        self.db.execute("UPDATE nodes SET status=? WHERE id=?", (status, commitment_id))
        self.db.commit()

    def briefing_facts(self, since_ts: float) -> dict:
        """Raw material for the assistant's 'I overheard…' briefing.

        The profile leads: what she KNOWS about him (distilled, ranked by
        importance, then belief, then age) comes before the raw lines she
        happened to hear, so a briefing is grounded in who he is, not just
        today's noise. `heard` keeps its exact old shape; `open_loops` gained
        `speaker` and `owes`, and BRIEFING_SYSTEM is told what they mean —
        telling the owner he promised something a guest promised is the same
        lie one layer up from the clock preparing work off it."""
        heard = self.db.execute(
            "SELECT text FROM episodes WHERE ts>=? ORDER BY ts", (since_ts,)
        ).fetchall()
        # `source` is carried so the briefing prompt can tell what the owner
        # told us from what was imported off a calendar somebody else wrote.
        # Projecting it away here silently laundered attacker-controlled text
        # into a block BRIEFING_SYSTEM reads as established fact.
        #
        # SPEECH LANE (RULING 2). A retired fact may be quoted as history, and
        # the briefing is where the §7 answer comes from — "you moved to Rowan
        # Ave in June; the account probably still shows 4 Maple St" needs the
        # dead address to exist. It arrives with "no longer true — retired N
        # days ago" already inside `fact`, and it sorts below every live fact,
        # so it can never lead the greeting or evict a live row from the ten.
        profile = [{"fact": f["fact"], "importance": f["importance"],
                    "source": f.get("source", "")}
                   for f in self.profile_facts(limit=10,
                                               retired=RETIRED_QUOTED)]
        return {"profile": profile,
                "heard": [h[0] for h in heard],
                "open_loops": self.open_loops()}

    # ------------------------------------------------- profile / consolidation

    def remember_fact(self, text: str, importance: int = 4,
                      source: str = "interview", confidence: float = 0.9,
                      ts: Optional[float] = None,
                      kind: Optional[str] = None) -> int:
        """Seed the profile directly — the day-zero interview (roadmap §8)
        writes what he tells her here, so she is not amnesiac on install.
        Merges into an existing row when it already states the same fact
        (re-posting an interview answer must not dupe). Returns the row id,
        or 0 when the fact is under veto and therefore nothing was written."""
        text = (text or "").strip()
        if not text:
            raise ValueError("remember_fact needs actual text")
        ts = ts or time.time()
        importance = max(1, min(5, int(importance)))
        if source == "interview":
            # THE OWNER'S OWN THUMBS LIFT THEIR OWN VETO.
            #
            # The veto means "stop DERIVING this", not "stop listening to me".
            # Their tap set it; them typing the fact again is them changing
            # their mind, and a stale veto silently swallowing their own words
            # would be the same class of bug as the tap not working — she looks
            # like she ignored them. Nothing else lifts it: a second supervised
            # read and a consolidation pass are exactly the re-derivations the
            # veto exists to stop.
            self._lift_veto(text)
        match, relation = self._relate_fact(text, ts)
        changed = self._last_match_changed_detail
        if match is not None and relation == "same":
            self._merge_fact(match, importance, ts, [],
                             new_text=text if changed else None, source=source)
            self.db.commit()
            return match
        if match is not None and relation == "replaces":
            # The day-zero interview corrects a fact ("no — my manager is Tom
            # now"), and a correction the store files as a second coexisting
            # row is the whole complaint. `kind` stays whatever the caller
            # gave, which for this path is nobody's verdict.
            fid = self._supersede(match, text, importance, confidence, source,
                                  ts, [], kind=kind)
            self.db.commit()
            return fid
        # `kind` defaults to no verdict and every ordinary caller leaves it
        # there. The day-zero interview and the supervised read both land
        # here, and nothing runs a model over "how long does this stay true"
        # on either path — so a label would be this code's guess wearing the
        # model's authority. It is a parameter at all so the consolidation
        # path and the tests can state a verdict that was actually made.
        fid = self._insert_fact(text, importance, confidence, source, ts, [],
                                kind=kind)
        self.db.commit()
        return fid

    def forget_fact(self, text: str, source: str = "") -> int:
        """THE VETO, server half. design/day-zero.md §3: "Every fact is
        vetoable. A tap deletes it and marks it never-re-derive."

        Two halves, and the second is the one that makes the tap mean
        anything: delete every profile row that states this fact, AND record
        the veto. Deleting alone is cosmetic — the next supervised read opens
        the same inbox, distils the same subject line, and the fact is back
        within one refresh, which reads as "she ignored me" to the one person
        the gesture exists for.

        Returns how many rows were deleted. Zero is a normal answer, not a
        failure: the app can veto a line it is showing before the worker has
        ingested the event that would have created the row, and the veto still
        has to stick.
        """
        text = (text or "").strip()
        if not text:
            return 0
        norm = " ".join(_fact_tokens(text))
        removed = 0
        # A VETO MAY ONLY DELETE WHAT THE SAME KIND OF SOURCE WROTE.
        #
        # This deleted every row `_same_as` matched, source-blind, and the text
        # driving it is a stranger's. `_same_as` is deliberately loose - a 0.8
        # Jaccard over `_compare_words`, which reduces "They asked me never to
        # touch: anything to do with my bank." to {anything, asked, bank, never,
        # touch} - so a mailed line distilling to "Never touch anything to do
        # with their bank, they asked." matches it.
        #
        # The whole exploit was then the DESIGNED gesture: the odd-looking card
        # is shown, the owner taps it to get rid of it (`design/day-zero.md`
        # §3), and the row that dies is their own importance-5 interview
        # boundary - the one `Interview.swift:70-75` calls the fact that must
        # never be the one that fell off the end. `vetoed_facts` then blocks
        # re-insertion for good and the app never re-asks, so one email plus one
        # expected tap removed it permanently and silently.
        #
        # Exact-token equality is still allowed across provenance, so the owner
        # vetoing their OWN words verbatim keeps working. Loose matching belongs
        # in the never-re-derive check below, which is a refusal to write - not
        # here, where it is a DELETE.
        from .anticipy_core import _UNTRUSTED_SOURCES
        untrusted_veto = str(source or "") in _UNTRUSTED_SOURCES
        for rid, fact, src in self.db.execute(
                "SELECT id, fact, source FROM profile_facts").fetchall():
            row_untrusted = str(src or "") in _UNTRUSTED_SOURCES
            if untrusted_veto and not row_untrusted \
                    and " ".join(_fact_tokens(fact)) != norm:
                continue
            if self._same_as(text, fact):
                self.db.execute("DELETE FROM profile_facts WHERE id=?", (rid,))
                removed += 1
        if not self.db.execute("SELECT 1 FROM vetoed_facts WHERE norm=?",
                               (norm,)).fetchone():
            self.db.execute(
                "INSERT INTO vetoed_facts(fact, norm, ts) VALUES (?,?,?)",
                (text, norm, time.time()))
        self.db.commit()
        return removed

    def _same_as(self, a: str, b: str) -> bool:
        """Do two strings state the same fact? This is the DETERMINISTIC tier
        of _relate_fact, factored out because the veto needs exactly this
        notion of sameness and must hold with no model available: a veto that
        only catches character-identical text is defeated by a reword on the
        second read, which is the whole failure it exists to prevent.

        Numbers are NOT decisive here, deliberately unlike _relate_fact.
        There a changed number is an UPDATE worth keeping ("dinner at 6" ->
        "at 8", see the comment at _relate_fact). Here it is the vetoed
        fact wearing one new detail ("a proposal is in flight" -> "a $40k
        proposal is in flight") and the owner said not to keep it. Blocking a
        bit too much of what they asked her to forget is the safe direction;
        letting it back is the bug the tap gets reported for.
        """
        if " ".join(_fact_tokens(a)) == " ".join(_fact_tokens(b)):
            return True
        wa, wb = self._compare_words(a), self._compare_words(b)
        if not wa or not wb:
            return False
        # Compared on the SUBJECT — the same reason _relate_fact compares
        # subjects when numbers differ: counting the differing numbers pushes
        # the score down by exactly the thing being tested for.
        sa = {w for w in wa if not w.isdigit()}
        sb = {w for w in wb if not w.isdigit()}
        if sa and sb and len(sa & sb) / len(sa | sb) >= 0.8:
            return True
        return len(wa & wb) / len(wa | wb) >= 0.8

    def _is_vetoed(self, text: str) -> bool:
        """Has the owner told her never to re-derive this? Asked at the two
        lowest writers rather than at the public seam, so a caller that
        reaches _insert_fact or _merge_fact directly — consolidate() does —
        cannot route around it."""
        text = (text or "").strip()
        if not text:
            return False
        if self.db.execute("SELECT 1 FROM vetoed_facts WHERE norm=?",
                           (" ".join(_fact_tokens(text)),)).fetchone():
            return True
        for (fact,) in self.db.execute(
                "SELECT fact FROM vetoed_facts").fetchall():
            if self._same_as(text, fact):
                return True
        return False

    def _lift_veto(self, text: str) -> None:
        for rid, fact in self.db.execute(
                "SELECT id, fact FROM vetoed_facts").fetchall():
            if self._same_as(text, fact):
                self.db.execute("DELETE FROM vetoed_facts WHERE id=?", (rid,))

    def profile_facts(self, limit: Optional[int] = None,
                      retired: str = RETIRED_EXCLUDED) -> list[dict]:
        """The distilled profile, most important first.

        `retired` is the lane (see RETIRED_EXCLUDED / RETIRED_QUOTED). The
        default drops retired rows entirely, and because `_profile_recall`,
        `recall`, `briefing_facts` and every gap-filler read the profile
        THROUGH this one method, that default is what makes RULING 2's action
        half hold at one chokepoint instead of at four sinks forever.

        Salience is importance GATED, confidence ORDERING inside the gate,
        and age last — EXEMPLARS-A-LIFE:465, implemented rather than
        paraphrased. importance sets the tier; `_confidence_band` reorders
        within it and provably cannot reach the tier above; `_decay` fades a
        fact at the half-life the model gave its KIND, and a fact called
        stable does not fade at all.

        What this replaced was `importance * 0.5 ** (age_days / 30)`:
        confidence was projected one line up and read by nothing anywhere in
        brain/, and one uniform half-life buried a 90-day-old importance-5
        allergy under a 1-day-old importance-4 situation by 6x.

        A BOUNDED window is split by provenance (`_provenance_window`), not
        simply taken off the top: salience carries no provenance term, so
        without the split fifteen fresh read-derived rows evict every one of
        the owner's own older answers. Unlimited callers get the whole store
        in pure salience order, unchanged — there is no window to protect."""
        now = time.time()
        out = []
        # The filter is in the WHERE clause, not a list comprehension after
        # the fact: a bounded window is taken off this list, so a retired row
        # that reached Python at all would still be occupying a slot the owner
        # paid for even once it was dropped.
        where = ("" if retired == RETIRED_QUOTED
                 else " WHERE retired_ts IS NULL")
        for r in self.db.execute(
            "SELECT id, fact, importance, confidence, source, provenance, "
            "first_seen_ts, last_seen_ts, kind, retired_ts, retired_by "
            f"FROM profile_facts{where}"
        ):
            try:
                prov = json.loads(r[5] or "[]")
            except Exception:
                prov = []
            age_days = max(0.0, (now - r[7]) / 86400.0)
            kind = _fact_kind(r[8])
            retired_ts = r[9]
            out.append({
                "id": r[0],
                "fact": (r[1] if retired_ts is None
                         else _retired_note(r[1], retired_ts, now)),
                "importance": r[2],
                "confidence": r[3], "source": r[4], "provenance": prov,
                "first_seen_ts": r[6], "last_seen_ts": r[7], "kind": kind,
                "retired_ts": retired_ts, "retired_by": r[10],
                "salience": (r[2] * _confidence_band(r[3])
                             * _decay(kind, age_days)),
            })
        # A RETIRED FACT NEVER LEADS, whatever it scores. This is the measured
        # bug: "partner is Dana" (importance 5) sat at salience 4.70 against
        # 2.76 for "broke up with Dana", so the dead fact was the FIRST thing
        # recall handed to every prompt. Dropping it in the action lane is not
        # enough — in the quoted lane it would still evict a live fact from a
        # bounded window, and a four-slot triage window is where that hurts.
        # Ordering by liveness first is structure (is this row still true?),
        # not a reading of what either sentence means.
        #
        # Age then breaks the tie rather than entering the score. A fact the
        # model called stable does not decay, so two of them at one importance
        # and one confidence score EXACTLY equal — where the old expression
        # separated everything by microseconds of last_seen. Without this the
        # order of the profile would fall to whatever order SQLite returned
        # rows in, which is not an answer to anything.
        out.sort(key=lambda f: (f["retired_ts"] is not None,
                                -f["salience"], -f["last_seen_ts"]))
        return _provenance_window(out, limit) if limit else out

    def consolidate(self, now: Optional[float] = None, batch: int = 200) -> dict:
        """One incremental consolidation pass: read episodes newer than the
        last consolidated id, have the model distill stable facts, merge or
        insert them, then advance the cursor — all in ONE transaction, so a
        crash mid-pass loses nothing and the same episodes are simply read
        again next time. With llm=None the pass is skipped entirely: the
        profile just stays empty, nothing crashes.

        Returns counters: {"ran", "episodes", "new", "merged", "retired",
        "remaining"}. ran=False means nothing was written OR advanced (no
        model, no LIVE model, or the model's output was unusable). `retired`
        counts facts this pass RETIRED — a profile that corrects itself rather
        than only growing — and it is a distinct number because "she still
        thinks Sarah is his partner" and "she never learned anything" are
        different failures with the same look from the outside.

        THE LIVENESS CHECK BELONGS HERE, not only at the one call site. The
        only thing standing between this method and a dead model was
        `Memory(path=mem_db, llm=llm if llm.live else None)` three thousand
        lines into worker.py, and nothing anywhere asserted it. That matters
        more than it looks: this is the sole writer of `kind`, so it is the
        precondition for the whole decay half of the ranker — the half that
        fixes the measured 6x shellfish inversion. If it never runs, that fix
        is inert and nothing goes red; if it runs against a model that is not
        live, every night burns a pass on a call that cannot answer. `live` is
        read defensively (absent -> assumed live) so any stand-in that does not
        model the flag behaves exactly as it always has."""
        if not self.llm:
            return {"ran": False, "reason": "no llm", "episodes": 0,
                    "new": 0, "merged": 0, "retired": 0, "remaining": 0}
        if not getattr(self.llm, "live", True):
            return {"ran": False, "reason": "llm is not live", "episodes": 0,
                    "new": 0, "merged": 0, "retired": 0, "remaining": 0}
        now = now or time.time()
        last = int(self._state_get("last_episode_id", "0") or 0)
        rows = self.db.execute(
            "SELECT id, ts, text FROM episodes WHERE id>? ORDER BY id LIMIT ?",
            (last, batch)).fetchall()
        if not rows:
            self._state_set("last_run_ts", str(now))
            self.db.commit()
            return {"ran": True, "episodes": 0, "new": 0, "merged": 0,
                    "retired": 0, "remaining": 0}
        try:
            listing = "\n".join(f"[{r[0]}] {r[2]}" for r in rows)
            res = self.llm.chat(CONSOLIDATE_SYSTEM, listing)
            cands = json.loads(_extract_json(res.text)).get("facts")
            if not isinstance(cands, list):
                raise ValueError("no facts list in model output")
        except Exception as e:
            # Nothing advanced: these episodes stay unconsolidated and the
            # next pass re-reads them. A flaky model must not eat a day.
            #
            # BUT ONE POISONOUS BATCH MUST NOT EAT EVERY DAY AFTER IT. The
            # cursor only moves on success, so a batch the model can never
            # parse was re-read every night forever and NOTHING recorded
            # after it was ever consolidated again — the profile silently
            # stopped learning, with one print line as the only sign.
            # After three consecutive failures on the SAME cursor the batch
            # is stepped over: losing 200 episodes' facts is bad, losing
            # every episode after them permanently is unrecoverable.
            key = f"consolidate_fail_{last}"
            try:
                strikes = int(self._state_get(key) or 0) + 1
            except Exception:
                strikes = 1
            self._state_set(key, str(strikes))
            if strikes >= 3:
                skipped = rows[-1][0]
                self._state_set("last_episode_id", str(skipped))
                self._state_set(key, "0")
                self.db.commit()
                print(f"consolidation: SKIPPING episodes {last+1}-{skipped} "
                      f"after 3 unusable model replies ({e}) — the profile "
                      f"would otherwise never advance past them")
                return {"ran": True, "episodes": 0, "new": 0, "merged": 0,
                        "retired": 0, "skipped_batch": [last + 1, skipped],
                        "remaining": self._episodes_after(skipped)}
            self.db.commit()
            return {"ran": False, "reason": f"model output unusable: {e}",
                    "strikes": strikes,
                    "episodes": 0, "new": 0, "merged": 0, "retired": 0,
                    "remaining": self._episodes_after(last)}
        valid = {r[0]: r[1] for r in rows}  # id -> ts
        new = merged = retired = 0
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
                # Only the two the store knows. A value the model invented is
                # no verdict, not a new half-life.
                kind = _fact_kind(c.get("kind"))
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
                match, relation = self._relate_fact(text, fact_ts)
                changed = self._last_match_changed_detail
                if match is not None and relation == "same":
                    self._merge_fact(match, imp, fact_ts, eps,
                                     new_text=text if changed else None,
                                     source="consolidation", kind=kind)
                    merged += 1
                elif match is not None and relation == "replaces":
                    # Counted separately, and counted only when a row landed:
                    # `retired` is the number that says the profile is
                    # CORRECTING itself rather than only growing, and the
                    # nightly print is the one place anybody would notice
                    # supersession quietly stopping.
                    if self._supersede(match, text, imp, 0.6, "consolidation",
                                       fact_ts, eps, kind=kind):
                        new += 1
                        retired += 1
                else:
                    # Counted only if a row actually landed. _insert_fact
                    # returns 0 for a vetoed fact, and a pass that reports
                    # writing facts it refused would make the veto invisible
                    # in the one number anybody watches.
                    if self._insert_fact(text, imp, 0.6, "consolidation",
                                         fact_ts, eps, kind=kind):
                        new += 1
            self._state_set("last_episode_id", str(rows[-1][0]))
            self._state_set("last_run_ts", str(now))
            self._state_set(f"consolidate_fail_{last}", "0")
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {"ran": True, "episodes": len(rows), "new": new,
                "merged": merged, "retired": retired,
                "remaining": self._episodes_after(rows[-1][0])}

    def last_consolidation_ts(self) -> float:
        try:
            return float(self._state_get("last_run_ts", "0") or 0)
        except ValueError:
            return 0.0

    def _episodes_after(self, episode_id: int) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM episodes WHERE id>?", (episode_id,)
        ).fetchone()[0]

    def _profile_recall(self, words: set[str], limit: int,
                        retired: str = RETIRED_EXCLUDED) -> list[dict]:
        """Profile facts matching the query, ranked by profile_facts'
        salience x relevance — so a core fact beats a grocery mumble even
        when the mumble is newer and matches more words.

        The `limit` slots are split by provenance for the same reason
        `profile_facts` splits them: relevance x salience carries no
        provenance term either, so fifteen fresh read-derived rows that all
        mention "Devon" would take every slot and the owner's own boundary
        would never reach `memory_notes`."""
        if not words:
            return []

        def line(f: dict, salience: float) -> dict:
            # "known:" is a claim, so a retired fact does not get it: its text
            # already opens "no longer true — retired N days ago" and prefixing
            # that with "known" would hand the prompt both readings at once.
            # Built in ONE place because the matched and padded branches below
            # both produce these rows, and two spellings of the same sentence
            # is how a fact reaches a prompt unmarked.
            dead = f.get("retired_ts") is not None
            return {
                "fact": f["fact"] if dead else f'known: {f["fact"]}',
                "src_type": "profile", "dst_type": "profile",
                "ts": f["last_seen_ts"], "quote": None,
                "importance": f["importance"],
                "salience": salience,
                "retired_ts": f.get("retired_ts"),
                # Carried so the caller can tell what the OWNER told us from
                # what was IMPORTED off a calendar invite somebody else wrote.
                # Without it every fact reaches the prompt with equal
                # authority, and a meeting title is attacker-controlled text.
                "source": f.get("source", ""),
            }

        out = []
        for f in self.profile_facts(retired=retired):
            blob = f["fact"].lower()
            rel = sum(1 for w in words if w in blob)
            if not rel:
                continue
            out.append(line(f, f["salience"] * rel))
        # Same tiebreak as profile_facts, and retired-last for the same reason:
        # a bounded window must not spend a slot on a dead fact while a live
        # one is waiting.
        out.sort(key=lambda f: (f["retired_ts"] is not None,
                                -f["salience"], -f["ts"]))
        if len(out) < limit:
            # Wording is the model's, not the owner's — "go-to restaurant"
            # answers "usual dinner spot" yet shares no word with it. The
            # most important known facts ride along so a paraphrased
            # question still reaches what she actually knows.
            have = {f["fact"] for f in out}
            # LIVE FIRST, then OWNER-TOLD, then importance. Retirement leads
            # the key for the same reason it leads profile_facts': this branch
            # pads the window with facts that matched NOTHING in the query, so
            # without it a retired importance-5 row would be padded in ahead of
            # a live importance-3 one — the measured bug, rebuilt inside the
            # block that exists to help paraphrased questions.
            #
            # Then owner-told: the key was -importance alone, and read facts
            # are capped at importance 4 while a consolidated fact is often 3 —
            # so the padding preferred a stranger's mail, the window below then
            # capped it, and recall came back SHORT with owner-told rows
            # sitting unused in the store.
            from .anticipy_core import _UNTRUSTED_SOURCES
            rest = sorted((f for f in self.profile_facts(retired=retired)
                           if line(f, 0.0)["fact"] not in have),
                          key=lambda f: (
                              f.get("retired_ts") is not None,
                              str(f.get("source") or "") in _UNTRUSTED_SOURCES,
                              -f["importance"]))
            for f in rest[:limit - len(out)]:
                out.append(line(f, 0.0))
        # A RETIRED FACT NEVER LEADS — asserted on the FINAL list, because the
        # padding branch above appends and would otherwise undo it. Measured
        # while writing this: recall("who is my partner") put "no longer true —
        # retired yesterday: partner is Dana" FIRST, ahead of the live fact
        # that replaced it, because the dead row matched the query on the word
        # "partner" and the live one matched nothing and was padded in behind.
        # Stable, so order within each class is exactly what the two branches
        # decided; it only moves dead facts behind live ones. Before
        # _provenance_window, so a dead fact is also the first thing dropped
        # when the window is short.
        out.sort(key=lambda f: f["retired_ts"] is not None)
        return _provenance_window(out, limit)

    # Set by _relate_fact when the row it matched states the SAME fact
    # with a DIFFERENT number — the caller must rewrite the wording rather
    # than keep the stale one.
    _last_match_changed_detail = False

    def _compare_words(self, text: str) -> set:
        """Words that decide whether two facts are the same one.

        Short tokens are dropped as noise EXCEPT numbers: "6" and "8" carry
        the whole meaning of a time, and dropping them made two different
        dinners look like one.
        """
        return {w for w in _fact_tokens(text)
                if (len(w) > 2 or w.isdigit()) and w not in self._STOP}

    def _relate_fact(self, text: str,
                     ts: Optional[float] = None) -> tuple:
        """How this fact stands to what is already stored: (row_id, relation)
        where relation is "same", "replaces" or "different".

        THE RELATION IS THE MODEL'S ANSWER, NOT THIS FUNCTION'S. Deciding that
        "broke up with Dana" retires "partner is Dana" is a judgement about
        what two sentences MEAN, and HARNESS-LAW 1 puts that with a model that
        has both of them in front of it. What runs here is a candidate sift in
        FRONT of the model (which pairs are even worth a question), the
        deterministic same-wording tiers that already shipped, and nothing
        else. No verb list, no threshold, decides that a fact is dead.

        THE SIFT HAD TO WIDEN, and this is the measured reason. It used to
        offer the model only pairs scoring 0.40-0.80 on word overlap.
        "partner is Dana" and "broke up with Dana" reduce to {partner, dana}
        and {broke, dana} — overlap 0.33 — so the one pair the whole feature
        exists for scored BELOW the band and was never asked about. A cheap
        sift that silently excludes the case is not a sift, it is the
        decision. Now any shared compare-word makes a pair a candidate and the
        model is asked about the three closest; the call budget is unchanged
        (it was already capped at three), the band is not.

        `ts` is the evidence date of the incoming fact and is used for exactly
        one thing: see the retired-row guard below.
        """
        self._last_match_changed_detail = False
        norm = " ".join(_fact_tokens(text))
        cand_words = self._compare_words(text)
        cand_nums = _fact_numbers(text)
        near = []
        for rid, fact, retired_ts in self.db.execute(
                "SELECT id, fact, retired_ts FROM profile_facts").fetchall():
            # A DEAD ROW STOPS BEING A TARGET ONCE SOMETHING NEWER THAN ITS
            # RETIREMENT SAYS THE SAME THING AGAIN.
            #
            # Without this, "actually, we're back together" merges into the
            # RETIRED "partner is Dana" row: evidence accrues on a corpse,
            # status is untouched by _merge_fact, the active occupant is never
            # judged against it, and the owner's correction changes nothing she
            # says — this card's own bug rebuilt one level down. Skipping the
            # row lets the loop reach the live occupant, which is what the
            # model should be judging the restatement against.
            #
            # The other direction is deliberately NOT skipped: evidence OLDER
            # than the retirement is a crash-replayed consolidation batch
            # (consolidate's cursor does not advance on a model failure, so
            # episodes are re-read) re-deriving a fact that has since died. It
            # merges into the retired row and stays retired, which records the
            # re-derivation without resurrecting it.
            if retired_ts is not None and ts is not None and ts > retired_ts:
                continue
            fnorm = " ".join(_fact_tokens(fact))
            if fnorm == norm:
                return rid, "same"
            fwords = self._compare_words(fact)
            if not cand_words or not fwords:
                continue
            overlap = len(cand_words & fwords) / len(cand_words | fwords)
            # SAME WORDS, DIFFERENT NUMBER, IS NOT THE SAME FACT.
            #
            # The word filter dropped anything of two characters or fewer, so
            # "dinner with Sarah at 6" and "dinner with Sarah at 8" compared
            # as IDENTICAL — overlap 1.00 — and merged. _merge_fact keeps the
            # original wording on purpose, so the 8 was thrown away and the
            # profile still said 6. The one detail most worth updating was
            # the one kind guaranteed to be lost, and nothing reported it.
            #
            # A changed number is the update, not noise: it is reported so the
            # caller can rewrite the wording instead of silently keeping the
            # stale one.
            if _fact_numbers(fact) != cand_nums:
                # Compare the SUBJECT only. Counting the differing numbers
                # here would push the score down by exactly the thing being
                # tested for — "dinner with Sarah at 6" vs "at 8" scores 0.50
                # on the full set and would read as two unrelated facts,
                # which is the opposite error to the one being fixed.
                subj_a = {w for w in cand_words if not w.isdigit()}
                subj_b = {w for w in fwords if not w.isdigit()}
                if subj_a and subj_b and (
                        len(subj_a & subj_b) / len(subj_a | subj_b)) >= 0.8:
                    self._last_match_changed_detail = True
                    return rid, "same"
                # NOT `continue` any more, and this is load-bearing. Dropping
                # the pair here meant a differing number could never be judged
                # at all: "home is 44 Birch Lane" / "home is 18 Rowan Ave" and
                # "standup is at 9" / "standup moved to 10" are the shape a
                # MOVE and a RESCHEDULE actually arrive in, and both were
                # falling out of candidacy on the strength of the digits.
                # What must still not happen is the >= 0.8 wording shortcut
                # below merging them and throwing the new number away, which is
                # why that branch is now an elif.
                pass
            elif overlap >= 0.8:
                return rid, "same"  # near-identical wording; no model needed
            # A RETIRED ROW IS NEVER PUT TO THE MODEL. The question the prompt
            # asks — which of these is true now — has no answer about a fact
            # that already stopped being true, and a "replaces" verdict against
            # a corpse would retire something twice. The deterministic tiers
            # above still see it, which is what keeps a replayed re-derivation
            # accruing on the dead row instead of coming back to life.
            if overlap > 0 and retired_ts is None:
                near.append((overlap, rid, fact))
        if self.llm and near:
            now = time.time()
            for _overlap, rid, fact in sorted(near, reverse=True)[:3]:
                try:
                    # AGES GO WITH THE FACTS. "partner is Dana" and "broke up
                    # with Dana" are the same two sentences whichever way round
                    # they were said; which one has taken the other's place is
                    # a question about WHEN, and asking it without the dates is
                    # asking the model to guess. `a` is what is stored, `b` is
                    # what just arrived.
                    seen = self.db.execute(
                        "SELECT last_seen_ts FROM profile_facts WHERE id=?",
                        (rid,)).fetchone()
                    res = self.llm.chat(SAME_FACT_SYSTEM, json.dumps({
                        "a": fact,
                        "a_last_heard_days_ago": _days_ago(
                            seen[0] if seen else now, now),
                        "b": text,
                        "b_last_heard_days_ago": _days_ago(ts or now, now),
                    }), aux=True)
                    relation = json.loads(
                        _extract_json(res.text)).get("relation")
                except Exception:
                    continue
                # An answer this store does not know — a value the model
                # invented, a reply in the old {"same":bool} shape from a
                # prompt revision nobody here has seen — is NO VERDICT, the
                # same contract _fact_kind and _speaker_verdict hold. No
                # verdict leaves the profile exactly as it was.
                if relation in ("same", "replaces"):
                    return rid, relation
        return None, "different"

    def _supersede(self, old_id: int, text: str, importance: int,
                   confidence: float, source: str, ts: float,
                   episode_ids: list[int],
                   kind: Optional[str] = None) -> int:
        """The model said these two cannot both be true. Land the new fact and
        retire the one it replaced. Returns the new row id, or 0 if nothing
        was written.

        NOTHING IS DELETED AND NOTHING IS REWRITTEN. The old row keeps its
        wording, its importance, its provenance and its episode ids, and gains
        only a date and a pointer — so "why did she stop believing that?" has
        an answer, and forget_fact stays the only thing in this store that
        destroys a fact.

        TWO DETERMINISTIC GUARDS. Both compare labels and timestamps, never
        words: the model has already said WHETHER one fact replaces the other,
        and these decide only whether this particular pair is allowed to act
        on that.
        """
        from .anticipy_core import _UNTRUSTED_SOURCES
        row = self.db.execute(
            "SELECT last_seen_ts, source FROM profile_facts WHERE id=?",
            (old_id,)).fetchone()
        if not row:
            return 0
        # GUARD 1 — THE PROVENANCE FENCE. A calendar invite or a mail subject
        # line is written by whoever sent it. Letting it retire something the
        # owner said out loud would make "delete his boundary" a thing a
        # stranger can do by sending him an email — the same exploit
        # forget_fact's veto fence and _merge_fact's launder guard already
        # close, arriving through a third door. The fact still lands; it just
        # does not get to kill anything. Untrusted retiring untrusted is fine,
        # and SPOKEN retiring imported is the intended direction (he moved,
        # and the calendar has not caught up).
        if (str(source or "") in _UNTRUSTED_SOURCES
                and str(row[1] or "") not in _UNTRUSTED_SOURCES):
            return self._insert_fact(text, importance, confidence, source, ts,
                                     episode_ids, kind=kind)
        new_id = self._insert_fact(text, importance, confidence, source, ts,
                                   episode_ids, kind=kind)
        # A VETOED FACT RETIRES NOTHING. _insert_fact returns 0 when the owner
        # has tapped this fact away, and retiring the old row anyway would turn
        # the veto into a silent deletion weapon: veto "partner is Maya", say
        # it once, and "partner is Dana" dies with nothing written in its
        # place. The owner would be left with neither fact and no gesture that
        # explains where they went.
        if not new_id:
            return 0
        # GUARD 2 — THE OLDER SIDE LOSES, WHICHEVER WAY IT ARRIVED. consolidate
        # does not advance its cursor when the model fails, so a batch is
        # re-read and a fact that has since been replaced can be re-derived
        # days later. Landing it active would resurrect a dead fact on a
        # timestamp nobody looked at. When the incoming evidence is the older
        # side it lands ALREADY retired, pointing at the row that outlived it.
        if ts >= row[0]:
            self.db.execute(
                "UPDATE profile_facts SET retired_ts=?, retired_by=? "
                "WHERE id=?", (ts, new_id, old_id))
        else:
            self.db.execute(
                "UPDATE profile_facts SET retired_ts=?, retired_by=? "
                "WHERE id=?", (row[0], old_id, new_id))
        return new_id

    def _insert_fact(self, text: str, importance: int, confidence: float,
                     source: str, ts: float, episode_ids: list[int],
                     kind: Optional[str] = None) -> int:
        """Returns the new row id, or 0 when the fact is under veto and no row
        was written. The check sits HERE, at the lowest writer, because
        consolidate() inserts without going through remember_fact — a gate at
        the public seam only would let the nightly pass quietly re-derive
        exactly what the owner tapped away."""
        if self._is_vetoed(text):
            return 0
        cur = self.db.execute(
            "INSERT INTO profile_facts(fact, importance, confidence, source, "
            "provenance, kind, first_seen_ts, last_seen_ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (text, importance, confidence, source,
             json.dumps(episode_ids or []), _fact_kind(kind), ts, ts))
        return cur.lastrowid

    def _merge_fact(self, fact_id: int, importance: int, ts: float,
                    episode_ids: list[int], new_text: Optional[str] = None,
                    source: str = "", kind: Optional[str] = None) -> None:
        """A restatement is evidence, not a new row: bump confidence, keep
        the higher importance, extend provenance, refresh last_seen. The
        original wording stays — churning the text on every restatement
        would make the profile impossible to audit.

        `source` is the provenance of the RESTATEMENT, and it only ever
        restricts the rewrite — see the two guards below. Both live here
        rather than in the callers because this is the one place a row's
        wording can change, and a rewrite is the only way text from one
        provenance can end up sitting in a row labelled with another."""
        row = self.db.execute(
            "SELECT importance, confidence, provenance, last_seen_ts, fact, "
            "source, kind FROM profile_facts WHERE id=?", (fact_id,)).fetchone()
        if not row:
            return
        # A ROW WITH NO STABILITY VERDICT CAN STILL GET ONE.
        #
        # Without this the column would be inert for everything that already
        # exists: every fact in every owner's database predates it, merges are
        # the common path for a fact that keeps coming up, and a row that never
        # gets re-INSERTED would never be labelled however many times the model
        # judged it. Filling a blank is not overwriting a verdict — an existing
        # label stands, the same instinct that keeps the original wording
        # through a merge, because churning either makes the profile
        # impossible to audit.
        if _fact_kind(kind) and not _fact_kind(row[6]):
            self.db.execute("UPDATE profile_facts SET kind=? WHERE id=?",
                            (_fact_kind(kind), fact_id))
        if new_text:
            # GUARD 1 — THE VETO SURVIVES A MERGE.
            #
            # Deleting the row and blocking the insert is not enough: a
            # near-match rewrite would write the vetoed wording INTO a
            # surviving neighbour, and the fact the owner tapped away is back
            # in the profile under a different row id. This is the "put the
            # marking where a later merge cannot miss it" case.
            #
            # GUARD 2 — UNTRUSTED TEXT MAY NOT BORROW THE OWNER'S VOICE.
            #
            # A merge keeps the row's existing `source`, so rewriting a row
            # sourced "interview" with text distilled off a mail read leaves
            # attacker-written words wearing the owner's provenance — after
            # which every consumer of _UNTRUSTED_SOURCES reads them as the
            # owner's own, and fill_gaps_from_memory may promote them into an
            # approved plan value. The rewrite is dropped and the owner's
            # wording stands; the restatement still counts as evidence
            # (confidence, last_seen), which is all an untrusted source has
            # standing to contribute.
            #
            # Imported locally: anticipy_core imports this module, so the
            # module-level import is a cycle. An ImportError propagates to
            # remember_fact's caller, leaving the row unchanged — fail closed.
            from .anticipy_core import _UNTRUSTED_SOURCES
            launders = (str(source or "") in _UNTRUSTED_SOURCES
                        and str(row[5] or "") not in _UNTRUSTED_SOURCES)
            if self._is_vetoed(new_text) or launders:
                new_text = None
        if new_text:
            # The fact moved (6pm -> 8pm). Keep the row, its provenance and
            # its history, but say the true thing: an audit trail that
            # preserves a wrong time is worse than no audit trail.
            self.db.execute("UPDATE profile_facts SET fact=? WHERE id=?",
                            (new_text, fact_id))
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
            (max(row[0], importance), _bumped(row[1]),
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

    def read_facts_admitted(self, job: str) -> int:
        """How many supervised-read facts this job has already had written.

        Lives in the STORE rather than in a worker dict because the ceiling it
        feeds (`worker.READ_FACTS_PER_JOB`) has to survive a restart: an
        in-process counter resets to zero on every redeploy, and a client that
        ignores its own cap can simply keep posting until one happens."""
        try:
            return int(self._state_get(f"read_facts_{job}", "0") or 0)
        except ValueError:
            # An unreadable counter is treated as "already at the ceiling"
            # nowhere — it is treated as zero, because refusing every fact
            # forever on a corrupt row would silently turn day zero off. The
            # ceiling is a flood guard, not a security boundary; the fence is.
            return 0

    def note_read_fact_admitted(self, job: str) -> int:
        """Count one admitted fact against `job`'s ceiling. Committed, because
        an uncommitted count is not a count across polls."""
        n = self.read_facts_admitted(job) + 1
        self._state_set(f"read_facts_{job}", str(n))
        self.db.commit()
        return n

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
                res = self.llm.chat(EXTRACT_SYSTEM, text, aux=True)
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
                    # ASKED FOR, DECLARED, CONSUMED — AND NEVER PASSED.
                    # EXTRACT_SYSTEM requests `completed`, the dataclass
                    # declares it and ingest() acts on it, but this branch
                    # built the object without it, so with a live model it
                    # was ALWAYS None. Closing a loop fell back entirely to
                    # the _DONE_RE verb list, and anything he finished in
                    # words that list does not contain stayed open forever.
                    completed=one("completed"),
                )
            except Exception as e:
                # A model returning garbage silently demoted memory to a
                # regex that finds capitalised words and "I'll ..." clauses.
                # Nothing anywhere reported the downgrade, so a degraded
                # brain looked exactly like a quiet day.
                print(f"memory: extraction model unusable, falling back to "
                      f"rules ({type(e).__name__}: {str(e)[:120]})")
        return _rule_extract(text)


def _bumped(confidence) -> float:
    """One more sighting of a fact she already believes.

    A flat +0.15 reached the 0.99 ceiling from the 0.6 consolidation seed in
    three restatements, which made confidence a "seen more than twice" flag
    rather than a graded belief — and now that the ranker READS it, a
    tie-breaker that is constant for most facts is not a tie-breaker.

    Above _CONFIDENCE_SETTLED nothing moves, which is EXEMPLARS-A-LIFE:467
    written out: "past ~0.95 a re-sighting refreshes last_seen and nothing
    else, or the profile becomes whatever he says most, not what matters
    most." The caller still refreshes last_seen either way.
    """
    try:
        c = float(confidence)
    except (TypeError, ValueError):
        c = 0.0
    if c >= _CONFIDENCE_SETTLED:
        return c
    return c + (_CONFIDENCE_CEILING - c) * _CONFIDENCE_STEP


def _speaker_verdict(speaker) -> Optional[str]:
    """The two values this store keeps about who spoke, and nothing else.

    "owner" and "other" are the roster's vocabulary. Everything else — None, a
    literal "unknown", a per-voice id like "other:v215", a value from a build
    nobody here has seen — is NO VERDICT and is stored as NULL.

    "other:v215" in particular is the roster failing to place a voice, not
    placing a different one: 200 tagged lines produced 195 distinct
    identities, 97% seen exactly once, and the owner recognised twice. Passing
    that through as evidence would hand the owner's own to-dos to a stranger,
    which is the failure hear() already normalises it away to avoid.
    """
    return speaker if speaker in ("owner", "other") else None


def _extract_json(text: str) -> str:
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start >= 0 <= end else "{}"


def _fact_tokens(text: str) -> list[str]:
    """Lowercase word tokens with possessives folded — "partner's" and
    "partner" must count as the same word or restatements never match."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return [w[:-2] if w.endswith("'s") else w for w in words]


def _fact_numbers(text: str) -> set:
    """Every number a fact states. Two facts that agree on every word but
    disagree on a number are not the same fact — they are the same fact
    updated, and the newer number is the point."""
    return set(re.findall(r"\d+(?:[.:]\d+)?", (text or "").lower()))


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
