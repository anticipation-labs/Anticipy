"use client";

import { useEffect, useMemo, useRef, useState } from "react";

// NO demo scaffolding: a real user never inherits someone else's day or someone else's
// people. The capture box opens empty with a human placeholder; the onboarding form opens
// empty so the first profile written is genuinely the owner's. (First-run setup lives at
// /welcome — the guided front door.)
const SAMPLE = "";

const SAMPLE_PLACEHOLDER =
  "Just talk. Paste a transcript, or type what your day sounds like — the small stuff you'd forget, the things you said you'd do. I'll sort out what matters.";

const DEFAULT_MEMORY = {
  ownerName: "",
  timezone: "",
  phone: "",
  email: "",
  preferences: "",
  people: "",
  connections: "",
  stores: "",
  notes: "",
};

// People/connection/store fields accept comma- OR pipe-separated columns, so the
// seed copy can stay human (no raw pipe-delimited data on screen) while the parser
// keeps working unchanged for either separator.
const FIELD_SEP = /\s*[|,]\s*/;

const sources = [
  ["typed", "Type it"],
  ["transcript", "Paste a transcript"],
  ["upload", "Upload audio"],
  ["start_listening", "Listen"],
];

function lines(value) {
  return (value || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function pipeParts(line) {
  return line.split(FIELD_SEP).map((part) => part.trim());
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

// AUTO_DO_WITH_OPT_OUT (the autonomy law): a reversible chore the assistant STARTED on its own
// ("call Amazon about the plant"). It is NOT an approval ask — it shows "I'm on it … — tell me to
// stop", with a STOP control, never Yes/Not-now. Detected by the persisted autonomy_mode (SEAM 2).
function isOptOut(card) {
  if (!card) return false;
  if (card.status === "stopped") return false; // a stopped chore drops out of the on-it lane
  if (card.status === "declined" || card.status === "done") return false;
  return card.autonomy_mode === "AUTO_DO_WITH_OPT_OUT" || card.execution?.opt_out === true;
}

function cardBucket(card) {
  // An in-flight opt-out chore is its own lane (started, stoppable) — never an approval ask.
  if (isOptOut(card)) return "onit";
  if (card.status === "stopped") return "done";
  if (card.status === "declined") return "done";
  if (card.status === "done" || card.disposition === "remember") return "done";
  if (card.disposition === "blocked" || card.status === "blocked") return "blocked";
  if (card.disposition === "ask" || card.status === "waiting") return "ask";
  return "ready";
}

// ---- copy guards (§4.8): the user never sees a codebase artifact ----
// Every string that originates in the engine passes through one of these before it
// reaches the DOM. Test scaffolding ("[Anticipy test]"), orphan transcript timestamps
// ("00:00:03]"), internal role prefixes ("Owner task:"), and engine route/disposition
// tags ("reversible:research -> act", "fail-safe ask", "cannot confirm safe -> ...")
// are scrubbed here, never rendered. If a string is ONLY machine noise, the caller
// drops the line rather than show it.

// Strip test labels, orphan timestamps, internal role prefixes, and ASCII arrows from
// any user text, then collapse a runaway rambling line (a vent dictated as one long
// run-on) down to its first clean clause so a title never shows a mid-word transcript dump.
function cleanText(value) {
  if (value == null) return "";
  let s = String(value)
    .replace(/\[Anticipy[^\]]*\]\s*/gi, "")            // "[Anticipy test]" scaffolding
    .replace(/^\s*\d{1,2}:\d{2}:\d{2}\]\s*/g, "")      // orphan "00:00:03]" timestamp head
    .replace(/\b\d{1,2}:\d{2}:\d{2}\]\s*/g, "")        // ...or mid-string
    .replace(/^\s*(?:Owner task|Owner|Follow up on your commitment)\s*:\s*/i, "")
    .replace(/\s*-+>\s*/g, " to ")                     // never a literal ASCII "->"
    .replace(/\s{2,}/g, " ")
    .trim();
  return s;
}

// A title-safe version of cleanText: caps an over-long / rambling string so it never
// shows as a wall of run-on transcript. Cuts at the first sentence end, else first 8
// words, with an ellipsis — but only when the line is genuinely too long.
function shortText(value, max = 72) {
  const s = cleanText(value);
  if (s.length <= max) return s;
  const sentence = s.match(/^.{12,72}?[.!?](?:\s|$)/);
  if (sentence) return sentence[0].trim();
  return s.split(/\s+/).slice(0, 9).join(" ") + "…";
}

// A reason string is internal machine noise (a route/disposition/triage tag) if it
// matches any of these — those must never reach the user (§4.8). When it does, the
// "why" line is dropped entirely rather than humanized into a guess.
const ROUTE_TAG_RE = /reversible:|->|\bfail-safe\b|re-gated|\bdecider\b|\bsignal\b|\broute\b|\bdisposition\b|goal_state|requires approval|planned step|\bact\b|\bask\b|\bcheckout\b(?!\s)/i;

// Engine triage reasons → one plain human sentence. Anything not in the map (or that
// looks like a raw route tag) returns "" so the caller drops the line.
const REASON_HUMAN = [
  [/explicit remember|commitment signal/i, "You said you'd remember this."],
  [/stated preference|identity|relationship fact/i, "Something about you, worth keeping."],
  [/care obligation|pickup|drop-?off/i, "A pickup that matters — I'll keep the timing safe."],
  [/scheduling|contact verb|concrete time|timed action/i, "There's a time on this, so I lined it up."],
  [/third-party communication|before sending/i, "I'll check with you before messaging someone."],
  [/money|checkout|pay/i, "Money's involved, so the last step stays yours."],
  [/item\/source context|exact item|source before/i, "I need the exact item before I can add it to a cart."],
];

