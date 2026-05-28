import Link from "next/link";
import { Footer } from "@/components/Footer";

// ─── Reusable doc primitives ─────────────────────────────────────
function SectionHeading({ num, title, id }: { num: string; title: string; id: string }) {
  return (
    <h2
      id={id}
      className="font-serif text-[clamp(28px,4vw,44px)] mt-20 mb-6 leading-[1.15]"
      style={{ color: "var(--text-on-dark)", letterSpacing: "-0.02em" }}
    >
      <span style={{ color: "var(--gold)" }}>{num}.</span> {title}
    </h2>
  );
}

function SubHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3
      className="font-serif text-[22px] mt-10 mb-4"
      style={{ color: "var(--text-on-dark)" }}
    >
      {children}
    </h3>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[16px] leading-[1.75] mb-5"
      style={{ color: "var(--text-on-dark-muted)" }}
    >
      {children}
    </p>
  );
}

function Em({ children }: { children: React.ReactNode }) {
  return <span style={{ color: "var(--text-on-dark)" }}>{children}</span>;
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code
      className="px-[6px] py-[2px] rounded text-[13px] font-mono"
      style={{
        background: "var(--dark-elevated)",
        color: "var(--gold)",
        border: "1px solid var(--dark-border)",
      }}
    >
      {children}
    </code>
  );
}

function CodeBlock({ children, lang }: { children: string; lang?: string }) {
  return (
    <pre
      className="overflow-x-auto rounded-card my-6 text-[13px] leading-[1.6] font-mono p-5"
      style={{
        background: "#0A0A0A",
        border: "1px solid var(--dark-border)",
        color: "#E8E8E8",
      }}
    >
      {lang && (
        <div
          className="text-[11px] uppercase tracking-[0.1em] mb-3"
          style={{ color: "var(--text-on-dark-muted)" }}
        >
          {lang}
        </div>
      )}
      <code>{children}</code>
    </pre>
  );
}

function UList({ children }: { children: React.ReactNode }) {
  return (
    <ul
      className="text-[16px] leading-[1.75] mb-5 pl-6 list-disc space-y-2"
      style={{ color: "var(--text-on-dark-muted)" }}
    >
      {children}
    </ul>
  );
}

function OList({ children }: { children: React.ReactNode }) {
  return (
    <ol
      className="text-[16px] leading-[1.75] mb-5 pl-6 list-decimal space-y-2"
      style={{ color: "var(--text-on-dark-muted)" }}
    >
      {children}
    </ol>
  );
}

function Callout({ children, variant = "neutral" }: { children: React.ReactNode; variant?: "neutral" | "warn" | "good" }) {
  const styles =
    variant === "warn"
      ? { background: "rgba(196, 68, 68, 0.06)", border: "1px solid rgba(196, 68, 68, 0.25)" }
      : variant === "good"
      ? { background: "rgba(200, 169, 126, 0.06)", border: "1px solid rgba(200, 169, 126, 0.30)" }
      : { background: "var(--dark-elevated)", border: "1px solid var(--dark-border)" };

  return (
    <div
      className="rounded-card p-5 my-6 text-[15px] leading-[1.7]"
      style={{ ...styles, color: "var(--text-on-dark)" }}
    >
      {children}
    </div>
  );
}

