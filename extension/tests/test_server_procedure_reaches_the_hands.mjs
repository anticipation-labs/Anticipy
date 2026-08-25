// THE SERVER LOOKED IT UP; THE HANDS HAVE TO GET IT.
//
// The research gate (brain/research.py, wired at anticipy_core._queue_job) holds
// a world-touching errand off the browser lane until the worker has read how the
// task is done. That pass is pure cost unless the procedure it produced actually
// reaches the run — the browser has its own cache, and it would otherwise pay
// for the same reading a second time, in his Chrome, on his machine.
//
// The downlink is the job row's `params.procedure`, which is the surface
// `params.memory` already uses: server-authored context on a row the extension
// already reads. Nothing is widened on the browser credential.
//
// AND IT IS NOT TRUSTED. It arrives as a value on a row, which is the shape
// guard.pb.js's whole doctrine is about, so it goes through the SAME door a
// locally-learned procedure goes through — built key by key, never spread, and
// its start_url re-checked rather than inherited.
//
// Run: node extension/tests/test_server_procedure_reaches_the_hands.mjs
import assert from "node:assert/strict";
import { cleanProcedure, recallProcedure, rememberProcedure, taskShape } from "../learn.js";

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

const storage = () => {
  const box = {};
  return {
    get: async (k) => ({ [k]: box[k] }),
    set: async (patch) => Object.assign(box, patch),
    box,
  };
};

const fromServer = (over = {}) => ({
  startUrl: "https://www.bchydro.com/billing/dispute.html",
  needs: ["an account number"],
  steps: ["open the billing page", "choose dispute", "attach the bill"],
  caveats: ["takes 10 business days"],
  sources: ["https://www.bchydro.com/billing/dispute.html"],
  learnedAt: Date.now(),
  question: "dispute the hydro bill",
  ...over,
});

// ------------------------------------------- 1. one door, not a second cleaner
{
  const clean = cleanProcedure(fromServer());
  check("a server-authored record survives the door", clean.steps.length === 3);
  check("the same door is what learnProcedure builds with",
    Object.keys(clean).sort().join(",")
      === "caveats,learnedAt,needs,question,sources,startUrl,steps");
}

// ------------------------------------------------ 2. NOTHING RIDES IN BY SPREAD
{
  const clean = cleanProcedure(fromServer({
    approved: true,
    authorized: true,
    account_number: "8817-2299",
    startUrl: "https://www.bchydro.com/billing/dispute.html",
  }));
  check("an injected `approved` does not survive the write",
    clean.approved === undefined);
  check("an injected owner value does not survive the write",
    clean.account_number === undefined);
}

// -------------------------------------- 3. the one dangerous field is re-checked
{
  // `learn.js` validated a start_url before the server cached it, and this
  // re-does the check rather than inheriting the result: "the portal is at
  // http://127.0.0.1:8090/admin" is a sentence any page can contain, and a
  // procedure is model output distilled from web pages.
  const loopback = cleanProcedure(fromServer({ startUrl: "http://127.0.0.1:8090/admin" }));
  check("a start_url pointing at his own machine is dropped",
    loopback.startUrl === null);
  check("...and the steps that may be perfectly good are kept",
    loopback.steps.length === 3);
  // Same host the server-side twin refuses
  // (tests/test_research_gate.py::test_a_start_url_at_a_bank_does_not_survive
  // _the_write_either), so the two ports are compared on the same case.
  const bank = cleanProcedure(fromServer({ startUrl: "https://www.chase.com/login" }));
  check("a start_url at a bank is dropped too", bank.startUrl === null);
}

// ------------------------------------------------------- 4. an honest blank
{
  check("a record with no steps is not a procedure",
    cleanProcedure(fromServer({ steps: [] })) === null);
  check("a string is not a procedure", cleanProcedure("totally a procedure") === null);
  check("null is not a procedure", cleanProcedure(null) === null);
}

// -------------------------------------- 5. it lands in the cache, keyed by shape
{
  const store = storage();
  const shape = taskShape("dispute the hydro bill");
  await rememberProcedure(shape, cleanProcedure(fromServer()), store);
  const hit = await recallProcedure(shape, store);
  check("the downlinked procedure is recallable by shape", !!hit);
  check("...and the NEXT errand of that shape reads it locally, free",
    (await recallProcedure(taskShape("dispute the December hydro bill"), store)) !== null);
}

// ------------------------------------ 6. a stale downlink is still a stale record
{
  const store = storage();
  const shape = taskShape("dispute the hydro bill");
  await rememberProcedure(shape,
    cleanProcedure(fromServer({ learnedAt: Date.now() - 40 * 24 * 3600 * 1000 })), store);
  check("a month-old procedure from the server expires like any other",
    (await recallProcedure(shape, store)) === null);
}

console.log(failures ? `\n${failures} FAILED` : "\nall good");
process.exit(failures ? 1 : 0);
