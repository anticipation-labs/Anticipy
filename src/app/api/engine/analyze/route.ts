import { NextResponse } from "next/server";
import { callKimi } from "@/lib/kimi";
import { callGroq } from "@/lib/groq";
import { callGemini } from "@/lib/gemini";
import { buildIntentPrompt } from "@/lib/intent-prompt";
import { sendIntentEmail } from "@/lib/resend-notify";
import { sendTwilioNotification } from "@/lib/twilio-notify";
import { supabaseAdmin } from "@/lib/supabase-admin";
import { requireSupabaseUser } from "@/lib/require-auth";
import {
  ExistingIntent,
  filterValidIntents,
  isDuplicateOfExisting,
  RawIntent,
} from "@/lib/dedup";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const authedUser = await requireSupabaseUser(req);
  if (!authedUser) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await req.json().catch(() => null);
    if (!body || typeof body !== "object") {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const sessionId = typeof body.sessionId === "string" ? body.sessionId : "";
    const transcript =
      typeof body.transcript === "string" ? body.transcript : "";
    const timezone =
      typeof body.timezone === "string" && body.timezone.length > 0
        ? body.timezone
        : "America/Vancouver";
    const isFinal = body.isFinal === undefined ? true : Boolean(body.isFinal);

    // Email recipient is the authenticated user — never trust a client-supplied address.
    const user_email = authedUser.email;

    if (!transcript.trim() || !sessionId) {
      return NextResponse.json(
        { error: "Missing transcript or sessionId" },
        { status: 400 }
      );
    }
    // Cap transcript size — keeps LLM calls bounded on long-running sessions.
    const MAX_TRANSCRIPT_CHARS = 60_000;
    const safeTranscript =
      transcript.length > MAX_TRANSCRIPT_CHARS
        ? transcript.slice(transcript.length - MAX_TRANSCRIPT_CHARS)
        : transcript;

    // Verify session exists AND belongs to the authenticated user. Without
    // the user_id check a caller who knows another user's session UUID could
    // pollute their intent feed.
    // Only block if already ended AND this is the final call (periodic mid-recording
    // calls are allowed to run multiple times on the same session).
    const { data: session } = await supabaseAdmin
      .from("anticipy_sessions")
      .select("id, status, user_id")
      .eq("id", sessionId)
      .single();

    if (!session || (session.user_id && session.user_id !== authedUser.id)) {
      return NextResponse.json(
        { error: "Session not found" },
        { status: 404 }
      );
    }
    if (isFinal && session.status === "ended") {
      return NextResponse.json(
        { error: "Session already ended" },
        { status: 409 }
      );
    }

    // Resolve local time — guard against invalid timezone strings from client
    let localTime: string;
    try {
      localTime = new Date().toLocaleString("en-US", { timeZone: timezone });
    } catch {
      localTime = new Date().toLocaleString("en-US", {
        timeZone: "America/New_York",
      });
    }

    // Get recent actions from this session — fetch full set for both LLM context and server-side dedup
    const { data: recentIntents } = await supabaseAdmin
      .from("anticipy_intents")
      .select("action_type, summary_for_user, evidence_quote")
      .eq("session_id", sessionId)
      .order("created_at", { ascending: false })
      .limit(50);

    const sessionExistingIntents: ExistingIntent[] = recentIntents ?? [];
    const recentActions = sessionExistingIntents
      .slice(0, 10)
      .map((i) => i.summary_for_user || "")
      .filter(Boolean);

    // Cross-session memory: fetch intents from user's other sessions in past 24h
    let crossSessionContext: string[] = [];
    try {
      const twentyFourHoursAgo = new Date(
        Date.now() - 24 * 60 * 60 * 1000
      ).toISOString();

      const { data: userSessions } = await supabaseAdmin
        .from("anticipy_sessions")
        .select("id")
        .eq("user_id", authedUser.id)
        .neq("id", sessionId)
        .gte("started_at", twentyFourHoursAgo)
        .order("started_at", { ascending: false })
        .limit(10);

      if (userSessions && userSessions.length > 0) {
        const otherSessionIds = userSessions.map((s) => s.id);
        const { data: crossIntents } = await supabaseAdmin
          .from("anticipy_intents")
          .select("summary_for_user, action_type, created_at")
          .in("session_id", otherSessionIds)
          .order("created_at", { ascending: false })
          .limit(10);

        crossSessionContext = (crossIntents ?? []).map(
          (i) => "[" + i.action_type + "] " + i.summary_for_user
        );
      }
    } catch (err) {
      console.warn("Cross-session memory query failed:", err);
    }

    // Build the prompt
    const { system, user } = buildIntentPrompt(
      safeTranscript,
      localTime,
      timezone,
      recentActions,
      crossSessionContext
    );

    const llmMessages = [
      { role: "system" as const, content: system },
      { role: "user" as const, content: user },
    ];

    let response: string = "";

    // Gemini Flash first (GOOGLE_API_KEY confirmed on Vercel), Groq second, Kimi third
    const models = [
      { name: "gemini", fn: () => callGemini(llmMessages, { temperature: 0.0, max_tokens: 8192 }) },
      { name: "groq", fn: () => callGroq(llmMessages, { temperature: 0.0, response_format: { type: "json_object" }, max_tokens: 8192 }) },
      { name: "kimi", fn: () => callKimi(llmMessages, { response_format: { type: "json_object" }, temperature: 0.0, max_tokens: 8192 }) },
    ];

    for (const model of models) {
      try {
        response = await model.fn();
        if (!response || response.trim().length === 0) throw new Error(`${model.name} empty`);
        JSON.parse(response);
        break;
      } catch (err) {
        console.warn(`${model.name} failed:`, err instanceof Error ? err.message : err);
        if (model.name === models[models.length - 1].name) {
          console.error("All models failed");
          if (isFinal) {
            await supabaseAdmin.from("anticipy_sessions").update({ status: "ended" }).eq("id", sessionId);
          }
          return NextResponse.json({ intents: [], totalInferred: 0, totalValid: 0 });
        }
      }
    }

    let parsed: { reasoning?: string; intents: Array<Record<string, unknown>> };
    try {
      parsed = JSON.parse(response);
    } catch {
      console.error(
        "Failed to parse LLM response:",
        response?.substring(0, 200)
      );
      parsed = { intents: [] };
    }

    const intents: RawIntent[] = parsed.intents ?? [];

    // Filter by confidence threshold and drop conversational/non-actionable types.
    // Pair filtered candidates with their original raw intent so we can still
    // pull confidence/importance/parameters when inserting.
    const validIntents = filterValidIntents(intents);
    const candidatesWithRaw = validIntents.map((c) => {
      const raw = intents.find((i) => {
        const at = String(i.action_type ?? "").toLowerCase().trim();
        const summary = String(i.summary_for_user ?? "").trim();
        return at === c.action_type && summary === c.summary_for_user;
      }) ?? {};
      return { candidate: c, raw };
    });

    // Track intents already stored in this same request so a single batch can't introduce dupes
    const insertedThisCall: ExistingIntent[] = [];

    // Store intents in Supabase and dispatch notifications
    const storedIntents = [];
    let skippedDuplicates = 0;
    for (const { candidate, raw } of candidatesWithRaw) {
      // Server-side fuzzy dedup against intents already in this session (and this batch).
      // Periodic auto-analysis re-processes the growing transcript, so the LLM frequently
      // re-emits the same intent — block it before it ever reaches the DB or notifications.
      const allExisting = [...sessionExistingIntents, ...insertedThisCall];
      if (isDuplicateOfExisting(candidate, allExisting)) {
        skippedDuplicates += 1;
        continue;
      }

      const importanceRaw = String(raw.importance ?? "standard").toLowerCase();
      const importance = ["critical", "important", "standard", "low"].includes(importanceRaw)
        ? importanceRaw
        : "standard";

      const { data, error } = await supabaseAdmin
        .from("anticipy_intents")
        .insert({
          session_id: sessionId,
          action_type: candidate.action_type,
          parameters:
            raw.parameters && typeof raw.parameters === "object"
              ? (raw.parameters as Record<string, unknown>)
              : {},
          confidence: raw.confidence as number,
          importance,
          summary_for_user: candidate.summary_for_user,
          evidence_quote: candidate.evidence_quote,
          status: "pending",
        })
        .select("id")
        .single();

      if (error) {
        console.error("Insert intent error:", error);
        continue;
      }

      const intentWithId = {
        ...raw,
        action_type: candidate.action_type,
        summary_for_user: candidate.summary_for_user,
        evidence_quote: candidate.evidence_quote,
        importance,
        id: data.id,
      };
      storedIntents.push(intentWithId);
      insertedThisCall.push({
        action_type: candidate.action_type,
        summary_for_user: candidate.summary_for_user,
        evidence_quote: candidate.evidence_quote,
      });

      // Broadcast to extension via Supabase Realtime (bypasses RLS — works with anon key)
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
              event: "new_intent",
              payload: {
                id: data.id,
                action_type: candidate.action_type,
                importance,
                confidence: raw.confidence,
                summary_for_user: candidate.summary_for_user,
                evidence_quote: candidate.evidence_quote,
                status: "pending",
              },
            }],
          }),
        }).catch((e) => console.warn("[broadcast] failed:", e.message));
      }

      // Skip all notifications (email + SMS + voice) for known test users so
      // automated E2E runs don't inbox-bomb the admin. Detected by email
      // domain — anticipy-test.local / .test / e2e-test-* are test-only.
      const isTestUser =
        !!user_email && (
          user_email.endsWith(".test") ||
          user_email.endsWith("@anticipy-test.local") ||
          user_email.startsWith("e2e-test-")
        );
      if (isTestUser) {
        // The intent row + Realtime broadcast still happen above; we just
        // suppress fan-out to email/SMS/voice for test users.
        continue;
      }

      // Importance-based notification dispatch:
      // critical → voice + SMS + email
      // important/standard → SMS + email
      // low → email only
      const adminEmail = process.env.ADMIN_EMAIL || "omar@anticipy.ai";
      const baseUrl =
        process.env.NEXT_PUBLIC_SITE_URL ||
        (process.env.VERCEL_URL
          ? `https://${process.env.VERCEL_URL}`
          : "http://localhost:3000");

      const intentPayload = {
        intentId: data.id,
        summary: candidate.summary_for_user,
        evidenceQuote: candidate.evidence_quote,
        importance,
        actionType: candidate.action_type,
      };

      // Always email the admin so we can see what users are doing in the demo.
      // If the authed user has an email (Supabase auth requires one, so this
      // is virtually always true), notify them too.
      if (user_email && user_email !== adminEmail) {
        const userEmailResult = await sendIntentEmail(user_email, intentPayload, baseUrl);
        if (userEmailResult) {
          await supabaseAdmin.from("anticipy_notifications").insert({
            intent_id: data.id,
            channel: "email",
            recipient: user_email,
            status: "sent",
          });
        }
      }

      const adminLabel = user_email
        ? `[Admin] User (${user_email}):`
        : "[Admin]";
      const adminEmailResult = await sendIntentEmail(
        adminEmail,
        intentPayload,
        baseUrl,
        adminLabel
      );
      if (adminEmailResult) {
        await supabaseAdmin.from("anticipy_notifications").insert({
          intent_id: data.id,
          channel: "email",
          recipient: adminEmail,
          status: "sent",
        });
      }

      // SMS + Voice for non-low importance levels
      const notifyPhone = process.env.TEST_USER_PHONE;
      if (notifyPhone && importance !== "low") {
        await sendTwilioNotification(
          notifyPhone,
          candidate.summary_for_user,
          importance,
          data.id
        );
      }
    }

    // Mark session as ended only on final analysis (not on periodic mid-recording calls)
    if (isFinal) {
      await supabaseAdmin
        .from("anticipy_sessions")
        .update({ status: "ended" })
        .eq("id", sessionId);
    }

    return NextResponse.json({
      intents: storedIntents,
      totalInferred: intents.length,
      totalValid: validIntents.length,
      totalSkippedDuplicates: skippedDuplicates,
    });
  } catch (err) {
    console.error("Analyze error:", err);
    return NextResponse.json(
      { error: "Analysis failed. Please try again." },
      { status: 500 }
    );
  }
}