// ─── DOC ─────────────────────────────────────────────────────────
export function EngineTransferDoc() {
  return (
    <div style={{ background: "var(--dark)", minHeight: "100vh" }}>
      {/* Subtle nav */}
      <header
        className="px-6 md:px-12 py-5 border-b"
        style={{ borderColor: "var(--dark-border)" }}
      >
        <div className="max-w-[820px] mx-auto flex items-center justify-between">
          <Link
            href="/"
            className="font-serif text-[20px]"
            style={{ color: "var(--text-on-dark)" }}
          >
            Anticipy
          </Link>
          <span
            className="text-[12px] uppercase tracking-[0.15em]"
            style={{ color: "var(--gold)" }}
          >
            Transfer Guide
          </span>
        </div>
      </header>

      {/* Hero */}
      <section className="px-6 md:px-12 pt-20 pb-12">
        <div className="max-w-[820px] mx-auto">
          <p
            className="text-[12px] uppercase tracking-[0.15em] mb-6"
            style={{ color: "var(--gold)" }}
          >
            Internal · Action Engine · v0
          </p>
          <h1
            className="font-serif leading-[1.05] mb-6"
            style={{
              color: "var(--text-on-dark)",
              fontSize: "clamp(40px, 7vw, 72px)",
              letterSpacing: "-0.03em",
            }}
          >
            Action Engine — Transfer Guide
          </h1>
          <p
            className="text-[18px] leading-[1.7] mb-4"
            style={{ color: "var(--text-on-dark-muted)" }}
          >
            Everything an engineer needs to take this codebase and ship it on the
            user&apos;s device. The engine is the moat — not the pendant, not the
            phone app, not the marketing site. This document is the handoff
            from the present (server-resident Python service) to the future
            (phone-side companion calling a hardened multi-tenant engine, with a
            pendant streaming intents over BLE). Read it once before touching any
            code; come back to it as the source of truth when something is
            ambiguous.
          </p>
          <p
            className="text-[14px]"
            style={{ color: "var(--text-on-dark-muted)", opacity: 0.7 }}
          >
            Source of truth: <Code>docs/ENGINE_AUDIT_AND_ROADMAP.md</Code>. This guide
            is a curated subset for transfer purposes; when in doubt, consult the
            audit.
          </p>
        </div>
      </section>

      {/* Body */}
      <main className="px-6 md:px-12 pb-24">
        <div className="max-w-[820px] mx-auto">
          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="1" id="three-stages" title="The three stages" />
          <P>
            Anticipy is a wearable that listens to ambient conversation and
            autonomously completes the small tasks people mention but never get
            around to: book the dinner, cancel the trial, dispute the charge,
            schedule the follow-up. The system is split into three stages, in
            strict order. Each one is replaceable; together they form the product.
          </P>

          <SubHeading>Ears — pendant</SubHeading>
          <P>
            A passive audio capture device worn on the body. The v1 spec is 8 g
            brushed titanium, nRF5340 SoC, MEMS mic, mechanical mute switch, BLE
            audio link to the phone, no on-board NPU. The pendant&apos;s job is to
            listen reliably for 12-24 hours on a charge and stream encrypted
            audio frames to the phone. It has no opinion about content. It does
            not transcribe. It does not classify. It never speaks to the cloud.
          </P>

          <SubHeading>Brain — phone companion</SubHeading>
          <P>
            The phone receives the pendant&apos;s audio stream over BLE. The
            entire intelligence pipeline — voice activity detection (Silero VAD),
            speaker diarization (Sortformer or equivalent CoreML model),
            transcription (Whisper Turbo or Parakeet V3), and a small
            ~1B-parameter intent classifier — runs on the phone&apos;s NPU.
            The diarization layer is the architectural keystone: only the
            user&apos;s own clustered voice ever produces an intent. Bystander
            speech is dropped at the VAD/Sortformer stage. This is what keeps
            Anticipy alive in two-party-consent jurisdictions and what Meta
            cannot credibly copy without dismantling its data-harvesting
            business model.
          </P>

          <SubHeading>Hands — Action Engine</SubHeading>
          <P>
            A Python/FastAPI service that drives a stealth Chromium via Browser
            Use to execute tasks on real websites. The phone sends a small
            text-only payload (the intent and any follow-up confirmation tokens);
            the engine runs the browser, streams progress over WebSocket, and
            returns a structured result. <Em>Audio never leaves the device.</Em>
            Only text and intent payloads cross the network.
          </P>

          <Callout variant="good">
            <strong style={{ color: "var(--gold)" }}>Architectural rule.</strong>{" "}
            The phone↔engine boundary is text-only. If you ever find yourself
            adding an audio ingest endpoint to the engine, stop. The privacy
            wedge is the entire moat against Meta.
          </Callout>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="2" id="api-contract" title="API contract" />
          <P>
            The phone↔engine surface is a single authenticated WebSocket
            (<Code>wss://engine.anticipy.ai/ws</Code>) plus a thin REST surface
            for auth, health, and confirmation callbacks. Every WebSocket message
            is a JSON envelope with a <Code>type</Code> discriminator. The shapes
            below are normative — the in-progress proactive package will conform
            to them.
          </P>

          <SubHeading>IntentPayload — phone → engine</SubHeading>
          <P>
            Sent when the on-device pipeline classifies a user utterance as an
            actionable intent. The engine accepts it, decides whether to act
            outright, ask one question, or silently log to the &ldquo;Things I
            noticed&rdquo; feed (the three confidence buckets — see §6).
          </P>
          <CodeBlock lang="typescript">{`interface IntentPayload {
  type: "intent.submit";
  // Stable client-generated id; engine echoes it on every related event.
  intent_id: string;            // uuid v7
  // The utterance, transcribed on-device.
  text: string;
  // Optional structured slots from the on-device classifier.
  slots?: {
    action?: string;            // "book" | "cancel" | "dispute" | ...
    target?: string;            // free-form: "Quattro for Friday at 7"
    urgency?: "now" | "today" | "soon" | "later";
    site_hint?: string;         // domain if classifier already picked one
  };
  // Diarization proof: only the user's voice cluster passes the gate.
  speaker: "user";
  // Confidence from the on-device classifier (0..1).
  confidence: number;
  // Wall-clock at end of utterance. Used for "Things I noticed" ordering.
  utterance_ended_at: string;   // ISO-8601
  // Whether the phone is willing to surface a prompt right now.
  // If false, anything below 0.85 confidence goes silently to the feed.
  interactive: boolean;
}`}</CodeBlock>

          <SubHeading>EngineStatusEvent — engine → phone</SubHeading>
          <P>
            Streamed throughout a task&apos;s life. The phone uses these to drive
            UI: a status pill, a current-step caption, the cost ledger, the
            confirmation sheet. Status messages are already sanitized of
            technical leakage (no JSON, no API errors, no model names — see
            <Code>engine/app/agent.py</Code> sanitization layer).
          </P>
          <CodeBlock lang="typescript">{`type EngineStatusEvent =
  | { type: "task.started"; intent_id: string; route: "act" | "ask" | "log" }
  | { type: "task.step";    intent_id: string; caption: string; step: number }
  | { type: "task.cost";    intent_id: string; usd: number; tokens_in: number; tokens_out: number }
  | { type: "task.confirm_required"; intent_id: string;
       reason: "irreversible" | "spend" | "send" | "delete" | "subscribe";
       human_summary: string;
       confirmation_token: ConfirmationToken;     // required to proceed
       expires_at: string }                       // ISO-8601, 120s default
  | { type: "task.completed"; intent_id: string; summary: string;
       artifacts?: Array<{ kind: "url" | "screenshot" | "receipt"; value: string }> }
  | { type: "task.failed";    intent_id: string;
       reason: "timeout" | "blocked" | "captcha_unsolved" | "auth_required" | "provider_outage" | "user_aborted";
       human_message: string }
  | { type: "task.aborted";   intent_id: string; cause: "disconnect" | "budget" | "user" };`}</CodeBlock>

          <SubHeading>ConfirmationToken — engine ↔ phone, signed</SubHeading>
          <P>
            For any irreversible action — sending, spending, deleting, contacting
            people — the engine pauses and emits a <Code>task.confirm_required</Code>{" "}
            event with a server-issued token. The phone surfaces a yes/no prompt;
            on confirm it sends back the token (signed) plus a wall-clock
            <Code>confirmed_at</Code>. Without that round-trip the engine fails
            closed. This replaces today&apos;s <Code>/execute-intent</Code>{" "}
            auto-confirm — see audit P0-E3.
          </P>
          <CodeBlock lang="typescript">{`interface ConfirmationToken {
  // Opaque, base64url-encoded. Engine verifies HMAC-SHA256(secret, payload).
  token: string;
  // Mirrored fields the phone shows the user — never trust client to reconstruct.
  intent_id: string;
  action_summary: string;       // "Spend $87.50 on dinner reservation at Quattro"
  // 120 second window. After expiry the token is dead.
  expires_at: string;
}

// Phone → engine on user "yes":
interface ConfirmationResponse {
  type: "intent.confirm";
  intent_id: string;
  token: string;                // verbatim from the engine
  confirmed_at: string;         // ISO-8601, phone wall-clock
  user_action: "approved" | "denied";
}`}</CodeBlock>

          <Callout>
            The contract above is the v1 surface. Anything not covered (memory
            recall, batch intents, multi-turn refusals) lives on the engine&apos;s
            roadmap, not in the phone client. Don&apos;t leak speculative shapes
            into the phone app — they will change.
          </Callout>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="3" id="modules" title="Module structure" />
          <P>
            The engine lives at <Code>engine/app/</Code>. Each module is small,
            single-purpose, and replaceable. The boundary between Browser Use,
            our wrapper, and the API layer is intentionally clean — see audit
            Appendix A.1.
          </P>

          <SubHeading>Existing modules</SubHeading>
          <UList>
            <li>
              <Code>main.py</Code> — FastAPI server, WebSocket handler, rate
              limiting, task lifecycle. The HTTP surface; should not know
              anything about browsers or LLMs.
            </li>
            <li>
              <Code>agent.py</Code> — Browser Use integration wrapper. Owns the
              browser session, cookie loading, status streaming, and output
              sanitization. The core of the engine.
            </li>
            <li>
              <Code>safety.py</Code> — Deterministic block/confirm rules. Runs
              before the LLM ever sees the goal. The LLM cannot override it.
            </li>
            <li>
              <Code>router.py</Code> — Pre-classifier (keyword) plus LLM fallback
              that decides whether an input is chat, question, or action.
            </li>
            <li>
              <Code>planner.py</Code> — Goal decomposition and URL extraction.
              No site-specific logic.
            </li>
            <li>
              <Code>models.py</Code> — LLM wrapper with the cascade
              (Gemini → Groq → Anthropic Haiku/Sonnet, see §5 of the audit).
              All caching policy lives here.
            </li>
            <li>
              <Code>auth.py</Code> — bcrypt password hashing, JWT issuance, login
              rate limiting. Will gain refresh tokens and Supabase-backed rate
              limit (audit P1).
            </li>
            <li>
              <Code>captcha.py</Code> — NopeCHA → CapSolver → 2Captcha cascade,
              plus Whisper-based audio reCAPTCHA solver.
            </li>
            <li>
              <Code>config.py</Code> — Env vars, budget limits, required-var
              validation. <Em>Refuse to start</Em> if JWT_SECRET or
              PROFILE_ENCRYPTION_KEY are unset (audit P0-E1, P0-E2).
            </li>
            <li>
              <Code>messages.py</Code> — All user-facing strings. The Donna
              persona lives here. One copywriter, one source of truth.
            </li>
            <li>
              <Code>vision.py</Code> — Stub today (always returns None). Will
              host dense-screenshot/PDF-reading routed to Opus when Sonnet
              fails.
            </li>
            <li>
              <Code>browser.py</Code>, <Code>harness.py</Code> — Legacy,
              not imported. Keep for reference until we&apos;ve verified
              Browser Use covers everything they did. Then delete.
            </li>
          </UList>

          <SubHeading>New: <Code>engine/app/proactive/</Code></SubHeading>
          <P>
            The proactive package is being built in parallel with this guide.
            It implements §6 (proactive engine) of the audit. Anticipated layout:
          </P>
          <UList>
            <li>
              <Code>proactive/__init__.py</Code> — Package surface.
            </li>
            <li>
              <Code>proactive/buckets.py</Code> — Confidence-bucket router
              (&gt;0.85 act, 0.5–0.85 ask, &lt;0.5 log).
            </li>
            <li>
              <Code>proactive/feed.py</Code> — &ldquo;Things I noticed&rdquo;
              feed writer. Persists to Supabase; pushes to phone over WS.
            </li>
            <li>
              <Code>proactive/persona.py</Code> — Donna voice templates,
              refusal-reasons enum, second-opinion branch.
            </li>
            <li>
              <Code>proactive/trust.py</Code> — Per-user autonomy slope. Goes up
              on accepted actions, down on user-corrected mistakes.
            </li>
            <li>
              <Code>proactive/eval/</Code> — LLM-as-judge eval harness with
              <Em> no hardcoded test cases</Em>. Scenarios are generated and
              judged in context (see §8).
            </li>
            <li>
              <Code>proactive/README.md</Code> — One-page intro for newcomers.
            </li>
          </UList>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="4" id="runtime" title="Runtime requirements" />
          <P>
            The engine is server-resident. iOS WebKit (App Store rule) and
            Android Chromium, even in Appium/WebView wrappers, do not have
            anything close to Browser Use&apos;s maturity. <Em>Don&apos;t put
            Playwright on a phone.</Em> Comet, Manus, and OpenAI Operator all
            keep the brain on a server and stream UI to phones. We do the same.
          </P>

          <SubHeading>Stack</SubHeading>
          <UList>
            <li>Python 3.12 (3.11 also works; 3.10 doesn&apos;t — type syntax)</li>
            <li>FastAPI + Uvicorn (single-worker for dev, supervisor for prod)</li>
            <li>Browser Use ≥ 0.12.6 (pin upper bound; their API moves)</li>
            <li>Patchright (stealth Playwright fork) + Chromium</li>
            <li>Xvfb (Linux-only virtual display; the browser runs headful for stealth)</li>
            <li>Supabase (Postgres + Auth + Realtime; project ref <Code>ogbxpqkmsdrcuilafycn</Code>)</li>
            <li>cryptography (Fernet, for cookie encryption)</li>
            <li>bcrypt + PyJWT</li>
            <li>litellm-style direct SDKs for Gemini, Groq, Anthropic (audit §5.4)</li>
          </UList>

          <SubHeading>Environment variables</SubHeading>
          <CodeBlock lang="env">{`# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# LLM providers
GOOGLE_API_KEY=          # Gemini 2.5 Flash (current default)
GROQ_API_KEY=            # Llama 4 Scout / Maverick
ANTHROPIC_API_KEY=       # Haiku 4.5, Sonnet 4.6, Opus 4.7 (after migration)
DEEPSEEK_API_KEY=        # Optional; no credits today

# CAPTCHA
TWOCAPTCHA_API_KEY=
CAPSOLVER_API_KEY=
# NopeCHA is bundled as an extension; no key required at low volume.

# Engine
NEXT_PUBLIC_ENGINE_URL=          # https URL for the frontend
PROFILE_ENCRYPTION_KEY=          # Fernet key, REQUIRED, never default
JWT_SECRET=                      # ≥32 bytes, REQUIRED, never default

# Optional
SENTRY_DSN=
LOG_LEVEL=info`}</CodeBlock>

          <Callout variant="warn">
            <strong style={{ color: "#f87171" }}>Hard rule.</strong>{" "}
            <Code>JWT_SECRET</Code> and <Code>PROFILE_ENCRYPTION_KEY</Code> must
            be set before <Code>uvicorn</Code> binds the port. The current
            <Code>config.py</Code> defaults silently regenerate them on every
            restart, which wipes every user&apos;s saved cookies. Fixing this is
            audit item P0-E2; if you&apos;re reading this on a fresh deploy and
            the audit hasn&apos;t shipped that fix yet, set both vars by hand
            from a 1Password secret.
          </Callout>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="5" id="deployment" title="Deployment options" />

          <SubHeading>(a) Container on Render / Fly.io / Railway</SubHeading>
          <P>
            The default. The repo ships a Dockerfile based on the Playwright
            Python image with Xvfb, all browser binaries, and a <Code>start.sh</Code>{" "}
            entrypoint. Hardening items still open: non-root user, HEALTHCHECK,
            multi-stage build, signal forwarding (audit A16). Today&apos;s deploy
            target on Railway is single-instance; horizontal scaling is unblocked
            once §3-§4 of the audit ship (concurrency cap, watchdog process,
            cookie-key persistence).
          </P>

          <SubHeading>(b) Bare metal on a Linux box</SubHeading>
          <P>
            Useful for power users and for early hardware bring-up. Requirements:
            Ubuntu 22.04 or later, Python 3.12, Xvfb, Chromium dependencies (the
            usual GTK/GLib/NSS bundle), a TLS-fronted reverse proxy (Caddy is
            simplest). Run uvicorn under systemd with restart=always; start Xvfb
            from the systemd unit&apos;s ExecStartPre. Don&apos;t skip the
            watchdog process — see audit §6.4.
          </P>

          <SubHeading>(c) Vercel — not viable</SubHeading>
          <P>
            Vercel functions cannot host this engine. There&apos;s no Xvfb, no
            persistent Chromium process, no long-running tasks (the 5-min limit
            kills tasks; our budget is 300s + browser launch overhead and we want
            headroom). The Next.js site stays on Vercel; the engine never will.
          </P>

          <SubHeading>(d) Phone-resident reference (eventually)</SubHeading>
          <P>
            Long term, when device NPUs and a mature mobile browser-automation
            framework exist, a fully on-device build becomes possible. Expect
            this to be a Swift/Kotlin reference implementation that talks to a
            local engine bound to <Code>127.0.0.1</Code> via the same WebSocket
            contract as §2. Until then: server-resident.
          </P>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="6" id="roadmap" title="6-phase hardware transferability roadmap" />
          <P>
            Reproduced verbatim from audit §9. Phases 0 and 1 are doable in
            parallel. Phases 3 and 4 are the long poles; everything else is
            engineering tractable.
          </P>

          <SubHeading>Phase 0 — Engine hardening (now → 6 weeks)</SubHeading>
          <P>
            §3 P0s + §4 P1s + §5/6/8 strategic upgrades from the audit. Engine
            becomes multi-tenant-safe, observably reliable, ~$0.02/task on the
            routed cascade with prompt caching. Milestone:{" "}
            <Em>9.5/10 on the expanded test_real.py-equivalent suite; 1k tasks
            in dogfood without a leaked browser process.</Em>
          </P>

          <SubHeading>Phase 1 — Phone companion, text-input first (6-14 weeks)</SubHeading>
          <P>
            Native iOS + Android (or Flutter) app. Auth to engine over WebSocket.
            UI shows the &ldquo;Things I noticed&rdquo; feed, current-task
            streaming, confirmation prompts, cost ledger. <Em>No mic yet.</Em>
            The point is to validate the engine&apos;s mobile-orchestrator
            surface before adding audio. Milestone:{" "}
            <Em>50 alpha users, 20 actions/user/week, &lt;5% false-positive rate
            on confirmations.</Em>
          </P>

          <SubHeading>Phase 2 — On-device audio (14-22 weeks)</SubHeading>
          <P>
            Phone&apos;s mic only — no pendant yet. Pipeline: Silero VAD →
            Sortformer diarization (CoreML) → Whisper Turbo or Parakeet V3 →
            ~1B-parameter intent classifier on NPU → IntentPayload to engine.
            Milestone:{" "}
            <Em>≤30s p95 from end-of-utterance to feed entry; ≤5s p95 for
            explicit commands; user-voice diarization recall ≥0.9 in noisy
            environments.</Em>
          </P>

          <SubHeading>Phase 3 — Pendant v1 (22-34 weeks)</SubHeading>
          <P>
            BLE-only audio capture. Mic + visible LED + mechanical mute switch +
            USB-C + 12-24h battery. Talks only to companion app. ODM partner in
            Shenzhen unless capex permits in-house. The marketed 8 g brushed-
            titanium spec is a stretch but achievable with nRF5340 + small LiPo.
            Milestone:{" "}
            <Em>1k units, ≥4.5/5 reliability, BLE audio loss &lt;1% over a
            2-hour continuous session.</Em>
          </P>

          <SubHeading>Phase 4 — Proactive layer (parallel, 24-40 weeks)</SubHeading>
          <P>
            Confidence buckets, &ldquo;Things I noticed&rdquo; feed, refusal
            logic, persona fine-tuning, multi-turn intent buildup. This is where
            Anticipy stops being &ldquo;Siri who books restaurants&rdquo; and
            starts being Donna. Milestone:{" "}
            <Em>≥30% of accepted actions are proactive offers (not user-
            initiated commands); &lt;10% dismissal rate.</Em>
          </P>

          <SubHeading>Phase 5 — Memory, taste, phone-free mode (40-60 weeks)</SubHeading>
          <P>
            Per-user semantic memory store, taste learning, conversation-level
            retrieval. Pendant gets enough on-board NPU (next-gen nRF or Ambiq)
            to run quantized Parakeet + small intent classifier locally and queue
            intents while the phone is unreachable. Milestone:{" "}
            <Em>≥50% of actions reference user-specific memory; 8h offline-
            pendant operation; intent queue end-to-end encrypted with per-device
            keys.</Em>
          </P>

          <Callout variant="good">
            Through all six phases the browser agent itself stays server-resident.
            That is not a limitation — it&apos;s the architecture every working
            consumer browser-agent product (Comet, Manus, Operator) uses.
          </Callout>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="7" id="security" title="Security model" />
          <P>
            Five concentric rings. None of them are optional in v1.
          </P>

          <SubHeading>1. Auth — JWT</SubHeading>
          <P>
            Engine users authenticate with username/password (bcrypt 12 rounds)
            and receive a short-lived JWT. Today the expiry is 72 hours; the
            audit reduces this to 1 hour with a refresh-token round-trip
            (P1-1). The JWT secret must be ≥32 bytes and set before startup;
            the existing <Code>"anticipy-engine-secret-change-me"</Code>{" "}
            default is being removed (audit P0-E1).
          </P>

          <SubHeading>2. Cookie storage — Fernet, per-user-derived key</SubHeading>
          <P>
            Saved login cookies are encrypted at rest in the
            <Code>browser_profiles</Code> Supabase table, keyed on{" "}
            <Code>(user_id, site_domain)</Code>. The current implementation uses
            a single master key — compromise of the key compromises every
            user&apos;s cookies. The audit moves to per-user-derived keys
            (HKDF over the master + the user_id), which is a 4-hour change and
            closes the obvious blast-radius risk (P1-4). Sensitive cookie names
            (<Code>password</Code>, <Code>passwd</Code>, <Code>secret</Code>,
            <Code>credit</Code>, <Code>card</Code>) are stripped before storage;
            session/auth/token cookies are kept because the engine needs them to
            stay logged in.
          </P>

          <SubHeading>3. Confirmation — server-issued signed token</SubHeading>
          <P>
            For any action that <Code>safety.check_needs_confirmation()</Code>{" "}
            flags (purchase, send, book, subscribe, delete, contact), the engine
            pauses, issues a HMAC-signed <Code>ConfirmationToken</Code> with a
            120-second TTL, and waits for the phone to round-trip it back with
            an explicit <Code>confirmed_at</Code> wall-clock and{" "}
            <Code>user_action: &ldquo;approved&rdquo;</Code>. Without that
            round-trip the engine fails closed. This replaces the current
            <Code>/execute-intent</Code> auto-confirm (audit P0-E3).
          </P>

          <SubHeading>4. On-device VAD/diarization gate</SubHeading>
          <P>
            The phone&apos;s VAD/Sortformer pipeline drops every voice cluster
            that isn&apos;t the enrolled user. Bystander speech never reaches
            the transcriber, never reaches the classifier, never reaches the
            engine. There is no &ldquo;please record everything&rdquo; toggle
            and there will not be one. The opt-in &ldquo;act on what others tell
            me to do&rdquo; setting (default OFF) lets the user widen the gate
            for a specific session, not permanently.
          </P>

          <SubHeading>5. No raw audio storage anywhere</SubHeading>
          <P>
            Not on the pendant. Not on the phone (only the diarization model&apos;s
            ephemeral working buffer). Not in transit to the engine. Not in
            Supabase. If you ever find yourself adding an audio storage
            endpoint, see §1 again.
          </P>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="8" id="testing" title="Testing strategy" />
          <P>
            Three layers, no shortcuts. Audit §8 has the full sprint plan; the
            summary below is enough to start.
          </P>

          <SubHeading>Layer 1 — Unit tests with mocked LLM</SubHeading>
          <P>
            Cover the deterministic logic where a regression silently kills
            production safety: <Code>safety.check_blocked()</Code>,{" "}
            <Code>router._pre_classify()</Code>, cost-tracker arithmetic, JWT
            issue/verify, encrypted-cookie round-trip, planner URL extraction.
            Target ≥90% line coverage on{" "}
            <Code>safety.py</Code>, <Code>auth.py</Code>, <Code>router.py</Code>,
            and <Code>planner.py</Code> by the end of week 2. Pytest, no external
            calls, no real keys.
          </P>

          <SubHeading>Layer 2 — Eval harness</SubHeading>
          <P>
            For the deterministic engine: 50-100 golden tasks with expected
            outputs, scored by an LLM-as-judge calibrated against human raters
            on a 20-task subset. Run on every model swap. Adopt the{" "}
            <Em>Online-Mind2Web 300-task harness</Em> as the public benchmark —
            it&apos;s what Browser Use Cloud (97%), Surfer 2 (97.1%), and
            Magnitude (93.9%) all report on. Skip WebVoyager (saturated). Add a
            small <Em>WebGames</Em> subset for spatial grounding (humans 96%,
            GPT-4o 41%) — that&apos;s where Sonnet 4.6&apos;s vision premium
            pays off.
          </P>
          <P>
            For the proactive engine the rule is different:{" "}
            <Em>no hardcoded test cases.</Em> The eval harness generates
            scenarios on the fly (varying speaker count, environment noise,
            urgency, action category, irreversibility), drives them through the
            confidence-bucket router, and judges in context against a rubric.
            Hard-coded scripts will overfit immediately and stop catching the
            interesting failures.
          </P>

          <SubHeading>Layer 3 — Real-site integration tests</SubHeading>
          <P>
            <Code>test_real.py</Code> exists today (470 LOC, target 9/10 pass).
            Expand to 20 tasks across 6 categories — booking, cancellation,
            dispute, scheduling, fact-finding, login-walled-content — and run
            nightly. Add <Em>failure-mode injection</Em>: kill the LLM provider
            mid-step, kill the browser process mid-step, swap the proxy mid-
            step, inject a CAPTCHA mid-step. The current 9-test suite covers
            happy paths only.
          </P>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="9" id="open-questions" title="Open questions (and Omar's answers)" />
          <P>
            Audit §11 lists five product calls only the founder can make. They
            were resolved on 2026-04-30. Treat the answers below as binding
            for v1.
          </P>

          <SubHeading>Q1. V1 audio architecture</SubHeading>
          <P>
            <Em>Decision: on-device only.</Em> The pendant streams encrypted
            audio over BLE to the phone; everything from VAD onward runs on the
            phone&apos;s NPU; only text and intent payloads cross the network.
            This kills cloud-stream as an option and is non-negotiable. It is
            the privacy wedge against Meta and the architectural reason
            Limitless&apos;s GDPR death cannot happen to us.
          </P>

          <SubHeading>Q2. V1 site coverage</SubHeading>
          <P>
            <Em>Decision: open web from day 1.</Em> Browser Use is generic; the
            engine has no hardcoded site logic and we don&apos;t want to build
            any. We accept that consumer-web reliability lands around 70% and
            invest in the per-domain stealth router (audit §6.1) to push it
            toward 85%+ on the high-frequency cancellation/booking/dispute
            corridor. Marketing can lean on the sites we&apos;ve verified;
            engineering doesn&apos;t maintain an allowlist.
          </P>

          <SubHeading>Q3. Confirmation policy</SubHeading>
          <P>
            <Em>Decision: action-category based, with confidence buckets layered
            on top.</Em> Send / contact / spend / delete / subscribe always
            confirms. Fact-finding never confirms. Everything else uses the
            three-bucket rule from §6 (act / ask / log). This formalizes the
            existing <Code>safety.ALWAYS_CONFIRM</Code> pattern and is what the
            <Code>ConfirmationToken</Code> contract in §2 enforces.
          </P>

          <SubHeading>Q4. Identity &amp; credentials</SubHeading>
          <P>
            <Em>Decision: encrypted cookies in Supabase + per-user key derivation
            for v1.</Em> What we have, plus the HKDF migration from audit P1-4.
            The phone-side credential proxy and on-pendant credentials are Phase
            5 options. Don&apos;t build them now.
          </P>

          <SubHeading>Q5. Donna persona</SubHeading>
          <P>
            <Em>Decision: voice with personality.</Em> Concise, dry, slightly
            impatient, opinionated, willing to refuse. All copy lives in{" "}
            <Code>engine/app/messages.py</Code> and{" "}
            <Code>engine/app/proactive/persona.py</Code>. Hire a copywriter, not
            just an ML engineer. The <Code>refusal_reasons</Code> enum is part
            of the persona, not part of the safety layer — it&apos;s how the
            agent says no in voice.
          </P>

          {/* ──────────────────────────────────────────────────────────── */}
          <SectionHeading num="10" id="where-to-start" title="Where to start" />
          <P>
            For a new engineer landing here today, in this order:
          </P>
          <OList>
            <li>
              <Code>CLAUDE.md</Code> — project conventions, architecture summary,
              env vars, key files.
            </li>
            <li>
              <Code>docs/ENGINE_AUDIT_AND_ROADMAP.md</Code> — the full source
              of truth. §1, §9, Appendix A and Appendix C are the mandatory
              read; the rest is reference.
            </li>
            <li>
              <Code>engine/app/main.py</Code> — the FastAPI surface. Get a feel
              for the WebSocket lifecycle and the rate limiting.
            </li>
            <li>
              <Code>engine/app/agent.py</Code> — the core. Browser Use wrapper,
              cookie loading, status streaming, sanitization. Read it twice.
            </li>
            <li>
              <Code>engine/app/proactive/README.md</Code> — the in-progress
              proactive package. If it doesn&apos;t exist yet, you&apos;re here
              before the parallel work landed; the layout in §3 above is the
              spec.
            </li>
          </OList>
          <P>
            After those five, run <Code>npm run dev</Code> in one terminal,
            bring up the engine in another (instructions in CLAUDE.md), and walk
            through the WebSocket contract end-to-end with{" "}
            <Code>test_real.py</Code>. You&apos;ll have the model in your head
            within an afternoon.
          </P>

          {/* Closing footer */}
          <div
            className="mt-24 mb-16 pt-10 text-center"
            style={{ borderTop: "1px solid var(--dark-border)" }}
          >
            <p
              className="text-[14px] mb-2"
              style={{ color: "var(--text-on-dark-muted)" }}
            >
              Locked by passcode. Don&apos;t share this URL.
            </p>
            <p
              className="text-[14px]"
              style={{ color: "var(--gold)" }}
            >
              — Omar
            </p>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
