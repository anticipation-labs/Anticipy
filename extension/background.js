// Anticipy Chrome Extension — Service Worker (Manifest V3)
// Connects to Supabase Realtime for live intent updates.
// When an intent is confirmed, the BrowserAgent executes it directly in the user's browser.

import { BrowserAgent } from "./agent.js";

// ─── Constants (public keys — safe to embed) ──────────────────────────────────
const SUPABASE_URL = "https://ogbxpqkmsdrcuilafycn.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9nYnhwcWttc2RyY3VpbGFmeWNuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4NDI3NDksImV4cCI6MjA5MDQxODc0OX0.PNfKYanSXJTfrYXWGZoUBFaZVE_jnsV4cqBXgxrRJ-0";

// ─── State ────────────────────────────────────────────────────────────────────
let realtimeWs = null;
let connected = false;
let lastActions = [];
let heartbeatRef = 0;
let joinRef = 0;

// In-memory dedup sets — survive only the lifetime of the SW. Combined
// with chrome.storage.local (durable across SW restarts) they close the
// TOCTOU race where two near-simultaneous Realtime events for the SAME
// intent (postgres_changes UPDATE + broadcast event) both pass a
// chrome.storage.local.get() check before either has called .set().
//
// First event into the SW wins via Set.add(), all subsequent events for
// the same id no-op without an async hop. Generic — any future handler
// that needs single-flight semantics on intent.id can reuse this.
const seenNewIntentIds = new Set();
const seenConfirmedIntentIds = new Set();
// Cap each Set so a long-lived SW doesn't grow unbounded.
const SEEN_SET_MAX = 500;
function trackSeen(set, id) {
  if (!id) return false;
  if (set.has(id)) return true;
  set.add(id);
  if (set.size > SEEN_SET_MAX) {
    // Drop the oldest entry — Set preserves insertion order.
    const first = set.values().next().value;
    if (first !== undefined) set.delete(first);
  }
  return false;
}

// Debug hook — exposes the confirmed-intent path to the SW global scope so a
// Playwright (or DevTools) caller can drive the agent without going through
// Realtime. Production code paths don't depend on this.
globalThis.__anticipy_debug_run_intent = (intent) => {
  try {
    handleConfirmedIntent(intent);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  }
};

// ─── MAIN-world inject: force every shadow root open ─────────────────────────
// Must run BEFORE the page's own scripts so the constructor of every custom
// element sees the patched attachShadow. We register a persistent content
// script in `world: "MAIN"` at `document_start`. Generic, no per-site code.

const SHADOW_OPEN_PATCH_ID = "anticipy_shadow_open_patch";
const SHADOW_OPEN_PATCH_SRC = `
(() => {
  try {
    if (window.__anticipy_shadow_open_installed__) return;
    window.__anticipy_shadow_open_installed__ = true;
    const orig = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function (init) {
      try {
        const opts = Object.assign({}, init || {}, { mode: "open" });
        return orig.call(this, opts);
      } catch (_) {
        return orig.call(this, init);
      }
    };
  } catch (_) {}
})();
`;

async function ensureShadowOpenScript() {
  try {
    const existing = await chrome.scripting.getRegisteredContentScripts({
      ids: [SHADOW_OPEN_PATCH_ID]
    });
    if (existing && existing.length > 0) return;
    await chrome.scripting.registerContentScripts([{
      id: SHADOW_OPEN_PATCH_ID,
      js: undefined,                         // (we use `code` via update below)
      matches: ["<all_urls>"],
      runAt: "document_start",
      world: "MAIN",
      allFrames: true,
      persistAcrossSessions: false,
      // Chrome MV3: `code` not allowed in registerContentScripts; use a file.
      // We emit a tiny patch.js at install time instead — see chrome.runtime.onInstalled.
    }]);
  } catch (e) {
    // Fall through: extension still works for open shadow roots without this.
    console.warn("[Anticipy] shadow-open patch register failed:", e?.message);
  }
}

