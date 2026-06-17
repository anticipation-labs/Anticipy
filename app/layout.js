import "./globals.css";

export const metadata = {
  title: "Anticipy",
  description: "It hears your day, remembers everything, and quietly gets the small things handled.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=Inter:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <nav className="nav">
          <a href="/" className="wordmark">
            Anticipy
          </a>
          {/* The wordmark is "home" (your day). The secondary steps follow in the order a
              first-timer takes them: get set up, connect, then take it with you. */}
          <span className="nav-spacer" />
          <a href="/welcome">Set up</a>
          <a href="/connect">Connect</a>
          <a href="/download">Download</a>
        </nav>
        {children}
      </body>
    </html>
  );
}
