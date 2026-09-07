import {callModel, type TextCommandEnv} from '../connections/wiring.ts';
import {connectionsFromEnv} from '../connections/provider.ts';
import {createD1Store} from '../connections/store.ts';
import {planTaskAccess} from '../connections/task_access.ts';
import {ownerId} from '../../../../spike/two-hands/src/connections/contract.ts';

type Env = TextCommandEnv & {ANTICIPY_SERVICE_TOKEN?: string};

export async function taskAccess(req: Request, env: Env): Promise<Response> {
  if (req.method !== 'POST') return new Response(null, {status: 405, headers: {Allow: 'POST'}});
  const want = env.ANTICIPY_SERVICE_TOKEN ?? '', got = req.headers.get('X-Anticipy-Token') ?? '';
  let difference = want.length ^ got.length;
  for (let i = 0; i < want.length; i++) difference |= want.charCodeAt(i) ^ (got.charCodeAt(i) || 0);
  if (!want || difference) return new Response(null, {status: 401});
  let body: Record<string, unknown>;
  try {body = await req.json() as Record<string, unknown>;} catch {return new Response(null, {status: 400});}
  if (!body || typeof body.owner_ref !== 'string' || typeof body.job_id !== 'string')
    return new Response(null, {status: 400});
  try {
    const job = await env.DB.prepare('SELECT id,goal,params,status,lane FROM jobs WHERE id=? AND owner_ref=?')
      .bind(body.job_id, body.owner_ref).first<{id:string;goal:string;params:string;status:string;lane:string}>();
    if (!job) return new Response(null, {status: 404});
    // Lane/status are execution metadata, not an interpretation of prose.
    if (job.status !== 'queued' || !['', 'browser'].includes((job.lane || '').trim().toLowerCase()))
      return new Response(null, {status: 204});
    if (!env.COMPOSIO_API_KEY) return new Response(null, {status: 503});
    const params = JSON.parse(job.params || '{}');
    const ids: unknown = params?._workflow?.source_event_ids;
    const sourceIds = Array.isArray(ids) ? ids.filter((id): id is string => typeof id === 'string') : [];
    const source = sourceIds.length
      ? (await env.DB.prepare(`SELECT text,source,speaker FROM events WHERE owner_ref=? AND id IN (${sourceIds.map(() => '?').join(',')})`)
          .bind(body.owner_ref, ...sourceIds).all()).results : [];
    const conversation = await env.DB.prepare(`SELECT kind,text,created FROM events WHERE owner_ref=?
      AND kind IN ('sms_reply','app_reply','transcript','anticipy_says','anticipy_text')
      ORDER BY created DESC,id DESC LIMIT 40`).bind(body.owner_ref).all();
    const store = createD1Store(env), owner = ownerId(body.owner_ref);
    const connections = await store.connectionsForOwner(owner);
    const provider = connectionsFromEnv(env);
    const offer = await planTaskAccess({task:{goal:job.goal,params}, source,
      conversation:(conversation.results ?? []).reverse(),
      connections:connections.map(row => ({toolkit:row.toolkit,status:row.status}))}, {
      judge: (system, context) => callModel(env, [{role:'system',content:system},
        {role:'user',content:JSON.stringify(context)}]),
      catalog: query => provider.search(query, {limit:20}),
    });
    if (offer.kind !== 'offer') return new Response(null, {status:offer.kind === 'none' ? 204 : 503});
    const current = await env.DB.prepare('SELECT status FROM jobs WHERE id=? AND owner_ref=?')
      .bind(body.job_id, body.owner_ref).first<{status:string}>();
    if (current?.status !== 'queued') return new Response(null, {status:204});
    // Ask first. A link minted during quiet hours could expire before the owner
    // wakes. Their contextual acceptance goes through the existing text-command
    // path, which creates a fresh consent link only when they want it.
    return Response.json({line: `${offer.reason}\nWould you like to connect ${offer.name}?`});
  } catch {return new Response(null, {status:503});}
}
