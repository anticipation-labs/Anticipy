// Actual popup module and actual DOM IDs; only Chrome/network/DOM are fixtures.
// No provider calls, credentials, browser profile or production data.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const source = readFileSync(new URL("../popup.js", import.meta.url), "utf8")
  .replace(/^import .*;\n/gm, "");
const html = readFileSync(new URL("../popup.html", import.meta.url), "utf8");
const settle = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
const paired = (owner = "owner-a") => ({
  paired: true, ownerRef: owner, agentId: `agent-${owner}`, agentToken: `token-${owner}`,
  recordId: `record-${owner}`, pairCode: "123456", backendUrl: "https://fixture.invalid",
});
const job = (owner = "owner-a", id = "job-a") => ({
  id, ownerRef: owner, status: "running", doing: `${owner} private task`, result: "",
});
const response = (row, ok = true) => ({ ok, json: async () => row });

function rig(storage, fetchJob = async () => response({ id: "job-a", owner_ref: "owner-a", params: {} }),
             sendReply = () => ({ ok: true })) {
  const nodes = new Map();
  for (const [, id] of html.matchAll(/\bid="([^"]+)"/g)) {
    const listeners = new Map(), hidden = new Set();
    nodes.set(id, {
      textContent: "", disabled: false, classList: { toggle() {} },
      toggleAttribute(name, enabled) { enabled ? hidden.add(name) : hidden.delete(name); },
      addEventListener(name, callback) { listeners.set(name, callback); },
      hidden, listeners,
    });
  }
  const changes = [], messages = [], reads = [];
  let closes = 0;
  const context = vm.createContext({
    console, Date, Set, String, Object, encodeURIComponent,
    document: { getElementById: id => { assert.ok(nodes.has(id), `actual DOM ID ${id}`); return nodes.get(id); },
      body: { classList: { toggle() {} } } },
    navigator: { clipboard: { writeText: async () => {} } }, window: { close() { closes++; } },
    setInterval() {},
    backendBase: async () => storage.backendUrl,
    parseJobParams: row => typeof row.params === "string" ? JSON.parse(row.params) : row.params || {},
    chrome: {
      storage: {
        local: { get: async keys => structuredClone(Object.fromEntries(keys.map(k => [k, storage[k]]))) },
        onChanged: { addListener: callback => changes.push(callback) },
      },
      runtime: { sendMessage: async message => { messages.push(structuredClone(message)); return sendReply(message); } },
    },
    fetch: async (url, options) => {
      if (url.endsWith("/api/health")) return response({});
      reads.push({ url, options });
      return fetchJob(url, options);
    },
  });
  vm.runInContext(source + "\nglobalThis.popupTest = { refresh, snapshot };", context);
  return {
    storage, nodes, messages, reads,
    closes: () => closes,
    refresh: () => context.popupTest.refresh(),
    async change(values) {
      const event = {};
      for (const [key, value] of Object.entries(values)) {
        event[key] = { oldValue: storage[key], newValue: value };
        storage[key] = value;
      }
      for (const callback of changes) callback(event, "local");
      await settle();
    },
    async click(id) { await nodes.get(id).listeners.get("click")(); await settle(); },
    hidden: id => nodes.get(id).hidden.has("hidden"),
    text: id => nodes.get(id).textContent,
  };
}

const cases = [];
const test = (name, fn) => cases.push({ name, fn });

