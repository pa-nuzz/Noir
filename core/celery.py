import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'run-scheduled-campaigns-every-minute': {
        'task': 'apps.campaigns.tasks.run_scheduled_campaigns_task',
        'schedule': crontab(minute='*'),
        'options': {'queue': 'critical'},
    },
    'process-workflows-every-5-minutes': {
        'task': 'apps.automations.tasks.process_workflows_task',
        'schedule': crontab(minute='*/5'),
        'options': {'queue': 'default'},
    },
    'sync-inboxes-every-10-minutes': {
        'task': 'apps.inbox.tasks.sync_all_inboxes_task',
        'schedule': crontab(minute='*/10'),
        'options': {'queue': 'default'},
    },
    'publish-scheduled-posts-every-minute': {
        'task': 'apps.social_accounts.tasks.publish_scheduled_posts',
        'schedule': crontab(minute='*'),
        'options': {'queue': 'default'},
    },
    'release-expired-locks-every-5-minutes': {
        'task': 'apps.locks.tasks.release_expired_locks',
        'schedule': crontab(minute='*/5'),
        'options': {'queue': 'default'},
    },
}
