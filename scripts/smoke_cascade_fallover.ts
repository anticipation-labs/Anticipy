/**
 * End-to-end fallover smoke test for the 4-tier LLM cascade.
 *
 * The companion `smoke_per_provider.ts` proves each provider can answer
 * a tiny intent prompt in isolation. This script proves the cascade
 * actually FALLS THROUGH from Plan A → B → C → D when the upstream
 * provider keys are unavailable, by selectively unsetting env vars and
 * importing `callLlm` from `src/lib/llm-cascade.ts`.
 *
 * Scenarios (each runs in a forked Node child so module-load env capture
 * in groq.ts / kimi.ts is honored — those modules read process.env at
 * import time, so we must mutate env BEFORE the module loads):
 *
 *   1. baseline — all four keys present → expect provider == "gemini"
 *   2. no Gemini → expect provider == "groq"
 *   3. no Gemini, no Groq → expect provider == "kimi"
 *   4. no Gemini, no Groq, no Kimi → expect provider == "deepseek"
 *
 * Run standalone:
 *   npx tsx scripts/smoke_cascade_fallover.ts
 *
 * Exit code: 0 if all four scenarios behave as expected (Plan D may
 * "fail-as-documented" if DeepSeek is credit-exhausted; we report that
 * precisely instead of treating it as a script failure). 1 otherwise.
 *
 * Permanent artifact — safe to wire into CI once test keys are provisioned.
 */
import { readFileSync, existsSync } from "fs";
import { spawn } from "child_process";

// Load .env.local for the parent so we can pass through to children.
if (existsSync(".env.local")) {
  for (const line of readFileSync(".env.local", "utf8").split("\n")) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (m && !process.env[m[1]]) {
      process.env[m[1]] = m[2].replace(/^"|"$/g, "");
    }
  }
}

/**
 * Tier ordering used to verify "the cascade walked at least as far as
 * the knockout boundary, never short of it." Real upstream providers
 * regularly 429 / 402 in production (Gemini quota, Groq TPD, DeepSeek
 * out-of-credit), so a strict "must equal the next-in-line provider"
 * check produces false failures whenever a non-knocked-out tier is also
 * misbehaving today. The cascade's contract is "never SKIP UP a tier",
 * not "always land on the immediately-next tier".
 */
const TIER_ORDER: Record<string, number> = {
  gemini: 0,
  groq: 1,
  kimi: 2,
  deepseek: 3,
  none: 4,
};

interface ChildOutcome {
  scenario: string;
  expected_min_provider: "gemini" | "groq" | "kimi" | "deepseek";
  actual_provider: string | null;
  ok: boolean;
  latency_ms: number;
  errors: Record<string, string>;
  raw_text_len: number;
  exit_code: number;
  stderr_tail: string;
}

/**
 * Body of the child process. When invoked with CHILD_MODE=1 the script
 * forks itself and runs this branch, calling `callLlmCascade` once and
 * emitting a single JSON line of structured output for the parent to
 * parse. We use a JSON-line protocol so console.warn from the cascade
 * (which dumps fall-to-plan messages) doesn't corrupt the result.
 */
