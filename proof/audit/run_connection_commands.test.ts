import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync, writeFileSync, readFileSync, rmSync, chmodSync, symlinkSync, statSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServer} from 'node:http';
import * as runner from './run_connection_commands.ts';

const ENV = {ANTICIPY_AUDIT_STATE_DIR:'/tmp/fixture-audit', ANTICIPY_AUDIT_GATEWAY_URL:'http://127.0.0.1:18999/api/v1/chat/completions'};
const MODEL_URL = 'https://openrouter.ai/api/v1/chat/completions';
const body = JSON.stringify({model:'anthropic/claude-sonnet-4.6',messages:[{role:'user',content:'synthetic fixture'}],max_tokens:1024});
const post = {method:'POST',body};
const modelResponse=()=>Response.json({choices:[{message:{content:'{"kind":"not_for_us"}'}}]});
function config(args:string[]=['fresh','--cases','list']) { return runner.parseOptions(args,ENV); }
function temporary(fn:(directory:string)=>unknown) {
 const directory=mkdtempSync(join(tmpdir(),'connection-runner-test-'));chmodSync(directory,0o700);
 return Promise.resolve().then(()=>fn(directory)).finally(()=>rmSync(directory,{recursive:true,force:true}));
}

test('fixture case identities remain exactly the original eleven',()=>{
 assert.deepEqual(runner.CASES.map(c=>c.id),['list','connect','accept-context','targeted-card','answer-other-question','reported-complete','quoted-command','unknown-app','ordinary-greeting','decline-context','disconnect-context']);
});
test('explicit state and loopback settings, selected order and bounds are retained',()=>{
 const c=config(['fresh','--cases','ordinary-greeting,list','--max-calls','3']);
 assert.equal(c.stateDir,ENV.ANTICIPY_AUDIT_STATE_DIR);assert.equal(c.gatewayURL,ENV.ANTICIPY_AUDIT_GATEWAY_URL);
 assert.deepEqual(c.cases.map(x=>x.id),['ordinary-greeting','list']);assert.equal(c.maxCalls,3);
});
for(const args of [[],['../escape'],['x/y'],['x.json'],['x'.repeat(81)],['x','--cases',''],['x','--cases','list,'],['x','--cases','unknown'],['x','--cases','list,list'],['x','--max-calls','0'],['x','--max-calls','65'],['x','--max-calls','1.5'],['x','--attempts','2'],['x','--cases','list','--cases','connect']]) {
 test('invalid arguments refuse before IO: '+JSON.stringify(args),()=>assert.throws(()=>config(args)));
}
for(const url of ['https://api.anticipy.ai/api/v1/chat/completions','http://127.0.0.1/api/v1/chat/completions','http://127.0.0.1:0/api/v1/chat/completions','http://127.0.0.1:65536/api/v1/chat/completions','http://user:pass@127.0.0.1:1/api/v1/chat/completions','http://127.0.0.1:1/api/v1/chat/completions?x=1','http://127.0.0.1:1/api/v1/chat/completions#x','http://127.0.0.1.evil:1/api/v1/chat/completions','http://2130706433:1/api/v1/chat/completions','http://127.0.0.1:1/../api/v1/chat/completions']) {
 test('unsafe gateway refuses: '+url,()=>assert.throws(()=>runner.parseOptions(['fresh'],{...ENV,ANTICIPY_AUDIT_GATEWAY_URL:url})));
}
test('missing explicit settings or relative state refuses',()=>{
 for(const env of [{},{...ENV,ANTICIPY_AUDIT_STATE_DIR:''},{...ENV,ANTICIPY_AUDIT_STATE_DIR:'work/audit'},{...ENV,ANTICIPY_AUDIT_GATEWAY_URL:''}])assert.throws(()=>runner.parseOptions(['fresh'],env));
});
test('only exact fixture catalogue GETs are answered with no native calls',async()=>{
 let calls=0;const t=runner.createFixtureTransport(config(), 'fixture-token',async()=>{calls++;throw Error('not reached');});
 for(const url of ['https://backend.composio.dev/api/v3.1/toolkits?search=notes&limit=5','https://backend.composio.dev/api/v3.1/toolkits/zellibrix']) assert.equal((await t.fetch(url)).status,200);
 assert.equal(calls,0);assert.equal(t.calls,0);
});
for(const url of ['https://backend.composio.dev/api/v3.1/tools/execute/SEND','https://backend.composio.dev/api/v3.1/connected_accounts','https://backend.composio.dev/api/v3.1evil/toolkits?q=x','https://api.anticipy.ai/me/connections','https://api.sendblue.co/api/send-message','https://unknown.invalid/api/v1/chat/completions']) {
 test('unknown fetch blocks permanently without forwarding: '+url,async()=>{
  let calls=0;const t=runner.createFixtureTransport(config(),'fixture-token',async()=>{calls++;return Response.json({});});
  await assert.rejects(t.fetch(url));await assert.rejects(t.fetch(MODEL_URL,post));assert.equal(calls,0);assert.equal(t.failure,'unexpected_fetch');
 });
}
test('model POST only reaches exact loopback gateway; foreign headers are discarded',async()=>{
 const seen:any[]=[];const t=runner.createFixtureTransport(config(),'fixture-token',async(url,init)=>{seen.push([url,init]);return modelResponse();});
 assert.equal((await t.fetch(MODEL_URL,{...post,headers:{authorization:'do-not-forward',cookie:'do-not-forward'}})).status,200);
 assert.equal(seen[0][0],ENV.ANTICIPY_AUDIT_GATEWAY_URL+'?audit_run=fresh');
 assert.deepEqual(seen[0][1].headers,{Authorization:'Bearer fixture-token','content-type':'application/json'});
 assert.equal(seen[0][1].redirect,'error');assert.equal(seen[0][1].body,body);assert.equal(t.calls,1);
});
test('call ceiling refuses without an extra attempt; failure consumes the call',async()=>{
 let calls=0;const t=runner.createFixtureTransport(config(['fresh','--max-calls','1']),'fixture-token',async()=>{calls++;return modelResponse();});
 await t.fetch(MODEL_URL,post);await assert.rejects(t.fetch(MODEL_URL,post));assert.equal(calls,1);assert.equal(t.failure,'model_call_limit');
});
test('transport errors are sanitized and never retried',async()=>{
 let calls=0;const t=runner.createFixtureTransport(config(),'fixture-token',async()=>{calls++;throw Error('SECRET response and token');});
 await assert.rejects(t.fetch(MODEL_URL,post),e=>String(e)==='Error: gateway_unavailable');
 await assert.rejects(t.fetch(MODEL_URL,post));assert.equal(calls,1);assert.equal(t.calls,1);
});
test('pre-aborted request never reaches native fetch',async()=>{
 let calls=0;const t=runner.createFixtureTransport(config(),'fixture-token',async()=>{calls++;return Response.json({});});
 await assert.rejects(t.fetch(MODEL_URL,{...post,signal:AbortSignal.abort()}));assert.equal(calls,0);
});
test('non-2xx response cannot lead to a retry or expose response body',async()=>{
 let calls=0;const t=runner.createFixtureTransport(config(),'fixture-token',async()=>{calls++;return new Response('SECRET',{status:429});});
 await assert.rejects(t.fetch(MODEL_URL,post),e=>String(e)==='Error: gateway_http_error');
 await assert.rejects(t.fetch(MODEL_URL,post));assert.equal(calls,1);assert.equal(t.httpStatus,429);
});
for(const bad of [{method:'GET'}, {...post,body:'not-json'}, {...post,body:JSON.stringify({model:'other',messages:[],max_tokens:1})}, {...post,body:body.replace('1024','0')}, {...post,body:JSON.stringify({...JSON.parse(body),stream:true})}]) {
 test('malformed model shape blocked before native call '+JSON.stringify(bad),async()=>{
  let calls=0;const t=runner.createFixtureTransport(config(),'fixture-token',async()=>{calls++;return Response.json({});});
  await assert.rejects(t.fetch(MODEL_URL,bad));assert.equal(calls,0);
 });
}
for(const stall of ['headers','body']) {
 test('native loopback '+stall+' stall is aborted and bounded',async()=>{
  let closed=false;const server=createServer((req,res)=>{res.on('close',()=>{closed=true;});if(stall==='body'){res.writeHead(200,{'content-type':'application/json'});res.write('{');}});
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const address=server.address() as {port:number};const c={...config(),gatewayURL:`http://127.0.0.1:${address.port}/api/v1/chat/completions`};
  const t=runner.createFixtureTransport(c,'fixture-token',fetch,{timeoutMs:40});
  try {const start=Date.now();await assert.rejects(t.fetch(MODEL_URL,post));assert.ok(Date.now()-start<1000);await new Promise(resolve=>setTimeout(resolve,30));assert.equal(closed,true);assert.equal(t.calls,1);}
  finally {server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));}
 });
}
test('oversized body is cancelled even when content length lies',async()=>{
 let cancelled=false;const stream=new ReadableStream({start(c){c.enqueue(new Uint8Array(20));},cancel(){cancelled=true;}});
 const t=runner.createFixtureTransport(config(),'fixture-token',async()=>new Response(stream,{headers:{'content-length':'1'}}),{maxResponseBytes:10});
 await assert.rejects(t.fetch(MODEL_URL,post));assert.equal(cancelled,true);assert.equal(t.failure,'gateway_response_too_large');
});
for(const response of ['not-json','{}','{"choices":[]}','{"choices":[{"message":{"content":""}}]}']) {
 test('HTTP 200 without an actual model message cannot masquerade as not-for-us: '+response,async()=>{
  let calls=0;const t=runner.createFixtureTransport(config(),'fixture-token',async()=>{calls++;return new Response(response);});
  await assert.rejects(t.fetch(MODEL_URL,post));assert.equal(t.failure,'gateway_response_invalid');
  await assert.rejects(t.fetch(MODEL_URL,post));assert.equal(calls,1);
 });
}
test('token is private bounded file; symlink/unsafe permissions/invalid contents refuse',async()=>temporary(async directory=>{
 const tokenPath=join(directory,'gateway-token');writeFileSync(tokenPath,'fixture-token',{mode:0o600});
 assert.equal(runner.readGatewayToken(directory),'fixture-token');
 for(const token of ['', 'line1\nline2','\u0000secret','x'.repeat(4097)]){writeFileSync(tokenPath,token);assert.throws(()=>runner.readGatewayToken(directory));}
 writeFileSync(tokenPath,'fixture-token');chmodSync(tokenPath,0o644);assert.throws(()=>runner.readGatewayToken(directory));
 rmSync(tokenPath);writeFileSync(join(directory,'actual'),'fixture-token',{mode:0o600});symlinkSync(join(directory,'actual'),tokenPath);assert.throws(()=>runner.readGatewayToken(directory));
}));
test('actual dispatcher fixture completes once with strict summary; duplicate label cannot make a call',async()=>temporary(async directory=>{
 writeFileSync(join(directory,'gateway-token'),'fixture-token',{mode:0o600});let calls=0;
 const native=async()=>{calls++;return Response.json({choices:[{message:{content:JSON.stringify({kind:'command',command:'list_connected'})}}]});};
 const c=runner.parseOptions(['run','--cases','list','--max-calls','2'],{...ENV,ANTICIPY_AUDIT_STATE_DIR:directory});
 assert.equal(await runner.runAudit(c,native),0);assert.equal(calls,1);
 const saved=JSON.parse(readFileSync(join(directory,'run.json'),'utf8'));
 assert.equal(saved.summary.passed,true);assert.equal(saved.summary.selected_count,1);assert.equal(saved.summary.completed_count,1);assert.equal(saved.summary.attempted_count,1);assert.equal(saved.cases[0].passed,true);
 assert.equal(statSync(join(directory,'run.json')).mode&0o777,0o600);
 await assert.rejects(runner.runAudit(c,native));assert.equal(calls,1);
}));
test('partial failures remain in fresh evidence, no false all-pass or secret logging',async()=>temporary(async directory=>{
 writeFileSync(join(directory,'gateway-token'),'fixture-token',{mode:0o600});let calls=0;const printed:string[]=[];
 const old=console.log;console.log=(...args)=>{printed.push(args.join(' '));};
 try {
  const c=runner.parseOptions(['failed','--cases','list,connect'],{...ENV,ANTICIPY_AUDIT_STATE_DIR:directory});
  assert.equal(await runner.runAudit(c,async()=>{calls++;throw Error('SECRET upstream body');}),1);
  const saved=JSON.parse(readFileSync(join(directory,'failed.json'),'utf8'));
  assert.equal(saved.summary.passed,false);assert.equal(saved.summary.selected_count,2);assert.equal(saved.summary.attempted_count,1);assert.equal(saved.summary.completed_count,1);assert.equal(saved.cases[0].passed,false);assert.equal(calls,1);
  assert.ok(!JSON.stringify(saved).includes('SECRET'));assert.ok(!printed.join('').includes('SECRET'));
 } finally {console.log=old;}
}));
test('actual dispatcher no-verdict is not a passing ordinary-greeting case',async()=>temporary(async directory=>{
 writeFileSync(join(directory,'gateway-token'),'fixture-token',{mode:0o600});
 const c=runner.parseOptions(['no-verdict','--cases','ordinary-greeting'],{...ENV,ANTICIPY_AUDIT_STATE_DIR:directory});
 assert.equal(await runner.runAudit(c,async()=>Response.json({choices:[{message:{content:'{"kind":"no-verdict"}'}}]})),1);
 const saved=JSON.parse(readFileSync(join(directory,'no-verdict.json'),'utf8'));
 assert.equal(saved.cases[0].passed,false);assert.equal(saved.cases[0].model_verdict_available,false);
}));
