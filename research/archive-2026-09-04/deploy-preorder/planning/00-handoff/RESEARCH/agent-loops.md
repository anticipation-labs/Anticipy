# Agent persistence, retry, and verification patterns

Research date: 2026-05-30. All sources are official docs or `main`-branch
source on GitHub at fetch time. Read-only desk research for Anticipy's Ralph
loop.

## 1. browser-use (Python, LLM-driven browser agent)

Source: `browser_use/agent/service.py`, `views.py`, `judge.py`.

**Retry / failure** is centralized in `_handle_step_error`. `AgentSettings`
defaults: `max_failures=5`, `max_actions_per_step=5`, `llm_timeout=60s`,
`step_timeout=180s`, `final_response_after_failure=True` (after max, one
more LLM call with only `done` exposed, forcing clean termination),
`planning_replan_on_stall=3` (nudge LLM to revise plan). On
`ModelRateLimitError`/`ModelProviderError`, `fallback_llm` swaps in and
retries once.

**Loop detection**: `ActionLoopDetector`. Each action gets a normalized
hash. Rolling 20-entry window. At 5/8/12 repetitions, escalating nudges.
Page stagnation (same URL + DOM-text SHA-256 + element count for >=5
steps) triggers a separate nudge. Soft, never blocks.

**Verification** is `judge.py`, a separate LLM call after `done`, given the
task, optional ground truth, step trajectory, and last N screenshots
(default 10). Returns `JudgementResult{verdict, failure_reason,
impossible_task, reached_captcha}`. Prompt explicitly says "be initially
doubtful of the agent's self reported success."

**Persistence**: `AgentState` Pydantic (designed for checkpointing per
docstring): `consecutive_failures`, `plan`, `paused`,
`message_manager_state`, `loop_detector`. No durable store; caller
serializes.

**Cost**: `TokenCost` tracks usage. No kill switch; budget enforced by
step count with soft warning at 75% of `max_steps`.

**Login / CAPTCHA**: `MissingCookieException` surfaces as a step failure.
CAPTCHA is detected post-hoc by the judge, or
`browser_session.wait_if_captcha_solving()` awaits a human solve.

## 2. LangGraph (state-machine agent framework)

Source: `libs/checkpoint/.../base/__init__.py`, `libs/langgraph/.../types.py`.

**Persistence is the headline feature.** Graph state is a typed `Checkpoint`
TypedDict `{v, id, ts, channel_values, channel_versions, versions_seen,
updated_channels}` keyed by `thread_id`. Implementations: `InMemorySaver`,
`AsyncSqliteSaver`, `AsyncPostgresSaver`. Each superstep writes a new
checkpoint. Restart = load latest for `thread_id`, resume from same node.
`Durability` is `'sync' | 'async' | 'exit'`.

**Retry** is per-node via `RetryPolicy(initial_interval=0.5,
backoff_factor=2.0, max_interval=128.0, max_attempts=3, jitter=True,
retry_on=default_retry_on)`. `retry_on` accepts exception classes or a
callable. Defaults skip `ValueError`/`TypeError` (logic bugs). Separate
`TimeoutPolicy`. No global agent retry; each node decides.

**Verification** is not built in; wire as a conditional edge or evaluator
node.

**User-in-loop**: `interrupt(payload)` inside a node suspends the graph and
persists state. Resume by passing `Command(resume=value)`. Canonical
"wait for user to log in, then continue" pattern.

**Cost gating**: not built in.

## 3. CrewAI (multi-agent orchestration)

Source: `lib/crewai/src/crewai/task.py`, `agents/crew_agent_executor.py`.

**Retry + verify combined into "guardrails"**: each `Task` accepts
`guardrail` (single) or `guardrails` (list), Python callables that validate
output before passing to the next task. `guardrail_max_retries=3`. On
failure the executor re-prompts with the guardrail's complaint. Closest
thing in any framework to "verify, retry with feedback."

**Agent loop**: `_invoke_loop_react()` or `_invoke_loop_native_tools()`.
Caps at `max_iter`. On hit, `handle_max_iterations_exceeded` forces a final
answer. Context-window overflow auto-detected
(`is_context_length_exceeded`) and handled by truncation.

**Persistence**: minimal. `Task.replay_from_task` replays from saved message
history. No checkpointer abstraction.

**Cost**: `enforce_rpm_limit` (RPM) and TokenCalcHandler tracking. No kill.

