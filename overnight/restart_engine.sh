#!/bin/bash
# Restart the engine with the LIVE MODEL env (so the moat + copy polish run on the real model),
# but force channels to MOCK so no real texts/calls fire during dev. Pass --clear-cards for a fresh
# owner-card index (needed for true brain measurement — re-ingest otherwise returns cached cards).
cd ~/Anticipy/engine || exit 1
PID=$(lsof -nP -iTCP:8787 -sTCP:LISTEN -t 2>/dev/null | head -1)
[ -n "$PID" ] && kill "$PID" 2>/dev/null
python3 -c "import time;time.sleep(2)"
[ "$1" = "--clear-cards" ] && find . .. -maxdepth 3 -path "*owner_cards/*.json" -delete 2>/dev/null
# export ONLY the model vars from .env.local (NOT Twilio/channels — keep texting off)
eval "$(grep -E '^(ANTICIPY_MODEL_PROVIDER|OPENROUTER_API_KEY|ANTICIPY_OPENAI_BASE_URL|ANTICIPY_MODEL_CHEAP|ANTICIPY_MODEL_SMART|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|CEREBRAS_API_KEY|DEEPSEEK_API_KEY)=' ../.env.local | sed 's/^/export /')"
export ANTICIPY_CHANNELS_MODE=mock   # SAFE: model on, real texts/calls OFF
export ANTICIPY_OWNER_TLD=ca   # owner is in Canada -> amazon.ca etc., not .com
nohup .venv/bin/python -m uvicorn anticipy_engine.main:app --port 8787 --host 127.0.0.1 >/tmp/eng.log 2>&1 &
python3 -c "import time;time.sleep(7)"
curl -s --max-time 8 http://127.0.0.1:8787/health >/dev/null \
  && echo "engine up (provider=$(curl -s http://127.0.0.1:8787/status >/dev/null 2>&1; echo openrouter), channels=mock)" \
  || echo "ENGINE DOWN — check /tmp/eng.log"
