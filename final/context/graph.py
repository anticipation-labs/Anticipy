"""final/context/graph.py — the temporal knowledge graph (Phase 4, Neo4j).

A focused, custom entity/relationship graph on the live Neo4j (AuraDB Free), behind
the ``ANTICIPY_GRAPH=neo4j`` flag. Default OFF → this module never touches the
network and the on-device learns-you behavior (context_eval 8/8) is byte-identical.

Why custom, not graphiti-core: graphiti pulls a heavy async LLM stack and its Gemini
path is finicky to verify in one night; the disambiguation + multi-hop we actually
need is a small, provable graph. Everything here is fail-safe — a missing key, an
unreachable database, or a Cypher error logs and no-ops, and every read returns an
empty result rather than raising into intake.

Model (bi-temporal edges)
--------------------------
Nodes:
  (:Owner   {scope})              — the wearer ("me"), one per scope.
  (:Entity  {name, scope, kind})  — a person / place / project / org / thing.

Edges  (A)-[:REL {predicate, ...}]->(B)  read as  "A's <predicate> is B":
  predicate     the relationship / role  ("lawyer", "accountant", "assistant", "employer")
  valid_from    VALID-TIME start   — when the fact became true in the world  (epoch)
  valid_to      VALID-TIME end     — when it stopped being true, else null
  ingested_at   TRANSACTION-TIME   — when WE recorded it  (epoch)
  invalid       bool               — superseded by a contradicting fact (soft-delete)
  statement     provenance text    — the sentence the wearer actually said

A contradicting fact for a *functional* predicate (one holder: accountant, employer)
does not overwrite history — it sets ``invalid=true`` + ``valid_to`` on the prior
edge, so "who was my accountant before Bob?" stays answerable. Two Sams (lawyer vs
brother) are DIFFERENT predicates, so both stay valid — the disambiguation is a real
graph traversal, not a string tie-break.

Composability is the point: "my accountant's assistant" is the 2-hop path
  (Owner)-[:REL {accountant}]->(Mia)-[:REL {assistant}]->(Jane).
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import List, Optional, Tuple

log = logging.getLogger("anticipy.context.graph")

# predicates with exactly one valid holder — a new object invalidates the prior edge.
# (Everything else, e.g. "friend", may have many; we never invalidate those.)
_FUNCTIONAL = {
    "accountant", "lawyer", "attorney", "dentist", "doctor", "landlord", "barber",
    "mechanic", "vet", "pharmacy", "manager", "boss", "employer", "assistant",
    "partner", "spouse", "wife", "husband", "realtor", "agent", "trainer",
}


def graph_enabled() -> bool:
    """The single flag gate. Default OFF → the whole layer is inert."""
    return os.environ.get("ANTICIPY_GRAPH", "").strip().lower() == "neo4j"


def _scope() -> str:
    return (os.environ.get("ANTICIPY_GRAPH_SCOPE", "") or "default").strip() or "default"


class GraphStore:
    """Thin, fail-safe wrapper over the Neo4j temporal graph.

    Construct once and reuse (it holds a pooled driver). Every method swallows its
    own errors: writes are best-effort, reads return empty on any failure. If the
    flag is off or the driver/creds are missing, ``ok`` is False and all ops no-op.
    """

    def __init__(self, scope: Optional[str] = None) -> None:
        self.scope = scope or _scope()
        self._driver = None
        self._db = os.environ.get("NEO4J_DATABASE") or None
        self._dead = False  # set after a hard connect failure so we stop retrying
        if graph_enabled():
            self._connect()

    # ---- lifecycle ---------------------------------------------------------------
    def _connect(self) -> None:
        if self._driver is not None or self._dead:
            return
        uri = os.environ.get("NEO4J_URI")
        user = os.environ.get("NEO4J_USERNAME")
        pw = os.environ.get("NEO4J_PASSWORD")
        if not (uri and user and pw):
            self._dead = True
            log.warning("ANTICIPY_GRAPH=neo4j but NEO4J_URI/USERNAME/PASSWORD missing; graph inert")
            return
        try:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(uri, auth=(user, pw))
            self._driver.verify_connectivity()
            self._ensure_constraints()
        except Exception as exc:  # unreachable / bad creds / driver missing
            self._driver = None
            self._dead = True
            log.warning("graph connect failed (%s); graph inert", str(exc)[:160])

    @property
    def ok(self) -> bool:
        return self._driver is not None

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            finally:
                self._driver = None

    def _run(self, cypher: str, **params):
        """Execute a query; return the list of records, or [] on any failure."""
        if self._driver is None:
            return []
        try:
            res = self._driver.execute_query(cypher, database_=self._db, **params)
            return list(res.records)
        except Exception as exc:
            log.warning("graph query failed (%s): %s", str(exc)[:140], cypher[:80])
            return []

    def _ensure_constraints(self) -> None:
        # uniqueness makes MERGE idempotent + fast; IF NOT EXISTS is safe to re-run.
        self._run(
            "CREATE CONSTRAINT anticipy_entity_uq IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE (e.scope, e.name) IS UNIQUE"
        )
        self._run(
            "CREATE CONSTRAINT anticipy_owner_uq IF NOT EXISTS "
            "FOR (o:Owner) REQUIRE o.scope IS UNIQUE"
        )

    # ---- normalization -----------------------------------------------------------
    @staticmethod
    def _norm(name: str) -> str:
        return re.sub(r"\s+", " ", (name or "").strip())

    @staticmethod
    def _pred(p: str) -> str:
        return re.sub(r"\s+", " ", (p or "").strip().lower())

    # ---- writes ------------------------------------------------------------------
    def upsert_entity(self, name: str, kind: str = "person") -> bool:
        name = self._norm(name)
        if not self.ok or not name:
            return False
        self._run(
            "MERGE (e:Entity {scope:$scope, name:$name}) "
            "ON CREATE SET e.kind=$kind, e.created_at=$now "
            "SET e.kind=coalesce(e.kind,$kind)",
            scope=self.scope, name=name, kind=kind, now=time.time(),
        )
        return True

    def add_owner_relation(self, predicate: str, obj: str, kind: str = "person",
                           statement: str = "", valid_from: Optional[float] = None) -> bool:
        """Record 'my <predicate> is <obj>' as (Owner)-[:REL {predicate}]->(obj)."""
        return self._add_edge(None, predicate, obj, obj_kind=kind,
                              statement=statement, valid_from=valid_from)

    def add_relation(self, subj: str, predicate: str, obj: str,
                     subj_kind: str = "person", obj_kind: str = "person",
                     statement: str = "", valid_from: Optional[float] = None) -> bool:
        """Record '<subj>'s <predicate> is <obj>' as (subj)-[:REL {predicate}]->(obj)."""
        return self._add_edge(subj, predicate, obj, subj_kind=subj_kind, obj_kind=obj_kind,
                              statement=statement, valid_from=valid_from)

    def _add_edge(self, subj: Optional[str], predicate: str, obj: str,
                  subj_kind: str = "person", obj_kind: str = "person",
                  statement: str = "", valid_from: Optional[float] = None) -> bool:
        pred = self._pred(predicate)
        obj = self._norm(obj)
        if not self.ok or not pred or not obj:
            return False
        now = time.time()
        vfrom = float(valid_from) if valid_from is not None else now

        # bi-temporal invalidation: for a functional predicate, any *other* currently-valid
        # holder is superseded — soft-delete it (keep history), never hard-delete.
        if pred in _FUNCTIONAL:
            if subj is None:
                self._run(
                    "MATCH (:Owner {scope:$scope})-[r:REL {predicate:$pred}]->(old:Entity) "
                    "WHERE coalesce(r.invalid,false)=false AND old.name<>$obj "
                    "SET r.invalid=true, r.valid_to=$now",
                    scope=self.scope, pred=pred, obj=obj, now=now,
                )
            else:
                self._run(
                    "MATCH (s:Entity {scope:$scope, name:$subj})-[r:REL {predicate:$pred}]->(old:Entity) "
                    "WHERE coalesce(r.invalid,false)=false AND old.name<>$obj "
                    "SET r.invalid=true, r.valid_to=$now",
                    scope=self.scope, subj=self._norm(subj), pred=pred, obj=obj, now=now,
                )

        if subj is None:
            self._run(
                "MERGE (o:Owner {scope:$scope}) "
                "MERGE (e:Entity {scope:$scope, name:$obj}) "
                "  ON CREATE SET e.kind=$obj_kind SET e.kind=coalesce(e.kind,$obj_kind) "
                "MERGE (o)-[r:REL {predicate:$pred}]->(e) "
                "  ON CREATE SET r.valid_from=$vfrom, r.ingested_at=$now "
                "SET r.invalid=false, r.valid_to=null, r.statement=$stmt, r.ingested_at=$now",
                scope=self.scope, obj=obj, obj_kind=obj_kind, pred=pred,
                vfrom=vfrom, now=now, stmt=statement or "",
            )
        else:
            self._run(
                "MERGE (s:Entity {scope:$scope, name:$subj}) "
                "  ON CREATE SET s.kind=$subj_kind SET s.kind=coalesce(s.kind,$subj_kind) "
                "MERGE (e:Entity {scope:$scope, name:$obj}) "
                "  ON CREATE SET e.kind=$obj_kind SET e.kind=coalesce(e.kind,$obj_kind) "
                "MERGE (s)-[r:REL {predicate:$pred}]->(e) "
                "  ON CREATE SET r.valid_from=$vfrom, r.ingested_at=$now "
                "SET r.invalid=false, r.valid_to=null, r.statement=$stmt, r.ingested_at=$now",
                scope=self.scope, subj=self._norm(subj), subj_kind=subj_kind,
                obj=obj, obj_kind=obj_kind, pred=pred, vfrom=vfrom, now=now, stmt=statement or "",
            )
        return True

    # ---- reads / traversal -------------------------------------------------------
    def resolve_role(self, role: str) -> List[dict]:
        """People currently reachable as 'my <role>' (invalid edges excluded)."""
        pred = self._pred(role)
        if not self.ok or not pred:
            return []
        recs = self._run(
            "MATCH (:Owner {scope:$scope})-[r:REL {predicate:$pred}]->(e:Entity) "
            "WHERE coalesce(r.invalid,false)=false "
            "RETURN e.name AS name, e.kind AS kind, r.statement AS statement",
            scope=self.scope, pred=pred,
        )
        return [dict(r) for r in recs]

    def multi_hop(self, role_chain: List[str]) -> List[dict]:
        """Traverse a possessive chain from the owner.

        role_chain ['accountant','assistant'] answers 'my accountant's assistant':
          (Owner)-[accountant]->(mid)-[assistant]->(end).
        Returns the END entities plus the full path of intermediate names.
        """
        chain = [self._pred(r) for r in (role_chain or []) if self._pred(r)]
        if not self.ok or not chain:
            return []
        # build (Owner)-[r0]->(n1)-[r1]->(n2)... dynamically, all edges must be valid.
        parts = ["(o:Owner {scope:$scope})"]
        where = []
        params = {"scope": self.scope}
        for i, pred in enumerate(chain):
            rv, nv = f"r{i}", f"n{i}"
            parts.append(f"-[{rv}:REL {{predicate:$p{i}}}]->({nv}:Entity)")
            where.append(f"coalesce({rv}.invalid,false)=false")
            params[f"p{i}"] = pred
        last = f"n{len(chain) - 1}"
        mids = ", ".join(f"n{i}.name AS hop{i}" for i in range(len(chain)))
        cypher = ("MATCH " + "".join(parts) + " WHERE " + " AND ".join(where) +
                  f" RETURN {last}.name AS name, {last}.kind AS kind" +
                  (f", {mids}" if mids else ""))
        return [dict(r) for r in self._run(cypher, **params)]

    def disambiguate(self, first_name: str, hint: str = "") -> Tuple[Optional[dict], List[dict]]:
        """Resolve a bare first name to ONE owner-connected person by traversal.

        Returns (chosen, candidates):
          - exactly one person whose name starts with first_name  -> (that, [])
          - several, and `hint` words name/echo one's role         -> (that, all)
          - several, no hint match                                 -> (None, all)
        `hint` is the surrounding sentence ("email Sam the signed *contract*" → a
        contract points at the lawyer, not the brother).
        """
        fn = self._norm(first_name).lower()
        if not self.ok or not fn:
            return None, []
        recs = self._run(
            "MATCH (:Owner {scope:$scope})-[r:REL]->(e:Entity {kind:'person'}) "
            "WHERE coalesce(r.invalid,false)=false AND toLower(e.name) STARTS WITH $fn "
            "RETURN DISTINCT e.name AS name, r.predicate AS role, r.statement AS statement",
            scope=self.scope, fn=fn,
        )
        cands = [dict(r) for r in recs]
        if len(cands) == 1:
            return cands[0], []
        if not cands:
            return None, []
        hint_l = (hint or "").lower()
        # cheap role→trigger lexicon: which surrounding words point at which role
        triggers = {
            "lawyer": ("contract", "legal", "lawsuit", "sign", "signed", "nda", "agreement", "case"),
            "attorney": ("contract", "legal", "lawsuit", "sign", "signed", "nda", "agreement", "case"),
            "accountant": ("tax", "taxes", "invoice", "receipt", "books", "expense", "audit"),
            "doctor": ("prescription", "appointment", "symptom", "sick", "results"),
            "landlord": ("rent", "lease", "leak", "repair", "apartment"),
        }
        for c in cands:
            role = (c.get("role") or "").lower()
            if role and role in hint_l:
                return c, cands
            for kw in triggers.get(role, ()):  # role implied by a topic word
                if kw in hint_l:
                    return c, cands
        return None, cands

    def multi_hop_from_question(self, text: str) -> List[dict]:
        """Parse a possessive question ('who is my accountant's assistant') into a
        role chain and traverse it. Returns [] when there's no 'my X's Y…' chain."""
        chain = parse_possessive_chain(text)
        return self.multi_hop(chain) if len(chain) >= 2 else []

    # ---- housekeeping ------------------------------------------------------------
    def clear_scope(self) -> int:
        """DETACH DELETE everything in this scope. Returns nodes removed."""
        if not self.ok:
            return 0
        recs = self._run(
            "MATCH (n) WHERE n.scope=$scope "
            "WITH n, count(n) AS _ DETACH DELETE n RETURN count(n) AS removed",
            scope=self.scope,
        )
        return int(recs[0]["removed"]) if recs else 0

    def stats(self) -> dict:
        recs = self._run(
            "MATCH (n) WHERE n.scope=$scope "
            "OPTIONAL MATCH (n)-[r:REL]->() "
            "RETURN count(DISTINCT n) AS nodes, count(r) AS edges", scope=self.scope,
        )
        return dict(recs[0]) if recs else {"nodes": 0, "edges": 0}


