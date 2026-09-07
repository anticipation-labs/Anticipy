"""Prepare one authorized read-only workflow on this audit's own account."""
import argparse
import json
from pathlib import Path
import secrets
from brain.workflow import new_plan, put_in_params, Consequence
from proof.audit.live_api_release import request
from proof.audit.model_gateway import atomic_json

parser=argparse.ArgumentParser();parser.add_argument('--fixture',required=True)
args=parser.parse_args();path=Path(args.fixture);fixture=json.loads(path.read_text())
if fixture.get('created_by')!='anticipy-browser-audit' or fixture.get('accountDeleted'):
    raise RuntimeError('Only an active synthetic fixture is allowed')
if fixture.get('jobId'): raise RuntimeError('This fixture already has a queue probe')
base=fixture['base'];owner=fixture['ownerId'];token=fixture['ownerToken']
service=json.loads(Path('work/audit/secrets.json').read_text())['ANTICIPY_SERVICE_TOKEN']
goal='Compare the Canvas Desk Lamp on both store pages. Tell me the lower listed price, both prices and their source links. Do not buy anything.'
status,ev,_=request(base,'POST','/api/collections/events/records',{'owner_ref':owner,'device_id':'isolated-browser-audit','kind':'app_reply','source':'typed','text':goal,'decision':'ignore'},token)
if status!=200: raise RuntimeError(f'Fixture event refused {status}')
plan=new_plan(owner_ref=owner,lineage_key='audit-'+secrets.token_hex(10),goal=goal,
    consequence=Consequence.READ_ONLY,source_event_id=ev['id'],authority_text=goal)
params=put_in_params({'task':goal,'start_url':'https://shop.audit.invalid/lamp','source':goal},plan)
status,job,_=request(base,'POST','/api/collections/jobs/records',{'owner_ref':owner,'owner':owner,
    'goal':goal,'params':json.dumps(params),'device_id':'isolated-browser-audit','lane':'',**plan.job_fields()},
    extra_headers={'X-Anticipy-Token':service,'X-Anticipy-Worker':'1'})
if status!=200: raise RuntimeError(f'Fixture workflow refused {status}: {job.get("message")}')
fixture['jobId']=job['id'];atomic_json(path,fixture)
print(json.dumps({'status':job['status'],'workflow':bool(job.get('workflow_id')),'read_only':job.get('consequence')=='read_only'}))
