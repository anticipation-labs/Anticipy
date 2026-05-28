import Link from "next/link";

export const metadata = {
  title: "Install the Anticipy Native Bridge - Anticipy",
  description:
    "Step-by-step guide to install the Anticipy native daemon and Chrome bridge.",
};

const codeStyle: React.CSSProperties = {
  padding: "2px 6px",
  background: "rgba(255,255,255,0.07)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 5,
  fontFamily: "monospace",
  fontSize: 13,
  color: "var(--text-on-dark)",
};

const steps = [
  {
    n: 1,
    title: "Create your account",
    body: (
      <>
        Go to{" "}
        <a
          href="/engine"
          style={{ color: "var(--gold)", textDecoration: "none" }}
        >
          anticipy.ai/engine
        </a>{" "}
        and sign up with your email and password. Keep this page open while
        you install the native bridge.
      </>
    ),
  },
  {
    n: 2,
    title: "Download the native bridge",
    body: (
      <>
        Click the{" "}
        <strong style={{ color: "var(--text-on-dark)" }}>Download v6 bridge</strong>{" "}
        button on the setup card (or download it directly below). Save the file
        somewhere easy to find. Your Desktop works fine.
      </>
    ),
    action: (
      <a
        href="/anticipy-extension-v6.zip?v=20260523-v6"
        download="anticipy-extension-v6.zip"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 8,
          padding: "9px 18px",
          background: "var(--gold)",
          color: "var(--dark)",
          borderRadius: 100,
          fontSize: 14,
          fontWeight: 600,
          textDecoration: "none",
          marginTop: 12,
        }}
      >
        <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
          <path
            d="M6.5 1v8M3 7l3.5 3.5L10 7M1 12h11"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        anticipy-extension-v6.zip
      </a>
    ),
  },
  {
    n: 3,
    title: "Unzip the file",
    body: (
      <>
        Double-click <code style={codeStyle}>anticipy-extension-v6.zip</code> to
        unzip it. You&apos;ll get a folder called{" "}
        <code style={codeStyle}>anticipy-v6</code>. Keep this folder because
        it contains both the daemon installer and the Chrome bridge.
      </>
    ),
  },
  {
    n: 4,
    title: "Install the daemon",
    body: (
      <>
        Open Terminal and run{" "}
        <code style={codeStyle}>
          bash ~/Downloads/anticipy-v6/DAEMON-INSTALLER/install.sh
        </code>
        . This registers the native host that Chrome uses to talk to the
        user-device engine.
      </>
    ),
  },
  {
    n: 5,
    title: "Open Chrome Extensions",
    body: (
      <>
        In Chrome, open a new tab and go to{" "}
        <code style={codeStyle}>chrome://extensions/</code>
        <br />
        Or use the menu: <strong style={{ color: "var(--text-on-dark)" }}>
          ⋮ → Extensions → Manage Extensions
        </strong>
      </>
    ),
  },
  {
    n: 6,
    title: "Enable Developer mode",
    body: (
      <>
        In the top-right corner of the Extensions page, toggle{" "}
        <strong style={{ color: "var(--text-on-dark)" }}>Developer mode</strong>{" "}
        on. Three new buttons will appear at the top.
      </>
    ),
  },
  {
    n: 7,
    title: "Load the bridge",
    body: (
      <>
        Click{" "}
        <strong style={{ color: "var(--text-on-dark)" }}>Load unpacked</strong>,
        then select the{" "}
        <code style={codeStyle}>
          anticipy-v6/EXTENSION-LOAD-THIS-IN-CHROME
        </code>{" "}
        folder you unzipped. The Anticipy Bridge v6 extension will appear in
        your list.
      </>
    ),
  },
  {
    n: 8,
    title: "Pin the bridge",
    body: (
      <>
        Click the puzzle-piece icon{" "}
        <strong style={{ color: "var(--text-on-dark)" }}>🧩</strong> in the
        Chrome toolbar and click the pin next to Anticipy Bridge v6 so it is
        always visible.
      </>
    ),
  },
  {
    n: 9,
    title: "Verify daemon connected",
    body: (
      <>
        Click the Anticipy Bridge icon in your toolbar. The popup should say
        daemon connected. If it shows a native-messaging error, rerun the
        daemon installer and reopen Chrome.
      </>
    ),
  },
];