test("unpaired popup never renders retained job or hand-back text", async () => {
  const r = rig({ ...paired(), paired: false, ownerRef: "", currentJob: job(), handBacks: { 7: { ownerRef: "owner-a", at: 5 } } });
  await settle();
  assert.ok(r.hidden("jobbox"));
  assert.equal(r.reads.length, 0);
  assert.equal(r.storage.currentJob.doing, "owner-a private task", "evidence retained");
});
test("foreign and unowned legacy task records stay hidden", async () => {
  for (const owner of ["owner-b", undefined]) {
    const r = rig({ ...paired(), currentJob: { ...job(owner), ownerRef: owner } });
    await settle(); assert.ok(r.hidden("jobbox")); assert.equal(r.reads.length, 0);
  }
});
test("owner flag without an agent credential is not linked", async () => {
  for (const agentToken of ["", "   ", null, {}]) {
    const r = rig({ ...paired(), agentToken, currentJob: job() });
    await settle(); assert.equal(r.text("linktext"), "Not linked"); assert.ok(r.hidden("jobbox"));
  }
});
test("same-owner task renders and Stop carries exact displayed identity", async () => {
  const r = rig({ ...paired(), currentJob: job() });
  await settle(); assert.equal(r.hidden("jobbox"), false);
  await r.click("stop");
  const message = r.messages.find(m => m.type === "anticipy-stop");
  assert.deepEqual(message, { type: "anticipy-stop", id: "job-a", ownerRef: "owner-a" });
});
test("a refused or missing worker response clears the pending action acknowledgement", async () => {
  for (const reply of [{ ok: false }, undefined]) {
    const r = rig({ ...paired(), currentJob: job() }, undefined, () => reply);
    await settle(); await r.click("stop");
    assert.ok(!r.text("jobdoing").includes("Stopping"));
    assert.equal(r.hidden("stop"), false, "refusal must not leave controls latched busy");
  }
});
test("Stop cannot silently target a different job that replaced the displayed one", async () => {
  const r = rig({ ...paired(), currentJob: job() });
  await settle();
  r.storage.currentJob = job("owner-a", "job-b"); // before the storage event arrives
  await r.click("stop");
  assert.equal(r.messages.filter(m => m.type === "anticipy-stop").length, 0);
});
test("a stale Stop after re-pair sends no message for either owner", async () => {
  const r = rig({ ...paired(), currentJob: job() });
  await settle(); Object.assign(r.storage, paired("owner-b"), { currentJob: job("owner-b", "job-b") });
  await r.click("stop");
  assert.equal(r.messages.filter(m => m.type === "anticipy-stop").length, 0);
});
test("only same-owner hand-backs are offered and their owner is sent", async () => {
  const r = rig({ ...paired(), currentJob: job(), handBacks: {
    7: { ownerRef: "owner-a", at: 1 }, 8: { ownerRef: "owner-b", at: 3 }, 9: { at: 4 },
  } });
  await settle(); await r.click("openhb");
  assert.deepEqual(r.messages.find(m => m.type === "anticipy-open-handback"),
    { type: "anticipy-open-handback", tabId: "7", ownerRef: "owner-a" });
});
test("retained foreign hand-back is not exposed to a valid new owner", async () => {
  const r = rig({ ...paired("owner-b"), currentJob: job("owner-b"), handBacks: { 7: { ownerRef: "owner-a", at: 1 } } });
  await settle(); assert.ok(r.hidden("openhb")); await r.click("openhb");
  assert.equal(r.messages.filter(m => m.type === "anticipy-open-handback").length, 0);
});
test("refused hand-back keeps the popup open instead of implying it opened the page", async () => {
  const r = rig({ ...paired(), currentJob: job(), handBacks: { 7: { ownerRef: "owner-a", at: 1 } } },
    undefined, () => ({ ok: false }));
  await settle(); await r.click("openhb"); assert.equal(r.closes(), 0);
});
test("delayed narration from the old owner cannot repaint after re-pair", async () => {
  let resolveOld;
  const delayed = new Promise(resolve => { resolveOld = resolve; });
  const r = rig({ ...paired(), currentJob: job() }, () => delayed);
  await settle(); assert.equal(r.reads.length, 1);
  await r.change({ ...paired("owner-b"), currentJob: null });
  resolveOld(response({ id: "job-a", owner_ref: "owner-a", params: { _doing: "owner-a secret narration" } }));
  await settle();
  assert.ok(r.hidden("jobbox"));
  for (const id of ["jobdoing", "joberrand", "jobresult"]) assert.equal(r.text(id), "");
});
test("unexpected owner or job in a read response cannot become live narration", async () => {
  for (const row of [
    { id: "job-a", owner_ref: "owner-b" }, { id: "job-b", owner_ref: "owner-a" }, { id: "job-a" },
  ]) {
    const r = rig({ ...paired(), currentJob: job() }, async () => response({ ...row, params: { _doing: "foreign narration" } }));
    await settle(); assert.ok(!r.text("jobdoing").includes("foreign narration"));
  }
});
test("same owner changing tasks cannot inherit the previous live step", async () => {
  const r = rig({ ...paired(), currentJob: job() }, async url => response({
    id: url.endsWith("job-a") ? "job-a" : "job-b", owner_ref: "owner-a",
    params: { _doing: url.endsWith("job-a") ? "step-a" : "step-b" },
  }));
  await settle(); assert.equal(r.text("jobdoing"), "step-a");
  await r.change({ currentJob: job("owner-a", "job-b") });
  assert.equal(r.text("jobdoing"), "step-b");
});

test("a record paired before owner ids shows the way out: New code, and no dead code", async () => {
  const r = rig({ ...paired(), ownerRef: "", paired: true, pairCode: "123456" });
  await settle();
  assert.equal(r.text("linktext"), "Not linked");
  assert.equal(r.hidden("getcode"), false, "the only recovery must be offered");
  assert.notEqual(r.text("paircode"), "123456", "a code the phone already used is not a code");
  assert.match(r.text("state"), /pair (it )?again/i);
});
test("a live step slower than the refresh tick still renders when the job is unchanged", async () => {
  // Every job-row read outlives the next 4 s tick: read N is answered only
  // after refresh N+1 has started. The job never changed, so read N's step is
  // still true and must be shown, not discarded for being slow.
  const resolvers = [];
  let reads = 0;
  const r = rig({ ...paired(), currentJob: job() },
    () => new Promise(res => resolvers.push(() => res(response({ id: "job-a", owner_ref: "owner-a",
      params: { _doing: ++reads === 1 ? "opening the page" : "typing the address" } })))));
  await settle();
  while (resolvers.length) resolvers.shift()();      // the load-time refresh completes normally
  await settle();
  assert.equal(r.text("jobdoing"), "opening the page");
  const first = r.refresh();
  await settle();
  const second = r.refresh();                        // the tick fired: epoch moved while read 1 is in flight
  await settle();
  resolvers.shift()();                               // read 1 answers now — job unchanged
  await first; await settle();
  assert.equal(r.text("jobdoing"), "typing the address", "a slow read of an unchanged job is still the live step");
  while (resolvers.length) resolvers.shift()();
  await second;
});

let failures = 0;
for (const { name, fn } of cases) {
  try { await fn(); console.log(`PASS: ${name}`); }
  catch (error) { failures++; console.error(`FAIL: ${name}: ${error.message}`); }
}
console.log(`popup owner boundary: ${cases.length - failures}/${cases.length} passed`);
process.exitCode = failures ? 1 : 0;
