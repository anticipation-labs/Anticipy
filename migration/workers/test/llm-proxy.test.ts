/**
 * Runs with no dependencies, no network and no D1:
 *
 *   node --experimental-strip-types migration/workers/test/llm-proxy.test.ts
 *
 * The pure half of src/llm.ts, pinned to backend/pb_hooks/agent_key.pb.js and
 * to the extension. The wire half — what actually reaches a provider, the
 * 429, the audit rows — is migration/spec/contract_tests.py
 * (TestAgentLlmProxy) run by scripts/llm_contract_local.sh against a real
 * workerd and a fake provider.
 *
 * TWO NUMBERS AND ONE STRING ARE READ OUT OF THE EXTENSION'S SOURCE rather
 * than typed here: MODEL_REPLY_FLOOR, and CEILING_429_MARK. The extension
 * floors every request at the first and stops retrying a 429 only when the
 * body carries the second. If either side moves without the other, the wire
 * carries a number the measured floor forbids, or the extension retries three
 * times against a ceiling that has already tripped. A test that typed the
 * values would pass while the two files disagreed.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  REPLY_FLOOR, REPLY_CEILING, CEILING_429_ERROR, HOURLY_CALL_CEILING,
  UPSTREAM_TIMEOUT_MS, GOOGLE_BASE, OPENROUTER_BASE,
  boundMaxTokens, wantsJsonObject, enabledModels, providerKeys, providerBase,
  isGemini3, geminiGenerationConfig, toGeminiContents, translateGemini,
  taskTagOf, redactMessages, redactProviderPayload,
} from "../src/llm.ts";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..", "..");
const agentLoop = readFileSync(join(repoRoot, "extension", "agent_loop.js"), "utf8");

let failures = 0;
function check(what: string, fn: () => void | Promise<void>): Promise<void> {
  return Promise.resolve().then(fn).catch((err) => {
    failures++;
    console.error("FAIL " + what + "\n     " + (err as Error).message);
  });
}

await check("REPLY_FLOOR is the extension's MODEL_REPLY_FLOOR, read from its source", () => {
  const m = agentLoop.match(/export const MODEL_REPLY_FLOOR = (\d+);/);
  assert.ok(m, "extension/agent_loop.js no longer exports MODEL_REPLY_FLOOR");
  assert.equal(REPLY_FLOOR, Number(m![1]));
  assert.equal(REPLY_FLOOR, 512, "research/evals/login-wall-2026-09-05/FINDINGS.md measured 512");
});

await check("the 429 text is the extension's CEILING_429_MARK, byte for byte", () => {
  const m = agentLoop.match(/const CEILING_429_MARK = "([^"]+)";/);
  assert.ok(m, "extension/agent_loop.js no longer defines CEILING_429_MARK");
  assert.equal(CEILING_429_ERROR, m![1]);
});

await check("the hook's constants: 400 an hour, 95 s upstream, 4096 ceiling", () => {
  assert.equal(HOURLY_CALL_CEILING, 400);
  assert.equal(UPSTREAM_TIMEOUT_MS, 95_000);
  assert.equal(REPLY_CEILING, 4096);
});

// --- agent_key.pb.js:239-241 -----------------------------------------------
await check("max_tokens is floored at 512 and capped at 4096, the hook's arithmetic", () => {
  assert.equal(boundMaxTokens(8), 512, "a one-token judge asks for 8");
  assert.equal(boundMaxTokens(64), 512, "the old floor is below the new one");
  assert.equal(boundMaxTokens(511), 512);
  assert.equal(boundMaxTokens(512), 512);
  assert.equal(boundMaxTokens(1000), 1000);
  assert.equal(boundMaxTokens(1000.9), 1000, "floor(), not round()");
  assert.equal(boundMaxTokens(4096), 4096);
  assert.equal(boundMaxTokens(9000), 4096);
  assert.equal(boundMaxTokens(undefined), 512, "omitted → the floor, never the provider's 65k");
  assert.equal(boundMaxTokens(0), 512, "0 is falsy in the hook and becomes the floor");
  assert.equal(boundMaxTokens("abc"), 512);
  assert.equal(boundMaxTokens("2000"), 2000, "Number() coerces a string, as the hook did");
  assert.equal(boundMaxTokens(Infinity), 512, "isFinite fails → the floor");
  assert.equal(boundMaxTokens(-5), 512);
});

// --- agent_key.pb.js:243-245 -----------------------------------------------
await check("only response_format {type:'json_object'} passes through", () => {
  assert.equal(wantsJsonObject({ type: "json_object" }), true);
  assert.equal(wantsJsonObject({ type: "json_object", schema: {} }), true);
  assert.equal(wantsJsonObject({ type: "text" }), false);
  assert.equal(wantsJsonObject({ type: "json_schema" }), false);
  assert.equal(wantsJsonObject("json_object"), false);
  assert.equal(wantsJsonObject(undefined), false);
  assert.equal(wantsJsonObject(null), false);
});

// --- agent_key.pb.js:202-208 -----------------------------------------------
await check("the model allowlist defaults are the hook's", () => {
  assert.deepEqual(enabledModels({}), {
    browser: "anthropic/claude-sonnet-4.6", vision: "google/gemini-2.5-flash",
  });
  assert.deepEqual(enabledModels({ ANTICIPY_BROWSER_MODEL: "google/gemini-3.1-pro-preview" }), {
    browser: "google/gemini-3.1-pro-preview", vision: "google/gemini-2.5-flash",
  });
});

await check("GEMINI_API_KEY is the Google key; GOOGLE_API_KEY is accepted as its alias", () => {
  assert.deepEqual(providerKeys({}), { gemini: "", openrouter: "" });
  assert.deepEqual(providerKeys({ GEMINI_API_KEY: "g" }), { gemini: "g", openrouter: "" });
  assert.deepEqual(providerKeys({ GOOGLE_API_KEY: "a" }), { gemini: "a", openrouter: "" });
  assert.deepEqual(providerKeys({ GEMINI_API_KEY: "g", GOOGLE_API_KEY: "a" }).gemini, "g",
    "the hook's name wins when both are bound");
  assert.deepEqual(providerKeys({ OPENROUTER_API_KEY: "o" }), { gemini: "", openrouter: "o" });
});

// --- LLM_PROVIDER_BASE -----------------------------------------------------
await check("LLM_PROVIDER_BASE is honoured for loopback only; anything else keeps the real host", () => {
  assert.equal(providerBase({}, GOOGLE_BASE), GOOGLE_BASE);
  assert.equal(providerBase({ LLM_PROVIDER_BASE: "" }, OPENROUTER_BASE), OPENROUTER_BASE);
  assert.equal(providerBase({ LLM_PROVIDER_BASE: "http://127.0.0.1:9797/" }, GOOGLE_BASE),
    "http://127.0.0.1:9797", "trailing slash trimmed so the path concatenates");
  assert.equal(providerBase({ LLM_PROVIDER_BASE: "http://localhost:9797" }, GOOGLE_BASE),
    "http://localhost:9797");
  assert.equal(providerBase({ LLM_PROVIDER_BASE: "http://[::1]:9797" }, GOOGLE_BASE),
    "http://[::1]:9797");
  assert.equal(providerBase({ LLM_PROVIDER_BASE: "https://evil.example" }, GOOGLE_BASE),
    GOOGLE_BASE, "a vendor key must never be sent to a stranger's host");
  assert.equal(providerBase({ LLM_PROVIDER_BASE: "http://127.0.0.1.evil.example" }, GOOGLE_BASE),
    GOOGLE_BASE, "a hostname that merely starts with the loopback digits");
  assert.equal(providerBase({ LLM_PROVIDER_BASE: "not a url" }, OPENROUTER_BASE), OPENROUTER_BASE);
});

// --- agent_key.pb.js:298-320 -----------------------------------------------
await check("Gemini 3 gets thinkingLevel low and keeps its temperature; 2.x gets budget 0 and temperature 0", () => {
  assert.equal(isGemini3("gemini-3.1-pro-preview"), true);
  assert.equal(isGemini3("gemini-3-flash"), true);
  assert.equal(isGemini3("Gemini-3.0-pro"), true);
  assert.equal(isGemini3("gemini-2.5-flash"), false);
  assert.equal(isGemini3("gemini-30-x"), false, "the separator is part of the check");

  assert.deepEqual(geminiGenerationConfig("gemini-3.1-pro-preview", 512, false), {
    maxOutputTokens: 512, thinkingConfig: { thinkingLevel: "low" },
  });
  assert.deepEqual(geminiGenerationConfig("gemini-2.5-flash", 512, false), {
    maxOutputTokens: 512, thinkingConfig: { thinkingBudget: 0 }, temperature: 0,
  });
  assert.deepEqual(geminiGenerationConfig("gemini-3.1-pro-preview", 4096, true), {
    maxOutputTokens: 4096, thinkingConfig: { thinkingLevel: "low" },
    responseMimeType: "application/json",
  });
});

// --- agent_key.pb.js:271-294 -----------------------------------------------
await check("chat messages become Gemini contents: system joined, assistant → model, data URLs inlined", () => {
  const out = toGeminiContents([
    { role: "system", content: "A" },
    { role: "system", content: "B" },
    { role: "system", content: [{ type: "text", text: "ignored: system parts are not joined" }] },
    { role: "user", content: "hello" },
    { role: "assistant", content: "hi" },
    { role: "user", content: [
      { type: "text", text: "look" },
      { type: "image_url", image_url: { url: "data:image/png;base64,AAAA" } },
      { type: "image_url", image_url: { url: "https://example.com/x.png" } },
      { type: "other" }, null,
    ] },
    { role: "user", content: [] },
    { role: "user", content: 42 },
  ]);
  assert.equal(out.systemText, "A\n\nB");
  assert.deepEqual(out.contents, [
    { role: "user", parts: [{ text: "hello" }] },
    { role: "model", parts: [{ text: "hi" }] },
    { role: "user", parts: [{ text: "look" }, { inlineData: { mimeType: "image/png", data: "AAAA" } }] },
  ]);
  assert.deepEqual(toGeminiContents([{ role: "system", content: "only" }]).contents, [],
    "a system-only prompt has no usable content → the hook's 400");
});

// --- agent_key.pb.js:359-380 -----------------------------------------------
await check("Gemini's answer is translated to chat-completions shape; no text → null (502)", () => {
  assert.equal(translateGemini({}, "gemini-2.5-flash"), null);
  assert.equal(translateGemini({ candidates: [] }, "gemini-2.5-flash"), null);
  assert.equal(translateGemini({ candidates: [{ content: { parts: [{ text: "" }] } }] }, "m"), null);
  assert.equal(translateGemini(null, "m"), null);
  assert.equal(translateGemini("nope", "m"), null);

  const plain = translateGemini({ candidates: [{ content: { parts: [{ text: "a" }, { text: "b" }] } }] },
    "gemini-2.5-flash");
  assert.deepEqual(plain, {
    choices: [{ message: { content: "ab" } }], model: "gemini-2.5-flash", provider: "google",
  }, "exactly the hook's shape when Google reports nothing more");

  const rich = translateGemini({
    candidates: [{ content: { parts: [{ text: "{\"ok\":true}" }] }, finishReason: "MAX_TOKENS" }],
    usageMetadata: { promptTokenCount: 10, candidatesTokenCount: 5, totalTokenCount: 15 },
  }, "gemini-3.1-pro-preview") as Record<string, unknown>;
  assert.deepEqual(rich.choices, [{ message: { content: "{\"ok\":true}" }, finish_reason: "length" }],
    "MAX_TOKENS → length, so a reader can see a cut-off verdict");
  assert.deepEqual(rich.usage, { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 });
  assert.equal(rich.provider, "google");
  const stop = translateGemini({ candidates: [{ content: { parts: [{ text: "x" }] }, finishReason: "STOP" }] }, "m");
  assert.equal((stop!.choices as Array<Record<string, unknown>>)[0].finish_reason, "stop");
});

// --- agent_key.pb.js:113-117 -----------------------------------------------
await check("the audit tag is found inside the serialized messages, or not at all", () => {
  assert.equal(taskTagOf(JSON.stringify([{ role: "user", content: "x [AUDIT:run-1:task.2] y" }])), "run-1:task.2");
  assert.equal(taskTagOf(JSON.stringify([{ role: "user", content: "[AUDIT:ab]" }])), "", "under 3 chars");
  assert.equal(taskTagOf(JSON.stringify([{ role: "user", content: "[AUDIT:has space]" }])), "");
  assert.equal(taskTagOf(JSON.stringify([{ role: "user", content: "plain" }])), "");
});

// --- agent_key.pb.js:69-112 ------------------------------------------------
await check("image bytes are redacted before the ledger sees them; text is untouched", async () => {
  const url = "data:image/png;base64," + "Q".repeat(400);
  const [text, img] = await redactMessages([
    { role: "user", content: "keep me" },
    { role: "user", content: [{ type: "text", text: "t" }, { type: "image_url", image_url: { url } }] },
  ]);
  assert.equal(text.content, "keep me");
  const parts = img.content as Array<Record<string, unknown>>;
  assert.deepEqual(parts[0], { type: "text", text: "t" });
  const redacted = parts[1].image_url as Record<string, unknown>;
  assert.equal(redacted.url, "data:image/png;base64,[IMAGE_BYTES_REDACTED]");
  assert.equal(redacted.encoded_chars, 400);
  assert.equal(redacted.approximate_bytes, 300);
  assert.match(String(redacted.sha256), /^[0-9a-f]{64}$/);
  assert.ok(!JSON.stringify(parts).includes("Q".repeat(50)), "no run of the bytes survives");

  const gem = await redactProviderPayload({
    contents: [{ role: "user", parts: [{ text: "t" }, { inlineData: { mimeType: "image/png", data: "Q".repeat(40) } }] }],
    generationConfig: { maxOutputTokens: 512 },
  }) as Record<string, unknown>;
  const gemParts = (gem.contents as Array<Record<string, unknown>>)[0].parts as Array<Record<string, unknown>>;
  assert.deepEqual(gemParts[0], { text: "t" });
  const inline = gemParts[1].inlineData as Record<string, unknown>;
  assert.equal(inline.data, "[IMAGE_BYTES_REDACTED]");
  assert.equal(inline.encoded_chars, 40);
  assert.equal(inline.approximate_bytes, 30);
  assert.deepEqual(gem.generationConfig, { maxOutputTokens: 512 }, "non-image branches copied intact");
});

if (failures) {
  console.error(`llm-proxy: ${failures} failing`);
  process.exit(1);
}
console.log("llm-proxy: all cases pass");
