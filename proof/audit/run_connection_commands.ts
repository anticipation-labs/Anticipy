/** Production command/query/match models through an explicitly selected metered
 * loopback gateway; real SQLite/D1 schema/planner/executor, fixture catalogue.
 * No provider credential, connected account, phone, SMS or live API exists here.
 * Each selected case runs once. Local success is not real-connector acceptance. */
import {readFileSync, openSync, closeSync, fstatSync, lstatSync, writeSync, ftruncateSync, fsyncSync, constants} from 'node:fs';
import {resolve, isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const ROOT = fileURLToPath(new URL('../..', import.meta.url));
const MODEL = 'anthropic/claude-sonnet-4.6';
const MODEL_URL = 'https://openrouter.ai/api/v1/chat/completions';
const VENDOR_ORIGIN = 'https://backend.composio.dev';
const TOOLKITS = '/api/v3.1/toolkits';
const REQUEST_LIMIT = 900_000, RESPONSE_LIMIT = 4 * 1024 * 1024, TIMEOUT_MS = 95_000;
const app = {slug:'zellibrix',name:'Zellibrix',meta:{description:'Team notes and documents',app_url:'https://zellibrix.example.invalid'},auth_schemes:['OAUTH2']};
export const CASES = [
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
] as const;
type Fixture = typeof CASES[number];
type Options = {label:string;stateDir:string;gatewayURL:string;cases:Fixture[];maxCalls:number};

function loopbackURL(raw:unknown):string {
 if (typeof raw !== 'string' || !/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):[0-9]{1,5}\/api\/v1\/chat\/completions$/.test(raw)) throw Error('explicit_loopback_gateway_required');
 let url:URL;try {url=new URL(raw);}catch {throw Error('explicit_loopback_gateway_required');}
 if (!url.port || Number(url.port)<1 || Number(url.port)>65535) throw Error('explicit_loopback_gateway_required');
 return raw;
}

export function parseOptions(args:string[], env:Record<string,string|undefined>):Options {
 const [label,...rest]=args;
 if (!label || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(label)) throw Error('fresh_bounded_label_required');
 let selector:string|undefined;let maxCalls=32;const seen=new Set<string>();
 for(let i=0;i<rest.length;i+=2){
  const flag=rest[i],value=rest[i+1];
  if (!['--cases','--max-calls'].includes(flag) || value===undefined || seen.has(flag)) throw Error('invalid_arguments');
  seen.add(flag);
  if(flag==='--cases')selector=value;
  else {if(!/^[0-9]+$/.test(value))throw Error('invalid_call_limit');maxCalls=Number(value);}
 }
 if(!Number.isInteger(maxCalls)||maxCalls<1||maxCalls>64)throw Error('invalid_call_limit');
 const names=selector===undefined?CASES.map(c=>c.id):selector.split(',').map(s=>s.trim());
 if(!names.length||new Set(names).size!==names.length||names.some(n=>!CASES.some(c=>c.id===n)))throw Error('invalid_case_selection');
 const stateDir=env.ANTICIPY_AUDIT_STATE_DIR;
 if(!stateDir||!isAbsolute(stateDir))throw Error('explicit_absolute_state_required');
 const gatewayURL=loopbackURL(env.ANTICIPY_AUDIT_GATEWAY_URL);
 return {label,stateDir:resolve(stateDir),gatewayURL,cases:names.map(n=>CASES.find(c=>c.id===n)!),maxCalls};
}

export function readGatewayToken(stateDir:string):string {
 let fd:number|undefined;
 try {
  const dir=lstatSync(stateDir);
  if(!dir.isDirectory() || (dir.mode&0o077)!==0 || dir.uid!==process.getuid?.())throw Error();
  fd=openSync(resolve(stateDir,'gateway-token'),constants.O_RDONLY|constants.O_NOFOLLOW);
  const info=fstatSync(fd);
  if(!info.isFile()||(info.mode&0o077)!==0||info.uid!==process.getuid?.()||info.size>4098)throw Error();
  const token=readFileSync(fd,'utf8').trim();
  if(!token||token.length>4096||!/^[\x21-\x7e]+$/.test(token))throw Error();
  return token;
 } catch {throw Error('private_gateway_token_required');}
 finally {if(fd!==undefined)closeSync(fd);}
}

