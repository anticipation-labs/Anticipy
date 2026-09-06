/**
 * wiring.ts — the four ports routes/connect.ts declares, built from the real
 * modules, so a deployed Worker can actually draw a connect page.
 *
 * WHY THIS FILE EXISTS AT ALL, MEASURED. On 2026-09-05 every piece of this
 * feature was written and tested — the store, the vendor client, the sentence
 * writer, the three routes, the iOS screen — and `installConnectWiring` had
 * ZERO callers, so every /c/ leg answered 503 for every token there has ever
 * been. A tested part that nothing calls is not a feature; it is a part. This
 * module and the two lines in src/index.ts that call it are the difference.
 *
 * AND THAT IS STILL ONLY HALF. Measured 2026-09-06:
 * `GET https://api.anticipy.ai/c/<43 chars>` answers 404 while `/api/health`
 * answers 200 — the deployed Worker does not carry the `/c/` prefix at all.
 * Until a deploy makes that URL answer 401, this file is repo-green and
 * HARNESS-LAWS law 3 is unmet.
 *
 * THE SEAM IS DELIBERATE AND THIS FILE DOES NOT ERASE IT. routes/connect.ts
 * owns the privacy model, the single-use gate and the HTML; it must not know
 * that the store is D1, that the catalog is an HTTP vendor, or that the
 * sentences come from a model. All three facts live here, and here only.
 *
 * WHAT THIS FILE IS NOT ALLOWED TO CONTAIN, since it is the file where it
 * would be easiest: an app name. There is no list of toolkits here, no logo,
 * no per-app copy and no per-app scope wording. Every one of those comes from
 * the catalog at run time (`provider.toolkit(slug)`) and from a model reading
 * that row (`words.sentences(meta)`). The behavioural pin is in
 * test/connections-wiring.test.ts, which runs the whole path on an app nobody
 * has ever heard of.
 *
 * HARNESS-LAWS LAW 1. Nothing here decides what a person MEANT. The three
 * checks in `connectDeps` are configuration checks — is a binding bound, is a
 * secret set — and the one in `callModel` is a model-id prefix, the same
 * routing rule src/llm.ts rule 8 already applies. The one place meaning is
 * decided is the permission sentences, and that is a model asked ONE question
 * on its own, with its answer audited by words.ts rather than trusted.
 *
 * Spec: "Connections: how Anticipy asks, learns, and never says Composio",
 * 2026-09-05, page 26.
 */
import {
  type ConnectDeps,
  type ConnectEnv,
  type ConnectWiring,
  type Connection,
} from "../routes/connect.ts";
import { createD1Store, ownerId, type ConnectionsStore, type StoredConnection }
  from "./store.ts";
import { connectionsFromEnv, type ConnectionsEnv } from "./provider.ts";
import { createD1ConnectCodeStore, type ConnectAuthDeps } from "../routes/connect_auth.ts";
import { makePermissionWords, MAX_SENTENCE_CHARS, SENTENCE_COUNT, type SentenceWriter }
  from "./words.ts";
import {
  boundMaxTokens,
  enabledModels,
  geminiGenerationConfig,
  providerBase,
  providerKeys,
  toGeminiContents,
  translateGemini,
  GOOGLE_BASE,
  MAX_REQUEST_CHARS,
  OPENROUTER_BASE,
  UPSTREAM_TIMEOUT_MS,
  type ChatMessage,
  type LlmEnv,
} from "../llm.ts";
import type { ToolkitMeta } from "../../../../spike/two-hands/src/connections/contract.ts";

/**
 * Everything the four ports need, in one shape.
 *
 * `ConnectWiring` is handed a `ConnectEnv` because that is all routes/
 * connect.ts knows about; the vendor secret and the model keys are this
 * module's business, so the widening happens here, once, in the open, rather
 * than as an `as any` at each use.
 */
export interface ConnectWiringEnv extends ConnectEnv, ConnectionsEnv, LlmEnv {}

/** How many tokens the sentence writer may spend. Three lines of at most
 *  `MAX_SENTENCE_CHARS` characters is well under this; the floor exists
 *  because src/llm.ts REPLY_FLOOR is 512 for a measured reason (a thinking
 *  model's reasoning counts against the cap and its verdicts came back cut off
 *  mid-word at 64), and `boundMaxTokens` would raise anything smaller anyway. */
