/**
 * src/policy/guard.ts — backend/pb_hooks/guard.pb.js:24-551, ported.
 *
 * 223 code lines there; the ladder below preserves every rung and its ORDER,
 * because the order is where the incidents were. Two of them are recorded in
 * the original and are re-stated here so a future refactor cannot re-introduce
 * them by tidying:
 *
 *   - The superuser branch MUST sit ABOVE the account branch. PocketBase fills
 *     `e.auth` for ANY auth record including a superuser, so `if (e.auth)`
 *     swallowed the dashboard and the Admin UI bounced to login on every
 *     auth-refresh. guard.pb.js:381-396.
 *   - An agent id that does not RESOLVE is a refusal, not a shrug. Sending
 *     X-Anticipy-Agent-ID COMMITS the caller to that identity; a failed lookup
 *     used to fall through into the anonymous pairing bootstrap, so a revoked
 *     credential silently got the anonymous surface. guard.pb.js:203-220.
 *
 * WHAT IS DELIBERATELY DIFFERENT FROM THE ORIGINAL — and why it is safe:
 *
 *   (a) THE FAIL-OPEN SWITCH IS GONE. guard.pb.js:25 is
 *       `if (!token) return e.next()` — with ANTICIPY_SERVICE_TOKEN unset the
 *       guard is a no-op for EVERY request, and design/LOGIN-DESIGN-2026-08-03.md:506
 *       names the consequence: any collection added later is unguarded by
 *       default. On D1 there is no API rule underneath to catch that. So this
 *       port FAILS CLOSED: a missing ANTICIPY_SERVICE_TOKEN is a 503 at boot,
 *       not an open door. ARCHITECTURE.md §3.6.
 *
 *   (b) `ownedList` runs the legacy substring predicate AND a sound AST check,
 *       and the owner scope is compiled into the SQL either way. The substring
 *       rule accepts `goal != 'owner_ref="<my id>"'` — no `||`, contains the
 *       magic substring, constrains nothing — which reads every owner's rows.
 *       ARCHITECTURE.md §3.4. Both are run so the contract suite can diff the
 *       status codes while the fix lands.
 */
import { parseFilter, provesOwnerScope, legacyOwnedList, FilterError } from "../../filter-dsl.ts";
import { ACCOUNT_REACHABLE } from "../pb/schema.ts";
import { refuse, badRequest } from "../pb/wire.ts";
import type { Ctx, Policy } from "./chain.ts";

export interface GuardEnv {
  DB: D1Database;
  ANTICIPY_SERVICE_TOKEN: string;
  PAIR_CODE_COUNTER: DurableObjectNamespace;
  /**
   * "1" during the dual-run phase: answer with the DEPLOYED substring rule
   * alone, so migration/spec/contract_tests.py diffs clean against PocketBase.
   * Unset (the default, and the end state) additionally requires the sound AST
   * check. Set it in `vars`, never as a secret — it is a behaviour switch and
   * whoever reads the config should see which mode is live.
   */
  LEGACY_OWNED_LIST_ONLY?: string;
}

const AGENTS_BASE = "/api/collections/agents/records";
const PENDANTS_BASE = "/api/collections/pendants/records";
const JOBS_BASE = "/api/collections/jobs/records";
const EVENTS_BASE = "/api/collections/events/records";
const EVIDENCE_BASE = "/api/collections/evidence/records";

/** guard.pb.js:368 — the auth endpoints, which must stay reachable. */
const AUTH_ENDPOINTS =
  /\/(auth-with-password|auth-with-oauth2|auth-with-otp|request-otp|auth-refresh|request-password-reset|confirm-password-reset|request-verification|confirm-verification|auth-methods)$/;

/** guard.pb.js:261 — the four columns a claimant may never write. */
const EVIDENCE_COLUMNS = new Set(["watching_until", "lane", "owner_ref", "owner"]);

