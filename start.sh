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
cd "$PROJECT_DIR" && nohup $CELERY -A core worker -l INFO --concurrency=2 --pool threads -Q default,low -n worker@%h > /tmp/celery_worker.log 2>&1 &
WPID=$!
disown
echo "  Celery worker PID: $WPID"

# 4. Start Celery beat (scheduler for periodic tasks)
echo "Starting Celery beat..."
cd "$PROJECT_DIR" && nohup $CELERY -A core beat -l INFO > /tmp/celery_beat.log 2>&1 &
BPID=$!
disown
echo "  Celery beat PID: $BPID"

# 5. Start critical queue worker (campaign sends, OAuth refresh)
echo "Starting Celery critical worker..."
cd "$PROJECT_DIR" && nohup $CELERY -A core worker -Q critical --concurrency=1 --pool threads -l INFO -n critical@%h > /tmp/celery_critical.log 2>&1 &
CPID=$!
disown
echo "  Celery critical worker PID: $CPID"

echo ""
echo "=== All services started ==="
echo "Run Django:  $PYTHON manage.py runserver 0.0.0.0:8080"
echo "View logs:   tail -f /tmp/celery_worker.log"
echo "             tail -f /tmp/celery_critical.log"
echo "             tail -f /tmp/celery_beat.log"
echo ""