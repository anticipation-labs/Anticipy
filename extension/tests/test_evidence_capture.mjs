// THE PHOTOGRAPH: taken at the milestones, and deposited exactly once.
//
// Card HANDS 3, step 2: "screenshot capture at milestones → stored as evidence
// rows." Before 2026-08-25 `screenshot()` had ONE call site — the vision step,
// fired only when needsEyes() decided the page was a calendar or a seat map —
// and the frame was handed to the step model and dropped. The evidence host
// (research/2026-08-24-evidence-host.md, backend commit 0d2ee640) was therefore
// a room with no door: "done = evidence" promised the owner a picture, and
// nothing in the product ever took one.
//
// Three properties, and the third is the one that bites:
//   1. a frame is captured before anything irreversible, and again when a done
//      claim has been VERIFIED;
//   2. the row that comes back is named in the receipt, first, so the 12-entry
//      cap can never drop the one pointer nothing else can reconstruct;
//   3. the bytes never enter a job row. `out` is serialized into `params` on a
//      hand-back and read by the trace writer on every path; a 100KB data URL
//      surviving one line too long is a screenshot of a logged-in page sitting
//      in a text column forever.
//
// Run: node extension/tests/test_evidence_capture.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
// A real capture is tens of KB, and `screenshot()` treats anything under 4000
// chars as the blank frame a hidden background tab returns. Without a
// believable fake the milestone can never fire and the suite would pass by
// never reaching what it tests.
const FAKE_JPEG = Buffer.from("x".repeat(9000)).toString("base64");
globalThis.fetch = async () => ({ ok: false, status: 0, json: async () => ({}), text: async () => "" });

const { runAgentGoal } = await import("../agent_loop.js");
const { jpegBytes, depositEvidence } = await import("../background.js");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

// ------------------------------------------------- 1. the bytes, on their own
{
  const ok = `data:image/jpeg;base64,${Buffer.from("hello").toString("base64")}`;
  check("a jpeg data url decodes to its bytes", jpegBytes(ok)?.length === 5);
  check("a png is not a jpeg and is not silently renamed one",
    jpegBytes("data:image/png;base64,aGk=") === null);
  check("garbage decodes to nothing rather than throwing",
    jpegBytes("not a data url") === null && jpegBytes(null) === null);
  check("an empty capture is not deposited",
    jpegBytes("data:image/jpeg;base64,") === null);
  // The extension's capture ceiling and the collection's maxSize are the same
  // number on purpose. A frame that got past the first must not die at the
  // second, where nobody can see the reason.
  const huge = `data:image/jpeg;base64,${Buffer.alloc(400001, 0x41).toString("base64")}`;
  check("a frame over the collection's own maxSize is refused here, not there",
    jpegBytes(huge) === null);
}

