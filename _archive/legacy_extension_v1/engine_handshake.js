// Anticipy Chrome Extension — engine page handshake
// Tiny content script that announces "the extension is here" to /engine so
// the page can hide the install CTA and skip the "extension isn't running"
// fallback toast. Runs only on anticipy.ai/engine* per manifest matches.
//
// Pattern: postMessage to the page world. The page's window.onmessage
// listener (src/app/engine/page.tsx) flips extensionDetected on receipt.

(function () {
  try {
    // Set a global tag the page can also read synchronously.
    // (Note: ISOLATED world cannot mutate page-world globals directly;
    // postMessage is the contract.)
    window.postMessage(
      { source: "anticipy_ext", type: "present", version: "2.0.0" },
      window.location.origin
    );
    // Re-announce a couple of times in case the page mounted late.
    setTimeout(() => {
      try {
        window.postMessage(
          { source: "anticipy_ext", type: "present", version: "2.0.0" },
          window.location.origin
        );
      } catch (_) {}
    }, 800);
    setTimeout(() => {
      try {
        window.postMessage(
          { source: "anticipy_ext", type: "present", version: "2.0.0" },
          window.location.origin
        );
      } catch (_) {}
    }, 2500);
  } catch (_) {
    // Extension context may be invalidated — silent ignore.
  }
})();
