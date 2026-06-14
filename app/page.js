"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const SAMPLE = `[08:02] Omar: yeah okay no the coffee machine is being weird again and I do not care.
[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.
[08:05] Omar: oh sure, I'll just clone myself, that'll fix the schedule.
[09:12] Sam needs the revised deck before Friday; I told him I'd send it.
[11:22] that water-table thing for Leila's birthday, put it in the cart if you find it, don't buy it.
[12:10] order the replacement filter today and just pay whatever it costs.
[13:00] My wife Maya prefers texts after lunch.`;

const DEFAULT_MEMORY = {
  ownerName: "Omar",
  timezone: "America/Vancouver",
  phone: "",
  email: "",
  preferences: "Ask before sending messages to real people.\nNever buy anything.",
  people: "Maya | wife | sms | school pickup changes\nSam | contractor | email | revised deck",
  connections: "Google Calendar | connected | api | calendar | reminders and events\nGmail | needs_auth | api | gmail.compose | drafts and approvals\nChrome | needs_setup | browser | chrome | browser tasks",
  stores: "Staples | https://www.staples.com | office supplies\nTarget | https://www.target.com | birthday gifts",
  notes: "Weekday afternoons are usually packed.",
};

const sources = [
  ["typed", "Typed"],
  ["transcript", "Transcript"],
  ["upload", "Upload"],
  ["start_listening", "Listen"],
];

function lines(value) {
  return (value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function pipeParts(line) {
  return line.split("|").map((part) => part.trim());
}

function normalizeConnectionStatus(value) {
  const allowed = new Set(["connected", "needs_auth", "needs_setup", "unavailable", "unknown"]);
  return allowed.has(value) ? value : "unknown";
}

function normalizeRoute(value) {
  const allowed = new Set(["api", "browser", "voice_text", "memory"]);
  return allowed.has(value) ? value : "api";
}

function onboardingPayload(form) {
  return {
    source: "owner_mode",
    owner_name: form.ownerName,
    timezone: form.timezone,
    phone: form.phone,
    email: form.email,
    preferences: lines(form.preferences),
    people: lines(form.people).map((line) => {
      const [name, relationship = "", channel = "", notes = ""] = pipeParts(line);
      return { name, relationship, channels: channel ? [channel] : [], notes };
    }).filter((person) => person.name),
    connections: lines(form.connections).map((line) => {
      const [name, status = "unknown", route = "api", identifier = "", notes = ""] = pipeParts(line);
      return { name, status: normalizeConnectionStatus(status), route: normalizeRoute(route), identifier, notes };
    }).filter((connection) => connection.name),
    stores: lines(form.stores).map((line) => {
      const [name, url = "", notes = "", route = "browser"] = pipeParts(line);
      return { name, url, notes, route: normalizeRoute(route) };
    }).filter((store) => store.name),
    raw_notes: form.notes,
  };
}

function cardBucket(card) {
  if (card.status === "declined") return "done";
  if (card.status === "done" || card.disposition === "remember") return "done";
  if (card.disposition === "blocked" || card.status === "blocked") return "blocked";
  if (card.disposition === "ask" || card.status === "waiting") return "ask";
  return "ready";
}

function proofValue(proof) {
  if (!proof) return "";
  if (proof.type === "memory_resolution") return [proof.item, proof.site].filter(Boolean).join(" @ ");
  if (proof.type === "browser_receipt") return [proof.answer || "browser verified", proof.url].filter(Boolean).join(" @ ");
  if (proof.decision) return [proof.decision, proof.goal_state].filter(Boolean).join(" / ");
  if (proof.memory_id) return proof.memory_id;
  if (proof.path) return proof.path;
  if (proof.type) return proof.type;
  return JSON.stringify(proof);
}

function proofLabel(proof) {
  if (proof?.type === "memory_resolution") return "used memory";
  if (proof?.type === "browser_receipt") return "browser receipt";
  const type = proof?.type || "proof";
  return type.replaceAll("_", " ");
}

function visibleProofs(proofs = []) {
  if (!Array.isArray(proofs)) return [];
  const userProof = new Set(["memory_resolution", "browser_receipt", "resolution"]);
  const humanReceipts = proofs.filter((proof) => userProof.has(proof?.type));
  const execution = proofs.filter((proof) => proof?.type === "engine_execution");
  const fallback = proofs.filter((proof) => {
    const type = proof?.type;
    return !userProof.has(type) && type !== "engine_execution" && type !== "card_record";
  });
  return [...humanReceipts, ...execution, ...fallback].slice(0, 4);
}

function outcomeText(card, pendingAsk) {
  const bucket = cardBucket(card);
  if (card.status === "declined") return "Declined by Omar";
  if (bucket === "blocked") return "Hard wall: no payment executed";
  if (bucket === "ask") return pendingAsk ? `Waiting for Omar: ${pendingAsk.ask_id.slice(0, 6)}` : "Waiting for Omar";
  if (bucket === "done") return "Done with receipt";
  return "Ready";
}

function receiptText(entry) {
  return entry.summary || entry.message || JSON.stringify(entry.data || entry);
}

function firedLoopText(item) {
  const pieces = [item.task || item.text || "loop", item.decision || "checked"];
  if (item.category) pieces.push(item.category);
  if (item.ask_id) pieces.push(`ask ${item.ask_id.slice(0, 6)}`);
  return pieces.join(" / ");
}

// The remember-list ts is a unix epoch in seconds (RememberList writes time.time()).
function formatRememberTs(ts) {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds)) return "";
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

const readinessOrder = [
  "app_input",
  "proactive_engine",
  "memory",
  "browser",
  "api_hands",
  "voice_text",
  "approvals",
  "money_wall",
  "owner_api",
];

const readinessNames = {
  app_input: "Input",
  proactive_engine: "Engine",
  memory: "Memory",
  browser: "Browser",
  api_hands: "APIs",
  voice_text: "Text/Call",
  approvals: "Approvals",
  money_wall: "Money",
  owner_api: "Access",
};

function readinessEntries(readiness) {
  const items = readiness?.items || {};
  return readinessOrder
    .map((key) => (items[key] ? { key, name: readinessNames[key] || key, ...items[key] } : null))
    .filter(Boolean);
}

function readinessTone(state) {
  if (state === "ready" || state === "protected") return "ok";
  if (state === "setup" || state === "warning" || state === "ready_to_enable") return "warn";
  if (state === "mock" || state === "local") return "muted";
  return "muted";
}

function loopMeta(loop) {
  const fields = loop.fields || {};
  return [fields.route, fields.action, fields.disposition || fields.kind]
    .filter(Boolean)
    .join(" / ");
}

function MemoryField({ label, value, onChange, multiline = false, placeholder = "" }) {
  const props = {
    value,
    onChange: (event) => onChange(event.target.value),
    placeholder,
    spellCheck: "true",
  };
  return (
    <label className="memory-field">
      <span>{label}</span>
      {multiline ? <textarea {...props} /> : <input {...props} />}
    </label>
  );
}

function ProfileView({ profile }) {
  if (!profile) return null;
  const summary = profile.summary || {};
  const facts = profile.key_facts || [];
  const blockers = profile.blockers || [];
  const browserOff = profile.browser_available === false;
  return (
    <div className="profile-view">
      <div className="profile-head">
        <strong>{profile.name}</strong>
        {profile.role ? <span className="profile-role">{profile.role}</span> : null}
        {browserOff ? (
          <span className="tag ask" title="No browser arm was available, so nothing was scraped. No facts were invented.">
            browser unavailable
          </span>
        ) : null}
      </div>
      {(profile.org || profile.location) ? (
        <div className="profile-sub">
          {profile.org ? <span>{profile.org}</span> : null}
          {profile.location ? <span>{profile.location}</span> : null}
        </div>
      ) : null}
      <div className="profile-counts">
        <span className="tag">{summary.facts ?? facts.length} facts</span>
        <span className="tag">{summary.needs_cross_check ?? 0} need cross-check</span>
        <span className="tag">
          {summary.sources_read_ok ?? 0}/{summary.sources_total ?? (profile.sources || []).length} sources read
        </span>
      </div>
      {facts.length ? (
        <ul className="profile-facts">
          {facts.map((fact, index) => (
            <li className="profile-fact" key={`${fact.field}-${index}`}>
              <div className="profile-fact-head">
                <span className="profile-field">{fact.field}</span>
                {fact.needs_cross_check ? (
                  <span className="tag ask" title="Low-trust single-page pull — confirm with a second source.">
                    needs cross-check
                  </span>
                ) : (
                  <span className="tag done" title="Whole-page read — a tier higher trust.">
                    {fact.confidence || fact.trust}
                  </span>
                )}
              </div>
              <p className="profile-value">{fact.value}</p>
              {fact.source_url ? (
                <a className="profile-source" href={fact.source_url} target="_blank" rel="noopener noreferrer">
                  {fact.source_url}
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="profile-empty">No facts assembled. Nothing was invented.</p>
      )}
      {blockers.length ? (
        <div className="profile-blockers">
          <span className="profile-field">Blockers</span>
          <ul>
            {blockers.map((b, index) => (
              <li key={`blocker-${index}`}>{b}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function TaskCard({ card, pendingAsk, onResolve }) {
  const bucket = cardBucket(card);
  const proofs = visibleProofs(card.proof);
  return (
    <article className={`card ${bucket}`}>
      <div className="card-head">
        <h4>{card.title || card.action || "Owner task"}</h4>
        <span className={`outcome ${bucket}`}>{outcomeText(card, pendingAsk)}</span>
      </div>
      <p className="source-text">{card.source_text}</p>
      <div className="meta">
        <span className={`tag ${bucket}`}>{card.disposition}</span>
        <span className="tag">{card.route}</span>
        <span className="tag">{card.action}</span>
        {card.status ? <span className={`tag ${bucket}`}>{card.status}</span> : null}
        {card.execution?.goal_state ? <span className={`tag ${bucket}`}>{card.execution.goal_state}</span> : null}
      </div>
      {card.reason ? <p>{card.reason}</p> : null}
      {proofs.length ? (
        <div className="proof">
          {proofs.map((proof, index) => (
            <div className="proof-row" key={`${card.id}-proof-${index}`}>
              <span>{proofLabel(proof)}</span>
              <code title={proofValue(proof)}>{proofValue(proof)}</code>
            </div>
          ))}
        </div>
      ) : null}
      {pendingAsk ? (
        <div className="pending-actions">
          <button onClick={() => onResolve(pendingAsk.ask_id, true)}>Approve</button>
          <button onClick={() => onResolve(pendingAsk.ask_id, false)}>Decline</button>
        </div>
      ) : null}
    </article>
  );
}

function PendingAsk({ ask, onResolve }) {
  return (
    <article className="card ask">
      <div className="card-head">
        <h4>{ask.action}</h4>
        <span className="outcome ask">Waiting for Omar: {ask.ask_id.slice(0, 6)}</span>
      </div>
      <p className="source-text">{ask.reason}</p>
      <div className="meta">
        <span className="tag ask">needs yes</span>
        <span className="tag">{ask.category || "ask"}</span>
        <span className="tag">{ask.ask_id}</span>
      </div>
      <div className="pending-actions">
        <button onClick={() => onResolve(ask.ask_id, true)}>Approve</button>
        <button onClick={() => onResolve(ask.ask_id, false)}>Decline</button>
      </div>
    </article>
  );
}

function MemoryLoop({ loop, onResolve, onConnect, connection }) {
  const meta = loopMeta(loop);
  const canResolve = !loop.fields?.owner_card_id;
  const canConnect = canResolve && loop.fields?.action === "connect_account";
  return (
    <article className={`loop-item ${loop.status || "open"}`}>
      <div className="loop-head">
        <strong>{loop.text}</strong>
        <span className="tag ask">{loop.status || "open"}</span>
      </div>
      {meta ? <span className="loop-meta">{meta}</span> : null}
      {connection ? (
        <span className="loop-meta">
          {connection.status}: {connection.message || connection.connect_url || connection.name}
        </span>
      ) : null}
      {canResolve ? (
        <div className="loop-actions">
          {canConnect ? <button type="button" onClick={() => onConnect(loop.id)}>Connect</button> : null}
          <button type="button" onClick={() => onResolve(loop.id)}>Done</button>
        </div>
      ) : null}
    </article>
  );
}

export default function Home() {
  const [text, setText] = useState(SAMPLE);
  const [source, setSource] = useState("typed");
  const [executeActions, setExecuteActions] = useState(true);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [cards, setCards] = useState([]);
  const [observed, setObserved] = useState([]);
  const [ignored, setIgnored] = useState(0);
  const [pending, setPending] = useState([]);
  const [loops, setLoops] = useState([]);
  const [remembered, setRemembered] = useState([]);
  // Per-line press-go state keyed by remembered line id: { busy } while in flight,
  // then the engine result (done-with-receipt for a whitelisted action, or the
  // prepared/handback state for a non-whitelisted one). DISPLAY-ONLY; the raw line
  // and inferred task stay visible alongside.
  const [approveResults, setApproveResults] = useState({});
  const [connections, setConnections] = useState({});
  const [tickResult, setTickResult] = useState(null);
  const [events, setEvents] = useState([]);
  const [memoryForm, setMemoryForm] = useState(DEFAULT_MEMORY);
  const [memoryBusy, setMemoryBusy] = useState(false);
  const [memoryResult, setMemoryResult] = useState(null);
  const [memoryError, setMemoryError] = useState("");
  const [profileName, setProfileName] = useState("");
  const [profileSources, setProfileSources] = useState("");
  const [profileBusy, setProfileBusy] = useState(false);
  const [profileResult, setProfileResult] = useState(null);
  const [profileError, setProfileError] = useState("");
  const [access, setAccess] = useState({ checked: false, required: false, authenticated: true });
  const [accessToken, setAccessToken] = useState("");
  const [accessBusy, setAccessBusy] = useState(false);
  const [accessError, setAccessError] = useState("");
  const [engine, setEngine] = useState({
    ok: false,
    label: "checking",
    openLoops: null,
    pendingCount: null,
    extensionConnected: false,
    memoryRecovered: false,
    channels: { status: "mock" },
    readiness: null,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const recognitionRef = useRef(null);

  const buckets = useMemo(() => {
    const next = { ready: [], ask: [], blocked: [], done: [] };
    for (const card of cards) next[cardBucket(card)].push(card);
    return next;
  }, [cards]);
  const pendingByGoal = useMemo(() => {
    const next = new Map();
    for (const ask of pending) {
      if (ask.goal_id) next.set(ask.goal_id, ask);
      if (ask.ask_id) next.set(ask.ask_id, ask);
    }
    return next;
  }, [pending]);
  const matchedPendingIds = useMemo(() => {
    const ids = new Set();
    for (const card of cards) {
      const ask = pendingByGoal.get(card.id) || pendingByGoal.get(card.execution?.ask_id);
      if (ask?.ask_id) ids.add(ask.ask_id);
    }
    return ids;
  }, [cards, pendingByGoal]);
  const unmatchedPending = pending.filter((ask) => !matchedPendingIds.has(ask.ask_id));
  const hasLatestRunStats = observed.length > 0 || ignored > 0;

  function ownerFetch(url, options = {}) {
    return fetch(url, { ...options, credentials: "same-origin" });
  }

  async function requestJson(url, options = {}) {
    const response = await ownerFetch(url, options);
    const data = await response.json().catch(() => ({}));
    handleOwnerAuthFailure(response, data);
    return { ok: response.ok, status: response.status, data };
  }

  function handleOwnerAuthFailure(response, data) {
    if (response.status === 401 && data?.error === "owner_auth_required") {
      setAccess({ checked: true, required: true, authenticated: false });
    }
  }

  async function refreshAccess() {
    const response = await fetch("/api/owner/session", { cache: "no-store", credentials: "same-origin" });
    const data = await response.json().catch(() => ({}));
    const next = {
      checked: true,
      required: Boolean(data.required),
      authenticated: !data.required || Boolean(data.authenticated),
    };
    setAccess(next);
    return next.authenticated;
  }

  async function unlockOwner(event) {
    event.preventDefault();
    setAccessBusy(true);
    setAccessError("");
    try {
      const response = await fetch("/api/owner/session", {
        method: "POST",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token: accessToken }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.message || data.error || "Owner unlock failed");
      setAccessToken("");
      setAccess({
        checked: true,
        required: Boolean(data.required),
        authenticated: !data.required || Boolean(data.authenticated),
      });
      await loadStatus();
    } catch (err) {
      setAccessError(err instanceof Error ? err.message : String(err));
    } finally {
      setAccessBusy(false);
    }
  }

  async function lockOwner() {
    await fetch("/api/owner/session", { method: "DELETE", credentials: "same-origin" });
    setAccess({ checked: true, required: true, authenticated: false });
    setCards([]);
    setPending([]);
    setLoops([]);
    setEvents([]);
  }

  async function loadStatus() {
    const [engineStatus, pendingRes, glassbox, durableCards, activeLoops, rememberedRes] = await Promise.allSettled([
      requestJson("/api/status", { cache: "no-store" }),
      requestJson("/api/pending", { cache: "no-store" }),
      requestJson("/api/glassbox?limit=20", { cache: "no-store" }),
      requestJson("/api/owner/cards?limit=50", { cache: "no-store" }),
      requestJson("/api/memory/open-loops?limit=50", { cache: "no-store" }),
      requestJson("/api/memory/remembered?limit=50", { cache: "no-store" }),
    ]);
    const authBlocked = [engineStatus, pendingRes, glassbox, durableCards, activeLoops, rememberedRes].some(
      (result) => result.status === "fulfilled" && result.value.status === 401,
    );
    if (authBlocked) return;

    if (engineStatus.status === "fulfilled" && engineStatus.value.ok) {
      const data = engineStatus.value.data || {};
      setEngine({
        ok: data.engine === "ok",
        label: data.engine === "ok" ? "engine online" : "engine degraded",
        openLoops: typeof data.open_loop_count === "number" ? data.open_loop_count : null,
        pendingCount: typeof data.pending_count === "number" ? data.pending_count : null,
        extensionConnected: Boolean(data.extension_connected),
        memoryRecovered: Boolean(data.memory_recovered),
        channels: data.channels || { status: "mock" },
        readiness: data.readiness || null,
      });
    } else {
      setEngine({
        ok: false,
        label: "engine offline",
        openLoops: null,
        pendingCount: null,
        extensionConnected: false,
        memoryRecovered: false,
        channels: { status: "mock" },
        readiness: null,
      });
    }
    if (pendingRes.status === "fulfilled") setPending(pendingRes.value.data.pending || []);
    if (glassbox.status === "fulfilled") setEvents(glassbox.value.data.entries || []);
    if (activeLoops.status === "fulfilled") setLoops(activeLoops.value.data.loops || []);
    if (rememberedRes.status === "fulfilled") setRemembered(rememberedRes.value.data.remembered || []);
    if (durableCards.status === "fulfilled") {
      const loadedCards = durableCards.value.data.cards || [];
      setCards((current) => {
        if (!current.length) return loadedCards;
        const loadedById = new Map(loadedCards.map((card) => [card.id, card]));
        const seen = new Set(current.map((card) => card.id));
        const refreshed = current.map((card) => loadedById.get(card.id) || card);
        const newDurableCards = loadedCards.filter((card) => !seen.has(card.id));
        return [...refreshed, ...newDurableCards];
      });
    }
  }

  useEffect(() => {
    let stopped = false;
    let intervalId = null;
    async function boot() {
      const allowed = await refreshAccess();
      if (stopped || !allowed) return;
      await loadStatus();
      if (!stopped) intervalId = setInterval(loadStatus, 5000);
    }
    boot();
    return () => {
      stopped = true;
      if (intervalId) clearInterval(intervalId);
    };
  }, []);

  function applyIngestResult(data) {
    setCards(data.cards || []);
    setObserved(data.observed_lines || []);
    setIgnored(data.ignored_line_count || 0);
  }

  function updateMemoryField(field, value) {
    setMemoryForm((current) => ({ ...current, [field]: value }));
  }

  async function saveMemory() {
    setMemoryBusy(true);
    setMemoryError("");
    try {
      const response = await ownerFetch("/api/owner/onboard", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(onboardingPayload(memoryForm)),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.detail || data.error || "Memory save failed");
      setMemoryResult(data);
      await loadStatus();
    } catch (err) {
      setMemoryError(err instanceof Error ? err.message : String(err));
    } finally {
      setMemoryBusy(false);
    }
  }

  async function buildProfile(event) {
    if (event) event.preventDefault();
    const name = profileName.trim();
    const sources = profileSources
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter((s) => /^https?:\/\//i.test(s));
    if (!name || sources.length === 0) {
      setProfileError("Enter a name and at least one public http(s) URL.");
      return;
    }
    setProfileBusy(true);
    setProfileError("");
    try {
      const response = await ownerFetch("/api/onboarding/profile", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, sources }),
      });
      const data = await response.json().catch(() => ({}));
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.detail || data.error || "Profile build failed");
      setProfileResult(data);
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : String(err));
    } finally {
      setProfileBusy(false);
    }
  }

  async function resolveLoop(loopId) {
    setBusy(true);
    setError("");
    try {
      const response = await ownerFetch("/api/memory/resolve-loop", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: loopId, status: "done" }),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.detail || data.error || "Loop resolve failed");
      setLoops((current) => current.filter((loop) => loop.id !== data.id));
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function approveRemembered(lineId) {
    // Press go on ONE remembered line. The engine is default-deny: it executes only
    // the three whitelisted reversible intents (with its own read-back proof) and hands
    // everything else back. We just render whatever it returns.
    setApproveResults((current) => ({ ...current, [lineId]: { busy: true } }));
    setError("");
    try {
      const response = await ownerFetch("/api/memory/remembered/approve", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ line_id: lineId }),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.detail || data.error || "Press-go failed");
      setApproveResults((current) => ({ ...current, [lineId]: { busy: false, result: data } }));
      await loadStatus();
    } catch (err) {
      setApproveResults((current) => ({
        ...current,
        [lineId]: { busy: false, error: err instanceof Error ? err.message : String(err) },
      }));
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function connectLoop(loopId) {
    setBusy(true);
    setError("");
    try {
      const response = await ownerFetch("/api/connections/authorize", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id: loopId }),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.detail || data.error || "Connection setup failed");
      setConnections((current) => ({ ...current, [loopId]: data }));
      if (data.connect_url) window.open(data.connect_url, "_blank", "noopener,noreferrer");
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function scanLoops() {
    setBusy(true);
    setError("");
    try {
      const response = await ownerFetch("/api/trigger/tick", { method: "POST" });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.detail || data.error || "Proactive scan failed");
      setTickResult(data);
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function runUpload() {
    const form = new FormData();
    form.append("file", uploadedFile);
    form.append("source", source);
    form.append("execute_actions", String(executeActions));
    return ownerFetch("/api/owner/upload", {
      method: "POST",
      body: form,
    });
  }

  async function runIngest() {
    setBusy(true);
    setError("");
    try {
      const response = uploadedFile ? await runUpload() : await ownerFetch("/api/owner/ingest", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          text,
          source,
          execute_actions: executeActions,
          meta: { ui: "owner_mode" },
        }),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) {
        throw new Error(data.message || data.detail || data.error || "Owner ingest failed");
      }
      applyIngestResult(data);
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function resolveAsk(askId, approved) {
    setBusy(true);
    setError("");
    try {
      const response = await ownerFetch("/api/resolve", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ask_id: askId, approved }),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.error || "Resolve failed");
      setPending((current) => current.filter((ask) => ask.ask_id !== askId));
      setCards((current) => current.map((card) => {
        const matched = card.execution?.ask_id === askId || card.execution?.goal_id === data.goal_id;
        if (!matched) return card;
        const nextStatus = data.blocked ? "blocked" : data.approved ? (data.state || "done") : "declined";
        return {
          ...card,
          status: nextStatus,
          execution: {
            ...(card.execution || {}),
            ask_id: null,
            goal_state: nextStatus,
          },
          proof: [
            ...(card.proof || []),
            {
              type: "resolution",
              decision: data.approved ? "approved" : "declined",
              goal_state: nextStatus,
            },
          ],
        };
      }));
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function loadFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploadedFile(file);
    setSource("upload");
    setError("");
    if (file.type.startsWith("text/") || /\.(txt|md|vtt|srt|json|csv)$/i.test(file.name)) {
      setText(await file.text());
    } else {
      setText(`Uploaded ${file.name}. Press Go to transcribe and create task cards.`);
    }
  }

  function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Speech recognition is not available in this browser.");
      return;
    }
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
      return;
    }
    setSource("start_listening");
    setUploadedFile(null);
    setError("");
    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript || "")
        .join(" ");
      setText((current) => `${current.trim()}\n${transcript}`.trim());
    };
    recognition.onend = () => {
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    recognition.start();
  }

  if (!access.checked) {
    return (
      <main className="shell owner-locked">
        <section className="owner-gate">
          <div className="mark">A</div>
          <h1>Anticipy Owner Mode</h1>
          <p>Checking owner access.</p>
        </section>
      </main>
    );
  }

  if (access.required && !access.authenticated) {
    return (
      <main className="shell owner-locked">
        <form className="owner-gate" onSubmit={unlockOwner}>
          <div className="mark">A</div>
          <h1>Anticipy Owner Mode</h1>
          <label className="owner-token-field">
            <span>Owner token</span>
            <input
              autoComplete="current-password"
              autoFocus
              onChange={(event) => setAccessToken(event.target.value)}
              type="password"
              value={accessToken}
            />
          </label>
          <button className="primary" disabled={accessBusy || !accessToken.trim()} type="submit">
            {accessBusy ? "Unlocking" : "Unlock"}
          </button>
          {accessError ? <div className="error">{accessError}</div> : null}
        </form>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="mark">A</div>
          <div>
            <h1>Anticipy Owner Mode</h1>
            <p>Local engine path: input, cards, actions, receipts.</p>
          </div>
        </div>
        <div className="status-strip">
          <span className={`dot ${engine.ok ? "ok" : "bad"}`} />
          <span>{engine.label}</span>
          {typeof engine.openLoops === "number" ? <span>{engine.openLoops} active loops</span> : null}
          {typeof engine.pendingCount === "number" ? <span>{engine.pendingCount} waiting</span> : null}
          {engine.memoryRecovered ? <span>memory recovered</span> : null}
          {access.required ? (
            <button className="quiet-link" onClick={lockOwner} type="button">
              Lock
            </button>
          ) : null}
        </div>
        {engine.readiness ? (
          <div className="readiness-grid" aria-label="System readiness">
            {readinessEntries(engine.readiness).map((item) => (
              <span className={`readiness-pill ${readinessTone(item.state)}`} key={item.key} title={item.label}>
                <strong>{item.name}</strong>
                <small>{item.state}</small>
              </span>
            ))}
          </div>
        ) : null}
      </header>

      <section className="workspace">
        <aside className="panel">
          <div className="panel-head">
            <h2>Input</h2>
            <button
              className="quiet-button"
              onClick={() => {
                setUploadedFile(null);
                setSource("typed");
                setText(SAMPLE);
              }}
            >
              Reset
            </button>
          </div>

          <div className="source-row" role="tablist" aria-label="Input source">
            {sources.map(([value, label]) => (
              <button
                className={source === value ? "active" : ""}
                key={value}
                onClick={() => {
                  setSource(value);
                  if (value !== "upload") setUploadedFile(null);
                }}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>

          <textarea
            className="transcript"
            value={text}
            onChange={(event) => {
              setUploadedFile(null);
              setText(event.target.value);
            }}
            spellCheck="true"
          />

          <div className="control-row">
            <input
              className="file-input"
              type="file"
              accept=".txt,.md,.vtt,.srt,.json,.csv,.mp3,.m4a,.wav,.aac,.flac,.ogg"
              onChange={loadFile}
            />
            <button className="secondary" type="button" onClick={startListening}>
              {recognitionRef.current ? "Stop" : "Listen"}
            </button>
          </div>
          {uploadedFile ? (
            <div className="upload-note">
              <span>Selected</span>
              <strong>{uploadedFile.name}</strong>
              <button className="quiet-link" type="button" onClick={() => setUploadedFile(null)}>
                use typed text
              </button>
            </div>
          ) : null}

          <div className="control-row">
            <label className="toggle">
              <input
                type="checkbox"
                checked={executeActions}
                onChange={(event) => setExecuteActions(event.target.checked)}
              />
              Run safe actions
            </label>
            <button className="primary" type="button" onClick={runIngest} disabled={busy || (!text.trim() && !uploadedFile)}>
              {busy ? "Working" : "Go"}
            </button>
          </div>
          {error ? <div className="error">{error}</div> : null}

          <details className="memory-primer">
            <summary>
              <span>Memory</span>
              {memoryResult ? <small>{memoryResult.written?.length || 0} saved</small> : null}
            </summary>
            <div className="memory-grid">
              <MemoryField
                label="Owner"
                value={memoryForm.ownerName}
                onChange={(value) => updateMemoryField("ownerName", value)}
              />
              <MemoryField
                label="Time zone"
                value={memoryForm.timezone}
                onChange={(value) => updateMemoryField("timezone", value)}
              />
              <MemoryField
                label="Phone"
                value={memoryForm.phone}
                onChange={(value) => updateMemoryField("phone", value)}
              />
              <MemoryField
                label="Email"
                value={memoryForm.email}
                onChange={(value) => updateMemoryField("email", value)}
              />
              <MemoryField
                label="Preferences"
                value={memoryForm.preferences}
                onChange={(value) => updateMemoryField("preferences", value)}
                multiline
              />
              <MemoryField
                label="People"
                value={memoryForm.people}
                onChange={(value) => updateMemoryField("people", value)}
                multiline
              />
              <MemoryField
                label="Apps"
                value={memoryForm.connections}
                onChange={(value) => updateMemoryField("connections", value)}
                multiline
              />
              <MemoryField
                label="Stores"
                value={memoryForm.stores}
                onChange={(value) => updateMemoryField("stores", value)}
                multiline
              />
              <MemoryField
                label="Notes"
                value={memoryForm.notes}
                onChange={(value) => updateMemoryField("notes", value)}
                multiline
              />
            </div>
            <div className="control-row">
              <button className="secondary" type="button" onClick={saveMemory} disabled={memoryBusy}>
                {memoryBusy ? "Saving" : "Save memory"}
              </button>
              {memoryResult?.missing_connections?.length ? (
                <span className="memory-result">Missing: {memoryResult.missing_connections.join(", ")}</span>
              ) : memoryResult ? (
                <span className="memory-result">Memory saved</span>
              ) : null}
            </div>
            {memoryError ? <div className="error">{memoryError}</div> : null}
          </details>

          <details className="memory-primer">
            <summary>
              <span>Build my profile</span>
              {profileResult ? <small>{profileResult.summary?.facts || 0} facts</small> : null}
            </summary>
            <form className="profile-form" onSubmit={buildProfile}>
              <MemoryField
                label="Name or entity"
                value={profileName}
                onChange={setProfileName}
                placeholder="e.g. Ada Lovelace"
              />
              <MemoryField
                label="Public source URLs (one per line)"
                value={profileSources}
                onChange={setProfileSources}
                placeholder="https://en.wikipedia.org/wiki/Ada_Lovelace"
                multiline
              />
              <div className="control-row">
                <button className="secondary" type="submit" disabled={profileBusy}>
                  {profileBusy ? "Reading" : "Build my profile"}
                </button>
                <span className="memory-result">Read-only, public pages — no login, no writes.</span>
              </div>
            </form>
            {profileError ? <div className="error">{profileError}</div> : null}
            {profileResult ? <ProfileView profile={profileResult} /> : null}
          </details>
        </aside>

        <section className="board">
          <div className="board-title">
            <h2>Task Board</h2>
            <button className="secondary" type="button" onClick={loadStatus}>
              Refresh
            </button>
          </div>

          <div className="metrics">
            <div className="metric">
              <strong>{hasLatestRunStats ? observed.length : "—"}</strong>
              <span>latest run lines</span>
            </div>
            <div className="metric">
              <strong>{cards.length}</strong>
              <span>visible cards</span>
            </div>
            <div className="metric">
              <strong>{pending.length}</strong>
              <span>waiting asks</span>
            </div>
            <div className="metric">
              <strong>{buckets.blocked.length}</strong>
              <span>hard walls</span>
            </div>
            <div className="metric">
              <strong>{hasLatestRunStats ? ignored : "—"}</strong>
              <span>latest ignored</span>
            </div>
          </div>

          <div className="columns">
            <div className="task-column">
              <h3>Ready</h3>
              {buckets.ready.length ? buckets.ready.map((card) => <TaskCard card={card} key={card.id} />) : (
                <div className="empty">No ready cards.</div>
              )}
            </div>
            <div className="task-column">
              <h3>Needs Omar</h3>
              {buckets.ask.map((card) => (
                <TaskCard
                  card={card}
                  key={card.id}
                  pendingAsk={pendingByGoal.get(card.id) || pendingByGoal.get(card.execution?.ask_id)}
                  onResolve={resolveAsk}
                />
              ))}
              {unmatchedPending.map((ask) => (
                <PendingAsk ask={ask} key={ask.ask_id} onResolve={resolveAsk} />
              ))}
              {!unmatchedPending.length && !buckets.ask.length ? <div className="empty">No asks waiting.</div> : null}
            </div>
            <div className="task-column">
              <h3>Blocked</h3>
              {buckets.blocked.length ? buckets.blocked.map((card) => <TaskCard card={card} key={card.id} />) : (
                <div className="empty">No blocked cards.</div>
              )}
            </div>
            <div className="task-column">
              <h3>Done</h3>
              {buckets.done.length ? buckets.done.map((card) => <TaskCard card={card} key={card.id} />) : (
                <div className="empty">No receipts yet.</div>
              )}
            </div>
          </div>

          <section className="ledger">
            <div className="ledger-head">
              <h2>Active Loops</h2>
              <div className="ledger-actions">
                <span className="status-strip">{loops.length} visible</span>
                <button className="secondary" type="button" onClick={scanLoops} disabled={busy}>
                  Scan
                </button>
              </div>
            </div>
            {tickResult ? (
              <div className="scan-result">
                <span>
                  Proactive scan: {(tickResult.fired || []).length} loop{(tickResult.fired || []).length === 1 ? "" : "s"} fired.
                </span>
                {(tickResult.fired || []).length ? (
                  <div className="scan-fired">
                    {(tickResult.fired || []).map((item, index) => (
                      <span key={item.loop_id || `${item.task || "loop"}-${index}`}>
                        {firedLoopText(item)}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            <div className="loop-list">
              {loops.length ? loops.map((loop) => (
                <MemoryLoop
                  loop={loop}
                  key={loop.id}
                  onConnect={connectLoop}
                  onResolve={resolveLoop}
                  connection={connections[loop.id]}
                />
              )) : <div className="empty">No active memory loops.</div>}
            </div>
          </section>

          <section className="ledger">
            <div className="ledger-head">
              <h2>Review — what you said you&apos;d do</h2>
              <span className="status-strip">{remembered.length} remembered</span>
            </div>
            <div className="loop-list">
              {remembered.length ? remembered.map((row, index) => {
                // DISPLAY-ONLY inference: the inferred task is shown ABOVE the raw line.
                // The raw line stays visible as the ground truth the owner can check.
                const inf = row.inferred;
                const hasTask = inf && inf.task;
                const conf = inf && inf.confidence;
                // Press-go is offered only for a confident inferred task (a real line,
                // not a vent). The engine still re-infers and is default-deny.
                const canApprove = Boolean(row.id) && hasTask && conf && conf !== "low";
                const ar = row.id ? approveResults[row.id] : undefined;
                const res = ar && ar.result;
                return (
                <article className="card" key={row.id || `${row.ts || "remembered"}-${index}`}>
                  <div className="card-head">
                    {hasTask
                      ? <h4 className="inferred-task">{inf.task}</h4>
                      : <h4>{row.text}</h4>}
                    {row.ts ? <span className="status-strip">{formatRememberTs(row.ts)}</span> : null}
                  </div>
                  {hasTask ? (
                    <p className="inferred-raw" title="What you actually said (ground truth)">
                      <span className="inferred-raw-label">you said</span> {row.text}
                    </p>
                  ) : null}
                  {(conf || (inf && inf.due_phrase) || (inf && inf.people && inf.people.length)) ? (
                    <div className="inferred-meta">
                      {conf ? <span className={`conf conf-${conf}`}>{conf} confidence</span> : null}
                      {inf && inf.due_phrase ? <span className="conf-due">{inf.due_phrase}</span> : null}
                      {inf && inf.people && inf.people.length
                        ? <span className="conf-people">{inf.people.join(", ")}</span> : null}
                    </div>
                  ) : null}
                  {(row.source || (row.people && row.people.length)) ? (
                    <div className="loop-meta">
                      {[row.source, (row.people || []).join(", ")].filter(Boolean).join(" / ")}
                    </div>
                  ) : null}
                  {canApprove ? (
                    <div className="approve-row">
                      {!res ? (
                        <button
                          type="button"
                          className="approve-btn"
                          onClick={() => approveRemembered(row.id)}
                          disabled={ar && ar.busy}
                        >
                          {ar && ar.busy ? "Working…" : "Approve & do it"}
                        </button>
                      ) : res.executed ? (
                        // Whitelisted reversible action ran: show the read-back receipt.
                        <div className="approve-done">
                          <span className="approve-badge done">Done{res.idempotent ? " (already)" : ""}</span>
                          <span className="approve-what">{res.would_do || res.intent}</span>
                          {res.receipt && Object.keys(res.receipt).length ? (
                            <pre className="approve-receipt">{JSON.stringify(res.receipt, null, 2)}</pre>
                          ) : null}
                        </div>
                      ) : res.prepared ? (
                        // Non-whitelisted: prepared and handed back, never executed.
                        <div className="approve-handback">
                          <span className="approve-badge handback">Prepared — your turn</span>
                          <span className="approve-what">{res.would_do || res.inferred_action || res.intent}</span>
                          {res.why_handback ? (
                            <span className="approve-why">{res.why_handback}</span>
                          ) : null}
                        </div>
                      ) : (
                        // Refused at the engine (e.g. re-inferred as a vent): no action.
                        <div className="approve-handback">
                          <span className="approve-badge handback">Not acted on</span>
                          <span className="approve-why">{res.reason || "no confident task"}</span>
                        </div>
                      )}
                      {ar && ar.error ? <span className="approve-why">{ar.error}</span> : null}
                    </div>
                  ) : null}
                </article>
                );
              }) : <div className="empty">Nothing remembered yet.</div>}
            </div>
          </section>

          <section className="ledger">
            <div className="ledger-head">
              <h2>Receipts</h2>
              <span className="status-strip">{events.length} events</span>
            </div>
            <div className="events">
              {events.length ? events.map((entry, index) => (
                <div className="event" key={`${entry.ts || index}-${entry.kind || "event"}`}>
                  <strong>{entry.kind || "event"}</strong>
                  <span title={JSON.stringify(entry)}>{receiptText(entry)}</span>
                </div>
              )) : <div className="empty">No engine events loaded.</div>}
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}
