"""Real Anticipy.hear, memory, Conversation and delivery; local Worker storage.

The harness substitutes sensed app availability and provider transports only.
No authored decision, expected outcome, or scoring rubric reaches a model.
This synchronous driver deliberately skips microphone decoding and polling waits;
it measures brain behavior, not capture latency or production scheduler health.
"""
import argparse
import dataclasses
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
BASE='http://127.0.0.1:8788'
STATE=ROOT/'work/audit/persona-lab'
CORPUS=Path(__file__).with_name('corpus.json')
SERVICE='persona-lab-local-only'

def json_value(value):
    if dataclasses.is_dataclass(value):return dataclasses.asdict(value)
    if hasattr(value,'value'):return value.value
    if hasattr(value,'isoformat'):return value.isoformat()
    raise TypeError(f'Unrecordable evidence type: {type(value).__name__}')

def child(person,label):
    import requests
    from unittest.mock import patch
    from proof.audit.run_transcripts import isolated_network
    from proof.audit.model_gateway import atomic_json as save
    from brain import llm,hands
    from brain.anticipy_core import Anticipy
    from brain.memory import Memory
    from brain.conversation import Conversation
    from brain.reply_delivery import ReplyDelivery
    from brain.task_delivery import TaskDelivery
    from brain.runtime_status import source_hash
    model_errors=[]
    original_chat=llm.LLM.chat
    def recorded_chat(client,*args,**kwargs):
        # Share the strong-model reservation across isolated persona processes.
        # Its conservative full-context reservation is much larger than actual
        # calls; serializing that tier respects the remaining audit budget.
        import contextlib
        import fcntl
        @contextlib.contextmanager
        def reservation_slot():
            if client.model == 'google/gemini-3.1-pro-preview':
                with (STATE/'strong-model.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    yield
            else:yield
        try:
            with reservation_slot():return original_chat(client,*args,**kwargs)
        except Exception as error:
            response=getattr(error,'response',None)
            model_errors.append({'type':type(error).__name__,'status':getattr(response,'status_code',None)})
            raise
    llm.LLM.chat=recorded_chat
    def atomic_json(path,value):save(path,json.loads(json.dumps(value,default=json_value)))
    sys.addaudithook(isolated_network)
    os.environ['ANTICIPY_SERVICE_TOKEN']=SERVICE
    run_dir=STATE/label/person['id']; run_dir.mkdir(parents=True,exist_ok=False)
    llm.OPENROUTER_URL='http://127.0.0.1:8790/api/v1/chat/completions?audit_run='+quote('persona-lab/'+label+'/'+person['id'],safe='')
    session=requests.Session();session.trust_env=False
    def call(method,path,data=None,auth=None):
        r=session.request(method,BASE+path,json=data,headers=({'Authorization':auth} if auth else {'X-Anticipy-Token':SERVICE,'X-Anticipy-Worker':'1'}),timeout=25)
        r.raise_for_status();return r.json()
    password=secrets.token_urlsafe(24);email=f"{label}-{person['id']}-{secrets.token_hex(4)}@anticipy-test.invalid"
    owner=call('POST','/api/collections/owners/records',{'email':email,'password':password,'passwordConfirm':password})
    auth=call('POST','/api/collections/owners/auth-with-password',{'identity':email,'password':password})['token']
    ref=owner['id'];atomic_json(run_dir/'identity-private.json',{'owner':ref,'token':auth})
    call('POST','/me/profile/upsert',{'name':person['name'],'timezone':person['timezone']},auth)
    def rows(collection):
        return call('GET',f'/api/collections/{collection}/records?filter='+quote(f'owner_ref="{ref}"')+'&perPage=500&sort=created')['items']
    def event(text,kind,source):
        return call('POST','/api/collections/events/records',{'owner_ref':ref,'device_id':'persona-lab','kind':kind,'text':text,'source':source,'speaker':'owner','decision':'','explicit':kind=='app_reply'})
    class TextSandbox:
        def __init__(self):self.sent=[]
        def send(self,to,body,media=None):
            r={'to':to,'body':body,'mock':True,'delivered':False,'media':media or []}
            self.sent.append(r);return r
    transport=TextSandbox()
    memory=Memory(run_dir/'memory.db')
    for fact in person['memories']:memory.remember_fact(fact,source='interview')
    memory.remember_fact(f"My name is {person['name']}; I work as a {person['role']}.",source='interview')
    memory.db.close()
    key=(ROOT/'work/audit/gateway-token').read_text().strip()
    # Production constructs additional model clients from this environment.
    # They must use the same metered transport, not an unavailable test double.
    os.environ['OPENROUTER_API_KEY']=key
    model=llm.LLM(api_key=key,model='deepseek/deepseek-v3.2',owner_name=person['name'],owner_zone=person['timezone'],owner_email=email)
    model.gemini_api_key=None
    memory=Memory(run_dir/'memory.db',llm=model)
    a=Anticipy(memory=memory,llm=model,backend_url=BASE,owner_id=ref,owner_ref=ref,owner_phone='mock:'+person['id'])
    delivery=ReplyDelivery(BASE,ref,transport,lambda:'mock:'+person['id'])
    conversation=Conversation(a,transport=transport);conversation.reply_delivery=delivery.publish
    a.conversation=conversation;a.task_delivery=TaskDelivery(delivery)
    tool={'slug':'WORKSPACE_SEARCH','name':'Search and read workspace records','description':'Search current documents, calendar entries, inspection or maintenance ledger records. Returns stable record IDs, exact source content, revisions and dates.',
          'toolkit':'workhub','tags':['readOnlyHint'],'input_parameters':{'type':'object','properties':{'query':{'type':'string'}},'required':['query']}}
    connected=person['lane']=='api' and person['id'] not in ('leo','priya')
    context=hands.HandContext(connections=(hands.ConnectedApp('workhub',alias='Document, calendar and maintenance workspace'),) if connected else (),
        browser_online=person['lane']=='browser',catalogs={'workhub':[tool]} if connected else {})
    def sensed_context(params=None,**kwargs):
        p=params or {}
        return dataclasses.replace(context,source=str(p.get('source') or ''),
            effect_channel=str((p.get('_effect') or {}).get('touches') or ''))
    result={'person':person['id'],'name':person['name'],'scope':__doc__,'source_sha256':source_hash(),'corpus_sha256':hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'memory_path':str(run_dir/'memory.db'),'memory_before':memory.profile_facts(),'steps':[],'texts':transport.sent,'model_errors':model_errors,'cleaned_up':False}
    started=time.monotonic()
    try:
        with patch.object(hands,'gather_context',side_effect=sensed_context):
            ev=event(person['transcript'],'transcript','phone_mic')
            start=time.monotonic()
            decision=a.hear(person['transcript'],explicit=False,capture_source='phone_mic',speaker='owner',source_event_id=ev['id'],lineage_key=ev['id'])
            result['steps'].append({'kind':'ambient','text':person['transcript'],'result':decision,'elapsed':time.monotonic()-start,'jobs':rows('jobs')})
            atomic_json(run_dir/'result.json',result)
            for job in rows('jobs'):
                if job['status'] in ('awaiting_confirm','needs_user') and job.get('result'):
                    a.task_delivery.publish(job,job['result'])
            for text in person['replies']:
                ev=event(text,'app_reply','typed'); start=time.monotonic()
                with conversation.from_event(ev):
                    reply=conversation.on_reply('mock:'+person['id'],text)
                delivery.sweep()
                result['steps'].append({'kind':'text_reply','text':text,'result':reply,'elapsed':time.monotonic()-start,'jobs':rows('jobs')})
                atomic_json(run_dir/'result.json',result)
            result['jobs']=rows('jobs');result['events']=rows('events');result['memory_after']=memory.profile_facts()
            memory.db.close();reopened=Memory(run_dir/'memory.db')
            def durable(facts):
                return sorted([{k:v for k,v in row.items() if k!='salience'} for row in facts],key=lambda row:row['id'])
            result['memory_restart_equal']=durable(reopened.profile_facts())==durable(result['memory_after']);reopened.db.close()
            result['owner_scope_ok']=all(row.get('owner_ref')==ref for row in result['jobs']+result['events'])
            before=len(transport.sent);delivery.sweep();delivery.sweep()
            result['text_replay_added']=len(transport.sent)-before
            result['runtime_completed']=True
    except Exception as e:
        result.update(runtime_completed=False,error=f'{type(e).__name__}: {e}')
        try:result['jobs']=rows('jobs');result['events']=rows('events')
        except Exception:pass
    finally:
        deleted=call('POST','/me/delete',{'confirm':'delete'},auth)
        result['cleaned_up']=deleted.get('account_deleted') is True
        result['elapsed_seconds']=time.monotonic()-started
        ledger=json.loads((ROOT/'work/audit/spend.json').read_text())
        calls=[c for c in ledger['calls'] if c.get('audit_run')=='persona-lab/'+label+'/'+person['id']]
        result['model_calls']=len(calls);result['model_call_ids']=[c['id'] for c in calls]
        result['model_cost_usd']=sum(c.get('cost_usd') or 0 for c in calls)
        result['unresolved_reservations']=sum(c['reserved_usd'] for c in calls if c.get('cost_usd') is None)
        atomic_json(run_dir/'result.json',result)
    print(json.dumps({k:result.get(k) for k in ['person','runtime_completed','error','model_calls','model_cost_usd','elapsed_seconds','cleaned_up']}),flush=True)
    return (result.get('runtime_completed') is True and result.get('cleaned_up') is True
            and not result.get('model_errors'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);parser.add_argument('--ids');parser.add_argument('--child',action='store_true');parser.add_argument('--held-out',action='store_true');args=parser.parse_args()
    data=CORPUS.read_bytes()
    if hashlib.sha256(data).hexdigest()!=CORPUS.with_suffix('.sha256.txt').read_text().strip():raise RuntimeError('Frozen corpus changed')
    people=json.loads(data)['personas'];selected=[p for p in people if not args.ids or p['id'] in args.ids.split(',')]
    if any(p['split']=='held_out' for p in selected) and not args.held_out:raise RuntimeError('Held-out cases require final evaluation flag')
    if args.child:
        if len(selected)!=1:raise RuntimeError('One owner per child process')
        raise SystemExit(0 if child(selected[0],args.label) else 1)
    def launch(p):
        log=STATE/(args.label+'-'+p['id']+'.log');log.parent.mkdir(parents=True,exist_ok=True)
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','TMPDIR')}
        env.update(PYTHONPATH=str(ROOT),PYTHONUNBUFFERED='1',ANTICIPY_MODEL='deepseek/deepseek-v3.2',ANTICIPY_STRONG_MODEL='google/gemini-3.1-pro-preview')
        cmd=[sys.executable,str(Path(__file__).resolve()),'--child','--label',args.label,'--ids',p['id']]+(['--held-out'] if args.held_out else [])
        with log.open('w') as out:
            try:r=subprocess.run(cmd,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=480)
            except subprocess.TimeoutExpired:print(p['id'],'HARNESS TIMEOUT',flush=True);return False
        result=STATE/args.label/p['id']/'result.json'
        d=json.loads(result.read_text()) if result.exists() else {'runtime_completed':False,'error':'child exit '+str(r.returncode)}
        print(p['id'],json.dumps({k:d.get(k) for k in ['runtime_completed','error','model_calls','elapsed_seconds']}),flush=True)
        return r.returncode==0 and d.get('runtime_completed') is True and not d.get('model_errors')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(launch,selected))
    raise SystemExit(0 if results and all(results) else 1)

if __name__=='__main__':main()
