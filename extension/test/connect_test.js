// Room 4 test: runs the extension's REAL connect logic against the live engine.
// Usage: node connect_test.js <engineBaseUrl>
const assert = require("assert");
const { connectToEngine } = require("../engine_client.js");

const base = process.argv[2] || "http://127.0.0.1:8787";

(async () => {
  const r = await connectToEngine(base);
  assert.strictEqual(r.connected, true, "extension should report connected");
  assert.ok(r.version, "engine version should be reported");
  console.log("PASS room 4: extension connected to engine ->", JSON.stringify(r));
})().catch((e) => {
  console.error("FAIL room 4:", e.message);
  process.exit(1);
});
