#!/bin/bash
# Run the M1 battery against CLEAN state. The owner-card cache returns the first-ever
# decision for a line (idempotent re-ingest) and bypasses _spine_card, so a true
# brain-measurement needs a fresh card index = cleared cards + engine restart.
set -e
cd ~/Anticipy/engine
PID=$(lsof -nP -iTCP:8787 -sTCP:LISTEN -t 2>/dev/null | head -1)
[ -n "$PID" ] && kill "$PID" 2>/dev/null || true
python3 -c "import time;time.sleep(2)"
find . .. -maxdepth 3 -path "*owner_cards/*.json" -delete 2>/dev/null || true
nohup .venv/bin/python -m uvicorn anticipy_engine.main:app --port 8787 --host 127.0.0.1 >/tmp/eng.log 2>&1 &
python3 -c "import time;time.sleep(6)"
curl -s --max-time 8 http://127.0.0.1:8787/health >/dev/null && echo "engine up (fresh card index)"
cd ~/Anticipy && python3 overnight/m1_battery.py
