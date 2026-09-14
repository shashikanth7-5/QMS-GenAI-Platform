FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

# Non-root runtime user — running as root inside the container gives
# code-execution incidents an easier blast radius. UID/GID chosen high
# enough not to collide with typical distro users.
RUN mkdir -p /app/data /app/data/uploads /app/data/chroma_db \
    && groupadd --system --gid 10001 qms \
    && useradd --system --uid 10001 --gid qms --home /app --shell /sbin/nologin qms \
    && chown -R qms:qms /app
USER qms

EXPOSE 5000

# Startup: retry `alembic upgrade head` a few times so Postgres has a chance
# to become healthy on cold start (docker-compose depends_on has the same
# guard, but K8s / ECS may not). Then exec gunicorn.
CMD ["sh", "-c", "case \"$DATABASE_URL\" in sqlite*) python -c \"from database import init_db; init_db()\" ;; *) for i in 1 2 3 4 5; do alembic upgrade head && break || (echo \"alembic retry $i\"; sleep 3); done ;; esac && python -m scripts.bootstrap_pilot_users && exec gunicorn --bind 0.0.0.0:5000 --workers ${WEB_CONCURRENCY:-1} --threads ${WEB_THREADS:-2} --timeout ${WEB_TIMEOUT:-120} --graceful-timeout 30 --access-logfile - --error-logfile - app:app"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail --silent --show-error http://127.0.0.1:5000/healthz || exit 1
