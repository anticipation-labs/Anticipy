# Verification Protocol

**Why this file exists:** the owner has been burned repeatedly by claims of "done" that weren't end-to-end true. This file is the rulebook that makes that impossible going forward.

---

## The 1 rule

**A row in PROGRESS_LOG.md is DONE only if it cites a real artifact and the exact command that produced it.** Otherwise it stays PARTIAL with the gap named.

No "should work." No "agent reported shipped." No "imports are clean." Only "I ran X, got Y, here is the path."

---

## What counts as a real artifact

| Type of work | Required proof |
|---|---|
| HTTP endpoint works | curl command + first 200 chars of response body |
| Engine module loads | `python3 -c "import X"` exit 0 |
| File exists in build output | `ls -la PATH` showing size + mtime |
| Tests pass | `pytest ...` output with `X passed, 0 failed` |
| Live site serves new artifact | `curl -sI URL` showing new `etag` or `content-length` |
| Code change landed | `git log --oneline -1 PATH` showing the commit + file in diff |
| UI rendered correctly | screencap path + Read the PNG inline (or via Chrome MCP, attach the screenshot) |
| Action executed in real Chrome | tab URL after action + DOM snapshot or screenshot + assertion |
| SMS sent and delivered | Twilio SID + status `delivered` from `/api/twilio/status` callback |
| Email sent and delivered | Resend message ID + delivery webhook event |
| Voice call completed | Twilio Call SID + status `completed` with duration > 0 |
| Background process alive | pid + etime + last log line within last 60s |

## What does NOT count as proof

- "Agent reported success"
- "API returned 200"
- "Build finished without errors"
- "Imports are clean"
- "5 unit tests pass" (only matters if those tests exercise the user-visible path)
- "Should work based on the code"
- "Did it before, it works"
- "Other agents verified it"

If any of those is the basis for DONE, the row is PARTIAL until I personally produce a real artifact.

---

## How to write a DONE row in PROGRESS_LOG.md

Template:
```
| P{N}-{i} | {one-line outcome} | claude | DONE | {verification: command run + observed result + artifact path; under 200 chars} |
```

Good example:
```
| P1-3 | Engine /health responds | claude | DONE | curl http://127.0.0.1:49671/health returned {"ok":true,"pid":7354,"port":49671} at 15:04 UTC; engine pid 7354 etime 90m |
```

Bad example (would be rejected):
```
| P1-3 | Engine working | claude | DONE | I think so |
```

## The honesty self-check (mandatory before any DONE claim)

Before writing DONE, I run mentally through these 4 questions:

1. **What artifact did I personally observe?** If "I don't have one," → PARTIAL.
2. **Could I reproduce that artifact right now?** If "not sure," → PARTIAL.
3. **Did the artifact prove the USER-visible outcome, or just an internal layer?** If only the latter, → PARTIAL with "needs user-visible verification" in notes.
4. **Has the state I'm claiming been verified within the last 10 minutes?** If older, → re-verify before claiming.

## Per-phase verification gates

Each phase in ARCHITECTURE.md has a specific "GATE" — the exact command + expected output that proves the phase is done. The gate must be re-runnable. The gate output gets pasted into PROGRESS_LOG.md.

Example gate format:
```
PHASE 1 GATE:
  Command: bash scripts/test/extension-handshake.sh
  Expected: "HANDSHAKE: OK" within 10s
  Pasted output: <full stdout>
  Re-runnable: yes
  Last passed: 2026-05-30 15:30 UTC
```

## When verification fails

- Status flips to BROKEN, not DONE.
- The failing artifact is documented (error message, exit code, stack trace).
- A new sub-row gets added with the recovery plan.
- I tell the owner immediately (not at the end).

## When the user asks "is X done?"

- I open PROGRESS_LOG.md, find the row, quote the cited verification.
- If the verification is older than 10 minutes, I re-run it and update.
- I never answer from memory of "I think I did that yesterday."

## Survival under compaction

This protocol persists in this file. If the next session forgets, reading this file restores it.

The single most important thing: **the DONE column in PROGRESS_LOG.md is the only source of truth about what's done.** Not my words. Not agent reports. Just that table with cited proofs.