export const guard: Policy = async (ctx: Ctx, envRaw): Promise<Response | null> => {
  const env = envRaw as GuardEnv;
  const { path, method } = ctx;

  // guard.pb.js:31-36 — the guarded surface.
  const guarded =
    path.startsWith("/api/collections/") ||
    (path === "/api/realtime" && method !== "GET");
  if (!guarded) return null;

  // (a) above. There is no `if (!token) return next()` here on purpose.
  if (!env.ANTICIPY_SERVICE_TOKEN) {
    return refuse(503, "the data API is not configured",
      "ANTICIPY_SERVICE_TOKEN is unset; refusing rather than serving unguarded");
  }

  // ---- rung 0: the service token. guard.pb.js:37 ------------------------
  if (ctx.principal.kind === "service") return null;

  // ---- rung 1: the per-agent credential. TERMINAL. guard.pb.js:200-357 --
  const agentIdHeader = ctx.request.headers.get("X-Anticipy-Agent-ID") ?? "";
  if (agentIdHeader) {
    if (ctx.principal.kind !== "agent") {
      // Resolved in resolvePrincipal(); an unresolved id lands here.
      return refuse(403, "agent credential is not recognized");
    }
    return agentRung(ctx, env, ctx.principal.ownerRef, ctx.principal.agentRowId);
  }

  // ---- rungs 2-3: the front door. guard.pb.js:367-379 --------------------
  if (path.startsWith("/api/collections/owners/") && AUTH_ENDPOINTS.test(path)) return null;
  if (method === "POST" && path === "/api/collections/owners/records") return null;

  // ---- rung 4: the dashboard. MUST precede the account rung. :394-396 ----
  if (ctx.principal.kind === "superuser") return null;

  // ---- rung 5: a signed-in account. TERMINAL. guard.pb.js:403-453 -------
  if (ctx.principal.kind === "account") {
    return accountRung(ctx, env, ctx.principal.ownerId);
  }

  // ---- rung 6: superuser LOGIN itself. guard.pb.js:462 ------------------
  if (path.startsWith("/api/collections/_superusers/")) return null;

  // ---- rungs 7-9: the tokenless pairing bootstrap ------------------------
  return bootstrapRungs(ctx, env);
};

// ---------------------------------------------------------------------------
// Rung 1 — the Chrome install
// ---------------------------------------------------------------------------

async function agentRung(
  ctx: Ctx, env: GuardEnv, ownerRef: string, agentRowId: string,
): Promise<Response | null> {
  const { path, method, body } = ctx;
  const b = body ?? {};
  const keys = Object.keys(b);

  // guard.pb.js:235-238 — its own row, three columns.
  if (path === `${AGENTS_BASE}/${agentRowId}` && method === "PATCH") {
    const allowed = new Set(["agent_token", "last_seen", "browser"]);
    if (keys.every((k) => allowed.has(k))) return null;
  }

  // guard.pb.js:240-242 — its owner's job list.
  if (ownerRef && path === JOBS_BASE && method === "GET") {
    if (await ownedList(ctx, ownerRef, env)) {
      ctx.forcedScope = { column: "owner_ref", value: ownerRef };
      return null;
    }
  }

  // guard.pb.js:261-273 — one job row, but never the four evidence columns.
  if (ownerRef && path.startsWith(`${JOBS_BASE}/`)) {
    const id = path.split("/").pop() as string;
    const owner = await recordOwner(ctx, "jobs", id);
    if (owner === ownerRef && (method === "GET" || method === "PATCH")) {
      const writesEvidence = keys.some((k) => EVIDENCE_COLUMNS.has(k));
      // `owner_ref` echoed back unchanged stays allowed: PocketBase clients
      // resend it and refusing that breaks ordinary work. :268-270.
      const echo = keys.every((k) => !EVIDENCE_COLUMNS.has(k)
        || (k === "owner_ref" && b[k] === ownerRef));
      if (!writesEvidence || echo) {
        ctx.forcedScope = { column: "owner_ref", value: ownerRef };
        return null;
      }
    }
  }

  // guard.pb.js:297-323 — narration from a supervised read, while supervised.
  if (ownerRef && path === EVENTS_BASE && method === "POST") {
    const kind = String(b.kind ?? "");
    const text = String(b.text ?? "");
    if ((kind === "read_line" || kind === "read_fact")
        && b.owner_ref === ownerRef
        && text.length > 0 && text.length <= 400) {
      const job = await loadRow(ctx, "jobs", String(b.goal ?? ""));
      if (job && job.owner_ref === ownerRef && job.lane === "supervised_read") {
        const { stillInTheFuture } = await import("../pb/wire.ts");
        if (stillInTheFuture(job.watching_until)) return null;
      }
    }
  }

  // guard.pb.js:342-346 — deposit evidence for its own owner. CREATE ONLY.
  if (ownerRef && method === "POST" && path === EVIDENCE_BASE
      && String(b.owner_ref ?? "") === ownerRef) {
    return null;
  }

  return refuse(403, "agent is not allowed to access that record");
}

