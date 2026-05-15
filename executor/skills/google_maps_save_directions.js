// Google Maps — save a directions / route to "Saved" places. Replaces
// Uber in the Phase 6 list per correction #6 (2026-05-13). Reversible
// (unsave in compensate). No real-money risk.
//
// Implementation: navigate to the directions URL, click the "Save"
// button on the route panel. Verifier checks the saved-confirmation
// toast text; compensate clicks "Saved" then "Remove".

const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'google_maps_save_directions';

function buildRecipe(params) {
  // Format: https://www.google.com/maps/dir/<from>/<to>
  const from = encodeURIComponent(params.from || 'My Location');
  const to = encodeURIComponent(params.to);
  const url = `https://www.google.com/maps/dir/${from}/${to}`;
  return [
    { action: 'navigate', target_ref: null, value: url, timeout_ms: 15000 },
    { action: 'wait', target_ref: 'button[aria-label*="Directions"], button[aria-label*="directions"]', timeout_ms: 8000 },
    { action: 'click', target_ref: 'button[aria-label*="Save"], button[data-tooltip="Save"]', timeout_ms: 5000 },
    { action: 'wait', target_ref: '[role="status"], [aria-label*="Saved"]', timeout_ms: 5000 },
    { action: 'extract', target_ref: '[role="status"]', value: 'save_confirmation' },
  ];
}

function verify(world) {
  const result = world?.result;
  if (!result || result.steps_failed > 0) {
    return { verdict: NOT_VERIFIED, reason: `steps_failed=${result?.steps_failed}` };
  }
  const conf = result.evidence?.parsed_confirmations?.[0] || {};
  const sav = (conf.save_confirmation || '').toLowerCase();
  if (sav.includes('saved') || sav.includes('added to')) {
    return { verdict: VERIFIED, reason: 'save_confirmation_visible' };
  }
  return { verdict: NOT_VERIFIED, reason: `no_save_confirmation_text, got=${sav.slice(0, 40)}` };
}

async function compensate(/* world */) {
  // Compensation requires a follow-up nav to maps.google.com/maps/d/saved
  // and clicking Remove. The recipe-replay handles this in the executor;
  // we return true so the saga unwinder knows to invoke the unsave recipe.
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate };
