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
  return async (meta: ToolkitMeta): Promise<unknown> => {
    const messages = sentencePrompt(meta);
    let reply = parseSentences(await callModel(env, messages));
    for (let attempt = 1; attempt < SENTENCE_ATTEMPTS; attempt++) {
      const complaint = tooLong(reply);
      if (complaint === null) return reply;
    // ONE RETRY, WITH THE FAILURE NAMED. Measured 2026-09-06 against the live
    // model: Gmail's eleven scopes produce the same 84-character line SIX
    // TIMES OUT OF SIX. The prompt already states the limit and the model
    // still misses it, so asking again identically is the definition of
    // pointless -- but asking again while SHOWING it the line it wrote and the
    // count it broke is a different question, and it is the question a person
    // would ask. Without it Gmail, the app this product exists around, can
    // never be connected by anybody.
    //
    // THE JUDGE DOES NOT MOVE. words.ts still measures every line against
    // MAX_SENTENCE_CHARS and still refuses a second answer that is too long.
    // Raising the cap would have been the easy green and the wrong one: the
    // limit is what a person actually reads, and an unread line is not consent.
      messages.push({ role: "assistant", content: JSON.stringify(reply) });
      messages.push({ role: "user", content: complaint });
      reply = parseSentences(await callModel(env, messages));
    }
    // Whatever the last attempt said, handed to words.ts to judge. If it is
    // still too long it is still refused -- the point of the loop is to give
    // the model the failure, not to give up on the limit.
    return reply;
  };
}

/**
 * How many times the writer will ask, counting the first.
 *
 * MEASURED, not chosen. Against the live model on 2026-09-06, Gmail's eleven
 * scopes came back over the limit 6 times out of 6 with one attempt, and 5 out
 * of 6 with two. Each attempt is one model call on a page a person is waiting
 * for, so this is a real cost and not a free retry -- but the page is drawn
 * once per connection, and an app nobody can connect costs infinitely more.
 */
export const SENTENCE_ATTEMPTS = 4;

/**
 * The complaint to send back, or null when every line already fits.
 *
 * Reads the writer's OWN parsed reply, not the model's raw text: a reply we
 * could not parse is not a length problem and must fall through to words.ts,
 * which has a cause for it and a sentence a person could act on.
 */
