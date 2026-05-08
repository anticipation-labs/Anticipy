import { supabaseAdmin } from "@/lib/supabase-admin";
import { executeAction } from "@/lib/execute-action";
import { escapeHtml } from "@/lib/escape";
import {
  recordPreferenceSignal,
  type PreferenceSignal,
} from "@/lib/preference-record";

export const dynamic = "force-dynamic";

const HTML_HEADERS = {
  "Content-Type": "text/html; charset=utf-8",
  "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
  "X-Robots-Tag": "noindex, nofollow",
} as const;

export async function GET(req: Request) {
  const url = new URL(req.url);
  const intentId = url.searchParams.get("intentId");
  const action = url.searchParams.get("action");

  if (!intentId || !action || (action !== "yes" && action !== "no")) {
    return new Response(
      renderPage("error", "Missing or invalid request parameters."),
      { headers: HTML_HEADERS, status: 400 }
    );
  }

  const newStatus = action === "yes" ? "confirmed" : "rejected";

  // Atomic guard: update only if status is still "pending" and return the updated row.
  // This single round-trip eliminates the SELECT→check→UPDATE TOCTOU race and also
  // avoids stale-read false positives from PgBouncer connection pooling.
  const { data: updated, error } = await supabaseAdmin
    .from("anticipy_intents")
    .update({ status: newStatus })
    .eq("id", intentId)
    .eq("status", "pending")
    .select("id");

  if (error) {
    return new Response(
      renderPage("error", "Something went wrong on our end. Please try again."),
      { headers: HTML_HEADERS, status: 500 }
    );
  }

  // Zero rows updated means either the intent doesn't exist or was already handled.
  if (!updated || updated.length === 0) {
    const { data: existingIntent } = await supabaseAdmin
      .from("anticipy_intents")
      .select("id")
      .eq("id", intentId)
      .single();

    if (!existingIntent) {
      return new Response(
        renderPage("error", "We couldn't find this request — it may have expired."),
        { headers: HTML_HEADERS, status: 404 }
      );
    }

    return new Response(
      renderPage(
        "handled",
        "This action has already been confirmed or skipped. Nothing more to do."
      ),
      { headers: HTML_HEADERS }
    );
  }

  let executionMessage = "";

  // Always pull the intent (for both yes and no) so we can record a
  // preference signal. Re-using the same fetch on the confirmed branch.
  const { data: intentRow } = await supabaseAdmin
    .from("anticipy_intents")
    .select("*")
    .eq("id", intentId)
    .single();

  // Resolve the wearer's user_id via session_id so recorded preferences
  // are scoped to the right user. Fail-open if the session row is gone.
  let prefUserId: string | null = null;
  if (intentRow?.session_id) {
    const { data: sess } = await supabaseAdmin
      .from("anticipy_sessions")
      .select("user_id")
      .eq("id", intentRow.session_id)
      .single();
    prefUserId =
      sess && typeof sess.user_id === "string" && sess.user_id.length > 0
        ? sess.user_id
        : null;
  }

  // Fire-and-forget preference recording: a small Gemini call summarizes
  // WHY this signal landed (one sentence) and writes a row to
  // anticipy_preferences. The reasoning is read back into future intent
  // extraction prompts via recallUserPreferences. Failures are logged.
  if (prefUserId && intentRow) {
    const signal: PreferenceSignal =
      newStatus === "confirmed" ? "accept" : "reject";
    void recordPreferenceSignal(
      prefUserId,
      {
        action_type: intentRow.action_type ?? null,
        summary_for_user: intentRow.summary_for_user ?? null,
        evidence_quote: intentRow.evidence_quote ?? null,
      },
      signal
    );
  }

  if (newStatus === "confirmed") {
    const intent = intentRow;

    if (intent) {
      const result = await executeAction(intent);

      // Always update intent status and log the action — including browser-routed ones.
      // Browser-routed actions now save a note fallback inside executeAction, so
      // there is always a record even if the extension never picks this up.
      await supabaseAdmin
        .from("anticipy_intents")
        .update({ status: result.success ? "executed" : "failed" })
        .eq("id", intentId);

      await supabaseAdmin.from("anticipy_actions").insert({
        intent_id: intentId,
        status: result.success ? "success" : "failed",
        result: result.data,
        external_id: result.externalId,
      });

      // For browser-routed actions, also broadcast to the Chrome extension as an
      // additional best-effort execution path (note fallback already saved above).
      if (result.data?.routing === "browser") {
        const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
        const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
        if (supabaseUrl && serviceKey) {
          fetch(`${supabaseUrl}/realtime/v1/api/broadcast`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              apikey: serviceKey,
              Authorization: `Bearer ${serviceKey}`,
            },
            body: JSON.stringify({
              messages: [{
                topic: "anticipy-intents",
                event: "confirmed_intent",
                payload: {
                  ...intent,
                  status: "confirmed",
                  parameters: {
                    ...(intent.parameters as Record<string, unknown>),
                    browser_task: result.data.task,
                  },
                },
              }],
            }),
          }).catch((e: Error) => console.warn("[broadcast] confirmed_intent failed:", e.message));
        }
      }

      executionMessage = result.message;
    }
  }

  const variant = newStatus === "confirmed" ? "confirmed" : "skipped";
  const mainMessage =
    variant === "confirmed"
      ? "Got it — Anticipy is on it."
      : "Skipped. No action will be taken.";

  return new Response(renderPage(variant, mainMessage, executionMessage), {
    headers: HTML_HEADERS,
  });
}

