/** Shipping registration/heartbeat against local workerd, with a real iOS
 * simulator doing the pairing. Only Chrome storage/alarm plumbing is simulated.
 * No model call, browser navigation, real account or provider is involved. */
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import assert from 'node:assert/strict';
import { installChrome } from '../../extension/tests/chrome_mock.mjs';
const root=resolve(import.meta.dirname,'../..');
const state=join(root,'work/audit');
const owner=JSON.parse(readFileSync(join(state,'overnight-visual-account.json'),'utf8'));
const harness=installChrome();
chrome.runtime.getManifest=()=>JSON.parse(readFileSync(join(root,'extension/manifest.json'),'utf8'));
harness.storageData.backendUrl='http://127.0.0.1:8787';
const network=[];const nativeFetch=globalThis.fetch;
globalThis.fetch=async (url, options={})=>{
 const parsed=new URL(String(url));
 if(!['localhost','127.0.0.1'].includes(parsed.hostname))throw new Error('Pairing proof permits local transport only');
 const result=await nativeFetch(url,options);
 network.push({path:parsed.pathname,method:options.method||'GET',status:result.status});
 return result;
};
const {ensureRegistered}=await import('../../extension/background.js');
const registrations=await Promise.all([ensureRegistered(),ensureRegistered(),ensureRegistered()]);
assert(registrations.every(r=>r?.recordId===registrations[0]?.recordId));
const credential=await chrome.storage.local.get(['agentId','agentToken','recordId','pairCode']);
assert.match(credential.pairCode,/^\d{6}$/);
writeFileSync(join(state,'overnight-pairing-private.json'),JSON.stringify(credential),{mode:0o600});
console.log(JSON.stringify({pair_code:credential.pairCode,scope:'local synthetic simulator only'}));
const deadline=Date.now()+240000;
let paired=false;
while(Date.now()<deadline){
 harness.fireAlarm('anticipy-heartbeat');
 await new Promise(resolve=>setTimeout(resolve,1000));
 if(harness.storageData.paired && harness.storageData.ownerRef===owner.id){paired=true;break;}
}
assert(paired,'The simulator did not finish pairing within the observation window');
assert.equal(network.filter(r=>r.path==='/agent/register'&&r.status===200).length,1);
const evidence={scope:'actual extension registration and heartbeat; local Worker/D1; actual iOS simulator pairing',
 paired:true,singleRegistration:true,ownerMatched:true,network};
writeFileSync(join(state,'overnight-pairing.json'),JSON.stringify(evidence,null,2));
console.log(JSON.stringify({paired:true,singleRegistration:true,ownerMatched:true}));
