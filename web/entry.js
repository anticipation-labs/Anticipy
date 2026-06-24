/* =========================================================
   ANTICIPY — landing-page entry gating
   The marketing page (index.html) stays public. But the links that
   lead INTO the product (onboarding / the Board) share the one front
   door: clicking them while signed out raises the sign-in screen, and
   only a real session navigates onward. Signed-in already? They pass
   straight through. No fake state, no second auth path.
   ========================================================= */
(function () {
  "use strict";

  var ANTICIPY = window.Anticipy || {};
  var auth = ANTICIPY.auth;
  var gate = ANTICIPY.gate;
  if (!auth || !gate) return; // auth.js / auth-screen.js missing -> leave links as-is

  // Any in-product destination on this site.
  function isProductLink(href) {
    if (!href) return false;
    return /(^|\/)onboard\.html(\?|#|$)/.test(href) || /(^|\/)app\.html(\?|#|$)/.test(href);
  }

  function gateLink(a) {
    a.addEventListener("click", function (e) {
      // already signed in -> let the normal navigation happen
      var u = auth.available ? auth.user() : null;
      if (u) return;

      // signed out -> intercept, raise the gate, then navigate on success
      e.preventDefault();
      var dest = a.getAttribute("href");
      gate.protect({
        onReady: function () {
          window.location.href = dest;
        },
      });
    });
  }

  function wire() {
    var links = document.querySelectorAll("a[href]");
    Array.prototype.forEach.call(links, function (a) {
      if (isProductLink(a.getAttribute("href"))) gateLink(a);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
