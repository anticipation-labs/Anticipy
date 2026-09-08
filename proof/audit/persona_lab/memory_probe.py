"""Recheck production extraction/storage for every fictional owner.

Uses real model judgments, separate durable SQLite stores and the frozen
transcripts. No transport, job executor or live account is involved.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from brain import llm
from brain.memory import Memory
from proof.audit.model_gateway import atomic_json
from proof.audit.run_transcripts import isolated_network

def main():
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);args=p.parse_args()
    output=ROOT/'work/audit/persona-lab'/args.label;output.mkdir(exist_ok=False)
    run='persona-lab/memory-probe/'+args.label
    llm.OPENROUTER_URL='http://127.0.0.1:8790/api/v1/chat/completions?audit_run='+quote(run,safe='')
    sys.addaudithook(isolated_network)
    corpus=Path(__file__).with_name('corpus.json')
    results=[]
    for person in json.loads(corpus.read_text())['personas']:
        model=llm.LLM(api_key=(ROOT/'work/audit/gateway-token').read_text().strip(),model='deepseek/deepseek-v3.2',owner_name=person['name'])
        model.gemini_api_key=None
        path=output/(person['id']+'.db');memory=Memory(path)
        for fact in person['memories']:memory.remember_fact(fact,source='interview')
        memory.llm=model
        result=memory.ingest(person['transcript'],speaker='owner')
        before=list(memory.db.execute('SELECT id,type,name,status FROM nodes ORDER BY id'))
        memory.db.close();memory=Memory(path)
        restart_equal=before==list(memory.db.execute('SELECT id,type,name,status FROM nodes ORDER BY id'))
        memory.db.close()
        results.append({'person':person['id'],'extraction':result,'nodes':before,'restart_equal':restart_equal})
        atomic_json(output/'results.json',{'scope':__doc__,'corpus_sha256':hashlib.sha256(corpus.read_bytes()).hexdigest(),'cases':results})
        print(person['id'],result.get('commitment'),flush=True)
    ledger=json.loads((ROOT/'work/audit/spend.json').read_text())
    calls=[c for c in ledger['calls'] if c.get('audit_run')==run]
    atomic_json(output/'results.json',{'scope':__doc__,'cases':results,'model_calls':len(calls),
        'model_cost_usd':sum(c.get('cost_usd') or 0 for c in calls),'model_call_ids':[c['id'] for c in calls]})

if __name__=='__main__':main()
