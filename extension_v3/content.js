/**
 * Anticipy Bridge — content script.
 *
 * Lives inside each tab the agent operates on. Pure DOM executor.
 * The server tells us what selector to click, what URL to navigate to,
 * what text to type. We do it. We never decide anything.
 *
 * Injected programmatically by background.js (chrome.scripting.executeScript)
 * so we don't need a content_scripts manifest entry.
 *
 * Idempotency guard: re-injection is harmless; we replace the listener.
 */
(() => {
  if (window.__anticipyBridgeContentLoaded) return;
  window.__anticipyBridgeContentLoaded = true;

  const MAX_TEXT_LEN = 200_000; // soft cap on extracted/snapshot text

  function $(selector) {
    // Trust any user-provided selector; server is the only sender.
    try { return document.querySelector(selector); } catch (_) { return null; }
  }

  function nodeOuter(node, limit = MAX_TEXT_LEN) {
    if (!node) return "";
    const html = node.outerHTML || "";
    return html.length > limit ? html.slice(0, limit) : html;
  }

  function visibleText(node, limit = MAX_TEXT_LEN) {
    if (!node) return "";
    const text = (node.innerText || node.textContent || "").trim();
    return text.length > limit ? text.slice(0, limit) : text;
  }

  async function actionNavigate(payload) {
    const url = payload.url;
    if (!url) throw new Error("navigate: missing url");
    window.location.href = url;
    return { navigatedTo: url };
  }

  async function actionClick(payload) {
    const el = $(payload.selector);
    if (!el) throw new Error(`click: selector not found: ${payload.selector}`);
    // Bring it into view in case of lazy rendering.
    el.scrollIntoView({ block: "center", inline: "center" });
    el.click();
    return { clicked: payload.selector };
  }

  async function actionType(payload) {
    const el = $(payload.selector);
    if (!el) throw new Error(`type: selector not found: ${payload.selector}`);
    el.focus();
    // Native value setter so React-controlled inputs notice.
    const proto = el instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
    if (setter) setter.call(el, payload.text || "");
    else el.value = payload.text || "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    if (payload.submit) {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
    }
    return { typed: (payload.text || "").length, selector: payload.selector };
  }

  async function actionExtract(payload) {
    const sel = payload.selector || "body";
    const el = $(sel);
    if (!el) throw new Error(`extract: selector not found: ${sel}`);
    return {
      selector: sel,
      text: visibleText(el),
      html: payload.includeHtml ? nodeOuter(el) : undefined,
    };
  }

  async function actionGetDOMSnapshot(payload) {
    const root = payload.selector ? $(payload.selector) : document.documentElement;
    if (!root) throw new Error("getDOMSnapshot: root not found");
    return {
      url: location.href,
      title: document.title,
      html: nodeOuter(root, payload.limit || MAX_TEXT_LEN),
    };
  }

  const handlers = {
    navigate: actionNavigate,
    click: actionClick,
    type: actionType,
    extract: actionExtract,
    getDOMSnapshot: actionGetDOMSnapshot,
  };

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    const fn = handlers[msg.type];
    if (!fn) {
      sendResponse({ ok: false, error: `unknown content action ${msg.type}` });
      return false;
    }
    Promise.resolve()
      .then(() => fn(msg.payload || {}))
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: String(err && err.message || err) }));
    return true; // async response
  });
})();
