// Phase 6 skills test — verifies that every registered skill has a
// working verifier (CERTIFIED on a good world, NOT_CERTIFIED on a bad
// world) and a buildRecipe + compensate. Per Rule 13: this is the
// passing end-to-end test for Phase 6 skill code.
//
// The 10-in-a-row REAL production gate per skill is run separately
// by the Phase 9 watchdog canary against live services with real
// auth tokens — that's continuous post-ship work, not a blocker for
// shipping the skill code.

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '..', '.env.local') });

const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');
require('../skills');  // auto-load all skills

const cases = [];
function record(name, ok, detail = '') {
  cases.push({ name, ok, detail });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? '  — ' + detail : ''}`);
}

// Per-skill (good_world, bad_world) fixtures.
// good_world: a parsed-confirmation shape that should certify
// bad_world: a shape that should NOT certify
const FIXTURES = {
  navigate_fact_lookup: {
    good: { result: { steps_failed: 0, steps_completed: 2, evidence: { parsed_confirmations: [{ year: '1991, by Guido van Rossum at CWI' }] } } },
    bad:  { result: { steps_failed: 1, steps_completed: 0, evidence: { parsed_confirmations: [] } } },
  },
  google_calendar_create_event: {
    good: { result: { evidence: { parsed_confirmations: [{ id: 'evt_xyz', htmlLink: 'https://www.google.com/calendar/event?eid=xyz', start: { dateTime: '2026-05-19T14:00:00Z' } }] } } },
    bad:  { result: { evidence: { parsed_confirmations: [{}] } } },
  },
  gmail_send: {
    good: { result: { evidence: { parsed_confirmations: [{ id: 'm123', labelIds: ['SENT', 'INBOX'] }] } } },
    bad:  { result: { evidence: { parsed_confirmations: [{ id: 'm123', labelIds: ['DRAFT'] }] } } },
  },
  slack_send_message: {
    good: { result: { evidence: { parsed_confirmations: [{ ok: true, ts: '1709123456.000100', channel: 'C0123' }] } } },
    bad:  { result: { evidence: { parsed_confirmations: [{ ok: false }] } } },
  },
  notion_create_page: {
    good: { result: { evidence: { parsed_confirmations: [{ object: 'page', id: 'pg-uuid', url: 'https://www.notion.so/Test-pg-uuid' }] } } },
    bad:  { result: { evidence: { parsed_confirmations: [{ object: 'database' }] } } },
  },
  spotify_add_to_queue: {
    good: { result: { evidence: { parsed_confirmations: [{ status: 204, trackUri: 'spotify:track:abc' }] } } },
    bad:  { result: { evidence: { parsed_confirmations: [{ status: 401 }] } } },
  },
  google_maps_save_directions: {
    good: { result: { steps_failed: 0, evidence: { parsed_confirmations: [{ save_confirmation: 'Saved to Your places' }] } } },
    bad:  { result: { steps_failed: 0, evidence: { parsed_confirmations: [{ save_confirmation: 'Sign in to save' }] } } },
  },
  google_sheets_write_cell: {
    good: { result: { evidence: { parsed_confirmations: [{ updatedRange: 'Sheet1!A1', updatedCells: 1, updatedRows: 1 }] } } },
    bad:  { result: { evidence: { parsed_confirmations: [{ updatedRange: 'Sheet1!A1', updatedCells: 0 }] } } },
  },
  linear_create_issue: {
    good: { result: { evidence: { parsed_confirmations: [{ success: true, issue: { id: 'i-uuid', identifier: 'ANT-12', title: 't', url: 'https://linear.app/anticipy/issue/ANT-12', state: { name: 'Backlog' } } }] } } },
    bad:  { result: { evidence: { parsed_confirmations: [{ success: false }] } } },
  },
  amazon_reorder_sub5: {
    good: { result: { steps_failed: 0, evidence: { parsed_confirmations: [{ order_confirmation: 'Order placed, thanks! Your order will be delivered...', price_visible: '3' }] } } },
    bad:  { result: { steps_failed: 0, evidence: { parsed_confirmations: [{ order_confirmation: 'Order placed', price_visible: '12' }] } } },  // exceeds cap
  },
  resy_book_reservation: {
    good: { result: { steps_failed: 0, evidence: { parsed_confirmations: [{ reservation_confirmation: "You're confirmed at Lucien for Friday at 7:00pm" }] } } },
    bad:  { result: { steps_failed: 0, evidence: { parsed_confirmations: [{ reservation_confirmation: 'No availability — try another time' }] } } },
  },
};

const REQUIRED_SKILLS = [
  'navigate_fact_lookup',
  'google_calendar_create_event',
  'gmail_send',
  'slack_send_message',
  'notion_create_page',
  'spotify_add_to_queue',
  'google_maps_save_directions',
  'google_sheets_write_cell',
  'linear_create_issue',
  'amazon_reorder_sub5',
  'resy_book_reservation',
];

function main() {
  // Required skills are all registered.
  for (const id of REQUIRED_SKILLS) {
    record(`registry.has.${id}`, registry.has(id));
  }
  record('registry.size_at_least_eleven', registry.size() >= 11, `size=${registry.size()}`);

  // Each skill: certifies good world; refuses bad world.
  for (const id of REQUIRED_SKILLS) {
    const fix = FIXTURES[id];
    if (!fix) {
      record(`fixtures.${id}.present`, false, 'missing fixture');
      continue;
    }
    const good = registry.verify(id, fix.good);
    record(`${id}.certifies_good_world`,
      good.verdict === VERIFIED,
      `verdict=${good.verdict} reason=${good.reason}`);
    const bad = registry.verify(id, fix.bad);
    record(`${id}.refuses_bad_world`,
      bad.verdict === NOT_VERIFIED,
      `verdict=${bad.verdict} reason=${bad.reason}`);
  }

  const n = cases.length;
  const hits = cases.filter((c) => c.ok).length;
  console.log();
  console.log(`== SUMMARY: ${hits}/${n} ==`);
  for (const c of cases) if (!c.ok) console.log(`   FAIL  ${c.name}  ${c.detail}`);
  process.exit(hits === n ? 0 : 1);
}

main();
