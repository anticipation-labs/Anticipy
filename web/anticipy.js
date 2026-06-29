/* =========================================================
   ANTICIPY — shared front-end runtime (anticipy.js)
   Loaded AFTER the Supabase CDN + auth.js on every page of the new
   flow. Provides ONE place for: the engine api() wrapper, the
   coming-soon registry + helper, a toast, and a tiny nav builder.
   No build step, no framework.
   ========================================================= */
(function () {
  "use strict";

  var A = (window.Anticipy = window.Anticipy || {});

  /* ---------- engine base (same-origin when served by uvicorn) ---------- */
  var SAME_ORIGIN =
    location.protocol.indexOf("http") === 0 &&
    (location.hostname === "127.0.0.1" || location.hostname === "localhost" ||
     /anticipy/i.test(location.hostname));
  var ENGINE = SAME_ORIGIN ? "" : (window.ANTICIPY_ENGINE_URL || "");

  function authHeader() {
    var a = A.auth;
    if (a && typeof a.authHeader === "function") {
      return a.authHeader().catch(function () { return {}; });
    }
    return Promise.resolve({});
  }

  // api("/path", {method, body}) -> Promise<json|text>. Sends the Supabase
  // bearer when signed in. Never throws on non-2xx silently — rejects with the
  // status so callers fail honestly.
  function api(path, opts) {
    opts = opts || {};
    return authHeader().then(function (auth) {
      var headers = Object.assign({ "Content-Type": "application/json" }, auth, opts.headers || {});
      var init = { method: opts.method || "GET", headers: headers };
      if (opts.body !== undefined) init.body = typeof opts.body === "string" ? opts.body : JSON.stringify(opts.body);
      return fetch(ENGINE + path, init).then(function (res) {
        var ct = res.headers.get("content-type") || "";
        var parse = ct.indexOf("application/json") >= 0 ? res.json() : res.text();
        return parse.then(function (data) {
          if (!res.ok) { var e = new Error("http_" + res.status); e.status = res.status; e.data = data; throw e; }
          return data;
        });
      });
    });
  }
  A.api = api;
  A.ENGINE = ENGINE;

  /* ---------- COMING-SOON registry ----------
     The single source of truth for which features are LIVE. A button with
     data-soon="<key>" is blocked + pill-tagged UNLESS LIVE[key] is true.
     Each later build phase flips its own keys to true — that is literally how
     we "remove the coming-soon labels". */
  var LIVE = (A.LIVE = {
    // Phase 1 (this build) — live now:
    auth: true,            // Supabase sign-in / sign-up / email
    onboarding_form: true, // the "about you" form (page 4) + clarify (page 11)
    onboarding_complete: true,
    capture_text: true,    // pasting a transcript into the Board
    autonomy_dial: true,   // setting Limited / Regular / Full-Send
    nav: true,

    // Later phases — coming soon (flip to true when the phase lands):
    onboarding_scrape: false, // Phase 7 — Layer scrapes
    onboarding_calls: false,  // Phase 7 — Twilio calls
    mp3_transcribe: false,    // Phase 6 — MP3 -> transcript
    mic_live: false,          // Phase 6 — live mic
    browser_act: false,       // Phase 3 — live browser action / watch-it-work
    memory_view: false,       // Phase 4 — memory viewer + correction
    text_mirror: false,       // Phase 5 — SMS mirror of every proof
    follow_up: false          // Phase 5 — durable 3-days-later follow-up
  });

  function isLive(key) { return !key || LIVE[key] === true; }
  A.isLive = isLive;

  // Decorate the page: add "soon" pills, and intercept clicks on not-live actions.
  function applyComingSoon(root) {
    root = root || document;
    var els = root.querySelectorAll("[data-soon]");
    Array.prototype.forEach.call(els, function (el) {
      var key = el.getAttribute("data-soon");
      if (isLive(key)) { el.removeAttribute("data-soon"); return; }
      if (!el.querySelector(".soon") && el.getAttribute("data-soon-pill") !== "off") {
        var pill = document.createElement("span");
        pill.className = "soon";
        pill.textContent = "soon";
        el.appendChild(pill);
      }
      if (!el.__soonWired) {
        el.__soonWired = true;
        el.addEventListener("click", function (e) {
          e.preventDefault(); e.stopPropagation();
          toast((el.getAttribute("data-soon-msg") || "Coming soon — wiring this up in a later step."), "soon");
        }, true);
      }
    });
  }
  A.applyComingSoon = applyComingSoon;

  /* ---------- toast ---------- */
  var toastWrap;
  function toast(msg, kind) {
    if (!toastWrap) {
      toastWrap = document.createElement("div");
      toastWrap.className = "an-toast-wrap";
      document.body.appendChild(toastWrap);
    }
    var t = document.createElement("div");
    t.className = "an-toast";
    if (kind === "soon") {
      t.innerHTML = '<span class="soon-ico">&#9733;</span> ' + escapeHtml(msg);
    } else {
      t.textContent = msg;
    }
    toastWrap.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("show"); });
    setTimeout(function () {
      t.classList.remove("show");
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
    }, kind === "soon" ? 2600 : 2200);
  }
  A.toast = toast;

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  A.escapeHtml = escapeHtml;

  /* ---------- signed-in nav ---------- */
  // Builds the product top-nav (Tasks · MP3 · Settings) into [data-an-nav].
  function buildNav(active) {
    var host = document.querySelector("[data-an-nav]");
    if (!host) return;
    var items = [
      { href: "app.html", label: "Tasks", key: "tasks" },
      { href: "mp3.html", label: "Upload", key: "mp3" },
      { href: "settings.html", label: "Settings", key: "settings" }
    ];
    host.innerHTML = "";
    items.forEach(function (it) {
      var a = document.createElement("a");
      a.href = it.href; a.textContent = it.label;
      if (it.key === active) a.className = "active";
      host.appendChild(a);
    });
  }
  A.buildNav = buildNav;

  /* ---------- boot ---------- */
  // Force the full signed-out flow (for demos) with ?flow=1 even on localhost.
  A.forceFlow = /[?&]flow=1/.test(location.search);

  function boot() {
    applyComingSoon(document);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
