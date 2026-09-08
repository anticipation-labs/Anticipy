/** Connection commands are sequenced once across SMS ingress and brain polls.
 * Models plan with the same owner conversation; D1 owns retries and effects.
 * No sentence is classified here. The saved event, never caller-supplied text,
 * supplies identity, source and words. */
import { ownerId } from '../../../../spike/two-hands/src/connections/contract.ts';
import { ownerPhone, prepareTextCommand, runTextCommandPlan,
  type TextCommandEnv, type TextCommandOutcome, type TextCommandContext } from './wiring.ts';
import { sendText, chooseProvider } from '../messaging.ts';
import { sha256Hex } from '../llm.ts';

type Event = { id: string; owner_ref: string; kind: string; source: string;
  speaker: string; text: string; created: string; goal: string };
type Run = { state: string; lease_until: number; outcome: string };
export type DispatchResult = { status: 'completed'; outcome: TextCommandOutcome }
  | { status: 'pending' | 'missing' | 'unavailable' };
const LEASE_MS = 300_000; // I/O lease, never an inference about human language.
const untouched = (): TextCommandOutcome => ({kind:'not_for_us',detail:'left to conversation',replied:false,question:false});

export async function dispatchConnectionEvent(
  env: TextCommandEnv, owner: string, eventId: string,
): Promise<DispatchResult> {
  const ev = await env.DB.prepare('SELECT id, owner_ref, kind, source, speaker, text, created, goal FROM events WHERE id=? AND owner_ref=?')
    .bind(eventId, owner).first<Event>();
  if (!ev) return {status:'missing'};
  const inApp = ev.kind === 'app_reply' || (ev.kind === 'transcript' && ev.source === 'typed');
  if (!inApp && ev.kind !== 'sms_reply') return {status:'completed', outcome:untouched()};
  const token = crypto.randomUUID();
  const now = Date.now();
  const won = await env.DB.prepare(`INSERT INTO connection_command_runs
    (event_id,owner_ref,state,lease_token,lease_until) VALUES (?,?,'planning',?,?)
    ON CONFLICT(event_id) DO UPDATE SET lease_token=excluded.lease_token,lease_until=excluded.lease_until
    WHERE connection_command_runs.owner_ref=excluded.owner_ref
      AND connection_command_runs.state='planning' AND connection_command_runs.lease_until < ?`)
    .bind(eventId,owner,token,now+LEASE_MS,now).run();
  const replyKey = `connection-reply:${eventId}`;
  if (!won.meta?.changes) {
    const old = await env.DB.prepare('SELECT state,lease_until,outcome FROM connection_command_runs WHERE event_id=? AND owner_ref=?')
      .bind(eventId,owner).first<Run>();
    if (!old) return {status:'missing'};
    if (old.state === 'completed') return {status:'completed',outcome:JSON.parse(old.outcome)};
    if (old.state === 'executing' && old.lease_until < now) {
      // The external call may have succeeded. Recover its durable answer if
      // present; otherwise acknowledge uncertainty, without repeating the call.
      const saved = await env.DB.prepare('SELECT decision FROM events WHERE owner_ref=? AND external_event_id=?')
        .bind(owner,replyKey).first<{decision:string}>();
      if (saved) return {status:'completed', outcome:{kind:'ask_which_app',detail:'recovered saved reply',replied:true,question:saved.decision==='ask'}};
      const text = "I couldn't confirm whether that app connection changed. Please check its status in Settings before trying again.";
      const written = await saveReply(env,ev,replyKey,text,true);
      return written ? {status:'completed',outcome:{kind:'ask_which_app',detail:'effect uncertain; not repeated',replied:true,question:true}} : {status:'unavailable'};
    }
    return {status:'pending'};
  }
  try {
    const rows = await env.DB.prepare(`SELECT kind,text,created FROM events
      WHERE owner_ref=? AND id<>? AND created<=?
      AND kind IN ('sms_reply','app_reply','transcript','anticipy_says','anticipy_text')
      ORDER BY created DESC,id DESC LIMIT 40`).bind(owner,eventId,ev.created).all<TextCommandContext['conversation'][number]>();
    const context: TextCommandContext = {source:ev.source,speaker:ev.speaker,conversation:(rows.results??[]).reverse()};
    if (ev.kind === 'app_reply') {
      let reference: unknown;
      try { reference=JSON.parse(ev.goal); } catch { reference=null; }
      if (reference && typeof reference==='object' && 'reply_to_job_id' in reference
          && typeof reference.reply_to_job_id==='string') {
        context.reply_target=await env.DB.prepare('SELECT goal,result,status FROM jobs WHERE id=? AND owner_ref=?')
          .bind(reference.reply_to_job_id,owner).first<{goal:string;result:string;status:string}>();
      }
    }
    const plan = context.reply_target === null
      ? {kind:'not_for_us' as const,because:'unclear' as const}
      : await prepareTextCommand(env,owner,ev.text,context);
    // Read-only planning may time out and be replaced. Only the current
    // holder can cross this fence into the executor.
    const execution = await env.DB.prepare(`UPDATE connection_command_runs SET state='executing',lease_until=?
      WHERE event_id=? AND owner_ref=? AND state='planning' AND lease_token=?`)
      .bind(Date.now()+LEASE_MS,eventId,owner,token).run();
    if (!execution.meta?.changes) return {status:'pending'};
    const outcome = await runTextCommandPlan(plan,env,{
      channel:inApp?'ios':'sms',
      async deliver(line,asks) {
        const saved = await saveReply(env,ev,replyKey,line,asks);
        if (!saved) return false;
        // The same durable outbox serves app and SMS replies. The owner brain
        // claims delivery independently, so provider I/O cannot lose an answer.
        return true;
      },
    });
    if (plan.kind !== 'not_for_us' && !outcome.replied) {
      await env.DB.prepare(`UPDATE connection_command_runs SET lease_until=0
        WHERE event_id=? AND owner_ref=? AND lease_token=?`)
        .bind(eventId,owner,token).run();
      return {status:'unavailable'};
    }
    await env.DB.prepare(`UPDATE connection_command_runs SET state='completed',outcome=?
      WHERE event_id=? AND owner_ref=? AND lease_token=?`).bind(JSON.stringify(outcome),eventId,owner,token).run();
    if (outcome.replied) await env.DB.prepare("UPDATE events SET decision=? WHERE id=? AND owner_ref=? AND decision=''")
      .bind(outcome.question?'ask':'ignore',eventId,owner).run();
    return {status:'completed',outcome};
  } catch (error) {
    console.log('connection dispatch failed', String(error));
    // A failed plan can retry. Once executing, retain the uncertainty fence.
    await env.DB.prepare("UPDATE connection_command_runs SET lease_until=0 WHERE event_id=? AND owner_ref=? AND lease_token=? AND state='planning'")
      .bind(eventId,owner,token).run();
    return {status:'unavailable'};
  }
}

