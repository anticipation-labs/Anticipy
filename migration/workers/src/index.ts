/**
 * src/index.ts — the Worker entry point.
 *
 * Replaces the PocketBase binary at backend/Dockerfile. It serves, in order:
 *
 *   /api/health                       PocketBase's liveness probe (CONTRACT.md §0.5)
 *   /api/collections/{n}/records[...] the generic records API   (src/pb/records.ts)
 *   /api/collections/owners/auth-*    the auth endpoints        (src/pb/auth.ts)
 *   /api/files/{c}/{id}/{name}        evidence, from R2         (src/assets.ts)
 *   the 55 routerAdd routes                                     (Phase 5)
 *   /internal.html, /*.zip, /mac/*    static assets             (src/assets.ts)
 *
 * WHAT IS NOT HERE, ON PURPOSE:
 *   /api/realtime. The audit says it is guarded but has no live consumer, and
 *   that claim is CONFIRMED — see ARCHITECTURE.md §8. It is not ported.
 *   A non-GET to it answers 410 with a sentence naming this decision, so a
 *   future client that tries gets an answer instead of a silent nothing.
 */
import { resetRequest, resetConfirm, type ResetEnv } from "./routes/password_reset.ts";
import { accountDelete } from "./routes/account_delete.ts";
import { smsInbound, transcriptionToken, type SmsEnv } from "./routes/sms.ts";
import { workerOwners, purgeAudit, authClaim, phoneRemove, profileUpsert, type ServiceEnv } from "./routes/service.ts";
import { agentRegister, agentKey, agentLlm, agentCaptcha, agentUpgradeCredential, type AgentEnv } from "./routes/agent.ts";
import { COLLECTIONS } from "./pb/schema.ts";
import { health, notFound, refuse, json } from "./pb/wire.ts";
import * as records from "./pb/records.ts";
import { authWithPassword, authRefresh, verifyToken } from "./pb/auth.ts";
import { runChain, type Ctx, type Principal } from "./policy/chain.ts";
import { guard } from "./policy/guard.ts";
import { ownerProfileOwner } from "./policy/owner_profile_owner.ts";
import { researchLane } from "./policy/research_lane.ts";
import { workflowGuard } from "./policy/workflow_guard.ts";
import { scheduled as cronHandler, type CronEnv } from "./cron.ts";

export { PairCodeCounter } from "./do/PairCodeCounter.ts";

export interface Env extends CronEnv {
  DB: D1Database;
  EVIDENCE: R2Bucket;
  ASSETS: Fetcher;
  PAIR_CODE_COUNTER: DurableObjectNamespace;
  ANTICIPY_SERVICE_TOKEN: string;
  ANTICIPY_AUTH_SECRET: string;
  ANTICIPY_INTERNAL_KEY: string;
  ANTICIPY_VAULT_KEY_GCM: string;
}

/**
 * migration/spec/CONTRACT.md §0.4. The order is load-bearing and the reason is
 * the status code: guard refuses before research_lane and workflow_guard ever
 * see the request, so a guard failure is a 403 and never a 409.
 */
