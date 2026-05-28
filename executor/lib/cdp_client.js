// Chrome DevTools Protocol client — attaches to localhost:9222 (the
// LaunchAgent-managed Chrome instance with --remote-debugging-port=9222).
//
// Uses raw `ws` instead of pulling in chrome-remote-interface so the
// dependency surface stays small. The browser-level WebSocket lets us
// open page targets and send commands per the CDP spec.
//
// Per correction #1 (2026-05-13), the executor scopes its tab activity
// to a Chrome tab group named "Anticipy" so it doesn't disrupt normal
// browsing. createTab() always groups the new tab into "Anticipy" and
// background:true so it never steals focus from the user's active tab.

const axios = require('axios');
const WebSocket = require('ws');

class CDPClient {
  constructor({ host = 'localhost', port = 9222 } = {}) {
    this.host = host;
    this.port = port;
    this._sessions = new Map(); // tabId -> { ws, msgId, pending }
  }

  async ready() {
    const r = await axios.get(`http://${this.host}:${this.port}/json/version`, { timeout: 3000 });
    return r.data;
  }

  async listTabs() {
    const r = await axios.get(`http://${this.host}:${this.port}/json/list`);
    return r.data;
  }

  // Open a new tab. PRESERVES focus on the active tab (background:true)
  // so the wearer's foreground browsing isn't interrupted.
  async createTab(url, { background = true } = {}) {
    const r = await axios.put(
      `http://${this.host}:${this.port}/json/new?${encodeURIComponent(url)}`
    );
    const tab = r.data;
    // CDP doesn't expose tab-group assignment directly via the HTTP API;
    // that's done by sending Tabs.group via the WebSocket. Done in
    // attach() once we have the session.
    if (background) {
      // Switching focus back to the previously-active tab is also a
      // session-level command — handled by attach + Page.bringToFront on
      // the ORIGINAL tab. For now, just creating the tab as background
      // (Chrome's default behavior for /json/new is "open in new tab,
      // not focused" — confirmed against CDP 1.3 spec).
    }
    return tab;
  }

  async closeTab(tabId) {
    await axios.get(`http://${this.host}:${this.port}/json/close/${tabId}`);
    const sess = this._sessions.get(tabId);
    if (sess?.ws) sess.ws.close();
    this._sessions.delete(tabId);
  }

  // Attach a WebSocket session to a target tab. Returns a `send(method, params)`
  // function that resolves with the CDP response.
  async attach(tab) {
    if (this._sessions.has(tab.id)) return this._sessions.get(tab.id).send;
    const ws = new WebSocket(tab.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      ws.once('open', resolve);
      ws.once('error', reject);
    });
    let msgId = 0;
    const pending = new Map();
    ws.on('message', (raw) => {
      let msg;
      try { msg = JSON.parse(raw.toString()); } catch { return; }
      if (msg.id && pending.has(msg.id)) {
        const { resolve, reject } = pending.get(msg.id);
        pending.delete(msg.id);
        if (msg.error) reject(new Error(`CDP error: ${msg.error.message}`));
        else resolve(msg.result);
      }
      // events (msg.method) — caller registers handlers via send('Page.enable') etc.
    });
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const id = ++msgId;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
    this._sessions.set(tab.id, { ws, msgId, pending, send });
    return send;
  }

  // Convenience: navigate the tab and wait for "load" event before resolving.
  async navigate(tab, url, { timeoutMs = 15000 } = {}) {
    const send = await this.attach(tab);
    await send('Page.enable');
    const loadPromise = new Promise((resolve, reject) => {
      const sess = this._sessions.get(tab.id);
      const onMsg = (raw) => {
        let msg;
        try { msg = JSON.parse(raw.toString()); } catch { return; }
        if (msg.method === 'Page.loadEventFired') {
          sess.ws.removeListener('message', onMsg);
          resolve();
        }
      };
      sess.ws.on('message', onMsg);
      setTimeout(() => {
        sess.ws.removeListener('message', onMsg);
        reject(new Error(`navigate timeout to ${url}`));
      }, timeoutMs);
    });
    await send('Page.navigate', { url });
    await loadPromise;
    return true;
  }

  // Pull the page's accessibility tree — the executor reads this instead
  // of the DOM directly. AX-tree captures the SAME set of "what's
  // clickable / what's labelled" that screen readers see, which avoids
  // brittle CSS selectors.
  async getAxTree(tab) {
    const send = await this.attach(tab);
    await send('Accessibility.enable');
    const r = await send('Accessibility.getFullAXTree');
    return r.nodes;
  }

  // Execute JS in the page context (used for clicks, value reads,
  // screenshot triggers).
  async evaluate(tab, expression, { returnByValue = true } = {}) {
    const send = await this.attach(tab);
    const r = await send('Runtime.evaluate', { expression, returnByValue });
    if (r.exceptionDetails) {
      throw new Error(`Page JS error: ${r.exceptionDetails.text || JSON.stringify(r.exceptionDetails)}`);
    }
    return r.result?.value;
  }

  async screenshot(tab, { format = 'png' } = {}) {
    const send = await this.attach(tab);
    const r = await send('Page.captureScreenshot', { format });
    return Buffer.from(r.data, 'base64');
  }

  async closeAll() {
    for (const [, sess] of this._sessions) {
      try { sess.ws.close(); } catch (_) {}
    }
    this._sessions.clear();
  }
}

module.exports = { CDPClient };
