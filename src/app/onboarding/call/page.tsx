"use client";

/**
 * Cold-start onboarding path 3a: phone call (stubbed).
 *
 * The user types a phone number. We post the call intent to the
 * local engine, which writes a stub record to a JSONL file with
 * is_stub set true. Twilio is not wired up yet. The UI never
 * pretends a call was placed. It only logs the intent and shows
 * an honest "we will call you back" confirmation.
 *
 * Brand: same dark and cream and gold palette and the same DM
 * Serif Display + Plus Jakarta Sans pairing as the rest of the
 * Anticipy app. No glass, no purple gradients.
 */

import { useCallback, useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

const LOCAL_ENGINE = "http://127.0.0.1:8731";

type Status =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "queued"; phone: string; queuedAt: string }
  | { kind: "error"; message: string };

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="min-h-screen bg-dark text-cream font-sans relative overflow-hidden"
      style={{
        backgroundImage:
          "radial-gradient(60rem 40rem at 50% -10%, rgba(200,169,126,0.10), transparent 70%)",
      }}
    >
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
}

function looksLikePhoneNumber(s: string): boolean {
  const cleaned = s.replace(/[^\d+]/g, "");
  if (!cleaned) return false;
  const digits = cleaned.replace(/\+/g, "");
  return digits.length >= 7 && digits.length <= 16;
}

export default function OnboardingCallPage() {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [intendedPrompt, setIntendedPrompt] = useState(
    "I want Anticipy to learn who matters in my life, what I am working on, "
    + "and what topics I want it to keep an ear out for."
  );
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [engineLive, setEngineLive] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        const r = await fetch(`${LOCAL_ENGINE}/health`, {
          cache: "no-store",
          mode: "cors",
        });
        if (!cancelled) setEngineLive(r.ok);
      } catch {
        if (!cancelled) setEngineLive(false);
      }
    };
    probe();
    const t = window.setInterval(probe, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  const submit = useCallback(async () => {
    if (!looksLikePhoneNumber(phone)) {
      setStatus({
        kind: "error",
        message: "That does not look like a phone number. Try again with country code.",
      });
      return;
    }
    setStatus({ kind: "submitting" });
    try {
      // Provision the local engine with the current Supabase token so
      // the engine can persist the stub under the user's data dir.
      const { data: sessionData } = await supabase.auth.getSession();
      const token = sessionData.session?.access_token;
      if (token) {
        await fetch(`${LOCAL_ENGINE}/api/provision`, {
          method: "POST",
          mode: "cors",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            auth_token: token,
            site_url: window.location.origin,
          }),
        }).catch(() => null);
      }

      const r = await fetch(`${LOCAL_ENGINE}/api/onboarding/call_stub`, {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: phone.trim(),
          name: name.trim() || null,
          intended_system_prompt: intendedPrompt.trim() || null,
        }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) {
        setStatus({
          kind: "error",
          message: String(j?.error || `request failed (status ${r.status})`),
        });
        return;
      }
      setStatus({
        kind: "queued",
        phone: phone.trim(),
        queuedAt: new Date().toISOString(),
      });
    } catch (e) {
      setStatus({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [phone, name, intendedPrompt]);

  return (
    <Shell>
      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        .fade-up { opacity: 0; animation: fadeUp 0.7s cubic-bezier(0.16,1,0.3,1) forwards; }
      `}</style>

      <nav className="fixed top-0 inset-x-0 z-20 flex items-center justify-between px-8 md:px-12 h-16 text-[12px] tracking-[0.2em] uppercase text-cream/40">
        <a href="/app" className="font-serif text-cream/80 tracking-normal text-[17px] normal-case">
          Anticipy
        </a>
        <div className="flex gap-7 items-center">
          <a href="/onboarding/chat" className="hover:text-cream/80 transition-colors">
            Chat instead
          </a>
          <a href="/app" className="hover:text-cream/80 transition-colors">
            Back to app
          </a>
        </div>
      </nav>

      <main className="px-8 md:px-20">
        <div className="min-h-screen flex flex-col justify-center max-w-[760px]">
          <p
            className="text-[11px] uppercase tracking-[0.22em] text-gold/80 font-medium mb-6 fade-up"
          >
            Onboarding, by phone
          </p>
          <h1
            className="font-serif text-[clamp(34px,6vw,68px)] leading-[1.05] tracking-[-0.02em] text-cream max-w-[18ch] fade-up"
            style={{ animationDelay: "60ms" }}
          >
            Let Anticipy call you to learn who matters.
          </h1>
          <p
            className="mt-7 text-[15px] leading-relaxed text-cream/55 max-w-[46ch] fade-up"
            style={{ animationDelay: "140ms" }}
          >
            A ten minute conversation, on your terms, no typing. We ask
            about the people around you, the topics you want us to listen
            for, and the things we should never touch. Then Anticipy is
            ready to go.
          </p>

          <div
            className="mt-12 grid gap-3 max-w-[440px] fade-up"
            style={{ animationDelay: "220ms" }}
          >
            <input
              aria-label="Your name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name (optional)"
              autoComplete="name"
              className="rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream placeholder:text-cream/30 outline-none focus:border-gold/50 transition-colors"
            />
            <input
              aria-label="Phone number"
              type="tel"
              inputMode="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1 555 123 4567"
              autoComplete="tel"
              className="rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream placeholder:text-cream/30 outline-none focus:border-gold/50 transition-colors"
            />
            <textarea
              aria-label="What you want Anticipy to focus on"
              value={intendedPrompt}
              onChange={(e) => setIntendedPrompt(e.target.value)}
              rows={4}
              className="rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream placeholder:text-cream/30 outline-none focus:border-gold/50 transition-colors resize-none"
            />

            <button
              onClick={submit}
              disabled={status.kind === "submitting" || !looksLikePhoneNumber(phone)}
              className="mt-2 rounded-pill px-8 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {status.kind === "submitting" ? "Queuing the call" : "Call me"}
            </button>

            {status.kind === "queued" && (
              <p className="mt-3 text-[12.5px] text-gold/90 leading-relaxed">
                Queued. Anticipy will call {status.phone} when the voice
                engine is live. This is a stub log only: no call has been
                placed yet. Voice provider is not wired up in this build.
              </p>
            )}
            {status.kind === "error" && (
              <p className="mt-3 text-[12.5px] text-gold/90 leading-relaxed">
                {status.message}
              </p>
            )}

            <p className="mt-4 text-[11.5px] text-cream/30 leading-relaxed">
              Honest state: the call is queued as a log entry on your
              Mac, marked is_stub true. When the voice provider is
              connected, queued entries will trigger a real outbound
              call. We never auto-create accounts or send messages on
              your behalf.
            </p>
            <p className="text-[11.5px] text-cream/30 leading-relaxed">
              Local engine:{" "}
              <span className={engineLive ? "text-gold/80" : "text-cream/50"}>
                {engineLive ? "connected" : "not connected"}
              </span>
            </p>
          </div>
        </div>
      </main>
    </Shell>
  );
}
