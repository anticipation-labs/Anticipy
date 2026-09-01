# Anticipy brain worker — production image.
FROM python:3.11-slim
WORKDIR /srv
COPY brain /srv/brain
# tzdata is NOT optional here even though nothing imports it by name.
# brain/llm.py:32 builds ZoneInfo(ANTICIPY_TZ, default "America/Vancouver") at
# MODULE IMPORT time, and python:3.11-slim ships no system tzdb — so ZoneInfo
# raises ZoneInfoNotFoundError while `import brain.llm` is still running, which
# kills the supervisor before main() exists and leaves Railway reporting a
# RUNNING container with a brain that never started. The pip package is the
# tzdb that zoneinfo falls back to when /usr/share/zoneinfo is absent.
RUN pip install --no-cache-dir requests httpx tzdata boto3
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "brain.supervisor"]