/** The only real I/O is one bounded POST to the approved loopback gateway.
 * Failure latches across catches/retries inside product code. There is no
 * automatic retry here, and a rejected request cannot be recast as success. */
export function createFixtureTransport(options:Options, token:string, nativeFetch:typeof fetch,
 bounds:{timeoutMs?:number;maxResponseBytes?:number}={}) {
 const gateway=loopbackURL(options.gatewayURL);
 const timeout=bounds.timeoutMs??TIMEOUT_MS, maximum=bounds.maxResponseBytes??RESPONSE_LIMIT;
 if(!Number.isInteger(timeout)||timeout<1||timeout>TIMEOUT_MS||!Number.isInteger(maximum)||maximum<1||maximum>RESPONSE_LIMIT)throw Error('invalid_transport_bounds');
 if(!Number.isInteger(options.maxCalls)||options.maxCalls<1||options.maxCalls>64)throw Error('invalid_call_limit');
 let calls=0,failure:string|null=null,httpStatus:number|null=null;
 const stop=(category:string,status:number|null=null):never=>{failure??=category;httpStatus??=status;throw Error(failure);};
 const intercepted:typeof fetch=async(input,init)=>{
  if(failure)throw Error(failure);
  if(typeof input!=='string'&&!(input instanceof URL))return stop('unexpected_fetch');
  let url:URL;try{url=new URL(String(input));}catch{return stop('unexpected_fetch');}
  const method=init?.method??'GET';
  if(url.origin===VENDOR_ORIGIN&&!url.username&&!url.password&&!url.hash&&method==='GET'){
   if(url.pathname===TOOLKITS && [...url.searchParams.keys()].every(k=>['search','limit'].includes(k)))return Response.json({items:[app],total_pages:1});
   if(url.pathname===TOOLKITS+'/zellibrix'&&!url.search)return Response.json(app);
  }
  if(String(input)!==MODEL_URL||method!=='POST')return stop('unexpected_fetch');
  if(typeof init?.body!=='string'||Buffer.byteLength(init.body)>REQUEST_LIMIT)return stop('invalid_model_request');
  let payload:any;try{payload=JSON.parse(init.body);}catch{return stop('invalid_model_request');}
  if(!payload||payload.model!==MODEL||!Array.isArray(payload.messages)||!payload.messages.length||!Number.isInteger(payload.max_tokens)||payload.max_tokens<1||payload.max_tokens>4096||payload.stream===true)return stop('invalid_model_request');
  if(init.signal?.aborted)return stop('gateway_cancelled');
  if(calls>=options.maxCalls)return stop('model_call_limit');
  calls++;
  const controller=new AbortController(),deadline=performance.now()+timeout;
  const signal=init.signal?AbortSignal.any([controller.signal,init.signal]):controller.signal;
  let reader:ReadableStreamDefaultReader<Uint8Array>|undefined;
  let rejectAbort:(error:Error)=>void=()=>{};
  const aborted=new Promise<never>((_,reject)=>{rejectAbort=reject;});
  const onAbort=()=>rejectAbort(Error('gateway_unavailable'));
  signal.addEventListener('abort',onAbort,{once:true});
  const timer=setTimeout(()=>controller.abort(),timeout);
  try{
   const operation=nativeFetch(gateway+'?audit_run='+encodeURIComponent(options.label),{
    method:'POST',body:init.body,headers:{Authorization:'Bearer '+token,'content-type':'application/json'},redirect:'error',signal,
   });
   void operation.then(res=>{if(signal.aborted)void res.body?.cancel().catch(()=>{});},()=>{});
   const response=await Promise.race([operation,aborted]);
   if(response.status<200||response.status>=300){void response.body?.cancel().catch(()=>{});return stop('gateway_http_error',response.status);}
   if(!response.body)return stop('gateway_response_invalid');
   reader=response.body.getReader();const chunks:Uint8Array[]=[];let size=0;
   for(;;){
    if(signal.aborted||performance.now()>=deadline)return stop('gateway_unavailable');
    const {done,value}=await Promise.race([reader.read(),aborted]);
    if(done)break;
    size+=value.byteLength;if(size>maximum)return stop('gateway_response_too_large');chunks.push(value);
   }
   const bytes=Buffer.concat(chunks);let answer:any;
   try{answer=JSON.parse(bytes.toString('utf8'));}catch{return stop('gateway_response_invalid');}
   const content=answer?.choices?.[0]?.message?.content;
   if(typeof content!=='string'||!content.trim())return stop('gateway_response_invalid');
   return new Response(bytes,{status:response.status,headers:{'content-type':'application/json'}});
  }catch{return stop(failure??'gateway_unavailable');}
  finally{
   clearTimeout(timer);signal.removeEventListener('abort',onAbort);controller.abort();
   if(reader)void reader.cancel().catch(()=>{});
  }
 };
 return {fetch:intercepted,get calls(){return calls;},get failure(){return failure;},get httpStatus(){return httpStatus;}};
}