function humanWhy(reason) {
  const text = cleanText(reason);
  if (!text) return "";
  for (const [re, say] of REASON_HUMAN) {
    if (re.test(text)) return say;
  }
  // Unknown reason: only keep it if it reads like a plain sentence (no route tags,
  // no arrows, no bare engine words). Otherwise stay silent.
  if (ROUTE_TAG_RE.test(text)) return "";
  return text;
}

// Rule-name titles the engine emits → clean human labels. If the engine already sent
// a humane title (e.g. "Prepare message for Sam"), we keep it; if it sent a rule name
// or a raw transcript, we map/repair it here. Never a truncated transcript, never a
// test label, never the "Owner task:" prefix.
const TITLE_HUMAN = [
  [/capture reminder|open loop/i, "A reminder you set"],
  [/schedule|timed action/i, "Something with a time on it"],
  [/protect pickup|drop-?off/i, "A pickup to protect"],
  [/block money|money action/i, "A payment — left for you"],
  [/resolve browser task/i, "Something to find online"],
];

// A line is vent-like / rambling (the dictated run-on filler) if it's long and has the
// telltale repetition of a vent rather than a crisp task. We never use it as a title.
function isRamble(s) {
  if (!s) return false;
  if (s.length > 90) return true;
  if (/\boh yeah\b.*\boh yeah\b/i.test(s)) return true;
  return false;
}

function humanTitle(card) {
  const raw = cleanText(card.title || card.action || "");
  // A rule-name title: map it to a clean label.
  for (const [re, label] of TITLE_HUMAN) {
    if (re.test(raw)) {
      // Prefer the real task text if it's a short, clean sentence.
      const src = cleanText(card.source_text || "");
      if (src && !isRamble(src) && !ROUTE_TAG_RE.test(src)) return shortText(src);
      return label;
    }
  }
  // An engine-humanized title we trust (e.g. "Prepare message for Sam"): keep as-is.
  if (raw && !isRamble(raw)) return shortText(raw);
  // Anything long/rambling (a raw transcript leaked as a title): fall back to a short
  // clean source, or a calm generic — never a truncated mid-word vent dump.
  const src = cleanText(card.source_text || "");
  if (src && !isRamble(src) && !ROUTE_TAG_RE.test(src)) return shortText(src);
  return "Something I caught";
}

// Is this card's source_text genuine user transcript (worth showing) or just the
// classifier rationale / a rambling vent? Show only short, clean, non-tag source.
function cardSourceLine(card) {
  const src = cleanText(card.source_text || "");
  if (!src) return "";
  if (ROUTE_TAG_RE.test(src)) return "";
  // A rambling vent / filler line is not a clean "source" — drop it entirely.
  if (isRamble(src)) return "";
  // If the title already IS the source, don't echo it twice.
  if (src === humanTitle(card)) return "";
  return src;
}

// A stable de-dup key for a caught item: collapse near-identical / progressively-
// truncated transcript variants (the "oh yeah we should go for dinner..." storm) into
// ONE. We key on the first handful of normalized words so all the truncations match.
function dedupeKey(card) {
  const base = cleanText(card.source_text || card.title || card.action || "")
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return base.split(" ").slice(0, 8).join(" ") || card.id;
}

// Collapse a list of cards to one card per dedupeKey (first wins, since the list is
// ordered freshest-first by the time it reaches here).
function dedupeCards(list) {
  const seen = new Set();
  const out = [];
  for (const card of list) {
    const key = dedupeKey(card);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(card);
  }
  return out;
}


// Turn a machine proof object into one plain, human receipt line. Never JSON, never
// a raw id or null — the spec's banned-string rule (§4.8). If there's nothing human
// to say, we say nothing (the caller drops empty receipts).
function proofValue(proof) {
  if (!proof) return "";
  if (proof.type === "memory_resolution") return cleanText([proof.item, proof.site].filter(Boolean).join(" at "));
  if (proof.type === "browser_receipt") return cleanText([proof.answer || "Checked it in the browser", proof.url].filter(Boolean).join(" — "));
  if (proof.decision) {
    // A resolution proof: ONE human phrase. "You said yes" already implies the outcome,
    // so we don't also append the raw/humanized goal_state (that's what produced the
    // doubled "You said yes — waiting on you" the critics flagged).
    if (proof.decision === "approved") return "You said yes";
    if (proof.decision === "declined") return "You passed";
    // Anything else (a raw token) is mapped, never shown raw.
    return humanState(proof.decision) || "";
  }
  // Never surface a filesystem path or a raw token to the user.
  return "";
}

function proofLabel(proof) {
  if (proof?.type === "memory_resolution") return "Remembered";
  if (proof?.type === "browser_receipt") return "Checked";
  if (proof?.type === "resolution") return "Your call";
  return "Note";
}

// Engine goal-states → words a person reads. Never surfaces goal_state/disposition raw.
function humanState(state) {
  const map = {
    done: "handled",
    waiting: "waiting on you",
    blocked: "left for you",
    declined: "set aside",
    prepared: "prepared, not sent",
    held: "held",
  };
  return state ? (map[state] || "") : "";
}