export const SENTENCE_MAX_TOKENS = 512;

// ---------------------------------------------------------------------------
// THE SENTENCE WRITER
// ---------------------------------------------------------------------------

/**
 * ONE QUESTION, ASKED ON ITS OWN — HARNESS-LAWS law 1's worked shape. It is not
 * a ninth key in some other JSON reply, because a field among many loses
 * (measured: seven cases, zero moved).
 *
 * The register rules are stated to the model rather than enforced by editing
 * its answer: a house-written replacement for a bad sentence is a claim about
 * somebody's mailbox that no model made. words.ts audits what comes back and
 * REFUSES it if it breaks one, and a refusal draws the "one moment" page — the
 * page never renders a sentence this file wrote.
 *
 * NO APP IS NAMED HERE. Every concrete word in the prompt comes from the
 * catalog row that was passed in.
 */
function sentencePrompt(meta: ToolkitMeta): ChatMessage[] {
  const system = [
    `You write the ${SENTENCE_COUNT} lines a person reads before they connect one of`,
    "their own apps to Anticipy, an assistant that does small jobs for them.",
    "",
    "Answer with JSON only, in this exact shape:",
    '{"sentences": ["...", "...", "..."]}',
    "",
    `Exactly ${SENTENCE_COUNT} sentences, one per thing the connection lets Anticipy do,`,
    "derived from the scopes you are given and from nothing else. Do not invent a",
    "capability the scopes do not carry, and do not leave one out.",
    "",
    "How they must read:",
    `- At most ${MAX_SENTENCE_CHARS} characters each. A line that wraps is not read,`,
    "  and an unread line is not consent.",
    "- Plain spoken English, second person, contractions. \"Anticipy can read your",
    "  mail so it can answer questions about it.\" Not a terms page.",
    "- Never these words: authorize, authorise, authorization, grant access,",
    "  permission, permissions, integration, api, oauth, or the name of any",
    "  company whose service is brokering the connection. Say what it can DO.",
    "- No exclamation marks. No URLs. Never repeat yourself: three lines that say",
    "  one thing show one thing while three are being given.",
  ].join("\n");

  const user = [
    `App name: ${meta.name}`,
    `App id: ${meta.slug}`,
    meta.description ? `What it is: ${meta.description}` : null,
    "What the connection would cover:",
    ...meta.scopes.map((s) => `- ${s}`),
  ].filter((line): line is string => line !== null).join("\n");

  return [{ role: "system", content: system }, { role: "user", content: user }];
}

/** The model's text, or null when it produced none. */
function replyText(clientJson: unknown): string | null {
  const j = (clientJson ?? {}) as Record<string, unknown>;
  const choices = Array.isArray(j.choices) ? j.choices : [];
  const first = choices[0] as { message?: { content?: unknown } } | undefined;
  const text = first?.message?.content;
  return typeof text === "string" && text.trim() !== "" ? text : null;
}

/**
 * What the model said, turned into something words.ts can audit — and NOTHING
 * else. It never repairs, pads or trims: a reply this cannot read is handed
 * back as the raw string, which words.ts classifies as `malformed-reply`, and
 * that is a distinguishable, retryable fact rather than three sentences
 * somebody's code made up.
 *
 * Both wrappers are accepted, `{"sentences": [...]}` and a bare array, because
 * which one a model picks is a coin toss and refusing the other would be
 * refusing a good answer over its packaging. Fenced code blocks are unwrapped
 * for the same reason: the fence is transport, not content.
 */
function parseSentences(text: string): unknown {
  const fenced = /^\s*```(?:json)?\s*([\s\S]*?)\s*```\s*$/i.exec(text);
  const body = fenced ? (fenced[1] as string) : text;
  let parsed: unknown;
  try {
    parsed = JSON.parse(body);
  } catch {
    return text;
  }
  if (Array.isArray(parsed)) return parsed;
  if (parsed !== null && typeof parsed === "object") {
    const lines = (parsed as { sentences?: unknown }).sentences;
    if (lines !== undefined) return lines;
  }
  return text;
}

