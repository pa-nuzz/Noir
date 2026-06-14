#!/usr/bin/env bash
set -e

VENV_DIR="$(dirname "$0")/venv"
PYTHON="$VENV_DIR/bin/python"
MANAGE="$PYTHON manage.py"

echo "=== Intelligent Digital Automation AI — Starting Services ==="

# 1. Start Redis (if not running)
if ! redis-cli ping &>/dev/null; then
    echo "Starting Redis..."
    brew services start redis 2>/dev/null || redis-server --daemonize yes
    sleep 1
fi
echo "✓ Redis is running"

# 2. Kill old celery processes
pkill -f "celery -A core" 2>/dev/null || true

# 3. Start Celery worker
echo "Starting Celery worker..."
nohup $PYTHON -m celery -A core worker -l INFO --concurrency=2 > /tmp/celery_worker.log 2>&1 &
echo "  Celery worker PID: $!"

# 4. Start Celery beat (scheduler for periodic tasks)
echo "Starting Celery beat..."
nohup $PYTHON -m celery -A core beat -l INFO > /tmp/celery_beat.log 2>&1 &
echo "  Celery beat PID: $!"

echo ""
echo "=== All services started ==="
echo "Run Django:  $PYTHON manage.py runserver 0.0.0.0:8080"
echo "View logs:   tail -f /tmp/celery_worker.log"
echo ""
