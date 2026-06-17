#!/usr/bin/env bash

VENV_DIR="$(dirname "$0")/venv"
PYTHON="$VENV_DIR/bin/python"
CELERY="$VENV_DIR/bin/celery"
MANAGE="$PYTHON manage.py"
PROJECT_DIR="$(dirname "$0")"

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

# 3. Start Celery worker (consumes both default and low queues for trending tasks)
echo "Starting Celery worker..."
cd "$PROJECT_DIR" && nohup $CELERY -A core worker -l INFO --concurrency=2 -Q default,low > /tmp/celery_worker.log 2>&1 &
WPID=$!
disown
echo "  Celery worker PID: $WPID"

# 4. Start Celery beat (scheduler for periodic tasks)
echo "Starting Celery beat..."
cd "$PROJECT_DIR" && nohup $CELERY -A core beat -l INFO > /tmp/celery_beat.log 2>&1 &
BPID=$!
disown
echo "  Celery beat PID: $BPID"

echo ""
echo "=== All services started ==="
echo "Run Django:  $PYTHON manage.py runserver 0.0.0.0:8080"
echo "View logs:   tail -f /tmp/celery_worker.log"
echo ""
