"use client";

/**
 * Cold-start onboarding path 3b: conversation.
 *
 * The user has a back-and-forth conversation with the broker LLM
 * until enough is known about them to populate the same UserProfile
 * the engine consumes (name, role_title, people, do_not_touch,
 * comms_prefs, working_hours, recurring_topics, etc).
 *
 * Conversation state lives in the browser. Each turn posts the full
 * history to the broker (the same DeepSeek route the engine already
 * uses). When the broker emits the special END_OF_INTAKE token, the
 * client posts the full transcript to the local engine which
 * extracts and persists the profile via _save_profile.
 *
 * Brand: same charcoal / cream / gold and the same serif headers
 * as src/app/app/page.tsx. No glass, no purple.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";

const LOCAL_ENGINE = "http://127.0.0.1:8731";
const BROKER_URL = "/api/engine/model";
const MIN_EXCHANGES = 15;
const MAX_EXCHANGES = 25;
const END_TOKEN = "END_OF_INTAKE";

type Role = "agent" | "user";
type Turn = { role: Role; text: string };

const INTERVIEW_SYSTEM = `\
You are Anticipy, a calm wearable AI doing a conversational onboarding
interview. Your job over the next ${MIN_EXCHANGES} to ${MAX_EXCHANGES}
exchanges is to learn enough about the wearer to populate a structured
profile that will let you resolve "the boss", "us", "her", "him" on day
one without guessing.

Cover, across the conversation: the wearer's name and role; their day
to day work in one sentence; their timezone and working hours; the most
important people in their life including anchors like the boss, partner,
clients, reports; the 3 to 5 tools they live in every day; what they
want Anticipy to do for them and what is strictly off limits (a do not
touch list); how to reach them for critical vs non critical things and
quiet hours; recurring topics they want you to keep an ear out for.

Style: warm, short, one question per turn. If an answer is one word or
clearly thin, ask a single follow up that probes further (an example,
a name, an email). If an answer is rich, acknowledge briefly and move
to the next topic.

When you have enough to populate the profile (target: 15 to 25 paired
exchanges, hard cap 25), end with exactly one final line that contains
ONLY the token ${END_TOKEN} on its own line, after a one sentence wrap
up acknowledging that intake is complete.

Output: ONE assistant message per turn, plain text, no JSON, no
markdown headers, no role labels. Never produce ${END_TOKEN} before
turn 15.`;

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

function turnsToMessages(turns: Turn[]) {
  return turns.map((t) => ({
    role: t.role === "agent" ? "assistant" : "user",
    content: t.text,
  }));
}

async function askBroker(turns: Turn[]): Promise<string> {
  const r = await fetch(BROKER_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "deepseek/deepseek-v4-flash",
      messages: [
        { role: "system", content: INTERVIEW_SYSTEM },
        ...turnsToMessages(turns),
      ],
      max_tokens: 400,
      temperature: 0.4,
    }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(String(j?.error || `broker ${r.status}`));
  }
  const text = j?.choices?.[0]?.message?.content;
  if (typeof text !== "string" || !text.trim()) {
    throw new Error("broker returned empty content");
  }
  return text.trim();
}

function stripEndToken(s: string): { text: string; ended: boolean } {
  const lines = s.split(/\r?\n/);
  let ended = false;
  const out: string[] = [];
  for (const ln of lines) {
    if (ln.trim() === END_TOKEN) {
      ended = true;
      continue;
    }
    out.push(ln);
  }
  return { text: out.join("\n").trim(), ended };
}

export default function OnboardingChatPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [engineLive, setEngineLive] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const userExchanges = useMemo(
    () => turns.filter((t) => t.role === "user").length,
    [turns]
  );

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
    const t = window.setInterval(probe, 6000);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [turns, busy]);

  const start = useCallback(async () => {
    if (turns.length || busy) return;
    setBusy(true);
    setError(null);
    try {
      const opener = await askBroker([]);
      const { text } = stripEndToken(opener);
      setTurns([{ role: "agent", text }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [turns.length, busy]);

  useEffect(() => {
    if (!turns.length && !busy && !error) {
      start();
    }
  }, [turns.length, busy, error, start]);

  const persist = useCallback(async (finalTurns: Turn[]) => {
    setBusy(true);
    try {
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

      const transcript = finalTurns.map((t) => ({
        speaker_id: t.role === "agent" ? "AGENT" : "WEARER",
        text: t.text,
      }));
      const r = await fetch(`${LOCAL_ENGINE}/api/onboarding/chat_complete`, {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || j?.ok === false) {
        throw new Error(String(j?.error || `engine ${r.status}`));
      }
      setProfile(j.profile ?? null);
      setCompleted(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const submit = useCallback(async () => {
    const text = draft.trim();
    if (!text || busy || completed) return;
    setDraft("");
    setError(null);
    const userTurn: Turn = { role: "user", text };
    const after: Turn[] = [...turns, userTurn];
    setTurns(after);
    setBusy(true);
    try {
      const reply = await askBroker(after);
      const { text: agentText, ended } = stripEndToken(reply);
      const next: Turn[] = [
        ...after,
        { role: "agent" as Role, text: agentText || "Thank you, that is enough to get started." },
      ];
      setTurns(next);
      // Hard cap regardless of model intent.
      const exchanges = next.filter((t) => t.role === "user").length;
      const shouldEnd =
        ended || (exchanges >= MIN_EXCHANGES && exchanges >= MAX_EXCHANGES);
      if (shouldEnd) {
        await persist(next);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [busy, completed, draft, persist, turns]);

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
          <a href="/onboarding/call" className="hover:text-cream/80 transition-colors">
            Call instead
          </a>
          <a href="/app" className="hover:text-cream/80 transition-colors">
            Back to app
          </a>
        </div>
      </nav>

      <main className="px-8 md:px-20">
        <div className="min-h-screen flex flex-col max-w-[820px] pt-24 pb-12">
          <p className="text-[11px] uppercase tracking-[0.22em] text-gold/80 font-medium mb-6 fade-up">
            Onboarding, by conversation
          </p>
          <h1
            className="font-serif text-[clamp(28px,4.5vw,52px)] leading-[1.05] tracking-[-0.02em] text-cream max-w-[22ch] fade-up"
            style={{ animationDelay: "60ms" }}
          >
            A short conversation. Then Anticipy already knows who matters.
          </h1>
          <p
            className="mt-5 text-[14px] leading-relaxed text-cream/55 max-w-[52ch] fade-up"
            style={{ animationDelay: "140ms" }}
          >
            About {MIN_EXCHANGES} to {MAX_EXCHANGES} exchanges. Tell us who is
            around you, what you want us to listen for, and what we should
            never touch. We write everything to your local Mac.
          </p>

          <div
            ref={scrollRef}
            className="mt-10 flex-1 overflow-y-auto rounded-card border border-dark-border bg-dark-elevated px-5 py-4 max-h-[60vh] fade-up"
            style={{ animationDelay: "200ms" }}
          >
            {turns.map((t, i) => (
              <div
                key={i}
                className={`mb-4 flex ${
                  t.role === "agent" ? "justify-start" : "justify-end"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-card px-4 py-3 text-[14px] leading-relaxed ${
                    t.role === "agent"
                      ? "bg-dark border border-dark-border text-cream/85"
                      : "bg-cream text-dark"
                  }`}
                >
                  {t.text}
                </div>
              </div>
            ))}
            {busy && (
              <div className="mb-4 flex justify-start">
                <div className="max-w-[80%] rounded-card px-4 py-3 text-[13px] text-cream/45 bg-dark border border-dark-border">
                  thinking
                </div>
              </div>
            )}
          </div>

          {!completed && (
            <div
              className="mt-4 flex gap-3 fade-up"
              style={{ animationDelay: "260ms" }}
            >
              <input
                aria-label="Your reply"
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !busy) submit();
                }}
                disabled={busy}
                placeholder="Type your reply"
                className="flex-1 rounded-card bg-dark-elevated border border-dark-border px-5 py-4 text-[14px] text-cream placeholder:text-cream/30 outline-none focus:border-gold/50 transition-colors disabled:opacity-40"
              />
              <button
                onClick={submit}
                disabled={busy || !draft.trim()}
                className="rounded-pill px-7 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Send
              </button>
            </div>
          )}

          <p className="mt-4 text-[11.5px] text-cream/30 leading-relaxed">
            Exchanges: {userExchanges} / {MAX_EXCHANGES}. Local engine:{" "}
            <span className={engineLive ? "text-gold/80" : "text-cream/50"}>
              {engineLive ? "connected" : "not connected"}
            </span>
            .
          </p>

          {error && (
            <p className="mt-3 text-[12.5px] text-gold/90 leading-relaxed">
              {error}
            </p>
          )}

          {completed && profile && (
            <div
              className="mt-6 rounded-card border border-dark-border bg-dark-elevated px-6 py-5 fade-up"
              style={{ animationDelay: "60ms" }}
            >
              <p className="text-[12px] uppercase tracking-[0.18em] text-gold/80 mb-3">
                Profile saved
              </p>
              <p className="text-[14px] text-cream/85">
                {String(profile.name || "Profile")} created. The local engine
                now resolves the people and anchors from this conversation.
              </p>
              <a
                href="/app"
                className="mt-5 inline-flex items-center gap-3 rounded-pill px-8 py-4 text-[14px] font-medium bg-cream text-dark hover:bg-gold transition-colors"
              >
                Open Anticipy
              </a>
            </div>
          )}
        </div>
      </main>
    </Shell>
  );
}
