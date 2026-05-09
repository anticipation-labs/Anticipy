import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { callKimiJson, kimiAvailable } from "@/lib/kimi";

export const dynamic = "force-dynamic";

/**
 * POST /api/agent/critic
 *
 * Critic agent — fired when the Verifier disagrees with the Executor TWICE
 * in a row on the same plan step (or on consecutive different steps with
 * no progress). Reads the recent history and decides:
 *   - WHY did the Executor fail to make progress?
 *   - What's a different approach the Executor should try?
 *   - Or: is this task genuinely unreachable from the current state?
 *
 * The Critic is independent — same model, fresh context — so it doesn't
 * inherit the Executor's flawed mental model.
 *
 * Body:
 *   { task: string,
 *     plan: PlanStep[],
 *     current_step_index: number,
 *     history: Array<{action, result, signalDiff?}>,  // last 10 steps
 *     verifier_evidence: string,                       // most recent verdict
 *     domain?: string }
 *
 * Response:
 *   { diagnosis: string,             // <=240 chars: WHY this is failing
 *     new_approach: string,           // <=240 chars: what to try next
 *     abort: boolean,
 *     abort_reason?: string,
 *     replan_step_index?: number      // if set, Executor restarts from this step
 *   }
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Anticipy-Code",
} as const;

const CRITIC_SYSTEM = `You are the Critic agent for Anticipy's browser-agent team.

<role>
The Executor has produced TWO recent steps that the Verifier rejected.
The Executor is stuck. Your job is to look at the FULL recent history
with fresh eyes — you're not the Executor, you don't share its biases —
and either propose a different concrete approach OR declare the task
unreachable from this state.
</role>

<rules>
- Read the action+result+signal-diff for the last 5-10 steps. The
  pattern often becomes obvious in 2-3 actions: clicking the wrong
  element repeatedly, typing into a non-input, looping on wait, etc.
- "diagnosis" must be specific. Not "the agent failed" — instead
  "agent kept clicking the cookie banner instead of dismissing it,
  expected URL change but the modal stayed".
- "new_approach" must be ACTIONABLE. Not "try harder" — instead
  "use dismiss_modal first, then re-getPageState, then resume plan".
- "abort: true" ONLY when there is no realistic path forward — the page
  is a sign-in wall the user isn't authenticated for, the site is
  geo-blocked, the captcha is non-bypassable, or the resource the user
  asked about doesn't exist on this site.
- If aborting, "abort_reason" must be a one-sentence user-readable
  explanation (the wearer will see this).
- "replan_step_index" lets you restart the Executor from a specific
  earlier plan step (e.g. "go back to step 2, the navigation was wrong").
  Omit it to keep the Executor on the current step with the new approach.
</rules>

<output>
Strict JSON only:
{
  "diagnosis": "<=240 chars, specific>",
  "new_approach": "<=240 chars, actionable>",
  "abort": false,
  "abort_reason": "",
  "replan_step_index": null
}
</output>`;

interface CriticRequest {
  task?: string;
  plan?: any[];
  current_step_index?: number;
  history?: any[];
  verifier_evidence?: string;
  domain?: string;
}

export async function POST(req: Request) {
  const ip = clientIp(req);
  const ipLimit = rateLimit(`agent-critic:ip:${ip}`, 60, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429, headers: CORS });
  }
  if (!kimiAvailable()) {
    return NextResponse.json(
      { error: "Critic unavailable (KIMI_API_KEY missing)" },
      { status: 503, headers: CORS }
    );
  }
  const accessCode = (req.headers.get("X-Anticipy-Code") || "").trim();
  if (!accessCode) {
    return NextResponse.json({ error: "Missing X-Anticipy-Code" }, { status: 401, headers: CORS });
  }

  let body: CriticRequest;
  try {
    body = (await req.json()) as CriticRequest;
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

  const history = Array.isArray(body.history) ? body.history.slice(-10) : [];
  const histBlocks = history.map((h, i) => {
    const a = h?.action || {};
    const ok = h?.result?.success ? "OK" : "FAIL";
    const sig = h?.signalDiff ? ` | effect: ${String(h.signalDiff).substring(0, 120)}` : "";
    return `  step-${i + 1} ${ok}: ${a.action || "?"}${a.url ? ` ${a.url.substring(0, 60)}` : ""}${a.selector ? ` sel="${a.selector}"` : ""}${a.text ? ` text="${String(a.text).substring(0, 40)}"` : ""}${sig}`;
  }).join("\n");

  const planText = Array.isArray(body.plan) && body.plan.length > 0
    ? body.plan.map((p: any) => `  step ${p.step}: ${p.goal}`).join("\n")
    : "(no plan)";

  const ctx = [
    `<task>${task}</task>`,
    body.domain ? `<domain>${body.domain}</domain>` : "",
    `<plan>\n${planText}\n</plan>`,
    `<current_step_index>${body.current_step_index ?? 0}</current_step_index>`,
    `<recent_history>\n${histBlocks || "(empty)"}\n</recent_history>`,
    `<verifier_latest_evidence>${(body.verifier_evidence || "").substring(0, 240)}</verifier_latest_evidence>`,
    `Diagnose and propose next move. JSON only.`,
  ].filter(Boolean).join("\n\n");

  let parsed: any;
  try {
    parsed = await callKimiJson({
      system: CRITIC_SYSTEM,
      messages: [{ role: "user", content: ctx }],
      temperature: 1.0,  // K2.5 requires temp=1
      maxTokens: 1200,
    });
  } catch (e: any) {
    return NextResponse.json(
      { error: `critic LLM failed: ${e?.message || String(e)}` },
      { status: 502, headers: CORS }
    );
  }

  return NextResponse.json(
    {
      diagnosis: String(parsed?.diagnosis || "").substring(0, 480),
      new_approach: String(parsed?.new_approach || "").substring(0, 480),
      abort: Boolean(parsed?.abort),
      abort_reason: String(parsed?.abort_reason || "").substring(0, 240),
      replan_step_index: typeof parsed?.replan_step_index === "number"
        ? parsed.replan_step_index
        : null,
    },
    { headers: CORS }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}
