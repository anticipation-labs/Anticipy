import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import { callAgentJson, agentLLMAvailable } from "@/lib/agent-llm";

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
After the Executor runs ONE action, you compare page state BEFORE and
AFTER and decide: did this action MAKE PROGRESS on the task? You catch
"silent stalls" — where the Executor thinks success but page didn't move
— but you do NOT penalize legitimate intermediate steps.
</role>

<rules>
DEFAULT: satisfied=true unless you have CONCRETE evidence the action
failed. The Executor is right far more often than wrong; your job is to
catch the rare clear failure, not to second-guess every action.

CONCRETE fail evidence (these are the ONLY cases where satisfied=false):
  - Page state IDENTICAL before+after AND the action was supposed to
    change something (click that should navigate, type that should fill
    a field, navigate to URL X but URL is unchanged). Identical means:
    same URL, same title, same heading, same body fingerprint.
  - The page navigated AWAY from where the task needs to go (e.g. landed
    on sign-in wall when task didn't require auth, hit a 404, blocked-
    by-Cloudflare page).
  - Extract action returned empty when the data should have been there
    AND the page actually loaded fully.

PASS by default in these cases (DO NOT mark them as fail):
  - Page changed in any meaningful way (URL/title/heading/+elements
    different) → progress, satisfied=true.
  - Action was an extract or getPageState or wait — these are
    information-gathering, almost always satisfied=true.
  - Plan step is high-level (e.g. "extract Python's release year") and
    the agent is doing intermediate scrolling/searching — satisfied=true,
    advance_plan=false (still on the same step, but progressing).
  - Modal appeared / dismissed / form opened — that's progress.

advance_plan rules:
  - true = the success_criteria for the CURRENT plan step is fully met
    AND the next plan step is the right thing to do next.
  - false = either step not yet done OR step done but next step depends
    on info we don't have yet.

confidence: "high" if the diff clearly shows the outcome; "low" if the
signals are ambiguous (page reloaded, can't tell if progress or redirect).

Be GENEROUS by default. The cost of a false fail (rejecting good work)
is the agent loops and burns budget. The cost of a false pass (letting
a real stall through) is the next step's verifier catches it. Stalls are
sticky; one false pass is recoverable. Lean toward satisfied=true.
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
  // Disabled in production while we run on Cerebras-only with tight RPM
  // budget. The Verifier was eating ~50% of the LLM-call budget per task,
  // doubling RPM pressure on the same Cerebras pool the Executor uses.
  // Agent.js handles this 503 gracefully — runs without the verdict.
  // Re-enable here once we have a separate quota pool (paid model or
  // multi-key rotation).
  return NextResponse.json(
    { error: "Verifier disabled — Executor only mode" },
    { status: 503, headers: CORS }
  );
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: CORS });
}
