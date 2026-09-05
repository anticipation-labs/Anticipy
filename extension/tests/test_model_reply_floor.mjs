// THE FLOOR UNDER EVERY MODEL REPLY IS BIG ENOUGH FOR A MODEL THAT THINKS.
//
// 2026-09-05, audit #70's live leg: at a 64-token floor the browser model
// (a thinking model; its reasoning counts against max_tokens) answered the
// one-token wall question with `PAY`, `SS`, `SSO` and nothing — 15 of 22
// pages cut off before the visible answer. A cut-off reply is a NO-VERDICT,
// so every CEILING judge stopped fencing and every FLOOR judge refused
// everything, while the offline suites — whose stubs answer in one token —
// stayed green. At 512 the same pages read 66/66.
//
// This suite pins the floor by driving the real modelFetch and reading the
// bytes on the wire. It cannot prove 512 is enough for the live model — the
// live leg (overnight/login_wall_gate.py) does that — but it can make sure
// nobody quietly puts the number back.
//
// Run: node extension/tests/test_model_reply_floor.mjs
import { installChrome } from "./chrome_mock.mjs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

installChrome();
const { modelFetch, MODEL_REPLY_FLOOR } = await import("../agent_loop.js");

const sent = [];
globalThis.fetch = async (url, opts = {}) => {
  sent.push(JSON.parse(opts.body));
  return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: "YES" } }] }), text: async () => "" };
};
const wire = async (payload) => {
  sent.length = 0;
  await modelFetch("test-key", { model: "m", messages: [{ role: "user", content: "?" }], ...payload });
  return Number(sent[0]?.max_tokens);
};

check("the floor is at least what the live measurement needed (512)", MODEL_REPLY_FLOOR >= 512, String(MODEL_REPLY_FLOOR));
check("a judge asking for 8 tokens gets the floor on the wire", await wire({ max_tokens: 8 }) === MODEL_REPLY_FLOOR, String(sent[0]?.max_tokens));
check("...and so does one asking for 64, the old floor", await wire({ max_tokens: 64 }) === MODEL_REPLY_FLOOR, String(sent[0]?.max_tokens));
check("a caller that asks for nothing gets the floor", await wire({}) === MODEL_REPLY_FLOOR, String(sent[0]?.max_tokens));
check("a caller that asks for more than the floor is not cut down to it", await wire({ max_tokens: 1024 }) === 1024, String(sent[0]?.max_tokens));
check("the ceiling still holds", await wire({ max_tokens: 90000 }) === 4096, String(sent[0]?.max_tokens));
check("garbage asks get the floor, not NaN", await wire({ max_tokens: "lots" }) === MODEL_REPLY_FLOOR, String(sent[0]?.max_tokens));

if (failures) { console.error(`test_model_reply_floor: ${failures} failed`); process.exit(1); }
console.log("test_model_reply_floor: all passed");
