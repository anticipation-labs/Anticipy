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

chrome.runtime.onInstalled.addListener(async () => {
  try {
    // Best-effort registration — silently no-ops if file isn't available.
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
});

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

function handleNewIntent(intent) {
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

  // Deduplicate: never execute the same intent twice in one session
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
    // Remove dedup so user can retry after signing in
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
  try {
    await fetch(
      `${SUPABASE_URL}/rest/v1/anticipy_intents?id=eq.${intentId}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "apikey": SUPABASE_ANON_KEY,
          "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
          "Prefer": "return=minimal"
        },
        body: JSON.stringify({
          status: result.success ? "completed" : "failed",
          execution_result: result.message || null
        })
      }
    );
  } catch (e) {
    console.warn("[Anticipy] Could not update intent in Supabase:", e.message);
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