// ------------------------------------------------------------ 2. the deposit
{
  const shot = `data:image/jpeg;base64,${Buffer.from("x".repeat(2000)).toString("base64")}`;
  const store = { get: async () => ({ ownerRef: "owner-abc" }) };
  let sent = null;
  const deps = {
    backendBase: async () => "https://backend.test",
    writeHeaders: async () => ({ "Content-Type": "application/json",
      "X-Anticipy-Agent-ID": "a1", "X-Anticipy-Agent-Token": "t1" }),
    storage: store,
    fetch: async (url, opts) => {
      sent = { url, opts };
      return { ok: true, status: 200, json: async () => ({ id: "rec123" }) };
    },
  };
  const ref = await depositEvidence({ id: "job7", effect_key: "eff9" }, shot, deps);
  check("the deposit returns a receipt entry naming the row", ref === "evidence:rec123");
  check("...posted to the evidence collection",
    sent?.url === "https://backend.test/api/collections/evidence/records"
    && sent.opts.method === "POST");
  check("...carrying the agent credential, and NOT the master token",
    sent.opts.headers["X-Anticipy-Agent-ID"] === "a1"
    && !("X-Anticipy-Token" in sent.opts.headers));
  // Multipart sets its own Content-Type, boundary and all. Leaving the JSON
  // one on makes PocketBase parse the body as JSON and reject a valid upload —
  // and every other call in background.js hardcodes it.
  check("...with the JSON content-type removed so the boundary survives",
    !("Content-Type" in sent.opts.headers));
  const form = sent.opts.body;
  check("...claiming the owner this credential resolves to",
    form.get("owner_ref") === "owner-abc");
  check("...bound to the job and to the exact effect the receipt names",
    form.get("job") === "job7" && form.get("effect_key") === "eff9");
  check("...and the image is an image", form.get("image")?.type === "image/jpeg");

  // Every failure below must return "" and must not throw. The owner's table
  // is booked either way; refusing to finish an errand because a photograph
  // did not upload would be a worse product than the one that took no photos.
  const refused = await depositEvidence({ id: "job7" }, shot, {
    ...deps, fetch: async () => ({ ok: false, status: 403, json: async () => ({}) }) });
  check("a refused deposit costs the errand nothing", refused === "");
  const thrown = await depositEvidence({ id: "job7" }, shot, {
    ...deps, fetch: async () => { throw new Error("offline"); } });
  check("a thrown deposit costs the errand nothing", thrown === "");
  // Unowned evidence is a picture nobody can see and nobody can erase, and
  // inventing an owner is the hole guard.pb.js:342-346 exists to close.
  const unowned = await depositEvidence({ id: "job7" }, shot, {
    ...deps, storage: { get: async () => ({}) } });
  check("with no owner, nothing is deposited at all", unowned === "");
  const noJob = await depositEvidence(null, shot, deps);
  check("with no job, nothing is deposited at all", noJob === "");
}

// ------------------------------- 2b. the pointer survives the receipt's own cap
//
// workflow_state.js:116 keeps the FIRST 12 evidence entries, because
// duplicating a full result there overflows PocketBase's text validation and
// turns a verified success into an HTTP 400. Every other entry in that array is
// a proof index the verifier can rebuild from the page; `evidence:<id>` is the
// only one that names a row nothing else in the product can find again. So it
// goes in front — appending it is a silent loss on any run with a long index.
{
  const { workflowPatch } = await import("../workflow_state.js");
  const plan = { plan_id: "plan-1", state: "running", updated_at: "" };
  const job = {
    id: "job7", workflow_id: "plan-1", effect_key: "eff9",
    params: JSON.stringify({ _workflow: plan }),
  };
  const long = Array.from({ length: 20 }, (_, i) => `url:https://page.test/${i}`);
  const patch = workflowPatch(job, "succeeded", {
    summary: "done", verified: true, evidence: ["evidence:rec123", ...long],
  });
  const receipt = JSON.parse(patch.receipt);
  check("the photo's row id survives a receipt with more evidence than the cap",
    receipt.evidence.includes("evidence:rec123") && receipt.evidence.length === 12);
  const appended = workflowPatch(job, "succeeded", {
    summary: "done", verified: true, evidence: [...long, "evidence:rec123"],
  });
  check("...and would NOT have survived if it were appended (so the order matters)",
    !JSON.parse(appended.receipt).evidence.includes("evidence:rec123"));
}

// ------------------------------------------- 3. the milestones, through the loop
const realExecuteScript = chrome.scripting.executeScript;
let controls = {};
chrome.scripting.executeScript = async (opts) => {
  const src = opts?.func ? String(opts.func) : "";
  const index = Array.isArray(opts?.args) ? Number(opts.args[0]) : null;
  if (src.includes("navigationLink")) {               // commitControl
    return [{ frameId: 0, result: !!controls[index]?.commit }];
  }
  if (src.includes("fieldsIn")) {                     // controlContext
    const c = controls[index];
    if (!c) return [{ frameId: 0, result: null }];
    return [{ frameId: 0, result: {
      label: c.label, tag: c.tag, href: "", nearbyText: c.label,
      formAction: c.formAction, name: c.name || "", elementId: c.elementId || "",
      fieldIndexes: c.fieldIndexes,
    } }];
  }
  return realExecuteScript(opts);
};

let page = null;
let captures = 0;
function fresh({ camera = true } = {}) {
  harness.tabs.clear();
  captures = 0;
  harness.onCdp = (tabId, method) => {
    if (method !== "Page.captureScreenshot") return undefined;
    captures += 1;
    return camera ? { data: FAKE_JPEG } : { data: "" };
  };
  harness.onInject = null;
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  harness.mapPage = () => page;
  harness.addTab({ url: "https://news.site/read", active: true });
}