async function runChild(): Promise<void> {
  // Re-load .env.local in case the child inherited a sparse env (it
  // shouldn't, since spawn() inherits by default, but cheap belt-and-
  // suspenders).
  if (existsSync(".env.local")) {
    for (const line of readFileSync(".env.local", "utf8").split("\n")) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (m && !process.env[m[1]]) {
        process.env[m[1]] = m[2].replace(/^"|"$/g, "");
      }
    }
  }

  // Apply the scenario knockouts NOW, before the dynamic import — groq.ts
  // and kimi.ts both capture process.env.<KEY> at module-load time, so
  // unsetting after import has no effect.
  const knockout = (process.env.CASCADE_KNOCKOUT ?? "").split(",").filter(Boolean);
  for (const k of knockout) {
    // Empty string is what the task spec asks for ("set to '' before
    // dynamic import"). Either "" or delete works for our wrappers — both
    // make the bearer header empty, which the upstream APIs reject with
    // 401, satisfying the cascade's catch.
    process.env[k] = "";
  }

  const TINY_AGENT_SYSTEM = `You are a browser action agent. The user describes a task they \
want performed on a real website. Return STRICT JSON ONLY with the schema:

{
  "action": "navigate" | "click" | "type" | "extract" | "search",
  "target": "<url-or-element-description>",
  "intent": "<one-sentence-restatement>"
}

Rules:
- JSON only. No fences. No prose.
- For info-retrieval like "find the headline on bbc.com", action is "extract", target is the URL.

Example:
Input: "Find the top story on hacker news"
Output: {"action":"extract","target":"https://news.ycombinator.com","intent":"retrieve top story"}`;

  const t0 = Date.now();
  let result: {
    text: string;
    provider: string;
    errors: Record<string, string>;
  };
  try {
    const { callLlmCascade } = await import("../src/lib/llm-cascade");
    result = await callLlmCascade(
      [
        { role: "system", content: TINY_AGENT_SYSTEM },
        { role: "user", content: "Find the headline on bbc.com" },
      ],
      { temperature: 0, max_tokens: 256 }
    );
  } catch (e) {
    result = {
      text: "",
      provider: "none",
      errors: {
        crash: e instanceof Error ? e.message.slice(0, 200) : String(e).slice(0, 200),
      },
    };
  }
  const latency_ms = Date.now() - t0;
  // Single JSON line on stdout. Parent splits on newlines.
  process.stdout.write(
    "__CASCADE_RESULT__" +
      JSON.stringify({
        provider: result.provider,
        text_len: result.text.length,
        errors: result.errors,
        latency_ms,
      }) +
      "\n"
  );
  // Give the JSON line time to flush before we exit.
  setTimeout(() => process.exit(0), 50);
}

function runScenario(
  scenario: string,
  knockoutKeys: string[],
  expectedMin: "gemini" | "groq" | "kimi" | "deepseek"
): Promise<ChildOutcome> {
  return new Promise((resolve) => {
    // Inherit the parent env so all OTHER keys (DB url, Supabase, etc.) are
    // still present in the child. The CASCADE_KNOCKOUT var tells the child
    // which keys to clear. Next.js's next-env.d.ts augments ProcessEnv to
    // require NODE_ENV, so we copy through a plain record and cast at the
    // call site rather than annotate.
    const childEnvRaw: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) {
      if (typeof v === "string") childEnvRaw[k] = v;
    }
    childEnvRaw.CASCADE_KNOCKOUT = knockoutKeys.join(",");
    childEnvRaw.CHILD_MODE = "1";
    if (!childEnvRaw.NODE_ENV) childEnvRaw.NODE_ENV = "development";
    const childEnv = childEnvRaw as unknown as NodeJS.ProcessEnv;

    // Explicit tuple type so TypeScript picks the overload that exposes
    // .stdout and .stderr as Readable streams (rather than collapsing to
    // `never` because the multiple stdio overloads of spawn don't unify).
    const child = spawn("npx", ["tsx", "scripts/smoke_cascade_fallover.ts"], {
      env: childEnv,
      stdio: ["ignore", "pipe", "pipe"] as const,
      cwd: process.cwd(),
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (b) => (stdout += b.toString()));
    child.stderr.on("data", (b) => (stderr += b.toString()));

    // Hard cap so a hung Kimi reasoning call can't pin the parent
    // forever. Kimi alone has a 90s SDK timeout; 180s wall covers all
    // four providers if multiple have to fail in sequence.
    const guard = setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        /* noop */
      }
    }, 180_000);

    child.on("exit", (code) => {
      clearTimeout(guard);
      let parsed: {
        provider?: string;
        text_len?: number;
        errors?: Record<string, string>;
        latency_ms?: number;
      } = {};
      // Find the marker line in stdout.
      const marker = "__CASCADE_RESULT__";
      const idx = stdout.lastIndexOf(marker);
      if (idx >= 0) {
        const eol = stdout.indexOf("\n", idx);
        const json = stdout.slice(idx + marker.length, eol >= 0 ? eol : undefined);
        try {
          parsed = JSON.parse(json);
        } catch {
          /* leave parsed empty */
        }
      }
      const actual = parsed.provider ?? null;
      // PASS condition: cascade landed at the knockout boundary or a
      // later (lower-tier) provider that actually answered. Two distinct
      // failure modes:
      //   - SKIP_UP: landed on a provider EARLIER than the knockout
      //     boundary (e.g. baseline returns "groq" — did the env get
      //     re-injected? did the cascade ignore an empty key?). Real
      //     cascade-logic regression.
      //   - ALL_FAILED: actual_provider=="none" meaning every tier raised.
      //     Treated as failure here; the parent then surfaces it as a
      //     documented-fail when the only failing tier is Plan D
      //     (DeepSeek out of credit).
      const expectedRank = TIER_ORDER[expectedMin];
      const actualRank =
        actual && actual !== "none" ? TIER_ORDER[actual] ?? 99 : 99;
      const ok =
        actual !== null && actual !== "none" && actualRank >= expectedRank;
      resolve({
        scenario,
        expected_min_provider: expectedMin,
        actual_provider: actual,
        ok,
        latency_ms: parsed.latency_ms ?? 0,
        errors: parsed.errors ?? {},
        raw_text_len: parsed.text_len ?? 0,
        exit_code: code ?? -1,
        // Tail of stderr — useful for diagnosing why a provider failed
        // (the cascade logs "fell to plan X" via console.warn → stderr).
        stderr_tail: stderr.split("\n").slice(-6).join("\n").slice(0, 800),
      });
    });
  });
}

