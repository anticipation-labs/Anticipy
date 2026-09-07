import assert from 'node:assert/strict';
import {discoverApp,collectConversationSignals} from '../src/connections/discovery.ts';
import {FakeD1,asD1} from './fake-d1.ts';
import {resetConnectionsProvider} from '../src/connections/provider.ts';
import type {ToolkitMeta} from '../../../spike/two-hands/src/connections/contract.ts';

const app={slug:'quillbox',name:'Quillbox'} as ToolkitMeta;
let asked:unknown[]=[];
function deps(replies:string[]) {
 return {judge:async (_q:string,c:unknown)=>{asked.push(c);return replies.shift()??'{}';},
   catalog:async (_q:string)=>[app]};
}
const context={conversation:[{speaker:'owner',text:'I keep the project in Quillbox.'}]};
assert.equal(await discoverApp(context,deps(['{"kind":"app","query":"Quillbox"}','{"kind":"app","slug":"quillbox"}'])),'quillbox');
assert.deepEqual(asked[0],context);
assert.deepEqual((asked[1] as {context:unknown}).context,context);
for(const reply of ['{"kind":"none"}','{"kind":"unclear"}','{}','not json','null']) {
 let searched=false;
 assert.equal(await discoverApp(context,{judge:async()=>reply,catalog:async()=>{searched=true;return [app];}}),null);
 assert.equal(searched,false);
}
assert.equal(await discoverApp(context,deps(['{"kind":"app","query":"Quillbox"}','{"kind":"app","slug":"invented"}'])),null);
assert.equal(await discoverApp(context,{judge:async()=>{throw Error('offline');},catalog:async()=>[app]}),null);

// The production collector reads each owner's stored conversation and claims
// a daily scan before model work. No test-provided prose can cross that seam.
const db=new FakeD1();
const now=Date.now(),stamp=new Date(now-1000).toISOString().replace('T',' ');
for(const owner of ['discoveryowner1','discoveryowner2']) {
 db.db.prepare('INSERT INTO owners(id,email,tokenKey) VALUES(?,?,?)').run(owner,`${owner}@example.invalid`,owner);
 db.db.prepare("INSERT INTO events(id,created,device_id,kind,text,speaker,owner_ref) VALUES(?,?,'fixture','app_reply',?,'owner',?)")
   .run(owner,stamp,`Private context for ${owner}`,owner);
}
const native=globalThis.fetch;
let prompts:string[]=[], unavailable=false;
globalThis.fetch=async (_url,init)=>{
 prompts.push(String(init?.body));
 if(unavailable) return Response.json({error:'fixture offline'},{status:503});
 return Response.json({choices:[{message:{content:'{"kind":"none"}'}}]});
};
const env={DB:asD1(db),COMPOSIO_API_KEY:'fixture',OPENROUTER_API_KEY:'fixture',ANTICIPY_AUTH_SECRET:'fixture'};
try {
 assert.equal(await collectConversationSignals(env,now),0);
 assert.equal(prompts.length,2);
 assert.ok(prompts[0].includes('Private context for discoveryowner1'));
 assert.ok(!prompts[0].includes('Private context for discoveryowner2'));
 assert.ok(!prompts[1].includes('Private context for discoveryowner1'));
 assert.equal(await collectConversationSignals(env,now+1000),0);
 assert.equal(prompts.length,2);
 db.db.prepare("UPDATE events SET decision='retry' WHERE kind='discovery_scan' AND owner_ref='discoveryowner1'").run();
 unavailable=true;
 await collectConversationSignals(env,now+2000);
 assert.equal(db.db.prepare("SELECT decision FROM events WHERE kind='discovery_scan' AND owner_ref='discoveryowner1'").get()?.decision,'retry');
 unavailable=false;
 await collectConversationSignals(env,now+3000);
 assert.equal(db.db.prepare("SELECT decision FROM events WHERE kind='discovery_scan' AND owner_ref='discoveryowner1'").get()?.decision,'completed');
 assert.equal(prompts.length,4);
} finally {globalThis.fetch=native;resetConnectionsProvider();}
console.log('conversation discovery: catalog identity, four-state uncertainty, owner scope and daily claim passed');
