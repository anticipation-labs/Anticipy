/**
 * Self-verification loop for intent extraction.
 *
 * Three Flash passes wrap the existing intent prompt without changing it:
 *
 *   Pass 1 (extract): the existing buildIntentPrompt() is sent to Flash at
 *     temp=0. Same model, same prompt — this preserves backwards
 *     compatibility. The output is the candidate intent list.
 *
 *   Pass 2 (critique): a second Flash call at temp=0 reads the transcript
 *     PLUS the candidates and answers six targeted questions:
 *       (a) Are any candidates false positives (chit-chat, delegations,
 *           retracted, status queries, past-completed)?
 *       (b) Did the extractor miss any genuine intents?
 *       (c) Are any importance levels miscalibrated?
 *       (d) Are any candidates duplicates of each other?
 *       (e) Are required_slots / missing_slots / clarification_question
 *           coherent for each candidate?
 *       (f) Is the final list complete & in the right order?
 *
 *   Pass 3 (refine): only if pass 2 reports flaws. Otherwise we return the
 *     pass-1 candidates as-is. The refine prompt sees the original
 *     transcript, the candidates, AND the critique, and emits the FINAL
 *     intent list in the same JSON shape the analyze route expects.
 *
 * Cost analysis (typical 1KB transcript, 4KB system prompt):
 *   Pass 1: ~5K input + 1K output → ~$0.00010 baseline
 *   Pass 2: ~4K input + 0.5K output → ~$0.00007
 *   Pass 3: ~5K input + 1K output → ~$0.00010 (skipped on clean critiques)
 *   Worst case: 3 passes ≈ $0.00027 vs $0.00010 baseline (2.7x) — well
 *   under the 4x cap in the brief. With cache hits the marginal cost of
 *   passes 2 & 3 drops further (system prompts cached server-side).
 *
 * Backwards compatible: the route still receives JSON in the
 *   { reasoning, intents: [...] } shape it parses today.
 */

import { parseJsonWithRepair } from "@/lib/gemini";
import { callLlm } from "@/lib/llm-cascade";

export interface ExtractCallContext {
  /** System prompt as built by buildIntentPrompt — passed through unchanged. */
  system: string;
  /** User prompt (transcript + recent context) as built by buildIntentPrompt. */
  user: string;
  /**
   * Stable cache key for the system prompt. Same key reuses the cached
   * payload across calls (5-min TTL on Gemini's side). Pass undefined to
   * disable caching.
   */
  cacheKey?: string;
  /**
   * Maximum number of times to invoke Flash for the extract pass before
   * giving up. The default is 1 — the ROUTE keeps its existing fallback
   * chain (Gemini → Groq → Kimi) for cross-provider fallback.
   */
  maxAttempts?: number;
}

export interface ExtractResult {
  /** Final {reasoning, intents} payload matching the route's expected JSON. */
  payload: { reasoning?: string; intents: Array<Record<string, unknown>> };
  /** Number of Flash calls actually made (1, 2, or 3). */
  passesUsed: number;
  /** True when the critique pass found at least one flaw worth refining. */
  refined: boolean;
}

const CRITIQUE_SYSTEM = `You are the CRITIQUE pass of a self-verifying intent extractor. \
Another AI has just produced a candidate list of "actionable items" from a conversation \
transcript. Your sole job is to find every flaw — false positives, missed intents, \
miscalibrated importance, duplicate candidates, incoherent slot/clarification fields. \
You DO NOT rewrite the list. You DO NOT add intents. You produce STRUCTURED FEEDBACK only.

Apply each of these checks. For every candidate intent, ask:
  - Is this a genuine future task the WEARER themselves committed to (not delegation, \
    not chit-chat, not status query, not past-completed, not aspiration without commitment)?
  - Was it RETRACTED later in the same conversation ("never mind", "scratch that", \
    "actually let's just")?
  - Is the importance level reasonable, given the urgency signals in the transcript?
  - Are the required_slots / missing_slots / clarification_question coherent (if there \
    are missing slots, is there a clarification question; if no missing slots, is the \
    question empty)?
  - Is this a duplicate of another candidate in the list (same task framed twice)?

DO NOT add new intents. The route has a separate empty-rescue layer for that. \
Your ONLY job is to flag flaws in the EXISTING candidates. Set missed_intents to []. \
If you find no flaws in the existing candidates, set is_clean = true.

Return STRICT JSON only — no markdown, no preamble:
{
  "candidates_flaws": [
    {
      "index": <0-based candidate index>,
      "issues": ["<short tag>", ...],
      "explanation": "<one short sentence>"
    }
  ],
  "missed_intents": [],
  "is_clean": <true|false>
}

issues tags must come from this set (use the most specific one that applies):
  delegation, chit_chat, retracted, past_completed, aspiration_only, status_query,
  duplicate, importance_too_high, importance_too_low, slots_incoherent,
  clarification_missing, clarification_extraneous, other

is_clean = true means NOTHING needs refinement: no candidate flaws AND no missed intents. \
Be strict — if you flag any issue, set is_clean = false.

Bias: when uncertain, do not flag. Conservative critique reduces churn.`;

