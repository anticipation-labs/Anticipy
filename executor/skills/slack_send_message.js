// Slack send message — uses Slack Web API with bot token.

const axios = require('axios');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'slack_send_message';

function buildRecipe(params) {
  return [
    {
      action: 'evaluate',
      target_ref: '__slack_post__',
      value: JSON.stringify({
        channel: params.channel,
        text: params.text,
      }),
      timeout_ms: 10000,
    },
  ];
}

async function callPost(token, channel, text) {
  const r = await axios.post(
    'https://slack.com/api/chat.postMessage',
    { channel, text },
    { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, timeout: 10000 }
  );
  if (!r.data.ok) throw new Error(`slack: ${r.data.error}`);
  return r.data;
}

async function callDelete(token, channel, ts) {
  const r = await axios.post(
    'https://slack.com/api/chat.delete',
    { channel, ts },
    { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, timeout: 10000 }
  );
  if (!r.data.ok) throw new Error(`slack delete: ${r.data.error}`);
  return r.data;
}

function verify(world) {
  const sent = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!sent || !sent.ok) return { verdict: NOT_VERIFIED, reason: 'slack_response_not_ok' };
  if (!sent.ts) return { verdict: NOT_VERIFIED, reason: 'no_ts_in_response' };
  if (!sent.channel) return { verdict: NOT_VERIFIED, reason: 'no_channel_in_response' };
  return { verdict: VERIFIED, reason: 'message_posted', ts: sent.ts };
}

async function compensate(world) {
  const sent = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!sent?.ts || !sent?.channel) return true;
  const token = world?.token;
  if (!token) return false;
  await callDelete(token, sent.channel, sent.ts);
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, callPost, callDelete };
