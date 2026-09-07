"""Use the explicitly served, existing production probe; touch no real owner."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, json, os, secrets, time
from proof.e2e_cloudflare import Api, cancel_job
from proof.audit.model_gateway import atomic_json
from brain.workflow import Consequence, new_plan, put_in_params
ROOT=Path(__file__).resolve().parents[2]
args = argparse.ArgumentParser()
args.add_argument('--label', required=True)
args.add_argument('--count', type=int, default=1, choices=range(1, 8))
args.add_argument('--goal', default='Open the appointment page in my browser for review. Do not submit or book anything.')
args.add_argument('--start-url', default='https://appointment.audit.invalid/')
args.add_argument('--expected-app')
options = args.parse_args()
OWNER='qeuy6sv1raof9rw'; LABEL=options.label
assert Path(LABEL).name == LABEL and LABEL not in ('.', '..')
public=ROOT/'work/audit'/f'{LABEL}.json';private=public.with_name(LABEL+'-private.json')
if public.exists() or private.exists():raise RuntimeError('Preserve prior evidence')
secrets_map=json.loads((ROOT/'work/audit/secrets.json').read_text())
api=Api('https://api.anticipy.ai',secrets_map['ANTICIPY_SERVICE_TOKEN'])
profiles=api.list('owner_profile',f'owner_ref="{OWNER}"')
assert len(profiles)==1 and profiles[0].get('email','').endswith('.invalid')
profile=profiles[0]
assert str(profile.get('phone','')).startswith('+1604555'), 'The designated fixture phone must remain fictional'
# Explicitly stand down every phone effect on this test account during the probe.
atomic_json(private,{'owner':OWNER,'profile_id':profile['id'],'restore_phone':profile['phone']})
budget_path=ROOT/'work/audit/overnight-live-browser-budget.json';lock=str(budget_path)+'.lock'
fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
try:
 budget=json.loads(budget_path.read_text());reserve=.5*options.count
 assert budget['reserved_upper_bound_usd']+reserve<=budget['limit_usd']
 budget['reserved_upper_bound_usd']+=reserve
 budget['calls'].append({'label':LABEL,'at':datetime.now(timezone.utc).isoformat(),'reserved_usd':reserve,'purpose':'backlog notices on the designated phone-disabled probe'})
 atomic_json(budget_path,budget)
finally:os.close(fd);os.unlink(lock)
jobs=[];event=None;evidence={'scope':'actual live worker app notices, existing allowlisted test owner','passed':False}
try:
 r=api.patch('/api/collections/owner_profile/records/'+profile['id'],{'phone':''});assert r.ok,f'phone stand-down {r.status_code}'
 assert not api.record('owner_profile',profile['id']).get('phone')
 goal=options.goal
 r=api.post('/api/collections/events/records',{'owner_ref':OWNER,'kind':'app_reply','source':'typed','device_id':LABEL,'text':goal,'decision':'ignore'})
 assert r.ok,f'event {r.status_code}';event=r.json()
 for index in range(options.count):
  plan=new_plan(owner_ref=OWNER,lineage_key='audit-'+secrets.token_hex(10),goal=goal,consequence=Consequence.READ_ONLY,source_event_id=event['id'],authority_text=goal)
  params=put_in_params({'task':goal,'source':goal,'start_url':options.start_url},plan)
  r=api.post('/api/collections/jobs/records',{'owner_ref':OWNER,'owner':OWNER,'goal':goal,'params':json.dumps(params),'device_id':LABEL,'lane':'',**plan.job_fields()})
  assert r.ok,f'job {r.status_code}';jobs.append(r.json())
  atomic_json(private,{'owner':OWNER,'profile_id':profile['id'],'restore_phone':profile['phone'],'job_ids':[j['id'] for j in jobs]})
 started=time.monotonic()
 while time.monotonic()-started<180:
  notes=[api.list('events',f'owner_ref="{OWNER}" && external_event_id="job-stalled:{job["id"]}:queued"') for job in jobs]
  if all(len(rows)==1 for rows in notes):break
  time.sleep(3)
 saved=[api.record('jobs',job['id']) for job in jobs]
 evidence.update(notice_counts=[len(rows) for rows in notes],job_statuses=[j.get('status') for j in saved],elapsed_seconds=round(time.monotonic()-started,2))
 evidence['notices']=[rows[0].get('text') for rows in notes if rows]
 assert all(len(rows)==1 for rows in notes) and all(j.get('status')=='queued' for j in saved),'The worker did not persist one notice for every still-queued task'
 if options.expected_app:
  assert all(str(rows[0].get('text','')).endswith(f'Would you like to connect {options.expected_app}?') for rows in notes), 'The actual worker did not offer the expected missing app'
  evidence['offered_app']=options.expected_app
 evidence['passed']=True
finally:
 evidence['tasks_cancelled']=[]
 for job in jobs:
  saved=api.record('jobs',job['id']);evidence['tasks_cancelled'].append(cancel_job(api,saved,'finished isolated live notice proof'))
 # Restore only the fictional phone field captured above, never another owner.
 r=api.patch('/api/collections/owner_profile/records/'+profile['id'],{'phone':profile['phone']})
 evidence['fixture_phone_restored']=r.ok and api.record('owner_profile',profile['id']).get('phone')==profile['phone']
 evidence['real_messages_sent']=0
 atomic_json(public,evidence);print(json.dumps(evidence))
