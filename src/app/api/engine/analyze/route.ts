import { NextResponse } from "next/server";
import { callKimi } from "@/lib/kimi";
import { callGroq } from "@/lib/groq";
import { callGemini } from "@/lib/gemini";
import { buildIntentPrompt, type PriorIntentContext } from "@/lib/intent-prompt";
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
import {
  runIntentGate,
  applyPerfectMomentThrottle,
  NOTIFY_RATE_WINDOW_MS,
} from "@/lib/intent-gates";
import { extractMemoryItems } from "@/lib/memory-extract";
import { recallRelevantMemory } from "@/lib/memory-recall";
import { recallUserPreferences } from "@/lib/preference-recall";

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
    // Clarification-loop hook: when the wearer answers a follow-up question
    // raised by a prior intent (extension's done(success:false)), the client
    // sends `answers_intent_id`. We pull the prior intent's slots so the LLM
    // can merge the answer with what was already known and re-emit the intent
    // with the previously-missing fields filled in.
    const answersIntentId =
      typeof body.answers_intent_id === "string" && body.answers_intent_id.length > 0
        ? body.answers_intent_id
        : "";

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

    // Single-flight per session_id. Two concurrent /analyze calls (most
    // commonly: a periodic mid-recording call and the final-on-stop call)
    // would each fuzzy-dedup against pre-call DB state, both insert, both
    // fan out emails. The original bug. The dedupe_key generated column
    // catches *identical* rewrites only — the LLM rewords the same intent
    // every tick, so identical-text dedup misses it. The reliable fix is
    // to serialize concurrent /analyze on the same session_id at the route
    // boundary so the second call sees the first's intents in the existing-
    // intents fetch and skips them via the existing fuzzy dedup.
    //
    // We use an INSERT into anticipy_inflight_locks with PRIMARY KEY
    // (session_id, kind). The second caller's INSERT fails with 23505
    // and we 429 immediately — the client retries on its next tick if it
    // still wants to. Stale locks (>5 min) get reaped before the attempt.
    const lockKind = "analyze";
    const STALE_LOCK_MS = 5 * 60 * 1000;
    const requestId =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `req-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    // Reap stale locks for THIS (session, kind) so a crashed prior call
    // never permanently blocks the session. Targeted delete keeps it cheap.
    await supabaseAdmin
      .from("anticipy_inflight_locks")
      .delete()
      .eq("session_id", sessionId)
      .eq("kind", lockKind)
      .lt(
        "acquired_at",
        new Date(Date.now() - STALE_LOCK_MS).toISOString()
      );
    const { error: lockErr } = await supabaseAdmin
      .from("anticipy_inflight_locks")
      .insert({
        session_id: sessionId,
        kind: lockKind,
        request_id: requestId,
      });
    if (lockErr && (lockErr as { code?: string }).code === "23505") {
      // Another /analyze for this session is in flight. Return 409 with an
      // empty result so the client treats this as a no-op (next tick will
      // pick up the previous call's intents via Realtime).
      return NextResponse.json(
        {
          intents: [],
          totalInferred: 0,
          totalValid: 0,
          skippedReason: "concurrent_analyze_in_flight",
        },
        { status: 409 }
      );
    }
    if (lockErr) {
      // Anything other than 23505 — log and continue without the lock.
      // We'd rather over-fire than silently drop the analysis.
      console.warn("[analyze] inflight-lock insert failed:", lockErr.message);
    }

    // Wrap the rest of the route so the lock is ALWAYS released, even on
    // throws further down. The outer try/catch already catches; we add a
    // finally below and re-throw to preserve the response shape.
    let releaseLock = async () => {
      try {
        await supabaseAdmin
          .from("anticipy_inflight_locks")
          .delete()
          .eq("session_id", sessionId)
          .eq("kind", lockKind)
          .eq("request_id", requestId);
      } catch (err) {
        console.warn(
          "[analyze] inflight-lock release failed:",
          err instanceof Error ? err.message : err
        );
      }
    };
    if (lockErr) releaseLock = async () => {}; // never acquired — nothing to release.

    try {

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

    // Cross-session memory: last 5 confirmed/executed intents from this user in the
    // past 72h, across ALL their sessions (not just this one). Tells the LLM
    // "the user already did X yesterday" so it stops re-emitting the same task
    // each time the wearer mentions it again. Mirrors the Python cascade's
    // long-horizon memory window.
    let crossSessionContext: string[] = [];
    try {
      const seventyTwoHoursAgo = new Date(
        Date.now() - 72 * 60 * 60 * 1000
      ).toISOString();

      const { data: userSessions } = await supabaseAdmin
        .from("anticipy_sessions")
        .select("id")
        .eq("user_id", authedUser.id)
        .gte("started_at", seventyTwoHoursAgo)
        .order("started_at", { ascending: false })
        .limit(50);

      if (userSessions && userSessions.length > 0) {
        const allSessionIds = userSessions.map((s) => s.id);
        const { data: crossIntents } = await supabaseAdmin
          .from("anticipy_intents")
          .select("summary_for_user, action_type, status, created_at")
          .in("session_id", allSessionIds)
          .in("status", ["confirmed", "executed"])
          .order("created_at", { ascending: false })
          .limit(5);

        crossSessionContext = (crossIntents ?? []).map(
          (i) =>
            "[" +
            (i.status || "done") +
            ":" +
            i.action_type +
            "] " +
            i.summary_for_user
        );
      }
    } catch (err) {
      console.warn("Cross-session memory query failed:", err);
    }

    // Clarification loop: when answers_intent_id is supplied, load the prior
    // intent so the LLM has the partial parameters + question to merge against
    // the wearer's answer. We verify the prior intent belongs to a session
    // owned by the authed user — never trust a client-supplied id blindly.
    let priorIntentContext: PriorIntentContext | null = null;
    if (answersIntentId) {
      try {
        const { data: priorRow } = await supabaseAdmin
          .from("anticipy_intents")
          .select(
            "id, action_type, summary_for_user, evidence_quote, parameters, execution_result, session_id"
          )
          .eq("id", answersIntentId)
          .single();
        if (priorRow) {
          // Ownership check — prior intent's session must belong to this user.
          const { data: priorSession } = await supabaseAdmin
            .from("anticipy_sessions")
            .select("user_id")
            .eq("id", priorRow.session_id)
            .single();
          if (
            priorSession &&
            (!priorSession.user_id || priorSession.user_id === authedUser.id)
          ) {
            priorIntentContext = {
              actionType: String(priorRow.action_type ?? ""),
              summary: String(priorRow.summary_for_user ?? ""),
              evidenceQuote: String(priorRow.evidence_quote ?? ""),
              parameters:
                priorRow.parameters && typeof priorRow.parameters === "object"
                  ? (priorRow.parameters as Record<string, unknown>)
                  : {},
              question: String(priorRow.execution_result ?? ""),
            };
          }
        }
      } catch (err) {
        console.warn("Prior-intent fetch failed:", err);
      }
    }

    // Long-term memory recall: pull top-N memorable items the wearer has
    // mentioned across sessions (preferences, relationships, references,
    // ongoing context). Lets the intent LLM disambiguate pronouns,
    // recognize follow-ups, and avoid duplicate intents.
    let memoryContext: string[] = [];
    try {
      memoryContext = await recallRelevantMemory(
        authedUser.id,
        safeTranscript,
        10
      );
    } catch (err) {
      console.warn(
        "[memory-recall] failed; continuing without memory context:",
        err instanceof Error ? err.message : err
      );
    }

    // Personalized preferences: prior accept/reject/edit/auto_proceed signals
    // surface as one-line reasons the LLM uses to pre-filter new intents.
    // Fail-open — analyze still works if the table is empty or query errors.
    let preferenceContext: string[] = [];
    try {
      preferenceContext = await recallUserPreferences(authedUser.id, 15);
    } catch (err) {
      console.warn(
        "[preference-recall] failed; continuing without preference context:",
        err instanceof Error ? err.message : err
      );
    }

    // Build the prompt
    const { system, user } = buildIntentPrompt(
      safeTranscript,
      localTime,
      timezone,
      recentActions,
      crossSessionContext,
      priorIntentContext,
      memoryContext,
      preferenceContext
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

    // Fire-and-forget memory extraction: a separate Gemini pass over the
    // SAME transcript pulls preferences, relationships, references, and
    // ongoing contexts the wearer would benefit from us remembering. Runs
    // in parallel with intent storage; failures are logged and ignored.
    // This is the layer that gives future analyze calls richer context
    // without polluting the actionable-intents pipeline.
    void (async () => {
      try {
        const items = await extractMemoryItems(
          safeTranscript,
          localTime,
          timezone
        );
        if (items.length === 0) return;
        const rows = items.map((it) => ({
          user_id: authedUser.id,
          session_id: sessionId,
          kind: it.kind,
          key: it.key,
          value: it.value,
          evidence_quote: it.evidence_quote,
          confidence: it.confidence,
        }));
        // Upsert on (user_id, lower(kind), lower(key)). The lowercased
        // generated columns are enforced by the unique index added in
        // migration deep_bug_hunt_idempotency_constraints. Without
        // ignoreDuplicates the second periodic /analyze tick within the
        // same session would write the same fact 30+ times for a long
        // recording — confirmed bloat in production before the fix.
        const { error: memErr } = await supabaseAdmin
          .from("anticipy_memory")
          .upsert(rows, {
            onConflict: "user_id,kind,key",
            ignoreDuplicates: true,
          });
        if (memErr) {
          // 23505 here means the lowercased uniqueness fired — ignored
          // intentionally. Anything else is a real error.
          if ((memErr as { code?: string }).code !== "23505") {
            console.warn(
              "[memory-extract] insert failed:",
              memErr.message
            );
          }
        }
      } catch (err) {
        console.warn(
          "[memory-extract] background pass failed:",
          err instanceof Error ? err.message : err
        );
      }
    })();

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

    // Per-user perfect-moment throttle: count notifications already dispatched
    // to this user in the last 60 minutes. If >5, demote new non-critical
    // intents to "low" so we don't inbox-bomb the wearer. Mirrors the spirit
    // of the proactive cascade's L6 dispatcher rate-limit.
    let recentUserNotificationCount = 0;
    try {
      const oneHourAgo = new Date(
        Date.now() - NOTIFY_RATE_WINDOW_MS
      ).toISOString();
      const { data: userSessionsForThrottle } = await supabaseAdmin
        .from("anticipy_sessions")
        .select("id")
        .eq("user_id", authedUser.id)
        .gte("started_at", oneHourAgo);
      const sessionIds = (userSessionsForThrottle ?? []).map((s) => s.id);
      if (sessionIds.length > 0) {
        const { count } = await supabaseAdmin
          .from("anticipy_intents")
          .select("id", { count: "exact", head: true })
          .in("session_id", sessionIds)
          .gte("created_at", oneHourAgo);
        recentUserNotificationCount = count ?? 0;
      }
    } catch (err) {
      console.warn("Perfect-moment throttle query failed:", err);
    }

    // Store intents in Supabase and dispatch notifications
    const storedIntents = [];
    let skippedDuplicates = 0;
    let skippedByGate = 0;
    for (const { candidate, raw } of candidatesWithRaw) {
      // Follow-up answers bypass dedup (the new intent will look very similar
      // to the prior failed one — that's the whole point) and the second-pass
      // gate (a short slot-fill reply like "NYC to LA Friday" looks like
      // conversational fragment to the gate but is exactly what we want).
      // Default to "perfect moment = true" in the follow-up case so the
      // throttle doesn't demote a fresh slot-filled intent.
      let perfectMoment = true;
      if (!priorIntentContext) {
        // Server-side fuzzy dedup against intents already in this session (and this batch).
        // Periodic auto-analysis re-processes the growing transcript, so the LLM frequently
        // re-emits the same intent — block it before it ever reaches the DB or notifications.
        const allExisting = [...sessionExistingIntents, ...insertedThisCall];
        if (isDuplicateOfExisting(candidate, allExisting)) {
          skippedDuplicates += 1;
          continue;
        }

        // Second-pass validation gate (ports the Python cascade's L1/L2/L5 logic
        // into a single LLM call). Drops delegations, future-tense pleasantries,
        // and intents the user retracted later in the same conversation.
        const gateVerdict = await runIntentGate({
          summary: candidate.summary_for_user,
          actionType: candidate.action_type,
          evidenceQuote: candidate.evidence_quote,
          transcript: safeTranscript,
          crossSessionContext,
        });
        if (!gateVerdict.admit) {
          skippedByGate += 1;
          console.log(
            "[intent-gate] dropped:",
            candidate.action_type,
            "—",
            gateVerdict.reasoning,
            JSON.stringify(gateVerdict.raw)
          );
          continue;
        }
        perfectMoment = gateVerdict.perfectMoment;
      }

      const importanceRaw = String(raw.importance ?? "standard").toLowerCase();
      const importanceFromLlm = ["critical", "important", "standard", "low"].includes(importanceRaw)
        ? importanceRaw
        : "standard";

      // Apply the perfect-moment gate verdict + per-user notify rate throttle
      // to potentially demote importance. Critical intents always pass.
      const importance = applyPerfectMomentThrottle(
        importanceFromLlm,
        recentUserNotificationCount,
        perfectMoment
      );
      if (importance !== importanceFromLlm) {
        console.log(
          "[intent-gate] importance demoted:",
          candidate.action_type,
          importanceFromLlm,
          "→",
          importance,
          "(perfect_moment=" + perfectMoment +
            ", recent_notifications=" + recentUserNotificationCount + ")"
        );
      }

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

      // 23505 = unique_violation. Race-safe: two concurrent /analyze calls
      // can both pass the in-memory dedup, but the DB-level
      // (session_id, dedupe_key) unique constraint catches the second one.
      // Treat as "already inserted by sibling call" — skip silently and DO
      // NOT fan out email/SMS, otherwise users get duplicate notifications.
      if (error && (error as { code?: string }).code === "23505") {
        skippedDuplicates += 1;
        continue;
      }

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
      // Each new intent counts toward the per-user notify rate. Lets the
      // throttle ratchet up across the candidates in THIS same batch, not
      // just across batches.
      recentUserNotificationCount += 1;

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

      // Email channel policy — importance-driven, opt-in only:
      //   - Wearer: email ONLY for `critical` (someone is waiting NOW or
      //     money/trust is at stake within hours). Everything else surfaces
      //     silently on /engine + the extension popup. (Future: per-user
      //     notification preference in settings widens this.)
      //   - Admin: NO email by default. Set ADMIN_EMAIL_NOTIFICATIONS=true
      //     env var on Vercel when you actually want a feed of user activity.
      const adminWantsEmail = process.env.ADMIN_EMAIL_NOTIFICATIONS === "true";
      const wearerWantsEmail = importance === "critical";

      if (wearerWantsEmail && user_email && user_email !== adminEmail) {
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

      if (adminWantsEmail) {
        const adminLabel = user_email ? `[Admin] User (${user_email}):` : "[Admin]";
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

    await releaseLock();
    return NextResponse.json({
      intents: storedIntents,
      totalInferred: intents.length,
      totalValid: validIntents.length,
      totalSkippedDuplicates: skippedDuplicates,
      totalSkippedByGate: skippedByGate,
    });
    } finally {
      // Inner finally: release the per-session lock no matter what.
      await releaseLock();
    }
  } catch (err) {
    console.error("Analyze error:", err);
    return NextResponse.json(
      { error: "Analysis failed. Please try again." },
      { status: 500 }
    );
  }
}