type Variant = "confirmed" | "skipped" | "handled" | "error";

interface VariantConfig {
  title: string;
  glyph: string;
  glyphColor: string;
  accent: string;
}

const VARIANTS: Record<Variant, VariantConfig> = {
  confirmed: {
    title: "Confirmed",
    glyph: "✓",
    glyphColor: "#C8A97E",
    accent: "#C8A97E",
  },
  skipped: {
    title: "Skipped",
    glyph: "—",
    glyphColor: "#8A8A8A",
    accent: "#8A8A8A",
  },
  handled: {
    title: "Already handled",
    glyph: "·",
    glyphColor: "#8A8A8A",
    accent: "#8A8A8A",
  },
  error: {
    title: "Something went wrong",
    glyph: "!",
    glyphColor: "#FF6B6B",
    accent: "#FF6B6B",
  },
};

/**
 * Renders the post-confirm/skip page. `message` is plain text and is
 * escaped here. `detail` is optional and also escaped here — pass the
 * raw execution message string (no HTML).
 */
function renderPage(variant: Variant, message: string, detail?: string): string {
  const cfg = VARIANTS[variant];
  const safeTitle = escapeHtml(cfg.title);
  const safeMessage = escapeHtml(message);
  const detailBlock = detail
    ? `<p style="margin:18px 0 0 0;font-size:13px;line-height:1.5;color:${cfg.accent};">${escapeHtml(detail)}</p>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="dark">
<meta name="robots" content="noindex,nofollow">
<title>Anticipy — ${safeTitle}</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body {
    margin: 0;
    background: #0C0C0C;
    color: #FAFAFA;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
  }
  .card {
    width: 100%;
    max-width: 420px;
    background: #111111;
    border: 1px solid #1F1F1F;
    border-radius: 20px;
    padding: 40px 32px;
    text-align: center;
  }
  .glyph {
    width: 56px;
    height: 56px;
    margin: 0 auto 20px auto;
    border-radius: 50%;
    border: 1px solid ${cfg.accent}33;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    line-height: 1;
    color: ${cfg.glyphColor};
  }
  .brand {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 13px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #C8A97E;
    margin: 0 0 6px 0;
  }
  h1 {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 22px;
    font-weight: 400;
    color: #FAFAFA;
    margin: 0 0 14px 0;
  }
  p.message {
    font-size: 15px;
    line-height: 1.55;
    color: #B8B8B8;
    margin: 0;
  }
  a.back {
    display: inline-block;
    margin-top: 28px;
    padding: 10px 22px;
    background: rgba(200, 169, 126, 0.08);
    border: 1px solid rgba(200, 169, 126, 0.25);
    color: #C8A97E;
    text-decoration: none;
    border-radius: 100px;
    font-size: 13px;
    font-weight: 500;
  }
  a.back:hover { background: rgba(200, 169, 126, 0.14); }
</style>
</head>
<body>
  <main class="card" role="main">
    <div class="glyph" aria-hidden="true">${cfg.glyph}</div>
    <p class="brand">Anticipy</p>
    <h1>${safeTitle}</h1>
    <p class="message">${safeMessage}</p>
    ${detailBlock}
    <a class="back" href="/engine">Open dashboard</a>
  </main>
</body>
</html>`;
}
