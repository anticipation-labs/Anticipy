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
import { callGroq } from "@/lib/groq";
import { callMistral } from "@/lib/mistral";

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

// Per-process inflight set. Two simultaneous buildUserProfile calls
// for the same userId in the same lambda would otherwise both pay the
// Gemini round-trip and one would overwrite the other (lost update).
// We coalesce them: the second caller awaits the first call's promise.
// On a horizontally-scaled deploy two different lambdas can still
// race — that's fine because we now use a freshest-count read +
// monotonic upsert (see buildUserProfile body) so the older write
// can't clobber the newer one.
const INFLIGHT_BUILDS = new Map<string, Promise<void>>();

/**
 * Count anticipy_preferences rows for the user via a HEAD request.
 * Used as the canonical signal_count source — distinct from
 * `signals.length`, which is capped by the .limit(30) we pull for
 * the rebuild prompt and would saturate at 30 even as the user
 * fans more in. Race-safe upserts compare against this value.
 */
async function countPreferencesForUser(userId: string): Promise<number> {
  const { count, error } = await supabaseAdmin
    .from("anticipy_preferences")
    .select("id", { count: "exact", head: true })
    .eq("user_id", userId);
  if (error) return 0;
  return count ?? 0;
}

/**
 * Rebuild the user's style profile from their last 30 preference
 * signals. Designed to be called fire-and-forget after every signal
 * record (confirm / reject / auto-proceed). Idempotent — safe to
 * call repeatedly.
 *
 * Throttle: if the persisted profile already reflects within ≤2 of
 * the current preference count (i.e. at most 2 new signals have
 * landed since the last build) we skip the rebuild — the profile
 * wouldn't meaningfully shift on a delta that small and the cost
 * compounds across heavy users.
 *
 * Concurrency: same-process duplicate calls are coalesced via
 * INFLIGHT_BUILDS. Cross-process races are handled by:
 *   (a) reading the FRESHEST signal_count immediately before the
 *       upsert (not the value captured at function entry), and
 *   (b) writing signal_count := MAX(stored, ours) so older slower
 *       writes can never roll back a newer faster write's count.
 */
export async function buildUserProfile(userId: string): Promise<void> {
  if (!userId) return;
  const existing = INFLIGHT_BUILDS.get(userId);
  if (existing) return existing;
  const promise = buildUserProfileInner(userId).finally(() => {
    INFLIGHT_BUILDS.delete(userId);
  });
  INFLIGHT_BUILDS.set(userId, promise);
  return promise;
}