const CHAIN = [guard, ownerProfileOwner, researchLane, workflowGuard] as const;

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (path === "/api/health" && method === "GET") return health();

    // The front door. Outside /api/collections/, so the data-API guard never
    // sees these -- they defend themselves. See routes/password_reset.ts.
    if (path === "/auth/reset/request" && method === "POST") {
      return resetRequest(request, env as unknown as ResetEnv);
    }
    if (path === "/auth/reset/confirm" && method === "POST") {
      return resetConfirm(request, env as unknown as ResetEnv);
    }
    // The privacy page's promise. The one irreversible operation here.
    if (path === "/me/delete" && method === "POST") {
      return accountDelete(request, env as never);
    }

    // The extension's lifecycle. /agent/key answers llm_proxy, never a vendor
    // credential -- the extension is a published zip.
    if (path === "/agent/register" && method === "POST") {
      return agentRegister(request, env as unknown as AgentEnv);
    }
    if (path === "/agent/key" && method === "GET") {
      return agentKey(request, env as unknown as AgentEnv);
    }
    if (path === "/agent/llm" && method === "POST") {
      return agentLlm(request, env as unknown as AgentEnv);
    }
    if (path.startsWith("/agent/solve-captcha") && method === "POST") {
      return agentCaptcha(request, env as unknown as AgentEnv);
    }
    if (path === "/agent/upgrade-credential" && method === "POST") {
      return agentUpgradeCredential(request, env as unknown as AgentEnv);
    }

    // The small service routes. /worker/owners returns two fields and nothing
    // else -- it is authorised by a shared token every worker carries.
    if (path === "/worker/owners" && method === "GET") {
      return workerOwners(request, env as unknown as ServiceEnv);
    }
    if (path === "/admin/purge-audit" && method === "POST") {
      return purgeAudit(request, env as unknown as ServiceEnv);
    }
    if (path === "/auth/claim" && method === "POST") {
      return authClaim(request, env as unknown as ServiceEnv);
    }
    if (path === "/me/phone/remove" && method === "POST") {
      return phoneRemove(request, env as unknown as ServiceEnv);
    }
    if (path === "/me/profile/upsert" && method === "POST") {
      return profileUpsert(request, env as unknown as ServiceEnv);
    }

    // Twilio's inbound webhook. TWILIO_AUTH_TOKEN is the only thing that can
    // validate X-Twilio-Signature -- there is no API-key equivalent.
    if (path === "/sms/inbound" && method === "POST") {
      return smsInbound(request, env as unknown as SmsEnv);
    }
    if (path === "/transcription/token" && method === "POST") {
      return transcriptionToken(request, env as unknown as SmsEnv);
    }

    // --- the auth endpoints. guard.pb.js:367-370 keeps these open. ---------
    if (path === "/api/collections/owners/auth-with-password" && method === "POST") {
      return authWithPassword(env, await readBody(request) ?? {});
    }
    if (path === "/api/collections/owners/auth-refresh" && method === "POST") {
      return authRefresh(env, request.headers.get("Authorization") ?? "");
    }

    // --- realtime: dropped, and it says so -- but only to a caller who got
    // past the guard. The contract (§2.2) is that a non-GET on /api/realtime is
    // GUARDED, and guard.pb.js treats it as part of the data API for exactly
    // that reason: opening the SSE channel is harmless on its own (EventSource
    // cannot send headers), the POST that ATTACHES subscriptions is not.
    // Answering 410 first would tell an unauthenticated stranger what this
    // backend does and does not serve, which is disclosure, not an answer.
    if (path === "/api/realtime" && method !== "GET") {
      // guard.pb.js:33-35 counts this as part of the data API and refuses it
      // with the same "forbidden" as any collection. Same shape here: a
      // stranger gets the refusal, not a description of the backend.
      const want = (env as { ANTICIPY_SERVICE_TOKEN?: string }).ANTICIPY_SERVICE_TOKEN || "";
      const got = request.headers.get("X-Anticipy-Token") || "";
      let ok = want.length > 0 && got.length === want.length;
      if (ok) {
        let d = 0;
        for (let i = 0; i < got.length; i++) d |= got.charCodeAt(i) ^ want.charCodeAt(i);
        ok = d === 0;
      }
      if (!ok) {
        return new Response(JSON.stringify({ error: "forbidden" }),
          { status: 403, headers: { "content-type": "application/json" } });
      }
    }
    if (path === "/api/realtime") {
      return refuse(410, "realtime is not served by this backend",
        "no shipped client subscribes; the extension polls on a 30s alarm "
        + "(extension/background.js:1721-1729). See migration/workers/ARCHITECTURE.md §8.");
    }

    // --- the generic records API ------------------------------------------
    const m = path.match(/^\/api\/collections\/([A-Za-z0-9_]+)\/records(?:\/([^/]+))?$/);
    if (m) return handleRecords(request, env, url, m[1], m[2] ?? null);

    // --- static assets. ARCHITECTURE.md §9. -------------------------------
    if (isStaticPath(path)) return env.ASSETS.fetch(request);

    return notFound();
  },

  scheduled(event: ScheduledController, env: Env, ctx: ExecutionContext) {
    return cronHandler(event, env, ctx);
  },
};

// ---------------------------------------------------------------------------

async function handleRecords(
  request: Request, env: Env, url: URL, collectionName: string, recordId: string | null,
): Promise<Response> {
  const method = request.method;
  const body = await readBody(request);
  const principal = await resolvePrincipal(request, env);

  const ctx: Ctx & { db: D1Database } = {
    request, url, method, path: url.pathname, body, principal,
    worker: workerMarker(request, env),
    forcedScope: null,
    extraAst: null,
    db: env.DB,
  };

  const def = records.resolveCollection(collectionName);
  if (def) { ctx.collection = def; ctx.recordId = recordId; }

  // THE CHAIN RUNS BEFORE THE COLLECTION IS EVEN RESOLVED, because guard.pb.js
  // answers 403 for an unknown collection under an account token and that
  // answer must not become a 404. CONTRACT.md §2.7.
  const refusal = await runChain(CHAIN, ctx, env);
  if (refusal) return refusal;

  if (!def) return notFound();

  const req: records.RecordsRequest = {
    collection: def, recordId, method, url, body, principal,
    forcedScope: ctx.forcedScope, extraAst: ctx.extraAst,
  };

  switch (method) {
    case "GET":    return recordId ? records.view(env, req) : records.list(env, req);
    case "POST":   return recordId ? notFound() : records.create(env, req);
    case "PATCH":  return recordId ? records.update(env, req) : notFound();
    case "DELETE": return recordId ? records.remove(env, req) : notFound();
    default:       return json(405, { code: 405, message: "Method not allowed.", data: {} });
  }
}

