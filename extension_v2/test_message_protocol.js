/**
 * Background ↔ content message-protocol unit tests.
 *
 * Pure-Node test runner — no Jest install required.
 * Run with: `node --test extension_v2/test_message_protocol.js`
 *
 * Mocks chrome.* APIs and loads background.js with the test flag
 * (__ANTICIPY_BRIDGE_TEST__) so the module exposes its internals on
 * globalThis.__bridge.
 *
 * Verifies the four core flows the server depends on:
 *   1. navigate  → forwarded to content.js, server gets ok:true.
 *   2. click     → same.
 *   3. extract   → server gets the text payload back.
 *   4. screenshot → background uses chrome.tabs.captureVisibleTab, server
 *                   gets the dataUrl back.
 *
 * Also covers: unknown commands, malformed JSON, the done message.
 *
 * No real network, no real DOM — protocol shape only.
 */
const { test, beforeEach, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// ─── Mock chrome.* before loading background.js ──────────────────────────
function makeChromeMock() {
  const tabs = new Map();
  let nextTabId = 100;
  let nextGroupId = 1;
  const messageHandlers = [];
  const contentResponders = new Map();

  return {
    _tabs: tabs,
    _contentResponders: contentResponders,
    _messageHandlers: messageHandlers,
    runtime: {
      onMessage: { addListener(fn) { messageHandlers.push(fn); } },
      onStartup: { addListener() {} },
      onInstalled: { addListener() {} },
      sendMessage: async () => {},
      lastError: null,
    },
    storage: {
      local: {
        _data: { userId: "u1", code: "c1", serverUrl: "wss://test/ws/agent" },
        async get(keys) {
          const out = {};
          (Array.isArray(keys) ? keys : [keys]).forEach((k) => {
            if (k in this._data) out[k] = this._data[k];
          });
          return out;
        },
        async set(obj) { Object.assign(this._data, obj); },
        async remove(keys) {
          (Array.isArray(keys) ? keys : [keys]).forEach((k) => delete this._data[k]);
        },
      },
    },
    tabs: {
      async create({ url }) {
        const id = nextTabId++;
        const t = { id, url: url || "about:blank", windowId: 1 };
        tabs.set(id, t);
        return t;
      },
      async get(id) {
        const t = tabs.get(id);
        if (!t) throw new Error("no such tab");
        return t;
      },
      async query() { return [...tabs.values()].slice(0, 1); },
      async remove(id) { tabs.delete(id); },
      async group({ tabIds, groupId }) {
        if (groupId) return groupId;
        return nextGroupId++;
      },
      async sendMessage(tabId, msg) {
        const responder = contentResponders.get(tabId)
          || contentResponders.get("*")
          || (() => ({ ok: true, data: { echo: msg.type } }));
        return responder(msg);
      },
      async captureVisibleTab(_winId, _opts) {
        return "data:image/png;base64,FAKE";
      },
      onRemoved: { addListener() {} },
    },
    tabGroups: { async update() {} },
    scripting: {
      async executeScript() { return [{ result: null }]; },
    },
  };
}

function loadBridge(chromeMock) {
  // Don't fail if WebSocket isn't defined — background.js calls `new WebSocket(...)`
  // inside connect(), which runs at import time. Stub it.
  globalThis.WebSocket = class {
    constructor() { this.readyState = 0; }
    addEventListener() {}
    send() {}
    close() {}
  };
  globalThis.WebSocket.OPEN = 1;
  globalThis.WebSocket.CONNECTING = 0;
  globalThis.WebSocket.CLOSED = 3;

  globalThis.__ANTICIPY_BRIDGE_TEST__ = true;

  const code = fs.readFileSync(path.join(__dirname, "background.js"), "utf8");
  // background.js references `chrome` from module scope — pass via a wrapper fn.
  // eslint-disable-next-line no-new-func
  new Function("chrome", code)(chromeMock);
  return globalThis.__bridge;
}

// ─── Tests ────────────────────────────────────────────────────────────────
describe("background ↔ content message protocol", () => {
  let bridge, sent, chrome;

  beforeEach(() => {
    sent = [];
    chrome = makeChromeMock();
    globalThis.chrome = chrome;
    bridge = loadBridge(chrome);
    bridge.setWs({
      readyState: 1,
      send: (raw) => sent.push(JSON.parse(raw)),
      addEventListener: () => {},
      close: () => {},
    });
    chrome._tabs.set(42, { id: 42, url: "https://example.com", windowId: 1 });
    bridge.setActiveTask({
      taskId: "t1",
      summary: "test",
      tabGroupId: 9,
      seedTabId: 42,
      tabIds: new Set([42]),
      currentStep: "",
      finished: false,
      result: "",
    });
  });

  test("navigate: round-trips through chrome.tabs.sendMessage", async () => {
    chrome._contentResponders.set(42, (msg) => {
      assert.equal(msg.type, "navigate");
      assert.equal(msg.payload.url, "https://target.example");
      return { ok: true, data: { navigatedTo: "https://target.example" } };
    });
    await bridge.onServerMessage({
      data: JSON.stringify({ type: "navigate", cmdId: "c1", url: "https://target.example", tabId: 42 }),
    });
    assert.equal(sent.length, 1);
    assert.equal(sent[0].type, "result");
    assert.equal(sent[0].cmdId, "c1");
    assert.equal(sent[0].ok, true);
    assert.equal(sent[0].tabId, 42);
    assert.equal(sent[0].data.data.navigatedTo, "https://target.example");
  });

  test("click: forwards selector to content script and returns ok", async () => {
    chrome._contentResponders.set(42, (msg) => {
      assert.equal(msg.type, "click");
      assert.equal(msg.payload.selector, "#submit");
      return { ok: true, data: { clicked: "#submit" } };
    });
    await bridge.onServerMessage({
      data: JSON.stringify({ type: "click", cmdId: "c2", selector: "#submit", tabId: 42 }),
    });
    assert.equal(sent[0].type, "result");
    assert.equal(sent[0].cmdId, "c2");
    assert.equal(sent[0].ok, true);
    assert.equal(sent[0].data.data.clicked, "#submit");
  });

  test("extract: returns visible text from content script", async () => {
    chrome._contentResponders.set(42, () => ({
      ok: true, data: { selector: "h1", text: "Hello World" },
    }));
    await bridge.onServerMessage({
      data: JSON.stringify({ type: "extract", cmdId: "c3", selector: "h1", tabId: 42 }),
    });
    assert.equal(sent[0].ok, true);
    assert.equal(sent[0].data.data.text, "Hello World");
  });

  test("screenshot: returns dataUrl from chrome.tabs.captureVisibleTab", async () => {
    await bridge.onServerMessage({
      data: JSON.stringify({ type: "screenshot", cmdId: "c4", tabId: 42 }),
    });
    assert.equal(sent[0].type, "result");
    assert.equal(sent[0].cmdId, "c4");
    assert.equal(sent[0].ok, true);
    assert.equal(sent[0].tabId, 42);
    assert.equal(sent[0].data.dataUrl, "data:image/png;base64,FAKE");
  });

  test("unknown command type: server gets a structured error", async () => {
    await bridge.onServerMessage({
      data: JSON.stringify({ type: "fly_to_moon", cmdId: "cX" }),
    });
    assert.equal(sent[0].type, "error");
    assert.equal(sent[0].cmdId, "cX");
    assert.match(sent[0].message, /unknown command/);
  });

  test("done: marks task finished without closing tabs", async () => {
    await bridge.onServerMessage({
      data: JSON.stringify({ type: "done", summary: "Booked!" }),
    });
    const task = bridge.getActiveTask();
    assert.equal(task.finished, true);
    assert.equal(task.result, "Booked!");
    assert.equal(chrome._tabs.has(42), true);
  });

  test("malformed JSON from server: dropped silently, no crash", async () => {
    await bridge.onServerMessage({ data: "{not json" });
    assert.equal(sent.length, 0);
  });
});
