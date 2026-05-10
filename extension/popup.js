// Anticipy Chrome Extension — Popup Script

const AUTH_ENDPOINT = "https://www.anticipy.ai/api/extension/auth";

document.addEventListener("DOMContentLoaded", () => {
  const statusDot      = document.getElementById("statusDot");
  const statusText     = document.getElementById("statusText");
  const reconnectBtn   = document.getElementById("reconnectBtn");
  const authPanel      = document.getElementById("authPanel");
  const signedInBanner = document.getElementById("signedInBanner");
  const signOutBtn     = document.getElementById("signOutBtn");
  const agentBanner    = document.getElementById("agentBanner");
  const agentDot       = document.getElementById("agentDot");
  const agentLabel     = document.getElementById("agentLabel");
  const agentMsg       = document.getElementById("agentMsg");
  const actionsContainer = document.getElementById("actionsContainer");
  const emptyState     = document.getElementById("emptyState");
  const openEngine     = document.getElementById("openEngine");
  const accessCodeInput = document.getElementById("accessCode");
  const signInBtn      = document.getElementById("signInBtn");
  const authError      = document.getElementById("authError");

  // ─── Boot ─────────────────────────────────────────────────────────────────

  chrome.storage.local.get(
    ["connectionStatus", "lastActions", "apiConfig", "agentStatus"],
    (data) => {
      const authenticated = !!(data.apiConfig?.groqApiKey || data.apiConfig?.geminiApiKey);
      setAuthState(authenticated);

      if (data.connectionStatus) updateStatus(data.connectionStatus === "connected");
      if (data.lastActions?.length) renderActions(data.lastActions);
      if (data.agentStatus) renderAgentStatus(data.agentStatus);
    }
  );

  // Also fetch live status from background
  chrome.runtime.sendMessage({ type: "GET_STATUS" }, (response) => {
    if (chrome.runtime.lastError || !response) return;
    updateStatus(response.connected);
    if (response.lastActions?.length) renderActions(response.lastActions);
  });

  // ─── Auth ──────────────────────────────────────────────────────────────────

  function setAuthState(authenticated) {
    if (authenticated) {
      authPanel.style.display = "none";
      signedInBanner.classList.add("show");
    } else {
      authPanel.style.display = "block";
      signedInBanner.classList.remove("show");
    }
  }

  signInBtn.addEventListener("click", async () => {
    const code = accessCodeInput.value.trim();
    if (!code) { showAuthError("Enter your access code."); return; }

    signInBtn.disabled = true;
    signInBtn.textContent = "Connecting…";
    hideAuthError();

    try {
      const resp = await fetch(AUTH_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });

      const data = await resp.json().catch(() => ({}));

      if (!resp.ok) {
        // Map any HTTP error to friendly copy. Investors should never see
        // "Error 401" or other raw HTTP statuses in the popup.
        let msg;
        if (resp.status === 401 || /invalid/i.test(data.error || "")) {
          msg = "That code didn't match. Double-check it on anticipy.ai/engine.";
        } else if (resp.status >= 500) {
          msg = "Anticipy is having a moment. Try again in a sec.";
        } else if (resp.status === 429) {
          msg = "Too many tries — wait a moment and try again.";
        } else {
          msg = "Couldn't connect. Check your access code and try again.";
        }
        showAuthError(msg);
        return;
      }

      if (!data.groqApiKey && !data.geminiApiKey) {
        showAuthError("Couldn't connect. Try again in a moment.");
        return;
      }

      await chrome.storage.local.set({
        apiConfig: {
          // 5-tier provider redundancy. Plan A: Cerebras Qwen3-235B
          // (fastest, free 1M tokens/day, primary). Plan B: Groq llama-
          // 3.3-70b text + llama-4-scout vision (free 14400 RPD, vision-
          // capable fallback). Plan C: Gemini 2.5 Flash. Plan D: Kimi
          // moonshot-v1-128k (paid). Plan E: DeepSeek (paid).
          cerebrasApiKey: data.cerebrasApiKey || null,
          groqApiKey: data.groqApiKey || null,
          geminiApiKey: data.geminiApiKey || null,
          kimiApiKey: data.kimiApiKey || null,
          deepseekApiKey: data.deepseekApiKey || null,
          // userId required so the SW can filter Realtime broadcasts and
          // never act on another user's intent. anticipy-intents is an
          // anon-readable topic — every connected extension gets every
          // broadcast — and without this we'd cross-fire on shared infra.
          userId: data.userId || null,
          username: data.username || null,
          // Stored so the BrowserAgent can call /api/extension/llm-proxy
          // for tier-2 Claude escalation without re-prompting the user.
          // The code is the same one already used to sign in.
          accessCode: code,
          proxyBaseUrl: "https://www.anticipy.ai"
        }
      });

      setAuthState(true);
    } catch {
      showAuthError("Could not reach anticipy.ai. Check your connection.");
    } finally {
      signInBtn.disabled = false;
      signInBtn.textContent = "Connect";
    }
  });

  // Allow Enter key in the access code field
  accessCodeInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") signInBtn.click();
  });

  signOutBtn.addEventListener("click", async () => {
    await chrome.storage.local.remove(["apiConfig", "agentStatus"]);
    setAuthState(false);
    agentBanner.classList.remove("show");
  });

  function showAuthError(msg) {
    authError.textContent = msg;
    authError.classList.add("show");
  }
  function hideAuthError() {
    authError.classList.remove("show");
  }

  // ─── Connection status ────────────────────────────────────────────────────

  function updateStatus(isConnected) {
    statusDot.className = "status-dot " + (isConnected ? "connected" : "disconnected");
    statusText.textContent = isConnected ? "Connected" : "Reconnecting";
    reconnectBtn.className = "reconnect-btn" + (isConnected ? "" : " show");
  }

  reconnectBtn.addEventListener("click", () => {
    reconnectBtn.textContent = "Reconnecting…";
    chrome.runtime.sendMessage({ type: "RECONNECT" }, () => {
      setTimeout(() => {
        chrome.runtime.sendMessage({ type: "GET_STATUS" }, (response) => {
          if (response) updateStatus(response.connected);
          reconnectBtn.textContent = "Reconnect";
        });
      }, 2000);
    });
  });

  // ─── Agent status banner ──────────────────────────────────────────────────

  function renderAgentStatus(agentStatus) {
    if (!agentStatus) { agentBanner.classList.remove("show"); return; }

    const { status, message } = agentStatus;
    agentBanner.className = `show ${status}`; // add status class for color
    agentBanner.classList.add("show");
    agentDot.className = `agent-dot ${status}`;
    agentLabel.textContent = status === "running" ? "Agent running" : status === "done" ? "Agent done" : "Agent failed";
    agentMsg.textContent = message || "—";
  }

  // ─── Actions list ─────────────────────────────────────────────────────────

  function renderActions(actions) {
    emptyState.style.display = "none";
    actionsContainer.innerHTML = "";

    const header = document.createElement("div");
    header.className = "actions-header";

    const label = document.createElement("div");
    label.className = "actions-label";
    label.textContent = `Recent (${actions.length})`;

    const clearBtn = document.createElement("button");
    clearBtn.className = "clear-btn";
    clearBtn.textContent = "Clear";
    clearBtn.addEventListener("click", () => {
      chrome.runtime.sendMessage({ type: "CLEAR_ACTIONS" }, () => {
        actionsContainer.innerHTML = "";
        actionsContainer.appendChild(emptyState);
        emptyState.style.display = "block";
      });
    });

    header.appendChild(label);
    header.appendChild(clearBtn);
    actionsContainer.appendChild(header);

    for (const action of actions) {
      const item = document.createElement("div");
      item.className = "action-item";

      const top = document.createElement("div");
      top.className = "action-top";

      const badge = document.createElement("span");
      badge.className = `action-badge badge-${action.importance || "standard"}`;
      badge.textContent = action.importance || "standard";

      const conf = document.createElement("span");
      conf.className = "action-confidence";
      conf.textContent = action.confidence ? `${Math.round(action.confidence * 100)}%` : "";

      top.appendChild(badge);
      top.appendChild(conf);

      const summary = document.createElement("div");
      summary.className = "action-summary";
      summary.textContent = action.summary;

      const meta = document.createElement("div");
      meta.className = "action-meta";

      const type = document.createElement("span");
      type.className = "action-type";
      type.textContent = (action.action_type || "").replace(/_/g, " ");

      const time = document.createElement("span");
      time.className = "action-time";
      time.textContent = relativeTime(action.timestamp);

      meta.appendChild(type);
      meta.appendChild(time);

      item.appendChild(top);
      item.appendChild(summary);
      item.appendChild(meta);
      actionsContainer.appendChild(item);
    }
  }

  function relativeTime(isoString) {
    if (!isoString) return "";
    const diff = Date.now() - new Date(isoString).getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "Just now";
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    return new Date(isoString).toLocaleDateString();
  }

  // ─── Footer ───────────────────────────────────────────────────────────────

  openEngine.addEventListener("click", () => {
    chrome.tabs.create({ url: "https://www.anticipy.ai/engine" });
    window.close();
  });

  // Also open engine from the "get code" link in auth panel
  const getCodeLink = document.getElementById("getCodeLink");
  if (getCodeLink) {
    getCodeLink.addEventListener("click", (e) => {
      e.preventDefault();
      chrome.tabs.create({ url: "https://www.anticipy.ai/engine" });
      window.close();
    });
  }

  // ─── Poll agent status every 2s while popup is open ───────────────────────
  const statusPoll = setInterval(() => {
    chrome.storage.local.get("agentStatus", ({ agentStatus }) => {
      renderAgentStatus(agentStatus || null);
    });
  }, 2000);

  window.addEventListener("unload", () => clearInterval(statusPoll));
});
