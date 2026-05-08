/**
 * Memory extraction layer for the proactive engine.
 *
 * Today the proactive cascade only writes intents — i.e. tasks the wearer
 * needs to do later. Everything else they say (preferences, names of
 * people in their life, casual references, ongoing context) is dropped
 * after the analyze pass returns. This module reclaims that signal: a
 * separate, lightweight Gemini call reads the same transcript and
 * surfaces "memorable" items the wearer would benefit from us
 * remembering on later analyze calls.
 *
 * Design:
 *   - NO hardcoded categories. The LLM decides what "memorable" means
 *     in context, generically. We do not enumerate "favorite food" /
 *     "spouse name" / etc — that path leads to brittle categories that
 *     miss real signal. Instead we ask for kind/key/value/evidence and
 *     let the model pick.
 *   - Fail-open / fail-empty. If the call fails, JSON is malformed, or
 *     the model returns nothing, we return []. The caller is
 *     fire-and-forget and never blocks the user-facing intent path on
 *     this output.
 *   - Bounded output. We cap the response at 12 items per pass. Spammy
 *     extraction defeats the point of memory — it's supposed to be
 *     high-signal.
 */

import { parseJsonWithRepair } from "@/lib/gemini";
import { callLlm } from "@/lib/llm-cascade";

export interface MemoryItem {
  /** Generic bucket label the LLM picks (preference / fact / relationship / reference / context / etc). */
  kind: string;
  /** Short snake_case label the LLM picks ("favorite_coffee", "sister_lila", "kids_school"). */
  key: string;
  /** The actual fact, in the LLM's words, ready to drop into a future prompt. */
  value: string;
  /** Verbatim quote from the transcript that motivated this item — for auditing. */
  evidence_quote: string;
  /** LLM's confidence the wearer would want this remembered (0..1). */
  confidence: number;
}

const SYSTEM_PROMPT = `You are the long-term MEMORY extractor for an AI wearable's intent engine. \
Your job is the OPPOSITE of intent extraction — you do NOT extract tasks. You extract \
random facts, preferences, names, relationships, and contexts the wearer mentioned \
that a future conversation could benefit from us remembering.

Examples of GOOD memory items (NOT exhaustive — use your judgement):
- preferences ("I always get oat milk at Blue Bottle", "I hate Mondays at the dentist")
- relationships ("my sister Lila just moved to Brooklyn", "John Yokels is my CFO")
- ongoing references ("the Gucci shoes I ordered last week", "the proposal we sent Tuesday")
- contexts ("I'm vegan", "my dog's name is Banjo", "I live in Vancouver")
- recurring patterns ("I work out every Thursday at 6am")

DO NOT extract:
- one-off conversational chit-chat with no lasting relevance ("the weather is nice today")
- the wearer's actionable to-dos (those are intents, not memory — a separate system handles them)
- sensitive content the wearer would not want stored long-term (passwords, SSN, etc) — skip silently
- speculation or hypotheticals ("if I move to Tokyo someday")

You DECIDE the bucket label (\`kind\`) for each item. Keep \`kind\` short and lowercase; \
common ones include preference, fact, relationship, reference, context, routine — but if \
something else fits better, USE IT. There is NO fixed enum.

Pick \`key\` as a short snake_case label that uniquely identifies this fact \
("favorite_coffee", "sister_lila_brooklyn_2026", "vegan_dietary_pref"). The \`key\` is \
how the recall layer will deduplicate / disambiguate later — make it specific, not generic.

Output STRICT JSON, no markdown, no preamble:
{
  "items": [
    {
      "kind": "<short lowercase label>",
      "key": "<short snake_case label>",
      "value": "<the actual content, one short sentence>",
      "evidence_quote": "<verbatim quote from the transcript>",
      "confidence": <0.0..1.0>
    }
  ]
}

Hard limits: at most 12 items. \`value\` ≤ 240 chars. \`evidence_quote\` ≤ 240 chars. \
If nothing memorable is in the transcript, return { "items": [] }. Be conservative: \
if you're unsure whether something is memorable, skip it.`;

const MAX_ITEMS = 12;
const MAX_VALUE_CHARS = 240;
const MAX_EVIDENCE_CHARS = 240;

export async function extractMemoryItems(
  transcript: string,
  localTime: string,
  timezone: string
): Promise<MemoryItem[]> {
  const trimmed = (transcript || "").trim();
  if (trimmed.length === 0) return [];

  const messages = [
    { role: "system" as const, content: SYSTEM_PROMPT },
    {
      role: "user" as const,
      content: `Transcript:\n"""\n${trimmed}\n"""\n\nCurrent local time: ${localTime} (${timezone}).\n\nExtract memory items as JSON.`,
    },
  ];

  let raw = "";
  try {
    raw = await callLlm(messages, {
      temperature: 0.0,
      max_tokens: 2048,
      // Cache the static memory-extract system prompt — this call runs on
      // every analyze tick, so cache hits at ~5min TTL save measurable cost.
      cacheKey: "memory-extract-v1",
      jsonOnly: true,
    });
  } catch (err) {
    console.warn(
      "[memory-extract] gemini call failed; returning []:",
      err instanceof Error ? err.message : err
    );
    return [];
  }

  // Schema-validate-and-repair: parseJsonWithRepair tries strict, fence-strip,
  // substring-extract, then falls back to a tiny Flash repair call. Repair
  // budget is gated by allowLLMRepair=true so it only fires when needed.
  const parsed = await parseJsonWithRepair<{ items?: unknown }>(raw, {
    allowLLMRepair: true,
    debugLabel: "memory-extract",
  });
  if (!parsed || typeof parsed !== "object") return [];
  const items = parsed.items;
  if (!Array.isArray(items)) return [];

  const out: MemoryItem[] = [];
  for (const entry of items) {
    if (entry === null || typeof entry !== "object") continue;
    const e = entry as Record<string, unknown>;

    const kind = String(e.kind ?? "").trim().toLowerCase();
    const key = String(e.key ?? "").trim().toLowerCase();
    const value = String(e.value ?? "").trim();
    const evidenceQuote = String(e.evidence_quote ?? "").trim();
    const confRaw = e.confidence;
    const confidence =
      typeof confRaw === "number" && Number.isFinite(confRaw)
        ? Math.max(0, Math.min(1, confRaw))
        : 0.7;

    if (!kind || !key || !value) continue;

    out.push({
      kind: kind.slice(0, 40),
      key: key.slice(0, 80),
      value: value.slice(0, MAX_VALUE_CHARS),
      evidence_quote: evidenceQuote.slice(0, MAX_EVIDENCE_CHARS),
      confidence,
    });

    if (out.length >= MAX_ITEMS) break;
  }
  return out;
}
