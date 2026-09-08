/** Brain-selected tool arguments through the production API hand and outcome
 * mapping; real D1 schema; stateful fictional provider, no external network.
 * Fault selection is test data, never a model verdict or product routing rule.
 */
import {readFileSync,writeFileSync} from 'node:fs';
import {FakeD1,asD1} from '../../../migration/workers/test/fake-d1.ts';
import {createD1Store} from '../../../migration/workers/src/connections/store.ts';
import {ComposioConnections,COMPOSIO_BASE_URL} from '../../../migration/workers/src/connections/provider.ts';
import {runStep} from '../../../migration/workers/src/connections/api_hand.ts';
import {stepFromRow,dispose,apiReadEvidence} from '../../../migration/workers/src/routes/hands_api.ts';

const input=JSON.parse(readFileSync(process.argv[2],'utf8'));
const output=process.argv[3]; if(!output)throw Error('Input and output paths required');
const jobs=input.jobs||[];const evidence:any[]=[];
const failures=['success','not_connected','auth_expired','rate_limited','server_error','false_success','missing_receipt','empty_records'];
for(const job of jobs){
 const params=typeof job.params==='string'?JSON.parse(job.params):job.params;
 const note=params?._hand;if(note?.hand!=='api')continue;
 const step=stepFromRow(job,note,params._workflow||null);
 for(const fault of failures){
  const db=new FakeD1();const env={DB:asD1(db),COMPOSIO_API_KEY:'mock-provider-only'};
  const store=createD1Store(env);const calls:any[]=[];
  if(fault!=='not_connected')await store.putConnection({user_id:step.owner as never,toolkit:step.toolkit,
   connected_account_id:'ca_'+job.owner_ref,alias:step.alias||null,status:'connected',writes_enabled:false,last_used_at:null});
  const catalog=[{slug:step.tool,name:'Search and read workspace records',toolkit:{slug:step.toolkit,name:'Workhub'},tags:['readOnlyHint'],
   input_parameters:{type:'object',properties:{query:{type:'string'}},required:['query']},is_deprecated:false}];
  const fixtureRows=process.argv[4]?JSON.parse(readFileSync(process.argv[4],'utf8'))[input.person]:[{id:'brief-current',revision:'C',title:'Current project brief',status:'signed',delivery:'2026-09-18T16:00:00Z'},
   {id:'inspection-18',lot:'LY-18',received:100,rejected:20,accepted:80},
   {id:'maintenance-latest',last_committed:'R-107',query_for:'R-108',matching_records:[]}];
  if(!Array.isArray(fixtureRows))throw Error('No provider fixture for this persona');
  const provider=new ComposioConnections({apiKey:'mock-provider-only',fetchImpl:async(url:any,init:any)=>{
   const path=String(url).slice(COMPOSIO_BASE_URL.length);calls.push({path,method:init?.method||'GET',body:init?.body?JSON.parse(init.body):null});
   if(path.startsWith('/tools?'))return Response.json({items:catalog,next_cursor:null});
   if(!path.startsWith('/tools/execute/'))throw Error('Unexpected mock provider route');
   if(fault==='auth_expired')return Response.json({error:{slug:'ActionExecute_ConnectedAccountNotFound'}},{status:401});
   if(fault==='rate_limited')return Response.json({error:{slug:'rate_limit'}},{status:429});
   if(fault==='server_error')return Response.json({error:{slug:'server_failure'}},{status:503});
   if(fault==='false_success')return Response.json({successful:false,error:'Provider refused the operation',data:null});
   if(fault==='missing_receipt')return Response.json({message:'Success!'});
   return Response.json({successful:true,error:null,log_id:'mock-log-'+job.id,
      data:{records:fault==='empty_records'?[]:fixtureRows}});
  }});
  const outcome=await runStep(env,step,{store,provider});const disposition=dispose(outcome,1);
  const executionCalls=calls.filter(c=>c.method==='POST');
  const expected=fault==='success'||fault==='empty_records'?'ran':fault==='not_connected'?'refused':'failed';
  const passed=outcome.outcome===expected && executionCalls.length===(fault==='not_connected'?0:1)
    && disposition.state!=='succeeded'
    && (expected!=='ran'||disposition.lane==='research');
  evidence.push({person:input.person,job_id:job.id,goal:job.goal,fault,step,outcome,disposition,
    params:{...params,_api_evidence:apiReadEvidence(outcome)},calls,passed});
  db.db.close();
 }
}
writeFileSync(output,JSON.stringify({scope:'Brain-produced API steps; real provider parser/hand/disposition and isolated D1; mock vendor responses; no live account',cases:evidence},null,2));
console.log(JSON.stringify({person:input.person,api_jobs:evidence.length/failures.length,cases:evidence.length,passed:evidence.filter(x=>x.passed).length}));
process.exitCode=evidence.length && evidence.every(x=>x.passed)?0:1;
