// An in-memory `chrome` for the never-foreground tests (brief 03 / roadmap §9).
// One window, real active-tab semantics, and — the part that matters — Chrome's
// dangerous behaviours reproduced faithfully:
//   * tabs.create with `active` omitted defaults to TRUE (steals focus),
//   * removing the ACTIVE tab hands focus to its opener (our working tab).
// Every extension-initiated focus grant is recorded in `harness.focusGrants`,
// and every activation from any cause in `harness.activationLog`, so a test
// can state "the owner's tab never lost the foreground" as an assertion.

export function installChrome() {
  let tabSeq = 0;
  let groupSeq = 0;
  const tabs = new Map(); // id -> {id, url, pendingUrl, active, openerTabId, windowId, groupId}
  const storageData = {};
  const notifications = new Map(); // id -> options
  const cleared = [];
  const badge = { text: "", color: "" };
  const focusGrants = [];   // {tabId} or {windowId} — extension called for focus
  const activationLog = []; // every tab id that ever became active, any cause
  const onRemovedListeners = [];
  const notifClickListeners = [];
  const startupListeners = [];
  const installedListeners = [];
  const alarmListeners = [];
  const alarms = new Map();
  let windowFocused = true;
  let currentWindowExists = true;

  const harness = {
    tabs, storageData, notifications, cleared, badge, focusGrants, activationLog, alarms,
    onCdp: null,          // (tabId, method, params) => result | undefined
    mapPage: null,        // (tabId) => {url, title, elements, text}
    activeTabId: () => [...tabs.values()].find((t) => t.active)?.id ?? null,
    windowFocused: () => windowFocused,
    setCurrentWindowExists: (exists) => { currentWindowExists = !!exists; },
    fireStartup: () => { for (const fn of startupListeners) fn(); },
    fireInstalled: (details = { reason: "update" }) => {
      for (const fn of installedListeners) fn(details);
    },
    fireAlarm: (name) => { for (const fn of alarmListeners) fn({ name }); },
  };

  function activate(id) {
    for (const t of tabs.values()) t.active = t.id === id;
    activationLog.push(id);
  }

  // Harness-side tab creation: "the page/user did this", not the extension —
  // no focus grant is recorded even when it lands focused, exactly like a
  // target=_blank popup Chrome chose to foreground.
  harness.addTab = ({ url = "about:blank", active = false, openerTabId } = {}) => {
    const t = { id: ++tabSeq, url, pendingUrl: undefined, active: false, openerTabId, windowId: 1, groupId: -1 };
    tabs.set(t.id, t);
    if (active) activate(t.id);
    return t;
  };
  // Vanish a tab with NO onRemoved event — what a Chrome restart looks like.
  harness.zapTab = (id) => { tabs.delete(id); };
  harness.fireNotificationClick = (id) => { for (const fn of notifClickListeners) fn(id); };

  const requireTab = (id) => {
    const t = tabs.get(id);
    if (!t) throw new Error(`No tab with id: ${id}.`);
    return t;
  };

  globalThis.chrome = {
    tabs: {
      query: async (q = {}) => {
        let out = [...tabs.values()];
        if (q.active !== undefined) out = out.filter((t) => t.active === q.active);
        // single-window world: lastFocusedWindow is a no-op filter
        return out.map((t) => ({ ...t }));
      },
      get: async (id) => ({ ...requireTab(id) }),
      create: async (props = {}) => {
        if (!currentWindowExists) throw new Error("No current window");
        const active = props.active !== false; // Chrome's real default: true
        const t = { id: ++tabSeq, url: props.url || "about:blank", pendingUrl: undefined, active: false, openerTabId: props.openerTabId, windowId: 1, groupId: -1 };
        tabs.set(t.id, t);
        if (active) { focusGrants.push({ tabId: t.id }); activate(t.id); }
        return { ...t };
      },
      update: async (id, props = {}) => {
        const t = requireTab(id);
        if (props.url !== undefined) t.url = props.url;
        if (props.active === true) { focusGrants.push({ tabId: id }); activate(id); }
        return { ...t };
      },
      remove: async (id) => {
        const t = requireTab(id);
        const wasActive = t.active;
        tabs.delete(id);
        if (wasActive) {
          // Chrome's successor pick: the opener if it's still around, else
          // the first remaining tab. This is how a swept popup can surface
          // the agent's own working tab.
          const heir = (t.openerTabId != null && tabs.get(t.openerTabId)) || [...tabs.values()][0];
          if (heir) activate(heir.id);
        }
        for (const fn of onRemovedListeners) fn(id, { windowId: 1, isWindowClosing: false });
      },
      group: async ({ tabIds }) => {
        const ids = Array.isArray(tabIds) ? tabIds : [tabIds];
        const g = ++groupSeq;
        for (const id of ids) requireTab(id).groupId = g;
        return g;
      },
      ungroup: async (id) => { requireTab(id).groupId = -1; },
      onRemoved: { addListener: (fn) => onRemovedListeners.push(fn) },
    },
    tabGroups: { update: async () => ({}) },
    windows: {
      create: async (props = {}) => {
        currentWindowExists = true;
        windowFocused = props.focused !== false;
        const t = harness.addTab({ url: props.url || "about:blank", active: false });
        if (props.focused === true) focusGrants.push({ windowId: 1 });
        return { id: 1, focused: windowFocused, state: props.state || "normal", tabs: [{ ...t }] };
      },
      update: async (windowId, props = {}) => {
        if (props.focused === true) { focusGrants.push({ windowId }); windowFocused = true; }
        return { id: windowId };
      },
    },
    storage: {
      local: {
        get: async (keys) => {
          const want = typeof keys === "string" ? [keys] : Array.isArray(keys) ? keys : Object.keys(keys || storageData);
          const out = {};
          for (const k of want) if (k in storageData) out[k] = structuredClone(storageData[k]);
          return out;
        },
        set: async (obj) => { for (const [k, v] of Object.entries(obj)) storageData[k] = structuredClone(v); },
        remove: async (keys) => { for (const k of (Array.isArray(keys) ? keys : [keys])) delete storageData[k]; },
      },
      onChanged: { addListener: () => {} },
    },
    scripting: {
      executeScript: async ({ target, func }) => {
        const src = func ? String(func) : "";
        if (src.includes("__anticipyMapPage")) {
          const m = harness.mapPage ? harness.mapPage(target.tabId) : { url: "", title: "", elements: "", text: "" };
          return [{ frameId: 0, result: { w: 1280, h: 800, iframes: [], sugg: "", ...m } }];
        }
        if (src.includes("__anticipySuggestions")) return [{ result: "" }];
        if (src.includes("__anticipyCenter")) return [{ result: { x: 5, y: 5 } }];
        return [{ result: null }];
      },
    },
    debugger: {
      attach: async () => {},
      detach: async () => {},
      sendCommand: async ({ tabId }, method, params) => {
        const out = harness.onCdp && harness.onCdp(tabId, method, params);
        return out || {};
      },
      onDetach: { addListener: () => {} },
    },
    notifications: {
      create: async (id, options) => { notifications.set(id, options); return id; },
      clear: async (id) => { notifications.delete(id); cleared.push(id); return true; },
      onClicked: { addListener: (fn) => notifClickListeners.push(fn) },
    },
    action: {
      setBadgeText: async ({ text }) => { badge.text = text; },
      setBadgeBackgroundColor: async ({ color }) => { badge.color = color; },
    },
    runtime: {
      getURL: (p) => p,
      getManifest: () => ({ version: "0.0.0-test" }),
      onMessage: { addListener: () => {} },
      onInstalled: { addListener: (fn) => installedListeners.push(fn) },
      onStartup: { addListener: (fn) => startupListeners.push(fn) },
    },
    alarms: {
      get: async (name) => alarms.has(name) ? structuredClone(alarms.get(name)) : undefined,
      create: async (name, options = {}) => {
        alarms.set(name, { name, scheduledTime: Date.now(), ...structuredClone(options) });
      },
      clear: async (name) => alarms.delete(name),
      onAlarm: { addListener: (fn) => alarmListeners.push(fn) },
    },
  };
  return harness;
}
