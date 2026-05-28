import { NextResponse } from "next/server";
import { callMistral, mistralAvailable } from "@/lib/mistral";
import { callGroq } from "@/lib/groq";
import { callGemini, lastGeminiUsage, parseJsonWithRepair } from "@/lib/gemini";
import { extractIntentsWithVerification } from "@/lib/intent-extract";
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
import { recallUserProfile } from "@/lib/meta-monitor";
import { recallSimilarEpisodes } from "@/lib/episode-recall";
import { rateLimit } from "@/lib/rate-limit";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const authedUser = await requireSupabaseUser(req);
  if (!authedUser) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Per-user rate limit. analyze is the most expensive endpoint in the
  // app: each call hits Gemini Flash up to 3x (extract → critique → refine)
  // plus a gate pass plus memory + preference recalls. The inflight-lock
  // pattern serializes concurrent calls for the same session, but a
  // compromised JWT could spin many sessions in a tight loop. 600/hr
  // sustained is ~10/min — far above any realistic dictation flow
  // (isFinal=false tics on the client are debounced) and bounded enough
  // to be visible on a Gemini billing dashboard before the bill matters.
  const userLimit = rateLimit(`analyze:user:${authedUser.id}`, 600, 60 * 60_000);
  if (!userLimit.allowed) {
    return NextResponse.json(
      { error: "Too many requests" },
      { status: 429 }
    );
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

    // Reap stale-OWN-USER sessions: any 'recording'/'processing' row older
    // than 24h is the artifact of a tab close or crashed lambda — flip it
    // to 'ended' so the training corpus and dedup paths see a closed
    // state. Scoped to the auth'd user so we never touch another user's
    // session. Targeted partial index keeps this O(log n).
    const STALE_SESSION_HOURS = 24;
    await supabaseAdmin
      .from("anticipy_sessions")
      .update({ status: "ended", ended_at: new Date().toISOString() })
      .eq("user_id", authedUser.id)
      .in("status", ["recording", "processing"])
      .lt(
        "started_at",
        new Date(Date.now() - STALE_SESSION_HOURS * 60 * 60 * 1000).toISOString()
      )
      .neq("id", sessionId); // never auto-end the session we're working on

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

    // Parallel context fan-out: four independent recalls (memory, preferences,
    // episode RAG, user profile) had been chained sequentially, blocking the
    // critical path on ~1.5-2s of cumulative latency. They share no inputs
    // beyond user_id + transcript, so Promise.allSettled runs them concurrently
    // and reduces wall-time to max-of-the-four (~0.5-0.7s). Each branch is
    // already fail-open internally, but allSettled means a thrown rejection on
    // one doesn't cancel the others.
    //
    // - memory: top-N memorable items the wearer has mentioned across sessions
    //   (preferences, relationships, references, ongoing context). Lets the
    //   intent LLM disambiguate pronouns and avoid duplicate intents.
    // - preferences: prior accept/reject/edit/auto_proceed signals as one-
    //   line reasons.
    // - episodes: vector-similarity recall over PAST terminal-status intents.
    //   Returns top-3 closest episodes (transcript + action + outcome).
    // - profile: distilled per-user style summary. Returns "" when
    //   signal_count<3 so early-stage users get the unbiased baseline.
    const [memoryRes, prefRes, episodeRes, profileRes] = await Promise.allSettled([
      recallRelevantMemory(authedUser.id, safeTranscript, 10),
      recallUserPreferences(authedUser.id, 15),
      recallSimilarEpisodes(authedUser.id, safeTranscript, 3),
      recallUserProfile(authedUser.id),
    ]);
    const memoryContext: string[] =
      memoryRes.status === "fulfilled" ? memoryRes.value : [];
    if (memoryRes.status === "rejected") {
      console.warn(
        "[memory-recall] failed; continuing without memory context:",
        memoryRes.reason instanceof Error ? memoryRes.reason.message : memoryRes.reason
      );
    }
    const preferenceContext: string[] =
      prefRes.status === "fulfilled" ? prefRes.value : [];
    if (prefRes.status === "rejected") {
      console.warn(
        "[preference-recall] failed; continuing without preference context:",
        prefRes.reason instanceof Error ? prefRes.reason.message : prefRes.reason
      );
    }
    const episodeContext: string[] =
      episodeRes.status === "fulfilled" ? episodeRes.value : [];
    if (episodeRes.status === "rejected") {
      console.warn(
        "[episode-recall] failed; continuing without episode context:",
        episodeRes.reason instanceof Error ? episodeRes.reason.message : episodeRes.reason
      );
    }
    const userProfileBlock: string =
      profileRes.status === "fulfilled" ? profileRes.value : "";
    if (profileRes.status === "rejected") {
      console.warn(
        "[meta-monitor] recall failed; continuing without profile:",
        profileRes.reason instanceof Error ? profileRes.reason.message : profileRes.reason
      );
    }

    // Optional learned-from-data few-shot block. Off by default. Operator
    // sets ANTICIPY_FEW_SHOT_BLOCK to the block text (e.g. piped from
    // engine/data/few_shot_block.txt produced by build_few_shot_block.py)
    // when running calibration experiments. Production traffic stays on the
    // current prompt.
    const fewShotBlock = process.env.ANTICIPY_FEW_SHOT_BLOCK || "";

    const fewShotPlusProfile =
      [fewShotBlock, userProfileBlock].filter(Boolean).join("\n\n");

    // Build the prompt
    const { system, user } = buildIntentPrompt(
      safeTranscript,
      localTime,
      timezone,
      recentActions,
      crossSessionContext,
      priorIntentContext,
      memoryContext,
      preferenceContext,
      { fewShotBlock: fewShotPlusProfile },
      episodeContext
    );

    const llmMessages = [
      { role: "system" as const, content: system },
      { role: "user" as const, content: user },
    ];

    let response: string = "";

    // ─── ROUTING POLICY ──────────────────────────────────────────────────
    // Provider whitelist (v-final-prototype, 2026-05-13): Cerebras, Mistral,
    // Gemini in hot path. Groq stays as a non-forbidden fallback. Anthropic/
    // Kimi/OpenAI/Deepgram are forbidden — Mistral is the high-quality
    // long-context substitute.
    //
    // Tier 1 (default): Gemini Flash. Cheap, fast, ~$0.0001/call. Handles
    //   the long tail of easy-to-medium scenarios.
    // Tier 1.5 (escalation): mistral-small-latest. Fires PRIMARY when the
    //   transcript is long (>2000 chars) — long context is where Flash's
    //   pronoun-chain / retraction / sarcasm gates leak the most. 262K ctx,
    //   free tier on La Plateforme. Also the second-pass rescue when Flash
    //   returned 0 intents but a heuristic says "transcript had actions".
    //   Skipped silently if MISTRAL_API_KEY is unset.
    // Tier 2/3 (fallback): Groq llama-3.3-70b, Mistral retry.
    const TRANSCRIPT_ESCALATION_CHARS = 2000;
    const mistralEnabled = mistralAvailable();
    const longTranscript = safeTranscript.length > TRANSCRIPT_ESCALATION_CHARS;
    const useMistralPrimary = mistralEnabled && longTranscript;

    const models: Array<{ name: string; fn: () => Promise<string> }> = [];
    if (useMistralPrimary) {
      // Long transcript → Mistral as PRIMARY. Flash drops to backup so we
      // still have a fallback if Mistral rate-limits or times out.
      models.push({
        name: "mistral-small",
        fn: () =>
          callMistral(llmMessages, {
            model: "mistral-small-latest",
            temperature: 0.0,
            max_tokens: 8192,
            jsonOnly: true,
          }),
      });
    }
    // Gemini path now runs the THREE-PASS self-verification loop:
    //   pass 1 = extract (the existing prompt), pass 2 = critique (find flaws),
    //   pass 3 = refine (only when critique is non-clean). The system prompts
    //   are cached server-side via Gemini's cachedContents API, so cache hits
    //   on subsequent calls within the 5-min TTL window pay ~10% of input
    //   tokens. Worst-case cost ≈ 3x baseline; clean-critique short-circuit
    //   keeps the steady-state cost much closer to 2x. See
    //   /workspaces/Anticipy/src/lib/intent-extract.ts for the cost model.
    models.push({
      name: "gemini",
      fn: async () => {
        const result = await extractIntentsWithVerification({
          system: llmMessages[0].content,
          user: llmMessages[1].content,
          cacheKey: "intent-system-v3",
        });
        // Log cache-hit signal when present — useful in production logs
        // for verifying the cache path is actually engaged.
        const usage = lastGeminiUsage();
        const cachedTok =
          usage && typeof (usage as Record<string, unknown>).cachedContentTokenCount === "number"
            ? ((usage as Record<string, unknown>).cachedContentTokenCount as number)
            : null;
        console.log(
          `[analyze] gemini self-verify passes=${result.passesUsed} refined=${result.refined}` +
            (cachedTok !== null ? ` cached_input_tokens=${cachedTok}` : "")
        );
        return JSON.stringify(result.payload);
      },
    });
    models.push({
      name: "groq",
      fn: () =>
        callGroq(llmMessages, {
          temperature: 0.0,
          response_format: { type: "json_object" },
          max_tokens: 8192,
        }),
    });
    if (mistralEnabled && !useMistralPrimary) {
      // Mistral fallback when not already primary. Avoids duplicate call.
      models.push({
        name: "mistral-small-fallback",
        fn: () =>
          callMistral(llmMessages, {
            model: "mistral-small-latest",
            temperature: 0.0,
            max_tokens: 8192,
            jsonOnly: true,
          }),
      });
    }

    let primaryName = "";
    for (const model of models) {
      try {
        response = await model.fn();
        if (!response || response.trim().length === 0) throw new Error(`${model.name} empty`);
        JSON.parse(response);
        primaryName = model.name;
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

    // ─── EMPTY-RESULT RESCUE ─────────────────────────────────────────────
    // If the primary returned 0 intents AND it wasn't already Mistral, ask
    // a tiny Gemini heuristic "did this transcript clearly have actions?".
    // If yes, re-run with Mistral. Generic — no keyword tables; the
    // heuristic LLM judges the transcript on its own merits.
    //
    // The heuristic is one Flash call (~$0.00005) so it's effectively free
    // even when it returns "no". Only when it returns "yes" do we burn a
    // Mistral call.
    const isMistralAlready =
      primaryName === "mistral-small" ||
      primaryName === "mistral-small-fallback";
    if (
      mistralEnabled &&
      !isMistralAlready &&
      response.trim().length > 0
    ) {
      let parsedPreview: { intents?: unknown[] } = {};
      try {
        parsedPreview = JSON.parse(response);
      } catch {
        /* fall through — handled below */
      }
      const zeroIntents =
        Array.isArray(parsedPreview.intents) && parsedPreview.intents.length === 0;
      if (zeroIntents) {
        let hasActions = false;
        try {
          const heuristicRaw = await callGemini(
            [
              {
                role: "system" as const,
                content:
                  "You are a precision binary classifier. Read the transcript and decide whether the WEARER personally committed to do at least one concrete future action AFTER the conversation ends — a real task with a verb + a specific subject (book X, call Y, buy Z, schedule W). Skip pleasantries, delegations to named third parties, hypotheticals, and retracted statements. Return STRICT JSON: {\"has_actions\": <true|false>, \"reasoning\": \"<one short sentence>\"}",
              },
              { role: "user" as const, content: safeTranscript },
            ],
            { temperature: 0.0, max_tokens: 256, cacheKey: "empty-rescue-heuristic-v1", jsonOnly: true }
          );
          // Schema-validate-and-repair: tiny system prompt sometimes leaks
          // prose despite responseMimeType=application/json. parseJsonWithRepair
          // tries strict, fence-strip, substring-extract, then a tiny Flash
          // repair as a last resort.
          const heuristic = await parseJsonWithRepair<{ has_actions?: boolean }>(
            heuristicRaw,
            { allowLLMRepair: false, debugLabel: "empty-rescue-heuristic" }
          );
          hasActions = Boolean(heuristic && heuristic.has_actions);
        } catch (err) {
          console.warn(
            "[analyze] empty-result heuristic failed:",
            err instanceof Error ? err.message : err
          );
        }
        if (hasActions) {
          console.log(
            "[analyze] Flash returned 0 intents but heuristic says transcript has actions — escalating to Mistral"
          );
          try {
            const mistralResponse = await callMistral(llmMessages, {
              model: "mistral-small-latest",
              temperature: 0.0,
              max_tokens: 8192,
              jsonOnly: true,
            });
            // Validate shape before swapping in.
            JSON.parse(mistralResponse);
            response = mistralResponse;
            primaryName = "mistral-small-rescue";
          } catch (err) {
            console.warn(
              "[analyze] Mistral rescue failed; keeping Flash empty result:",
              err instanceof Error ? err.message : err
            );
          }
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

    // Schema-validate-and-repair on the merged LLM response. Until now this
    // was a flat try/JSON.parse; truncated tails or prose-wrapped JSON would
    // silently dump every intent. parseJsonWithRepair walks the strict →
    // fence-strip → substring-extract → tiny-Flash-repair ladder.
    const parsedMaybe = await parseJsonWithRepair<{
      reasoning?: string;
      intents: Array<Record<string, unknown>>;
    }>(response, { allowLLMRepair: true, debugLabel: "analyze-merged" });
    const parsed: { reasoning?: string; intents: Array<Record<string, unknown>> } =
      parsedMaybe && Array.isArray(parsedMaybe.intents)
        ? parsedMaybe
        : { intents: [] };
    if (!parsedMaybe || !Array.isArray(parsedMaybe.intents)) {
      console.error(
        "Failed to parse LLM response:",
        response?.substring(0, 200)
      );
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

      // Test-domain users (e2e-test-*, .test, @anticipy-test.local) get
      // FULLY isolated: no Realtime broadcast, no email, no SMS, no voice.
      // Without the broadcast skip, every benchmark run would fan out to
      // every connected production extension (the broadcast topic is anon-
      // accessible by design so the extension can subscribe). Real users
      // would see ghost test intents firing in their browsers.
      const isTestUser =
        !!user_email && (
          user_email.endsWith(".test") ||
          user_email.endsWith("@anticipy-test.local") ||
          user_email.startsWith("e2e-test-")
        );

      // Broadcast to extension via Supabase Realtime — production users only.
      const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
      const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
      if (!isTestUser && supabaseUrl && serviceKey) {
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
                user_id: authedUser.id,
              },
            }],
          }),
        }).catch((e) => console.warn("[broadcast] failed:", e.message));
      }

      if (isTestUser) {
        // Skip all fan-out for test users — intent row exists in DB for the
        // test harness's polling, but no notifications fire to anyone.
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
        // Bind the email's signed confirm token to the wearer so a leaked
        // link can't be replayed by someone else's user_id (defense in
        // depth on top of the HMAC).
        userId: authedUser.id,
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
