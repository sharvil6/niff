# syntax=docker/dockerfile:1

# 1. Build the web page.
FROM node:26-trixie-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY web/ ./
RUN npm run build

# 2. Install Niff and its dependencies into a virtual environment.
FROM python:3.13-slim-trixie AS build
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dependencies first, in their own layer, so a code change doesn't reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# 3. Runtime: only the virtual environment and the built page, run as a non-root user.
FROM python:3.13-slim-trixie
RUN groupadd --system niff \
    && useradd --system --gid niff --no-create-home niff \
    && mkdir /data \
    && chown niff:niff /data
COPY --from=build /app/.venv /app/.venv
COPY --from=web /web/dist /app/web/dist
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    NIFF_DB_PATH=/data/niff.db \
    NIFF_WEB_DIST=/app/web/dist
WORKDIR /app
USER niff
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
# One worker on purpose: the hourly sync runs inside the app process, so more workers would sync
# more than once.
CMD ["uvicorn", "niff.main:app", "--host", "0.0.0.0", "--port", "8000"]