// ---------------------------------------------------------------------------
// Rung 5 — a signed-in account
// ---------------------------------------------------------------------------

async function accountRung(ctx: Ctx, env: GuardEnv, authId: string): Promise<Response | null> {
  const { path, method } = ctx;
  const b = ctx.body ?? {};

  // guard.pb.js:408 — the person's own owners record, any method.
  if (path === `/api/collections/owners/records/${authId}`) return null;

  const m = path.match(
    /^\/api\/collections\/(jobs|events|owner_profile|segments|agents|pendants|evidence)\/records(?:\/([^/]+))?$/);
  if (!m) return refuse(403, "account is not allowed to access that collection");
  const collection = m[1];
  const recordId = m[2] ?? "";

  if (!ACCOUNT_REACHABLE.includes(collection as typeof ACCOUNT_REACHABLE[number])) {
    return refuse(403, "account is not allowed to access that collection");
  }

  // guard.pb.js:429-433 — pair-code lookup, deliberately pre-owner.
  if (!recordId && method === "GET" && (collection === "agents" || collection === "pendants")) {
    const filter = ctx.url.searchParams.get("filter") ?? "";
    const pair = filter.match(/^\s*pair_code\s*=\s*"(\d{6})"\s*$/);
    if (pair) return pairLookup(ctx, env, collection, pair[1]);
  }

  // guard.pb.js:434-445 — the claim. Blank owners are refused loudly.
  if (recordId && method === "PATCH" && (collection === "agents" || collection === "pendants")) {
    const rec = await loadRow(ctx, collection, recordId);
    if (rec && !truthy(rec.paired) && b.paired === true && b.owner_ref === authId
        && typeof b.owner === "string" && b.owner.trim() !== "") {
      return null;
    }
  }

  if (!recordId && method === "GET") {
    if (await ownedList(ctx, authId, env)) {
      ctx.forcedScope = { column: "owner_ref", value: authId };
      return null;
    }
  }
  if (!recordId && method === "POST" && b.owner_ref === authId) return null;
  if (recordId) {
    const owner = await recordOwner(ctx, collection, recordId);
    if (owner === authId && (!b.owner_ref || b.owner_ref === authId)) {
      ctx.forcedScope = { column: "owner_ref", value: authId };
      return null;
    }
  }
  return refuse(403, "record belongs to a different owner");
}

// ---------------------------------------------------------------------------
// ownedList — the authorization primitive, and its fix
// ---------------------------------------------------------------------------

/**
 * guard.pb.js:45-50, plus the AST check that closes the string-literal hole.
 *
 * `LEGACY_OWNED_LIST_ONLY=1` runs ONLY the substring predicate, byte-identical to
 * the deployed backend, for the phase where migration/spec/contract_tests.py
 * is diffed against both. Unset (the default) requires BOTH.
 *
 * Either way, whoever calls this sets ctx.forcedScope, so the SQL is scoped
 * regardless of which predicate said yes. That is the part that actually
 * closes the hole; the predicate only decides the status code.
 */
