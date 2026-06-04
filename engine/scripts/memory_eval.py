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
import random
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

from anticipy_engine.core.scorecard import Scorecard
from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.live_memory.inject import Injector, _toks
from anticipy_engine.memory import Memory
from anticipy_engine.memory.embed import LIVE_MODEL_ID, embedding_dim
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

    # LME instrument checks — only when the dataset is present (CI runs without it)
    if LME_HAYSTACK.exists():
        data = load_lme()
        art = None
        for x in data[:30]:
            if is_abs(x):
                continue
            a = ingest_instance(x)
            if a["gold_item_ids"]:
                art = a
                break
        check("LME ingest+map: a surviving gold turn maps to a retrievable item",
              art is not None and all(art["lm"].memory.db.get(g) is not None for g in art["gold_item_ids"]))
        absinst = next((x for x in data if is_abs(x)), None)
        aart = ingest_instance(absinst) if absinst else None
        check("LME _abs: empty gold (skipped by recall, folded into abstention)",
              aart is not None and aart["gold_total"] == 0 and len(aart["gold_item_ids"]) == 0)
    else:
        print("  [skip] LME data absent (.anticipy-data/longmemeval) — LME selftest skipped (OK for CI)")

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
    "temporal-reasoning": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct.",
    "single-session-preference": "I will give you a question, a rubric for the desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.",
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


# ===========================================================================
# PHASE 2A — LongMemEval external dataset adapter
# Ingest the haystack through the REAL capture gate (no embed-the-gold shortcut),
# map gold turns -> the item ids they produced, score recall reconciled to
# session granularity (effective_k), and attribute failures four ways.
# ===========================================================================
LME_DIR = Path(os.environ.get("LONGMEMEVAL_DIR", ".anticipy-data/longmemeval"))
LME_HAYSTACK = LME_DIR / "longmemeval_s.json"


def _has_answer(turn) -> bool:
    return str(turn.get("has_answer", "")).strip().lower() == "true"


def is_abs(inst) -> bool:
    return str(inst["question_id"]).endswith("_abs")