async function saveReply(env: TextCommandEnv, ev: Event, key: string, line: string, asks: boolean): Promise<boolean> {
  const stamp = new Date().toISOString().replace('T',' ');
  const id = crypto.randomUUID().replaceAll('-','').slice(0,15);
  const result = await env.DB.batch([env.DB.prepare(`INSERT INTO events
    (id,created,updated,device_id,kind,text,decision,source,owner_ref,parent_line,external_event_id)
    SELECT ?,?,?,'anticipy-connections','anticipy_text',?,?,?,?,?,?
    WHERE EXISTS(SELECT 1 FROM owners WHERE id=?)
    ON CONFLICT(external_event_id) WHERE external_event_id!='' DO NOTHING`)
    .bind(id,stamp,stamp,line,asks?'ask':'ignore',ev.source,ev.owner_ref,ev.id,key,ev.owner_ref),
    env.DB.prepare(`INSERT INTO events
      (id,created,updated,device_id,kind,text,decision,goal,owner_ref,external_event_id)
      SELECT ?,?,?,'anticipy-connections','reply_outbox','','reply_pending',id,owner_ref,('reply-outbox:' || id)
      FROM events WHERE owner_ref=? AND external_event_id=?
      ON CONFLICT(external_event_id) WHERE external_event_id!='' DO NOTHING`)
      .bind(crypto.randomUUID().replaceAll('-','').slice(0,15),stamp,stamp,ev.owner_ref,key)]);
  if (result[0].meta?.changes) {
    // Same unique claim protocol as brain/reply_delivery.py. Either process may
    // deliver, but only the INSERT winner sends, and both preserve uncertainty.
    try {
      const to = await ownerPhone(env)(ownerId(ev.owner_ref));
      if (to && chooseProvider(env) !== 'none') {
        const recipient_digest = await sha256Hex(to);
        const attemptId = crypto.randomUUID().replaceAll('-','').slice(0,15);
        const claimed = await env.DB.prepare(`INSERT INTO events
          (id,created,updated,device_id,kind,text,decision,goal,owner_ref,external_event_id)
          SELECT ?,?,?,'anticipy-connections','notification_status',?,'sms_unconfirmed',?,?,?
          WHERE EXISTS(SELECT 1 FROM owners WHERE id=?)
          ON CONFLICT(external_event_id) WHERE external_event_id!='' DO NOTHING`)
          .bind(attemptId,stamp,stamp,JSON.stringify({state:'sms_unconfirmed',recipient_digest}),
            id,ev.owner_ref,`reply-sms:${id}`,ev.owner_ref).run();
        if (claimed.meta?.changes) {
          // The claim awaited storage. The owner may have revoked or changed
          // their number since the earlier lookup; it cannot authorize this
          // final provider call. Unknown lookup retains the uncertainty fence.
          const current = await ownerPhone(env)(ownerId(ev.owner_ref));
          if (current !== to) {
            await env.DB.prepare('UPDATE events SET decision=?,text=?,updated=? WHERE id=? AND owner_ref=?')
              .bind('sms_skipped',JSON.stringify({state:'sms_skipped',recipient_digest}),
                new Date().toISOString().replace('T',' '),attemptId,ev.owner_ref).run();
            return true; // The answer is durably visible in the owner's app.
          }
          const sent = await sendText(env,to,line,{tag:'connection reply'});
          const state = sent.ok ? (['DELIVERED','READ'].includes(sent.status.toUpperCase()) ? 'sms_delivered' : 'sms_accepted') : 'sms_unconfirmed';
          await env.DB.prepare('UPDATE events SET decision=?,text=?,updated=? WHERE id=? AND owner_ref=?')
            .bind(state,JSON.stringify({state,provider_id:sent.ok?sent.id:'',recipient_digest}),
              new Date().toISOString().replace('T',' '),attemptId,ev.owner_ref).run();
        }
      }
    } catch { /* durable pending reply and attempt fence survive */ }
  }
  return !!result[0].meta?.changes;
}