# possessive-chain parser: "my accountant's assistant" -> ["accountant","assistant"]
_MY_CHAIN = re.compile(r"\bmy\s+([a-z][a-z '’\-]*?)(?=$|[?.!,])", re.I)
# words that end a role phrase — trailing filler on the final segment is dropped so
# "my accountant's assistant the receipt" still yields ["accountant","assistant"].
_CHAIN_STOP = {"the", "a", "an", "to", "for", "about", "on", "with", "and", "please",
               "this", "that", "when", "who", "is", "of", "his", "her", "their",
               "number", "email", "phone", "address", "contact"}


def parse_possessive_chain(text: str) -> List[str]:
    """Extract the role chain from the FIRST 'my X['s Y['s Z]]' in ``text``."""
    m = _MY_CHAIN.search(text or "")
    if not m:
        return []
    parts = re.split(r"['’]s\s+", m.group(1))  # split on apostrophe-s boundaries
    out: List[str] = []
    for p in parts:
        # keep only the leading role words, stopping at the first filler token
        role_words: List[str] = []
        for w in p.split():
            if w.lower() in _CHAIN_STOP:
                break
            role_words.append(w)
        role = " ".join(role_words).strip()
        if role:
            out.append(role)
    return out


__all__ = ["GraphStore", "graph_enabled", "parse_possessive_chain"]
