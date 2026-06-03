// Room 4: the hands (stub). On load, connect to the local engine and remember
// the result. No browser driving yet — that's the action chunk.
importScripts("engine_client.js");

const ENGINE = "http://127.0.0.1:8787";
let state = { connected: false };

async function boot() {
  try {
    const r = await connectToEngine(ENGINE);
    state = { connected: r.connected, version: r.version };
    console.log("[anticipy] connected to engine", r);
  } catch (e) {
    state = { connected: false, error: String(e) };
    console.log("[anticipy] engine offline:", String(e));
  }
}

chrome.runtime.onInstalled.addListener(boot);
chrome.runtime.onStartup.addListener(boot);
boot();

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg === "status") sendResponse(state);
  return true;
});
