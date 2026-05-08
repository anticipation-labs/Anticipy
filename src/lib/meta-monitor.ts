/**
 * Meta-monitor — the "second brain" that watches the first AI's
 * decisions and distills them into a per-user style profile, which
 * the first AI then reads on every analyze call.
 *
 * Architecture:
 *
 *   transcript --> [intent-extract.ts (3-pass self-verify)]
 *                         |
 *                         v
 *                  [intent-gates.ts]
 *                         |
 *                         v
 *                   anticipy_intents
 *                         |
 *                  user clicks Yes / Skip / lets timer expire
 *                         |
 *                         v
 *                  anticipy_preferences  <--- recorded event log
 *                         |
 *               buildUserProfile()  (this file, fire-and-forget)
 *                         |
 *                         v
 *                  anticipy_user_profile  <--- moving snapshot
 *                         |
 *               recallUserProfile()  (next /analyze call)
 *                         |
 *                         v
 *                  injected into prompt as "USER PROFILE"
 *
 * The first AI is stateless across sessions (Gemini Flash has no
 * persistent memory). This module is the closure around it: every
 * confirm/reject signal updates the profile, every analyze reads it.
 *
 * Cost: one extra Flash call per confirm/reject/auto-proceed, fire-
 * and-forget. ~$0.0001/signal. Profile is cached server-side in DB
 * so the analyze read is one row fetch, not an LLM call.
 */
import { supabaseAdmin } from "@/lib/supabase-admin";
import { callGemini } from "@/lib/gemini";

const PROFILE_REBUILD_PROMPT = `You are a meta-monitor for an AI assistant. The user has just \
accepted or rejected an extracted intent. Your job is to update the user's \
STYLE PROFILE so future extractions match their preferences without asking again.

You receive: (a) the user's existing profile (style_summary, common_accepts, \
common_rejects), (b) the last 30 preference signals (intent + accept/reject + \
reasoning).

Output a refreshed profile. Be DECLARATIVE and CONCRETE — \
"this user accepts shopping reminders for groceries but rejects travel \
bookings without an explicit confirmation step" is good. \
"the user has preferences" is bad. Avoid timeline language ("recently", \
"this week") — the profile is consulted asynchronously and ages quickly.

Rules:
- style_summary: 2-4 sentences. Distinctive patterns only. Skip generic \
  observations.
- common_accepts / common_rejects: arrays of {action_type, summary_pattern, \
  why} objects. summary_pattern is a SHORT phrase that captures the gist \
  ("morning coffee orders", "post-meeting follow-ups"), not a verbatim quote.
- drift_alerts: array of {kind, evidence}. Examples of drift to flag:
    "spike_in_rejects" → user has rejected ≥3 of the last 5 of action_type X
    "auto_proceed_then_undo" → user let a timeout fire, then undid the action
    "contradicts_prior_accept" → user rejected something near-identical to a previous accept

Be brutally honest. The point of this profile is to MAKE THE FIRST AI BETTER, \
not to flatter the user. If they reject 80% of what gets extracted, say so.

Return STRICT JSON, no preamble:

{
  "style_summary": "<2-4 sentences>",
  "common_accepts": [{"action_type": "...", "summary_pattern": "...", "why": "..."}],
  "common_rejects": [{"action_type": "...", "summary_pattern": "...", "why": "..."}],
  "drift_alerts": [{"kind": "...", "evidence": "..."}]
}`;

interface PreferenceRow {
  signal: string;
  intent_summary: string | null;
  action_type: string | null;
  evidence_quote: string | null;
  reasoning: string | null;
  created_at: string;
}

interface ProfileRow {
  user_id: string;
  style_summary: string;
  common_accepts: unknown[];
  common_rejects: unknown[];
  drift_alerts: unknown[];
  signal_count: number;
  updated_at: string;
}

/**
 * Pull the per-user style profile to inject into an /analyze prompt.
 * Returns "" when the user has fewer than 3 signals — early-stage
 * users get the unbiased baseline rather than a noisy half-formed
 * profile. Fail-open on any error: the first AI is never blocked
 * waiting on the second brain.
 */