function tooLong(reply: unknown): string | null {
  // parseSentences returns the ARRAY, not `{sentences: [...]}`. Reading the
  // object shape was this function's first bug and it was invisible: `tooLong`
  // returned null for every reply, the retry never fired once, and Gmail went
  // on failing 6/6 exactly as before with a retry sitting in the file looking
  // like it worked. Both shapes are accepted now, and the suite drives the
  // real parseSentences rather than a hand-built object, so a change to what
  // it returns cannot quietly switch the retry off again.
  const lines = Array.isArray(reply)
    ? reply
    : (reply as { sentences?: unknown } | null)?.sentences;
  if (!Array.isArray(lines)) return null;
  const over = lines.filter((l): l is string =>
    typeof l === "string" && l.length > MAX_SENTENCE_CHARS);
  if (over.length === 0) return null;
  return [
    `${over.length === 1 ? "One of those lines is" : `${over.length} of those lines are`}`
    + ` longer than ${MAX_SENTENCE_CHARS} characters, so it wraps and nobody reads it:`,
    ...over.map((l) => `- ${l.length} characters: ${l}`),
    "",
    `Write all ${SENTENCE_COUNT} again. Same meaning, same order, nothing dropped and`,
    `nothing merged -- every line at most ${MAX_SENTENCE_CHARS} characters. Shorten by`,
    "cutting words, not by cutting what the connection can do.",
  ].join("\n");
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

// ===========================================================================
// THE NUDGE HALF — what `installNudgeWiring` is handed
// ===========================================================================
//
// WHY THIS LIVES IN THE SAME FILE AS THE CONNECT HALF. They are the two halves
// of one seam: the connect half is what a person sees AFTER they tap, the nudge
// half is what puts the link in front of them in the first place. Both are the
// place — and the only place — where this feature learns that the store is D1,
// that the catalog is an HTTP vendor, and that the words come from a model.
// Splitting them would mean two files that must agree about which secrets make
// connecting possible, and they would drift.
//
// WHY IT EXISTS AT ALL, MEASURED. `installNudgeWiring`
// (src/connections/nudge.ts:326) had ZERO callers on 2026-09-06 — the same
// shape as `installConnectWiring` a day earlier and with the same result: a
// tested policy, a tested sweep, a tested link mint, a tested judge, and not
// one person ever asked anything. src/cron.ts installs this at module load.
//
// WHAT THIS FILE STILL MUST NOT CONTAIN, and does not: an app name, a logo, a
// slug, a domain, or one word of per-app copy. The candidate's toolkit is a
// column read out of D1 and passed on; the name comes from the catalog at run
// time; the sentence comes from a model. test/connections-ask.test.ts drives
// the whole path on slugs that exist in no catalog.
//
// The imports for this half are declared here rather than in the block at the
// top of the file, so that the whole nudge half is one contiguous region and a
// change to it cannot collide with a change to the connect half.

import {
  GLOBAL_ASK_INTERVAL_DAYS,
  type NudgeDeps,
  type NudgeEnv,
  type NudgeMoment,
  type NudgeWiring,
} from "./nudge.ts";
import { ALIVE_WEIGHT_FLOOR, MOMENT_SOURCES, createDue } from "./due.ts";
import { DEFAULT_HALF_LIFE_MS, SOURCE_DECAYS, decayedWeight } from "./signals.ts";
import { makeAskWriter, askModel, MAX_PHRASING_LINES, type AskEnv } from "./ask.ts";
import { chooseProvider } from "../messaging.ts";
import type { SignalSource, StoreEnv } from "./store.ts";
import type {
  AccountAlias, NudgeTrigger, OwnerId, Toolkit,
} from "../../../../spike/two-hands/src/connections/contract.ts";

/**
 * Everything the six ports need, in one shape — and an INTERSECTION rather than
 * an interface, because `NudgeEnv.DB` is optional (nudge.ts never queries D1
 * itself) while `StoreEnv.DB` is required, and an interface cannot extend both.
 */
export type NudgeWiringEnv = NudgeEnv & StoreEnv & ConnectionsEnv & AskEnv;

/** The job statuses that mean the work is OVER.
 *
 *  A LIST OF STATUSES, WHICH IS STRUCTURE AND NOT MEANING. It reads a status
 *  column — a fact this system wrote about its own work — and never a sentence
 *  anybody said. That is the `MOMENT_TRIGGER` shape from due.ts, with one
 *  honest difference: `app_usage_signals.source` carries a CHECK constraint and
 *  `jobs.status` does not (schema.sql only requires it to be non-empty), so
 *  this list cannot be complete by construction. Which is exactly why the
 *  polarity below is the one it is.
 *
 *  THE POLARITY IS THE ASK'S. Anything NOT on this list counts as still
 *  running, so an unknown status — a state the brain adds tomorrow, a row
 *  written by an older build — reads as "something of theirs is in flight" and
 *  HOLDS the ask. The other direction would text somebody mid-errand, which is
 *  the one thing the spec says an ask must never do. Values observed in
 *  brain/worker.py: queued, running, awaiting_confirm, needs_user, handling,
 *  done, failed, cancelled.
 */
export const FINISHED_JOB_STATUS: readonly string[] =
  Object.freeze(["done", "failed", "cancelled"]);

/**
 * How long a job may go UNTOUCHED and still count as a step in progress.
 *
 * WHY THERE HAS TO BE A NUMBER HERE AT ALL, measured 2026-09-06. Without one,
 * `taskInFlight` counted every row not on `FINISHED_JOB_STATUS` over ALL TIME,
 * and `resultDelivered` read the same count — so a SINGLE row stranded by a
 * deploy in March held both floors closed for the rest of that owner's life,
 * and the log said "a step is still running", which is also what a healthy
 * busy minute says. An unbounded floor is not a conservative floor; it is a
 * switch that one bad row turns off permanently.
 *
 * WHY ONE DAY. Everything in this product that claims a job hands it back in
 * MINUTES — brain/worker.py's `RESEARCH_STRANDED_MINUTES` is 15, and the
 * extension's own stale sweep is shorter — so a day is three orders of
 * magnitude of headroom over any step anybody is standing in front of. The
 * two long-lived statuses, `awaiting_confirm` and `needs_user`, are the ones
 * this bound is really about: they wait on the OWNER, and a question they
 * have not answered in over a day has stopped being a step this ask could
 * interrupt. It is still the generous side of the trade — a whole day of
 * silence bought by one open row.
 *
 * DAY GRANULARITY, so the real window is one to two days depending on the
 * hour. That is deliberate: the comparison is `substr(..., 1, 10)` against a
 * bare date for the reason the query below states at length — this tree holds
 * two spellings of a timestamp and only the date part compares the same in
 * both. Fuzzy on the generous side beats exact and wrong for half the rows.
 */
export const STRANDED_JOB_AFTER_DAYS = 1;

/** The contract's two account aliases, AS VALUES. `AccountAlias` is erased
 *  before this file runs, so a row that says "Work" or "personal " stops here
 *  rather than at a D1 CHECK three writes later. */
const ACCOUNT_ALIASES: readonly string[] = Object.freeze(["work", "personal"]);

/**
 * The owner-local hour, or null when we cannot tell 2am from 2pm.
 *
 * NULL IS THE ANSWER WHEN THERE IS NO TIMEZONE, and it must be: `localHour` is
 * a floor input to `shouldAsk`, and defaulting to UTC is exactly how somebody
 * in Auckland gets a connect link at 2am from a server that thought it was
 * lunchtime. `owner_profile.timezone` is an IANA id (schema.sql 1.5); an owner
 * who has never set one is an owner this sweep stays quiet about.
 *
 * Clocks are senses. Nothing here decides what anybody meant.
 */
export function ownerLocalHour(timezone: string, now: number): number | null {
  const zone = typeof timezone === "string" ? timezone.trim() : "";
  if (zone === "") return null;
  if (typeof now !== "number" || !Number.isFinite(now)) return null;
  let text: string;
  try {
    text = new Intl.DateTimeFormat("en-GB", {
      timeZone: zone, hour: "2-digit", hourCycle: "h23",
    }).format(new Date(now));
  } catch {
    // An unreadable IANA id is not a reason to guess at an hour.
    return null;
  }
  const digits = text.replace(/[^0-9]/g, "");
  if (digits === "") return null;
  const hour = Number(digits);
  if (!Number.isInteger(hour) || hour < 0 || hour > 24) return null;
  // Some ICU builds render midnight as 24 under h23's cousin h24. Folded rather
  // than refused, because an hour that is off by a day-boundary is the one this
  // whole check exists to get right.
  return hour === 24 ? 0 : hour;
}

interface PersonRow {
  owner_phone: unknown;
  profile_phone: unknown;
  timezone: unknown;
}

/** The account row and its profile, in one read. */
async function readPerson(env: NudgeWiringEnv, owner: string): Promise<PersonRow | null> {
  const row = await env.DB.prepare(
    `SELECT o."phone" AS owner_phone, p."phone" AS profile_phone, p."timezone" AS timezone
       FROM "owners" o
       LEFT JOIN "owner_profile" p ON p."owner_ref" = o."id"
      WHERE o."id" = ?1
      LIMIT 1`,
  ).bind(owner).first<PersonRow>();
  return row ?? null;
}

/**
 * WHERE THE TEXT GOES. The account's own number first, the profile's second.
 *
 * TWO COLUMNS BECAUSE THE TREE HAS TWO. `owners.phone` is the account's (E.164,
 * schema.sql 1.7) and `owner_profile.phone` is the one an inbound text is
 * routed by (`idx_owner_profile_phone`). An owner who has one and not the other
 * is a real shape in this database, and taking only one of them would make the
 * ask unreachable for whichever half of the table stored it elsewhere.
 *
 * IT NEVER FALLS THROUGH TO ANOTHER COLUMN OR ANOTHER ROW. An owner with no
 * number is a hold — `sendConnectAsk` answers `no-phone` — never a guess. The
 * one failure this whole feature is shaped around is a message that reaches the
 * wrong person.
 */
export function ownerPhone(env: NudgeWiringEnv) {
  return async (owner: OwnerId): Promise<string | null> => {
    const row = await readPerson(env, ownerId(String(owner ?? "")));
    if (!row) return null;
    const account = typeof row.owner_phone === "string" ? row.owner_phone.trim() : "";
    if (account !== "") return account;
    const profile = typeof row.profile_phone === "string" ? row.profile_phone.trim() : "";
    return profile !== "" ? profile : null;
  };
}

interface WorkRow {
  unfinished: unknown;
  stranded: unknown;
  /** The date of the OLDEST stranded row's last touch, so the log can say
   *  "stuck since March" rather than "busy". Null when nothing is stranded. */
  stranded_since: unknown;
  finished_recently: unknown;
}

interface EvidenceRow {
  alias: unknown;
  /** The three the decay needs. As STORED — which is the weight as of this
   *  row's own `last_seen_at` and not the weight now; see the read itself. */
  source: unknown;
  weight: unknown;
  last_seen_at: unknown;
}

interface PhrasingRow {
  text: unknown;
}

/**
 * HOW MANY OF THE OWNER'S OWN LINES, and how long each may be.
 *
 * The count mirrors ask.ts's `MAX_PHRASING_LINES` — imported rather than
 * retyped, so the two cannot drift and this read cannot fetch rows the prompt
 * would silently drop. The per-line ceiling is this file's, and it is a CEILING
 * ON SOMEBODY ELSE'S DATA in exactly the sense ask.ts means: a transcript line
 * has no length this code may assume, `callAskModel` refuses a prompt over
 * MAX_REQUEST_CHARS, and an ask lost because one line ran long is an ask lost
 * to plumbing. 240 characters is several sentences of speech — enough to hear
 * a voice in, which is the whole job.
 */
const PHRASING_LINE_CHARS = 240;

/**
 * THE OWNER'S OWN WORDS — the spec's third writer input ("the user's own
 * phrasing history", page 22), read from this owner's own rows and nobody
 * else's.
 *
 * WHAT IT SELECTS AND WHY IT SELECTS NOTHING CLEVERER. The newest lines this
 * owner SPOKE (`speaker = 'owner'`) that were ADDRESSED TO US — a text they
 * sent this number (`kind = 'sms_reply'`, which is what src/pb/sender.ts lands
 * an inbound message as) or a line the sense layer already marked
 * `addressee = 'assistant'`. There is no filter for lines that MENTION an app,
 * and there must not be one: "is this line about their apps?" is a meaning
 * question, and answering it with a LIKE or a word list would be the law-1
 * violation this whole area is shaped around. It would also be the wrong
 * question — the writer wants a VOICE, not a topic.
 *
 * THE ADDRESSEE FILTER IS NOT A REFINEMENT, IT IS THE PRIVACY LINE. This owner
 * wears a pendant. `speaker = 'owner'` alone is every sentence they have said
 * out loud in front of it, including halves of private conversations with
 * other people, and putting one of those into a prompt so a text message can
 * sound more like them is not a trade this product gets to make on their
 * behalf. Both clauses read machine facts our own code wrote — a channel and a
 * column — and neither reads what anybody said.
 *
 * IT ERRS TOWARD EMPTY. An owner who has never texted this number and whose
 * addressee column is unset gets no phrasing and a slightly stiffer sentence.
 * That is the correct direction: a missing voice costs register, and the wrong
 * lines cost something that cannot be given back.
 *
 * NOTHING READS THESE LINES. They are handed to the model and to nothing else:
 * no branch in this file, in nudge.ts or in words.ts looks at their content.
 * They cannot change whether somebody is asked, only how the sentence sounds.
 *
 * `owner_ref = ?1` IS THE WHOLE PRIVACY MODEL and it is the reason this read
 * lives here rather than in ask.ts: `AskInput` carries no owner, so a writer
 * that fetched its own phrasing would have to remember whose ask it was
 * writing, and the first parallel sweep would put one person's sentences in
 * another person's text.
 *
 * AN UNREADABLE `events` TABLE IS NOT A HOLD. Every other input to the moment
 * is a floor — absent, nobody is asked. This one is not: it changes register,
 * never permission, so failing to read it costs a slightly stiffer sentence
 * and must not cost somebody their ask. It returns [] and says nothing.
 */
async function ownerPhrasing(env: NudgeWiringEnv, owner: string): Promise<string[]> {
  try {
    const res = await env.DB.prepare(
      `SELECT substr("text", 1, ?3) AS "text" FROM "events"
        WHERE "owner_ref" = ?1 AND "speaker" = 'owner' AND "text" != ''
          AND ("kind" = 'sms_reply' OR "addressee" = 'assistant')
        ORDER BY "created" DESC
        LIMIT ?2`,
    ).bind(owner, MAX_PHRASING_LINES, PHRASING_LINE_CHARS).all<PhrasingRow>();
    const out: string[] = [];
    for (const row of res.results ?? []) {
      const line = typeof row?.text === "string" ? row.text.trim() : "";
      if (line !== "") out.push(line);
    }
    return out;
  } catch {
    return [];
  }
}

/**
 * THE MOMENT, established from this owner's own rows — the port
 * `src/connections/nudge.ts` declares and deliberately refuses to implement.
 *
 * EVERY FIELD IS A FLOOR INPUT: absent or unreadable, this returns null and
 * `sendConnectAsk` answers `no-moment` and texts nobody. That is why every
 * branch below returns null rather than a default.
 *
 *   localHour                 owner_profile.timezone, through the ICU clock.
 *                             No timezone, no ask. See `ownerLocalHour`.
 *
 *   taskInFlight              any `jobs` row of theirs whose status is not on
 *                             `FINISHED_JOB_STATUS` AND which something has
 *                             TOUCHED inside `STRANDED_JOB_AFTER_DAYS`. An
 *                             unknown status counts as running — see that
 *                             constant for the polarity — but an unknown
 *                             status nobody has moved since March does not,
 *                             see `STRANDED_JOB_AFTER_DAYS` for why an
 *                             unbounded version of this floor is a switch one
 *                             bad row turns off forever.
 *
 *   resultDelivered           NOTHING of theirs is unfinished, AND at least one
 *                             job of theirs finished inside the last
 *                             `GLOBAL_ASK_INTERVAL_DAYS` days.
 *
 *                             THE SECOND HALF IS NOT DECORATION, and this is
 *                             the honest part of the design. This Worker does
 *                             not record that a result was DELIVERED — the
 *                             brain sends those — so "the ask comes after the
 *                             result, never instead of it" cannot be read
 *                             directly. What can be read is whether this person
 *                             is waiting on anything (they are not) and whether
 *                             Anticipy has actually finished something for them
 *                             lately (it has). Requiring both keeps the two
 *                             floors in `shouldAsk` independent: collapsing
 *                             `resultDelivered` into `!taskInFlight` would make
 *                             one input answer two questions, and a rule that
 *                             is really one rule wearing two hats is a rule
 *                             that gets deleted by somebody tidying up.
 *
 *                             It errs toward silence: an owner whose only job
 *                             is nine days old is not asked. The alternative
 *                             errs toward an interruption out of nowhere.
 *
 *   tasksThatWouldHaveUsedIt  how many pieces of MOMENT-BEARING evidence this
 *                             owner has for this app that have not decayed to
 *                             nothing. Not a count of jobs, and the name is the
 *                             contract's rather than this file's: an `observer`
 *                             row exists only because a browser run ended on
 *                             that app's own host, and a `said` row only
 *                             because a model resolved this owner's own words
 *                             to this toolkit — so each one is at least one
 *                             real occasion the connection would have been
 *                             used. The policy reads this number in exactly one
 *                             place (`=== 0`, a hold), which is the question a
 *                             row count answers exactly: is there any evidence
 *                             at all, or is this an advertisement.
 *
 *   alias                     the account this evidence was about, when the
 *                             rows agree on one. Two different aliases is
 *                             ambiguity, and ambiguity is `null` — the spec
 *                             answers that case by ASKING ("work or personal
 *                             for this?"), never by picking.
 *
 *   whatHappened / browserMs  DELIBERATELY UNSET from a sweep. Neither is
 *                             recorded anywhere this can read, and inventing
 *                             "that took 40 seconds" is the writer being handed
 *                             a fact nobody measured. `MOMENT_SENTENCE` in
 *                             ask.ts gives the model the moment it really has.
 *                             A caller that KNOWS one of them — the in-task
 *                             path, which watched the browser run — calls
 *                             `sendConnectAsk` with its own deps and fills them
 *                             in.
 *
 * HARNESS-LAWS LAW 1. Three SQL reads and a clock. Nothing here reads prose,
 * and the one enum it compares against (`FINISHED_JOB_STATUS`) is a status
 * column, not a sentence.
 */
export function nudgeMomentFor(env: NudgeWiringEnv) {
  return async (
    owner: OwnerId,
    toolkit: Toolkit,
    _trigger: NudgeTrigger,
    now: number,
  ): Promise<NudgeMoment | null> => {
    // `_trigger` is unused ON PURPOSE and is not a hole: the trigger says which
    // moment NAMED this ask, and the policy is what scores it. Everything below
    // is a fact about the owner right now, and it is the same fact whichever
    // trigger asked.
    const who = ownerId(String(owner ?? ""));
    const slug = typeof toolkit === "string" ? toolkit.trim().toLowerCase() : "";
    if (slug === "") return null;
    if (typeof now !== "number" || !Number.isFinite(now)) return null;

    const person = await readPerson(env, who);
    if (!person) return null;
    const localHour = ownerLocalHour(String(person.timezone ?? ""), now);
    if (localHour === null) return null;

    // THE WORK. `substr(created, 1, 10)` compares the DATE ONLY, on purpose.
    // This tree holds timestamps in TWO SPELLINGS — "2026-09-06 12:00:00.000Z"
    // (pbNow, a space) and "2026-09-06T12:00:00.000Z" (toISOString, a T); see
    // pbTime in src/pb/wire.ts, which exists for the same reason. A space sorts
    // BEFORE a T, so any comparison that reaches past the tenth character
    // answers differently depending on which writer made the row.
    //
    // Against today's `since`, which is a bare date, both spellings already
    // compare correctly — so this is belt and braces rather than a live bug
    // fix, and it is worth the two words because the day somebody gives the
    // bound a time of day, the raw column silently starts preferring rows
    // written by one of the two writers. test/connections-ask.test.ts drives a
    // job in each spelling.
    //
    // BOUND, never interpolated. The list is a frozen constant so a literal
    // would be harmless today, and it would stop being harmless the first time
    // somebody made it configurable.
    //
    // `MAX("updated", "created")` IS THE LAST TIME ANYTHING TOUCHED THE ROW.
    // `jobs.updated` is the column the rest of the system already calls a
    // heartbeat — src/pb/records.ts stamps it on every PATCH, and
    // brain/worker.py's own stranded sweep selects on `updated <= cutoff` —
    // but it is `NOT NULL DEFAULT ''` and a hand-written row can carry the
    // empty string, which would sort before every date and read as stranded.
    // The scalar MAX falls back to `created` for exactly that row, so a job is
    // only stranded when BOTH of its clocks say so; a row carrying neither is
    // not evidence that a step is in progress, and reads as stranded.
    const finishedList = FINISHED_JOB_STATUS.map((_, i) => `?${i + 4}`).join(", ");
    const dayOf = (ms: number): string => new Date(ms).toISOString().slice(0, 10);
    const since = dayOf(now - GLOBAL_ASK_INTERVAL_DAYS * 24 * 60 * 60 * 1000);
    const touchedSince = dayOf(now - STRANDED_JOB_AFTER_DAYS * 24 * 60 * 60 * 1000);
    const lastTouch = `substr(MAX("updated", "created"), 1, 10)`;
    const work = await env.DB.prepare(
      `SELECT
         SUM(CASE WHEN "status" IN (${finishedList}) THEN 0
                  WHEN ${lastTouch} >= ?3 THEN 1 ELSE 0 END) AS unfinished,
         SUM(CASE WHEN "status" IN (${finishedList}) THEN 0
                  WHEN ${lastTouch} >= ?3 THEN 0 ELSE 1 END) AS stranded,
         MIN(CASE WHEN "status" IN (${finishedList}) THEN NULL
                  WHEN ${lastTouch} >= ?3 THEN NULL
                  ELSE ${lastTouch} END) AS stranded_since,
         SUM(CASE WHEN "status" IN (${finishedList})
                   AND substr("created", 1, 10) >= ?2 THEN 1 ELSE 0 END) AS finished_recently
         FROM "jobs" WHERE "owner_ref" = ?1`,
    ).bind(who, since, touchedSince, ...FINISHED_JOB_STATUS).first<WorkRow>();
    // SUM over no rows is NULL, which is an owner with no jobs at all.
    const unfinished = Number(work?.unfinished ?? 0) || 0;
    const stranded = Number(work?.stranded ?? 0) || 0;
    const strandedSince = typeof work?.stranded_since === "string" ? work.stranded_since : "";
    const finishedRecently = Number(work?.finished_recently ?? 0) || 0;

    // TWO SENTENCES THAT USED TO BE ONE. "A step is still running" was printed
    // for a job that started ninety seconds ago and for a job abandoned in
    // March, and the second one is not a busy owner, it is a bug in some other
    // module wearing this one's clothes. An operator reading the sweep's log
    // has to be able to tell them apart without opening the database.
    //
    // Only when there is something open: a line per candidate per tick about
    // an owner with nothing running is how a log stops being read.
    if (unfinished > 0 || stranded > 0) {
      console.log(
        `connect ask: ${who} has ${unfinished} job(s) touched inside `
          + `${STRANDED_JOB_AFTER_DAYS}d (busy now, the ask holds) and ${stranded} not touched `
          + `since ${strandedSince || "a date neither of its clocks carries"} `
          + "(stranded, holding nothing).",
      );
    }

    // THE EVIDENCE, over the same sources due.ts calls moments and no others —
    // imported rather than re-listed, so a third moment cannot be selected as a
    // candidate and then counted as no evidence here.
    //
    // NO WEIGHT PREDICATE, AND THAT IS THE FIX. This read carried
    // `AND "weight" > 0` until 2026-09-06 and called it an aliveness test. It
    // never was one: signals.ts decays on READ, and the STORED column only
    // moves when a new signal arrives for that (owner, app, source, alias) —
    // which RAISES it. So the number never falls, the predicate was true for
    // every row that has ever existed, and a browser run from four hundred days
    // ago counted as one of the "tasks that would have used it" the spec makes
    // the whole ask conditional on. due.ts deleted the same predicate for the
    // same reason and moved the test into TypeScript; this is the other half of
    // that fix, and it goes through the SAME seam rather than a second copy:
    // `decayedWeight` and `SOURCE_DECAYS` are signals.ts's, `ALIVE_WEIGHT_FLOOR`
    // is due.ts's, and neither number is restated here. Two definitions of
    // alive, in two files, is exactly the state this repair ends.
    const inList = MOMENT_SOURCES.map((_, i) => `?${i + 3}`).join(", ");
    const evidence = await env.DB.prepare(
      `SELECT "alias", "source", "weight", "last_seen_at" FROM "app_usage_signals"
        WHERE "user_id" = ?1 AND "toolkit" = ?2
          AND "source" IN (${inList})`,
    ).bind(who, slug, ...MOMENT_SOURCES).all<EvidenceRow>();
    // `>` and not `>=`, matching the direction the deleted SQL predicate
    // pointed and the one due.ts's own filter keeps: a row sitting exactly on
    // the floor has run out its silence. A weight nothing can read is NaN, and
    // every comparison against NaN is false, so it falls OUT — which is the
    // direction that asks fewer people. The `SOURCE_DECAYS` lookup is the same
    // seam `weightNow` uses in due.ts, and its odd answers all land on the
    // decaying branch, which is the stricter one.
    const rows = (evidence.results ?? []).filter((row) => {
      const stored = Number(row?.weight);
      const alive = SOURCE_DECAYS[String(row?.source) as SignalSource]
        ? decayedWeight(stored, Number(row?.last_seen_at), now, DEFAULT_HALF_LIFE_MS)
        : stored;
      return alive > ALIVE_WEIGHT_FLOOR;
    });

    const aliases = new Set<string>();
    for (const row of rows) {
      const alias = typeof row?.alias === "string" ? row.alias.trim() : "";
      if (alias !== "") aliases.add(alias);
    }
    // CHECKED BY A CALL, not by the annotation, because the annotation is
    // erased before this runs. `connections.alias` and `connect_links.alias`
    // both CHECK the value in D1, so a junk alias would fail the link INSERT —
    // which is a mint that throws, an ask that is not sent, and a log line
    // about a link rather than about an alias. Refusing here is one line and
    // says the true thing.
    const only = aliases.size === 1 ? [...aliases][0] : "";
    const alias: AccountAlias | null =
      ACCOUNT_ALIASES.includes(only) ? (only as AccountAlias) : null;

    // NOT A FLOOR INPUT, unlike everything above it: an owner whose lines
    // cannot be read is still asked, in a slightly stiffer voice. See
    // `ownerPhrasing`.
    const phrasing = await ownerPhrasing(env, who);

    return {
      localHour,
      taskInFlight: unfinished > 0,
      resultDelivered: unfinished === 0 && finishedRecently > 0,
      tasksThatWouldHaveUsedIt: rows.length,
      alias,
      phrasing,
    };
  };
}

/**
 * Why is a missing secret `null` and not a degraded sweep?
 *
 * The same answer the connect half gives, with one difference in TONE and none
 * in behaviour: nobody is standing in front of this waiting, so an unwired
 * sweep is SILENT rather than a 503. `connectNudgeSweep` logs that it asked
 * nobody and names the missing wiring, which is the honest place for a deploy
 * check to notice.
 *
 * All four are configuration facts, not judgements about anybody:
 *   DB                 no store, so no link can be bound and no history read.
 *   COMPOSIO_API_KEY   no catalog, so the ask cannot name the app — and a text
 *                      that says "connect your undefined" is, to the person
 *                      reading it, indistinguishable from a phishing message.
 *   a model key        nothing writes the sentence, and this file will not.
 *   a messaging path   nowhere to send it. Checked HERE rather than left to
 *                      fail at the send, because `sendConnectAsk` mints the
 *                      link and writes the `asked` row BEFORE it sends: a
 *                      Worker with no provider would burn a link and a row per
 *                      candidate per tick and hand the lease back each time,
 *                      forever, and every one of those is a D1 write.
 */
function missingNudgeConfig(env: NudgeWiringEnv): string | null {
  if (!env || !env.DB) return "the DB binding";
  const vendorKey = typeof env.COMPOSIO_API_KEY === "string" ? env.COMPOSIO_API_KEY.trim() : "";
  if (!vendorKey) return "COMPOSIO_API_KEY";
  const keys = providerKeys(env);
  // The same routing rule `callAskModel` uses, asked one step earlier so the
  // answer is a log line an operator can read instead of a sweep that refuses
  // every draft it asks for.
  const modelKey = askModel(env).startsWith("google/")
    ? (keys.gemini ? null : "GEMINI_API_KEY")
    : (keys.openrouter ? null : "OPENROUTER_API_KEY");
  if (modelKey !== null) return modelKey;
  if (chooseProvider(env) === "none") {
    return "a messaging provider (SENDBLUE_API_KEY_ID + SENDBLUE_API_SECRET_KEY, "
      + "or the TWILIO_* trio)";
  }
  return null;
}

/**
 * The six ports, built.
 *
 * `catalog` is NARROWED to the one method the ask needs rather than handed the
 * whole provider. nudge.ts's seam says why in its own words: a file that could
 * reach the rest of the client could spend a token, delete a connection or
 * start a session, and none of that belongs to writing one text message.
 *
 * `now` is left unset: tests own the clock and production passes nothing.
 * `baseUrl` is left unset for the reason `connectDeps` gives — nudge.ts already
 * reads `env.CONNECT_BASE_URL` and falls back to `CONNECT_URL_BASE`, and
 * setting it here would SHADOW the variable a preview deployment sets, so a
 * preview would mint links that redeem against production.
 */
export function nudgeDeps(env: NudgeWiringEnv): NudgeDeps | null {
  const missing = missingNudgeConfig(env);
  if (missing !== null) {
    console.log(
      `connect nudge wiring: not installed on this Worker — ${missing} is unset, so nobody `
        + "will be asked to connect anything. Set it and redeploy.",
    );
    return null;
  }
  const provider = connectionsFromEnv(env);
  return {
    store: createD1Store(env),
    catalog: { toolkit: (slug: Toolkit) => provider.toolkit(slug) },
    write: makeAskWriter(env),
    moment: nudgeMomentFor(env),
    phone: ownerPhone(env),
    due: createDue(env),
  };
}

/**
 * The argument `installNudgeWiring` takes. src/cron.ts calls it once at module
 * load; it is a FUNCTION of env rather than a built object because a Worker's
 * bindings do not exist at module load — they arrive per request and per tick.
 */
export const nudgeWiring: NudgeWiring = (env: NudgeEnv): NudgeDeps | null =>
  nudgeDeps(env as NudgeWiringEnv);

// ===========================================================================
// THE TEXT TWIN — the ports src/connections/text_commands.ts declares, and the
// one executor that carries its plans out.
//
// The spec's rule for this whole area is one line: "Everything here has a text
// twin" (page 27 of 31). text_commands.ts turns ONE inbound message into a
// PLAN and performs no side effect; everything below is the other half — the
// two model calls the plan is decided by, and the sends and writes it becomes.
//
// WHY THE DEPS ARE A FUNCTION OF THE MESSAGE. `TextCommandDeps.catalog` takes
// the owner and not the message, so the list a judge is allowed to pick from
// has to be narrowed BEFORE the deps are built. That is why `textCommandDeps`
// takes `said`: the catalog it returns is the vendor's own search over the
// owner's words, unioned with the apps this owner already holds. Both halves
// are LOOKUPS — one is the vendor answering its own catalog question (the same
// thing GET /me/connections/catalog?q= does with the owner's words untouched),
// the other is a table read — and neither decides what anything MEANT. The
// meaning question is asked once, of a model, with that list in front of it.
//
// WHY THE UNION AND NOT JUST THE SEARCH. A search over a whole sentence can
// miss; the owner's own connected rows cannot. "disconnect the one I set up
// last week" has to be able to resolve against apps they hold even when the
// vendor's search finds nothing for that sentence. The failure direction of a
// miss is `ask_which_app` — a question, never a wrong app.
//
// HARNESS-LAWS LAW 1. Nothing here decides what a person MEANT. There is no
// regex over the message, no word list, no substring test and no app name; the
// message is passed verbatim to the vendor's search and verbatim to the two
// judges, and every branch below reads a machine value: a plan `kind` this
// module produced, a row this database holds, a status this system wrote.
// ===========================================================================

import {
  displayName,
  planTextCommand,
  TEXT_COMMANDS,
  type TextCommand,
  type TextCommandDeps,
  type TextCommandPlan,
} from "./text_commands.ts";
import { FORBIDDEN_TERMS, forbiddenTermIn } from "./words.ts";
import { freshNudge, maturedBySilence, mintConnectLink } from "./nudge.ts";
import { sendText } from "../messaging.ts";
import type { ToolkitMeta as ToolkitRow } from "../../../../spike/two-hands/src/connections/contract.ts";

/** Everything the text twin needs, in one shape: the store, the vendor, the
 *  model and a way to send a reply. It is `NudgeWiringEnv` exactly — the ask
 *  needs the same four — and it is named separately so a reader of the SMS
 *  route is not sent to a nudge to find out what its route requires. */
export type TextCommandEnv = NudgeWiringEnv;

/**
 * How many catalog rows one inbound message may put in front of the judge.
 *
 * A CEILING ON A PROMPT, not a ranking. `MAX_SEARCH_RESULTS` (40) is what the
 * vendor will return; 20 is what one SMS is worth spending, and the rows that
 * survive are the ones the vendor put first — this file does not re-order,
 * score or filter them, because "which of these did they mean" is the
 * question the model below is being asked and answering it twice in two
 * different ways is how two answers come to disagree.
 */
export const TEXT_CATALOG_LIMIT = 20;

/**
 * QUESTION 1 — which of OUR operations is this, if any?
 *
 * ONE QUESTION, ASKED ON ITS OWN. Not a second key in question 2's reply: a
 * field among many loses (measured, seven cases, zero moved). FOUR STATES,
 * because "they were not talking to us", "they were and I cannot pin it" and
 * "nobody answered" are three different facts.
 *
 * THE MENU IS HANDED OVER, NEVER MATCHED. `TEXT_COMMANDS` is rendered into the
 * prompt as the options; nothing in this file compares a member against
 * anything a person typed. Replace every member with an integer and the shape
 * of this call is unchanged.
 */
function commandPrompt(said: string, commands: readonly TextCommand[]): ChatMessage[] {
  const system = [
    "Somebody has texted an assistant that can also connect their own apps to",
    "itself. Decide which ONE of the assistant's app operations this message is",
    "asking for, if any. You are not answering the message.",
    "",
    "Answer with JSON only, in exactly one of these shapes:",
    '{"kind":"command","command":"<one of the options>"}',
    '{"kind":"none"}      the message is not asking for any of them',
    '{"kind":"unclear"}   it might be, and you cannot tell which',
    "",
    "The options, and what each one means:",
    "- list_connected         show me which of my apps are set up",
    "- connect_app            set up one of my apps",
    "- disconnect_app         stop using one of my apps, remove it",
    "- use_work_account       for this app, use my work account",
    "- use_personal_account   for this app, use my personal account",
    "",
    "The exact strings you may answer with:",
    ...commands.map((c) => `- ${c}`),
    "",
    "MOST MESSAGES ARE NONE. This is an ordinary conversation thread and the",
    "assistant does many other things; ordinary talk, questions, plans and",
    "errands are all `none`. Answer `command` only when the message is plainly",
    "asking for one of the five. When in doubt answer `unclear`, never a guess:",
    "a wrong pin takes the message away from everything else that would have",
    "answered it.",
  ].join("\n");
  return [{ role: "system", content: system }, { role: "user", content: said }];
}

/**
 * QUESTION 2 — which app is it about?
 *
 * Asked SEPARATELY, and only when the pinned operation needs an app. The
 * catalog rows are rendered from the list the caller handed over and from
 * nothing else, so the model is choosing from what this owner was actually
 * offered; `text_commands.ts` then re-checks the answer against that same list
 * by identity, so a plausible app it was never shown resolves to nothing.
 */
function matchPrompt(said: string, catalog: ToolkitRow[]): ChatMessage[] {
  const system = [
    "Somebody has texted about one of their own apps. Decide WHICH app, from",
    "the list you are given and only from that list.",
    "",
    "Answer with JSON only, in exactly one of these shapes:",
    '{"kind":"toolkit","slug":"<an id from the list>"}',
    '{"kind":"none"}      they named no app at all',
    '{"kind":"unclear"}   they named one and you cannot tell which of these it is',
    "",
    "Answer `toolkit` only when one row is plainly the one they mean. Two",
    "plausible rows is `unclear`, and an app that is not in the list is",
    "`unclear` as well — never the nearest row. The person will simply be asked",
    "which one they meant, and being asked is far better than the wrong",
    "mailbox being touched.",
  ].join("\n");
  const user = [
    "THE MESSAGE",
    said,
    "",
    "THE APPS, id first",
    ...catalog.map((row) => {
      const name = typeof row?.name === "string" ? row.name : "";
      return `- ${String(row?.slug ?? "")}${name ? ` — ${name}` : ""}`;
    }),
  ].join("\n");
  return [{ role: "system", content: system }, { role: "user", content: user }];
}

/** The model's JSON, or null when there is none to read. Never repaired: a
 *  reply we cannot parse is a MISSING answer, and text_commands.ts reads a
 *  missing answer as `no-verdict`, which acts on nothing. */
function parseVerdict(text: string): unknown {
  const trimmed = String(text ?? "").trim();
  const fenced = trimmed.startsWith("```")
    ? trimmed.replace(/^```[a-zA-Z]*\s*/, "").replace(/```\s*$/, "").trim()
    : trimmed;
  try {
    return JSON.parse(fenced);
  } catch {
    return null;
  }
}

/**
 * THE TWO PORTS text_commands.ts declares, built from the real modules.
 *
 * `said` is the inbound message and it is passed VERBATIM everywhere it goes —
 * to the vendor's search, to both judges. Nothing here trims it to a keyword,
 * tests its length or looks at a single character of it: an empty message is
 * asked about exactly like any other, because a length gate would be
 * `shard_too_thin()` again and that guard is registered tape.
 */
export function textCommandDeps(env: TextCommandEnv, said: string): TextCommandDeps {
  const provider = connectionsFromEnv(env);
  const store = createD1Store(env);
  return {
    async catalog(owner: OwnerId): Promise<ToolkitRow[]> {
      // TWO LOOKUPS, UNIONED, slug-deduplicated, the search first because it
      // is the half that can carry an app they do not yet hold — which is the
      // whole of "connect X".
      const seen = new Map<string, ToolkitRow>();
      try {
        for (const row of await provider.search(said, { limit: TEXT_CATALOG_LIMIT })) {
          if (row && typeof row.slug === "string" && row.slug !== "") seen.set(row.slug, row);
        }
      } catch {
        // A vendor that is down has narrowed the list, not decided anything.
      }
      try {
        for (const row of await store.connectionsForOwner(owner)) {
          const slug = typeof row?.toolkit === "string" ? row.toolkit : "";
          if (slug === "" || seen.has(slug)) continue;
          if (seen.size >= TEXT_CATALOG_LIMIT) break;
          try {
            seen.set(slug, await provider.toolkit(slug as Toolkit));
          } catch {
            // The row is real and the vendor could not describe it. A slug with
            // no name still resolves and still disconnects; `displayName`
            // shows the slug rather than a name nobody wrote.
            seen.set(slug, {
              slug: slug as Toolkit, name: "", logo: null, description: null,
              appUrl: null, scopes: [],
            });
          }
        }
      } catch {
        // Same reasoning: a store that cannot be read has narrowed the list.
      }
      return [...seen.values()];
    },
    judge: {
      async command(phrase: string, commands: readonly TextCommand[]): Promise<unknown> {
        return parseVerdict(await callModel(env, commandPrompt(phrase, commands)));
      },
      async match(phrase: string, catalog: ToolkitRow[]): Promise<unknown> {
        if (catalog.length === 0) return { kind: "none" };
        return parseVerdict(await callModel(env, matchPrompt(phrase, catalog)));
      },
    },
  };
}

// ---------------------------------------------------------------------------
// THE EXECUTOR
// ---------------------------------------------------------------------------

/**
 * What became of a plan. Returned rather than thrown so the SMS route can log
 * one line and always answer the carrier 200: a carrier that retries a text
 * because our reply failed delivers the same message twice.
 */
export interface TextCommandOutcome {
  kind: TextCommandPlan["kind"];
  /** What happened, for the log. Nothing branches on these words. */
  detail: string;
  /** True when a reply actually left the building. */
  replied: boolean;
  /**
   * True when the reply that went out was a QUESTION the owner still has to
   * answer, so the caller can stamp their message `ask` rather than `ignore`.
   *
   * IT IS THE OUTCOME'S AND NOT THE PLAN'S, and that is the point. `plan.kind`
   * knows about `ask_which_app`; it does NOT know that a `choose_account` plan
   * over two indistinguishable accounts also ends in a question. A caller
   * deriving this from the plan kind would get the second one wrong, and would
   * go on getting it wrong for every question added after this one.
   */
  question: boolean;
}

/**
 * EVERY SENTENCE THIS FILE CAN SEND, in one place, so they can be read
 * together and audited together.
 *
 * They are written here rather than by a model on purpose, and the reason is
 * the opposite of the connect page's: these are RECEIPTS for something the
 * person just asked for, not persuasion. "Done" does not need a voice, and a
 * model that writes a receipt can write a receipt for something that did not
 * happen. The one place a model's words would help — the ask that interrupts
 * somebody out of nowhere — is ask.ts, and that is where the writer lives.
 *
 * NO APP IS NAMED HERE. Every `{app}` is filled from the catalog row at run
 * time, through `displayName`, which contains what a vendor feed may put into
 * one of our texts.
 *
 * AUDITED, NOT PROMISED: `textReplySentences` below is exported so the suite
 * can put every one of them through words.ts's own `forbiddenTermIn`.
 */
export const TEXT_REPLY = Object.freeze({
  nothingConnected: "You haven't set up any apps yet. Text me the name of one and I'll send you a link.",
  connectedList: (apps: string) => `You've got ${apps} set up. Text me the name of another one any time.`,
  connectHere: (app: string, link: string) =>
    `Here's your link to set up ${app}. It works for ten minutes.\n${link}`,
  connectFailed: (app: string) =>
    `I couldn't get you a link for ${app} just now. Try me again in a minute.`,
  alreadyConnected: (app: string) => `${app} is already set up. Nothing to do.`,
  disconnectDone: (app: string) => `Done — ${app} is disconnected.`,
  disconnectPartly: (app: string) =>
    `I've removed ${app} from Anticipy. You may also want to remove Anticipy in `
    + `${app}'s own settings.`,
  disconnectNothing: (app: string) => `${app} wasn't set up here, so there was nothing to remove.`,
  disconnectFailed: (app: string) => `I couldn't remove ${app} just now. Try me again in a minute.`,
  accountSet: (app: string, which: string) => `Got it — I'll use your ${which} ${app}.`,
  accountUnknown: (app: string) => `You don't have ${app} set up here yet, so there's no account to pick.`,
  whichApp: "Which app do you mean?",
  // AMBIGUITY ASKS. Two accounts for one app and nothing to tell them apart is
  // the one case where doing something is worse than doing nothing: whichever
  // row we labelled becomes the mailbox the router sends this owner's work
  // from. Settings is where the spec puts the account chooser (page 21, "an
  // account chooser when there are two"), so the question points at a screen
  // that exists rather than asking for a label over SMS that nothing reads.
  whichAccount: (app: string) =>
    `You've got more than one ${app} account here and I'd rather not guess which. `
    + "Pick the one you mean in Settings, under Connected apps.",
} as const);

/** Every sentence the executor can send, rendered once with a fictional app, so
 *  a suite can audit them all against words.ts without knowing their shapes. */
export function textReplySentences(app = "Zeta", link = "https://anticipy.ai/c/x"): string[] {
  return [
    TEXT_REPLY.nothingConnected,
    TEXT_REPLY.connectedList(app),
    TEXT_REPLY.connectHere(app, link),
    TEXT_REPLY.connectFailed(app),
    TEXT_REPLY.alreadyConnected(app),
    TEXT_REPLY.disconnectDone(app),
    TEXT_REPLY.disconnectPartly(app),
    TEXT_REPLY.disconnectNothing(app),
    TEXT_REPLY.disconnectFailed(app),
    TEXT_REPLY.accountSet(app, "work"),
    TEXT_REPLY.accountUnknown(app),
    TEXT_REPLY.whichApp,
    TEXT_REPLY.whichAccount(app),
  ];
}

/**
 * THE LAST GATE BEFORE A REPLY LEAVES. Our own sentence, with a vendor's app
 * name interpolated into it, checked against words.ts's own list.
 *
 * A CEILING ON OUR OWN OUTPUT, not a judgement about anybody: the only outcome
 * of a failure is that we say less. The names in `TEXT_REPLY` are ours and
 * clear the list by construction; the one string that does not come from this
 * repo is the catalog's `name`, and a vendor feed carrying "…Integration" in
 * an app's title would otherwise put a forbidden word in a text we signed.
 * It falls back to a sentence naming no app rather than sending nothing: the
 * person asked a question and silence is the one answer that is always wrong.
 */
function sayable(line: string, fallback: string, link = ""): string {
  // OUR OWN LINK IS LIFTED OUT BEFORE THE SCAN, exactly as the ask judge does
  // it (words.ts: "the vocabulary checks run over the WORDS, with the link
  // lifted out"). This deployment's own base is `api.anticipy.ai`, and `api`
  // is on the list — so a scan over the raw sentence would strip the app's
  // name out of every message that carries a link, forever, because of our own
  // hostname. A token is machine-issued and nobody reads it.
  const words = link === "" ? line : line.split(link).join(" ");
  const term = forbiddenTermIn(words);
  if (term === null) return line;
  console.log(
    `text twin: a reply carried ${JSON.stringify(term)}, which comes from a catalog name — `
      + `sent the app-less form instead. FORBIDDEN_TERMS has ${FORBIDDEN_TERMS.length} entries.`,
  );
  return fallback;
}

/**
 * CARRY OUT ONE PLAN. Every side effect this surface has lives here.
 *
 * IT NEVER THROWS. The caller is a carrier webhook that must answer 200 or be
 * sent the same message again, and a text the person already sent arriving
 * twice is worse than a reply they did not get.
 *
 * IT READS THE DATABASE BEFORE IT ANSWERS. The plan is what the person ASKED
 * for, not what is possible — text_commands.ts reads no table and says so — so
 * "Done, disconnected" over an app that was never set up, and a fresh link for
 * one that already is, are both this function's to avoid.
 */
export async function runTextCommandPlan(
  plan: TextCommandPlan,
  env: TextCommandEnv,
): Promise<TextCommandOutcome> {
  const done = (detail: string, replied = false): TextCommandOutcome =>
    ({ kind: plan.kind, detail, replied, question: false });
  if (plan.kind === "not_for_us") return done(`left alone (${plan.because})`);

  const store = createD1Store(env);
  const owner = plan.owner;

  // WHERE THE REPLY GOES: this owner's own number, from their own row, by the
  // same reader the ask uses. NEVER the `From` of the inbound message — an
  // owner is resolved from a phone number by `landInboundText` and the reply
  // belongs to the account, not to whatever handset happened to send it.
  let to: string | null = null;
  try {
    to = await ownerPhone(env)(owner);
  } catch {
    to = null;
  }
  if (!to) return done("this owner has no number on file, so there was nowhere to reply");

  /** `asks` marks a reply that LEAVES SOMETHING OPEN — a question the owner
   *  still has to answer. It is stated at each call site rather than inferred
   *  from the sentence, because inferring it would mean reading our own copy
   *  for a question mark, and a rule like that dies the first time a question
   *  is phrased without one. */
  const reply = async (line: string, asks = false): Promise<TextCommandOutcome> => {
    const sent = await sendText(env, to as string, line, { tag: "text twin" });
    return { kind: plan.kind, detail: sent.ok ? "replied" : `reply failed: ${sent.error}`,
             replied: sent.ok, question: asks && sent.ok };
  };

  try {
    switch (plan.kind) {
      case "ask_which_app":
        // THE ONE PLAN WHOSE WHOLE PURPOSE IS TO BE ANSWERED.
        return await reply(TEXT_REPLY.whichApp, true);

      case "list_connections": {
        const rows = (await store.connectionsForOwner(owner))
          .filter((r) => r.status === "connected");
        if (rows.length === 0) return await reply(TEXT_REPLY.nothingConnected);
        // The NAMES come from the catalog at run time; a row the vendor cannot
        // describe shows its own slug. No app is named in this file.
        const provider = connectionsFromEnv(env);
        const named: string[] = [];
        for (const row of rows) {
          let meta: ToolkitRow | null = null;
          try { meta = await provider.toolkit(row.toolkit); } catch { meta = null; }
          const name = displayName(meta, row.toolkit);
          named.push(row.alias ? `${name} (${row.alias})` : name);
        }
        const list = named.length === 1 ? named[0]
          : named.slice(0, -1).join(", ") + " and " + named[named.length - 1];
        return await reply(sayable(TEXT_REPLY.connectedList(list),
                                   TEXT_REPLY.connectedList(`${named.length} apps`)));
      }

      case "connect": {
        const held = (await store.connectionsForOwner(owner))
          .some((r) => r.toolkit === plan.toolkit && r.status === "connected");
        if (held) {
          return await reply(sayable(TEXT_REPLY.alreadyConnected(plan.appName),
                                     TEXT_REPLY.alreadyConnected("that app")));
        }
        let minted;
        try {
          minted = await mintConnectLink(env, owner, plan.toolkit, null);
        } catch (err) {
          console.log(`text twin: could not mint a link — ${String(err)}`);
          return await reply(sayable(TEXT_REPLY.connectFailed(plan.appName),
                                     TEXT_REPLY.connectFailed("that app")));
        }
        // OUR LINK ONLY. `mintConnectLink` builds it on this deployment's own
        // base; the vendor's URL is fetched at REDEEM time, inside /c/, and
        // never reaches a phone.
        const out = await reply(sayable(TEXT_REPLY.connectHere(plan.appName, minted.url),
                                        TEXT_REPLY.connectHere("that app", minted.url),
                                        minted.url));
        // AND WRITE IT DOWN, but only once it actually went. See
        // `recordSolicitedAsk` for which way round the failure has to fail.
        if (out.replied) await recordSolicitedAsk(store, owner, plan.toolkit);
        return out;
      }

      case "disconnect": {
        const rows = (await store.connectionsForOwner(owner))
          .filter((r) => r.toolkit === plan.toolkit && r.status !== "disconnected");
        if (rows.length === 0) {
          return await reply(sayable(TEXT_REPLY.disconnectNothing(plan.appName),
                                     TEXT_REPLY.disconnectNothing("that app")));
        }
        const provider = connectionsFromEnv(env);
        let anyRevokeUnavailable = false;
        for (const row of rows) {
          // REVOKE THEN DELETE, in that order and never the other way: a row
          // deleted first is a token left live at the far end with nothing left
          // pointing at it. The vendor call comes first, our row goes second.
          const result = await provider.disconnect(owner, row.connected_account_id);
          if (result.revokeUnavailable) anyRevokeUnavailable = true;
          await store.deleteConnection(owner, row.connected_account_id);
        }
        // "Access was revoked" is a claim about somebody else's system, and
        // about 5% of accounts cannot be revoked programmatically. When the
        // vendor says it could not, the reply says what actually happened.
        const line = anyRevokeUnavailable
          ? sayable(TEXT_REPLY.disconnectPartly(plan.appName),
                    TEXT_REPLY.disconnectPartly("that app"))
          : sayable(TEXT_REPLY.disconnectDone(plan.appName),
                    TEXT_REPLY.disconnectDone("that app"));
        return await reply(line);
      }

      case "choose_account": {
        const rows = (await store.connectionsForOwner(owner))
          .filter((r) => r.toolkit === plan.toolkit && r.status === "connected");
        if (rows.length === 0) {
          return await reply(sayable(TEXT_REPLY.accountUnknown(plan.appName),
                                     TEXT_REPLY.accountUnknown("that app")));
        }
        // THE ANSWER IS STORED AGAINST THE ACCOUNT IT NAMES, and against
        // nothing else. The spec also stores it "against the context that
        // caused it" (page 42); which context is open is a fact this Worker
        // does not hold, so that half belongs to the caller that does, and
        // this writes the durable half rather than inventing the other.
        //
        // AMBIGUITY REFUSES AND ASKS. This used to end `?? rows[0]`, which
        // labelled whichever row D1 returned first when an owner held two
        // accounts for one app and neither carried the alias — and the row
        // that wins is the mailbox the router then sends this owner's work
        // from. Row order is not a fact about anybody. The spec answers this
        // case by asking ("work or personal for this?", page 23), never by
        // picking, and `nudgeMomentFor` above already refuses the same way on
        // the same question.
        //
        // ONE account is not ambiguous: "use my work <app>" over a single
        // connection is the owner telling us that this one is the work one.
        // Two rows carrying the SAME alias is ambiguous again — relabelling
        // one of them changes nothing about which the router picks.
        const named = rows.filter((r) => r.alias === plan.alias);
        const wanted = named.length === 1 ? named[0] : (rows.length === 1 ? rows[0] : null);
        if (wanted === null) {
          return await reply(sayable(TEXT_REPLY.whichAccount(plan.appName),
                                     TEXT_REPLY.whichAccount("that app")),
                             true);
        }
        await store.putConnection({ ...wanted, alias: plan.alias });
        return await reply(sayable(TEXT_REPLY.accountSet(plan.appName, plan.alias),
                                   TEXT_REPLY.accountSet("that app", plan.alias)));
      }
    }
  } catch (err) {
    console.log(`text twin: ${plan.kind} failed — ${String(err)}`);
    return done(`failed: ${String((err as Error)?.message ?? err)}`);
  }
  return done("no branch handled the plan, so nothing was done");
}

/**
 * WRITE DOWN A LINK THE OWNER ASKED FOR — the `connect_nudges` row every other
 * connect ask writes, written for this one too.
 *
 * THE DEFECT THIS CLOSES, measured 2026-09-06. The twin minted a link, texted
 * it, and wrote NOTHING. `sendConnectAsk` reads `connect_nudges.sent_at` for
 * the spec's global cap ("one connect ask per user per 7 days across all
 * apps", page 24), so somebody who texted "connect <app>" at 9am and got a
 * link could be interrupted by the sweep about a DIFFERENT app at 10am. The
 * same row is what the 72-hour soft-no and the decline ladder read, so an
 * unwritten one is invisible to all three.
 *
 * DOES A SOLICITED LINK SPEND THE WEEKLY BUDGET? YES, AND HERE IS WHY — the
 * question is a real one, because the spec's cap is written about asks WE
 * start, and a link somebody asked for is not an interruption.
 *
 *   It cannot cost this owner their own request. The twin reads no policy at
 *   all: `runTextCommandPlan` mints on demand, at any decline level, which is
 *   exactly what page 24 promises at level 3 — "stop asking; the user must
 *   bring it up ('connect <app>') or Settings". Nothing written here can ever
 *   become a reason to refuse somebody who asked. That is the asymmetry the
 *   decision turns on.
 *
 *   What it CAN do is keep the sweep quiet for a week. And that is the cap
 *   doing its job rather than misfiring: the budget belongs to the PERSON, not
 *   to the sweep, and "you just dealt with connecting one app, so here is an
 *   unprompted pitch for a second" is precisely the pestering the cap exists
 *   to stop. The cost of being wrong this way is a week of proactive silence
 *   for somebody who has just demonstrated they know how to ask. The cost of
 *   being wrong the other way is a second text nobody wanted.
 *
 * AND IT NEVER WRITES `state: 'asked'`. THIS IS THE OTHER HALF OF THE ROW AND
 * IT IS A DIFFERENT SENTENCE — the round-2 finding against the paragraph
 * above, driven 2026-09-06.
 *
 *   `asked` does not mean "a link is out". It means "WE put a connect link in
 *   front of this person and are waiting for an answer we started", and
 *   `maturedBySilence` reads exactly that: 72 hours of quiet on an `asked` row
 *   is a soft no, level 1, and the next real moment snoozed a fortnight. So
 *   somebody who TEXTS "connect <app>", is handed the link, and does not
 *   finish the errand that week was recorded as having declined it.
 *
 *   The 72-hour rule's own reason (page 24) is "so we do not re-send into a
 *   void". A person who texted us is not a void. Silence on a link we pushed
 *   and silence on an errand somebody started are two different facts, and one
 *   column cannot carry both — so the state a solicited link writes is the one
 *   that is TRUE of it: whatever the row already said, with an outstanding
 *   push of ours cleared, because a person who has just asked for the link has
 *   answered that push and no soft no is owed.
 *
 *   `never_asked` is not a lie in that row: we have not asked them. `sent_at`
 *   and `user_named_it` beside it say a link went, and who wanted it.
 *
 * WHICH SENDS SPEND THE 7-DAY BUDGET, plainly, because the next reader will
 * need it and a column cannot say it: EVERY connect link that reaches this
 * owner's phone spends it, whoever asked for the link. WHICH SENDS ENTER THE
 * DECLINE LADDER: only the ones the product pushed.
 *
 *   The two are not the same question. The cap is a promise about a person's
 *   attention — one connect decision a week is one connect decision a week,
 *   and "you just dealt with connecting one app, so here is an unprompted
 *   pitch for a second" is precisely the pestering it exists to stop. The
 *   ladder is a promise about our welcome, and a link somebody requested is
 *   evidence FOR us, not against.
 *
 *   THE COST OF THE FIRST HALF, named rather than discovered later: for one
 *   week after somebody texts "connect <app>", even a laptop-closed moment —
 *   score 1.0, the strongest trigger in the product — is held for every other
 *   app. The task still queues and still runs when their Mac wakes; what they
 *   lose is the offer. That is the same week any pushed ask would have spent,
 *   and it is the price of the cap being about them rather than about us. It
 *   is pinned in test/connections-wiring.test.ts section 10, so changing this
 *   mind means changing that check on purpose.
 *
 *   It can never cost this owner their own request: the twin reads no policy
 *   at all — `runTextCommandPlan` mints on demand, at any decline level, which
 *   is exactly what page 24 promises at level 3 ("stop asking; the user must
 *   bring it up"). Nothing written here can become a reason to refuse somebody
 *   who asked.
 *
 * WHAT IT PRESERVES. `maturedBySilence` first, exactly as `sendConnectAsk`
 * does it, so a decline the previous silence earned is not erased by the
 * re-ask; the level and the snooze ride through untouched.
 *
 * AND WHAT IT DOES NOT OVERWRITE: `needs_reconnect`, and now `declined` and
 * `connected` too. `needs_reconnect` is not a rung on the ladder — it is a
 * live connection that broke — and stamping it `asked` would silently retire
 * the weekly reconnect cadence (page 24, "one gentle ask, then weekly max").
 * Keeping the state while stamping `sent_at` is what tells `shouldAsk` the
 * reconnect WAS raised just now, which is true. `declined` is the word
 * routes/connect.ts `recordSkip` reads to know a tap it has already counted
 * ("a refresh, a double tap or a retried POST must not walk somebody from ask
 * me in a fortnight to never ask me again"); rewriting it here would hand that
 * guard a row it cannot recognise. `connected` says an app is live, and a
 * second link for a second account does not un-connect the first.
 *
 * THE SAME APP IS STILL QUIET AFTERWARDS, and by the cap rather than by the
 * state: the `sent_at` this writes is in `nudgesForOwner`, so `shouldAsk`
 * holds this app for the same seven days it holds every other one. Losing the
 * `asked` branch's "an ask sent 4h ago is still open" costs nothing, because
 * the wider promise already covers it.
 *
 * `user_named_it` is the honest trigger: they named the app, in a text
 * (page 22, "the user says it ... in transcripts or texts"). It is also the
 * one enum value that keeps the level-1 laptop-closed override available,
 * because that override is spent by a previous ask whose trigger WAS
 * `laptop_closed`.
 *
 * IT IS CALLED AFTER THE SEND, WHICH IS THE OPPOSITE OF `sendConnectAsk`, and
 * the reason is that the failure directions are mirror images. A sweep ask
 * that goes unrecorded is RE-SENT on the next tick, so the row is taken as a
 * lease first. A solicited link that goes unrecorded costs at most one
 * proactive text this week — while a row written before a send that then
 * failed would hold a decline against somebody for a link they never got.
 *
 * IT NEVER THROWS. The person has their link; a bookkeeping row that would not
 * write must not turn their answered request into a failure.
 */
async function recordSolicitedAsk(
  store: ConnectionsStore,
  owner: OwnerId,
  toolkit: Toolkit,
): Promise<void> {
  const now = Date.now();
  try {
    const found = await store.readNudge(owner, toolkit);
    const before = maturedBySilence(found ?? freshNudge(owner, toolkit), now);
    await store.putNudge({
      ...before,
      // NEVER `asked`. An outstanding push of ours has just been answered — by
      // the owner asking for the link — so it stops being outstanding, and
      // nothing else about the row is this write's to rewrite.
      state: before.state === "asked" ? "never_asked" : before.state,
      trigger: "user_named_it",
      sent_at: now,
      acted_at: null,
      channel: "sms",
    });
  } catch (err) {
    console.log(
      `text twin: sent ${owner} a connect link and could not record it, so the 7-day cap `
        + `and the reconnect cadence cannot see it and the sweep may interrupt them again `
        + `this week — ${String(err)}`,
    );
  }
}

/**
 * ONE INBOUND MESSAGE, END TO END: decide, then carry it out.
 *
 * The SMS routes call exactly this, so the two carriers cannot drift; the
 * split between deciding and doing is preserved above it, where it is testable.
 * A message nobody claimed costs one model call and returns without a reply,
 * which is what `not_for_us` means and why it is not an error.
 */
export async function handleInboundText(
  env: TextCommandEnv,
  owner: string,
  said: string,
  eventId = "",
): Promise<TextCommandOutcome> {
  // THE SAME FOUR PIECES OF CONFIG THE ASK NEEDS, and for the same four
  // reasons: no DB is no store, no vendor key is no catalog, no model key is
  // no judge, and no messaging provider is nowhere to reply. Asked BEFORE the
  // model call rather than after, because a Worker missing one of them would
  // otherwise spend a model call on every inbound text in order to discover it
  // cannot answer any of them.
  const missing = missingNudgeConfig(env);
  if (missing !== null) {
    console.log(
      `text twin: not wired on this Worker — ${missing} is unset, so nobody's text `
        + "about their apps will be understood. Set it and redeploy.",
    );
    return { kind: "not_for_us", detail: `not wired: ${missing}`, replied: false, question: false };
  }

  let plan: TextCommandPlan;
  try {
    plan = await planTextCommand(ownerId(String(owner ?? "")), said, textCommandDeps(env, said));
  } catch (err) {
    // A bad owner id is OUR wiring being wrong, and planTextCommand throws on
    // one rather than acting. It must not cost the carrier a 500.
    console.log(`text twin: could not plan this message — ${String(err)}`);
    return {
      kind: "not_for_us", detail: `not planned: ${String(err)}`, replied: false, question: false,
    };
  }
  const outcome = await runTextCommandPlan(plan, env);
  // A QUESTION LEFT OPEN IS NOT A LINE THAT WAS HANDLED. See `claimEvent` for
  // why both of these claim the row and only one of them says `ignore`.
  if (outcome.replied) await claimEvent(env, eventId, outcome.question ? "ask" : "ignore");
  console.log(`text twin: ${outcome.kind} — ${outcome.detail}`);
  return outcome;
}

/**
 * MARK THE MESSAGE ANSWERED, so the person is not answered twice.
 *
 * WHY THIS IS NEEDED AT ALL. `landInboundText` writes every inbound text as an
 * `events` row and the brain picks those up with `kind="sms_reply" &&
 * decision=""` (brain/worker.py `fetch_unprocessed`). Without this line, a
 * message the twin has just answered with a connect link is ALSO handed to the
 * brain, which knows nothing about connections and will answer it again in its
 * own words. Two replies to one text, from one number, is the product looking
 * broken in the one place it is most visible.
 *
 * ONLY WHEN A REPLY ACTUALLY WENT. A plan that was refused, held or failed
 * leaves the row untouched, so the brain still gets its go — losing somebody's
 * message is far worse than answering it twice, and this must never be able to
 * swallow one silently.
 *
 * CONDITIONAL ON `decision = ''`, so it can never overwrite a decision the
 * brain has already made about the same row. It is best effort and says so: the
 * twin runs on `waitUntil` after the carrier has been answered, and the brain
 * polls on its own clock, so a row it has already claimed is a row this update
 * changes nothing about. The failure mode of losing that race is one duplicate
 * answer, which is the direction to fail in.
 *
 * WHICH WORD, AND WHY IT IS NOT ALWAYS `'ignore'`. Both are the brain's own
 * vocabulary for this column (schema.sql: ignore|act|ask), and both keep the
 * row out of `fetch_unprocessed`, which polls `decision=""`. They are not
 * interchangeable:
 *
 *   `'ignore'` says nothing further is needed for this line, because it has
 *   already been handled. True of a link sent, a list read, a disconnection
 *   done.
 *
 *   `'ask'` says the product asked this person something and is waiting for
 *   the answer — brain/worker.py's own use of the word (`post_event(...,
 *   decision="ask")`). True of `ask_which_app`, whose entire purpose is to be
 *   answered, and of the account question a `choose_account` plan falls back
 *   to when two accounts cannot be told apart.
 *
 * THE DEFECT THIS CLOSES, found 2026-09-06: `if (outcome.replied) await
 * claimEvent(...)` stamped `ignore` for EVERY reply, so the one message the
 * twin had deliberately left open was the one it recorded as finished. The
 * row said handled while the product stood there waiting.
 */
async function claimEvent(
  env: TextCommandEnv, eventId: string, decision: "ignore" | "ask",
): Promise<void> {
  const id = typeof eventId === "string" ? eventId.trim() : "";
  if (id === "") {
    console.log(
      "text twin: answered a message with no event id, so the brain may answer it too. "
        + "The caller should pass `landed.id` from landInboundText.",
    );
    return;
  }
  try {
    // BOUND, not interpolated, even though the argument's type is a closed
    // pair of literals: the type is erased before this runs, and a column
    // holding a caller's string is how the next reader learns that SQL in this
    // file takes text from its callers.
    const res = await env.DB.prepare(
      `UPDATE "events" SET "decision" = ?2 WHERE "id" = ?1 AND "decision" = ''`,
    ).bind(id, decision).run();
    if ((res.meta?.changes ?? 0) === 0) {
      console.log(`text twin: event ${id} already carried a decision; it may be answered twice`);
    }
  } catch (err) {
    console.log(`text twin: could not mark event ${id} answered — ${String(err)}`);
  }
}

/** The menu, re-exported so a caller can prove the prompt above offers exactly
 *  the members text_commands.ts declares without importing two modules. */
export { TEXT_COMMANDS };