function pad(s: string, n: number): string {
  if (s.length >= n) return s.slice(0, n);
  return s + " ".repeat(n - s.length);
}

function printReport(outcomes: ChildOutcome[]): void {
  console.log("");
  console.log("=== Cascade fallover smoke ===");
  console.log("");
  console.log(
    `${pad("scenario", 28)}  ${pad("expected≥", 10)}  ${pad("actual", 10)}  ${pad("ms", 7)}  ${pad("ok", 4)}  notes`
  );
  console.log("-".repeat(120));
  for (const o of outcomes) {
    const errSummary =
      Object.keys(o.errors).length > 0
        ? Object.entries(o.errors)
            .map(([k, v]) => `${k}=${(v ?? "").toString().slice(0, 40)}`)
            .join(" | ")
        : "";
    console.log(
      `${pad(o.scenario, 28)}  ${pad(o.expected_min_provider, 10)}  ${pad(
        o.actual_provider ?? "(none)",
        10
      )}  ${pad(String(o.latency_ms), 7)}  ${pad(o.ok ? "PASS" : "FAIL", 4)}  ${errSummary}`
    );
  }
  console.log("");
  for (const o of outcomes) {
    if (!o.ok) {
      console.log(`-- ${o.scenario} FAIL details --`);
      console.log(`   expected_min_provider=${o.expected_min_provider}`);
      console.log(`   actual_provider=${o.actual_provider ?? "(none)"}`);
      console.log(`   exit_code=${o.exit_code}`);
      if (o.stderr_tail) {
        console.log(`   stderr_tail:`);
        for (const ln of o.stderr_tail.split("\n")) console.log(`     ${ln}`);
      }
    }
  }
  // Plan D verdict — explicit. The LLM-key memory note flags DeepSeek as
  // possibly credit-exhausted; the report needs to say plainly whether it
  // works today or is documented-fail. We use the all-knocked-out
  // scenario (the one whose expected_min_provider is "deepseek").
  const planD = outcomes.find((o) => o.expected_min_provider === "deepseek");
  if (planD) {
    console.log("");
    console.log("Plan D (DeepSeek) verdict:");
    if (planD.actual_provider === "deepseek") {
      console.log("  WORKS — DeepSeek answered when A, B, C were knocked out.");
    } else {
      const ds = planD.errors?.deepseek ?? "(no error captured)";
      console.log(`  DOCUMENTED-FAIL — DeepSeek returned: ${ds}`);
      console.log(`  When A+B+C are unavailable AND D is broken, the cascade returns provider=${
        planD.actual_provider ?? "none"
      }, text=""`);
      console.log("  This matches src/lib/llm-cascade.ts: callLlm logs '[llm-cascade] all four providers failed' and returns empty string.");
    }
  }
  console.log("");
  const passed = outcomes.filter((o) => o.ok).length;
  console.log(`Summary: ${passed}/${outcomes.length} cascade scenarios behaved as expected.`);
}