// MV3 quirk: registerContentScripts requires a JS file path, not inline code.
// Workaround: ship the patch as a static file (extension/world_patch.js) and
// register it. We materialize it from the constant if missing via writing
// nothing — the patch file is shipped alongside content.js (created below).

async function ensureShadowOpenRegistered() {
  try {
    const existing = await chrome.scripting.getRegisteredContentScripts({
      ids: [SHADOW_OPEN_PATCH_ID]
    });
    if (!existing || existing.length === 0) {
      await chrome.scripting.registerContentScripts([{
        id: SHADOW_OPEN_PATCH_ID,
        js: ["world_patch.js"],
        matches: ["<all_urls>"],
        runAt: "document_start",
        world: "MAIN",
        allFrames: true,
        persistAcrossSessions: true,
      }]);
      console.log("[Anticipy] shadow-open MAIN-world patch registered");
    }
  } catch (e) {
    console.warn("[Anticipy] shadow-open register failed:", e?.message);
  }
}

// Register on every SW boot path: install, startup, and module-load (covers
// Playwright fresh-profile loads where neither install nor startup fire reliably).
chrome.runtime.onInstalled.addListener(ensureShadowOpenRegistered);
chrome.runtime.onStartup.addListener(ensureShadowOpenRegistered);
ensureShadowOpenRegistered();

// ─── Keep-alive alarm (MV3 kills SW after ~30s idle) ──────────────────────────
chrome.alarms.create("keepalive", { periodInMinutes: 0.4 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "keepalive") {
    if (realtimeWs?.readyState === WebSocket.OPEN) {
      heartbeatRef++;
      realtimeWs.send(JSON.stringify({
        topic: "phoenix",
        event: "heartbeat",
        payload: {},
        ref: String(heartbeatRef)
      }));
    } else {
      connectRealtime();
    }
  }
});

// ─── Supabase Realtime connection ─────────────────────────────────────────────

function connectRealtime() {
  if (realtimeWs && (
    realtimeWs.readyState === WebSocket.OPEN ||
    realtimeWs.readyState === WebSocket.CONNECTING
  )) return;

  const wsUrl =
    SUPABASE_URL.replace("https://", "wss://") +
    "/realtime/v1/websocket?apikey=" + SUPABASE_ANON_KEY + "&vsn=1.0.0";

  try {
    realtimeWs = new WebSocket(wsUrl);

    realtimeWs.onopen = () => {
      connected = true;
      updateBadge("connected");
      console.log("[Anticipy] Realtime connected");

      // Channel 1: postgres_changes on anticipy_intents (works if RLS allows anon SELECT)
      joinRef++;
      realtimeWs.send(JSON.stringify({
        topic: "realtime:anticipy_db",
        event: "phx_join",
        payload: {
          config: {
            broadcast: { self: false },
            postgres_changes: [
              { event: "INSERT", schema: "public", table: "anticipy_intents" },
              { event: "UPDATE", schema: "public", table: "anticipy_intents" }
            ]
          },
          access_token: SUPABASE_ANON_KEY
        },
        ref: String(joinRef)
      }));

      // Channel 2: broadcast on "anticipy-intents" (no RLS, always works)
      joinRef++;
      realtimeWs.send(JSON.stringify({
        topic: "realtime:anticipy-intents",
        event: "phx_join",
        payload: {
          config: {
            broadcast: { self: true },
          },
          access_token: SUPABASE_ANON_KEY
        },
        ref: String(joinRef)
      }));
    };

    realtimeWs.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.event === "phx_reply" && msg.payload?.status === "ok") {
          console.log("[Anticipy] Channel joined");
          return;
        }

        if (msg.event === "system" && msg.payload?.status === "ok") return;

        // postgres_changes events (if RLS allows)
        if (msg.event === "postgres_changes") {
          const change = msg.payload?.data;
          if (!change) return;
          if (change.type === "INSERT" && change.record?.summary_for_user) {
            handleNewIntent(change.record);
          } else if (change.type === "UPDATE" && change.record?.status === "confirmed") {
            handleConfirmedIntent(change.record);
          }
          return;
        }

        // Broadcast events (no RLS, reliable)
        if (msg.event === "broadcast") {
          const inner = msg.payload;
          console.log("[Anticipy] broadcast event:", inner?.event, "id:", inner?.payload?.id);
          if (inner?.event === "new_intent" && inner?.payload?.summary_for_user) {
            handleNewIntent(inner.payload);
          }
          if (inner?.event === "confirmed_intent" && inner?.payload?.id) {
            handleConfirmedIntent(inner.payload);
          }
          return;
        }

        // Legacy: some Supabase versions send event type directly
        if (msg.event === "INSERT") {
          const record = msg.payload?.record || msg.payload;
          if (record?.summary_for_user) handleNewIntent(record);
        }
      } catch {
        // Heartbeat responses, non-JSON frames — ignore
      }
    };

    realtimeWs.onclose = () => {
      connected = false;
      realtimeWs = null;
      updateBadge("disconnected");
      console.log("[Anticipy] Realtime disconnected — reconnecting in 5s");
      setTimeout(connectRealtime, 5000);
    };

    realtimeWs.onerror = () => {
      connected = false;
      updateBadge("disconnected");
      // onclose fires after onerror; reconnect happens there
    };
  } catch (e) {
    console.error("[Anticipy] WebSocket setup failed:", e);
    connected = false;
    updateBadge("disconnected");
    setTimeout(connectRealtime, 10_000);
  }
}

