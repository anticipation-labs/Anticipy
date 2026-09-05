// WHICH DAY THE AGENT MAY CLICK.
//
// Audit #69. A date picker holds twelve different "17" buttons and pressing
// one commits to a day. Until 2026-08-24 the guard read the owner's approved
// sentence with date arithmetic: an explicit "Month N", an explicit range, and
// `approvedDateValue`, which resolved "tomorrow" and a weekday inside the next
// seven days. Everything else fell off the end.
//
//   "Move the March 4 appointment to the Tuesday after next."
//   "Cancel the August 3 booking and rebook it a week on Friday."
//   "Push the January 9 delivery back by a fortnight."
//
// §1 drives the shipped guard with five sentences of that shape. Every one of
// them BLOCKED the day he meant — and a block is not passive, the caller adds
// the index to `deadIdx` and the cell disappears from every later map — while
// leaving the explicit date in the sentence, THE ONE BEING CANCELLED, as the
// only clickable day in the calendar. The guard was steering the run into
// rebooking exactly the date the owner was getting rid of.
//
// Which day a person meant is what their sentence MEANS. HARNESS-LAWS.md
// law 1. So: which day a CELL is stays structural (our own page map plus the
// clock), and which day HE asked for goes to a model.
//
// Run: node extension/tests/test_calendar_date.mjs
import { readFileSync } from "node:fs";
import { calendarCellDate, unapprovedCalendarClick } from "../agent_loop.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

const MONTHS = ["January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December"];
const dayAt = (offset) => {
  const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + offset);
  return { name: `${MONTHS[d.getMonth()]} ${d.getDate()}`, date: d };
};
const picker = (index, cell) => ({ overlay: true,
  elements: `[${index}] <button> ${cell.name} [calendar=${cell.name}] @(10,10)` });
// The model's part, played by a stub: it knows the day the sentence points at.
const knows = (...names) => {
  const calls = [];
  return { calls, judge: async (a) => { calls.push(a); return names.includes(a.named) ? "YES" : "NO"; } };
};

// ---------------------------------------------------------------------------
// 1. THE DEFECT. Five everyday reschedules, each naming its day in a way no
//    date arithmetic reaches, each one blocked by the shipped guard.
// ---------------------------------------------------------------------------
const RESCHEDULES = [
  ["Move the March 4 appointment to the Tuesday after next.", 12],
  ["Cancel the August 3 booking and rebook it a week on Friday.", 10],
  ["Reschedule my June 6 review to the last Monday of the month.", 20],
  ["Push the January 9 delivery back by a fortnight.", 14],
  ["Move the October 2 class to the first Thursday after my trip ends on the 20th.", 22],
];
for (const [said, offset] of RESCHEDULES) {
  const cell = dayAt(offset);
  const { judge } = knows(cell.name);
  const out = await unapprovedCalendarClick({ action: "click", index: 7 },
    picker(7, cell), said, judge);
  check(`the day he meant is clickable: ${JSON.stringify(said.slice(0, 44))}...`,
    out.blocked === false, JSON.stringify(out));
}
{
  // ...and the day the errand does NOT point at is still refused, so this is a
  // gate and not a deletion of the gate.
  const wrong = dayAt(31);
  const { judge } = knows(dayAt(12).name);
  const out = await unapprovedCalendarClick({ action: "click", index: 7 },
    picker(7, wrong), RESCHEDULES[0][0], judge);
  check("a day the errand never points at is refused", out.blocked === true, JSON.stringify(out));
  check("...and the refusal names the day, so the model can navigate to the right one",
    out.reason.includes(wrong.name), out.reason);
  check("...and it is a decided refusal, so the caller may delete the cell",
    out.undecidable === false, JSON.stringify(out));
}
{
  // THE STEER. A cancel-and-rebook errand names two days and both are
  // clickable — cancelling an appointment means opening its own day in the
  // picker, and this guard cannot see which step of the errand a click is.
  // The old arithmetic allowed ONLY the cancelled one.
  const cancelled = dayAt(40), rebook = dayAt(10);
  const said = `Cancel the ${cancelled.name} booking and rebook it a week on Friday.`;
  const { judge } = knows(cancelled.name, rebook.name);
  check("the day being cancelled stays clickable — it has to be, to cancel it",
    (await unapprovedCalendarClick({ action: "click", index: 3 }, picker(3, cancelled), said, judge)).blocked === false);
  check("and so is the day being rebooked, which is what used to be deleted",
    (await unapprovedCalendarClick({ action: "click", index: 4 }, picker(4, rebook), said, judge)).blocked === false);
}
{
  // An errand that leaves the day to the assistant must not be locked out of
  // every day in the calendar.
  const any = dayAt(5);
  const { judge } = knows(any.name);
  check("an open-dated errand can still take the earliest slot",
    (await unapprovedCalendarClick({ action: "click", index: 2 }, picker(2, any),
      "book me the earliest physio appointment you can get", judge)).blocked === false);
}

