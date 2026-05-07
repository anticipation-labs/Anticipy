// MAIN-world patch — runs at document_start in every frame, before any page
// script. It coerces every Element.prototype.attachShadow call to mode:'open'
// so the Anticipy content script can pierce shadow trees uniformly.
//
// Generic; no per-site code. Idempotent.

(() => {
  try {
    if (window.__anticipy_shadow_open_installed__) return;
    window.__anticipy_shadow_open_installed__ = true;
    const orig = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function (init) {
      try {
        const opts = Object.assign({}, init || {}, { mode: "open" });
        return orig.call(this, opts);
      } catch (_) {
        return orig.call(this, init);
      }
    };
  } catch (_) {}
})();
