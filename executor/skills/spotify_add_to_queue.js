// Spotify — add track to playback queue. Reversible (skip past it).

const axios = require('axios');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'spotify_add_to_queue';

function buildRecipe(params) {
  return [
    {
      action: 'evaluate',
      target_ref: '__spotify_queue__',
      value: JSON.stringify({ trackUri: params.trackUri }),
      timeout_ms: 10000,
    },
  ];
}

async function callAddToQueue(token, trackUri, deviceId = null) {
  const url = new URL('https://api.spotify.com/v1/me/player/queue');
  url.searchParams.set('uri', trackUri);
  if (deviceId) url.searchParams.set('device_id', deviceId);
  const r = await axios.post(
    url.toString(),
    null,
    { headers: { Authorization: `Bearer ${token}` }, timeout: 10000 }
  );
  return { status: r.status, trackUri };
}

async function callNextTrack(token) {
  const r = await axios.post(
    'https://api.spotify.com/v1/me/player/next',
    null,
    { headers: { Authorization: `Bearer ${token}` }, timeout: 10000 }
  );
  return r.status;
}

function verify(world) {
  const queued = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!queued) return { verdict: NOT_VERIFIED, reason: 'no_confirmation' };
  if (queued.status !== 204 && queued.status !== 200) {
    return { verdict: NOT_VERIFIED, reason: `unexpected_status:${queued.status}` };
  }
  if (!queued.trackUri) return { verdict: NOT_VERIFIED, reason: 'no_track_uri' };
  return { verdict: VERIFIED, reason: 'queued', trackUri: queued.trackUri };
}

async function compensate(world) {
  // Compensation = skip past the queued item (closest reversal Spotify exposes)
  const token = world?.token;
  if (!token) return true;
  await callNextTrack(token);
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, callAddToQueue, callNextTrack };