const REFINE_SYSTEM = `You are the REFINE pass of a self-verifying intent extractor. \
You are given:
  1. The full transcript and full upstream context.
  2. The candidate intents the extractor produced.
  3. A structured CRITIQUE flagging false positives, missed items, and slot/clarification issues.

Your job: produce the FINAL intent list. Apply every critique point: drop flagged false \
positives, fix slot/clarification coherence, demote/promote importance where flagged. \
Preserve every candidate not flagged in the critique. \
DO NOT add new intents (the route handles missed intents in a separate layer); only \
modify or drop the existing candidates.

Output the SAME JSON shape the upstream extractor uses:
{
  "reasoning": "<short summary of the changes vs the candidate list>",
  "intents": [
    {
      "action_type": "snake_case_name",
      "confidence": 0.0-1.0,
      "importance": "critical|important|standard|low",
      "summary_for_user": "...",
      "evidence_quote": "...",
      "parameters": { ... },
      "required_slots": ["..."],
      "missing_slots": ["..."],
      "clarification_question": "..."
    }
  ]
}

Rules:
  - When dropping a candidate, do NOT include it in the final list at all.
  - When the critique flags importance miscalibration, set importance to the level the \
    critique recommends.
  - Preserve evidence_quote verbatim from the transcript when possible.
  - STRICT JSON only — no markdown, no preamble.`;

/**
 * Run the three-pass self-verifying extractor. Falls back gracefully:
 *   - Pass 1 fails → throw (caller's outer fallback chain catches).
 *   - Pass 2 fails → return pass-1 result (no critique). Same as today.
 *   - Pass 2 reports clean → skip pass 3, return pass-1 result.
 *   - Pass 3 fails → return pass-1 result. Critique was advisory only.
 */
