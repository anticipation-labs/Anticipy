import { supabaseAdmin } from "@/lib/supabase-admin";
import {
  formDataToParams,
  reconstructWebhookUrl,
  verifyTwilioRequest,
} from "@/lib/twilio-verify";
import {
  ONBOARDING_QUESTIONS,
  QUESTION_TOTAL,
} from "@/lib/onboarding-questions";

export const dynamic = "force-dynamic";

/**
 * Twilio voice-onboarding answer handler.
 *
 * Twilio POSTs SpeechResult here after each <Gather> finishes. We:
 *   1. Verify the Twilio signature.
 *   2. Append the answer to anticipy_voice_onboarding_calls.answers.
 *   3. If more questions remain, return TwiML that asks the next one.
 *   4. If the 7th answer just landed, write the dossier-shaped fragment
 *      to the dossier path that the engine's DossierLoader reads from
 *      (~/.anticipy/v7/dossiers/<account_id>/dossier.json is the local
 *      contract, but this is the website so we write a cloud row that
 *      the engine merges down on its next /api/onboarding/voice_status
 *      poll). Mark dossier_written so subsequent polls report
 *      "completed".
 *   5. Thank the user and hang up.
 *
 * The dossier fragment shape mirrors the JSON the local engine's
 * onboarding extractor produces (name, role, what they do, people,
 * tools, mandate, do_not_touch, comms, quiet hours). The website
 * does not run the LLM extractor; it parks the raw answers under
 * recurring_topics + transcript so the engine's pull job can re-run
 * the extractor with the same INTERVIEW_SCRIPT contract.
 */

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function twiml(body: string): Response {
  return new Response(
    `<?xml version="1.0" encoding="UTF-8"?>\n<Response>${body}</Response>`,
    { headers: { "Content-Type": "text/xml" } },
  );
}

function hangupTwiml(message: string): Response {
  return twiml(
    `<Say voice="Polly.Joanna">${escapeXml(message)}</Say><Hangup/>`,
  );
}

interface AnswerRow {
  q_index: number;
  question: string;
  answer: string;
  confidence: number;
  at: string;
}

function buildFragment(answers: AnswerRow[]): Record<string, unknown> {
  // Shape parity with the engine's frozen onboarding extractor output:
  // people array, tools array, recurring_topics array, do_not_touch
  // array, preferences map. We do not LLM-extract here; the engine's
  // pull job will re-run app.anticipy.onboarding.run_intake on the
  // transcript so the canonical UserProfile shape lands. The raw rows
  // ensure no information is lost between voice -> cloud -> engine.
  const transcript = answers
    .filter((a) => a && a.answer)
    .map((a) => ({
      speaker_id: "AGENT" as const,
      text: a.question,
      then: { speaker_id: "WEARER", text: a.answer },
    }))
    .flatMap((pair) => [
      pair,
      { speaker_id: "WEARER", text: pair.then.text },
    ]);
  return {
    onboarding_source: "voice_call",
    onboarding_completed_at: new Date().toISOString(),
    transcript: answers.map((a) => ({
      q: a.q_index,
      question: a.question,
      answer: a.answer,
    })),
    recurring_topics: answers
      .map((a) => a.answer)
      .filter((s) => !!s && s.length > 0),
    // The transcript field is also written as a paired AGENT/WEARER
    // sequence so the engine's chat_complete extractor can consume the
    // same row without reformatting.
    chat_transcript: transcript,
  };
}

