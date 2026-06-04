"""Phase-1 memory recall-eval harness — the measuring stick for memory.

Decouples "did the right note surface" (RETRIEVAL) from "was the answer right"
(READING). Wraps a labeled, seeded replay week and scores the REAL memory agent
(inject / open_loops ledger / maintain / self-check), reusing Scorecard.record_recall.

TWO LAYERS
  - DETERMINISTIC CORE (default): ZERO model calls, pure math vs gold labels —
    recall@k, commitments (exact ledger), abstention, calibration. Runs in CI.
  - JUDGED LAYER (--judge or ANTICIPY_EVAL_JUDGE=live): a pinned LLM judge +
    reader for answer-accuracy + the oracle retrieval-vs-reasoning attribution.
    Real model calls; NEVER in the free CI gate.

Honesty rules (the harness is the watcher): gold ids come from the labeled week by
construction; the gold answer/id is NEVER passed into inject() (anti-cheat grep
clean); judge != generator, pinned snapshot, temp 0; determinism classes never blend.

Usage:
  --selftest                vet the instrument (zero model calls), exit nonzero if broken
  [--repeat N] [--seed S]   deterministic core, N runs, mean ± stddev (default N=10)
  --judge                   also run the judged layer (oracle attribution); needs OPENROUTER
  --out PATH                versioned JSON output (default .anticipy-data/memory_eval.json)
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from anticipy_engine.core.scorecard import Scorecard
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.live_memory.inject import Injector, _toks
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import CaptureEvent

KS = (5, 10, 50)
ABSTAIN_FLOOR = 0.34   # abstain if no retrieved note clears this relevance bar (separates
                       # content matches ~0.45+ from stopword-only matches ~0.2); model-free.
DATASET_NAME = "phase1-labeled-week"

# ---------------------------------------------------------------------------
# THE LABELED WEEK  (deterministic; gold ids are recorded by construction)
# Each capture with a `key` is a gold-bearing fact/commitment; key=None = noise.
# ---------------------------------------------------------------------------
CAPTURES = [
    ("f_meaning",  "I've been researching ergonomic standing desks for my home office."),
    (None,         "um"),
    ("f_kbd",      "I switched to a mechanical keyboard with brown switches for typing."),
    ("f_name",     "Sarah is my product designer and she owns all the Figma files."),
    (None,         "ok thanks"),
    ("f_job_old",  "I work at OldCo Incorporated."),                 # superseded mid-week
    ("f_date",     "My passport expires on March 14th."),
    (None,         "the weather was nice for a walk today"),
    ("c_dentist",  "Remind me to call the dentist on Friday."),       # commitment
    ("f_trip1",    "I booked the flights to Lisbon for our team offsite."),
    ("f_bro",      "My brother Daniel is visiting from Seattle this spring."),
    ("c_taxes",    "I'll email the accountant about the taxes by Thursday."),  # commitment
    (None,         "hey"),
    ("f_trip2",    "The Lisbon offsite hotel is the Memmo Alfama, check-in on the 9th."),
    ("f_job_new",  "I work at NewCo Labs now."),                      # supersedes f_job_old
    (None,         "watched a documentary about deep-sea fish"),
    ("c_insure",   "I need to renew the car insurance next week."),   # commitment
]

# probe: (key, probe_type, text, gold_keys, gold_answer, should_abstain)
PROBES = [
    ("p_meaning1", "by-meaning",       "ergonomic standing desk for my home office",      ["f_meaning"], "ergonomic standing desks for the home office", False),
    ("p_meaning2", "by-meaning",       "mechanical keyboard with brown switches typing",  ["f_kbd"],     "a mechanical keyboard with brown switches", False),
    ("p_name1",    "by-name",          "Sarah product designer Figma files",              ["f_name"],    "Sarah, the product designer who owns the Figma files", False),
    ("p_name2",    "by-name",          "my brother Daniel visiting Seattle",              ["f_bro"],     "brother Daniel, visiting from Seattle", False),
    ("p_date",     "by-date",          "passport expires what date",                      ["f_date"],    "March 14th", False),
    ("p_multi",    "multi-session",    "Lisbon offsite flights and hotel plans",          ["f_trip1", "f_trip2"], "flights to Lisbon and the Memmo Alfama hotel, check-in the 9th", False),
    ("p_update",   "knowledge-update", "which company do I work at now",                  ["f_job_new"], "NewCo Labs", False),
    ("p_abs1",     "abstention",       "what is my blood type",                           [],            None, True),
    ("p_abs2",     "abstention",       "when is my mother's birthday",                    [],            None, True),
]
# commitment_key -> expected due substring (state must be 'open', task must equal text)
COMMITMENTS = {"c_dentist": "Friday", "c_taxes": "by Thursday", "c_insure": "next week"}


def _dataset_sha() -> str:
    blob = json.dumps([CAPTURES, PROBES, COMMITMENTS], sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def build_week(data_dir: Path):
    """Capture the week into a fresh memory, run the cold sweep, return (lm, key->id)."""
    lm = LiveMemoryBrain(Memory(data_dir=data_dir))   # gateway=None -> stub, ZERO model calls
    ids = {}
    for key, text in CAPTURES:
        r = lm.capture(CaptureEvent(source="mac_mic", text=text))
        if key:
            assert r.get("kept"), f"week build: gold capture dropped: {text!r}"
            ids[key] = r["item"].id
    lm.maintain()   # cold sweep: supersedes f_job_old with f_job_new (location/employer subject)
    return lm, ids


# ---------------------------------------------------------------------------
# metric helpers (pure math)
# ---------------------------------------------------------------------------
def _kw_relevance(probe: str, item) -> float:
    q = _toks(probe)
    if not q:
        return 0.0
    hay = _toks(item.text) | _toks(" ".join(item.people)) | _toks(" ".join(str(v) for v in item.fields.values()))
    return len(q & hay) / len(q)


def recall_at_k(retrieved_ids, gold_ids, k):
    top = set(retrieved_ids[:k]); gold = set(gold_ids)
    return float(bool(top & gold)), float(gold.issubset(top))  # (recall_any@k, recall_all@k)


def abstention_metrics(pairs):
    TA = FAns = FA = TAns = 0
    for should, did in pairs:
        if should and did: TA += 1
        elif should and not did: FAns += 1
        elif (not should) and did: FA += 1
        else: TAns += 1
    return (TA / ((TA + FAns) or 1), FA / ((FA + TAns) or 1))


def brier(pairs):
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs) if pairs else 0.0


def ece_equiwidth(pairs, M=10):
    if not pairs:
        return 0.0
    bins = [[] for _ in range(M)]
    for p, o in pairs:
        p = min(max(p, 0.0), 1.0)
        bins[min(int(math.ceil(p * M)) - 1, M - 1) if p > 0 else 0].append((p, o))
    n = len(pairs)
    return sum(len(b) / n * abs(sum(o for _, o in b) / len(b) - sum(p for p, _ in b) / len(b)) for b in bins if b)


def ece_equimass(pairs, M=10):
    if not pairs:
        return 0.0
    s = sorted(pairs, key=lambda x: x[0])
    n = len(s); ece = 0.0
    for m in range(M):
        b = s[m * n // M:(m + 1) * n // M]
        if b:
            ece += len(b) / n * abs(sum(o for _, o in b) / len(b) - sum(p for p, _ in b) / len(b))
    return ece


# ---------------------------------------------------------------------------
# DETERMINISTIC CORE (zero model calls)
# ---------------------------------------------------------------------------
def deterministic_run(data_dir: Path, scorecard: Scorecard | None = None) -> dict:
    lm, ids = build_week(data_dir)
    # eval injector: un-truncated (big budget, k=50) so recall@k measures the
    # RETRIEVER's ranking, not the 2k-char prompt-assembly budget. Same Injector class.
    inj = Injector(lm.memory, char_budget=10_000_000, k=50)

    recall = {f"recall_any@{k}": [] for k in KS}
    recall.update({f"recall_all@{k}": [] for k in KS})
    by_type = {}                 # ptype -> list of recall_all@10
    abst_pairs, calib_pairs = [], []

    for key, ptype, text, gold_keys, _ans, should_abstain in PROBES:
        out = inj.inject(text)                                   # probe text ONLY — never the gold
        items = out["items"]
        retrieved = [i.id for i in items]
        nonloop = [i for i in items if i.kind != "open_loop"]
        top_rel = max((_kw_relevance(text, i) for i in nonloop), default=0.0)
        did_abstain = top_rel < ABSTAIN_FLOOR                    # model-free: nothing relevant enough
        abst_pairs.append((should_abstain, did_abstain))
        if should_abstain:
            continue                                             # no gold -> skip retrieval scoring
        gold = [ids[k] for k in gold_keys]
        hits = {}
        for k in KS:
            a, al = recall_at_k(retrieved, gold, k)
            recall[f"recall_any@{k}"].append(a); recall[f"recall_all@{k}"].append(al)
            hits[k] = (a, al)
        by_type.setdefault(ptype, []).append(hits[10][1])        # recall_all@10 per type
        conf = max((_kw_relevance(text, i) for i in nonloop), default=0.0)
        calib_pairs.append((conf, hits[10][0]))                  # confidence vs retrieval hit
        if scorecard is not None:
            scorecard.record_recall(text, bool(hits[10][0]), len(retrieved), reason=ptype)

    # COMMITMENTS — exact ledger check (P0): every promise present, fields + state correct
    loops = {l.text: l for l in lm.memory.open_loops.all()}
    present = 0
    for ckey, due_sub in COMMITMENTS.items():
        ctext = dict(CAPTURES)[ckey]
        l = loops.get(ctext)
        if l and l.status == "open" and l.fields.get("task") == ctext and due_sub.lower() in str(l.fields.get("due", "")).lower():
            present += 1
    commit_rate = present / len(COMMITMENTS)

    ab_recall, ab_over = abstention_metrics(abst_pairs)
    m = {f"{k}": (sum(v) / len(v) if v else 0.0) for k, v in recall.items()}
    for ptype, vals in by_type.items():
        m[f"recall_all@10::{ptype}"] = sum(vals) / len(vals)
    m["commitments.rate"] = commit_rate
    m["abstention.recall"] = ab_recall
    m["abstention.over_rate"] = ab_over
    m["calibration.ece_eqwidth"] = ece_equiwidth(calib_pairs)
    m["calibration.ece_eqmass"] = ece_equimass(calib_pairs)
    m["calibration.brier"] = brier(calib_pairs)
    return m


# ---------------------------------------------------------------------------
# SELF-TEST — vet the instrument (zero model calls)
# ---------------------------------------------------------------------------
def selftest() -> bool:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        ok = ok and cond

    # 1) plant a fact -> it surfaces in recall_any@10
    lm = LiveMemoryBrain(Memory(data_dir=Path(tempfile.mkdtemp())))
    gid = lm.capture(CaptureEvent(source="mac_mic", text="I adopted a golden retriever named Cooper last spring."))["item"].id
    inj = Injector(lm.memory, char_budget=10_000_000, k=50)
    r = [i.id for i in inj.inject("golden retriever Cooper dog")["items"]]
    check("plant fact -> recall_any@10 surfaces it", gid in set(r[:10]))

    # 2) never-stored probe -> abstention fires (nothing clears the relevance floor)
    probe = "what is my social security number"
    nonloop = [i for i in inj.inject(probe)["items"] if i.kind != "open_loop"]
    top_rel = max((_kw_relevance(probe, i) for i in nonloop), default=0.0)
    check("never-stored probe -> abstain", top_rel < ABSTAIN_FLOOR)

    # 3) stale OldValue->NewValue -> current-value retrieval surfaces NEW, not superseded OLD
    lm2 = LiveMemoryBrain(Memory(data_dir=Path(tempfile.mkdtemp())))
    old_id = lm2.capture(CaptureEvent(source="mac_mic", text="I live in Portland."))["item"].id
    new_id = lm2.capture(CaptureEvent(source="mac_mic", text="I live in Denver now."))["item"].id
    lm2.maintain()
    inj2 = Injector(lm2.memory, char_budget=10_000_000, k=50)
    r2 = set(i.id for i in inj2.inject("which city do I live in")["items"])
    check("knowledge-update -> NEW surfaces", new_id in r2)
    check("knowledge-update -> superseded OLD does NOT surface", old_id not in r2)

    print("INSTRUMENT", "SOUND" if ok else "BROKEN")
    return ok


# ---------------------------------------------------------------------------
# JUDGED LAYER (flag-gated; real model calls; NOT in CI)
# ---------------------------------------------------------------------------
JUDGE_MODEL = "openai/gpt-4o-2024-08-06"      # pinned snapshot; judge != generator
READER_MODEL = "google/gemini-3.5-flash"      # the "generator"; different family

_JUDGE_RUBRIC = {
    "default": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.",
    "multi-session": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response only contains a subset of the information required by the answer, answer no.",
}


def _judge_prompt(ptype, q, gold, resp):
    rubric = _JUDGE_RUBRIC.get(ptype, _JUDGE_RUBRIC["default"])
    return (f"{rubric}\n\nQuestion: {q}\n\nCorrect Answer: {gold}\n\nModel Response: {resp}\n\n"
            "Is the model response correct? Answer yes or no only.")


async def judged_run(data_dir: Path) -> dict:
    from anticipy_engine.core.env import load_local_env
    from anticipy_engine.core.gateway import CHEAP, PROVIDER_OPENROUTER, ModelGateway
    load_local_env()
    reader = ModelGateway(provider=PROVIDER_OPENROUTER, cheap_model=READER_MODEL, smart_model=READER_MODEL)
    judge = ModelGateway(provider=PROVIDER_OPENROUTER, cheap_model=JUDGE_MODEL, smart_model=JUDGE_MODEL)
    lm, ids = build_week(data_dir)
    inj = Injector(lm.memory, char_budget=10_000_000, k=50)

    async def read(probe, ctx_items):
        ctx = "\n".join(f"- {i.text}" for i in ctx_items) or "(no memories)"
        prompt = ("Answer the question using ONLY the user's stored memories below. "
                  "If they do not contain the answer, say you don't know.\n"
                  f"MEMORIES:\n{ctx}\n\nQUESTION: {probe}\nAnswer concisely:")
        return ((await reader.think(prompt, tier=CHEAP, caller="agent", temperature=0)) or "").strip()

    async def judged(ptype, q, gold, resp):
        raw = ((await judge.think(_judge_prompt(ptype, q, gold, resp), tier=CHEAP, caller="agent", temperature=0)) or "").lower()
        return "yes" in raw and "no" not in raw.split()  # reject dual; require a clean yes

    buckets = {"OK": 0, "RETRIEVAL": 0, "READER_CONTEXT": 0, "REASONING_CEILING": 0, "noise": 0}
    rows, oracle_ok, retr_ok, n = [], 0, 0, 0
    for key, ptype, text, gold_keys, gold_ans, should_abstain in PROBES:
        if should_abstain:
            continue
        n += 1
        gold = [ids[k] for k in gold_keys]
        gold_items = [lm.memory.db.get(g) for g in gold]
        retr_items = [i for i in inj.inject(text)["items"] if i.kind != "open_loop"]
        recall_hit = set(gold).issubset(set(i.id for i in inj.inject(text)["items"][:10]))
        try:
            o_label = await judged(ptype, text, gold_ans, await read(text, gold_items))   # oracle context
            r_label = await judged(ptype, text, gold_ans, await read(text, retr_items))   # retrieved context
        except Exception as e:
            buckets["noise"] += 1; rows.append((key, f"judge/reader error: {e}")); continue
        oracle_ok += o_label; retr_ok += r_label
        if o_label and r_label: b = "OK"
        elif o_label and not r_label and not recall_hit: b = "RETRIEVAL"
        elif o_label and not r_label and recall_hit: b = "READER_CONTEXT"
        elif not o_label: b = "REASONING_CEILING"
        else: b = "noise"
        buckets[b] += 1
        rows.append((key, b, f"oracle={'P' if o_label else 'F'} retr={'P' if r_label else 'F'} recall@10={'hit' if recall_hit else 'miss'}"))
    return {"judge_model": JUDGE_MODEL, "reader_model": READER_MODEL, "n": n,
            "oracle_accuracy": oracle_ok / n if n else 0.0, "retrieved_accuracy": retr_ok / n if n else 0.0,
            "retrieval_attributable_loss": (oracle_ok - retr_ok) / n if n else 0.0,
            "buckets": buckets, "rows": rows,
            "judge_prompt_sha256": hashlib.sha256(json.dumps(_JUDGE_RUBRIC, sort_keys=True).encode()).hexdigest()[:16]}


# ---------------------------------------------------------------------------
# aggregate + report
# ---------------------------------------------------------------------------
def aggregate(runs):
    keys = sorted({k for r in runs for k in r})
    out = {}
    for k in keys:
        vals = [r[k] for r in runs if k in r]
        mean = statistics.fmean(vals)
        sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        ci95 = 1.96 * sd / math.sqrt(len(vals)) if vals else 0.0
        out[k] = {"mean": round(mean, 4), "stddev": round(sd, 4), "ci95": round(ci95, 4), "n": len(vals)}
    return out


def print_scorecard(agg):
    def g(k): return agg.get(k, {}).get("mean", float("nan"))
    print("\n==== MEMORY RECALL-EVAL — DETERMINISTIC CORE (zero model calls) ====")
    print("  RETRIEVAL recall (mean over probes):")
    for k in KS:
        print(f"    recall_any@{k:<2} = {g(f'recall_any@{k}'):.3f}   recall_all@{k:<2} = {g(f'recall_all@{k}'):.3f}  (gate)")
    print("  recall_all@10 by probe-type:")
    for key in sorted(k for k in agg if k.startswith("recall_all@10::")):
        print(f"    {key.split('::')[1]:<16} = {agg[key]['mean']:.3f}")
    print(f"  COMMITMENTS (ledger, P0): {g('commitments.rate')*100:.1f}%   [bar 100%]")
    print(f"  ABSTENTION:  recall = {g('abstention.recall'):.3f}   over_abstention = {g('abstention.over_rate'):.3f}")
    print(f"  CALIBRATION: ECE(eqwidth)={g('calibration.ece_eqwidth'):.3f}  ECE(eqmass)={g('calibration.ece_eqmass'):.3f}  Brier={g('calibration.brier'):.3f}")
    n = agg.get("commitments.rate", {}).get("n", 0)
    sd = max((v["stddev"] for v in agg.values()), default=0.0)
    print(f"  (runs={n}; max per-metric stddev={sd:.4f} — deterministic core has ~0 variance by design)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=".anticipy-data/memory_eval.json")
    args = ap.parse_args()

    if args.selftest:
        print("=== SELF-TEST (instrument soundness; zero model calls) ===")
        sys.exit(0 if selftest() else 1)

    sc = Scorecard(Path(tempfile.mkdtemp()) / "eval_scorecard.jsonl")
    runs = [deterministic_run(Path(tempfile.mkdtemp()), scorecard=sc) for _ in range(args.repeat)]
    agg = aggregate(runs)
    print_scorecard(agg)

    judged = None
    if args.judge or os.environ.get("ANTICIPY_EVAL_JUDGE") == "live":
        print("\n=== JUDGED LAYER (pinned judge; real model calls) ===")
        judged = asyncio.run(judged_run(Path(tempfile.mkdtemp())))
        print(f"  judge={judged['judge_model']}  reader={judged['reader_model']}  n={judged['n']}")
        print(f"  reasoning ceiling (oracle acc) = {judged['oracle_accuracy']:.3f}")
        print(f"  retrieved accuracy             = {judged['retrieved_accuracy']:.3f}")
        print(f"  retrieval-attributable loss    = {judged['retrieval_attributable_loss']:.3f}")
        print("  ATTRIBUTION:")
        for k, v in judged["buckets"].items():
            print(f"    {k:<18} {v}")

    manifest = {"harness_git_sha": _git_sha(), "memory_version": DATASET_NAME,
                "dataset_version_sha256": _dataset_sha(), "seeds": [args.seed], "temperature": 0,
                "judge_model_id": judged["judge_model"] if judged else None,
                "judge_prompt_sha256": judged["judge_prompt_sha256"] if judged else None}
    result = {"run_manifest": manifest, "per_category": agg, "raw_runs": runs,
              "judged": judged, "baseline_ref": None}
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  versioned JSON -> {out}")
    # commitments are a P0 hard gate
    if agg.get("commitments.rate", {}).get("mean", 0.0) < 1.0:
        print("  COMMITMENTS < 100% -> P0 FAIL"); sys.exit(2)


if __name__ == "__main__":
    main()
