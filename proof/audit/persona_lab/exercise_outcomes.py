"""Run actual API evidence through the production server composer/verifier.

This is an executor handoff probe, not a claim that a production polling worker
or live provider account ran. API evidence is produced by api_faults.ts using
the real provider parser and hand. Expected outcomes never enter model prompts.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from brain import llm,server_work
from proof.audit.model_gateway import atomic_json
from proof.audit.run_transcripts import isolated_network

def main():
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('output');p.add_argument('--faults',default='success,empty_records');args=p.parse_args()
    target=Path(args.output)
    if target.exists():raise RuntimeError('Use a new output name; retain original evidence')
    data=json.loads(Path(args.input).read_text())
    run='persona-lab/outcomes/'+target.stem
    llm.OPENROUTER_URL='http://127.0.0.1:8790/api/v1/chat/completions?audit_run='+quote(run,safe='')
    model=llm.LLM(api_key=(ROOT/'work/audit/gateway-token').read_text().strip(),model='google/gemini-3.1-pro-preview')
    model.gemini_api_key=None
    sys.addaudithook(isolated_network)
    results=[]
    for c in data['cases']:
        if c['fault'] not in args.faults.split(','):continue
        with (ROOT/'work/audit/persona-lab/strong-model.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            out=server_work.run(c['goal'],c['params'],model=model,
                research_runner=lambda *a: {'ok':False,'needs_user':True,'result':'No public lookup is connected in this isolated fixture.'},
                context={'api_outcome':c['outcome'],'api_disposition':c['disposition']})
        results.append({'person':c['person'],'job_id':c['job_id'],'fault':c['fault'],'goal':c['goal'],'result':out})
        atomic_json(target,{'scope':__doc__,'input_sha256':hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),'cases':results})
        print(json.dumps(results[-1]),flush=True)
    if not results:raise RuntimeError('No matching API cases')
    ledger=json.loads((ROOT/'work/audit/spend.json').read_text())
    calls=[c for c in ledger['calls'] if c.get('audit_run')==run]
    atomic_json(target,{'scope':__doc__,'input_sha256':hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
        'cases':results,'model_calls':len(calls),'model_cost_usd':sum(c.get('cost_usd') or 0 for c in calls),
        'model_call_ids':[c['id'] for c in calls]})

if __name__=='__main__':main()
