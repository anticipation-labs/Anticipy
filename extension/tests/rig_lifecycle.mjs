// A LIFECYCLE RIG FOR THE SERVICE WORKER — not a test; a fixture the
// transport suites share.
//
// Real chrome_mock, the Worker's real filter DSL and jobs schema over FakeD1,
// a fake clock the shipped modules read through Date, and an in-memory backend
// that answers exactly the routes background.js and agent_loop.js talk to,
// with the Worker's lease rule (policy/workflow_guard.ts: a running row refuses
// a write whose X-Anticipy-Lease is not the held lease) mirrored. Nothing here
// reaches a network; every suite imports the REAL shipped modules and this file
// stands in for Chrome and the API only.
//
// Written 2026-09-12 to reproduce the "connects, then loses its connection"
// classes against the real background.js; see test_same_worker_reclaim_keeps_
// live_lease.mjs and test_heartbeat_window_contract.mjs.
import { installChrome } from "./chrome_mock.mjs";
import { parseFilter, compileFilter } from "../../migration/workers/filter-dsl.ts";
import { COLLECTIONS } from "../../migration/workers/src/api/schema.ts";
import { FakeD1 } from "../../migration/workers/test/fake-d1.ts";

export const OWNER = "ownerrefaaaaaa1";
export const ME = "ext-agent-0123456789abcdef";
export const TOKEN = "t".repeat(64);
export const RECORD = "agentrecord0001";

export const flush = (ms = 30) => new Promise((r) => setTimeout(r, ms));
export async function until(pred, { tries = 400, step = 25, what = "condition" } = {}) {
  for (let i = 0; i < tries; i++) { if (pred()) return true; await flush(step); }
  throw new Error(`timed out waiting for ${what}`);
}

// A fake clock. background.js and agent_loop.js read Date.now()/new Date() at
// call time, so swapping the global is enough; static Date.parse/UTC inherit.
export function fakeClock(start = Date.parse("2026-09-12T10:00:00.000Z")) {
  const Real = globalThis.Date;
  const clock = { now: start, advance(ms) { this.now += ms; return this.now; }, set(t) { this.now = t; } };
  class FakeDate extends Real {
    constructor(...a) { if (a.length) super(...a); else super(clock.now); }
    static now() { return clock.now; }
  }
  globalThis.Date = FakeDate;
  return clock;
}

const JOB_COLUMNS = ["created", "updated", "goal", "params", "status", "result", "device_id", "owner",
  "claimed_by", "claimed_at", "owner_ref", "lane", "attempts", "trace", "workflow_id",
  "workflow_version", "workflow_state", "consequence", "lineage_key", "effect_key",
  "scope_digest", "approval", "receipt", "reconciliation", "lease_token", "lease_until",
  "source_event_ids", "effect_uncertain", "watching_until", "commitment_key"];

