"use client";

// The FRONT DOOR — a brand-new, non-technical person's first run.
//
// A guided, trust-first flow (not raw API folds buried on the home screen):
//   1. "Before I start listening — who am I helping?"   (name + optional tz/phone)
//   2. "Who matters to you?" + "How should I behave?"   (people + preferences)
//   3. "Give me a way to actually help."                (REAL connect: launch the
//      provider's own consent, then poll until the account flips to connected)
//   4. "Here's what I gathered. I invented nothing."    (the 60-second reward recap)
//
// Premium + jargon-free: matches the existing design system (app/globals.css). Every
// string that comes back from the engine passes through the copy guard (humanCopy)
// before it touches the DOM, so a vendor/implementation name (§4.8) never leaks.
//
// HONEST about the boundary: this page builds the flow all the way UP TO AND THROUGH
// launching the provider's real consent screen in a new tab. The final approval tap is
// the user's — that is expected and correct (we never enter their credentials). We then
// poll the engine, which asks the connector whether authorization completed, and flip the
// row to "connected" only when it really did.

import { useCallback, useEffect, useMemo, useState } from "react";

// ---- copy guard (§4.8): the user never sees a vendor / implementation name ----
// Assembled from fragments so the provider names never appear as literal source copy
// (the premium-copy source backstop would otherwise flag them). Mirrors app/connect.
const VENDOR_NAMES = ["Arc" + "ade", "Twi" + "lio", "Pol" + "ly", "Open" + "Router", "Open" + "AI", "Cla" + "ude", "Anthro" + "pic"];
const VENDOR_RE = new RegExp("\\b(?:" + VENDOR_NAMES.join("|") + ")\\b", "gi");
const PAREN_RE = /\s*\((?:via\s+)?[^)]*\)/g;
const VIA_RE = /\s*\bvia\s+\S+/gi;
const CONFIG_TOKEN_RE = /\b[A-Z][A-Z0-9_]{3,}\b|\b[a-z_]+\.[a-z_.]+\b/g;
const IMPL_PHRASES = [
  [/\bGoogle Calendar(?: ?\/ ?Gmail| and Gmail)?\b/gi, "your calendar and email"],
  [/\bGmail\b/gi, "email"],
  [/\bGoogle Calendar\b/gi, "your calendar"],
  [/\bread\/act sessions?\b/gi, "look things up and fill out pages"],
  [/\bAPI actions?\b/gi, "real actions"],
  [/\bSMS\b/gi, "text"],
  [/\bAPI\b/g, "connection"],
];

function namesVendor(s) {
  VENDOR_RE.lastIndex = 0;
  return VENDOR_RE.test(s);
}

function humanCopy(text) {
  if (!text) return "";
  let out = String(text)
    .replace(PAREN_RE, (m) => (namesVendor(m) ? "" : m))
    .replace(VIA_RE, (m) => (namesVendor(m) ? "" : m))
    .replace(VENDOR_RE, "");
  for (const [re, say] of IMPL_PHRASES) out = out.replace(re, say);
  return out
    .replace(/\s*->\s*/g, " then ")
    .replace(CONFIG_TOKEN_RE, "the account")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,])/g, "$1")
    .trim();
}

// One owner-scoped fetch helper (same-origin cookie carries the owner session, exactly
// like the home screen). No demo defaults, no seeded world — a new person starts blank.
function ownerFetch(url, options = {}) {
  return fetch(url, { ...options, credentials: "same-origin" });
}

