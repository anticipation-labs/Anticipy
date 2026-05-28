/**
 * Anticipy v4 — content script.
 *
 * Pure DOM executor. Injected programmatically by background.js the first
 * time we need it in a tab. Idempotent — re-injection only re-registers
 * the listener.
 *
 * Marks `window.__anticipy_ext_installed__ = true` so the engine page can
 * detect the extension via window.postMessage handshake (matches v3
 * convention).
 */
(() => {
  if (window.__anticipyBridgeV4ContentLoaded) return;
  window.__anticipyBridgeV4ContentLoaded = true;
  window.__anticipy_ext_installed__ = true;

  const MAX_TEXT_LEN = 200_000;

  function $(sel) {
    try { return document.querySelector(sel); } catch (_) { return null; }
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

  async function actionNavigate(p) {
    if (!p.url) throw new Error("navigate: missing url");
    window.location.href = p.url;
    return { navigatedTo: p.url };
  }

  async function actionClick(p) {
    const el = $(p.selector);
    if (!el) throw new Error(`click: selector not found: ${p.selector}`);
    el.scrollIntoView({ block: "center", inline: "center" });
    el.click();
    return { clicked: p.selector };
  }

  async function actionType(p) {
    const el = $(p.selector);
    if (!el) throw new Error(`type: selector not found: ${p.selector}`);
    el.focus();
    const text = p.text == null ? "" : String(p.text);
    const shouldPreserveValue = p.submit && text === "";
    if (!shouldPreserveValue) {
      const proto = el instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) setter.call(el, text); else el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (p.submit) {
      el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", bubbles: true }));
      el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", bubbles: true }));
    }
    return {
      typed: shouldPreserveValue ? 0 : text.length,
      selector: p.selector,
      submitted: Boolean(p.submit),
      preservedValue: shouldPreserveValue,
    };
  }

  async function actionKey(p) {
    const key = String(p.key || "Enter");
    const selector = p.selector || "";
    const el = selector ? $(selector) : document.activeElement;
    if (!el) throw new Error(`key: selector not found: ${selector}`);
    if (typeof el.focus === "function") el.focus();
    const modifiers = Array.isArray(p.modifiers) ? p.modifiers.map(String) : [];
    const eventInit = {
      key,
      code: String(p.code || (key === "Enter" ? "Enter" : key)),
      bubbles: true,
      cancelable: true,
      altKey: modifiers.includes("Alt"),
      ctrlKey: modifiers.includes("Control") || modifiers.includes("Ctrl"),
      metaKey: modifiers.includes("Meta") || modifiers.includes("Command"),
      shiftKey: modifiers.includes("Shift"),
    };
    el.dispatchEvent(new KeyboardEvent("keydown", eventInit));
    el.dispatchEvent(new KeyboardEvent("keyup", eventInit));
    return {
      key,
      selector,
      activeTag: document.activeElement && document.activeElement.tagName,
    };
  }

  async function actionExtract(p) {
    const sel = p.selector || "body";
    const el = $(sel);
    if (!el) throw new Error(`extract: selector not found: ${sel}`);
    return {
      selector: sel,
      text: visibleText(el),
      html: p.includeHtml ? nodeOuter(el) : undefined,
    };
  }

  async function actionGetDOMSnapshot(p) {
    const root = p.selector ? $(p.selector) : document.documentElement;
    if (!root) throw new Error("getDOMSnapshot: root not found");
    return {
      url: location.href,
      title: document.title,
      html: nodeOuter(root, p.limit || MAX_TEXT_LEN),
    };
  }

  const handlers = {
    navigate: actionNavigate,
    click: actionClick,
    type: actionType,
    key: actionKey,
    read: actionExtract,
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
    return true;
  });

  // Page handshake — lets /engine know the extension is running.
  try {
    window.postMessage({ type: "anticipy:extension_present", version: "4.0.0" }, "*");
  } catch (_) {}
})();
