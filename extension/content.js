// Anticipy content script — injects extension ID into the page so the frontend
// can discover and communicate with the extension directly via externally_connectable.
// Runs on Vercel and localhost pages.
(function() {
  const el = document.createElement("div");
  el.id = "anticipy-ext-id";
  el.dataset.id = chrome.runtime.id;
  el.style.display = "none";
  document.documentElement.appendChild(el);
})();
