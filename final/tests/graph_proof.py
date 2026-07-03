"""final/tests/graph_proof.py — PROOF for the Phase-4 temporal knowledge graph.

Writes two 'Sam' people with DIFFERENT relationships and shows the graph
disambiguates by TRAVERSAL (not string tie-break), resolves a MULTI-HOP question
("who is my accountant's assistant"), and honors BI-TEMPORAL invalidation (a
contradicting fact soft-deletes the old edge, keeping history). Two layers:

  Part 1 — the raw GraphStore (Neo4j traversal + bi-temporal edges).
  Part 2 — end-to-end through the ContextEngine (observe facts, resolve lines),
           proving the graph actually FEEDS context resolution.

Runs against the LIVE Neo4j in an ISOLATED scope and DETACH-DELETEs that scope on
exit. Requires ANTICIPY_GRAPH=neo4j + the NEO4J_* creds (auto-loaded from .env.local).

Run:  ANTICIPY_GRAPH=neo4j PYTHONPATH=engine:. engine/.venv/bin/python final/tests/graph_proof.py
"""
from __future__ import annotations

import os
import sys
import tempfile

# live keys from .env.local (NEO4J_*, GOOGLE_API_KEY)
from anticipy_engine.core.env import load_local_env  # noqa: E402

load_local_env()
os.environ["ANTICIPY_GRAPH"] = "neo4j"
os.environ["ANTICIPY_GRAPH_SCOPE"] = "graph_proof"  # isolated, cleaned on exit

from final.context.graph import GraphStore  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def part1_raw_graph() -> None:
    print("PART 1 — raw graph traversal (two Sams, multi-hop, bi-temporal)")
    print("=" * 66)
    g = GraphStore(scope="graph_proof")
    if not g.ok:
        FAILURES.append("neo4j not reachable")
        print("  [FAIL] could not connect to Neo4j"); return
    g.clear_scope()

    # two Sams, DIFFERENT relationships — indistinguishable as strings
    g.add_owner_relation("lawyer", "Sam Rivera", statement="Sam Rivera is my lawyer")
    g.add_owner_relation("brother", "Sam Chen", statement="Sam Chen is my little brother")
    # a 2-hop chain: my accountant (Mia) -> her assistant (Jane)
    g.add_owner_relation("accountant", "Mia Torres", statement="Mia is my accountant")
    g.add_relation("Mia Torres", "assistant", "Jane Doe", statement="Jane is Mia's assistant")

    st = g.stats()
    check("graph populated", st.get("nodes", 0) >= 5 and st.get("edges", 0) >= 4, str(st))

    # DISAMBIGUATE BY TRAVERSAL — same first name, resolved by relationship context
    law = g.resolve_role("lawyer")
    check("resolve_role('lawyer') -> Sam Rivera",
          len(law) == 1 and law[0]["name"] == "Sam Rivera", str(law))
    bro = g.resolve_role("brother")
    check("resolve_role('brother') -> Sam Chen",
          len(bro) == 1 and bro[0]["name"] == "Sam Chen", str(bro))

    chosen, cands = g.disambiguate("Sam", hint="email Sam the signed contract")
    check("disambiguate 'Sam' + 'signed contract' -> the LAWYER Sam Rivera",
          chosen is not None and chosen["name"] == "Sam Rivera" and len(cands) == 2,
          f"chose={chosen and chosen.get('name')} of {len(cands)} candidates")

    chosen2, _ = g.disambiguate("Sam", hint="going to my brother Sam's place")
    check("disambiguate 'Sam' + 'brother' -> the BROTHER Sam Chen",
          chosen2 is not None and chosen2["name"] == "Sam Chen",
          f"chose={chosen2 and chosen2.get('name')}")

    amb, cands3 = g.disambiguate("Sam", hint="ping Sam quickly")
    check("disambiguate 'Sam' with NO relationship cue -> stays ambiguous (would ask)",
          amb is None and len(cands3) == 2, f"chose={amb}, candidates={len(cands3)}")

    # MULTI-HOP: who is my accountant's assistant?
    hop = g.multi_hop(["accountant", "assistant"])
    check("multi_hop([accountant, assistant]) -> Jane Doe via Mia",
          len(hop) == 1 and hop[0]["name"] == "Jane Doe" and hop[0].get("hop0") == "Mia Torres",
          str(hop))
    hop_q = g.multi_hop_from_question("who is my accountant's assistant?")
    check("natural question 'who is my accountant's assistant?' -> Jane Doe",
          len(hop_q) == 1 and hop_q[0]["name"] == "Jane Doe", str(hop_q))

    # BI-TEMPORAL: the accountant changes; old edge is invalidated, not deleted
    g.add_owner_relation("accountant", "Bob Lee", statement="my accountant is now Bob")
    acc = g.resolve_role("accountant")
    check("after 'accountant is now Bob' -> resolve_role('accountant') == Bob only",
          len(acc) == 1 and acc[0]["name"] == "Bob Lee", str(acc))
    hist = g._run(
        "MATCH (:Owner {scope:$s})-[r:REL {predicate:'accountant'}]->(e:Entity) "
        "RETURN e.name AS name, coalesce(r.invalid,false) AS invalid, r.valid_to AS valid_to "
        "ORDER BY name", s="graph_proof")
    hist = [dict(x) for x in hist]
    mia = next((h for h in hist if h["name"] == "Mia Torres"), None)
    check("prior fact kept as HISTORY (Mia edge invalid=true, valid_to set)",
          mia is not None and mia["invalid"] is True and mia["valid_to"] is not None, str(mia))
    hop_after = g.multi_hop(["accountant", "assistant"])
    check("multi-hop after change -> empty (Bob has no assistant; invalid edge not traversed)",
          hop_after == [], str(hop_after))

    g.close()


def part2_context_engine() -> None:
    print("\nPART 2 — end-to-end through the ContextEngine (graph feeds resolution)")
    print("=" * 66)
    from anticipy_engine.memory.store import Memory
    from final.context.engine import ContextEngine

    tmp = tempfile.mkdtemp(prefix="graph_proof_")
    mem = Memory(data_dir=tmp)
    ce = ContextEngine(mem)
    check("ContextEngine has a live graph (flag on)", ce.graph is not None and ce.graph.ok)
    if ce.graph is not None and ce.graph.ok:
        ce.graph.clear_scope()

    # tell it the facts (seam 1) — captured into memory AND mirrored into the graph
    for fact in ["Sam Rivera is my lawyer", "Sam Chen is my little brother",
                 "Mia is my accountant", "Jane is Mia's assistant"]:
        ce.observe(fact)

    class Line:
        def __init__(self, t): self.text = t

    # (a) two Sams resolved by relationship context, not by asking
    l1 = Line("email Sam the signed contract")
    ce.resolve_observed([l1])
    check("line 'email Sam the signed contract' resolves to Sam Rivera (lawyer)",
          "rivera" in l1.text.lower() or "lawyer" in l1.text.lower(), repr(l1.text))

    # (b) multi-hop: name my accountant's assistant on the card
    l2 = Line("email my accountant's assistant the receipt")
    ce.resolve_observed([l2])
    check("line 'email my accountant's assistant the receipt' names Jane",
          "jane" in l2.text.lower(), repr(l2.text))

    if ce.graph is not None:
        ce.graph.clear_scope()
        ce.graph.close()


def main() -> int:
    part1_raw_graph()
    part2_context_engine()
    print("\n" + "=" * 66)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} FAILED -> {FAILURES}")
        return 1
    print("RESULT: ALL PROOFS PASSED — graph disambiguates by traversal, "
          "resolves multi-hop, and honors bi-temporal invalidation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
