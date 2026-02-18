# ---- Agent Build ----
FROM python:3.12-slim AS agent

WORKDIR /app/agent

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY agent/pyproject.toml agent/uv.lock* ./
RUN uv sync --no-dev --no-install-project

# Copy source and assets
COPY agent/ .

# Ensure conversation data directory exists
RUN mkdir -p /app/agent/data/conversations

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/agent

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost', 7880)); s.close()" || exit 1

CMD ["uv", "run", "python", "-m", "src.agent"]

# ---- Frontend Build ----
FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .

# Build args for NEXT_PUBLIC_ env vars (baked into static build)
ARG NEXT_PUBLIC_LIVEKIT_URL
ENV NEXT_PUBLIC_LIVEKIT_URL=${NEXT_PUBLIC_LIVEKIT_URL}

RUN npm run build

# ---- Frontend Runtime ----
FROM node:22-slim AS frontend

WORKDIR /app/frontend
COPY --from=frontend-builder /app/frontend/.next ./.next
COPY --from=frontend-builder /app/frontend/node_modules ./node_modules
COPY --from=frontend-builder /app/frontend/package.json .
COPY --from=frontend-builder /app/frontend/public ./public

ENV NODE_ENV=production
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:3000/ || exit 1

CMD ["npm", "start"]