**User-in-loop**: `ask_for_human_input=True`. Synchronously blocks for
stdin or a provider-defined input source. No async page-back.

## 4. Open Interpreter (local code-running agent)

Source: `interpreter/core/respond.py`. `while True` in `respond()`. Errors:
`litellm.BudgetExceededError` -> print, `break` (hard kill); `RateLimitError`
with "exceeded"/"insufficient_quota" -> billing message, re-raise; "not
have access" -> prompt user to fall back to OI's hosted `i` model; Auth
errors -> verbose "how to set API key." Verification is weak: loop_message
"take a screenshot and verify"; loop_breakers are string-match phrases.
No LLM-judge. Persistence: `interpreter.messages` in memory. Cost:
`--max_budget` -> `litellm._current_cost` -> `BudgetExceededError` hard
kill. Human-in-loop: `confirmation` yield before each code execution.

## 5. AutoGen v0.4 (Microsoft, multi-agent teams)

Source: `_round_robin_group_chat.py`, `agents/_assistant_agent.py`. Retry:
`AssistantAgent.max_tool_iterations=1` (iteration count, not retry-on-fail).
Verification: `TerminationCondition` primitive, like `TextMentionTermination
("TERMINATE")`, `MaxMessageTermination(n)`, composable with `&`/`|`. Reviewer
agent that emits "TERMINATE" only when output passes is the canonical
verify pattern. Persistence: every team/agent implements
`save_state`/`load_state` returning Pydantic (e.g. `RoundRobinManagerState`
with message_thread, current_turn, next_speaker_index). Human-in-loop:
`UserProxyAgent` as first-class agent, often nested as outer.

## 6. Anthropic "Building effective agents" (Dec 2024)

Source: anthropic.com/research/building-effective-agents .

Most successful production agents use simple composable patterns, not
frameworks. Patterns:
1. **Augmented LLM** = LLM + retrieval + tools + memory.
2. **Prompt chaining** = sequential LLM calls with a gate between each.
3. **Routing** = classify, dispatch to specialized prompt/model. Quote:
   "Route easy/common questions to smaller, cost-efficient models like
   Claude Haiku 4.5 and hard/unusual questions to more capable models like
   Claude Sonnet 4.5."
4. **Parallelization** (sectioning + voting) for guardrails + multi-view.
5. **Orchestrator-workers** = central LLM decomposes, dispatches, synthesizes.
6. **Evaluator-optimizer** = LLM_A produces, LLM_B evaluates, loop until
   evaluator passes. *This is the principled name for the Ralph loop.*
7. **Agents** = LLM in a tool loop with environmental ground truth. Quote:
   "during execution, it's crucial for the agents to gain 'ground truth'
   from the environment at each step." Must include "stopping conditions
   (such as a maximum number of iterations)" and "pause for human feedback
   at checkpoints or when encountering blockers."

## 7. "Ralph loop" prior-art search

No published framework or paper uses "Ralph loop" as a term of art. The
mechanic (generate -> evaluate -> refine -> commit -> repeat) is Anthropic's
**evaluator-optimizer**. Community names: ReAct loop, agentic loop,
self-correction loop. Treat "Ralph loop" as internal Anticipy shorthand.

## Comparison

| Framework | Retry | Verify | Persist | Wake-up | Cost cap | Human-in-loop |
|---|---|---|---|---|---|---|
| browser-use | max_failures=5, fallback LLM, replan at 3, loop detector | LLM judge w/ screenshots + ground truth | AgentState Pydantic, caller stores | None | Token tracking only | MissingCookieException + captcha wait |
| LangGraph | RetryPolicy per node, exp backoff, jitter | Manual (conditional edge) | Checkpoint by thread_id, SQLite/Postgres | interrupt() + Command(resume=) | None | interrupt() |
| CrewAI | guardrail_max_retries=3, re-prompt with critique | guardrail callable per task | Replay from message history | None | RPM only | ask_for_human_input blocks |
| Open Interpreter | Broad try/except, fall back to hosted model | "Take a screenshot and verify" prompt | interpreter.messages JSON | None | --max_budget hard kill | Per-code-block y/n |
| AutoGen v0.4 | max_tool_iterations only | TerminationCondition (composable) | save_state/load_state Pydantic | None | None | UserProxyAgent |
| Anthropic principles | "stopping conditions" | "ground truth at each step" | n/a | Pause at checkpoints | Route by difficulty | Pause at blockers |

