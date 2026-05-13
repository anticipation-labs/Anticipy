/**
 * Unified LLM call surface for the agent-team routes (plan/verify/critic/
 * reflect). Tries Cerebras (free 1M tokens/day) first, falls back to Groq
 * (free, llama-3.3-70b), then Mistral (free, mistral-small-latest). When
 * all three are down the route surfaces a 502 to the caller — the
 * extension already handles a missing verdict gracefully.
 *
 * Use this from every route handler. Single source of truth for the
 * fallback chain. Kimi/Moonshot removed 2026-05-13 per v-final-prototype
 * provider whitelist.
 */

import { callCerebrasJson, cerebrasAvailable } from "./cerebras";
import { callGroqJson, groqAvailable } from "./groq";
import { callMistralJson, mistralAvailable } from "./mistral";

export interface AgentMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface AgentLLMOptions {
  system?: string;
  messages: AgentMessage[];
  temperature?: number;
  maxTokens?: number;
}

export interface AgentLLMResult<T = any> {
  data: T;
  provider: "cerebras" | "groq" | "mistral";
}

/**
 * Tries Cerebras Qwen3-235B (free), Groq llama-3.3-70b (free), Mistral
 * mistral-small-latest (free) in order. Each is free-tier limited to ~30
 * RPM but the quota pools are independent — combined ~90+ RPM. Stops at
 * first success.
 */
export async function callAgentJson<T = any>(opts: AgentLLMOptions): Promise<AgentLLMResult<T>> {
  const errors: string[] = [];
  const callArgs = {
    system: opts.system,
    messages: opts.messages,
    temperature: opts.temperature ?? 0.1,
    maxTokens: opts.maxTokens ?? 1200,
  };

  if (cerebrasAvailable()) {
    try {
      const data = await callCerebrasJson<T>(callArgs);
      return { data, provider: "cerebras" };
    } catch (e: any) {
      errors.push(`cerebras: ${e?.message || e}`);
    }
  }
  if (groqAvailable()) {
    try {
      const data = await callGroqJson<T>(callArgs);
      return { data, provider: "groq" };
    } catch (e: any) {
      errors.push(`groq: ${e?.message || e}`);
    }
  }
  if (mistralAvailable()) {
    try {
      const data = await callMistralJson<T>(callArgs);
      return { data, provider: "mistral" };
    } catch (e: any) {
      errors.push(`mistral: ${e?.message || e}`);
    }
  }

  throw new Error(`All agent LLM providers failed: ${errors.join(" | ")}`);
}

export function agentLLMAvailable(): boolean {
  return cerebrasAvailable() || groqAvailable() || mistralAvailable();
}
