// He asked for a guarantee: nothing here is hard-coded to restaurant
// reservations. This test is that guarantee, enforced.
//
// The engine must never name a site, and its RULES must be about forms,
// pages and consent — not about dinner. Examples inside a prompt are
// allowed to be concrete, but they must not be the only shape a rule
// knows: a rule mentioning a booking must also cover the general case.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const files = ["agent_loop.js", "background.js", "page_map.js", "workflow_state.js"]
  .map((f) => [f, readFileSync(join(here, "..", f), "utf8")]);

// --- no site may be named, anywhere, in code OR prose ----------------------
const SITES = /opentable|sevenrooms|resy|tock\b|yelp|earls|cactus\s*club|doordash|ubereats|skipthedishes/i;
// Comments may name a site — they record real incidents, and that history
// is why these rules exist. CODE and PROMPT TEXT may not: that is where a
// name would actually steer behaviour.
for (const [name, src] of files) {
  const hits = src.split("\n")
    .map((l, i) => [i + 1, l])
    .filter(([, l]) => !/^\s*(\/\/|\*|\/\*)/.test(l))
    .filter(([, l]) => SITES.test(l));
  assert.equal(hits.length, 0,
    `${name} names a specific site: ${hits.slice(0, 3).map(([n, l]) => n + ": " + l.trim().slice(0, 80)).join(" | ")}`);
}

// --- no per-site branching ------------------------------------------------
const loop = files.find(([n]) => n === "agent_loop.js")[1];
assert.ok(!/hostname\s*===\s*["']/.test(loop),
  "no branch may switch on a specific hostname");
assert.ok(!/includes\(["'][a-z]+\.(com|ca)["']\)/i.test(loop),
  "no branch may test for a specific domain");

// --- the rules must be general ---------------------------------------------
// Every rule that mentions a booking must ALSO name non-booking work, so the
// engine is never taught that a task means a table.
const bookingRule = /Complete Reservation, Book, Confirm, Place order/;
assert.ok(bookingRule.test(loop),
  "the commit-button rule should list several kinds of commit, not one");
for (const general of ["application", "registration", "appointment", "order",
                       "request", "claim"]) {
  assert.ok(new RegExp(general, "i").test(loop),
    `the engine must know about ${general} work too, not only bookings`);
}

// --- the new rule about fetching a code is domain-free ---------------------
const fetchRule = loop.match(/WHEN THE THING YOU NEED WAS SENT SOMEWHERE[\s\S]{0,900}/)[0];
assert.ok(!/restaurant|booking|reservation|table/i.test(fetchRule),
  "the fetch-the-code rule must not be about dinner");
for (const word of ["code", "link", "document", "reference"]) {
  assert.ok(fetchRule.includes(word), `it must cover a ${word} too`);
}
assert.ok(/want me to open your inbox and read it, or will you paste it/.test(fetchRule),
  "it must offer BOTH options and then wait");
assert.ok(/Never open their mail without that answer/.test(fetchRule),
  "and never read their mail unasked");

console.log("test_no_domain_hardcoding: all passed");