// ─── Intent handlers ─────────────────────────────────────────────────────────

async function intentBelongsToUs(intent) {
  // The anticipy-intents broadcast topic is anon-readable — every connected
  // extension worldwide receives every broadcast. Without this filter, user
  // A's extension would fire a notification + run an agent task on user B's
  // intent. /api/engine/analyze and /api/engine/confirm both stamp the
  // payload with `user_id`; we compare against the userId the popup stored
  // at login time.
  //
  // Fail-CLOSED: if either side of the comparison is missing or doesn't
  // match, drop the event. The cost of dropping a legit event for an
  // unauthenticated extension is one missed notification (the user can
  // re-open the engine page); the cost of accepting a foreign event is
  // every Anticipy user's tasks running on every other user's machine.
  if (!intent || typeof intent !== "object") return false;
  const incomingUserId = intent.user_id;
  if (!incomingUserId) return false;
  const { apiConfig } = await chrome.storage.local.get("apiConfig");
  const ourUserId = apiConfig?.userId;
  if (!ourUserId) return false;
  return incomingUserId === ourUserId;
}

async function handleNewIntent(intent) {
  if (!(await intentBelongsToUs(intent))) {
    return;
  }
  // Guard against fan-out: the SW joins both postgres_changes and broadcast
  // channels, and an INSERT typically arrives via both within a few ms. The
  // synchronous Set.add() races nothing — first event wins, second no-ops.
  if (trackSeen(seenNewIntentIds, intent.id)) {
    console.log("[Anticipy] handleNewIntent: duplicate event for", intent.id, "— skipping");
    return;
  }

  lastActions.unshift({
    id: intent.id,
    summary: intent.summary_for_user,
    importance: intent.importance,
    action_type: intent.action_type,
    status: intent.status,
    confidence: intent.confidence,
    evidence_quote: intent.evidence_quote,
    timestamp: new Date().toISOString()
  });
  lastActions = lastActions.slice(0, 10);
  chrome.storage.local.set({ lastActions });

  const cfg = {
    critical: { emoji: "🔴", priority: 2, requireInteraction: true },
    important: { emoji: "🟠", priority: 1, requireInteraction: false },
    standard: { emoji: "🟡", priority: 0, requireInteraction: false },
    low: { emoji: "⚪", priority: 0, requireInteraction: false }
  }[intent.importance] || { emoji: "🟡", priority: 0, requireInteraction: false };

  chrome.notifications.create(intent.id || `intent-${Date.now()}`, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: `${cfg.emoji} Anticipy`,
    message: intent.summary_for_user || "New action detected",
    priority: cfg.priority,
    requireInteraction: cfg.requireInteraction
  });

  chrome.action.setBadgeText({ text: String(lastActions.length) });
  chrome.action.setBadgeBackgroundColor({ color: "#C8A97E" });
}

