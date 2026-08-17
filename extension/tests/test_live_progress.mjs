// He should be able to see what it is doing without asking anyone.
//
// A run can last forty minutes. The extension writes a trace every four
// seconds and every line of it is written for an engineer — "step 12: llm
// error", raw JSON decisions — and the phone reads none of it. So a run
// working perfectly and a run that has died look identical from the sofa.
// That is the whole "why is it always stalling?" feeling.
//
// These tests pin the two properties that make the live line safe to show:
// it names the SITE not the URL, and the FIELD not what was typed into it.
import { humanStep } from "../agent_loop.js";

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};
const say = (d, url) => humanStep(d, { url });

check("opening a site names the site",
  say({ action: "navigate" }, "https://www.opentable.com/r/earls") === "Opening opentable.com",
  say({ action: "navigate" }, "https://www.opentable.com/r/earls"));

check("typing names the field, never the value",
  say({ action: "type", label: "Email", value: "omarkebrahim@gmail.com" }, "https://jobs.example.com/apply")
    === "Filling in email on jobs.example.com");

check("choosing a time reads like a person wrote it",
  say({ action: "select", label: "7:30 PM" }, "https://www.opentable.com") === "Choosing 7:30 PM on opentable.com");

check("submitting says so plainly",
  say({ action: "enter" }, "https://jobs.example.com") === "Submitting the form on jobs.example.com");

check("verifying is not called done",
  /Checking it actually went through/.test(say({ action: "done" }, "https://x.example")));

check("an unknown action still says something human",
  say({ action: "wibble" }, "https://x.example") === "Working on x.example");

check("a missing url never produces 'undefined'",
  !/undefined|null|\[object/.test(say({ action: "click", label: "Next" }, undefined)),
  say({ action: "click", label: "Next" }, undefined));

// --- the privacy properties, which are the reason this is safe to display ---
const PRIVATE = [
  { d: { action: "type", label: "Card number", value: "4111111111111111" }, url: "https://pay.example.com/checkout?token=SECRET123&ref=BK-99812" },
  { d: { action: "type", label: "Password", value: "hunter2" }, url: "https://mail.google.com/u/0/#inbox/FMfcgz" },
  { d: { action: "select", label: "Party size", value: "4" }, url: "https://opentable.com/book?conf=ABC-1123&email=omar%40x.com" },
];
for (const { d, url } of PRIVATE) {
  const line = say(d, url);
  check(`typed value never appears: ${d.label}`, !line.includes(String(d.value)), line);
  check(`query string never appears: ${d.label}`,
    !/SECRET123|BK-99812|ABC-1123|omar%40x|FMfcgz|\?/.test(line), line);
  check(`the line stays short enough for a card: ${d.label}`, line.length <= 70, `${line.length} chars`);
}

check("he could hand someone his phone mid-run",
  !/hunter2|4111|@/.test(PRIVATE.map(({ d, url }) => say(d, url)).join(" ")));

if (failures) { console.error(`test_live_progress: ${failures} failed`); process.exit(1); }
console.log("test_live_progress: all passed");
