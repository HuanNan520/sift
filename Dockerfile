FROM python:3.12-slim

# Sift backend · self-host image
# Build: docker build -t sift:latest .
# Run:   docker compose up -d
LABEL org.opencontainers.image.source="https://github.com/HuanNan520/sift"
LABEL org.opencontainers.image.description="Sift · AI 自治的个人长期记忆底座 · self-host"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OS deps (build-time + runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        ca-certificates \
        ffmpeg \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (single layer for cacheability)
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Source
COPY tools/ /app/tools/

# Data lives in a volume so the host can back it up
VOLUME ["/data"]
ENV SIFT_USERS_ROOT=/data/users \
    SIFT_DB=/data/sift.sqlite \
    SIFT_BASE_URL=http://localhost:8000

EXPOSE 8000

# tini for proper signal handling under docker-compose stop
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "sift-api:app", \
     "--app-dir", "/app/tools", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