/**
 * One model call, over the Worker's own LLM path.
 *
 * IT REUSES src/llm.ts RATHER THAN COPYING IT. The model names, the provider
 * split (rule 8: a `google/` model goes to Google directly, everything else to
 * OpenRouter — never "whichever key exists", which once made a DeepSeek request
 * run on Gemini while the audit row still said DeepSeek), the reply cap, the
 * loopback-only base override and the request-size ceiling are all that file's
 * exported decisions, imported. A second provider client in this repo would be
 * a second set of those decisions, and they would diverge.
 *
 * WHAT IT DELIBERATELY DOES NOT REUSE: `llmProxy` itself. That function is the
 * BROWSER EXTENSION's door — it takes a Request, a paired `agents` row, an
 * hourly meter keyed to that agent and a certification ledger. None of it
 * exists for a server-side call the owner never sees, and inventing a fake
 * agent row to get through it would put unattributable rows in the audit table.
 *
 * IT THROWS ON EVERY FAILURE, and that is the FLOOR polarity: showing a person
 * what they are about to hand over is a privilege that needs a verdict, and the
 * absence of one is not permission to make three sentences up. words.ts turns
 * the throw into `no-verdict`; connect.ts turns that into "one moment", never a
 * page with a Connect button over a blank list.
 */
/**
 * THE CONNECT PAGE'S OWN MODEL, and why it is not the browser agent's.
 *
 * This used to read `enabledModels(env).browser`, and that made the connect
 * page unreachable in production. ANTICIPY_BROWSER_MODEL is
 * `google/gemini-3.1-pro-preview`, so the routing rule below sent the sentences
 * to Gemini and demanded GEMINI_API_KEY — a secret this Worker has never had.
 * Measured on 2026-09-06: every /c/ leg answered 503 "Connecting isn't switched
 * on here" for that reason alone, with everything else wired and green.
 *
 * The coupling was wrong on the merits, not just inconvenient.
 * ANTICIPY_BROWSER_MODEL exists to say what a PAIRED BROWSER AGENT may spend
 * through — it is a spending cap on somebody else's Chrome. Three plain
 * sentences generated from a toolkit's scopes are neither browser work nor
 * agent work: they are one small text call on our own page. Tying them
 * together means changing the agent's model silently takes the connect page
 * down, which is a failure nobody would think to look for.
 *
 * The default is an OpenRouter model because OPENROUTER_API_KEY is the key this
 * Worker actually holds, and a default that needs a secret nobody set is a
 * feature that does not exist. ANTICIPY_CONNECT_MODEL overrides it; a
 * `google/` value still routes to Gemini through the same rule, so pointing it
 * there later costs one variable and one secret.
 */
export const DEFAULT_CONNECT_MODEL = "anthropic/claude-sonnet-4.6";

function connectModel(env: LlmEnv & { ANTICIPY_CONNECT_MODEL?: string }): string {
  const named = typeof env.ANTICIPY_CONNECT_MODEL === "string"
    ? env.ANTICIPY_CONNECT_MODEL.trim() : "";
  return named || DEFAULT_CONNECT_MODEL;
}

