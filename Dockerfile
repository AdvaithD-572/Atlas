FROM node:24.21.0-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20 AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm test && npm run build

FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS dependencies
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.19
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM dependencies AS verification
RUN uv sync --frozen --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
COPY atlas/ /app/atlas/
COPY tests/ /app/tests/
COPY scripts/ /app/scripts/
COPY evaluation/ /app/evaluation/
COPY docs/ /app/docs/
CMD ["python", "-m", "scripts.verify"]

FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ATLAS_FRONTEND_DIR=/app/static
COPY --from=dependencies /app/.venv /app/.venv
COPY atlas/ /app/atlas/
COPY --from=frontend /frontend/dist /app/static
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=8s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=7)"
CMD ["python", "-m", "uvicorn", "atlas.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--limit-concurrency", "16", "--timeout-keep-alive", "5"]
