// Google Calendar — create event via API.
// Uses OAuth-issued bearer token from anticipy_google_tokens.

const axios = require('axios');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'google_calendar_create_event';

function buildRecipe(params) {
  return [
    {
      action: 'evaluate',
      target_ref: '__google_calendar_create__',
      value: JSON.stringify({
        summary: params.title,
        description: params.description || '',
        start: { dateTime: params.start_iso, timeZone: params.timeZone || 'UTC' },
        end: { dateTime: params.end_iso, timeZone: params.timeZone || 'UTC' },
        location: params.location || '',
        attendees: (params.attendees || []).map((email) => ({ email })),
      }),
      timeout_ms: 10000,
    },
  ];
}

async function callCreate(accessToken, calendarId, eventBody) {
  const r = await axios.post(
    `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events`,
    eventBody,
    { headers: { Authorization: `Bearer ${accessToken}` }, timeout: 10000 }
  );
  return r.data;
}

async function callDelete(accessToken, calendarId, eventId) {
  await axios.delete(
    `https://www.googleapis.com/calendar/v3/calendars/${encodeURIComponent(calendarId)}/events/${encodeURIComponent(eventId)}`,
    { headers: { Authorization: `Bearer ${accessToken}` }, timeout: 10000 }
  );
  return true;
}

function verify(world) {
  const created = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!created || !created.id) return { verdict: NOT_VERIFIED, reason: 'no_event_id_in_evidence' };
  if (!created.htmlLink || !/^https:\/\/(www\.)?google\.com\/calendar\//.test(created.htmlLink)) {
    return { verdict: NOT_VERIFIED, reason: 'no_calendar_link' };
  }
  if (!created.start?.dateTime) return { verdict: NOT_VERIFIED, reason: 'no_start_time' };
  return { verdict: VERIFIED, reason: 'event_created', eventId: created.id };
}

async function compensate(world) {
  const created = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!created?.id) return true;
  const accessToken = world?.accessToken;
  const calendarId = world?.calendarId || 'primary';
  if (!accessToken) return false;
  await callDelete(accessToken, calendarId, created.id);
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, callCreate, callDelete };