async function callModel(env: LlmEnv, messages: ChatMessage[]): Promise<string> {
  const model = connectModel(env);
  const keys = providerKeys(env);
  const bounded = boundMaxTokens(SENTENCE_MAX_TOKENS);
  // src/llm.ts rule 8, applied identically.
  const geminiModel = model.startsWith("google/") ? model.slice("google/".length) : "";

  let url: string;
  let headers: Record<string, string>;
  let serialized: string;
  if (geminiModel) {
    if (!keys.gemini) throw new Error("no GEMINI_API_KEY for the connect page's sentences");
    const { systemText, contents } = toGeminiContents(messages);
    if (!contents.length) throw new Error("the sentence prompt has no usable content");
    const payload: Record<string, unknown> = {
      contents,
      generationConfig: geminiGenerationConfig(geminiModel, bounded, true),
    };
    if (systemText) payload.systemInstruction = { parts: [{ text: systemText }] };
    url = providerBase(env, GOOGLE_BASE) + "/v1beta/models/"
      + encodeURIComponent(geminiModel) + ":generateContent";
    headers = { "x-goog-api-key": keys.gemini };
    serialized = JSON.stringify(payload);
  } else {
    if (!keys.openrouter) throw new Error("no OPENROUTER_API_KEY for the connect page's sentences");
    url = providerBase(env, OPENROUTER_BASE) + "/api/v1/chat/completions";
    headers = {
      "Authorization": "Bearer " + keys.openrouter,
      "HTTP-Referer": "https://anticipy.ai",
      "X-Title": "Anticipy",
    };
    serialized = JSON.stringify({
      model, messages, temperature: 0, max_tokens: bounded,
      response_format: { type: "json_object" },
    });
  }

  // A catalog row is another company's data and its length is not ours to
  // assume. Refusing here beats being refused by the provider with a 400 the
  // log reads as "the model is down".
  if (serialized.length > MAX_REQUEST_CHARS) {
    throw new Error("the sentence prompt is larger than the model will take");
  }

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: serialized,
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
  });
  let json: unknown = null;
  try { json = await res.json(); } catch { json = null; }
  if (!json) throw new Error(`the model returned no JSON (${res.status})`);
  if (res.status < 200 || res.status >= 300) {
    // The provider's own error text is theirs and may name a vendor. The status
    // is the whole of what this log line is allowed to carry.
    throw new Error(`the model provider refused the request (${res.status})`);
  }

  const text = replyText(geminiModel ? translateGemini(json, geminiModel) : json);
  if (text === null) throw new Error("the model returned no text");
  return text;
}

/**
 * The `SentenceWriter` words.ts takes. Exported so the suite can drive the real
 * one against a stubbed provider rather than a stub of its own.
 */
export function makeSentenceWriter(env: LlmEnv): SentenceWriter {
  return async (meta: ToolkitMeta): Promise<unknown> =>
    parseSentences(await callModel(env, sentencePrompt(meta)));
}

// ---------------------------------------------------------------------------
// THE FOUR PORTS
// ---------------------------------------------------------------------------

/**
 * Why is a missing secret `null` and not a degraded page?
 *
 * `null` is routes/connect.ts's "this Worker cannot serve connect pages", and
 * it draws a 503 that says nothing has changed on the person's account. The
 * alternative — hand back deps whose provider throws on every call — draws
 * "Anticipy couldn't load this just now. Refresh in a moment", which is a LIE
 * when the secret is permanently unset: no refresh will ever help. An honest
 * 503 and a hopeful one are not the same answer, and the operator-facing half
 * differs too: the log line below names the variable to set.
 *
 * All three are configuration facts, not judgements about a request:
 *   DB                 no store, so no link can even be looked up.
 *   COMPOSIO_API_KEY   no catalog, so the page cannot name the app, no vendor
 *                      link can be minted, and the callback cannot be
 *                      confirmed against the owner's own accounts. Every leg
 *                      is dead, not just the pretty one.
 *   a model key        no permission sentences, so the only page that could be
 *                      drawn is a Connect button over a blank list of claims.
 *                      A person cannot consent to nothing.
 */
function missingConfig(env: ConnectWiringEnv): string | null {
  if (!env || !env.DB) return "the DB binding";
  const vendorKey = typeof env.COMPOSIO_API_KEY === "string" ? env.COMPOSIO_API_KEY.trim() : "";
  if (!vendorKey) return "COMPOSIO_API_KEY";
  const keys = providerKeys(env);
  // The same routing rule callModel uses, asked one step earlier so the answer
  // is a 503 the operator can read instead of a page that never loads.
  return connectModel(env).startsWith("google/")
    ? (keys.gemini ? null : "GEMINI_API_KEY")
    : (keys.openrouter ? null : "OPENROUTER_API_KEY");
}

