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
import { hqHealth, hqLogin, hqGate, hqGone, hqPage, hqCors, HQ_DEAD_ROUTES, type HqEnv } from "./routes/hq.ts";
import { hqSession, hqSessionEnd, hqMe, hqClerkExchange, hqState, hqMePassword } from "./routes/hq_data.ts";
import { hqPeopleCreate, hqPeopleUpdate } from "./routes/hq_people.ts";
import { hqTodoCreate, hqTodoUpdate, hqTodoDelete } from "./routes/hq_todos.ts";
import {
  hqEventCreate, hqEventDelete, hqTrackUpsert, hqTrackDelete,
  hqExpenseCreate, hqExpenseDelete, hqNoteUpsert, hqNoteDelete,
} from "./routes/hq_boards.ts";
import {
  hqPasswordUpsert, hqPasswordReveal, hqPasswordDelete, hqPeopleCode,
  hqNotifsRead, hqSettings,
} from "./routes/hq_vault.ts";
import {
  hqCommentCreate, hqCommentUpdate, hqCommentDelete,
  hqReminderCreate, hqReminderDelete, hqCalendar,
} from "./routes/hq_threads.ts";
import { hqAssistant } from "./routes/hq_assistant.ts";
import { hqPeopleFaces, hqFellows } from "./routes/hq_fellows.ts";
import { referralHop, type FellowEnv } from "./routes/fellowship.ts";
import {
  fellowsHealth, fellowsCode, fellowsVerify, fellowsStart, fellowsConfirm,
  fellowsMe, fellowsApply, fellowsProgress, fellowsProfile, fellowsSubmissions,
  fellowsSubmissionsRemove, fellowsGuardianLink, fellowsGuardianGet,
  fellowsGuardianPost, internalFellowsRemove, internalFellowsSubmissionsRemove,
  internalFellowsSubmissionsRelease,
} from "./routes/fellows.ts";
import type { FellowsEnv } from "./routes/fellows_base.ts";
import { smsInbound, transcriptionToken, type SmsEnv } from "./routes/sms.ts";
import { sendblueInbound, type SendblueEnv } from "./routes/sendblue.ts";
import { connectRoute, installConnectWiring, type ConnectEnv } from "./routes/connect.ts";
import { connectionsApiRoute, type ConnectionsApiEnv } from "./routes/connections_api.ts";
import {
  connectionsWebhook, CONNECTIONS_WEBHOOK_PATH, type ConnectionsWebhookEnv,
} from "./routes/connections_webhook.ts";
import { connectAuthWiring, connectWiring } from "./connections/wiring.ts";
import {
  connectAuthRoute, connectSession, installConnectAuthWiring,
  type ConnectAuthEnv,
} from "./routes/connect_auth.ts";
import { installConnectSessionReader } from "./routes/connect.ts";
import { workerOwners, purgeAudit, authClaim, phoneRemove, profileUpsert, type ServiceEnv } from "./routes/service.ts";
import { agentRegister, agentKey, agentLlm, agentCaptcha, agentUpgradeCredential, type AgentEnv } from "./routes/agent.ts";
import {
  serveFile, shareEvidence, depositEvidenceImage, discardEvidenceImage, type AssetEnv,
} from "./assets.ts";
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
  // /agent/llm — src/llm.ts header lists what each one is. The keys are
  // secrets; the two model names are plain vars; LLM_PROVIDER_BASE is a
  // test-only loopback override that is never set on a deployed Worker.
  GEMINI_API_KEY?: string;
  GOOGLE_API_KEY?: string;
  OPENROUTER_API_KEY?: string;
  ANTICIPY_BROWSER_MODEL?: string;
  ANTICIPY_VISION_MODEL?: string;
  LLM_PROVIDER_BASE?: string;
  // /sms/sendblue — routes/sendblue.ts. The secret is a secret (the value
  // Sendblue's dashboard sends in sb-signing-secret); the number is a plain
  // var, an inbound allowlist exactly like TWILIO_PHONE_NUMBER.
  SENDBLUE_WEBHOOK_SECRET?: string;
  SENDBLUE_FROM_NUMBER?: string;
}

/**
 * migration/spec/CONTRACT.md §0.4. The order is load-bearing and the reason is
 * the status code: guard refuses before research_lane and workflow_guard ever
 * see the request, so a guard failure is a 403 and never a 409.
 */