export function installRig({ clock, rttMs = 0, onModel = null, keyReply = null, upgradeReply = null,
                             agentsPatch = null, jobsPatchDelayMs = 0, storage = {} } = {}) {
  const harness = installChrome();
  const sessionData = {};
  globalThis.chrome.storage.session = {
    get: async (keys) => { const out = {}; for (const k of (Array.isArray(keys) ? keys : [keys])) if (k in sessionData) out[k] = sessionData[k]; return out; },
    set: async (obj) => { Object.assign(sessionData, obj); },
  };
  const messageListeners = [];
  globalThis.chrome.runtime.onMessage = { addListener: (fn) => messageListeners.push(fn) };
  globalThis.chrome.tabs.onUpdated = { addListener: () => {} };
  const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
  harness.onCdp = (tabId, method) => (method === "Page.captureScreenshot" ? { data: FAKE_JPEG } : undefined);
  harness.mapPage = (tabId) => ({
    url: harness.tabs.get(tabId)?.url || "https://venue.fixture.invalid/happy-hour",
    title: "Happy hour",
    elements: "[0] <link> Menus @(10,10)\n[1] <link> Happy hour @(20,20)\n[2] <button> Reserve @(30,30)",
    text: "Happy hour runs 3-6pm daily.",
    fields: [],
  });
  Object.assign(harness.storageData, {
    backendUrl: "http://127.0.0.1:8090", agentId: ME, agentToken: TOKEN, recordId: RECORD,
    agentCredentialInstalled: true, ownerRef: OWNER, owner: "owner", paired: true,
    openrouterKey: "backend-proxy", agentModel: "m", visionModel: "v", serviceToken: "",
    keyFetchedAt: (clock ? clock.now : Date.now()), ...storage,
  });

  const db = new FakeD1();
  const agents = { id: RECORD, agent_id: ME, agent_token: TOKEN, paired: 1, owner: "owner",
                   owner_ref: OWNER, last_seen: "", browser: "", updated: "" };
  const log = [];
  const modelCalls = [];
  const reply = (body, status = 200) => ({
    ok: status >= 200 && status < 300, status,
    json: async () => body, text: async () => JSON.stringify(body),
    clone() { return this; },
  });
  const now = () => (clock ? clock.now : Date.now());
  const iso = () => new Date(now()).toISOString();

  const rig = { harness, db, agents, log, modelCalls, messageListeners, sessionData, reply,
    seedJob(id, { lane = "", owner = OWNER, consequence = "read_only", task = `do ${id}`, attempts = 0 } = {}) {
      const created = new Date(now() - 60000).toISOString();
      const params = JSON.stringify({ task, approved_scope: task, _workflow: {
        plan_id: `plan-${id}`, owner_ref: owner, lineage_key: `lin-${id}`, version: 1, goal: task,
        consequence, state: "queued", scope_digest: "sd", effect_key: `ek-${id}`, facts: {}, required: [],
        approval: null, lease: null, receipt: null, attempts, authority_text: task,
      } });
      db.db.prepare(`INSERT INTO jobs (id, created, updated, goal, params, status, owner_ref, lane, claimed_by,
        claimed_at, attempts, workflow_id, workflow_version, workflow_state, consequence, lineage_key,
        effect_key, lease_token, lease_until, device_id)
        VALUES (?, ?, ?, 'agent_goal', ?, 'queued', ?, ?, '', '', ?, ?, 1, 'queued', ?, ?, ?, '', '', 'fixture')`)
        .run(id, created, created, params, owner, lane, attempts, `plan-${id}`, consequence, `lin-${id}`, `ek-${id}`);
    },
    row(id) { return db.rows("SELECT * FROM jobs WHERE id = ?", id)[0]; },
    sendMessage(msg) {
      return new Promise((resolve) => { for (const fn of messageListeners) fn(msg, {}, resolve); });
    },
  };

  globalThis.fetch = async (raw, opts = {}) => {
    const url = new URL(String(raw));
    const method = opts.method || "GET";
    const headers = opts.headers || {};
    const body = opts.body && typeof opts.body === "string" ? JSON.parse(opts.body) : null;
    const entry = { at: now(), seq: log.length, method, path: url.pathname + url.search, body, headers, status: 0 };
    log.push(entry);
    if (rttMs) clock.advance(rttMs);
    const answer = (r) => { entry.status = r.status; entry.answeredAt = now(); return r; };
    const agentId = headers["X-Anticipy-Agent-ID"] || "";
    const token = headers["X-Anticipy-Agent-Token"] || "";
    const credentialed = agentId === agents.agent_id && token === agents.agent_token;
    const collections = url.pathname.startsWith("/api/collections/");
    if (collections && agentId && !credentialed) return answer(reply({ error: "agent credential is not recognized" }, 403));

    if (url.pathname === "/agent/register" && method === "POST") {
      const rec = { id: `agentrecord${String(log.length).padStart(4, "0")}`, agent_id: body.agent_id,
                    agent_token: "n".repeat(64), pair_code: "654321" };
      Object.assign(agents, { id: rec.id, agent_id: rec.agent_id, agent_token: rec.agent_token, paired: 0,
                              owner: "", owner_ref: "", last_seen: iso(), browser: body.browser || "" });
      return answer(reply(rec));
    }
    if (url.pathname === "/agent/upgrade-credential") {
      return answer(upgradeReply ? upgradeReply(body) : reply({ error: "upgrade not authorized" }, 403));
    }
    if (url.pathname === "/agent/key") {
      if (keyReply) return answer(keyReply({ agentId, token, credentialed }));
      if (!agentId || token.length < 40) return answer(reply({ error: "agent credentials required" }, 400));
      if (!credentialed || !agents.paired) return answer(reply({ error: "not a paired agent" }, 403));
      if (!agents.owner_ref) return answer(reply({ error: "paired agent has no canonical owner; pair it again from the signed-in app" }, 409));
      return answer(reply({ llm_proxy: true, owner_ref: agents.owner_ref, owner: { first_name: "Owner" }, model: "m", vision_model: "v" }));
    }
    if (url.pathname === "/agent/llm") {
      if (!credentialed || !agents.paired) return answer(reply({ error: "not a paired agent" }, 403));
      const all = body.messages.map((m) => (Array.isArray(m.content)
        ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n") : String(m.content || "")));
      const joined = all.join("\n");
      let kind = "step";
      if (/You plan a task/.test(joined)) kind = "plan";
      else if (/reading the open web to learn HOW/.test(joined)) kind = "learn";
      else if (/You audit a browser agent's claim/.test(joined)) kind = "verify";
      else if (/pre-submit form auditor/.test(joined)) kind = "form-audit";
      else if (/would following the remembered procedure/.test(joined)) kind = "recall";
      else if (/ONE question about the page's PURPOSE/.test(joined)) kind = "wall";
      const call = { kind, prompt: all[all.length - 1], at: now() };
      modelCalls.push(call);
      let content;
      if (kind === "plan") content = JSON.stringify({ start_url: "https://venue.fixture.invalid/happy-hour", why: "the venue", steps: [], unfamiliar: false });
      else if (kind === "verify") content = JSON.stringify({ verified: true, evidence: ["happy hour 3-6pm"] });
      else if (kind === "recall") content = "YES";
      else if (kind === "wall") content = "NONE";
      else content = onModel ? await onModel(call) : JSON.stringify({ action: "scroll", dy: 400 });
      if (content && typeof content === "object" && content.status) return answer(reply(content.body || {}, content.status));
      return answer(reply({ choices: [{ message: { content } }] }));
    }
    if (url.pathname === `/api/collections/agents/records/${agents.id}` && method === "PATCH") {
      if (agentsPatch) return answer(agentsPatch(body));
      if (!credentialed) return answer(reply({ error: "agent credential is not recognized" }, 403));
      if (body.last_seen) agents.last_seen = body.last_seen;
      if (body.browser) agents.browser = body.browser;
      agents.updated = iso();
      return answer(reply({ ...agents, paired: !!agents.paired }));
    }
    if (url.pathname === "/api/collections/jobs/records" && method === "GET") {
      if (!credentialed) return answer(reply({ error: "agent is not allowed to access that record" }, 403));
      const filter = compileFilter(parseFilter(url.searchParams.get("filter")), { schema: COLLECTIONS.jobs.columns });
      const limit = Number(url.searchParams.get("perPage") || 30);
      return answer(reply({ items: db.rows(`SELECT * FROM jobs WHERE ${filter.sql} ORDER BY created, id LIMIT ?`, ...filter.params, limit) }));
    }
    if (url.pathname.startsWith("/api/collections/jobs/records/")) {
      const id = url.pathname.split("/").at(-1);
      const row = rig.row(id);
      if (!row) return answer(reply({ error: "not found" }, 404));
      if (method === "GET") return answer(reply(row));
      if (method === "PATCH") {
        // A slow renewal, when a suite asks for one: the clock moves while the
        // write is in flight, the way a 20 s request deadline would let it.
        if (jobsPatchDelayMs && clock) clock.advance(jobsPatchDelayMs);
        // workflow_guard.ts — LEASE POSSESSION.
        if (row.status === "running" && body.status !== "cancelled") {
          const presented = headers["X-Anticipy-Lease"] || "";
          if (!row.lease_token || presented !== row.lease_token) {
            return answer(reply({ error: "running update came from the wrong lease" }, 409));
          }
        }
        const sets = []; const vals = [];
        for (const [k, v] of Object.entries(body)) {
          if (!JOB_COLUMNS.includes(k)) continue;
          sets.push(`"${k}" = ?`); vals.push(v === null ? "" : (typeof v === "boolean" ? (v ? 1 : 0) : v));
        }
        sets.push(`"updated" = ?`); vals.push(iso());
        db.db.prepare(`UPDATE jobs SET ${sets.join(", ")} WHERE id = ?`).run(...vals, id);
        return answer(reply(rig.row(id)));
      }
    }
    if (url.pathname === "/api/collections/evidence/records") return answer(reply({ id: "ev1" }));
    if (url.pathname === "/api/collections/events/records") return answer(reply({ id: "evt1" }));
    if (url.pathname === "/api/health") return answer(reply({ code: 200 }));
    return answer(reply({ error: "no such route in the rig" }, 404));
  };
  return rig;
}
