// Sandbox rehearsal — fork user's Chrome profile to a temp dir with
// read-only cookies, run the trajectory there, gate commit-to-live on
// the verifier's CERTIFIED verdict.
//
// Per master prompt L6: only used for NOVEL paths (skill_router miss).
// For known skills the rehearsal step is skipped — the verified
// trajectory in skill_library is replayed directly on the live profile.
//
// Key constraints:
//   - The user's main Chrome on :9222 keeps running. The sandbox uses
//     a SEPARATE profile dir + a different debug port (default :9223).
//   - Cookies are exported from the live profile via CDP
//     Network.getAllCookies (live Chrome must allow it; ours does
//     because we own :9222). Imported into the sandbox via
//     Network.setCookie. This avoids touching the live SQLite file.
//   - Sandbox is spawned with --no-first-run --no-default-browser-check
//     and a temp user-data-dir under /tmp/anticipy-sandbox-<uuid>.
//   - At end of run: kill the sandbox process, remove the temp dir.
//   - On commit, the executor re-runs the trajectory against the live
//     :9222 (not the sandbox).

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const { CDPClient } = require('./cdp_client');
const { SkillExecutor } = require('./skill_executor');

const CHROME_BIN = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

class SandboxRehearsal {
  constructor({ liveCdp, sandboxPort = 9223, chromeBin = CHROME_BIN } = {}) {
    this.liveCdp = liveCdp || new CDPClient({ port: 9222 });
    this.sandboxPort = sandboxPort;
    this.chromeBin = chromeBin;
    this._proc = null;
    this._tempDir = null;
    this._sandboxCdp = null;
  }

  // Start a fresh sandbox Chrome with cloned-by-CDP cookies. Returns a
  // CDPClient bound to the sandbox port.
  async start({ cookieDomains = null } = {}) {
    if (this._proc) throw new Error('sandbox already started');
    const id = crypto.randomBytes(6).toString('hex');
    this._tempDir = path.join(os.tmpdir(), `anticipy-sandbox-${id}`);
    fs.mkdirSync(this._tempDir, { recursive: true });

    // Spawn Chrome with sandbox profile + different port
    this._proc = spawn(
      this.chromeBin,
      [
        `--remote-debugging-port=${this.sandboxPort}`,
        `--user-data-dir=${this._tempDir}`,
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-features=Translate',
        '--password-store=basic',
        '--use-mock-keychain',
        '--no-startup-window',  // headless start, we open tabs explicitly
      ],
      { stdio: 'ignore', detached: false }
    );

    // Wait for the debug port to come up.
    this._sandboxCdp = new CDPClient({ port: this.sandboxPort });
    const startedAt = Date.now();
    while (Date.now() - startedAt < 8000) {
      try {
        await this._sandboxCdp.ready();
        break;
      } catch (_) {
        await new Promise((r) => setTimeout(r, 200));
      }
    }
    try {
      await this._sandboxCdp.ready();
    } catch (e) {
      throw new Error(`sandbox Chrome failed to start: ${e.message || e}`);
    }

    // Clone cookies from the LIVE profile. Open a synthetic page in the
    // sandbox first so Network domain can be enabled per-session.
    try {
      await this._cloneCookies(cookieDomains);
    } catch (e) {
      console.warn('[sandbox] cookie clone failed (continuing without cookies):', e.message || e);
    }

    return this._sandboxCdp;
  }

  // Pull all cookies from the live profile via CDP, write into the
  // sandbox via CDP. cookieDomains optionally filters to a subset
  // (e.g. ["resy.com", "gmail.com"]) to avoid copying everything.
  async _cloneCookies(cookieDomains) {
    // Live: open a generic page to attach a session and call Network.getAllCookies
    const liveTab = await this.liveCdp.createTab('about:blank', { background: true });
    let allCookies = [];
    try {
      const liveSend = await this.liveCdp.attach(liveTab);
      await liveSend('Network.enable');
      const r = await liveSend('Network.getAllCookies');
      allCookies = (r && r.cookies) || [];
    } finally {
      try { await this.liveCdp.closeTab(liveTab.id); } catch (_) {}
    }

    let cookiesToCopy = allCookies;
    if (Array.isArray(cookieDomains) && cookieDomains.length > 0) {
      cookiesToCopy = allCookies.filter((c) =>
        cookieDomains.some((d) => (c.domain || '').toLowerCase().endsWith(d.toLowerCase()))
      );
    }

    if (cookiesToCopy.length === 0) return;

    const sandboxTab = await this._sandboxCdp.createTab('about:blank');
    try {
      const sbSend = await this._sandboxCdp.attach(sandboxTab);
      await sbSend('Network.enable');
      for (const c of cookiesToCopy) {
        // Network.setCookie has its own arg shape — strip fields it
        // doesn't accept and tag the rest verbatim.
        await sbSend('Network.setCookie', {
          name: c.name,
          value: c.value,
          domain: c.domain,
          path: c.path || '/',
          secure: !!c.secure,
          httpOnly: !!c.httpOnly,
          sameSite: c.sameSite,
          expires: c.expires,
        }).catch(() => null);
      }
    } finally {
      try { await this._sandboxCdp.closeTab(sandboxTab.id); } catch (_) {}
    }
  }

  // Run a recipe in the sandbox; returns { result, verdict, evidence }.
  async rehearse({ task, registry }) {
    if (!this._sandboxCdp) throw new Error('sandbox not started');
    const sandboxExecutor = new SkillExecutor({ cdp: this._sandboxCdp, supabase: null });
    const result = await sandboxExecutor.run(task);
    let verdict = { verdict: 'NOT_CERTIFIED', reason: 'no_verifier' };
    if (registry && task.skill_id) {
      verdict = registry.verify(task.skill_id, {
        result,
        evidence: result.evidence,
        ranIn: 'sandbox',
      });
    } else if (registry) {
      // Fallback: certify if every step succeeded
      verdict = result.steps_failed === 0 && result.steps_completed > 0
        ? { verdict: 'CERTIFIED', reason: 'no_verifier_all_steps_passed' }
        : { verdict: 'NOT_CERTIFIED', reason: `steps_failed=${result.steps_failed}` };
    }
    return { result, verdict };
  }

  async stop() {
    try { await this._sandboxCdp?.closeAll(); } catch (_) {}
    try { if (this._proc && !this._proc.killed) this._proc.kill('SIGTERM'); } catch (_) {}
    // Wait briefly then SIGKILL if still alive.
    await new Promise((r) => setTimeout(r, 500));
    try { if (this._proc && !this._proc.killed) this._proc.kill('SIGKILL'); } catch (_) {}
    if (this._tempDir) {
      try { fs.rmSync(this._tempDir, { recursive: true, force: true }); } catch (_) {}
    }
    this._proc = null;
    this._tempDir = null;
    this._sandboxCdp = null;
  }
}

module.exports = { SandboxRehearsal };
