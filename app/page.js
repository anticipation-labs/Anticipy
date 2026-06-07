const downloadPath = "/downloads/Anticipy-mac.zip";

export default function Home() {
  return (
    <main className="page">
      <style>{`
        .page {
          min-height: 100vh;
          display: grid;
          grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
          gap: 4rem;
          align-items: center;
          padding: 5rem;
          box-sizing: border-box;
        }

        .copy {
          max-width: 720px;
        }

        .eyebrow {
          letter-spacing: 0;
          text-transform: uppercase;
          font-size: 0.78rem;
          color: #d7b46a;
          margin: 0;
          font-weight: 700;
        }

        .headline {
          font-family: 'DM Serif Display', Georgia, serif;
          font-size: 5rem;
          line-height: 0.98;
          margin: 1rem 0 1.25rem;
          font-weight: 400;
          letter-spacing: 0;
        }

        .dek {
          color: #c9c3b7;
          font-size: 1.1rem;
          line-height: 1.6;
          max-width: 580px;
          margin: 0;
        }

        .actions {
          display: flex;
          gap: 0.75rem;
          flex-wrap: wrap;
          margin-top: 2rem;
        }

        .download {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 48px;
          padding: 0 1.25rem;
          border-radius: 8px;
          background: #f4f0e8;
          color: #111214;
          text-decoration: none;
          font-weight: 800;
        }

        .preview {
          border: 1px solid #333942;
          border-radius: 8px;
          background: #17191d;
          box-shadow: 0 24px 80px rgba(0, 0, 0, 0.38);
          overflow: hidden;
        }

        .chrome {
          height: 38px;
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 0 14px;
          border-bottom: 1px solid #303640;
          background: #202329;
        }

        .dot {
          width: 11px;
          height: 11px;
          border-radius: 50%;
        }

        .preview-body {
          padding: 1.25rem;
        }

        .rail {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 10px;
          margin-bottom: 16px;
        }

        .rail-item {
          min-height: 72px;
          border-radius: 8px;
          background: #242934;
          border: 1px solid #38404d;
          display: grid;
          place-items: center;
          color: #ddd6ca;
          font-weight: 700;
        }

        .feed {
          border-radius: 8px;
          border: 1px solid #333b47;
          background: #111317;
          padding: 1rem;
        }

        .feed-row {
          display: flex;
          justify-content: space-between;
          gap: 1rem;
          padding: 0.75rem 0;
          border-bottom: 1px solid #2b313a;
          color: #d9d2c7;
        }

        .feed-row:last-child {
          border-bottom: 0;
        }

        .status {
          color: #d7b46a;
        }

        @media (max-width: 860px) {
          .page {
            min-height: auto;
            grid-template-columns: 1fr;
            gap: 2rem;
            padding: 2rem;
          }

          .headline {
            font-size: 3.25rem;
          }
        }

        @media (max-width: 430px) {
          .page {
            padding: 1.25rem;
          }

          .headline {
            font-size: 2.65rem;
          }

          .rail {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      <section className="copy">
        <p className="eyebrow">Anticipy for Mac</p>
        <h1 className="headline">Download Anticipy</h1>
        <p className="dek">
          Install the local Mac surface that connects to the Anticipy engine on this machine.
        </p>
        <div className="actions">
          <a className="download" href={downloadPath} download>
            Download for macOS
          </a>
        </div>
      </section>

      <section className="preview" aria-label="Anticipy app preview">
        <div className="chrome" aria-hidden="true">
          <span className="dot" style={{ background: "#ff6b5f" }} />
          <span className="dot" style={{ background: "#f6c653" }} />
          <span className="dot" style={{ background: "#61c454" }} />
        </div>
        <div className="preview-body">
          <div className="rail">
            {["Listen", "Think", "Act"].map((label) => (
              <div className="rail-item" key={label}>
                {label}
              </div>
            ))}
          </div>
          <div className="feed">
            {["Engine online", "Calendar connector ready", "Waiting for approval"].map((row) => (
              <div className="feed-row" key={row}>
                <span>{row}</span>
                <span className="status">Live</span>
              </div>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
