// Hardware Portability Guide — internal docs page.
// Server component, gated by the existing /internal layout PasswordGate
// (sessionStorage-based, dev-friendly).
//
// Lives at: /internal/hardware-transfer

const COLORS = {
  bg: "#0C0C0C",
  cream: "#F5F0EB",
  gold: "#C8A97E",
  dim: "#8A8A8A",
  border: "#1f1f1f",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 48 }}>
      <h2 style={{
        fontFamily: "Georgia, serif",
        color: COLORS.gold,
        fontSize: 22,
        marginBottom: 12,
        borderBottom: `1px solid ${COLORS.border}`,
        paddingBottom: 6,
      }}>{title}</h2>
      {children}
    </section>
  );
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code style={{
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      background: "#161616",
      padding: "1px 6px",
      borderRadius: 3,
      fontSize: 13,
      color: COLORS.cream,
    }}>{children}</code>
  );
}

export default function HardwareTransferPage() {
  return (
    <main style={{
      background: COLORS.bg,
      minHeight: "100vh",
      color: COLORS.cream,
      padding: "48px 24px",
      fontFamily: "ui-sans-serif, system-ui, sans-serif",
      fontSize: 15,
      lineHeight: 1.55,
    }}>
      <div style={{ maxWidth: 880, margin: "0 auto" }}>
        <header style={{ marginBottom: 40 }}>
          <p style={{ color: COLORS.dim, fontSize: 12, letterSpacing: 1.5, marginBottom: 6 }}>
            ANTICIPY · INTERNAL
          </p>
          <h1 style={{ fontFamily: "Georgia, serif", fontSize: 36, color: COLORS.gold, margin: 0 }}>
            Hardware-Portability Guide
          </h1>
          <p style={{ color: COLORS.dim, marginTop: 12 }}>
            How the current cloud + extension stack maps onto the wearable when hardware ships.
            Read top to bottom; everything cited is in the repo.
          </p>
        </header>

        <Section title="1 · Architecture map">
          <p>
            Today there are four pieces. Each row says where the piece runs <em>now</em>,
            where it runs on the <em>wearable</em>, and what changes at the boundary.
          </p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14, marginTop: 12 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}`, color: COLORS.gold }}>
                  <th style={{ textAlign: "left", padding: 8 }}>Component</th>
                  <th style={{ textAlign: "left", padding: 8 }}>Today</th>
                  <th style={{ textAlign: "left", padding: 8 }}>On the wearable</th>
                  <th style={{ textAlign: "left", padding: 8 }}>Migration</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 8 }}>Audio capture + VAD + speaker-ID (L0)</td>
                  <td style={{ padding: 8 }}>Browser mic in software demo</td>
                  <td style={{ padding: 8 }}><strong>On-device</strong></td>
                  <td style={{ padding: 8 }}>Latency &amp; privacy. Hardware DSP runs VAD; speaker-ID model lives in flash.</td>
                </tr>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 8 }}>Salience filter (L1)</td>
                  <td style={{ padding: 8 }}><Code>engine/app/proactive/salience.py</Code></td>
                  <td style={{ padding: 8 }}>On-device (small model)</td>
                  <td style={{ padding: 8 }}>Most utterances are noise. Filtering on-device saves bandwidth.</td>
                </tr>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 8 }}>Interpreter (L2)</td>
                  <td style={{ padding: 8 }}><Code>proactive/interpreter.py</Code></td>
                  <td style={{ padding: 8 }}>Cloud (LLM)</td>
                  <td style={{ padding: 8 }}>Wearable streams salient chunks to cloud only.</td>
                </tr>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 8 }}>Reversibility / Urgency / Donna / Dispatcher (L3-L6)</td>
                  <td style={{ padding: 8 }}><Code>proactive/{`{reversibility,urgency,donna,dispatcher}`}.py</Code></td>
                  <td style={{ padding: 8 }}>Cloud</td>
                  <td style={{ padding: 8 }}>Production today goes through <Code>src/app/api/engine/analyze/route.ts</Code> instead. Either path writes to the same Supabase tables.</td>
                </tr>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 8 }}>Intent broadcast</td>
                  <td style={{ padding: 8 }}>Supabase Realtime (<Code>anticipy-intents</Code> topic)</td>
                  <td style={{ padding: 8 }}>Same</td>
                  <td style={{ padding: 8 }}>No change. The wearable&apos;s intents land in the same channel as the demo&apos;s.</td>
                </tr>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 8 }}>Action engine (browser agent)</td>
                  <td style={{ padding: 8 }}><strong>Chrome extension</strong> in user&apos;s real browser</td>
                  <td style={{ padding: 8 }}>Same — extension keeps running</td>
                  <td style={{ padding: 8 }}>Wearable doesn&apos;t need Chromium. Intents fan out to whichever Chrome the user has open.</td>
                </tr>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <td style={{ padding: 8 }}>Cloud failover engine</td>
                  <td style={{ padding: 8 }}><Code>engine/</Code> (Python + headful Chromium)</td>
                  <td style={{ padding: 8 }}>Same (cloud)</td>
                  <td style={{ padding: 8 }}>Used when the user&apos;s extension is offline or a site blocks the user&apos;s cookie session.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Section>

        <Section title="2 · On-device vs off-device split">
          <p><strong>On-device (privacy / latency)</strong>: audio capture, VAD, speaker-ID, salience filter (L0–L1). Decision fires within ~200 ms of speech end.</p>
          <p><strong>Cloud</strong>: LLM-driven layers (L2 Interpreter and downstream), action engine, profile sync, encrypted cookie store, dashboards. Today already runs on Vercel + (eventually) Fly.io for the engine.</p>
          <p><strong>User&apos;s Chrome</strong>: action execution via the extension. Real cookies. Real residential IP.</p>
          <p>The wearable&apos;s job is just <em>capture + filter + tag</em>. Heavy lifting happens off-device.</p>
        </Section>

        <Section title="3 · Dispatch protocol from wearable → action surface">
          <p>
            Recommended path: <strong>wearable → user&apos;s phone (BLE) → Supabase Realtime</strong>.
            The phone is always near the wearable, has Wi-Fi, and already runs the user&apos;s Anticipy
            companion app. It writes the intent row into <Code>anticipy_intents</Code> via Supabase
            REST (service-role key, scoped to that user&apos;s session).
          </p>
          <p>
            Not recommended: wearable speaks to Supabase directly. Adds a TLS stack, certificate
            management, and a Realtime client to the wearable&apos;s firmware.
          </p>
          <p>
            Wire format the phone uses (matches what <Code>analyze/route.ts</Code> writes today):
          </p>
          <pre style={{
            background: "#161616",
            padding: 16,
            borderRadius: 6,
            fontSize: 13,
            overflowX: "auto",
            fontFamily: "ui-monospace, SFMono-Regular, monospace",
          }}>{`{
  "id": "<uuid>",
  "session_id": "<uuid>",
  "summary_for_user": "<one-line natural-language>",
  "action_type": "browser_action" | "send_email" | ...,
  "parameters": { "browser_task": "<the actual instruction>", ... },
  "status": "pending",
  "confidence": 0.9,
  "importance": "standard",
  "evidence_quote": "<exact quote that triggered this>"
}`}</pre>
          <p>
            After insert, the broadcast handler in <Code>anticipy-intents</Code> wakes the
            user&apos;s Chrome extension. Once the user (or wearable haptic confirm) approves,
            the row is PATCHed to <Code>status=&quot;confirmed&quot;</Code> and the extension&apos;s
            BrowserAgent runs.
          </p>
        </Section>

        <Section title="4 · Action execution on the wearable side">
          <p>The wearable does not run Chrome. Two execution surfaces, in priority order:</p>
          <ol>
            <li>
              <strong>Chrome extension</strong> in the user&apos;s laptop / desktop —
              <Code>extension/agent.js</Code> picks up <Code>confirmed_intent</Code> broadcast,
              runs the LLM agent loop, executes actions in the user&apos;s real tabs.
              Real cookies, real IP. Default path.
            </li>
            <li>
              <strong>Cloud failover engine</strong> at <Code>engine/app/agent.py</Code> —
              Python + Browser Use + headful Chromium. Used when (a) the user has no Chrome
              available, (b) a site blocks the extension surface, or (c) the user explicitly
              requests &quot;run this from the cloud&quot;. Single-Fly.io machine on
              <Code>shared-cpu-2x</Code> with 2 GB RAM.
            </li>
          </ol>
          <p>
            Both surfaces consume the same intent row and write back the same
            <Code>execution_result</Code> + <Code>status</Code>. The wearable doesn&apos;t need to know which fired.
          </p>
        </Section>

        <Section title="5 · Code-sandbox isolation (per-user)">
          <p>
            <Code>engine/app/code_sandbox.py</Code> wraps user-supplied code with bwrap (user
            namespace + mount-ns + pid-ns + net-ns + resource limits). Multi-tenant, no shared
            state, capped at 256 MB RAM and 5 s CPU per call.
          </p>
          <p>
            On the wearable&apos;s RTOS (or Linux variant): the bwrap path translates to whatever
            sandbox the SDK ships. If it&apos;s Yocto-Linux, bwrap continues to work as-is. If
            it&apos;s a custom RTOS, the equivalent is the SDK&apos;s app-isolation API
            (per-process address space + capability gates). The Python wrapper
            <Code>code_sandbox.run()</Code> is the porting unit.
          </p>
        </Section>

        <Section title="6 · Exact API contracts the wearable must hit">
          <p>Two endpoints; nothing else.</p>
          <ul>
            <li>
              <strong>Insert intent</strong>:&nbsp;
              <Code>POST {`{SUPABASE_URL}`}/rest/v1/anticipy_intents</Code> with the JSON above.
              Headers: <Code>apikey</Code>, <Code>Authorization: Bearer {`{service-role-key}`}</Code>.
              Returns <Code>201 Created</Code>.
            </li>
            <li>
              <strong>Confirm</strong>:&nbsp;
              <Code>GET https://www.anticipy.ai/api/engine/confirm?intentId=&lt;id&gt;&amp;action=yes</Code>.
              The route atomically PATCHes <Code>pending → confirmed</Code> (TOCTOU-safe via
              <Code>WHERE status=&apos;pending&apos;</Code>) and broadcasts the
              <Code>confirmed_intent</Code> event. The user&apos;s extension runs.
            </li>
          </ul>
          <p>
            Confirm has authentication via signed gate cookies set by
            <Code>src/lib/engine-transfer-gate.ts</Code> for the /engine UI.  Wearable can use
            the user&apos;s Supabase session token (issued at first phone-pair) to call confirm
            directly, bypassing the click-the-notification step.
          </p>
        </Section>

        <Section title="7 · Ship-day checklist">
          <p>When the wearable lands, the changes that actually need to happen:</p>
          <ol>
            <li>
              Add <Code>device_id</Code> column to <Code>anticipy_intents</Code> so we can
              tell which wearable a row came from. RLS rule: extension only sees rows where
              <Code>device_id IS NULL OR device_id = current_user_device()</Code>.
            </li>
            <li>
              Add a wearable-pair flow at <Code>/pair</Code>: phone scans a QR, the phone
              gets a Supabase JWT scoped to a single device row in
              <Code>anticipy_devices</Code>. Wearable holds that JWT in NVRAM.
            </li>
            <li>
              Phone-side BLE service that reads salient-chunks from the wearable, posts to
              <Code>POST /api/engine/analyze</Code> (server-side LLM extracts intents).
            </li>
            <li>
              Haptic confirm flow: wearable buzz → phone notifies → tap to confirm →
              call <Code>/api/engine/confirm</Code> with the same flow as today&apos;s
              notification click.
            </li>
            <li>
              Per-user LLM API key rotation. Today the extension gets a shared
              Groq + Gemini key from <Code>/api/extension/auth</Code>. At wearable scale
              (1k+ users), proxy through anticipy.ai with per-user rate limits, OR
              issue per-user keys with quotas. Either is generic; pick one.
            </li>
            <li>
              Cloud failover already deployable to Fly.io (<Code>engine/Dockerfile</Code>
              and <Code>start.sh</Code> are ready). Set
              <Code>NEXT_PUBLIC_ENGINE_URL=https://anticipy-engine.fly.dev</Code> on Vercel.
            </li>
          </ol>
        </Section>

        <Section title="8 · What stays out of the wearable, deliberately">
          <ul>
            <li>Chromium / any web rendering engine.</li>
            <li>The full LLM stack — only L0/L1 small models live on-device.</li>
            <li>OAuth / cookie storage — that lives in the user&apos;s real Chrome via the extension.</li>
            <li>Action engine retries, planner state — pure cloud or extension.</li>
          </ul>
        </Section>

        <footer style={{ marginTop: 64, paddingTop: 24, borderTop: `1px solid ${COLORS.border}`, color: COLORS.dim, fontSize: 13 }}>
          Last updated: 2026-05-07. Source files cited live in the repo at the paths shown.
          When something here drifts from reality, fix the code <em>and</em> this page.
        </footer>
      </div>
    </main>
  );
}
