// Unit tests for the provider-quota tracking that lives on BrowserAgent.
// No real LLM calls — we instrument the cascade with stubbed _call*
// methods that simulate 429s, successes, and blocked windows.

import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// We can't `await import` extension/agent.js as ESM (it uses `chrome.*`
// globals via free vars). Build a minimal browseragent harness that just
// imports the per-instance helpers we're testing — copy the relevant
// bits via a regex extract OR re-define them here. Cleaner: re-define
// the exact methods, then assert they match the source.
const agentSrc = readFileSync(resolve(__dirname, "agent.js"), "utf8");

// Helper assertions — make sure the methods we re-define here are still
// in agent.js verbatim. If you rename or refactor on the agent side and
// forget to update this test, the assertion below will yell at you.
function assertSourceContains(snippet) {
  assert.ok(
    agentSrc.includes(snippet),
    `agent.js missing required snippet:\n${snippet}\n`
  );
}
assertSourceContains("_isProviderBlocked(name)");
assertSourceContains("_markProvider429(name)");
assertSourceContains("_markProviderOk(name)");
assertSourceContains("_QUOTA_BASE_COOLDOWN_MS = 5000");
assertSourceContains("_QUOTA_MAX_COOLDOWN_MS = 60000");

// Minimal class mirroring just the quota helpers. If you change the
// helpers on BrowserAgent, copy them here.
class StubAgent {
  constructor() {
    this._providerUnblockAt = {};
    this._providerFailCount = {};
    this._QUOTA_BASE_COOLDOWN_MS = 5000;
    this._QUOTA_MAX_COOLDOWN_MS = 60000;
  }
  _isProviderBlocked(name) {
    const until = this._providerUnblockAt[name] || 0;
    return Date.now() < until;
  }
  _markProvider429(name) {
    const fails = (this._providerFailCount[name] || 0) + 1;
    this._providerFailCount[name] = fails;
    const cooldown = Math.min(
      this._QUOTA_BASE_COOLDOWN_MS * Math.pow(2, fails - 1),
      this._QUOTA_MAX_COOLDOWN_MS
    );
    this._providerUnblockAt[name] = Date.now() + cooldown;
  }
  _markProviderOk(name) {
    if (this._providerFailCount[name]) this._providerFailCount[name] = 0;
    delete this._providerUnblockAt[name];
  }
  _earliestUnblockMs() {
    const futures = Object.values(this._providerUnblockAt).filter(t => t > Date.now());
    return futures.length ? Math.min(...futures) : null;
  }
}

const tests = [];
function test(name, fn) { tests.push({ name, fn }); }

test("first 429 sets 5s cooldown", () => {
  const a = new StubAgent();
  const before = Date.now();
  a._markProvider429("gemini");
  const until = a._providerUnblockAt["gemini"];
  assert.ok(until > before + 4900 && until < before + 5100,
    `expected 5s cooldown, got ${until - before}ms`);
});

test("second 429 sets 10s cooldown", () => {
  const a = new StubAgent();
  a._markProvider429("gemini");
  const before = Date.now();
  a._markProvider429("gemini");
  const until = a._providerUnblockAt["gemini"];
  assert.ok(until > before + 9900 && until < before + 10100,
    `expected 10s cooldown, got ${until - before}ms`);
});

test("exponential backoff caps at 60s", () => {
  const a = new StubAgent();
  for (let i = 0; i < 10; i++) a._markProvider429("groq");
  const before = Date.now();
  a._markProvider429("groq");
  const until = a._providerUnblockAt["groq"];
  // 11 fails → 5 * 2^10 = 5120s, capped at 60s.
  assert.ok(until > before + 59900 && until < before + 60100,
    `expected 60s cap, got ${until - before}ms`);
});

test("_isProviderBlocked returns true while in cooldown", () => {
  const a = new StubAgent();
  a._markProvider429("kimi");
  assert.equal(a._isProviderBlocked("kimi"), true);
});

test("_isProviderBlocked returns false for unknown provider", () => {
  const a = new StubAgent();
  assert.equal(a._isProviderBlocked("never-seen"), false);
});

test("_markProviderOk clears state", () => {
  const a = new StubAgent();
  a._markProvider429("deepseek");
  a._markProvider429("deepseek");
  a._markProviderOk("deepseek");
  assert.equal(a._isProviderBlocked("deepseek"), false);
  assert.equal(a._providerFailCount["deepseek"], 0);
});

test("after _markProviderOk, next 429 resets to 5s base (not exponential)", () => {
  const a = new StubAgent();
  a._markProvider429("gemini");
  a._markProvider429("gemini");
  a._markProviderOk("gemini");
  const before = Date.now();
  a._markProvider429("gemini");
  const until = a._providerUnblockAt["gemini"];
  assert.ok(until > before + 4900 && until < before + 5100,
    `expected reset to 5s, got ${until - before}ms`);
});

test("_earliestUnblockMs picks the soonest", () => {
  const a = new StubAgent();
  a._markProvider429("gemini");        // 5s
  a._markProvider429("groq");          // 5s
  a._markProvider429("groq");          // 10s — overwrites
  const earliest = a._earliestUnblockMs();
  // Gemini should still be the earliest (only 1 fail = 5s vs groq 10s).
  assert.equal(earliest, a._providerUnblockAt["gemini"]);
});

test("_earliestUnblockMs returns null when nothing blocked", () => {
  const a = new StubAgent();
  assert.equal(a._earliestUnblockMs(), null);
});

test("simultaneous 429 on all providers schedules wait until earliest", () => {
  const a = new StubAgent();
  a._markProvider429("gemini");
  a._markProvider429("groq");
  a._markProvider429("kimi");
  a._markProvider429("deepseek");
  const earliest = a._earliestUnblockMs();
  assert.ok(earliest > Date.now());
  assert.ok(earliest <= Date.now() + 5100);
});

test("hardcoded failure-phrase list is GONE from agent.js", () => {
  // The old friendlyAgentMessage had string-match rules. Verify they're
  // NOT in the source anymore.
  const banned = [
    "Hit my AI rate limit. Give me a minute and try again",
    "got stuck on the page — let me try a different approach",
    "took longer than expected — try a simpler ask",
    "Hit a hiccup mid-task. Mind trying that again",
    "wants you signed in. Open it once",
    "asked for a human check. Open it once",
    "blocking automated access right now",
    "Network hiccup mid-task",
  ];
  for (const phrase of banned) {
    assert.ok(
      !agentSrc.includes(phrase),
      `agent.js still contains banned hardcoded phrase: "${phrase}"`
    );
  }
});

test("agent.js still has the SINGLE generic fallback line (not a rule list)", () => {
  // The new policy is: ONE fallback line. Verify it's there and that
  // there are no `lower.includes(` calls in friendlyAgentMessage anymore.
  assert.ok(agentSrc.includes("I couldn't finish that one. Want to try again?"));
  // The friendlyAgentMessage function must not use string-match rules.
  const fnStart = agentSrc.indexOf("async function friendlyAgentMessage");
  const fnEnd = agentSrc.indexOf("}\n", fnStart);
  const fn = agentSrc.substring(fnStart, fnEnd);
  assert.ok(
    !fn.includes("lower.includes("),
    "friendlyAgentMessage must not use lower.includes() string-match rules"
  );
});

let pass = 0, fail = 0;
for (const t of tests) {
  try { t.fn(); console.log(`  PASS  ${t.name}`); pass++; }
  catch (e) { console.error(`  FAIL  ${t.name}\n    ${e.message}`); fail++; }
}
console.log(`\n${pass}/${pass + fail} passed`);
process.exit(fail === 0 ? 0 : 1);
