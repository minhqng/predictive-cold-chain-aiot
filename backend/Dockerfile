# ColdGuard backend runtime image (C-W01-02).
# Minimal reproducible Python 3.12 container: locked dependencies via uv,
# one application process (uvicorn), non-root runtime. No test extras,
# no virtualenv copying, no hot-reload mounts.
FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv/backend

COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Pinned installer so the image build itself is reproducible.
RUN pip install --no-cache-dir "uv==0.12.21" \
    && uv sync --locked --no-dev --no-editable \
    && uv cache clean

RUN useradd --system --uid 10001 --create-home app \
    && chown -R app:app /srv/backend

USER app

EXPOSE 8000

CMD [".venv/bin/uvicorn", "coldguard_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
