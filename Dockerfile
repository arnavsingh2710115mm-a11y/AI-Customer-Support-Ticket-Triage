# Build React separately from the Python API runtime.
FROM node:22-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS application
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . ./
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Keep application files read-only; only demo review-log storage is writable.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/logs \
    && chown appuser:appuser /app/logs
USER appuser
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
