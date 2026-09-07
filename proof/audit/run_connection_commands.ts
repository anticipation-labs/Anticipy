/** Real production command/query/match models through the metered gateway;
 * real D1 schema/planner/executor, isolated vendor catalog and no SMS.
 * No provider credential or connected account exists in these fixtures. */
import '../../migration/workers/src/index.ts';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve} from 'node:path';
import {createHash} from 'node:crypto';
import {FakeD1,asD1} from '../../migration/workers/test/fake-d1.ts';
import {dispatchConnectionEvent} from '../../migration/workers/src/connections/dispatch.ts';
import {resetConnectionsProvider,COMPOSIO_BASE_URL} from '../../migration/workers/src/connections/provider.ts';
const label=process.argv[2];if(!label)throw Error('fresh label required');
const output=resolve('work/audit',label+'.json');if(existsSync(output))throw Error('do not overwrite evidence');
const token=readFileSync('work/audit/gateway-token','utf8').trim();
const nativeFetch=globalThis.fetch;let calls=0;
const app={slug:'zellibrix',name:'Zellibrix',meta:{description:'Team notes and documents',app_url:'https://zellibrix.example.invalid'},auth_schemes:['OAUTH2']};
globalThis.fetch=async(input,init)=>{
 const url=String(input);if(url.startsWith(COMPOSIO_BASE_URL)){
   if(url.includes('/toolkits/'))return Response.json(app);
   if(url.includes('/toolkits?'))return Response.json({items:[app],total_pages:1});
   throw Error('Unexpected vendor effect: '+url);
 }
 calls++;
 return nativeFetch('http://127.0.0.1:8790/api/v1/chat/completions?audit_run='+encodeURIComponent(label),{
  ...init,headers:{Authorization:'Bearer '+token,'content-type':'application/json'}});
};
const cases=[
 {id:'list',text:'What apps have I connected so far?',want:'list_connections'},
 {id:'connect',text:'Please connect Zellibrix so you can help with my team notes.',want:'connect'},
 {id:'accept-context',prior:'I can use Zellibrix to read the briefing. Would you like to connect it?',text:'Yes, please.',want:'connect'},
 {id:'targeted-card',prior:'Would you like to connect Zellibrix?',text:'Yes, please.',target:true,want:'not_for_us'},
 {id:'answer-other-question',prior:'What time does the meeting end?',text:'Yes, please.',want:'not_for_us'},
 {id:'reported-complete',text:'I already connected Zellibrix yesterday. Anyway, the launch was great.',want:'not_for_us'},
 {id:'quoted-command',text:'The document says "disconnect Zellibrix". Explain what that sentence means; leave my connections alone.',want:'not_for_us'},
 {id:'unknown-app',text:'Connect the app we were discussing.',want:'ask_which_app'},
 {id:'ordinary-greeting',text:"Hi, how are you? Good, good yourself. I'm good.",want:'not_for_us'},
 {id:'decline-context',prior:'Would you like to connect Zellibrix?',text:'No, leave it for now.',want:'not_for_us'},
 {id:'disconnect-context',prior:'Zellibrix is the notes app you asked about.',text:'Remove that connection, please.',want:'disconnect'},
];
const results:any[]=[];
try {
 for(const [index,c]of cases.entries()){
  const db=new FakeD1();const owner='connectiontest1';resetConnectionsProvider();
  db.db.prepare('INSERT INTO owners(id,email,tokenKey) VALUES(?,?,?)').run(owner,'case@example.invalid','fixture');
  if(c.prior)db.db.prepare("INSERT INTO events(id,created,device_id,owner_ref,kind,text) VALUES('prior','2026-09-07 11:59:00.000Z','fixture',?,'anticipy_text',?)").run(owner,c.prior);
  db.db.prepare("INSERT INTO events(id,created,device_id,owner_ref,kind,source,text) VALUES('current','2026-09-07 12:00:00.000Z','fixture',?,'app_reply','typed',?)").run(owner,c.text);
  if('target' in c && c.target){
   db.db.prepare("INSERT INTO jobs(id,goal,status,result,owner_ref) VALUES('task','Schedule design review','needs_user','Does 4 PM work?',?)").run(owner);
   db.db.prepare('UPDATE events SET goal=? WHERE id=?').run(JSON.stringify({reply_to_job_id:'task'}),'current');
  }
  const before=calls;const start=Date.now();
  const env={DB:asD1(db),COMPOSIO_API_KEY:'fixture-only',OPENROUTER_API_KEY:token,ANTICIPY_AUTH_SECRET:'fixture'};
  const out=await dispatchConnectionEvent(env,owner,'current');
  const got=out.status==='completed'?out.outcome.kind:out.status;
  const replies=db.db.prepare("SELECT text FROM events WHERE kind='anticipy_text' AND id!='prior'").all();
  const links=Number(db.db.prepare('SELECT count(*) AS n FROM connect_links').get()?.n??0);
  const row={id:c.id,text:c.text,prior:c.prior??'',want:c.want,got,passed:got===c.want && (c.want!=='connect'||links===1),link_count:links,calls:calls-before,milliseconds:Date.now()-start,reply_count:replies.length};
  results.push(row);writeFileSync(output,JSON.stringify({scope:'real models; isolated D1/vendor; no SMS; no provider account',model:'anthropic/claude-sonnet-4.6',source_sha256:createHash('sha256').update(readFileSync('migration/workers/src/connections/wiring.ts')).digest('hex'),cases:results},null,2),{mode:0o600});
  console.log(JSON.stringify(row));db.db.close();
 }
}finally{globalThis.fetch=nativeFetch;resetConnectionsProvider();}
process.exitCode=results.every(x=>x.passed)?0:1;
