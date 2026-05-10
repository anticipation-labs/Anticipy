import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { callAgentJson, agentLLMAvailable } from "@/lib/agent-llm";

export const dynamic = "force-dynamic";

/**
 * POST /api/agent/reflect
 *
 * Reflector agent — last line of defence. Fired when TWO Critic cycles
 * have run with no progress (i.e. the agent has tried two different
 * approaches and the Verifier still rejected the steps). The Reflector
 * decides:
 *   - PIVOT_WILDLY: throw out the plan, generate a new one with a
 *     fundamentally different angle (different starting URL, different
 *     primary action like search-via-URL instead of UI-search, etc.)
 *   - ABORT: there is no realistic path; surface a clean failure.
 *   - CONTINUE: rare — only when the latest critic's new_approach really
 *     does seem viable but hasn't had a fair shot yet.
 *
 * Body:
 *   { task, plan, history, two_critic_diagnoses: [string,string], domain? }
 *
 * Response:
 *   { decision: "pivot"|"abort"|"continue",
 *     reasoning: string,             // <=240 chars
 *     new_plan?: PlanStep[],         // if pivot, the fresh plan with a different angle
 *     abort_message?: string         // if abort, what to tell the user
 *   }
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Anticipy-Code",
} as const;

const REFLECTOR_SYSTEM = `You are the Reflector — the last-line-of-defence agent for Anticipy's browser team.

<role>
Two Critic cycles have already failed. The agent has tried two different
approaches and is still not making progress. You decide:
  PIVOT — throw out the current plan and generate a NEW plan with a
    fundamentally different angle. Examples:
      - "We've been clicking around on the home page; instead navigate
         directly to the search-results URL"
      - "We've been trying to dismiss a modal; instead reload the page
         without the modal-trigger query param"
      - "We've been on site.com; instead use a different site that has
         the same data (e.g. wikipedia for Python release year, not
         python.org)"
  ABORT — declare the task unreachable. Surface a one-sentence
    user-readable failure message.
  CONTINUE — VERY rare. Only when the latest critic's approach genuinely
    hasn't been tried yet (the Executor never got around to executing
    the proposed action because it was preempted by a timeout or unrelated
    error).
</role>

<rules>
- Default to PIVOT, not CONTINUE. If we're at the Reflector, the
  conventional approaches have failed.
- ABORT is appropriate when: the page genuinely requires sign-in we don't
  have; the resource doesn't exist; the site has hard captcha; the user's
  task is fundamentally ambiguous (REQUIRED-SLOT not provided).
- "new_plan" should be 3-5 steps with a DIFFERENT structural approach
  from the original plan. Don't just rename the steps.
- "reasoning" is <=240 chars and explains the call.
- "abort_message" (only if abort) is what the user reads. Calm. No jargon.
</rules>

<output>
Strict JSON:
{
  "decision": "pivot"|"abort"|"continue",
  "reasoning": "...",
  "new_plan": [...],          // only if decision==="pivot"
  "abort_message": "..."      // only if decision==="abort"
}
</output>`;

interface ReflectRequest {
  task?: string;
  plan?: any[];
  history?: any[];
  two_critic_diagnoses?: string[];
  domain?: string;
}

export async function POST(req: Request) {
  const ip = clientIp(req);
  const ipLimit = rateLimit(`agent-reflect:ip:${ip}`, 30, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429, headers: CORS });
  }
  return NextResponse.json(
    { error: "Reflector disabled — Executor only mode" },
    { status: 503, headers: CORS }
  );

  /* eslint-disable */
  // @ts-ignore
  if (!agentLLMAvailable()) {
    return NextResponse.json(
      { error: "Reflector unavailable (no CEREBRAS or KIMI key)" },
      { status: 503, headers: CORS }
    );
  }
  const accessCode = (req.headers.get("X-Anticipy-Code") || "").trim();
  if (!accessCode) {
    return NextResponse.json({ error: "Missing X-Anticipy-Code" }, { status: 401, headers: CORS });
  }

  let body: ReflectRequest;
  try {
    body = (await req.json()) as ReflectRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400, headers: CORS });
  }
  const task = (body.task || "").trim();
  if (!task) {
    return NextResponse.json({ error: "task required" }, { status: 400, headers: CORS });
  }

  const supabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.SUPABASE_SERVICE_ROLE_KEY ?? ""
  );
  const { data: user } = await supabase
    .from("engine_users")
    .select("id")
    .eq("access_code", accessCode)
    .single();
  if (!user) {
    return NextResponse.json({ error: "Invalid access code" }, { status: 401, headers: CORS });
  }

  const planText = Array.isArray(body.plan) && body.plan.length > 0
    ? body.plan.map((p: any) => `  ${p.step}: ${p.goal}`).join("\n")
    : "(no original plan)";

  const history = Array.isArray(body.history) ? body.history.slice(-12) : [];
  const histBlocks = history.map((h, i) => {
    const a = h?.action || {};
    const ok = h?.result?.success ? "OK" : "FAIL";
    return `  ${i + 1} ${ok} ${a.action || "?"}${a.url ? ` url=${a.url.substring(0, 60)}` : ""}${a.selector ? ` sel="${a.selector}"` : ""}`;
  }).join("\n");

  const diags = Array.isArray(body.two_critic_diagnoses) ? body.two_critic_diagnoses.slice(0, 2) : [];
  const diagText = diags.length > 0
    ? diags.map((d, i) => `  diagnosis-${i + 1}: ${String(d).substring(0, 240)}`).join("\n")
    : "(no critic diagnoses)";

  const ctx = [
    `<task>${task}</task>`,
    body.domain ? `<domain>${body.domain}</domain>` : "",
    `<original_plan>\n${planText}\n</original_plan>`,
    `<recent_history>\n${histBlocks || "(empty)"}\n</recent_history>`,
    `<critic_diagnoses>\n${diagText}\n</critic_diagnoses>`,
    `Decide. JSON only.`,
  ].filter(Boolean).join("\n\n");

  let parsed: any;
  try {
    const out = await callAgentJson({
      system: REFLECTOR_SYSTEM,
      messages: [{ role: "user", content: ctx }],
      temperature: 0.1,
      maxTokens: 1500,
    });
    parsed = out.data;
  } catch (e: any) {
    return NextResponse.json(
      { error: `reflector LLM failed: ${e?.message || String(e)}` },
      { status: 502, headers: CORS }
    );
  }

  const decision = parsed?.decision === "pivot" || parsed?.decision === "abort" || parsed?.decision === "continue"
    ? parsed.decision
    : "abort";
  const newPlan = decision === "pivot" && Array.isArray(parsed?.new_plan)
    ? parsed.new_plan.slice(0, 7)
    : null;

  return NextResponse.json(
    {
      decision,
      reasoning: String(parsed?.reasoning || "").substring(0, 480),
      new_plan: newPlan,
      abort_message: decision === "abort"
        ? String(parsed?.abort_message || "I couldn't reach the answer — the path I'd take isn't available right now.").substring(0, 240)
        : null,
    },
    { headers: CORS }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}
