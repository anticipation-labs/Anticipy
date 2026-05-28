/**
 * Canonical executeAction implementation shared across confirm, sms-reply, and voice-callback.
 *
 * Routing tiers:
 *   Tier 1  - Direct API calls  (calendar, notes, email via provider, SMS via Twilio)
 *   Tier 2  - Browser agent     (everything else, plus fallback for Tier-1 failures)
 *
 * The browser agent runs in the Python FastAPI engine (/execute-intent endpoint).
 * If the engine is unreachable, Tier-2 actions fall back to saving a note in Supabase
 * so no action is silently lost.
 */

import { supabaseAdmin } from "./supabase-admin";
import { createCalendarEvent } from "./google-calendar";
import { sendSMS } from "./twilio-notify";
import { sendNotification } from "./notification-adapter";
import { escapeHtml, sanitizeHeader } from "./escape";

export interface ActionResult {
  success: boolean;
  message: string;
  data: Record<string, unknown>;
  externalId?: string;
}

// ---------------------------------------------------------------------------
// Browser task builder
// Translates a structured intent into a plain-English task the browser agent
// can execute without any per-site hardcoding.
// ---------------------------------------------------------------------------

export function buildBrowserTask(
  actionType: string,
  params: Record<string, unknown>
): string {
  const p = params;

  switch (actionType) {
    case "email_draft": {
      const toLine = (p.recipient_email as string)?.includes("@")
        ? `${p.recipient_name} <${p.recipient_email}>`
        : String(p.recipient_name || "the recipient");
      return [
        "Open Gmail (mail.google.com) and compose a new email.",
        `To: ${toLine}`,
        `Subject: ${p.subject || "No subject"}`,
        `Message body:\n${p.body || ""}`,
        "Click Send to deliver the email.",
      ].join("\n");
    }

    case "message_draft": {
      const channel = String(p.channel || "message").toLowerCase();
      const recipient = String(p.recipient_name || "the recipient");
      const body = String(p.body || "");

      if (channel === "whatsapp") {
        return `Open WhatsApp Web (web.whatsapp.com), find the conversation with ${recipient}, type this message: "${body}", and send it.`;
      }
      if (channel === "slack") {
        return `Open Slack (app.slack.com), find ${recipient}, type this message: "${body}", and send it.`;
      }
      // Default for unknown channel: open Gmail as a fallback
      return [
        "Open Gmail (mail.google.com) and compose a new email.",
        `To: ${recipient}`,
        `Message: ${body}`,
        "Click Send.",
      ].join("\n");
    }

    case "lookup": {
      return [
        `Search Google for: "${p.query}"`,
        p.why_useful ? `Context: ${p.why_useful}` : "",
        "Read the top 3 to 5 results and return a concise, accurate summary of the key findings.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "book_flight": {
      return [
        "Search for flights on Google Flights (flights.google.com).",
        p.from ? `Departing from: ${p.from}` : "",
        p.to ? `Destination: ${p.to}` : "",
        p.date ? `Date: ${p.date}` : "",
        p.return_date ? `Return date: ${p.return_date}` : "",
        p.passengers ? `Passengers: ${p.passengers}` : "",
        p.cabin_class ? `Class: ${p.cabin_class}` : "",
        "Find the best available options and report the top 3 results with price, airline, and departure time.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "make_reservation":
    case "book_restaurant":
    case "restaurant_reservation": {
      const venue = String(p.venue || p.restaurant || p.place || "the restaurant");
      return [
        `Make a restaurant reservation at ${venue} using OpenTable (opentable.com).`,
        p.date ? `Date: ${p.date}` : "",
        p.time ? `Time: ${p.time}` : "",
        p.party_size ? `Party size: ${p.party_size} people` : "",
        p.notes ? `Special requests: ${p.notes}` : "",
        "Complete the booking and confirm all reservation details.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "order_gift":
    case "send_gift":
    case "send_flowers": {
      const recipient = String(p.recipient_name || "the recipient");
      const item = String(p.item || p.gift_type || "flowers");
      return [
        `Order ${item} for ${recipient}.`,
        p.occasion ? `Occasion: ${p.occasion}` : "",
        p.budget ? `Budget: ${p.budget}` : "",
        p.delivery_address ? `Deliver to: ${p.delivery_address}` : "",
        p.message ? `Gift message: ${p.message}` : "",
        "Find a reputable seller, choose a suitable option, and complete the order.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "pay_invoice":
    case "send_payment": {
      return [
        `Make a payment.`,
        p.amount ? `Amount: ${p.amount}` : "",
        p.recipient_name ? `To: ${p.recipient_name}` : "",
        p.method ? `Via: ${p.method}` : "",
        p.reference ? `Reference: ${p.reference}` : "",
        "Complete the payment and confirm the transaction.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "schedule_call":
    case "book_meeting": {
      const with_ = String(p.with || p.recipient_name || p.attendee || "");
      return [
        `Schedule a call${with_ ? ` with ${with_}` : ""}.`,
        p.date ? `Date: ${p.date}` : "",
        p.time ? `Time: ${p.time}` : "",
        p.duration ? `Duration: ${p.duration}` : "",
        p.platform ? `Platform: ${p.platform}` : "",
        "Use Calendly or Google Meet to book the meeting and send an invite.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "follow_up_with":
    case "check_in_on":
    case "return_call": {
      const person = String(p.recipient_name || p.person || "them");
      const context = String(p.context || p.subject || p.body || "");
      return [
        `Send a follow-up message to ${person}.`,
        context ? `Context: ${context}` : "",
        "Open Gmail and compose a brief, friendly follow-up email. Send it.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "send_congratulations":
    case "send_condolences":
    case "send_apology": {
      const person = String(p.recipient_name || "them");
      const humanType = actionType.replace("send_", "").replace("_", " ");
      return [
        `Send ${humanType} to ${person}.`,
        p.context ? `Context: ${p.context}` : "",
        p.body ? `Message: ${p.body}` : "",
        "Open Gmail and compose a heartfelt message. Send it.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    case "share_document": {
      return [
        `Share a document with ${p.recipient_name || "the recipient"}.`,
        p.document ? `Document: ${p.document}` : "",
        p.permissions ? `Permissions: ${p.permissions}` : "",
        "Find the document in Google Drive and share it with the appropriate permissions.",
      ]
        .filter(Boolean)
        .join("\n");
    }

    default: {
      // Generic: convert snake_case action type to natural language
      const humanAction = actionType.replace(/_/g, " ");
      const paramLines = Object.entries(p)
        .filter(([, v]) => v !== null && v !== undefined && v !== "")
        .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`)
        .join("\n");
      return paramLines
        ? `${humanAction}.\n\nDetails:\n${paramLines}`
        : humanAction;
    }
  }
}

// Actions that genuinely require a browser to complete.
// Everything NOT in this set (and not already handled as Tier 1) gets saved
// directly as a note. No browser dependency, no silent failures.
const BROWSER_ACTIONS = new Set([
  "lookup",
  "research_product",
  "buy_item",
  "book_flight",
  "make_reservation",
  "book_restaurant",
  "restaurant_reservation",
  "order_gift",
  "send_gift",
  "send_flowers",
  "pay_invoice",
  "send_payment",
  "schedule_call",
  "book_meeting",
  "follow_up_with",
  "check_in_on",
  "return_call",
  "send_congratulations",
  "send_condolences",
  "send_apology",
  "share_document",
]);

// ---------------------------------------------------------------------------
// Browser agent router
// Saves a note fallback (so the task is never silently lost), stores the task
// description on the intent for the extension, then returns routing="browser"
// so the confirm endpoint knows to broadcast AND insert an anticipy_actions row.
// ---------------------------------------------------------------------------

async function routeToBrowserAgent(
  intent: Record<string, unknown>,
  taskDescription: string
): Promise<ActionResult> {
  // Save a note so the action survives even if the extension is offline.
  const noteTitle =
    (intent.summary_for_user as string) || taskDescription.split("\n")[0];
  supabaseAdmin
    .from("anticipy_notes")
    .insert({ session_id: intent.session_id, title: noteTitle, body: taskDescription })
    .then(({ error }) => {
      if (error) console.warn("[executeAction] Could not save fallback note:", error.message);
    });

  // Store the task description on the intent so the extension can use it directly.
  try {
    const existingParams = (intent.parameters as Record<string, unknown>) || {};
    await supabaseAdmin
      .from("anticipy_intents")
      .update({ parameters: { ...existingParams, browser_task: taskDescription } })
      .eq("id", intent.id as string);
  } catch (e) {
    console.warn("[executeAction] Could not store browser_task in parameters:", e);
  }

  return {
    success: true,
    message: "Saved - dispatching to browser agent.",
    data: { routing: "browser", task: taskDescription },
  };
}

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

/**
 * Looks up the email of the user that owns the session this intent belongs to.
 * Calendar tokens are keyed by app-user email, so we need this to dispatch
 * to the right calendar when multiple users have connected their own.
 * Falls back to the env-configured admin email only when the session row has
   * no user_email (legacy rows from before per-user signup) - never to a
 * hardcoded address, since that would silently use the wrong account.
 */
async function resolveSessionUserEmail(
  intent: Record<string, unknown>
): Promise<string> {
  const fallback = process.env.ADMIN_EMAIL || process.env.TEST_USER_EMAIL || "";
  const sessionId = intent.session_id as string | undefined;
  if (!sessionId) return fallback;
  try {
    const { data } = await supabaseAdmin
      .from("anticipy_sessions")
      .select("user_email")
      .eq("id", sessionId)
      .maybeSingle();
    return (data?.user_email as string | null) || fallback;
  } catch {
    return fallback;
  }
}

export async function executeAction(
  intent: Record<string, unknown>
): Promise<ActionResult> {
  const actionType = intent.action_type as string;
  const params = (intent.parameters as Record<string, unknown>) || {};
  const userEmail = await resolveSessionUserEmail(intent);

  try {
    switch (actionType) {
      // -----------------------------------------------------------------------
      // TIER 1 - Direct API calls (fast, no browser needed)
      // -----------------------------------------------------------------------

      case "calendar_add": {
        const event = await createCalendarEvent(userEmail, {
          title: (params.title as string) || "Untitled Event",
          startIso:
            (params.start_iso as string) || new Date().toISOString(),
          endIso:
            (params.end_iso as string) ||
            new Date(Date.now() + 3_600_000).toISOString(),
          description: params.description as string,
          location: params.location as string,
          attendees: params.attendees as string[],
          timezone: "America/Vancouver",
        });
        return {
          success: true,
          message: `Calendar event created: "${params.title}"`,
          data: { eventId: event.eventId, htmlLink: event.htmlLink },
          externalId: event.eventId,
        };
      }

      case "reminder_add": {
        try {
          const dueIso =
            (params.due_iso as string) ||
            new Date(Date.now() + 3_600_000).toISOString();
          const event = await createCalendarEvent(userEmail, {
            title: `Reminder: ${params.text || "Reminder"}`,
            startIso: dueIso,
            endIso: dueIso,
            description: `Reminder set by Anticipy: ${params.text}`,
            timezone: "America/Vancouver",
          });
          return {
            success: true,
            message: `Reminder set: "${params.text}"`,
            data: { eventId: event.eventId, htmlLink: event.htmlLink },
            externalId: event.eventId,
          };
        } catch {
          // Calendar not connected - save as note
          await supabaseAdmin.from("anticipy_notes").insert({
            session_id: intent.session_id,
            title: `Reminder: ${params.text || "Reminder"}`,
            body: `Due: ${params.due_iso || "Not specified"}\n\n${params.text || ""}`,
          });
          return {
            success: true,
            message: `Reminder saved: "${params.text}"`,
            data: { fallback: "note" },
          };
        }
      }

      case "note_add": {
        const { error: noteErr } = await supabaseAdmin
          .from("anticipy_notes")
          .insert({
            session_id: intent.session_id,
            title: (params.title as string) || "Untitled Note",
            body: (params.body as string) || "",
          });
        if (noteErr) throw new Error(noteErr.message);
        return {
          success: true,
          message: `Note saved: "${params.title}"`,
          data: { title: params.title },
        };
      }

      case "email_draft": {
        // If we have a direct email address, send via Resend immediately
        const recipientEmail = params.recipient_email as string | undefined;
        if (recipientEmail?.includes("@")) {
          try {
            const senderHandle = userEmail.split("@")[0];
            const safeSenderHandle = escapeHtml(senderHandle);
            // sanitizeHeader strips CR/LF. Without that, an LLM-extracted
            // subject could inject extra headers (Bcc:, Reply-To:, etc.) into
            // the SMTP envelope.
            const rawSubject = sanitizeHeader(
              (params.subject as string) || "Message via Anticipy",
              180
            );
            const safeFromHandle = sanitizeHeader(senderHandle, 60);
            const rawBody = (params.body as string) || "";
            const safeBodyHtml = escapeHtml(rawBody).replace(/\n/g, "<br>");
            const sent = await sendNotification({
              channel: "email",
              to: recipientEmail,
              subject: rawSubject,
              text: rawBody,
              html: `<p>${safeBodyHtml}</p>
                     <hr style="border:none;border-top:1px solid #eee;margin:16px 0">
                     <p style="font-size:12px;color:#888">Sent via Anticipy on behalf of ${safeSenderHandle}</p>`,
              from: `${safeFromHandle} via Anticipy <notifications@aevoy.com>`,
              intentId: String(intent.id || ""),
              userId: String(intent.user_id || ""),
              idempotencyKey: `execute-email:${String(intent.id || "")}:${recipientEmail}`,
            });

            if (sent.ok) {
              return {
                success: true,
                message: `Email sent to ${params.recipient_name || recipientEmail}: "${params.subject}"`,
                data: { emailId: sent.providerMessageId, recipient: recipientEmail },
                externalId: sent.providerMessageId,
              };
            }
            console.warn("[executeAction] Email provider failed, routing to browser agent:", sent.error);
          } catch (emailErr) {
            console.warn("[executeAction] Resend threw, routing to browser agent:", emailErr);
          }
        }

        // No email address or provider failed: browser agent opens Gmail.
        return routeToBrowserAgent(intent, buildBrowserTask("email_draft", params));
      }

      case "message_draft": {
        const channel = (params.channel as string | undefined) || "";
        const phone = params.recipient_phone as string | undefined;

        // SMS with a known phone number → Twilio direct send
        if (channel.toLowerCase() === "sms" && phone) {
          const body = (params.body as string) || "";
          const smsResult = await sendSMS(phone, body, intent.id as string);
          // Don't leak raw provider errors (e.g. "Twilio: 21610 unsubscribed").
          // Console-log keeps full diagnostic; user message stays calm.
          if (!smsResult.success && smsResult.error) {
            console.warn("[sms] Twilio failure:", smsResult.error);
          }
          return {
            success: smsResult.success,
            message: smsResult.success
              ? `SMS sent to ${params.recipient_name || phone}`
              : "Couldn't send that message. Try again in a moment.",
            data: { sid: smsResult.sid, mock: smsResult.mock },
          };
        }

        // Everything else → browser agent
        return routeToBrowserAgent(
          intent,
          buildBrowserTask("message_draft", params)
        );
      }

      // -----------------------------------------------------------------------
      // TIER 2 - Browser-required actions
      // Only route here when the task genuinely needs a browser.
      // All other unknown action types are saved as notes (Tier 3 below).
      // -----------------------------------------------------------------------

      case "lookup":
      default: {
        if (BROWSER_ACTIONS.has(actionType)) {
          return routeToBrowserAgent(intent, buildBrowserTask(actionType, params));
        }

        // TIER 3 - Note-like actions (schedule_meeting_reminder, create_report,
        // health_instruction, set_goal, add_task, etc.)
        // Save directly to anticipy_notes. No browser dependency.
        const noteTitle =
          (params.title as string) ||
          (params.summary as string) ||
          (intent.summary_for_user as string) ||
          actionType.replace(/_/g, " ");
        const noteBody = buildBrowserTask(actionType, params);
        const { error: noteErr } = await supabaseAdmin
          .from("anticipy_notes")
          .insert({ session_id: intent.session_id, title: noteTitle, body: noteBody });
        if (noteErr) console.warn("[executeAction] Note save error:", noteErr.message);
        return {
          success: true,
          message: `Saved: "${noteTitle}"`,
          data: { title: noteTitle, note_saved: true },
        };
      }
    }
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Execution failed";
    console.error(`[executeAction] Error (${actionType}):`, message);
    return {
      success: false,
      message: `Failed: ${message}`,
      data: { error: message },
    };
  }
}
