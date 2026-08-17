/// <reference path="../pb_data/types.d.ts" />

// Server-side CAPTCHA solving, on the owner's explicit instruction
// (2026-08-16). The rule this softens is written in agent_loop.js and stands
// everywhere else: a CAPTCHA is a site asking whether a person is here, and
// the answer is normally to go and get the person.
//
// Two things make this different from the dead solver that was ripped out of
// the extension months ago:
//
//   1. THE KEY NEVER LEAVES THE SERVER. The old one was to live in the
//      extension, where anyone who unzips a published build reads it and
//      spends the owner's balance. Solving is a backend endpoint the paired
//      agent asks for, exactly like the model proxy next door.
//   2. IT IS BOUNDED. Only challenge types we can name, only for an agent
//      attached to a real account, never on a protected/financial host, and
//      capped per hour so a loop cannot drain the balance in a night.
//
// If the key is absent the endpoint answers 501 and the browser falls back to
// what it does today: stop, and hand the screen to the person.

routerAdd("POST", "/agent/solve-captcha", (e) => {
  // Declared INSIDE the handler: this runtime cannot see anything declared
  // outside the handler body (the trap password_reset.pb.js documents, and
  // audit_retention.pb.js re-learned the hard way).
  const HOURLY_SOLVE_CEILING = 25;
  const POLL_TIMEOUT_MS = 120000;
  const POLL_EVERY_MS = 3000;
  // Money and consent live on the same host list: a challenge on a bank, a
  // brokerage or an identity provider is never solved on someone's behalf.
  const NEVER_SOLVE = /(^|\.)(chase|wellsfargo|bankofamerica|citi|rbc|td|scotiabank|bmo|cibc|tangerine|wealthsimple|questrade|robinhood|coinbase|binance|kraken|paypal|venmo|wise|revolut|stripe|irs|cra-arc|gc)\.(com|ca|net|org|gov)$|accounts\.google\.com|login\.microsoftonline\.com|appleid\.apple\.com|id\.gov/i;

  const apiKey = $os.getenv("CAPSOLVER_API_KEY") || "";
  if (!apiKey) {
    return e.json(501, { error: "solving is not configured" });
  }

  const agentId = e.request.header.get("X-Anticipy-Agent-ID") || "";
  const agentToken = e.request.header.get("X-Anticipy-Agent-Token") || "";
  if (!agentId || !agentToken || agentToken.length < 20) {
    return e.json(400, { error: "agent credentials required" });
  }
  let agentRecord = null;
  try {
    agentRecord = e.app.findFirstRecordByFilter(
      "agents", "agent_id = {:id} && agent_token = {:token} && paired = true",
      { id: agentId, token: agentToken });
  } catch (_) {
    return e.json(403, { error: "not a paired agent" });
  }
  if (!agentRecord) return e.json(403, { error: "not a paired agent" });
  if (!String(agentRecord.getString("owner_ref") || "").trim()) {
    return e.json(403, { error: "this agent is not attached to an account" });
  }

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {
    return e.json(400, { error: "unreadable request" });
  }
  const websiteURL = String(body.websiteURL || "").trim();
  const websiteKey = String(body.websiteKey || "").trim();
  const kind = String(body.type || "").trim();
  if (!websiteURL || !websiteKey) {
    return e.json(400, { error: "websiteURL and websiteKey are required" });
  }
  let host = "";
  try { host = String(websiteURL).split("/")[2] || ""; } catch (_) { host = ""; }
  if (NEVER_SOLVE.test(host)) {
    console.log("captcha: refusing a protected host", host);
    return e.json(403, {
      error: "this site is never solved automatically",
      detail: "a challenge on money or identity belongs to the person",
    });
  }
  const TASKS = {
    recaptcha_v2: "ReCaptchaV2TaskProxyLess",
    recaptcha_v3: "ReCaptchaV3TaskProxyLess",
    hcaptcha: "HCaptchaTaskProxyLess",
    turnstile: "AntiTurnstileTaskProxyLess",
  };
  const taskType = TASKS[kind];
  if (!taskType) {
    return e.json(400, { error: "unsupported challenge type", detail: kind });
  }

  // A loop must not be able to spend the night. Counted on the agent row for
  // the same reason the model meter is: the audit ledger once filled the
  // volume and took production down.
  const hourNow = new Date().toISOString().slice(0, 13);
  const storedHour = String(agentRecord.getString("solve_hour") || "");
  const used = storedHour === hourNow
    ? (Number(agentRecord.get("solve_calls")) || 0) : 0;
  if (used >= HOURLY_SOLVE_CEILING) {
    console.log("captcha: hourly ceiling hit for", agentId);
    return e.json(429, { error: "too many solves this hour" });
  }

  const post = (path, payload) => {
    const r = $http.send({
      url: `https://api.capsolver.com/${path}`,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      timeout: 30,
    });
    try { return JSON.parse(r.raw || "{}"); } catch (_) { return {}; }
  };

  const task = { type: taskType, websiteURL: websiteURL, websiteKey: websiteKey };
  if (kind === "recaptcha_v3") {
    task.pageAction = String(body.pageAction || "verify");
    task.minScore = 0.7;
  }
  const created = post("createTask", { clientKey: apiKey, task: task });
  if (created.errorId || !created.taskId) {
    console.log("captcha: createTask refused:", created.errorCode || "unknown");
    return e.json(502, {
      error: "the solver refused the task",
      detail: String(created.errorCode || created.errorDescription || ""),
    });
  }

  agentRecord.set("solve_hour", hourNow);
  agentRecord.set("solve_calls", used + 1);
  try { e.app.save(agentRecord); } catch (_) {}

  // Hand the ticket back and let the caller poll. Holding an HTTP request
  // open for two minutes invites a proxy timeout and pins a request slot for
  // work that is already happening in a background tab.
  return e.json(202, { taskId: created.taskId, type: kind });
});

