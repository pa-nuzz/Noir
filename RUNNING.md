# Running MailFlow AI

## Required Services

### 1. PostgreSQL Database
Ensure PostgreSQL is running and the database is created. Check `DB_NAME`, `DB_USER`, `DB_PASSWORD` in your `.env` file.

### 2. Redis Server
MailFlow AI uses Redis as the Celery message broker. Redis must be running before starting Celery.

### 3. Django Development Server

```bash
python manage.py runserver
```

### 4. Celery Worker (REQUIRED for all background tasks)

Without the Celery worker running, these features will BREAK:
- Campaign sending (emails queued but never sent)
- Inbox syncing (new emails never fetched)
- AI auto-reply (drafts never generated)
- Scheduled posts (never published)
- Lock expiration cleanup

**Start the worker:**

```bash
celery -A core worker -l info
```

### 5. Celery Beat Scheduler (REQUIRED for periodic tasks)

Starts the scheduler that triggers periodic tasks like inbox syncing and lock cleanup.

```bash
celery -A core beat -l info
```

## Full Startup Sequence

1. **Ensure PostgreSQL is running**
   ```bash
   brew services start postgresql@14  # macOS with Homebrew
   # OR
   sudo service postgresql start    # Linux
   ```

2. **Ensure Redis is running**
   ```bash
   redis-server
   # OR (if using Homebrew)
   brew services start redis
   ```

3. **Apply any new migrations** (if you haven't already)
   ```bash
   python manage.py migrate
   ```

4. **Start all services** (in separate terminal windows):

   Terminal 1 - Django:
   ```bash
   python manage.py runserver
   ```

   Terminal 2 - Celery Worker:
   ```bash
   celery -A core worker -l info
   ```

   Terminal 3 - Celery Beat:
   ```bash
   celery -A core beat -l info
   ```

## Troubleshooting

### "Inbox stuck at loading" or "Syncing..." stays forever
**Cause:** Celery worker is not running. The sync task is queued but never executed.
**Fix:** Start the Celery worker (`celery -A core worker -l info`).

### Campaign says "sending" but never updates to "sent"
**Cause:** Celery worker not running. Campaign task is queued but never executed.
**Fix:** Start the Celery worker.

### SMTP connected but no emails sent
**Cause:** Campaign send is a Celery task. If worker is down, emails are never sent.
**Fix:** Start the Celery worker.

### AI draft generation stuck at "loading..."
**Cause:** Django messages framework is used for feedback. If the async task (Celery) isn't running, the draft is never generated.
**Fix:** Start the Celery worker.

## Environment Variables (in .env)

Make sure your `.env` file has:
```
DATABASE_URL=postgres://user:password@localhost:5432/mailflow_ai
REDIS_URL=redis://localhost:6379/0
FERNET_KEY=your-fernet-key-here
SECRET_KEY=your-secret-key-here
DEBUG=True
# Set to production domain for tracking
TRACKING_BASE_URL=http://127.0.0.1:8000 - production is https://idadev.techaxis.com.np 
# Optional: use environment-specific SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
```