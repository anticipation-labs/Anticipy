import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { callKimiJson, kimiAvailable } from "@/lib/kimi";

export const dynamic = "force-dynamic";

/**
 * POST /api/agent/verify
 *
 * Verifier agent — called by the Executor after each non-trivial action.
 * Decides whether the action satisfied the current plan step. Catches the
 * "silent stall" failure mode where a click returned success but the page
 * didn't actually change; the Executor's local check was lying.
 *
 * Body:
 *   { task: string,                  // the original user task
 *     plan_step: { step: number, goal: string, success_criteria: string },
 *     action: object,                // the JSON action the Executor just ran
 *     before_signals: object,        // page signals BEFORE the action
 *     after_signals: object,         // page signals AFTER the action
 *     last_step_success: boolean,    // what the Executor itself believes
 *     extracted_data?: object,       // running extracted_data
 *     visible_text_excerpt?: string  // up to 1500 chars of current visible text
 *   }
 *
 * Response:
 *   { satisfied: boolean,
 *     evidence: string,              // <=140 chars: WHY satisfied / not
 *     confidence: "high"|"med"|"low",
 *     advance_plan: boolean,         // if satisfied AND plan should advance
 *     suggested_next?: string }      // optional hint for Executor
 */

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, X-Anticipy-Code",
} as const;

const VERIFIER_SYSTEM = `You are the Verifier agent for Anticipy's browser-agent team.

<role>
After the Executor runs ONE action, you compare the page state BEFORE
and AFTER and decide: did this action satisfy the current plan step?
You are independent of the Executor — your job is to catch silent stalls
where the Executor thinks it succeeded but the page didn't actually move.
</role>

<rules>
- Use evidence, not optimism. A click that returned success but produced
  no observable change (URL same, title same, no new elements, body text
  unchanged) is a FAILED verification, even if the Executor reported
  success.
- "satisfied: true" means the plan step's success_criteria is met RIGHT
  NOW — based on the visible_text_excerpt, signals diff, and extracted
  data. If the criteria is "URL changed to X" you check after_signals.url.
  If it's "extracted product price into result", you check extracted_data.
- "advance_plan: true" only when satisfied AND the next plan step is now
  the right one to execute. (Some steps require multiple actions to satisfy;
  satisfied=false but progress made → advance=false.)
- "confidence" reflects how sure you are based on observable signals.
  "high" = direct evidence in the diff. "low" = ambiguous (e.g. page
  reloaded, can't tell if it's progress or a redirect to login).
- If the action's effect was clearly to navigate AWAY from the task (e.g.
  agent landed on a sign-in wall), set satisfied=false with evidence like
  "navigation to sign-in wall — not progress on task".
- Be CRITICAL but FAIR. If the Executor extracted the answer the user asked
  for and put it in extracted_data, that satisfies a "extract the answer"
  step regardless of what other UI noise happened.
</rules>

<output>
Strict JSON only:
{"satisfied": true|false,
 "evidence": "<=140 chars stating WHY satisfied or not, citing specific signals>",
 "confidence": "high"|"med"|"low",
 "advance_plan": true|false,
 "suggested_next": ""  /* optional, <=80 chars hint for Executor on what to do next */
}
</output>`;

interface VerifyRequest {
  task?: string;
  plan_step?: { step?: number; goal?: string; success_criteria?: string };
  action?: any;
  before_signals?: any;
  after_signals?: any;
  last_step_success?: boolean;
  extracted_data?: any;
  visible_text_excerpt?: string;
}

interface VerifyLLMResponse {
  satisfied?: boolean;
  evidence?: string;
  confidence?: "high" | "med" | "low";
  advance_plan?: boolean;
  suggested_next?: string;
}

function summarizeSignals(s: any): string {
  if (!s || typeof s !== "object") return "(none)";
  const fields = ["url", "title", "topHeading", "buttonCount", "inputCount", "linkCount", "formCount", "hasModal", "bodyTextLen"];
  return fields.map(k => `${k}=${JSON.stringify(s[k] ?? null)}`).join(" ");
}

