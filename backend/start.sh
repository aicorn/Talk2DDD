#!/bin/bash
set -e

# Run database migrations before starting the server
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete. Starting server..."

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