const CHAIN = [guard, ownerProfileOwner, researchLane, workflowGuard] as const;

/**
 * THE CONNECT WIRING, installed once when this module loads.
 *
 * routes/connect.ts declares four ports and refuses to guess at any of them: an
 * unwired Worker answers 503 on every /c/ leg rather than draw a consent page it
 * cannot fill in. Until this line existed, nothing anywhere called
 * `installConnectWiring`, so every /c/ leg in this repo answered 503 to every
 * token there has ever been while five tested modules sat behind it. A part
 * nothing calls is not a feature.
 *
 * MEASURED ON LIVE, 2026-09-06: `GET https://api.anticipy.ai/c/<43 chars>`
 * answers 404 while `/api/health` answers 200 — the deployed Worker predates the
 * whole `/c/` prefix, so this line is repo-green and NOT yet Law-3 done. The
 * live leg goes green when that URL answers 401 (the sign-in page, for any
 * token) rather than 404 (not deployed) or 503 (deployed, secrets unset).
 *
 * It is a FUNCTION of env and it runs at module load rather than per request:
 * a Worker's bindings and secrets do not exist when a module is evaluated, so
 * the ports are built on the first request that needs them. See
 * src/connections/wiring.ts for what each one is, and for why a Worker missing
 * the DB binding, the vendor secret or a model key installs this anyway and
 * then answers the honest 503 instead of a page that never loads.
 */
