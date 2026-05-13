import { readFileSync, existsSync } from "fs";
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}
process.env.GOOGLE_API_KEY = "INVALID-FORCE-FAIL";
process.env.GROQ_API_KEY = "INVALID-FORCE-FAIL";

async function main() {
  const { callLlmCascade } = await import("../src/lib/llm-cascade");
  const t0 = Date.now();
  const result = await callLlmCascade(
    [
      { role: "system", content: 'Return strict JSON: {"verb":"pong","ok":true}' },
      { role: "user", content: "ping" },
    ],
    { temperature: 0, max_tokens: 50, jsonOnly: true }
  );
  console.log(`[planC-probe] provider=${result.provider} latency=${Date.now()-t0}ms`);
  console.log(`[planC-probe] text=${result.text.slice(0, 100)}`);
  console.log(`[planC-probe] errors=${JSON.stringify(result.errors).slice(0, 200)}`);
  if (result.provider === "none") process.exit(1);
  if (result.provider !== "mistral" && result.provider !== "deepseek") {
    console.error(`FAIL: should have fallen to mistral or deepseek, got ${result.provider}`);
    process.exit(1);
  }
  console.log(`OK: cascade fell off Gemini+Groq → ${result.provider}`);
}
main().catch(e => { console.error(e); process.exit(1); });
