# ---- Agent Build ----
FROM python:3.12-slim AS agent

WORKDIR /app/agent

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first for layer caching
COPY agent/pyproject.toml .
RUN uv sync --no-dev --no-install-project

# Copy source
COPY agent/ .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/agent

CMD ["uv", "run", "python", "-m", "src.agent"]

# ---- Frontend Build ----
FROM node:22-slim AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
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

CMD ["npm", "start"]