## Recommendations for Anticipy's Ralph loop

1. **Goal as durable record.** SQLite table `goals(goal_id, user_id, prompt,
   status, budget_remaining_usd, created_at, next_attempt_at)`. Status:
   `pending | running | blocked | waiting_human | waiting_clock | done |
   abandoned`. LangGraph proved `thread_id`-keyed SQLite is the right
   shape. Avoid memory.jsonl; has known unbounded-growth bugs in this repo.

2. **Per-step state in sibling table.** `goal_steps(goal_id, step_n,
   action_hash, screenshot_path, llm_output_json, error, duration_ms)`.
   Mirrors browser-use `AgentHistoryList`. Enables replay and judge.

3. **Failure taxonomy with code-level dispatch** (copy browser-use):
   - `ModelRateLimitError`/`ModelProviderError` -> switch to fallback LLM,
     retry once.
   - `MissingCookieException` (login wall) -> status `waiting_human`, SMS
     user with deep link, return.
   - `CaptchaDetected` -> retry on stealth browser if available; else
     status `blocked`.
   - `NetworkTimeout` -> exponential backoff (LangGraph semantics: 0.5,
     2.0, 8.0, 32.0 s, max 3 attempts).
   - `ElementNotFound` -> let LLM see failure, replan (consecutive counter,
     nudge at 3, max_failures=5, direct browser-use port).
   - `Unknown` -> 1 retry, then abandon with full trace.

4. **Verification = two-layer.** Per-step ground truth: URL changed?
   DOM-text hash changed? Expected selector exists? Cheap, deterministic.
   End-of-goal: Sonnet 4.6 judge call with trajectory summary + last 5
   screenshots, returning Pydantic `{verdict, failure_reason,
   needs_human}`. Copy browser-use `judge.py` system prompt verbatim
   (especially "be initially doubtful of the agent's self reported
   success").

5. **Wake-up scheduling.** `next_attempt_at` unix timestamp. Single
   `wake_scheduler` coroutine polls SQLite every 30 s for
   `status='waiting_clock' AND next_attempt_at <= now()`. SMS-reply
   webhook flips `status='waiting_human'` rows back to `pending`. Strictly
   more reliable than in-memory `asyncio.sleep`.

6. **Cost gating per goal.** From `project_cost_ceiling_200_per_user_year`:
   $0.002/task avg -> per-goal cap ~$0.05. Track in
   `budget_remaining_usd`, subtract after every LLM call. Hit zero ->
   status `blocked`, SMS "this is costing more than expected, want me to
   keep trying? YES/NO/EDIT" per `feedback_sms_pre_confirm`. Open
   Interpreter's `BudgetExceededError` is the right shape; the user prompt
   is the right policy.

7. **Routing by difficulty** (Anthropic). Default DeepSeek V4 Flash via
   OpenRouter (per `project_fara_build_plan`). Escalate to Sonnet 4.6 ONLY
   when `consecutive_failures >= 3`, OR judge says `needs_human`, OR page
   is canvas-heavy (Sheets, Figma).

8. **Soft loop detection.** Port browser-use `ActionLoopDetector` directly.
   Action hash, 20-step window, nudge at 5/8/12. Page fingerprint
   stagnation at >=5. Never blocks; only adds context.

## Anti-patterns these frameworks tried and abandoned

- **Hard-killing on loop detection.** browser-use originally blocked repeated
  actions; current code only nudges. Legit progress can look like repetition
  (e.g. paginating 50 results).
- **One global retry counter.** CrewAI's `max_retries` got deprecated in favor
  of per-guardrail `guardrail_max_retries`. Different failure classes need
  different budgets.
- **In-memory-only state.** Every framework eventually added explicit
  serialization. LangGraph's checkpointer is load-bearing for restart.
- **Synchronous human-in-loop.** CrewAI's `ask_for_human_input` blocks the
  process. LangGraph's `interrupt()` + checkpoint is strictly better; process
  exits, durable state survives, resume on user reply.
- **Letting the model self-grade.** browser-use's judge prompt explicitly says
  don't trust the agent's self-reported `success=True`. Judge is a separate
  LLM call with a separate prompt and visual evidence.
- **One model for everything.** Anthropic, browser-use (`fallback_llm`),
  CrewAI (`function_calling_llm`) all converged on tiered models. Route by
  cost, escalate on failure.