async function handleConfirmedIntent(intent) {
  if (!intent?.id) return;
  if (!(await intentBelongsToUs(intent))) {
    // Cross-user broadcast — drop. See intentBelongsToUs() docstring.
    return;
  }

  // Synchronous in-memory guard — wins the race against the second
  // Realtime event (postgres_changes UPDATE vs broadcast confirmed_intent
  // for the same row arriving within a few ms). Without this, both events
  // pass the chrome.storage.local.get() check below before either's
  // .set() lands, and we run TWO BrowserAgents on the same task.
  if (trackSeen(seenConfirmedIntentIds, intent.id)) {
    console.log("[Anticipy] handleConfirmedIntent: duplicate event for", intent.id, "— skipping");
    return;
  }

  // Cross-restart guard — covers SW termination + reconnect replays.
  // The in-memory Set above is the fast path; this is the durable backup.
  const dedupKey = `executed_${intent.id}`;
  const stored = await chrome.storage.local.get(dedupKey);
  if (stored[dedupKey]) {
    console.log("[Anticipy] already executed intent", intent.id);
    return;
  }
  await chrome.storage.local.set({ [dedupKey]: true });

  console.log("[Anticipy] confirmed intent → agent:", intent.id, (intent.summary_for_user || "").substring(0, 80));

  // Load API keys from storage
  const { apiConfig } = await chrome.storage.local.get("apiConfig");

  if (!apiConfig?.groqApiKey && !apiConfig?.geminiApiKey) {
    chrome.notifications.create(`nokeys-${intent.id}`, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "⚠️ Anticipy — Not signed in",
      message: "Click the Anticipy extension icon and sign in to enable browser automation.",
      priority: 1,
      requireInteraction: true
    });
    // Remove BOTH dedup layers so user can retry after signing in.
    seenConfirmedIntentIds.delete(intent.id);
    await chrome.storage.local.remove(dedupKey);
    return;
  }

  // Run the browser agent
  const agent = new BrowserAgent(intent, apiConfig);
  const result = await agent.run();

  // Update Supabase with the outcome
  await updateIntentInSupabase(intent.id, result);

  // Show result notification
  chrome.notifications.create(`done-${intent.id}`, {
    type: "basic",
    iconUrl: "icons/icon128.png",
    title: result.success ? "✅ Anticipy done" : "⚠️ Anticipy",
    message: result.message || (result.success ? "Task completed." : "Task could not be completed."),
    priority: result.success ? 0 : 1
  });
}

// ─── Supabase REST update ──────────────────────────────────────────────────────

async function updateIntentInSupabase(intentId, result) {
  // Two-step PATCH: status first (required, schema-checked), then optional
  // execution_result. If the result column ever drifts again the status will
  // still land — defense in depth against schema/code skew.
  const baseHeaders = {
    "Content-Type": "application/json",
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
    "Prefer": "return=minimal"
  };
  const status = result.success ? "executed" : "failed";
  try {
    await fetch(
      `${SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.${intentId}`,
      { method: "PATCH", headers: baseHeaders, body: JSON.stringify({ status }) }
    );
  } catch (e) {
    console.warn("[Anticipy] Could not update intent status:", e.message);
  }
  try {
    await fetch(
      `${SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.${intentId}`,
      {
        method: "PATCH", headers: baseHeaders,
        body: JSON.stringify({
          execution_result: result.message || null,
          executed_at: new Date().toISOString(),
        })
      }
    );
  } catch (e) {
    console.warn("[Anticipy] Could not update intent result:", e.message);
  }
}

