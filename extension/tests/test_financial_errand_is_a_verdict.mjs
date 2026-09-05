// WHETHER AN ERRAND IS SOMEONE'S BANK ACCOUNT IS NOT TWO WORD LISTS.
//
// Audit #F36. Until 2026-09-05 runAgentGoal refused an errand outright, before
// any tab opened, when its GOAL WORDING matched BOTH of:
//
//     /\b(bank(ing)?|brokerage|credit\s*card|crypto\s*(exchange|wallet))\b/i
//     /\b(log\s*in|sign\s*in|password|statements?|transfers?|balance|accounts?)\b/i
//
// The audit filed this as a NOTE and offered two resolutions, the cheaper being
// "file it in the law-1 ledger as LEGAL — seatbelt-with-cost, recording the two
// measured false refusals". Measuring it before writing that entry is what
// changed the disposition: on ten realistic errands it refuses THREE it should
// run, and it FAILS OPEN on the one case it exists for. "Find my Chase balance
// and tell me" names a bank and asks for a balance, and contains no word from
// the first list, so it sailed straight through.
//
// WHAT REPLACED IT: nothing, and that is the finding.
//
// `BLOCKED_DOMAINS` already refuses chase.com and sixteen others at EVERY
// navigation. It is fail-closed, needs no model, and checks what the plan
// TOUCHES — precisely the seatbelt law 1 permits. A goal's WORDING is not what
// it touches. So the pre-check was a redundant optimiser in front of a correct
// guard: its benefit was skipping a wandering search on the two errands in ten
// it read correctly; its cost was refusing three outright.
//
// A model judge was built for this and then REMOVED. It fixed the accuracy and
// put one model call at the front of every browser run — latency and money on
// every errand — to save a wasted search on two in ten, in front of a guard
// that would refuse them anyway. This suite exists so that trade stays written
// down and nobody re-adds either half without re-reading it.
//
// Run: node extension/tests/test_financial_errand_is_a_verdict.mjs
import { readFileSync } from "node:fs";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// The two lists exactly as they were. This is the ONLY place they still exist,
// kept so the deleted behaviour stays measurable rather than remembered.
const OLD_A = /\b(bank(ing)?|brokerage|credit\s*card|crypto\s*(exchange|wallet))\b/i;
const OLD_B = /\b(log\s*in|sign\s*in|password|statements?|transfers?|balance|accounts?)\b/i;
const oldWouldRefuse = (goal) => OLD_A.test(goal) && OLD_B.test(goal);

// [errand, is it actually operating a financial account]
const CASES = [
  ["Update the bank account on my payroll portal", false],
  ["Log in to the gym site and cancel my membership", false],
  ["Find my Chase balance and tell me", true],
  ["Log into the bank and download my statements", true],
  ["Email the accounts team the credit card receipt for the hotel", false],
  ["Check the balance on my Starbucks card", false],
  ["Sign in to the school portal and pay the trip fee", false],
  ["Transfer money from my brokerage to checking", true],
  ["Update my credit card on the Netflix account", false],
  ["Cancel the crypto wallet newsletter subscription", false],
];

const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

// ---------------------------------------------------------------------------
// (a) THE MEASUREMENT. This is the evidence the deletion rests on.
// ---------------------------------------------------------------------------
{
  const falseRefusals = CASES.filter(([g, real]) => !real && oldWouldRefuse(g));
  const missed = CASES.filter(([g, real]) => real && !oldWouldRefuse(g));
  const correct = CASES.filter(([g, real]) => real && oldWouldRefuse(g));

  check("(a) the word lists refused three errands they should have run",
    falseRefusals.length === 3, falseRefusals.map(([g]) => g).join(" | "));
  check("(a) ...and read only two of the three real ones correctly",
    correct.length === 2, correct.map(([g]) => g).join(" | "));
  check("(a) ...and FAILED OPEN on the remaining one",
    missed.length === 1 && /Chase/.test(missed[0][0]), missed.map(([g]) => g).join(" | "));
  check("(a) ...because a named bank carries no word from the institution list",
    !OLD_A.test("Find my Chase balance and tell me"));
  check("(a) so it stopped more errands than it caught",
    falseRefusals.length > correct.length,
    `${falseRefusals.length} wrong refusals vs ${correct.length} right ones`);
}

// ---------------------------------------------------------------------------
// (b) THE GUARD THAT WAS ALWAYS DOING THE REAL WORK still stands, and covers
//     every case the deleted check claimed — including the one it missed.
// ---------------------------------------------------------------------------
{
  const list = (code.match(/const BLOCKED_DOMAINS = \[([\s\S]*?)\];/) || [])[1] || "";
  const domains = [...list.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  check("(b) BLOCKED_DOMAINS still exists and is not empty", domains.length >= 15,
    `${domains.length} domains`);
  check("(b) it covers the bank the word lists waved through",
    domains.includes("chase.com"));
  for (const d of ["wellsfargo.com", "schwab.com", "coinbase.com", "paypal.com"]) {
    check(`(b) ...and ${d}`, domains.includes(d));
  }
  check("(b) it is matched on the HOST of a navigation, not on the goal's words",
    /const host = new URL\(url\)\.hostname;/.test(code)
      && /BLOCKED_DOMAINS\.find\(\(d\) => host === d \|\| host\.endsWith\("\." \+ d\)\)/.test(code));
  check("(b) a subdomain of a blocked host is blocked too",
    /host\.endsWith\("\." \+ d\)/.test(code));
}

// ---------------------------------------------------------------------------
// (c) THE LAW LEG. Neither half comes back — not the word lists, not a judge
//     at the front of every run.
// ---------------------------------------------------------------------------
{
  check("(c) law 1: the institution word list is gone from the code",
    !/bank\(ing\)\?\|brokerage/.test(code), "still present");
  check("(c) law 1: the operation word list is gone from the code",
    !/log\\s\*in\|sign\\s\*in\|password\|statements\?/.test(code), "still present");
  check("(c) the goal is no longer tested against either list anywhere",
    !/test\(goal\)\s*\n?\s*&&\s*\/\\b\(log/.test(code));
  check("(c) and no judge was put at the front of every run in their place",
    !/financialErrandJudge/.test(code),
    "a per-run model call is the cost this deletion exists to avoid");
  check("(c) no tape marker was added for this audit",
    !code.includes("TA" + "PE:"));
}

// ---------------------------------------------------------------------------
// (d) THE RECORD. The trade is written where the next reader will find it.
// ---------------------------------------------------------------------------
{
  const note = src.slice(src.indexOf("THE FINANCIAL-ERRAND PRE-CHECK IS GONE"),
                         src.indexOf("A parked run's tab IS its state"));
  check("(d) the deleted predicates are written out", /brokerage/.test(note));
  check("(d) the three false refusals are named", /payroll portal/.test(note)
    && /accounts team/.test(note) && /Netflix/.test(note));
  check("(d) the fail-open case is named", /Chase/.test(note));
  check("(d) it says why BLOCKED_DOMAINS is the real guard",
    /fail-closed/.test(note) && /TOUCHES/.test(note));
  check("(d) it records that a judge was built and rejected, and why",
    /judge/.test(note) && /every browser run/i.test(note));
  check("(d) it states the cost of the deletion rather than hiding it",
    /WHAT THIS COSTS/.test(note) && /burns a few model steps/.test(note));
}

console.log(failures === 0
  ? "test_financial_errand_is_a_verdict: the wording check is gone; the touch guard stands"
  : `test_financial_errand_is_a_verdict: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