installConnectWiring(connectWiring);
// The phone-code half, and the reader that lets its cookie count.
//
// WITHOUT THESE TWO LINES THE FEATURE IS UNREACHABLE, which is not a figure of
// speech: the connect page arrives by TEXT and opens in Safari, where the
// browser holds no account cookie, so every leg answered "Sign in to finish"
// to every human being. Measured live on 2026-09-06 with everything else green.
//
// The order matters only in that both must happen before the first request.
// `connectAuthWiring` shares connect.ts's own link store (see wiring.ts), so
// the two routes can never disagree about whether a link is still live, and
// `connectSession` widens "who is asking" from the account cookie alone to
// "the account cookie OR a code cookie minted for this very link".
installConnectAuthWiring(connectAuthWiring);
installConnectSessionReader(connectSession);

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
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
    // Sendblue's webhook: inbound iMessage/SMS AND status updates for texts we
    // sent, on one URL, proven by the dashboard's secret in sb-signing-secret.
    // It lands the same events row /sms/inbound lands (src/pb/sender.ts), so
    // the brain cannot tell the carriers apart.
    if (path === "/sms/sendblue" && method === "POST") {
      return sendblueInbound(request, env as unknown as SendblueEnv);
    }
    if (path === "/transcription/token" && method === "POST") {
      return transcriptionToken(request, env as unknown as SmsEnv);
    }

    // The connections vendor's ONE webhook. It publishes nothing for a
    // successful connection -- only that a connected account has expired -- so
    // this is the only way we ever learn a credential died at the far end
    // without a task failing in front of the owner first.
    //
    // The whole path is handed over, unknown methods included, so it answers
    // 405 with an Allow header rather than the generic 404: a webhook URL that
    // 404s reads, in a vendor dashboard, as a URL somebody typed wrong.
    //
    // Outside /api/collections/ like the other doors: it defends itself, and
    // the whole of that defence is an HMAC over the raw body. An unsigned POST
    // here would strip the API hand off a working connection and text its owner
    // about it. See routes/connections_webhook.ts.
    if (path === CONNECTIONS_WEBHOOK_PATH) {
      return connectionsWebhook(request, env as unknown as ConnectionsWebhookEnv);
    }

    // Settings -> Connected Apps, the six routes the phone already calls.
    //
    // The whole prefix is handed over, unknown methods included, so the route
    // can answer 405 with an Allow header rather than fall through to the
    // generic 404: a GET on /link or /writes must be REFUSED and not routed
    // elsewhere, or a link prefetcher spends this owner's connect-link budget
    // and an address-bar preload flips a write toggle.
    //
    // Outside /api/collections/ like the reset, delete and /c/ doors, so the
    // data-API guard never sees it -- it defends itself, and the whole of that
    // defence is that the owner comes from the token: there is no path segment,
    // query key or body field anywhere in routes/connections_api.ts through
    // which a caller can name somebody else. See that file's header.
    if (path === "/me/connections" || path.startsWith("/me/connections/")) {
      return connectionsApiRoute(request, env as unknown as ConnectionsApiEnv);
    }

    // OUR connect link -- /c/{token}, /c/{token}/go, /c/{token}/done. The page
    // where an owner connects one of their own apps, the tap that mints the
    // vendor's link (the only place one is ever produced), and the vendor's
    // callback, which is the only signal a connection exists.
    //
    // Outside /api/collections/ like the reset and delete doors, so the data-API
    // guard never sees it: it defends itself, and it has to, because a link in a
    // text is not a credential. Every leg requires the signed-in session to BE
    // the owner the token was minted for, and a caller who has proved nothing
    // gets one byte-identical answer for every token there is. See
    // routes/connect.ts.
    //
    // The whole prefix is handed over, including unknown methods, so the route
    // can answer 405 with an Allow header rather than fall through to the
    // generic 404 -- a GET on /go must be REFUSED, not routed elsewhere, or a
    // link prefetcher spends the owner's single-use token before they tap it.
    if (path.startsWith("/c/")) {
      // The code routes first, and they answer `null` for anything that is not
      // theirs — so this is a chain, not a branch, and connect.ts keeps owning
      // every path it owned before.
      const authed = await connectAuthRoute(request, env as unknown as ConnectAuthEnv);
      if (authed) return authed;
      // ctx IS LOAD-BEARING, not decoration. /go hands the connection backup
      // (connections/wait.ts) to ctx.waitUntil the moment the vendor link is
      // minted, and a Worker cancels background work the instant the response
      // is returned -- so without it the poll starts and is killed, and a
      // browser that dies between the vendor's consent screen and /done leaves
      // an account bound at the vendor with no row here and nothing that would
      // ever mention it again. The vendor publishes no success webhook, so
      // nothing arrives later to repair that. connect.ts refuses to start the
      // poll at all when it is handed no ctx, and says so once per redirect,
      // rather than starting a timer a Worker will kill.
      return connectRoute(request, env as unknown as ConnectEnv, undefined, ctx);
    }

    // --- the referral hop. fellowship.pb.js, recovered. ------------------
    // Above HQ because it is not HQ and carries no key: a fellow's link is
    // public by definition.
    if (path.startsWith("/r/") && method === "GET") {
      return referralHop(request, env as unknown as FellowEnv,
                         path.slice("/r/".length));
    }

    // --- the public fellowship API. fellowship.pb.js, recovered. ---------
    // A separate SITE (anticipyfellowship.com) calls these on this same
    // backend, so they must answer here once traffic moves. No HQ key: a
    // fellow signing up holds nothing; each handler owns its own auth (email
    // code, session hash, guardian token). /fellows/hq is NOT here — that is
    // HQ. Every unauthenticated contract was diffed against production; the
    // authenticated/email/oembed/payout halves ship UNPROVEN. See fellows.ts.
    if (path.startsWith("/fellows/") && path !== "/fellows/hq") {
      const f = env as unknown as FellowsEnv;
      if (path === "/fellows/health" && method === "GET") return fellowsHealth(request, f);
      if (path === "/fellows/code" && method === "POST") return fellowsCode(request, f);
      if (path === "/fellows/verify" && method === "POST") return fellowsVerify(request, f);
      if (path === "/fellows/start" && method === "POST") return fellowsStart(request, f);
      if (path === "/fellows/confirm" && method === "GET") return fellowsConfirm(request, f);
      if (path === "/fellows/me" && method === "GET") return fellowsMe(request, f);
      if (path === "/fellows/apply" && method === "POST") return fellowsApply(request, f);
      if (path === "/fellows/progress" && method === "POST") return fellowsProgress(request, f);
      if (path === "/fellows/profile" && method === "POST") return fellowsProfile(request, f);
      if (path === "/fellows/submissions" && method === "POST") return fellowsSubmissions(request, f);
      if (path === "/fellows/submissions/remove" && method === "POST") return fellowsSubmissionsRemove(request, f);
      if (path === "/fellows/guardian/link" && method === "POST") return fellowsGuardianLink(request, f);
      if (path === "/fellows/guardian" && method === "GET") return fellowsGuardianGet(request, f);
      if (path === "/fellows/guardian" && method === "POST") return fellowsGuardianPost(request, f);
      // An unknown /fellows/* path falls through to the generic 404 below.
    }

    // --- HQ's front door. CONTRACT.md §7. --------------------------------
    // Its own auth stack: X-Internal-Key, X-HQ-Session, 8-char login codes,
    // and a Clerk exchange. None of it is PocketBase auth.
    if (path.startsWith("/internal/") || path === "/fellows/hq") {
      const hq = env as unknown as HqEnv;

      // The preflight answers 204 and NOTHING else, before any auth.
      if (method === "OPTIONS") {
        return new Response(null, { status: 204, headers: hqCors(request, hq) });
      }
      // 410 FIRST, before any key is read -- so a retired route can never
      // answer 401 or 503 and invite a retry.
      if (HQ_DEAD_ROUTES.includes(path)) return hqGone(request, hq);

      if (path === "/internal/health" && method === "GET") return hqHealth(request, hq);
      if (path === "/internal/login" && method === "POST") return hqLogin(request, hq);
      if (path === "/fellows/hq" && method === "GET") return hqPage(request, hq);

      // UNGATED ON PURPOSE, and they must sit ABOVE hqGate.
      //
      // Ari holds an eight-character code and nothing else -- he never has the
      // shared key -- so the route that trades that code for a session cannot
      // itself be key-gated, or his first screen is a 401 and there is no way
      // in. Signing out likewise: a stale token must always be discardable.
      // Both still 503 when the key is unset, so a half-configured deploy
      // does not leave one door open in an area every other door has shut.
      if (path === "/internal/session" && method === "POST") return hqSession(request, hq);
      if (path === "/internal/session/end" && method === "POST") return hqSessionEnd(request, hq);

      // Dual auth: X-HQ-Session OR the key. resolveActor() owns the choice, so
      // it cannot be made differently in two places.
      if (path === "/internal/me" && method === "GET") return hqMe(request, hq);
      if (path === "/internal/me/password" && method === "POST") return hqMePassword(request, hq);

      // UNGATED, matching production exactly: /internal/people/faces answers
      // 200 with names and ids to a caller holding no key at all. Reproduced
      // rather than tightened -- see hq_fellows.ts.
      if (path === "/internal/people/faces" && method === "GET") {
        return hqPeopleFaces(request, hq);
      }
      // Gated, and it checks the key itself so it can sit up here beside its
      // sibling instead of being separated by the shared gate.
      if (path === "/internal/fellows" && method === "GET") return hqFellows(request, hq);
      // The fellowship admin actions. Each self-gates on X-Internal-Key
      // (fellowship.pb.js:2069+), so they sit here beside the read route rather
      // than behind hqGate's dual-auth. THESE MOVE MONEY AND REMOVE PEOPLE —
      // ported from recovered source and UNPROVEN on the authenticated path;
      // /internal/fellows/pay is in the untracked fellowship_host.pb.js and is
      // NOT here at all.
      if (path === "/internal/fellows/remove" && method === "POST") {
        return internalFellowsRemove(request, env as unknown as FellowsEnv);
      }
      if (path === "/internal/fellows/submissions/remove" && method === "POST") {
        return internalFellowsSubmissionsRemove(request, env as unknown as FellowsEnv);
      }
      if (path === "/internal/fellows/submissions/release" && method === "POST") {
        return internalFellowsSubmissionsRelease(request, env as unknown as FellowsEnv);
      }
      if (path === "/internal/state" && method === "GET") return hqState(request, hq);
      if (path === "/internal/people" && method === "POST") return hqPeopleCreate(request, hq);
      if (path === "/internal/people" && method === "PATCH") return hqPeopleUpdate(request, hq);
      if (path === "/internal/todos" && method === "POST") return hqTodoCreate(request, hq);
      if (path === "/internal/todos" && method === "PATCH") return hqTodoUpdate(request, hq);
      if (path === "/internal/todos/delete" && method === "POST") return hqTodoDelete(request, hq);
      if (path === "/internal/events" && method === "POST") return hqEventCreate(request, hq);
      if (path === "/internal/events/delete" && method === "POST") return hqEventDelete(request, hq);
      if (path === "/internal/tracks" && method === "POST") return hqTrackUpsert(request, hq);
      if (path === "/internal/tracks/delete" && method === "POST") return hqTrackDelete(request, hq);
      if (path === "/internal/expenses" && method === "POST") return hqExpenseCreate(request, hq);
      if (path === "/internal/expenses/delete" && method === "POST") return hqExpenseDelete(request, hq);
      if (path === "/internal/notes" && method === "POST") return hqNoteUpsert(request, hq);
      if (path === "/internal/notes/delete" && method === "POST") return hqNoteDelete(request, hq);
      if (path === "/internal/passwords" && method === "POST") return hqPasswordUpsert(request, hq);
      if (path === "/internal/passwords/reveal" && method === "POST") return hqPasswordReveal(request, hq);
      if (path === "/internal/passwords/delete" && method === "POST") return hqPasswordDelete(request, hq);
      if (path === "/internal/people/code" && method === "POST") return hqPeopleCode(request, hq);
      if (path === "/internal/notifs/read" && method === "POST") return hqNotifsRead(request, hq);
      if (path === "/internal/settings" && method === "POST") return hqSettings(request, hq);
      if (path === "/internal/comments" && method === "POST") return hqCommentCreate(request, hq);
      if (path === "/internal/comments" && method === "PATCH") return hqCommentUpdate(request, hq);
      if (path === "/internal/comments/delete" && method === "POST") return hqCommentDelete(request, hq);
      if (path === "/internal/reminders" && method === "POST") return hqReminderCreate(request, hq);
      if (path === "/internal/reminders/delete" && method === "POST") return hqReminderDelete(request, hq);
      if (path === "/internal/assistant" && method === "POST") return hqAssistant(request, hq);
      if (path.startsWith("/internal/cal/") && method === "GET") {
        return hqCalendar(request, hq, path.slice("/internal/cal/".length));
      }

      // Also ungated: the caller is proving who they are WITH the Clerk token,
      // so requiring the shared key first would defeat the point of the route.
      if (path === "/internal/clerk/exchange" && method === "POST") {
        return hqClerkExchange(request, hq);
      }

      // Everything else behind the session gate.
      const refused = hqGate(request, hq);
      if (refused) return refused;
      // Every HQ route is wired above. Anything reaching here is a path that
      // internal_hq.pb.js never had, and 404 is the honest answer -- the old
      // "not yet ported" 503 would now be a lie in the other direction.
      return new Response(JSON.stringify({ error: "not found" }),
        { status: 404, headers: { "content-type": "application/json", ...hqCors(request, hq) } });
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

    // --- the evidence host. evidence.pb.js, chain step 1 (chain.ts:35). ----
    //
    // BOTH HALVES WERE MISSING, and they fail in opposite directions. The
    // fetch door was written (assets.ts:serveFile) and never routed, so
    // /api/files/* fell through to a generic 404 and serveFile was dead code —
    // every done-text went out without its receipt. The share mint was not
    // written at all, so brain/evidence.py:118-131 logged "the share door
    // answered 404" on every send (audit F13).
    //
    // The door goes ABOVE the records regex because that is where the oracle's
    // routerUse sits: before the data API, not inside it. It carries its own
    // authorisation (owner, service token, or an open share window) — the
    // records guard never sees this path and never did.
    if (path.startsWith("/api/files/") && method === "GET") {
      const who = await resolvePrincipal(request, env);
      return serveFile(request, env as unknown as AssetEnv,
                       who.kind === "account" ? who.ownerId : null);
    }
    if (path === "/evidence/share" && method === "POST") {
      return shareEvidence(request, env as unknown as AssetEnv);
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
  const { body, files } = await readBodyAndFiles(request);
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

  // THE ONE COLLECTION WITH BYTES. 1700000045_evidence.js has the only
  // `type: "file"` field in all 58 migrations, so this is the whole of file
  // handling in this backend rather than a general upload path — and that is
  // deliberate: "an evidence host that accepts arbitrary files is a file host"
  // (schema.sql:606). AFTER the chain, so the guard has already decided this
  // credential may deposit for this owner.
  if (def.name === "evidence" && method === "POST" && !recordId) {
    return depositEvidence(env, req, files);
  }

  switch (method) {
    case "GET":    return recordId ? records.view(env, req) : records.list(env, req);
    case "POST":   return recordId ? notFound() : records.create(env, req);
    case "PATCH":  return recordId ? records.update(env, req) : notFound();
    case "DELETE": return recordId ? records.remove(env, req) : notFound();
    default:       return json(405, { code: 405, message: "Method not allowed.", data: {} });
  }
}

/**
 * POST /api/collections/evidence/records, carrying the picture.
 *
 * A DEPOSIT WITH NO PICTURE IS REFUSED rather than stored. Measured
 * 2026-09-05: a multipart create whose body the Worker ignored wrote row
 * 48mu1cxcrpwjfp2 with owner_ref "", job "" and image "" — a row that can
 * never be served, never be found by its owner and never be deleted by them
 * either. The empty create is the shape that produced it.
 *
 * Bytes first, then the row that names them; a refused row takes its object
 * back out. See assets.ts for why that order and not the other.
 */
async function depositEvidence(
  env: Env, req: records.RecordsRequest, files: { field: string; file: File }[],
): Promise<Response> {
  const image = files.find((f) => f.field === "image")?.file;
  if (!image) {
    // A JSON create with no file at all is the same refusal: the column holds
    // a filename, so a row without bytes is a promise nothing can keep.
    return json(400, {
      data: { image: { code: "validation_required", message: "Cannot be blank." } },
      message: "Failed to create record.", status: 400,
    });
  }

  const stored = await depositEvidenceImage(env as unknown as AssetEnv, image);
  if (!stored.ok) return stored.response;

  let created: Response;
  try {
    created = await records.create(env, {
      ...req,
      body: { ...(req.body ?? {}), id: stored.deposit.id, image: stored.deposit.filename },
    });
  } catch (err) {
    // A REFUSAL AND A THROW LEAVE THE SAME ORPHAN. D1's CHECK constraints
    // (owner_ref and job are both `length > 0`) come back as a thrown error,
    // not a status, and records.create rethrows anything that is not a known
    // column or unique collision. Discard first, then let it travel: the bytes
    // must not outlive the row whichever way the row failed.
    await discardEvidenceImage(env as unknown as AssetEnv, stored.deposit);
    throw err;
  }
  if (created.status !== 200) {
    await discardEvidenceImage(env as unknown as AssetEnv, stored.deposit);
  }
  return created;
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

/**
 * Parse once. PocketBase's e.requestInfo().body is also parse-once.
 *
 * MULTIPART IS A BODY TOO, and forgetting that is what silently killed the
 * receipt photo. PocketBase parses multipart for every route; this returned
 * null unless the content-type said JSON, so an upload arrived at the guard as
 * an EMPTY BODY — `String(b.owner_ref ?? "")` read "", the agent rung's
 * owner comparison failed, and the deposit was 403 (audit F13). The extension
 * deletes its own Content-Type header for exactly this call
 * (background.js:1374-1376), so the shape is not exotic: it is the only way to
 * post bytes.
 *
 * The string entries become the body the policy chain reads. The File entries
 * are handed back separately: they are not columns, and letting one reach the
 * generic writer would be a 400 unknown_field at best.
 */
export interface ParsedBody {
  body: Record<string, unknown> | null;
  files: { field: string; file: File }[];
}

export async function readBodyAndFiles(request: Request): Promise<ParsedBody> {
  if (request.method === "GET" || request.method === "HEAD") return { body: null, files: [] };
  const ct = request.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    try { return { body: await request.json<Record<string, unknown>>(), files: [] }; }
    catch { return { body: null, files: [] }; }
  }
  if (ct.includes("multipart/form-data")) {
    try {
      const form = await request.formData();
      const body: Record<string, unknown> = {};
      const files: { field: string; file: File }[] = [];
      for (const [field, value] of form.entries()) {
        if (typeof value === "string") body[field] = value;
        else files.push({ field, file: value as File });
      }
      return { body, files };
    } catch { return { body: null, files: [] }; }
  }
  return { body: null, files: [] };
}

async function readBody(request: Request): Promise<Record<string, unknown> | null> {
  return (await readBodyAndFiles(request)).body;
}

const STATIC_PREFIXES = [
  "/internal.html", "/setup.html", "/privacy.html", "/mac.html",
  "/site.css", "/theme.js", "/mac/",
];
function isStaticPath(path: string): boolean {
  return STATIC_PREFIXES.some((p) => path === p || path.startsWith(p))
    || path.endsWith(".zip");
}
