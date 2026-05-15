// Gmail send — uses Google Gmail API with OAuth bearer token.

const axios = require('axios');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'gmail_send';

function buildRecipe(params) {
  return [
    {
      action: 'evaluate',
      target_ref: '__gmail_send__',
      value: JSON.stringify({
        to: params.to,
        subject: params.subject,
        body: params.body,
      }),
      timeout_ms: 10000,
    },
  ];
}

function rfc2822(message) {
  // Minimal RFC 2822 + base64url encode for the Gmail API.
  const lines = [
    `To: ${message.to}`,
    `Subject: ${message.subject}`,
    'Content-Type: text/plain; charset="UTF-8"',
    '',
    message.body,
  ];
  return Buffer.from(lines.join('\r\n'), 'utf-8')
    .toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function callSend(accessToken, message) {
  const raw = rfc2822(message);
  const r = await axios.post(
    'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
    { raw },
    { headers: { Authorization: `Bearer ${accessToken}` }, timeout: 10000 }
  );
  return r.data;
}

async function callTrash(accessToken, messageId) {
  const r = await axios.post(
    `https://gmail.googleapis.com/gmail/v1/users/me/messages/${encodeURIComponent(messageId)}/trash`,
    {},
    { headers: { Authorization: `Bearer ${accessToken}` }, timeout: 10000 }
  );
  return r.data;
}

function verify(world) {
  const sent = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!sent || !sent.id) return { verdict: NOT_VERIFIED, reason: 'no_message_id' };
  if (!Array.isArray(sent.labelIds) || !sent.labelIds.includes('SENT')) {
    return { verdict: NOT_VERIFIED, reason: 'message_not_labeled_SENT' };
  }
  return { verdict: VERIFIED, reason: 'message_sent', messageId: sent.id };
}

async function compensate(world) {
  const sent = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!sent?.id) return true;
  const accessToken = world?.accessToken;
  if (!accessToken) return false;
  await callTrash(accessToken, sent.id);
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, callSend, callTrash };
