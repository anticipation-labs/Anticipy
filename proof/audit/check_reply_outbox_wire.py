"""Real local Worker/D1 queue roundtrip; transport is a non-network recorder."""
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
import requests
from brain.reply_delivery import ReplyDelivery

base='http://127.0.0.1:8787'
config=json.loads(Path('work/mac-dev/wrangler.json').read_text())
os.environ['ANTICIPY_SERVICE_TOKEN']=config['vars']['ANTICIPY_SERVICE_TOKEN']
headers={'X-Anticipy-Token':os.environ['ANTICIPY_SERVICE_TOKEN'],'X-Anticipy-Worker':'1'}
name=uuid.uuid4().hex[:15]
password=uuid.uuid4().hex
created=requests.post(base+'/api/collections/owners/records',headers=headers,json={
    'email':f'{name}@example.invalid','password':password,'passwordConfirm':password},timeout=10)
created.raise_for_status()
owner=created.json()['id']
Path('work/audit/reply-wire-owner.json').write_text(json.dumps({'id':owner}))
sent=[]
def send(phone,body):
    sent.append(body)
    return {'sid':'local-recorder-only','delivered':False}
delivery=ReplyDelivery(base,owner,SimpleNamespace(send=send),lambda:'+15555550101')
try:
    event={'id':name,'owner_ref':owner,'source':'typed'}
    delivery.publish(event,'Synthetic reply wire proof; no handset contacted.')
    delivery.publish(event,'Duplicate model wording must not replace saved words.')
    delivery.sweep()
    rows=delivery.rows('kind="anticipy_text" || kind="notification_status" || kind="reply_outbox"')
    assert len(sent)==1
    assert len([r for r in rows if r['kind']=='anticipy_text'])==1
    assert [r['decision'] for r in rows if r['kind']=='reply_outbox']==['sms_accepted']
    print('PASS real Worker/D1 outbox: saved reply, unique attempt, restart sweep, no duplicate; recorder only')
finally:
    for row in delivery.rows('id!=""'):
        r=requests.delete(delivery.url+'/'+row['id'],headers=headers,timeout=10);r.raise_for_status()
    login=requests.post(base+'/api/collections/owners/auth-with-password',json={
        'identity':f'{name}@example.invalid','password':password},timeout=10)
    login.raise_for_status()
    r=requests.post(base+'/me/delete',headers={'Authorization':login.json()['token']},json={'confirm':'delete'},timeout=30)
    r.raise_for_status()
    Path('work/audit/reply-wire-owner.json').unlink()
