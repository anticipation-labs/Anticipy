// A scripted OpenRouter-shaped provider on loopback, reached only through the
// local Worker's test-only LLM_PROVIDER_BASE. It is the same "model" the
// offline suites and proof/audit/check_browser_frame_clicks.mjs script: audit
// prompts are verified, a page map naming the fixture button is answered with
// a click on that button's MAP index, the next step is "done". Nothing here
// reads meaning off the owner's words (HARNESS-LAWS Law 1): it is a fixture
// answering a fixture, and every request is logged by shape only.
//
//   node proof/audit/installed_extension/fake_provider.mjs --port 8796 --log FILE
import { createServer } from "node:http";
import { appendFileSync } from "node:fs";

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };
const PORT = Number(arg("port", "8796"));
const LOG = arg("log", "");
const LABEL = new RegExp(arg("label", "Reveal slots"));
const clicked = new Map();           // per conversation key: how many clicks answered
const log = (row) => { if (LOG) appendFileSync(LOG, JSON.stringify({ at: new Date().toISOString(), ...row }) + "\n"); };

function decide(body) {
  const messages = Array.isArray(body.messages) ? body.messages : [];
  const text = messages.map((m) => (typeof m.content === "string" ? m.content : JSON.stringify(m.content))).join("\n");
  if (messages.some((m) => typeof m.content === "string" && m.content.startsWith("You audit"))) return { verified: true };
  const key = String(body.user || "") + ":" + (text.match(/Goal: ([^\n]{0,80})/)?.[1] || "");
  const m = text.match(new RegExp(`\\[(\\d+)\\] <[a-z-]+> ${LABEL.source}`, "m"));
  if (!m) return { action: "wait" };
  const n = clicked.get(key) || 0;
  if (n >= 1) return { action: "done", result: "Revealed it." };
  clicked.set(key, n + 1);
  return { action: "click", index: Number(m[1]) };
}

const server = createServer((req, res) => {
  // One task at a time: the harness resets the click ledger before each job,
  // because the model sees no job id and the goal wording is the only key.
  if (req.method === "POST" && req.url === "/__reset") { clicked.clear(); res.writeHead(204); res.end(); return; }
  if (req.method !== "POST" || !req.url.startsWith("/api/v1/chat/completions")) {
    res.writeHead(404); res.end(); return;
  }
  let raw = "";
  req.on("data", (c) => { raw += c; if (raw.length > 4_000_000) req.destroy(); });
  req.on("end", () => {
    let body; try { body = JSON.parse(raw); } catch { res.writeHead(400); res.end("{}"); return; }
    const reply = decide(body);
    log({ model: body.model, messages: (body.messages || []).length, bytes: raw.length,
      reply: reply.action || (reply.verified ? "verified" : "?"), index: reply.index ?? null,
      auth: req.headers.authorization ? "bearer" : "none" });
    const content = JSON.stringify(reply);
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ id: "fixture", model: body.model, choices: [{ message: { role: "assistant", content } }],
      usage: { prompt_tokens: 1, completion_tokens: 1 } }));
  });
});
server.listen(PORT, "127.0.0.1", () => console.log(JSON.stringify({ provider: `http://127.0.0.1:${PORT}` })));
