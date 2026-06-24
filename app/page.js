"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const SAMPLE = "";

const DEFAULT_MEMORY = {
  ownerName: "",
  timezone: "America/Vancouver",
  phone: "",
  email: "",
  preferences: "",
  people: "",
  connections: "",
  stores: "",
  notes: "",
};

const MODES = [
  ["typed", "Type"],
  ["transcript", "Paste"],
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

// Which human section a card belongs to. The engine's own disposition/status is the
// source of truth — this only chooses how to GROUP it for a person to read.
function sectionOf(card) {
  if (card.status === "declined") return "remember"; // you said no; it lives as a note
  if (card.disposition === "blocked" || card.status === "blocked") return "blocked";
  if (card.disposition === "remember") return "remember";
  if (card.disposition === "ask" || card.status === "waiting") return "ask";
  if (card.status === "done") return "done";
  return "doing";
}

// Kept for the durable-card refresh/merge logic below (server cards carry status only).
function cardBucket(card) {
  if (card.status === "declined") return "done";
  if (card.status === "done" || card.disposition === "remember") return "done";
  if (card.disposition === "blocked" || card.status === "blocked") return "blocked";
  if (card.disposition === "ask" || card.status === "waiting") return "ask";
  return "ready";
}

function lowerFirst(value) {
  const s = (value || "").trim();
  return s ? s[0].toLowerCase() + s.slice(1) : s;
}

function isInternalText(text) {
  if (!text) return true;
  const markers = ["fail-safe", "\u2192", "->", "low-confidence", "confirm before", "cannot confirm", "memory "];
  return markers.some((m) => text.toLowerCase().includes(m));
}

function humanizeText(text) {
  if (!text || isInternalText(text)) return null;
  let t = text.replace(/^(Confirm task|Follow up|Confirm):?\s*/i, "").trim();
  if (!t) return null;
  return t[0].toUpperCase() + t.slice(1);
}

function humanCopy(text, fallback = "") {
  return humanizeText(text) || fallback;
}

function cardSourceLine(card) {
  return humanCopy(card?.source_text, "");
}

function humanWhy(ask) {
  return humanCopy(ask?.reason || ask?.action, "I wanted to check first.");
}

function loopTitle(loop) {
  return humanCopy(loop?.text, "Something to keep an eye on.");
}

function spokenLine(card) {
  const section = sectionOf(card);
  if (section === "blocked") {
    return "This touches money, so I stopped. The actual payment is always yours.";
  }
  if (card.disposition === "remember") {
    const fact = (card.title || "").replace(/^remember:?\s*/i, "").trim();
    return fact ? `Noted \u2014 ${lowerFirst(fact)}` : "Noted.";
  }
  switch (card.action) {
    case "create_calendar_or_reminder":
    case "create_reminder":
    case "schedule_event":
      return "I'll set a reminder so this doesn't slip.";
    case "draft_or_confirm_message":
    case "draft_message":
    case "send_message":
      return "I've drafted the message \u2014 say the word and I'll send it.";
    case "find_or_cart_without_purchase":
      return "I'll find it and put it in the cart. I won't check out.";
    case "prepare_purchase_path_without_payment":
      return "I'll get it ready to buy, then stop before paying.";
    case "write_profile_memory":
      return "Noted \u2014 that helps me get you right.";
    default: {
      const title = humanizeText(card.title);
      if (title) return title;
      const src = humanizeText(card.source_text);
      if (src) return src;
      return "I'll take care of this.";
    }
  }
}

// Short, plain-language outcome chip for a card.
function chipFor(card, pendingAsk) {
  const section = sectionOf(card);
  if (card.status === "declined") return { cls: "calm", text: "You said no" };
  if (section === "blocked") return { cls: "blocked", text: "Stopped at money" };
  if (section === "ask") return { cls: "ask", text: pendingAsk ? "Needs your okay" : "Waiting on you" };
  if (card.disposition === "remember") return { cls: "remember", text: "Remembered" };
  if (card.status === "failed") return { cls: "ask", text: "Needs a connected account" };
  if (section === "done") return { cls: "do", text: "Done" };
  return { cls: "do", text: "Ready" };
}

function proofValue(proof) {
  if (!proof) return "";
  if (proof.type === "memory_resolution") return [proof.item, proof.site].filter(Boolean).join(" @ ");
  if (proof.type === "browser_receipt") return [proof.answer || "browser verified", proof.url].filter(Boolean).join(" @ ");
  if (proof.decision) return [proof.decision, proof.goal_state].filter(Boolean).join(" / ");
  if (proof.memory_id) return proof.memory_id;
  if (proof.path) return proof.path;
  if (proof.type) return proof.type;
  return "";
}

// A single human-readable receipt line for a card, if the engine left proof.
function receiptLine(card) {
  const proofs = Array.isArray(card.proof) ? card.proof : [];
  const human = proofs.find((p) => p?.type === "memory_resolution" || p?.type === "browser_receipt");
  const value = proofValue(human);
  if (value) return value;
  const goalState = card.execution?.goal_state;
  if (goalState && !["waiting", "blocked", "done", "declined", "failed", "ready"].includes(goalState)) {
    return goalState;
  }
  return "";
}

function receiptText(entry) {
  return humanCopy(entry?.summary || entry?.message, "Updated.");
}

function firedLoopText(item) {
  const pieces = [item.task || item.text || "loop", item.decision || "checked"];
  if (item.category) pieces.push(item.category);
  return pieces.join(" — ");
}

function formatRememberTs(ts) {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds)) return "";
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

