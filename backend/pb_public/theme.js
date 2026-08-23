// Light or dark on Anticipy's public pages, decided before the first frame.
//
// Blocking, in <head>, and not deferred: `defer`/`type=module` would paint the
// default palette first and the chosen one a frame later, and a page changing
// colour under someone is the most visible thing on it.
//
// LIGHT IS THE DEFAULT, and prefers-color-scheme is deliberately not
// consulted. This is the page somebody is walked through over a phone call
// while they install a browser extension; it has to be the same page for
// everyone, not a different one for whoever happens to run their Mac dark.
// Dark is one click away and remembered forever after. Do NOT "improve" this
// into a system-following default — that hands the first impression back to a
// setting nobody chose for this product.
//
// The extension's own two surfaces carry the same logic and the same key
// (extension/theme.js). They are a different origin, so the value cannot be
// shared; the behaviour is.
(function () {
  var KEY = "anticipy.theme";
  var root = document.documentElement;

  // localStorage throws, not returns null, in a locked-down or partitioned
  // profile. Somebody in that profile still gets a themed page.
  function stored() {
    try { return window.localStorage.getItem(KEY); } catch (e) { return null; }
  }

  // Anything that is not the string "dark" is light, so a corrupted or
  // half-written value can only ever fail toward the default.
  function apply(theme) {
    root.setAttribute("data-theme", theme === "dark" ? "dark" : "light");
  }

  apply(stored());

  function label(button) {
    var dark = root.getAttribute("data-theme") === "dark";
    button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  }

  function wire() {
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) {
      label(buttons[i]);
      buttons[i].addEventListener("click", function (event) {
        var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
        apply(next);
        try { window.localStorage.setItem(KEY, next); } catch (e) { /* private mode */ }
        label(event.currentTarget);
      });
    }
  }

  // This runs before <body> exists, so the buttons are not there yet.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }

  // Setup and privacy are one link apart, and both can be open at once.
  window.addEventListener("storage", function (event) {
    if (event.key !== KEY) return;
    apply(event.newValue);
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) label(buttons[i]);
  });
})();
