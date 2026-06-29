export const metadata = {
  title: "Download Anticipy",
  description: "Download Anticipy — the proactive assistant that hears your day and gets your work done.",
};

export default function DownloadPage() {
  return (
    <main className="ant" style={{ maxWidth: 640, margin: "0 auto", padding: "48px 20px 80px" }}>
      <h1 style={{ fontFamily: "var(--serif)", fontSize: 36, marginBottom: 8 }}>Get Anticipy</h1>
      <p style={{ color: "var(--muted)", fontSize: 15, marginBottom: 32, lineHeight: 1.6 }}>
        Everything you need to run the full system on your own machine.
      </p>

      <section className="ant-card" style={{ padding: 24, marginBottom: 20 }}>
        <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, margin: "0 0 8px" }}>
          Browser Helper
        </h2>
        <p style={{ color: "var(--ink-soft)", fontSize: 14, lineHeight: 1.6, margin: "0 0 16px" }}>
          Lets Anticipy work in the browser you already use, so it can prepare safe steps and stop
          before anything that needs your approval.
        </p>
        <a
          href="/anticipy-chrome-extension.zip"
          download
          style={{
            display: "inline-block",
            background: "var(--ink)",
            color: "var(--bg)",
            fontSize: 15,
            fontWeight: 600,
            padding: "12px 28px",
            borderRadius: 10,
            textDecoration: "none",
            marginBottom: 16,
          }}
        >
          Download Extension (.zip)
        </a>
        <div style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 8,
          padding: "14px 16px",
          fontSize: 13,
          lineHeight: 1.6,
          color: "var(--ink-soft)",
        }}>
          <strong>How to install:</strong>
          <ol style={{ margin: "8px 0 0", paddingLeft: 20 }}>
            <li>Unzip the downloaded file</li>
            <li>Open the browser extensions page</li>
            <li>Enable &ldquo;Developer mode&rdquo; (top right toggle)</li>
            <li>Click &ldquo;Load unpacked&rdquo; and select the unzipped folder</li>
            <li>The Anticipy icon appears in your toolbar</li>
          </ol>
        </div>
      </section>

      <section className="ant-card" style={{ padding: 24, marginBottom: 20 }}>
        <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, margin: "0 0 8px" }}>
          Quick Start
        </h2>
        <p style={{ color: "var(--ink-soft)", fontSize: 14, lineHeight: 1.6, margin: "0 0 16px" }}>
          Clone the repo, add your private settings file, and start Anticipy.
        </p>
        <pre style={{
          background: "#1b1a17",
          color: "#f6f3ec",
          padding: "16px 18px",
          borderRadius: 8,
          fontSize: 13,
          lineHeight: 1.6,
          overflow: "auto",
          whiteSpace: "pre-wrap",
        }}>{`# 1. Clone and enter the repo
git clone https://github.com/your-org/anticipy.git && cd anticipy

# 2. Copy your private settings file
cp .env.example .env.local

# 3. Start everything
./scripts/anticipy_setup.sh

# Or manually:
cd engine && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn anticipy_engine.main:app &
cd .. && npm install && npm run dev`}</pre>
      </section>

      <section className="ant-card" style={{ padding: 24 }}>
        <h2 style={{ fontFamily: "var(--serif)", fontSize: 20, margin: "0 0 8px" }}>
          How it works
        </h2>
        <div style={{ fontSize: 14, lineHeight: 1.7, color: "var(--ink-soft)" }}>
          <p style={{ margin: "0 0 12px" }}>
            <strong>Listen</strong> - Press the big Listen button and talk. Anticipy turns
            what matters into plain next steps.
          </p>
          <p style={{ margin: "0 0 12px" }}>
            <strong>Think</strong> - It separates real commitments from vents, jokes, and
            passing noise. Vents are never tasks. Money is always yours to approve.
          </p>
          <p style={{ margin: "0 0 12px" }}>
            <strong>Act</strong> - It can prepare reminders, drafts, browser steps, and calls,
            then pause before anything irreversible.
          </p>
          <p style={{ margin: 0 }}>
            <strong>Remember</strong> - It keeps the people, preferences, commitments, and
            open loops you choose to keep.
          </p>
        </div>
      </section>
    </main>
  );
}
