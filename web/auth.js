/* =========================================================
   ANTICIPY — shared auth (the one identity path)
   Vanilla JS, no build step. Loaded BEFORE app.js / onboard.js /
   script.js. Wraps the Supabase JS client (loaded from CDN just
   before this file) and exposes one small, honest surface that
   the Board and onboarding both use:

     Anticipy.auth.currentSession()  -> Promise<session|null>
     Anticipy.auth.requireAuth(opts) -> Promise<session>   (gates the page)
     Anticipy.auth.authHeader()      -> Promise<{Authorization}|{}>
     Anticipy.auth.signIn / signUp / signOut
     Anticipy.auth.onChange(fn)      -> subscribe to auth state
     Anticipy.auth.user()            -> the cached user (or null)

   PUBLIC values only. The Supabase anon key is public by design
   (row-level security + the engine re-verifies every token against
   Supabase /auth/v1/user). NO service-role key, NO secret ever ships here.
   ========================================================= */
(function () {
  "use strict";

  /* ---------- public config (safe to ship) ----------
     These MUST match the engine's NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY
     (.env.local — the LIVE "Anticipy" project ogbxpqkmsdrcuilafycn). The engine re-verifies
     every access token against THIS project's /auth/v1/user (engine/.../core/auth.py), so
     sign-in here MUST mint tokens the engine can verify. Repointed off the dead
     eawoquqgfndmphogwjeu ref so a hosted signup actually leaves the owner core. */
  var SUPABASE_URL = "https://ogbxpqkmsdrcuilafycn.supabase.co";
  var SUPABASE_ANON_KEY =
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9nYnhwcWttc2RyY3VpbGFmeWNuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ4NDI3NDksImV4cCI6MjA5MDQxODc0OX0.PNfKYanSXJTfrYXWGZoUBFaZVE_jnsV4cqBXgxrRJ-0";

  var ANTICIPY = (window.Anticipy = window.Anticipy || {});

  /* ---------- guard: the CDN client must be present ---------- */
  if (!window.supabase || typeof window.supabase.createClient !== "function") {
    // The Supabase UMD bundle didn't load (offline / blocked CDN). Expose a
    // degraded surface so callers fail honestly instead of throwing — every
    // method resolves to "signed out", and requireAuth shows the screen.
    var unavailable = function () {
      return Promise.reject(new Error("auth_unavailable"));
    };
    ANTICIPY.auth = {
      available: false,
      client: null,
      currentSession: function () { return Promise.resolve(null); },
      user: function () { return null; },
      authHeader: function () { return Promise.resolve({}); },
      onChange: function () { return function () {}; },
      signIn: unavailable,
      signUp: unavailable,
      signOut: function () { return Promise.resolve(); },
      requireAuth: function (opts) {
        // Can't verify identity → show the gate, never silently let them in.
        if (opts && typeof opts.onSignedOut === "function") opts.onSignedOut();
        return new Promise(function () {}); // never resolves: the page stays gated
      },
    };
    return;
  }

  var client = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: true,       // session in localStorage (the client owns this)
      autoRefreshToken: true,     // keep the access token fresh in the background
      detectSessionInUrl: true,   // pick up the email-confirmation redirect hash
      storageKey: "anticipy.auth",
    },
  });

  var cachedSession = null;

  /* Keep a hot copy of the session for the synchronous-ish authHeader path. */
  client.auth.getSession().then(function (res) {
    cachedSession = (res && res.data && res.data.session) || null;
  });
  client.auth.onAuthStateChange(function (_event, session) {
    cachedSession = session || null;
  });

  /* ---------- the surface ---------- */
  function currentSession() {
    return client.auth.getSession().then(function (res) {
      cachedSession = (res && res.data && res.data.session) || null;
      return cachedSession;
    });
  }

  function user() {
    return cachedSession && cachedSession.user ? cachedSession.user : null;
  }

  // Resolve a fresh Bearer header for an engine call. Returns {} when signed
  // out so the call still goes out (the engine answers, and a 401 drops the
  // caller to sign-in). getSession() refreshes the token if it's near expiry.
  function authHeader() {
    return currentSession().then(function (s) {
      var t = s && s.access_token ? s.access_token : "";
      return t ? { Authorization: "Bearer " + t } : {};
    });
  }

  function signIn(email, password) {
    return client.auth
      .signInWithPassword({ email: email, password: password })
      .then(function (res) {
        if (res.error) throw res.error;
        cachedSession = res.data.session || null;
        return res.data;
      });
  }

  function signUp(email, password) {
    return client.auth
      .signUp({
        email: email,
        password: password,
        options: { emailRedirectTo: redirectTarget() },
      })
      .then(function (res) {
        if (res.error) throw res.error;
        // If the project requires email confirmation, res.data.session is null
        // and a confirmation mail was sent. If autoconfirm is on, a session is
        // returned and the caller proceeds straight in.
        cachedSession = res.data.session || null;
        return res.data;
      });
  }

  function signOut() {
    return client.auth.signOut().then(function () {
      cachedSession = null;
    });
  }

  function onChange(fn) {
    var sub = client.auth.onAuthStateChange(function (event, session) {
      cachedSession = session || null;
      fn(event, session);
    });
    return function () {
      try { sub.data.subscription.unsubscribe(); } catch (e) { /* noop */ }
    };
  }

  // Where Supabase sends the user back after clicking the email-confirm link.
  // Always THIS origin's onboarding entry, so a confirmed user lands in setup.
  function redirectTarget() {
    try {
      return location.origin + "/onboard.html";
    } catch (e) {
      return undefined;
    }
  }

  /* requireAuth: the page-level gate. Resolves with a live session, or calls
     onSignedOut (so the page can render the sign-in screen) and stays pending.
     The page that uses this never proceeds to the product without a session. */
  function requireAuth(opts) {
    opts = opts || {};
    // LOCAL single-user dev (served from 127.0.0.1 / localhost): the engine is open and there is one
    // default brain, so skip the sign-in gate entirely. Sign-in + per-user is the HOSTED (cloud)
    // experience; locally the app boots straight in and the extension drives THIS same default brain.
    if (/^https?:$/.test(location.protocol) &&
        (location.hostname === "127.0.0.1" || location.hostname === "localhost")) {
      return Promise.resolve(null);
    }
    return currentSession().then(function (session) {
      if (session) return session;
      if (typeof opts.onSignedOut === "function") opts.onSignedOut();
      // Resolve once the user signs in (the auth screen drives it). We listen
      // for the next SIGNED_IN and hand back the session.
      return new Promise(function (resolve) {
        var off = onChange(function (event, s) {
          if (s) {
            off();
            resolve(s);
          }
        });
      });
    });
  }

  ANTICIPY.auth = {
    available: true,
    client: client,
    currentSession: currentSession,
    user: user,
    authHeader: authHeader,
    signIn: signIn,
    signUp: signUp,
    signOut: signOut,
    onChange: onChange,
    requireAuth: requireAuth,
  };
})();
