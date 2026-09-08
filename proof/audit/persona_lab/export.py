"""Export only this lab's synthetic evidence; never copy credential files."""
import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile
import re

ROOT=Path(__file__).resolve().parents[3]
STATE=ROOT/'work/audit/persona-lab'
OUT=ROOT/'research/overnight-2026-09-07'

def load(path):return json.loads(path.read_text())
def public(value):
    if isinstance(value,dict):return {k:public(v) for k,v in value.items() if k not in ('memory_path','evidenceShot')}
    if isinstance(value,list):return [public(v) for v in value]
    # Transport-only redaction: never publish even an expired fixture link token.
    if isinstance(value,str):return re.sub(r'https://api\.anticipy\.ai/c/[A-Za-z0-9_-]+', 'https://api.anticipy.ai/c/FIXTURE-LINK-REDACTED', value)
    return value

def main():
    corpus=load(Path(__file__).with_name('corpus.json'))
    selected={'asha':'memory-fixed','theo':'memory-fixed','camila':'memory-fixed','fatima':'final-fatima','tomas':'final-tomas'}
    people=[]
    for p in corpus['personas']:
        label=selected.get(p['id'],'context-fixed-1')
        result=load(STATE/label/p['id']/'result.json')
        assert result['runtime_completed'] and result['cleaned_up'] and not result['model_errors'],p['id']
        assert result['owner_scope_ok'] and result['memory_restart_equal'] and result['text_replay_added']==0
        people.append({'persona':p,'run_label':label,'result':public(result)})
    browsers=[]
    for name in ['mina-baseline','changed-prices','gallery-utf8','capacity','hostile-minutes','misleading-receipt','accessibility']:
        data=public(load(ROOT/'output/playwright'/('overnight-persona-'+name)/'result.json'))
        assert data['passed'],name
        browsers.append({'case':name,**data})
    ledger=load(ROOT/'work/audit/spend.json')
    calls=[c for c in ledger['calls'] if 'persona' in str(c.get('audit_run',''))]
    assert all(c.get('cost_usd') is not None for c in calls)
    checks={
        'personas':15,'transcript_words':sum(len(p['transcript'].split()) for p in corpus['personas']),
        'typed_followups':sum(len(p['replies']) for p in corpus['personas']),
        'clean_owner_runs':15,'memory_restart_checks':15,'outbox_replay_duplicates':0,
        'real_chrome_final_cases':len(browsers),'python_passed':3024,'python_skipped':2,
        'worker_suite_passed':True,'worker_typecheck_passed':True,
        'paid_calls_including_calibration_and_retests':len(calls),
        'model_cost_usd':sum(c['cost_usd'] for c in calls),
        'whole_audit_gateway_observed_usd':ledger['observed_cost_usd'],
    }
    # Retain the original failing observations alongside the successful retests.
    baseline={}
    for name in ['mina','asha','theo','fatima','camila','tomas']:
        path=STATE/'baseline-4'/name/'result.json'
        if path.exists():baseline[name]=public(load(path))
    evidence={'scope':'Synthetic lab; real model judgments and code, mocked external data and texting. See README/report for untested paths.',
        'repair_commit':'61db0e7dc7ca8c2cb7bad11bfa7f36d73aecc2ea','checks':checks,
        'personas':people,'baseline':baseline,
        'memory_probe':load(STATE/'memory-extraction-v2/results.json'),
        'browser':browsers,'connection_before':load(STATE/'connection-probe.json'),
        'connection_after':load(STATE/'connection-probe-fixed.json'),
        'api_faults':{'fatima_original':load(STATE/'fatima-api-fixed.json'),
                      'fatima_variant':load(STATE/'fatima-api-variant.json'),
                      'iris':load(STATE/'iris-api-fixed.json')},
        'api_synthesis':[load(STATE/'fatima-synthesis.json'),load(STATE/'iris-synthesis.json')],
        'invalid_lab_runs':['baseline-1: obsolete local service credential',
            'baseline-2: result serializer', 'baseline-3: strong model unavailable',
            'early baseline-4 routing: fixture omitted source from sensed hand context',
            'baseline-4 Leo, context-fixed-1 Fatima/Camila, final-camila: audit reservation 402; rerun without overlap',
            'initial gallery: private-place consent not yet supplied; UTF-8 content type added to fixtures',
            'memory-extraction-final: test queried obsolete SQLite column names; corrected probe is memory-extraction-v2']}
    (OUT/'persona-lab-evidence.json').write_text(json.dumps(public(evidence),indent=2,ensure_ascii=False)+'\n')
    archive=OUT/'persona-lab-memories.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in corpus['personas']:
            db=STATE/'memory-extraction-v2'/(p['id']+'.db')
            with sqlite3.connect(db) as connection:
                assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            z.write(db,p['id']+'/memory.db')
        z.writestr('README.txt','15 fictional SQLite memories. Final extraction probe, seeded notes plus long transcript; no real users or provider credentials. Transcript follow-up/task evidence is in persona-lab-evidence.json.\n')
    print(json.dumps(checks,indent=2));print('Memory archive SHA256:',hashlib.sha256(archive.read_bytes()).hexdigest())

if __name__=='__main__':main()
