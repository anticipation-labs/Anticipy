// Shared engine client. Runs both inside the MV3 service worker (as a global,
// via importScripts) and in Node (via require) so the connect logic is testable
// headlessly against the live engine. `fetch` is available in both.

async function connectToEngine(baseUrl) {
  const health = await fetch(baseUrl + "/health").then((r) => r.json());
  if (health.service !== "anticipy-engine") {
    throw new Error("not the Anticipy engine on " + baseUrl);
  }
  const hello = await fetch(baseUrl + "/extension/hello", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ client: "chrome-extension" }),
  }).then((r) => r.json());
  return { connected: hello.connected === true, version: health.version };
}

// Node test harness imports this; the service worker reads it as a global.
if (typeof module !== "undefined" && module.exports) {
  module.exports = { connectToEngine };
}
