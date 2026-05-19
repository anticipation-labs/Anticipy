/** @type {import('next').NextConfig} */
const nextConfig = {
  async redirects() {
    return [
      { source: "/", destination: "/app", permanent: false },
      { source: "/engine", destination: "/app", permanent: false },
      { source: "/engine/:path*", destination: "/app", permanent: false },
      { source: "/demo", destination: "/app", permanent: false },
      { source: "/engine-transfer", destination: "/app", permanent: false },
      { source: "/ambient-intent", destination: "/app", permanent: false },
      { source: "/compare", destination: "/app", permanent: false },
      { source: "/funded", destination: "/app", permanent: false },
      { source: "/for", destination: "/app", permanent: false },
      { source: "/for/:path*", destination: "/app", permanent: false },
      { source: "/vs/:path*", destination: "/app", permanent: false },
      { source: "/waitlist", destination: "/app", permanent: false },
      { source: "/crm", destination: "/app", permanent: false },
      { source: "/crm/:path*", destination: "/app", permanent: false },
      { source: "/guide/:path*", destination: "/app", permanent: false },
    ];
  },
  async headers() {
    return [
      {
        // Apply low-risk security headers to every route. We deliberately
        // skip Content-Security-Policy here — the /engine page pulls
        // wss://*.supabase.co + supabase.in for Realtime, plus dynamic
        // scripts from Vercel telemetry, and a misconfigured CSP would
        // silently break the live demo. Add CSP later, after validating
        // the full third-party origin list against a real session.
        source: "/(.*)",
        headers: [
          // Block clickjacking — no embed in foreign frames.
          { key: "X-Frame-Options", value: "DENY" },
          // Disable MIME sniffing so a stored JSON or text response
          // can't be reinterpreted as script by old browsers.
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Don't leak the full URL (which may contain ?session=… or
          // ?intent=…) in cross-origin Referer headers.
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Microphone is required by /engine (voice capture). Camera
          // and geolocation are not used anywhere on this site, so
          // disable them at the platform level. Same-origin allow on
          // microphone — the extension explicitly opts in elsewhere.
          {
            key: "Permissions-Policy",
            value: "microphone=(self), camera=(), geolocation=()",
          },
          // Set HSTS so once the user visits over HTTPS, the browser
          // refuses to downgrade. 1 year + preload-eligible.
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains; preload",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
