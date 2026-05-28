"""MH-P2 gate: memory write path + store + decay/dedup.

Ingests a scripted SIMULATED MULTI-DAY life through the new
MemoryWriter onto the existing app.memory InProcess backend
(deterministic, offline, no shared-DB pollution; the real Supabase
pgvector write is the labelled wired edge). Binds on:

  CORRECT STORAGE  the expected durable facts exist with the right
    kind, exactly the expected count (no spurious facts).
  NO DUPLICATE FACTS  paraphrased restatements collapse onto the
    one existing durable row (dedup > 0, no second fact).
  NON-PROMOTABLE INVARIANT (hard)  a low-trust life-log item, even
    when it is phrased like a fact and asks to be a durable kind,
    is quarantined to life_log and NEVER appears in durable reads;
    durable facts contain ZERO life-log content; a single ambient
    observation never auto-creates a durable fact.
  DECAY  an old un-reinforced life-log item is pruned; a reinforced
    item and every durable fact survive (floored).
  PROMOTION IS EXPLICIT  promotion to durable happens only via the
    explicit corroborated-promote call, never automatically.

REPORTED: measured write latency (the baseline MH-P3's hard
retrieval budget is set from). frozen action engine + reasoning +
cascade git-clean.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]

DAY = 86400.0


async def _run() -> tuple[bool, list[str]]:
    from app.memory import InProcessMemoryBackend
    from app.memory_v2.write import IngestItem, MemoryWriter

    log: list[str] = []
    ok = True
    be = InProcessMemoryBackend()
    w = MemoryWriter(be)
    uid = "mh-p2-wearer"
    t0 = 1_700_000_000.0          # day 1 base

    # Day 1: real durable facts + genuine ambient life-log.
    r1 = await w.ingest(uid, [
        IngestItem("my wife is Priya", "fact", "confirmed", t0,
                   wearer_confirmed=True),
        IngestItem("my boss is Dana", "contact", "confirmed", t0,
                   wearer_confirmed=True),
        IngestItem("I prefer a window seat", "preference", "observed",
                   t0 + 100),
        IngestItem("the coffee here was pretty good today", "life_log",
                   "life_log", t0 + 200),
        IngestItem("traffic on the bridge was bad this morning",
                   "life_log", "life_log", t0 + 300),
    ])

    # Day 2: paraphrased restatements (must DEDUP, not duplicate) + a
    # low-trust life-log line that WANTS to be a durable fact (must be
    # blocked by the non-promotable invariant).
    r2 = await w.ingest(uid, [
        IngestItem("Priya is my wife", "fact", "observed", t0 + DAY),
        IngestItem("Dana, my boss", "contact", "observed", t0 + DAY + 50),
        IngestItem("I think I might switch banks someday", "fact",
                   "life_log", t0 + DAY + 100),     # MUST stay life_log
        IngestItem("oat flat white is my usual", "preference",
                   "life_log", t0 + DAY + 150),     # corroboration #1
    ])

    # Day 3: reinforce one durable fact; second corroboration of the
    # coffee preference; then an EXPLICIT corroborated promotion.
    r3 = await w.ingest(uid, [
        IngestItem("my wife is Priya", "fact", "observed", t0 + 2 * DAY),
        IngestItem("oat flat white is my usual", "preference",
                   "life_log", t0 + 2 * DAY + 50),  # corroboration #2
    ])
    promoted = await w.promote_if_corroborated(
        uid, "preference", "oat flat white is my usual")
    auto_pre = await w.promote_if_corroborated(
        uid, "fact", "I think I might switch banks someday")

    # --- BINDING: non-promotable invariant -------------------------
    durable = await w.durable_facts(uid)
    dvals = " ".join(str(m.value) for m in durable).lower()
    no_lifelog_leak = ("switch banks" not in dvals
                       and "traffic on the bridge" not in dvals
                       and "coffee here was pretty good" not in dvals)
    blocked = r2.blocked_promotions >= 1
    inv_ok = no_lifelog_leak and blocked and not auto_pre
    log.append(f"  BINDING non-promotable: lifelog_absent_from_durable="
               f"{no_lifelog_leak} blocked_promotions={r2.blocked_promotions}"
               f" auto_promote_refused={not auto_pre} -> {inv_ok}")
    ok &= inv_ok

    # --- BINDING: no duplicate facts -------------------------------
    facts = [m for m in durable if m.kind == "fact"]
    contacts = [m for m in durable if m.kind == "contact"]
    wife = [m for m in facts if "priya" in str(m.value).lower()]
    boss = [m for m in contacts if "dana" in str(m.value).lower()]
    dedup_ok = len(wife) == 1 and len(boss) == 1 and (
        r2.deduped + r3.deduped) >= 2
    log.append(f"  BINDING no-dup: wife_rows={len(wife)} (==1) "
               f"boss_rows={len(boss)} (==1) deduped="
               f"{r2.deduped + r3.deduped} (>=2) -> {dedup_ok}")
    ok &= dedup_ok

    # --- BINDING: correct storage ----------------------------------
    kinds = sorted({m.kind for m in durable})
    pref = [m for m in durable if m.kind == "preference"]
    store_ok = ("fact" in kinds and "contact" in kinds
                and "preference" in kinds and len(wife) == 1
                and any("window seat" in str(m.value).lower()
                        for m in pref))
    log.append(f"  BINDING storage: durable_kinds={kinds} "
               f"n_durable={len(durable)} -> {store_ok}")
    ok &= store_ok

    # --- BINDING: explicit promotion only --------------------------
    promo_ok = (promoted is True) and (auto_pre is False)
    has_promoted_pref = any(m.value.get("_promoted")
                            for m in pref)
    log.append(f"  BINDING promotion explicit-only: corroborated_promote="
               f"{promoted} auto_refused={not auto_pre} "
               f"promoted_row_present={has_promoted_pref} -> "
               f"{promo_ok and has_promoted_pref}")
    ok &= promo_ok and has_promoted_pref

    # --- BINDING: decay --------------------------------------------
    now = t0 + 40 * DAY            # 40 days later
    before = len(await be.recent(uid, k=100000))
    sweep = await w.decay_sweep(uid, now=now)
    after_rows = await be.recent(uid, k=100000)
    after_vals = " ".join(str(m.value) for m in after_rows).lower()
    durable_after = await w.durable_facts(uid)
    decay_ok = (sweep["pruned"] >= 1
                and "traffic on the bridge" not in after_vals
                and any("priya" in str(m.value).lower()
                        for m in durable_after)
                and any("window seat" in str(m.value).lower()
                        for m in durable_after))
    log.append(f"  BINDING decay: rows {before}->{len(after_rows)} "
               f"pruned={sweep['pruned']} (>=1) durable_survive="
               f"{len(durable_after)} -> {decay_ok}")
    ok &= decay_ok

    # --- REPORTED: write latency baseline --------------------------
    lat = round((r1.write_latency_ms + r2.write_latency_ms
                 + r3.write_latency_ms) / 3.0, 2)
    log.append(f"  REPORTED mean write latency/batch={lat}ms "
               f"(baseline for MH-P3's hard retrieval budget) "
               f"[stored={r1.stored + r2.stored + r3.stored} "
               f"deduped={r2.deduped + r3.deduped} "
               f"quarantined_lifelog={r1.quarantined_lifelog + r2.quarantined_lifelog + r3.quarantined_lifelog}]")

    return ok, log


def main() -> int:
    print("== MH-P2 GATE (memory write path + store + decay/dedup) ==")
    ok, log = asyncio.run(_run())

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    if not fc:
        log.append(f"      DIRTY: {fr.stdout.strip()!r}")
    ok &= fc

    for ln in log:
        print(ln)
    print("  NOTE local InProcess backend + deterministic offline "
          "embedder for an exact gate; Supabase pgvector + Gemini "
          "text-embedding-004 wired as the labelled prod edge, not "
          "autonomously written.")
    print(f"MH_P2_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