async function ownedList(ctx: Ctx, ownerRef: string, env: GuardEnv): Promise<boolean> {
  const raw = ctx.url.searchParams.get("filter") ?? "";
  const legacy = legacyOwnedList(raw, ownerRef);
  if (env.LEGACY_OWNED_LIST_ONLY === "1") return legacy;

  let sound = false;
  try {
    sound = provesOwnerScope(parseFilter(raw), ownerRef);
  } catch (e) {
    if (!(e instanceof FilterError)) throw e;
    sound = false;
  }
  // AND, not OR: a filter must satisfy the deployed rule (so no client that
  // works today starts failing) and be structurally sound (so the literal hole
  // is shut). The one case this refuses that legacy accepted is the attack.
  return legacy && sound;
}

// ---------------------------------------------------------------------------
// Rungs 7-9 — the tokenless bootstrap
// ---------------------------------------------------------------------------

async function bootstrapRungs(ctx: Ctx, env: GuardEnv): Promise<Response | null> {
  const { path, method } = ctx;
  const b = ctx.body ?? {};

  // 1. guard.pb.js:466-470 — self-registration, never born paired/owned.
  if (method === "POST" && path === AGENTS_BASE) {
    if (!b.paired && !b.owner) return null;
    return refuse(403, "forbidden");
  }

  // 2. guard.pb.js:486-501 — a LIST that names the code it is looking for.
  if (method === "GET" && (path === AGENTS_BASE || path === PENDANTS_BASE)) {
    const filter = ctx.url.searchParams.get("filter") ?? "";
    const perPage = parseInt(ctx.url.searchParams.get("perPage") ?? "30", 10);
    // The cap is an independent defence: a future hole in the filter check
    // still cannot become a bulk export. :490-492.
    if (perPage > 50) return refuse(403, "forbidden");
    const pair = filter.match(/^\s*pair_code\s*=\s*"(\d{6})"\s*$/);
    if (pair) {
      return pairLookup(ctx, env, path === AGENTS_BASE ? "agents" : "pendants", pair[1]);
    }
    // A fresh install finding its own paired agent by its high-entropy owner
    // id. Anchored, and restricted to the shape an id actually has. :499.
    if (/^\s*owner\s*=\s*"[A-Za-z0-9._-]{8,64}"\s*$/.test(filter)) return null;
    return refuse(403, "forbidden");
  }

  // 3. guard.pb.js:511-548 — claiming.
  if (method === "PATCH"
      && (path.startsWith(`${AGENTS_BASE}/`) || path.startsWith(`${PENDANTS_BASE}/`))) {
    const allowed = new Set(["owner", "paired", "last_seen", "browser"]);
    const keys = Object.keys(b);
    const collection = path.startsWith(AGENTS_BASE) ? "agents" : "pendants";
    const id = path.split("/").pop() as string;
    // owner_ref is REFUSED here: nothing on this path can verify it, and an
    // unauthenticated caller could PATCH a victim's owner_ref onto their own
    // agent and start receiving the victim's jobs. :519-526.
    if ("owner_ref" in b) {
      return refuse(403, "pair from the signed-in app",
        "an owner_ref may only be claimed by the account it belongs to");
    }
    const rec = await loadRow(ctx, collection, id);
    if (rec && keys.length > 0 && keys.every((k) => allowed.has(k))) {
      const touchesPairing = "owner" in b || "paired" in b;
      const namesOwner = typeof b.owner === "string" && b.owner.trim() !== "";
      if (!touchesPairing || (!truthy(rec.paired) && namesOwner)) return null;
    }
    return refuse(403, "forbidden");
  }

  return refuse(403, "forbidden");
}

// ---------------------------------------------------------------------------
// pairLookup — the guess ceiling, now in a Durable Object
// ---------------------------------------------------------------------------

