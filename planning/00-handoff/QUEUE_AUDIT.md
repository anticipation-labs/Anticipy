# Task Queue Audit (2026-05-29)

Source: `curl http://127.0.0.1:8731/api/task_queue/list` snapshot in `/tmp/queue_audit.json`.

## Full breakdown

| Status      | Count |
| ----------- | ----- |
| done        | 146   |
| pending     | 33    |
| waiting     | 21    |
| **total**   | 200   |

The list endpoint caps the response at limit=200 by default, so older `done` rows may be truncated. The popover UX problem is the `waiting` bucket.

## Waiting classification

Total waiting: **21**.

| Category              | Count | Definition                                                                                                                                                  |
| --------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| stale_trivia          | 7     | `status=waiting`, `waiting_reason=needs_user_clarification`, `age > 3600s`, instruction matches a lexical trivia opener (e.g. "wait, when did", "when was") |
| dev_test_leak         | 10    | instruction contains a known synthetic test recipient pattern (`omarkebrahim+anticipy-*`, `@anticipy-test.local`, `@example.com`, "Anticipipeline")        |
| recovery_with_retry   | 3     | `waiting_reason` starts with `recovery:` (login_required, mfa_challenge). All currently at `retry_count=0`, so no rollup needed yet.                        |
| real                  | 1     | Anything else. The user genuinely needs to clarify.                                                                                                         |

## Example task_ids per category

### stale_trivia (5 of 7)

- `task-0c7aff325b744df6` (134m old): "wait, when did the Roman Empire fall"
- `task-452706c677f74ca3` (154m old): "wait, when did the Roman Empire fall"
- `task-c76feff5d88647c0` (190m old): "wait, when did the Roman Empire fall"
- `task-2d05077c7dfb4e43` (210m old): "wait, when did the Roman Empire fall"
- `task-83d68885b7cb4d33` (216m old): "wait, when did the Roman Empire fall"

### dev_test_leak (5 of 10)

- `task-5671f6cc04884720` (212m old): "Draft a thank you email to Amar Kebrahim plus Anticipipeline at gmail.com..."
- `task-d3fd8b42a1db4bb6` (212m old): same as above, duplicate fire
- `task-be72522882fd4c81` (211m old): "draft an email to omarkebrahim+anticipy-demo@gmail.com saying hello from the demo"
- `task-1274aa4d774d4217` (212m old): "Draft a thank you email to Amar Kebrahim plus Anticipipeline..."
- `task-55ad9111b140465b` (215m old): "send an email to omarkebrahim+anticipy-crashtest@gmail.com saying hello"

### recovery_with_retry (3 of 3)

- `task-5e5947eda31a4295` (187m old): "draft an email about today" (recovery:login_required, rc=0)
- `task-7350ab80f9644b82` (380m old): "send Sarah the deck" (recovery:mfa_challenge, rc=0)
- `task-d41909614e084ee5` (394m old): "send Sarah the meeting notes" (recovery:login_required, rc=0)

### real (1 of 1)

- `task-459d6c6e7ab64ce0` (376m old): "Send a follow up email about the marketing review"

## Policy implemented

1. **stale_trivia**: cancel with `reason="stale_trivia_swept"`.
2. **dev_test_leak**: cancel with `reason="dev_test_leak_purged"`.
3. **recovery_with_retry**: keep all if `retry_count <= 3`. If `retry_count > 3`, fire a single rollup SMS via `failure_recovery.route_recovery`, keep the LAST (newest) task, cancel the rest with `reason="rolled_up"`.
4. **real**: untouched.

Expected outcome on this snapshot: 7 stale_trivia + 10 dev_test_leak = 17 cancelled, 0 escalated, 3 recovery + 1 real = 4 kept waiting.

## UI hint

`max_visible_in_ui` (default 5) is exposed via `app.task_queue.store.max_visible_in_ui()` and the cleanup response so the popover can show "4 waiting" instead of "21 waiting", and only render the freshest 5 cards.