export default function ExtensionInstallPage() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--dark)",
        color: "var(--text-on-dark)",
      }}
    >
      {/* Header */}
      <header
        style={{
          padding: "16px 24px",
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <a
          href="/"
          className="font-serif"
          style={{
            fontSize: 20,
            color: "var(--text-on-dark)",
            textDecoration: "none",
          }}
        >
          Anticipy
        </a>
        <span style={{ color: "rgba(255,255,255,0.2)" }}>·</span>
        <Link
          href="/engine"
          style={{
            fontSize: 13,
            color: "var(--text-on-dark-muted)",
            textDecoration: "none",
          }}
        >
          Engine
        </Link>
        <span style={{ color: "rgba(255,255,255,0.2)" }}>·</span>
        <span
          style={{
            fontSize: 13,
            color: "var(--gold)",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          Install Guide
        </span>
      </header>

      <main style={{ maxWidth: 680, margin: "0 auto", padding: "48px 24px 80px" }}>
        {/* Title */}
        <h1
          className="font-serif"
          style={{
            fontSize: "clamp(28px, 5vw, 40px)",
            fontWeight: 400,
            marginBottom: 12,
            lineHeight: 1.2,
          }}
        >
          Install the native Chrome bridge
        </h1>
        <p
          style={{
            fontSize: 16,
            color: "var(--text-on-dark-muted)",
            fontWeight: 300,
            lineHeight: 1.7,
            marginBottom: 48,
          }}
        >
          The Anticipy native bridge lets the user-device engine act through
          your real Chrome profile, with your real signed-in surfaces.
        </p>

        {/* Requirement note */}
        <div
          style={{
            padding: "12px 16px",
            background: "rgba(200,169,126,0.06)",
            border: "1px solid rgba(200,169,126,0.15)",
            borderRadius: 10,
            marginBottom: 40,
            fontSize: 13,
            color: "var(--text-on-dark-muted)",
            lineHeight: 1.6,
          }}
        >
          <strong style={{ color: "var(--gold)" }}>Requires:</strong> macOS,
          Python 3.10+, and Google Chrome. Not compatible with Firefox or
          Safari.
        </div>

        {/* Steps */}
        <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {steps.map((step, i) => (
            <li
              key={step.n}
              style={{
                display: "flex",
                gap: 20,
                marginBottom: i < steps.length - 1 ? 36 : 0,
                position: "relative",
              }}
            >
              {/* Number + connector line */}
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    background: "rgba(200,169,126,0.12)",
                    border: "1px solid rgba(200,169,126,0.3)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 13,
                    fontWeight: 600,
                    color: "var(--gold)",
                    flexShrink: 0,
                  }}
                >
                  {step.n}
                </div>
                {i < steps.length - 1 && (
                  <div
                    style={{
                      width: 1,
                      flex: 1,
                      minHeight: 24,
                      background: "rgba(255,255,255,0.06)",
                      marginTop: 8,
                    }}
                  />
                )}
              </div>

              {/* Content */}
              <div style={{ paddingTop: 5, paddingBottom: 8 }}>
                <h3
                  style={{
                    fontSize: 16,
                    fontWeight: 600,
                    marginBottom: 8,
                    color: "var(--text-on-dark)",
                  }}
                >
                  {step.title}
                </h3>
                <p
                  style={{
                    fontSize: 14,
                    color: "var(--text-on-dark-muted)",
                    fontWeight: 300,
                    lineHeight: 1.7,
                  }}
                >
                  {step.body}
                </p>
                {step.action}
              </div>
            </li>
          ))}
        </ol>

        {/* CTA */}
        <div
          style={{
            marginTop: 60,
            padding: "24px",
            background: "var(--dark-elevated)",
            border: "1px solid var(--dark-border)",
            borderRadius: 14,
            textAlign: "center",
          }}
        >
          <p
            style={{
              fontSize: 16,
              fontWeight: 500,
              marginBottom: 8,
            }}
          >
            Ready to set up your account?
          </p>
          <p
            style={{
              fontSize: 14,
              color: "var(--text-on-dark-muted)",
              fontWeight: 300,
              marginBottom: 20,
            }}
          >
            Sign in, then download the native bridge for your real Chrome.
          </p>
          <Link
            href="/engine"
            style={{
              display: "inline-block",
              padding: "10px 28px",
              background: "var(--gold)",
              color: "var(--dark)",
              borderRadius: 100,
              fontSize: 14,
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            Go to Engine →
          </Link>
        </div>
      </main>

      {/* Footer */}
      <footer
        style={{
          padding: "20px 24px",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.2)" }}>
          &copy; 2026 Anticipation Labs
        </p>
        <Link
          href="/engine"
          style={{
            fontSize: 13,
            color: "var(--text-on-dark-muted)",
            textDecoration: "none",
          }}
        >
          Back to Engine
        </Link>
      </footer>
    </div>
  );
}
