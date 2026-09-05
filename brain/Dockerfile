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
# ONE image, two roles, chosen at runtime so this file can be BOTH the live
# Railway `worker` image AND the Cloudflare per-owner container image without a
# flag day (BRAIN-ON-CONTAINERS.md §8.2 / §10.4):
#   * Railway runs the fleet supervisor — no ANTICIPY_OWNER_REF in its env, so
#     the dispatch falls through to `brain.supervisor` exactly as before.
#   * A Cloudflare OwnerBrain container is started by the DO with
#     ANTICIPY_OWNER_REF set (migration/workers/brain/src/index.ts envFor), so
#     the dispatch runs `brain.container_entry`: pull that owner's memory.db from
#     R2, then exec the unchanged worker.
# This removes the "one-way Dockerfile:14 flip" risk: the same committed image
# is correct in both places, decided by the presence of the per-owner ref.
CMD ["sh", "-c", "if [ -n \"$ANTICIPY_OWNER_REF\" ]; then exec python -m brain.container_entry; else exec python -m brain.supervisor; fi"]
