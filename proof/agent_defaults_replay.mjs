// Replay of the 2026-08-10 Earls failure through the REAL agent prompt and
// model: a reservation widget opens pre-filled with the site's own default
// (today 6:30 PM); the approved task is tomorrow at noon, and the values are
// on the record. The agent must SET the fields — never stop to ask about a
// default, never re-ask for a fact it already has.
// Run: OPENROUTER_API_KEY=... node proof/agent_defaults_replay.mjs
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "extension", "agent_loop.js"), "utf8");
const sys = src.match(/const AGENT_SYSTEM = `([\s\S]*?)`;/)[1];

const key = process.env.OPENROUTER_API_KEY;
if (!key) { console.error("need OPENROUTER_API_KEY"); process.exit(1); }
const model = process.env.ANTICIPY_MODEL || "google/gemini-2.5-flash";

const user = `WHAT THEY AGREED TO (their one answer, already given):
Task: Book lunch at Earls on Marine Drive in West Vancouver for tomorrow at noon.. They said: "yes". Heard originally: we should grab lunch tomorrow, Earls on Marine Drive in West Van, around noon
You have their authority for all of it, to the end. Only a MATERIAL difference from the above may stop you.

FACTS ALREADY GIVEN (from the owner and the task record — set form fields to these; never ask for any of them):
  time: noon
  party size: 2

GOAL: Book lunch at Earls on Marine Drive in West Vancouver for tomorrow at noon.

HISTORY:
step 3: click 12 -> ok

URL: https://www.opentable.ca/r/earls-kitchen-bar-west-vancouver
TITLE: Earls Kitchen + Bar - West Vancouver - OpenTable
ELEMENTS:
[0] <combobox> Party size: 2 people (options: 1 person, 2 people, 3 people, 4 people)
[1] <combobox> Date: Mon, Aug 10 (options: Mon Aug 10, Tue Aug 11, Wed Aug 12)
[2] <combobox> Time: 6:30 PM (options: 11:30 AM, 12:00 PM, 12:30 PM, 6:30 PM, 7:00 PM)
[3] <button> Find a table

PAGE TEXT:
Make a reservation. Party size 2 people. Date Mon, Aug 10. Time 6:30 PM.`;

// The stop rule must SURVIVE the fix: when the site genuinely cannot offer
// what was agreed (no midday slots at all on the right date), stopping and
// naming what IS available is correct.
const noNoon = user
  .replace("[1] <combobox> Date: Mon, Aug 10 (options: Mon Aug 10, Tue Aug 11, Wed Aug 12)",
           "[1] <combobox> Date: Tue, Aug 11 (options: Mon Aug 10, Tue Aug 11, Wed Aug 12)")
  .replace("(options: 11:30 AM, 12:00 PM, 12:30 PM, 6:30 PM, 7:00 PM)",
           "(options: 6:30 PM, 7:00 PM, 7:30 PM)")
  .replace("Date Mon, Aug 10.", "Date Tue, Aug 11.")
  .replace("step 3: click 12 -> ok",
           "step 3: select 1 'Tue Aug 11' -> ok\n"
           + "step 4: select 2 '12:00 PM' -> no option matching \"12:00 PM\" — options are: 6:30 PM | 7:00 PM | 7:30 PM");

// Live, 2026-08-11: "Book Earls for lunch tomorrow" named no location; the
// agent wandered a locations list — Winnipeg, Ambleside, back again — opening
// reservation widgets on cities the owner never mentioned, for 60 steps. A
// choice the task never gave is not the agent's to make.
const noLocation = `WHAT THEY AGREED TO (their one answer, already given):
Task: Book Earls for lunch tomorrow. They said: "Book it please for two people at 1 PM".
You have their authority for all of it, to the end. Only a MATERIAL difference from the above may stop you.

FACTS ALREADY GIVEN (from the owner and the task record — set form fields to these; never ask for any of them):
  time: 1 PM
  number of people: 2

GOAL: Book Earls for lunch tomorrow

HISTORY:
step 1: navigate https://earls.ca/locations -> ok

URL: https://earls.ca/locations
TITLE: Locations | Earls Kitchen + Bar
ELEMENTS:
[0] <link> 300 Main Street (Winnipeg) — Make a Reservation
[1] <link> Ambleside (West Vancouver) — Make a Reservation
[2] <link> Robson Street (Vancouver) — Make a Reservation
[3] <link> Yaletown (Vancouver) — Make a Reservation
[4] <link> Park Royal (West Vancouver) — Make a Reservation

PAGE TEXT:
Find your Earls. 70 locations across North America.`;

let pass = 0, runs = 3;
for (let i = 0; i < runs; i++) {
  const r = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model, temperature: 0, response_format: { type: "json_object" },
      messages: [{ role: "system", content: `Right now it is Monday, August 10, 2026, 11:15 AM PDT.\n\n${sys}` },
                 { role: "user", content: user }] }),
  });
  const text = (await r.json()).choices?.[0]?.message?.content ?? "";
  let act = {};
  try { act = JSON.parse(text.match(/\{[\s\S]*\}/)[0]); } catch {}
  const settingField = (act.action === "select" && [1, 2].includes(act.index))
    || (act.action === "click" && [1, 2].includes(act.index));
  const ok = settingField && act.action !== "needs_user";
  console.log(`  run ${i + 1}: ${ok ? "ok  " : "FAIL"} -> ${JSON.stringify(act).slice(0, 120)}`);
  if (ok) pass++;
}
let pass2 = 0;
for (let i = 0; i < runs; i++) {
  const r = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model, temperature: 0, response_format: { type: "json_object" },
      messages: [{ role: "system", content: `Right now it is Monday, August 10, 2026, 11:15 AM PDT.\n\n${sys}` },
                 { role: "user", content: noNoon }] }),
  });
  const text = (await r.json()).choices?.[0]?.message?.content ?? "";
  let act = {};
  try { act = JSON.parse(text.match(/\{[\s\S]*\}/)[0]); } catch {}
  const ok = act.action === "needs_user" && /6:30|7/.test(act.reason || "");
  console.log(`  no-noon run ${i + 1}: ${ok ? "ok  " : "FAIL"} -> ${JSON.stringify(act).slice(0, 140)}`);
  if (ok) pass2++;
}
let pass3 = 0;
for (let i = 0; i < runs; i++) {
  const r = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model, temperature: 0, response_format: { type: "json_object" },
      messages: [{ role: "system", content: `Right now it is Tuesday, August 11, 2026, 11:57 AM PDT.\n\n${sys}` },
                 { role: "user", content: noLocation }] }),
  });
  const text = (await r.json()).choices?.[0]?.message?.content ?? "";
  let act = {};
  try { act = JSON.parse(text.match(/\{[\s\S]*\}/)[0]); } catch {}
  const ok = act.action === "needs_user";
  console.log(`  no-location run ${i + 1}: ${ok ? "ok  " : "FAIL"} -> ${JSON.stringify(act).slice(0, 140)}`);
  if (ok) pass3++;
}
console.log(`agent defaults replay: set-fields ${pass}/${runs}, honest-stop ${pass2}/${runs}, no-location-stop ${pass3}/${runs}`);
process.exit(pass === runs && pass2 === runs && pass3 === runs ? 0 : 1);
