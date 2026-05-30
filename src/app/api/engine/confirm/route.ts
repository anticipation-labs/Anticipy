import { supabaseAdmin } from "@/lib/supabase-admin";
import { executeAction } from "@/lib/execute-action";
import { escapeHtml } from "@/lib/escape";
import {
  recordPreferenceSignal,
  type PreferenceSignal,
} from "@/lib/preference-record";
import { buildUserProfile } from "@/lib/meta-monitor";
import { embedAndStoreIntent } from "@/lib/episode-recall";
import { rateLimit, clientIp } from "@/lib/rate-limit";
import {
  isLegacyPlainUuid,
  legacyGraceActive,
  verifyConfirmToken,
} from "@/lib/confirm-token";

export const dynamic = "force-dynamic";

const HTML_HEADERS = {
  "Content-Type": "text/html; charset=utf-8",
  "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
  "X-Robots-Tag": "noindex, nofollow",
} as const;

// Per-IP rate limit on the confirm GET endpoint. The endpoint runs an
// LLM call (preference reasoning) per request, so even with the atomic
// status-flip guard a flooded URL can still drive Gemini cost. 30/hr per
// IP comfortably covers a real user (a handful of clicks / refreshes per
// session); anything above that is bot traffic.
const CONFIRM_RATE_LIMIT = 30;
const CONFIRM_RATE_WINDOW_MS = 60 * 60 * 1000;