/**
 * guard.pb.js:116-195. The counter moves from `e.app.store()` (PocketBase's
 * in-process app-wide KV, shared across the isolated hook runtimes) to a
 * Durable Object, because a Worker has NO shared process to count in — every
 * request may land in a fresh isolate anywhere on the network, so an
 * in-isolate Map counts nothing. See src/do/PairCodeCounter.ts and
 * ARCHITECTURE.md §5.
 *
 * The posture is preserved exactly, including the one that looks like an
 * outage and is not: if the counter cannot be reached, pairing is REFUSED
 * (503), because "serving lookups that nobody is counting is the exact hole
 * this closes" (:126-135).
 */
async function pairLookup(
  ctx: Ctx, env: GuardEnv, collection: "agents" | "pendants", code: string,
): Promise<Response | null> {
  const stub = env.PAIR_CODE_COUNTER.get(env.PAIR_CODE_COUNTER.idFromName("global"));

  let ip = ctx.request.headers.get("CF-Connecting-IP") ?? "";
  // guard.pb.js:101-108 is candid that behind Railway's edge every caller
  // currently shares one bucket. On Cloudflare, CF-Connecting-IP is set by the
  // edge and is not caller-controllable, so the per-IP bucket becomes real for
  // the first time. The all-callers ceiling stays regardless: it is what
  // bounds the walk and bounds how many keys can be minted.
  if (!ip) ip = "unknown";

  const gate = await stub.fetch("https://pair/check", {
    method: "POST",
    body: JSON.stringify({ ip }),
  }).then((r) => r.json() as Promise<{ allowed: boolean }>).catch(() => null);

  if (!gate) {
    console.log("pair-code lookup: no counter to count guesses in — refusing");
    return refuse(503, "pairing is briefly unavailable",
      "the server cannot count pair code attempts right now");
  }
  if (!gate.allowed) {
    return refuse(429, "too many pair code attempts",
      "wait a few minutes, then read the current code off the extension popup");
  }

  const found = await ctx_env_first(ctx, collection, code);
  if (found && !truthy(found.paired)) return null;   // a real pairing spends nothing

  await stub.fetch("https://pair/spend", { method: "POST", body: JSON.stringify({ ip }) });

  // A MISS still falls through, so the phone can say "that code didn't match"
  // rather than "I can't reach Anticipy" (SettingsView.swift:270-284). Only
  // the ceiling refuses. :87-91.
  if (!found) return null;

  return refuse(403, "that pair code is already paired",
    "read the current code off the extension popup");
}

// ---------------------------------------------------------------------------
// small helpers
// ---------------------------------------------------------------------------

const truthy = (v: unknown): boolean => v === true || v === 1 || v === "1";

async function ctx_env_first(
  ctx: Ctx, collection: string, code: string,
): Promise<Record<string, unknown> | null> {
  const db = (ctx as unknown as { db: D1Database }).db;
  return db.prepare(
    `SELECT * FROM "${collection}" WHERE "pair_code" = ?1 LIMIT 1`,
  ).bind(code).first<Record<string, unknown>>();
}

async function loadRow(
  ctx: Ctx, collection: string, id: string,
): Promise<Record<string, unknown> | null> {
  if (!id) return null;
  const db = (ctx as unknown as { db: D1Database }).db;
  return db.prepare(
    `SELECT * FROM "${collection}" WHERE "id" = ?1 LIMIT 1`,
  ).bind(id).first<Record<string, unknown>>();
}

/**
 * guard.pb.js:51-54. A throw and an empty result get the same answer, on
 * purpose: "a guard that fails open when the database hiccups is a guard you
 * open by making the database hiccup" (:349-354).
 */
async function recordOwner(ctx: Ctx, collection: string, id: string): Promise<string> {
  try {
    const row = await loadRow(ctx, collection, id);
    return String(row?.owner_ref ?? "");
  } catch {
    return "";
  }
}

export { badRequest };
