/** @type {import('next').NextConfig} */
const nextConfig = {
  // PostHog's ingest endpoints are on well-known hostnames that every major
  // content blocker ships a rule for, which silently drops a large share of
  // events — disproportionately from the technical, privacy-minded audience
  // this product is aimed at. Proxying through our own origin means the
  // requests are first-party. Note this changes only WHERE events are sent,
  // not WHAT: consent gating and masking still govern collection.
  skipTrailingSlashRedirect: true,
  // /apply is the listings hub for every open role, so the URLs people guess
  // all point there. /growth was the old single-role page and is redirected to
  // its replacement so any link already posted keeps working.
  //
  // Note /build has CHANGED MEANING: it used to be the combined hardware +
  // software role and is now Senior Hardware Engineer. That is deliberate, and
  // it is why nothing redirects to /build any more.
  async redirects() {
    return [
      { source: "/jobs", destination: "/apply", permanent: true },
      { source: "/join", destination: "/apply", permanent: true },
      { source: "/careers", destination: "/apply", permanent: true },
      { source: "/growth", destination: "/grow", permanent: true },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/ingest/static/:path*",
        destination: "https://us-assets.i.posthog.com/static/:path*",
      },
      {
        source: "/ingest/:path*",
        destination: "https://us.i.posthog.com/:path*",
      },
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
