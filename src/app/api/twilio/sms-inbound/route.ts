import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  verifyTwilioRequest,
  reconstructWebhookUrl,
  formDataToParams,
} from "@/lib/twilio-verify";

export const dynamic = "force-dynamic";

/**
 * Twilio inbound SMS webhook relay for the engine.
 *
 * Twilio cannot reach engines on 127.0.0.1 on user laptops, so this
 * route is the public-facing HTTPS endpoint that accepts the inbound
 * SMS, verifies the signature with TWILIO_AUTH_TOKEN, and persists the
 * payload to public.anticipy_sms_inbound. Each engine polls that table
 * on a 10s interval, claims new rows, and forwards them to its own
 * /api/sms/inbound (the existing handler in
 * engine/app/product/server.py).
 *
 * Distinct from /api/engine/twilio/sms-reply which still handles the
 * older website-side intent confirm flow. This route serves the engine
 * pre-confirm flow (engine/app/product/sms_pre_confirm.py).
 *
 * Returns TwiML so Twilio messages the user with a thin acknowledgement
 * (the actual rich reply, like "Anticipy: confirmed, dispatching", is
 * sent by the engine after it polls and dispatches; this route only
 * needs to confirm Twilio's POST was accepted).
 *
 * Env required:
 *   TWILIO_AUTH_TOKEN
 *   SUPABASE_SERVICE_ROLE_KEY
 *   NEXT_PUBLIC_SUPABASE_URL
 */
export async function POST(req: Request) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    // Malformed body (e.g. JSON sent to a Twilio webhook) is treated
    // the same as an unsigned request. Return 403 so probers and
    // accidental hits do not get a 500.
    return new Response("Forbidden", { status: 403 });
  }
  const params = formDataToParams(formData);
  const signature = req.headers.get("x-twilio-signature");
  if (!verifyTwilioRequest(signature, reconstructWebhookUrl(req), params)) {
    return new Response("Forbidden", { status: 403 });
  }

  const from = (params.From || "").trim();
  const to = (params.To || "").trim();
  const body = (params.Body || "").trim();
  const messageSid = (params.MessageSid || "").trim() || null;
  const twilioAccountSid =
    (params.AccountSid || "").trim() || null;

  if (!from || !to || !body) {
    return twimlResponse("Anticipy: missing required fields.");
  }

  // Best-effort map from From-number to a known account. The dossier
  // table stores the user's phone number when they onboarded; if we
  // find a match, the engine that owns that account will see a
  // narrower filter. Otherwise the row is still inserted with
  // account_id=null and any engine running with include_unmapped=1
  // can pick it up. Today the schema does not carry phone numbers per
  // account so the mapping is intentionally a no-op; the engine
  // poller already polls with include_unmapped=1 so this is
  // forward-compat hook only.
  const accountId: string | null = null;

  try {
    const { error } = await supabaseAdmin
      .from("anticipy_sms_inbound")
      .insert({
        from_number: from,
        to_number: to,
        body,
        message_sid: messageSid,
        twilio_account_sid: twilioAccountSid,
        raw_form: params,
        account_id: accountId,
      });
    if (error) {
      // Duplicate MessageSid is fine; Twilio sometimes retries.
      const code = (error as { code?: string }).code;
      if (code !== "23505") {
        console.error("[sms-inbound] insert failed", error);
        return new Response("Server error", { status: 500 });
      }
    }
  } catch (exc) {
    console.error("[sms-inbound] unexpected error", exc);
    return new Response("Server error", { status: 500 });
  }

  return twimlResponse(
    "Anticipy: got it. Dispatching to your engine."
  );
}

/**
 * Engine poll surface. The engine calls GET with its account_id and
 * gets back unconsumed rows. Rows are marked consumed (atomic UPDATE)
 * before being returned so two engines don't process the same reply.
 *
 * Query params:
 *   account_id   match this account (or NULL rows in dev mode)
 *   limit        max rows to return (default 20, max 100)
 *   include_unmapped  if "1", also return rows where account_id is null
 *
 * Returned shape:
 *   { ok: true, count: N, rows: [{ from_number, to_number, body,
 *                                  message_sid, received_at, id }, ...] }
 */
export async function GET(req: Request) {
  const url = new URL(req.url);
  const accountId = (url.searchParams.get("account_id") || "").trim();
  const limitRaw = parseInt(
    url.searchParams.get("limit") || "20",
    10
  );
  const limit = Math.min(
    Math.max(isFinite(limitRaw) ? limitRaw : 20, 1),
    100
  );
  const includeUnmapped =
    url.searchParams.get("include_unmapped") === "1";

  if (!accountId && !includeUnmapped) {
    return jsonResponse(
      { ok: false, error: "account_id required" },
      400
    );
  }

  const consumerLabel =
    req.headers.get("x-engine-id") ||
    `account:${accountId || "unmapped"}`;

  try {
    let query = supabaseAdmin
      .from("anticipy_sms_inbound")
      .select(
        "id, from_number, to_number, body, message_sid, received_at, raw_form"
      )
      .is("consumed_at", null)
      .order("received_at", { ascending: true })
      .limit(limit);

    if (accountId && !includeUnmapped) {
      query = query.eq("account_id", accountId);
    } else if (accountId && includeUnmapped) {
      query = query.or(
        `account_id.eq.${accountId},account_id.is.null`
      );
    } else {
      query = query.is("account_id", null);
    }

    const { data: rows, error } = await query;
    if (error) {
      console.error("[sms-inbound] select failed", error);
      return jsonResponse({ ok: false, error: error.message }, 500);
    }
    const list = rows ?? [];
    if (list.length === 0) {
      return jsonResponse({ ok: true, count: 0, rows: [] });
    }

    // Atomic claim. Only return rows we actually flipped to consumed
    // so two pollers don't both ship the same reply.
    const ids = list.map((r) => r.id);
    const now = new Date().toISOString();
    const { data: claimed, error: claimErr } = await supabaseAdmin
      .from("anticipy_sms_inbound")
      .update({ consumed_at: now, consumed_by: consumerLabel })
      .in("id", ids)
      .is("consumed_at", null)
      .select(
        "id, from_number, to_number, body, message_sid, received_at, raw_form"
      );
    if (claimErr) {
      console.error("[sms-inbound] claim failed", claimErr);
      return jsonResponse(
        { ok: false, error: claimErr.message },
        500
      );
    }
    return jsonResponse({
      ok: true,
      count: (claimed ?? []).length,
      rows: claimed ?? [],
    });
  } catch (exc) {
    console.error("[sms-inbound] poll unexpected error", exc);
    return jsonResponse(
      {
        ok: false,
        error: exc instanceof Error ? exc.message : String(exc),
      },
      500
    );
  }
}

function twimlResponse(message: string) {
  const twiml = `<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>${escapeXml(message)}</Message></Response>`;
  return new Response(twiml, {
    headers: { "Content-Type": "text/xml" },
  });
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
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
