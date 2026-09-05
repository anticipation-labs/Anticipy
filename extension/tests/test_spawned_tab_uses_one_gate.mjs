// THE FIFTH DOOR: A CLICK THAT OPENS A TAB IS A NAVIGATION TOO.
//
// F05. `09ec97ad` widened the SSRF seatbelt from "this machine" to "the
// owner's whole internal network" — the router at 192.168.1.1, a NAS, a work
// VPN host, and on a cloud desktop the metadata service at 169.254.169.254
// that hands out credentials. It swapped `loopbackTarget` for
// `internalNetworkTarget` at four navigation sites and missed the fifth: the
// tab a click spawns, which the loop ADOPTS by navigating the working tab to
// it. `loopbackTarget` matches localhost/127.x/::1/0.0.0.0 and nothing else,
// so a page the agent was reading could hand it
//
//     <a target="_blank" href="http://192.168.1.1/">
//
// and the run followed it: one authenticated GET from the owner's own browser
// plus a full DOM map of the reply, before the landed-page check could hand
// back. The "ONE GATE, EVERY NAVIGATION" comment in the loop named this exact
// path as covered while the path asked a different question.
//
// This suite drives the REAL loop with a page whose click spawns a tab, and
// reads what the working tab was actually navigated to. It is the same
// seatbelt in every leg — what the plan TOUCHES, an address class, never what
// a sentence means (HARNESS-LAWS law 1's second exemption).
//
// Run: node extension/tests/test_spawned_tab_uses_one_gate.mjs
import { installChrome } from "./chrome_mock.mjs";

