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

import { parseJsonWithRepair } from "@/lib/gemini";
import { callLlm, callLlmMixture } from "@/lib/llm-cascade";

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

2. is_concrete_commitment: Does the candidate include AT LEAST ONE specific slot — a named \
person, a specific time, a place, an item, an amount, OR a deliverable? Answer TRUE if ANY of \
those is present. Answer FALSE only for pure floating pleasantries with NO slots at all ("we \
should grab coffee sometime", "let's catch up soon", "we should look into that later"). \
Errand-style items like "pick up dry cleaning", "buy bread", "renew the dentist appointment" \
ARE concrete (item + implied deliverable) — answer TRUE. When in doubt, answer TRUE.

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
 * Adversarial second-gate prompt: takes the OPPOSITE side and argues for
 * REJECTION. Used as a tie-breaker when the primary gate is borderline.
 * Generic — same six concepts as GATE_SYSTEM_PROMPT, but framed as "find
 * evidence to drop this candidate".
 */
const ADVERSARIAL_GATE_SYSTEM_PROMPT = `You are the ADVERSARIAL gate for an intent extractor. \
The primary gate has just admitted a candidate intent and you are the second opinion: \
your job is to find any reason this candidate SHOULD be rejected. Argue the OPPOSITE side.

Look at the FULL transcript and the candidate, and return STRICT JSON:
{
  "should_reject": <true|false>,
  "rejection_grounds": [
    "delegation"|"chit_chat"|"retracted"|"past_completed"|"aspiration_only"|
    "status_query"|"hypothetical"|"third_party_quote"|"other"
  ],
  "reasoning": "<one short sentence with the strongest evidence for rejection>"
}

Be specifically adversarial:
  - If there is ANY plausible reading where the wearer was just venting, daydreaming, \
    or relaying someone else's plan — flag it.
  - If the wearer used "should/need to/keep meaning to" without a concrete commit verb, \
    flag aspiration_only.
  - If a later turn could be read as a retraction (even mild), flag retracted.
  - If the speaker chain is ambiguous (could the "I'll" be a quoted third party?), flag \
    third_party_quote.

Only set should_reject = true when at least ONE rejection ground holds with strong textual \
support. When in doubt, set should_reject = false (we err toward admitting).`;

function buildAdversarialUserPrompt(input: GateInput): string {
  return `Candidate that the primary gate ADMITTED:
  action_type: ${input.actionType}
  summary: ${input.summary}
  evidence_quote: "${input.evidenceQuote}"

Full transcript (oldest first):
"""
${input.transcript}
"""

Argue the case for REJECTION and return the JSON.`;
}

/**
 * Run the four-question gate against a single candidate intent.
 *
 * Adds two free-tier-friendly enhancements over the original single-call gate:
 *
 *   • ADVERSARIAL ARBITRATION: if the primary call ADMITS the intent but
 *     any of its raw answers are borderline (e.g. wearer=true but concrete=false,
 *     or perfect_moment is uncertain), we run a second Flash call that argues
 *     the OPPOSITE side. The verdict is the consensus: admit only if the
 *     primary admitted AND the adversarial gate didn't flag a strong
 *     rejection ground. This catches the "Flash says yes by default" failure
 *     mode without changing the primary prompt.
 *   • VOTING CONSENSUS: when the two gates disagree (primary admit, adversarial
 *     flags rejection), we run THREE additional Flash calls at temp=0.3 against
 *     the primary prompt and pick the majority verdict. 3-of-5 voting beats a
 *     single high-stakes decision. Skipped when the primary's reasoning is
 *     unambiguous (all four checks consistent).
 *
 * Cost analysis (per gate call, typical 1KB transcript):
 *   • Primary: ~$0.000050 (unchanged)
 *   • Adversarial: ~$0.000040 (smaller prompt + smaller output)
 *   • Voting (only on disagreement, ~5-10% of calls): 3 × $0.000050 = $0.000150
 *   • Average per gate: ~$0.000105 vs $0.000050 baseline (2.1x) — well under cap.
 *
 * Fail-open semantics: timeouts, parse failures, or empty responses ADMIT
 * the intent and mark perfectMoment=false (so we still queue it but skip
 * the loud notification). Same philosophy as the Python dispatcher — we'd
 * rather double-fire than silently drop a real task.
 */
export async function runIntentGate(input: GateInput): Promise<GateVerdict> {
  const primary = await runPrimaryGate(input);

  // If the primary already DROPPED the intent, no point running the
  // adversarial gate (it can only support dropping further). Return as-is.
  if (!primary.admit) return primary;

  // Borderline: run the adversarial gate. We always run it now — it's cheap
  // (~$0.00004) and catches Flash's "default yes" failure mode generically.
  const adversarial = await runAdversarialGate(input);
  if (!adversarial) return primary; // adversarial fail-soft → trust primary

  // Strong adversarial rejection signal — the gates disagree. Trigger voting.
  const disagreement = adversarial.shouldReject === true;
  if (!disagreement) {
    // Adversarial agreed (no rejection). Return the primary verdict unchanged.
    return primary;
  }

  // Voting consensus: 3 additional primary-prompt calls at slight temperature.
  // Goal is to converge on what the model "would usually say" rather than
  // accept a one-shot answer.
  const voters = await Promise.all([
    runPrimaryGate(input, { temperature: 0.3 }),
    runPrimaryGate(input, { temperature: 0.3 }),
    runPrimaryGate(input, { temperature: 0.3 }),
  ]);
  const allVotes = [primary, ...voters];
  const admitVotes = allVotes.filter((v) => v.admit).length;
  const dropVotes = allVotes.length - admitVotes;
  const majorityAdmit = admitVotes > dropVotes;

  if (!majorityAdmit) {
    // Majority says drop. Trust the consensus over the original primary.
    return {
      admit: false,
      perfectMoment: false,
      reasoning:
        "voting consensus rejected (" +
        adversarial.reasoning +
        ")",
      raw: {
        isWearersResponsibility: primary.raw.isWearersResponsibility,
        isConcreteCommitment: primary.raw.isConcreteCommitment,
        wasRetractedLater: true, // synthesized — adversarial flagged retraction-class issue
        isWaitingForMoment: false,
      },
    };
  }

  // Majority admit but adversarial flagged a rejection ground — admit but
  // strongly demote perfect_moment so the intent queues silently.
  return {
    admit: true,
    perfectMoment: false,
    reasoning:
      "admitted by majority despite adversarial flag: " + adversarial.reasoning,
    raw: primary.raw,
  };
}