/**
 * Where a finished connection is written, and the reason `store.ts` grew one
 * method for it.
 *
 * ONE D1 BATCH, both halves: the `connections` row and this owner's
 * `connect_nudges` row for this toolkit. It is called under the callback's
 * exactly-once lease, and that lease is a promise about ONE write — two calls
 * would be two failure modes under one promise, and the half that failed would
 * be invisible: the owner has connected the app and Anticipy keeps asking them
 * to connect it.
 *
 * `ownerId()` is called and not assumed. The type is erased before this line
 * runs, so this is the last place a display name could be stopped before it
 * reaches a query — and one operator's own mailbox served everybody once
 * already. The id arrives from the STORED LINK ROW (routes/connect.ts binds it
 * at mint time and never reads an owner off the request), so this check should
 * never fire; it costs a microsecond and it is the difference between "should
 * never" and "cannot".
 *
 * `Date.now()` rather than the injected clock: `onConnected` is handed only the
 * connection, so the moment it was recorded is this function's to know. It is
 * a timestamp on a log column, not a decision.
 */
function writeConnection(store: ConnectionsStore) {
  return async (c: Connection): Promise<void> => {
    const row: StoredConnection = {
      user_id: ownerId(c.user_id),
      toolkit: c.toolkit,
      connected_account_id: c.connected_account_id,
      alias: c.alias,
      status: c.status,
      // Passed through, never defaulted here. routes/connect.ts is the one file
      // that decides a new connection arrives with writes OFF, and a `?? true`
      // on this line would opt every owner into changes they never agreed to.
      writes_enabled: c.writes_enabled,
      last_used_at: c.last_used_at,
    };
    await store.recordConnection(row, Date.now());
  };
}

/**
 * The four ports, built.
 *
 * Note what is NOT set: `now`, `successStatus` and `baseUrl`. Tests own the
 * clock and production passes nothing; the vendor's spelling of success is
 * CALLBACK_SUCCESS until there is a reason and a place to configure it; and
 * `baseUrl` is left undefined ON PURPOSE, because routes/connect.ts already
 * reads `env.CONNECT_BASE_URL` and falls back to `CONNECT_URL_BASE`. Setting it
 * here would SHADOW the environment variable a preview deployment sets, and a
 * preview whose callback URL silently pointed at production is exactly the
 * failure that variable exists to prevent.
 */
export function connectDeps(env: ConnectWiringEnv): ConnectDeps | null {
  const missing = missingConfig(env);
  if (missing !== null) {
    console.log(
      `connect wiring: not installed on this Worker — ${missing} is unset, so no connect `
        + "page can be drawn and no link can be redeemed. Set it and redeploy.",
    );
    return null;
  }
  const store = createD1Store(env);
  return {
    store,
    provider: connectionsFromEnv(env),
    words: makePermissionWords(makeSentenceWriter(env)),
    onConnected: writeConnection(store),
  };
}

/**
 * The argument `installConnectAuthWiring` takes: the phone-code half.
 *
 * IT SHARES connect.ts's LINK STORE, and that is the whole point of building it
 * here rather than in `connect_auth.ts`. Two `createD1Store(env)` calls would
 * be two answers to "is this link still live" — one route could text a code for
 * a link the other had already spent. `connectDeps` builds the store once and
 * this reuses that instance.
 *
 * The same `missingConfig` gate applies by construction: if `connectDeps`
 * refuses, there is no store to share and this refuses too, so the code half
 * can never be live on a Worker whose page half is not.
 */
export const connectAuthWiring = (env: ConnectWiringEnv): ConnectAuthDeps | null => {
  const deps = connectDeps(env);
  if (!deps) return null;
  return {
    links: deps.store,
    codes: createD1ConnectCodeStore(env),
    // The catalog, injected. A blip costs the app's NAME in one sentence of the
    // text, never the code itself — so this swallows the failure rather than
    // letting it stop somebody signing in.
    async toolkitName(slug: string): Promise<string | null> {
      try {
        return (await deps.provider.toolkit(slug))?.name ?? null;
      } catch {
        return null;
      }
    },
  };
};

/**
 * The argument `installConnectWiring` takes. src/index.ts calls it once at
 * module load; it is a FUNCTION OF env rather than a built object because a
 * Worker's bindings do not exist at module load — they arrive per request.
 */
export const connectWiring: ConnectWiring = (env: ConnectEnv): ConnectDeps | null =>
  connectDeps(env as ConnectWiringEnv);
