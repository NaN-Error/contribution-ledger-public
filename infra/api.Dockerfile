FROM python:3.13.14-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY apps/api/requirements.lock ./requirements.lock
RUN python -m pip install --no-cache-dir pip==26.2 \
    && python -m pip install --no-cache-dir --no-deps -r requirements.lock && python -m pip check
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lib/contribution-ledger/evidence \
    && chown appuser:appuser /var/lib/contribution-ledger/evidence \
    && chmod 700 /var/lib/contribution-ledger/evidence
RUN mkdir -p /var/lib/contribution-ledger/ai-credentials /var/lib/contribution-ledger/ai-master \
    && chown appuser:appuser /var/lib/contribution-ledger/ai-credentials /var/lib/contribution-ledger/ai-master \
    && chmod 700 /var/lib/contribution-ledger/ai-credentials /var/lib/contribution-ledger/ai-master
RUN mkdir -p /var/lib/contribution-ledger/auth-master \
    && chown appuser:appuser /var/lib/contribution-ledger/auth-master \
    && chmod 700 /var/lib/contribution-ledger/auth-master
COPY --chown=appuser:appuser apps/api/ ./
USER appuser
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--no-proxy-headers"]

FROM base AS test
USER root
COPY apps/api/requirements-dev.lock ./requirements-dev.lock
RUN python -m pip install --no-cache-dir --no-deps -r requirements-dev.lock && python -m pip check
# Tests inspect operator scripts and fixtures using the actual monorepo layout.
# Keep this extra source only in the test stage, never the runtime image.
COPY --chown=appuser:appuser . /repo/
WORKDIR /repo/apps/api
ENV PYTHONPATH=/repo/apps/api PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
USER appuser
CMD ["python", "-m", "pytest", "-q"]

# Explicit optional worker image. The manual API never imports Celery.
FROM base AS jobs
USER root
COPY apps/api/requirements-jobs.lock ./requirements-jobs.lock
RUN python -m pip install --no-cache-dir --no-deps -r requirements-jobs.lock && python -m pip check
USER appuser
CMD ["python", "-m", "app.workers.scheduler", "--loop"]
