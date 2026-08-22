// Light or dark, on both of this extension's surfaces, decided before the
// first frame is painted.
//
// THREE THINGS THIS FILE IS DELIBERATE ABOUT.
//
// 1. It is a CLASSIC script in <head>, not a module.
//    `<script type="module">` is deferred — it runs after the document has
//    been parsed, which means the browser paints the default palette first and
//    the chosen one a frame later. On a page whose whole job is to be calm
//    while somebody types six digits, that flash is the most visible thing on
//    it. A blocking classic script in <head> sets the attribute before any
//    pixels exist. (It is an external file, not inline: MV3's extension_pages
//    CSP is `script-src 'self'`, so an inline <script> would be refused
//    outright and this page would have no theme control at all.)
//
// 2. It reads localStorage, not chrome.storage.
//    chrome.storage.local is the right home for state the service worker
//    shares, and it is async — so it cannot answer before paint, which is the
//    one requirement here. popup.html and onboarding.html are the same origin
//    (chrome-extension://<id>), so localStorage is already shared between
//    exactly the two surfaces that need to agree, and it answers
//    synchronously. Nothing outside these two pages has any use for the value.
//
// 3. LIGHT IS THE DEFAULT, and prefers-color-scheme is not consulted.
//    This page opens itself, unasked, in somebody's browser, and it is the
//    page a person is walked through over a phone call. It has to be the same
//    page for everyone, not a different one on whoever happens to run their
//    Mac dark. Dark is one click away and remembered forever after. Do NOT
//    "improve" this into a system-following default: that hands the first
//    impression back to a setting nobody chose for this product.
(function () {
  var KEY = "anticipy.theme";
  var root = document.documentElement;

  // localStorage throws, not returns null, when storage is partitioned or
  // disabled. A person with a locked-down profile still gets a themed page.
  function stored() {
    try { return window.localStorage.getItem(KEY); } catch (e) { return null; }
  }
  function remember(value) {
    try { window.localStorage.setItem(KEY, value); } catch (e) { /* private mode */ }
  }

  // Anything that is not the string "dark" is light, so a corrupted or
  // half-written value can only ever fail toward the default.
  function apply(theme) {
    root.setAttribute("data-theme", theme === "dark" ? "dark" : "light");
  }

  apply(stored());

  // The label names what the click DOES, which is the only thing anyone wants
  // from a control they will press at most once. The visible text is swapped
  // by CSS off [data-theme]; this is the accessible name, which CSS cannot
  // reach.
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
        remember(next);
        label(event.currentTarget);
      });
    }
  }

  // This script runs before <body> exists, so the buttons are not there yet.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }

  // The popup and the setup page can be open at the same time — the popup's
  // own footer links open onboarding.html in a tab. `storage` fires on every
  // OTHER same-origin document, so the two surfaces never disagree about
  // which theme this browser is in.
  window.addEventListener("storage", function (event) {
    if (event.key !== KEY) return;
    apply(event.newValue);
    var buttons = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < buttons.length; i++) label(buttons[i]);
  });
})();
