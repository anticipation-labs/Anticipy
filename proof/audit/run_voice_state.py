"""Synthetic voice-state replay through Anticipy._voice and the paid audit gateway.
Four concurrent calls fit the gateway's conservative full-context reservations.
Outputs require semantic review, not substring-based scoring.
"""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path
import json, os
from brain import llm
from brain.anticipy_core import Anticipy
from brain.memory import Memory
from proof.audit.model_gateway import atomic_json
import argparse
parser=argparse.ArgumentParser(); parser.add_argument("--label", required=True); args=parser.parse_args()
S=Path(__file__).resolve().parents[2]/"work/audit"
if (S/(args.label+".json")).exists(): raise SystemExit("Use a new label to preserve evidence")
from urllib.parse import quote
llm.OPENROUTER_URL="http://127.0.0.1:8790/api/v1/chat/completions?audit_run="+quote(args.label,safe="")
key=(S/"gateway-token").read_text().strip()
contexts=[
{"situation":"their very first minutes with you; introduce yourself warmly", "their_name":"Amira", "what_you_do":"listen, remember what matters, and handle errands with approval"},
{"situation":"acknowledge the task", "goal":"compare the two supplier proposals", "execution":{"status":"queued", "verified_results":[]}},
{"situation":"acknowledge the task", "goal":"create a reminder for tomorrow morning", "execution":{"status":"awaiting_confirm", "verified_results":[]}},
{"situation":"acknowledge the task", "goal":"draft a reply to the client", "execution":{"status":"running", "verified_results":[]}},
]
def run(pair):
 i,c=pair
 primary=llm.LLM(api_key=key,owner_name="Amira",owner_email="amira@example.invalid",owner_zone="America/Vancouver")
 primary.gemini_api_key=None
 strong=llm.LLM(api_key=key,model="google/gemini-3.1-pro-preview")
 strong.gemini_api_key=None
 a=Anticipy.__new__(Anticipy); a.llm=primary; a.brain=SimpleNamespace(strong=strong); a.memory=Memory()
 return {"case":i,"context":c,"reply":a._voice(c)}
with ThreadPoolExecutor(max_workers=4) as pool:
 results=list(pool.map(run,[(i,c) for i,c in enumerate(contexts) for _ in range(3)]))
atomic_json(S/(args.label+".json"),results)
for r in results: print(json.dumps(r))

raise SystemExit(0 if all(r["reply"] for r in results) else 1)
