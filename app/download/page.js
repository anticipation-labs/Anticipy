// The Anticipy download front-door. Static server component — no client state — so
// it builds and renders standalone. Restyled to the one premium visual language
// (charcoal ground, cream text, DM Serif voice) per ANTICIPY_UX_SPEC §5 / R5.1 —
// no second, busier visual system.
//
// HONEST STATUS: the desktop app is a DEV build today. A signed, notarized public
// download needs an Apple Developer ID + notarization — that is the one live-deferred
// step, flagged below, never faked. The Download button points at the dev artifact
// path the packaging script produces; wire it to the hosted artifact at release.

export const metadata = {
  title: "Download Anticipy",
  description: "The assistant that hears your day, remembers everything, and quietly gets the small things handled.",
};

const DEV_DOWNLOAD_URL =
  process.env.NEXT_PUBLIC_ANTICIPY_DOWNLOAD_URL || "/api/download/anticipy-execute";
const SIGNED = process.env.NEXT_PUBLIC_ANTICIPY_DOWNLOAD_SIGNED === "1";

export default function DownloadPage() {
  return (
    <main className="shell">
      <div className="gate-screen">
        <div className="gate settle" style={{ maxWidth: 460 }}>
          <h1 className="gate-line">It hears you. It&apos;s handled.</h1>
          <p className="gate-why" style={{ fontSize: "var(--t-body)", lineHeight: 1.6 }}>
            The assistant that hears your messy day, remembers everything, and quietly gets your work
            done — preparing each task and waiting for your go. It never acts on a throwaway comment,
            and never spends a cent without you.
          </p>

          <a href={DEV_DOWNLOAD_URL} className="primary" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", textDecoration: "none", width: "fit-content", margin: "8px auto 0", minHeight: 48, padding: "0 28px" }}>
            Download for macOS
          </a>

          <p className="gate-why">
            macOS 13+ · installs the browser helper and walks you through setup
          </p>

          {!SIGNED && (
            <div
              style={{
                marginTop: 16,
                padding: "14px 18px",
                borderRadius: 12,
                background: "var(--ink-raised)",
                border: "1px solid var(--hairline-strong)",
                color: "var(--warm-gray)",
                fontSize: "var(--t-meta)",
                lineHeight: 1.6,
                textAlign: "left",
              }}
            >
              <strong style={{ color: "var(--cream)", fontWeight: 500 }}>Early preview.</strong> After
              it downloads, double-click the file to unzip it. The first time you open it, your Mac may
              ask if you trust it — hold Control, click the app, and choose Open. After that, a normal
              double-click works from anywhere — Downloads, Applications, or your Desktop. A one-click
              version is on the way.
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
