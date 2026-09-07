import { dispatchConnectionEvent } from '../connections/dispatch.ts';
import type { TextCommandEnv } from '../connections/wiring.ts';
type Env = TextCommandEnv & {ANTICIPY_SERVICE_TOKEN?:string};
export async function connectionCommand(req:Request,env:Env):Promise<Response> {
  const json=(status:number,body:unknown)=>Response.json(body,{status});
  if(req.method!=='POST') return new Response('Method Not Allowed',{status:405,headers:{Allow:'POST'}});
  const want=env.ANTICIPY_SERVICE_TOKEN??'',got=req.headers.get('X-Anticipy-Token')??'';
  let difference=want.length^got.length;
  for(let i=0;i<want.length;i++) difference|=want.charCodeAt(i)^(got.charCodeAt(i)||0);
  if(!want||difference) return json(401,{ok:false});
  let body:Record<string,unknown>;
  try {body=await req.json() as Record<string,unknown>;} catch{return json(400,{ok:false});}
  if(!body||typeof body.event_id!=='string'||typeof body.owner_ref!=='string'||!body.event_id||!body.owner_ref)
    return json(400,{ok:false});
  try {
    const out=await dispatchConnectionEvent(env,body.owner_ref,body.event_id);
    return json(out.status==='completed'?200:out.status==='pending'?202:out.status==='missing'?404:503,out);
  } catch {return json(503,{status:'unavailable'});}
}