def lme_dataset_sha() -> str:
    try:
        h = hashlib.sha256()
        with open(LME_HAYSTACK, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except Exception:
        return "missing"


def load_lme():
    return json.load(open(LME_HAYSTACK))


def sample_subset(data, n, seed):
    """Stratified across question types; ~20% abstention (>=10 when n>=50); knowledge-update first."""
    rng = random.Random(seed)
    abs_pool = [x for x in data if is_abs(x)]
    abs_target = min(len(abs_pool), max(1, round(n * 0.2)))     # ~20%; 10 at n=50; never all-abs for small n
    chosen = rng.sample(abs_pool, abs_target)
    by_type = {}
    for x in data:
        if not is_abs(x):
            by_type.setdefault(x["question_type"], []).append(x)
    pools = {t: rng.sample(v, len(v)) for t, v in by_type.items()}
    order = sorted(pools)
    if "knowledge-update" in order:
        order = ["knowledge-update"] + [t for t in order if t != "knowledge-update"]
    while len(chosen) < n and any(pools.values()):
        for t in order:
            if len(chosen) >= n:
                break
            if pools[t]:
                chosen.append(pools[t].pop())
    rng.shuffle(chosen)
    return chosen


def sample_judged(data, n, seed):
    """Stratified ANSWERABLE-only sample across question types — the judged layer's set,
    decoupled from the (possibly full-500) deterministic set. Ids recorded in the manifest."""
    rng = random.Random(seed)
    by_type = {}
    for x in data:
        if not is_abs(x):
            by_type.setdefault(x["question_type"], []).append(x)
    pools = {t: rng.sample(v, len(v)) for t, v in by_type.items()}
    order = sorted(pools)
    chosen = []
    while len(chosen) < n and any(pools.values()):
        for t in order:
            if len(chosen) >= n:
                break
            if pools[t]:
                chosen.append(pools[t].pop())
    rng.shuffle(chosen)
    return chosen


def ingest_instance(inst):
    """Ingest the haystack through the REAL capture gate (haystack text ONLY; never the
    gold answer or gold flag). Map gold turns -> produced item ids. Fresh isolated memory."""
    lm = LiveMemoryBrain(Memory(data_dir=Path(tempfile.mkdtemp())))   # stub gateway -> zero model calls
    gold_sessions = set(inst["answer_session_ids"])
    item_session, gold_item_ids, gold_turn_texts = {}, [], []
    gold_total = 0
    for sid, sess in zip(inst["haystack_session_ids"], inst["haystack_sessions"]):
        gold_sess = sid in gold_sessions
        for turn in sess:
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            r = lm.capture(CaptureEvent(source="mac_mic", text=content))   # REAL gate; text only
            item = r.get("item")
            if item is not None:
                item_session[item.id] = sid
            if gold_sess and _has_answer(turn):
                gold_total += 1
                gold_turn_texts.append(content)
                if item is not None:
                    gold_item_ids.append(item.id)
    lm.maintain()
    return {"lm": lm, "gold_sessions": gold_sessions, "item_session": item_session,
            "gold_item_ids": gold_item_ids, "gold_turn_texts": gold_turn_texts,
            "gold_total": gold_total,
            "capture_recall": (len(set(gold_item_ids)) / gold_total) if gold_total else None}


def _covered_sessions(retrieved_ids, item_session):
    seen = []
    for iid in retrieved_ids:
        sid = item_session.get(iid)
        if sid and sid not in seen:
            seen.append(sid)
    return seen


def lme_recall(retrieved_ids, item_session, gold_sessions, k):
    """Session-reconciled recall over the semantic ranking (loops excluded upstream):
    effective_k = the first k UNIQUE sessions covered by the ranked items."""
    sess = set(_covered_sessions(retrieved_ids, item_session)[:k])
    gold = set(gold_sessions)
    return float(bool(sess & gold)), float(gold.issubset(sess))


def lme_deterministic(subset, scorecard=None) -> dict:
    recall = {f"recall_any@{k}": [] for k in KS}
    recall.update({f"recall_all@{k}": [] for k in KS})
    by_type, cap_recalls, abst_pairs, calib_pairs = {}, [], [], []
    for inst in subset:
        art = ingest_instance(inst)
        inj = Injector(art["lm"].memory, char_budget=10_000_000, k=50)
        out = inj.inject(inst["question"])                          # QUESTION only (anti-cheat)
        nonloop = [i for i in out["items"] if i.kind != "open_loop"]
        retrieved = [i.id for i in nonloop]                         # semantic ranking; loops excluded from recall@k
        top_rel = max((_kw_relevance(inst["question"], i) for i in nonloop), default=0.0)
        did_abstain = top_rel < ABSTAIN_FLOOR
        if is_abs(inst):
            abst_pairs.append((True, did_abstain))
            continue
        abst_pairs.append((False, did_abstain))
        if art["capture_recall"] is not None:
            cap_recalls.append(art["capture_recall"])
        a10 = 0.0
        for k in KS:
            a, al = lme_recall(retrieved, art["item_session"], art["gold_sessions"], k)
            recall[f"recall_any@{k}"].append(a)
            recall[f"recall_all@{k}"].append(al)
            if k == 10:
                a10 = a
                by_type.setdefault(inst["question_type"], []).append(al)
        calib_pairs.append((top_rel, a10))
        if scorecard is not None:
            scorecard.record_recall(inst["question"], bool(a10), len(retrieved), reason=inst["question_type"])
    ab_recall, ab_over = abstention_metrics(abst_pairs)
    m = {k: (sum(v) / len(v) if v else 0.0) for k, v in recall.items()}
    for t, vals in by_type.items():
        m[f"recall_all@10::{t}"] = sum(vals) / len(vals)
    m["capture_recall"] = sum(cap_recalls) / len(cap_recalls) if cap_recalls else 0.0
    m["abstention.recall"] = ab_recall
    m["abstention.over_rate"] = ab_over
    m["calibration.ece_eqwidth"] = ece_equiwidth(calib_pairs)
    m["calibration.ece_eqmass"] = ece_equimass(calib_pairs)
    m["calibration.brier"] = brier(calib_pairs)
    m["_n_answerable"] = len(cap_recalls)
    m["_n_abs"] = sum(1 for s, _ in abst_pairs if s)
    return m


async def lme_judged(subset, repeats=3):
    """Four-bucket attribution on natural questions (real model calls; NOT in CI)."""
    from anticipy_engine.core.env import load_local_env
    from anticipy_engine.core.gateway import CHEAP, PROVIDER_OPENROUTER, ModelGateway
    load_local_env()
    reader = ModelGateway(provider=PROVIDER_OPENROUTER, cheap_model=READER_MODEL, smart_model=READER_MODEL)
    judge = ModelGateway(provider=PROVIDER_OPENROUTER, cheap_model=JUDGE_MODEL, smart_model=JUDGE_MODEL)

    arts = []                                       # ingest each non-abs instance ONCE
    for inst in subset:
        if is_abs(inst):
            continue
        art = ingest_instance(inst)
        inj = Injector(art["lm"].memory, char_budget=10_000_000, k=50)
        out = inj.inject(inst["question"])
        nonloop = [i for i in out["items"] if i.kind != "open_loop"]   # loops are the spine, not retrieval
        retr_items = nonloop[:10]                                      # reader context: top-10 retrieved
        _, rall10 = lme_recall([i.id for i in nonloop], art["item_session"], art["gold_sessions"], 10)
        arts.append((inst, art, retr_items, rall10))

    async def read(probe, texts):
        ctx = "\n".join(f"- {t}" for t in texts) or "(no memories)"
        p = ("Answer the question using ONLY the user's stored memories below. If they do not "
             f"contain the answer, say you don't know.\nMEMORIES:\n{ctx}\n\nQUESTION: {probe}\nAnswer concisely:")
        return ((await reader.think(p, tier=CHEAP, caller="agent", temperature=0)) or "").strip()

    async def judged(ptype, q, gold, resp):
        raw = ((await judge.think(_judge_prompt(ptype, q, gold, resp), tier=CHEAP, caller="agent", temperature=0)) or "").lower()
        return ("yes" in raw) and ("no" not in raw.split())

    runs = []
    for _ in range(repeats):
        b = {"CAPTURE": 0, "RETRIEVAL": 0, "READER_CONTEXT": 0, "REASONING_CEILING": 0, "OK": 0, "noise": 0}
        oracle_ok = retr_ok = n = 0
        for inst, art, retr_items, rall10 in arts:
            n += 1
            q, gold_ans, ptype = inst["question"], inst["answer"], inst["question_type"]
            if art["gold_total"] > 0 and not art["gold_item_ids"]:
                b["CAPTURE"] += 1
                continue
            try:
                o = await judged(ptype, q, gold_ans, await read(q, art["gold_turn_texts"]))     # ungated gold ceiling
                r = await judged(ptype, q, gold_ans, await read(q, [i.text for i in retr_items]))
            except Exception:
                b["noise"] += 1
                continue
            oracle_ok += o
            retr_ok += r
            # honest precedence: if even ungated gold context fails, it's a reasoning/judge
            # ceiling, NOT retrieval's fault -> check that first; only blame RETRIEVAL when oracle could.
            bucket = ("REASONING_CEILING" if not o else "RETRIEVAL" if rall10 == 0
                      else "READER_CONTEXT" if not r else "OK")
            b[bucket] += 1
        runs.append({"buckets": b, "n": n, "oracle_acc": oracle_ok / n if n else 0.0,
                     "retr_acc": retr_ok / n if n else 0.0})
    return {"judge_model": JUDGE_MODEL, "reader_model": READER_MODEL, "repeats": repeats, "n": len(arts),
            "runs": runs, "model_cost_usd": round(reader.total_cost() + judge.total_cost(), 4),
            "reader_calls": len(reader.calls), "judge_calls": len(judge.calls),
            "cost_basis": "gateway flat-rate estimate (cheap=$0.0005, smart=$0.02 per call); "
                          "OpenRouter dashboard is the billed source of truth",
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


def print_lme_scorecard(agg, det):
    def g(k): return agg.get(k, {}).get("mean", float("nan"))
    print("\n==== LONGMEMEVAL SUBSET — DETERMINISTIC CORE (session-reconciled; zero model calls) ====")
    print(f"  answerable={int(round(g('_n_answerable')))}  abstention={int(round(g('_n_abs')))}")
    print("  RETRIEVAL recall (session granularity; effective_k = first k UNIQUE sessions, loops excluded):")
    for k in KS:
        print(f"    recall_any@{k:<2} = {g(f'recall_any@{k}'):.3f}   recall_all@{k:<2} = {g(f'recall_all@{k}'):.3f}")
    print(f"  CAPTURE-RECALL (gold turns surviving the keep/drop gate) = {g('capture_recall'):.3f}")
    print("  recall_all@10 by question-type:")
    for key in sorted(k for k in agg if k.startswith("recall_all@10::")):
        print(f"    {key.split('::')[1]:<26} = {agg[key]['mean']:.3f}")
    print(f"  ABSTENTION:  recall = {g('abstention.recall'):.3f}   over_abstention = {g('abstention.over_rate'):.3f}")
    print(f"  CALIBRATION: ECE(eqwidth)={g('calibration.ece_eqwidth'):.3f}  ECE(eqmass)={g('calibration.ece_eqmass'):.3f}  Brier={g('calibration.brier'):.3f}")


def print_lme_attribution(j):
    runs = j["runs"]
    cats = ["OK", "CAPTURE", "RETRIEVAL", "READER_CONTEXT", "REASONING_CEILING", "noise"]
    mean_b = {c: statistics.fmean([r["buckets"].get(c, 0) for r in runs]) for c in cats}
    oracle = statistics.fmean([r["oracle_acc"] for r in runs])
    retr = statistics.fmean([r["retr_acc"] for r in runs])
    labels = {
        "OK":                "retrieved -> reader answered correctly",
        "CAPTURE":           "keep/drop gate dropped ALL gold turns",
        "RETRIEVAL":         "captured, but gold session not in top-10",
        "READER_CONTEXT":    "gold retrieved, but reader missed it",
        "REASONING_CEILING": "even ungated gold context fails (reader/judge limit)",
        "noise":             "judge/reader error",
    }
    print(f"  judge={j['judge_model']}  reader={j['reader_model']}  n={j['n']}  repeats={len(runs)}")
    print(f"  reasoning ceiling (oracle acc)  = {oracle:.3f}")
    print(f"  retrieved accuracy              = {retr:.3f}")
    print(f"  retrieval-attributable loss     = {max(0.0, oracle - retr):.3f}")
    print(f"  FOUR-BUCKET ATTRIBUTION (mean count over repeats; n per repeat = {j['n']}):")
    for c in cats:
        print(f"    {c:<18} {mean_b[c]:>5.1f}   ({labels[c]})")
    print(f"  model calls      = {j.get('reader_calls', 0)} reader + {j.get('judge_calls', 0)} judge "
          f"= {j.get('reader_calls', 0) + j.get('judge_calls', 0)} total")
    print(f"  model cost (USD) = {j['model_cost_usd']}  (gateway flat-rate estimate; "
          f"OpenRouter dashboard = billed source of truth)")


def run_lme(args):
    if not LME_HAYSTACK.exists():
        print(f"  LongMemEval haystack not found at {LME_HAYSTACK} (set LONGMEMEVAL_DIR). Cannot run --lme.")
        sys.exit(3)
    mode = os.environ.get("ANTICIPY_MEMORY_MODE", "stub")
    live = mode == "live"
    data = load_lme()
    scope = "FULL-500" if args.full else f"SUBSET-{args.subset}"
    det_set = data if args.full else sample_subset(data, args.subset, args.seed)
    n_abs = sum(1 for x in det_set if is_abs(x))
    print(f"=== LONGMEMEVAL {scope} SCORECARD (external hard yardstick) ===")
    print(f"  memory_mode    = {mode}" + (f"  embedder={LIVE_MODEL_ID} (dim {embedding_dim()})" if live else "  embedder=hash-stub (dim 256)"))
    print(f"  haystack       = {LME_HAYSTACK}")
    print(f"  dataset sha256 = {lme_dataset_sha()}")
    print(f"  loaded {len(data)} instances; deterministic set = {len(det_set)} "
          f"(answerable={len(det_set) - n_abs}, abstention={n_abs}; seed={args.seed})")

    # DETERMINISTIC layer — single pass over the WHOLE det set (zero reader/judge calls;
    # embedder-only under live, local + free of API spend; ~0 variance by construction).
    sc = Scorecard(Path(tempfile.mkdtemp()) / "lme_scorecard.jsonl")
    det = lme_deterministic(det_set, scorecard=sc)
    agg = aggregate([det])
    print_lme_scorecard(agg, det)

    # JUDGED layer — stratified ANSWERABLE sample ONLY (never all 500), flag-gated, paid calls.
    judged = None
    judge_pool = (sample_judged(data, args.judge_subset, args.seed) if args.full
                  else [x for x in det_set if not is_abs(x)][:args.judge_subset])
    if args.judge or os.environ.get("ANTICIPY_EVAL_JUDGE") == "live":
        proj = len(judge_pool) * args.judge_repeats * 4   # 2 reads + 2 judges per instance per repeat
        print(f"\n=== JUDGED LAYER (pinned judge; real model calls) ===")
        print(f"  stratified answerable sample = {len(judge_pool)} across "
              f"{len({x['question_type'] for x in judge_pool})} types x {args.judge_repeats} repeats")
        print(f"  PROJECTED paid calls = {len(judge_pool)} x {args.judge_repeats} x 4 = {proj}   [ceiling ~200]")
        if proj > 200:
            print(f"  !! {proj} > 200-call ceiling -> NOT running judged (report only). "
                  f"Set --judge-subset <= {200 // (args.judge_repeats * 4)} to fit.")
        else:
            judged = asyncio.run(lme_judged(judge_pool, repeats=args.judge_repeats))
            print_lme_attribution(judged)

    manifest = {
        "harness_git_sha": _git_sha(),
        "memory_version": "phase2a-longmemeval",
        "scope": scope,
        "n_instances": len(det_set),
        "memory_mode": mode,
        "embed_model": (LIVE_MODEL_ID if live else "hash-stub"),
        "embed_dim": (embedding_dim() if live else 256),
        "longmemeval_dataset_sha256": lme_dataset_sha(),
        "subset_ids": (None if args.full else [x["question_id"] for x in det_set]),
        "judged_sample_ids": [x["question_id"] for x in judge_pool],
        "seeds": [args.seed],
        "temperature": 0,
        "judge_model_id": JUDGE_MODEL if judged else None,
        "judge_prompt_sha256": judged["judge_prompt_sha256"] if judged else None,
        "reader_model_id": READER_MODEL if judged else None,
    }
    result = {
        "run_manifest": manifest,
        "per_category": agg,
        "raw_runs": [det],
        "judged": judged,
        "baseline_ref": None,
        "model_cost_usd": (judged["model_cost_usd"] if judged else 0.0),
    }
    tag = ("full_" if args.full else "") + mode
    out = Path(args.out if args.out != ".anticipy-data/memory_eval.json"
               else f".anticipy-data/memory_eval_lme_{tag}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  versioned JSON -> {out}")
    print(f"  TOTAL MODEL COST (USD) = {result['model_cost_usd']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default=".anticipy-data/memory_eval.json")
    ap.add_argument("--lme", action="store_true", help="run the LongMemEval external subset baseline")
    ap.add_argument("--full", action="store_true", help="LME deterministic core over ALL instances (full 500), not a subset")
    ap.add_argument("--subset", type=int, default=50, help="LME deterministic subset size")
    ap.add_argument("--judge-subset", type=int, default=12, help="LME judged subset size (answerable only)")
    ap.add_argument("--judge-repeats", type=int, default=3, help="LME judged repeats")
    args = ap.parse_args()

    if args.selftest:
        print("=== SELF-TEST (instrument soundness; zero model calls) ===")
        sys.exit(0 if selftest() else 1)

    if args.lme:
        run_lme(args)
        return

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
