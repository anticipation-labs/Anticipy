/**
 * src/policy/chain.ts — the middleware chain, and the principals it recognises.
 *
 * ┌───────────────────────────────────────────────────────────────────────┐
 * │ THESE MIDDLEWARES ARE THE AUTHORIZATION. THEY ARE NOT A BOLT-ON.      │
 * ├───────────────────────────────────────────────────────────────────────┤
 * │ In PocketBase a collection's API rule is a nullable string, and the   │
 * │ two empty-ish values mean OPPOSITE things:                            │
 * │                                                                       │
 * │     ""    = PUBLIC. Anyone, unauthenticated, may do this.             │
 * │     null  = SUPERUSER ONLY.                                           │
 * │                                                                       │
 * │ 42 rule slots across 11 of the 12 product collections are `""`.       │
 * │ migration/d1/RULES.md counted them. The migration authors wrote the   │
 * │ reason down themselves:                                               │
 * │                                                                       │
 * │   "`""` is not 'public'. It is what jobs (1700000001:17) and every    │
 * │    other worker-read collection already use, because guard.pb.js is   │
 * │    the real gate"  — 1700000042_purges_readable.js:24-27              │
 * │                                                                       │
 * │ D1 has no equivalent of an API rule at all. So there is no second     │
 * │ lock behind these files. If this chain is skipped, mis-ordered, or    │
 * │ shipped disabled, every transcript, every job, every profile (name,   │
 * │ email, phone, birthday, free-form facts) and every receipt photo is   │
 * │ readable by anyone who can guess a URL.                               │
 * └───────────────────────────────────────────────────────────────────────┘
 *
 * ORDER IS LOAD-BEARING. migration/spec/CONTRACT.md §0.4 fixes it, and the
 * reason is the status code: guard.pb.js refuses BEFORE research_lane and
 * workflow_guard ever see the request, so a request that fails the guard is a
 * 403 {"error":"forbidden"} and never a 409 workflow violation. A port that
 * evaluates workflow rules first answers wrongly on a large class of requests
 * and the contract suite catches it as a diff.
 *
 *   1. files.ts               (/api/files/*)      evidence.pb.js:56
 *   2. guard.ts               (/api/collections/*) guard.pb.js:24
 *   3. cors.ts                (/internal/*)       internal_hq.pb.js:4224
 *   4. ownerProfileOwner.ts                       owner_profile_owner.pb.js:34
 *   5. researchLane.ts                            research_lane.pb.js:272
 *   6. workflowGuard.ts                           workflow_guard.pb.js:6
 */
import type { Node } from "../../filter-dsl.ts";
import type { CollectionDef } from "../pb/schema.ts";

// ---------------------------------------------------------------------------
// Principals — guard.pb.js recognises exactly three, plus anonymous.
// migration/d1/RULES.md, "The three principals the guard actually recognises".
// ---------------------------------------------------------------------------

export type Principal =
  /** X-Anticipy-Token === ANTICIPY_SERVICE_TOKEN. A god credential. guard.pb.js:37 */
  | { kind: "service" }
  /** A PocketBase superuser session. guard.pb.js:394-396 — MUST be checked before "account". */
  | { kind: "superuser"; id: string }
  /** An owners JWT. guard.pb.js:403-453 */
  | { kind: "account"; ownerId: string; row: Record<string, unknown> }
  /** X-Anticipy-Agent-ID + a resolved >=40-char token. guard.pb.js:200-357 */
  | { kind: "agent"; agentRowId: string; agentId: string; ownerRef: string }
  | { kind: "anonymous" };

/**
 * Set when the worker marker is present AND (if a service token is configured)
 * the token matches. research_lane.pb.js:429-432. Note it is a ROUTING marker
 * and not a credential — brain/pb.py:21-26 says so — so when no service token
 * is configured the marker alone is believed, exactly as today.
 */
export interface WorkerMarker { fromWorker: boolean; }

// ---------------------------------------------------------------------------
// The request as it travels down the chain
// ---------------------------------------------------------------------------

export interface Ctx {
  request: Request;
  url: URL;
  method: string;
  path: string;
  /** Parsed once. PocketBase's e.requestInfo().body is also parse-once. */
  body: Record<string, unknown> | null;
  principal: Principal;
  worker: WorkerMarker;

  /** Set by the router when the path is /api/collections/{name}/records[/{id}] */
  collection?: CollectionDef;
  recordId?: string | null;

  /**
   * THE STRUCTURAL BACKSTOP. Set by guard.ts. Compiled into the WHERE of
   * every list/view/update/delete, so no filter — parsed correctly or not —
   * can read or write another owner's rows. See ARCHITECTURE.md §3.5.
   */
  forcedScope: { column: string; value: string } | null;

  /** Extra AND clauses. researchLane.ts puts the lane exclusion here. */
  extraAst: Node | null;

  /** Populated lazily by policies that need the stored row (PATCH targets). */
  storedRow?: Record<string, unknown> | null;
}

/** A middleware returns a Response to REFUSE, or null to continue. */
export type Policy = (ctx: Ctx, env: unknown) => Promise<Response | null> | Response | null;

/**
 * Run the chain in order. The first Response wins and nothing after it runs —
 * the same semantics as PocketBase's `e.next()` versus `return e.json(...)`.
 */
export async function runChain(
  policies: readonly Policy[], ctx: Ctx, env: unknown,
): Promise<Response | null> {
  for (const p of policies) {
    const r = await p(ctx, env);
    if (r) return r;
  }
  return null;
}
