/** Read-only server evidence for one persisted inbound SMS and one owner.
 * Unrelated conversation history must not consume the active-task evidence
 * budget. Every delivered revision of a still-open task remains eligible;
 * selecting the newest revision would turn an old "yes" into new authority.
 */
export interface ReplyPresentationsEnv {
  DB: D1Database;
  ANTICIPY_SERVICE_TOKEN?: string;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: {
    "content-type": "application/json; charset=utf-8", "cache-control": "no-store",
  } });
}

function tokenOk(req: Request, env: ReplyPresentationsEnv): boolean {
  const want = env.ANTICIPY_SERVICE_TOKEN || "";
  const got = req.headers.get("X-Anticipy-Token") || "";
  if (!want || want.length !== got.length) return false;
  let difference = 0;
  for (let i = 0; i < got.length; i++) difference |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return difference === 0;
}

const ROW_ID = /^[a-z0-9]{15}$/;
const SERVER_STAMP = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/;
const SAFE_ATTEMPT = "CASE WHEN json_valid(a.text) THEN a.text ELSE '{}' END";
const SAFE_SNAPSHOT = "CASE WHEN json_valid(o.text) THEN o.text ELSE '{}' END";

// Server identities, not message prose. The attempt and outbox external keys
// are globally unique; ownership must still agree on every leg of the chain.
const DELIVERED_CHAIN = `
  FROM events m
  JOIN events o ON o.owner_ref = m.owner_ref AND o.kind = 'reply_outbox'
    AND o.goal = m.id AND o.external_event_id = 'reply-outbox:' || m.id
  JOIN events a ON a.owner_ref = m.owner_ref AND a.kind = 'notification_status'
    AND a.goal = m.id AND a.external_event_id = 'reply-sms:' || m.id
  WHERE m.owner_ref = ?1 AND m.kind = 'anticipy_text'
    AND a.decision = 'sms_delivered'
    AND json_type(${SAFE_ATTEMPT}, '$.provider_id') = 'text'
    AND length(trim(json_extract(${SAFE_ATTEMPT}, '$.provider_id'))) > 0
    AND json_extract(${SAFE_ATTEMPT}, '$.recipient_digest') = ?2
    AND julianday(m.created) < julianday(?3) AND julianday(m.updated) < julianday(?3)
    AND julianday(o.created) < julianday(?3) AND julianday(o.updated) < julianday(?3)
    AND julianday(a.created) < julianday(?3) AND julianday(a.updated) < julianday(?3)`;

interface DeliveredRow {
  id: string; text: string; owner_ref: string; created: string; updated: string;
  observed_delivered_at: string;
}
interface PresentationRow extends DeliveredRow {
  presentation_id: string; snapshot_text: string; outbox_created: string;
  outbox_updated: string; attempt_created: string;
}

export async function replyPresentations(req: Request, env: ReplyPresentationsEnv): Promise<Response> {
  if (req.method !== "POST") return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
  if (!tokenOk(req, env)) return json(401, { ok: false, message: "service token required" });
  let body: Record<string, unknown>;
  try {
    body = await req.json() as Record<string, unknown>;
    if (!body || Array.isArray(body) || typeof body !== "object"
        || Object.keys(body).length !== 2 || !Object.hasOwn(body, "owner_ref") || !Object.hasOwn(body, "event_id")
        || typeof body.owner_ref !== "string" || !ROW_ID.test(body.owner_ref)
        || typeof body.event_id !== "string" || !ROW_ID.test(body.event_id)) throw new Error("invalid identity");
  } catch {
    return json(400, { ok: false, message: "exact owner_ref and event_id row identifiers are required" });
  }
  try {
    const inbound = await env.DB.prepare(`SELECT kind,goal,created,julianday(created) AS stamp
      FROM events WHERE id = ?1 AND owner_ref = ?2`).bind(body.event_id, body.owner_ref)
      .first<{ kind: string; goal: string; created: string; stamp: number | null }>();
    if (!inbound) return json(404, { ok: false, message: "inbound event not found" });
    if (inbound.kind !== "sms_reply" || typeof inbound.goal !== "string" || !inbound.goal.trim()
        || !SERVER_STAMP.test(inbound.created) || typeof inbound.stamp !== "number" || !Number.isFinite(inbound.stamp)) {
      return json(400, { ok: false, message: "a persisted SMS sender and server timestamp are required" });
    }
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",
      new TextEncoder().encode(inbound.goal))), value => value.toString(16).padStart(2, "0")).join("");
    const candidates = await env.DB.prepare(`SELECT m.id,m.text,m.owner_ref,m.created,m.updated,
      a.updated AS observed_delivered_at,o.id AS presentation_id,o.text AS snapshot_text,
      o.created AS outbox_created,o.updated AS outbox_updated,a.created AS attempt_created
      ${DELIVERED_CHAIN}
      AND json_extract(${SAFE_SNAPSHOT}, '$.purpose') = 'task_question'
      AND EXISTS (SELECT 1 FROM jobs j WHERE j.owner_ref = m.owner_ref
        AND j.id = json_extract(${SAFE_SNAPSHOT}, '$.job_id')
        AND j.status IN ('awaiting_confirm','needs_user','queued'))
      ORDER BY julianday(m.created) DESC,m.id DESC LIMIT 201`)
      .bind(body.owner_ref, digest, inbound.created).all<PresentationRow>();
    const recent = await env.DB.prepare(`SELECT m.id,m.text,m.owner_ref,m.created,m.updated,
      a.updated AS observed_delivered_at ${DELIVERED_CHAIN}
      ORDER BY julianday(m.created) DESC,m.id DESC LIMIT 40`)
      .bind(body.owner_ref, digest, inbound.created).all<DeliveredRow>();
    if (candidates.success !== true || recent.success !== true
        || !Array.isArray(candidates.results) || !Array.isArray(recent.results)) {
      throw new Error("unverified evidence result");
    }
    const rows = candidates.results;
    const complete = rows.length <= 200;
    return json(200, { ok: true, owner_ref: body.owner_ref, event_id: body.event_id,
      inbound_created: inbound.created, recipient_digest: digest, complete,
      messages: recent.results,
      presentations: complete ? rows.map(row => ({
        presentation_id: row.presentation_id, snapshot: JSON.parse(row.snapshot_text),
        text: row.text, message_id: row.id, owner_ref: row.owner_ref,
        created: row.created, updated: row.updated, outbox_created: row.outbox_created,
        outbox_updated: row.outbox_updated, attempt_created: row.attempt_created,
        observed_delivered_at: row.observed_delivered_at,
      })) : [],
    });
  } catch {
    // A failed or malformed read is not proof that no question was delivered.
    // Never expose SQL, receipt bodies, provider handles, or another owner.
    return json(503, { ok: false, message: "reply presentation evidence could not be read" });
  }
}
