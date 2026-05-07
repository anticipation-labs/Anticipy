/**
 * Second-pass validation gates ported from the Python proactive cascade.
 *
 * Mirrors the L1 (salience) / L2 (extraction) / L5 (Donna retraction & regret)
 * checks that the eval-only Python cascade in engine/app/proactive/ uses, but
 * collapses them into a SINGLE Gemini call per candidate intent. A single
 * call keeps latency reasonable in the production /api/engine/analyze path
 * while still asking the four questions that matter:
 *
 *   1. WEARER — is this the wearer's responsibility, or are they delegating
 *      it to a named third party? ("Sarah, can you book the room?" → Sarah's
 *      task, not the wearer's.)
 *   2. CONCRETE — is this a real commitment with at least one concrete slot
 *      (person, place, time, item, amount), or is it a future-tense
 *      pleasantry like "we should grab coffee sometime"?
 *   3. RETRACTED — does the SAME conversation later contain a retraction,
 *      pivot, or supersession of this intent ("actually never mind", "scratch
 *      that", "wait, instead let me…")?
 *   4. PERFECT_MOMENT — should this be surfaced NOW with a notification, or
 *      should it just sit in the queue silently? Used to set importance,
 *      not to drop the intent.
 *
 * NO regex. NO keyword tables. NO per-utterance pattern matching. The model
 * decides every gate, in context, exactly like the Python cascade does.
 *
 * Fail-open: if the gate LLM call fails or returns malformed JSON, we ADMIT
 * the intent — we'd rather over-notify than silently drop a real task.
 */

import { callGemini } from "@/lib/gemini";

export interface GateInput {
  /** Wearer's high-level summary of what they want done. */
  summary: string;
  /** Verb / action_type the extractor inferred. */
  actionType: string;
  /** Verbatim quote from the transcript that triggered this candidate. */
  evidenceQuote: string;
  /** The full transcript window being analyzed (already capped upstream). */
  transcript: string;
  /** Last few confirmed/executed intents from this user (cross-session memory). */
  crossSessionContext?: string[];
}

export interface GateVerdict {
  /** Final admit decision after wearer / concrete / retracted gates. */
  admit: boolean;
  /** Whether this is the right MOMENT to surface; false → drop importance to "low". */
  perfectMoment: boolean;
  /**
   * One short sentence of reasoning from the gate model — useful in logs but
   * never shown to the user.
   */
  reasoning: string;
  /** Raw gate answers, surfaced for logging / debugging. */
  raw: {
    isWearersResponsibility: boolean;
    isConcreteCommitment: boolean;
    wasRetractedLater: boolean;
    isWaitingForMoment: boolean;
  };
}

const GATE_SYSTEM_PROMPT = `You are the precision validation gate for an AI wearable's intent extractor. \
A larger model has just proposed a candidate intent from a long-form conversation transcript. \
Your job is to apply four crisp yes/no checks and return STRICT JSON.

You answer four questions about the candidate intent, given the FULL recent transcript:

1. is_wearers_responsibility: Is the candidate intent something the WEARER themselves committed \
to do? Answer FALSE when the wearer is delegating it to a named third party in the conversation \
("Sarah, can you book the room?", "John, send the deck", "I'll have Marcus handle that"). \
Answer TRUE when the wearer is the one acting, even if they're responding to someone else's \
request ("Yeah I'll grab the milk on the way home").

2. is_concrete_commitment: Is this a CONCRETE commitment with at least one specific slot \
(named person, specific time, place, item, amount, deliverable)? Answer FALSE for future-tense \
pleasantries with no concrete commitment ("we should grab coffee sometime", "let's catch up \
soon", "you should come hiking next time", "we should look into that later"). Answer TRUE when \
there is a specific recipient AND a concrete time/deliverable/topic.

3. was_retracted_later: Reading the FULL transcript end to end, did the wearer LATER retract, \
contradict, supersede, or pivot away from this intent? Look for "actually never mind", "scratch \
that", "wait, instead", "on second thought", "I changed my mind", "let me just do Y instead", \
"forget it", "skip it" — any signal that the wearer's LATEST position is different from the \
candidate. The latest position wins. Answer TRUE if retracted/superseded; FALSE if it stands.

4. is_waiting_for_moment: Is THIS THE MOMENT to surface the intent to the user as a \
notification? Answer TRUE for tasks with real time pressure, deadlines, or things the user \
clearly wants to remember NOW. Answer FALSE for tasks that are worth queuing silently but \
don't need an email/SMS interrupting the user right now (e.g. low-stakes preferences, \
"someday/maybe" items, things explicitly scheduled far in the future).

Return STRICT JSON only, no markdown, no preamble:
{
  "is_wearers_responsibility": <true|false>,
  "is_concrete_commitment": <true|false>,
  "was_retracted_later": <true|false>,
  "is_waiting_for_moment": <true|false>,
  "reasoning": "<one short sentence explaining the call>"
}

Bias when uncertain:
  - is_wearers_responsibility: bias TRUE when ambiguous (the wearer benefits from a captured task).
  - is_concrete_commitment: bias TRUE when there is at least one concrete slot.
  - was_retracted_later: bias FALSE when ambiguous (don't drop real tasks on a hunch).
  - is_waiting_for_moment: bias FALSE when ambiguous (queue silently rather than spam).`;