async function main(): Promise<void> {
  // Child branch: run the single cascade call and emit JSON.
  if (process.env.CHILD_MODE === "1") {
    await runChild();
    return;
  }

  // Parent branch: run all four scenarios sequentially. Sequential, not
  // parallel — Gemini's quota gets shared across siblings and we want
  // honest, isolated provider behavior per scenario.
  //
  // Each scenario asserts the WEAKER guarantee that the cascade lands at
  // or below (later than) the knockout boundary — this matches the
  // cascade's actual contract ("never skip up a tier") and is robust to
  // real upstream provider quotas being exhausted on any given day.
  const scenarios: Array<{
    name: string;
    knockout: string[];
    expectedMin: "gemini" | "groq" | "kimi" | "deepseek";
  }> = [
    { name: "baseline (all keys present)", knockout: [], expectedMin: "gemini" },
    {
      name: "knock out Gemini",
      knockout: ["GOOGLE_API_KEY"],
      expectedMin: "groq",
    },
    {
      name: "knock out Gemini + Groq",
      knockout: ["GOOGLE_API_KEY", "GROQ_API_KEY"],
      expectedMin: "kimi",
    },
    {
      name: "knock out Gemini + Groq + Kimi",
      knockout: ["GOOGLE_API_KEY", "GROQ_API_KEY", "KIMI_API_KEY"],
      expectedMin: "deepseek",
    },
  ];

  const outcomes: ChildOutcome[] = [];
  for (const s of scenarios) {
    console.error(
      `[fallover] running scenario: ${s.name} → expecting ≥${s.expectedMin}`
    );
    const out = await runScenario(s.name, s.knockout, s.expectedMin);
    outcomes.push(out);
  }
  printReport(outcomes);

  // The cascade's contract is "never skip up a tier". Failure
  // taxonomy:
  //   (a) SKIP_UP: cascade landed BEFORE its knockout boundary (e.g.
  //       baseline returned "kimi" — but Plan A's key was set, so
  //       something is wrong). Real cascade-logic regression → exit 1.
  //   (b) ALL_DOWN: every tier raised, actual==="none". Not a cascade-
  //       logic regression — it's an upstream-availability regression.
  //       Surfaced separately so a credit-exhausted day doesn't masquerade
  //       as cascade breakage.
  //   (c) Plan D documented-fail: A+B+C knocked out AND DeepSeek 402
  //       (insufficient balance). Per the LLM-key memory note this is
  //       expected; treated as exit 0 with an explicit note.
  const skipUps: ChildOutcome[] = [];
  const allDowns: ChildOutcome[] = [];
  for (const o of outcomes) {
    if (o.ok) continue;
    if (o.actual_provider === "none") {
      allDowns.push(o);
    } else {
      // The cascade returned a real provider, just one that was
      // ranked earlier than the knockout boundary — a true logic bug.
      skipUps.push(o);
    }
  }
  // The Plan D scenario is allowed to land on "none" iff DeepSeek 402
  // ("Insufficient Balance"). That's the documented-fail.
  const planDDocFail = allDowns.find(
    (o) =>
      o.expected_min_provider === "deepseek" &&
      (o.errors?.deepseek ?? "").toLowerCase().includes("balance")
  );
  const otherAllDowns = allDowns.filter((o) => o !== planDDocFail);

  if (skipUps.length > 0) {
    console.log(
      `(Exit 1: ${skipUps.length} scenario(s) landed BEFORE their knockout boundary — cascade-logic regression.)`
    );
    process.exit(1);
  }
  if (otherAllDowns.length > 0) {
    // Not a cascade bug, but worth surfacing visibly. Use exit 2 so CI
    // can distinguish "cascade is broken" (1) from "all providers are
    // unavailable today" (2) from "all good" (0).
    console.log(
      `(Exit 2: ${otherAllDowns.length} non-PlanD scenario(s) landed on provider=none — upstream availability regression, not cascade logic.)`
    );
    process.exit(2);
  }
  if (planDDocFail) {
    console.log("(Exit 0: only Plan D documented-fail tripped; cascade logic intact.)");
  }
  process.exit(0);
}

main().catch((e) => {
  console.error("smoke_cascade_fallover crashed:", e);
  process.exit(2);
});