const harness = installChrome();
const { runAgentGoal } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : `  -> ${detail}`}`);
  if (!ok) failures++;
};

// Every chrome.tabs.update that carried a url — i.e. every navigation the
// extension itself performed. This is the measurement: the question is not
// what the loop logged, it is where the owner's browser was sent.
const navigations = [];
const realUpdate = chrome.tabs.update;
chrome.tabs.update = async (id, props = {}) => {
  if (props && props.url !== undefined) navigations.push({ id, url: String(props.url) });
  return realUpdate(id, props);
};

const PAGE = {
  url: "https://deals.example/offer",
  title: "Offer",
  elements: '[0] <link> Open the full offer [href=https://deals.example/full] @(10,10)',
  text: "An ordinary page with one link on it.",
  fields: [],
};

// The loop's own two sentinels, so a scripted reply lands on the right call.
const AUDIT_SENTINEL = /You audit a browser agent's claim/;
const STEP_SENTINEL = /You are Anticipy's browser agent/;

// One run: the model clicks element 0, the page answers by opening `spawnTo`
// in a new tab (target=_blank), then the model says done.
async function runWithSpawn(spawnTo, { goal = "read the offer page", startUrl = PAGE.url } = {}) {
  harness.tabs.clear();
  harness.focusGrants.length = 0;
  harness.activationLog.length = 0;
  navigations.length = 0;
  for (const key of Object.keys(harness.storageData)) delete harness.storageData[key];
  const owner = harness.addTab({ url: "https://news.site/read", active: true });
  harness.mapPage = (tabId) => ({ ...PAGE, url: harness.tabs.get(tabId)?.url || PAGE.url });

  let spawned = false;
  harness.onCdp = (tabId, method, params) => {
    if (!spawned && method === "Input.dispatchMouseEvent" && params?.type === "mousePressed") {
      spawned = true;
      // Chrome's real behaviour for target=_blank: a new tab, opened by the
      // page, foregrounded, owned by the tab that was clicked.
      harness.addTab({ url: spawnTo, active: true, openerTabId: tabId });
    }
    return undefined;
  };

  const steps = [{ action: "click", index: 0 }, { action: "done", result: "The offer page has one link on it." }];
  let at = 0;
  const trace = [];
  globalThis.fetch = async (url, opts = {}) => {
    if (!String(url).includes("openrouter")) return { ok: false, status: 0, json: async () => ({}), text: async () => "" };
    const joined = JSON.parse(opts.body).messages.map((m) => (Array.isArray(m.content)
      ? m.content.map((p) => (p.type === "text" ? p.text : "")).join("\n") : String(m.content || ""))).join("\n");
    let content = "{}";
    if (AUDIT_SENTINEL.test(joined)) content = '{"verified":true}';
    else if (STEP_SENTINEL.test(joined)) content = JSON.stringify(steps[Math.min(at++, steps.length - 1)]);
    return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content } }] }), text: async () => "" };
  };

  const out = await runAgentGoal(goal, {
    apiKey: "test-key", scope: goal, readOnly: true, authorized: false, planning: false,
    startUrl, maxSteps: 6, budgetMs: 60_000, stillLive: async () => true,
    onTrace: (history) => { trace.length = 0; trace.push(...history); },
  });
  return { out, trace, owner, wentTo: navigations.map((n) => n.url) };
}

const followed = (wentTo, url) => wentTo.some((seen) => seen === url);

// ---------------------------------------------------------------------------
// (a) THE DEFECT. The owner's own network, reached through a spawned tab.
//     Each of these walked past `loopbackTarget` and was adopted.
// ---------------------------------------------------------------------------
for (const target of [
  "http://192.168.1.1/",                                  // the router's admin panel
  "http://10.0.0.5/backups",                              // a NAS on a work LAN
  "http://169.254.169.254/latest/meta-data/iam/security-credentials/",  // cloud metadata
  "http://172.16.4.9/",                                   // the other private block
  "http://100.64.0.1/",                                   // carrier-grade NAT
  "http://[fd00::1]/",                                    // IPv6 unique-local
]) {
  const { out, trace, wentTo } = await runWithSpawn(target);
  check(`(a) a spawned tab at ${target.slice(0, 44)} is never followed`,
    !followed(wentTo, target), JSON.stringify(wentTo));
  check("(a) ...and the run says why, in the trace the job keeps",
    trace.some((line) => /BLOCKED UNEXPECTED TARGET/.test(line)
      && /local or internal-network site/.test(line)), trace.join(" | ").slice(0, 240));
  check("(a) ...and the run is not killed by it — it goes on and finishes",
    out.status === "done", `${out.status}: ${String(out.result).slice(0, 120)}`);
}

// ---------------------------------------------------------------------------
// (b) THE CONTROL. The same click, an ordinary public URL: still adopted.
//     Without this leg every assertion above passes on a loop that follows
//     nothing at all.
// ---------------------------------------------------------------------------
{
  const { out, trace, wentTo } = await runWithSpawn("https://deals.example/full");
  check("(b) an ordinary spawned tab is still adopted in place",
    followed(wentTo, "https://deals.example/full"), JSON.stringify(wentTo));
  check("(b) ...and the trace says it followed it, not that it blocked it",
    trace.some((line) => /link opened a new tab — following/.test(line))
      && !trace.some((line) => /BLOCKED UNEXPECTED TARGET/.test(line)),
    trace.join(" | ").slice(0, 240));
  check("(b) ...and the run finishes", out.status === "done");
}

// ---------------------------------------------------------------------------
// (c) THE AUTHORISATION IS THE TASK'S, AND IT STILL WORKS. A goal that names
//     the internal host is a developer running an errand on his own machine,
//     not a hijack — the same rule the other four doors apply.
// ---------------------------------------------------------------------------
{
  const { wentTo } = await runWithSpawn("http://localhost:8025/inbox",
    { goal: "check the mail catcher at http://localhost:8025/", startUrl: "http://localhost:8025/" });
  check("(c) a task that names localhost may follow a spawned localhost tab",
    followed(wentTo, "http://localhost:8025/inbox"), JSON.stringify(wentTo));
}
{
  const { wentTo, trace } = await runWithSpawn("http://192.168.1.1/status",
    { goal: "read the router status page at http://192.168.1.1/", startUrl: "http://192.168.1.1/" });
  check("(c) ...and a task that names the router may follow one to the router",
    followed(wentTo, "http://192.168.1.1/status"), JSON.stringify(wentTo));
  check("(c) ...with nothing blocked in the trace",
    !trace.some((line) => /BLOCKED UNEXPECTED TARGET/.test(line)), trace.join(" | ").slice(0, 200));
}

// ---------------------------------------------------------------------------
// (d) WHAT THE NARROW CHECK ALREADY DID STILL HAPPENS. The loopback case was
//     the one `loopbackTarget` caught; the wider gate must not have lost it,
//     and the money gate on this door must still hand back rather than log.
// ---------------------------------------------------------------------------
{
  const { wentTo, trace } = await runWithSpawn("http://127.0.0.1:8090/_/");
  check("(d) an unauthorised loopback spawn is still refused",
    !followed(wentTo, "http://127.0.0.1:8090/_/"), JSON.stringify(wentTo));
  check("(d) ...and says so", trace.some((line) => /BLOCKED UNEXPECTED TARGET/.test(line)));
}
{
  const { out, wentTo } = await runWithSpawn("https://chase.com/login");
  check("(e) a spawned tab at a protected financial site hands back to the owner",
    out.status === "needs_user" && /protected financial site/.test(String(out.result)),
    `${out.status}: ${String(out.result).slice(0, 120)}`);
  check("(e) ...and the working tab was never sent there",
    !followed(wentTo, "https://chase.com/login"), JSON.stringify(wentTo));
}

if (failures) { console.log(`test_spawned_tab_uses_one_gate: ${failures} FAILED`); process.exit(1); }
console.log("test_spawned_tab_uses_one_gate: every navigation asks the one gate, the adopted tab included");
process.exit(0);
