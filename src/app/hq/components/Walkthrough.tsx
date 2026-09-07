"use client";

import { useState } from "react";
import { useHQ } from "../lib/store";
import { Modal } from "./ui";

const STEPS = [
  {
    title: "This is HQ.",
    body: "Everything the company needs to do lives here. One list, one calendar, one place to look each morning.",
  },
  {
    title: "Work has an owner.",
    body: "Every task belongs to someone. Assign it to yourself, another person, or an agent — and it stays visible either way.",
  },
  {
    title: "Agents show their work.",
    body: "Watch progress step by step, answer their questions, and receive proof when they finish: files changed, tests run, receipts kept.",
  },
  {
    title: "Nothing risky happens silently.",
    body: "External emails, deployments, purchases, and destructive actions always stop and ask for approval first.",
  },
];

export default function Walkthrough() {
  const { setWalkthroughDone } = useHQ();
  const [step, setStep] = useState(0);
  const last = step === STEPS.length - 1;

  return (
    <Modal onClose={() => setWalkthroughDone(true)} label="Welcome walkthrough" width={440}>
      <div style={{ padding: "28px 28px 20px" }}>
        <p className="hq-mono" style={{ color: "var(--hq-gold)", marginBottom: 10 }}>
          {step + 1} / {STEPS.length}
        </p>
        <h2 className="hq-serif" style={{ fontSize: 26, marginBottom: 10 }}>{STEPS[step].title}</h2>
        <p style={{ color: "var(--hq-muted)", fontSize: 14, lineHeight: 1.6 }}>{STEPS[step].body}</p>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 26 }}>
          <button className="hq-btn" style={{ border: "none", color: "var(--hq-muted)" }} onClick={() => setWalkthroughDone(true)}>
            Skip
          </button>
          <div style={{ display: "flex", gap: 8 }}>
            {step > 0 && (
              <button className="hq-btn" onClick={() => setStep((s) => s - 1)}>Back</button>
            )}
            <button
              className="hq-btn hq-btn-primary"
              onClick={() => (last ? setWalkthroughDone(true) : setStep((s) => s + 1))}
            >
              {last ? "Start working" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
