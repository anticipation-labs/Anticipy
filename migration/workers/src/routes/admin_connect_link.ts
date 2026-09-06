/**
 * POST /admin/connect-link — mint a connect page for ONE owner and text it to
 * them. The manual trigger the Week A gate needs (spec p27: "I connect Google,
 * Notion and Slack from a text link and from the app"), because nothing in
 * the product mints a link on demand: the ask engine is Week B and frozen, and
 * the phone mints only from Settings.
 *
 * WHAT IT DELIBERATELY IS NOT. It is not an ask. It writes no connect_nudges
 * row, spends none of the owner's 7-day budget, enters no decline ladder, and
 * drafts no copy through a model — a link the owner asked for by hand is not
 * an interruption, and routing it through the ask engine would charge them for
 * it (the exact over-correction the 2026-09-06 audits caught in
 * recordSolicitedAsk). The text is one fixed sentence plus our URL. Never the
 * vendor's URL: mintConnectPage returns api.anticipy.ai/c/{token} and nothing
 * else, and the register scan in connect-routes.test.ts holds the page.
 *
 * AUTH: X-Internal-Key, compared constant-time exactly as hq_fellows.ts does.
 * The owner is named in the BODY here — the one place in this tree that is
 * allowed to, because the caller is the operator with the internal key, not a
 * person on a phone; it is still checked against the owners table before a
 * byte is minted, and a missing row is 404, not a mint for nobody.
 *
 * BODY: {"owner": "<15-char owner row id>", "toolkits": ["gmail", ...],
 *        "alias": "work" | "personal" | null, "send": true}
 * `send: false` mints and returns the URL without texting — for a dry run,
 * and for pasting into the app-side test the gate also asks for.
 */
import { mintConnectPage, type NudgeEnv, type NudgeDeps } from "../connections/nudge.ts";
import { createD1Store } from "../connections/store.ts";
import { ownerPhone, type NudgeWiringEnv } from "../connections/wiring.ts";
import { sendText, type MessagingEnv } from "../messaging.ts";

export const ADMIN_CONNECT_LINK_PATH = "/admin/connect-link";

export type AdminConnectLinkEnv = NudgeEnv & NudgeWiringEnv & MessagingEnv & {
  ANTICIPY_INTERNAL_KEY?: string;
  DB: D1Database;
};

const OWNER_ID = /^[a-z0-9]{15}$/;
const TOOLKIT = /^[a-z0-9_-]{1,64}$/;

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status, headers: { "content-type": "application/json; charset=utf-8" },
  });
}

/** The fixed sentence. No app name from the catalog is rendered here on
 *  purpose — the PAGE names the apps, with their real logos and their three
 *  permission sentences; a text that pre-announced them would be a second copy
 *  of the consent, drifting from the first. */
function textFor(url: string, count: number): string {
  const what = count === 1 ? "an app" : `${count} apps`;
  return `Here's your link to connect ${what} to Anticipy: ${url} — it works for 10 minutes.`;
}

export async function adminConnectLink(req: Request, env: AdminConnectLinkEnv): Promise<Response> {
  if (req.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
  }
  // Constant-time, copied from hq_fellows.ts rather than re-decided.
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal key is not configured" });
  const got = req.headers.get("X-Internal-Key") || "";
  let d = got.length === key.length ? 0 : 1;
  for (let i = 0; i < got.length && i < key.length; i++) d |= got.charCodeAt(i) ^ key.charCodeAt(i);
  if (d !== 0) return json(401, { error: "wrong key" });

  let body: { owner?: unknown; toolkits?: unknown; alias?: unknown; send?: unknown };
  try { body = await req.json(); } catch { return json(400, { error: "body is not JSON" }); }

  const owner = typeof body.owner === "string" ? body.owner.trim() : "";
  if (!OWNER_ID.test(owner)) return json(400, { error: "owner must be a 15-char owner row id" });
  const toolkits = Array.isArray(body.toolkits)
    ? body.toolkits.filter((t): t is string => typeof t === "string" && TOOLKIT.test(t)) : [];
  if (toolkits.length === 0) return json(400, { error: "toolkits must name at least one app slug" });
  const alias = body.alias === "work" || body.alias === "personal" ? body.alias : null;
  const send = body.send !== false;

  // The owner must exist. A mint for a row that is not there is a token bound
  // to nobody, which the page would refuse anyway — refuse it here, legibly.
  const row = await env.DB.prepare(`SELECT "id" FROM "owners" WHERE "id" = ?1 LIMIT 1`)
    .bind(owner).first<{ id: string }>();
  if (!row) return json(404, { error: "no such owner" });

  // The store is built HERE and injected, the way the nudge suite does it,
  // rather than read off the module-level wiring cron.ts installs at load.
  // A route that only works when another module happened to run first is a
  // route that works in production and fails in every test -- and the reverse
  // is the failure this repo keeps finding. mintConnectPage needs only
  // deps.store (put/putAll); createD1Store is the same store production wires.
  const deps = { store: createD1Store(env) } as unknown as NudgeDeps;
  const link = await mintConnectPage(env, owner, toolkits, alias, deps);
  const out: Record<string, unknown> = {
    ok: true, url: link.url, expires_at: link.expires_at,
    fingerprint: link.fingerprint, toolkits, sent: false,
  };
  if (!send) return json(200, out);

  const to = await ownerPhone(env)(owner as never);
  if (!to) return json(409, { ...out, error: "owner has no phone on file; link minted, not sent" });
  const sent = await sendText(env, to, textFor(link.url, toolkits.length), { tag: "admin connect-link" });
  out.sent = sent.ok;
  if (!sent.ok) return json(502, { ...out, error: sent.error || "send failed" });
  console.log(`admin connect-link: ${link.fingerprint} minted for ${owner} (${toolkits.length} app(s)) and texted`);
  return json(200, out);
}
