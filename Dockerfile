# ---- Builder: Abhängigkeiten in ein eigenes Prefix installieren ----
FROM python:3.12-slim-bookworm AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime: schlankes Image ohne Build-Tools, Non-Root-User ----
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

RUN groupadd --system --gid 1001 app && \
    useradd --system --uid 1001 --gid app --no-create-home app

COPY --from=builder /install /usr/local
COPY --chown=app:app app ./app
COPY --chown=app:app knowledge ./knowledge
RUN mkdir -p /app/data /app/site && chown app:app /app/data /app/site

# Versionskennung (in GitHub Actions = Commit-SHA), im Dashboard unter "System" sichtbar
ARG APP_VERSION=lokal
ENV APP_VERSION=$APP_VERSION \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
