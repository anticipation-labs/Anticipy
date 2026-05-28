import { readFileSync, existsSync } from "fs";
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^"|"$/g, "");
  }
}

async function main() {
  const { callGemini } = await import("../src/lib/gemini");
  try {
    const t0 = Date.now();
    const resp = await callGemini(
      [
        { role: "system", content: 'Return strict JSON: {"ok": true}' },
        { role: "user", content: "ping" },
      ],
      { temperature: 0, max_tokens: 50 }
    );
    console.log(`OK in ${Date.now() - t0}ms, length=${resp.length}: ${resp.slice(0, 200)}`);
  } catch (e) {
    console.error("THREW:", e instanceof Error ? e.message : e);
  }
}

main();
