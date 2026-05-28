const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

async function loadBridge({ failFileInjection }) {
  const posted = [];
  const chrome = {
    runtime: {
      connectNative: () => ({
        postMessage: () => {},
        onMessage: { addListener: () => {} },
        onDisconnect: { addListener: () => {} },
      }),
      onMessage: { addListener: () => {} },
      onStartup: { addListener: () => {} },
      onInstalled: { addListener: () => {} },
      sendMessage: () => {},
    },
    storage: {
      local: { set: () => {} },
    },
    scripting: {
      calls: [],
      async executeScript(options) {
        this.calls.push(options);
        if (options.files && failFileInjection) {
          throw new Error("Could not load file: 'content.js'.");
        }
        return [];
      },
    },
    tabs: {
      async query() {
        return [{ id: 42, active: true, windowId: 7, url: "https://example.test/" }];
      },
      async sendMessage(tabId, msg) {
        posted.push({ tabId, msg });
        return { ok: true, data: { echoed: msg.type } };
      },
      onRemoved: { addListener: () => {} },
    },
    tabGroups: {
      update: async () => {},
    },
    windows: {
      update: async () => {},
    },
  };
  const context = {
    console,
    setInterval: () => 1,
    clearInterval: () => {},
    setTimeout: () => {},
    chrome,
    __ANTICIPY_V4_TEST__: true,
  };
  context.globalThis = context;
  vm.createContext(context);
  const code = fs.readFileSync(path.join(__dirname, "background.js"), "utf8");
  vm.runInContext(code, context, { filename: "background.js" });
  context.__bridgeV4.setPort({ postMessage: (payload) => posted.push(payload) });
  context.__bridgeV4.setActiveTask({
    taskId: "test-task",
    summary: "test",
    tabGroupId: null,
    tabIds: new Set([42]),
    currentStep: "",
    finished: false,
  });
  return { bridge: context.__bridgeV4, chrome, posted };
}

(async () => {
  {
    const { bridge, chrome } = await loadBridge({ failFileInjection: false });
    await bridge.runInTab({ type: "read", selector: "body" }, "cmd-normal");
    assert.deepStrictEqual(chrome.scripting.calls.map((call) => Object.keys(call).sort()), [
      ["files", "target"],
    ]);
  }

  {
    const { bridge, chrome, posted } = await loadBridge({ failFileInjection: true });
    await bridge.runInTab({ type: "read", selector: "body" }, "cmd-fallback");
    assert.strictEqual(chrome.scripting.calls.length, 2);
    assert.strictEqual(JSON.stringify(chrome.scripting.calls[0].files), JSON.stringify(["content.js"]));
    assert.strictEqual(chrome.scripting.calls[1].func.name, "installContentScriptFallback");
    assert.match(chrome.scripting.calls[1].args[0], /Could not load file: 'content\.js'/);
    const result = posted.at(-1);
    assert.strictEqual(result.type, "result");
    assert.strictEqual(result.cmdId, "cmd-fallback");
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.tabId, 42);
    assert.strictEqual(JSON.stringify(result.data), JSON.stringify({ echoed: "read" }));
    assert.strictEqual(result.error, undefined);
  }

  console.log("ok - extension_v4 content injection falls back after packaged file load failure");
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
