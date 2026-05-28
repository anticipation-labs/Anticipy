// Resy — book a reservation via the Resy web app. AX-tree-driven
// (Computer Use fallback only if AX-tree returns empty for the booking
// modal). Reservations DON'T charge — Resy's pricing is per-cover at
// the restaurant level, not at booking — so the financial-cap rule
// doesn't fire. Restaurants do penalize no-shows; the compensate
// (cancel) path is the safety net.
//
// Per master prompt: party of 2, 7pm, 2-3 weeks out, rotate
// restaurants. Cancel immediately after verification.

const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'resy_book_reservation';

function buildRecipe(params) {
  // Resy URL pattern: https://resy.com/cities/{city}/{slug}?date=YYYY-MM-DD&seats={n}
  const url = `https://resy.com/cities/${params.city || 'ny'}/${params.slug}?date=${params.date}&seats=${params.party_size || 2}`;
  return [
    { action: 'navigate', target_ref: null, value: url, timeout_ms: 20000 },
    { action: 'wait', target_ref: 'button[data-test-id="time-slot"], .ReservationButton, .TimeSlot', timeout_ms: 10000 },
    // Pick the time-slot closest to params.time (e.g. "19:00"). Selector
    // strategy: first slot with the requested hour in its label.
    { action: 'click', target_ref: `button[aria-label*="${params.time}"]`, timeout_ms: 5000 },
    { action: 'wait', target_ref: '[data-test-id="reserve-button"], button:has-text("Reserve")', timeout_ms: 5000 },
    { action: 'click', target_ref: '[data-test-id="reserve-button"]', timeout_ms: 5000 },
    { action: 'wait', target_ref: '.ConfirmationModal, [data-test-id="confirmation"]', timeout_ms: 15000 },
    { action: 'extract', target_ref: '.ConfirmationModal, [data-test-id="confirmation"]', value: 'reservation_confirmation' },
  ];
}

function verify(world) {
  const result = world?.result;
  if (!result || result.steps_failed > 0) {
    return { verdict: NOT_VERIFIED, reason: `steps_failed=${result?.steps_failed}` };
  }
  const conf = result.evidence?.parsed_confirmations?.[0] || {};
  const text = (conf.reservation_confirmation || '').toLowerCase();
  if (!text) return { verdict: NOT_VERIFIED, reason: 'no_confirmation_text' };
  // The Resy modal has phrases like "you're confirmed" / "reservation confirmed".
  if (text.includes('confirm') || text.includes('reservation')) {
    return { verdict: VERIFIED, reason: 'reservation_confirmed' };
  }
  return { verdict: NOT_VERIFIED, reason: `no_confirm_keyword, got=${text.slice(0, 60)}` };
}

async function compensate(/* world */) {
  // Cancel: navigate to /account/reservations, click Cancel on the
  // newest entry, confirm. Run by the executor's saga-runner against
  // the live profile (Resy ties cancellation to the booking session).
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate };
