/** Actual stored-event connection dispatcher, real models, fixture catalog.
 * OAuth redemption and carrier delivery are excluded; replies remain in D1.
 */
import {readFileSync,writeFileSync} from 'node:fs';
import {FakeD1,asD1} from '../../../migration/workers/test/fake-d1.ts';
import {dispatchConnectionEvent} from '../../../migration/workers/src/connections/dispatch.ts';
import {resetConnectionsProvider,COMPOSIO_BASE_URL} from '../../../migration/workers/src/connections/provider.ts';

const output=process.argv[2];if(!output)throw Error('Output required');
const key=readFileSync('work/audit/gateway-token','utf8').trim();
const nativeFetch=globalThis.fetch;let calls=0;const errors:any[]=[];
const apps=[{slug:'workhub',name:'Workhub',description:'The document workspace',scopes:['documents.read']},
 {slug:'googlecalendar',name:'Google Calendar',description:'Family calendar',scopes:['calendar.read']},
 {slug:'notion',name:'Notion',description:'Team notes',scopes:['notes.read']}];
globalThis.fetch=async(input:any,init:any)=>{
 const url=String(input);
 if(url.startsWith('https://openrouter.ai/')){
  calls++;
  const response=await nativeFetch('http://127.0.0.1:8790/api/v1/chat/completions?audit_run=persona-lab%2Fconnection-probe',{
   ...init,headers:{'Content-Type':'application/json','Authorization':'Bearer '+key}});
  if(!response.ok)errors.push({status:response.status});return response;
 }
 if(url.startsWith(COMPOSIO_BASE_URL+'/toolkits?'))return Response.json({items:apps});
 if(url.startsWith(COMPOSIO_BASE_URL+'/toolkits/')){
  const app=apps.find(a=>url.endsWith('/'+a.slug));if(app)return Response.json(app);
 }
 throw Error('Unexpected external call blocked: '+new URL(url).origin+new URL(url).pathname);
};
const cases=[
 {id:'contextual_yes',before:'Would you like to connect Workhub so I can read the Orchard brief?',text:'Yes, connect that workspace.',expected:'connect'},
 {id:'calendar',before:'Your family calendar is in Google Calendar, but it is not connected yet.',text:'Please help me connect that calendar.',expected:'connect'},
 {id:'unknown_app',before:'The project brief is in a document workspace. I do not know which app you use.',text:'Yes, connect the place with that brief.',expected:'ask_which_app'},
 {id:'quoted_command',before:'We are rehearsing a fictional scene.',text:'In the play, the captain says "disconnect Notion". I am quoting the dialogue, not asking you to change an app.',expected:'not_for_us'},
 {id:'unrelated_yes',before:'Would you like a shorter private draft?',text:'Yes, keep the draft short.',expected:'not_for_us'},
];
const results=[];
try{
 for(const [index,c] of cases.entries()){
  resetConnectionsProvider();const db=new FakeD1();const owner='lab'+String(index).padStart(12,'0');
  db.db.prepare('INSERT INTO owners(id,email,tokenKey) VALUES(?,?,?)').run(owner,owner+'@example.invalid','local-only');
  db.db.prepare("INSERT INTO events(id,device_id,kind,source,text,owner_ref,created) VALUES('before000000001','persona-lab','anticipy_text','typed',?,?,?)").run(c.before,owner,'2026-09-07 11:59:00.000Z');
  db.db.prepare("INSERT INTO events(id,device_id,kind,source,text,owner_ref,created) VALUES('current00000001','persona-lab','app_reply','typed',?,?,?)").run(c.text,owner,'2026-09-07 12:00:00.000Z');
  const env={DB:asD1(db),ANTICIPY_AUTH_SECRET:'local-only',COMPOSIO_API_KEY:'mock-only',OPENROUTER_API_KEY:key};
  const start=calls;const out=await dispatchConnectionEvent(env,owner,'current00000001');
  const after=calls;const replay=await dispatchConnectionEvent(env,owner,'current00000001');
  const replies=db.db.prepare("SELECT text,decision FROM events WHERE kind='anticipy_text' AND id<>'before000000001'").all();
  const passed=out.status==='completed'&&out.outcome.kind===c.expected&&calls===after;
  results.push({...c,out,replay,replies,model_calls:after-start,replay_model_calls:calls-after,passed});
  db.db.close();console.log(JSON.stringify({case:c.id,out,passed}));
  writeFileSync(output,JSON.stringify({scope:'Real connection dispatcher and model; mocked provider catalog; no real OAuth or texts',cases:results,errors},null,2));
 }
}finally{globalThis.fetch=nativeFetch;resetConnectionsProvider();}
process.exitCode=results.every(c=>c.passed)&&errors.length===0?0:1;