function scripted(actions) {
  const queue = [...actions];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) {
      return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    }
    const body = JSON.parse(opts.body);
    const joined = body.messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "[image]")).join("\n")
      : String(m.content || ""))).join("\n");
    let content;
    if (/You plan a task/.test(joined)) {
      content = JSON.stringify({ start_url: page.url, why: "the venue", steps: [], unfamiliar: false });
    } else if (/pre-submit form auditor/.test(joined)) content = JSON.stringify({ values: [] });
    else if (/You audit a browser agent's claim/.test(joined)) {
      content = JSON.stringify({ verified: true, evidence: ["confirmation 4471"] });
    } else content = JSON.stringify(queue.shift() || { action: "wait" });
    return { ok: true, status: 200,
      json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };
}

// --- a booking: one commit, then a verified done
{
  fresh();
  const GOAL = "book a table for 6 under the name Alex Reyes";
  page = {
    url: "https://fixture.test/book",
    title: "Reserve a table",
    elements: "[1] <textbox> Name @(10,10)\n[3] <button> Book table @(10,70)",
    text: "Held for 4:32. Review your reservation and book the table.",
    fields: [{ index: 1, name: "guest_name", label: "Name", type: "text",
               required: true, readOnly: false, value: "Alex Reyes" }],
  };
  const form = { formAction: "https://fixture.test/book/submit", fieldIndexes: [1] };
  controls = { 3: { ...form, commit: true, label: "Book table", tag: "button",
                    name: "", elementId: "book-table" } };
  scripted([{ action: "click", index: 3 }, { action: "done", result: "Table booked" }]);
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: true, planning: false,
    maxSteps: 6, startUrl: page.url, stillLive: async () => true,
  });
  const evidence = out?.receipt?.evidence || [];
  check("the errand finished verified", out?.status === "done" && out.receipt?.verified === true);
  check("a frame was captured before the irreversible click",
    evidence.some((e) => /^shot:before-commit@https:\/\/fixture\.test\/book/.test(e)));
  check("and again once the done claim was VERIFIED, not when it was claimed",
    evidence.some((e) => /^shot:verified-done@/.test(e)));
  // The verifier builds its own proof index (verificationEvidence) rather than
  // keeping the model's words — the milestone marks are added BESIDE it, never
  // in place of it.
  check("the verifier's own proof index is still there beside the marks",
    evidence.some((e) => e.startsWith("url:https://fixture.test/book"))
    && evidence.some((e) => e.startsWith("proof:")));
  check("exactly ONE picture leaves the run, not one per milestone",
    typeof out.evidenceShot === "string" && out.evidenceShot.startsWith("data:image/jpeg;base64,"));
  // The receipt is what gets JSON.stringify'd into a PocketBase text column.
  check("no image bytes ride the receipt into the job row",
    !JSON.stringify(out.receipt).includes("data:image"));
}

// --- the camera comes back blank: a hidden tab that will not render
{
  fresh({ camera: false });
  const GOAL = "check the happy hour times";
  page = {
    url: "https://fixture.test/hours", title: "Happy hour",
    elements: "[0] <link> Menus @(10,10)",
    text: "Happy hour runs 3-6pm daily.", fields: [],
  };
  controls = {};
  scripted([{ action: "done", result: "3-6pm daily" }]);
  const out = await runAgentGoal(GOAL, {
    apiKey: "test-key", scope: GOAL, authorized: false, planning: false,
    maxSteps: 4, startUrl: page.url, stillLive: async () => true,
  });
  const evidence = out?.receipt?.evidence || [];
  check("a blank frame still leaves a mark saying there is no photo of this",
    evidence.some((e) => e === `shot:verified-done(none)@${page.url}`));
  check("...and nothing is offered for deposit", !out.evidenceShot);
  check("the camera was actually asked (the milestone is not dead code)", captures > 0);
}

console.log(failures === 0
  ? "test_evidence_capture: milestones photographed, deposited once, and the bytes never reach a job row"
  : `test_evidence_capture: ${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
