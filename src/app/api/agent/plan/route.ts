import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { kimiCostUsd } from "@/lib/kimi";
import { callAgentJson, agentLLMAvailable } from "@/lib/agent-llm";
import { embedQuery, voyageAvailable, padVectorTo, vectorToPg } from "@/lib/voyage";

export const dynamic = "force-dynamic";

/**
 * POST /api/agent/plan
 *
 * Planner agent. Called once at task start by the extension's BrowserAgent.
 * Returns a 3-7 step plan + the RAG examples that informed it. The
 * Executor then runs steps one at a time, calling /api/agent/verify after
 * each one.
 *
 * Auth: X-Anticipy-Code header (same access code as the rest of the
 * extension routes).
 *
 * Body:
 *   { task: string, current_url?: string, current_title?: string,
 *     domain?: string }
 *
 * Response:
 *   { plan: [{step, goal, success_criteria}],
 *     required_facts: string[],
 *     unreachable: boolean,
 *     unreachable_reason?: string,
 *     examples_used: { id, task_summary, outcome }[],
 *     usage: { tokens, cost_usd } }
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Anticipy-Code",
} as const;

const PLANNER_SYSTEM = `You are the Planner agent for Anticipy's browser-agent team.

<role>
Read the wearer's task, look at the 3 most-similar past trajectories
from this user (provided as <example_trajectory> blocks), and output a
concrete 3-7 step plan that the Executor agent will follow.
</role>

<rules>
- Each step has a goal AND a success_criteria the Verifier can check.
- success_criteria must be observable (URL contains, element appears,
  text appears in visible body, value extracted into result.message).
- Do NOT try to be exhaustive — 7 steps max. The Executor handles
  micro-tactics (which selector to click, which input to type).
- If the user's task references multiple sites, plan steps to use
  open_tab early (DON'T loiter on site A re-extracting the same content).
- If the task is genuinely unreachable from a non-authenticated browser
  state (banking/healthcare requiring sign-in, captcha gate, account
  creation), set unreachable=true with a one-sentence reason.
- required_facts: list facts the user-task itself names (specific dates,
  specific products, specific people). The Executor MUST surface these
  in its done() message; the Verifier checks for them.
</rules>

<output>
Reply with strict JSON only:
{
  "plan": [
    {"step": 1, "goal": "<one short sentence>", "success_criteria": "<observable check>"},
    ...
  ],
  "required_facts": ["<fact>", ...],
  "unreachable": false,
  "unreachable_reason": ""
}
</output>`;

interface PlanRequest {
  task?: string;
  current_url?: string;
  current_title?: string;
  domain?: string;
}

interface PlanStep {
  step: number;
  goal: string;
  success_criteria: string;
}
interface PlanLLMResponse {
  plan?: PlanStep[];
  required_facts?: string[];
  unreachable?: boolean;
  unreachable_reason?: string;
}

export async function POST(req: Request) {
  const ip = clientIp(req);
  const ipLimit = rateLimit(`agent-plan:ip:${ip}`, 60, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429, headers: CORS });
  }
  // Disabled — saves 1 Cerebras call per task. Extension's _planTask
  // catches 503 and runs plan-less, which is fine on simple tasks.
  // Re-enable when we have a separate quota pool for the planner.
  return NextResponse.json(
    { error: "Planner disabled — Executor only" },
    { status: 503, headers: CORS }
  );

  if (!agentLLMAvailable()) {
    return NextResponse.json(
      { error: "Agent backend not configured (no CEREBRAS_API_KEY or KIMI_API_KEY)" },
      { status: 503, headers: CORS }
    );
  }

  const accessCode = (req.headers.get("X-Anticipy-Code") || "").trim();
  if (!accessCode) {
    return NextResponse.json({ error: "Missing X-Anticipy-Code" }, { status: 401, headers: CORS });
  }

  let body: PlanRequest;
  try {
    body = (await req.json()) as PlanRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400, headers: CORS });
  }
  const task = (body.task || "").trim();
  if (!task) {
    return NextResponse.json({ error: "task is required" }, { status: 400, headers: CORS });
  }

  // Auth — resolve access_code → user_id (same lookup the trajectory + auth
  // routes use). Service role for the lookup.
  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );
  const { data: user, error: userErr } = await supabase
    .from("engine_users")
    .select("id")
    .eq("access_code", accessCode)
    .single();
  if (userErr || !user) {
    return NextResponse.json({ error: "Invalid access code" }, { status: 401, headers: CORS });
  }
  const userId = user.id as string;

  // ─── RAG retrieval: top-3 most-similar past trajectories ──────────────
  // Voyage is independent quota from Kimi (the agent budget) so this is
  // ~free relative to the LLM call. If voyage isn't configured we just
  // skip retrieval — planner still produces a plan, just without examples.
  type ExampleRef = { id: string; task_summary: string; outcome: string };
  let examples: ExampleRef[] = [];
  let exampleBlocks: string[] = [];

  if (voyageAvailable()) {
    try {
      const { vector } = await embedQuery(task);
      const padded = padVectorTo(vector, 768);
      const pgVec = vectorToPg(padded);
      // pgvector cosine: <=> operator. Filter to this user's successful
      // trajectories ONLY (failed traces would mislead the planner).
      const { data: similar } = await supabase.rpc("engine_trajectories_top3", {
        p_user_id: userId,
        p_query_vec: pgVec,
      });
      if (Array.isArray(similar) && similar.length > 0) {
        examples = similar.slice(0, 3).map((r: any) => ({
          id: r.id,
          task_summary: r.task_summary,
          outcome: r.outcome,
        }));
        exampleBlocks = similar.slice(0, 3).map((r: any, idx: number) => {
          const stepsPreview = Array.isArray(r.steps)
            ? r.steps.slice(0, 8).map((s: any) => {
                const a = s?.action || {};
                const act = a.action || "?";
                const tgt = a.url || a.selector || a.text || "";
                return `  ${act}${tgt ? `(${String(tgt).substring(0, 50)})` : ""}`;
              }).join("\n")
            : "";
          return `<example_trajectory index="${idx + 1}" outcome="${r.outcome}">
  task: ${String(r.task_summary).substring(0, 240)}
  actions:
${stepsPreview}
</example_trajectory>`;
        });
      }
    } catch (e: any) {
      // Retrieval is best-effort. Plan without examples on failure.
      console.warn("[/api/agent/plan] retrieval failed:", e?.message || e);
    }
  }

  // ─── Plan via Kimi K2.6 ───────────────────────────────────────────────
  const ctx = [
    `<task>${task}</task>`,
    body.current_url ? `<current_url>${body.current_url}</current_url>` : "",
    body.current_title ? `<current_title>${body.current_title}</current_title>` : "",
    body.domain ? `<domain>${body.domain}</domain>` : "",
    exampleBlocks.length > 0
      ? `<retrieved_examples>\n${exampleBlocks.join("\n")}\n</retrieved_examples>`
      : `<retrieved_examples>(none — first task on this domain or no past matches)</retrieved_examples>`,
    `Output JSON per the schema in <output> from your system prompt.`,
  ].filter(Boolean).join("\n\n");

  let parsed: PlanLLMResponse;
  const usage: { prompt_tokens?: number; completion_tokens?: number } = {};
  try {
    const out = await callAgentJson<PlanLLMResponse>({
      system: PLANNER_SYSTEM,
      messages: [{ role: "user", content: ctx }],
      temperature: 0.1,
      maxTokens: 1500,
    });
    parsed = out.data;
    // out.provider tells us which backend served this — useful for
    // future cost tracking but kept out of the response shape for now.
  } catch (e: any) {
    return NextResponse.json(
      { error: `planner LLM failed: ${e?.message || String(e)}` },
      { status: 502, headers: CORS }
    );
  }

  const plan = Array.isArray(parsed?.plan) ? parsed.plan.slice(0, 7) : [];
  const required = Array.isArray(parsed?.required_facts) ? parsed.required_facts : [];
  const unreachable = Boolean(parsed?.unreachable);

  return NextResponse.json(
    {
      plan,
      required_facts: required,
      unreachable,
      unreachable_reason: parsed?.unreachable_reason || "",
      examples_used: examples,
      usage: { tokens: usage, cost_usd: kimiCostUsd(usage) },
    },
    { headers: CORS }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}
