#!/bin/bash
set -e

echo "============================================="
echo "  Talk2DDD Backend Starting"
echo "============================================="

# Run database migrations with retry loop.
# Even though docker-compose waits for the DB health check before starting the
# backend, there can be a brief window between pg_isready and full PostgreSQL
# readiness. Retrying here avoids unnecessary container restarts.
echo "[migrations] Running alembic upgrade head..."
MAX_RETRIES=30
RETRY_INTERVAL=2
n=0
until alembic upgrade head; do
    n=$((n + 1))
    if [ "$n" -ge "$MAX_RETRIES" ]; then
        echo "[migrations] ERROR: Migration failed after ${MAX_RETRIES} attempts. Exiting."
        exit 1
    fi
    echo "[migrations] Attempt ${n}/${MAX_RETRIES} failed, retrying in ${RETRY_INTERVAL}s..."
    sleep "$RETRY_INTERVAL"
done
echo "[migrations] Complete."

echo "[server] Starting uvicorn on 0.0.0.0:8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