export async function runAudit(options:Options,nativeFetch:typeof fetch=globalThis.fetch):Promise<number>{
 options=parseOptions([options.label,'--cases',options.cases.map(c=>c.id).join(','),'--max-calls',String(options.maxCalls)],{
  ANTICIPY_AUDIT_STATE_DIR:options.stateDir,ANTICIPY_AUDIT_GATEWAY_URL:options.gatewayURL,
 });
 const token=readGatewayToken(options.stateDir);
 const output=resolve(options.stateDir,options.label+'.json');
 let fd:number;try{fd=openSync(output,'wx',0o600);}catch{throw Error('fresh_evidence_required');}
 const transport=createFixtureTransport(options,token,nativeFetch);
 const results:any[]=[];let attempted=0,runFailure:string|null=null;
 const summary=()=>({selected_cases:options.cases.map(c=>c.id),selected_count:options.cases.length,attempted_count:attempted,
  completed_count:results.length,passed_count:results.filter(c=>c.passed===true).length,
  passed:!runFailure&&!transport.failure&&results.length===options.cases.length&&results.every((r,i)=>r.id===options.cases[i].id&&r.passed===true),
  model_calls:transport.calls,max_model_calls:options.maxCalls,attempts_per_case:1});
 const save=()=>{
  const data=JSON.stringify({scope:'real models through metered loopback gateway; isolated SQLite/D1 fixture catalogue; no SMS or provider accounts',model:MODEL,
   source_sha256:createHash('sha256').update(readFileSync(resolve(ROOT,'migration/workers/src/connections/wiring.ts'))).digest('hex'),
   summary:summary(),failure:runFailure??transport.failure,http_status:transport.httpStatus,cases:results},null,2);
  writeSync(fd,data,0,'utf8');ftruncateSync(fd,Buffer.byteLength(data));fsyncSync(fd);
 };
 const oldFetch=globalThis.fetch,oldLog=console.log,oldWarn=console.warn,oldError=console.error;
 let reset:(()=>void)|undefined;
 try{
  save();
  // Validate and reserve before importing product runtime. Never use inherited
  // provider env: the only bindings below are local fixtures and gateway token.
  globalThis.fetch=transport.fetch;
  console.log=console.warn=console.error=()=>{};
  await import('../../migration/workers/src/index.ts');
  const {FakeD1,asD1}=await import('../../migration/workers/test/fake-d1.ts');
  const {dispatchConnectionEvent}=await import('../../migration/workers/src/connections/dispatch.ts');
  const {resetConnectionsProvider}=await import('../../migration/workers/src/connections/provider.ts');reset=resetConnectionsProvider;
  for(const c of options.cases){
   attempted++;save();const before=transport.calls,start=Date.now();let db:InstanceType<typeof FakeD1>|undefined;
   let row:any={id:c.id,text:c.text,prior:'prior' in c?c.prior:'',want:c.want,got:'unavailable',passed:false};
   try{
    db=new FakeD1();const owner='connectiontest1';reset();
    db.db.prepare('INSERT INTO owners(id,email,tokenKey) VALUES(?,?,?)').run(owner,'case@example.invalid','fixture');
    if('prior' in c)db.db.prepare("INSERT INTO events(id,created,device_id,owner_ref,kind,text) VALUES('prior','2026-09-07 11:59:00.000Z','fixture',?,'anticipy_text',?)").run(owner,c.prior);
    db.db.prepare("INSERT INTO events(id,created,device_id,owner_ref,kind,source,text) VALUES('current','2026-09-07 12:00:00.000Z','fixture',?,'app_reply','typed',?)").run(owner,c.text);
    if('target' in c&&c.target){
     db.db.prepare("INSERT INTO jobs(id,goal,status,result,owner_ref) VALUES('task','Schedule design review','needs_user','Does 4 PM work?',?)").run(owner);
     db.db.prepare('UPDATE events SET goal=? WHERE id=?').run(JSON.stringify({reply_to_job_id:'task'}),'current');
    }
    const out=await dispatchConnectionEvent({DB:asD1(db),COMPOSIO_API_KEY:'fixture-only',OPENROUTER_API_KEY:token,ANTICIPY_AUTH_SECRET:'fixture'},owner,'current');
    const raw=out.status==='completed'?out.outcome.kind:out.status;
    const got=new Set(['list_connections','connect','not_for_us','ask_which_app','disconnect','pending','unavailable','missing']).has(raw)?raw:'unexpected_outcome';
    const replies=db.db.prepare("SELECT count(*) AS n FROM events WHERE kind='anticipy_text' AND id!='prior'").get();
    const links=Number(db.db.prepare('SELECT count(*) AS n FROM connect_links').get()?.n??0);
    const empty=['connections','agents'].every(table=>Number(db!.db.prepare(`SELECT count(*) AS n FROM ${table}`).get()?.n??-1)===0);
    const jobs=Number(db.db.prepare('SELECT count(*) AS n FROM jobs').get()?.n??-1);
    // This exact diagnostic is generated from the planner's closed no-verdict
    // state, not matched against owner/model prose. Silence is not a passing
    // negative-intent case, even though product safely leaves it alone.
    const available=out.status==='completed'&&out.outcome.detail!=='left alone (no-verdict)';
    row={...row,got,passed:!transport.failure&&available&&got===c.want&&links===(c.want==='connect'?1:0)&&empty&&jobs===('target' in c?1:0),model_verdict_available:available,link_count:links,reply_count:Number(replies?.n??0)};
   }catch{row.error='evaluation_case_unavailable';}
   finally{db?.db.close();reset?.();}
   row.calls=transport.calls-before;row.milliseconds=Date.now()-start;results.push(row);save();
   oldLog(JSON.stringify({id:row.id,want:row.want,got:row.got,passed:row.passed,calls:row.calls}));
   if(transport.failure||row.error)break;
  }
 }catch{runFailure='evaluation_run_unavailable';}
 finally{
  globalThis.fetch=oldFetch;console.log=oldLog;console.warn=oldWarn;console.error=oldError;reset?.();
  try{save();}finally{closeSync(fd);}
 }
 oldLog(JSON.stringify(summary()));return summary().passed?0:1;
}

if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 try{process.exitCode=await runAudit(parseOptions(process.argv.slice(2),process.env));}
 catch{console.error('connection_audit_refused: verify explicit state, gateway, selection and fresh label');process.exitCode=2;}
}
