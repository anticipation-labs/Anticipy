/**
 * The Chrome extension's lifecycle.
 *
 *   POST /agent/register             mint a credential, exactly once
 *   GET  /agent/key                  the agent's server-controlled config
 *   POST /agent/llm                  the model proxy
 *   POST /agent/solve-captcha[/result]
 *
 * Ported from backend/pb_hooks/agent_auth.pb.js, agent_key.pb.js and
 * captcha_solve.pb.js.
 *
 * THE VENDOR KEY NEVER LEAVES THE SERVER. /agent/key answers `llm_proxy: true`
 * and an owner_ref -- never a provider credential. The extension is a published
 * zip: anyone can unzip a build and read whatever it was handed, which is how
 * the previous design would have spent the owner's balance. The contract suite
 * asserts the absence directly, sniffing the whole response for key shapes.
 *
 * AN EXCEPTION IS NOT AN ANSWER. Registration asks "does this exist?" with a
 * query that returns a VALUE: an empty list means nothing matched, and a throw
 * stays a failure. Reading the throw as "no" is what let a transient database
 * error mint a duplicate pair_code -- and pair_code carries NO unique index
 * (only agent_id does), so the duplicate SAVES, two browsers wear one code, and
 * the phone pairs to whichever row comes back first. That is the one outcome
 * here that retrying cannot undo, because the code is already on somebody's
 * screen. So a lookup failure REFUSES the registration.
 */
import { llmProxy, type LlmEnv } from "../llm.ts";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json" },
  });

/** LlmEnv carries DB, the two provider keys and the two model names. */
export interface AgentEnv extends LlmEnv {
  ANTICIPY_SERVICE_TOKEN?: string;
  CAPSOLVER_API_KEY?: string;
}

const AGENT_ID_RE = /^[A-Za-z0-9._-]{20,100}$/;

function hex(n: number): string {
  return [...crypto.getRandomValues(new Uint8Array(n))]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
}
function sixDigits(): string {
  const out: string[] = [];
  while (out.length < 6) {
    for (const b of crypto.getRandomValues(new Uint8Array(16))) {
      if (b < 250 && out.length < 6) out.push(String(b % 10));
    }
  }
  return out.join("");
}
function pbNow(d = new Date()) { return d.toISOString().replace("T", " "); }
function pbId() {
  const A = "abcdefghijklmnopqrstuvwxyz0123456789";
  return [...crypto.getRandomValues(new Uint8Array(15))].map((b) => A[b % A.length]).join("");
}
async function body(req: Request): Promise<Record<string, unknown>> {
  try { const v = await req.json(); return v && typeof v === "object" ? v as Record<string, unknown> : {}; }
  catch { return {}; }
}

/** agent_id + a >=40-char token that resolves to ONE paired row, or nothing. */
async function paired(env: AgentEnv, agentId: string, token: string) {
  if (!agentId || token.length < 40) return { bad: "credentials" as const };
  try {
    const row = await env.DB.prepare(
      `SELECT * FROM agents WHERE agent_id = ? AND agent_token = ? AND paired = 1 LIMIT 1`)
      .bind(agentId, token).first<Record<string, unknown>>();
    return row ? { row } : { bad: "unpaired" as const };
  } catch {
    return { bad: "unpaired" as const };   // a failed lookup is not a pass
  }
}

export async function agentRegister(req: Request, env: AgentEnv): Promise<Response> {
  const b = await body(req);
  const agentId = String(b.agent_id ?? "").trim();
  if (!AGENT_ID_RE.test(agentId)) return json(400, { error: "valid agent_id required" });

  try {
    const dup = await env.DB.prepare(`SELECT id FROM agents WHERE agent_id = ? LIMIT 1`)
      .bind(agentId).first();
    if (dup) return json(409, { error: "agent already registered" });
  } catch (err) {
    console.log("agent registration: agent_id lookup failed:", String(err));
    return json(503, { error: "registration unavailable" });
  }

  const token = hex(32);          // 64 hex chars
  let code = "";
  for (let i = 0; i < 8 && !code; i++) {
    const c = sixDigits();
    try {
      const taken = await env.DB.prepare(`SELECT id FROM agents WHERE pair_code = ? LIMIT 1`)
        .bind(c).first();
      if (!taken) code = c;
    } catch (err) {
      console.log("agent registration: pair_code lookup failed:", String(err));
      return json(503, { error: "registration unavailable" });
    }
  }
  if (!code) return json(503, { error: "registration unavailable" });

  // THE ROW ID IS PART OF THE CONTRACT. agent_auth.pb.js:62 answers
  // `id: record.id`, and extension/background.js:181-196 stores it as
  // `recordId` — the handle every later heartbeat and pairing read uses.
  // Until 2026-09-05 this port minted the id inline in the bind and never
  // returned it. Measured live against api.anticipy.ai with a real 0.13.0
  // install: recordId undefined → the next poll re-registers → 409 → a fresh
  // agent_id → 200 without an id again — one junk agents row per poll,
  // 62 rows in 165 s, and a browser that can never pair. The smoke leg 3
  // ("a fresh install can register") is the pin; repo-green never saw it.
  const id = pbId();
  await env.DB.prepare(
    `INSERT INTO agents (id, agent_id, agent_token, pair_code, paired, created, updated)
     VALUES (?,?,?,?,?,?,?)`)
    .bind(id, agentId, token, code, 0, pbNow(), pbNow()).run();

  // The only time the credential is ever shown.
  return json(200, { id, agent_id: agentId, agent_token: token, pair_code: code });
}

