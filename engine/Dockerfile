# Anticipy hosted engine (engine-context build; service root = engine/). API-only: the static web UI
# is served by Vercel, and main.py guards the web mount, so no web/ needed here. Binds 0.0.0.0:$PORT.
FROM python:3.13-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.cloud.txt .
RUN pip install --no-cache-dir -r requirements.cloud.txt
COPY anticipy_engine ./anticipy_engine
ENV PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["sh", "-c", "uvicorn anticipy_engine.main:app --host 0.0.0.0 --port ${PORT:-8787}"]
