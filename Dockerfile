# Anticipy hosted engine — one container = one user's engine (the per-user-instance model).
# Slim: no whisper/torch (cloud audio is via Twilio/Deepgram). Binds 0.0.0.0:$PORT for the public deploy
# (Railway/Hetzner inject $PORT). All secrets come from the platform env, never baked in.
FROM python:3.13-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# deps first (layer-cached)
COPY engine/requirements.cloud.txt ./engine/requirements.cloud.txt
RUN pip install --no-cache-dir -r engine/requirements.cloud.txt

# app code + the static web UI the engine can serve same-origin
COPY engine/anticipy_engine ./engine/anticipy_engine
COPY web ./web

ENV PYTHONUNBUFFERED=1
WORKDIR /app/engine
EXPOSE 8787
# $PORT from the platform; fall back to 8787 locally. 0.0.0.0 so the platform can route to it.
CMD ["sh", "-c", "uvicorn anticipy_engine.main:app --host 0.0.0.0 --port ${PORT:-8787}"]