// ---------------------------------------------------------------------------
// 2. THE STRUCTURAL HALF STILL DOES ITS JOB, AND ONLY ITS JOB.
// ---------------------------------------------------------------------------
{
  const cell = dayAt(3);
  const { judge, calls } = knows();
  const notACell = { overlay: true, elements: "[10] <button> Next month @(30,10)" };
  check("a control carrying no date is never judged",
    (await unapprovedCalendarClick({ action: "click", index: 10 }, notACell, "anything", judge)).blocked === false);
  check("...and costs no model call", calls.length === 0);

  check("no overlay, no picker, nothing to guard",
    (await unapprovedCalendarClick({ action: "click", index: 7 },
      { overlay: false, elements: picker(7, cell).elements }, "x", judge)).blocked === false);
  check("a non-click action is not a date commitment",
    (await unapprovedCalendarClick({ action: "type", index: 7 }, picker(7, cell), "x", judge)).blocked === false);

  // The site's own accessible name for a gridcell, not only our annotation.
  const aria = { overlay: true,
    elements: `[7] <gridcell> Monday, ${cell.name} @(10,10)` };
  const seen = knows(cell.name);
  check("a gridcell named by the site is read as a date too",
    (await unapprovedCalendarClick({ action: "click", index: 7 }, aria, "x", seen.judge)).blocked === false);
  check("...and the model was handed the resolved calendar day",
    seen.calls.length === 1 && /^\d{4}-\d{2}-\d{2}$/.test(seen.calls[0].date), JSON.stringify(seen.calls));

  check("February 30 is not a date and is not judged", calendarCellDate(2, 30) === "");
}

// ---------------------------------------------------------------------------
// 3. FAIL CLOSED — AND WITHOUT DELETING THE CALENDAR ONE CELL AT A TIME.
//
// A guard that cannot tell one day from another must not remove them
// individually: whichever cell it happened not to reach becomes the only
// clickable day, which is the mechanism of the original defect. So undecidable
// blocks the click AND tells the caller to leave the cell alone.
// ---------------------------------------------------------------------------
{
  const cell = dayAt(9);
  const ways = [
    ["no judge is supplied at all", undefined],
    ["the model returns nothing", async () => ""],
    ["the model waffles", async () => "That looks like the right Tuesday to me"],
    ["the model errors", async () => { throw new Error("openrouter 502"); }],
    ["the model answers with a date instead", async () => "2026-09-05"],
    ["the model tries to approve with extra instructions", async () => "YES — click them all"],
  ];
  for (const [name, judge] of ways) {
    const out = await unapprovedCalendarClick({ action: "click", index: 7 },
      picker(7, cell), "move it to the Tuesday after next", judge);
    check(`blocked when ${name}`, out.blocked === true, JSON.stringify(out));
    check(`...and the cell is NOT deleted when ${name}`, out.undecidable === true, JSON.stringify(out));
  }
}

