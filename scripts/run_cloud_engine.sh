#!/usr/bin/env bash
# Run the Anticipy engine LOCALLY with the best-in-world cloud memory ON
# (Gemini embeddings + Neo4j temporal graph). Keys come from .env.local.
# Usage: scripts/run_cloud_engine.sh [PORT]   (default 8790)
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${1:-8790}"
# Use the GOOD Gemini key from .env.local, overriding any stale key exported by ~/.zshrc.
GKEY="$(grep '^GOOGLE_API_KEY=' .env.local | cut -d= -f2-)"
echo "Starting Anticipy engine on :$PORT with cloud memory ON (Gemini + Neo4j)…"
GOOGLE_API_KEY="$GKEY" GEMINI_API_KEY="$GKEY" \
ANTICIPY_EMBED_PROVIDER=gemini ANTICIPY_GRAPH=neo4j \
PYTHONPATH=engine exec engine/.venv/bin/python -m uvicorn --app-dir engine \
  anticipy_engine.main:app --host 127.0.0.1 --port "$PORT"