function visibleProofs(proofs = []) {
  if (!Array.isArray(proofs)) return [];
  // Only the three proof types that map to a plain human receipt are ever shown. The
  // rest (engine_execution with its raw act/ask disposition, card_record file paths,
  // memory_write/read_back internals) carry machine noise §4.8 bans, and the card's
  // own status dot already says whether it's handled/waiting — so we drop them.
  const userProof = new Set(["memory_resolution", "browser_receipt", "resolution"]);
  return proofs.filter((proof) => userProof.has(proof?.type)).slice(0, 2);
}

// A human one-word state for a card, mapped to the dot color in the row. No raw
// ids, no "Waiting for Omar" role-speak — the words the spec asks for (§4.8).
function outcomeWord(card) {
  const bucket = cardBucket(card);
  if (card.status === "stopped") return { label: "Stopped", tone: "" };
  if (card.status === "declined") return { label: "Set aside", tone: "" };
  if (bucket === "onit") return { label: "On it", tone: "onit" };
  if (bucket === "blocked") return { label: "Left for you", tone: "held" };
  if (bucket === "ask") return { label: "Waiting for your yes", tone: "waiting" };
  if (bucket === "done") return { label: "Handled", tone: "handled" };
  return { label: "Ready", tone: "" };
}

// The follow-up line for a card, read from the ATTACHED PLAN DICT (card.follow_up), not
// from any action literal. When an obligation's outcome depends on someone else, the engine
// schedules a check at follow_up.when_ts; this tells the user, in plain words, when we'll
// circle back. Returns "" when there is no plan (most cards) so nothing extra renders.
function followUpNote(card) {
  const fu = card?.follow_up;
  if (!fu || typeof fu !== "object") return "";
  const days = Number(fu.in_days);
  if (Number.isFinite(days)) {
    if (days <= 0) return "I'll check back on this shortly.";
    if (days === 1) return "I'll check back on this tomorrow.";
    return `I'll check back on this in ${days} days.`;
  }
  return "I'll check back on this and nudge you if it stalls.";
}

function receiptText(entry) {
  // Only ever a human sentence. If the event has no summary/message, we describe it
  // plainly rather than dumping JSON (which would leak {...}/null to the user).
  if (entry.summary) return cleanText(entry.summary);
  if (entry.message) return cleanText(entry.message);
  if (entry.data && typeof entry.data === "object") {
    const note = entry.data.summary || entry.data.message || entry.data.note;
    if (note) return cleanText(note);
  }
  return "Noted.";
}

function firedLoopText(item) {
  const what = cleanText(item.task || item.text || "") || "a loop";
  const did = item.decision === "approved" ? "took it on" : item.decision === "declined" ? "left it for you" : "checked on it";
  return `Looked back at "${what}" and ${did}.`;
}

