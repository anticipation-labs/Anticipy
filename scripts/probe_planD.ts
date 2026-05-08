import { readFileSync, existsSync } from "fs";
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}
process.env.GOOGLE_API_KEY = "INVALID-FORCE-FAIL";
process.env.GROQ_API_KEY = "INVALID-FORCE-FAIL";
process.env.KIMI_API_KEY = "INVALID-FORCE-FAIL";

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
  console.log(`[planD-probe] provider=${result.provider} latency=${Date.now()-t0}ms`);
  console.log(`[planD-probe] text=${result.text.slice(0, 100)}`);
  console.log(`[planD-probe] errors keys=${Object.keys(result.errors).join(",")}`);
  if (result.provider === "deepseek") {
    console.log("OK: Plan D (DeepSeek) functional");
  } else if (result.provider === "none") {
    console.log("DOC: Plan D unavailable. Errors:");
    for (const [k, v] of Object.entries(result.errors)) {
      console.log(`  ${k}: ${(v as string).slice(0, 120)}`);
    }
  } else {
    console.error(`UNEXPECTED: provider=${result.provider}, expected deepseek or none`);
  }
}
main().catch(e => { console.error(e); process.exit(1); });