// ─── Badge helper ─────────────────────────────────────────────────────────────

function updateBadge(status) {
  if (status === "connected") {
    chrome.action.setBadgeBackgroundColor({ color: "#4CAF50" });
    chrome.action.setBadgeText({ text: "" });
  } else {
    chrome.action.setBadgeBackgroundColor({ color: "#FF5252" });
    chrome.action.setBadgeText({ text: "!" });
  }
  chrome.storage.local.set({ connectionStatus: status });
}

// ─── Message handlers (popup ↔ background) ────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === "GET_STATUS") {
    sendResponse({ connected, lastActions, wsState: realtimeWs?.readyState ?? -1 });
    return true;
  }

  if (message.type === "RECONNECT") {
    if (realtimeWs) { realtimeWs.close(); realtimeWs = null; }
    connectRealtime();
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "CLEAR_ACTIONS") {
    lastActions = [];
    chrome.storage.local.set({ lastActions: [] });
    chrome.action.setBadgeText({ text: "" });
    sendResponse({ ok: true });
    return true;
  }

  // ─── Tab management routed through SW (chrome.tabs lives here, not in
  //     content scripts). Generic capabilities — the LLM agent decides when
  //     to use them. ──────────────────────────────────────────────────────
  if (message.type === "TABS_OPEN") {
    chrome.tabs.create({ url: message.url, active: message.active !== false }, (tab) => {
      if (chrome.runtime.lastError) {
        sendResponse({ success: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse({ success: true, tabId: tab.id, url: tab.url });
      }
    });
    return true;
  }
  if (message.type === "TABS_LIST") {
    chrome.tabs.query({}, (tabs) => {
      sendResponse({
        success: true,
        tabs: tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: t.active })),
      });
    });
    return true;
  }
  if (message.type === "TABS_SWITCH") {
    chrome.tabs.update(message.tabId, { active: true }, (tab) => {
      if (chrome.runtime.lastError) {
        sendResponse({ success: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse({ success: true, tabId: tab?.id });
      }
    });
    return true;
  }
  if (message.type === "TABS_CLOSE") {
    chrome.tabs.remove(message.tabId, () => {
      if (chrome.runtime.lastError) {
        sendResponse({ success: false, error: chrome.runtime.lastError.message });
      } else {
        sendResponse({ success: true });
      }
    });
    return true;
  }

  // Backstop: content script asks for a MAIN-world inject of the shadow-open
  // patch into its own tab. Useful when the persistent registerContentScripts
  // hadn't applied yet at first navigation.
  if (message.type === "INJECT_SHADOW_PATCH" && _sender?.tab?.id) {
    chrome.scripting.executeScript({
      target: { tabId: _sender.tab.id, allFrames: true },
      world: "MAIN",
      files: ["world_patch.js"],
    }).catch((e) => console.warn("[Anticipy] inject shadow patch failed:", e?.message));
    sendResponse({ ok: true });
    return true;
  }

  // Forward a single DOM action to the active tab's content script (used for manual testing)
  if (message.type === "EXECUTE_DOM_ACTION") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, { type: "DOM_ACTION", action: message.action }, sendResponse);
      } else {
        sendResponse({ success: false, error: "No active tab" });
      }
    });
    return true;
  }
});

// ─── Notification click — open engine page ────────────────────────────────────

chrome.notifications.onClicked.addListener((notificationId) => {
  chrome.tabs.create({ url: "https://www.anticipy.ai/engine" });
  chrome.notifications.clear(notificationId);
});

// ─── Lifecycle ────────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  console.log("[Anticipy] Extension installed");
  connectRealtime();
});

chrome.runtime.onStartup.addListener(() => {
  console.log("[Anticipy] Extension started");
  connectRealtime();
});

connectRealtime();
