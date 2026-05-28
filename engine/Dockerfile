FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

# xvfb for headful Chromium; CJK + emoji fonts so non-ASCII pages don't tofu
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    fonts-liberation \
    fonts-noto \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Persistent profile dir (mount a volume here in production)
RUN mkdir -p /data/engine_profiles && chmod 777 /data/engine_profiles
ENV BROWSER_PROFILE_BASE=/data/engine_profiles

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Install patchright browsers (used by browser-use)
RUN python -m patchright install chromium
# Install playwright browsers (fallback)
RUN python -m playwright install chromium 2>/dev/null || true

COPY . .

EXPOSE 8000
CMD ["sh", "start.sh"]