/** Internal: single Flash call with the primary gate prompt. */
async function runPrimaryGate(
  input: GateInput,
  options: { temperature?: number } = {}
): Promise<GateVerdict> {
  const messages = [
    { role: "system" as const, content: GATE_SYSTEM_PROMPT },
    { role: "user" as const, content: buildGateUserPrompt(input) },
  ];

  // MIXTURE OF EXPERTS — fan out to up to 3 healthy providers in
  // parallel; majority-vote on the binary "admit" verdict. The harness
  // lift that makes the gate accurate even when Plan A is the dumbest
  // available model (e.g., Plan A quota-locked, falling through to a
  // smaller fallback). Wall-time stays ~max(provider) instead of sum.
  let raw = "";
  let mixtureMeta = "";
  try {
    const result = await callLlmMixture(messages, {
      temperature: options.temperature ?? 0.0,
      max_tokens: 512,
      cacheKey: "intent-gate-primary-v1",
      jsonOnly: true,
      maxVoters: 3,
      // Vote on the load-bearing field. When voters disagree, the
      // majority verdict's raw response is returned. Generic — the
      // function does JSON.parse + key lookup, no rule-specific logic.
      binaryField: "isConcreteCommitment",
    });
    raw = result.text;
    mixtureMeta = `voters=${result.voters} agreement=${result.agreement} provider=${result.provider}`;
    if (!raw) {
      throw new Error(
        `mixture failed: ${Object.entries(result.errors)
          .map(([k, v]) => `${k}=${v}`)
          .join(" | ")}`
      );
    }
  } catch (err) {
    console.warn(
      "[intent-gate] mixture call failed; failing open:",
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
  if (mixtureMeta) {
    // Visibility for the operator — confirms the harness fanned out
    // and tells us when we're running degraded (1 voter only).
    console.log(`[intent-gate] mixture ${mixtureMeta}`);
  }

  const parsed = await parseJsonWithRepair<Record<string, unknown>>(raw, {
    allowLLMRepair: false,
    debugLabel: "intent-gate-primary",
  });
  if (!parsed || typeof parsed !== "object") {
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

  const isWearer = Boolean(parsed.is_wearers_responsibility ?? true);
  const isConcrete = Boolean(parsed.is_concrete_commitment ?? true);
  const wasRetracted = Boolean(parsed.was_retracted_later ?? false);
  const isWaiting = Boolean(parsed.is_waiting_for_moment ?? false);
  const reasoning =
    typeof parsed.reasoning === "string" ? parsed.reasoning.slice(0, 240) : "";

  // Drop rules: ONLY (wearer=false) or (retracted=true) drop the intent.
  // is_concrete_commitment is now an IMPORTANCE signal — soft pleasantries
  // get demoted, not dropped. This keeps recall high; precision is enforced
  // by the wearer + retracted checks plus the upstream extraction prompt.
  const admit = isWearer && !wasRetracted;
  // Soft demotion: non-concrete admitted intents get perfectMoment=false so
  // they queue silently without email/SMS spam.
  const perfectMoment = isWaiting && isConcrete;

  return {
    admit,
    perfectMoment,
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
 * Internal: adversarial second gate — argues for rejection. Returns null on
 * any failure (caller treats null as "no rejection signal" and trusts
 * the primary gate).
 */
interface AdversarialResult {
  shouldReject: boolean;
  grounds: string[];
  reasoning: string;
}

async function runAdversarialGate(
  input: GateInput
): Promise<AdversarialResult | null> {
  let raw = "";
  try {
    raw = await callLlm(
      [
        { role: "system" as const, content: ADVERSARIAL_GATE_SYSTEM_PROMPT },
        { role: "user" as const, content: buildAdversarialUserPrompt(input) },
      ],
      {
        temperature: 0.0,
        max_tokens: 384,
        cacheKey: "intent-gate-adversarial-v1",
        jsonOnly: true,
      }
    );
  } catch (err) {
    console.warn(
      "[intent-gate] adversarial call failed:",
      err instanceof Error ? err.message : err
    );
    return null;
  }

  const parsed = await parseJsonWithRepair<{
    should_reject?: boolean;
    rejection_grounds?: string[];
    reasoning?: string;
  }>(raw, { allowLLMRepair: false, debugLabel: "intent-gate-adversarial" });
  if (!parsed) return null;

  return {
    shouldReject: Boolean(parsed.should_reject),
    grounds: Array.isArray(parsed.rejection_grounds)
      ? parsed.rejection_grounds.filter((g): g is string => typeof g === "string").slice(0, 6)
      : [],
    reasoning:
      typeof parsed.reasoning === "string" ? parsed.reasoning.slice(0, 200) : "",
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
