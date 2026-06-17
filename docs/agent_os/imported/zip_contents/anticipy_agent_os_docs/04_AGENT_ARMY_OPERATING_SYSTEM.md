# 04 — Agent Army Operating System

## The no-slop law

Many agents are useful only if each output is verified.

**No agent work counts until an independent skeptic tries to break it against a real artifact and fails.**

A builder can create. A builder cannot certify.

## Roles

### Foreman

Owns the mission, current truth, gate choice, and merge/revert decisions.

Inputs:

- Constitution.
- Current truth.
- Receipts.
- Failures.
- User decisions.
- Git state.

Outputs:

- One next gate.
- Agent briefs.
- Merge/revert decisions.
- Updated ledgers.

### Builder agents

Build code/docs/evals for a specific gate. They must include:

- changed files,
- commands run,
- receipt produced,
- known gaps,
- why this satisfies the gate.

### Skeptic agents

Try to prove the builder wrong. They should attack:

- self-attestation,
- stale base,
- false positives,
- vent/sarcasm,
- money/payment holes,
- wrong account,
- hidden trigger paths,
- browser prompt injection,
- mock-only success,
- unverified external state.

### Research agents

Search current docs and return decisions, not dumps.

Each research agent must return:

- what changed since last known state,
- recommended tool/model/architecture,
- citations/URLs,
- risks,
- decision.

### Integrator

Re-applies only verified patches to current HEAD. It does not blindly merge stale worktrees.

### Judge

Runs gates, receipts, hidden evals, and final decision.

## Agent spawning pattern

For each gate:

```text
Foreman writes gate spec
  ├─ Research agents x2-5 if current-state matters
  ├─ Builder agents x3-8 in isolated worktrees
  ├─ Skeptic agents x3-5 against best candidate
  ├─ Integrator re-applies to HEAD
  └─ Judge runs receipt + full suite + hidden eval
```

Do not run 50 agents on one vague mission. Run 50 agents on sharply-separated subproblems.

## Worktree rules

- Every builder gets its own worktree/branch.
- Worktree name includes gate and role.
- Builders may not edit receipt ledger except to propose entries.
- Builders may not edit hidden eval answers.
- Integrator checks diff against current HEAD.
- Stale-base patches are design input, not landable code.

## Loop cadence

The loop is not “run forever.”

Loop condition:

- Continue while the next gate has an objective receipt and no human-only account access is required.
- Halt when blocked by user credential/login, legal external clock, Apple notarization credentials, or a product decision.
- If 3 consecutive cycles produce no receipt, halt and re-aim. Do not grind.

## What counts as progress

Progress is:

- a gate closed with receipt,
- a false claim caught and reverted,
- a blocker reduced to a specific user action,
- a failure mode written with a tripwire.

Progress is not:

- tokens spent,
- agents spawned,
- code volume,
- “suite green” alone,
- a dashboard that does not drive real artifacts.

## Agent brief header

Every spawned agent must receive this header:

```text
You are building Anticipy: Donna from Suits for real life. Full done is not negotiable.
Prepare harmless work, park final press-go, ask only at irreversible step.
Never act on vents/jokes/sarcasm. Money/payment is a hard stop.
No self-attestation: real artifact read-back or not done.
You are not allowed to shrink scope, call mock proof product proof, or grade your own work.
Your output must include changed files, receipt, risks, and how a skeptic could break it.
```

## When to use billions of agents

Use huge parallelism for:

- codebase inventory,
- current research,
- fixture/persona generation,
- adversarial transcript generation,
- cross-browser/site reliability measurement,
- independent skeptics,
- documentation coverage.

Do not use huge parallelism for:

- one central risky edit,
- money policy,
- account secrets,
- final integration without a human-readable plan.

## Handling shutdowns and compaction

If laptop sleeps or context compresses:

1. Reload `CLAUDE.md` / router.
2. Read Constitution.
3. Read Current Truth.
4. Read Receipts.
5. Read Failures.
6. Check git state.
7. Check unfinished workflows/worktrees.
8. Resume the next gate.

Never ask the user to redefine done if it is already in the docs.
