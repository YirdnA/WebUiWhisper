FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libmagic1 is required by python-magic (upload sniffing).
# tini gives clean PID-1 signal handling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 tini ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# State dir needs to be writable by uid 1000 even with a read-only root FS,
# so production mounts a named volume here. Dev compose binds a local dir.
RUN mkdir -p /var/lib/webuiwhisper \
    && chown -R 1000:1000 /var/lib/webuiwhisper /app

USER 1000:1000

EXPOSE 8001

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", \
     "--proxy-headers", "--forwarded-allow-ips=*", "--no-server-header"]
