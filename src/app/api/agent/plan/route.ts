import { NextResponse } from "next/server";
import { rateLimit, clientIp } from "@/lib/rate-limit";

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
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}
