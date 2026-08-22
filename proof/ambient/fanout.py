#!/usr/bin/env python3
"""Run one ambient corpus across every voice lane at once, then merge.

    ~/.anticipy-rig/venv/bin/python proof/ambient/fanout.py \
        --corpus proof/ambient/corpus.big.json --label round1

    ~/.anticipy-rig/venv/bin/python proof/ambient/fanout.py --label round1 --merge-only

WHY. proof/ambient/run.py pushes ONE utterance at a time and waits for the
brain to stamp it, because there is a live model behind this and a stampede
measures the provider's rate limiter instead of the brain. Measured on this
box: 31 seconds per line. A thousand-line corpus is therefore about nine hours
serially, which is not a thing anybody runs twice, and "run it again and see if
it still holds" is the entire point of this exercise.

Six lanes make it about ninety minutes, and they are genuinely independent:
separate owner, separate worker process, separate memory database, separate
clock file. Nothing is shared except PocketBase and the model key.

WHAT IT DOES NOT DO: it does not shard a CONVERSATION. Lines that share a
`convo` id are context for each other — brain/segmenter.py glues them into one
segment on purpose — so splitting them across lanes would feed half a
conversation to a worker that never heard the other half, and the later turns
of a retraction would be graded as if the retraction never happened. Whole
conversations move together; only the solo lines are free to be dealt round.

SEEDED MEMORY. Every lane starts from the same three facts the rig seeds, so a
line that leans on "the place I always go" resolves the same way in lane 6 as
in lane 1. Without this the same utterance scores differently depending on
which lane happened to draw it, which would make every A/B meaningless.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RIG = os.environ.get("ANTICIPY_RIG_DIR", os.path.expanduser("~/.anticipy-rig"))
PY = os.path.join(RIG, "venv", "bin", "python")
REGISTRY = os.path.join(RIG, "state", "lanes.json")

SEED_FACTS = [
    "he always books the Coal Harbour location, never the downtown one",
    "he prefers a table by the window",
    "dinner is usually the two of them, not a group",
]


def voice_lanes() -> list:
    if not os.path.exists(REGISTRY):
        sys.exit("no lanes: run `python proof/lanes.py provision voice 6` first")
    reg = json.load(open(REGISTRY))
    lanes = [v for v in reg.values() if v.get("kind") == "voice"]
    lanes.sort(key=lambda l: l["tag"])
    if not lanes:
        sys.exit("no voice lanes provisioned")
    return lanes


def seed_memory(lane: dict) -> None:
    """Same three facts in every lane, and only once per lane."""
    if os.path.exists(lane["memory_db"]):
        return
    code = (
        "import sys, os;"
        f"sys.path.insert(0, {REPO!r});"
        "from brain.memory import Memory;"
        f"m = Memory(path={lane['memory_db']!r});"
        f"[m.remember_fact(f, importance=5, source='interview', confidence=0.95) for f in {SEED_FACTS!r}]"
    )
    subprocess.run([PY, "-c", code], check=True, capture_output=True)


def shard(corpus: list, n: int) -> list:
    """Deal the corpus into n shards, keeping conversations whole.

    Longest-first by conversation size, each group to whichever shard is
    currently smallest. Plain round-robin would leave one lane holding every
    five-turn conversation and finishing twenty minutes after the rest.
    """
    groups = defaultdict(list)
    for item in corpus:
        key = item.get("convo") or f"solo:{item['id']}"
        groups[key].append(item)
    for g in groups.values():
        g.sort(key=lambda i: i.get("turn", 0))
    ordered = sorted(groups.values(), key=len, reverse=True)
    shards = [[] for _ in range(n)]
    for g in ordered:
        smallest = min(range(n), key=lambda i: len(shards[i]))
        shards[smallest].extend(g)
    return shards


def start_worker(lane: dict, key: str, model: str, log: str):
    env = dict(os.environ)
    # EVERY credential that could reach a real person goes, and the list has to
    # grow with the code (proof/local_rig.sh:214-223 explains why each one is
    # here). A laptop worker that inherited production Twilio credentials once
    # repointed the owner's live number at 127.0.0.1.
    for gone in ("BRAVE_API_KEY", "GEMINI_API_KEY", "ANTICIPY_SERVICE_TOKEN",
                 "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER",
                 "TWILIO_FROM", "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET"):
        env.pop(gone, None)
    env.update({
        "TWILIO_MOCK": "true",
        "ANTICIPY_PB": "http://127.0.0.1:8090",
        "ANTICIPY_OWNER_REF": lane["owner_ref"],
        "ANTICIPY_OWNER_ID": lane["owner_id"],
        "ANTICIPY_TZ": "America/Vancouver",
        "OPENROUTER_API_KEY": key,
        # An A/B of two models has to be settable without editing .env.local,
        # or the "control" run and the "variant" run are reading a file that
        # somebody changed in between. Environment wins; .env.local is the
        # default.
        "ANTICIPY_MODEL": os.environ.get("ANTICIPY_MODEL") or model,
        "ANTICIPY_AUX_MODEL": os.environ.get("ANTICIPY_AUX_MODEL", ""),
        "ANTICIPY_MEMORY_DB": lane["memory_db"],
        "ANTICIPY_CLOCK_STATE": lane["clock_state"],
        "ANTICIPY_SEGMENTS": "1",
    })
    fh = open(log, "a")
    return subprocess.Popen([PY, "-u", "-m", "brain.worker"], cwd=REPO, env=env,
                            stdout=fh, stderr=subprocess.STDOUT,
                            start_new_session=True)


def env_value(name: str) -> str:
    path = os.path.join(REPO, ".env.local")
    for line in open(path):
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"\'')
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus.json"))
    ap.add_argument("--label", required=True, help="names this round's outputs")
    ap.add_argument("--lanes", type=int, default=0, help="0 = every voice lane")
    ap.add_argument("--gap", type=float, default=1.0)
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--limit", type=int, default=0, help="first N of the corpus")
    ap.add_argument("--merge-only", action="store_true",
                    help="just merge the shard files already on disk")
    ap.add_argument("--keep-workers", action="store_true",
                    help="leave the per-lane workers running afterwards")
    args = ap.parse_args()

    lanes = voice_lanes()
    if args.lanes:
        lanes = lanes[:args.lanes]
    outdir = os.path.join(HERE, "rounds", args.label)
    os.makedirs(outdir, exist_ok=True)
    merged = os.path.join(outdir, "results.jsonl")

    def merge() -> int:
        rows, seen = [], set()
        for lane in lanes:
            path = os.path.join(outdir, f"{lane['tag']}.jsonl")
            if not os.path.exists(path):
                continue
            for line in open(path):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("id") in seen:
                    continue
                seen.add(r["id"])
                rows.append(r)
        rows.sort(key=lambda r: r.get("id", ""))
        with open(merged, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(f"merged {len(rows)} rows -> {merged}")
        return len(rows)

    if args.merge_only:
        merge()
        return 0

    corpus = json.load(open(args.corpus))
    if args.limit:
        corpus = corpus[:args.limit]
    shards = shard(corpus, len(lanes))
    print(f"{len(corpus)} utterances across {len(lanes)} lane(s): "
          + ", ".join(f"{l['tag']}={len(s)}" for l, s in zip(lanes, shards)))

    key, model = env_value("OPENROUTER_API_KEY"), env_value("ANTICIPY_MODEL")
    if not key:
        sys.exit("no OPENROUTER_API_KEY in .env.local")

    workers, runs = [], []
    try:
        for lane, part in zip(lanes, shards):
            seed_memory(lane)
            wlog = os.path.join(outdir, f"{lane['tag']}.worker.log")
            workers.append(start_worker(lane, key, model, wlog))
        # A worker needs a moment to print `worker up` and start polling; a
        # corpus pushed into the gap sits unanswered and burns the timeout.
        time.sleep(8)
        for lane, part in zip(lanes, shards):
            ids = os.path.join(outdir, f"{lane['tag']}.ids")
            with open(ids, "w") as fh:
                fh.write("\n".join(i["id"] for i in part) + "\n")
            out = os.path.join(outdir, f"{lane['tag']}.jsonl")
            log = open(os.path.join(outdir, f"{lane['tag']}.run.log"), "a")
            env = dict(os.environ)
            # PIN THE BACKEND. .env.local carries ANTICIPY_PB pointing at
            # production, and anything that inherits this shell inherits that.
            # run.py refuses a non-loopback host outright (which is how this
            # was caught rather than discovered later in somebody's real
            # queue), so the value has to be corrected here, not merely hoped
            # about. The same reasoning as the worker env above.
            env["ANTICIPY_PB"] = "http://127.0.0.1:8090"
            env["ANTICIPY_OWNER_REF"] = lane["owner_ref"]
            runs.append(subprocess.Popen(
                [PY, "-u", os.path.join(HERE, "run.py"),
                 "--pb", "http://127.0.0.1:8090",
                 "--corpus", args.corpus, "--only", f"@{ids}", "--out", out,
                 "--fresh", "--gap", str(args.gap),
                 "--timeout", str(args.timeout),
                 "--owner-ref", lane["owner_ref"]],
                cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True))
        print("lanes running. Progress:  wc -l " + os.path.join(outdir, "*.jsonl"))
        for p in runs:
            p.wait()
    finally:
        if not args.keep_workers:
            for w in workers:
                w.terminate()
            for w in workers:
                try:
                    w.wait(timeout=10)
                except Exception:
                    w.kill()
    n = merge()
    print(f"\nNow: {PY} proof/ambient/score.py --corpus {args.corpus} "
          f"--results {merged}")
    return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
