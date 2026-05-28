// Google Sheets — write cell via Sheets v4 API. The canvas-fallback
// path lives in the executor and only fires for tasks the API can't
// express (e.g. visual chart placement).

const axios = require('axios');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'google_sheets_write_cell';

function buildRecipe(params) {
  return [
    {
      action: 'evaluate',
      target_ref: '__sheets_write__',
      value: JSON.stringify({
        spreadsheetId: params.spreadsheetId,
        range: params.range,           // e.g. "Sheet1!A1"
        value: params.value,
      }),
      timeout_ms: 10000,
    },
  ];
}

async function callWrite(accessToken, spreadsheetId, range, value) {
  const r = await axios.put(
    `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(spreadsheetId)}/values/${encodeURIComponent(range)}?valueInputOption=USER_ENTERED`,
    { range, values: [[value]] },
    { headers: { Authorization: `Bearer ${accessToken}` }, timeout: 10000 }
  );
  return r.data;
}

async function callRead(accessToken, spreadsheetId, range) {
  const r = await axios.get(
    `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(spreadsheetId)}/values/${encodeURIComponent(range)}`,
    { headers: { Authorization: `Bearer ${accessToken}` }, timeout: 10000 }
  );
  return r.data;
}

async function callClear(accessToken, spreadsheetId, range) {
  const r = await axios.post(
    `https://sheets.googleapis.com/v4/spreadsheets/${encodeURIComponent(spreadsheetId)}/values/${encodeURIComponent(range)}:clear`,
    {},
    { headers: { Authorization: `Bearer ${accessToken}` }, timeout: 10000 }
  );
  return r.data;
}

function verify(world) {
  const written = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!written) return { verdict: NOT_VERIFIED, reason: 'no_confirmation' };
  if (!written.updatedRange) return { verdict: NOT_VERIFIED, reason: 'no_updatedRange' };
  if (typeof written.updatedCells !== 'number' || written.updatedCells < 1) {
    return { verdict: NOT_VERIFIED, reason: 'no_cells_updated' };
  }
  return { verdict: VERIFIED, reason: 'cell_written', range: written.updatedRange };
}

async function compensate(world) {
  const written = world?.result?.evidence?.parsed_confirmations?.[0];
  if (!written?.updatedRange) return true;
  const accessToken = world?.accessToken;
  const spreadsheetId = world?.spreadsheetId;
  if (!accessToken || !spreadsheetId) return false;
  await callClear(accessToken, spreadsheetId, written.updatedRange);
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, callWrite, callRead, callClear };