/**
 * Which of the four principals is this?
 *
 * ORDER MATTERS AND IS NOT THE OBVIOUS ONE. An agent id that fails to resolve
 * must NOT fall through to anonymous — guard.pb.js:203-220 records that as a
 * shipped bug where a revoked credential silently received the anonymous
 * surface. So a present-but-unresolved agent header yields `anonymous` here
 * and guard.ts turns it into a 403 by checking the header itself.
 */
async function resolvePrincipal(request: Request, env: Env): Promise<Principal> {
  const h = request.headers;

  // Rung 0. Constant-time compare: a length-varying `===` on a shared secret
  // leaks its length, and this token is the god credential.
  const presented = h.get("X-Anticipy-Token") ?? "";
  if (env.ANTICIPY_SERVICE_TOKEN && timingSafeEqual(presented, env.ANTICIPY_SERVICE_TOKEN)) {
    return { kind: "service" };
  }

  // Rung 1. A token shorter than 40 characters cannot match any row — that is
  // the column's own minimum (1700000026_agent_tokens.js:12) — so a short or
  // missing token is this same failed lookup with the query skipped.
  const agentId = h.get("X-Anticipy-Agent-ID") ?? "";
  const agentToken = h.get("X-Anticipy-Agent-Token") ?? "";
  if (agentId && agentToken.length >= 40) {
    const row = await env.DB.prepare(
      `SELECT "id","agent_id","owner_ref" FROM "agents"
        WHERE "agent_id" = ?1 AND "agent_token" = ?2 LIMIT 1`,
    ).bind(agentId, agentToken).first<Record<string, unknown>>();
    if (row) {
      return { kind: "agent", agentRowId: String(row.id),
               agentId: String(row.agent_id), ownerRef: String(row.owner_ref ?? "") };
    }
    return { kind: "anonymous" };   // guard.ts refuses; it does not fall through
  }
  if (agentId) return { kind: "anonymous" };

  // Rung 5.
  const authHeader = h.get("Authorization") ?? "";
  if (authHeader) {
    const v = await verifyToken(env, authHeader);
    if (v) return { kind: "account", ownerId: String(v.row.id), row: v.row };
  }

  // There is no superuser principal yet. PocketBase's `_superusers` collection
  // has NO D1 equivalent (migration/d1/schema.sql:158-163) — HQ identity is
  // internal_sessions + internal_people.code_hash, and product identity is
  // `owners`. So the dashboard rung (guard.pb.js:394-396) has nothing to
  // resolve against and every superuser-gated route must be re-homed on the
  // internal key. ARCHITECTURE.md §4.4.
  return { kind: "anonymous" };
}

/**
 * research_lane.pb.js:429-432. `X-Anticipy-Worker` is a ROUTING marker and not
 * a credential (brain/pb.py:19-26); the service token is what authenticates.
 * When no service token is configured the marker alone is believed, which is
 * the deployed behaviour and is preserved so a local rig keeps working.
 */
function workerMarker(request: Request, env: Env): { fromWorker: boolean } {
  const marker = !!request.headers.get("X-Anticipy-Worker");
  if (!env.ANTICIPY_SERVICE_TOKEN) return { fromWorker: marker };
  return {
    fromWorker: marker
      && timingSafeEqual(request.headers.get("X-Anticipy-Token") ?? "",
                         env.ANTICIPY_SERVICE_TOKEN),
  };
}

/**
 * The equivalent of `$security.equal`, which internal_hq.pb.js uses at 40-odd
 * call sites and which guard.pb.js:37 does NOT (it uses `===`). Every secret
 * comparison in this Worker goes through here.
 *
 * The byte loop runs over the longer of the two, so the answer does not depend
 * on WHERE the first difference is. It does still depend on the LENGTHS, which
 * is the same concession Node's crypto.timingSafeEqual makes by refusing
 * mismatched lengths outright; the secrets compared here are fixed-length
 * tokens, so nothing is learned from it.
 */
function timingSafeEqual(a: string, b: string): boolean {
  if (!a || !b) return false;
  const enc = new TextEncoder();
  const ab = enc.encode(a);
  const bb = enc.encode(b);
  let diff = ab.byteLength ^ bb.byteLength;
  const n = Math.max(ab.byteLength, bb.byteLength);
  for (let i = 0; i < n; i++) diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  return diff === 0;
}

/** Parse once. PocketBase's e.requestInfo().body is also parse-once. */
async function readBody(request: Request): Promise<Record<string, unknown> | null> {
  if (request.method === "GET" || request.method === "HEAD") return null;
  const ct = request.headers.get("content-type") ?? "";
  if (!ct.includes("application/json")) return null;
  try { return await request.json<Record<string, unknown>>(); }
  catch { return null; }
}

const STATIC_PREFIXES = [
  "/internal.html", "/setup.html", "/privacy.html", "/mac.html",
  "/site.css", "/theme.js", "/mac/",
];
function isStaticPath(path: string): boolean {
  return STATIC_PREFIXES.some((p) => path === p || path.startsWith(p))
    || path.endsWith(".zip");
}
