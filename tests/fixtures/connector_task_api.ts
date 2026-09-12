/** Loopback-only integration fixture: real Worker/router/SQL and provider adapter.
 * Fake boundaries are external vendor fetches and the successful OAuth callback's
 * recordConnection input. No live account, provider, model, or SMS transport exists.
 */
import {createServer} from 'node:http';
import worker from '../../migration/workers/src/index.ts';
import {FakeD1,asD1} from '../../migration/workers/test/fake-d1.ts';
import {createD1Store} from '../../migration/workers/src/connections/store.ts';
import {COMPOSIO_BASE_URL,resetConnectionsProvider} from '../../migration/workers/src/connections/provider.ts';

const OWNER='fixtureowner001';
const ACCOUNT='fixture-account-1';
// Every account /__fixture/connect has recorded, by vendor id -> alias; the
// default connect records ACCOUNT with no alias, a two-account scenario
// records two with labels.
const accounts=new Map<string,string|null>();
const APP='fixture_notes';
const TOOL='FIXTURE_NOTES_READ';
const db=new FakeD1();
db.db.prepare('INSERT INTO owners(id,email,tokenKey) VALUES(?,?,?)')
  .run(OWNER,'connector-recovery@example.invalid','fixture-token-key');
const env={DB:asD1(db),ANTICIPY_SERVICE_TOKEN:'fixture-service-token',
  ANTICIPY_AUTH_SECRET:'fixture-auth-secret',COMPOSIO_API_KEY:'fixture-provider-key'};
const calls:{method:string,path:string,body:unknown}[]=[];
let connected=false;
let raceField:string|null=null;
// What the fake vendor answers an execute with, and what it says the account's
// status is when the Worker reads it back after a refusal.
let deny:string|null=null;
let vendorStatus='ACTIVE';
const prepare=db.prepare.bind(db);
db.prepare=(sql:string)=>{
  if(raceField&&sql.startsWith('UPDATE "jobs" SET')){
    const field=raceField;raceField=null;
    // Deliberately retain the timestamp: the SQL CAS must compare claim/lane,
    // not depend on a second actor receiving a different millisecond.
    db.db.prepare(`UPDATE jobs SET ${field}=? WHERE owner_ref=?`)
      .run(field==='lane'?'research':'fixture-browser',OWNER);
  }
  return prepare(sql);
};
resetConnectionsProvider();
globalThis.fetch=async(input,init)=>{
  const url=new URL(typeof input==='string'?input:input instanceof URL?input.href:input.url);
  const base=new URL(COMPOSIO_BASE_URL);
  if(url.origin!==base.origin) throw new Error('external network forbidden by connector fixture');
  const path=url.pathname.slice(base.pathname.replace(/\/$/,'').length);
  const method=init?.method??'GET';
  const body=init?.body?JSON.parse(String(init.body)):null;
  calls.push({method,path,body});
  if(method==='GET'&&path==='/tools') return Response.json({items:[{
    slug:TOOL,toolkit:{slug:APP},name:'Read fixture notes',description:'Read the requested notes.',
    tags:['readOnlyHint'],input_parameters:{type:'object',properties:{query:{type:'string'}},required:['query']},
  }]});
  const accountRead=path.match(/^\/connected_accounts\/([^/]+)$/);
  if(method==='GET'&&accountRead&&accounts.has(decodeURIComponent(accountRead[1])))
    return Response.json({id:decodeURIComponent(accountRead[1]),user_id:OWNER,toolkit:{slug:APP},status:vendorStatus});
  // The owner's account LIST — what provider.connections() reads to decide
  // whether a refused execute means the credential is dead or just that scope.
  if(method==='GET'&&path==='/connected_accounts'&&url.searchParams.get('user_ids')===OWNER)
    return Response.json({items:[...accounts.keys()].map(id=>({id,user_id:OWNER,toolkit:{slug:APP},status:vendorStatus}))});
  if(method==='POST'&&path===`/tools/execute/${TOOL}`&&accounts.has(String(body.connected_account_id))){
    if(body.user_id!==OWNER||body.arguments?.query!=='Orion')
      throw new Error('fixture scope or arguments changed');
    if(deny==='http403')
      return Response.json({error:{code:'forbidden',message:'Request had insufficient authentication scopes.'}},{status:403});
    if(deny==='tool403')
      return Response.json({successful:false,data:null,log_id:'fixture-denied-log',
        error:{status:403,code:'PERMISSION_DENIED',message:'Request had insufficient authentication scopes.'}});
    return Response.json({successful:true,data:{notes:[{title:'Orion',body:'Review is on Friday.'}]},log_id:'fixture-read-receipt'});
  }
  throw new Error(`unexpected fake provider operation: ${method} ${path}`);
};