function buildGateUserPrompt(input: GateInput): string {
  const cross =
    input.crossSessionContext && input.crossSessionContext.length > 0
      ? input.crossSessionContext.map((c, i) => `  ${i + 1}. ${c}`).join("\n")
      : "  (none)";
  return `Candidate intent under review:
  action_type: ${input.actionType}
  summary: ${input.summary}
  evidence_quote: "${input.evidenceQuote}"

User's last few confirmed/executed intents (last 72h, may be empty):
${cross}

Full recent transcript (oldest first):
"""
${input.transcript}
"""

Apply the four checks and return the JSON.`;
}

/**
 * Run the four-question gate against a single candidate intent.
 *
 * Fail-open semantics: timeouts, parse failures, or empty responses ADMIT
 * the intent and mark perfectMoment=false (so we still queue it but skip
 * the loud notification). Same philosophy as the Python dispatcher — we'd
 * rather double-fire than silently drop a real task.
 */
export async function runIntentGate(input: GateInput): Promise<GateVerdict> {
  const messages = [
    { role: "system" as const, content: GATE_SYSTEM_PROMPT },
    { role: "user" as const, content: buildGateUserPrompt(input) },
  ];

  let raw = "";
  try {
    raw = await callGemini(messages, { temperature: 0.0, max_tokens: 512 });
  } catch (err) {
    console.warn(
      "[intent-gate] gemini call failed; failing open:",
      err instanceof Error ? err.message : err
    );
    return {
      admit: true,
      perfectMoment: false,
      reasoning: "gate llm error; admitted with low importance",
      raw: {
        isWearersResponsibility: true,
        isConcreteCommitment: true,
        wasRetractedLater: false,
        isWaitingForMoment: false,
      },
    };
  }

  let parsed: Record<string, unknown> | null = null;
  try {
    parsed = JSON.parse((raw || "").trim());
  } catch {
    console.warn(
      "[intent-gate] unparseable gate response; failing open:",
      (raw || "").slice(0, 200)
    );
    return {
      admit: true,
      perfectMoment: false,
      reasoning: "gate llm unparseable; admitted with low importance",
      raw: {
        isWearersResponsibility: true,
        isConcreteCommitment: true,
        wasRetractedLater: false,
        isWaitingForMoment: false,
      },
    };
  }

  if (!parsed || typeof parsed !== "object") {
    return {
      admit: true,
      perfectMoment: false,
      reasoning: "gate llm non-object; admitted with low importance",
      raw: {
        isWearersResponsibility: true,
        isConcreteCommitment: true,
        wasRetractedLater: false,
        isWaitingForMoment: false,
      },
    };
  }

  const isWearer = Boolean(parsed.is_wearers_responsibility ?? true);
  const isConcrete = Boolean(parsed.is_concrete_commitment ?? true);
  const wasRetracted = Boolean(parsed.was_retracted_later ?? false);
  const isWaiting = Boolean(parsed.is_waiting_for_moment ?? false);
  const reasoning =
    typeof parsed.reasoning === "string" ? parsed.reasoning.slice(0, 240) : "";

  // Drop rules: any of (wearer=false), (concrete=false), or (retracted=true) → drop.
  const admit = isWearer && isConcrete && !wasRetracted;

  return {
    admit,
    perfectMoment: isWaiting,
    reasoning,
    raw: {
      isWearersResponsibility: isWearer,
      isConcreteCommitment: isConcrete,
      wasRetractedLater: wasRetracted,
      isWaitingForMoment: isWaiting,
    },
  };
}

/**
 * Per-user perfect-moment throttle: if the user already received MORE than
 * NOTIFY_RATE_LIMIT intent notifications in the past NOTIFY_RATE_WINDOW_MS,
 * downgrade NEW non-critical intents to importance="low" so we email/queue
 * them silently instead of pinging email/SMS again. "Critical" still goes
 * through — the throttle never silences a real emergency.
 */
export const NOTIFY_RATE_LIMIT = 5;
export const NOTIFY_RATE_WINDOW_MS = 60 * 60 * 1000; // 60 minutes

export function applyPerfectMomentThrottle(
  importance: string,
  recentNotificationCount: number,
  perfectMomentVerdict: boolean
): string {
  // Critical always rings — this is the one carve-out.
  if (importance === "critical") return importance;
  // Gate said "not the right moment" → demote regardless of throttle.
  if (!perfectMomentVerdict) return "low";
  // Over the per-user notify rate → demote new non-critical to "low".
  if (recentNotificationCount > NOTIFY_RATE_LIMIT) return "low";
  return importance;
}