// The remember-list ts is a unix epoch in seconds (RememberList writes time.time()).
function formatRememberTs(ts) {
  const seconds = Number(ts);
  if (!Number.isFinite(seconds)) return "";
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

// (The readiness checklist now lives only on /connect; its render helpers were removed
// from the home surface so the day view stays a single calm moment, not a status console.)

function loopMeta(loop) {
  // The "why this is open" line, in human words — never the raw route/action/
  // disposition fields (those are engine internals, §4.8).
  const fields = loop.fields || {};
  const action = fields.action;
  if (action === "connect_account") return "Waiting on an account connection.";
  // A follow-up is a SCHEDULED check the engine set on a card whose outcome depends on
  // someone else — recognized by the loop's kind (the scheduled fire-site row), not by an
  // action literal. The card that spawned it shows the human "I'll check back…" line.
  if (fields.kind === "follow_up") return "A follow-up I'll circle back on.";
  if (fields.kind === "reminder") return "A reminder you set.";
  return "Still open.";
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
    <div className="recap">
      <div className="recap-head">
        <strong>{profile.name}</strong>
        {profile.role ? <span className="recap-role">{profile.role}</span> : null}
        {browserOff ? (
          <span className="row-state" title="I couldn't open a browser, so I read nothing. I didn't invent anything.">
            <span className="state-dot waiting" /> couldn&apos;t look further
          </span>
        ) : null}
      </div>
      {(profile.org || profile.location) ? (
        <div className="recap-sub">
          {profile.org ? <span>{profile.org}</span> : null}
          {profile.location ? <span>{profile.location}</span> : null}
        </div>
      ) : null}
      <div className="recap-sub">
        <span>{summary.facts ?? facts.length} things I picked up</span>
        {(summary.needs_cross_check ?? 0) ? <span>{summary.needs_cross_check} I&apos;d double-check</span> : null}
        <span>
          read {summary.sources_read_ok ?? 0} of {summary.sources_total ?? (profile.sources || []).length}
        </span>
      </div>
      {facts.length ? (
        <ul className="recap-facts">
          {facts.map((fact, index) => (
            <li className="recap-fact" key={`${fact.field}-${index}`}>
              <div className="recap-fact-head">
                <span className="recap-field">{fact.field}</span>
                {fact.needs_cross_check ? (
                  <span className="row-state" title="I only saw this on one page — worth confirming.">
                    <span className="state-dot waiting" /> worth a check
                  </span>
                ) : (
                  <span className="row-state" title="I read the whole page — I'm fairly sure.">
                    <span className="state-dot handled" /> fairly sure
                  </span>
                )}
              </div>
              <p className="recap-value">{fact.value}</p>
              {fact.source_url ? (
                <a className="recap-source" href={fact.source_url} target="_blank" rel="noopener noreferrer">
                  where I saw it
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="recap-empty">No facts assembled. Nothing was invented.</p>
      )}
      {blockers.length ? (
        <div className="recap-blockers">
          <span className="recap-field">What stopped me</span>
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

// The plain-English "I'm on it … — tell me to stop" line for an AUTO_DO_WITH_OPT_OUT chore.
// Pulls the chore's own words from the source line so it reads like a person, not a status code.
function onItLine(card) {
  const what = shortText(card.source_text || card.title || "") || "this";
  return `I'm on it with ${what} — tell me to stop.`;
}

function TaskCard({ card, pendingAsk, onResolve, onStop, accent: showAccent = true }) {
  const bucket = cardBucket(card);
  const word = outcomeWord(card);
  const optOut = bucket === "onit";
  // Only the human receipts that actually have something to say (proofValue !== "").
  const proofs = visibleProofs(card.proof)
    .map((proof) => ({ label: proofLabel(proof), value: proofValue(proof) }))
    .filter((p) => p.value);
  // Only the lead waiting/blocked/on-it row carries a status color (R1.2 / R2.11); queued
  // rows after it render plain so a single screen shows one accent at most.
  const accent = !showAccent
    ? ""
    : bucket === "ask"
      ? "accent-ask"
      : bucket === "blocked"
        ? "accent-blocked"
        : bucket === "onit"
          ? "accent-onit"
          : "";
  const title = humanTitle(card);
  // For an opt-out chore the "I'm on it … — tell me to stop" line replaces the why blurb so the
  // card reads as STARTED work, not a pending decision.
  const why = optOut ? onItLine(card) : humanWhy(card.reason);
  const followUp = followUpNote(card);
  const sourceLine = optOut ? "" : cardSourceLine(card);
  return (
    <article className={`row settle ${accent}`}>
      <div className="row-head">
        <h4 className="row-title">{title}</h4>
        <span className="row-state">
          <span className={`state-dot ${word.tone}`} />
          {word.label}
        </span>
      </div>
      {sourceLine ? <p className="row-source">{sourceLine}</p> : null}
      {why ? <p className={optOut ? "row-onit" : "row-why"}>{why}</p> : null}
      {followUp ? <p className="row-followup">{followUp}</p> : null}
      {proofs.length ? (
        <div className="row-receipt">
          <dl>
            {proofs.map((proof, index) => (
              <div key={`${card.id}-proof-${index}`} style={{ display: "contents" }}>
                <dt>{proof.label}</dt>
                <dd>{proof.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
      {optOut && onStop ? (
        <div className="row-actions">
          {/* The autonomy law: an opt-out chore is STARTED, not pending. The only control is
              STOP — never a Yes/Not-now approval. */}
          <button className="btn-stop" onClick={() => onStop(card.id)}>Stop</button>
        </div>
      ) : null}
      {!optOut && pendingAsk ? (
        <div className="row-actions">
          <button onClick={() => onResolve(pendingAsk.ask_id, true)}>Yes</button>
          <button onClick={() => onResolve(pendingAsk.ask_id, false)}>Not now</button>
        </div>
      ) : null}
    </article>
  );
}

function PendingAsk({ ask, onResolve, accent = true }) {
  const title = shortText(ask.action) || "Something I caught";
  const why = humanWhy(ask.reason);
  return (
    <article className={`row settle ${accent ? "accent-ask" : ""}`}>
      <div className="row-head">
        <h4 className="row-title">{title}</h4>
        <span className="row-state">
          <span className="state-dot waiting" />
          Waiting for your yes
        </span>
      </div>
      {why ? <p className="row-why">{why}</p> : null}
      <div className="row-actions">
        <button onClick={() => onResolve(ask.ask_id, true)}>Yes</button>
        <button onClick={() => onResolve(ask.ask_id, false)}>Not now</button>
      </div>
    </article>
  );
}

function MemoryLoop({ loop, onResolve, onConnect, connection }) {
  const meta = loopMeta(loop);
  const canResolve = !loop.fields?.owner_card_id;
  const canConnect = canResolve && loop.fields?.action === "connect_account";
  return (
    <article className="row settle">
      <div className="row-head">
        <h4 className="row-title">{shortText(loop.text) || "An open thread"}</h4>
        <span className="row-state">
          <span className="state-dot waiting" />
          Open
        </span>
      </div>
      {meta ? <p className="row-why">{meta}</p> : null}
      {connection ? (
        <p className="row-why">
          {connection.message || (connection.connect_url ? "Opening where you finish connecting." : connection.name)}
        </p>
      ) : null}
      {canResolve ? (
        <div className="row-actions">
          {canConnect ? <button type="button" onClick={() => onConnect(loop.id)}>Connect</button> : null}
          <button type="button" onClick={() => onResolve(loop.id)}>Mark done</button>
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
  // Per-line DRY-RUN preview state keyed by remembered line id: { busy } while in flight,
  // then the engine's preview ({would_execute, intent, tool, args, handback, why}). This is
  // trust-before-connect: it shows what press-go WOULD do live WITHOUT executing anything —
  // no Goal, no orchestrator, no memory write, no account needed.
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
  const [error, setError] = useState("");
  const recognitionRef = useRef(null);

  const buckets = useMemo(() => {
    const next = { onit: [], ready: [], ask: [], blocked: [], done: [] };
    for (const card of cards) next[cardBucket(card)].push(card);
    // Collapse near-identical / progressively-truncated duplicates so a real user sees
    // ONE decision per real thing, never a wall of copies (the dinner-vent storm).
    return {
      onit: dedupeCards(next.onit),
      ready: dedupeCards(next.ready),
      ask: dedupeCards(next.ask),
      blocked: dedupeCards(next.blocked),
      done: dedupeCards(next.done),
    };
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
  const hasLatestRunStats = observed.length > 0 || ignored > 0;
  // Everything waiting for a yes, from BOTH sources (cards bucketed as "ask" and raw
  // pending asks with no card), merged into ONE list and deduped ACROSS both so a single
  // vent can't show up once as a card and once as a pending ask. Capped to a short list.
  const WAITING_CAP = 6;
  const waiting = useMemo(() => {
    const keyOf = (text) =>
      cleanText(text || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim().split(" ").slice(0, 8).join(" ");
    const seen = new Set();
    const out = [];
    for (const card of buckets.ask) {
      const k = keyOf(card.source_text || card.title || card.action);
      if (k && seen.has(k)) continue;
      if (k) seen.add(k);
      out.push({ kind: "card", id: card.id, card, ask: pendingByGoal.get(card.id) || pendingByGoal.get(card.execution?.ask_id) });
    }
    const unmatched = pending.filter((a) => !matchedPendingIds.has(a.ask_id));
    for (const ask of unmatched) {
      const k = keyOf(ask.action);
      if (k && seen.has(k)) continue;
      if (k) seen.add(k);
      out.push({ kind: "ask", id: ask.ask_id, ask });
    }
    return out;
  }, [buckets.ask, pending, pendingByGoal, matchedPendingIds]);
  const waitingVisible = waiting.slice(0, WAITING_CAP);
  const waitingHidden = Math.max(0, waiting.length - waitingVisible.length);
  // The "Here's what I caught" digest shows a short list, not the whole backlog (§2.3):
  // a handful of the most recent handled/ready items, with the rest summarized in one
  // calm line below rather than scrolled as a flat wall.
  const HANDLED_CAP = 6;
  const handledAll = [...buckets.done, ...buckets.ready];
  const handledCount = handledAll.length;
  const handledVisible = handledAll.slice(0, HANDLED_CAP);
  const handledHidden = Math.max(0, handledCount - handledVisible.length);
  // First run = the surface is genuinely empty (nothing caught, nothing waiting, nothing
  // open). We greet a newcomer with one calm first step instead of a populated dashboard.
  const isFirstRun =
    cards.length === 0 && pending.length === 0 && loops.length === 0 && remembered.length === 0;
  // "Things you said you'd do" — collapse the truncation storm and drop empty/vent rows
  // so it's a short readable list, not a wall. Keyed on the first words like the cards.
  const rememberedView = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const row of remembered) {
      const said = cleanText(row.text || "");
      if (!said) continue;
      const key = said.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim().split(" ").slice(0, 8).join(" ");
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(row);
    }
    return out.slice(0, 12);
  }, [remembered]);
  // "Still open" loops: collapse the same dictated vent repeated as many open threads,
  // and cap the list so it's a short tail, not a 47-row scroll.
  const loopsView = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const loop of loops) {
      const said = cleanText(loop.text || "");
      const key = said.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim().split(" ").slice(0, 8).join(" ") || loop.id;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(loop);
    }
    return out;
  }, [loops]);
  const loopsVisible = loopsView.slice(0, 8);
  const loopsHidden = Math.max(0, loopsView.length - loopsVisible.length);
  // The ledger ("What I did and heard") is a short recent tail, not the whole log.
  const eventsVisible = events.slice(0, 10);

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

  async function previewRemembered(lineId) {
    // DRY-RUN ONE remembered line: ask the engine what press-go WOULD do live, WITHOUT
    // doing it. The engine runs the SAME default-deny inference + whitelist mapping but
    // builds no Goal, calls no orchestrator, writes no memory, and touches no api/browser
    // hands — so this needs no connected account. We just render the planned action.
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

  async function stopCard(cardId) {
    // The autonomy law's opt-out: the owner pressed STOP on an "On it — you can stop me" chore.
    setBusy(true);
    setError("");
    try {
      const response = await ownerFetch("/api/owner/stop", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ card_id: cardId }),
      });
      const data = await response.json();
      handleOwnerAuthFailure(response, data);
      if (!response.ok) throw new Error(data.message || data.error || "Stop failed");
      setCards((current) =>
        current.map((card) =>
          card.id === cardId
            ? {
                ...card,
                status: "stopped",
                execution: { ...(card.execution || {}), goal_state: "stopped" },
              }
            : card,
        ),
      );
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
      setText(`Ready: ${file.name}. Hit "Read my day" and I'll listen through it.`);
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
    // BUGFIX (the "hello x 4 trillion" duplication): event.results is CUMULATIVE and includes
    // unstable interim results that fire many times per word. The old handler joined ALL of them
    // and APPENDED on every event, so one word ballooned into thousands. Walk only from
    // event.resultIndex and append each FINAL segment exactly once.
    recognition.onresult = (event) => {
      let finalChunk = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result && result.isFinal) {
          finalChunk += (result[0]?.transcript || "") + " ";
        }
      }
      const clean = finalChunk.trim();
      if (clean) {
        setText((current) => (current.trim() ? `${current.trim()} ${clean}` : clean));
      }
    };
    recognition.onerror = (event) => {
      setError(`Listening hit a snag (${event.error || "unknown"}). You can also type it.`);
    };
    recognition.onend = () => {
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    recognition.start();
  }

  if (!access.checked) {
    return (
      <main className="shell">
        <section className="gate-screen">
          <div className="gate orb-wrap">
            <div className="orb" />
            <p className="orb-word">One moment</p>
          </div>
        </section>
      </main>
    );
  }

  if (access.required && !access.authenticated) {
    return (
      <main className="shell">
        <section className="gate-screen">
          <form className="gate settle" onSubmit={unlockOwner}>
            <p className="gate-line">Welcome back.</p>
            <label className="token-field">
              <span>Your key</span>
              <input
                autoComplete="current-password"
                autoFocus
                onChange={(event) => setAccessToken(event.target.value)}
                type="password"
                value={accessToken}
              />
            </label>
            <button className="primary" disabled={accessBusy || !accessToken.trim()} type="submit">
              {accessBusy ? "One moment" : "Come in"}
            </button>
            {accessError ? <div className="error">{accessError}</div> : null}
          </form>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <div className="column">
        <div className="surface-head settle">
          <h1 className="surface-title">{isFirstRun ? "Hi. Let's begin." : "Here’s your day."}</h1>
          <p className="surface-sub">
            {isFirstRun
              ? "Tell me about your day below — type it, paste it, or just talk. When you’re ready, connect your accounts so I can actually help."
              : "I’m listening, remembering, and getting the small things handled. You only see what needs you."}
          </p>
          {isFirstRun ? (
            <a
              href="/welcome"
              className="primary"
              style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", textDecoration: "none", marginTop: 16, width: "fit-content" }}
            >
              Set me up first
            </a>
          ) : null}
        </div>

        <div className="presence settle">
          <span className={`pulse ${engine.ok ? "on" : ""}`} />
          <span>{engine.ok ? "Listening" : "Resting for a moment"}</span>
          {access.required ? (
            <button className="quiet-link" onClick={lockOwner} type="button">
              Step away
            </button>
          ) : null}
        </div>

        {/* The readiness checklist lives on /connect, not here — the home screen is one
            calm moment (the day), never a second status console competing with it (R1.7). */}

        {/* ---- capture: type, paste, upload, or listen ---- */}
        <section className="block">
          <div className="block-head">
            <h2 className="block-title">Tell me about your day</h2>
            <button
              className="quiet-link"
              type="button"
              onClick={() => {
                setUploadedFile(null);
                setSource("typed");
                setText(""); // blank the box — never restore a sample world
              }}
            >
              clear
            </button>
          </div>

          <div className="source-row" role="tablist" aria-label="How to share">
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
            placeholder={SAMPLE_PLACEHOLDER}
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
              {recognitionRef.current ? "Stop listening" : "Listen"}
            </button>
          </div>
          {uploadedFile ? (
            <div className="upload-note">
              <span>Ready</span>
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
              Let me handle the reversible ones
            </label>
            <button className="primary" type="button" onClick={runIngest} disabled={busy || (!text.trim() && !uploadedFile)}>
              {busy ? "Reading" : "Read my day"}
            </button>
          </div>
          {error ? <div className="error">{error}</div> : null}

          <details className="fold">
            <summary>
              <span>What I know about you</span>
              {memoryResult ? <small>{memoryResult.written?.length || 0} saved</small> : null}
            </summary>
            <div className="field-grid">
              <MemoryField
                label="Your name"
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
                label="How I should behave"
                value={memoryForm.preferences}
                onChange={(value) => updateMemoryField("preferences", value)}
                multiline
              />
              <MemoryField
                label="People in your life"
                value={memoryForm.people}
                onChange={(value) => updateMemoryField("people", value)}
                multiline
              />
              <MemoryField
                label="Accounts to reach"
                value={memoryForm.connections}
                onChange={(value) => updateMemoryField("connections", value)}
                multiline
              />
              <MemoryField
                label="Places you shop"
                value={memoryForm.stores}
                onChange={(value) => updateMemoryField("stores", value)}
                multiline
              />
              <MemoryField
                label="Anything else"
                value={memoryForm.notes}
                onChange={(value) => updateMemoryField("notes", value)}
                multiline
              />
            </div>
            <div className="control-row" style={{ marginTop: 18 }}>
              <button className="secondary" type="button" onClick={saveMemory} disabled={memoryBusy}>
                {memoryBusy ? "Saving" : "Remember this"}
              </button>
              {memoryResult?.missing_connections?.length ? (
                <span className="fold-result">Still to connect: {memoryResult.missing_connections.join(", ")}</span>
              ) : memoryResult ? (
                <span className="fold-result">Got it.</span>
              ) : null}
            </div>
            {memoryError ? <div className="error">{memoryError}</div> : null}
          </details>

          <details className="fold">
            <summary>
              <span>Look someone up</span>
              {profileResult ? <small>{profileResult.summary?.facts || 0} things found</small> : null}
            </summary>
            <form className="stack" onSubmit={buildProfile}>
              <MemoryField
                label="Name"
                value={profileName}
                onChange={setProfileName}
                placeholder="e.g. Ada Lovelace"
              />
              <MemoryField
                label="Public pages to read (one per line)"
                value={profileSources}
                onChange={setProfileSources}
                placeholder="https://en.wikipedia.org/wiki/Ada_Lovelace"
                multiline
              />
              <div className="control-row">
                <button className="secondary" type="submit" disabled={profileBusy}>
                  {profileBusy ? "Reading" : "Read them up"}
                </button>
                <span className="fold-result">Public pages only — no sign-in, nothing changed.</span>
              </div>
            </form>
            {profileError ? <div className="error">{profileError}</div> : null}
            {profileResult ? <ProfileView profile={profileResult} /> : null}
          </details>
        </section>

        {/* ---- what I caught (the digest) ---- */}
        <section className="block">
          <div className="block-head">
            <h2 className="block-title">Here&apos;s what I caught</h2>
            <button className="quiet-link" type="button" onClick={loadStatus}>
              refresh
            </button>
          </div>

          {hasLatestRunStats ? (
            <p className="glance">
              I read <strong>{observed.length}</strong> {observed.length === 1 ? "line" : "lines"} and let{" "}
              <strong>{ignored}</strong> throwaway {ignored === 1 ? "one" : "ones"} pass.
            </p>
          ) : null}

          <div className="rows">
            {handledVisible.map((card) => <TaskCard card={card} key={card.id} accent={false} />)}
            {!handledCount ? (
              <div className="empty">Nothing handled yet — share your day above and I&apos;ll get started.</div>
            ) : null}
          </div>
          {handledHidden > 0 ? (
            <p className="glance">…and {handledHidden} more, all handled. Nothing there needs you.</p>
          ) : null}
        </section>

        {/* ---- On it — you can stop me (the autonomy law: reversible chores STARTED, not asked) ---- */}
        {buckets.onit.length ? (
          <section className="block">
            <h2 className="block-title">On it — you can stop me</h2>
            <p className="block-note">
              These are reversible — I&apos;ve already started. Tell me to stop any one and I will.
            </p>
            <div className="rows">
              {buckets.onit.map((card, index) => (
                <TaskCard card={card} key={card.id} onStop={stopCard} accent={index === 0} />
              ))}
            </div>
          </section>
        ) : null}

        {/* ---- waiting for your yes (R2.11: ONE amber row, the rest plain below) ---- */}
        {waiting.length ? (
          <section className="block">
            <h2 className="block-title">Waiting for your yes</h2>
            {waiting.length > 1 ? (
              <p className="block-note">One thing wants your yes. The rest can wait.</p>
            ) : null}
            <div className="rows">
              {/* Only the lead row carries the amber accent; the rest render plain so a
                  single screen shows one status color at most (R1.2 / R2.11). */}
              {waitingVisible.map((item, index) =>
                item.kind === "card" ? (
                  <TaskCard
                    card={item.card}
                    key={item.id}
                    pendingAsk={item.ask}
                    onResolve={resolveAsk}
                    accent={index === 0}
                  />
                ) : (
                  <PendingAsk
                    ask={item.ask}
                    key={item.id}
                    onResolve={resolveAsk}
                    accent={index === 0}
                  />
                ),
              )}
            </div>
            {waitingHidden > 0 ? (
              <p className="glance">…and {waitingHidden} more waiting quietly below.</p>
            ) : null}
          </section>
        ) : null}

        {/* ---- left for you (the only hard stop) ---- */}
        {buckets.blocked.length ? (
          <section className="block">
            <h2 className="block-title">Left for you</h2>
            <p className="block-note">I got these to the last step. The final move is yours — I won&apos;t spend or sign in for you.</p>
            <div className="rows">
              {buckets.blocked.map((card, index) => <TaskCard card={card} key={card.id} accent={index === 0} />)}
            </div>
          </section>
        ) : null}

        {/* ---- still open (loops) ---- */}
        <section className="block">
          <div className="block-head">
            <h2 className="block-title">Still open</h2>
            <button className="quiet-link" type="button" onClick={scanLoops} disabled={busy}>
              look back now
            </button>
          </div>
          {tickResult ? (
            <div className="glance">
              {(tickResult.fired || []).length
                ? (tickResult.fired || []).map((item, index) => (
                    <p className="row-why" key={item.loop_id || `${item.task || "loop"}-${index}`} style={{ margin: 0 }}>
                      {firedLoopText(item)}
                    </p>
                  ))
                : <span>I looked back and nothing needed me.</span>}
            </div>
          ) : null}
          <div className="rows">
            {loopsVisible.length ? loopsVisible.map((loop) => (
              <MemoryLoop
                loop={loop}
                key={loop.id}
                onConnect={connectLoop}
                onResolve={resolveLoop}
                connection={connections[loop.id]}
              />
            )) : <div className="empty">Nothing left open.</div>}
          </div>
          {loopsHidden > 0 ? (
            <p className="glance">…and {loopsHidden} more open, nothing urgent.</p>
          ) : null}
        </section>

        {/* ---- review: what you said you'd do ---- */}
        <section className="block">
          <h2 className="block-title">Things you said you&apos;d do</h2>
            <div className="rows">
              {rememberedView.length ? rememberedView.map((row, index) => {
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
                // DRY-RUN preview is offered for ANY remembered line with an id (even a
                // non-whitelisted or low-confidence one) so the owner can see what press-go
                // WOULD do live — the planned intent/tool/args for a whitelisted line, the
                // handback for the rest, or the vent stop — WITHOUT executing or connecting.
                const canPreview = Boolean(row.id);
                const pr = row.id ? previewResults[row.id] : undefined;
                const pres = pr && pr.result;
                return (
                <article className="row settle" key={row.id || `${row.ts || "remembered"}-${index}`}>
                  <div className="row-head">
                    {hasTask
                      ? <h4 className="row-title">{shortText(inf.task)}</h4>
                      : <h4 className="row-title">{shortText(row.text)}</h4>}
                    {row.ts ? <span className="row-when">{formatRememberTs(row.ts)}</span> : null}
                  </div>
                  {hasTask ? (
                    <p className="row-why" title="What you actually said">
                      You said: {shortText(row.text, 120)}
                    </p>
                  ) : null}
                  {(conf || (inf && inf.due_phrase) || (inf && inf.people && inf.people.length)) ? (
                    <div className="row-meta">
                      {conf ? <span>{conf === "high" ? "I'm fairly sure" : conf === "med" ? "fairly likely" : "just a hunch"}</span> : null}
                      {inf && inf.due_phrase ? <span>by {inf.due_phrase}</span> : null}
                      {inf && inf.people && inf.people.length
                        ? <span>{inf.people.join(", ")}</span> : null}
                    </div>
                  ) : null}
                  {(row.source || (row.people && row.people.length)) ? (
                    <p className="row-source">
                      {cleanText([row.source, (row.people || []).join(", ")].filter(Boolean).join(" — "))}
                    </p>
                  ) : null}
                  {canApprove ? (
                    <div className="row-actions">
                      {!res ? (
                        <button
                          type="button"
                          onClick={() => approveRemembered(row.id)}
                          disabled={ar && ar.busy}
                        >
                          {ar && ar.busy ? "On it" : "Yes, handle it"}
                        </button>
                      ) : res.executed ? (
                        // Whitelisted reversible action ran: read-back receipt, in words.
                        <span className="row-state">
                          <span className="state-dot handled" />
                          {res.idempotent ? "Already handled" : "Handled"} — {cleanText(res.would_do) || "done"}
                        </span>
                      ) : res.prepared ? (
                        // Non-whitelisted: prepared and handed back, never executed.
                        <span className="row-state">
                          <span className="state-dot waiting" />
                          Prepared — your turn. {cleanText(res.why_handback || res.would_do || res.inferred_action || "")}
                        </span>
                      ) : (
                        // Refused at the engine (e.g. re-inferred as a vent): no action.
                        <span className="row-state">
                          <span className="state-dot" />
                          Left it alone. {cleanText(res.reason) || "Sounded like a passing comment."}
                        </span>
                      )}
                      {ar && ar.error ? <span className="row-why">{ar.error}</span> : null}
                    </div>
                  ) : null}
                  {canPreview ? (
                    <div className="row-actions">
                      <button
                        type="button"
                        onClick={() => previewRemembered(row.id)}
                        disabled={pr && pr.busy}
                      >
                        {pr && pr.busy
                          ? "Looking"
                          : pres
                            ? "Look again"
                            : "Show me what you'd do"}
                      </button>
                    </div>
                  ) : null}
                  {pres ? (
                    pres.would_execute ? (
                      // Whitelisted: describe the planned action in plain words. Never the
                      // raw tool name or a JSON args blob (§4.8 — no machine noise).
                      <p className="row-why">
                        <span className="row-state"><span className="state-dot handled" /> I&apos;d go ahead</span>
                        {" — "}{cleanText(pres.would_do) || "handle this"}{pres.note ? `. ${cleanText(pres.note)}` : ""}
                      </p>
                    ) : pres.handback ? (
                      <p className="row-why">
                        <span className="row-state"><span className="state-dot waiting" /> I&apos;d hand it back</span>
                        {" — "}{cleanText(pres.handback || pres.inferred_action) || "prepare it and leave the last step to you"}
                        {pres.why ? `. ${cleanText(pres.why)}` : ""}
                      </p>
                    ) : (
                      // Vent / narration: press-go would do nothing at all.
                      <p className="row-why">
                        <span className="row-state"><span className="state-dot" /> I&apos;d stay quiet</span>
                        {" — "}{cleanText(pres.why) || "this sounded like a passing comment, not a task"}
                      </p>
                    )
                  ) : null}
                  {pr && pr.error ? <p className="row-why">{pr.error}</p> : null}
                </article>
                );
              }) : <div className="empty">Nothing to look back on yet.</div>}
            </div>
        </section>

        {/* ---- the ledger: everything I did and heard ---- */}
        <section className="block">
          <h2 className="block-title">What I did and heard</h2>
          <div className="rows">
            {eventsVisible.length ? eventsVisible.map((entry, index) => (
              <div className="row" key={`${entry.ts || index}-${entry.kind || "event"}`}>
                <p className="row-why" style={{ margin: 0 }}>{receiptText(entry)}</p>
              </div>
            )) : <div className="empty">Nothing logged yet.</div>}
          </div>
        </section>

        <p className="close-line">That&apos;s everything. Nothing else needs you right now.</p>
      </div>
    </main>
  );
}
