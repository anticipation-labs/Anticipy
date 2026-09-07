"""Join real model, production consent method and local workerd/D1.
Synthetic accounts only; local backend only; no browser or messaging execution.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
from urllib.parse import quote, urlsplit

from brain import llm
from brain.anticipy_core import Anticipy
from brain.memory import Memory
from proof.audit.live_api_release import request
from proof.audit.model_gateway import atomic_json
from proof.audit.run_spoken_consent import CASES


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--label',required=True)
    parser.add_argument('--base',default='http://127.0.0.1:8787'); args=parser.parse_args()
    if urlsplit(args.base).hostname not in ('127.0.0.1','localhost'):
        raise SystemExit('This proof may only mutate a loopback fixture backend')
    root=Path(__file__).resolve().parents[2]; state=root/'work/audit'
    output=state/(args.label+'.json')
    if output.exists(): raise SystemExit('Use a new label to preserve evidence')
    config=json.loads((root/'work/mac-dev/wrangler.json').read_text())
    os.environ['ANTICIPY_SERVICE_TOKEN']=config['vars']['ANTICIPY_SERVICE_TOKEN']
    llm.OPENROUTER_URL='http://127.0.0.1:8790/api/v1/chat/completions?audit_run='+quote(args.label,safe='')
    key=(state/'gateway-token').read_text().strip()
    def run(case):
        name,line,conversation,tasks,expected=case
        email='consent-'+secrets.token_hex(10)+'@anticipy-test.invalid'; password=secrets.token_urlsafe(32)
        status,owner,_=request(args.base,'POST','/api/collections/owners/records',
            {'email':email,'password':password,'passwordConfirm':password})
        assert status==200, (name,'signup',status)
        status,auth,_=request(args.base,'POST','/api/collections/owners/auth-with-password',{'identity':email,'password':password})
        assert status==200, (name,'login',status)
        token=auth['token']; ids={}
        try:
            for task in tasks:
                status,created,_=request(args.base,'POST','/api/collections/jobs/records',
                    {**task,'id':'','params':json.dumps(task['params']),'owner_ref':owner['id'],'lane':'research','device_id':'consent-wire'},token)
                assert status==200, (name,'create-task',status)
                ids[task['id']]=created['id']
            model=llm.LLM(api_key=key,model='google/gemini-3.1-pro-preview',owner_name='Amira',owner_email=email)
            model.gemini_api_key=None
            a=Anticipy(memory=Memory(':memory:'),llm=None,owner_ref=owner['id'],backend_url=args.base)
            a.llm=model; a.brain=SimpleNamespace(strong=model)
            released=a._release_freshest_held(line,context=conversation,speaker='owner')
            rows={}
            for symbol,id in ids.items():
                status,saved,_=request(args.base,'GET','/api/collections/jobs/records/'+id,token=token)
                assert status==200
                rows[symbol]={'status':saved['status'],'params':json.loads(saved['params'])}
            queued=[symbol for symbol,saved in rows.items() if saved['status']=='queued']
            passed=queued==([expected] if expected else []) and bool(released)==bool(expected)
            return {'case':name,'passed':passed,'expected_release':expected,'released_goal':released,'stored_tasks':rows}
        finally:
            status,deleted,_=request(args.base,'POST','/me/delete',{'confirm':'delete'},token)
            assert status==200 and deleted.get('account_deleted'), (name,'cleanup',status)
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(run,CASES))
    atomic_json(output,{'scope':'production consent method, real model, local HTTP and database; synthetic accounts deleted','results':results})
    for r in results: print(r['case'],'PASS' if r['passed'] else 'FAIL',flush=True)
    raise SystemExit(0 if all(r['passed'] for r in results) else 1)

if __name__=='__main__': main()