function loopMeta(loop) {
  const fields = loop.fields || {};
  return [fields.route, fields.action, fields.disposition || fields.kind]
    .filter(Boolean)
    .join(" — ");
}

const SECTION_META = {
  doing: { title: "I'm taking care of these" },
  ask: { title: "Just need your okay" },
  blocked: { title: "I stopped at money" },
  remember: { title: "Worth remembering" },
};
const SECTION_ORDER = ["doing", "ask", "blocked", "remember"];

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
          <span className="ant-pill" title="No browser arm was available, so nothing was scraped. No facts were invented.">
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
      {facts.length ? (
        <ul className="profile-facts">
          {facts.map((fact, index) => (
            <li className="profile-fact" key={`${fact.field}-${index}`}>
              <div className="profile-fact-head">
                <span className="profile-field">{fact.field}</span>
                {fact.needs_cross_check ? (
                  <span className="ant-pill" title="Low-trust single-page pull — confirm with a second source.">
                    needs cross-check
                  </span>
                ) : (
                  <span className="ant-pill">{fact.confidence || fact.trust}</span>
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
          <span className="profile-field">Couldn&apos;t read</span>
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

// One card, rendered as a calm row with a colored rail + first-person line.
function Item({ card, pendingAsk, onResolve }) {
  const section = sectionOf(card);
  const chip = chipFor(card, pendingAsk);
  const receipt = receiptLine(card);
  const ask = pendingAsk;
  return (
    <article className={`ant-item ${section}`}>
      <p className="ant-item-action">{spokenLine(card)}</p>
      {cardSourceLine(card) ? <p className="ant-quote">{cardSourceLine(card)}</p> : null}
      <div className="ant-item-foot">
        <span className={`ant-chip ${chip.cls}`}>{chip.text}</span>
        {receipt ? <span className="ant-receipt">{receipt}</span> : null}
      </div>
      {ask ? (
        <div className="ant-actions">
          <button className="ant-yes" onClick={() => onResolve(ask.ask_id, true)}>Yes, go ahead</button>
          <button className="ant-no" onClick={() => onResolve(ask.ask_id, false)}>Not now</button>
        </div>
      ) : null}
    </article>
  );
}

function humanAskText(ask) {
  const action = humanizeText(ask.action);
  if (action) return action;
  const reason = humanWhy(ask);
  if (reason) return reason;
  return "I need your go-ahead on something.";
}

function AskItem({ ask, onResolve }) {
  return (
    <article className="ant-item ask">
      <p className="ant-item-action">{humanAskText(ask)}</p>
      <div className="ant-item-foot">
        <span className="ant-chip ask">Needs your okay</span>
      </div>
      <div className="ant-actions">
        <button className="ant-yes" onClick={() => onResolve(ask.ask_id, true)}>Yes, go ahead</button>
        <button className="ant-no" onClick={() => onResolve(ask.ask_id, false)}>Not now</button>
      </div>
    </article>
  );
}

export default function Home() {
  const [text, setText] = useState("");
  const [source, setSource] = useState("typed");
  const [executeActions, setExecuteActions] = useState(true);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [cards, setCards] = useState([]);
  const [observed, setObserved] = useState([]);
  const [ignored, setIgnored] = useState(0);
  const [pending, setPending] = useState([]);
  const [loops, setLoops] = useState([]);
  const [remembered, setRemembered] = useState([]);
  const [approveResults, setApproveResults] = useState({});
  const [previewResults, setPreviewResults] = useState({});
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
  const [hasRun, setHasRun] = useState(false);
  const [error, setError] = useState("");
  const recognitionRef = useRef(null);

  // ─── Deepgram real-time listen state ───
  const [listening, setListening] = useState(false);
  const [liveSegments, setLiveSegments] = useState([]);   // [{speaker, text, isFinal}]
  const [interimText, setInterimText] = useState("");
  const [listenProcessing, setListenProcessing] = useState(false);
  const [anticipation, setAnticipation] = useState("");
  const listenWsRef = useRef(null);
  const audioCtxRef = useRef(null);
  const mediaStreamRef = useRef(null);

  const sections = useMemo(() => {
    const next = { doing: [], ask: [], blocked: [], remember: [], done: [] };
    for (const card of cards) {
      const s = sectionOf(card);
      (next[s] || next.done).push(card);
    }
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
  // Lines the engine saw but chose to leave alone (vents, sarcasm, narration).
  const cardLineNos = useMemo(() => new Set(cards.map((c) => c.line_no)), [cards]);
  const leftAlone = useMemo(
    () => observed.filter((line) => !cardLineNos.has(line.line_no)),
    [observed, cardLineNos],
  );
  const hasResult = cards.length > 0 || leftAlone.length > 0;
  const askCount = sections.ask.length + unmatchedPending.length;

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
        label: data.engine === "ok" ? "listening" : "engine degraded",
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

  const resultsRef = useRef(null);
  function applyIngestResult(data) {
    setCards(data.cards || []);
    setObserved(data.observed_lines || []);
    setIgnored(data.ignored_line_count || 0);
    setHasRun(true);
    // Auto-scroll to results
    setTimeout(() => {
      if (resultsRef.current) {
        resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 100);
    // Anticipatory research: find people mentioned in cards and research them
    const allCards = data.cards || [];
    const peopleSet = new Set();
    for (const card of allCards) {
      // Check args.person (single person from triage)
      if (card.args?.person) peopleSet.add(card.args.person);
      // Check args.people (array)
      const people = card.people || card.args?.people || [];
      for (const p of (Array.isArray(people) ? people : [])) {
        if (p && p.length > 1) peopleSet.add(p);
      }
      // Extract names from task_text as fallback
      const taskText = card.args?.task_text || card.text || "";
      const nameMatches = taskText.match(/\b[A-Z][a-z]{2,}\b/g) || [];
      const skipNames = new Set(["Send", "Get", "Put", "Set", "Call", "Tell", "Ask", "Pay", "Buy", "Order", "Pick", "Drop", "The", "This", "That", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]);
      for (const n of nameMatches) {
        if (!skipNames.has(n)) peopleSet.add(n);
      }
    }
    if (peopleSet.size > 0) {
      const people = Array.from(peopleSet);
      fetch("/api/anticipate/research", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: people[0], task_context: text, people }),
      })
        .then((r) => r.json())
        .then((res) => {
          if (res.notification) {
            setAnticipation(res.notification);
          }
        })
        .catch(() => {});
    }
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
    const profileUrls = profileSources
      .split(/[\n,]/)
      .map((s) => s.trim())
      .filter((s) => /^https?:\/\//i.test(s));
    if (!name || profileUrls.length === 0) {
      setProfileError("Enter a name and at least one public http(s) URL.");
      return;
    }
    setProfileBusy(true);
    setProfileError("");
    try {
      const response = await ownerFetch("/api/onboarding/profile", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, sources: profileUrls }),
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

  async function previewRemembered(lineId) {
    setPreviewResults((current) => ({ ...current, [lineId]: { busy: true } }));
    setError("");
    try {
      const response = await ownerFetch("/api/memory/remembered/dryrun", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ line_id: lineId }),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.detail || data.error || "Dry-run failed");
      setPreviewResults((current) => ({ ...current, [lineId]: { busy: false, result: data } }));
    } catch (err) {
      setPreviewResults((current) => ({
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
      setText(`Uploaded ${file.name}. Hand it to me and I'll listen through it.`);
    }
  }

  async function startDeepgramListen() {
    if (listening) {
      stopDeepgramListen();
      return;
    }
    setError("");
    setListenProcessing(false);
    setLiveSegments([]);
    setInterimText("");

    try {
      // Get engine WebSocket URL
      const res = await fetch("/api/listen/stream");
      const { ws_url } = await res.json();

      // Request mic access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true },
      });
      mediaStreamRef.current = stream;

      // Create AudioContext at 16kHz for linear16 PCM
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;
      const mic = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);

      // Connect WebSocket to engine
      const ws = new WebSocket(ws_url);
      listenWsRef.current = ws;

      ws.onopen = () => {
        setListening(true);
        setSource("start_listening");
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "transcript") {
            if (msg.is_final && msg.transcript.trim()) {
              const newSegs = (msg.segments || []).map((s) => ({
                speaker: s.speaker,
                text: s.text,
                isFinal: true,
              }));
              if (newSegs.length) {
                setLiveSegments((prev) => [...prev, ...newSegs]);
              } else {
                setLiveSegments((prev) => [...prev, { speaker: null, text: msg.transcript, isFinal: true }]);
              }
              setInterimText("");
            } else if (!msg.is_final) {
              setInterimText(msg.transcript);
            }
          } else if (msg.type === "utterance_end") {
            // Visual break indicator
            setLiveSegments((prev) => [...prev, { speaker: -1, text: "---", isFinal: true, isBreak: true }]);
          } else if (msg.type === "processing") {
            setListenProcessing(true);
          } else if (msg.type === "ingest_result") {
            setListenProcessing(false);
            const data = msg.result;
            applyIngestResult(data);
          } else if (msg.type === "ingest_error") {
            setListenProcessing(false);
            setError(msg.error || "Listen ingest failed");
          } else if (msg.type === "error") {
            setError(msg.message || "Listen error");
            stopDeepgramListen();
          }
        } catch (parseErr) {
          // ignore non-JSON
        }
      };

      ws.onerror = () => {
        setError("Listen connection failed — is the engine running?");
        stopDeepgramListen();
      };

      ws.onclose = () => {
        setListening(false);
      };

      // Stream audio to WebSocket as linear16 PCM
      processor.onaudioprocess = (audioEvent) => {
        if (ws.readyState !== WebSocket.OPEN) return;
        const float32 = audioEvent.inputBuffer.getChannelData(0);
        const int16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
          int16[i] = Math.max(-32768, Math.min(32767, float32[i] * 32768));
        }
        ws.send(int16.buffer);
      };

      mic.connect(processor);
      processor.connect(audioCtx.destination);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      stopDeepgramListen();
    }
  }

  function stopDeepgramListen() {
    if (listenWsRef.current) {
      try { listenWsRef.current.close(); } catch (e) { /* */ }
      listenWsRef.current = null;
    }
    if (audioCtxRef.current) {
      try { audioCtxRef.current.close(); } catch (e) { /* */ }
      audioCtxRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    setListening(false);
  }

  // Keep old Web Speech API as fallback
  function startListening() {
    startDeepgramListen();
  }

  function onModeClick(value) {
    if (value === "start_listening") {
      startListening();
      return;
    }
    setSource(value);
    if (value !== "upload") setUploadedFile(null);
  }

  if (!access.checked) {
    return (
      <main className="ant-gate-wrap">
        <section className="ant-gate">
          <div className="mark">A</div>
          <h1>One moment</h1>
          <p>Checking that it&apos;s you.</p>
        </section>
      </main>
    );
  }

  if (access.required && !access.authenticated) {
    return (
      <main className="ant-gate-wrap">
        <form className="ant-gate" onSubmit={unlockOwner}>
          <div className="mark">A</div>
          <h1>Welcome back</h1>
          <p>Enter your owner key to pick up where you left off.</p>
          <label>
            <span>Owner key</span>
            <input
              autoComplete="current-password"
              autoFocus
              onChange={(event) => setAccessToken(event.target.value)}
              type="password"
              value={accessToken}
            />
          </label>
          <button className="ant-primary" disabled={accessBusy || !accessToken.trim()} type="submit">
            {accessBusy ? "Unlocking…" : "Unlock"}
          </button>
          {accessError ? <div className="ant-error">{accessError}</div> : null}
        </form>
      </main>
    );
  }

  return (
    <main className="ant">
      <div className="ant-wrap">
        <header className="ant-hero">
          <span className="ant-status">
            <span className={`dot ${engine.ok ? "ok" : "bad"}`} />
            {listening ? "Listening" : engine.ok ? "Ready" : engine.label}
            {access.required ? (
              <>
                {" · "}
                <button className="ant-quiet-link" onClick={lockOwner} type="button">lock</button>
              </>
            ) : null}
          </span>
          <h1>{memoryForm.ownerName ? `Hey ${memoryForm.ownerName}` : "Hey there"}</h1>
          <p className="ant-hero-sub">
            Talk, and I&apos;ll handle the rest.
          </p>
        </header>

        {/* ─── THE BIG LISTEN BUTTON ─── */}
        <section className="ant-listen-hero">
          <button
            className={`ant-listen-btn ${listening ? "active" : ""}`}
            type="button"
            onClick={startDeepgramListen}
          >
            <span className="ant-listen-icon">
              {listening ? (
                <svg viewBox="0 0 24 24" fill="currentColor" width="48" height="48">
                  <rect x="6" y="6" width="12" height="12" rx="2" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" fill="currentColor" width="48" height="48">
                  <path d="M12 1a4 4 0 0 1 4 4v7a4 4 0 0 1-8 0V5a4 4 0 0 1 4-4z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2H3v2a9 9 0 0 0 8 8.94V23h2v-2.06A9 9 0 0 0 21 12v-2h-2z" />
                </svg>
              )}
            </span>
            <span className="ant-listen-label">{listening ? "Stop" : "Listen"}</span>
          </button>
          {listening ? (
            <span className="ant-listen-pulse">
              <span /><span /><span />
            </span>
          ) : (
            <span className="ant-listen-hint">Just talk — I&apos;ll hear what matters</span>
          )}
        </section>

        {/* ─── LIVE TRANSCRIPT ─── */}
        {(listening || liveSegments.length > 0) ? (
          <section className="ant-live-transcript">
            <h2 className="ant-section-title">Live transcript</h2>
            <div className="ant-transcript-body">
              {liveSegments.map((seg, i) => (
                seg.isBreak ? (
                  <div key={`brk-${i}`} className="ant-transcript-break" />
                ) : (
                  <div key={`seg-${i}`} className={`ant-transcript-line ${seg.isFinal ? "final" : "interim"}`}>
                    {seg.speaker !== null && seg.speaker >= 0 ? (
                      <span className={`ant-speaker speaker-${seg.speaker % 4}`}>
                        {seg.speaker === 0 ? "You" : `Speaker ${seg.speaker}`}
                      </span>
                    ) : null}
                    <span className="ant-transcript-text">{seg.text}</span>
                  </div>
                )
              ))}
              {interimText ? (
                <div className="ant-transcript-line interim">
                  <span className="ant-transcript-text">{interimText}</span>
                </div>
              ) : null}
              {listenProcessing ? (
                <div className="ant-thinking">
                  <span className="dots"><i /><i /><i /></span>
                  Processing what I heard…
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        {/* ─── SECONDARY INPUTS: Paste / Type / Upload ─── */}
        <details className="ant-fold ant-input-fold" open={!listening && !hasRun && liveSegments.length === 0}>
          <summary>
            <span>Or type / paste / upload</span>
            <small></small>
          </summary>
          <div className="ant-fold-body">
            <section className="ant-input-card">
              <div className="ant-modes">
                {[["typed", "Type"], ["transcript", "Paste"], ["upload", "Upload"]].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={source === value ? "active" : ""}
                    onClick={() => { setSource(value); if (value !== "upload") setUploadedFile(null); }}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <textarea
                className="ant-textarea"
                value={text}
                placeholder="Paste a conversation, a day's transcript, or just type what happened."
                onChange={(event) => {
                  setUploadedFile(null);
                  setText(event.target.value);
                }}
                spellCheck="true"
              />

              {source === "upload" ? (
                <div className="ant-file-row">
                  <input
                    type="file"
                    accept=".txt,.md,.vtt,.srt,.json,.csv,.mp3,.m4a,.wav,.aac,.flac,.ogg"
                    onChange={loadFile}
                  />
                </div>
              ) : null}
              {uploadedFile ? (
                <div className="ant-upload-note">
                  <span>Picked</span>
                  <strong>{uploadedFile.name}</strong>
                  <button className="ant-quiet-link" type="button" onClick={() => setUploadedFile(null)}>
                    use typed text instead
                  </button>
                </div>
              ) : null}

              <div className="ant-input-foot">
                <button
                  className="ant-quiet-link"
                  type="button"
                  onClick={() => {
                    setUploadedFile(null);
                    setSource("typed");
                    setText("");
                  }}
                >
                  clear
                </button>
                <span className="spacer" />
                <label className="ant-status" title="Let me carry out the safe, reversible ones on my own.">
                  <input
                    type="checkbox"
                    checked={executeActions}
                    onChange={(event) => setExecuteActions(event.target.checked)}
                  />
                  act on the safe ones
                </label>
                <button
                  className="ant-primary"
                  type="button"
                  onClick={runIngest}
                  disabled={busy || (!text.trim() && !uploadedFile)}
                >
                  {busy ? "Thinking…" : "Hand it to me"}
                </button>
              </div>
              {error ? <div className="ant-error">{error}</div> : null}
            </section>
          </div>
        </details>

        {!hasRun ? (
          <a className="ant-nudge" href="/onboarding">
            <span className="ant-nudge-emoji">+</span>
            <span className="ant-nudge-body">
              <strong>Set up your profile</strong>
              <span>I&apos;ll learn who matters to you and how to help.</span>
            </span>
            <span className="ant-nudge-arrow" aria-hidden="true"></span>
          </a>
        ) : null}

        {busy && !hasResult ? (
          <div className="ant-thinking">
            <span className="dots"><i /><i /><i /></span>
            Reading through your day…
          </div>
        ) : null}

        {hasResult ? (
          <section className="ant-response" ref={resultsRef}>
          {anticipation && (
            <div style={{
              background: "linear-gradient(135deg, #f0f9ff 0%, #e8f4f8 100%)",
              borderLeft: "3px solid #0ea5e9",
              padding: "12px 16px",
              borderRadius: "8px",
              marginBottom: "16px",
              fontSize: "14px",
              color: "#0c4a6e",
              lineHeight: "1.5",
            }}>
              <strong style={{fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.5px", opacity: 0.7}}>
                Anticipatory research
              </strong>
              <div style={{marginTop: "4px"}}>{anticipation}</div>
            </div>
          )}
            {hasRun ? (
              <p className="ant-recap">
                {observed.length} thing{observed.length === 1 ? "" : "s"} heard
                {sections.doing.length ? ` · ${sections.doing.length} handling` : ""}
                {askCount ? ` · ${askCount} need${askCount === 1 ? "s" : ""} you` : ""}
                {sections.blocked.length ? ` · ${sections.blocked.length} stopped` : ""}
                {leftAlone.length ? ` · ${leftAlone.length} left alone` : ""}
              </p>
            ) : null}

            {SECTION_ORDER.map((key) => {
              const items = sections[key];
              const extra = key === "ask" ? unmatchedPending : [];
              if (!items.length && !extra.length) return null;
              return (
                <div className="ant-group" key={key}>
                  <div className="ant-group-head">
                    <h2>{SECTION_META[key].title}</h2>
                    <span className="count">{items.length + extra.length}</span>
                  </div>
                  {items.map((card) => (
                    <Item
                      card={card}
                      key={card.id}
                      pendingAsk={pendingByGoal.get(card.id) || pendingByGoal.get(card.execution?.ask_id)}
                      onResolve={resolveAsk}
                    />
                  ))}
                  {extra.map((ask) => (
                    <AskItem ask={ask} key={ask.ask_id} onResolve={resolveAsk} />
                  ))}
                </div>
              );
            })}

            {leftAlone.length ? (
              <div className="ant-group">
                <div className="ant-group-head">
                  <h2>I left these alone</h2>
                  <span className="count">{leftAlone.length}</span>
                </div>
                {leftAlone.map((line) => (
                  <article className="ant-item calm" key={`vent-${line.line_no}`}>
                    <p className="ant-quote">{line.text}</p>
                    <div className="ant-item-foot">
                      <span className="ant-chip calm">Just venting — not a task</span>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </section>
        ) : (
          !busy ? <p className="ant-empty">Nothing to show yet — hand me your day above.</p> : null
        )}

        <div className="ant-more">
          <div className="ant-more-label">Settings</div>
          <details className="ant-fold">
            <summary>
              <span>What I know about you</span>
              <small>{memoryResult ? `${memoryResult.written?.length || 0} saved` : "edit"}</small>
            </summary>
            <div className="ant-fold-body">
              <div className="memory-grid">
                <MemoryField label="Your name" value={memoryForm.ownerName} onChange={(v) => updateMemoryField("ownerName", v)} />
                <MemoryField label="Time zone" value={memoryForm.timezone} onChange={(v) => updateMemoryField("timezone", v)} />
                <MemoryField label="Phone" value={memoryForm.phone} onChange={(v) => updateMemoryField("phone", v)} />
                <MemoryField label="Email" value={memoryForm.email} onChange={(v) => updateMemoryField("email", v)} />
                <MemoryField label="How I should behave" value={memoryForm.preferences} onChange={(v) => updateMemoryField("preferences", v)} multiline />
                <MemoryField label="People who matter" value={memoryForm.people} onChange={(v) => updateMemoryField("people", v)} multiline />
                <MemoryField label="Apps & accounts" value={memoryForm.connections} onChange={(v) => updateMemoryField("connections", v)} multiline />
                <MemoryField label="Stores I use" value={memoryForm.stores} onChange={(v) => updateMemoryField("stores", v)} multiline />
                <MemoryField label="Anything else" value={memoryForm.notes} onChange={(v) => updateMemoryField("notes", v)} multiline />
              </div>
              <div className="ant-fold-foot">
                <button className="ant-ghost" type="button" onClick={saveMemory} disabled={memoryBusy}>
                  {memoryBusy ? "Saving…" : "Save"}
                </button>
                {memoryResult?.missing_connections?.length ? (
                  <span className="ant-inline-note">Still needs: {memoryResult.missing_connections.join(", ")}</span>
                ) : memoryResult ? (
                  <span className="ant-inline-note">Saved.</span>
                ) : null}
              </div>
              {memoryError ? <div className="ant-error">{memoryError}</div> : null}
            </div>
          </details>

          {loops.length || tickResult ? (
            <details className="ant-fold">
              <summary>
                <span>Things I&apos;m keeping an eye on</span>
                <small>{loops.length}</small>
              </summary>
              <div className="ant-fold-body">
                <div className="ant-fold-foot">
                  <button className="ant-ghost" type="button" onClick={scanLoops} disabled={busy}>
                    {busy ? "Checking…" : "Check now"}
                  </button>
                  {tickResult ? (
                    <span className="ant-inline-note">
                      {(tickResult.fired || []).length
                        ? `${(tickResult.fired || []).length} came due: ${(tickResult.fired || []).map(firedLoopText).join("; ")}`
                        : "Nothing due right now."}
                    </span>
                  ) : null}
                </div>
                <div className="ant-loop-list">
                  {loops.map((loop) => {
                    const meta = loopMeta(loop);
                    const conn = connections[loop.id];
                    const canResolve = !loop.fields?.owner_card_id;
                    const canConnect = canResolve && loop.fields?.action === "connect_account";
                    return (
                      <article className="ant-loop" key={loop.id}>
                        <div className="ant-loop-body">
                          <strong>{loopTitle(loop)}</strong>
                          {meta ? <span className="ant-loop-meta">{meta}</span> : null}
                          {conn ? (
                            <span className="ant-loop-meta">{conn.status}: {conn.message || conn.connect_url || conn.name}</span>
                          ) : null}
                        </div>
                        {canResolve ? (
                          <div className="ant-loop-actions">
                            {canConnect ? <button className="ant-ghost" type="button" onClick={() => connectLoop(loop.id)}>Connect</button> : null}
                            <button className="ant-ghost" type="button" onClick={() => resolveLoop(loop.id)}>Done</button>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}
                </div>
              </div>
            </details>
          ) : null}

          {remembered.length ? (
            <details className="ant-fold">
              <summary>
                <span>Things you said you&apos;d do</span>
                <small>{remembered.length}</small>
              </summary>
              <div className="ant-fold-body">
                <div className="ant-loop-list">
                  {remembered.map((row, index) => {
                    const inf = row.inferred;
                    const hasTask = inf && inf.task;
                    const conf = inf && inf.confidence;
                    const canApprove = Boolean(row.id) && hasTask && conf && conf !== "low";
                    const ar = row.id ? approveResults[row.id] : undefined;
                    const res = ar && ar.result;
                    const canPreview = Boolean(row.id);
                    const pr = row.id ? previewResults[row.id] : undefined;
                    const pres = pr && pr.result;
                    return (
                      <article className="ant-remember" key={row.id || `${row.ts || "remembered"}-${index}`}>
                        <div className="ant-remember-head">
                          <strong>{hasTask ? inf.task : row.text}</strong>
                          {row.ts ? <span className="ant-loop-meta">{formatRememberTs(row.ts)}</span> : null}
                        </div>
                        {hasTask ? <p className="ant-quote">{row.text}</p> : null}
                        {(conf || (inf && inf.due_phrase) || (inf && inf.people && inf.people.length)) ? (
                          <div className="ant-pill-row">
                            {conf ? <span className="ant-pill">{conf} confidence</span> : null}
                            {inf && inf.due_phrase ? <span className="ant-pill">{inf.due_phrase}</span> : null}
                            {inf && inf.people && inf.people.length ? <span className="ant-pill">{inf.people.join(", ")}</span> : null}
                          </div>
                        ) : null}
                        <div className="ant-remember-actions">
                          {canApprove && !res ? (
                            <button className="ant-yes" type="button" onClick={() => approveRemembered(row.id)} disabled={ar && ar.busy}>
                              {ar && ar.busy ? "Working…" : "Do it now"}
                            </button>
                          ) : null}
                          {canPreview ? (
                            <button className="ant-ghost" type="button" onClick={() => previewRemembered(row.id)} disabled={pr && pr.busy}>
                              {pr && pr.busy ? "Previewing…" : pres ? "Refresh preview" : "Preview"}
                            </button>
                          ) : null}
                        </div>
                        {res ? (
                          <p className="ant-inline-note">
                            {res.executed
                              ? `Done${res.idempotent ? " (already)" : ""} — ${res.would_do || res.intent}`
                              : res.prepared
                                ? `Prepared, your turn — ${res.would_do || res.inferred_action || res.intent}`
                                : `Not acted on — ${res.reason || "no confident task"}`}
                          </p>
                        ) : null}
                        {ar && ar.error ? <p className="ant-inline-note err">{ar.error}</p> : null}
                        {pres ? (
                          <p className="ant-inline-note">
                            {pres.would_execute
                              ? `Would run live — ${pres.would_do || pres.intent}${pres.tool ? ` (${pres.tool})` : ""}`
                              : pres.handback
                                ? `Would hand back — ${pres.handback || pres.inferred_action || pres.intent}`
                                : `Nothing would run — ${pres.why || "vent / narration"}`}
                          </p>
                        ) : null}
                        {pr && pr.error ? <p className="ant-inline-note err">{pr.error}</p> : null}
                      </article>
                    );
                  })}
                </div>
              </div>
            </details>
          ) : null}

          <details className="ant-fold">
            <summary>
              <span>Look someone up</span>
              <small>{profileResult ? `${profileResult.summary?.facts || 0} facts` : "from links"}</small>
            </summary>
            <div className="ant-fold-body">
              <form className="profile-form" onSubmit={buildProfile}>
                <MemoryField label="Name or company" value={profileName} onChange={setProfileName} placeholder="e.g. Ada Lovelace" />
                <MemoryField
                  label="Public links (one per line)"
                  value={profileSources}
                  onChange={setProfileSources}
                  placeholder="https://en.wikipedia.org/wiki/Ada_Lovelace"
                  multiline
                />
                <div className="ant-fold-foot">
                  <button className="ant-ghost" type="submit" disabled={profileBusy}>
                    {profileBusy ? "Reading…" : "Read these"}
                  </button>
                  <span className="ant-inline-note">Public pages only — no login, no writes.</span>
                </div>
              </form>
              {profileError ? <div className="ant-error">{profileError}</div> : null}
              {profileResult ? <ProfileView profile={profileResult} /> : null}
            </div>
          </details>

        </div>
      </div>
    </main>
  );
}
