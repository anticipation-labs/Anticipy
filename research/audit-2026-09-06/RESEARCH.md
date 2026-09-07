# Research evidence and design decisions

Researched 2026-09-06/07 using primary sources. This document records design
evidence, not successful Anticipy tests. Three independent research lanes were
used as required by the Deep Research skill. No paid calls were made for research.

## Harnesses and general tasks

A harness is the software surrounding the model: it supplies context, runs the
decision loop, routes tools, records results, persists progress, enforces access,
and enables recovery and evaluation. A workflow fixes the orchestration path;
an agent selects its own actions. Anticipy's laws reserve interpretation for a
model with context while allowing deterministic controls over ownership and
effects. Generality requires unfamiliar compositions, not fifty renamed copies
of one task.

| Primary source | Supported claim | Application and limits |
| --- | --- | --- |
| [Anthropic: Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents), Apr 8 2026 | Durable history, harness and execution sandbox can be separate; credentials can remain outside execution. | Record correlated input, context, actions and receipts; restart each layer. Architectural experience, not proof of a universal optimum. Parent independently verified this page. |
| [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), Dec 19 2024 | Distinguishes predetermined workflows from model-directed agents. | Prefer simple measured components; preserve model choice of tools. Tooling examples have aged. |
| [OpenAI: Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices), living docs | Representative, held-out, edge and adversarial cases; calibrate model judgments with humans. | Freeze hidden outcomes and inspect failures and apparent successes. Model judges have position/verbosity bias; hosted platform availability is separate from methodology. |
| [OpenAI: Trace grading](https://developers.openai.com/api/docs/guides/trace-grading), living docs | Traces help locate where execution diverges. | Retain retrieved source IDs and provider arguments. A trace alone does not prove a completed task. |
| [WebArena](https://webarena.dev/og/) and [original paper](https://arxiv.org/abs/2307.13854), Jul 25 2023 | Functional browser tasks use persistent websites and programmatic outcome checks. | Run actual browser interactions against isolated sites; inspect resulting world state. Does not verify current live OAuth/provider behavior. |
| [Apple ToolSandbox](https://arxiv.org/html/2408.04682v1), Aug 8 2024 | Stateful multi-turn tasks need required and prohibited events, without one fixed trajectory. | Exercise missing context, disabled tools and retries. User simulators can hallucinate; original benchmark omits important auth/asynchronous cases. |
| [Sierra tau-bench](https://arxiv.org/html/2406.12045v1), Jun 17 2024 | pass^k measures all repeated trials succeeding, unlike at-least-one pass@k. | Repeat critical tasks; supplement final-state checks with authorization checks. Original reward can miss a skipped required confirmation. |
| [AgentDojo](https://arxiv.org/html/2406.13352v1), Jun 19 2024 | Measure benign utility, utility under attack and attacker success separately. | Inject instructions into untrusted emails, pages and memory; check both exfiltration and legitimate completion. Fixed attacks do not establish adaptive robustness. |
| [AWS: Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/), announced Jan 15 2021 | Caller request IDs, atomic recording and reconciliation address uncertain retry outcomes. | Inject response loss after provider success and duplicate callbacks. A provider without deduplication/read-back cannot promise exactly-once effects. |

## Memory

Working context, remembered episodes, consolidated facts and learned procedures
are different stores. Retrieval quality, reasoning quality, attribution, temporal
updates, isolation, deletion and crash durability need separate measurements.
Neither a correct answer nor a committed local SQLite transaction proves all of
them. Memory content is evidence, not authorization.

| Primary source | Supported claim | Application and limits |
| --- | --- | --- |
| [CoALA](https://arxiv.org/html/2309.02427v3), Sep 2023 / TMLR 2024 | Episodic, semantic and procedural memory have distinct roles; retrieval supplies working context. | Describe Anticipy's actual stores with this taxonomy. Conceptual architecture, not performance proof. |
| [LongMemEval](https://xiaowu0162.github.io/long-mem-eval/) and [authors' repository](https://github.com/xiaowu0162/LongMemEval), Oct 2024 / ICLR 2025 | 500 questions cover extraction, cross-session/temporal reasoning, updates and abstention; evidence-only histories diagnose retrieval. | Compare normal retrieval with evidence-only runs. Conversational QA does not test external actions or erasure. |
| [LoCoMo paper](https://aclanthology.org/2024.acl-long.747/) and [Snap repository](https://github.com/snap-research/LoCoMo), Aug 2024 | Ten released conversations, with human-reviewed synthetic long histories; QA, summaries and dialogue. | Useful long-history patterns; too narrow to claim population or workflow coverage. |
| [Memora](https://arxiv.org/html/2604.20006v1), Apr 21 2026 | Score both inclusion of current information and absence of superseded information. | Test corrections, retractions and historical queries. Preprint with simulated conversations and explicitly limited social/multi-user scope. |
| [Mem0 paper](https://arxiv.org/html/2504.19413v1), Apr 28 2025 | Evaluates extraction/consolidation/retrieval; excludes adversarial/unanswerable LoCoMo questions. | Published average gains do not establish abstention or deletion. Vendor-authored comparison; do not import threshold-based semantic rules. |
| [Zep facts](https://help.getzep.com/facts), [security](https://help.getzep.com/memory-security), [deletion](https://help.getzep.com/deleting-data-from-the-graph), living docs | Event time differs from ingestion time; authenticated identity controls access; deleting an episode can leave information in shared summaries. | Follow provenance into derived stores and test erasure there. Product semantics, not proof of extraction accuracy. |
| [Cloudflare container lifecycle](https://developers.cloudflare.com/containers/concepts/architecture/), updated Aug 28 2026; [DO storage](https://developers.cloudflare.com/durable-objects/best-practices/access-durable-objects-storage/) | Container disks are ephemeral; Durable Object storage is separately persistent. | Kill immediately after acknowledgement and restore from external storage. Parent independently verified container lifecycle. |
| [Cloudflare R2 consistency](https://developers.cloudflare.com/r2/reference/consistency/), updated Apr 30 2026; [Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/) | Completed writes/deletes are strongly consistent; competing writes use last-completer-wins; conditional writes are available. | Test old snapshots finishing after new snapshots and deletion. Strong consistency does not impose application ordering. Parent independently verified consistency. |
| [SQLite corruption guidance](https://sqlite.org/howtocorrupt.html) and [backup API](https://sqlite.org/backup.html) | Copying an active database as an ordinary file can mix transaction versions; database-aware backup gives a consistent snapshot. | Verify backup API and restored integrity, then separately test acknowledged-write durability. |

## Connections and messaging

| Primary source | Supported claim | Application and limits |
| --- | --- | --- |
| [Composio sessions](https://docs.composio.dev/kb/guide/mcp-tool-router-sessions), verified Aug 17 2026 | Sessions scope tools/accounts to a stable user; they are not conversation memory; deleting one leaves connected accounts. | Test session/account ownership and full reset separately. Confirm actual API version. |
| [Composio connected accounts](https://docs.composio.dev/reference/api-reference/connected-accounts), living API v3.1 | Disablement, deletion and provider-grant revocation differ. Opt-in callback identity verification prevents a forwarded Connect Link attaching another person's account. | Test authenticated callback identity and single-use ten-minute session URI. Parent independently verified; provider revocation endpoint behavior remains untested. |
| [Composio search](https://docs.composio.dev/reference/api-reference/tool-router/postToolRouterSessionBySessionIdSearch) and [execute](https://docs.composio.dev/reference/api-reference/tool-router/postToolRouterSessionBySessionIdExecute) | Search is session-scoped; schemas may be partial; execution accepts account selection. | Resolve full schemas and select the intended account explicitly. Documentation varies on fallback when selection is disabled. |
| [Composio event reception](https://docs.composio.dev/docs/setting-up-triggers/subscribing-to-events) and [triggers](https://docs.composio.dev/kb/guide/platform-triggers) | HMAC covers raw body, ID and timestamp; delivery is at least once; local subscription bypasses production authentication. | Test raw-body changes, stale signatures and concurrent replays, plus one real provider-origin event. |
| [Sendblue webhooks](https://docs.sendblue.com/getting-started/webhooks/) | Shared-secret authentication, retries, duplicate messages, status callbacks and account-wide delivery. | Verify genuine callback header contract; do not assume Verify-product HMAC applies to messages. Current page does not name the header. |
| [Sendblue sending](https://docs.sendblue.com/getting-started/sending-messages/) | Real iMessage/SMS; line ownership matters; SMS SENT may be terminal while iMessage normally reaches DELIVERED. | Provider acceptance and handset receipt are different evidence. Sendblue sandboxes are compute, not fake messaging. |
| [Twilio test credentials](https://www.twilio.com/docs/iam/test-credentials) | Selected REST tests do not charge or contact phones, and generate no SMS status callbacks. | Useful validation tests, not delivery proof. Requires separate test credentials. |
| [Twilio secure webhooks](https://www.twilio.com/docs/usage/webhooks/webhooks-security) | Signature depends on exact external URL and all received request parameters; JSON verification differs. | Test proxy URL reconstruction, query strings, form expansion and authentic callbacks. |

## Evidence gaps to close in Anticipy

- Inventory actual API/SDK versions, deployed routes and ownership checks.
- Run fifty synthetic owners with distinct contacts, multi-session histories,
  corrections, uncertainty, delayed tasks and cross-application outcomes.
- Inspect resulting state and prohibited effects independently of model prose.
- Test crash recovery, snapshot ordering, deleted-owner resurrection and private
  data isolation across every store and derived artifact.
- Exercise real Composio consent/revocation and real phone delivery separately
  from local simulations; record unavailable credentials explicitly.
- Reconcile local source with deployed API, brain, extension and App Store build.

Every application recommendation above is an inference from the stated source
contract. None is a claim that Anticipy already implements it or has passed it.
