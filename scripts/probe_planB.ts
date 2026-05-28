import { readFileSync, existsSync } from "fs";
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}
// Force Plan A failure to verify Plan B is reachable
process.env.GOOGLE_API_KEY = "INVALID-FORCE-FAIL";

async function main() {
  const { callLlmCascade } = await import("../src/lib/llm-cascade");
  const t0 = Date.now();
  const result = await callLlmCascade(
    [
      { role: "system", content: 'Return strict JSON: {"verb":"ping","ok":true}' },
      { role: "user", content: "ping" },
    ],
    { temperature: 0, max_tokens: 50, jsonOnly: true }
  );
  console.log(`[planB-probe] provider=${result.provider} latency=${Date.now()-t0}ms`);
  console.log(`[planB-probe] text=${result.text.slice(0, 100)}`);
  console.log(`[planB-probe] errors=${JSON.stringify(result.errors)}`);
  if (result.provider === "none") process.exit(1);
  if (result.provider === "gemini") {
    console.error("FAIL: should have fallen off Gemini (key invalidated)");
    process.exit(1);
  }
  console.log(`OK: cascade fell off Gemini → ${result.provider}`);
}
main().catch(e => { console.error(e); process.exit(1); });
