"""Temporal knowledge-graph memory: ingest, recall, open loops."""
import sys, time
sys.path.insert(0, "/home/ubuntu/anticipy_app")

from brain.memory import Memory


def test_ingest_builds_graph():
    m = Memory()
    out = m.ingest("I'll send Sarah the pitch deck right after this call.")
    assert "Sarah" in out["entities"]
    assert out["commitment"] is not None
    assert "pitch deck" in out["commitment"] or "deck" in out["commitment"]


def test_recall_is_time_ordered_chain():
    m = Memory()
    t0 = time.time() - 3600
    m.ingest("Had coffee with Sarah to talk about the pitch deck.", ts=t0)
    m.ingest("I'll send Sarah the pitch deck tomorrow.", ts=t0 + 600)
    m.ingest("Random chatter about the weather.", ts=t0 + 700)
    facts = m.recall("what did I promise Sarah?")
    assert facts, "recall found nothing"
    assert any("Sarah" in f["fact"] for f in facts)
    ts = [f["ts"] for f in facts]
    assert ts == sorted(ts, reverse=True), "facts must be newest-first"
    assert all("weather" not in (f["quote"] or "") for f in facts), "off-topic leak"


def test_open_loops_lifecycle():
    m = Memory()
    out = m.ingest("I'll email Marcus the invoice on Friday.")
    loops = m.open_loops()
    assert len(loops) == 1 and "invoice" in loops[0]["what"]
    m.resolve(out["commitment_id"])
    assert m.open_loops() == []


def test_briefing_facts():
    m = Memory()
    start = time.time() - 10
    m.ingest("I'll book the Italian place for Saturday.")
    facts = m.briefing_facts(start)
    assert len(facts["heard"]) == 1
    assert len(facts["open_loops"]) == 1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("memory: all tests passed")