export async function POST(req: Request) {
  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return new Response("Forbidden", { status: 403 });
  }
  const params = formDataToParams(formData);
  const signature = req.headers.get("x-twilio-signature");
  if (!verifyTwilioRequest(signature, reconstructWebhookUrl(req), params)) {
    return new Response("Forbidden", { status: 403 });
  }

  const url = new URL(req.url);
  const accountId = (url.searchParams.get("account_id") || "").trim();
  const qParam = url.searchParams.get("q") || "0";
  const qIndex = Number.isFinite(Number(qParam)) ? Number(qParam) : 0;
  if (!accountId || accountId.length > 128) {
    return hangupTwiml("This call was placed without an onboarding context. Goodbye.");
  }
  if (qIndex < 0 || qIndex >= QUESTION_TOTAL) {
    return hangupTwiml("Thanks. We are all set.");
  }

  const callSid = (params.CallSid || "").trim();
  const speechResult = (params.SpeechResult || "").trim();
  const confidenceRaw = Number(params.Confidence || "0");
  const confidence = Number.isFinite(confidenceRaw) ? confidenceRaw : 0;

  // Append to the row keyed on CallSid (preferred) or account_id (fallback).
  let rowSel = supabaseAdmin
    .from("anticipy_voice_onboarding_calls")
    .select("*")
    .order("placed_at", { ascending: false })
    .limit(1);
  if (callSid) {
    rowSel = rowSel.eq("twilio_sid", callSid);
  } else {
    rowSel = rowSel.eq("account_id", accountId);
  }
  const { data: existing, error: selErr } = await rowSel.maybeSingle();
  if (selErr) {
    console.error("[voice-onboarding-answer] select failed", selErr);
  }
  const answers: AnswerRow[] = Array.isArray(existing?.answers)
    ? (existing!.answers as AnswerRow[])
    : [];
  const row: AnswerRow = {
    q_index: qIndex,
    question: ONBOARDING_QUESTIONS[qIndex],
    answer: speechResult,
    confidence,
    at: new Date().toISOString(),
  };
  answers.push(row);

  const nextIndex = qIndex + 1;
  const isFinal = nextIndex >= QUESTION_TOTAL;
  const update: Record<string, unknown> = {
    answers,
    question_index: nextIndex,
    question_total: QUESTION_TOTAL,
    status: isFinal ? "completed" : "in_progress",
    updated_at: new Date().toISOString(),
  };
  if (isFinal) {
    update.dossier_written = true;
    // Park the fragment on the row so the engine's pull job can pick
    // it up without re-deriving from raw answers. Stored alongside the
    // raw answers so we never lose either signal.
    update.dossier_fragment = buildFragment(answers);
  }

  if (existing?.id) {
    const { error: updErr } = await supabaseAdmin
      .from("anticipy_voice_onboarding_calls")
      .update(update)
      .eq("id", existing.id);
    if (updErr) {
      console.error("[voice-onboarding-answer] update failed", updErr);
    }
  } else {
    // Defensive: if the broker insert lost its row, create one so the
    // answer is still captured rather than dropped on the floor.
    const insertRow: Record<string, unknown> = {
      user_id: existing?.user_id || "00000000-0000-0000-0000-000000000000",
      account_id: accountId,
      to_e164: params.To || params.Called || "",
      twilio_sid: callSid,
      status: isFinal ? "completed" : "in_progress",
      answers,
      question_index: nextIndex,
      question_total: QUESTION_TOTAL,
      dossier_written: !!isFinal,
      ...(isFinal ? { dossier_fragment: buildFragment(answers) } : {}),
    };
    const { error: insErr } = await supabaseAdmin
      .from("anticipy_voice_onboarding_calls")
      .insert(insertRow);
    if (insErr) {
      console.error("[voice-onboarding-answer] insert failed", insErr);
    }
  }

  if (isFinal) {
    return twiml(
      `<Say voice="Polly.Joanna">Thanks. That is everything I needed. Anticipy now has the context to help. Goodbye.</Say><Hangup/>`,
    );
  }

  const nextQ = escapeXml(ONBOARDING_QUESTIONS[nextIndex]);
  const ordinals = ["one", "two", "three", "four", "five", "six", "seven"];
  const action =
    `/api/twilio/onboarding/answer`
    + `?account_id=${encodeURIComponent(accountId)}`
    + `&q=${nextIndex}`;
  const body =
    `<Say voice="Polly.Joanna">Got it. Question ${ordinals[nextIndex] || (nextIndex + 1)} of seven. ${nextQ}</Say>`
    + `<Gather input="speech" speechTimeout="auto" timeout="15"`
    + ` language="en-US"`
    + ` hints="boss, reports, partner, gmail, google calendar, notion, slack, linear, pacific, eastern, central, mountain, vancouver, san francisco, new york, toronto"`
    + ` action="${action}" method="POST">`
    + `<Say voice="Polly.Joanna">I am listening.</Say>`
    + `</Gather>`
    + `<Say voice="Polly.Joanna">I did not hear an answer. I will save what I have so far. Goodbye.</Say>`
    + `<Hangup/>`;
  return twiml(body);
}

export async function GET() {
  return new Response("Method Not Allowed", { status: 405 });
}
