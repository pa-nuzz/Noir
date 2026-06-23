#!/bin/bash
# Start Celery workers and beat with auto-restart (idempotent — checks by process pattern, not pid file)
set -e

PROJECT_DIR="/Users/suraj/DIA/ida"
VENV="$PROJECT_DIR/venv"
LOG_DIR="/tmp"
cd "$PROJECT_DIR"

start_if_dead() {
    local pattern="$1"
    local cmd="$2"
    if pgrep -f "$pattern" > /dev/null 2>&1; then
        echo "$pattern: already running"
    else
        echo "Starting $pattern..."
        eval "$cmd"
    fi
}

start_if_dead "celery.*worker.*-Q default,low" \
    "nohup $VENV/bin/celery -A core worker -l INFO --concurrency=2 --pool threads -Q default,low -n worker@%h > $LOG_DIR/celery_worker.log 2>&1 &"

start_if_dead "celery.*worker.*-Q critical" \
    "nohup $VENV/bin/celery -A core worker -Q critical --concurrency=1 --pool threads -l INFO -n critical@%h > $LOG_DIR/celery_critical.log 2>&1 &"

start_if_dead "celery.*-A.*core.*beat" \
    "nohup $VENV/bin/celery -A core beat -l INFO > $LOG_DIR/celery_beat.log 2>&1 &"