import { supabaseAdmin } from "@/lib/supabase-admin";
import { executeAction } from "@/lib/execute-action";
import {
  verifyTwilioRequest,
  reconstructWebhookUrl,
  formDataToParams,
} from "@/lib/twilio-verify";

export const dynamic = "force-dynamic";

/**
 * Twilio inbound SMS webhook.
 * Parses YES/NO replies and confirms/rejects the most recent pending intent.
 */
export async function POST(req: Request) {
  const formData = await req.formData();
  const params = formDataToParams(formData);
  const signature = req.headers.get("x-twilio-signature");
  if (!verifyTwilioRequest(signature, reconstructWebhookUrl(req), params)) {
    return new Response("Forbidden", { status: 403 });
  }

  const body = (params.Body || "").trim().toLowerCase();
  const from = params.From || "";

  if (!body || !from) {
    return twimlResponse("Anticipy: Sorry, I didn't understand that.");
  }

  const isConfirm =
    body === "yes" ||
    body === "y" ||
    body === "1" ||
    body === "confirm" ||
    body === "do it";

  const isReject =
    body === "no" ||
    body === "n" ||
    body === "2" ||
    body === "skip" ||
    body === "cancel";

  if (!isConfirm && !isReject) {
    return twimlResponse(
      "Anticipy: Reply YES to confirm or NO to skip the last action."
    );
  }

  // Resolve which intent the wearer is replying to. Older code picked the
  // most-recent SMS for this phone — but if two intents are pending and
  // the user replies "yes" to the first one (still in their phone), we
  // would silently confirm the SECOND, more-recent one. Now: when more
  // than one pending intent exists, we either accept an explicit ID
  // prefix in the reply ("yes ab12") or ask for one. Generic — no
  // hardcoded action types or per-user logic.
  const { data: pendingNotifications } = await supabaseAdmin
    .from("anticipy_notifications")
    .select("intent_id, sent_at")
    .eq("recipient", from)
    .eq("channel", "sms")
    .order("sent_at", { ascending: false })
    .limit(20);

  const candidateIntentIds = Array.from(
    new Set((pendingNotifications ?? []).map((n) => n.intent_id).filter(Boolean))
  ) as string[];

  if (candidateIntentIds.length === 0) {
    return twimlResponse("Anticipy: No pending actions found.");
  }

  // Filter to actually-pending intents — anything already executed/skipped
  // is no longer a candidate for this reply.
  const { data: pendingIntents } = await supabaseAdmin
    .from("anticipy_intents")
    .select("id, summary_for_user, status")
    .in("id", candidateIntentIds)
    .eq("status", "pending");

  const stillPending = pendingIntents ?? [];
  if (stillPending.length === 0) {
    return twimlResponse("Anticipy: That action has already been handled.");
  }

  // Detect a 4-12 char alphanumeric ID prefix in the body, e.g. "yes ab12cd".
  // Match against the start of the intent UUID — short, generic, no schemas.
  const idTokenMatch = body.match(/\b([0-9a-f]{4,12})\b/i);
  const idPrefix = idTokenMatch ? idTokenMatch[1].toLowerCase() : null;

  let intent: typeof stillPending[number] | null = null;
  if (stillPending.length === 1) {
    intent = stillPending[0];
  } else if (idPrefix) {
    const matches = stillPending.filter((row) =>
      String(row.id).toLowerCase().startsWith(idPrefix)
    );
    if (matches.length === 1) {
      intent = matches[0];
    } else if (matches.length > 1) {
      return twimlResponse(
        "Anticipy: That ID prefix matches multiple actions. Reply with more characters."
      );
    } else {
      return twimlResponse(
        "Anticipy: I couldn't find an action matching that ID. Open Anticipy for the list."
      );
    }
  } else {
    // Multiple pending — ask which one. Show first 4 chars of each id and
    // a short summary so the wearer knows which to disambiguate.
    const lines = stillPending
      .slice(0, 4)
      .map((row) => {
        const id4 = String(row.id).slice(0, 4);
        const sum = String(row.summary_for_user || "(no summary)").slice(0, 60);
        return `${id4}: ${sum}`;
      })
      .join("\n");
    return twimlResponse(
      `Anticipy: ${stillPending.length} actions pending. Reply YES <id> with one of:\n${lines}`
    );
  }

  if (!intent) {
    return twimlResponse("Anticipy: That action has already been handled.");
  }
  const intentId = intent.id;

  const newStatus = isConfirm ? "confirmed" : "rejected";

  // Atomic claim: only update if still pending, and check the row count.
  // Without the count check, two near-simultaneous webhooks (e.g. SMS reply
  // and email-link click) could both pass the SELECT above, only one wins
  // the UPDATE, but the loser still falls through to executeAction below
  // and runs the action a second time.
  const { data: flipped } = await supabaseAdmin
    .from("anticipy_intents")
    .update({ status: newStatus })
    .eq("id", intentId)
    .eq("status", "pending")
    .select("id");

  if (!flipped || flipped.length === 0) {
    return twimlResponse("Anticipy: That action has already been handled.");
  }

  // Record the reply
  await supabaseAdmin
    .from("anticipy_notifications")
    .update({
      reply_received_at: new Date().toISOString(),
      reply_text: body,
    })
    .eq("intent_id", intentId)
    .eq("channel", "sms");

  if (isConfirm) {
    // Fetch the FULL intent row before executing — the disambiguation
    // SELECT only pulled (id, summary, status) above.
    const { data: fullIntent } = await supabaseAdmin
      .from("anticipy_intents")
      .select("*")
      .eq("id", intentId)
      .single();

    if (!fullIntent) {
      return twimlResponse("Anticipy: That action has already been handled.");
    }

    const result = await executeAction(fullIntent);

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

    return twimlResponse(
      result.success
        ? `Anticipy: Done! ${result.message}`
        : `Anticipy: Sorry, that failed. ${result.message}`
    );
  }

  return twimlResponse("Anticipy: Skipped. No action taken.");
}

function twimlResponse(message: string) {
  const twiml = `<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>${escapeXml(message)}</Message></Response>`;
  return new Response(twiml, {
    headers: { "Content-Type": "text/xml" },
  });
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