function diffPreview(before: any, after: any): string {
  if (!before || !after) return "(insufficient signals)";
  const out: string[] = [];
  if (before.url !== after.url) out.push(`url: ${before.url} → ${after.url}`);
  if (before.title !== after.title) out.push(`title: "${(before.title||"").substring(0,50)}" → "${(after.title||"").substring(0,50)}"`);
  if (before.topHeading !== after.topHeading) out.push(`heading: "${before.topHeading}" → "${after.topHeading}"`);
  const numFields = ["buttonCount", "inputCount", "linkCount", "formCount", "bodyTextLen"];
  for (const k of numFields) {
    const b = Number(before[k] || 0);
    const a = Number(after[k] || 0);
    if (b !== a) out.push(`${k}: ${b} → ${a} (${a > b ? "+" : ""}${a - b})`);
  }
  if (before.hasModal !== after.hasModal) out.push(`hasModal: ${before.hasModal} → ${after.hasModal}`);
  if (before.bodyFingerprint !== after.bodyFingerprint) out.push(`bodyFingerprint changed`);
  return out.length > 0 ? out.join(" | ") : "NONE — page didn't visibly change";
}

export async function POST(req: Request) {
  const ip = clientIp(req);
  const ipLimit = rateLimit(`agent-verify:ip:${ip}`, 240, 60_000);
  if (!ipLimit.allowed) {
    return NextResponse.json({ error: "Too many requests" }, { status: 429, headers: CORS });
  }
  if (!kimiAvailable()) {
    return NextResponse.json(
      { error: "Verifier unavailable (KIMI_API_KEY missing)" },
      { status: 503, headers: CORS }
    );
  }
  const accessCode = (req.headers.get("X-Anticipy-Code") || "").trim();
  if (!accessCode) {
    return NextResponse.json({ error: "Missing X-Anticipy-Code" }, { status: 401, headers: CORS });
  }

  let body: VerifyRequest;
  try {
    body = (await req.json()) as VerifyRequest;
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400, headers: CORS });
  }
  const task = (body.task || "").trim();
  const action = body.action;
  if (!task || !action || typeof action !== "object") {
    return NextResponse.json({ error: "task and action are required" }, { status: 400, headers: CORS });
  }

  // Auth
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

  const planStep = body.plan_step || {};
  const ctx = [
    `<task>${task}</task>`,
    `<plan_step number="${planStep.step ?? "?"}">
  <goal>${planStep.goal ?? "(no plan)"}</goal>
  <success_criteria>${planStep.success_criteria ?? "(no criteria)"}</success_criteria>
</plan_step>`,
    `<action_executed>${JSON.stringify(action).substring(0, 500)}</action_executed>`,
    `<executor_self_report>last_step_success=${Boolean(body.last_step_success)}</executor_self_report>`,
    `<signals_before>${summarizeSignals(body.before_signals)}</signals_before>`,
    `<signals_after>${summarizeSignals(body.after_signals)}</signals_after>`,
    `<diff>${diffPreview(body.before_signals, body.after_signals)}</diff>`,
    body.extracted_data && Object.keys(body.extracted_data).length > 0
      ? `<extracted_data>${JSON.stringify(body.extracted_data).substring(0, 600)}</extracted_data>`
      : `<extracted_data>(empty)</extracted_data>`,
    body.visible_text_excerpt
      ? `<visible_text>${body.visible_text_excerpt.substring(0, 1500)}</visible_text>`
      : "",
    `Score it. JSON only.`,
  ].filter(Boolean).join("\n\n");

  let parsed: VerifyLLMResponse;
  try {
    parsed = await callKimiJson<VerifyLLMResponse>({
      system: VERIFIER_SYSTEM,
      messages: [{ role: "user", content: ctx }],
      // moonshot-v1-128k is the default — fires up to 60×/task.
      temperature: 0.1,
      maxTokens: 400,

    });
  } catch (e: any) {
    return NextResponse.json(
      { error: `verifier LLM failed: ${e?.message || String(e)}` },
      { status: 502, headers: CORS }
    );
  }

  return NextResponse.json(
    {
      satisfied: Boolean(parsed?.satisfied),
      evidence: String(parsed?.evidence || "").substring(0, 280),
      confidence: parsed?.confidence === "high" || parsed?.confidence === "low" ? parsed.confidence : "med",
      advance_plan: Boolean(parsed?.advance_plan),
      suggested_next: String(parsed?.suggested_next || "").substring(0, 160),
    },
    { headers: CORS }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}
