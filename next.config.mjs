// Where HQ and the referral redirect are served from. An env var so a preview
// deploy can point at a staging backend without a code change.
//
// THE FELLOWSHIP NO LONGER COMES THROUGH HERE. It has its own domain,
// anticipyfellowship.com, its own Vercel project, and a CATCH-ALL rewrite to
// this same backend — so adding a /fellows/* route needs no change in this
// file any more. What is left below is HQ (which deliberately stays on
// anticipy.ai, behind the site passcode) and /r/*.
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
      { source: "/ugc", destination: "https://anticipyfellowship.com/fellowships", permanent: false },
      { source: "/ugc/apply", destination: "https://anticipyfellowship.com/fellowships", permanent: false },
      // THE FELLOWSHIP MOVED to its own domain. These four keep every link
      // that already exists — in an email, in a DM, in somebody's notes —
      // working, and they are the ONLY thing about the fellowship left on
      // this site.
      //
      // 302 and not 301 on purpose. A 301 is cached by browsers effectively
      // for ever, so it cannot be taken back if the domain choice changes;
      // the programme is a day old and the links are few. Flip these to
      // permanent once the address has settled.
      { source: "/fellowships", destination: "https://anticipyfellowship.com/fellowships", permanent: false },
      { source: "/fellowships.html", destination: "https://anticipyfellowship.com/fellowships", permanent: false },
      { source: "/fellowship-growth-learning", destination: "https://anticipyfellowship.com/fellowship-growth-learning", permanent: false },
      { source: "/fellowship-growth-learning.html", destination: "https://anticipyfellowship.com/fellowship-growth-learning", permanent: false },
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
      // The fellowship pages and /fellows/* used to be rewritten here. They
      // are gone: anticipyfellowship.com serves them now, and the redirects
      // above carry the old URLs there. Nothing in this file needs touching
      // when a /fellows/* route is added any more.
      //
      // /r/* STAYS, and that is not an oversight. It is the SALES link — it
      // redirects to this site's own front page with ?ref= — so it belongs on
      // the domain that sells the product, both because that is where the
      // buyer is going and because a link reading anticipyfellowship.com in a
      // creator's bio tells a stranger nothing about what is being sold.
      //
      // A fellow's minted link. /c/* was the old creator link shape and is
      // pointed at the same place so anything already posted keeps working.
      { source: "/r/:code", destination: `${FELLOWSHIP_ORIGIN}/r/:code` },
      { source: "/c/:code", destination: `${FELLOWSHIP_ORIGIN}/r/:code` },
      // HQ — the team's own workspace — now answers at anticipy.ai/internal.
      //
      // It used to be reachable only at the raw Railway hostname, because
      // this site answers /internal itself and nothing forwarded. Nobody is
      // going to type backend-production-61e0a.up.railway.app.
      //
      // NOTHING WAS DELETED TO MAKE ROOM. The hardware hub that lived here —
      // BOM, schematic, assembly, manufacturing, packaging, pendant-upload,
      // competitive — moved one level down to /internal/docs, and the ten
      // pages that linked back to it now link there. Every doc keeps its own
      // URL, untouched.
      //
      // src/middleware.ts still matches /internal and /internal/:path*, so
      // this is BEHIND the site passcode as well as HQ's own key. Two gates
      // is the correct posture for a page that lists three people's phone
      // numbers, and the gate cookie is per-device, so it is one extra
      // password once rather than one every visit.
      { source: "/internal", destination: `${FELLOWSHIP_ORIGIN}/internal.html` },
      // The routes HQ's own page calls. /internal/docs/* is a real Next
      // route and is NOT listed here, so it keeps winning on the filesystem.
      { source: "/internal/state", destination: `${FELLOWSHIP_ORIGIN}/internal/state` },
      { source: "/internal/login", destination: `${FELLOWSHIP_ORIGIN}/internal/login` },
      { source: "/internal/health", destination: `${FELLOWSHIP_ORIGIN}/internal/health` },
      { source: "/internal/people", destination: `${FELLOWSHIP_ORIGIN}/internal/people` },
      { source: "/internal/todos", destination: `${FELLOWSHIP_ORIGIN}/internal/todos` },
      { source: "/internal/todos/delete", destination: `${FELLOWSHIP_ORIGIN}/internal/todos/delete` },
      { source: "/internal/events", destination: `${FELLOWSHIP_ORIGIN}/internal/events` },
      { source: "/internal/events/delete", destination: `${FELLOWSHIP_ORIGIN}/internal/events/delete` },
      { source: "/internal/tracks", destination: `${FELLOWSHIP_ORIGIN}/internal/tracks` },
      // Signing in as yourself, and the seven routes HQ calls once you are.
      // These were missing, so /internal/me 404'd at the edge and the page
      // could never learn who you were — it reached the person picker and
      // then stopped dead. Enumerated, never globbed: /internal/docs/* is a
      // real Next route and a catch-all would swallow the whole hardware hub.
      { source: "/internal/me", destination: `${FELLOWSHIP_ORIGIN}/internal/me` },
      { source: "/internal/session", destination: `${FELLOWSHIP_ORIGIN}/internal/session` },
      { source: "/internal/session/end", destination: `${FELLOWSHIP_ORIGIN}/internal/session/end` },
      { source: "/internal/people/code", destination: `${FELLOWSHIP_ORIGIN}/internal/people/code` },
      { source: "/internal/comments", destination: `${FELLOWSHIP_ORIGIN}/internal/comments` },
      { source: "/internal/notifs/read", destination: `${FELLOWSHIP_ORIGIN}/internal/notifs/read` },
      { source: "/internal/settings", destination: `${FELLOWSHIP_ORIGIN}/internal/settings` },
      // Clerk sign-in: the page trades a verified Clerk token for an ordinary
      // HQ session at this one route; nothing else in HQ knows Clerk exists.
      { source: "/internal/clerk/exchange", destination: `${FELLOWSHIP_ORIGIN}/internal/clerk/exchange` },
      // Expenses (personal tracker + company log) and the password vault.
      { source: "/internal/expenses", destination: `${FELLOWSHIP_ORIGIN}/internal/expenses` },
      { source: "/internal/expenses/delete", destination: `${FELLOWSHIP_ORIGIN}/internal/expenses/delete` },
      { source: "/internal/passwords", destination: `${FELLOWSHIP_ORIGIN}/internal/passwords` },
      { source: "/internal/passwords/reveal", destination: `${FELLOWSHIP_ORIGIN}/internal/passwords/reveal` },
      { source: "/internal/passwords/delete", destination: `${FELLOWSHIP_ORIGIN}/internal/passwords/delete` },
      // The little AI on the side. Only the assistant — the old router and
      // research surfaces stay unreachable.
      { source: "/internal/assistant", destination: `${FELLOWSHIP_ORIGIN}/internal/assistant` },
      // The team notebook.
      { source: "/internal/notes", destination: `${FELLOWSHIP_ORIGIN}/internal/notes` },
      { source: "/internal/notes/delete", destination: `${FELLOWSHIP_ORIGIN}/internal/notes/delete` },
      // The welcome screen's cast list and the settings password change.
      { source: "/internal/people/faces", destination: `${FELLOWSHIP_ORIGIN}/internal/people/faces` },
      { source: "/internal/me/password", destination: `${FELLOWSHIP_ORIGIN}/internal/me/password` },
      { source: "/internal/fellows", destination: `${FELLOWSHIP_ORIGIN}/internal/fellows` },
      { source: "/internal/fellows/remove", destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/remove` },
      // These three existed in the backend and nowhere here, so past the site
      // gate they 404'd at Vercel while answering 401 "wrong key" at the
      // origin — alive, and unreachable through the domain. One of them is
      // the route that pays a fellow.
      { source: "/internal/fellows/pay", destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/pay` },
      { source: "/internal/fellows/submissions/remove", destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/submissions/remove` },
      { source: "/internal/fellows/submissions/release", destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/submissions/release` },
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