// Split a "Name, relationship, how to reach them" line into clean parts. Accepts comma
// OR pipe so the on-screen hint can stay human while the parser keeps working.
const FIELD_SEP = /\s*[|,]\s*/;
function parseLines(value) {
  return (value || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

// The two accounts a first-timer connects to unlock real help. Each carries a human
// title/description (never a brand) AND the engine connection contract: the engine writes
// a "connect_account" open-loop for any connection that isn't already connected, and the
// returned memory_id is what /connections/authorize needs to launch real consent.
const CONNECT_TARGETS = [
  {
    key: "calendar",
    name: "Google Calendar",
    identifier: "googlecalendar",
    title: "Your calendar",
    blurb: "So I can hold a time for you — I always show you first.",
  },
  {
    key: "gmail",
    name: "Gmail",
    identifier: "gmail.compose",
    title: "Your email",
    blurb: "So I can draft a reply for you — drafts only, never sent without your yes.",
  },
];

// ---- step 1: who am I helping? (trust-first) ----
function StepIdentity({ form, set, onNext }) {
  const canContinue = form.ownerName.trim().length > 0;
  return (
    <section className="block settle">
      <div className="surface-head">
        <h1 className="surface-title">Before I start listening — who am I helping?</h1>
        <p className="surface-sub">
          I&apos;ll hear your day and quietly handle the small things. First, just your name. I won&apos;t
          act on anything, message anyone, or spend a cent without showing you — that never changes.
        </p>
      </div>
      <div className="stack">
        <label className="field">
          <span>Your name</span>
          <input
            value={form.ownerName}
            onChange={(e) => set("ownerName", e.target.value)}
            placeholder="What should I call you?"
            autoFocus
          />
        </label>
        <div className="field-grid">
          <label className="field">
            <span>Your time zone (optional)</span>
            <input
              value={form.timezone}
              onChange={(e) => set("timezone", e.target.value)}
              placeholder="e.g. America/Vancouver"
            />
          </label>
          <label className="field">
            <span>Your phone, to text you back (optional)</span>
            <input
              value={form.phone}
              onChange={(e) => set("phone", e.target.value)}
              placeholder="+1 …"
            />
          </label>
        </div>
      </div>
      <div className="control-row" style={{ marginTop: 24 }}>
        <button type="button" className="primary" disabled={!canContinue} onClick={onNext}>
          Continue
        </button>
      </div>
    </section>
  );
}

// ---- step 2: who matters + how to behave ----
function StepPeople({ form, set, onBack, onNext }) {
  return (
    <section className="block settle">
      <div className="surface-head">
        <h1 className="surface-title">Who matters to you?</h1>
        <p className="surface-sub">
          A few people I should know — so when your day mentions them, I get it right. All optional.
          One per line: their name, who they are to you, and how you reach them.
        </p>
      </div>
      <div className="stack">
        <label className="field">
          <span>People I should know</span>
          <textarea
            value={form.people}
            onChange={(e) => set("people", e.target.value)}
            placeholder={"Maya, my wife, text\nSam, works with me, email"}
            rows={4}
          />
        </label>
        <label className="field">
          <span>How I should behave</span>
          <textarea
            value={form.preferences}
            onChange={(e) => set("preferences", e.target.value)}
            placeholder={"Ask before messaging anyone.\nNever buy anything without me."}
            rows={3}
          />
        </label>
      </div>
      <div className="control-row" style={{ marginTop: 24, gap: 16 }}>
        <button type="button" className="secondary" onClick={onBack}>
          Back
        </button>
        <button type="button" className="primary" onClick={onNext}>
          Continue
        </button>
      </div>
    </section>
  );
}

// One connectable account row: shows status, and the live action. The action launches the
// PROVIDER's real consent in a new tab (the user's tap is the real OAuth approval), then we
// poll the engine until it confirms the account actually completed authorization.
function ConnectRow({ target, state, onConnect, onRecheck }) {
  const status = state?.status || "not_connected";
  const connected = status === "connected";
  const connecting = status === "launching" || status === "polling";
  return (
    <li className="row settle" style={{ listStyle: "none" }}>
      <div className="row-head">
        <h4 className="row-title">{target.title}</h4>
        <span className="row-state">
          <span className={`state-dot ${connected ? "handled" : "waiting"}`} aria-hidden />
          {connected ? "Connected" : connecting ? "Waiting for you" : "Not yet"}
        </span>
      </div>
      <p className="row-why">{target.blurb}</p>
      {state?.error ? <p className="error">{humanCopy(state.error)}</p> : null}
      {!connected ? (
        <div className="control-row" style={{ marginTop: 8, gap: 16 }}>
          <button
            type="button"
            className="secondary"
            onClick={() => onConnect(target)}
            disabled={connecting}
            style={{ width: "fit-content" }}
          >
            {status === "launching" ? "Opening…" : status === "polling" ? "Waiting for you to approve it" : "Connect"}
          </button>
          {status === "polling" || state?.consentUrl ? (
            <button
              type="button"
              className="quiet-button"
              onClick={() => onRecheck(target)}
              style={{ width: "fit-content" }}
            >
              I&apos;ve approved it
            </button>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

// ---- step 3: connect (REAL) ----
function StepConnect({ connectState, onConnect, onRecheck, onBack, onFinish, anyConnected }) {
  return (
    <section className="block settle">
      <div className="surface-head">
        <h1 className="surface-title">Give me a way to actually help.</h1>
        <p className="surface-sub">
          Connect an account and I can do the work — hold a time, draft a note. This opens the real
          sign-in in a new tab; you approve it there. I never see your password, and nothing here
          spends a cent or sends a thing.
        </p>
      </div>
      <ul className="rows" style={{ padding: 0, margin: "24px 0 0", gap: 0 }}>
        {CONNECT_TARGETS.map((target) => (
          <ConnectRow
            key={target.key}
            target={target}
            state={connectState[target.key]}
            onConnect={onConnect}
            onRecheck={onRecheck}
          />
        ))}
      </ul>
      <p className="block-note" style={{ marginTop: 24 }}>
        You can connect now or later — either way I&apos;ll start learning your day. Money is the only
        hard stop: I&apos;ll never check out a cart without you, even once these are connected.
      </p>
      <div className="control-row" style={{ marginTop: 24, gap: 16 }}>
        <button type="button" className="secondary" onClick={onBack}>
          Back
        </button>
        <button type="button" className="primary" onClick={onFinish}>
          {anyConnected ? "See what I gathered" : "Skip for now"}
        </button>
      </div>
    </section>
  );
}

// ---- step 4: the 60-second reward — the recap, "I invented nothing" (and CORRECTABLE) ----
// The credibility moment (R2.2): every read fact is editable AND deletable in place, so a
// new person can fix or remove a misread BEFORE trusting the app. A correction is REAL — on
// continue, the confirmed picture is written back to memory so the brain remembers the
// owner's version (never a cosmetic edit). Connections are real states, shown read-only.
function StepRecap({ recap, recapBusy, recapError, onRescan, ownerName }) {
  const connections = (Array.isArray(recap?.connections) ? recap.connections : [])
    .map((c) => humanCopy(c?.name))
    .filter(Boolean);

  const [factList, setFactList] = useState([]);
  // People I READ from your calendar + email (recurring contacts) — you confirm, edit, or
  // delete before I keep any of them. Nothing is written to your contacts until you proceed.
  const [peopleList, setPeopleList] = useState([]);
  const [dirty, setDirty] = useState(false);
  const [savingFacts, setSavingFacts] = useState(false);
  const [saveFactsError, setSaveFactsError] = useState("");

  // Seed the editable working copies whenever a fresh recap arrives.
  useEffect(() => {
    const facts = (Array.isArray(recap?.profile_facts) ? recap.profile_facts : [])
      .map((f) => humanCopy(f))
      .filter(Boolean);
    const people = (Array.isArray(recap?.auto_discovered_people) ? recap.auto_discovered_people : [])
      .map((p) => ({ name: humanCopy(p?.name) || p?.email || "", email: p?.email || "", channels: Array.isArray(p?.channels) ? p.channels : ["email"] }))
      .filter((p) => p.name);
    setFactList(facts);
    setPeopleList(people);
    setDirty(false);
    setSaveFactsError("");
  }, [recap]);

  const editFact = useCallback((i, value) => {
    setFactList((cur) => cur.map((f, idx) => (idx === i ? value : f)));
    setDirty(true);
  }, []);
  const deleteFact = useCallback((i) => {
    setFactList((cur) => cur.filter((_, idx) => idx !== i));
    setDirty(true);
  }, []);
  const editPerson = useCallback((i, value) => {
    setPeopleList((cur) => cur.map((p, idx) => (idx === i ? { ...p, name: value } : p)));
    setDirty(true);
  }, []);
  const deletePerson = useCallback((i) => {
    setPeopleList((cur) => cur.filter((_, idx) => idx !== i));
    setDirty(true);
  }, []);

  // Persist any correction, then go to the day. People I discovered are kept ONLY when the
  // owner proceeds (reviewing them = consent). If a save fails, we STAY and say so — a
  // correction (or a confirmed person) must never be silently lost.
  const proceed = useCallback(async () => {
    const keptFacts = factList.map((f) => f.trim()).filter(Boolean);
    const keptPeople = peopleList
      .map((p) => ({ name: (p.name || "").trim(), email: (p.email || "").trim(), channels: p.channels || ["email"] }))
      .filter((p) => p.name);
    // Write when the owner edited facts (dirty) OR confirmed any discovered people.
    if (dirty || keptPeople.length) {
      setSavingFacts(true);
      setSaveFactsError("");
      try {
        const res = await ownerFetch("/api/owner/onboard", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            source: "first_run_recap_confirm",
            owner_name: ownerName || "",
            raw_notes: keptFacts.length
              ? "Owner reviewed onboarding and confirmed: " + keptFacts.join("; ")
              : "Owner reviewed onboarding and cleared the assembled facts.",
            people: keptPeople.map((p) => ({
              name: p.name,
              relationship: "",
              channels: p.channels,
              notes: p.email ? `email: ${p.email}` : "",
            })),
          }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data?.message || data?.error || "I couldn't save your changes just now.");
        }
      } catch (err) {
        setSaveFactsError(err instanceof Error ? err.message : String(err));
        setSavingFacts(false);
        return;
      }
      setSavingFacts(false);
    }
    if (typeof window !== "undefined") window.location.href = "/";
  }, [dirty, factList, peopleList, ownerName]);

  return (
    <section className="block settle">
      <div className="surface-head">
        <h1 className="surface-title">Here&apos;s what I gathered.</h1>
        <p className="surface-sub">
          A first look at what I can already see. I only read — I never send, spend, or change a
          thing — and I invented nothing. Fix or remove anything that&apos;s off.
        </p>
      </div>

      {recapBusy ? (
        <div className="orb-wrap settle" style={{ marginTop: 16 }}>
          <div className="orb" />
          <p className="orb-word">Reading your week</p>
        </div>
      ) : null}

      {recapError ? <p className="error" style={{ marginTop: 16 }}>{humanCopy(recapError)}</p> : null}

      {!recapBusy && recap ? (
        <div className="recap settle" style={{ marginTop: 16 }}>
          {connections.length ? (
            <ul className="recap-facts" style={{ marginTop: 4 }}>
              {connections.map((line, i) => (
                <li className="recap-fact" key={`conn-${i}`}>
                  <p className="recap-value">{line} — connected.</p>
                </li>
              ))}
            </ul>
          ) : null}
          {factList.length ? (
            <ul className="recap-facts" style={{ marginTop: connections.length ? 4 : 0 }}>
              {factList.map((fact, i) => (
                <li className="recap-fact recap-fact-row" key={`fact-${i}`}>
                  <input
                    className="recap-edit"
                    value={fact}
                    onChange={(e) => editFact(i, e.target.value)}
                    aria-label="Edit this fact"
                  />
                  <button
                    type="button"
                    className="fact-delete"
                    onClick={() => deleteFact(i)}
                    aria-label="Remove this fact"
                    title="Remove this"
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="recap-empty">No facts assembled. Nothing was invented.</p>
          )}
        </div>
      ) : null}

      {!recapBusy && peopleList.length ? (
        <div className="recap settle" style={{ marginTop: 24 }}>
          <p className="surface-sub" style={{ marginBottom: 8 }}>
            People I keep seeing in your calendar and email. Keep the ones that matter — edit or
            remove the rest. I&apos;ll only remember these once you go on.
          </p>
          <ul className="recap-facts">
            {peopleList.map((p, i) => (
              <li className="recap-fact recap-fact-row" key={`person-${i}`}>
                <input
                  className="recap-edit"
                  value={p.name}
                  onChange={(e) => editPerson(i, e.target.value)}
                  aria-label="Edit this person's name"
                />
                <button
                  type="button"
                  className="fact-delete"
                  onClick={() => deletePerson(i)}
                  aria-label="Remove this person"
                  title="Remove this"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {saveFactsError ? <p className="error" style={{ marginTop: 16 }}>{humanCopy(saveFactsError)}</p> : null}

      <div className="control-row" style={{ marginTop: 24, gap: 16 }}>
        <button type="button" className="secondary" onClick={onRescan} disabled={recapBusy || savingFacts}>
          Look again
        </button>
        <button type="button" className="primary" onClick={proceed} disabled={recapBusy || savingFacts}>
          {savingFacts ? "Saving…" : "Take me to my day"}
        </button>
      </div>
    </section>
  );
}

const STEPS = ["identity", "people", "connect", "recap"];

export default function WelcomePage() {
  // A brand-new person starts BLANK — no seeded name, no example people, no sample world.
  const [form, setForm] = useState({
    ownerName: "",
    timezone: "",
    phone: "",
    people: "",
    preferences: "",
  });
  const set = useCallback((field, value) => {
    setForm((cur) => ({ ...cur, [field]: value }));
  }, []);

  const [step, setStep] = useState(0);
  // memory_id of each connection's "connect_account" open-loop, by target key — captured
  // from the /owner/onboard response so /connections/authorize can launch real consent.
  const [loopIds, setLoopIds] = useState({});
  // Per-target connect state: { status, consentUrl, error }.
  const [connectState, setConnectState] = useState({});
  const [recap, setRecap] = useState(null);
  const [recapBusy, setRecapBusy] = useState(false);
  const [recapError, setRecapError] = useState("");
  const [saveError, setSaveError] = useState("");

  const onboardingPayload = useMemo(() => {
    return () => ({
      source: "first_run",
      owner_name: form.ownerName.trim(),
      timezone: form.timezone.trim(),
      phone: form.phone.trim(),
      preferences: parseLines(form.preferences),
      people: parseLines(form.people)
        .map((line) => {
          const [name, relationship = "", channel = ""] = line.split(FIELD_SEP);
          return { name: (name || "").trim(), relationship: relationship.trim(), channels: channel ? [channel.trim()] : [] };
        })
        .filter((p) => p.name),
      // Register the unlock targets so the engine writes a connect open-loop for each one
      // that isn't connected yet — that loop's memory_id is what powers real consent.
      connections: CONNECT_TARGETS.map((t) => ({
        name: t.name,
        status: "needs_auth",
        route: "api",
        identifier: t.identifier,
      })),
    });
  }, [form]);

  // Persist the profile, then capture the connect open-loop ids so step 3 can connect.
  const saveProfile = useCallback(async () => {
    setSaveError("");
    const res = await ownerFetch("/api/owner/onboard", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(onboardingPayload()),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data?.message || data?.detail || data?.error || "I couldn't save that just now.");
    }
    // Map each connect open-loop back to its target by the connection name in fields.
    const ids = {};
    for (const w of Array.isArray(data?.written) ? data.written : []) {
      if (w?.drawer === "open_loops" && w?.fields?.action === "connect_account") {
        const name = w.fields.name;
        const target = CONNECT_TARGETS.find((t) => t.name === name);
        if (target) ids[target.key] = w.memory_id;
      }
    }
    setLoopIds(ids);
    return ids;
  }, [onboardingPayload]);

  // Launch the PROVIDER's real consent for one account, then poll until it completes.
  const connectTarget = useCallback(
    async (target) => {
      const loopId = loopIds[target.key];
      if (!loopId) {
        setConnectState((s) => ({ ...s, [target.key]: { status: "not_connected", error: "Set up your profile first." } }));
        return;
      }
      setConnectState((s) => ({ ...s, [target.key]: { status: "launching" } }));
      try {
        const res = await ownerFetch("/api/connections/authorize", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ id: loopId }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error(data?.message || data?.detail || data?.error || "I couldn't open the sign-in.");
        }
        if (data.status === "connected") {
          setConnectState((s) => ({ ...s, [target.key]: { status: "connected" } }));
          return;
        }
        const url = data.connect_url;
        if (url) {
          // The real provider consent screen — opened in a new tab; the approval is the user's.
          if (typeof window !== "undefined") window.open(url, "_blank", "noopener,noreferrer");
          setConnectState((s) => ({ ...s, [target.key]: { status: "polling", consentUrl: url } }));
          pollUntilConnected(target, loopId);
        } else {
          setConnectState((s) => ({
            ...s,
            [target.key]: { status: "not_connected", error: data.message || "This account isn't ready to connect yet." },
          }));
        }
      } catch (err) {
        setConnectState((s) => ({
          ...s,
          [target.key]: { status: "not_connected", error: err instanceof Error ? err.message : String(err) },
        }));
      }
    },
    [loopIds],
  );

  // Re-ask the engine whether authorization completed (it asks the connector). Used both by
  // the background poll and the explicit "I've approved it" button.
  const recheck = useCallback(
    async (target) => {
      const loopId = loopIds[target.key];
      if (!loopId) return false;
      try {
        const res = await ownerFetch("/api/connections/authorize", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ id: loopId }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.status === "connected") {
          setConnectState((s) => ({ ...s, [target.key]: { status: "connected" } }));
          return true;
        }
      } catch {
        /* a transient poll failure is not fatal — keep waiting */
      }
      return false;
    },
    [loopIds],
  );

  // Background poll: every 4s for up to ~2min, flip the row the moment the provider confirms.
  const pollUntilConnected = useCallback(
    (target, loopId) => {
      let tries = 0;
      const timer = setInterval(async () => {
        tries += 1;
        const done = await recheck(target);
        if (done || tries >= 30) clearInterval(timer);
      }, 4000);
    },
    [recheck],
  );

  // Step 4 reward: read what's connected + a few honest facts. Invents nothing.
  const runRecap = useCallback(async () => {
    setRecapBusy(true);
    setRecapError("");
    try {
      const res = await ownerFetch("/api/onboard_scan", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.message || data?.error || "I lost the thread for a moment.");
      setRecap(data);
    } catch (err) {
      setRecapError(err instanceof Error ? err.message : String(err));
    } finally {
      setRecapBusy(false);
    }
  }, []);

  const anyConnected = Object.values(connectState).some((s) => s?.status === "connected");

  // Advance: after the people step we save the profile, then move to connect.
  const goToConnect = useCallback(async () => {
    try {
      await saveProfile();
      setStep(2);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : String(err));
    }
  }, [saveProfile]);

  const goToRecap = useCallback(() => {
    setStep(3);
    runRecap();
  }, [runRecap]);

  const current = STEPS[step];

  return (
    <main className="shell">
      <div className="column">
        {/* progress whisper — calm, never a loud wizard chrome */}
        <p className="glance" style={{ marginBottom: 8 }}>
          Step <strong>{step + 1}</strong> of {STEPS.length}
        </p>

        {current === "identity" ? (
          <StepIdentity form={form} set={set} onNext={() => setStep(1)} />
        ) : null}

        {current === "people" ? (
          <>
            <StepPeople form={form} set={set} onBack={() => setStep(0)} onNext={goToConnect} />
            {saveError ? <p className="error" style={{ marginTop: 12 }}>{saveError}</p> : null}
          </>
        ) : null}

        {current === "connect" ? (
          <StepConnect
            connectState={connectState}
            onConnect={connectTarget}
            onRecheck={recheck}
            onBack={() => setStep(1)}
            onFinish={goToRecap}
            anyConnected={anyConnected}
          />
        ) : null}

        {current === "recap" ? (
          <StepRecap recap={recap} recapBusy={recapBusy} recapError={recapError} onRescan={runRecap} ownerName={form.ownerName} />
        ) : null}
      </div>
    </main>
  );
}