async function buildUserProfileInner(userId: string): Promise<void> {
  try {
    // Read the existing row's signal_count BEFORE any work — this
    // is the throttle baseline. It is NOT the value we eventually
    // write back (we re-read freshly at upsert time, see below).
    const { data: existing } = await supabaseAdmin
      .from("anticipy_user_profile")
      .select("signal_count")
      .eq("user_id", userId)
      .maybeSingle();
    const oldCount = (existing?.signal_count ?? 0) as number;

    // Canonical count of preferences (independent of the .limit(30)
    // window below). signals.length saturates at 30 and would make
    // the throttle fire forever once a user crossed that threshold.
    const trueCount = await countPreferencesForUser(userId);

    // Throttle: skip if at most 2 new signals have arrived since the
    // last successful build. Profile won't meaningfully shift on a
    // delta that small and the cost compounds across heavy users.
    // Always rebuild on the very first build (oldCount=0) so the user
    // gets a profile as soon as they cross the 3-signal floor.
    if (oldCount > 0 && trueCount - oldCount <= 2) {
      return;
    }

    if (trueCount < 3) return; // not enough signal yet

    // Pull last 30 signals — enough to capture style without flooding
    // the rebuild prompt.
    const { data: signals, error: sigErr } = await supabaseAdmin
      .from("anticipy_preferences")
      .select(
        "signal, intent_summary, action_type, evidence_quote, reasoning, created_at"
      )
      .eq("user_id", userId)
      .order("created_at", { ascending: false })
      .limit(30);
    if (sigErr || !signals) return;
    if (signals.length < 3) return; // belt-and-suspenders

    // Pull existing profile body to feed back into the rebuild — this
    // gives the meta-monitor continuity rather than re-deriving from
    // scratch each time.
    const { data: prevProfile } = await supabaseAdmin
      .from("anticipy_user_profile")
      .select("style_summary, common_accepts, common_rejects, signal_count")
      .eq("user_id", userId)
      .maybeSingle();

    const userMessage = JSON.stringify({
      existing_profile: prevProfile
        ? {
            style_summary: prevProfile.style_summary,
            common_accepts: prevProfile.common_accepts,
            common_rejects: prevProfile.common_rejects,
          }
        : {
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

    // Provider redundancy chain (v-final-prototype whitelist, 2026-05-13):
    // A=Gemini, B=Groq, C=Mistral. Kimi/Moonshot removed (forbidden).
    // Each tier uses that provider's best available model. If A is
    // quota'd, B takes over with no quality drop; if B fails, C takes over.
    let llmText = "";
    let usedProvider = "";
    type Plan = {
      name: string;
      run: () => Promise<string>;
    };
    const plans: Plan[] = [
      {
        name: "gemini",
        run: () =>
          callGemini(
            [
              { role: "system", content: PROFILE_REBUILD_PROMPT },
              { role: "user", content: userMessage },
            ],
            { temperature: 0.2, max_tokens: 1500, cacheKey: "meta-monitor-v1" }
          ),
      },
      {
        name: "groq",
        run: () =>
          callGroq(
            [
              { role: "system", content: PROFILE_REBUILD_PROMPT },
              { role: "user", content: userMessage },
            ],
            {
              temperature: 0.2,
              max_tokens: 1500,
              response_format: { type: "json_object" },
            }
          ),
      },
      {
        name: "mistral",
        run: () =>
          callMistral(
            [
              { role: "system", content: PROFILE_REBUILD_PROMPT },
              { role: "user", content: userMessage },
            ],
            {
              model: "mistral-small-latest",
              temperature: 0.2,
              max_tokens: 1500,
              jsonOnly: true,
            }
          ),
      },
    ];
    const errors: string[] = [];
    for (const plan of plans) {
      try {
        llmText = await plan.run();
        if (!llmText) throw new Error(`${plan.name} returned empty`);
        usedProvider = plan.name;
        break;
      } catch (err) {
        const msg = err instanceof Error ? err.message.slice(0, 160) : String(err);
        errors.push(`${plan.name}: ${msg}`);
        console.warn(
          `[meta-monitor] ${plan.name} failed; trying next plan:`,
          msg
        );
      }
    }
    if (!llmText) {
      console.warn(
        `[meta-monitor] All providers failed; skipping rebuild — ${errors.join(" | ")}`
      );
      return;
    }

    let parsed: {
      style_summary?: string;
      common_accepts?: unknown[];
      common_rejects?: unknown[];
      drift_alerts?: unknown[];
    } = {};
    try {
      // Test-only knob: lets engine/test_meta_monitor.py exercise the
      // "Gemini returned non-JSON" path without us mocking the network.
      // No-op in production where the env var is never set.
      if (process.env.META_MONITOR_TEST_FORCE_MALFORMED === "1") {
        throw new Error("forced malformed for tests");
      }
      const stripped = llmText
        .replace(/^```(?:json)?\s*/, "")
        .replace(/```\s*$/, "");
      parsed = JSON.parse(stripped);
    } catch {
      return; // malformed — leave the previous profile in place
    }

    // Re-read the row IMMEDIATELY before upsert. A concurrent build
    // for the same user (different lambda / different process) may
    // have advanced signal_count since our entry-time read; we never
    // want to roll it back.
    const { data: latest } = await supabaseAdmin
      .from("anticipy_user_profile")
      .select("signal_count")
      .eq("user_id", userId)
      .maybeSingle();
    const latestStored = (latest?.signal_count ?? 0) as number;
    // Use the live preferences count fetched FRESH so we never pin
    // a stale snapshot from function entry — and ensure the persisted
    // count is monotone with respect to the current truth.
    const freshTrueCount = await countPreferencesForUser(userId);
    const writeCount = Math.max(latestStored, freshTrueCount);

    const row = {
      user_id: userId,
      style_summary:
        typeof parsed.style_summary === "string"
          ? parsed.style_summary.slice(0, 1500)
          : "",
      common_accepts: Array.isArray(parsed.common_accepts)
        ? parsed.common_accepts.slice(0, 10)
        : [],
      common_rejects: Array.isArray(parsed.common_rejects)
        ? parsed.common_rejects.slice(0, 10)
        : [],
      drift_alerts: Array.isArray(parsed.drift_alerts)
        ? parsed.drift_alerts.slice(0, 5)
        : [],
      signal_count: writeCount,
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
