import "./globals.css";

export const metadata = {
  title: "Anticipy Owner Mode",
  description: "Messy life input into safe task cards with receipts.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <nav
          style={{
            display: "flex",
            alignItems: "center",
            gap: 18,
            padding: "8px 18px",
            fontSize: 13,
            fontWeight: 500,
            borderBottom: "1px solid var(--line)",
            background: "var(--panel)",
            color: "var(--muted)",
          }}
        >
          <a href="/" style={{ color: "var(--ink)", fontWeight: 700, textDecoration: "none" }}>
            Anticipy
          </a>
          <a href="/" style={{ color: "var(--muted)", textDecoration: "none" }}>Owner</a>
          <a href="/connect" style={{ color: "var(--muted)", textDecoration: "none" }}>Connect accounts</a>
          <a href="/download" style={{ color: "var(--muted)", textDecoration: "none" }}>Download</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
