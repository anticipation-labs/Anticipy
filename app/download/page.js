// The Anticipy.ai download front-door (Omar's "done": go to Anticipy.ai, see a
// Download button, download the branded app). Static server component — no client
// state — so it builds and renders standalone.
//
// HONEST STATUS: the desktop app ("Anticipy Execute") is a DEV build today. A
// signed, notarized public download needs an Apple Developer ID (Omar's account)
// + Apple notarization — that is the one live-deferred step, flagged below, never
// faked. The Download button points at the dev artifact path the packaging script
// (scripts/package_app.sh) produces; wire it to the hosted artifact at release.

export const metadata = {
  title: "Download Anticipy Execute",
  description: "Download Anticipy — the proactive assistant that hears your day and gets your work done.",
};

const DEV_DOWNLOAD_URL =
  process.env.NEXT_PUBLIC_ANTICIPY_DOWNLOAD_URL || "/api/download/anticipy-execute";
const SIGNED = process.env.NEXT_PUBLIC_ANTICIPY_DOWNLOAD_SIGNED === "1";

export default function DownloadPage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "48px 20px",
        fontFamily: "Inter, system-ui, sans-serif",
        background: "radial-gradient(1200px 600px at 50% -10%, #1b2440 0%, #0b0f1c 60%)",
        color: "#eef2ff",
      }}
    >
      <div style={{ maxWidth: 560 }}>
        <div style={{ fontSize: 14, letterSpacing: 2, opacity: 0.7, textTransform: "uppercase" }}>
          Anticipy.ai
        </div>
        <h1 style={{ fontSize: 44, fontWeight: 700, margin: "12px 0 8px", lineHeight: 1.1 }}>
          Anticipy Execute
        </h1>
        <p style={{ fontSize: 18, opacity: 0.85, margin: "0 0 28px", lineHeight: 1.5 }}>
          The proactive assistant that hears your messy day, remembers everything, and quietly
          gets your work done — preparing each task and waiting for your go. It never acts on a
          throwaway comment, and never spends a cent without you.
        </p>

        <a
          href={DEV_DOWNLOAD_URL}
          style={{
            display: "inline-block",
            background: "#5b8cff",
            color: "#0b0f1c",
            fontSize: 18,
            fontWeight: 600,
            padding: "16px 36px",
            borderRadius: 12,
            textDecoration: "none",
            boxShadow: "0 8px 30px rgba(91,140,255,0.35)",
          }}
        >
          Download for macOS
        </a>

        <p style={{ fontSize: 13, opacity: 0.65, margin: "16px 0 0" }}>
          macOS 13+ · installs the Chrome extension and walks you through setup
        </p>

        {!SIGNED && (
          <div
            style={{
              marginTop: 32,
              padding: "14px 18px",
              borderRadius: 10,
              background: "rgba(255,196,84,0.10)",
              border: "1px solid rgba(255,196,84,0.35)",
              color: "#ffd98a",
              fontSize: 13,
              lineHeight: 1.5,
              textAlign: "left",
            }}
          >
            <strong>Developer preview.</strong> This build is not yet Apple-notarized, so macOS
            will ask you to confirm on first open (right-click → Open). A signed, one-click public
            download ships once the Apple Developer ID is in place.
          </div>
        )}
      </div>
    </main>
  );
}
