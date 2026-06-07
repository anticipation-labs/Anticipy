const downloadHref = "/downloads/Anticipy-mac.zip";
const checksumHref = "/downloads/Anticipy-mac.zip.sha256";

export default function Home() {
  return (
    <main className="page">
      <style>{`
        :root {
          color-scheme: dark;
          --bg: #0d0e10;
          --panel: #17191d;
          --panel-strong: #202329;
          --line: #303640;
          --text: #f7f0e6;
          --muted: #aab2bc;
          --gold: #d7b866;
          --green: #79d7a0;
          --blue: #8db7ff;
        }
        * { box-sizing: border-box; }
        html, body { margin: 0; min-height: 100%; background: var(--bg); }
        body {
          font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          color: var(--text);
        }
        a { color: inherit; }
        .page {
          min-height: 100vh;
          background:
            linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0) 340px),
            var(--bg);
        }
        .shell {
          width: min(1120px, calc(100vw - 40px));
          margin: 0 auto;
          padding: 28px 0 44px;
        }
        .nav {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 20px;
          min-height: 44px;
        }
        .brand {
          font-size: 18px;
          font-weight: 650;
        }
        .status {
          color: var(--green);
          font-size: 13px;
          border: 1px solid rgba(121, 215, 160, 0.35);
          background: rgba(121, 215, 160, 0.08);
          padding: 8px 11px;
          border-radius: 999px;
        }
        .hero {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(320px, 440px);
          gap: 42px;
          align-items: center;
          padding: 76px 0 44px;
        }
        h1 {
          font-size: clamp(44px, 6vw, 76px);
          line-height: 0.98;
          letter-spacing: 0;
          margin: 0;
          max-width: 760px;
        }
        .lede {
          margin: 22px 0 0;
          color: var(--muted);
          font-size: 18px;
          line-height: 1.6;
          max-width: 650px;
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 30px;
        }
        .button {
          min-height: 48px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 10px;
          border-radius: 8px;
          padding: 0 18px;
          font-size: 15px;
          font-weight: 650;
          text-decoration: none;
          border: 1px solid transparent;
        }
        .primary { background: var(--text); color: #101114; }
        .secondary { border-color: var(--line); color: var(--text); background: rgba(255,255,255,0.04); }
        .window {
          border: 1px solid var(--line);
          background: var(--panel);
          border-radius: 8px;
          overflow: hidden;
          box-shadow: 0 28px 80px rgba(0,0,0,0.38);
        }
        .windowTop {
          height: 38px;
          display: flex;
          align-items: center;
          gap: 7px;
          padding: 0 14px;
          background: var(--panel-strong);
          border-bottom: 1px solid var(--line);
        }
        .dot { width: 10px; height: 10px; border-radius: 50%; background: #db6c62; }
        .dot:nth-child(2) { background: var(--gold); }
        .dot:nth-child(3) { background: var(--green); }
        .screen {
          padding: 22px;
          display: grid;
          gap: 16px;
        }
        .feedLine {
          min-height: 48px;
          border: 1px solid var(--line);
          background: #101216;
          border-radius: 8px;
          padding: 13px 14px;
        }
        .feedLine strong { display: block; font-size: 13px; color: var(--gold); margin-bottom: 5px; }
        .feedLine span { color: var(--muted); font-size: 13px; line-height: 1.45; }
        .grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 14px;
          margin-top: 22px;
        }
        .step {
          border: 1px solid var(--line);
          background: rgba(255,255,255,0.035);
          border-radius: 8px;
          padding: 18px;
        }
        .step h2 {
          font-size: 15px;
          margin: 0 0 9px;
        }
        .step p {
          margin: 0;
          color: var(--muted);
          font-size: 14px;
          line-height: 1.55;
        }
        .note {
          margin-top: 20px;
          padding: 16px 18px;
          border-radius: 8px;
          border: 1px solid rgba(215,184,102,0.32);
          background: rgba(215,184,102,0.08);
          color: #e9d7a2;
          font-size: 14px;
          line-height: 1.55;
        }
        code {
          display: block;
          margin-top: 9px;
          padding: 12px 13px;
          overflow-wrap: anywhere;
          border-radius: 8px;
          border: 1px solid var(--line);
          background: #08090b;
          color: var(--green);
          font-size: 13px;
        }
        @media (max-width: 820px) {
          .shell { width: min(100vw - 28px, 680px); padding-top: 18px; }
          .hero { grid-template-columns: 1fr; padding-top: 46px; gap: 28px; }
          .grid { grid-template-columns: 1fr; }
          .status { display: none; }
        }
      `}</style>
      <div className="shell">
        <nav className="nav" aria-label="Primary">
          <div className="brand">Anticipy</div>
          <div className="status">Mac build available</div>
        </nav>

        <section className="hero">
          <div>
            <h1>Anticipy for Mac.</h1>
            <p className="lede">
              Download the local app, open it on this Mac, and connect it to the
              private engine running on your machine.
            </p>
            <div className="actions">
              <a className="button primary" href={downloadHref} download>
                Download for macOS
              </a>
              <a className="button secondary" href={checksumHref}>
                SHA-256
              </a>
            </div>
          </div>

          <div className="window" aria-label="Anticipy Mac app preview">
            <div className="windowTop">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
            <div className="screen">
              <div className="feedLine">
                <strong>Live surface</strong>
                <span>Glass-box feed, pending approvals, and local engine status.</span>
              </div>
              <div className="feedLine">
                <strong>Approvals</strong>
                <span>Reversible actions can pause here before anything leaves the Mac.</span>
              </div>
              <div className="feedLine">
                <strong>Local first</strong>
                <span>The app talks to the engine at 127.0.0.1 when it is running.</span>
              </div>
            </div>
          </div>
        </section>

        <section className="grid" aria-label="Install steps">
          <div className="step">
            <h2>1. Download</h2>
            <p>
              The zip contains `Anticipy.app`, built from this repo and ad-hoc
              signed on this Mac.
            </p>
          </div>
          <div className="step">
            <h2>2. Move</h2>
            <p>
              Unzip it, then move `Anticipy.app` to Applications or open it from
              the extracted folder for a quick check.
            </p>
          </div>
          <div className="step">
            <h2>3. Open</h2>
            <p>
              If macOS blocks the first launch, use Privacy and Security, Open
              Anyway. Full notarization still needs a Developer ID certificate.
            </p>
          </div>
        </section>

        <div className="note">
          Terminal install path for production:
          <code>curl -fsSL https://www.anticipy.ai/install.sh | bash</code>
        </div>
      </div>
    </main>
  );
}
