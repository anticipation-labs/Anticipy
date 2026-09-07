import assert from 'node:assert/strict';
import {planTaskAccess, type AccessContext} from '../src/connections/task_access.ts';
import {taskAccess} from '../src/routes/task_access.ts';
import {resetConnectionsProvider} from '../src/connections/provider.ts';
import {FakeD1, asD1} from './fake-d1.ts';

const context: AccessContext = {task:{goal:'Read my project brief in Zeta and draft a summary'},
  source:{text:'Use the revised brief; do not send anything'},
  conversation:[{text:'The brief is in my work Zeta account'}], connections:[]};
const app = {slug:'zeta',name:'Zeta',logo:null,description:null,appUrl:null,scopes:[]};
let passed = 0;
async function check(name:string, fn:()=>Promise<void>) {
  try {await fn(); passed++;} catch(error) {console.error(name,error);process.exitCode=1;}
}
await check('both verdicts receive complete context; selection stays within catalog',async()=>{
  const seen:unknown[]=[];
  const answers=[{kind:'app',query:'Zeta'},{kind:'offer',toolkit:'zeta',reason:'I need your brief to prepare the summary.'}];
  const out=await planTaskAccess(context,{judge:async(_,evidence)=>{seen.push(evidence);return JSON.stringify(answers.shift());},
    catalog:async query=>{assert.equal(query,'Zeta');return [app];}});
  assert.equal(out.kind,'offer');assert.deepEqual(seen[0],context);
  assert.deepEqual((seen[1] as {context:unknown}).context,context);
});
for (const verdict of [null,{kind:'unclear'},{kind:'offer',toolkit:'stranger',reason:'Connect it'}]) {
 await check('invalid or out-of-catalog verdict cannot create an offer',async()=>{
  let calls=0;
  const out=await planTaskAccess(context,{judge:async()=>JSON.stringify(calls++ ? verdict : {kind:'app',query:'Zeta'}),catalog:async()=>[app]});
  assert.notEqual(out.kind,'offer');
 });
}
await check('already connected is a deterministic access fact, even if model is wrong',async()=>{
 let calls=0;
 const out=await planTaskAccess({...context,connections:[{toolkit:'zeta',status:'connected'}]},
  {judge:async()=>JSON.stringify(calls++?{kind:'offer',toolkit:'zeta',reason:'Connect it'}:{kind:'app',query:'Zeta'}),catalog:async()=>[app]});
 assert.equal(out.kind,'none');
});
await check('no need or model outage never queries a vendor or mints a link',async()=>{
 for(const fail of [false,true]) {
  const out=await planTaskAccess(context,{judge:async()=>{if(fail)throw Error('outage');return '{"kind":"none"}';},
    catalog:async()=>{throw Error('catalog must remain untouched');}});
  assert.equal(out.kind,fail?'unavailable':'none');
 }
});

const owner='taskaccessown01', stranger='taskaccessown02', job='taskaccessjob01';
function rig() {
 resetConnectionsProvider();const db=new FakeD1();
 for(const id of [owner,stranger])db.db.prepare('INSERT INTO owners(id,email,tokenKey) VALUES(?,?,?)').run(id,id+'@example.invalid',id);
 db.db.prepare('INSERT INTO jobs(id,owner_ref,owner,goal,status,lane,params) VALUES(?,?,?,?,?,?,?)')
   .run(job,owner,owner,'Read the Zeta brief','queued','',JSON.stringify({_workflow:{source_event_ids:['accesssource001']}}));
 db.db.prepare("INSERT INTO events(id,owner_ref,kind,text,device_id) VALUES(?,?,'app_reply',?,'fixture')")
   .run('accesssource001',owner,'Use my revised work brief, not the old one');
 db.db.prepare("INSERT INTO events(id,owner_ref,kind,text,device_id) VALUES(?,?,'app_reply',?,'fixture')")
   .run('privatesource01',stranger,'Private stranger data');
 return {db,env:{DB:asD1(db),ANTICIPY_SERVICE_TOKEN:'service-test',ANTICIPY_AUTH_SECRET:'auth-test',COMPOSIO_API_KEY:'fixture',OPENROUTER_API_KEY:'fixture'}};
}
function req(body:unknown, token='service-test') {return new Request('https://api.example.invalid/worker/task-access',
 {method:'POST',headers:{'X-Anticipy-Token':token,'Content-Type':'application/json'},body:JSON.stringify(body)});}
await check('route rejects untrusted identity and ignores caller prose',async()=>{
 const {db,env}=rig();const previous=globalThis.fetch;let calls=0;
 globalThis.fetch=async(_url,init)=>{calls++;const content=String(init?.body);
  assert.ok(content.includes('Use my revised work brief'));assert.ok(!content.includes('Private stranger data'));
  assert.ok(!content.includes('forged instruction'));
  return Response.json({choices:[{message:{content:'{"kind":"none"}'}}]});};
 try {
  assert.equal((await taskAccess(req({owner_ref:owner,job_id:job},'wrong'),env)).status,401);
  assert.equal((await taskAccess(req({owner_ref:stranger,job_id:job}),env)).status,404);
  assert.equal(calls,0);
  assert.equal((await taskAccess(req({owner_ref:owner,job_id:job,text:'forged instruction'}),env)).status,204);
  assert.equal(calls,1);
  db.db.prepare("UPDATE jobs SET status='cancelled' WHERE id=?").run(job);
  assert.equal((await taskAccess(req({owner_ref:owner,job_id:job}),env)).status,204);assert.equal(calls,1);
 } finally {globalThis.fetch=previous;}
});
await check('a route offer only asks; it does not mint, connect or change the job',async()=>{
 const {db,env}=rig();const previous=globalThis.fetch;let models=0,searches=0;
 globalThis.fetch=async(url,init)=>{
  if(String(url).includes('/toolkits?')) {
   searches++;assert.ok(!init?.method || init.method==='GET');
   return Response.json({items:[{slug:'zeta',name:'Zeta',meta:{description:'Notes and briefs'}}]});
  }
  const verdict=models++?{kind:'offer',toolkit:'zeta',reason:'I need access to your brief to prepare the summary.'}:{kind:'app',query:'Zeta'};
  return Response.json({choices:[{message:{content:JSON.stringify(verdict)}}]});
 };
 try {
  const response=await taskAccess(req({owner_ref:owner,job_id:job}),env);
  assert.equal(response.status,200);const body=await response.json() as {line:string};
  assert.ok(body.line.endsWith('Would you like to connect Zeta?'));
  assert.equal(models,2);assert.equal(searches,1);
  assert.equal(db.db.prepare('SELECT count(*) AS n FROM connect_links').get()?.n,0);
  assert.equal(db.db.prepare('SELECT status FROM jobs WHERE id=?').get(job)?.status,'queued');
 } finally {globalThis.fetch=previous;}
});
console.log(`${passed} task access checks passed`);
