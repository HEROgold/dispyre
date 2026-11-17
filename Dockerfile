# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder stage — resolve deps with uv, build the venv. No dev dependencies.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Pin uv via its official static-binary image rather than `pip install uv` —
# keeps the builder stage reproducible and avoids bootstrapping pip first.
# Bump this periodically; check the current release with:
#   gh api repos/astral-sh/uv/releases/latest --jq '.tag_name'
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
RUN uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Runtime stage — slim base, just the venv + source, non-root user.
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Flagged by droast/hadolint comparison as worth setting explicitly rather
# than relying on defaults: skip .pyc writes and force unbuffered stdio so
# container logs show up immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Run as a dedicated non-root user rather than the image default (root) —
# also flagged by that same droast/hadolint comparison.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/src /app/src

USER app

ENTRYPOINT ["dispyre"]
