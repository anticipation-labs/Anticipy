# Anticipy Engine ("the brain")

Local-first hub. Binds to `127.0.0.1:8787` (override with `ANTICIPY_ENGINE_PORT`;
8000 is avoided because it's commonly taken by other local services). The SwiftUI
app and the browser extension are clients of this engine; nothing thinks on its
own — everything routes through here.

## Setup

```bash
cd engine
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python -m uvicorn --app-dir . anticipy_engine.main:app --host 127.0.0.1 --port 8787
```

## Test (Room 1 — health)

```bash
bash scripts/health_check.sh
```

Expected: `{"status":"ok",...}` with `HTTP 200`.

## Rooms (scaffold)

Room 1 (this) exposes `/health` only. Capture, model, memory, live-memory, the
proactive loop, the action layer, and channels attach as routers in later rooms
without changing the `/health` contract.