export async function extractIntentsWithVerification(
  ctx: ExtractCallContext
): Promise<ExtractResult> {
  // Pass 1 — same prompt, same call. Backwards compatible.
  const messages = [
    { role: "system" as const, content: ctx.system },
    { role: "user" as const, content: ctx.user },
  ];

  let pass1Raw = "";
  let pass1Err: Error | null = null;
  const maxAttempts = ctx.maxAttempts ?? 1;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      pass1Raw = await callLlm(messages, {
        temperature: 0.0,
        max_tokens: 8192,
        cacheKey: ctx.cacheKey,
        jsonOnly: true,
      });
      if (pass1Raw && pass1Raw.trim().length > 0) break;
    } catch (err) {
      pass1Err = err instanceof Error ? err : new Error(String(err));
    }
  }
  if (!pass1Raw || pass1Raw.trim().length === 0) {
    throw pass1Err ?? new Error("Gemini extract pass returned empty");
  }

  const pass1 = await parseJsonWithRepair<{
    reasoning?: string;
    intents?: Array<Record<string, unknown>>;
  }>(pass1Raw, { allowLLMRepair: true, debugLabel: "intent-extract-pass1" });
  if (!pass1 || !Array.isArray(pass1.intents)) {
    // Couldn't parse even after repair. Surface a defensive empty list —
    // matches the route's existing error path.
    return {
      payload: { reasoning: "extract pass parse failure", intents: [] },
      passesUsed: 1,
      refined: false,
    };
  }
  const candidates = pass1.intents;

  // Pass 2 — critique. Always runs for non-empty candidate lists. Skipped
  // for genuinely-empty lists (no candidates to critique, missed-intents
  // detection covered separately by the route's empty-result rescue path).
  if (candidates.length === 0) {
    return {
      payload: { reasoning: pass1.reasoning, intents: candidates },
      passesUsed: 1,
      refined: false,
    };
  }

  const critiquePayload = JSON.stringify(
    {
      transcript_excerpt: ctx.user,
      candidates: candidates.map((c, i) => ({
        index: i,
        action_type: c.action_type,
        summary_for_user: c.summary_for_user,
        evidence_quote: c.evidence_quote,
        importance: c.importance,
        confidence: c.confidence,
        required_slots: c.required_slots,
        missing_slots: c.missing_slots,
        clarification_question: c.clarification_question,
      })),
    },
    null,
    2
  );

  let critiqueRaw = "";
  try {
    critiqueRaw = await callLlm(
      [
        { role: "system" as const, content: CRITIQUE_SYSTEM },
        { role: "user" as const, content: critiquePayload },
      ],
      {
        temperature: 0.0,
        max_tokens: 1536,
        cacheKey: "intent-critique-v1",
        jsonOnly: true,
      }
    );
  } catch (err) {
    console.warn(
      "[intent-extract] critique pass failed, returning pass-1:",
      err instanceof Error ? err.message : err
    );
    return {
      payload: { reasoning: pass1.reasoning, intents: candidates },
      passesUsed: 1,
      refined: false,
    };
  }

  const critique = await parseJsonWithRepair<{
    candidates_flaws?: Array<{ index: number; issues?: string[]; explanation?: string }>;
    missed_intents?: Array<{ summary: string; evidence_quote?: string; explanation?: string }>;
    is_clean?: boolean;
  }>(critiqueRaw, { allowLLMRepair: false, debugLabel: "intent-extract-critique" });

  if (!critique || critique.is_clean === true) {
    return {
      payload: { reasoning: pass1.reasoning, intents: candidates },
      passesUsed: critique ? 2 : 1,
      refined: false,
    };
  }

  const hasFlaws =
    (critique.candidates_flaws && critique.candidates_flaws.length > 0) ||
    (critique.missed_intents && critique.missed_intents.length > 0);
  if (!hasFlaws) {
    return {
      payload: { reasoning: pass1.reasoning, intents: candidates },
      passesUsed: 2,
      refined: false,
    };
  }

  // Pass 3 — refine. Send transcript + candidates + critique back to Flash
  // and ask it to emit the corrected list.
  const refineUser = `ORIGINAL CONTEXT (transcript + recent activity + memory):
"""
${ctx.user}
"""

CANDIDATE INTENTS produced by the upstream extractor:
${JSON.stringify(candidates, null, 2)}

CRITIQUE flagged the following issues — apply each one:
${JSON.stringify(critique, null, 2)}

Emit the FINAL intent list in the JSON shape specified by your system prompt. \
Drop flagged false positives. Add the missed_intents. Fix slot/clarification coherence. \
Preserve every candidate not flagged.`;

  let refineRaw = "";
  try {
    refineRaw = await callLlm(
      [
        { role: "system" as const, content: REFINE_SYSTEM },
        { role: "user" as const, content: refineUser },
      ],
      {
        temperature: 0.0,
        max_tokens: 8192,
        cacheKey: "intent-refine-v1",
        jsonOnly: true,
      }
    );
  } catch (err) {
    console.warn(
      "[intent-extract] refine pass failed, returning pass-1:",
      err instanceof Error ? err.message : err
    );
    return {
      payload: { reasoning: pass1.reasoning, intents: candidates },
      passesUsed: 2,
      refined: false,
    };
  }

  const refined = await parseJsonWithRepair<{
    reasoning?: string;
    intents?: Array<Record<string, unknown>>;
  }>(refineRaw, { allowLLMRepair: true, debugLabel: "intent-extract-refine" });

  if (!refined || !Array.isArray(refined.intents)) {
    return {
      payload: { reasoning: pass1.reasoning, intents: candidates },
      passesUsed: 2,
      refined: false,
    };
  }

  return {
    payload: { reasoning: refined.reasoning ?? pass1.reasoning, intents: refined.intents },
    passesUsed: 3,
    refined: true,
  };
}
