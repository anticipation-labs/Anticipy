"use client";

import { useState, FormEvent } from "react";
import { createClient } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost:54321",
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "placeholder-anon-key"
);

export default function AdminLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      setError("Invalid credentials.");
      setLoading(false);
      return;
    }

    router.push("/admin");
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center px-6"
      style={{ background: "var(--dark)" }}
    >
      <div className="w-full max-w-sm">
        <h1
          className="font-serif text-[32px] text-center mb-8"
          style={{ color: "var(--text-on-dark)" }}
        >
          Admin
        </h1>

        <form onSubmit={handleLogin} className="flex flex-col gap-4">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="px-4 py-3 rounded-lg text-[15px] outline-none"
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              color: "var(--text-on-dark)",
            }}
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="px-4 py-3 rounded-lg text-[15px] outline-none"
            style={{
              background: "var(--dark-elevated)",
              border: "1px solid var(--dark-border)",
              color: "var(--text-on-dark)",
            }}
          />

          {error && (
            <p className="text-red-400 text-[14px] text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="px-6 py-3 rounded-lg text-[15px] font-medium transition-colors disabled:opacity-60"
            style={{
              background: "var(--text-on-dark)",
              color: "var(--dark)",
            }}
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