const server=createServer(async(req,res)=>{
  try{
    if(req.headers.host!==`127.0.0.1:${(server.address() as {port:number}).port}`)
      throw new Error('foreign host');
    let text='';
    for await(const piece of req){text+=piece;if(text.length>262144)throw new Error('body too large');}
    const url=new URL(req.url??'/',`http://${req.headers.host}`);
    let response:Response;
    if(url.pathname.startsWith('/__fixture/')){
      if(req.headers['x-anticipy-token']!==env.ANTICIPY_SERVICE_TOKEN)throw new Error('fixture token required');
      if(url.pathname==='/__fixture/connect'&&req.method==='POST'){
        // {alias?, account?}: call twice with two labels to connect two
        // accounts on the one toolkit, the shape of a work + personal Google.
        const body=text?JSON.parse(text):{};
        const account=typeof body.account==='string'&&body.account?body.account:ACCOUNT;
        const alias=typeof body.alias==='string'&&body.alias?body.alias:null;
        await createD1Store(env).recordConnection({user_id:OWNER,toolkit:APP as never,
          connected_account_id:account,alias:alias as never,auth_config_id:'fixture-auth-config',
          writes_enabled:false,status:'connected',created_at:Date.now()},Date.now());
        accounts.set(account,alias);connected=true;
        response=Response.json({connected:true,account,alias});
      }else if(url.pathname==='/__fixture/state'&&req.method==='GET'){
        response=Response.json({jobs:db.rows('SELECT * FROM jobs WHERE owner_ref=?',OWNER),
          connections:db.rows('SELECT connected_account_id,alias,status,writes_enabled,toolkit FROM connections WHERE user_id=?',OWNER),
          events:db.rows('SELECT * FROM events WHERE owner_ref=?',OWNER),calls,connected});
      }else if(url.pathname==='/__fixture/disconnect'&&req.method==='POST'){
        const body=JSON.parse(text);
        if(!accounts.has(body.account))throw new Error('unknown fixture account');
        db.db.prepare("UPDATE connections SET status='needs_reconnect' WHERE user_id=? AND connected_account_id=?")
          .run(OWNER,body.account);
        response=Response.json({disconnected:true});
      }else if(url.pathname==='/__fixture/facts'&&req.method==='POST'){
        // CHANGE WHAT IS TRUE ABOUT THE CONNECTION, nothing else. The recovery
        // budget is keyed on the task's params AND this owner's connection
        // facts, so this is how a test asks "do changed facts start a fresh
        // budget" without touching the task or inventing a second toolkit.
        const body=JSON.parse(text);
        if(typeof body.writes_enabled!=='boolean')throw new Error('invalid facts fixture');
        db.db.prepare('UPDATE connections SET writes_enabled=? WHERE user_id=?')
          .run(body.writes_enabled?1:0,OWNER);
        response=Response.json({writes_enabled:body.writes_enabled});
      }else if(url.pathname==='/__fixture/deny'&&req.method==='POST'){
        // Make the vendor refuse the ONE tool, in either measured shape, while
        // its account status stays whatever `status` says (ACTIVE by default).
        const body=JSON.parse(text);
        if(![null,'http403','tool403'].includes(body.mode))throw new Error('invalid deny fixture');
        if(body.status!==undefined&&!['ACTIVE','EXPIRED'].includes(body.status))throw new Error('invalid vendor status');
        deny=body.mode;if(body.status)vendorStatus=body.status;
        response=Response.json({deny,status:vendorStatus});
      }else if(url.pathname==='/__fixture/race'&&req.method==='POST'){
        const body=JSON.parse(text);
        if(!['lane','claimed_by','claimed_at'].includes(body.field))throw new Error('invalid race fixture');
        raceField=body.field;response=Response.json({armed:true});
      }else response=new Response(null,{status:404});
    }else{
      const request=new Request(url,{method:req.method,headers:req.headers as Record<string,string>,
        ...(text?{body:text}:{})});
      response=await worker.fetch(request,env as never,{waitUntil:()=>{throw new Error('unexpected background work');}} as never);
    }
    res.writeHead(response.status,Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
  }catch(error){
    console.error('fixture failure:',error);
    res.writeHead(500,{'content-type':'application/json'});res.end('{"error":"fixture_failure"}');
  }
});
server.requestTimeout=10000;
server.listen(0,'127.0.0.1',()=>{
  console.log(JSON.stringify({base:`http://127.0.0.1:${(server.address() as {port:number}).port}`,owner:OWNER}));
});
process.once('SIGTERM',()=>server.close(()=>process.exit(0)));
