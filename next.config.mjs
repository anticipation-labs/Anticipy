// Where the fellowship pages and their API are served from. An env var so a
// preview deploy can point at a staging backend without a code change, and so
// moving the backend never means editing a rewrite by hand.
const FELLOWSHIP_ORIGIN =
  process.env.FELLOWSHIP_ORIGIN || "https://backend-production-61e0a.up.railway.app";

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
      // THE UGC CREATOR PROGRAMME IS RETIRED, REPLACED BY THE FELLOWSHIP.
      //
      // Not permanent: three people applied under the old terms ($25 a video
      // past 1,000 views, plus 15% of anything their link sold) and every one
      // of those signups failed to store, because anticipy_ugc_creators was
      // never created in Supabase — the notification emails say so in their
      // own first line. Those three are owed a conversation, not a 301, and a
      // temporary redirect keeps the door open until they have had one.
      { source: "/ugc", destination: "/fellowships", permanent: false },
      { source: "/ugc/apply", destination: "/fellowships", permanent: false },
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
      // THE FELLOWSHIP, SERVED FROM anticipy.ai.
      //
      // The pages and their API live on the PocketBase backend. Rewriting
      // rather than proxying in an API route means the browser only ever
      // talks to anticipy.ai, so there is no cross-origin request to permit
      // and no CORS header to get wrong — the session token stays first
      // party, and one origin owns the cookie jar.
      //
      // The API paths are rewritten too, and they must be: the pages call
      // /fellows/* relative to wherever they are served from, so without
      // these lines the pages would load on anticipy.ai and then fail every
      // single request against a route that does not exist here.
      { source: "/fellowships", destination: `${FELLOWSHIP_ORIGIN}/fellowships.html` },
      { source: "/fellowship-growth-learning", destination: `${FELLOWSHIP_ORIGIN}/fellowship-growth-learning.html` },
      // The .html shapes resolve too, because the two pages link to each
      // other by filename. One set of pages then works unchanged on both
      // origins, with no origin-sniffing in the page and no build step.
      { source: "/fellowships.html", destination: `${FELLOWSHIP_ORIGIN}/fellowships.html` },
      { source: "/fellowship-growth-learning.html", destination: `${FELLOWSHIP_ORIGIN}/fellowship-growth-learning.html` },
      { source: "/fellows/:path*", destination: `${FELLOWSHIP_ORIGIN}/fellows/:path*` },
      // A fellow's minted link. /c/* was the old creator link shape and is
      // pointed at the same place so anything already posted keeps working.
      { source: "/r/:code", destination: `${FELLOWSHIP_ORIGIN}/r/:code` },
      { source: "/c/:code", destination: `${FELLOWSHIP_ORIGIN}/r/:code` },
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