export async function GET(req: Request) {
  // 1) Rate-limit by client IP first — cheapest possible gate. The bucket
  //    namespace pins this limiter to /confirm so other routes don't share
  //    the same bucket.
  const ip = clientIp(req);
  const limit = rateLimit(
    `engine-confirm:${ip}`,
    CONFIRM_RATE_LIMIT,
    CONFIRM_RATE_WINDOW_MS
  );
  if (!limit.allowed) {
    const retryAfter = Math.max(1, Math.ceil((limit.resetAt - Date.now()) / 1000));
    return new Response(
      renderPage(
        "error",
        "Too many requests. Try again in a minute."
      ),
      {
        headers: { ...HTML_HEADERS, "Retry-After": String(retryAfter) },
        status: 429,
      }
    );
  }

  const url = new URL(req.url);
  // Two ways to pass the intent: signed `token` (preferred, new) or bare
  // `intentId` (legacy, accepted during the grace window).
  const tokenParam = url.searchParams.get("token");
  const intentIdParam = url.searchParams.get("intentId");
  const action = url.searchParams.get("action");

  // Resolve intentId from whichever parameter is present.
  let intentId: string | null = null;
  if (tokenParam) {
    const verified = verifyConfirmToken(tokenParam);
    if (!verified.ok) {
      // Distinguish expired vs forged for the user message but never leak
      // whether a token's intentId existed.
      const reason = verified.reason;
      const detail =
        reason === "expired"
          ? "This link has expired. Open Anticipy to see your latest actions."
          : "This link is invalid. Open Anticipy to see your latest actions.";
      return new Response(renderPage("error", detail), {
        headers: HTML_HEADERS,
        status: 400,
      });
    }
    intentId = verified.intentId;
  } else if (intentIdParam) {
    // Legacy bare-UUID fallback — only honoured for a grace period and only
    // when the value really looks like a UUID. Anything else is rejected.
    if (!isLegacyPlainUuid(intentIdParam)) {
      return new Response(
        renderPage("error", "This link is invalid. Open Anticipy to see your latest actions."),
        { headers: HTML_HEADERS, status: 400 }
      );
    }
    if (!legacyGraceActive()) {
      return new Response(
        renderPage(
          "error",
          "This link has expired. Open Anticipy to see your latest actions."
        ),
        { headers: HTML_HEADERS, status: 400 }
      );
    }
    intentId = intentIdParam;
  }

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
        renderPage("error", "We couldn't find this request. It may have expired."),
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

  // Resolve the wearer's user_id and user_email via session_id. user_id
  // scopes the preference signal; user_email gates the test-user broadcast
  // skip below so confirmed test intents never fan out to production
  // extensions. Fail-open on missing session — preference recording and
  // broadcast each handle null safely.
  let prefUserId: string | null = null;
  let sessionEmail: string | null = null;
  if (intentRow?.session_id) {
    const { data: sess } = await supabaseAdmin
      .from("anticipy_sessions")
      .select("user_id, user_email")
      .eq("id", intentRow.session_id)
      .single();
    prefUserId =
      sess && typeof sess.user_id === "string" && sess.user_id.length > 0
        ? sess.user_id
        : null;
    sessionEmail =
      sess && typeof sess.user_email === "string" && sess.user_email.length > 0
        ? sess.user_email
        : null;
  }
  // Same test-user predicate as analyze/route.ts. Keep the conditions in
  // sync with that file — divergence would let test confirms bypass the
  // gate while test analyzes were silenced.
  const isTestUser =
    !!sessionEmail && (
      sessionEmail.endsWith(".test") ||
      sessionEmail.endsWith("@anticipy-test.local") ||
      sessionEmail.startsWith("e2e-test-")
    );

  // Awaited preference recording. We used to fire-and-forget here, but
  // Vercel terminates lambdas the moment the response is sent — so the
  // background insert was getting silently killed. Awaiting adds ~600ms
  // (one Gemini call + one row insert) which is acceptable for a confirm
  // click that only fires once. Failures inside recordPreferenceSignal
  // are already swallowed and logged, so this never blocks the user.
  if (prefUserId && intentRow) {
    const signal: PreferenceSignal =
      newStatus === "confirmed" ? "accept" : "reject";
    try {
      await recordPreferenceSignal(
        prefUserId,
        {
          action_type: intentRow.action_type ?? null,
          summary_for_user: intentRow.summary_for_user ?? null,
          evidence_quote: intentRow.evidence_quote ?? null,
        },
        signal
      );
      // Meta-monitor: rebuild the user's style profile from their last
      // 30 signals. Awaited so the next /analyze call sees an up-to-
      // date profile (no race where the user clicks Yes and immediately
      // dictates again with stale style context). Internal throttle
      // skips the rebuild when too few new signals have arrived since
      // the last one. Cost: at most one Gemini Flash call (~$0.0001).
      try {
        await buildUserProfile(prefUserId);
      } catch (err) {
        console.warn(
          "[confirm] buildUserProfile failed (non-fatal):",
          err instanceof Error ? err.message : err
        );
      }

      // Episode embedding: persist a 768-d Gemini vector over this
      // intent's surface text so future /analyze calls can vector-recall
      // it as a similar past episode. Awaited (Vercel kills the lambda
      // on response — same reason recordPreferenceSignal is awaited).
      // Internal status check makes it a no-op for non-terminal rows;
      // an existing embedding short-circuits the embed call so duplicate
      // signal arrivals don't re-bill the API.
      try {
        await embedAndStoreIntent(intentId);
      } catch (err) {
        console.warn(
          "[confirm] embedAndStoreIntent failed (non-fatal):",
          err instanceof Error ? err.message : err
        );
      }
    } catch (err) {
      // Defensive — recordPreferenceSignal already swallows everything,
      // but never let the user-facing path die over a learning row.
      console.warn(
        "[confirm] recordPreferenceSignal threw unexpectedly:",
        err instanceof Error ? err.message : err
      );
    }
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
      // Test users are SOURCE-gated here so a test confirm cannot fan out into
      // any real user's extension (the broadcast topic is anon-readable, so
      // every connected extension would otherwise pick it up and execute).
      if (result.data?.routing === "browser" && !isTestUser) {
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
                  // user_id required so the extension can filter cross-user
                  // broadcasts and never act on another user's confirm.
                  // anticipy_intents itself doesn't carry user_id (it's
                  // session-scoped); we resolved it from the session row
                  // earlier in this handler as prefUserId.
                  user_id: prefUserId,
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
      ? "Got it. Anticipy is on it."
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
    glyph: "·",
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
<title>Anticipy: ${safeTitle}</title>
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
