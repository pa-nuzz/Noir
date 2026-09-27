# Running MailFlow locally

## First-time setup

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` only when you need local secrets or a configured
PostgreSQL database. Without `DB_NAME`, Django uses `db.sqlite3` automatically.
When `DB_NAME` is set, all PostgreSQL settings must point to a reachable
database.

## Start Django

```bash
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000.

## Optional background workers

Redis is required for Celery tasks. Start it with your operating system's
service manager, then run each process in its own terminal:

```bash
celery -A core worker -l info
celery -A core beat -l info
```

The web application does not require Celery for ordinary page loads. Campaign
sending, inbox synchronization, scheduled work, and AI background jobs require
the worker to be running.

## Troubleshooting

- If Django reports a PostgreSQL timeout, check `DB_HOST`, `DB_PORT`, and the
  database firewall. Remove `DB_NAME` from `.env` to use a local SQLite
  database instead.
- If a task remains queued, verify Redis and the Celery worker.
- If the first migration on a fresh checkout fails, remove the local
  `db.sqlite3` and run `python manage.py migrate` again.
