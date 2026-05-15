// Aevoy [ANTICIPY-Q] / [ANTICIPY-CONFIRM] email helpers — sends FROM
// aevoy@anticipy.ai (Resend) TO omarkebrahim@gmail.com per correction
// #5 (2026-05-13). Reply parsing via Gmail API watch is in a separate
// module (see lib/gmail_inbox.js) and not strictly required for the
// outbound path.

const axios = require('axios');

const RESEND_API = 'https://api.resend.com/emails';
const FROM = 'aevoy@anticipy.ai';

class AevoyEmailer {
  constructor({ apiKey, to } = {}) {
    if (!apiKey) throw new Error('RESEND_API_KEY required for AevoyEmailer');
    if (!to) throw new Error('TO email required for AevoyEmailer');
    this.apiKey = apiKey;
    this.to = to;
  }

  // Send a [ANTICIPY-Q] question email. Returns { id } on success.
  async sendQuestion({ topic, blockedOn, tried = [], questionId, asksFor }) {
    const subject = `[ANTICIPY-Q] ${topic}`;
    const body = [
      `Blocked on: ${blockedOn}`,
      '',
      'What I tried:',
      ...tried.map((t) => `- ${t}`),
      '',
      'What I need from you:',
      asksFor,
      '',
      `Question ID: ${questionId}`,
      `Sent: ${new Date().toISOString()}`,
    ].join('\n');
    return this._send(subject, body);
  }

  // Send a [ANTICIPY-CONFIRM] action confirmation email. Used by the
  // policy.AEVOY_CONFIRM path BEFORE executing irreversible / financial
  // actions.
  async sendConfirm({ topic, action, summary, taskId }) {
    const subject = `[ANTICIPY-CONFIRM] ${topic}`;
    const body = [
      `Proposed action: ${action}`,
      '',
      summary,
      '',
      `Task ID: ${taskId}`,
      `Sent: ${new Date().toISOString()}`,
      '',
      'Reply "approve" or "deny".',
    ].join('\n');
    return this._send(subject, body);
  }

  // Send a final outcome notification (after a Task finishes, success
  // or failure).
  async sendOutcome({ topic, status, summary, taskId }) {
    const subject = `[ANTICIPY-${status === 'executed' ? 'DONE' : 'FAILED'}] ${topic}`;
    const body = [summary, '', `Task ID: ${taskId}`].join('\n');
    return this._send(subject, body);
  }

  async _send(subject, text) {
    const r = await axios.post(
      RESEND_API,
      { from: FROM, to: this.to, subject, text },
      {
        headers: { Authorization: `Bearer ${this.apiKey}`, 'Content-Type': 'application/json' },
        timeout: 10000,
      }
    );
    return r.data;
  }
}

module.exports = { AevoyEmailer };
