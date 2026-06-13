"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const SAMPLE = `[08:02] Omar: yeah okay no the coffee machine is being weird again and I do not care.
[08:04] Maya: school moved pickup to 3 today, please remind me before I forget.
[08:05] Omar: oh sure, I'll just clone myself, that'll fix the schedule.
[09:12] Sam needs the revised deck before Friday; I told him I'd send it.
[11:22] that water-table thing for Leila's birthday, put it in the cart if you find it, don't buy it.
[12:10] order the replacement filter today and just pay whatever it costs.
[13:00] My wife Maya prefers texts after lunch.`;

const sources = [
  ["typed", "Typed"],
  ["transcript", "Transcript"],
  ["upload", "Upload"],
  ["start_listening", "Listen"],
];

function cardBucket(card) {
  if (card.status === "done" || card.disposition === "remember") return "done";
  if (card.disposition === "blocked" || card.status === "blocked") return "blocked";
  if (card.disposition === "ask" || card.status === "waiting") return "ask";
  return "ready";
}

function proofValue(proof) {
  if (!proof) return "";
  if (proof.decision) return [proof.decision, proof.goal_state].filter(Boolean).join(" / ");
  if (proof.memory_id) return proof.memory_id;
  if (proof.path) return proof.path;
  if (proof.type) return proof.type;
  return JSON.stringify(proof);
}

function proofLabel(proof) {
  const type = proof?.type || "proof";
  return type.replaceAll("_", " ");
}

function outcomeText(card, pendingAsk) {
  const bucket = cardBucket(card);
  if (bucket === "blocked") return "Hard wall: no payment executed";
  if (bucket === "ask") return pendingAsk ? `Waiting for Omar: ${pendingAsk.ask_id.slice(0, 6)}` : "Waiting for Omar";
  if (bucket === "done") return "Done with receipt";
  return "Ready";
}

function TaskCard({ card, pendingAsk, onResolve }) {
  const bucket = cardBucket(card);
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
      {card.proof?.length ? (
        <div className="proof">
          {card.proof.slice(-4).map((proof, index) => (
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

export default function Home() {
  const [text, setText] = useState(SAMPLE);
  const [source, setSource] = useState("typed");
  const [executeActions, setExecuteActions] = useState(true);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [cards, setCards] = useState([]);
  const [observed, setObserved] = useState([]);
  const [ignored, setIgnored] = useState(0);
  const [pending, setPending] = useState([]);
  const [events, setEvents] = useState([]);
  const [engine, setEngine] = useState({ ok: false, label: "checking" });
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

  async function loadStatus() {
    const [health, pendingRes, glassbox] = await Promise.allSettled([
      fetch("/api/health", { cache: "no-store" }).then((r) => r.json().then((data) => ({ ok: r.ok, data }))),
      fetch("/api/pending", { cache: "no-store" }).then((r) => r.json()),
      fetch("/api/glassbox?limit=20", { cache: "no-store" }).then((r) => r.json()),
    ]);
    if (health.status === "fulfilled" && health.value.ok) {
      setEngine({ ok: true, label: health.value.data.service || "engine online" });
    } else {
      setEngine({ ok: false, label: "engine offline" });
    }
    if (pendingRes.status === "fulfilled") setPending(pendingRes.value.pending || []);
    if (glassbox.status === "fulfilled") setEvents(glassbox.value.entries || []);
  }

  useEffect(() => {
    loadStatus();
    const id = setInterval(loadStatus, 5000);
    return () => clearInterval(id);
  }, []);

  function applyIngestResult(data) {
    setCards(data.cards || []);
    setObserved(data.observed_lines || []);
    setIgnored(data.ignored_line_count || 0);
  }

  async function runUpload() {
    const form = new FormData();
    form.append("file", uploadedFile);
    form.append("source", source);
    form.append("execute_actions", String(executeActions));
    return fetch("/api/owner/upload", {
      method: "POST",
      body: form,
    });
  }

  async function runIngest() {
    setBusy(true);
    setError("");
    try {
      const response = uploadedFile ? await runUpload() : await fetch("/api/owner/ingest", {
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
      const response = await fetch("/api/resolve", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ask_id: askId, approved }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || data.error || "Resolve failed");
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
        </div>
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
              <strong>{observed.length}</strong>
              <span>lines observed</span>
            </div>
            <div className="metric">
              <strong>{cards.length}</strong>
              <span>cards created</span>
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
              <strong>{ignored}</strong>
              <span>ignored lines</span>
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
              <h2>Receipts</h2>
              <span className="status-strip">{events.length} events</span>
            </div>
            <div className="events">
              {events.length ? events.map((entry, index) => (
                <div className="event" key={`${entry.ts || index}-${entry.kind || "event"}`}>
                  <strong>{entry.kind || "event"}</strong>
                  <span>{JSON.stringify(entry.data || entry)}</span>
                </div>
              )) : <div className="empty">No engine events loaded.</div>}
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}
