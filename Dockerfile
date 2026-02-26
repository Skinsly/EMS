# syntax=docker/dockerfile:1.7
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app-runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG UID=10001
ARG GID=10001
RUN groupadd --system --gid ${GID} appgroup \
    && useradd --system --uid ${UID} --gid appgroup --create-home appuser

COPY backend/requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r /app/requirements.txt

COPY backend/app /app/app
COPY --from=frontend-builder /frontend/dist /app/frontend-dist

RUN mkdir -p /app/data /app/uploads \
    && chown -R appuser:appgroup /app

EXPOSE 8000

HEALTHCHECK --interval=120s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
