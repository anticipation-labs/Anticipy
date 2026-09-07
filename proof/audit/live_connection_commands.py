"""Live stored-event dispatch, real models/catalog, own phone-less fixture only.

Mints owner-bound connect links but does not redeem them, connect accounts,
message a phone, or access a real mailbox. Reserves $2 from the existing native
API audit ceiling before any invocation. Never resets either spending ledger.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
from urllib.parse import urlencode

from proof.audit.live_api_release import request
from proof.audit.model_gateway import atomic_json

ROOT=Path(__file__).resolve().parents[2]
BASE='https://api.anticipy.ai'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--label', required=True)
    parser.add_argument('--revision', required=True)
    args=parser.parse_args()
    file=ROOT/'work/audit'/f'{args.label}.json'
    private=file.with_name(args.label+'-private.json')
    if file.exists() or private.exists(): raise RuntimeError('Fresh label required')
    status,_,headers=request(BASE,'GET','/api/health')
    if status!=200 or headers.get('x-anticipy-revision')!=args.revision:
        raise RuntimeError('Expected API source is not live')
    budget_file=ROOT/'work/audit/overnight-live-browser-budget.json'
    lock=str(budget_file)+'.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        budget=json.loads(budget_file.read_text())
        if budget['reserved_upper_bound_usd']+2>budget['limit_usd']: raise RuntimeError('Native API ceiling reached')
        budget['reserved_upper_bound_usd']+=2
        budget['calls'].append({'label':args.label,'at':datetime.now(timezone.utc).isoformat(),
            'scope':'at most five small connection commands plus idempotent replays; no paid vendor effects',
            'upper_bound_usd':2})
        atomic_json(budget_file,budget)
    finally:
        os.close(fd);os.unlink(lock)
    service=json.loads((ROOT/'work/audit/secrets.json').read_text())['ANTICIPY_SERVICE_TOKEN']
    fixture={'email':'connections-'+secrets.token_hex(12)+'@anticipy-test.invalid',
        'password':secrets.token_urlsafe(32),'base':BASE}
    atomic_json(private,fixture)
    evidence={'scope':__doc__,'revision':args.revision,'cases':[],'cleaned_up':False}
    def call(method,path,body=None,as_service=False):
        status,out,_=request(BASE,method,path,body,None if as_service else fixture.get('token'),
            {'X-Anticipy-Token':service,'X-Anticipy-Worker':'1'} if as_service else None)
        if status!=200: raise RuntimeError(f'{method} {path.split("?")[0]} returned {status}')
        return out
    def event(text,kind='app_reply',goal=''):
        return call('POST','/api/collections/events/records',{'kind':kind,'text':text,'goal':goal,
            'source':'typed','device_id':'isolated-connection-audit','owner_ref':fixture['owner_ref'],
            'decision':'processing' if kind=='app_reply' else 'ignore'},True)
    try:
        owner=call('POST','/api/collections/owners/records',dict(email=fixture['email'],password=fixture['password'],passwordConfirm=fixture['password']))
        fixture['owner_ref']=owner['id'];atomic_json(private,fixture)
        auth=call('POST','/api/collections/owners/auth-with-password',{'identity':fixture['email'],'password':fixture['password']})
        fixture['token']=auth['token'];atomic_json(private,fixture)
        cases=[('list','Which of my apps are connected?','list_connections'),
               ('connect','Please connect my Gmail.','connect'),
               ('accept-context','Yes, please.','connect'),
               ('quoted-command','The note says "disconnect Gmail". Explain what that means; do not change my connections.','not_for_us'),
               ('targeted-card','Yes, please.','not_for_us')]
        for name,text,want in cases:
            goal=''
            if name=='accept-context': event('Would you like to connect Google Calendar?','anticipy_text')
            if name=='targeted-card':
                event('Would you like to connect Gmail?','anticipy_text')
                job=call('POST','/api/collections/jobs/records',{'goal':'Schedule design review','status':'needs_user',
                    'result':'Does 4 PM work?','owner_ref':fixture['owner_ref'],'device_id':'isolated-connection-audit'},True)
                goal=json.dumps({'reply_to_job_id':job['id']})
            ev=event(text,goal=goal)
            out=call('POST','/worker/connection-command',{'event_id':ev['id'],'owner_ref':fixture['owner_ref']},True)
            replay=call('POST','/worker/connection-command',{'event_id':ev['id'],'owner_ref':fixture['owner_ref']},True)
            filt=f'owner_ref="{fixture["owner_ref"]}" && parent_line="{ev["id"]}" && kind="anticipy_text"'
            rows=call('GET','/api/collections/events/records?'+urlencode({'filter':filt,'perPage':20}),as_service=True)['items']
            got=(out.get('outcome')or{}).get('kind')
            has_link=any('https://api.anticipy.ai/c/' in row.get('text','') for row in rows)
            passed=out.get('status')=='completed' and got==want and replay==out and len(rows)==(0 if want=='not_for_us' else 1) and (want!='connect' or has_link)
            evidence['cases'].append({'id':name,'expected':want,'actual':got,'passed':passed,'reply_count':len(rows),
                'replay_identical':replay==out,'link_present':has_link})
            atomic_json(file,evidence);print(json.dumps(evidence['cases'][-1]),flush=True)
    finally:
        if fixture.get('owner_ref'):
            if not fixture.get('token'):
                auth=call('POST','/api/collections/owners/auth-with-password',{'identity':fixture['email'],'password':fixture['password']})
                fixture['token']=auth['token'];atomic_json(private,fixture)
            cleaned=call('POST','/me/delete',{'confirm':'delete'})
            evidence['cleaned_up']=cleaned.get('account_deleted') is True
        atomic_json(file,evidence)
    if not evidence['cleaned_up'] or len(evidence['cases'])!=5 or not all(c['passed'] for c in evidence['cases']):
        raise SystemExit(1)

if __name__=='__main__': main()