// The other half: has it finished? Same credentials, no key exposure.
routerAdd("POST", "/agent/solve-captcha/result", (e) => {
  const apiKey = $os.getenv("CAPSOLVER_API_KEY") || "";
  if (!apiKey) return e.json(501, { error: "solving is not configured" });

  const agentId = e.request.header.get("X-Anticipy-Agent-ID") || "";
  const agentToken = e.request.header.get("X-Anticipy-Agent-Token") || "";
  if (!agentId || !agentToken || agentToken.length < 20) {
    return e.json(400, { error: "agent credentials required" });
  }
  try {
    const rec = e.app.findFirstRecordByFilter(
      "agents", "agent_id = {:id} && agent_token = {:token} && paired = true",
      { id: agentId, token: agentToken });
    if (!rec) return e.json(403, { error: "not a paired agent" });
  } catch (_) {
    return e.json(403, { error: "not a paired agent" });
  }

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {
    return e.json(400, { error: "unreadable request" });
  }
  const taskId = String(body.taskId || "").trim();
  if (!taskId) return e.json(400, { error: "taskId is required" });

  let got = {};
  try {
    const r = $http.send({
      url: "https://api.capsolver.com/getTaskResult",
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientKey: apiKey, taskId: taskId }),
      timeout: 30,
    });
    got = JSON.parse(r.raw || "{}");
  } catch (err) {
    return e.json(502, { error: "could not reach the solver" });
  }
  if (got.errorId) {
    console.log("captcha: solve failed:", got.errorCode || "unknown");
    return e.json(502, { error: "the solver could not do it",
                         detail: String(got.errorCode || "") });
  }
  if (got.status !== "ready") return e.json(200, { status: "processing" });
  const sol = got.solution || {};
  const token = sol.gRecaptchaResponse || sol.token || sol.captchaToken || "";
  if (!token) return e.json(502, { error: "solver returned no token" });
  console.log("captcha: solved task", taskId);
  return e.json(200, { status: "ready", token: token });
});
