// The hosted Railway setup page is the one consumer-facing ceremony for this
// extension. This bridge runs only when background.js has confirmed the page's
// exact origin/path against the configured backend. It publishes setup state,
// never the agent credential or the owner's identity.
(function installAnticipySetupBridge() {
  if (globalThis.__anticipySetupBridgeInstalled) return;
  globalThis.__anticipySetupBridgeInstalled = true;

  async function publish() {
    try {
      const state = await chrome.runtime.sendMessage({ type: "anticipy-setup-state" });
      window.postMessage({
        type: "anticipy-setup-state",
        source: "anticipy-extension",
        installed: true,
        code: state?.code || "",
        linked: !!state?.linked,
      }, window.location.origin);
    } catch (_) {
      // A worker may be restarting. The page remains in its honest waiting
      // state, and the next page request or storage change tries again.
    }
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window || event.origin !== window.location.origin) return;
    if (event.data?.source === "anticipy-page"
        && event.data?.type === "anticipy-setup-request") publish();
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes.pairCode || changes.paired || changes.ownerRef || changes.recordId) publish();
  });
  publish();
})();