export async function agentKey(req: Request, env: AgentEnv): Promise<Response> {
  const url = new URL(req.url);
  const agentId = url.searchParams.get("agent_id") || "";
  const token = (req.headers.get("X-Anticipy-Agent-Token") || "").trim();
  const p = await paired(env, agentId, token);
  if ("bad" in p) {
    return p.bad === "credentials"
      ? json(400, { error: "agent credentials required" })
      : json(403, { error: "not a paired agent" });
  }
  const ownerRef = String(p.row.owner_ref ?? "");
  if (!ownerRef) {
    return json(409, {
      error: "paired agent has no canonical owner; pair it again from the signed-in app",
    });
  }
  const model = env.ANTICIPY_BROWSER_MODEL || "";
  if (!model) return json(503, { error: "backend has no model configured" });

  // llm_proxy, never a vendor credential. Changing the model for every paired
  // agent is one env change and no extension update.
  return json(200, { llm_proxy: true, model, owner_ref: ownerRef });
}

/**
 * Rules 1 and 2 of CONTRACT.md §6.4 live here; everything after the paired
 * lookup is src/llm.ts, which receives the row this found and never echoes it.
 */
export async function agentLlm(req: Request, env: AgentEnv): Promise<Response> {
  const startedAt = Date.now();
  const agentId = (req.headers.get("X-Anticipy-Agent-ID") || "").trim();
  const token = (req.headers.get("X-Anticipy-Agent-Token") || "").trim();
  const p = await paired(env, agentId, token);
  if ("bad" in p) {
    return p.bad === "credentials"
      ? json(400, { error: "agent credentials required" })
      : json(403, { error: "not a paired agent" });
  }
  return llmProxy(req, env, p.row, startedAt);
}

/** Bounded by design: only for a paired agent, and only when configured. */
export async function agentCaptcha(req: Request, env: AgentEnv): Promise<Response> {
  const agentId = (req.headers.get("X-Anticipy-Agent-ID") || "").trim();
  const token = (req.headers.get("X-Anticipy-Agent-Token") || "").trim();
  const p = await paired(env, agentId, token);
  if ("bad" in p) {
    return p.bad === "credentials"
      ? json(400, { error: "agent credentials required" })
      : json(403, { error: "not a paired agent" });
  }
  if (!env.CAPSOLVER_API_KEY) return json(503, { error: "captcha solving is not configured" });
  return json(503, { error: "captcha solving not yet ported" });
}


/**
 * POST /agent/upgrade-credential   -- service token only.
 *
 * Moves a legacy agent row onto a real credential. The extension calls it
 * (extension/background.js:142) and treats the 403 as the expected answer when
 * it is not authorised, so this must refuse in exactly that shape rather than
 * 404 -- a 404 would read to the extension as "this backend is too old".
 */
export async function agentUpgradeCredential(req: Request, env: AgentEnv): Promise<Response> {
  const token = env.ANTICIPY_SERVICE_TOKEN || "";
  const sent = req.headers.get("X-Anticipy-Token") || "";
  // Constant-time-ish: compare only when both are present and equal length.
  const ok = !!token && sent.length === token.length &&
    sent.split("").reduce((d, c, i) => d | (c.charCodeAt(0) ^ token.charCodeAt(i)), 0) === 0;
  if (!ok) return json(403, { error: "upgrade not authorized" });
  return json(503, { error: "credential upgrade not yet ported" });
}