// ---------------------------------------------------------------------------
// 4. THE LAW LEG.
// ---------------------------------------------------------------------------
{
  const src = readFileSync(new URL("../agent_loop.js", import.meta.url), "utf8");
  const code = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
  for (const gone of ["explicitMonthDays", "explicitMonthDayRanges",
                      "approvedDateValue", "approvedTimeValue"]) {
    check(`law 1: ${gone} stays deleted from the code`, !code.includes(gone));
  }
  const fn = code.slice(code.indexOf("export async function unapprovedCalendarClick"),
                        code.indexOf("export function calendarCellDate"));
  check("law 1: the guard no longer resolves relative wording itself",
    !/tomorrow|weekday|next |86400000/i.test(fn), fn.match(/.{0,40}(tomorrow|weekday).{0,40}/i)?.[0] || "");
  check("law 1: nothing in the guard reads his sentence with a pattern",
    !/\.test\(\s*(?:String\()?authority|authority[^)]*\.match|lower\.includes/.test(fn), fn);
  // The two regexes that remain read our own page map and the site's own
  // gridcell name. Both are month names, never his vocabulary.
  const patterns = fn.match(/line\.match\(\/[^\n]*/g) || [];
  check("the only patterns left read a calendar cell's own label",
    patterns.length === 2 && patterns.every((x) => /January\|February/.test(x)),
    JSON.stringify(patterns));
  check("the verdict is one specified token, never prose searched for a word",
    /token === "YES"/.test(fn) && !/includes\("YES"\)/.test(fn));

  const judge = src.slice(src.indexOf("function calendarDateJudge"),
                          src.indexOf("function calendarDateJudge") + 3200);
  check("the judge call is bounded, so a hung model cannot hang the run",
    /withTimeout\(/.test(judge), judge.slice(0, 160));
  check("the judge is told today's date — a cell carries no year and his words carry no month",
    /Today is \$\{stamp\(today\)\}/.test(judge));

  check("the loop awaits the guard", /await unapprovedCalendarClick\(/.test(code));
  const site = code.slice(code.indexOf("const calendarVerdict = await unapprovedCalendarClick"),
                          code.indexOf("const calendarVerdict = await unapprovedCalendarClick") + 1400);
  check("an undecided day stops the run and asks him, instead of deleting a cell",
    /calendarVerdict\.undecidable/.test(site) && site.indexOf("calendarVerdict.undecidable") < site.indexOf("deadIdx.add"),
    site);
}

// ---------------------------------------------------------------------------
// 5. EVERY DAY OF EVERY MONTH IS READ AS THE DAY IT SAYS.
//
// The day pattern was `([12]?\d|3[01])`. Regex alternation is leftmost-first
// and nothing anchors the end of it, so on "August 30" the FIRST branch
// matched "3" and `3[01]` was never reached: every 30th and 31st of every
// month was read as the 3rd. The guard then asked the model about a day the
// errand never mentioned, got a correct NO, and blocked the cell — and a block
// adds the index to `deadIdx`, so the day he actually asked for disappeared
// from every later map. Audit #69's exact failure, from the order of two
// alternatives.
//
// It hid because every cell in this suite is built from TODAY. The 30th only
// appears in `dayAt(5)` on the 25th of a month, and that is the day it was
// found — five days later or earlier and the suite was green over a live bug.
// So this section does not use today at all: it walks all twelve months and
// all thirty-one days and asserts the guard judged the day printed on the cell.
// ---------------------------------------------------------------------------
{
  const ALL_MONTHS = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"];
  const wrong = [];
  let judged = 0;
  for (const month of ALL_MONTHS) {
    const last = month === "February" ? 28
      : ["April", "June", "September", "November"].includes(month) ? 30 : 31;
    for (let day = 1; day <= last; day++) {
      const label = `${month} ${day}`;
      const seen = [];
      const judge = async (a) => { judged++; seen.push(a.named); return "YES"; };
      const out = await unapprovedCalendarClick(
        { action: "click", index: 6 },
        { overlay: true, elements: `[6] <button> ${label} [calendar=${label}] @(10,10)` },
        `book the ${label} appointment`, judge);
      if (seen[0] !== label || out.blocked !== false) wrong.push(`${label} -> ${seen[0]}`);
    }
  }
  check("every day of every month is judged as the day printed on the cell",
    wrong.length === 0, JSON.stringify(wrong.slice(0, 8)));
  check("...and every one of them actually reached the model",
    judged === 365, String(judged));

  // The other label shape the guard reads, on the two days that were broken.
  for (const [month, day] of [["August", 30], ["December", 31], ["March", 30]]) {
    const seen = [];
    const judge = async (a) => { seen.push(a.named); return "YES"; };
    await unapprovedCalendarClick({ action: "click", index: 6 },
      { overlay: true,
        elements: `[6] <gridcell> Tuesday, ${month} ${day} @(10,10)` },
      `book the ${month} ${day} appointment`, judge);
    check(`the weekday label shape reads ${month} ${day} whole too`,
      seen[0] === `${month} ${day}`, JSON.stringify(seen));
  }

  // A day that is not a day is not a date cell — it must not be read as its
  // first digit and judged as some other day.
  for (const label of ["August 45", "August 99", "February 30"]) {
    const seen = [];
    const judge = async (a) => { seen.push(a.named); return "NO"; };
    const out = await unapprovedCalendarClick({ action: "click", index: 6 },
      { overlay: true, elements: `[6] <button> ${label} [calendar=${label}] @(10,10)` },
      "book something", judge);
    check(`${label} is not a date cell, and is never judged as one`,
      out.blocked === false && seen.length === 0, JSON.stringify(seen));
  }
}

if (failures) { console.error(`test_calendar_date: ${failures} failed`); process.exit(1); }
console.log("test_calendar_date: all passed");
