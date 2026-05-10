/**
 * Unified LLM call surface for the agent-team routes (plan/verify/critic/
 * reflect). Tries Cerebras (free 1M tokens/day) first, falls back to Kimi
 * (paid Moonshot, when funded) on Cerebras failure. When BOTH are down
 * the route surfaces a 502 to the caller — the extension already handles
 * a missing verdict gracefully.
 *
 * Use this from every route handler. Single source of truth for the
 * fallback chain.
 */

import { callCerebrasJson, cerebrasAvailable } from "./cerebras";
import { callKimiJson, kimiAvailable } from "./kimi";

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
  provider: "cerebras" | "kimi";
}

/**
 * Calls Cerebras Qwen3-235B first (free), falls back to Kimi
 * moonshot-v1-128k on any Cerebras error. Returns parsed JSON.
 */
export async function callAgentJson<T = any>(opts: AgentLLMOptions): Promise<AgentLLMResult<T>> {
  const errors: string[] = [];

  if (cerebrasAvailable()) {
    try {
      const data = await callCerebrasJson<T>({
        system: opts.system,
        messages: opts.messages,
        temperature: opts.temperature ?? 0.1,
        maxTokens: opts.maxTokens ?? 1200,
      });
      return { data, provider: "cerebras" };
    } catch (e: any) {
      errors.push(`cerebras: ${e?.message || e}`);
    }
  }

  if (kimiAvailable()) {
    try {
      const data = await callKimiJson<T>({
        system: opts.system,
        messages: opts.messages,
        temperature: opts.temperature ?? 0.1,
        maxTokens: opts.maxTokens ?? 1200,
      });
      return { data, provider: "kimi" };
    } catch (e: any) {
      errors.push(`kimi: ${e?.message || e}`);
    }
  }

  throw new Error(`All agent LLM providers failed: ${errors.join(" | ")}`);
}

export function agentLLMAvailable(): boolean {
  return cerebrasAvailable() || kimiAvailable();
}