export async function recallUserProfile(userId: string): Promise<string> {
  if (!userId) return "";
  try {
    const { data, error } = await supabaseAdmin
      .from("anticipy_user_profile")
      .select("style_summary, common_accepts, common_rejects, drift_alerts, signal_count")
      .eq("user_id", userId)
      .maybeSingle();
    if (error || !data) return "";
    if ((data.signal_count ?? 0) < 3) return "";
    const blocks: string[] = [];
    if (data.style_summary) {
      blocks.push(`STYLE: ${data.style_summary}`);
    }
    const accepts = Array.isArray(data.common_accepts) ? data.common_accepts : [];
    if (accepts.length) {
      const lines = accepts
        .slice(0, 5)
        .map((a) => {
          const o = a as { action_type?: string; summary_pattern?: string; why?: string };
          return `  + ${o.action_type ?? "?"} / ${o.summary_pattern ?? "?"} — ${o.why ?? ""}`;
        });
      blocks.push(`USER USUALLY ACCEPTS:\n${lines.join("\n")}`);
    }
    const rejects = Array.isArray(data.common_rejects) ? data.common_rejects : [];
    if (rejects.length) {
      const lines = rejects
        .slice(0, 5)
        .map((a) => {
          const o = a as { action_type?: string; summary_pattern?: string; why?: string };
          return `  - ${o.action_type ?? "?"} / ${o.summary_pattern ?? "?"} — ${o.why ?? ""}`;
        });
      blocks.push(`USER USUALLY REJECTS:\n${lines.join("\n")}`);
    }
    const alerts = Array.isArray(data.drift_alerts) ? data.drift_alerts : [];
    if (alerts.length) {
      const lines = alerts
        .slice(0, 3)
        .map((a) => {
          const o = a as { kind?: string; evidence?: string };
          return `  ! ${o.kind ?? "?"}: ${o.evidence ?? ""}`;
        });
      blocks.push(`DRIFT ALERTS:\n${lines.join("\n")}`);
    }
    return blocks.length ? `\nUSER PROFILE (use to bias your extraction):\n${blocks.join("\n\n")}\n` : "";
  } catch {
    return "";
  }
}

/**
 * Rebuild the user's style profile from their last 30 preference
 * signals. Designed to be called fire-and-forget after every signal
 * record (confirm / reject / auto-proceed). Idempotent — safe to
 * call repeatedly. Throttle by signal_count: if the row was updated
 * within the last 5 signals, skip the rebuild (the profile won't
 * meaningfully change).
 */
export async function buildUserProfile(userId: string): Promise<void> {
  if (!userId) return;
  try {
    const { data: existing } = await supabaseAdmin
      .from("anticipy_user_profile")
      .select("signal_count")
      .eq("user_id", userId)
      .maybeSingle();
    const oldCount = (existing?.signal_count ?? 0) as number;

    // Pull last 30 signals — enough to capture style without flooding
    // the rebuild prompt.
    const { data: signals, error: sigErr } = await supabaseAdmin
      .from("anticipy_preferences")
      .select("signal, intent_summary, action_type, evidence_quote, reasoning, created_at")
      .eq("user_id", userId)
      .order("created_at", { ascending: false })
      .limit(30);
    if (sigErr || !signals) return;
    const newCount = signals.length;

    // Throttle: if we've already built a profile and only ≤2 new
    // signals have arrived since, skip. Profile won't meaningfully
    // shift on small deltas; the cost compounds across heavy users.
    if (oldCount > 0 && newCount > 0 && newCount - oldCount <= 2 && newCount === oldCount) {
      return;
    }

    if (newCount < 3) return; // not enough signal yet

    // Pull existing profile to feed back into the rebuild — this
    // gives the meta-monitor continuity rather than re-deriving from
    // scratch each time.
    const { data: prevProfile } = await supabaseAdmin
      .from("anticipy_user_profile")
      .select("style_summary, common_accepts, common_rejects")
      .eq("user_id", userId)
      .maybeSingle();

    const userMessage = JSON.stringify({
      existing_profile: prevProfile ?? {
        style_summary: "",
        common_accepts: [],
        common_rejects: [],
      },
      recent_signals: (signals as PreferenceRow[]).map((s) => ({
        signal: s.signal,
        action_type: s.action_type,
        intent_summary: s.intent_summary,
        evidence_quote: s.evidence_quote,
        reasoning: s.reasoning,
      })),
    });

    let llmText = "";
    try {
      llmText = await callGemini(
        [
          { role: "system", content: PROFILE_REBUILD_PROMPT },
          { role: "user", content: userMessage },
        ],
        { temperature: 0.2, max_tokens: 1500, cacheKey: "meta-monitor-v1" }
      );
    } catch {
      return; // upstream unavailable / quota exhausted — leave profile alone
    }
    if (!llmText) return;

    let parsed: {
      style_summary?: string;
      common_accepts?: unknown[];
      common_rejects?: unknown[];
      drift_alerts?: unknown[];
    } = {};
    try {
      const stripped = llmText.replace(/^```(?:json)?\s*/, "").replace(/```\s*$/, "");
      parsed = JSON.parse(stripped);
    } catch {
      return; // malformed — leave the previous profile in place
    }

    const row = {
      user_id: userId,
      style_summary: typeof parsed.style_summary === "string" ? parsed.style_summary.slice(0, 1500) : "",
      common_accepts: Array.isArray(parsed.common_accepts) ? parsed.common_accepts.slice(0, 10) : [],
      common_rejects: Array.isArray(parsed.common_rejects) ? parsed.common_rejects.slice(0, 10) : [],
      drift_alerts: Array.isArray(parsed.drift_alerts) ? parsed.drift_alerts.slice(0, 5) : [],
      signal_count: newCount,
      updated_at: new Date().toISOString(),
    };

    await supabaseAdmin
      .from("anticipy_user_profile")
      .upsert(row, { onConflict: "user_id" });
  } catch (err) {
    // Fire-and-forget — never let the meta-monitor break a user-
    // facing flow. Log only.
    console.warn(
      "[meta-monitor] buildUserProfile failed:",
      err instanceof Error ? err.message : err
    );
  }
}

export type { ProfileRow };
