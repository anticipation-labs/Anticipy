"""Exercise direct-input selection against the real API with disposable owners.

No model, provider or message calls. This proves the query and tenant boundary;
the scheduling test executes the main-loop section under a simulated clock.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace

from brain import worker as W
from brain.conversation import Conversation
from proof.audit.live_api_release import request

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',choices=['http://127.0.0.1:8788','https://api.anticipy.ai'],required=True)
    parser.add_argument('--label',required=True)
    args=parser.parse_args()
    output=ROOT/'work/audit'/(args.label+'.json')
    if output.exists():raise RuntimeError('Use a new evidence label')
    if args.base.startswith('http://127.'):
        service='persona-lab-local-only'
    else:
        service=json.loads((ROOT/'work/audit/secrets.json').read_text())['ANTICIPY_SERVICE_TOKEN']
    os.environ['ANTICIPY_SERVICE_TOKEN']=service
    W.PB=args.base
    credentials=[];evidence={'scope':__doc__,'base':args.base,'messages_sent':0,'model_calls':0,'checks':[]}
    def call(method,path,data=None,token=None):
        code,body,_=request(args.base,method,path,data,token,
            None if token else {'X-Anticipy-Token':service,'X-Anticipy-Worker':'1'})
        if code!=200:raise RuntimeError(f'{method} {path.split("?")[0]} HTTP {code}')
        return body
    try:
        for i in range(2):
            email='priority-'+secrets.token_hex(12)+'@anticipy-test.invalid'
            password=secrets.token_urlsafe(32)
            owner=call('POST','/api/collections/owners/records',{'email':email,'password':password,'passwordConfirm':password})
            login=call('POST','/api/collections/owners/auth-with-password',{'identity':email,'password':password})
            credentials.append((owner['id'],login['token']))
        owner,other=[x[0] for x in credentials]
        now=datetime.now(timezone.utc)
        def event(kind,source,minutes,who=owner,decision=''):
            return call('POST','/api/collections/events/records',{'owner_ref':who,'device_id':'reply-priority-fixture',
                'kind':kind,'source':source,'text':'Fictional scheduling fixture; no request to act.',
                'decision':decision,'capture_started_at':(now-timedelta(minutes=minutes)).isoformat()})
        ambient=event('transcript','phone_mic',4)
        event('transcript','phone_mic',4,who=other)
        sms=event('sms_reply','typed',1)
        typed=event('transcript','typed',2)
        app=event('app_reply','typed',3)
        future=event('transcript','phone_mic',0)
        event('app_reply','typed',5,decision='ignore')
        event('app_reply','typed',6,who=other)
        rows=W.fetch_direct_inputs(owner)
        assert [r['id'] for r in rows]==[app['id'],typed['id'],sms['id']], 'Selection/order mismatch'
        assert all(r['owner_ref']==owner for r in rows),'Cross-owner input'
        conversation=Conversation(SimpleNamespace(owner_ref=owner,backend_url=args.base,llm=None))
        conversation._incoming_event=typed
        context=conversation._captured_context()
        assert [r['id'] for r in context]==[ambient['id']], 'Captured source/time isolation mismatch'
        assert future['id'] not in str(context)
        evidence['checks']=['app, typed composer and SMS are selected together',
            'capture order survives different arrival order',
            'ambient speech and already processed rows are excluded',
            'another owner is excluded',
            'prior unprocessed speech reaches context; later speech and other owners do not']
        evidence['passed']=True
    except Exception as error:
        evidence.update(passed=False,error=str(error));raise
    finally:
        cleaned=[]
        for owner,token in credentials:
            code,body,_=request(args.base,'POST','/me/delete',{'confirm':'delete'},token)
            cleaned.append(code==200 and body.get('account_deleted') is True)
        evidence['fixture_accounts_removed']=len(cleaned)
        evidence['cleaned_up']=bool(cleaned) and all(cleaned)
        evidence['checked_utc']=datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps(evidence))
        if not evidence['cleaned_up']:raise RuntimeError('Fixture cleanup incomplete')


if __name__=='__main__':main()
