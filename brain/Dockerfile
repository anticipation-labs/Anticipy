# Anticipy brain worker — production image.
FROM python:3.11-slim
WORKDIR /srv
COPY brain /srv/brain
RUN pip install --no-cache-dir requests httpx
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "brain.supervisor"]
