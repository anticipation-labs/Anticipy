/**
 * Preference recording — when an intent transitions to a terminal state
 * (confirmed / rejected / executed / failed / auto_proceeded), summarize
 * WHY in one short sentence via Gemini Flash and persist the row to
 * anticipy_preferences for future recall.
 *
 * The reasoning is generic — the LLM picks the words. We never hardcode
 * categories. Future intent prompts will read these reasons back via
 * recallUserPreferences and use them to pre-filter.
 *
 * Always fire-and-forget at the call site: failures are logged and
 * never block the user-facing path.
 */
import { callGemini } from "@/lib/gemini";
import { supabaseAdmin } from "@/lib/supabase-admin";

export type PreferenceSignal =
  | "accept"
  | "reject"
  | "edit"
  | "auto_proceed";

interface IntentLike {
  action_type?: string | null;
  summary_for_user?: string | null;
  evidence_quote?: string | null;
}

const REASONING_SYSTEM_PROMPT = `You summarize WHY a wearer accepted or rejected a specific proposed intent, in one short sentence (<= 22 words). \
The summary will be re-fed into the intent-extraction prompt later as a personalization hint.

Rules:
- Be specific to THIS intent and the signal. Cite the action and the user-visible reason that fits.
- Do NOT invent reasons not in the data. If the only signal is a yes/no with no extra context, write something neutral and minimal.
- Use third-person ("user prefers...", "user dislikes...", "user usually accepts..."). Never use first person or address the user.
- Output PLAIN TEXT only. No JSON, no quotes, no preamble.
- Generic phrasing — do not enumerate fixed categories. Examples (NOT a fixed list): "user dislikes morning meetings", "user usually confirms shopping intents", "user rejects subscription sign-ups", "user accepts reminder follow-ups for family".

If the signal is reject, lean toward "user dislikes / avoids / rejects ...". \
If accept, lean toward "user accepts / confirms / wants ...". \
If auto_proceed, lean toward "user did not respond; system auto-confirmed/declined ...". \
If edit, lean toward "user kept the intent but adjusted ...".`;

async function summarizeReasoning(
  signal: PreferenceSignal,
  intent: IntentLike
): Promise<string> {
  const summary = String(intent.summary_for_user ?? "").trim();
  const evidence = String(intent.evidence_quote ?? "").trim();
  const action = String(intent.action_type ?? "").trim();

  if (!summary && !evidence) {
    // Nothing to summarize. Caller still records a row with empty reasoning.
    return "";
  }

  const userMsg =
    `Signal: ${signal}\n` +
    `Action type: ${action || "unknown"}\n` +
    `Intent summary: ${summary || "(none)"}\n` +
    `Evidence quote: ${evidence || "(none)"}\n\n` +
    `Write the one-sentence reasoning now.`;

  try {
    const raw = await callGemini(
      [
        { role: "system", content: REASONING_SYSTEM_PROMPT },
        { role: "user", content: userMsg },
      ],
      { temperature: 0.0, max_tokens: 120 }
    );
    // Gemini returns JSON-formatted output by default in this codebase
    // (responseMimeType: application/json). Strip wrapping quotes/braces
    // defensively. We asked for plain text, but be tolerant.
    const trimmed = (raw || "").trim();
    if (!trimmed) return "";
    // If the model wrapped the line in JSON, peel one layer.
    if (
      (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
      (trimmed.startsWith("[") && trimmed.endsWith("]"))
    ) {
      try {
        const parsed = JSON.parse(trimmed);
        if (typeof parsed === "string") return parsed.trim().slice(0, 240);
        if (parsed && typeof parsed === "object") {
          // Common shapes: {reasoning: "..."} / {text: "..."} / first string value.
          for (const v of Object.values(parsed as Record<string, unknown>)) {
            if (typeof v === "string" && v.trim()) {
              return v.trim().slice(0, 240);
            }
          }
        }
      } catch {
        // fall through and use the raw line
      }
    }
    // Strip leading quotes ("..." or '...') the model sometimes emits.
    const stripped = trimmed.replace(/^["']|["']$/g, "").trim();
    return stripped.slice(0, 240);
  } catch (err) {
    console.warn(
      "[preference-record] gemini reasoning call failed:",
      err instanceof Error ? err.message : err
    );
    return "";
  }
}

export async function recordPreferenceSignal(
  userId: string,
  intent: IntentLike,
  signal: PreferenceSignal
): Promise<void> {
  if (!userId) return;
  const summary = String(intent.summary_for_user ?? "").trim();
  if (!summary) {
    // Without a summary we have nothing useful to recall later.
    return;
  }

  const reasoning = await summarizeReasoning(signal, intent);

  try {
    const { error } = await supabaseAdmin.from("anticipy_preferences").insert({
      user_id: userId,
      signal,
      intent_summary: summary.slice(0, 500),
      action_type: intent.action_type
        ? String(intent.action_type).slice(0, 80)
        : null,
      evidence_quote: intent.evidence_quote
        ? String(intent.evidence_quote).slice(0, 500)
        : null,
      reasoning: reasoning || null,
    });
    if (error) {
      console.warn(
        "[preference-record] insert failed:",
        error.message
      );
    }
  } catch (err) {
    console.warn(
      "[preference-record] insert threw:",
      err instanceof Error ? err.message : err
    );
  }
}
