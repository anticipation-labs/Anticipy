"""Real reply model -> Conversation -> local Worker/D1, with no effect runner.
Synthetic phone-less accounts are deleted after every case. Eval expectations
never enter the model. Metered gateway is the only model transport.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
from urllib.parse import quote

from brain import llm
from brain.anticipy_core import Anticipy
from brain.conversation import Conversation
from brain.memory import Memory
from brain.workflow import Consequence, new_plan, put_in_params
from proof.audit.live_api_release import request
from proof.audit.model_gateway import atomic_json

ROOT=Path(__file__).resolve().parents[2]
STATE=ROOT/'work/audit'
BASE='http://127.0.0.1:8787'
SERVICE={'X-Anticipy-Token':'overnight-local-service-only'}
CASES=[
 ('yes_one','yes',[('Prepare the lamp comparison','','awaiting_confirm')], 'May I prepare the lamp comparison?', {'0':'queued'}),
 ('yes_context','yes',[('Prepare the lamp comparison','','awaiting_confirm'),('Prepare the room comparison','','awaiting_confirm')], 'May I prepare the room comparison?', {'0':'awaiting_confirm','1':'queued'}),
 ('both','yes, both please',[('Prepare the lamp comparison','','awaiting_confirm'),('Prepare the room comparison','','awaiting_confirm')], 'I can prepare the lamp and room comparisons. Should I do both?', {'0':'queued','1':'queued'}),
 ('cancel_done','I already handled that, don\'t do it',[('Prepare the lamp comparison','','awaiting_confirm')], 'May I prepare the lamp comparison?', {'0':'cancelled'}),
 ('explain','What?',[('Prepare the room comparison','','awaiting_confirm')], 'I can compare the three room offers without booking. Want me to?', {'0':'awaiting_confirm'}),
 ('social','Thank you, that makes sense',[('Prepare the room comparison','','awaiting_confirm')], 'The room comparison would include capacity and prices. I have not started.', {'0':'awaiting_confirm'}),
 ('missing_time','It ends at 4 PM.', [('Prepare the family appointment','What time does it end?','awaiting_confirm')], 'What time does the family appointment end?', {'0':'awaiting_confirm'}, 'legacy'),
 ('two_questions','Park Royal',[('Prepare the workshop','Which room should I use?','needs_user'),('Prepare the lunch plan','Which location should I use?','needs_user')], 'Which location should I use for lunch?', {'0':'needs_user','1':'queued'}),
 ('correct_premise','There is no login screen. I can see the public menu; continue there.', [('Compare the lunch menu','Please sign in to read the menu.','needs_user')], 'Please sign in to read the menu.', {'0':'queued'}),
 ('partial','Use four people instead',[('Prepare lunch for two','What time should I use?','needs_user')], 'What time should I use?', {'0':'needs_user'}),
 ('unseen_value','I sent it',[('Prepare the reservation','What is your six digit verification code?','needs_user')], 'What is your six digit verification code?', {'0':'needs_user'}),
 ('typed_schema','The Park Royal location',[('Prepare lunch','Which location?','awaiting_confirm')], 'Which location?', {'0':'awaiting_confirm'}, 'schema'),
 ('decline_queued','Wait, cancel the comparison',[('Prepare the lamp comparison','','queued')], 'The lamp comparison is queued.', {'0':'cancelled'}),
 ('quoted_yes','My colleague said "yes" to her own project, not this comparison.', [('Prepare the lamp comparison','','awaiting_confirm')], 'May I prepare the lamp comparison?', {'0':'awaiting_confirm'}),
]

class AuditLLM(llm.LLM):
 def chat(self, *args, **kwargs):
  try: return super().chat(*args, **kwargs)
  except Exception as error:
   response=getattr(error,'response',None)
   print('MODEL UNAVAILABLE',type(error).__name__,getattr(response,'status_code',None),getattr(response,'text','')[:200],flush=True)
   raise

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--label',required=True);parser.add_argument('--cases');parser.add_argument('--parallel',type=int,default=1);args=parser.parse_args()
 out=STATE/(args.label+'.json')
 if out.exists():raise SystemExit('Use a fresh evidence label')
 os.environ['ANTICIPY_SERVICE_TOKEN']=SERVICE['X-Anticipy-Token']
 llm.OPENROUTER_URL='http://127.0.0.1:8790/api/v1/chat/completions?audit_run='+quote(args.label,safe='')
 key=(STATE/'gateway-token').read_text().strip()
 def run(case):
  name,text,tasks,last_reply,expected,*shape=case
  email='reply-'+secrets.token_hex(10)+'@anticipy-test.invalid';password=secrets.token_urlsafe(24)
  status,owner,_=request(BASE,'POST','/api/collections/owners/records',{'email':email,'password':password,'passwordConfirm':password});assert status==200
  status,auth,_=request(BASE,'POST','/api/collections/owners/auth-with-password',{'identity':email,'password':password});assert status==200
  token=auth['token'];ids={};row_data={}
  def admin(method,path,data=None):
   status,result,_=request(BASE,method,path,data,extra_headers=SERVICE)
   assert status==200,(name,status,result)
   return result
  try:
   request(BASE,'POST','/me/profile/upsert',{'name':'Casey Fixture','timezone':'America/Vancouver'},token)
   for index,(goal,question,state) in enumerate(tasks):
    params={'source':goal,'authorized':state=='needs_user','approved_scope':('Task: '+goal if state=='needs_user' else '')}
    fields={}
    if shape==['schema']:
     plan=new_plan(owner_ref=owner['id'],lineage_key='fixture-'+name,goal=goal,
      consequence=Consequence.CONSEQUENTIAL,source_event_id='fixture-source',required=['location'])
     params=put_in_params(params,plan);fields=plan.job_fields()
    elif question and state=='awaiting_confirm': fields['workflow_state']='draft'
    row=admin('POST','/api/collections/jobs/records',{'owner_ref':owner['id'],'device_id':'reply-wire','goal':goal,'status':state,'lane':'research','params':json.dumps(params),'result':question,**fields})
    ids[str(index)]=row['id'];row_data[str(index)]=row
   admin('POST','/api/collections/events/records',{'owner_ref':owner['id'],'device_id':'reply-wire','kind':'anticipy_text','text':last_reply})
   model=llm.LLM(api_key=key,model='deepseek/deepseek-v3.2',owner_name='Casey',owner_email=email);model.gemini_api_key=None
   a=Anticipy(memory=Memory(':memory:'),llm=None,owner_ref=owner['id'],backend_url=BASE)
   strong=AuditLLM(api_key=key,model='google/gemini-3.1-pro-preview',owner_name='Casey',owner_email=email);strong.gemini_api_key=None
   a.llm=model;a.brain=SimpleNamespace(strong=strong)
   conv=Conversation(a,llm=model)
   context=None
   if shape:
    row=row_data['0'];context={'reply_to_job_id':row['id'],'workflow_version':row.get('workflow_version') or 0,'question':row.get('result') or '', 'goal':row['goal']}
   with conv.reply_in_app(): result=conv.on_reply('app:'+owner['id'],text,reply_context=context)
   saved={symbol:admin('GET','/api/collections/jobs/records/'+id) for symbol,id in ids.items()}
   observed={symbol:row['status'] for symbol,row in saved.items()}
   passed=observed==expected and result["intent"] != "unavailable"
   if name in ('quoted_yes','social','explain','unseen_value'):
    passed=passed and result.get('acted') is None and all(saved[key]['params']==row_data[key]['params'] for key in saved)
   if shape==['legacy']:passed=passed and saved['0']['result']=='' and saved['0']['workflow_state']=='awaiting_approval'
   if shape==['schema']:
    plan=json.loads(saved['0']['params'])['_workflow']
    passed=passed and plan['facts'].get('location') in ('Park Royal','The Park Royal location') and plan['state']=='awaiting_approval' and saved['0']['result']==''
   evidence={'case':name,'owner_text':text,'prior_question':last_reply,'passed':passed,'expected':expected,'observed':observed,'result':result,'tasks':[{k:r.get(k) for k in ('goal','result','params','workflow_state','workflow_version')} for r in saved.values()]}
   print(name,'PASS' if passed else 'FAIL',result['intent'],flush=True)
   return evidence
  finally:
   status,result,_=request(BASE,'POST','/me/delete',{'confirm':'delete'},token)
   assert status==200 and result.get('account_deleted'),(name,'cleanup',status)
 selected=[case for case in CASES if not args.cases or case[0] in args.cases.split(",")]
 with ThreadPoolExecutor(max_workers=args.parallel) as pool:results=list(pool.map(run,selected))
 atomic_json(out,{'scope':'real model and Conversation with local Worker records; no effect runner; all synthetic accounts deleted','results':results})
 raise SystemExit(0 if all(r['passed'] for r in results) else 1)

if __name__=='__main__':main()
